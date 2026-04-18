"""End-to-end test: fetch real Uniqlo sale data, run the full pipeline, and
verify that the HTML report is structurally correct and faithfully represents
every deal returned by the API.

Requires network access.  Marked ``e2e`` so it is **excluded** from the
default ``pytest`` run (local + unit CI).  The CI pipeline runs it in a
dedicated job::

    python -m pytest -m e2e -v
"""

from __future__ import annotations

import html as html_mod
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from uniqlo_sales_alerter.clients.uniqlo import UniqloClient
from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.models.products import SaleItem
from uniqlo_sales_alerter.notifications.html_report import (
    HtmlReportNotifier,
    _build_report,
    _render_card,
)
from uniqlo_sales_alerter.services.sale_checker import SaleChecker

_LIVE_CHECK_URL = "https://www.uniqlo.com/de/api/commerce/v5/de/products"
_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "x-fr-clientid": "uq.de.web-spa",
}
_E2E_TIMEOUT = 30


def _api_reachable() -> bool:
    """Return True if the Uniqlo sale-products endpoint responds.

    Tests the same endpoint + params the SaleChecker will use so we don't
    get false positives from a connectivity check that works but rate-limited
    sale queries.
    """
    try:
        resp = httpx.get(
            _LIVE_CHECK_URL,
            params={"limit": 1, "httpFailure": "true", "flagCodes": "discount"},
            headers=_API_HEADERS,
            timeout=_E2E_TIMEOUT,
        )
        return resp.status_code == 200
    except (httpx.RequestError, httpx.HTTPStatusError):
        return False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not _api_reachable(), reason="Uniqlo API unreachable"),
    pytest.mark.asyncio,
]

_cached_deals: list[SaleItem] | None = None
_cached_config: AppConfig | None = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def e2e_config() -> AppConfig:
    """Minimal config targeting Germany with relaxed filters so we get results."""
    global _cached_config
    if _cached_config is None:
        _cached_config = AppConfig.model_validate({
            "uniqlo": {"country": "de/de", "check_interval_minutes": 0},
            "filters": {
                "gender": ["men", "women"],
                "min_sale_percentage": 0,
            },
            "notifications": {"notify_on": "every_check"},
        })
    return _cached_config


@pytest.fixture()
async def live_deals(e2e_config: AppConfig, tmp_path) -> list[SaleItem]:
    """Run the real sale-check pipeline once and cache the result.

    The Uniqlo API rate-limits aggressive callers, so we fetch only once
    per test session and share the result across all tests.
    """
    global _cached_deals
    if _cached_deals is not None:
        return _cached_deals

    checker = SaleChecker(e2e_config, state_file=tmp_path / ".state.json")
    try:
        result = await checker.check()
    finally:
        await checker.close()

    if not result.matching_deals:
        pytest.skip(
            "Live sale check returned zero deals — API may be rate-limiting "
            "or there are genuinely no sale items right now."
        )

    _cached_deals = result.matching_deals
    return _cached_deals


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLiveSaleCheckPipeline:
    """Verify the full fetch → filter → stock-verify pipeline with real data."""

    async def test_deals_have_required_fields(self, live_deals: list[SaleItem]):
        """Every SaleItem must have all fields the notification channels need."""
        for deal in live_deals:
            assert deal.product_id, "product_id must not be empty"
            assert deal.name, "name must not be empty"
            assert deal.sale_price > 0, f"{deal.product_id}: sale_price must be positive"
            assert deal.currency_symbol, f"{deal.product_id}: currency_symbol must not be empty"
            assert deal.available_sizes, f"{deal.product_id}: must have at least one size"
            assert deal.gender, f"{deal.product_id}: gender must not be empty"

    async def test_deals_have_valid_product_urls(self, live_deals: list[SaleItem]):
        """Each deal should have well-formed product URLs with required query params."""
        for deal in live_deals:
            assert len(deal.product_urls) == len(deal.available_sizes), (
                f"{deal.product_id}: product_urls and available_sizes length mismatch"
            )
            for url in deal.product_urls:
                parsed = urlparse(url)
                assert parsed.scheme == "https", f"URL must be HTTPS: {url}"
                assert "uniqlo.com" in parsed.netloc, f"URL must be on uniqlo.com: {url}"
                qs = parse_qs(parsed.query)
                assert "colorDisplayCode" in qs, f"Missing colorDisplayCode in {url}"
                assert "sizeDisplayCode" in qs, f"Missing sizeDisplayCode in {url}"

    async def test_discount_percentage_consistency(self, live_deals: list[SaleItem]):
        """When the discount is known, verify the percentage matches the prices."""
        for deal in live_deals:
            if deal.has_known_discount and deal.discount_percentage > 0:
                assert deal.original_price > deal.sale_price, (
                    f"{deal.product_id}: original_price ({deal.original_price}) "
                    f"must exceed sale_price ({deal.sale_price})"
                )
                expected_pct = round(
                    (deal.original_price - deal.sale_price)
                    / deal.original_price * 100, 1,
                )
                assert abs(deal.discount_percentage - expected_pct) < 0.2, (
                    f"{deal.product_id}: discount_percentage ({deal.discount_percentage}) "
                    f"doesn't match computed value ({expected_pct})"
                )


class TestHtmlReportFromLiveData:
    """Generate an HTML report from real deals and validate its content."""

    async def test_report_contains_all_deals(self, live_deals: list[SaleItem]):
        """The HTML report must include a card for every deal."""
        report = _build_report(live_deals, datetime.now(timezone.utc))

        assert "<!DOCTYPE html>" in report
        assert f"{len(live_deals)} deal(s)" in report

        card_count = report.count('<div class="card">')
        assert card_count == len(live_deals), (
            f"Expected {len(live_deals)} cards, found {card_count}"
        )

    async def test_every_deal_name_appears_in_report(self, live_deals: list[SaleItem]):
        report = _build_report(live_deals, datetime.now(timezone.utc))

        for deal in live_deals:
            safe_name = html_mod.escape(deal.name)
            assert safe_name in report, (
                f"Deal name '{deal.name}' not found in report"
            )

    async def test_every_product_url_appears_in_report(self, live_deals: list[SaleItem]):
        report = _build_report(live_deals, datetime.now(timezone.utc))

        for deal in live_deals:
            for url in deal.product_urls:
                assert url in report, (
                    f"Product URL not found in report: {url}"
                )

    async def test_price_display_in_report(self, live_deals: list[SaleItem]):
        """Report must show the sale price for every deal."""
        report = _build_report(live_deals, datetime.now(timezone.utc))

        for deal in live_deals:
            price_str = f"{deal.currency_symbol}{deal.sale_price:.2f}"
            assert price_str in report, (
                f"Sale price '{price_str}' for {deal.product_id} not in report"
            )

    async def test_discount_labels_in_report(self, live_deals: list[SaleItem]):
        """Deals with known discounts should show the percentage."""
        report = _build_report(live_deals, datetime.now(timezone.utc))

        for deal in live_deals:
            if deal.has_known_discount and deal.discount_percentage > 0:
                label = f"-{deal.discount_percentage:.0f}%"
                assert label in report, (
                    f"Discount label '{label}' for {deal.product_id} not in report"
                )

    async def test_sizes_in_report(self, live_deals: list[SaleItem]):
        """All available sizes should appear as size chips."""
        report = _build_report(live_deals, datetime.now(timezone.utc))

        for deal in live_deals:
            for size in deal.available_sizes:
                assert f">{size}<" in report, (
                    f"Size '{size}' for {deal.product_id} not found as chip text"
                )

    async def test_render_card_produces_valid_fragment(self, live_deals: list[SaleItem]):
        """_render_card should produce a valid card div for any real deal."""
        for i, deal in enumerate(live_deals[:5], 1):
            card = _render_card(deal, i)
            assert '<div class="card">' in card
            assert '<div class="card-img">' in card
            assert '<div class="card-body">' in card
            assert '<div class="price-row">' in card
            assert f"{i}." in card

    async def test_report_with_server_url(self, live_deals: list[SaleItem]):
        """When server_url is set, every card should have Ignore action links
        and the footer should include a Settings link."""
        server_url = "http://localhost:8000"
        report = _build_report(
            live_deals, datetime.now(timezone.utc), server_url=server_url,
        )

        assert f"{server_url}/settings" in report, "Footer should contain Settings link"

        for deal in live_deals:
            assert f"/actions/ignore/{deal.product_id}" in report, (
                f"Missing Ignore action for {deal.product_id}"
            )


class TestHtmlReportNotifierWritesFile:
    """Verify the HtmlReportNotifier writes a valid file to disk."""

    async def test_notifier_writes_report_to_disk(
        self, live_deals: list[SaleItem], tmp_path, monkeypatch,
    ):
        monkeypatch.setattr("webbrowser.open", lambda *a, **kw: None)

        notifier = HtmlReportNotifier(
            enabled=True, output_dir=str(tmp_path),
        )
        await notifier.send(live_deals)

        html_files = list(tmp_path.glob("uniqlo_deals_*.html"))
        assert len(html_files) == 1, f"Expected 1 report file, found {len(html_files)}"

        content = html_files[0].read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert f"{len(live_deals)} deal(s)" in content


class TestProductUrlsResolvable:
    """Verify that the product URLs we generate actually exist on uniqlo.com.

    Samples a few deals and checks that the Uniqlo product page API returns
    data for the product ID embedded in each URL.
    """

    async def test_product_ids_exist_in_api(
        self, live_deals: list[SaleItem], e2e_config: AppConfig,
    ):
        """Spot-check that product IDs from the pipeline exist in the Uniqlo API."""
        sample = live_deals[:3]
        client = UniqloClient(e2e_config)
        try:
            ids = [d.product_id for d in sample]
            products = await client.fetch_products_by_ids(ids)
        finally:
            await client.aclose()

        found_ids = {p.product_id for p in products}
        for deal in sample:
            assert deal.product_id in found_ids, (
                f"Product {deal.product_id} not found when re-fetching from API"
            )

    async def test_product_pages_return_200(self, live_deals: list[SaleItem]):
        """Spot-check that product page URLs return HTTP 200."""
        urls_to_check = [
            deal.product_urls[0]
            for deal in live_deals[:3]
            if deal.product_urls
        ]
        assert urls_to_check, "No product URLs available for verification"

        async with httpx.AsyncClient(
            timeout=_E2E_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        ) as client:
            for url in urls_to_check:
                resp = await client.get(url)
                assert resp.status_code == 200, (
                    f"Product page returned {resp.status_code}: {url}"
                )
