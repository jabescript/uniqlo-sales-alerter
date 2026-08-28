"""Telegram notification channel using the Bot API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from uniqlo_sales_alerter.models.products import SaleItem
from uniqlo_sales_alerter.notifications.base import (
    DealActions,
    format_price,
    format_stock_suffix,
    resolve_color_image,
    variant_change_text,
)

if TYPE_CHECKING:
    from uniqlo_sales_alerter.config import TelegramChannelConfig

logger = logging.getLogger(__name__)


def _escape_md(text: str) -> str:
    """Escape characters reserved by Telegram MarkdownV2."""
    for char in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(char, f"\\{char}")
    return text


def _size_link(
    size_label: str, url: str, qty: int, status: str, threshold: int,
    change_tag: str = "",
    color_name: str = "",
) -> str:
    """Render a single size as a MarkdownV2 link with optional color and stock suffix."""
    stock_text, is_low = format_stock_suffix(qty, status, threshold)
    parts = []
    if color_name:
        parts.append(color_name)
    parts.append(size_label)
    if stock_text:
        parts.append(stock_text + (" ⚠" if is_low else ""))
    if change_tag:
        parts.append(change_tag)
    label = _escape_md(" · ".join(parts))
    return f"[{label}]({url})"


def _build_caption(
    deal: SaleItem,
    server_url: str = "",
    low_stock_threshold: int = 0,
    ignored_keywords: list[str] | None = None,
) -> str:
    """Build a MarkdownV2 caption for a single deal."""
    name = _escape_md(deal.name)
    price = format_price(deal)

    if price.show_strikethrough:
        original_md = _escape_md(price.original_text)
        sale_price_md = _escape_md(price.sale_text)
        discount_md = _escape_md(price.discount_label)
        price_line = f"~{original_md}~ ➜ {sale_price_md} \\({discount_md}\\)"
    elif price.show_sale_badge:
        price_line = f"{_escape_md(price.sale_text)} ✦ {_escape_md(price.discount_label)}"
    else:
        price_line = _escape_md(price.sale_text)

    size_links = " \\| ".join(
        _size_link(
            size_label, url,
            deal.variant_at(i).quantity,
            deal.variant_at(i).status,
            low_stock_threshold,
            variant_change_text(deal, i),
            color_name=deal.variant_at(i).color_name,
        )
        for i, (size_label, url) in enumerate(
            zip(deal.available_sizes, deal.product_urls),
        )
    )

    footer_parts = []
    if server_url:
        footer_parts.append(f"[Settings]({server_url}/settings)")
    if ignored_keywords:
        keywords_text = _escape_md(", ".join(ignored_keywords))
        footer_parts.append(f"Ignored keywords: {keywords_text}")
    footer = "\n".join(footer_parts)

    lines = [
        f"*{name}*",
        price_line,
        size_links or _escape_md(", ".join(deal.available_sizes)),
    ]
    if footer:
        lines.append(f"\n{footer}")
    if deal.is_watched:
        lines.insert(0, "⭐ *Watched item*")
    return "\n".join(lines)


class TelegramNotifier:
    """Sends deal notifications via Telegram Bot API."""

    def __init__(
        self,
        config: TelegramChannelConfig,
        *,
        server_url: str = "",
        low_stock_threshold: int = 0,
        ignored_keywords: list[str] | None = None,
    ) -> None:
        self._config = config
        self._server_url = server_url
        self._low_stock_threshold = low_stock_threshold
        self._ignored_keywords = ignored_keywords or []

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
            caption = _build_caption(
                deal,
                server_url=self._server_url,
                low_stock_threshold=self._low_stock_threshold,
                ignored_keywords=self._ignored_keywords,
            )
            actions = DealActions(deal, self._server_url)
            markup = None
            if actions.ignore_url:
                if actions.unwatch_urls:
                    rows = [
                        [InlineKeyboardButton(
                            f"Unwatch {size_label}", url=url,
                        )]
                        for size_label, url in actions.unwatch_urls
                    ]
                else:
                    rows = [
                        [InlineKeyboardButton(
                            f"Watch {size_label}", url=watch_url,
                        )]
                        for size_label, watch_url in actions.watch_urls
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
            except TelegramError as exc:
                if markup:
                    logger.warning(
                        "Failed to send Telegram message with action buttons for %s (%s); "
                        "retrying without buttons.",
                        deal.product_id,
                        exc,
                    )
                    try:
                        if photo_url:
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=photo_url,
                                caption=caption,
                                parse_mode="MarkdownV2",
                            )
                        else:
                            await bot.send_message(
                                chat_id=chat_id,
                                text=caption,
                                parse_mode="MarkdownV2",
                            )
                        continue
                    except TelegramError:
                        pass
                logger.exception("Failed to send Telegram message for %s", deal.product_id)
