import random
import sqlite3
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import Router, types, F
from aiogram.filters import Command
from handlers.helper_funcs import get_user_info

router = Router()

rps_games = {}

# --- buttons ---
@router.callback_query(F.data.startswith("pvp_acc:"))
async def pvp_accept(callback: types.CallbackQuery):
    _, c_id, bet, t_id = callback.data.split(":")
    c_id, bet, t_id = int(c_id), int(bet), int(t_id)

    is_allowed = False
    if callback.from_user.id == t_id:
        is_allowed = True
    elif t_id < 0:
        member = await callback.message.chat.get_member(callback.from_user.id)
        if member.status in ["administrator", "creator"]:
            is_allowed = True

    if not is_allowed:
        return await callback.answer("Это не твой вызов! ⛔️", show_alert=True)
        
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT amount, full_name FROM potatoes JOIN users ON potatoes.user_id = users.user_id AND potatoes.chat_id = users.chat_id WHERE potatoes.chat_id = ? AND potatoes.user_id = ?", (callback.message.chat.id, c_id))
    attacker = cursor.fetchone()
    
    cursor.execute("SELECT amount, full_name FROM potatoes JOIN users ON potatoes.user_id = users.user_id AND potatoes.chat_id = users.chat_id WHERE potatoes.chat_id = ? AND potatoes.user_id = ?", (callback.message.chat.id, t_id))
    target = cursor.fetchone()

    if not attacker or attacker[0] < bet or not target or target[0] < bet:
        await callback.message.edit_text("Дуэль не состоялась: у одного из игроков не хватает картошки! 🥔")
        conn.close()
        return

    is_challenger_winner = random.choice([True, False])
    
    if is_challenger_winner:
        w_id, l_id = c_id, t_id
        w_name, l_name = attacker[1], target[1]
    else:
        w_id, l_id = t_id, c_id
        w_name, l_name = target[1], attacker[1]

    cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, w_id))
    cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, l_id))
    
    conn.commit()
    conn.close()

    result_text = (
        f"⚔️ **Дуэль на {bet} 🥔 состоялась!**\n\n"
        f"🏆 Победитель: **{w_name}** (+{bet})\n"
        f"😭 Проигравший: **{l_name}** (-{bet})"
    )
    
    await callback.message.edit_text(result_text, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("pvp_dec:"))
async def pvp_decline(callback: types.CallbackQuery):
    _, c_id = callback.data.split(":")
    if callback.from_user.id == int(c_id):
         await callback.message.edit_text("Вызов отменен автором. 👋")
    else:
         await callback.message.edit_text(f"{callback.from_user.full_name} испугался и отклонил вызов! 👋")
    await callback.answer()


@router.callback_query(F.data.startswith("rps_acc:"))
async def rps_accepted(callback: types.CallbackQuery):
    _, c_id, t_id, bet = callback.data.split(":")
    if callback.from_user.id != int(t_id):
        return await callback.answer("Это не твой вызов!", show_alert=True)

    game_id = f"{callback.message.chat.id}_{callback.message.message_id}"
    rps_games[game_id] = {
        "p1": int(c_id),
        "p2": int(t_id),
        "bet": int(bet),
        "p1_move": None,
        "p2_move": None
    }

    kb = InlineKeyboardBuilder()
    kb.button(text="🪨", callback_data=f"rps_m:rock:{game_id}")
    kb.button(text="📜", callback_data=f"rps_m:paper:{game_id}")
    kb.button(text="✂️", callback_data=f"rps_m:scissors:{game_id}")
    
    await callback.message.edit_text(
        f"🎮 <b>Игра началась!</b>\nОба игрока, выберите жест на кнопках ниже 👇",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("rps_m:"))
async def rps_m(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    move = parts[1]
    game_id = parts[2]
    
    game = rps_games.get(game_id)
    if not game:
        return await callback.answer("Игра уже завершена!", show_alert=True)

    uid = callback.from_user.id

    if uid not in [game['p1'], game['p2']]:
        return await callback.answer("Ты не участвуешь!", show_alert=True)

    if uid == game['p1'] and not game['p1_move']:
        game['p1_move'] = move
        await callback.answer("Твой ход принят!")
    elif uid == game['p2'] and not game['p2_move']:
        game['p2_move'] = move
        await callback.answer("Твой ход принят!")
    else:
        return await callback.answer("Ты уже выбрал!")

    if game['p1_move'] and game['p2_move']:
        p1_id, p2_id = game['p1'], game['p2']
        m1, m2 = game['p1_move'], game['p2_move']
        bet = game['bet']
        
        wins_against = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        emoji = {"rock": "🪨", "scissors": "✂️", "paper": "📜"}

        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()

        if m1 == m2:
            cursor.execute("UPDATE potatoes SET games = games + 1 WHERE chat_id = ? AND user_id IN (?, ?)", (callback.message.chat.id, p1_id, p2_id))
            res_text = f"🤝 <b>Ничья!</b>\nОба выбрали {emoji[m1]}. Картошка остается при вас."
        elif wins_against[m1] == m2:
            cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, p1_id))
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, p2_id))
            res_text = f"🏆 Победил Игрок 1!\n{emoji[m1]} бьет {emoji[m2]}\n+{bet} 🥔"
        else:
            cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, p2_id))
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, p1_id))
            res_text = f"🏆 Победил Игрок 2!\n{emoji[m2]} бьет {emoji[m1]}\n+{bet} 🥔"

        conn.commit()
        conn.close()
        del rps_games[game_id]

        await callback.message.edit_text(f"🏁 <b>Результат игры:</b>\n\n{res_text}", parse_mode="HTML")

# --- handlers ---
@router.message(Command("give"))
async def give_potato(message: types.Message):
    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение того, кому хочешь дать картошку!")

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("Укажи сумму! Пример: /give 10")

    amount = int(args[1])
    if amount <= 0: return

    giver_id = message.from_user.id
    receiver_id = message.reply_to_message.from_user.id
    chat_id = message.chat.id

    if giver_id == receiver_id:
        return await message.answer("Передавать картошку самому себе нельзя! 🥔")

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (chat_id, giver_id))
    row = cursor.fetchone()
    
    if not row or row[0] < amount:
        conn.close()
        return await message.answer("У тебя недостаточно картошки!")

    try:
        cursor.execute("UPDATE potatoes SET amount = amount - ? WHERE chat_id = ? AND user_id = ?", (amount, chat_id, giver_id))
        cursor.execute("INSERT OR IGNORE INTO potatoes (chat_id, user_id, amount) VALUES (?, ?, 0)", (chat_id, receiver_id))
        cursor.execute("UPDATE potatoes SET amount = amount + ? WHERE chat_id = ? AND user_id = ?", (amount, chat_id, receiver_id))
        conn.commit()
        await message.answer(f"✅ Ты передал {amount} 🥔 пользователю {message.reply_to_message.from_user.full_name}!")
    except Exception as e:
        await message.answer("Произошла ошибка при передаче.")
    finally:
        conn.close()

@router.message(Command('pvp'))
async def pvp_battle(message: types.Message):
    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение игрока, с которым хочешь сразиться!\nПример: /pvp 5")
        
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) <= 0:
        return await message.answer("Укажи корректную ставку цифрой! Пример: /pvp 5")
        
    bet = int(args[1])
    c_id, c_name = get_user_info(message)
    d_id, d_name = get_user_info(message.reply_to_message)
    
    if c_id == d_id: return await message.answer("Нельзя драться с самим собой 🤡")
        
    if message.reply_to_message.from_user.is_bot and not message.reply_to_message.sender_chat:
        return await message.answer("Обычные боты не играют в азартные игры! 🤖")

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, c_id))
    c_row = cursor.fetchone()
    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, d_id))
    d_row = cursor.fetchone()

    if not c_row or c_row[0] < bet:
        conn.close()
        return await message.answer(f"У тебя недостаточно картошки! У тебя есть: {c_row[0] if c_row else 0} 🥔")
        
    if not d_row or d_row[0] < bet:
        conn.close()
        return await message.answer("У твоего противника не хватает картошки! Найди кого-то побогаче.")

    cursor.execute("SELECT pvp_confirm FROM settings WHERE chat_id = ?", (message.chat.id,))
    row = cursor.fetchone()
    is_confirm_on = row[0] if row else 1

    if is_confirm_on == 0:
        is_p1_win = random.choice([True, False])
        w_id, l_id = (c_id, d_id) if is_p1_win else (d_id, c_id)
        w_name, l_name = (c_name, d_name) if is_p1_win else (d_name, c_name)

        cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (bet, message.chat.id, w_id))
        cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, message.chat.id, l_id))
        conn.commit()
        conn.close()
        return await message.answer(f"⚔️ **Мгновенный бой!**\n🏆 Победитель: {w_name}\n😭 Проигравший: {l_name}")

    conn.close()
 
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
            types.InlineKeyboardButton(text="Принять ✅", callback_data=f"pvp_acc:{c_id}:{bet}:{d_id}"),
            types.InlineKeyboardButton(text="Отклонить ❌", callback_data=f"pvp_dec:{c_id}")
        ]
    ])
    await message.answer(f"⚔️ Игрок {message.reply_to_message.from_user.full_name}, тебя вызывает на дуэль {message.from_user.full_name}!\nСтавка: {bet} 🥔", reply_markup=kb)

@router.message(Command("rps"))
async def rps_challenge(message: types.Message):
    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение противника!")
    
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("Укажи ставку!")
    
    bet = int(args[1])
    c_id = message.from_user.id
    t_id = message.reply_to_message.from_user.id
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, c_id))
    c_row = cursor.fetchone()
    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, t_id))
    d_row = cursor.fetchone()

    if not c_row or c_row[0] < bet:
        conn.close()
        return await message.answer(f"У тебя недостаточно картошки! У тебя есть: {c_row[0] if c_row else 0} 🥔")
        
    if not d_row or d_row[0] < bet:
        conn.close()
        return await message.answer("У твоего противника не хватает картошки! Найди кого-то побогаче.")

    conn.close()

    kb = InlineKeyboardBuilder()
    kb.button(text="Принять вызов ✅", callback_data=f"rps_acc:{c_id}:{t_id}:{bet}")
    kb.button(text="Отказаться ❌", callback_data=f"pvp_dec:{c_id}") # Можно юзать pvp_dec, логика отказа та же
    
    await message.answer(
        f"🤜 <b>{message.from_user.full_name}</b> вызывает <b>{message.reply_to_message.from_user.full_name}</b> на КНБ!\n"
        f"Ставка: {bet} 🥔", 
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )