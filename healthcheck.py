from __future__ import annotations

import sys

from database import connect


def main() -> int:
    try:
        with connect() as connection:
            result = connection.execute("SELECT 1").fetchone()
        return 0 if result and result[0] == 1 else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
