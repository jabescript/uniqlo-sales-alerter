"""Tests for config loading and validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from uniqlo_sales_alerter.config import AppConfig, load_config


class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.country_code == "de"
        assert cfg.lang_code == "de"
        assert cfg.base_url == "https://www.uniqlo.com/de/api/commerce/v5/de/products"
        assert cfg.client_id == "uq.de.web-spa"
        assert cfg.filters.min_sale_percentage == 50.0

    def test_uk_country(self):
        cfg = AppConfig.model_validate({"uniqlo": {"country": "uk/en"}})
        assert cfg.country_code == "uk"
        assert cfg.lang_code == "en"
        assert cfg.client_id == "uq.gb.web-spa"
        assert "uk/api/commerce/v5/en" in cfg.base_url

    def test_gender_normalised_to_upper(self):
        cfg = AppConfig.model_validate({"filters": {"gender": ["men", "Women"]}})
        assert cfg.filters.gender == ["MEN", "WOMEN"]

    def test_product_page_base(self):
        cfg = AppConfig.model_validate({"uniqlo": {"country": "fr/fr"}})
        assert cfg.product_page_base == "https://www.uniqlo.com/fr/fr/products"

    def test_size_filters_shoes_and_one_size(self):
        cfg = AppConfig.model_validate({
            "filters": {
                "sizes": {
                    "shoes": ["42", "42.5"],
                    "one_size": True,
                },
            },
        })
        assert cfg.filters.sizes.shoes == ["42", "42.5"]
        assert cfg.filters.sizes.one_size is True

    def test_size_filters_one_size_defaults_false(self):
        cfg = AppConfig()
        assert cfg.filters.sizes.one_size is False
        assert cfg.filters.sizes.shoes == []


class TestLoadConfig:
    def test_load_from_yaml(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            uniqlo:
              country: "uk/en"
              check_interval_minutes: 15
            filters:
              gender:
                - women
              min_sale_percentage: 30
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)
        cfg = load_config(config_file)

        assert cfg.country_code == "uk"
        assert cfg.uniqlo.check_interval_minutes == 15
        assert cfg.filters.gender == ["WOMEN"]
        assert cfg.filters.min_sale_percentage == 30.0

    def test_env_var_resolution(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MY_TOKEN", "secret123")
        yaml_content = textwrap.dedent("""\
            notifications:
              channels:
                telegram:
                  enabled: true
                  bot_token: "${MY_TOKEN}"
                  chat_id: "12345"
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)
        cfg = load_config(config_file)

        assert cfg.notifications.channels.telegram.bot_token == "secret123"
        assert cfg.notifications.channels.telegram.chat_id == "12345"

    def test_missing_file_returns_defaults(self, tmp_path: Path):
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.country_code == "de"

    def test_empty_file_returns_defaults(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        cfg = load_config(config_file)
        assert cfg.country_code == "de"
