"""Telegram Bot API transport and order notification formatting.

The bot token is read only from Django settings. This module never exposes it
to templates or logs and contains no order state-transition business rules.
"""
from __future__ import annotations

import html
import json
import logging
import threading
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from .models import Order

logger = logging.getLogger(__name__)
_API_TIMEOUT = 10


class TelegramApiError(RuntimeError):
    """The Telegram Bot API rejected or could not complete a request."""


def _chat_id() -> int:
    try:
        return int(settings.TELEGRAM_GROUP_CHAT_ID)
    except (TypeError, ValueError) as exc:
        raise TelegramApiError("TELEGRAM_GROUP_CHAT_ID is not configured") from exc


def _api_call(method: str, payload: dict) -> dict:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise TelegramApiError("TELEGRAM_BOT_TOKEN is not configured")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_API_TIMEOUT) as response:
            result = json.loads(response.read())
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise TelegramApiError(f"Telegram request failed: {method}") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise TelegramApiError(f"Telegram rejected request: {method}")
    return result


def _mention(user_id: int) -> str:
    return f'<a href="tg://user?id={user_id}">staff member</a>'


def format_order_message(order: Order) -> str:
    lines = [
        f"<b>🛒 ՆՈՐ ՕՆԼԱՅՆ ՊԱՏՎԵՐ #{html.escape(str(order.id))}</b>",
        f"Հաճախորդ՝ {html.escape(order.customer_name)}",
        f"Հեռախոս՝ {html.escape(order.phone)}",
        f"Հասցե՝ {html.escape(order.address)}",
        "",
        "<b>Ապրանքներ՝</b>",
    ]
    for item in order.items.all():
        lines.append(
            f"• {html.escape(item.product_name)} - {item.quantity} հատ - "
            f"{html.escape(str(item.unit_price))} դրամ"
        )
    lines.extend(
        [
            "",
            f"<b>Ընդհանուր՝ {html.escape(str(order.total_amount))} դրամ</b>",
            f"Ստեղծվել է՝ {timezone.localtime(order.created_at):%d.%m.%Y %H:%M}",
            "",
            "Խնդրում ենք հաստատել կամ մերժել պատվերը Admin PC-ում։",
        ]
    )
    return "\n".join(lines)


def send_order_notification(order_id) -> None:
    if not settings.TELEGRAM_ENABLED:
        return None
    order = Order.objects.prefetch_related("items").get(pk=order_id)
    chat_id = _chat_id()
    result = _api_call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": format_order_message(order),
            "parse_mode": "HTML",
        },
    )
    message = result.get("result")
    if not isinstance(message, dict) or not isinstance(message.get("message_id"), int):
        raise TelegramApiError("Telegram response did not contain a message id")


def schedule_order_notification(order_id) -> None:
    if not settings.TELEGRAM_ENABLED:
        return

    def send() -> None:
        for attempt in range(3):
            try:
                send_order_notification(order_id)
                return
            except Exception:
                logger.exception(
                    "telegram op=send_order_notification outcome=failed attempt=%s",
                    attempt + 1,
                )
                if attempt < 2:
                    threading.Event().wait(2**attempt)

    threading.Thread(
        target=send, name="telegram-order-notification", daemon=True
    ).start()
