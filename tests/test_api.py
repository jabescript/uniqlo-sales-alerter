"""Tests for the FastAPI REST endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from uniqlo_sales_alerter.config import AppConfig
from uniqlo_sales_alerter.models.products import SaleCheckResult, SaleItem
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.services.sale_checker import SaleChecker

from .conftest import sample_deal as _sample_deal


def _make_result(deals: list[SaleItem] | None = None) -> SaleCheckResult:
    deals = deals or [_sample_deal()]
    return SaleCheckResult(
        checked_at=datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc),
        total_products_scanned=1000,
        total_on_sale=50,
        matching_deals=deals,
        new_deals=deals,
    )


@pytest.fixture()
def client():
    """Create a TestClient with a pre-populated state (no actual API calls)."""
    from uniqlo_sales_alerter.main import AppState, app

    config = AppConfig()
    checker = SaleChecker(config)
    dispatcher = NotificationDispatcher(config)
    checker.last_result = _make_result()

    app.state.app_state = AppState(
        config=config,
        sale_checker=checker,
        dispatcher=dispatcher,
    )

    app.router.lifespan_context = None  # type: ignore[assignment]
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestSalesEndpoint:
    def test_get_sales(self, client: TestClient):
        resp = client.get("/api/v1/sales")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_products_scanned"] == 1000
        assert len(data["matching_deals"]) == 1
        assert data["matching_deals"][0]["product_id"] == "E123456-000"

    def test_returns_503_when_no_result(self, client: TestClient):
        from uniqlo_sales_alerter.main import app

        app.state.app_state.sale_checker.last_result = None
        resp = client.get("/api/v1/sales")
        assert resp.status_code == 503

    def test_filter_by_gender(self, client: TestClient):
        from uniqlo_sales_alerter.main import app

        deals = [
            _sample_deal(product_id="E001", gender="MEN"),
            _sample_deal(product_id="E002", gender="WOMEN"),
        ]
        app.state.app_state.sale_checker.last_result = _make_result(deals)

        resp = client.get("/api/v1/sales?gender=women")
        data = resp.json()
        assert len(data["matching_deals"]) == 1
        assert data["matching_deals"][0]["product_id"] == "E002"

    def test_filter_by_min_discount(self, client: TestClient):
        from uniqlo_sales_alerter.main import app

        deals = [
            _sample_deal(product_id="E001", discount_percentage=60),
            _sample_deal(product_id="E002", discount_percentage=30),
        ]
        app.state.app_state.sale_checker.last_result = _make_result(deals)

        resp = client.get("/api/v1/sales?min_discount=50")
        data = resp.json()
        assert len(data["matching_deals"]) == 1
        assert data["matching_deals"][0]["product_id"] == "E001"


class TestProductEndpoint:
    def test_get_existing_product(self, client: TestClient):
        resp = client.get("/api/v1/products/E123456-000")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test T-Shirt"

    def test_product_not_found(self, client: TestClient):
        resp = client.get("/api/v1/products/ENOTFOUND")
        assert resp.status_code == 404


class TestConfigEndpoint:
    def test_get_config_redacts_secrets(self, client: TestClient):
        from uniqlo_sales_alerter.main import app

        app.state.app_state.config = AppConfig.model_validate({
            "notifications": {
                "channels": {
                    "telegram": {"enabled": True, "bot_token": "secret_tok", "chat_id": "123"},
                    "email": {"enabled": True, "smtp_password": "secret_pw"},
                },
            },
        })

        resp = client.get("/api/v1/config")
        data = resp.json()
        assert data["notifications"]["channels"]["telegram"]["bot_token"] == "***"
        assert data["notifications"]["channels"]["email"]["smtp_password"] == "***"


class TestTriggerCheck:
    def test_trigger_check(self, client: TestClient):
        from uniqlo_sales_alerter.main import app

        result = _make_result()
        with patch.object(
            app.state.app_state.sale_checker,
            "check", new_callable=AsyncMock, return_value=result,
        ):
            resp = client.post("/api/v1/sales/check")
            assert resp.status_code == 200
            assert resp.json()["total_products_scanned"] == 1000


class TestUnwatchAction:
    """The /actions/unwatch endpoint should filter by color+size when provided."""

    def _set_watched(self, client: TestClient, variants: list[dict]) -> None:
        from uniqlo_sales_alerter.main import app

        app.state.app_state.config = AppConfig.model_validate({
            "filters": {"watched_variants": variants},
        })

    def test_unwatch_with_color_and_size_removes_only_matching(
        self, client: TestClient,
    ):
        self._set_watched(client, [
            {"id": "E001", "color": "09", "size": "002", "name": "Black M"},
            {"id": "E001", "color": "01", "size": "003", "name": "White L"},
        ])

        with patch(
            "uniqlo_sales_alerter.api.routes._save_and_reload",
            new_callable=AsyncMock,
        ) as mock_save:
            resp = client.get(
                "/actions/unwatch/E001?name=Test&color=09&size=002",
                follow_redirects=False,
            )
            assert resp.status_code == 200
            assert "removed" in resp.text.lower()
            saved_data = mock_save.call_args[0][0]
            remaining = saved_data["filters"]["watched_variants"]
            assert len(remaining) == 1
            assert remaining[0]["color"] == "01"
            assert remaining[0]["size"] == "003"

    def test_unwatch_without_color_removes_all_for_product(
        self, client: TestClient,
    ):
        self._set_watched(client, [
            {"id": "E001", "color": "09", "size": "002", "name": "Black M"},
            {"id": "E001", "color": "01", "size": "003", "name": "White L"},
            {"id": "E002", "color": "05", "size": "001", "name": "Other"},
        ])

        with patch(
            "uniqlo_sales_alerter.api.routes._save_and_reload",
            new_callable=AsyncMock,
        ) as mock_save:
            resp = client.get(
                "/actions/unwatch/E001?name=Test",
                follow_redirects=False,
            )
            assert resp.status_code == 200
            saved_data = mock_save.call_args[0][0]
            remaining = saved_data["filters"]["watched_variants"]
            assert len(remaining) == 1
            assert remaining[0]["id"] == "E002"

    def test_unwatch_nonexistent_variant_returns_not_watched(
        self, client: TestClient,
    ):
        self._set_watched(client, [
            {"id": "E001", "color": "09", "size": "002", "name": "Black M"},
        ])
        resp = client.get(
            "/actions/unwatch/E001?name=Test&color=99&size=999",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "not on your" in resp.text.lower() or "not watched" in resp.text.lower()
