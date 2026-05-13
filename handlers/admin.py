import sqlite3
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config


router = Router()

# --- buttons --- 
@router.callback_query(F.data == "admin_back")
async def admin_back_to_main(callback: types.CallbackQuery):
    # По сути, мы копируем логику из admin_main, но делаем .edit_text
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM chats")
    chats = cursor.fetchall()
    conn.close()

    builder = InlineKeyboardBuilder()
    for chat_id, title in chats:
        display_name = title if title else f"ID: {chat_id}"
        builder.button(text=f"🏗 {display_name}", callback_data=f"adm_chat:{chat_id}")
    
    builder.adjust(1)
    await callback.message.edit_text("🛠 <b>Панель управления</b>\nВыберите чат:", 
                                     reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("adm_chat:"))
async def admin_chat_settings(callback: types.CallbackQuery):
    chat_id = callback.data.split(":")[1]

    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💰 Цена /sleep", callback_data=f"set_val:{chat_id}:sleep_price")],
        [types.InlineKeyboardButton(text="⏳ Длительность /sleep", callback_data=f"set_val:{chat_id}:sleep_duration")],
        [types.InlineKeyboardButton(text="⚔️ Подтверждение PVP (Вкл/Выкл)", callback_data=f"toggle_pvp:{chat_id}")],
        [types.InlineKeyboardButton(text="🥔 Время КД /dig", callback_data=f"set_val:{chat_id}:dig_cd")],
        [types.InlineKeyboardButton(text="🧹 Очистить БД", callback_data=f"clear_confirm:{chat_id}")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(f"Настройки чата <code>{chat_id}</code>:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("toggle_pvp:"))
async def toggle_pvp_confirm(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("INSERT OR IGNORE INTO settings (chat_id, pvp_confirm) VALUES (?, 1)", (chat_id,))
    cursor.execute("SELECT pvp_confirm FROM settings WHERE chat_id = ?", (chat_id,))
    res = cursor.fetchone()

    new_val = 0 if res[0] == 1 else 1
    
    cursor.execute("UPDATE settings SET pvp_confirm = ? WHERE chat_id = ?", (new_val, chat_id))
    conn.commit()
    conn.close()
    
    status = "ВКЛЮЧЕНО" if new_val == 1 else "ВЫКЛЮЧЕНО"
    await callback.answer(f"Подтверждение PVP теперь {status}", show_alert=True)
    
    await admin_chat_settings(callback)

@router.callback_query(F.data.startswith("clear_confirm:"))
async def clear_db_ask(callback: types.CallbackQuery):
    chat_id = callback.data.split(":")[1]
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="ДА, УДАЛЯЙ ВСЁ 🔥", callback_data=f"clear_final:{chat_id}")],
        [types.InlineKeyboardButton(text="Ой, нет, назад! ⬅️", callback_data=f"adm_chat:{chat_id}")]
    ])
    
    await callback.message.edit_text(f"⚠️ <b>ВНИМАНИЕ!</b>\nВы собираетесь обнулить всю картошку в чате <code>{chat_id}</code>. Это действие необратимо!", 
                                    reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("clear_final:"))
async def clear_db_execute(callback: types.CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM potatoes WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM winners WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM settings WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()
    
    await callback.answer("БАЗА ДАННЫХ ЧАТА ОЧИЩЕНА 🧹", show_alert=True)
    await callback.message.edit_text(f"✅ Данные чата {chat_id} успешно удалены.")

@router.callback_query(F.data.startswith("adm_chat:"))
async def admin_chat_settings(callback: types.CallbackQuery):
    chat_id = callback.data.split(":")[1]
    
    # menu
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💰 Цена /sleep", callback_data=f"set_val:{chat_id}:sleep_price")],
        [types.InlineKeyboardButton(text="🧹 Очистить БД чата", callback_data=f"clear_confirm:{chat_id}")],
        [types.InlineKeyboardButton(text="🥔 Имениться время КД /dig", callback_data=f"set_val:{chat_id}:dig_cd")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])
    
    await callback.message.edit_text(f"Настройки для чата <code>{chat_id}</code>:", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("set_val:"))
async def set_value_menu(callback: types.CallbackQuery):
    _, chat_id, param = callback.data.split(":")
    
    # Разные наборы кнопок для разных параметров
    if param == "dig_cd":
        values = [1, 3, 6, 12, 24]
        label = "время КД /dig (в часах)"
    elif param == "sleep_price":
        values = [5, 10, 20, 50, 100]
        label = "цену /sleep (в 🥔)"
    elif param == "sleep_duration":
        values = [1, 2, 5, 10, 20, 30]
        label = "длительность /sleep в минутах"

    builder = InlineKeyboardBuilder()
    for val in values:
        builder.button(text=str(val), callback_data=f"save_v:{chat_id}:{param}:{val}")
    
    builder.button(text="⬅️ Назад", callback_data=f"adm_chat:{chat_id}")
    builder.adjust(3)
    
    await callback.message.edit_text(f"Выберите новое {label} для чата {chat_id}:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(F.data.startswith("save_v:"))
async def save_value(callback: types.CallbackQuery):
    _, chat_id, param, value = callback.data.split(":")

    allowed_params = ["sleep_price", "dig_cd", "sleep_duration"]
    if param not in allowed_params:
        await callback.answer("Ошибка: недопустимый параметр!", show_alert=True)
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO settings (chat_id) VALUES (?)", (chat_id,))
    cursor.execute(f"UPDATE settings SET {param} = ? WHERE chat_id = ?", (value, chat_id)) #nosec
    conn.commit()
    conn.close()
    
    await callback.answer(f"✅ Сохранено: {param} = {value}", show_alert=True)
    callback.data = f"adm_chat:{chat_id}" 
    await admin_chat_settings(callback)

# --- handlers ---
# admin panel
@router.message(Command("admin"), F.chat.type == "private")
async def admin_main(message: types.Message):
    
    ADMIN_ID = config.MY_ID
    
    if not ADMIN_ID:
        await message.answer("Ошибка: ADMIN_ID не настроен в .env")
        return
    
    if message.from_user.id != ADMIN_ID:
        return
        
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM chats")
    chats = cursor.fetchall()
    conn.close()

    if not chats:
        await message.answer("В базе пока нет данных о группах.")
        return

    builder = InlineKeyboardBuilder()
    
    for chat_id, title in chats:
        display_name = title if title else f"ID: {chat_id}"
        builder.button(text=f"🏗 {display_name}", callback_data=f"adm_chat:{chat_id}")
    
    builder.adjust(1)

    await message.answer(
        "🛠 <b>Панель управления</b>\nВыберите чат для настройки:", 
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.message(Command("add"), F.reply_to_message)
async def admin_add_potato(message: types.Message):
    ADMIN_ID = config.MY_ID

    if not ADMIN_ID or message.from_user.id != ADMIN_ID:
        return
        
    args = message.text.split()
    if len(args) < 2 or not args[1].lstrip('-').isdigit():
        return await message.answer("Укажи сумму! Пример: /add 1000")
        
    amount = int(args[1])
    target_id = message.reply_to_message.from_user.id
    target_name = message.reply_to_message.from_user.full_name
    chat_id = message.chat.id

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (chat_id, target_id))
    row = cursor.fetchone()

    if row:
        cursor.execute("UPDATE potatoes SET amount = amount + ? WHERE chat_id = ? AND user_id = ?", (amount, chat_id, target_id))
    else:
        cursor.execute("INSERT INTO potatoes (chat_id, user_id, amount, last_dig_date) VALUES (?, ?, ?, 0)", (chat_id, target_id, amount))

    conn.commit()
    conn.close()

    action = "выдал" if amount >= 0 else "забрал"
    await message.answer(f"👑 Админ {action} {abs(amount)} 🥔 для {target_name}!")