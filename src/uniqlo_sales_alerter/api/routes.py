"""FastAPI REST endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from uniqlo_sales_alerter.models.products import SaleCheckResult, SaleItem

router = APIRouter(prefix="/api/v1")

_NO_RESULT = HTTPException(
    status_code=503, detail="No sale check has been run yet",
)

_SECRET_FIELDS: list[tuple[list[str], str]] = [
    (["notifications", "channels", "telegram", "bot_token"], "bot_token"),
    (["notifications", "channels", "email", "smtp_password"], "smtp_password"),
]


def _redact_secrets(data: dict[str, Any]) -> dict[str, Any]:
    """Replace secret values with ``'***'`` for safe external display."""
    import copy
    d = copy.deepcopy(data)
    for path, _key in _SECRET_FIELDS:
        node = d
        for segment in path[:-1]:
            node = node.get(segment, {})
        if node.get(path[-1]):
            node[path[-1]] = "***"
    return d


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
        g = gender.upper()
        deals = [
            d for d in deals
            if d.gender.upper() in (g, "UNISEX")
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

    current = state.config
    for path, _key in _SECRET_FIELDS:
        node = body
        for segment in path[:-1]:
            node = node.get(segment, {})
        if node.get(path[-1]) == "***":
            src: Any = current
            for segment in path:
                src = getattr(src, segment, "")
            node[path[-1]] = src

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
