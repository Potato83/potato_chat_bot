from __future__ import annotations

import asyncio

from aiogram import F, Router, html, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from handlers.helper_funcs import real_user_id
from services.admin_ops import (
    SETTING_VALUES,
    AdminOperationError,
    InvalidConfirmation,
    create_reset_confirmation,
    list_chats,
    reset_chat,
    set_setting,
    toggle_pvp,
)
from services.economy import (
    BalanceLimitExceeded,
    InvalidAmount,
    admin_adjust,
)

router = Router()


async def _require_admin(callback: types.CallbackQuery) -> bool:
    if not config.MY_ID or callback.from_user.id != config.MY_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return False
    return True


async def _render_admin_main(
    target: types.Message,
    *,
    edit: bool,
) -> None:
    chats = await asyncio.to_thread(list_chats)
    if not chats:
        text = "В базе пока нет данных о группах."
        if edit:
            await target.edit_text(text)
        else:
            await target.answer(text)
        return
    builder = InlineKeyboardBuilder()
    for chat_id, title in chats:
        display_name = title or f"ID: {chat_id}"
        builder.button(
            text=f"🏗 {display_name}",
            callback_data=f"adm:chat:{chat_id}",
        )
    builder.adjust(1)
    text = "🛠 <b>Панель управления</b>\nВыберите чат:"
    if edit:
        await target.edit_text(
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
    else:
        await target.answer(
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )


async def _render_chat_settings(
    callback: types.CallbackQuery,
    chat_id: int,
) -> None:
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="💰 Цена /sleep",
                    callback_data=f"adm:set:{chat_id}:sleep_price",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="⏳ Длительность /sleep",
                    callback_data=f"adm:set:{chat_id}:sleep_duration",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="⚔️ Подтверждение PvP",
                    callback_data=f"adm:pvp:{chat_id}",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🥔 Кулдаун /dig",
                    callback_data=f"adm:set:{chat_id}:dig_cd",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="🧹 Сбросить данные чата",
                    callback_data=f"adm:reset:{chat_id}",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="adm:back",
                )
            ],
        ]
    )
    await callback.message.edit_text(
        f"Настройки чата <code>{chat_id}</code>:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "adm:back")
async def admin_back_to_main(callback: types.CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    await _render_admin_main(callback.message, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:chat:"))
async def admin_chat_settings(callback: types.CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    try:
        chat_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный чат.", show_alert=True)
        return
    await _render_chat_settings(callback, chat_id)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:pvp:"))
async def toggle_pvp_confirm(callback: types.CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    try:
        chat_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный чат.", show_alert=True)
        return
    value = await asyncio.to_thread(
        toggle_pvp,
        chat_id,
        admin_id=callback.from_user.id,
    )
    await _render_chat_settings(callback, chat_id)
    status = "включено" if value else "выключено"
    await callback.answer(
        f"Подтверждение PvP {status}.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("adm:reset:"))
async def clear_db_ask(callback: types.CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    try:
        chat_id = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректный чат.", show_alert=True)
        return
    token = await asyncio.to_thread(
        create_reset_confirmation,
        chat_id,
        callback.from_user.id,
    )
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="ДА, СОЗДАТЬ BACKUP И СБРОСИТЬ",
                    callback_data=f"adm:confirm:{token}",
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"adm:chat:{chat_id}",
                )
            ],
        ]
    )
    await callback.message.edit_text(
        "⚠️ Будет создан полный backup базы, затем удалены пользователи, "
        f"деньги, предметы, займы и игры чата <code>{chat_id}</code>.\n"
        "Подтверждение действует 2 минуты.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:confirm:"))
async def clear_db_execute(callback: types.CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    token = callback.data.split(":", 2)[-1]
    try:
        result = await asyncio.to_thread(
            reset_chat,
            token,
            callback.from_user.id,
        )
    except InvalidConfirmation:
        await callback.answer(
            "Подтверждение истекло или уже использовано.",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        f"✅ Данные чата <code>{result.chat_id}</code> сброшены.\n"
        f"Backup: <code>{html.quote(result.backup_path.name)}</code>",
        parse_mode="HTML",
    )
    await callback.answer("Данные сброшены, backup создан.", show_alert=True)


@router.callback_query(F.data.startswith("adm:set:"))
async def set_value_menu(callback: types.CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    try:
        _, _, chat_id_raw, parameter = callback.data.split(":")
        chat_id = int(chat_id_raw)
        values = sorted(SETTING_VALUES[parameter])
    except (ValueError, KeyError):
        await callback.answer("Некорректный параметр.", show_alert=True)
        return
    labels = {
        "dig_cd": "кулдаун /dig в часах",
        "sleep_price": "цену /sleep в 🥔",
        "sleep_duration": "длительность /sleep в минутах",
    }
    builder = InlineKeyboardBuilder()
    for value in values:
        builder.button(
            text=str(value),
            callback_data=f"adm:save:{chat_id}:{parameter}:{value}",
        )
    builder.button(
        text="⬅️ Назад",
        callback_data=f"adm:chat:{chat_id}",
    )
    builder.adjust(3)
    await callback.message.edit_text(
        f"Выберите {labels[parameter]} для чата {chat_id}:",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:save:"))
async def save_value(callback: types.CallbackQuery) -> None:
    if not await _require_admin(callback):
        return
    try:
        _, _, chat_id_raw, parameter, value_raw = callback.data.split(":")
        chat_id = int(chat_id_raw)
        value = int(value_raw)
        await asyncio.to_thread(
            set_setting,
            chat_id,
            parameter,
            value,
            admin_id=callback.from_user.id,
        )
    except (ValueError, AdminOperationError):
        await callback.answer("Недопустимое значение.", show_alert=True)
        return
    await _render_chat_settings(callback, chat_id)
    await callback.answer("Настройка сохранена.", show_alert=True)


@router.message(Command("admin"), F.chat.type == "private")
async def admin_main(message: types.Message) -> None:
    if not config.MY_ID:
        await message.answer("Ошибка: MY_ID не настроен в .env")
        return
    if not message.from_user or message.from_user.id != config.MY_ID:
        return
    await _render_admin_main(message, edit=False)


@router.message(Command("add"), F.reply_to_message)
async def admin_add_potato(message: types.Message) -> None:
    if (
        not config.MY_ID
        or not message.from_user
        or message.from_user.id != config.MY_ID
    ):
        return
    target_id = real_user_id(message.reply_to_message)
    if target_id is None:
        await message.answer("Цель должна быть обычным пользователем.")
        return
    args = message.text.split() if message.text else []
    if len(args) < 2 or not args[1].lstrip("-").isdigit():
        await message.answer("Укажи сумму! Пример: /add 1000")
        return
    amount = int(args[1])
    if amount == 0 or abs(amount) > config.MAX_BALANCE:
        await message.answer("Сумма вне допустимого диапазона.")
        return
    try:
        balance = await asyncio.to_thread(
            admin_adjust,
            message.chat.id,
            target_id,
            amount,
            admin_id=message.from_user.id,
            operation_key=f"admin:{message.chat.id}:{message.message_id}",
        )
    except (InvalidAmount, BalanceLimitExceeded):
        await message.answer("Изменение превысило допустимый баланс.")
        return
    action = "выдал" if amount > 0 else "забрал"
    await message.answer(
        f"👑 Админ {action} {abs(amount)} 🥔 у "
        f"{html.quote(message.reply_to_message.from_user.full_name)}. "
        f"Баланс: {balance} 🥔.",
        parse_mode="HTML",
    )
