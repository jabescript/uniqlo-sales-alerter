"""Core service that orchestrates sale checks.

Delegates to focused modules:

- :mod:`~.filters` — product filtering pipeline
- :mod:`~.stock` — real-time stock verification
- :mod:`~.state` — seen-variant persistence for new-deal detection
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from uniqlo_sales_alerter.clients.uniqlo import UniqloClient
from uniqlo_sales_alerter.models.products import (
    ChangeReason,
    SaleCheckResult,
    UniqloProduct,
)
from uniqlo_sales_alerter.services.filters import apply_filters
from uniqlo_sales_alerter.services.state import SeenVariantStore, StateSnapshot
from uniqlo_sales_alerter.services.stock import StockVerifier

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import AppConfig, WatchedVariant

logger = logging.getLogger(__name__)

_DEFAULT_STATE_PATH = Path(
    os.environ.get("STATE_FILE", Path.cwd() / ".seen_variants.json"),
)

# Reasons that, on their own, justify firing a fresh notification.
# PRICE_RISE is intentionally excluded: it surfaces as a tag only when
# another reason already puts the item into the notification batch.
_NOTIFY_REASONS: frozenset[ChangeReason] = frozenset({
    ChangeReason.NEW,
    ChangeReason.NEW_VARIANT,
    ChangeReason.PRICE_DROP,
    ChangeReason.RESTOCKED,
    ChangeReason.BACK_ABOVE_LOW,
})


def _has_notify_reason(item) -> bool:
    """True when *item* has at least one variant whose change list
    contains a notification-worthy reason."""
    for reasons in item.variant_changes:
        if any(r in _NOTIFY_REASONS for r in reasons):
            return True
    return False


class SaleChecker:
    """Fetches products, filters for matching deals, and caches results."""

    def __init__(
        self,
        config: AppConfig,
        *,
        state_file: Path | None = None,
    ) -> None:
        self._config = config
        self._client = UniqloClient(config)
        self.last_result: SaleCheckResult | None = None

        self._watched_ids, self._watched_by_product = self._index_watched(
            config.filters.watched_variants,
        )
        self._ignored_ids: set[str] = {
            p.id.upper() for p in config.filters.ignored_products
        }
        self._ignored_keywords: list[str] = [
            kw.lower() for kw in config.filters.ignored_keywords if kw.strip()
        ]

        self._state = SeenVariantStore(
            state_file or _DEFAULT_STATE_PATH,
            suppress_low_stock=config.notifications.suppress_low_stock_alerts,
            low_stock_threshold=config.notifications.low_stock_threshold,
            retention_days=config.notifications.state_retention_days,
        )
        # Change classification ALWAYS uses the on-disk snapshot so
        # NEW/PRICE_DROP/RESTOCKED tags reflect reality across restarts.
        # ``notify_on`` only governs *what* gets dispatched, not how
        # variants are classified.  For ``all_then_new`` we still want
        # the first check after process startup to dispatch every
        # currently matching deal as a catch-up batch — see
        # ``_catch_up_pending`` below.
        loaded = self._state.load()
        self._disk_snapshot = loaded
        self._prev_snapshot = loaded
        self._seen_variants: set[str] = loaded.variants
        self._catch_up_pending = (
            config.notifications.notify_on == "all_then_new"
        )

        self._stock_verifier = StockVerifier(
            self._client, config, self._watched_by_product,
        )

    @property
    def http_client(self) -> UniqloClient:
        """The underlying Uniqlo API client."""
        return self._client

    async def close(self) -> None:
        """Release underlying HTTP resources."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Main check pipeline
    # ------------------------------------------------------------------

    async def check(self) -> SaleCheckResult:
        """Run a full sale check: fetch, filter, verify stock, detect new deals."""
        sale_products = await self._client.fetch_sale_products()
        logger.debug("Fetched %d sale products from Uniqlo API", len(sale_products))

        all_products = await self._include_watched_products(sale_products)
        sale_pids = {p.product_id.upper() for p in sale_products}

        matching = self._apply_filters(all_products, sale_pids)
        matching = await self._verify_stock(matching)

        current_variants: set[str] = set()
        current_buckets: dict[str, str] = {}
        for item in matching:
            current_variants |= self._state.current_variant_keys(item)
            current_buckets.update(self._state.current_stock_buckets(item))

        # Annotate each item with per-variant change reasons using the
        # *previous* snapshot (loaded once at construction time).
        prev_seen = self._prev_snapshot.variants
        prev_buckets = self._prev_snapshot.stock_buckets
        for item in matching:
            changes, prev_disc = self._state.classify_item(
                item, prev_seen, prev_buckets,
            )
            item.variant_changes = changes
            item.previous_discount = prev_disc

        new_deals = [item for item in matching if _has_notify_reason(item)]

        # ``all_then_new``: on the first check after process startup,
        # dispatch a full snapshot of currently matching deals.  This
        # must still honour ``suppress_low_stock_alerts`` — a deal whose
        # only variants are suppressed low-stock has no persistable keys
        # and stays silent here, exactly as it would in steady state.
        # (Using ``list(matching)`` instead would leak suppressed
        # low-stock items on every restart/config-reload.)
        if self._catch_up_pending:
            new_deals = [
                item for item in matching
                if self._state.current_variant_keys(item)
            ]
            self._catch_up_pending = False

        result = SaleCheckResult(
            total_products_scanned=len(sale_products),
            total_on_sale=len(sale_products),
            matching_deals=matching,
            new_deals=new_deals,
        )

        # Persist updated state.  Variants observed this run get fresh
        # buckets + timestamps; variants that disappeared but were known
        # on disk get a one-time ``oos`` transition write so they can
        # later be detected as RESTOCKED.
        now_iso = datetime.now(timezone.utc).isoformat()
        new_last_seen = dict(self._disk_snapshot.last_seen)
        new_buckets = dict(self._disk_snapshot.stock_buckets)
        for key, bucket in current_buckets.items():
            new_buckets[key] = bucket
            new_last_seen[key] = now_iso
        observed = set(current_buckets)
        for key, prior_bucket in self._disk_snapshot.stock_buckets.items():
            if key in observed:
                continue
            if prior_bucket != "oos":
                new_buckets[key] = "oos"
                new_last_seen[key] = now_iso

        snapshot = StateSnapshot(
            variants=current_variants | self._disk_snapshot.variants,
            stock_buckets=new_buckets,
            last_seen=new_last_seen,
        )
        self._disk_snapshot = snapshot
        self._prev_snapshot = snapshot
        self._seen_variants = snapshot.variants
        self._state.save(snapshot)
        self.last_result = result
        return result

    # ------------------------------------------------------------------
    # Delegation methods
    # ------------------------------------------------------------------

    def _apply_filters(
        self,
        products: list[UniqloProduct],
        sale_product_ids: set[str] | None = None,
    ) -> list:
        """Delegate to :func:`filters.apply_filters`."""
        return apply_filters(
            products,
            config=self._config,
            watched_ids=self._watched_ids,
            watched_by_product=self._watched_by_product,
            ignored_ids=self._ignored_ids,
            ignored_keywords=self._ignored_keywords,
            sale_product_ids=sale_product_ids,
        )

    async def _verify_stock(self, items: list) -> list:
        """Delegate to :meth:`StockVerifier.verify`."""
        return await self._stock_verifier.verify(items)

    def _variant_keys(self, item) -> set[str]:
        """Delegate to :meth:`SeenVariantStore.current_variant_keys`."""
        return self._state.current_variant_keys(item)

    def _save_state(self, variants: set[str]) -> None:
        """Persist *variants* using the existing sidecars.

        Kept for backward compatibility with tests that drive the store
        directly; production code calls :meth:`SeenVariantStore.save`
        with a full :class:`StateSnapshot`.
        """
        self._state.save(StateSnapshot(
            variants=variants,
            stock_buckets=self._disk_snapshot.stock_buckets,
            last_seen=self._disk_snapshot.last_seen,
        ))

    # ------------------------------------------------------------------
    # Watched product helpers
    # ------------------------------------------------------------------

    async def _include_watched_products(
        self, sale_products: list[UniqloProduct],
    ) -> list[UniqloProduct]:
        """Fetch any watched products missing from the sale results."""
        all_products: list[UniqloProduct] = list(sale_products)
        if not self._watched_ids:
            return all_products

        sale_pids = {p.product_id.upper() for p in sale_products}
        missing_upper = self._watched_ids - sale_pids
        if not missing_upper:
            return all_products

        to_fetch: set[str] = set()
        for pid_upper in missing_upper:
            for wv in self._watched_by_product.get(pid_upper, []):
                to_fetch.add(wv.id)
        watched_extra = await self._client.fetch_products_by_ids(sorted(to_fetch))
        logger.debug(
            "Fetched %d watched product(s) not currently on sale",
            len(watched_extra),
        )
        all_products.extend(watched_extra)
        return all_products

    @staticmethod
    def _index_watched(
        variants: list[WatchedVariant],
    ) -> tuple[set[str], dict[str, list[WatchedVariant]]]:
        """Index watched variants into a product-ID set and per-product map."""
        by_product: dict[str, list[WatchedVariant]] = {}
        for wv in variants:
            by_product.setdefault(wv.id.upper(), []).append(wv)
        return set(by_product.keys()), by_product

    # ------------------------------------------------------------------
    # Legacy static method kept for test compatibility
    # ------------------------------------------------------------------

    @staticmethod
    def _pick_in_stock_variant(
        size_name: str,
        l2s: list[dict],
        stock_map: dict[str, dict],
        wanted_sizes: set[str],
        preferred_color: str | None = None,
    ) -> tuple[str, str, str, int, str, str, str] | None:
        """Thin wrapper around :func:`stock.pick_in_stock_variant`.

        Returns a plain tuple for backward compatibility with existing
        tests.  New code should use :func:`stock.pick_in_stock_variant`
        which returns a :class:`StockVariant`.
        """
        from uniqlo_sales_alerter.services.stock import pick_in_stock_variant

        sv = pick_in_stock_variant(
            size_name, l2s, stock_map, wanted_sizes,
            preferred_color=preferred_color,
        )
        if sv is None:
            return None
        return (
            sv.color_display_code, sv.size_display_code, sv.color_name,
            sv.quantity, sv.status, sv.color_code, sv.size_code,
        )
