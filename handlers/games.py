import random
import sqlite3
from aiogram import Router, types, F
from aiogram.filters import Command
import time

from handlers.helper_funcs import get_moscow_today, get_user_info

router = Router()

# --- handlers ---
# daily hero)
@router.message(Command("pidor"))
async def who_is_pidor(message: types.Message):
    if message.chat.type == "private":
        await message.answer("Эту команду можно использовать только в группах!")
        return

    today = get_moscow_today()
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT winner_name, last_date FROM winners WHERE chat_id = ?", (message.chat.id,))
    row = cursor.fetchone()

    if row and row[1] == today:
        await message.answer(f"Сегодняшний pidor уже выбран! Это — {row[0]}! ✨")
    else:
        cursor.execute("SELECT full_name FROM users WHERE chat_id = ? AND user_id != 777000", (message.chat.id,))
        users = cursor.fetchall()

        if len(users) < 2:
            await message.answer("Для игры нужно хотя бы 2 человека, которые писали боту!")
        else:
            winner = random.choice(users)[0]
            cursor.execute("INSERT OR REPLACE INTO winners (chat_id, winner_name, last_date) VALUES (?, ?, ?)",
                           (message.chat.id, winner, today))
            conn.commit()
            
            phrases =[
                f"Так-так... Кто же сегодня pidor? 🧐\nБарабанная дробь...\n\nЭто {winner}! 🎉",
                f"Сегодня боги pidors выбрали {winner}! ⭐",
                f"Внимательно изучив этот чат, я заявляю: {winner} — сегодня pidor! 🔥"
            ]
            await message.answer(random.choice(phrases))
    conn.close()

# digging potatoes
@router.message(Command('dig'))
async def dig_potato(message: types.Message):
    user_id, _ = get_user_info(message)
    now = int(time.time())
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT dig_cd FROM settings WHERE chat_id = ?", (message.chat.id,))
    res = cursor.fetchone()
    cd_hours = res[0] if res else 24
    cd_seconds = cd_hours * 3600
    
    cursor.execute("SELECT amount, last_dig_date FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, user_id))
    row = cursor.fetchone()
    
    last_dig = int(row[1]) if (row and row[1]) else 0
    
    if now - last_dig < cd_seconds:
        remaining = (cd_seconds - (now - last_dig)) // 60 
        await message.answer(f"Подожди еще {remaining} мин. ⏳")
        conn.close()
        return

    mined = random.randint(1, 10)
    
    if row is None:
        total = mined 
        cursor.execute("INSERT INTO potatoes (chat_id, user_id, amount, last_dig_date) VALUES (?, ?, ?, ?)",(message.chat.id, user_id, total, now))
    else:
        total = row[0] + mined 
        cursor.execute("UPDATE potatoes SET amount = ?, last_dig_date = ? WHERE chat_id = ? AND user_id = ?",(total, now, message.chat.id, user_id))
    
    conn.commit()
    conn.close()
    await message.answer(f"Ты пошел в огород и выкопал {mined} 🥔!\nТеперь у тебя в мешке: {total} шт.")

# top for dig game
@router.message(Command('top'))
async def top_potatoes(message: types.Message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prefix, full_name, amount, wins, games
        FROM potatoes 
        JOIN users ON potatoes.user_id = users.user_id AND potatoes.chat_id = users.chat_id
        WHERE potatoes.chat_id = ? 
        ORDER BY potatoes.amount DESC 
        LIMIT 10
    """, (message.chat.id,))
    top_players = cursor.fetchall()
    conn.close()
    
    if not top_players:
        return await message.answer("Тут пока пусто...")
        
    reply_text = "🏆 **Топ богачей чата:**\n\n"
    for index, (prefix, name, amount, wins, games) in enumerate(top_players, start=1):
        medal = ["🥇", "🥈", "🥉"][index-1] if index <= 3 else "👤"
        display_name = f"{prefix} {name}" if prefix else name
        
        # Считаем винрейт
        wr = int((wins / games) * 100) if games and games > 0 else 0
        wr_text = f" [WR: {wr}%]" if games > 0 else ""
        
        reply_text += f"{medal} {display_name} — {amount} 🥔{wr_text}\n"
        
    await message.answer(reply_text, parse_mode="Markdown")

