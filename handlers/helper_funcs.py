from datetime import datetime, timedelta, timezone
from aiogram import types
from datetime import timedelta


# --- helper funcs ---
# always mocsow time
def get_moscow_today():
    moscow_time = datetime.now(timezone.utc) + timedelta(hours=3)
    return moscow_time.strftime("%Y-%m-%d")

# smart id
def get_user_info(msg: types.Message):
    if msg.sender_chat:
        return msg.sender_chat.id, msg.sender_chat.title
    return msg.from_user.id, msg.from_user.first_name

# black jack
def get_card_value(hand):
    score = 0
    aces = 0
    for card in hand:
        if card in ['J', 'Q', 'K']: score += 10
        elif card == 'A': 
            aces += 1
            score += 11
        else: score += int(card)
        
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score

# incurance
def check_insurance(cursor, chat_id, user_id):
    cursor.execute("SELECT amount FROM inventory WHERE chat_id = ? AND user_id = ? AND item_type = 'insurance'", (chat_id, user_id))
    res = cursor.fetchone()
    if res and res[0] > 0:
        cursor.execute("UPDATE inventory SET amount = amount - 1 WHERE chat_id = ? AND user_id = ? AND item_type = 'insurance'", (chat_id, user_id))
        return True
    return False