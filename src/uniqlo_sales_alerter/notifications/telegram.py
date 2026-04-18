"""Telegram notification channel using the Bot API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from uniqlo_sales_alerter.models.products import SaleItem
from uniqlo_sales_alerter.notifications.base import PROJECT_URL, DealActions

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import TelegramChannelConfig

logger = logging.getLogger(__name__)


def _escape_md(text: str) -> str:
    """Escape characters reserved by Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _build_caption(deal: SaleItem) -> str:
    name = _escape_md(deal.name)
    sym = _escape_md(deal.currency_symbol)
    sale = _escape_md(f"{deal.sale_price:.2f}")

    if deal.has_known_discount:
        original = _escape_md(f"{deal.original_price:.2f}")
        pct = _escape_md(f"{deal.discount_percentage:.0f}%")
        price_line = f"~{sym}{original}~ ➜ {sym}{sale} \\(\\-{pct}\\)"
    else:
        price_line = f"{sym}{sale} ✦ Sale"

    unique_colors = list(dict.fromkeys(cn for cn in deal.color_names if cn))
    color_line = (
        f"Color: {_escape_md(' · '.join(unique_colors))}"
        if unique_colors else ""
    )

    size_links = " \\| ".join(
        f"[{_escape_md(sz)}]({url})"
        for sz, url in zip(deal.available_sizes, deal.product_urls)
    )

    lines = [
        f"*{name}*",
        price_line,
        size_links or _escape_md(", ".join(deal.available_sizes)),
        f"\n[Uniqlo Sales Alerter]({PROJECT_URL})",
    ]
    if color_line:
        lines.insert(1, color_line)
    if deal.is_watched:
        lines.insert(0, "⭐ *Watched item*")
    return "\n".join(lines)


class TelegramNotifier:
    """Sends deal notifications via Telegram Bot API."""

    def __init__(self, config: TelegramChannelConfig, *, server_url: str = "") -> None:
        self._config = config
        self._server_url = server_url

    def is_enabled(self) -> bool:
        return self._config.enabled and bool(self._config.bot_token) and bool(self._config.chat_id)

    async def send(self, deals: list[SaleItem]) -> None:
        if not deals:
            return

        try:
            from telegram import Bot
        except ImportError:
            logger.error("python-telegram-bot is not installed; skipping Telegram notifications")
            return

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        bot = Bot(token=self._config.bot_token)
        chat_id = self._config.chat_id

        for deal in deals:
            caption = _build_caption(deal)
            actions = DealActions(deal, self._server_url)
            markup = None
            if actions.ignore_url:
                if actions.unwatch_url:
                    rows = [[InlineKeyboardButton(
                        "Unwatch", url=actions.unwatch_url,
                    )]]
                else:
                    rows = [
                        [InlineKeyboardButton(
                            f"Watch {sz}", url=wurl,
                        )]
                        for sz, wurl in actions.watch_urls
                    ]
                rows.append([InlineKeyboardButton(
                    "Ignore", url=actions.ignore_url,
                )])
                markup = InlineKeyboardMarkup(rows)
            try:
                if deal.image_url:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=deal.image_url,
                        caption=caption,
                        parse_mode="MarkdownV2",
                        reply_markup=markup,
                    )
                else:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=caption,
                        parse_mode="MarkdownV2",
                        reply_markup=markup,
                    )
            except Exception:
                logger.exception("Failed to send Telegram message for %s", deal.product_id)
