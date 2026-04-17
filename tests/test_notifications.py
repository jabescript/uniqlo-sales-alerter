"""Tests for the notification system."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from uniqlo_sales_alerter.config import AppConfig, EmailChannelConfig, TelegramChannelConfig
from uniqlo_sales_alerter.notifications.base import Notifier
from uniqlo_sales_alerter.notifications.console import ConsoleNotifier, _format_deal
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.notifications.email import EmailNotifier, _build_html, _expand_to_variants
from uniqlo_sales_alerter.notifications.html_report import HtmlReportNotifier, _build_report
from uniqlo_sales_alerter.notifications.telegram import TelegramNotifier, _build_caption

from .conftest import sample_deal as _sample_deal

_UNKNOWN_DISCOUNT_OVERRIDES = dict(
    original_price=49.90,
    sale_price=49.90,
    discount_percentage=0,
    has_known_discount=False,
    currency_symbol="$",
)


class TestTelegramCaption:
    def test_basic_caption(self):
        deal = _sample_deal()
        caption = _build_caption(deal)
        assert "Test T\\-Shirt" in caption
        assert "19\\.90" in caption
        assert "39\\.90" in caption
        assert "[S](" in caption
        assert "[M](" in caption
        assert "[L](" in caption

    def test_watched_badge(self):
        deal = _sample_deal(is_watched=True)
        caption = _build_caption(deal)
        assert "Watched item" in caption

    def test_no_watched_badge(self):
        deal = _sample_deal(is_watched=False)
        caption = _build_caption(deal)
        assert "Watched" not in caption

    def test_caption_shows_color(self):
        deal = _sample_deal(color_names=["SCHWARZ", "SCHWARZ", "SCHWARZ"])
        caption = _build_caption(deal)
        assert "Color: SCHWARZ" in caption

    def test_caption_hides_color_when_empty(self):
        deal = _sample_deal(color_names=["", "", ""])
        caption = _build_caption(deal)
        assert "Color:" not in caption


class TestTelegramNotifier:
    def test_is_enabled(self):
        cfg = TelegramChannelConfig(enabled=True, bot_token="tok", chat_id="123")
        assert TelegramNotifier(cfg).is_enabled() is True

    def test_disabled_when_no_token(self):
        cfg = TelegramChannelConfig(enabled=True, bot_token="", chat_id="123")
        assert TelegramNotifier(cfg).is_enabled() is False

    def test_disabled_when_flag_off(self):
        cfg = TelegramChannelConfig(enabled=False, bot_token="tok", chat_id="123")
        assert TelegramNotifier(cfg).is_enabled() is False


class TestEmailHtml:
    def test_html_contains_deal_info(self):
        deal = _sample_deal()
        html = _build_html([deal])
        assert "Test T-Shirt" in html
        assert "19.90" in html
        assert "39.90" in html
        assert "50%" in html
        assert "img" in html

    def test_html_size_links(self):
        deal = _sample_deal()
        html = _build_html([deal])
        assert 'href="' in html
        assert ">S</a>" in html
        assert ">M</a>" in html
        assert ">L</a>" in html

    def test_html_watched_badge(self):
        deal = _sample_deal(is_watched=True)
        html = _build_html([deal])
        assert "Watched" in html

    def test_html_shows_color_name(self):
        deal = _sample_deal(color_names=["SCHWARZ", "SCHWARZ", "SCHWARZ"])
        html = _build_html([deal])
        assert "SCHWARZ" in html
        assert "Color:" in html

    def test_html_hides_color_when_empty(self):
        deal = _sample_deal(color_names=["", "", ""])
        html = _build_html([deal])
        assert "Color:" not in html

    def test_html_expands_to_per_variant_rows(self):
        deal = _sample_deal()
        html = _build_html([deal])
        assert html.count("<tr") == 3  # one row per size variant

    def test_expand_to_variants_splits_sizes(self):
        deal = _sample_deal()
        variants = _expand_to_variants(deal)
        assert len(variants) == 3
        assert variants[0].available_sizes == ["S"]
        assert variants[1].available_sizes == ["M"]
        assert variants[2].available_sizes == ["L"]

    def test_expand_to_variants_preserves_single_size(self):
        deal = _sample_deal(
            available_sizes=["M"],
            product_urls=["https://example.com/p?colorDisplayCode=00&sizeDisplayCode=002"],
            color_names=["SCHWARZ"],
        )
        variants = _expand_to_variants(deal)
        assert len(variants) == 1
        assert variants[0] is deal


def _make_email_cfg(**overrides) -> EmailChannelConfig:
    defaults = dict(
        enabled=True, smtp_host="smtp.test.com", smtp_port=587,
        use_tls=True, from_address="me@test.com", to_addresses=["a@b.com"],
    )
    defaults.update(overrides)
    return EmailChannelConfig(**defaults)


class TestEmailNotifier:
    def test_is_enabled(self):
        assert EmailNotifier(_make_email_cfg()).is_enabled() is True

    def test_disabled_when_no_recipients(self):
        assert EmailNotifier(_make_email_cfg(to_addresses=[])).is_enabled() is False

    def test_disabled_when_no_from_address(self):
        assert EmailNotifier(_make_email_cfg(from_address="")).is_enabled() is False

    def test_disabled_when_flag_off(self):
        assert EmailNotifier(_make_email_cfg(enabled=False)).is_enabled() is False

    @pytest.mark.asyncio
    async def test_send_calls_aiosmtplib(self, monkeypatch):
        import aiosmtplib

        sent_kwargs: dict = {}

        async def fake_send(msg, **kwargs):
            sent_kwargs.update(kwargs)
            return ({}, "OK")

        monkeypatch.setattr(aiosmtplib, "send", fake_send)

        cfg = _make_email_cfg(smtp_user="user", smtp_password="pass")
        await EmailNotifier(cfg).send([_sample_deal()])

        assert sent_kwargs["hostname"] == "smtp.test.com"
        assert sent_kwargs["port"] == 587
        assert sent_kwargs["start_tls"] is True
        assert sent_kwargs["use_tls"] is False
        assert sent_kwargs["username"] == "user"
        assert sent_kwargs["password"] == "pass"
        assert sent_kwargs["timeout"] == 30

    @pytest.mark.asyncio
    async def test_send_uses_implicit_tls_for_port_465(self, monkeypatch):
        import aiosmtplib

        sent_kwargs: dict = {}

        async def fake_send(msg, **kwargs):
            sent_kwargs.update(kwargs)
            return ({}, "OK")

        monkeypatch.setattr(aiosmtplib, "send", fake_send)

        await EmailNotifier(_make_email_cfg(smtp_port=465)).send([_sample_deal()])

        assert sent_kwargs["use_tls"] is True
        assert sent_kwargs["start_tls"] is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc_factory", [
        lambda m: m.SMTPAuthenticationError(535, "fail"),
        lambda m: m.SMTPConnectError("refused"),
        lambda m: m.SMTPTimeoutError("timed out"),
    ])
    async def test_send_smtp_errors_raise(self, monkeypatch, exc_factory):
        import aiosmtplib

        exc = exc_factory(aiosmtplib)

        async def fail(msg, **kwargs):
            raise exc

        monkeypatch.setattr(aiosmtplib, "send", fail)

        with pytest.raises(type(exc)):
            await EmailNotifier(_make_email_cfg()).send([_sample_deal()])

    @pytest.mark.asyncio
    async def test_send_logs_diagnostics_on_failure(self, monkeypatch, caplog):
        import aiosmtplib

        async def fail_auth(msg, **kwargs):
            raise aiosmtplib.SMTPAuthenticationError(535, "Bad credentials")

        monkeypatch.setattr(aiosmtplib, "send", fail_auth)

        notifier = EmailNotifier(_make_email_cfg(smtp_user="user", smtp_password="wrong"))
        with pytest.raises(aiosmtplib.SMTPAuthenticationError), caplog.at_level("ERROR"):
            await notifier.send([_sample_deal()])

        assert "authentication failed" in caplog.text.lower()
        assert "smtp.test.com" in caplog.text


class TestNotificationDispatcher:
    def test_notifier_protocol_compliance(self):
        cfg = TelegramChannelConfig(enabled=True, bot_token="t", chat_id="c")
        notifier = TelegramNotifier(cfg)
        assert isinstance(notifier, Notifier)

    @staticmethod
    def _make_notifier(*, enabled: bool = True, send_side_effect=None) -> MagicMock:
        notifier = MagicMock()
        notifier.is_enabled.return_value = enabled
        notifier.send = AsyncMock(side_effect=send_side_effect)
        return notifier

    @pytest.mark.asyncio
    async def test_dispatch_calls_enabled_notifiers(self):
        config = AppConfig.model_validate({
            "notifications": {
                "channels": {
                    "telegram": {"enabled": True, "bot_token": "tok", "chat_id": "123"},
                },
            },
        })
        dispatcher = NotificationDispatcher(config)

        mock_notifier = self._make_notifier(enabled=True)
        dispatcher._notifiers = [mock_notifier]

        deals = [_sample_deal()]
        await dispatcher.dispatch(deals)

        mock_notifier.send.assert_awaited_once_with(deals)

    @pytest.mark.asyncio
    async def test_dispatch_skips_disabled_notifiers(self):
        config = AppConfig()
        dispatcher = NotificationDispatcher(config)

        mock_notifier = self._make_notifier(enabled=False)
        dispatcher._notifiers = [mock_notifier]

        await dispatcher.dispatch([_sample_deal()])
        mock_notifier.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_handles_notifier_error_gracefully(self):
        config = AppConfig()
        dispatcher = NotificationDispatcher(config)

        failing = self._make_notifier(enabled=True, send_side_effect=RuntimeError("boom"))
        succeeding = self._make_notifier(enabled=True)

        dispatcher._notifiers = [failing, succeeding]
        deals = [_sample_deal()]

        await dispatcher.dispatch(deals)
        succeeding.send.assert_awaited_once_with(deals)

    @pytest.mark.asyncio
    async def test_register_custom_notifier(self):
        config = AppConfig()
        dispatcher = NotificationDispatcher(config)

        custom = self._make_notifier(enabled=True)
        dispatcher.register(custom)

        deals = [_sample_deal()]
        await dispatcher.dispatch(deals)
        custom.send.assert_awaited_once_with(deals)

    @pytest.mark.asyncio
    async def test_preview_cli_includes_console_and_real_channels(self):
        config = AppConfig.model_validate({
            "notifications": {"preview_cli": True},
        })
        dispatcher = NotificationDispatcher(config)
        types = {type(n).__name__ for n in dispatcher._notifiers}
        assert "ConsoleNotifier" in types
        assert "TelegramNotifier" in types
        assert "EmailNotifier" in types

    @pytest.mark.asyncio
    async def test_preview_html_includes_html_report_and_real_channels(self):
        config = AppConfig.model_validate({
            "notifications": {"preview_html": True},
        })
        dispatcher = NotificationDispatcher(config)
        types = {type(n).__name__ for n in dispatcher._notifiers}
        assert "HtmlReportNotifier" in types
        assert "TelegramNotifier" in types
        assert "EmailNotifier" in types
        assert "ConsoleNotifier" not in types

    @pytest.mark.asyncio
    async def test_both_previews_and_real_channels(self):
        config = AppConfig.model_validate({
            "notifications": {"preview_cli": True, "preview_html": True},
        })
        dispatcher = NotificationDispatcher(config)

        types = {type(n).__name__ for n in dispatcher._notifiers}
        assert "ConsoleNotifier" in types
        assert "HtmlReportNotifier" in types
        assert "TelegramNotifier" in types
        assert "EmailNotifier" in types

    @pytest.mark.asyncio
    async def test_no_preview_only_real_channels(self):
        config = AppConfig()
        dispatcher = NotificationDispatcher(config)
        types = {type(n).__name__ for n in dispatcher._notifiers}
        assert "TelegramNotifier" in types
        assert "EmailNotifier" in types
        assert "ConsoleNotifier" not in types
        assert "HtmlReportNotifier" not in types


class TestConsoleNotifier:
    def test_is_enabled(self):
        assert ConsoleNotifier(enabled=True).is_enabled() is True

    def test_is_disabled(self):
        assert ConsoleNotifier(enabled=False).is_enabled() is False

    def test_protocol_compliance(self):
        assert isinstance(ConsoleNotifier(), Notifier)

    @pytest.mark.asyncio
    async def test_send_prints_deals(self, capsys):
        notifier = ConsoleNotifier(enabled=True)
        deals = [_sample_deal(), _sample_deal(name="Another Item")]
        await notifier.send(deals)

        output = capsys.readouterr().out
        assert "Test T-Shirt" in output
        assert "Another Item" in output
        assert "19.90" in output
        assert "2 deal(s)" in output

    @pytest.mark.asyncio
    async def test_send_empty_deals(self, capsys):
        notifier = ConsoleNotifier(enabled=True)
        await notifier.send([])

        output = capsys.readouterr().out
        assert "No deals" in output

    def test_format_deal_shows_color(self):
        deal = _sample_deal(color_names=["SCHWARZ", "SCHWARZ", "SCHWARZ"])
        output = _format_deal(deal, 1)
        assert "Color:" in output
        assert "SCHWARZ" in output

    def test_format_deal_hides_color_when_empty(self):
        deal = _sample_deal(color_names=["", "", ""])
        output = _format_deal(deal, 1)
        assert "Color:" not in output


class TestHtmlReport:
    _TS = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)

    def test_report_contains_deal_info(self):
        html = _build_report([_sample_deal()], self._TS)
        assert "Test T-Shirt" in html
        assert "19.90" in html
        assert "39.90" in html
        assert "-50%" in html
        assert "1 deal(s)" in html

    def test_report_contains_images(self):
        html = _build_report([_sample_deal()], self._TS)
        assert "image.uniqlo.com/test.jpg" in html
        assert "<img" in html

    def test_report_contains_size_links(self):
        html = _build_report([_sample_deal()], self._TS)
        assert "size-chip" in html
        assert ">S</a>" in html
        assert ">M</a>" in html
        assert ">L</a>" in html

    def test_report_watched_badge(self):
        html = _build_report([_sample_deal(is_watched=True)], self._TS)
        assert "WATCHED" in html

    def test_report_no_image_fallback(self):
        html = _build_report([_sample_deal(image_url=None)], self._TS)
        assert "No image" in html

    def test_report_uses_uniqlo_brand_colors(self):
        html = _build_report([_sample_deal()], self._TS)
        assert "#ED1D24" in html
        assert '<div class="logo">UNIQLO</div>' in html
        assert "<header>" in html

    def test_report_shows_color_label(self):
        deal = _sample_deal(color_names=["SCHWARZ", "SCHWARZ", "SCHWARZ"])
        html = _build_report([deal], self._TS)
        assert "color-label" in html
        assert "SCHWARZ" in html

    def test_report_hides_color_when_empty(self):
        deal = _sample_deal(color_names=["", "", ""])
        html = _build_report([deal], self._TS)
        assert '<div class="color-label">' not in html


class TestHtmlReportNotifier:
    def test_is_enabled(self):
        assert HtmlReportNotifier(enabled=True).is_enabled() is True

    def test_is_disabled(self):
        assert HtmlReportNotifier(enabled=False).is_enabled() is False

    def test_protocol_compliance(self):
        assert isinstance(HtmlReportNotifier(), Notifier)

    @pytest.mark.asyncio
    async def test_send_writes_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("webbrowser.open", lambda url: None)
        notifier = HtmlReportNotifier(enabled=True, output_dir=str(tmp_path))
        deals = [_sample_deal()]
        await notifier.send(deals)

        html_files = list(tmp_path.glob("uniqlo_deals_*.html"))
        assert len(html_files) == 1
        content = html_files[0].read_text(encoding="utf-8")
        assert "Test T-Shirt" in content

    @pytest.mark.asyncio
    async def test_send_empty_deals(self, capsys):
        notifier = HtmlReportNotifier(enabled=True)
        await notifier.send([])

        output = capsys.readouterr().out
        assert "No deals" in output


class TestUnknownDiscountDisplay:
    """Verify all formatters show 'Sale' instead of a percentage for unknown-discount items."""

    def test_console_shows_sale_label(self):
        deal = _sample_deal(**_UNKNOWN_DISCOUNT_OVERRIDES)
        output = _format_deal(deal, 1)
        assert "(Sale)" in output
        assert "%" not in output
        assert "->" not in output

    def test_console_known_discount_shows_percentage(self):
        deal = _sample_deal()
        output = _format_deal(deal, 1)
        assert "%" in output
        assert "->" in output

    def test_telegram_shows_sale_label(self):
        deal = _sample_deal(**_UNKNOWN_DISCOUNT_OVERRIDES)
        caption = _build_caption(deal)
        assert "Sale" in caption
        assert "~" not in caption

    def test_telegram_known_discount_shows_strikethrough(self):
        deal = _sample_deal()
        caption = _build_caption(deal)
        assert "~" in caption

    def test_email_shows_sale_label(self):
        deal = _sample_deal(**_UNKNOWN_DISCOUNT_OVERRIDES)
        html = _build_html([deal])
        assert "Sale" in html
        assert "line-through" not in html

    def test_email_known_discount_shows_strikethrough(self):
        deal = _sample_deal()
        html = _build_html([deal])
        assert "line-through" in html

    def test_html_report_shows_sale_label(self):
        ts = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
        deal = _sample_deal(**_UNKNOWN_DISCOUNT_OVERRIDES)
        html = _build_report([deal], ts)
        assert ">Sale</span>" in html
        assert 'class="price-old"' not in html

    def test_html_report_known_discount_shows_percentage(self):
        ts = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)
        deal = _sample_deal()
        html = _build_report([deal], ts)
        assert "price-old" in html
        assert "%" in html
