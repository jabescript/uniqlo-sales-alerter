"""End-to-end test: fetch real Uniqlo sale data, run the full pipeline, and
verify that the HTML report is structurally correct and faithfully represents
every deal returned by the API.

Requires network access.  Marked ``e2e`` so it is **excluded** from the
default ``pytest`` run (local + unit CI).  The CI pipeline runs it in a
dedicated job::

    python -m pytest -m e2e -v
"""

from __future__ import annotations

import asyncio
import html as html_mod
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch
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

_E2E_TIMEOUT = 30


def _api_reachable(country_code: str = "de", lang: str = "de") -> bool:
    """Return True if a Uniqlo sale-products endpoint responds.

    Tests the same endpoint + params the SaleChecker will use so we don't
    get false positives from a connectivity check that works but rate-limited
    sale queries.
    """
    url = f"https://www.uniqlo.com/{country_code}/api/commerce/v5/{lang}/products"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "x-fr-clientid": f"uq.{country_code}.web-spa",
    }
    try:
        resp = httpx.get(
            url,
            params={"limit": 1, "httpFailure": "true", "flagCodes": "discount"},
            headers=headers,
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

# ---------------------------------------------------------------------------
# Per-country pipeline cache — each country's API is hit at most once
# ---------------------------------------------------------------------------


@dataclass
class _CountryData:
    """Cached pipeline results for one country."""

    config: AppConfig
    raw_products: list
    matching_deals: list[SaleItem]
    pre_verify_count: int


_country_cache: dict[str, _CountryData] = {}
_CACHE_TMP = Path(tempfile.mkdtemp(prefix="e2e_uniqlo_"))


async def _get_country_data(country: str) -> _CountryData:
    """Run the full pipeline for *country* once, then return cached results.

    First call fetches sale products and runs ``SaleChecker.check()`` (with
    the fetch result reused via a mock so we don't hit the API twice).
    Subsequent calls return the cached ``_CountryData`` immediately.
    """
    if country in _country_cache:
        return _country_cache[country]

    config = AppConfig.model_validate({
        "uniqlo": {"country": country, "check_interval_minutes": 0},
        "filters": {
            "gender": ["men", "women"],
            "min_sale_percentage": 0,
        },
        "notifications": {"notify_on": "every_check"},
    })

    state = _CACHE_TMP / f"state_{country.replace('/', '_')}.json"
    checker = SaleChecker(config, state_file=state)
    try:
        raw = await checker._client.fetch_sale_products()
        sale_pids = {p.product_id.upper() for p in raw}
        pre_verify_count = len(checker._apply_filters(raw, sale_pids))

        with patch.object(
            checker._client, "fetch_sale_products",
            new_callable=AsyncMock, return_value=raw,
        ):
            result = await checker.check()

        data = _CountryData(
            config=config,
            raw_products=raw,
            matching_deals=result.matching_deals,
            pre_verify_count=pre_verify_count,
        )
        _country_cache[country] = data
        return data
    finally:
        await checker.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def e2e_config() -> AppConfig:
    """Config for Germany, populated lazily via the cache."""
    data = await _get_country_data("de/de")
    return data.config


@pytest.fixture()
async def live_deals() -> list[SaleItem]:
    """Pipeline results for Germany, cached across all tests."""
    data = await _get_country_data("de/de")
    if not data.matching_deals:
        pytest.skip(
            "Live sale check returned zero deals — API may be rate-limiting "
            "or there are genuinely no sale items right now."
        )
    return data.matching_deals


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


# ---------------------------------------------------------------------------
# SEA country e2e tests (stock_api="none" countries)
# ---------------------------------------------------------------------------

_SEA_COUNTRIES = [
    pytest.param("ph/en", id="philippines"),
    pytest.param("th/en", id="thailand"),
]


class TestSeaCountryPipeline:
    """Verify the full pipeline works for countries with unreliable stock APIs.

    PH and TH use v3 listing endpoints and have ``stock_api="none"`` in the
    capabilities registry.  Each country's pipeline runs at most once — the
    result is cached and shared across all tests in this class.
    """

    @pytest.mark.parametrize("country", _SEA_COUNTRIES)
    async def test_sea_pipeline_returns_deals(self, country: str):
        """Full pipeline for a SEA country produces valid deals."""
        data = await _get_country_data(country)
        assert data.config.capabilities.stock_api == "none", (
            f"Expected stock_api='none' for {country}"
        )

        if not data.matching_deals:
            pytest.skip(
                f"Live sale check for {country} returned zero deals — "
                "API may be rate-limiting or there are no sale items."
            )

        for deal in data.matching_deals:
            assert deal.product_id, "product_id must not be empty"
            assert deal.name, "name must not be empty"
            assert deal.sale_price > 0, (
                f"{deal.product_id}: sale_price must be positive"
            )
            assert deal.available_sizes, (
                f"{deal.product_id}: must have at least one size"
            )

    @pytest.mark.parametrize("country", _SEA_COUNTRIES)
    async def test_sea_no_items_dropped(self, country: str):
        """stock_api='none' countries must never drop items during verification."""
        data = await _get_country_data(country)

        if not data.raw_products:
            pytest.skip(
                f"No sale products returned for {country} — "
                "API may be rate-limiting."
            )

        assert len(data.matching_deals) == data.pre_verify_count, (
            f"stock_api='none' must not drop any items: "
            f"had {data.pre_verify_count}, got {len(data.matching_deals)}"
        )

    @pytest.mark.parametrize("country", _SEA_COUNTRIES)
    async def test_sea_listing_not_truncated(self, country: str):
        """Pagination must retrieve all available items, not just one page."""
        data = await _get_country_data(country)

        if not data.raw_products:
            pytest.skip(
                f"No sale products returned for {country} — "
                "API may be rate-limiting."
            )

        assert len(data.raw_products) >= 50, (
            f"Expected at least 50 raw sale products for {country}, "
            f"got {len(data.raw_products)} — pagination may be truncated"
        )

    @pytest.mark.parametrize("country", _SEA_COUNTRIES)
    async def test_sea_urls_use_code_style(self, country: str):
        """SEA countries must use colorCode/sizeCode URL format."""
        data = await _get_country_data(country)
        assert data.config.capabilities.url_style == "code"

        if not data.matching_deals:
            pytest.skip(f"No deals for {country}")

        for deal in data.matching_deals:
            for url in deal.product_urls:
                if not url:
                    continue
                qs = parse_qs(urlparse(url).query)
                assert "colorCode" in qs, (
                    f"SEA URL must use colorCode, got: {url}"
                )
                assert "sizeCode" in qs, (
                    f"SEA URL must use sizeCode, got: {url}"
                )
                assert "colorDisplayCode" not in qs, (
                    f"SEA URL must NOT use colorDisplayCode: {url}"
                )
                path = urlparse(url).path
                parts = path.rstrip("/").split("/")
                product_idx = next(
                    (i for i, p in enumerate(parts) if p == "products"),
                    -1,
                )
                assert product_idx >= 0
                after_pid = product_idx + 2
                assert after_pid >= len(parts), (
                    f"code-style URL must not have /{parts[after_pid]} "
                    f"price-group segment: {url}"
                )

    @pytest.mark.parametrize("country", _SEA_COUNTRIES)
    async def test_sea_products_resolvable(self, country: str):
        """A sample of SEA products must be resolvable via the L2 endpoint."""
        data = await _get_country_data(country)

        if not data.matching_deals:
            pytest.skip(f"No deals for {country}")

        sample = data.matching_deals[:5]
        client = UniqloClient(data.config)
        try:
            for deal in sample:
                l2s = await client.fetch_product_l2s(
                    deal.product_id, deal.price_group,
                )
                assert l2s, (
                    f"Product {deal.product_id} not resolvable via L2 "
                    f"endpoint for {country}"
                )
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# Representative country sweep — one per distinct API style
# ---------------------------------------------------------------------------
#
# Each ``CountryCapabilities`` combination that produces different pipeline
# behaviour gets exactly one representative.  Countries within the same
# group share identical code paths; testing all 21 would only add API
# pressure and flakiness.
#
#   Style                           listing_sources              stock  url     Representative
#   ─────────────────────────────── ──────────────────────────── ────── ─────── ──────────────
#   v5 discount only                (v5_disc,)                   v5     disp    de
#   v5 discount + limitedOffer      (v5_disc, v5_ltd)            v5     disp    id
#   v3 only                         (v3_disc, v3_ltd)            none   code    ph
#   v5 + v3 mixed                   (v5_ltd, v3_disc, v3_ltd)    none   code    th
#   v5 discount + sale_paths        (v5_disc, sale_paths)        v5     disp    sg

_REPRESENTATIVE_STYLES: dict[str, str] = {
    "de/de": "v5_disc",
    "id/en": "v5_disc+v5_ltd",
    "ph/en": "v3_disc+v3_ltd",
    "th/en": "v5_ltd+v3",
    "sg/en": "v5_disc+sale_paths",
}

_REPRESENTATIVE_COUNTRIES = [
    pytest.param(country, id=style)
    for country, style in _REPRESENTATIVE_STYLES.items()
]


class TestCountrySweep:
    """Verify URL format and product resolvability for each API style.

    One representative country per distinct ``CountryCapabilities``
    combination.  DE, PH, and TH are already cached by earlier test
    classes, so this sweep only triggers new fetches for ID and SG.

    A warmup test pre-fetches all representatives concurrently so that
    the individual parametrized tests read from cache.
    """

    async def test_0_prefetch_all_styles(self):
        """Pre-fetch all representative countries concurrently."""
        await asyncio.gather(
            *(_get_country_data(c) for c in _REPRESENTATIVE_STYLES),
            return_exceptions=True,
        )

    @pytest.mark.parametrize("country", _REPRESENTATIVE_COUNTRIES)
    async def test_url_format_and_resolvability(self, country: str):
        data = await _get_country_data(country)
        caps = data.config.capabilities

        if not data.matching_deals:
            pytest.skip(f"No deals for {country}")

        for deal in data.matching_deals[:10]:
            for url in deal.product_urls:
                if not url:
                    continue
                parsed = urlparse(url)
                assert parsed.scheme == "https", (
                    f"URL must be HTTPS: {url}"
                )
                assert "uniqlo.com" in parsed.netloc, (
                    f"URL must be on uniqlo.com: {url}"
                )
                qs = parse_qs(parsed.query)

                if caps.url_style == "code":
                    assert "colorCode" in qs, (
                        f"Expected colorCode in {url}"
                    )
                    assert "sizeCode" in qs, (
                        f"Expected sizeCode in {url}"
                    )
                else:
                    assert "colorDisplayCode" in qs, (
                        f"Expected colorDisplayCode in {url}"
                    )
                    assert "sizeDisplayCode" in qs, (
                        f"Expected sizeDisplayCode in {url}"
                    )

    @pytest.mark.parametrize("country", _REPRESENTATIVE_COUNTRIES)
    async def test_products_resolvable(self, country: str):
        """Spot-check that a sample of products can be re-fetched via the API."""
        data = await _get_country_data(country)
        caps = data.config.capabilities

        if not data.matching_deals:
            pytest.skip(f"No deals for {country}")

        sample = data.matching_deals[:3]
        client = UniqloClient(data.config)
        try:
            if caps.stock_api == "none":
                for deal in sample:
                    l2s = await client.fetch_product_l2s(
                        deal.product_id, deal.price_group,
                    )
                    assert l2s, (
                        f"Product {deal.product_id} not resolvable "
                        f"via L2 for {country}"
                    )
            else:
                ids = [d.product_id for d in sample]
                refetched = await client.fetch_products_by_ids(ids)
                found_ids = {p.product_id for p in refetched}
                assert found_ids, (
                    f"fetch_products_by_ids returned nothing for {ids}"
                )
                missing = [
                    d.product_id for d in sample
                    if d.product_id not in found_ids
                ]
                assert len(missing) < len(sample), (
                    f"None of {ids} resolvable via API"
                )
        finally:
            await client.aclose()
