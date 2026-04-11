"""Configuration loading and validation.

Reads ``config.yaml``, resolves ``${ENV_VAR}`` placeholders from environment
variables, and exposes the result as typed Pydantic models.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"


def _resolve_env_vars(value: object) -> object:
    """Recursively walk a data structure and replace ``${VAR}`` with ``os.environ[VAR]``."""
    if isinstance(value, str):
        def _replacer(match: re.Match[str]) -> str:
            var = match.group(1)
            resolved = os.environ.get(var, "")
            if not resolved:
                logger.warning("Environment variable %s is not set", var)
            return resolved

        return _ENV_VAR_RE.sub(_replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Pydantic config models
# ---------------------------------------------------------------------------


class UniqloConfig(BaseModel):
    country: str = "de/de"
    check_interval_minutes: int = Field(default=30, ge=1)


class SizeFilters(BaseModel):
    clothing: list[str] = Field(default_factory=list)
    pants: list[str] = Field(default_factory=list)
    shoes: list[str] = Field(default_factory=list)
    one_size: bool = False


class FilterConfig(BaseModel):
    gender: list[str] = Field(default_factory=lambda: ["men", "women"])
    min_sale_percentage: float = Field(default=50.0, ge=0, le=100)
    sizes: SizeFilters = Field(default_factory=SizeFilters)
    watched_urls: list[str] = Field(default_factory=list)


class TelegramChannelConfig(BaseModel):
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


class EmailChannelConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    use_tls: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)


class ChannelsConfig(BaseModel):
    telegram: TelegramChannelConfig = Field(default_factory=TelegramChannelConfig)
    email: EmailChannelConfig = Field(default_factory=EmailChannelConfig)


class NotificationConfig(BaseModel):
    preview_cli: bool = False
    preview_html: bool = False
    notify_on: Literal["all_then_new", "new_deals", "every_check"] = "all_then_new"
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)


class AppConfig(BaseModel):
    uniqlo: UniqloConfig = Field(default_factory=UniqloConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)

    @model_validator(mode="after")
    def _normalise_gender(self) -> "AppConfig":
        self.filters.gender = [g.upper() for g in self.filters.gender]
        return self

    @property
    def country_code(self) -> str:
        """First segment of the country path, e.g. ``'de'`` from ``'de/de'``."""
        return self.uniqlo.country.split("/")[0]

    @property
    def lang_code(self) -> str:
        """Second segment of the country path, e.g. ``'de'`` from ``'de/de'``."""
        parts = self.uniqlo.country.split("/")
        return parts[1] if len(parts) > 1 else parts[0]

    @property
    def base_url(self) -> str:
        return f"https://www.uniqlo.com/{self.country_code}/api/commerce/v5/{self.lang_code}/products"

    _CLIENT_ID_COUNTRY_OVERRIDES: dict[str, str] = {"uk": "gb"}

    @property
    def client_id(self) -> str:
        cc = self._CLIENT_ID_COUNTRY_OVERRIDES.get(self.country_code, self.country_code)
        return f"uq.{cc}.web-spa"

    @property
    def product_page_base(self) -> str:
        return f"https://www.uniqlo.com/{self.uniqlo.country}/products"


def load_config(path: Path | str | None = None) -> AppConfig:
    """Load and validate configuration from a YAML file.

    Environment variable placeholders (``${VAR}``) are resolved before
    validation so that secrets never need to live in the YAML file.
    """
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not config_path.exists():
        logger.warning("Config file %s not found, using defaults", config_path)
        return AppConfig()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    resolved = _resolve_env_vars(raw)
    return AppConfig.model_validate(resolved)
