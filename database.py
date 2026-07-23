from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

import config

DEFAULT_DB_PATH = config.DATABASE_PATH
SCHEMA_VERSION = 3


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def backup_database(
    db_path: str | Path | None = None,
    backup_dir: str | Path | None = None,
    *,
    label: str = "backup",
) -> Path:
    source_path = Path(db_path or DEFAULT_DB_PATH)
    destination_dir = Path(backup_dir or config.BACKUP_DIR)
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    destination = destination_dir / f"{source_path.stem}-{label}-{timestamp}.db"

    with connect(source_path) as source:
        with sqlite3.connect(destination) as target:
            source.backup(target)
    return destination


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _column_names(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    if column not in _column_names(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _create_core_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            full_name TEXT NOT NULL DEFAULT '',
            prefix TEXT,
            updated_at INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS potatoes (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            last_dig_date INTEGER,
            wins INTEGER NOT NULL DEFAULT 0,
            games INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            sleep_price INTEGER NOT NULL DEFAULT 10,
            dig_cd INTEGER NOT NULL DEFAULT 24,
            pvp_confirm INTEGER NOT NULL DEFAULT 1,
            sleep_duration INTEGER NOT NULL DEFAULT 2
        );

        CREATE TABLE IF NOT EXISTS winners (
            chat_id INTEGER PRIMARY KEY,
            winner_name TEXT NOT NULL,
            last_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT
        );

        CREATE TABLE IF NOT EXISTS inventory (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (chat_id, user_id, item_type)
        );

        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            principal INTEGER NOT NULL CHECK (principal > 0),
            due_amount INTEGER NOT NULL CHECK (due_amount >= principal),
            issued_at INTEGER NOT NULL,
            due_at INTEGER NOT NULL,
            next_loan_at INTEGER NOT NULL,
            settled_at INTEGER,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'settled'))
        );
        """
    )

    # Columns added after the original public schema.
    _ensure_column(connection, "users", "updated_at", "INTEGER NOT NULL DEFAULT 0")


def _create_transaction_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_key TEXT NOT NULL UNIQUE,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            kind TEXT NOT NULL,
            reference_id TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_operations_account
            ON operations(chat_id, user_id, id);
        CREATE INDEX IF NOT EXISTS idx_operations_reference
            ON operations(reference_id);

        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (
                kind IN ('blackjack', 'pvp', 'rps', 'flip', 'roulette')
            ),
            chat_id INTEGER NOT NULL,
            challenger_id INTEGER NOT NULL,
            target_id INTEGER,
            bet INTEGER NOT NULL CHECK (bet > 0),
            status TEXT NOT NULL CHECK (
                status IN (
                    'pending', 'active', 'settled', 'declined', 'expired'
                )
            ),
            challenger_reserved INTEGER NOT NULL DEFAULT 0
                CHECK (challenger_reserved IN (0, 1)),
            target_reserved INTEGER NOT NULL DEFAULT 0
                CHECK (target_reserved IN (0, 1)),
            payload TEXT NOT NULL DEFAULT '{}',
            message_id INTEGER,
            result TEXT,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            settled_at INTEGER,
            version INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_games_expiry
            ON games(status, expires_at);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_blackjack
            ON games(chat_id, challenger_id)
            WHERE kind = 'blackjack' AND status = 'active';

        CREATE TABLE IF NOT EXISTS admin_confirmations (
            token TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER
        );

        CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            chat_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_loans_one_active
            ON loans(chat_id, user_id)
            WHERE status = 'active';
        CREATE INDEX IF NOT EXISTS idx_loans_due
            ON loans(status, due_at);
        """
    )


def _create_integrity_triggers(connection: sqlite3.Connection) -> None:
    max_balance = int(config.MAX_BALANCE)
    connection.executescript(
        f"""
        CREATE TRIGGER IF NOT EXISTS potatoes_amount_insert_guard
        BEFORE INSERT ON potatoes
        WHEN typeof(NEW.amount) != 'integer'
          OR NEW.amount < -{max_balance}
          OR NEW.amount > {max_balance}
        BEGIN
            SELECT RAISE(ABORT, 'invalid balance');
        END;

        CREATE TRIGGER IF NOT EXISTS potatoes_amount_update_guard
        BEFORE UPDATE OF amount ON potatoes
        WHEN typeof(NEW.amount) != 'integer'
          OR NEW.amount < -{max_balance}
          OR NEW.amount > {max_balance}
        BEGIN
            SELECT RAISE(ABORT, 'invalid balance');
        END;

        CREATE TRIGGER IF NOT EXISTS inventory_amount_insert_guard
        BEFORE INSERT ON inventory
        WHEN typeof(NEW.amount) != 'integer' OR NEW.amount < 0
        BEGIN
            SELECT RAISE(ABORT, 'invalid inventory amount');
        END;

        CREATE TRIGGER IF NOT EXISTS inventory_amount_update_guard
        BEFORE UPDATE OF amount ON inventory
        WHEN typeof(NEW.amount) != 'integer' OR NEW.amount < 0
        BEGIN
            SELECT RAISE(ABORT, 'invalid inventory amount');
        END;
        """
    )


def _seed_opening_ledger(connection: sqlite3.Connection) -> None:
    now = int(time.time())
    connection.execute(
        """
        INSERT OR IGNORE INTO operations (
            operation_key, chat_id, user_id, delta, balance_after,
            kind, reference_id, created_at
        )
        SELECT
            'opening:' || chat_id || ':' || user_id,
            chat_id,
            user_id,
            CAST(amount AS INTEGER),
            CAST(amount AS INTEGER),
            'opening_balance',
            NULL,
            ?
        FROM potatoes
        """,
        (now,),
    )
    # SQLite uses dynamic typing. Normalize any historical REAL values before
    # the integer-only trigger starts protecting future writes.
    connection.execute(
        "UPDATE potatoes SET amount = CAST(amount AS INTEGER) "
        "WHERE typeof(amount) != 'integer'"
    )


def init_db(db_path: str | Path | None = None) -> None:
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    should_backup = False
    if path.exists() and path.stat().st_size > 0:
        with sqlite3.connect(path) as probe:
            current_version = probe.execute("PRAGMA user_version").fetchone()[0]
            should_backup = current_version < SCHEMA_VERSION and _table_exists(
                probe, "potatoes"
            )
    if should_backup and os.getenv("SKIP_AUTO_DB_BACKUP") != "1":
        backup_database(path, label="pre-migration")

    with connect(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("BEGIN IMMEDIATE")
        _create_core_schema(connection)
        _create_transaction_schema(connection)
        _seed_opening_ledger(connection)
        _create_integrity_triggers(connection)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def save_user_data(
    chat_id: int,
    user_id: int,
    full_name: str,
    chat_title: str | None,
    chat_type: str,
    db_path: str | Path | None = None,
) -> None:
    if user_id == 777000:
        return

    now = int(time.time())
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO users (chat_id, user_id, full_name, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                full_name = excluded.full_name,
                updated_at = excluded.updated_at
            """,
            (chat_id, user_id, full_name, now),
        )
        if chat_type in {"group", "supergroup"}:
            connection.execute(
                """
                INSERT INTO chats (chat_id, title)
                VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title
                """,
                (chat_id, chat_title),
            )
