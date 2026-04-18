"""Pydantic models for Uniqlo API responses and application-level sale items."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

_DEFAULT_CURRENCY = "€"


# ---------------------------------------------------------------------------
# Shared URL builder
# ---------------------------------------------------------------------------


def build_product_url(
    base: str,
    product_id: str,
    price_group: str,
    color: str = "",
    size: str = "",
) -> str:
    """Reconstruct a Uniqlo product page URL from component fields.

    ``base`` is :pyattr:`AppConfig.product_page_base` (e.g.
    ``https://www.uniqlo.com/de/de/products``).
    """
    params: list[str] = []
    if color:
        params.append(f"colorDisplayCode={color}")
    if size:
        params.append(f"sizeDisplayCode={size}")
    qs = ("?" + "&".join(params)) if params else ""
    return f"{base}/{product_id}/{price_group}{qs}"


# ---------------------------------------------------------------------------
# Uniqlo Commerce API response models (partial — only fields we need)
# ---------------------------------------------------------------------------


class UniqloPrice(BaseModel):
    """A price with an optional currency descriptor."""

    value: float
    currency: dict[str, str] | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, v: Any) -> float:
        return float(v)


class UniqloPriceInfo(BaseModel):
    """Base and optional promotional price for a product."""

    base: UniqloPrice
    promo: UniqloPrice | None = None
    is_dual_price: bool = Field(default=False, alias="isDualPrice")


class UniqloSize(BaseModel):
    """A single size option with its API display code."""

    name: str
    display_code: str = Field(default="", alias="displayCode")


class UniqloImageDetail(BaseModel):
    image: str = ""


class UniqloProduct(BaseModel, populate_by_name=True):
    """Represents a single product from the Uniqlo API."""

    product_id: str = Field(alias="productId")
    name: str = ""
    gender_category: str = Field(default="", alias="genderCategory")
    prices: UniqloPriceInfo
    sizes: list[UniqloSize] = Field(default_factory=list)
    images: dict[str, Any] = Field(default_factory=dict)
    price_group: str = Field(default="", alias="priceGroup")
    rating: dict[str, Any] = Field(default_factory=dict)
    representative: dict[str, Any] = Field(default_factory=dict)
    representative_color_display_code: str = Field(
        default="", alias="representativeColorDisplayCode"
    )

    @property
    def is_on_sale(self) -> bool:
        return self.prices.promo is not None and self.prices.promo.value < self.prices.base.value

    @property
    def discount_percentage(self) -> float:
        if not self.is_on_sale or self.prices.base.value == 0:
            return 0.0
        promo = self.prices.promo
        if promo is None:
            return 0.0
        return round((self.prices.base.value - promo.value) / self.prices.base.value * 100, 1)

    @property
    def main_image_url(self) -> str | None:
        main_images: dict[str, Any] = self.images.get("main", {})
        for _color_code, detail in main_images.items():
            if isinstance(detail, dict) and "image" in detail:
                return detail["image"]
        return None

    def image_url_for_color(self, color_code: str) -> str | None:
        """Return the image URL for a specific colour code, or the default."""
        main_images: dict[str, Any] = self.images.get("main", {})
        detail = main_images.get(color_code)
        if isinstance(detail, dict) and "image" in detail:
            return detail["image"]
        return self.main_image_url

    @property
    def color_image_map(self) -> dict[str, str]:
        """Map of colour display code to image URL."""
        result: dict[str, str] = {}
        for color_code, detail in self.images.get("main", {}).items():
            if isinstance(detail, dict) and "image" in detail:
                result[color_code] = detail["image"]
        return result

    @property
    def size_names(self) -> list[str]:
        return [s.name for s in self.sizes]

    @property
    def currency_symbol(self) -> str:
        if self.prices.base.currency:
            return self.prices.base.currency.get("symbol", _DEFAULT_CURRENCY)
        return _DEFAULT_CURRENCY


class UniqloPagination(BaseModel):
    total: int = 0
    offset: int = 0
    count: int = 0


class UniqloApiResult(BaseModel):
    items: list[UniqloProduct] = Field(default_factory=list)
    pagination: UniqloPagination = Field(default_factory=UniqloPagination)


class UniqloApiResponse(BaseModel):
    status: str = ""
    result: UniqloApiResult = Field(default_factory=UniqloApiResult)


# ---------------------------------------------------------------------------
# Application-level models
# ---------------------------------------------------------------------------


class SaleItem(BaseModel):
    """A product that passed all configured filters."""

    product_id: str
    name: str
    original_price: float
    sale_price: float
    currency_symbol: str = _DEFAULT_CURRENCY
    discount_percentage: float
    gender: str
    available_sizes: list[str]
    image_url: str | None = None
    color_images: dict[str, str] = Field(default_factory=dict)
    product_urls: list[str] = Field(default_factory=list)
    color_names: list[str] = Field(default_factory=list)
    price_group: str = ""
    rating_average: float | None = None
    rating_count: int | None = None
    is_watched: bool = False
    has_known_discount: bool = True


class SaleCheckResult(BaseModel):
    """Result of a single sale-check run."""

    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_products_scanned: int = 0
    total_on_sale: int = 0
    matching_deals: list[SaleItem] = Field(default_factory=list)
    new_deals: list[SaleItem] = Field(default_factory=list)
