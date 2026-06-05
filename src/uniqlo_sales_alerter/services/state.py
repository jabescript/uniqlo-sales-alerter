"""Seen-variant state management for new-deal detection.

Tracks which product variants have been seen so that only genuinely new
deals trigger notifications.  State is persisted to a JSON file on disk.

The file holds three structures, all keyed for fast probing:

- ``variants``: set of ``product_id:color:size:discount`` keys (the
  original "have we seen this exact price for this variant?" set).
- ``stock_buckets``: per-variant ``"in" | "low" | "oos"`` keyed by
  ``product_id:color:size`` (no discount suffix).  Used to detect
  RESTOCKED and BACK_ABOVE_LOW transitions.
- ``last_seen``: ISO-8601 UTC timestamp per ``product_id:color:size``
  key, used to TTL-prune disappeared variants.

Old files with just ``{"variants": [...]}`` load fine — missing sidecars
default to empty dicts, classification falls back gracefully (no false
tags on first upgraded run).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from uniqlo_sales_alerter.models.products import (
    ChangeReason,
    SaleItem,
    is_low_stock,
    parse_variant_codes,
    stock_bucket,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    """Loaded state from disk."""

    variants: set[str] = field(default_factory=set)
    stock_buckets: dict[str, str] = field(default_factory=dict)
    last_seen: dict[str, str] = field(default_factory=dict)


def _bucket_key(product_id: str, color: str, size: str) -> str:
    """Stable variant key without discount suffix."""
    return f"{product_id}:{color}:{size}"


def _discount_suffix(discount: float, known: bool) -> str:
    """Format the discount portion of a variant set-key."""
    return f"{discount:g}" if known else "sale"


def _full_key(product_id: str, color: str, size: str, suffix: str) -> str:
    return f"{product_id}:{color}:{size}:{suffix}"


def _extract_discounts(keys: list[str]) -> list[float]:
    """Parse the discount suffix off each ``pid:color:size:<discount>`` key.

    Returns numeric discounts only; the ``"sale"`` placeholder is skipped
    because it carries no comparable percentage.
    """
    out: list[float] = []
    for k in keys:
        parts = k.rsplit(":", 1)
        if len(parts) != 2:
            continue
        suffix = parts[1]
        if suffix == "sale":
            continue
        try:
            out.append(float(suffix))
        except ValueError:
            continue
    return out


class SeenVariantStore:
    """Manages variant state on disk: seen-keys set + per-variant sidecars.

    A variant-set key has the form ``product_id:color:size:discount`` and
    uniquely identifies a purchasable variant at a specific price point.
    Sidecar dicts use ``product_id:color:size`` (no discount) so that
    price changes don't create disconnected history.
    """

    def __init__(
        self,
        path: Path,
        *,
        suppress_low_stock: bool = False,
        low_stock_threshold: int = 0,
        retention_days: int = 30,
    ) -> None:
        self._path = path
        self._suppress_low_stock = suppress_low_stock
        self._low_stock_threshold = low_stock_threshold
        self._retention_days = retention_days

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------

    def load(self) -> StateSnapshot:
        """Load previously persisted state.  Returns empty snapshot when
        the file is missing or corrupt."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            logger.debug("No state file at %s — starting fresh", self._path)
            return StateSnapshot()
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt state file %s — starting fresh", self._path)
            return StateSnapshot()

        return StateSnapshot(
            variants=set(data.get("variants", [])),
            stock_buckets=dict(data.get("stock_buckets", {})),
            last_seen=dict(data.get("last_seen", {})),
        )

    def save(self, snapshot: StateSnapshot) -> None:
        """Persist *snapshot* to disk, pruning expired ``oos`` entries.

        Only variants currently in the ``oos`` bucket whose ``last_seen``
        timestamp is older than :attr:`_retention_days` are dropped.
        Currently-observed variants (``in``/``low``) are never pruned, so
        long-running deals never re-trigger as ``NEW``.
        """
        pruned = self._prune(snapshot)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "variants": sorted(pruned.variants),
            "stock_buckets": dict(sorted(pruned.stock_buckets.items())),
            "last_seen": dict(sorted(pruned.last_seen.items())),
        }
        self._path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.debug(
            "Saved %d variant keys, %d stock buckets to %s",
            len(pruned.variants), len(pruned.stock_buckets), self._path,
        )

    def _prune(self, snapshot: StateSnapshot) -> StateSnapshot:
        """Drop ``oos`` entries whose ``last_seen`` is older than the TTL."""
        if self._retention_days <= 0:
            return snapshot
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._retention_days)
        dropped_keys: set[str] = set()
        for key, bucket in snapshot.stock_buckets.items():
            if bucket != "oos":
                continue
            ts_raw = snapshot.last_seen.get(key)
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                continue
            if ts < cutoff:
                dropped_keys.add(key)

        if not dropped_keys:
            return snapshot

        logger.debug(
            "Pruned %d stale oos variant(s) older than %d days",
            len(dropped_keys), self._retention_days,
        )
        keep_buckets = {
            k: v for k, v in snapshot.stock_buckets.items()
            if k not in dropped_keys
        }
        keep_seen = {
            k: v for k, v in snapshot.last_seen.items()
            if k not in dropped_keys
        }
        keep_variants = {
            k for k in snapshot.variants
            if _variant_key_bucket(k) not in dropped_keys
        }
        return StateSnapshot(
            variants=keep_variants,
            stock_buckets=keep_buckets,
            last_seen=keep_seen,
        )

    # ------------------------------------------------------------------
    # Current-run key/bucket extraction
    # ------------------------------------------------------------------

    def current_variant_keys(self, item: SaleItem) -> set[str]:
        """Extract ``product_id:color:size:discount`` keys from *item*.

        When :attr:`_suppress_low_stock` is True, low-stock variants are
        omitted so they stay "unseen" — the user is only alerted when
        stock climbs back above the threshold.
        """
        suffix = _discount_suffix(
            item.discount_percentage, item.has_known_discount,
        )
        keys: set[str] = set()
        saw_variant_url = False
        for idx, url in enumerate(item.product_urls):
            color, size = parse_variant_codes(url)
            if not (color and size):
                continue
            saw_variant_url = True
            if self._suppress_low_stock and self._variant_is_low(item, idx):
                continue
            keys.add(_full_key(item.product_id, color, size, suffix))
        if not saw_variant_url:
            keys.add(f"{item.product_id}:{suffix}")
        return keys

    def current_stock_buckets(self, item: SaleItem) -> dict[str, str]:
        """Extract per-variant stock buckets keyed by ``pid:color:size``."""
        result: dict[str, str] = {}
        for idx, url in enumerate(item.product_urls):
            color, size = parse_variant_codes(url)
            if not (color and size):
                continue
            v = item.variant_at(idx)
            result[_bucket_key(item.product_id, color, size)] = stock_bucket(
                v.quantity, v.status, self._low_stock_threshold,
            )
        return result

    def _variant_is_low(self, item: SaleItem, idx: int) -> bool:
        """True when the variant at *idx* is currently in low-stock state."""
        v = item.variant_at(idx)
        return is_low_stock(v.quantity, v.status, self._low_stock_threshold)

    # ------------------------------------------------------------------
    # Change classification
    # ------------------------------------------------------------------

    def classify_item(
        self,
        item: SaleItem,
        prev_seen: set[str],
        prev_buckets: dict[str, str],
    ) -> tuple[list[list[ChangeReason]], float | None]:
        """Return ``(variant_changes, previous_discount)`` for *item*.

        ``variant_changes[i]`` lists every change reason applicable to
        the variant at index *i*.  ``previous_discount`` is the highest
        prior discount observed for any variant of this product (used by
        notification channels to render ``"PRICE DROP X% → Y%"``).
        """
        pid = item.product_id
        pid_prefix = f"{pid}:"
        any_prior_variant = any(k.startswith(pid_prefix) for k in prev_seen)
        new_discount = item.discount_percentage if item.has_known_discount else None

        prev_discounts_for_item: list[float] = []
        per_variant: list[list[ChangeReason]] = []

        for idx, url in enumerate(item.product_urls):
            color, size = parse_variant_codes(url)
            reasons: list[ChangeReason] = []
            if not (color and size):
                per_variant.append(reasons)
                continue
            # Mirror current_variant_keys: when low-stock suppression is
            # on, a currently-low variant is deliberately kept out of the
            # seen-set so it can re-alert once it climbs back above the
            # threshold.  It must therefore emit no change reasons here
            # either — otherwise it would fire as NEW on every run despite
            # never being persisted.
            if self._suppress_low_stock and self._variant_is_low(item, idx):
                per_variant.append(reasons)
                continue
            bkey = _bucket_key(pid, color, size)
            prefix = f"{pid}:{color}:{size}:"
            prior_keys = [k for k in prev_seen if k.startswith(prefix)]
            had_this_variant = bool(prior_keys)
            prior_bucket = prev_buckets.get(bkey)

            v = item.variant_at(idx)
            new_bucket = stock_bucket(
                v.quantity, v.status, self._low_stock_threshold,
            )

            if not any_prior_variant:
                reasons.append(ChangeReason.NEW)
            elif not had_this_variant:
                reasons.append(ChangeReason.NEW_VARIANT)

            if had_this_variant and new_discount is not None:
                prior_discounts = _extract_discounts(prior_keys)
                if prior_discounts:
                    prev_discounts_for_item.extend(prior_discounts)
                    if new_discount > max(prior_discounts):
                        reasons.append(ChangeReason.PRICE_DROP)
                    elif new_discount < min(prior_discounts):
                        reasons.append(ChangeReason.PRICE_RISE)

            if prior_bucket == "oos" and new_bucket in ("in", "low"):
                reasons.append(ChangeReason.RESTOCKED)
            elif prior_bucket == "low" and new_bucket == "in":
                reasons.append(ChangeReason.BACK_ABOVE_LOW)

            per_variant.append(reasons)

        prev_discount = max(prev_discounts_for_item) if prev_discounts_for_item else None
        return per_variant, prev_discount


def _variant_key_bucket(variant_key: str) -> str:
    """Strip the discount suffix from a ``pid:color:size:discount`` key."""
    parts = variant_key.rsplit(":", 1)
    return parts[0] if len(parts) == 2 else variant_key
