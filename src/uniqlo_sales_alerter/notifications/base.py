"""Protocol that all notification channels must satisfy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from urllib.parse import quote

from uniqlo_sales_alerter.models.products import SaleItem

PROJECT_URL = "https://github.com/kequach/uniqlo-sales-alerter"


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
