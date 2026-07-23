from __future__ import annotations

import asyncio
import logging
import ssl
from contextlib import suppress
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import BotCommand, ErrorEvent

import config
from database import init_db
from handlers import admin, common, games, pve, pvp, shop
from middlewares import AntiSpamMiddleware
from services.economy import run_reconciliation_worker
from services.games import run_game_cleanup_worker
from services.loans import run_loan_worker

logger = logging.getLogger(__name__)


class ConfigurableAiohttpSession(AiohttpSession):
    """Aiogram session with TLS settings scoped to this bot only."""

    def __init__(
        self,
        *,
        proxy: str | None = None,
        verify_tls: bool = True,
        ca_file: str | Path | None = None,
    ) -> None:
        super().__init__(proxy=proxy)
        if not verify_tls:
            self._connector_init["ssl"] = False
        elif ca_file:
            self._connector_init["ssl"] = ssl.create_default_context(
                cafile=str(ca_file)
            )


def build_bot_session() -> ConfigurableAiohttpSession:
    if not config.TLS_VERIFY:
        logger.warning(
            "TLS certificate verification is disabled for the Telegram session"
        )
    return ConfigurableAiohttpSession(
        proxy=config.PROXY_URL,
        verify_tls=config.TLS_VERIFY,
        ca_file=config.TLS_CA_FILE,
    )


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.middleware(AntiSpamMiddleware())
    dispatcher.include_routers(
        admin.router,
        games.router,
        pvp.router,
        pve.router,
        shop.router,
        common.router,
    )

    @dispatcher.errors()
    async def handle_unexpected_error(event: ErrorEvent) -> bool:
        update = event.update
        exception = event.exception
        logger.error(
            "Unhandled update error",
            exc_info=(
                type(exception),
                exception,
                exception.__traceback__,
            ),
            extra={
                "update_id": update.update_id if update else None,
            },
        )
        return True

    return dispatcher


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "%(message)s"
        ),
    )
    config.validate_runtime_config()
    await asyncio.to_thread(init_db)

    bot = Bot(token=config.BOT_TOKEN, session=build_bot_session())
    commands = [
        BotCommand(command="start", description="Команды бота"),
        BotCommand(command="all", description="Позвать известных участников"),
        BotCommand(command="dig", description="Копать картошку"),
        BotCommand(command="top", description="Топ богачей чата"),
        BotCommand(command="pvp", description="Дуэль на ставку"),
        BotCommand(command="rps", description="Камень-Ножницы-Бумага"),
        BotCommand(command="bj", description="Блэкджек"),
        BotCommand(command="roulette", description="Рулетка"),
        BotCommand(command="flip", description="Монетка"),
        BotCommand(command="shop", description="Магазин"),
        BotCommand(command="sleep", description="Усыпить игрока"),
        BotCommand(command="give", description="Передать картошку"),
        BotCommand(command="zaim", description="Занять 50 🥔"),
        BotCommand(command="pidor", description="Ежедневная игра"),
    ]
    await bot.set_my_commands(commands)

    dispatcher = build_dispatcher()
    workers = [
        asyncio.create_task(run_loan_worker(bot), name="loan-worker"),
        asyncio.create_task(
            run_game_cleanup_worker(bot),
            name="game-cleanup-worker",
        ),
        asyncio.create_task(
            run_reconciliation_worker(),
            name="reconciliation-worker",
        ),
    ]
    logger.info("Potato bot is starting")
    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker
        await bot.session.close()
        logger.info("Potato bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
