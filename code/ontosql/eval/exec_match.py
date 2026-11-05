"""Execution-match comparison used for Execution Accuracy (EX).

Two queries match when they return the same result on the database:
  * rows are compared as a multiset unless the gold query has a top-level
    ORDER BY, in which case row order must also match;
  * column order is ignored (a query that selects (b, a) instead of (a, b)
    still counts) by trying column permutations when widths agree;
  * numbers are compared after rounding, so 2 == 2.0 and float noise is ignored.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from ..db import ExecutionError, execute

FLOAT_DIGITS = 6
MAX_PERMUTE_COLS = 6


def _norm(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        f = round(float(v), FLOAT_DIGITS)
        return int(f) if f.is_integer() else f
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, str):
        return v.strip()
    return v


def _norm_rows(rows: list[tuple]) -> list[tuple]:
    return [tuple(_norm(v) for v in r) for r in rows]


def has_top_level_order_by(sql: str) -> bool:
    """True if ORDER BY appears outside any parentheses (i.e. on the outer query)."""
    depth = 0
    s = re.sub(r"'(?:[^']|'')*'", "''", sql)  # blank out string literals
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and s[i : i + 8].upper() == "ORDER BY":
            return True
    return False


def results_match(pred: list[tuple], gold: list[tuple], ordered: bool) -> bool:
    pred, gold = _norm_rows(pred), _norm_rows(gold)
    if len(pred) != len(gold):
        return False
    if not gold:
        return True
    wp, wg = len(pred[0]), len(gold[0])
    if wp != wg:
        return False

    def same(p: list[tuple]) -> bool:
        return p == gold if ordered else Counter(p) == Counter(gold)

    if same(pred):
        return True
    if wp > MAX_PERMUTE_COLS:
        return False
    for perm in itertools.permutations(range(wp)):
        if perm == tuple(range(wp)):
            continue
        if same([tuple(r[i] for i in perm) for r in pred]):
            return True
    return False


def check(
    db_file: str | Path, pred_sql: str, gold_sql: str, timeout_s: float = 10.0
) -> tuple[bool, bool, Optional[str]]:
    """Return (valid, correct, error).

    valid   - the predicted query executed without error
    correct - its result matches the gold query's result
    """
    try:
        pred_rows = execute(db_file, pred_sql, timeout_s=timeout_s)
    except ExecutionError as e:
        return False, False, str(e)
    try:
        gold_rows = execute(db_file, gold_sql, timeout_s=timeout_s)
    except ExecutionError as e:
        # A broken gold query is a data bug, not a model error; surface it loudly.
        return True, False, f"GOLD FAILED: {e}"
    return True, results_match(pred_rows, gold_rows, has_top_level_order_by(gold_sql)), None
