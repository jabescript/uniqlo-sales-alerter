"""Application entry-point — FastAPI app, lifespan, and scheduler wiring."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from uniqlo_sales_alerter.api.routes import _redact_secrets, router
from uniqlo_sales_alerter.config import AppConfig, load_config, save_config
from uniqlo_sales_alerter.models.products import SaleCheckResult
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker
from uniqlo_sales_alerter.settings_ui import build_settings_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class AppState:
    config: AppConfig
    sale_checker: SaleChecker
    dispatcher: NotificationDispatcher
    scheduler: AsyncIOScheduler = field(default_factory=AsyncIOScheduler)


state: AppState  # module-level reference set during lifespan


async def run_sale_check(app_state: AppState) -> SaleCheckResult:
    """Execute a sale check and dispatch notifications."""
    try:
        result = await app_state.sale_checker.check()
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


def _schedule_job(app_state: AppState) -> None:
    """Register a periodic sale check with the async scheduler."""

    async def _job() -> None:
        await run_sale_check(app_state)

    interval = app_state.config.uniqlo.check_interval_minutes
    app_state.scheduler.add_job(_job, "interval", minutes=interval, id="sale_check")
    app_state.scheduler.start()
    logger.info("Scheduled sale checks every %d minute(s)", interval)


async def reload_config() -> AppConfig:
    """Reload configuration from YAML (without re-applying env overrides)."""
    global state
    state.scheduler.remove_all_jobs()
    await state.sale_checker.close()

    config = load_config(apply_env_overrides=False)
    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    scheduler = state.scheduler
    state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
        scheduler=scheduler,
    )

    async def _job() -> None:
        await run_sale_check(state)

    interval = config.uniqlo.check_interval_minutes
    scheduler.add_job(_job, "interval", minutes=interval, id="sale_check")
    logger.info("Config reloaded — rescheduled checks every %d minute(s)", interval)
    return config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global state
    config = load_config()
    save_config(config)

    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    state = AppState(config=config, sale_checker=checker, dispatcher=dispatcher)

    _schedule_job(state)

    try:
        await run_sale_check(state)
    except Exception:
        logger.exception("Initial sale check failed — will retry on schedule")

    yield

    state.scheduler.shutdown(wait=False)
    await state.sale_checker.close()
    logger.info("Scheduler stopped")


app = FastAPI(
    title="Uniqlo Sales Alerter",
    description="Monitors Uniqlo sales and surfaces deals matching your criteria.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page() -> HTMLResponse:
    """Serve the configuration web UI."""
    config_data = _redact_secrets(state.config.model_dump())
    return HTMLResponse(build_settings_page(config_data))
