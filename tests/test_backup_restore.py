from __future__ import annotations

from pathlib import Path

from database import backup_database, save_user_data
from scripts.restore_db import restore_database
from services.economy import admin_adjust, get_balance


def test_backup_restore_round_trip(db_path: Path, tmp_path: Path) -> None:
    save_user_data(1, 2, "User", "Chat", "group", db_path)
    admin_adjust(
        1,
        2,
        50,
        admin_id=99,
        operation_key="grant:before-backup",
        db_path=db_path,
    )
    backup = backup_database(
        db_path,
        tmp_path / "backups",
        label="test",
    )
    admin_adjust(
        1,
        2,
        25,
        admin_id=99,
        operation_key="grant:after-backup",
        db_path=db_path,
    )
    assert get_balance(1, 2, db_path=db_path) == 75

    previous = restore_database(backup, db_path)

    assert previous.is_file()
    assert get_balance(1, 2, db_path=db_path) == 50
