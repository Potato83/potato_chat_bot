from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from database import DEFAULT_DB_PATH, backup_database, init_db


def restore_database(source: Path, target: Path) -> Path:
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == target.resolve():
        raise ValueError("source and target must be different files")

    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as probe:
        integrity = probe.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"source database is damaged: {integrity}")
        if (
            probe.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'potatoes'
                """
            ).fetchone()
            is None
        ):
            raise RuntimeError("source is not a Potato Bot database")

    pre_restore_backup = backup_database(target, label="pre-restore")
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_connection:
        with sqlite3.connect(target) as target_connection:
            source_connection.backup(target_connection)
    init_db(target)
    return pre_restore_backup


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Restore Potato Bot SQLite database. Stop the bot before running."
        )
    )
    parser.add_argument("source", type=Path, help="backup file to restore")
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"database to replace (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()
    backup = restore_database(args.source, args.target)
    print(f"Restore complete. Previous database: {backup}")


if __name__ == "__main__":
    main()
