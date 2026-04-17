import sqlite3
import asyncio
import time
import random
from datetime import datetime, timedelta, timezone

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import ChatPermissions

from handlers.helper_funcs import get_user_info

router = Router()

# Словарь для хранения кулдаунов займов (КД - 1 час)
zaim_cooldowns = {}

# --- buttons ---
@router.callback_query(F.data.startswith("buy:"))
async def buy_item(callback: types.CallbackQuery):
    _, item_type, price = callback.data.split(":")
    price = int(price)
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    res = cursor.fetchone()
    if not res or res[0] < price:
        await callback.answer("У тебя мало картошки! 🥔", show_alert=True)
        conn.close()
        return

    cursor.execute("UPDATE potatoes SET amount = amount - ? WHERE chat_id = ? AND user_id = ?", (price, chat_id, user_id))
    
    cursor.execute("""
        INSERT INTO inventory (chat_id, user_id, item_type, amount) 
        VALUES (?, ?, ?, 1)
        ON CONFLICT(chat_id, user_id, item_type) DO UPDATE SET amount = amount + 1
    """, (chat_id, user_id, item_type))
    
    conn.commit()
    conn.close()
    
    await callback.answer(f"Успешно куплено: {item_type}! 🛍", show_alert=True)

# --- handlers ---
# shop
@router.message(Command("shop"))
async def open_shop(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🛡 Щит (50 🥔)", callback_data="buy:shield:50")],[types.InlineKeyboardButton(text="📜 Лицензия на титул (200 🥔)(/settitle)", callback_data="buy:title:200")],[types.InlineKeyboardButton(text="🛡 Страховка казино (100 🥔)", callback_data="buy:insurance:100")]
    ])
    await message.answer("🛒 <b>Картофельная лавка</b>\nТут можно потратить свои запасы:", reply_markup=kb, parse_mode="HTML")

# mute someone
@router.message(Command('sleep'))
async def sleep_user(message: types.Message):
    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение цели!")

    attacker_id, attacker_name = get_user_info(message)
    target_id, target_name = get_user_info(message.reply_to_message)

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        # 1. Проверяем щит цели
        cursor.execute("SELECT amount FROM inventory WHERE chat_id = ? AND user_id = ? AND item_type = 'shield'", (message.chat.id, target_id))
        shield = cursor.fetchone()
        if shield and shield[0] > 0:
            cursor.execute("UPDATE inventory SET amount = amount - 1 WHERE chat_id = ? AND user_id = ? AND item_type = 'shield'", (message.chat.id, target_id))
            conn.commit()
            return await message.answer(f"🛡 {target_name} отразил атаку щитом!")

        # 2. Проверяем настройки и баланс
        cursor.execute("SELECT sleep_price, sleep_duration FROM settings WHERE chat_id = ?", (message.chat.id,))
        set_row = cursor.fetchone()
        price = set_row[0] if set_row else 10
        duration = set_row[1] if set_row else 2

        cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, attacker_id))
        balance = cursor.fetchone()
        if not balance or balance[0] < price:
            return await message.answer(f"Мало картошки (нужно {price})")

        # 3. Мутим со стаком времени
        member = await message.bot.get_chat_member(message.chat.id, target_id)
        now = datetime.now(timezone.utc)
        
        if getattr(member, 'until_date', None) and member.until_date > now:
            new_until_date = member.until_date + timedelta(minutes=duration)
            msg_text = f"💤 Сон продлен! {target_name} будет спать еще {duration} мин. (Цена: {price} 🥔)"
        else:
            new_until_date = now + timedelta(minutes=duration)
            msg_text = f"💤 {target_name} уснул на {duration} мин. (Цена: {price} 🥔)"

        await message.bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=new_until_date
        )
        cursor.execute("UPDATE potatoes SET amount = amount - ? WHERE chat_id = ? AND user_id = ?", (price, message.chat.id, attacker_id))
        conn.commit()
        await message.answer(msg_text)

    except Exception as e:
        await message.answer("Не вышло. Возможно, цель — админ.")
    finally:
        conn.close()

@router.message(Command("settitle"))
async def set_user_title(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("Использование: `/settitle Король` (до 15 символов)", parse_mode="Markdown")

    new_prefix = args[1].strip()
    
    if len(new_prefix) > 15:
        return await message.answer("⚠️ Титул слишком длинный! Максимум 15 символов.")

    user_id = message.from_user.id
    chat_id = message.chat.id

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT amount FROM inventory WHERE chat_id = ? AND user_id = ? AND item_type = 'title'", 
                       (chat_id, user_id))
        res = cursor.fetchone()

        if not res or res[0] <= 0:
            return await message.answer("❌ У тебя нет Лицензии на титул! Купи её в /shop.")

        cursor.execute("UPDATE inventory SET amount = amount - 1 WHERE chat_id = ? AND user_id = ? AND item_type = 'title'", 
                       (chat_id, user_id))
        
        cursor.execute("UPDATE users SET prefix = ? WHERE chat_id = ? AND user_id = ?", 
                       (f"[{new_prefix}]", chat_id, user_id))
        
        conn.commit()
        await message.answer(f"✅ Твой новый титул установлен: **{new_prefix}**", parse_mode="Markdown")
        
    finally:
        conn.close()

@router.message(Command("removetitle"))
async def remove_user_title(message: types.Message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET prefix = NULL WHERE chat_id = ? AND user_id = ?", 
                   (message.chat.id, message.from_user.id))
    conn.commit()
    conn.close()
    await message.answer("Титул успешно удален! Теперь ты обычный фермер.")
    

# --- Логика займов ---
@router.message(Command("zaim"))
async def take_loan(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    key = (chat_id, user_id)
    now = time.time()
    
    if key in zaim_cooldowns:
        if now - zaim_cooldowns[key] < 3600:
            rem = int(3600 - (now - zaim_cooldowns[key])) // 60
            return await message.answer(f"🏦 КД на займ! Приходи через {rem} мин.")
            
    zaim_cooldowns[key] = now
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Выдаем 50 картошек
    cursor.execute("UPDATE potatoes SET amount = amount + 50 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    if cursor.rowcount == 0:
        cursor.execute("INSERT INTO potatoes (chat_id, user_id, amount) VALUES (?, ?, 50)", (chat_id, user_id))
    conn.commit()
    conn.close()
    
    await message.answer(f"🏦 {message.from_user.full_name}, ты взял в долг 50 🥔!\nВерни через 30 минут, иначе получишь мут на 10 минут.")
    
    # Запускаем таймер возврата в фоне
    asyncio.create_task(loan_timer(message.bot, chat_id, user_id, message.from_user.full_name))

async def loan_timer(bot, chat_id, user_id, user_name):
    await asyncio.sleep(1800) # Ждем 30 минут
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    row = cursor.fetchone()
    
    if row and row[0] >= 50:
        # Успешное погашение
        cursor.execute("UPDATE potatoes SET amount = amount - 50 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        conn.commit()
        conn.close()
        try:
            await bot.send_message(chat_id, f"🏦 Время вышло! {user_name} успешно погасил долг (50 🥔 списано).")
        except: pass
    else:
        # Не вернул долг - списываем до нуля и даем мут
        cursor.execute("UPDATE potatoes SET amount = CASE WHEN amount < 50 THEN 0 ELSE amount - 50 END WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        conn.commit()
        conn.close()
        
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            now = datetime.now(timezone.utc)
            # Если уже в муте - стакаем
            new_until = (member.until_date if getattr(member, 'until_date', None) and member.until_date > now else now) + timedelta(minutes=random.randint(300,1440))
            
            await bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=new_until
            )
            await bot.send_message(chat_id, f"🚨 {user_name} не вернул долг вовремя! Наказание: мут на 10 минут.")
        except Exception:
            await bot.send_message(chat_id, f"🚨 {user_name} не вернул долг, но замутить его не удалось (возможно, админ).")