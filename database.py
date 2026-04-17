import sqlite3
from aiogram import types

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER,
        user_id INTEGER,
        full_name TEXT, 
        prefix TEXT,
        PRIMARY KEY (chat_id, user_id))''')
        
    cursor.execute('''CREATE TABLE IF NOT EXISTS potatoes (
        chat_id INTEGER,
        user_id INTEGER,
        amount INTEGER DEFAULT 0,
        last_dig_date INTEGER,
        wins INTEGER DEFAULT 0,
        games INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, user_id))''')
        
    # Таблица настроек
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        chat_id INTEGER PRIMARY KEY,
        sleep_price INTEGER DEFAULT 10,
        dig_cd INTEGER DEFAULT 24,  
        pvp_confirm INTEGER DEFAULT 1,
        sleep_duration INTEGER DEFAULT 2)''')
        
    # Остальные таблицы
    cursor.execute('CREATE TABLE IF NOT EXISTS winners (chat_id INTEGER PRIMARY KEY, winner_name TEXT, last_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, title TEXT)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (chat_id INTEGER, user_id INTEGER, item_type TEXT, amount INTEGER DEFAULT 0, PRIMARY KEY (chat_id, user_id, item_type))''')
    conn.commit()
    conn.close()

def save_user_data(chat_id, user_id, full_name, chat_title, chat_type):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    if user_id != 777000: 
        cursor.execute("""
            INSERT INTO users (chat_id, user_id, full_name) 
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET full_name = excluded.full_name
        """, (chat_id, user_id, full_name))
        
    if chat_type in["group", "supergroup"]:
        cursor.execute("INSERT OR REPLACE INTO chats (chat_id, title) VALUES (?, ?)",
                       (chat_id, chat_title))
    conn.commit()
    conn.close()