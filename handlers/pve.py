from __future__ import annotations

import asyncio

from aiogram import F, Router, types
from aiogram.filters import Command

import config
from handlers.helper_funcs import real_user_id
from services.economy import (
    BalanceLimitExceeded,
    InsufficientFunds,
    InvalidAmount,
)
from services.games import (
    ActiveGameExists,
    BlackjackResult,
    GameAlreadyFinished,
    GameExpired,
    GameNotFound,
    InvalidPick,
    NotParticipant,
    StaleGameAction,
    blackjack_hit,
    blackjack_stay,
    link_game_message,
    play_coinflip,
    play_roulette,
    start_blackjack,
)

router = Router()


def _parse_bet_arg(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    value = int(parts[1])
    if value < config.MIN_BET or value > config.MAX_BET:
        return None
    return value


def _blackjack_keyboard(result: BlackjackResult) -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="Ещё ➕",
                    callback_data=(
                        f"bj:h:{result.game_id}:{result.version}"
                    ),
                ),
                types.InlineKeyboardButton(
                    text="Стоп 🛑",
                    callback_data=(
                        f"bj:s:{result.game_id}:{result.version}"
                    ),
                ),
            ]
        ]
    )


def _active_blackjack_text(result: BlackjackResult) -> str:
    return (
        "🃏 <b>Блэкджек</b>\n\n"
        f"Ваши карты: {', '.join(result.player_hand)} "
        f"(счёт: {result.player_score})\n"
        f"Дилер: {result.dealer_hand[0]}, [?]"
    )


def _settled_blackjack_text(result: BlackjackResult) -> str:
    labels = {
        "blackjack": "🃏 <b>БЛЭКДЖЕК!</b>",
        "win": "🏆 <b>Вы выиграли!</b>",
        "loss": "📉 <b>Дилер выиграл.</b>",
        "push": "🤝 <b>Ничья!</b>",
        "bust": "💥 <b>Перебор!</b>",
    }
    label = labels.get(result.outcome or "", "🏁 <b>Игра завершена</b>")
    insurance = (
        "\n🛡 Страховка вернула половину ставки."
        if result.insurance_used
        else ""
    )
    sign = "+" if result.net > 0 else ""
    return (
        f"{label}\n\n"
        f"Ваши карты: {', '.join(result.player_hand)} "
        f"(счёт: {result.player_score})\n"
        f"Карты дилера: {', '.join(result.dealer_hand)} "
        f"(счёт: {result.dealer_score})\n\n"
        f"Итог: {sign}{result.net} 🥔{insurance}"
    )


async def _answer_game_error(callback: types.CallbackQuery, exc: Exception) -> None:
    if isinstance(exc, NotParticipant):
        text = "Это не ваша игра!"
    elif isinstance(exc, StaleGameAction):
        text = "Эта кнопка уже устарела."
    elif isinstance(exc, GameExpired):
        text = "Время игры истекло, ставка возвращена."
    else:
        text = "Игра уже завершена."
    await callback.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("bj:h:"))
async def bj_hit_handler(callback: types.CallbackQuery) -> None:
    try:
        _, _, game_id, raw_version = callback.data.split(":")
        result = await asyncio.to_thread(
            blackjack_hit,
            game_id,
            callback.message.chat.id,
            callback.from_user.id,
            message_id=callback.message.message_id,
            expected_version=int(raw_version),
        )
    except (
        GameAlreadyFinished,
        GameExpired,
        GameNotFound,
        NotParticipant,
        StaleGameAction,
        ValueError,
    ) as exc:
        await _answer_game_error(callback, exc)
        return

    if result.status == "settled":
        await callback.message.edit_text(
            _settled_blackjack_text(result),
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            _active_blackjack_text(result),
            reply_markup=_blackjack_keyboard(result),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("bj:s:"))
async def bj_stay_handler(callback: types.CallbackQuery) -> None:
    try:
        _, _, game_id, raw_version = callback.data.split(":")
        result = await asyncio.to_thread(
            blackjack_stay,
            game_id,
            callback.message.chat.id,
            callback.from_user.id,
            message_id=callback.message.message_id,
            expected_version=int(raw_version),
        )
    except (
        GameAlreadyFinished,
        GameExpired,
        GameNotFound,
        NotParticipant,
        StaleGameAction,
        ValueError,
    ) as exc:
        await _answer_game_error(callback, exc)
        return

    await callback.message.edit_text(
        _settled_blackjack_text(result),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(Command("flip"))
async def coinflip(message: types.Message) -> None:
    user_id = real_user_id(message)
    bet = _parse_bet_arg(message.text)
    if user_id is None:
        await message.answer("Играть могут только обычные пользователи.")
        return
    if bet is None:
        await message.answer(
            f"Ставка? Пример: /flip 10 "
            f"(от {config.MIN_BET} до {config.MAX_BET})"
        )
        return
    try:
        result = await asyncio.to_thread(
            play_coinflip,
            message.chat.id,
            user_id,
            bet,
            operation_key=f"flip:{message.chat.id}:{message.message_id}",
        )
    except InsufficientFunds:
        await message.answer("Поднакопи перед походом в казино 🤡")
        return
    except (InvalidAmount, BalanceLimitExceeded):
        await message.answer("Некорректная или слишком большая ставка.")
        return

    if result.won:
        text = f"🌕 Орёл! Итог: +{result.net} 🥔."
    elif result.insurance_used:
        text = f"🌑 Решка. Страховка сработала, итог: {result.net} 🥔."
    else:
        text = f"🌑 Решка. Итог: {result.net} 🥔."
    await message.answer(text)


@router.message(Command("roulette"))
async def roulette(message: types.Message) -> None:
    user_id = real_user_id(message)
    args = message.text.split() if message.text else []
    bet = _parse_bet_arg(message.text)
    if user_id is None:
        await message.answer("Играть могут только обычные пользователи.")
        return
    if bet is None or len(args) < 3:
        await message.answer(
            "Формат: /roulette [ставка] [исход]\n"
            "Исходы: red/black/green, even/odd, 1st/2nd/3rd, "
            "1-18/19-36 или число 0-36."
        )
        return
    pick = args[2].lower()
    try:
        result = await asyncio.to_thread(
            play_roulette,
            message.chat.id,
            user_id,
            bet,
            pick,
            operation_key=f"roulette:{message.chat.id}:{message.message_id}",
        )
    except InvalidPick:
        await message.answer("Такого исхода в рулетке нет.")
        return
    except InsufficientFunds:
        await message.answer("Поднакопи перед походом в казино 🤡")
        return
    except (InvalidAmount, BalanceLimitExceeded):
        await message.answer("Некорректная или слишком большая ставка.")
        return

    number, color = result.result.split(":")
    if result.won:
        verdict = f"Ставка зашла! Итог: +{result.net} 🥔."
    elif result.insurance_used:
        verdict = f"Страховка сработала. Итог: {result.net} 🥔."
    else:
        verdict = f"Проигрыш. Итог: {result.net} 🥔."
    await message.answer(
        f"🎰 Выпало <b>{number} ({color})</b>. {verdict}",
        parse_mode="HTML",
    )


@router.message(Command("bj"))
async def start_blackjack_handler(message: types.Message) -> None:
    user_id = real_user_id(message)
    bet = _parse_bet_arg(message.text)
    if user_id is None:
        await message.answer("Играть могут только обычные пользователи.")
        return
    if bet is None:
        await message.answer(
            f"Ставка? Пример: /bj 10 "
            f"(от {config.MIN_BET} до {config.MAX_BET})"
        )
        return

    try:
        result = await asyncio.to_thread(
            start_blackjack,
            message.chat.id,
            user_id,
            bet,
        )
    except InsufficientFunds:
        await message.answer("Поднакопи перед походом в казино 🤡")
        return
    except ActiveGameExists:
        await message.answer("Сначала закончи текущую игру в блэкджек.")
        return

    if result.status == "settled":
        await message.answer(
            _settled_blackjack_text(result),
            parse_mode="HTML",
        )
        return

    sent = await message.answer(
        _active_blackjack_text(result),
        reply_markup=_blackjack_keyboard(result),
        parse_mode="HTML",
    )
    await asyncio.to_thread(link_game_message, result.game_id, sent.message_id)
