import random, sqlite3
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.helper_funcs import get_user_info, get_card_value
from handlers.states import BJState

router = Router()

def check_insurance(cursor, chat_id, user_id):
    cursor.execute("SELECT amount FROM inventory WHERE chat_id = ? AND user_id = ? AND item_type = 'insurance'", (chat_id, user_id))
    res = cursor.fetchone()
    if res and res[0] > 0:
        cursor.execute("UPDATE inventory SET amount = amount - 1 WHERE chat_id = ? AND user_id = ? AND item_type = 'insurance'", (chat_id, user_id))
        return True
    return False

# --- buttons ---
@router.callback_query(BJState.in_game, F.data == "bj_hit")
async def bj_hit_handler(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = callback.from_user.id
    if uid != data.get("player_id"):
        return await callback.answer("Это не ваша игра!", show_alert=True)

    deck, player_hand = data['deck'], data['p_hand']
    player_hand.append(deck.pop())
    score = get_card_value(player_hand)
    await state.update_data(deck=deck, p_hand=player_hand)
    
    if score > 21:
        bet = data['bet']
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        if check_insurance(cursor, callback.message.chat.id, uid):
            refund = bet // 2
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet - refund, callback.message.chat.id, uid))
            msg = f"💥 Перебор! Но страховка вернула {refund} 🥔"
        else:
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, uid))
            msg = f"💥 Перебор! Ты проиграл {bet} 🥔"
        conn.commit()
        conn.close()
        await callback.message.edit_text(msg)
        await state.clear()
    else:
        kb = types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(text="Еще ➕", callback_data="bj_hit"),
                types.InlineKeyboardButton(text="Стоп 🛑", callback_data="bj_stay")
            ]
        ])
        await callback.message.edit_text(
            f"🃏 <b>Блэкджек</b>\n\n"
            f"Ваши карты: {', '.join(player_hand)} (Счет: {score})\n"
            f"Дилер: {data['d_hand'][0]}, [?]",
            reply_markup=kb, parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(BJState.in_game, F.data == "bj_stay")
async def bj_stay_handler(callback: types.CallbackQuery, state: FSMContext):    
    data = await state.get_data()
    if callback.from_user.id != data.get("player_id"):
        return await callback.answer("Это не ваша игра!", show_alert=True)

    deck, player_hand, dealer_hand, bet = data['deck'], data['p_hand'], data['d_hand'], data['bet']
    player_score = get_card_value(player_hand)
    
    while get_card_value(dealer_hand) < 17:
        dealer_hand.append(deck.pop())
    
    dealer_score = get_card_value(dealer_hand)
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    if dealer_score > 21 or player_score > dealer_score:
        result = "🏆 <b>Вы выиграли!</b>"
        win_amount = bet
        cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (win_amount, callback.message.chat.id, callback.from_user.id))
    elif player_score < dealer_score:
        result = "📉 <b>Дилер выиграл.</b>"
        win_amount = -bet
        cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, callback.message.chat.id, callback.from_user.id))
    else:
        result = "🤝 <b>Ничья!</b>"
        win_amount = 0
        cursor.execute("UPDATE potatoes SET games = games + 1 WHERE chat_id = ? AND user_id = ?", (callback.message.chat.id, callback.from_user.id))

    conn.commit()
    conn.close()

    await callback.message.edit_text(
        f"{result}\n\n"
        f"Ваши карты: {', '.join(player_hand)} (Счет: {player_score})\n"
        f"Карты дилера: {', '.join(dealer_hand)} (Счет: {dealer_score})\n\n"
        f"Итог: {win_amount} 🥔", 
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()

# --- handlers ---
@router.message(Command("flip"))
async def coinflip(message: types.Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("Ставка? Пример: /flip 10")
    
    bet = int(args[1])
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, message.from_user.id))
    row = cursor.fetchone()

    if not row or bet > row[0]:
        conn.close()
        return await message.answer("Поднакопи перед походом в казино🤡")

    if random.choice([True, False]):
        cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (bet, message.chat.id, message.from_user.id))
        text = f"🌕 Орел! Ты выиграл {bet} 🥔!"
    else:
        if check_insurance(cursor, message.chat.id, message.from_user.id):
            refund = bet // 2 
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet - refund, message.chat.id, message.from_user.id))
            text = f"🌑 Решка! Ты проиграл, но сработала 🛡 страховка: вернули {refund} 🥔."
        else:
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, message.chat.id, message.from_user.id))
            text = f"🌑 Решка! Ты проиграл {bet} 🥔."

    conn.commit()
    conn.close()
    await message.answer(text)

@router.message(Command("roulette"))
async def roulette(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        return await message.answer("Формат: /roulette [ставка] [ставка_на]\nМожно ставить на: red/black/green, even/odd, 1st/2nd/3rd, 1-18/19-36 или число 0-36.")
    
    if not args[1].isdigit():
        return await message.answer("Ставка должна быть числом!")
        
    bet = int(args[1])
    pick = args[2].lower()
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, message.from_user.id))
    row = cursor.fetchone()

    if not row or bet > row[0]:
        conn.close()
        return await message.answer("Поднакопи перед походом в казино🤡")
    
    result_val = random.randint(0, 36)
    red_nums = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    
    if result_val == 0: color = "green"
    elif result_val in red_nums: color = "red"
    else: color = "black"

    # Проверка выигрыша
    is_win = False
    multiplier = 0
    
    if pick == str(result_val) or (pick == "green" and result_val == 0):
        is_win, multiplier = True, 36
    elif pick == color and pick in ["red", "black"]:
        is_win, multiplier = True, 2
    elif pick == "even" and result_val != 0 and result_val % 2 == 0:
        is_win, multiplier = True, 2
    elif pick == "odd" and result_val != 0 and result_val % 2 != 0:
        is_win, multiplier = True, 2
    elif pick == "1-18" and 1 <= result_val <= 18:
        is_win, multiplier = True, 2
    elif pick == "19-36" and 19 <= result_val <= 36:
        is_win, multiplier = True, 2
    elif pick == "1st" and 1 <= result_val <= 12:
        is_win, multiplier = True, 3
    elif pick == "2nd" and 13 <= result_val <= 24:
        is_win, multiplier = True, 3
    elif pick == "3rd" and 25 <= result_val <= 36:
        is_win, multiplier = True, 3

    if is_win:
        win = bet * (multiplier - 1)
        cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (win, message.chat.id, message.from_user.id))
        text = f"🎰 Выпало <b>{result_val} ({color})</b>! Твоя ставка зашла! Ты поднял {win} 🥔!"
    else:
        if check_insurance(cursor, message.chat.id, message.from_user.id):
            refund = bet // 2
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet - refund, message.chat.id, message.from_user.id))
            text = f"🎰 Выпало <b>{result_val} ({color})</b>! Ты проиграл, но сработала 🛡 страховка: вернули {refund} 🥔."
        else:
            cursor.execute("UPDATE potatoes SET amount = amount - ?, games = games + 1 WHERE chat_id = ? AND user_id = ?", (bet, message.chat.id, message.from_user.id))
            text = f"🎰 Выпало <b>{result_val} ({color})</b>. Проигрыш. 💸"

    conn.commit()
    conn.close()
    await message.answer(text, parse_mode="HTML")

@router.message(Command("bj"))
async def start_blackjack(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        return await message.answer("Ставка? Пример: /bj 10")
    
    bet = int(args[1])
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT amount FROM potatoes WHERE chat_id = ? AND user_id = ?", (message.chat.id, message.from_user.id))
    row = cursor.fetchone()

    if not row or bet > row[0]:
        conn.close()
        return await message.answer("Поднакопи перед походом в казино🤡")

    deck =['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] * 4
    random.shuffle(deck)
    
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop()]
    p_score = get_card_value(player_hand)

    if p_score == 21:
        bet = bet*1.5
        cursor.execute("UPDATE potatoes SET amount = amount + ?, games = games + 1, wins = wins + 1 WHERE chat_id = ? AND user_id = ?", (bet, message.chat.id, message.from_user.id))
        conn.commit()   
        conn.close()

        await message.answer(
            f"🃏 <b>БЛЭКДЖЕК!</b> 🃏\n\n"
            f"Ваши карты: {', '.join(player_hand)} (Счет: 21)\n"
            f"Дилер открывает карты: {', '.join(dealer_hand)} (Счет: {get_card_value(dealer_hand)})\n\n"
            f"💰 Ты сорвал куш: +{bet} 🥔!", 
            parse_mode="HTML"
        )
        return

    conn.close()
    await state.update_data(deck=deck, p_hand=player_hand, d_hand=dealer_hand, bet=bet, player_id=message.from_user.id)
    await state.set_state(BJState.in_game)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="Еще ➕", callback_data="bj_hit")
    kb.button(text="Стоп 🛑", callback_data="bj_stay")
    kb.adjust(2)
    
    await message.answer(
        f"🃏 <b>Блэкджек</b>\n\n"
        f"Ваши карты: {', '.join(player_hand)} (Счет: {p_score})\n"
        f"Дилер: {dealer_hand[0]}, [?]",
        reply_markup=kb.as_markup(), 
        parse_mode="HTML"
    )