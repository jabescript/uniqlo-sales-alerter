"""Telegram notification channel using the Bot API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from uniqlo_sales_alerter.models.products import SaleItem
from uniqlo_sales_alerter.notifications.base import (
    PROJECT_URL,
    DealActions,
    format_price,
    resolve_color_image,
    unique_colors,
)

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import TelegramChannelConfig

logger = logging.getLogger(__name__)


def _escape_md(text: str) -> str:
    """Escape characters reserved by Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _build_caption(deal: SaleItem, server_url: str = "") -> str:
    """Build a MarkdownV2 caption for a single deal."""
    name = _escape_md(deal.name)
    fp = format_price(deal)

    if fp.show_strikethrough:
        orig_md = _escape_md(fp.original_text)
        sale_md = _escape_md(fp.sale_text)
        pct_md = _escape_md(fp.discount_label)
        price_line = f"~{orig_md}~ ➜ {sale_md} \\(\\{pct_md}\\)"
    elif fp.show_sale_badge:
        price_line = f"{_escape_md(fp.sale_text)} ✦ {_escape_md(fp.discount_label)}"
    else:
        price_line = _escape_md(fp.sale_text)

    colors = unique_colors(deal)
    color_line = (
        f"Color: {_escape_md(' · '.join(colors))}"
        if colors else ""
    )

    size_links = " \\| ".join(
        f"[{_escape_md(sz)}]({url})"
        for sz, url in zip(deal.available_sizes, deal.product_urls)
    )

    footer = f"[Uniqlo Sales Alerter]({PROJECT_URL})"
    if server_url:
        footer += f" · [Settings]({server_url}/settings)"

    lines = [
        f"*{name}*",
        price_line,
        size_links or _escape_md(", ".join(deal.available_sizes)),
        f"\n{footer}",
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
        from telegram.error import TelegramError
        bot = Bot(token=self._config.bot_token)
        chat_id = self._config.chat_id

        for deal in deals:
            caption = _build_caption(deal, server_url=self._server_url)
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
            photo_url = resolve_color_image(
                deal.product_urls[0] if deal.product_urls else "",
                deal.color_images,
                deal.image_url,
            )

            try:
                if photo_url:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_url,
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
            except TelegramError:
                logger.exception("Failed to send Telegram message for %s", deal.product_id)
