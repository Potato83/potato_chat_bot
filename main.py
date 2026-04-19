import asyncio
import logging
import aiohttp

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand

from database import init_db
from handlers import admin, games, pve, pvp, common, shop
from middlewares import AntiSpamMiddleware
import config


# --- patch SSL  ---
old_init = aiohttp.TCPConnector.__init__
def new_init(self, *args, **kwargs):
    kwargs['ssl'] = False
    old_init(self, *args, **kwargs)
aiohttp.TCPConnector.__init__ = new_init

async def main():
    init_db()
    logging.basicConfig(level=logging.INFO)

    proxy_url = config.PROXY_URL
    if proxy_url:
        session = AiohttpSession(proxy=proxy_url)
        bot = Bot(token=config.BOT_TOKEN, session=session)
    else:
        bot = Bot(token=config.BOT_TOKEN)

    # === Меню команд ===
    commands =[
        BotCommand(command="start", description="Команды бота"),
        BotCommand(command="all", description="Пинг всех"),
        BotCommand(command="dig", description="Копать картошку (КД)"),
        BotCommand(command="top", description="Топ богачей чата"),
        BotCommand(command="pvp", description="Дуэль (ставка)"),
        BotCommand(command="rps", description="Камень-Ножницы-Бумага"),
        BotCommand(command="bj", description="Блэкджек (ставка)"),
        BotCommand(command="roulette", description="Рулетка (ставка)"),
        BotCommand(command="flip", description="Монетка (ставка)"),
        BotCommand(command="shop", description="Магазин предметов"),
        BotCommand(command="sleep", description="Усыпить игрока (мут)"),
        BotCommand(command="give", description="Передать картошку"),
        BotCommand(command="zaim", description="Взять в долг (50 🥔)"),
        BotCommand(command="pidor", description="pidor дня"),
    ]
    await bot.set_my_commands(commands)

    dp = Dispatcher()
    
    dp.message.middleware(AntiSpamMiddleware())

    dp.include_routers(
        admin.router,
        games.router,
        pvp.router,
        pve.router,
        shop.router,
        common.router,
    )

    print("--- БОТ ЗАПУСКАЕТСЯ ---")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

# silly citty
#                   ___
#  /\__/\          /  \
# | 0_0 |         |   /
# \____/_________/   |
#  |                 |
#  |  _____________ |
#_/ _/         _/ _/