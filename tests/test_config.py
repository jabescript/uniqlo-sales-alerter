"""Tests for config loading and validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from uniqlo_sales_alerter.config import (
    AppConfig,
    _coerce,
    _config_from_env,
    _deep_merge,
    load_config,
)


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

    def test_sale_paths_default_empty(self):
        cfg = AppConfig()
        assert cfg.uniqlo.sale_paths == []

    def test_sale_paths_configured(self):
        cfg = AppConfig.model_validate({
            "uniqlo": {"country": "sg/en", "sale_paths": ["5855", "5856"]},
        })
        assert cfg.uniqlo.sale_paths == ["5855", "5856"]


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


class TestCoerce:
    @pytest.mark.parametrize("value,type_name,expected", [
        ("hello", "str", "hello"),
        ("42", "int", 42),
        ("30.5", "float", 30.5),
        ("S, M, L", "list", ["S", "M", "L"]),
        ("men", "list", ["men"]),
        ("", "list", []),
    ])
    def test_coerce(self, value, type_name, expected):
        assert _coerce(value, type_name) == expected

    def test_coerce_bool_true(self):
        for val in ("1", "true", "True", "TRUE", "yes", "YES"):
            assert _coerce(val, "bool") is True

    def test_coerce_bool_false(self):
        for val in ("0", "false", "no", "other"):
            assert _coerce(val, "bool") is False


class TestDeepMerge:
    @pytest.mark.parametrize("base,override,expected", [
        pytest.param({"a": 1}, {"b": 2}, {"a": 1, "b": 2}, id="flat"),
        pytest.param({"a": 1}, {"a": 2}, {"a": 2}, id="override"),
        pytest.param(
            {"a": {"x": 1, "y": 2}}, {"a": {"y": 3, "z": 4}},
            {"a": {"x": 1, "y": 3, "z": 4}}, id="nested",
        ),
        pytest.param({"a": [1]}, {"a": [2, 3]}, {"a": [2, 3]}, id="non_dict_override"),
    ])
    def test_deep_merge(self, base, override, expected):
        assert _deep_merge(base, override) == expected


class TestConfigFromEnv:
    def test_picks_up_set_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIQLO_COUNTRY", "uk/en")
        monkeypatch.setenv("FILTER_MIN_SALE_PERCENTAGE", "25")
        result = _config_from_env()
        assert result["uniqlo"]["country"] == "uk/en"
        assert result["filters"]["min_sale_percentage"] == 25.0

    def test_ignores_unset_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("UNIQLO_COUNTRY", raising=False)
        result = _config_from_env()
        assert "uniqlo" not in result or "country" not in result.get("uniqlo", {})

    def test_list_var(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FILTER_GENDER", "men,women,unisex")
        result = _config_from_env()
        assert result["filters"]["gender"] == ["men", "women", "unisex"]

    def test_nested_sizes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FILTER_SIZES_CLOTHING", "S,M,L")
        monkeypatch.setenv("FILTER_SIZES_ONE_SIZE", "true")
        result = _config_from_env()
        assert result["filters"]["sizes"]["clothing"] == ["S", "M", "L"]
        assert result["filters"]["sizes"]["one_size"] is True

    def test_telegram_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok123")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "456")
        result = _config_from_env()
        tg = result["notifications"]["channels"]["telegram"]
        assert tg["enabled"] is True
        assert tg["bot_token"] == "tok123"
        assert tg["chat_id"] == "456"

    def test_smtp_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("SMTP_HOST", "mail.example.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_TO", "a@b.com,c@d.com")
        result = _config_from_env()
        email = result["notifications"]["channels"]["email"]
        assert email["smtp_host"] == "mail.example.com"
        assert email["smtp_port"] == 465
        assert email["to_addresses"] == ["a@b.com", "c@d.com"]


class TestLoadConfigEnvVars:
    """Integration tests for load_config with env-var-only and hybrid modes."""

    def test_env_only_no_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("UNIQLO_COUNTRY", "us/en")
        monkeypatch.setenv("FILTER_GENDER", "men")
        monkeypatch.setenv("FILTER_MIN_SALE_PERCENTAGE", "20")
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.country_code == "us"
        assert cfg.filters.gender == ["MEN"]
        assert cfg.filters.min_sale_percentage == 20.0

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        yaml_content = textwrap.dedent("""\
            uniqlo:
              country: "de/de"
            filters:
              min_sale_percentage: 50
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)
        monkeypatch.setenv("UNIQLO_COUNTRY", "fr/fr")
        cfg = load_config(config_file)
        assert cfg.country_code == "fr"
        assert cfg.filters.min_sale_percentage == 50.0

    def test_env_merges_with_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        yaml_content = textwrap.dedent("""\
            uniqlo:
              country: "de/de"
              check_interval_minutes: 60
        """)
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml_content)
        monkeypatch.setenv("TELEGRAM_ENABLED", "true")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        cfg = load_config(config_file)
        assert cfg.country_code == "de"
        assert cfg.uniqlo.check_interval_minutes == 60
        assert cfg.notifications.channels.telegram.enabled is True
        assert cfg.notifications.channels.telegram.bot_token == "tok"
