from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import types

import config

MOSCOW_TIMEZONE = ZoneInfo("Europe/Moscow")


def get_moscow_today() -> str:
    return datetime.now(MOSCOW_TIMEZONE).strftime("%Y-%m-%d")


def get_user_info(message: types.Message) -> tuple[int, str]:
    if message.sender_chat:
        return message.sender_chat.id, message.sender_chat.title
    if message.from_user:
        return message.from_user.id, message.from_user.full_name
    raise ValueError("message has no identifiable sender")


def real_user_id(message: types.Message) -> int | None:
    if message.sender_chat or not message.from_user or message.from_user.is_bot:
        return None
    return message.from_user.id


def get_card_value(hand: list[str] | tuple[str, ...]) -> int:
    score = 0
    aces = 0
    for card in hand:
        if card in {"J", "Q", "K"}:
            score += 10
        elif card == "A":
            aces += 1
            score += 11
        else:
            score += int(card)

    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score


def parse_bet(text: str, balance: int) -> int:
    """Return a valid integer bet, or zero for malformed/unsafe input."""
    args = text.split()
    if len(args) < 2 or not args[1].isdigit():
        return 0
    bet = int(args[1])
    if (
        bet < config.MIN_BET
        or bet > config.MAX_BET
        or bet > balance
    ):
        return 0
    return bet
