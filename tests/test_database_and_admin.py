from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from database import SCHEMA_VERSION, connect, init_db, save_user_data
from services.admin_ops import (
    InvalidConfirmation,
    create_reset_confirmation,
    reset_chat,
)
from services.economy import admin_adjust, get_balance


def test_legacy_real_balance_is_normalized(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE potatoes (
                chat_id INTEGER,
                user_id INTEGER,
                amount INTEGER DEFAULT 0,
                last_dig_date INTEGER,
                wins INTEGER DEFAULT 0,
                games INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
            """
        )
        connection.execute(
            "INSERT INTO potatoes (chat_id, user_id, amount) VALUES (1, 2, 2.5)"
        )

    init_db(path)

    with connect(path) as connection:
        row = connection.execute(
            "SELECT amount, typeof(amount) AS value_type FROM potatoes"
        ).fetchone()
        assert (row["amount"], row["value_type"]) == (2, "integer")
        assert connection.execute("PRAGMA user_version").fetchone()[0] == (
            SCHEMA_VERSION
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE potatoes SET amount = 3.5 WHERE chat_id = 1 AND user_id = 2"
            )


def test_reset_creates_backup_and_deletes_all_chat_data(
    db_path: Path,
) -> None:
    save_user_data(1, 2, "User", "Chat", "group", db_path)
    admin_adjust(
        1,
        2,
        50,
        admin_id=99,
        operation_key="grant",
        db_path=db_path,
    )
    token = create_reset_confirmation(1, 99, now=100, db_path=db_path)
    result = reset_chat(token, 99, now=101, db_path=db_path)

    assert result.backup_path.is_file()
    assert get_balance(1, 2, db_path=db_path) == 0
    with connect(db_path) as connection:
        assert connection.execute(
            "SELECT 1 FROM users WHERE chat_id = 1"
        ).fetchone() is None
        assert connection.execute(
            "SELECT 1 FROM chats WHERE chat_id = 1"
        ).fetchone() is None
    with pytest.raises(InvalidConfirmation):
        reset_chat(token, 99, now=102, db_path=db_path)
