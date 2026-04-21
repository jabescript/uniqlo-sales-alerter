"""Tests for the notification system."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from uniqlo_sales_alerter.config import AppConfig, EmailChannelConfig, TelegramChannelConfig
from uniqlo_sales_alerter.notifications.base import (
    Notifier,
    _derive_color_image,
    resolve_color_image,
)
from uniqlo_sales_alerter.notifications.console import ConsoleNotifier, _format_deal
from uniqlo_sales_alerter.notifications.dispatcher import NotificationDispatcher
from uniqlo_sales_alerter.notifications.email import EmailNotifier, _build_html, _expand_to_variants
from uniqlo_sales_alerter.notifications.html_report import HtmlReportNotifier, _build_report
from uniqlo_sales_alerter.notifications.telegram import TelegramNotifier, _build_caption, _escape_md

from .conftest import sample_deal as _sample_deal

_REPORT_TS = datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)

_UNKNOWN_DISCOUNT_OVERRIDES = dict(
    original_price=49.90,
    sale_price=49.90,
    discount_percentage=0,
    has_known_discount=False,
    currency_symbol="$",
)


def _render_console(deal):
    return _format_deal(deal, 1)


def _render_telegram(deal):
    return _build_caption(deal)


def _render_email(deal):
    return _build_html([deal])


def _render_report(deal):
    return _build_report([deal], _REPORT_TS)


_RENDERERS = {
    "console": _render_console,
    "telegram": _render_telegram,
    "email": _render_email,
    "html_report": _render_report,
}


class TestCrossChannelColorLabel:
    """Color label display must be consistent across all four notification channels."""

    def test_shows_color(self):
        deal = _sample_deal(color_names=["SCHWARZ", "SCHWARZ", "SCHWARZ"])
        for name, render in _RENDERERS.items():
            assert "SCHWARZ" in render(deal), f"{name} should show color name"

    def test_hides_color_when_empty(self):
        deal = _sample_deal(color_names=["", "", ""])
        absent = {"html_report": '<div class="color-label">'}
        for name, render in _RENDERERS.items():
            marker = absent.get(name, "Color:")
            assert marker not in render(deal), f"{name} should hide color label"


class TestCrossChannelWatchedBadge:
    """Watched badge must appear in all notification channels that render deals."""

    def test_watched_badge_shown(self):
        deal = _sample_deal(is_watched=True)
        for name in ("telegram", "email", "html_report"):
            output = _RENDERERS[name](deal)
            assert "watched" in output.lower(), f"{name} should show watched badge"


class TestCrossChannelUnknownDiscount:
    """All channels show 'Sale' for unknown-discount items, strikethrough/percentage for known."""

    _SALE_LABEL = {
        "console": {"present": ["(Sale)"], "absent": ["%", "->"]},
        "telegram": {"present": ["Sale"], "absent": ["~"]},
        "email": {"present": ["Sale"], "absent": ["line-through"]},
        "html_report": {"present": [">Sale</span>"], "absent": ['class="price-old"']},
    }
    _KNOWN_DISCOUNT = {
        "console": ["%", "->"],
        "telegram": ["~"],
        "email": ["line-through"],
        "html_report": ["price-old", "%"],
    }

    def test_unknown_discount_shows_sale_label(self):
        deal = _sample_deal(**_UNKNOWN_DISCOUNT_OVERRIDES)
        for name, render in _RENDERERS.items():
            output = render(deal)
            for s in self._SALE_LABEL[name]["present"]:
                assert s in output, f"{name} should show '{s}'"
            for s in self._SALE_LABEL[name]["absent"]:
                assert s not in output, f"{name} should not show '{s}'"

    def test_known_discount_shows_original_price(self):
        deal = _sample_deal()
        for name, render in _RENDERERS.items():
            output = render(deal)
            for s in self._KNOWN_DISCOUNT[name]:
                assert s in output, f"{name} should show '{s}'"


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

    def test_no_watched_badge(self):
        deal = _sample_deal(is_watched=False)
        caption = _build_caption(deal)
        assert "Watched" not in caption


class TestTelegramNotifier:
    @pytest.mark.parametrize("cfg_kwargs,expected", [
        (dict(enabled=True, bot_token="tok", chat_id="123"), True),
        (dict(enabled=True, bot_token="", chat_id="123"), False),
        (dict(enabled=False, bot_token="tok", chat_id="123"), False),
    ], ids=["enabled", "no_token", "flag_off"])
    def test_is_enabled(self, cfg_kwargs, expected):
        assert TelegramNotifier(TelegramChannelConfig(**cfg_kwargs)).is_enabled() is expected


_RESERVED_MD_V2 = frozenset(r"\_*[]()~`>#+-=|{}.!")


def _assert_no_double_escaped_reserved(text: str) -> None:
    """Reject MarkdownV2 where a reserved char follows ``\\\\`` (escaped backslash).

    The pattern ``\\X`` (two literal backslashes then reserved *X*) tells
    Telegram "literal backslash + unescaped X" — which it rejects.  This
    catches the class of bug where an f-string adds an extra ``\\`` before
    an already-escaped variable.
    """
    for i in range(len(text) - 2):
        if text[i] == "\\" and text[i + 1] == "\\" and text[i + 2] in _RESERVED_MD_V2:
            ctx = text[max(0, i - 10) : i + 10]
            raise AssertionError(
                f"Double-escaped '{text[i + 2]}' at position {i}: …{ctx}…"
            )


class TestEscapeMd:
    """Validate the MarkdownV2 escape helper."""

    _CASES = [
        ("hello", "hello"),
        ("-50%", "\\-50%"),
        ("(test)", "\\(test\\)"),
        ("a.b", "a\\.b"),
        ("a_b", "a\\_b"),
        ("a*b~c", "a\\*b\\~c"),
    ]

    @pytest.mark.parametrize("raw,expected", _CASES, ids=[c[0] for c in _CASES])
    def test_escapes_reserved_chars(self, raw, expected):
        assert _escape_md(raw) == expected

    def test_no_double_escape_on_clean_input(self):
        """Escaping a string without backslashes should never produce ``\\\\``."""
        result = _escape_md("Price: -50% (sale)")
        assert "\\\\" not in result


class TestTelegramCaptionMarkdownV2:
    """Validate that _build_caption produces well-formed MarkdownV2."""

    def test_strikethrough_discount_no_double_escape(self):
        """Known-discount captions must not double-escape the percentage."""
        deal = _sample_deal()
        caption = _build_caption(deal)
        _assert_no_double_escaped_reserved(caption)

    def test_unknown_discount_no_double_escape(self):
        deal = _sample_deal(**_UNKNOWN_DISCOUNT_OVERRIDES)
        caption = _build_caption(deal)
        _assert_no_double_escaped_reserved(caption)

    def test_plain_price_no_double_escape(self):
        deal = _sample_deal(has_known_discount=True, discount_percentage=0)
        caption = _build_caption(deal)
        _assert_no_double_escaped_reserved(caption)

    def test_special_chars_in_name_escaped(self):
        deal = _sample_deal(name="T-Shirt (100% Cotton)")
        caption = _build_caption(deal)
        assert "T\\-Shirt" in caption
        assert "\\(100% Cotton\\)" in caption

    def test_server_url_in_footer(self):
        deal = _sample_deal()
        caption = _build_caption(deal, server_url="http://192.168.1.50:8000")
        assert "[Settings](" in caption
        assert "192.168.1.50" in caption

    def test_no_settings_link_without_server_url(self):
        deal = _sample_deal()
        caption = _build_caption(deal, server_url="")
        assert "Settings" not in caption


class TestTelegramNotifierSend:
    """Test TelegramNotifier.send with mocked telegram.Bot."""

    @staticmethod
    def _make_config(**overrides) -> TelegramChannelConfig:
        defaults = dict(enabled=True, bot_token="test-token", chat_id="12345")
        defaults.update(overrides)
        return TelegramChannelConfig(**defaults)

    @staticmethod
    def _mock_bot(monkeypatch) -> MagicMock:
        """Patch telegram.Bot and return the mock instance."""
        import telegram

        mock_instance = MagicMock()
        mock_instance.send_photo = AsyncMock()
        mock_instance.send_message = AsyncMock()
        monkeypatch.setattr(telegram, "Bot", MagicMock(return_value=mock_instance))
        return mock_instance

    @pytest.mark.asyncio
    async def test_send_photo_for_deal_with_image(self, monkeypatch):
        bot = self._mock_bot(monkeypatch)
        notifier = TelegramNotifier(self._make_config())

        await notifier.send([_sample_deal()])

        bot.send_photo.assert_awaited_once()
        kwargs = bot.send_photo.call_args.kwargs
        assert kwargs["chat_id"] == "12345"
        assert kwargs["parse_mode"] == "MarkdownV2"
        assert kwargs["photo"]

    @pytest.mark.asyncio
    async def test_send_message_when_no_image(self, monkeypatch):
        bot = self._mock_bot(monkeypatch)
        notifier = TelegramNotifier(self._make_config())

        await notifier.send([_sample_deal(image_url=None)])

        bot.send_message.assert_awaited_once()
        bot.send_photo.assert_not_awaited()
        assert bot.send_message.call_args.kwargs["parse_mode"] == "MarkdownV2"

    @pytest.mark.asyncio
    async def test_send_skips_empty_deals(self, monkeypatch):
        bot = self._mock_bot(monkeypatch)
        notifier = TelegramNotifier(self._make_config())

        await notifier.send([])

        bot.send_photo.assert_not_awaited()
        bot.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_multiple_deals_sends_per_deal(self, monkeypatch):
        bot = self._mock_bot(monkeypatch)
        notifier = TelegramNotifier(self._make_config())

        await notifier.send([_sample_deal(), _sample_deal(name="Second")])

        assert bot.send_photo.await_count == 2

    @pytest.mark.asyncio
    async def test_send_continues_after_telegram_error(self, monkeypatch):
        """A failing deal must not prevent subsequent deals from sending."""
        bot = self._mock_bot(monkeypatch)
        from telegram.error import TelegramError

        bot.send_photo.side_effect = [TelegramError("fail"), None]

        notifier = TelegramNotifier(self._make_config())
        await notifier.send([_sample_deal(name="Fail"), _sample_deal(name="OK")])

        assert bot.send_photo.await_count == 2

    @pytest.mark.asyncio
    async def test_send_includes_action_buttons_with_server_url(self, monkeypatch):
        bot = self._mock_bot(monkeypatch)
        notifier = TelegramNotifier(
            self._make_config(), server_url="http://localhost:8000",
        )

        await notifier.send([_sample_deal()])

        markup = bot.send_photo.call_args.kwargs["reply_markup"]
        assert markup is not None
        buttons = [btn for row in markup.inline_keyboard for btn in row]
        labels = [btn.text for btn in buttons]
        assert "Ignore" in labels

    @pytest.mark.asyncio
    async def test_watched_deal_has_unwatch_button(self, monkeypatch):
        bot = self._mock_bot(monkeypatch)
        notifier = TelegramNotifier(
            self._make_config(), server_url="http://localhost:8000",
        )

        await notifier.send([_sample_deal(is_watched=True)])

        markup = bot.send_photo.call_args.kwargs["reply_markup"]
        buttons = [btn for row in markup.inline_keyboard for btn in row]
        labels = [btn.text for btn in buttons]
        assert "Unwatch" in labels
        assert not any(label.startswith("Watch ") for label in labels)

    @pytest.mark.asyncio
    async def test_no_buttons_without_server_url(self, monkeypatch):
        bot = self._mock_bot(monkeypatch)
        notifier = TelegramNotifier(self._make_config(), server_url="")

        await notifier.send([_sample_deal()])

        assert bot.send_photo.call_args.kwargs["reply_markup"] is None


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

    def test_html_expands_to_per_variant_rows(self):
        deal = _sample_deal()
        html = _build_html([deal])
        assert html.count("<tr") == 3

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
    @pytest.mark.parametrize("overrides,expected", [
        ({}, True),
        (dict(to_addresses=[]), False),
        (dict(from_address=""), False),
        (dict(enabled=False), False),
    ], ids=["enabled", "no_recipients", "no_from", "flag_off"])
    def test_is_enabled(self, overrides, expected):
        assert EmailNotifier(_make_email_cfg(**overrides)).is_enabled() is expected

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
    async def test_preview_mode_notifiers(self):
        cases = [
            ({"preview_cli": True},
             {"ConsoleNotifier", "TelegramNotifier", "EmailNotifier"}, set()),
            ({"preview_html": True},
             {"HtmlReportNotifier", "TelegramNotifier", "EmailNotifier"},
             {"ConsoleNotifier"}),
            ({"preview_cli": True, "preview_html": True},
             {"ConsoleNotifier", "HtmlReportNotifier",
              "TelegramNotifier", "EmailNotifier"}, set()),
            ({},
             {"TelegramNotifier", "EmailNotifier"},
             {"ConsoleNotifier", "HtmlReportNotifier"}),
        ]
        for cfg_overrides, expected_present, expected_absent in cases:
            config = AppConfig.model_validate(
                {"notifications": cfg_overrides},
            )
            dispatcher = NotificationDispatcher(config)
            types = {type(n).__name__ for n in dispatcher._notifiers}
            label = str(cfg_overrides)
            for name in expected_present:
                assert name in types, f"{name} should be present ({label})"
            for name in expected_absent:
                assert name not in types, f"{name} should be absent ({label})"


class TestConsoleNotifier:
    @pytest.mark.parametrize("enabled,expected", [(True, True), (False, False)])
    def test_is_enabled(self, enabled, expected):
        assert ConsoleNotifier(enabled=enabled).is_enabled() is expected

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


class TestHtmlReport:
    def test_report_contains_deal_info(self):
        html = _build_report([_sample_deal()], _REPORT_TS)
        assert "Test T-Shirt" in html
        assert "19.90" in html
        assert "39.90" in html
        assert "-50%" in html
        assert "1 deal(s)" in html

    def test_report_contains_images(self):
        html = _build_report([_sample_deal()], _REPORT_TS)
        assert "image.uniqlo.com/test.jpg" in html
        assert "<img" in html

    def test_report_contains_size_links(self):
        html = _build_report([_sample_deal()], _REPORT_TS)
        assert "size-chip" in html
        assert ">S</a>" in html
        assert ">M</a>" in html
        assert ">L</a>" in html

    def test_report_no_image_fallback(self):
        html = _build_report([_sample_deal(image_url=None)], _REPORT_TS)
        assert "No image" in html

    def test_report_uses_uniqlo_brand_colors(self):
        html = _build_report([_sample_deal()], _REPORT_TS)
        assert "#ED1D24" in html
        assert '<div class="logo">UNIQLO</div>' in html
        assert "<header>" in html


class TestHtmlReportNotifier:
    @pytest.mark.parametrize("enabled,expected", [(True, True), (False, False)])
    def test_is_enabled(self, enabled, expected):
        assert HtmlReportNotifier(enabled=enabled).is_enabled() is expected

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


class TestResolveColorImage:
    """Verify colour-aware image resolution, including CDN URL derivation."""

    _CDN_09 = "https://image.uniqlo.com/UQ/ST3/eu/imagesgoods/485476/item/eugoods_09_485476_3x4.jpg"
    _CDN_01 = "https://image.uniqlo.com/UQ/ST3/eu/imagesgoods/485476/item/eugoods_01_485476_3x4.jpg"

    def test_exact_match_in_map(self):
        url = "https://www.uniqlo.com/de/de/products/E485476-000/00?colorDisplayCode=09"
        result = resolve_color_image(url, {"09": self._CDN_09}, None)
        assert result == self._CDN_09

    def test_derives_image_when_color_missing_from_map(self):
        url = "https://www.uniqlo.com/de/de/products/E485476-000/00?colorDisplayCode=01"
        result = resolve_color_image(url, {"09": self._CDN_09}, None)
        assert result == self._CDN_01

    def test_falls_back_when_url_has_no_color_param(self):
        url = "https://www.uniqlo.com/de/de/products/E485476-000/00"
        fallback = self._CDN_09
        assert resolve_color_image(url, {"09": self._CDN_09}, fallback) == fallback

    def test_falls_back_when_color_images_empty(self):
        url = "https://www.uniqlo.com/de/de/products/E485476-000/00?colorDisplayCode=01"
        fallback = self._CDN_09
        assert resolve_color_image(url, {}, fallback) == fallback

    def test_falls_back_when_cdn_pattern_unrecognised(self):
        url = "https://www.uniqlo.com/de/de/products/E485476-000/00?colorDisplayCode=01"
        non_cdn = "https://example.com/image.jpg"
        assert resolve_color_image(url, {"09": non_cdn}, "fallback.jpg") == "fallback.jpg"

    def test_derive_color_image_substitutes_code(self):
        assert _derive_color_image(self._CDN_09, "01") == self._CDN_01

    def test_derive_color_image_returns_none_for_non_cdn(self):
        assert _derive_color_image("https://example.com/image.jpg", "01") is None

    def test_email_variant_uses_derived_image(self):
        deal = _sample_deal(
            available_sizes=["M"],
            product_urls=[
                "https://www.uniqlo.com/de/de/products/E485476-000/00"
                "?colorDisplayCode=01&sizeDisplayCode=003",
            ],
            color_names=["OFF WHITE"],
            color_images={"09": self._CDN_09},
            image_url=self._CDN_09,
        )
        variants = _expand_to_variants(deal)
        assert len(variants) == 1
        assert variants[0].image_url == self._CDN_01

    def test_email_multi_variant_derives_per_color(self):
        deal = _sample_deal(
            available_sizes=["M", "L"],
            product_urls=[
                "https://www.uniqlo.com/de/de/products/E485476-000/00"
                "?colorDisplayCode=01&sizeDisplayCode=003",
                "https://www.uniqlo.com/de/de/products/E485476-000/00"
                "?colorDisplayCode=69&sizeDisplayCode=004",
            ],
            color_names=["OFF WHITE", "NAVY"],
            color_images={"09": self._CDN_09},
            image_url=self._CDN_09,
        )
        variants = _expand_to_variants(deal)
        assert len(variants) == 2
        assert "_01_" in variants[0].image_url
        assert "_69_" in variants[1].image_url
