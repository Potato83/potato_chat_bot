from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from aiogram import F, Router, html, types
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import ChatPermissions

from handlers.helper_funcs import real_user_id
from services.economy import (
    SHOP_CATALOG,
    InsufficientFunds,
    InvalidAmount,
    ItemUnavailable,
    charge_sleep,
    get_sleep_duration,
    purchase,
    refund_sleep,
    remove_title,
    set_title,
)
from services.loans import (
    LOAN_COOLDOWN_SECONDS,
    LOAN_DUE_AMOUNT,
    LOAN_PRINCIPAL,
    LOAN_TERM_SECONDS,
    issue_loan,
)

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("buy:"))
async def buy_item(callback: types.CallbackQuery) -> None:
    product_id = callback.data.split(":", 1)[1]
    try:
        title, price, balance = await asyncio.to_thread(
            purchase,
            callback.message.chat.id,
            callback.from_user.id,
            product_id,
            operation_key=f"shop:{callback.id}",
        )
    except ItemUnavailable:
        await callback.answer("Такого товара нет.", show_alert=True)
        return
    except InsufficientFunds:
        await callback.answer("У тебя мало картошки! 🥔", show_alert=True)
        return
    await callback.answer(
        f"Куплено: {title} за {price} 🥔. Баланс: {balance} 🥔",
        show_alert=True,
    )


@router.message(Command("shop"))
async def open_shop(message: types.Message) -> None:
    rows = []
    for product_id, (title, price) in SHOP_CATALOG.items():
        rows.append(
            [
                types.InlineKeyboardButton(
                    text=f"{title} ({price} 🥔)",
                    callback_data=f"buy:{product_id}",
                )
            ]
        )
    await message.answer(
        "🛒 <b>Картофельная лавка</b>\n"
        "Цена товара всегда проверяется на сервере:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


@router.message(Command("sleep"))
async def sleep_user(message: types.Message) -> None:
    attacker_id = real_user_id(message)
    if attacker_id is None:
        await message.answer("Команда доступна только обычным пользователям.")
        return
    if not message.reply_to_message:
        await message.answer("Ответь на сообщение цели!")
        return
    target_id = real_user_id(message.reply_to_message)
    if target_id is None:
        await message.answer("Эту цель нельзя отправить спать.")
        return
    if target_id == attacker_id:
        await message.answer("Себя отправить спать нельзя.")
        return

    chat_id = message.chat.id
    operation_key = f"sleep:{chat_id}:{message.message_id}"
    try:
        charge = await asyncio.to_thread(
            charge_sleep,
            chat_id,
            attacker_id,
            target_id,
            operation_key=operation_key,
        )
    except InsufficientFunds as exc:
        await message.answer(
            f"Мало картошки: доступно {exc.balance}, нужно {exc.required} 🥔."
        )
        return

    target_name = html.quote(message.reply_to_message.from_user.full_name)
    if charge.shield_used:
        await message.answer(
            f"🛡 {target_name} отразил атаку щитом! "
            f"За попытку списано {charge.price} 🥔.",
            parse_mode="HTML",
        )
        return

    duration = await asyncio.to_thread(get_sleep_duration, chat_id)
    restriction_applied = False
    try:
        member = await message.bot.get_chat_member(chat_id, target_id)
        now = datetime.now(timezone.utc)
        current_until = getattr(member, "until_date", None)
        if current_until and current_until > now:
            until_date = current_until + timedelta(minutes=duration)
            text = (
                f"💤 Сон продлён: {target_name} спит ещё {duration} мин. "
                f"Цена: {charge.price} 🥔."
            )
        else:
            until_date = now + timedelta(minutes=duration)
            text = (
                f"💤 {target_name} уснул на {duration} мин. "
                f"Цена: {charge.price} 🥔."
            )
        await message.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date,
        )
        restriction_applied = True
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.warning(
            "Sleep moderation failed",
            extra={
                "chat_id": chat_id,
                "attacker_id": attacker_id,
                "target_id": target_id,
            },
            exc_info=True,
        )
        await asyncio.to_thread(refund_sleep, chat_id, attacker_id, charge)
        await message.answer(
            "Не получилось ограничить пользователя. Оплата возвращена."
        )
        return
    except Exception:
        logger.exception(
            "Unexpected sleep command failure",
            extra={
                "chat_id": chat_id,
                "attacker_id": attacker_id,
                "target_id": target_id,
            },
        )
        if not restriction_applied:
            await asyncio.to_thread(refund_sleep, chat_id, attacker_id, charge)
        await message.answer(
            "Произошла внутренняя ошибка. "
            + ("Ограничение уже применено." if restriction_applied else "Оплата возвращена.")
        )
        return
    await message.answer(text, parse_mode="HTML")


@router.message(Command("settitle"))
async def set_user_title(message: types.Message) -> None:
    user_id = real_user_id(message)
    if user_id is None:
        await message.answer("Титулы доступны только обычным пользователям.")
        return
    args = message.text.split(maxsplit=1) if message.text else []
    if len(args) < 2:
        await message.answer("Использование: /settitle Король (до 15 символов)")
        return
    new_title = args[1].strip()
    try:
        await asyncio.to_thread(
            set_title,
            message.chat.id,
            user_id,
            new_title,
            operation_key=f"title:{message.chat.id}:{message.message_id}",
        )
    except InvalidAmount:
        await message.answer(
            "Титул должен содержать от 1 до 15 символов и быть в одну строку."
        )
        return
    except ItemUnavailable:
        await message.answer(
            "❌ У тебя нет лицензии на титул. Купи её в /shop."
        )
        return
    await message.answer(
        f"✅ Новый титул установлен: <b>{html.quote(new_title)}</b>",
        parse_mode="HTML",
    )


@router.message(Command("removetitle"))
async def remove_user_title(message: types.Message) -> None:
    user_id = real_user_id(message)
    if user_id is None:
        await message.answer("Титулы доступны только обычным пользователям.")
        return
    await asyncio.to_thread(remove_title, message.chat.id, user_id)
    await message.answer("Титул удалён. Теперь ты обычный фермер.")


@router.message(Command("zaim"))
async def take_loan(message: types.Message) -> None:
    user_id = real_user_id(message)
    if user_id is None:
        await message.answer("Займ доступен только обычным пользователям.")
        return
    decision = await asyncio.to_thread(
        issue_loan,
        message.chat.id,
        user_id,
    )
    current_time = int(time.time())

    if decision.status == "active":
        await message.answer(
            "🏦 У тебя уже есть активный займ. Списание через "
            f"{decision.remaining_minutes(current_time)} мин."
        )
        return
    if decision.status == "cooldown":
        await message.answer(
            "🏦 Таймер на займ ещё не закончился. Приходи через "
            f"{decision.remaining_minutes(current_time)} мин."
        )
        return
    if decision.status == "debt":
        await message.answer(
            f"🏦 Сначала погаси долг: баланс {decision.balance} 🥔."
        )
        return

    await message.answer(
        f"🏦 {html.quote(message.from_user.full_name)}, ты занял "
        f"{LOAN_PRINCIPAL} 🥔.\n"
        f"Через {LOAN_TERM_SECONDS // 60} минут автоматически спишется "
        f"{LOAN_DUE_AMOUNT} 🥔 (+10%). Если картошки не хватит, баланс "
        f"уйдёт в минус.\nНовый займ — не раньше чем через "
        f"{LOAN_COOLDOWN_SECONDS // 60} минут после срока возврата.",
        parse_mode="HTML",
    )
