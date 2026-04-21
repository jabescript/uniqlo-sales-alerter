"""Tests for the sale checker service and filtering logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.models.products import UniqloProduct
from uniqlo_sales_alerter.services.sale_checker import SaleChecker

from .conftest import make_raw_product, noop_verify, noop_watched_fetch, sample_deal

_MEN = "MEN"


def _product(raw: dict) -> UniqloProduct:
    return UniqloProduct.model_validate(raw)


def _raw(pid="E001", base=100, promo=40, gender=_MEN, **kw):
    return make_raw_product(
        product_id=pid, base_price=base, promo_price=promo, gender=gender, **kw
    )


class TestUniqloProduct:
    @pytest.mark.parametrize("promo_price,expected", [
        (60, True),
        (None, False),
    ], ids=["on_sale", "no_promo"])
    def test_is_on_sale(self, promo_price, expected):
        p = _product(make_raw_product(base_price=100, promo_price=promo_price))
        assert p.is_on_sale is expected

    @pytest.mark.parametrize("promo_price,expected", [
        (60, 40.0),
        (None, 0.0),
    ], ids=["discounted", "no_promo"])
    def test_discount_percentage(self, promo_price, expected):
        p = _product(make_raw_product(base_price=100, promo_price=promo_price))
        assert p.discount_percentage == expected

    @pytest.mark.parametrize("image_url,expected", [
        ("https://example.com/img.jpg", "https://example.com/img.jpg"),
        (None, None),
    ], ids=["has_image", "no_image"])
    def test_main_image_url(self, image_url, expected):
        p = _product(make_raw_product(image_url=image_url))
        assert p.main_image_url == expected

    def test_size_names(self):
        p = _product(make_raw_product(sizes=["XS", "S", "M"]))
        assert p.size_names == ["XS", "S", "M"]


class TestSaleCheckerFiltering:
    """Tests for the filter logic using mocked API responses."""

    @pytest.fixture()
    def checker(self, sale_config: AppConfig) -> SaleChecker:
        return SaleChecker(sale_config)

    def _apply(self, checker: SaleChecker, raw_products: list[dict]):
        products = [_product(r) for r in raw_products]
        sale_products = [p for p in products if p.is_on_sale]
        return checker._apply_filters(sale_products)

    def test_filters_by_min_discount(self, checker: SaleChecker):
        products = [
            _raw("E001", promo=50),
            _raw("E002", promo=70),
        ]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert result[0].product_id == "E001"

    def test_filters_by_gender(self, checker: SaleChecker):
        products = [
            _raw("E001", gender=_MEN),
            _raw("E002", gender="WOMEN"),
        ]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert result[0].product_id == "E001"

    def test_unisex_passes_any_gender_filter(self, checker: SaleChecker):
        products = [_raw("E001", gender="UNISEX")]
        result = self._apply(checker, products)
        assert len(result) == 1

    def test_filters_by_size(self, checker: SaleChecker):
        products = [
            _raw("E001", sizes=["M", "L"]),
            _raw("E002", sizes=["XXS"]),
        ]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert result[0].product_id == "E001"

    def test_available_sizes_only_matching(self, checker: SaleChecker):
        """available_sizes should contain only sizes that are both in-stock and configured."""
        products = [_raw("E001", sizes=["S", "M", "L", "XL"])]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert set(result[0].available_sizes) == {"M", "L"}

    def test_available_sizes_preserves_order(self, checker: SaleChecker):
        products = [_raw("E001", sizes=["XL", "L", "M", "S"])]
        result = self._apply(checker, products)
        assert result[0].available_sizes == ["L", "M"]

    def test_variant_urls_per_matching_size(self, checker: SaleChecker):
        """Each matching size gets its own URL with the correct sizeDisplayCode."""
        products = [_raw("E001", sizes=["S", "M", "L", "XL"])]
        result = self._apply(checker, products)
        deal = result[0]
        assert len(deal.product_urls) == 2
        assert len(deal.product_urls) == len(deal.available_sizes)
        for url in deal.product_urls:
            assert "colorDisplayCode=00" in url
            assert "sizeDisplayCode=" in url
            assert "/E001/00?" in url

    def test_variant_urls_include_correct_display_codes(
        self, checker: SaleChecker
    ):
        products = [_raw("E001", sizes=["M"])]
        result = self._apply(checker, products)
        assert len(result[0].product_urls) == 1
        assert "sizeDisplayCode=001" in result[0].product_urls[0]

    def test_pants_size_match(self, checker: SaleChecker):
        products = [_raw("E001", sizes=["32inch"])]
        result = self._apply(checker, products)
        assert len(result) == 1

    def test_shoe_size_match(self):
        config = AppConfig.model_validate({
            "filters": {
                "gender": ["men"],
                "min_sale_percentage": 40,
                "sizes": {"shoes": ["42", "42.5"]},
            },
        })
        checker = SaleChecker(config)
        products = [
            _raw("E001", sizes=["41", "42", "43"]),
            _raw("E002", sizes=["38", "39"]),
        ]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert result[0].product_id == "E001"
        assert result[0].available_sizes == ["42"]

    def test_one_size_match(self):
        config = AppConfig.model_validate({
            "filters": {
                "gender": ["men"],
                "min_sale_percentage": 40,
                "sizes": {"one_size": True},
            },
        })
        checker = SaleChecker(config)
        products = [
            _raw("E001", sizes=["One Size"]),
            _raw("E002", sizes=["S", "M"]),
        ]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert result[0].product_id == "E001"
        assert result[0].available_sizes == ["One Size"]

    def test_one_size_disabled_by_default(self, checker: SaleChecker):
        """One Size products don't match unless one_size=true."""
        products = [_raw("E001", sizes=["One Size"])]
        result = self._apply(checker, products)
        assert len(result) == 0

    def test_mixed_size_categories(self):
        """Clothing + shoes + one_size all contribute to the size filter."""
        config = AppConfig.model_validate({
            "filters": {
                "gender": ["men", "women"],
                "min_sale_percentage": 40,
                "sizes": {
                    "clothing": ["M"],
                    "shoes": ["42"],
                    "one_size": True,
                },
            },
        })
        checker = SaleChecker(config)
        products = [
            _raw("E001", sizes=["M", "L"]),
            _raw("E002", sizes=["42", "43"]),
            _raw("E003", sizes=["One Size"]),
            _raw("E004", sizes=["XS"]),
        ]
        result = self._apply(checker, products)
        ids = {r.product_id for r in result}
        assert ids == {"E001", "E002", "E003"}

    def test_watched_product_bypasses_discount_filter(self, checker: SaleChecker):
        products = [_raw("E999999-001", promo=95)]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert result[0].is_watched is True
        assert result[0].discount_percentage == 5.0

    def test_watched_product_includes_filter_and_watched_sizes(
        self, checker: SaleChecker,
    ):
        """Watched items include the watched URL's size plus any filter-matching sizes."""
        products = [_raw("E999999-001", promo=95, sizes=["XS", "M", "XXL"])]
        result = self._apply(checker, products)
        assert len(result) == 1
        # M matches both the size filter and the watched URL (sizeDisplayCode=002)
        assert result[0].available_sizes == ["M"]

    def test_watched_size_outside_filter_is_included(self):
        """A watched variant's size is included even when the global size filter omits it."""
        config = AppConfig.model_validate({
            "filters": {
                "gender": ["men"],
                "min_sale_percentage": 40,
                "sizes": {"clothing": ["L"]},
                "watched_variants": [
                    {"id": "E999999-001", "color": "09", "size": "001"},
                ],
            },
        })
        checker = SaleChecker(config)
        # sizes: XS=001, M=002, L=003
        products = [_raw("E999999-001", promo=95, sizes=["XS", "M", "L"])]
        result = self._apply(checker, products)
        assert len(result) == 1
        # L from filter + XS from watched URL (sizeDisplayCode=001)
        assert "L" in result[0].available_sizes
        assert "XS" in result[0].available_sizes

    def test_sorted_by_discount_descending(self, checker: SaleChecker):
        products = [
            _raw("E001", promo=55),
            _raw("E002", promo=30),
        ]
        result = self._apply(checker, products)
        assert result[0].product_id == "E002"
        assert result[1].product_id == "E001"

    def test_empty_products(self, checker: SaleChecker):
        assert self._apply(checker, []) == []

    def test_no_size_filter_passes_everything(self, default_config: AppConfig):
        checker = SaleChecker(default_config)
        products = [_raw("E001", sizes=["XXS"])]
        result = self._apply(checker, products)
        assert len(result) == 1

    def test_no_size_filter_shows_all_available_sizes(
        self, default_config: AppConfig
    ):
        checker = SaleChecker(default_config)
        products = [_raw("E001", sizes=["S", "M", "L", "XL"])]
        result = self._apply(checker, products)
        assert result[0].available_sizes == ["S", "M", "L", "XL"]

    def test_out_of_stock_sizes_excluded(self, checker: SaleChecker):
        """Product only has XS in stock — doesn't match configured M/L/32inch."""
        products = [_raw("E001", sizes=["XS"])]
        result = self._apply(checker, products)
        assert len(result) == 0

    def test_partial_size_availability(self, checker: SaleChecker):
        """Only M is available but L is out of stock; M should still appear."""
        products = [_raw("E001", sizes=["M"])]
        result = self._apply(checker, products)
        assert len(result) == 1
        assert result[0].available_sizes == ["M"]


def _make_l2(size_name: str, size_dc: str, color_name: str, color_dc: str, l2id: str):
    """Helper to build a minimal L2 variant dict."""
    return {
        "l2Id": l2id,
        "size": {
            "name": size_name,
            "displayCode": size_dc,
            "code": f"SMA{size_dc}",
        },
        "color": {
            "name": color_name,
            "displayCode": color_dc,
            "code": f"COL{color_dc}",
        },
    }


class TestStockVerification:
    """Tests for _pick_in_stock_variant and _verify_stock."""

    def test_picks_highest_quantity_color(self):
        l2s = [
            _make_l2("M", "004", "RED", "15", "A1"),
            _make_l2("M", "004", "BLUE", "64", "A2"),
        ]
        stock = {
            "A1": {"statusCode": "LOW_STOCK", "quantity": 1},
            "A2": {"statusCode": "IN_STOCK", "quantity": 50},
        }
        result = SaleChecker._pick_in_stock_variant("M", l2s, stock, {"M"})
        assert result == ("64", "004", "BLUE", 50, "IN_STOCK", "COL64", "SMA004")

    def test_returns_none_when_all_out_of_stock(self):
        l2s = [_make_l2("M", "004", "RED", "15", "A1")]
        stock = {"A1": {"statusCode": "STOCK_OUT", "quantity": 0}}
        result = SaleChecker._pick_in_stock_variant("M", l2s, stock, {"M"})
        assert result is None

    def test_ignores_wrong_sizes(self):
        l2s = [
            _make_l2("S", "003", "RED", "15", "A1"),
            _make_l2("M", "004", "RED", "15", "A2"),
        ]
        stock = {
            "A1": {"statusCode": "IN_STOCK", "quantity": 100},
            "A2": {"statusCode": "STOCK_OUT", "quantity": 0},
        }
        result = SaleChecker._pick_in_stock_variant("M", l2s, stock, {"M"})
        assert result is None  # only M matters, and it's out

    def test_preferred_color_wins_over_higher_quantity(self):
        """When a watched URL specifies a color, it is preferred if in stock."""
        l2s = [
            _make_l2("M", "004", "RED", "15", "A1"),
            _make_l2("M", "004", "BLUE", "64", "A2"),
        ]
        stock = {
            "A1": {"statusCode": "IN_STOCK", "quantity": 5},
            "A2": {"statusCode": "IN_STOCK", "quantity": 50},
        }
        result = SaleChecker._pick_in_stock_variant(
            "M", l2s, stock, {"M"}, preferred_color="15",
        )
        assert result == ("15", "004", "RED", 5, "IN_STOCK", "COL15", "SMA004")

    def test_preferred_color_falls_back_when_oos(self):
        """If the preferred color is out of stock, fall back to highest quantity."""
        l2s = [
            _make_l2("M", "004", "RED", "15", "A1"),
            _make_l2("M", "004", "BLUE", "64", "A2"),
        ]
        stock = {
            "A1": {"statusCode": "STOCK_OUT", "quantity": 0},
            "A2": {"statusCode": "IN_STOCK", "quantity": 50},
        }
        result = SaleChecker._pick_in_stock_variant(
            "M", l2s, stock, {"M"}, preferred_color="15",
        )
        assert result == ("64", "004", "BLUE", 50, "IN_STOCK", "COL64", "SMA004")

    @pytest.mark.asyncio
    async def test_verify_stock_drops_oos_sizes(self, sale_config: AppConfig):
        checker = SaleChecker(sale_config)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M", "L"], product_urls=["url_m", "url_l"],
            price_group="00",
        )
        l2s = [
            _make_l2("M", "004", "RED", "15", "A1"),
            _make_l2("L", "005", "RED", "15", "A2"),
        ]
        stock = {
            "A1": {"statusCode": "STOCK_OUT", "quantity": 0},
            "A2": {"statusCode": "IN_STOCK", "quantity": 5},
        }
        with (
            patch.object(
                checker._client, "fetch_product_l2s",
                new_callable=AsyncMock, return_value=l2s,
            ),
            patch.object(
                checker._client, "fetch_variant_stock",
                new_callable=AsyncMock, return_value=stock,
            ),
        ):
            result = await checker._verify_stock([item])

        assert len(result) == 1
        assert result[0].available_sizes == ["L"]
        assert "colorDisplayCode=15" in result[0].product_urls[0]
        assert result[0].color_names == ["RED"]
        assert result[0].stock_quantities == [5]
        assert result[0].stock_statuses == ["IN_STOCK"]

    @pytest.mark.asyncio
    async def test_verify_stock_drops_item_when_all_oos(
        self, sale_config: AppConfig,
    ):
        """When a reliable stock API reports 100% OOS the item is dropped."""
        checker = SaleChecker(sale_config)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=["url_m"], price_group="00",
        )
        l2s = [_make_l2("M", "004", "RED", "15", "A1")]
        stock = {"A1": {"statusCode": "STOCK_OUT", "quantity": 0}}
        with (
            patch.object(
                checker._client, "fetch_product_l2s",
                new_callable=AsyncMock, return_value=l2s,
            ),
            patch.object(
                checker._client, "fetch_variant_stock",
                new_callable=AsyncMock, return_value=stock,
            ),
        ):
            result = await checker._verify_stock([item])

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_verify_stock_enriches_urls_for_unreliable_stock_api(self):
        """Countries with stock_api='none' fetch L2 for URLs but skip stock."""
        config = AppConfig.model_validate({
            "uniqlo": {"country": "ph/en"},
            "filters": {"gender": ["men"], "min_sale_percentage": 40},
        })
        assert config.capabilities.stock_api == "none"
        assert config.capabilities.url_style == "code"
        checker = SaleChecker(config)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=["url_m"], price_group="00",
        )
        l2s = [_make_l2("M", "004", "RED", "15", "A1")]
        with (
            patch.object(
                checker._client, "fetch_product_l2s",
                new_callable=AsyncMock, return_value=l2s,
            ) as mock_l2,
            patch.object(
                checker._client, "fetch_variant_stock",
                new_callable=AsyncMock,
            ) as mock_stock,
        ):
            result = await checker._verify_stock([item])

        mock_l2.assert_awaited_once()
        mock_stock.assert_not_awaited()
        assert len(result) == 1
        assert result[0].available_sizes == ["M"]
        assert "colorCode=COL15" in result[0].product_urls[0]
        assert "sizeCode=SMA004" in result[0].product_urls[0]
        assert "/00?" not in result[0].product_urls[0]
        assert result[0].color_names == ["RED"]
        assert result[0].stock_quantities == [0]
        assert result[0].stock_statuses == [""]

    @pytest.mark.asyncio
    async def test_verify_stock_drops_partial_oos(
        self, sale_config: AppConfig
    ):
        """When stock has a mix of statuses and no wanted sizes are in stock,
        the item is dropped (the stock data is considered reliable)."""
        checker = SaleChecker(sale_config)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=["url_m"], price_group="00",
        )
        l2s = [
            _make_l2("M", "004", "RED", "15", "A1"),
            _make_l2("S", "003", "BLUE", "64", "A2"),
        ]
        stock = {
            "A1": {"statusCode": "STOCK_OUT", "quantity": 0},
            "A2": {"statusCode": "IN_STOCK", "quantity": 5},
        }
        with (
            patch.object(
                checker._client, "fetch_product_l2s",
                new_callable=AsyncMock, return_value=l2s,
            ),
            patch.object(
                checker._client, "fetch_variant_stock",
                new_callable=AsyncMock, return_value=stock,
            ),
        ):
            result = await checker._verify_stock([item])

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_verify_stock_keeps_item_on_api_failure(
        self, sale_config: AppConfig
    ):
        """When stock API fails, keep original listing data."""
        checker = SaleChecker(sale_config)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=["url_m"], price_group="00",
        )
        with (
            patch.object(
                checker._client, "fetch_product_l2s",
                new_callable=AsyncMock, return_value=[],
            ),
            patch.object(
                checker._client, "fetch_variant_stock",
                new_callable=AsyncMock, return_value={},
            ),
        ):
            result = await checker._verify_stock([item])

        assert len(result) == 1
        assert result[0].available_sizes == ["M"]


class TestSaleCheckerCheck:
    @pytest.mark.asyncio
    async def test_check_tracks_new_deals(self, sale_config: AppConfig, tmp_path: Path):
        state_file = tmp_path / ".seen_variants.json"
        checker = SaleChecker(sale_config, state_file=state_file)
        products = [
            _product(_raw("E001")),
            _product(_raw("E002", promo=30)),
        ]
        with (
            patch.object(
                checker._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker),
            noop_watched_fetch(checker),
        ):
            result1 = await checker.check()
            assert len(result1.matching_deals) == 2
            assert len(result1.new_deals) == 2

            result2 = await checker.check()
            assert len(result2.matching_deals) == 2
            assert len(result2.new_deals) == 0

    @pytest.mark.asyncio
    async def test_check_detects_newly_added_deal(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        state_file = tmp_path / ".seen_variants.json"
        checker = SaleChecker(sale_config, state_file=state_file)
        products_v1 = [_product(_raw("E001"))]
        products_v2 = [
            _product(_raw("E001")),
            _product(_raw("E002", promo=30)),
        ]
        with (
            patch.object(
                checker._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
            ) as mock,
            noop_verify(checker),
            noop_watched_fetch(checker),
        ):
            mock.return_value = products_v1
            await checker.check()

            mock.return_value = products_v2
            result = await checker.check()
            assert len(result.new_deals) == 1
            assert result.new_deals[0].product_id == "E002"

    @pytest.mark.asyncio
    async def test_state_persists_across_instances(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        """With notify_on=new_deals, a new instance remembers previous deals."""
        sale_config.notifications.notify_on = "new_deals"
        state_file = tmp_path / ".seen_variants.json"
        products = [_product(_raw("E001"))]

        checker1 = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker1._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker1),
            noop_watched_fetch(checker1),
        ):
            result1 = await checker1.check()
            assert len(result1.new_deals) == 1

        assert state_file.exists()

        checker2 = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker2._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker2),
            noop_watched_fetch(checker2),
        ):
            result2 = await checker2.check()
            assert len(result2.new_deals) == 0

    @pytest.mark.asyncio
    async def test_new_variant_detected_as_new(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        """When a product gains a new size variant, it counts as a new deal."""
        state_file = tmp_path / ".seen_variants.json"
        products_v1 = [_product(_raw("E001", sizes=["M"]))]
        products_v2 = [_product(_raw("E001", sizes=["M", "L"]))]

        checker = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
            ) as mock,
            noop_verify(checker),
            noop_watched_fetch(checker),
        ):
            mock.return_value = products_v1
            result1 = await checker.check()
            assert len(result1.new_deals) == 1

            mock.return_value = products_v2
            result2 = await checker.check()
            assert len(result2.new_deals) == 1
            assert "L" in result2.new_deals[0].available_sizes

    @pytest.mark.asyncio
    async def test_price_change_detected_as_new(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        """When a product's discount percentage changes, it counts as a new deal."""
        state_file = tmp_path / ".seen_variants.json"
        products_v1 = [_product(_raw("E001", base=100, promo=40))]  # 60% off
        products_v2 = [_product(_raw("E001", base=100, promo=30))]  # 70% off

        checker = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
            ) as mock,
            noop_verify(checker),
            noop_watched_fetch(checker),
        ):
            mock.return_value = products_v1
            result1 = await checker.check()
            assert len(result1.new_deals) == 1

            mock.return_value = products_v2
            result2 = await checker.check()
            assert len(result2.new_deals) == 1, (
                "A price change should make the deal new again"
            )
            assert result2.new_deals[0].discount_percentage == 70.0

    @pytest.mark.asyncio
    async def test_corrupt_state_file_starts_fresh(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        sale_config.notifications.notify_on = "new_deals"
        state_file = tmp_path / ".seen_variants.json"
        state_file.write_text("not valid json!!!", encoding="utf-8")

        checker = SaleChecker(sale_config, state_file=state_file)
        assert checker._seen_variants == set()

        products = [_product(_raw("E001"))]
        with (
            patch.object(
                checker._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker),
            noop_watched_fetch(checker),
        ):
            result = await checker.check()
            assert len(result.new_deals) == 1

    @pytest.mark.asyncio
    async def test_state_file_format(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        """The state file contains variant keys as product:color:size:discount."""
        state_file = tmp_path / ".seen_variants.json"
        products = [_product(_raw("E001", sizes=["M"]))]

        checker = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker),
            noop_watched_fetch(checker),
        ):
            await checker.check()

        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert "updated_at" in data
        assert isinstance(data["variants"], list)
        assert len(data["variants"]) > 0
        for key in data["variants"]:
            parts = key.split(":")
            assert len(parts) == 4, f"Expected product:color:size:discount, got {key}"


class TestAllThenNewMode:
    """Tests for the all_then_new notification mode."""

    @pytest.mark.asyncio
    async def test_ignores_state_file_on_startup(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        """all_then_new does not load the state file, so first check reports all."""
        state_file = tmp_path / ".seen_variants.json"
        products = [_product(_raw("E001"))]

        # First instance: run a check so the state file is written.
        checker1 = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker1._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker1),
            noop_watched_fetch(checker1),
        ):
            await checker1.check()
        assert state_file.exists()

        # Second instance (simulates restart): state file is ignored.
        checker2 = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker2._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker2),
            noop_watched_fetch(checker2),
        ):
            result = await checker2.check()
            assert len(result.new_deals) == 1, (
                "all_then_new should treat everything as new on startup"
            )

    @pytest.mark.asyncio
    async def test_subsequent_checks_only_new(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        """After the first check, only genuinely new variants are flagged."""
        state_file = tmp_path / ".seen_variants.json"
        products = [_product(_raw("E001"))]

        checker = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker),
            noop_watched_fetch(checker),
        ):
            result1 = await checker.check()
            assert len(result1.new_deals) == 1

            result2 = await checker.check()
            assert len(result2.new_deals) == 0

    @pytest.mark.asyncio
    async def test_new_deals_mode_loads_state(
        self, sale_config: AppConfig, tmp_path: Path,
    ):
        """Contrast: new_deals mode loads state and suppresses already-seen deals."""
        state_file = tmp_path / ".seen_variants.json"
        products = [_product(_raw("E001"))]

        # Run once with all_then_new to populate the state file.
        checker1 = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker1._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker1),
            noop_watched_fetch(checker1),
        ):
            await checker1.check()

        # Switch to new_deals mode and create a fresh instance.
        sale_config.notifications.notify_on = "new_deals"
        checker2 = SaleChecker(sale_config, state_file=state_file)
        with (
            patch.object(
                checker2._client,
                "fetch_sale_products",
                new_callable=AsyncMock,
                return_value=products,
            ),
            noop_verify(checker2),
            noop_watched_fetch(checker2),
        ):
            result = await checker2.check()
            assert len(result.new_deals) == 0, (
                "new_deals mode should suppress already-seen variants on startup"
            )


class TestWatchedProductFetch:
    """Tests for fetching watched products that aren't in the sale catalogue."""

    @pytest.mark.asyncio
    async def test_watched_not_on_sale_is_fetched_separately(self, tmp_path: Path):
        """A watched product that isn't on sale should be fetched via fetch_products_by_ids."""
        config = AppConfig.model_validate({
            "filters": {
                "gender": ["men"],
                "min_sale_percentage": 40,
                "sizes": {"clothing": ["M"]},
                "watched_variants": [
                    {"id": "E777-001", "color": "09", "size": "002"},
                ],
            },
        })
        checker = SaleChecker(config, state_file=tmp_path / ".sv.json")

        sale_products = [_product(_raw("E001"))]
        watched_product = _product(_raw("E777-001", promo=None))

        with (
            patch.object(
                checker._client, "fetch_sale_products",
                new_callable=AsyncMock, return_value=sale_products,
            ),
            patch.object(
                checker._client, "fetch_products_by_ids",
                new_callable=AsyncMock, return_value=[watched_product],
            ) as mock_fetch_ids,
            noop_verify(checker),
        ):
            result = await checker.check()

        mock_fetch_ids.assert_awaited_once()
        ids_requested = mock_fetch_ids.call_args[0][0]
        assert "E777-001" in ids_requested

        pids = {d.product_id for d in result.matching_deals}
        assert "E777-001" in pids
        watched_item = next(d for d in result.matching_deals if d.product_id == "E777-001")
        assert watched_item.is_watched is True
        assert watched_item.discount_percentage == 0.0

    @pytest.mark.asyncio
    async def test_watched_already_on_sale_not_fetched_again(self, tmp_path: Path):
        """When a watched product is already in the sale results, skip fetch_products_by_ids."""
        config = AppConfig.model_validate({
            "filters": {
                "gender": ["men"],
                "min_sale_percentage": 40,
                "sizes": {"clothing": ["M"]},
                "watched_variants": [
                    {"id": "E001", "color": "09", "size": "002"},
                ],
            },
        })
        checker = SaleChecker(config, state_file=tmp_path / ".sv.json")

        sale_products = [_product(_raw("E001"))]

        with (
            patch.object(
                checker._client, "fetch_sale_products",
                new_callable=AsyncMock, return_value=sale_products,
            ),
            patch.object(
                checker._client, "fetch_products_by_ids",
                new_callable=AsyncMock, return_value=[],
            ) as mock_fetch_ids,
            noop_verify(checker),
        ):
            result = await checker.check()

        mock_fetch_ids.assert_not_awaited()
        assert len(result.matching_deals) == 1

    @pytest.mark.asyncio
    async def test_multiple_watched_variants_same_product_fetched_once(
        self, tmp_path: Path,
    ):
        """Two watched variants for the same product should trigger only one fetch."""
        config = AppConfig.model_validate({
            "filters": {
                "gender": ["men"],
                "min_sale_percentage": 40,
                "sizes": {"clothing": ["M"]},
                "watched_variants": [
                    {"id": "E777-001", "color": "09", "size": "002"},
                    {"id": "E777-001", "color": "15", "size": "003"},
                ],
            },
        })
        checker = SaleChecker(config, state_file=tmp_path / ".sv.json")

        watched_product = _product(_raw("E777-001", promo=None))

        with (
            patch.object(
                checker._client, "fetch_sale_products",
                new_callable=AsyncMock, return_value=[],
            ),
            patch.object(
                checker._client, "fetch_products_by_ids",
                new_callable=AsyncMock, return_value=[watched_product],
            ) as mock_fetch_ids,
            noop_verify(checker),
        ):
            await checker.check()

        ids_requested = mock_fetch_ids.call_args[0][0]
        assert ids_requested.count("E777-001") == 1


class TestUnknownDiscountFiltering:
    """Tests for items where promo == base (limited countries like US/CA/JP/KR/SG)."""

    @pytest.fixture()
    def checker(self, sale_config: AppConfig) -> SaleChecker:
        return SaleChecker(sale_config)

    def test_unknown_discount_passes_through(self, checker: SaleChecker):
        """Items with promo == base pass filters, bypass min_percentage,
        and set has_known_discount=False."""
        products = [_product(_raw("E001", base=50, promo=50))]
        result = checker._apply_filters(products)
        assert len(result) == 1
        assert result[0].product_id == "E001"
        assert result[0].discount_percentage == 0
        assert result[0].has_known_discount is False

    def test_known_discount_has_known_discount_true(self, checker: SaleChecker):
        products = [_product(_raw("E001", base=100, promo=40))]
        result = checker._apply_filters(products)
        assert result[0].has_known_discount is True

    @pytest.mark.parametrize("raw_kwargs", [
        pytest.param(dict(base=50, promo=50, gender="WOMEN"), id="wrong_gender"),
        pytest.param(dict(base=50, promo=50, sizes=["XXS"]), id="wrong_size"),
    ])
    def test_unknown_discount_still_filtered(self, checker: SaleChecker, raw_kwargs):
        products = [_product(_raw("E001", **raw_kwargs))]
        result = checker._apply_filters(products)
        assert len(result) == 0

    def test_mixed_known_and_unknown(self, checker: SaleChecker):
        """Known-discount items still honour min_sale_percentage."""
        products = [
            _product(_raw("E001", base=100, promo=100)),  # unknown
            _product(_raw("E002", base=100, promo=80)),   # 20% — below 40% min
            _product(_raw("E003", base=100, promo=50)),   # 50% — passes
        ]
        result = checker._apply_filters(products)
        pids = {r.product_id for r in result}
        assert pids == {"E001", "E003"}

    def test_no_promo_watched_only_has_known_discount_true(self, checker: SaleChecker):
        """Watched-only items with promo=None have known pricing (no discount)."""
        products = [_product(_raw("E001", base=50, promo=None))]
        result = checker._apply_filters(products, sale_product_ids=set())
        assert len(result) == 1
        assert result[0].has_known_discount is True
        assert result[0].discount_percentage == 0

    def test_no_promo_sale_feed_has_known_discount_false(self, checker: SaleChecker):
        """Sale-feed items with promo=None show 'Sale' (unknown discount)."""
        products = [_product(_raw("E001", base=50, promo=None))]
        result = checker._apply_filters(products, sale_product_ids={"E001"})
        assert len(result) == 1
        assert result[0].has_known_discount is False


class TestVariantKeys:
    """Unit tests for the _variant_keys helper."""

    @pytest.mark.parametrize("deal_kwargs,expected_keys", [
        pytest.param(
            dict(
                product_id="E001", discount_percentage=60,
                available_sizes=["M", "L"],
                product_urls=[
                    "https://www.uniqlo.com/de/de/products/E001/00?colorDisplayCode=09&sizeDisplayCode=004",
                    "https://www.uniqlo.com/de/de/products/E001/00?colorDisplayCode=09&sizeDisplayCode=005",
                ],
            ),
            {"E001:09:004:60", "E001:09:005:60"},
            id="extracts_keys_from_urls",
        ),
        pytest.param(
            dict(
                product_id="E001", discount_percentage=60,
                available_sizes=["M"],
                product_urls=[
                    "https://x.com/products/E001/00?colorDisplayCode=01&sizeDisplayCode=004",
                    "https://x.com/products/E001/00?colorDisplayCode=09&sizeDisplayCode=004",
                ],
            ),
            {"E001:01:004:60", "E001:09:004:60"},
            id="different_colors_same_size",
        ),
        pytest.param(
            dict(
                product_id="E001", discount_percentage=60,
                available_sizes=["M"], product_urls=[],
            ),
            {"E001:60"},
            id="fallback_no_urls",
        ),
        pytest.param(
            dict(
                product_id="E001", original_price=50, sale_price=50,
                discount_percentage=0, has_known_discount=False,
                available_sizes=["M"],
                product_urls=[
                    "https://x.com/products/E001/00?colorDisplayCode=09&sizeDisplayCode=004",
                ],
            ),
            {"E001:09:004:sale"},
            id="unknown_discount_with_url",
        ),
        pytest.param(
            dict(
                product_id="E001", original_price=50, sale_price=50,
                discount_percentage=0, has_known_discount=False,
                available_sizes=["M"], product_urls=[],
            ),
            {"E001:sale"},
            id="unknown_discount_fallback",
        ),
    ])
    def test_variant_keys(self, default_config, deal_kwargs, expected_keys):
        checker = SaleChecker(default_config)
        item = sample_deal(**deal_kwargs)
        assert checker._variant_keys(item) == expected_keys


class TestLowStockSuppression:
    """The ``suppress_low_stock_alerts`` toggle omits low-stock variant keys.

    With the toggle on, low-stock variants stay *unseen* (absent from the
    seen-set), so future checks only add them back — and therefore fire a
    new-deal alert — once the quantity climbs above the threshold.
    """

    _URLS = [
        "https://x.com/products/E001/00?colorDisplayCode=09&sizeDisplayCode=004",
    ]
    _URLS_MULTI = [
        "https://x.com/products/E001/00?colorDisplayCode=09&sizeDisplayCode=004",
        "https://x.com/products/E001/00?colorDisplayCode=09&sizeDisplayCode=005",
    ]

    def _checker(
        self, *, suppress: bool, threshold: int = 5,
    ) -> SaleChecker:
        cfg = AppConfig.model_validate({
            "notifications": {
                "suppress_low_stock_alerts": suppress,
                "low_stock_threshold": threshold,
            },
        })
        return SaleChecker(cfg)

    def test_toggle_off_keys_unchanged(self):
        """Classic behaviour: low-stock variants still produce keys."""
        checker = self._checker(suppress=False, threshold=5)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=self._URLS,
            stock_quantities=[3], stock_statuses=["IN_STOCK"],
        )
        assert checker._variant_keys(item) == {"E001:09:004:60"}

    def test_toggle_on_suppresses_low_stock_key(self):
        """Low-stock variant must not appear in the key set."""
        checker = self._checker(suppress=True, threshold=5)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=self._URLS,
            stock_quantities=[3], stock_statuses=["IN_STOCK"],
        )
        assert checker._variant_keys(item) == set()

    def test_toggle_on_keeps_non_low_variants(self):
        """Only low-stock variants are filtered; healthy ones survive."""
        checker = self._checker(suppress=True, threshold=5)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M", "L"], product_urls=self._URLS_MULTI,
            stock_quantities=[3, 20], stock_statuses=["IN_STOCK", "IN_STOCK"],
        )
        assert checker._variant_keys(item) == {"E001:09:005:60"}

    def test_toggle_on_respects_threshold_precedence(self):
        """API LOW_STOCK is ignored when user threshold is set."""
        checker = self._checker(suppress=True, threshold=5)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=self._URLS,
            stock_quantities=[42], stock_statuses=["LOW_STOCK"],
        )
        # qty 42 > threshold 5 → not low → key kept.
        assert checker._variant_keys(item) == {"E001:09:004:60"}

    def test_toggle_on_uses_api_fallback_when_threshold_zero(self):
        """Threshold 0 falls back to API flag for low-stock determination."""
        checker = self._checker(suppress=True, threshold=0)
        item = sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=self._URLS,
            stock_quantities=[42], stock_statuses=["LOW_STOCK"],
        )
        # API says low → key filtered out.
        assert checker._variant_keys(item) == set()


class TestNewDealDedup:
    """End-to-end retrigger behaviour with and without the suppression toggle."""

    _URLS = [
        "https://x.com/products/E001/00?colorDisplayCode=09&sizeDisplayCode=004",
    ]

    def _cfg(self, *, suppress: bool, threshold: int) -> AppConfig:
        return AppConfig.model_validate({
            "notifications": {
                "notify_on": "new_deals",
                "suppress_low_stock_alerts": suppress,
                "low_stock_threshold": threshold,
            },
        })

    def _build_item(self, qty: int) -> object:
        return sample_deal(
            product_id="E001", discount_percentage=60,
            available_sizes=["M"], product_urls=self._URLS,
            stock_quantities=[qty], stock_statuses=["IN_STOCK"],
        )

    def _run_check(
        self, cfg: AppConfig, item, state_file: Path,
    ) -> tuple[set[str], list[str]]:
        """Simulate one check cycle; return (new_seen_set, new_deal_keys)."""
        checker = SaleChecker(cfg, state_file=state_file)
        seen_before = checker._seen_variants
        keys = checker._variant_keys(item)
        new_keys = sorted(keys - seen_before)
        checker._save_state(keys)
        return keys, new_keys

    def test_qty_fluctuation_above_threshold_does_not_retrigger(
        self, tmp_path: Path,
    ):
        """20 -> 10 (both above 5): no alert either time."""
        cfg = self._cfg(suppress=False, threshold=5)
        state = tmp_path / ".seen.json"
        _, first = self._run_check(cfg, self._build_item(20), state)
        _, second = self._run_check(cfg, self._build_item(10), state)
        assert first, "first check must fire"
        assert second == [], "qty drop within normal stock must not retrigger"

    def test_oos_to_low_restock_suppressed_when_toggle_on(
        self, tmp_path: Path,
    ):
        """Item at 20 → OOS → restock at 2 (≤ threshold) must NOT alert."""
        cfg = self._cfg(suppress=True, threshold=5)
        state = tmp_path / ".seen.json"
        # First run: healthy qty → key saved.
        self._run_check(cfg, self._build_item(20), state)
        # OOS run: item missing from matching → keys for this item not in current.
        # We simulate by having an empty matching set: just clear state.
        SaleChecker(cfg, state_file=state)._save_state(set())
        # Restock at low level — toggle must suppress.
        _, new_keys = self._run_check(cfg, self._build_item(2), state)
        assert new_keys == [], "low-stock restock must be suppressed"

    def test_oos_to_low_restock_alerts_when_toggle_off(
        self, tmp_path: Path,
    ):
        """Same sequence without the toggle: user gets the classic restock alert."""
        cfg = self._cfg(suppress=False, threshold=5)
        state = tmp_path / ".seen.json"
        self._run_check(cfg, self._build_item(20), state)
        SaleChecker(cfg, state_file=state)._save_state(set())
        _, new_keys = self._run_check(cfg, self._build_item(2), state)
        assert new_keys, "without the toggle, any restock should retrigger"

    def test_low_restock_then_climb_fires_once_above_threshold(
        self, tmp_path: Path,
    ):
        """Toggle on: suppressed at 2, then alert fires when qty climbs to 20."""
        cfg = self._cfg(suppress=True, threshold=5)
        state = tmp_path / ".seen.json"
        # Restock at low level — no alert.
        _, low = self._run_check(cfg, self._build_item(2), state)
        assert low == []
        # Climb to healthy — alert fires.
        _, high = self._run_check(cfg, self._build_item(20), state)
        assert high, "alert must fire when qty climbs above the threshold"

    def test_first_seen_low_stock_is_suppressed(self, tmp_path: Path):
        """A brand-new item first spotted at low stock must not alert."""
        cfg = self._cfg(suppress=True, threshold=5)
        state = tmp_path / ".seen.json"
        _, new_keys = self._run_check(cfg, self._build_item(3), state)
        assert new_keys == []
