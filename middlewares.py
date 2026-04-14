import time
from aiogram import BaseMiddleware
from aiogram.types import Message, ChatPermissions
from datetime import timedelta

from database import save_user_data

storage = {}

class AntiSpamMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        if not event.from_user or event.from_user.is_bot:
            return await handler(event, data)

        user_key = (event.chat.id, event.from_user.id)
        current_text = event.text.strip().lower()
        now = time.time()

        save_user_data(
            event.chat.id, 
            event.from_user.id, 
            event.from_user.full_name, 
            event.chat.title, 
            event.chat.type
        )

        if user_key in storage:
            last_text, count, last_time = storage[user_key]

            if current_text == last_text and (now - last_time) < 5:
                count += 1
                if count >= 20: # На n-й раз мутим
                    try:
                        await event.chat.restrict(
                            user_id=event.from_user.id,
                            permissions=ChatPermissions(can_send_messages=False),
                            until_date=timedelta(minutes=5)
                        )
                        await event.answer("🔇 Хватит спамить! Отдохни 5 минут.")
                        del storage[user_key]
                        return
                    except:
                        pass
            else:
                count = 1
            
            storage[user_key] = [current_text, count, now]
        else:
            storage[user_key] = [current_text, 1, now]

        return await handler(event, data)