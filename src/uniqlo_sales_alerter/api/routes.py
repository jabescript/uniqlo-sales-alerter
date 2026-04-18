"""FastAPI REST endpoints."""

from __future__ import annotations

import html
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import HTMLResponse

from uniqlo_sales_alerter.models.products import SaleCheckResult, SaleItem

router = APIRouter(prefix="/api/v1")
actions_router = APIRouter(prefix="/actions")

_NO_RESULT = HTTPException(
    status_code=503, detail="No sale check has been run yet",
)

_SECRET_PATHS: list[list[str]] = [
    ["notifications", "channels", "telegram", "bot_token"],
    ["notifications", "channels", "email", "smtp_password"],
]


def _walk_dict(data: dict, path: list[str]) -> tuple[dict, str]:
    """Traverse *data* along *path* and return ``(parent_dict, leaf_key)``."""
    node = data
    for segment in path[:-1]:
        node = node.get(segment, {})
    return node, path[-1]


def _redact_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Replace secret values with ``'***'`` for safe external display."""
    import copy
    redacted = copy.deepcopy(data)
    for path in _SECRET_PATHS:
        node, key = _walk_dict(redacted, path)
        if node.get(key):
            node[key] = "***"
    return redacted


def _restore_secrets(body: dict[str, Any], current: object) -> None:
    """Replace ``'***'`` placeholders in *body* with real values from *current*."""
    for path in _SECRET_PATHS:
        node, key = _walk_dict(body, path)
        if node.get(key) == "***":
            src: Any = current
            for segment in path:
                src = getattr(src, segment, "")
            node[key] = src


def _latest_result() -> SaleCheckResult:
    from uniqlo_sales_alerter.main import state

    result = state.sale_checker.last_result
    if result is None:
        raise _NO_RESULT
    return result


@router.get("/sales", response_model=SaleCheckResult)
async def get_sales(
    gender: str | None = Query(
        None, description="Filter by gender (men/women/unisex)",
    ),
    min_discount: float | None = Query(
        None, ge=0, le=100, description="Override minimum discount %",
    ),
) -> SaleCheckResult:
    """Return the latest cached sale-check results, optionally filtered."""
    result = _latest_result()
    deals = result.matching_deals

    if gender is not None:
        gender_upper = gender.upper()
        deals = [
            d for d in deals
            if d.gender.upper() in (gender_upper, "UNISEX")
        ]
    if min_discount is not None:
        deals = [d for d in deals if d.discount_percentage >= min_discount]

    deal_ids = {d.product_id for d in deals}
    return SaleCheckResult(
        checked_at=result.checked_at,
        total_products_scanned=result.total_products_scanned,
        total_on_sale=result.total_on_sale,
        matching_deals=deals,
        new_deals=[
            d for d in result.new_deals if d.product_id in deal_ids
        ],
    )


@router.post("/sales/check", response_model=SaleCheckResult)
async def trigger_check() -> SaleCheckResult:
    """Trigger an immediate sale check."""
    from uniqlo_sales_alerter.main import run_sale_check, state

    return await run_sale_check(state)


@router.get("/products/{product_id}", response_model=SaleItem)
async def get_product(product_id: str) -> SaleItem:
    """Look up a specific product in the latest results."""
    result = _latest_result()
    for deal in result.matching_deals:
        if deal.product_id == product_id:
            return deal
    raise HTTPException(
        status_code=404,
        detail=f"Product {product_id} not found in current deals",
    )


@router.get("/config")
async def get_config() -> dict[str, Any]:
    """Return the active configuration (secrets are redacted)."""
    from uniqlo_sales_alerter.main import state

    return _redact_secrets(state.config.model_dump())


@router.put("/config")
async def update_config(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate, persist, and reload configuration."""
    from uniqlo_sales_alerter.config import AppConfig, save_config
    from uniqlo_sales_alerter.main import reload_config, state

    _restore_secrets(body, state.config)

    try:
        config = AppConfig.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_config(config)
    await reload_config()

    return {
        "status": "ok",
        "message": "Configuration saved and reloaded",
        "config": _redact_secrets(config.model_dump()),
    }


# ---------------------------------------------------------------------------
# Browser action endpoints (GET for link compatibility)
# ---------------------------------------------------------------------------

def _action_page(title: str, body: str) -> HTMLResponse:
    """Return a minimal styled confirmation page (*body* is pre-escaped)."""
    safe_title = html.escape(title)
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{safe_title}</title>
<style>
body{{font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;
background:#f2f2f2;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;color:#333}}
.card{{background:#fff;border-radius:6px;padding:40px 48px;text-align:center;
box-shadow:0 2px 12px rgba(0,0,0,.08);max-width:460px}}
h1{{color:#ED1D24;font-size:1.3rem;margin-bottom:12px}}
p{{color:#555;font-size:.95rem;line-height:1.5}}
</style></head><body><div class="card">
<h1>{safe_title}</h1><p>{body}</p>
<p style="margin-top:18px;font-size:.8rem;color:#999">
You can close this tab.</p>
</div></body></html>"""
    return HTMLResponse(page)


async def _resolve_name(product_id: str) -> str | None:
    """Fetch product name from the Uniqlo API. Returns ``None`` if not found."""
    from uniqlo_sales_alerter.main import state

    products = await state.sale_checker.http_client.fetch_products_by_ids(
        [product_id],
    )
    return products[0].name if products else None


@router.get("/products/{product_id}/verify")
async def verify_product(product_id: str) -> dict[str, Any]:
    """Check if a product exists in the Uniqlo API and return its name."""
    name = await _resolve_name(product_id)
    if name is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product {product_id} not found in the Uniqlo catalogue",
        )
    return {"product_id": product_id, "name": name}


async def _save_and_reload(data: dict) -> None:
    """Validate, persist, and reload from a raw config dict."""
    from uniqlo_sales_alerter.config import AppConfig, save_config
    from uniqlo_sales_alerter.main import reload_config

    config = AppConfig.model_validate(data)
    save_config(config)
    await reload_config()


@actions_router.get("/ignore/{product_id}")
async def action_ignore(
    product_id: str,
    name: str = Query(""),
) -> HTMLResponse:
    """Add a product to the ignore list (browser-friendly)."""
    from uniqlo_sales_alerter.main import state

    current = state.config
    pid_upper = product_id.upper()
    if any(p.id.upper() == pid_upper for p in current.filters.ignored_products):
        return _action_page(
            "Already ignored",
            f"<b>{html.escape(name or product_id)}</b> is already on your "
            "ignore list.",
        )

    if not name:
        name = await _resolve_name(product_id) or ""
    if not name:
        return _action_page(
            "Product not found",
            f"Could not find <b>{html.escape(product_id)}</b> in the Uniqlo "
            "catalogue. Check the product ID or URL and try again.",
        )

    data = current.model_dump()
    data["filters"]["ignored_products"].append(
        {"id": product_id, "name": name},
    )
    await _save_and_reload(data)

    return _action_page(
        "Product ignored",
        f"<b>{html.escape(name)}</b> has been added to your ignore list.",
    )


@actions_router.get("/unwatch/{product_id}")
async def action_unwatch(
    product_id: str,
    name: str = Query(""),
) -> HTMLResponse:
    """Remove a product from the watch list (browser-friendly)."""
    from uniqlo_sales_alerter.main import state

    current = state.config
    pid_upper = product_id.upper()
    before = len(current.filters.watched_variants)
    kept = [
        wv for wv in current.filters.watched_variants
        if wv.id.upper() != pid_upper
    ]

    if len(kept) == before:
        return _action_page(
            "Not watched",
            f"<b>{html.escape(name or product_id)}</b> is not on your "
            "watch list.",
        )

    data = current.model_dump()
    data["filters"]["watched_variants"] = [
        wv.model_dump() for wv in kept
    ]
    await _save_and_reload(data)

    display = html.escape(name or product_id)
    return _action_page(
        "Variant unwatched",
        f"<b>{display}</b> has been removed from your watch list.",
    )


@actions_router.get("/watch/{product_id}")
async def action_watch(
    product_id: str,
    name: str = Query(""),
    url: str = Query(""),
) -> HTMLResponse:
    """Add a variant to the watch list (browser-friendly)."""
    from uniqlo_sales_alerter.config import parse_uniqlo_url
    from uniqlo_sales_alerter.main import state

    fields = parse_uniqlo_url(url) if url else {}
    color = fields.get("color", "")
    size = fields.get("size", "")
    pid_upper = product_id.upper()

    current = state.config
    if any(
        wv.id.upper() == pid_upper
        and wv.color == color and wv.size == size
        for wv in current.filters.watched_variants
    ):
        return _action_page(
            "Already watched",
            f"<b>{html.escape(name or product_id)}</b> is already on your "
            "watch list.",
        )

    if not name:
        name = await _resolve_name(product_id) or ""
    if not name:
        return _action_page(
            "Product not found",
            f"Could not find <b>{html.escape(product_id)}</b> in the Uniqlo "
            "catalogue. Check the product URL and try again.",
        )

    entry: dict = {"url": url, "name": name} if url else {
        "id": product_id, "name": name,
    }
    data = current.model_dump()
    data["filters"]["watched_variants"].append(entry)
    await _save_and_reload(data)

    return _action_page(
        "Variant watched",
        f"<b>{html.escape(name)}</b> has been added to your watch list.",
    )
