"""Read-only SQLite access with a wall-clock timeout.

All execution (baseline, verification, evaluation) goes through `execute`
so that a bad query can never modify a database or hang a run.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_S = 10.0


class ExecutionError(Exception):
    """Raised when a query fails to execute (syntax, missing table, timeout...)."""


def db_path(spider_dir: str | Path, db_id: str) -> Path:
    """Location of a Spider database file: <spider>/database/<db_id>/<db_id>.sqlite."""
    return Path(spider_dir) / "database" / db_id / f"{db_id}.sqlite"


def connect_readonly(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    # Spider contains some non-UTF8 text; never crash on decode.
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    return conn


def execute(
    path: str | Path, sql: str, timeout_s: float = DEFAULT_TIMEOUT_S, max_rows: int = 100_000
) -> list[tuple[Any, ...]]:
    """Run `sql` against the database at `path` and return all rows.

    Raises ExecutionError on any failure, including exceeding `timeout_s`.
    """
    if not sql or not sql.strip():
        raise ExecutionError("empty query")
    conn = connect_readonly(path)
    deadline = time.monotonic() + timeout_s

    def _abort_if_late() -> int:
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(_abort_if_late, 10_000)
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows + 1)
        if len(rows) > max_rows:
            rows = rows[:max_rows]
        return [tuple(r) for r in rows]
    except sqlite3.OperationalError as e:
        if "interrupted" in str(e):
            raise ExecutionError(f"timeout after {timeout_s}s") from e
        raise ExecutionError(str(e)) from e
    except (sqlite3.Error, ValueError) as e:
        raise ExecutionError(str(e)) from e
    finally:
        conn.close()
