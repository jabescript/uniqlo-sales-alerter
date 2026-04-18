"""Application entry-point — FastAPI app, lifespan, and scheduler wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from uniqlo_sales_alerter.api.routes import _redact_secrets, actions_router, router
from uniqlo_sales_alerter.clients.uniqlo import UniqloClient
from uniqlo_sales_alerter.config import AppConfig, load_config, save_config
from uniqlo_sales_alerter.models.products import (
    SaleCheckResult,
    UniqloProduct,
    build_product_url,
)
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker
from uniqlo_sales_alerter.settings_ui import build_settings_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class AppState:
    config: AppConfig
    sale_checker: SaleChecker
    dispatcher: NotificationDispatcher
    scheduler: AsyncIOScheduler = field(default_factory=AsyncIOScheduler)
    last_check_at: datetime | None = None


def _in_quiet_hours(config: AppConfig) -> bool:
    """Return ``True`` if the current local time falls within the configured quiet window."""
    quiet = config.quiet_hours
    if not quiet.enabled:
        return False
    start_h, start_m = map(int, quiet.start.split(":"))
    end_h, end_m = map(int, quiet.end.split(":"))
    start = time(start_h, start_m)
    end = time(end_h, end_m)
    now = datetime.now().time()
    if start <= end:
        return start <= now < end
    # Wraps midnight (e.g. 23:00 → 06:00)
    return now >= start or now < end


def _find_color_name(l2s: list[dict], color_code: str) -> str:
    """Look up the human-readable colour name from L2 variant data."""
    for l2 in l2s:
        color = l2.get("color", {})
        if color.get("displayCode") == color_code:
            return color.get("name", "")
    return ""


def _find_size_name(product: UniqloProduct, size_code: str) -> str:
    """Look up the human-readable size name from a product's size list."""
    for sz in product.sizes:
        if sz.display_code == size_code:
            return sz.name
    return ""


async def _enrich_config(config: AppConfig, client: UniqloClient) -> bool:
    """Fill in missing metadata for watched variants and ignored products.

    Resolves product names, human-readable colour/size names, and
    reconstructs missing URLs.  Returns ``True`` when at least one entry
    was updated (caller should persist the config).
    """
    base = config.product_page_base

    incomplete_variants = [
        wv for wv in config.filters.watched_variants
        if wv.id and (
            not wv.name or not wv.color_name
            or not wv.size_name or not wv.url
        )
    ]
    incomplete_ignored = [
        ip for ip in config.filters.ignored_products
        if ip.id and (not ip.name or not ip.url)
    ]
    if not incomplete_variants and not incomplete_ignored:
        return False

    # Batch-fetch product listings for all products that need enrichment.
    all_ids = list(
        {wv.id for wv in incomplete_variants}
        | {ip.id for ip in incomplete_ignored}
    )
    products = await client.fetch_products_by_ids(all_ids)
    product_by_id = {p.product_id.upper(): p for p in products}

    # Fetch L2 variant data (colour names) for products that need it.
    l2_keys = {
        (wv.id, wv.price_group)
        for wv in incomplete_variants
        if not wv.color_name or not wv.size_name
    }
    l2_by_product: dict[str, list[dict]] = {}
    for pid, pg in l2_keys:
        l2_by_product[pid.upper()] = await client.fetch_product_l2s(pid, pg)

    changed = False

    for ip in incomplete_ignored:
        prod = product_by_id.get(ip.id.upper())
        if prod and not ip.name:
            ip.name = prod.name
            changed = True
        if not ip.url:
            pg = prod.price_group if prod else "00"
            ip.url = build_product_url(base, ip.id, pg)
            changed = True

    for wv in incomplete_variants:
        prod = product_by_id.get(wv.id.upper())

        if prod and not wv.name:
            wv.name = prod.name
            changed = True

        if not wv.url:
            wv.url = build_product_url(
                base, wv.id, wv.price_group, wv.color, wv.size,
            )
            changed = True

        if not wv.size_name and prod:
            wv.size_name = _find_size_name(prod, wv.size)
            changed = changed or bool(wv.size_name)

        if not wv.color_name:
            l2s = l2_by_product.get(wv.id.upper(), [])
            wv.color_name = _find_color_name(l2s, wv.color)
            changed = changed or bool(wv.color_name)

    if changed:
        logger.debug(
            "Enriched metadata for %d watched variant(s) "
            "and %d ignored product(s)",
            len(incomplete_variants), len(incomplete_ignored),
        )
    return changed


async def run_sale_check(app_state: AppState) -> SaleCheckResult:
    """Execute a sale check and dispatch notifications."""
    try:
        result = await app_state.sale_checker.check()
        app_state.last_check_at = datetime.now()
        logger.info(
            "Sale check complete — %d matching deals (%d new)",
            len(result.matching_deals),
            len(result.new_deals),
        )

        notify_on = app_state.config.notifications.notify_on
        deals_to_notify = (
            result.matching_deals if notify_on == "every_check" else result.new_deals
        )
        if deals_to_notify:
            await app_state.dispatcher.dispatch(deals_to_notify)

        return result

    except Exception:
        logger.exception("Sale check failed")
        raise


def _add_check_job(app_state: AppState) -> None:
    """Register periodic and/or fixed-time sale checks with the scheduler."""

    async def _interval_job() -> None:
        if _in_quiet_hours(app_state.config):
            logger.debug("Quiet hours active (%s – %s) — skipping periodic check",
                         app_state.config.quiet_hours.start,
                         app_state.config.quiet_hours.end)
            return
        interval = app_state.config.uniqlo.check_interval_minutes
        if (
            app_state.last_check_at
            and datetime.now() - app_state.last_check_at
            < timedelta(minutes=interval * 0.8)
        ):
            logger.debug(
                "Skipping periodic check — a scheduled check ran recently",
            )
            return
        await run_sale_check(app_state)

    async def _scheduled_job() -> None:
        await run_sale_check(app_state)

    interval = app_state.config.uniqlo.check_interval_minutes
    if interval > 0:
        app_state.scheduler.add_job(
            _interval_job, "interval", minutes=interval,
            id="sale_check_interval",
        )
        logger.info("Scheduled periodic checks every %d minute(s)", interval)
    else:
        logger.info("Periodic checks disabled (check_interval_minutes=0)")

    for check_time in app_state.config.uniqlo.scheduled_checks:
        hour, minute = check_time.split(":")
        app_state.scheduler.add_job(
            _scheduled_job, "cron",
            hour=int(hour), minute=int(minute),
            id=f"sale_check_{check_time}",
        )
        logger.info("Scheduled fixed check at %s", check_time)



async def _try_enrich(config: AppConfig, client: UniqloClient) -> None:
    """Enrich watched/ignored metadata; save config if anything changed."""
    try:
        if await _enrich_config(config, client):
            save_config(config)
    except Exception:
        logger.warning("Watched-variant enrichment failed — will retry later")


async def reload_config(app: FastAPI) -> AppConfig:
    """Reload configuration from YAML (without re-applying env overrides)."""
    current: AppState = app.state.app_state
    current.scheduler.remove_all_jobs()
    await current.sale_checker.close()

    config = load_config(apply_env_overrides=False)
    checker = SaleChecker(config)
    await _try_enrich(config, checker.http_client)

    dispatcher = NotificationDispatcher(config)
    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=current.scheduler,
    )

    _add_check_job(app.state.app_state)
    logger.info("Config reloaded")
    return config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = load_config()
    save_config(config)

    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    app.state.app_state = AppState(
        config=config, sale_checker=checker, dispatcher=dispatcher,
    )

    await _try_enrich(config, checker.http_client)

    app_state: AppState = app.state.app_state
    _add_check_job(app_state)
    app_state.scheduler.start()

    if config.notifications.check_on_startup:
        try:
            await run_sale_check(app_state)
        except Exception:
            logger.exception("Initial sale check failed — will retry on schedule")
    else:
        logger.info("Startup check disabled (check_on_startup=false)")

    yield

    app_state = app.state.app_state
    app_state.scheduler.shutdown(wait=False)
    await app_state.sale_checker.close()
    logger.info("Scheduler stopped")


app = FastAPI(
    title="Uniqlo Sales Alerter",
    description="Monitors Uniqlo sales and surfaces deals matching your criteria.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
app.include_router(actions_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """Serve the configuration web UI."""
    app_state: AppState = request.app.state.app_state
    config_data = _redact_secrets(app_state.config.model_dump())
    return HTMLResponse(build_settings_page(config_data))
