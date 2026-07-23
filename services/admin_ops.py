from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from database import backup_database, connect

SETTING_VALUES = {
    "dig_cd": {1, 3, 6, 12, 24},
    "sleep_price": {5, 10, 20, 50, 100},
    "sleep_duration": {1, 2, 5, 10, 20, 30},
}
SETTING_UPDATE_SQL = {
    "dig_cd": "UPDATE settings SET dig_cd = ? WHERE chat_id = ?",
    "sleep_price": "UPDATE settings SET sleep_price = ? WHERE chat_id = ?",
    "sleep_duration": (
        "UPDATE settings SET sleep_duration = ? WHERE chat_id = ?"
    ),
}


class AdminOperationError(Exception):
    pass


class InvalidConfirmation(AdminOperationError):
    pass


@dataclass(frozen=True, slots=True)
class ResetResult:
    chat_id: int
    backup_path: Path


def list_chats(
    *,
    db_path: str | Path | None = None,
) -> list[tuple[int, str | None]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT chat_id, title FROM chats ORDER BY title, chat_id"
        ).fetchall()
        return [(int(row["chat_id"]), row["title"]) for row in rows]


def toggle_pvp(
    chat_id: int,
    *,
    admin_id: int,
    db_path: str | Path | None = None,
) -> int:
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO settings (chat_id) VALUES (?)",
            (chat_id,),
        )
        current = connection.execute(
            "SELECT pvp_confirm FROM settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        new_value = 0 if int(current["pvp_confirm"]) == 1 else 1
        connection.execute(
            "UPDATE settings SET pvp_confirm = ? WHERE chat_id = ?",
            (new_value, chat_id),
        )
        connection.execute(
            """
            INSERT INTO admin_audit (
                admin_id, chat_id, action, details, created_at
            )
            VALUES (?, ?, 'toggle_pvp', ?, ?)
            """,
            (admin_id, chat_id, f"value={new_value}", int(time.time())),
        )
        return new_value


def get_pvp_setting(
    chat_id: int,
    *,
    db_path: str | Path | None = None,
) -> bool:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT pvp_confirm FROM settings WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return bool(row["pvp_confirm"]) if row else True


def set_setting(
    chat_id: int,
    parameter: str,
    value: int,
    *,
    admin_id: int,
    db_path: str | Path | None = None,
) -> None:
    if parameter not in SETTING_VALUES or value not in SETTING_VALUES[parameter]:
        raise AdminOperationError("invalid setting value")

    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT OR IGNORE INTO settings (chat_id) VALUES (?)",
            (chat_id,),
        )
        connection.execute(
            SETTING_UPDATE_SQL[parameter],
            (value, chat_id),
        )
        connection.execute(
            """
            INSERT INTO admin_audit (
                admin_id, chat_id, action, details, created_at
            )
            VALUES (?, ?, 'set_setting', ?, ?)
            """,
            (
                admin_id,
                chat_id,
                f"{parameter}={value}",
                int(time.time()),
            ),
        )


def create_reset_confirmation(
    chat_id: int,
    admin_id: int,
    *,
    now: int | None = None,
    db_path: str | Path | None = None,
) -> str:
    current_time = int(time.time()) if now is None else now
    token = secrets.token_urlsafe(12)
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO admin_confirmations (
                token, action, chat_id, admin_id, expires_at
            )
            VALUES (?, 'reset_chat', ?, ?, ?)
            """,
            (token, chat_id, admin_id, current_time + 120),
        )
        connection.execute(
            """
            DELETE FROM admin_confirmations
            WHERE expires_at < ? OR used_at IS NOT NULL
            """,
            (current_time,),
        )
    return token


def reset_chat(
    token: str,
    admin_id: int,
    *,
    now: int | None = None,
    db_path: str | Path | None = None,
) -> ResetResult:
    current_time = int(time.time()) if now is None else now
    path = Path(db_path) if db_path else None

    with connect(path) as connection:
        confirmation = connection.execute(
            """
            SELECT chat_id
            FROM admin_confirmations
            WHERE token = ? AND action = 'reset_chat'
              AND admin_id = ? AND used_at IS NULL AND expires_at > ?
            """,
            (token, admin_id, current_time),
        ).fetchone()
        if confirmation is None:
            raise InvalidConfirmation("confirmation is invalid or expired")
        chat_id = int(confirmation["chat_id"])

    backup_path = backup_database(path, label=f"before-reset-{chat_id}")

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        consumed = connection.execute(
            """
            UPDATE admin_confirmations
            SET used_at = ?
            WHERE token = ? AND admin_id = ?
              AND used_at IS NULL AND expires_at > ?
            """,
            (current_time, token, admin_id, current_time),
        )
        if consumed.rowcount != 1:
            raise InvalidConfirmation("confirmation was already used")

        connection.execute("DELETE FROM games WHERE chat_id = ?", (chat_id,))
        connection.execute("DELETE FROM loans WHERE chat_id = ?", (chat_id,))
        connection.execute(
            "DELETE FROM inventory WHERE chat_id = ?", (chat_id,)
        )
        connection.execute(
            "DELETE FROM operations WHERE chat_id = ?", (chat_id,)
        )
        connection.execute(
            "DELETE FROM potatoes WHERE chat_id = ?", (chat_id,)
        )
        connection.execute("DELETE FROM winners WHERE chat_id = ?", (chat_id,))
        connection.execute(
            "DELETE FROM settings WHERE chat_id = ?", (chat_id,)
        )
        connection.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
        connection.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
        connection.execute(
            """
            INSERT INTO admin_audit (
                admin_id, chat_id, action, details, created_at
            )
            VALUES (?, ?, 'reset_chat', ?, ?)
            """,
            (
                admin_id,
                chat_id,
                f"backup={backup_path.name}",
                current_time,
            ),
        )
    return ResetResult(chat_id=chat_id, backup_path=backup_path)
