"""Tests for the Uniqlo API client with mocked HTTP responses."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from uniqlo_sales_alerter.clients.uniqlo import (
    UniqloClient,
    _backoff_seconds,
    _normalize_v3_product,
    _retry_after,
)
from uniqlo_sales_alerter.config import AppConfig

from .conftest import make_api_response, make_raw_product


@pytest.fixture()
def config() -> AppConfig:
    return AppConfig.model_validate({"uniqlo": {"country": "de/de"}})


@pytest.fixture()
async def client(config: AppConfig):
    c = UniqloClient(config)
    yield c
    await c.aclose()


def _mock_v3_empty(config: AppConfig):
    """Register an empty-response mock for the v3 endpoint."""
    empty = make_api_response([], total=0)
    return respx.get(config.base_url_v3).mock(
        return_value=httpx.Response(200, json=empty),
    )


class TestFetchSaleProducts:
    """Tests for the merged v5 + v3 sale product fetching."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_sale_products(self, client: UniqloClient, config: AppConfig):
        products = [
            make_raw_product(product_id=f"E{i:06d}-000", promo_price=10.0)
            for i in range(3)
        ]
        response = make_api_response(products, total=3)
        empty = make_api_response([], total=0)
        respx.get(config.base_url).side_effect = [
            httpx.Response(200, json=response),
            httpx.Response(200, json=empty),
        ]
        _mock_v3_empty(config)

        result = await client.fetch_sale_products()
        assert len(result) == 3
        assert result[0].product_id == "E000000-000"

    @pytest.mark.asyncio
    @respx.mock
    async def test_merges_discount_and_limited_offer(self):
        """Country with both v5_disc and v5_ltd merges results."""
        cfg = AppConfig.model_validate({"uniqlo": {"country": "id/en"}})
        c = UniqloClient(cfg)
        discount_products = [make_raw_product(product_id="E001", promo_price=10.0)]
        limited_products = [make_raw_product(product_id="E002", promo_price=15.0)]
        discount_resp = make_api_response(discount_products, total=1)
        limited_resp = make_api_response(limited_products, total=1)
        respx.get(cfg.base_url).side_effect = [
            httpx.Response(200, json=discount_resp),
            httpx.Response(200, json=limited_resp),
        ]

        result = await c.fetch_sale_products()
        pids = {p.product_id for p in result}
        assert pids == {"E001", "E002"}
        await c.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_deduplicates_across_flags(
        self, client: UniqloClient, config: AppConfig,
    ):
        same_product = make_raw_product(product_id="E001", promo_price=10.0)
        discount_resp = make_api_response([same_product], total=1)
        limited_resp = make_api_response([same_product], total=1)
        respx.get(config.base_url).side_effect = [
            httpx.Response(200, json=discount_resp),
            httpx.Response(200, json=limited_resp),
        ]
        _mock_v3_empty(config)

        result = await client.fetch_sale_products()
        assert len(result) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_sale_products_sends_both_flagcodes(self):
        """Country with v5_disc+v5_ltd queries both flagCodes."""
        cfg = AppConfig.model_validate({"uniqlo": {"country": "id/en"}})
        c = UniqloClient(cfg)
        response = make_api_response([], total=0)
        v5_route = respx.get(cfg.base_url).mock(
            return_value=httpx.Response(200, json=response)
        )

        await c.fetch_sale_products()

        v5_urls = [str(call.request.url) for call in v5_route.calls]
        assert any("flagCodes=discount" in u for u in v5_urls)
        assert any("flagCodes=limitedOffer" in u for u in v5_urls)
        await c.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_v3_products_merged_with_v5(self):
        """Country with v5_ltd+v3_disc+v3_ltd merges all sources (e.g. Thailand)."""
        cfg = AppConfig.model_validate({"uniqlo": {"country": "th/en"}})
        c = UniqloClient(cfg)
        v5_product = make_raw_product(product_id="E001", promo_price=10.0)
        v5_resp = make_api_response([v5_product], total=1)
        respx.get(cfg.base_url).mock(
            return_value=httpx.Response(200, json=v5_resp),
        )
        v3_product = make_raw_product(product_id="E002", promo_price=15.0)
        v3_resp = make_api_response([v3_product], total=1)
        v3_empty = make_api_response([], total=0)
        respx.get(cfg.base_url_v3).side_effect = [
            httpx.Response(200, json=v3_resp),
            httpx.Response(200, json=v3_empty),
        ]

        result = await c.fetch_sale_products()
        pids = {p.product_id for p in result}
        assert pids == {"E001", "E002"}
        await c.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_v3_dedup_with_v5(
        self, client: UniqloClient, config: AppConfig,
    ):
        """Same product from v3 and v5 is deduplicated."""
        product = make_raw_product(product_id="E001", promo_price=10.0)
        resp = make_api_response([product], total=1)
        empty = make_api_response([], total=0)
        respx.get(config.base_url).side_effect = [
            httpx.Response(200, json=resp),
            httpx.Response(200, json=empty),
        ]
        respx.get(config.base_url_v3).side_effect = [
            httpx.Response(200, json=resp),
            httpx.Response(200, json=empty),
        ]

        result = await client.fetch_sale_products()
        assert len(result) == 1


class TestSalePathsFetching:
    """Tests for sale_paths-based product fetching (e.g. Singapore)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_sale_paths_adds_products(self):
        """Products from sale_paths are merged with flagCode results."""
        cfg = AppConfig.model_validate({
            "uniqlo": {"country": "sg/en", "sale_paths": ["5856"]},
        })
        client = UniqloClient(cfg)

        flag_product = make_raw_product(product_id="E001", promo_price=10.0)
        flag_resp = make_api_response([flag_product], total=1)
        path_product = make_raw_product(product_id="E002")
        path_resp = make_api_response([path_product], total=1)

        respx.get(cfg.base_url).side_effect = [
            httpx.Response(200, json=flag_resp),   # v5_disc
            httpx.Response(200, json=path_resp),   # path=5856
        ]

        result = await client.fetch_sale_products()
        pids = {p.product_id for p in result}
        assert pids == {"E001", "E002"}
        await client.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_sale_paths_deduplicates(self):
        """Same product from flagCodes and sale_paths is not duplicated."""
        cfg = AppConfig.model_validate({
            "uniqlo": {"country": "sg/en", "sale_paths": ["5856"]},
        })
        client = UniqloClient(cfg)

        product = make_raw_product(product_id="E001", promo_price=10.0)
        resp = make_api_response([product], total=1)

        respx.get(cfg.base_url).side_effect = [
            httpx.Response(200, json=resp),   # v5_disc
            httpx.Response(200, json=resp),   # path=5856
        ]

        result = await client.fetch_sale_products()
        assert len(result) == 1
        await client.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_empty_sale_paths_no_extra_requests(
        self, client: UniqloClient, config: AppConfig,
    ):
        """When sale_paths is empty, no extra API calls are made."""
        empty = make_api_response([], total=0)
        v5_route = respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=empty),
        )
        _mock_v3_empty(config)

        await client.fetch_sale_products()

        v5_urls = [str(call.request.url) for call in v5_route.calls]
        assert not any("path=" in u for u in v5_urls)

    @pytest.mark.asyncio
    @respx.mock
    async def test_multiple_sale_paths(self):
        """Multiple sale_paths each get their own request."""
        cfg = AppConfig.model_validate({
            "uniqlo": {"country": "sg/en", "sale_paths": ["5856", "5857"]},
        })
        client = UniqloClient(cfg)

        p1 = make_raw_product(product_id="E001")
        p2 = make_raw_product(product_id="E002")
        empty = make_api_response([], total=0)

        respx.get(cfg.base_url).side_effect = [
            httpx.Response(200, json=empty),                    # v5_disc
            httpx.Response(200, json=make_api_response([p1])),  # path=5856
            httpx.Response(200, json=make_api_response([p2])),  # path=5857
        ]

        result = await client.fetch_sale_products()
        pids = {p.product_id for p in result}
        assert pids == {"E001", "E002"}
        await client.aclose()


class TestFetchAllProducts:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_single_page(
        self, client: UniqloClient, config: AppConfig
    ):
        products = [
            make_raw_product(product_id=f"E{i:06d}-000") for i in range(3)
        ]
        response = make_api_response(products, total=3)
        respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=response)
        )

        result = await client.fetch_all_products()
        assert len(result) == 3
        assert result[0].product_id == "E000000-000"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_with_pagination(
        self, client: UniqloClient, config: AppConfig
    ):
        page1 = [
            make_raw_product(product_id=f"E{i:06d}-000") for i in range(100)
        ]
        page2 = [
            make_raw_product(product_id=f"E{i:06d}-000")
            for i in range(100, 130)
        ]

        page1_resp = make_api_response(page1, total=130)
        page1_resp["result"]["pagination"]["count"] = 100
        page2_resp = make_api_response(page2, total=130)
        page2_resp["result"]["pagination"]["offset"] = 100
        page2_resp["result"]["pagination"]["count"] = 30

        route = respx.get(config.base_url)
        route.side_effect = [
            httpx.Response(200, json=page1_resp),
            httpx.Response(200, json=page2_resp),
        ]

        result = await client.fetch_all_products()
        assert len(result) == 130


class TestErrorHandling:
    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_api_error_status(
        self, client: UniqloClient, config: AppConfig
    ):
        error_resp = {
            "status": "nok",
            "error": {"code": 0, "details": [{"message": "error"}]},
        }
        respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=error_resp)
        )
        respx.get(config.base_url_v3).mock(
            return_value=httpx.Response(200, json=error_resp)
        )

        result = await client.fetch_sale_products()
        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_http_500(
        self, client: UniqloClient, config: AppConfig
    ):
        empty = make_api_response([], total=0)
        respx.get(config.base_url).side_effect = [
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(500),
            httpx.Response(200, json=empty),
            httpx.Response(200, json=empty),
        ]
        respx.get(config.base_url_v3).mock(
            return_value=httpx.Response(200, json=empty),
        )

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_sale_products()
        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_sends_correct_headers(
        self, client: UniqloClient, config: AppConfig
    ):
        response = make_api_response([], total=0)
        route = respx.get(config.base_url).mock(
            return_value=httpx.Response(200, json=response)
        )

        await client.fetch_all_products()

        assert route.called
        request = route.calls[0].request
        assert request.headers["x-fr-clientid"] == "uq.de.web-spa"
        assert request.headers["accept"] == "application/json"


class TestFetchProductL2s:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_l2_variants(
        self, client: UniqloClient, config: AppConfig,
    ):
        l2_data = [
            {"l2Id": "abc", "color": {"displayCode": "01"}, "size": {"name": "M"}},
        ]
        url = f"{config.base_url}/E123-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(200, json={"result": {"l2s": l2_data}}),
        )

        result = await client.fetch_product_l2s("E123-000", "00")
        assert len(result) == 1
        assert result[0]["l2Id"] == "abc"

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_empty_on_http_error(
        self, client: UniqloClient, config: AppConfig,
    ):
        url = f"{config.base_url}/E123-000/price-groups/00"
        respx.get(url).mock(return_value=httpx.Response(500))

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_product_l2s("E123-000", "00")
        assert result == []


class TestFetchVariantStock:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_stock_map(
        self, client: UniqloClient, config: AppConfig,
    ):
        stock_data = {"abc": {"statusCode": "IN_STOCK", "quantity": 5}}
        url = f"{config.base_url}/E123-000/price-groups/00/stock"
        respx.get(url).mock(
            return_value=httpx.Response(200, json={"result": stock_data}),
        )

        result = await client.fetch_variant_stock("E123-000", "00")
        assert result["abc"]["statusCode"] == "IN_STOCK"

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_empty_on_http_error(
        self, client: UniqloClient, config: AppConfig,
    ):
        url = f"{config.base_url}/E123-000/price-groups/00/stock"
        respx.get(url).mock(return_value=httpx.Response(500))

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_variant_stock("E123-000", "00")
        assert result == {}


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_aclose_idempotent(self, config: AppConfig):
        c = UniqloClient(config)
        await c.aclose()
        await c.aclose()  # should not raise

    @pytest.mark.asyncio
    @respx.mock
    async def test_shared_client_reused_across_calls(
        self, client: UniqloClient, config: AppConfig,
    ):
        """Ensure the same httpx.AsyncClient is reused, not recreated."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(200, json={"result": {"l2s": []}}),
        )

        await client.fetch_product_l2s("E1-000", "00")
        first_client = client._client

        await client.fetch_product_l2s("E1-000", "00")
        assert client._client is first_client


class TestRateLimitHandling:
    """Tests for 429 / retry / backoff behaviour in _request."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_retries_then_succeeds(
        self, client: UniqloClient, config: AppConfig,
    ):
        """A single 429 followed by a 200 should succeed."""
        l2_data = [{"l2Id": "x"}]
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"result": {"l2s": l2_data}}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_product_l2s("E1-000", "00")

        assert len(result) == 1
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_exhausts_retries_returns_empty(
        self, client: UniqloClient, config: AppConfig,
    ):
        """Three consecutive 429s should exhaust retries; L2 returns []."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"retry-after": "0"}),
        )

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_product_l2s("E1-000", "00")

        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_on_stock_retries_then_succeeds(
        self, client: UniqloClient, config: AppConfig,
    ):
        stock_data = {"abc": {"statusCode": "IN_STOCK", "quantity": 3}}
        url = f"{config.base_url}/E1-000/price-groups/00/stock"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"result": stock_data}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_variant_stock("E1-000", "00")

        assert result["abc"]["statusCode"] == "IN_STOCK"
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_on_page_fetch_retries(
        self, client: UniqloClient, config: AppConfig,
    ):
        """Pagination should also retry on 429."""
        products = [make_raw_product(product_id="E000001-000", promo_price=10.0)]
        ok_resp = make_api_response(products, total=1)

        route = respx.get(config.base_url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json=ok_resp),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_sale_products()

        assert len(result) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_503_retries_then_succeeds(
        self, client: UniqloClient, config: AppConfig,
    ):
        """503 (service unavailable) should also be retried."""
        l2_data = [{"l2Id": "y"}]
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json={"result": {"l2s": l2_data}}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            result = await client.fetch_product_l2s("E1-000", "00")

        assert len(result) == 1
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_after_header_respected(
        self, client: UniqloClient, config: AppConfig,
    ):
        """When the server sends Retry-After: 7, we should sleep ~7s."""
        l2_data = [{"l2Id": "z"}]
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "7"}),
            httpx.Response(200, json={"result": {"l2s": l2_data}}),
        ]

        with patch(
            "uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep",
        ) as mock_sleep:
            await client.fetch_product_l2s("E1-000", "00")

        mock_sleep.assert_awaited_once_with(7.0)

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_prints_to_console(
        self, client: UniqloClient, config: AppConfig, capsys,
    ):
        """A 429 should print a visible message to stdout."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        route = respx.get(url)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"result": {"l2s": []}}),
        ]

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            await client.fetch_product_l2s("E1-000", "00")

        output = capsys.readouterr().out
        assert "[Rate limit]" in output
        assert "429" in output

    @pytest.mark.asyncio
    @respx.mock
    async def test_429_exhausted_prints_gave_up(
        self, client: UniqloClient, config: AppConfig, capsys,
    ):
        """When all retries fail on 429, a 'gave up' message is printed."""
        url = f"{config.base_url}/E1-000/price-groups/00"
        respx.get(url).mock(
            return_value=httpx.Response(429, headers={"retry-after": "0"}),
        )

        with patch("uniqlo_sales_alerter.clients.uniqlo.asyncio.sleep"):
            await client.fetch_product_l2s("E1-000", "00")

        output = capsys.readouterr().out
        assert "Gave up" in output


class TestBackoffHelpers:
    def test_backoff_without_jitter(self):
        assert _backoff_seconds(1, jitter=False) == 2.0
        assert _backoff_seconds(2, jitter=False) == 4.0
        assert _backoff_seconds(3, jitter=False) == 8.0
        assert _backoff_seconds(10, jitter=False) == 60.0  # capped at max

    def test_backoff_with_jitter_in_range(self):
        for _ in range(50):
            val = _backoff_seconds(2, jitter=True)
            assert 2.0 <= val <= 6.0

    @pytest.mark.parametrize("headers,expected", [
        ({"retry-after": "10"}, 10.0),
        ({"retry-after": "999"}, 60.0),
        ({}, None),
        ({"retry-after": "not-a-number"}, None),
    ], ids=["numeric", "capped", "missing", "non_numeric"])
    def test_retry_after(self, headers, expected):
        resp = httpx.Response(429, headers=headers)
        assert _retry_after(resp) == expected


class TestNormalizeV3Product:
    """Tests for _normalize_v3_product which adapts v3 data to v5 schema."""

    def test_string_prices_become_floats(self):
        raw = {
            "productId": "E001",
            "name": "Test",
            "prices": {
                "base": {"currency": {"code": "THB", "symbol": "THB"}, "value": "590.0000"},
                "promo": {"currency": {"code": "THB", "symbol": "THB"}, "value": "490.0000"},
            },
            "images": {"main": []},
            "sizes": [],
            "genderName": "Men",
            "unisexFlag": "0",
        }
        result = _normalize_v3_product(raw)
        from uniqlo_sales_alerter.models.products import UniqloProduct
        product = UniqloProduct.model_validate(result)
        assert product.prices.base.value == 590.0
        assert product.prices.promo is not None
        assert product.prices.promo.value == 490.0

    def test_gender_name_mapped_to_category(self):
        raw = {
            "productId": "E001",
            "name": "Test",
            "prices": {"base": {"value": "100"}, "promo": None},
            "images": {"main": []},
            "sizes": [],
            "genderName": "Women",
            "unisexFlag": "0",
        }
        result = _normalize_v3_product(raw)
        assert result["genderCategory"] == "WOMEN"

    def test_unisex_flag_overrides_gender(self):
        raw = {
            "productId": "E001",
            "name": "Test",
            "prices": {"base": {"value": "100"}, "promo": None},
            "images": {"main": []},
            "sizes": [],
            "genderName": "Men",
            "unisexFlag": "1",
        }
        result = _normalize_v3_product(raw)
        assert result["genderCategory"] == "UNISEX"

    def test_images_list_converted_to_dict(self):
        raw = {
            "productId": "E001",
            "name": "Test",
            "prices": {"base": {"value": "100"}, "promo": None},
            "images": {
                "main": [
                    {"url": "https://example.com/img1.jpg", "colorCode": "09"},
                    {"url": "https://example.com/img2.jpg", "colorCode": "01"},
                ],
            },
            "sizes": [],
            "genderName": "Men",
        }
        result = _normalize_v3_product(raw)
        main = result["images"]["main"]
        assert isinstance(main, dict)
        assert main["09"]["image"] == "https://example.com/img1.jpg"
        assert main["01"]["image"] == "https://example.com/img2.jpg"

    def test_price_group_from_plds(self):
        raw = {
            "productId": "E001",
            "name": "Test",
            "prices": {"base": {"value": "100"}, "promo": None},
            "images": {"main": []},
            "sizes": [],
            "genderName": "Men",
            "plds": [{"displayCode": "000", "name": "-"}],
        }
        result = _normalize_v3_product(raw)
        assert result["priceGroup"] == "00"

    def test_default_price_group(self):
        raw = {
            "productId": "E001",
            "name": "Test",
            "prices": {"base": {"value": "100"}, "promo": None},
            "images": {"main": []},
            "sizes": [],
            "genderName": "Men",
        }
        result = _normalize_v3_product(raw)
        assert result["priceGroup"] == "00"
