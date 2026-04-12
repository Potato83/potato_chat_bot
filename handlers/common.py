import random
import sqlite3
from aiogram import Router, types, F
from aiogram.filters import Command

from handlers.helper_funcs  import get_user_info

router = Router()

# --- handlers ---
# check
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    _, name = get_user_info(message)
    commands = "/ping /all - пинг всех\n/pidor - выбирает сегодняшнего pidor!"\
            "\n/dig - копать картошку\n/top - лидеры по количеству картошка"\
            "\n/pvp - подраться за картошку!\n/rps - камень-ножницы-бумага"\
            "\n/give - отдать кому-то картошки\n /bj - блэкджек"\
            "\n/flip - подбросить монетку\n /roulette - крутить рулетку"\
            "\n/shop - команды магазина\n/pat - погладить кого-то"
            
                
    await message.answer(f"Привет, {name}! Бот запущен.\n\nКоманды:\n{commands}")

# ping all
@router.message(Command("ping", "all"))
async def cmd_ping(message: types.Message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT user_id, full_name FROM users WHERE chat_id = ?", (message.chat.id,))
    users = cursor.fetchall()
    conn.close()

    if not users:
        return

    text = "📢 <b>Общий сбор!</b>\n\n"
    for uid, name in users:
        if uid < 0: 
            text += f"📢 {name}, "
        else:
            text += f'<a href="tg://user?id={uid}">{name}</a>, '

    await message.answer(text, parse_mode="HTML")

# patter)
@router.message(Command("pat"))
async def cmd_pat(message: types.Message):
    if not message.reply_to_message:
        await message.answer("Эту команду нужно писать в ответ на сообщение того, кого хочешь погладить!")
        return
    _, patter = get_user_info(message)
    _, patted = get_user_info(message.reply_to_message)
    await message.answer(f"{patter} погладил(а) {patted} по голове! 🥰")

# doggy
@router.message(F.text.lower().regexp(r"раф|гаф|гав"))
async def goodboy(message: types.Message):
    await message.reply(random.choice(["good boy!", "хороший песик!"]))

# POTATO!!
@router.message(F.text.lower().contains("картошка"))
async def potato_reaction(message: types.Message):
    await message.reply("Кто-то сказал КАРТОШКА? 🥔")