"""Protocol and shared helpers for notification channels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import parse_qs, quote, urlparse

from uniqlo_sales_alerter.models.products import SaleItem

PROJECT_URL = "https://github.com/kequach/uniqlo-sales-alerter"

FAVICON_LINK = (
    '<link rel="icon" href="data:image/svg+xml,'
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
    "<path d='M4 15.5 15.5 4H28a1 1 0 0 1 1 1v12.5"
    "L17.5 29a2 2 0 0 1-2.8 0L4 18.3a2 2 0 0 1 0-2.8z'"
    " fill='%23ED1D24'/>"
    "<circle cx='23' cy='9' r='2.5' fill='%23fff'/>"
    '</svg>"/>'
)


# ---------------------------------------------------------------------------
# Shared formatting helpers (used by all notification channels)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FormattedPrice:
    """Channel-agnostic price data pre-computed from a :class:`SaleItem`.

    Channels only need to decide *how* to render each field (ANSI, HTML,
    MarkdownV2, etc.) — the business logic lives here once.
    """

    sale_text: str
    original_text: str
    discount_label: str
    show_strikethrough: bool
    show_sale_badge: bool


def format_price(deal: SaleItem) -> FormattedPrice:
    """Derive display-ready price fields from *deal*."""
    sym = deal.currency_symbol
    sale = f"{sym}{deal.sale_price:.2f}"
    if deal.has_known_discount and deal.discount_percentage > 0:
        return FormattedPrice(
            sale_text=sale,
            original_text=f"{sym}{deal.original_price:.2f}",
            discount_label=f"-{deal.discount_percentage:.0f}%",
            show_strikethrough=True,
            show_sale_badge=False,
        )
    if not deal.has_known_discount:
        return FormattedPrice(
            sale_text=sale,
            original_text="",
            discount_label="Sale",
            show_strikethrough=False,
            show_sale_badge=True,
        )
    return FormattedPrice(
        sale_text=sale,
        original_text="",
        discount_label="",
        show_strikethrough=False,
        show_sale_badge=False,
    )


def resolve_color_image(
    url: str,
    color_images: dict[str, str],
    fallback: str | None,
) -> str | None:
    """Pick the product image matching the variant URL's colour code."""
    if color_images and url:
        params = parse_qs(urlparse(url).query)
        color_code = params.get("colorDisplayCode", [""])[0]
        if color_code and color_code in color_images:
            return color_images[color_code]
    return fallback


def unique_colors(deal: SaleItem) -> list[str]:
    """Deduplicated, non-empty colour names preserving insertion order."""
    return list(dict.fromkeys(cn for cn in deal.color_names if cn))


@runtime_checkable
class Notifier(Protocol):
    """Structural interface for notification channels.

    Any class with matching ``send`` and ``is_enabled`` signatures is
    automatically considered a ``Notifier`` — no inheritance required.
    """

    def is_enabled(self) -> bool: ...

    async def send(self, deals: list[SaleItem]) -> None: ...


class DealActions:
    """Pre-built action URLs for a single deal."""

    __slots__ = ("ignore_url", "watch_urls", "unwatch_url")

    def __init__(self, deal: SaleItem, server_url: str) -> None:
        if not server_url:
            self.ignore_url = ""
            self.watch_urls: list[tuple[str, str]] = []
            self.unwatch_url = ""
            return
        name_enc = quote(deal.name, safe="")
        self.ignore_url = (
            f"{server_url}/actions/ignore/{deal.product_id}?name={name_enc}"
        )
        self.unwatch_url = (
            f"{server_url}/actions/unwatch/{deal.product_id}?name={name_enc}"
            if deal.is_watched else ""
        )
        self.watch_urls = []
        for sz, prod_url in zip(deal.available_sizes, deal.product_urls):
            url_enc = quote(prod_url, safe="")
            watch = (
                f"{server_url}/actions/watch/{deal.product_id}"
                f"?name={name_enc}&url={url_enc}"
            )
            self.watch_urls.append((sz, watch))
