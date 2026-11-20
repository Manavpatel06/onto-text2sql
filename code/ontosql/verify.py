"""Stage 6: self-verification and repair.  Owner: Vatsal.

Three checks before a query is returned:
  1. syntax      - the SQL parses (sqlglot, dialect="sqlite") and is a single read-only query
  2. schema      - every table and column referenced exists in the schema
  3. execution   - it runs on a read-only copy without error (ontosql.db.execute)

On failure the error message goes back to the generator; at most 2 repairs
(pipeline.MAX_REPAIRS).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from .db import ExecutionError, execute
from .prompts import SYSTEM_SQL
from .schema import Schema


@dataclass
class VerifyResult:
    ok: bool
    stage: str = ""  # "syntax" | "schema" | "execution" | "" when ok
    message: str = ""  # human-readable error fed back to the model


def _suggest(name: str, choices: list[str]) -> str:
    close = difflib.get_close_matches(name.lower(), [c.lower() for c in choices], n=1, cutoff=0.6)
    if not close:
        return ""
    orig = next(c for c in choices if c.lower() == close[0])
    return f"; did you mean {orig}?"


def check_syntax(sql: str) -> tuple[exp.Expression | None, str]:
    if not sql or not sql.strip():
        return None, "empty query"
    try:
        trees = [t for t in sqlglot.parse(sql, read="sqlite") if t is not None]
    except ParseError as e:
        return None, f"syntax error: {str(e).splitlines()[0]}"
    if len(trees) != 1:
        return None, "expected exactly one SQL statement"
    tree = trees[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.With)) and tree.find(exp.Select) is None:
        return None, "only read-only SELECT queries are allowed"
    if tree.find(exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create) is not None:
        return None, "only read-only SELECT queries are allowed"
    return tree, ""


def check_schema(tree: exp.Expression, schema: Schema) -> str:
    """Return an error message, or "" if every table and column exists."""
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    table_names = [t.name for t in schema.tables]
    alias_to_table: dict[str, str] = {}
    used_tables: list[str] = []
    for t in tree.find_all(exp.Table):
        name = t.name
        if not name or name.lower() in cte_names:
            continue
        real = schema.table(name)
        if real is None:
            return f"table {name} does not exist{_suggest(name, table_names)}"
        used_tables.append(real.name)
        alias_to_table[(t.alias or name).lower()] = real.name
        alias_to_table[name.lower()] = real.name

    select_aliases = {a.alias.lower() for a in tree.find_all(exp.Alias) if a.alias}
    subquery_aliases = {s.alias.lower() for s in tree.find_all(exp.Subquery) if s.alias}
    has_derived = bool(cte_names or subquery_aliases)

    for col in tree.find_all(exp.Column):
        name = col.name
        if not name or name == "*":
            continue
        qual = col.table.lower() if col.table else ""
        if qual:
            if qual in cte_names or qual in subquery_aliases:
                continue
            table = alias_to_table.get(qual)
            if table is None:
                return f"unknown table or alias {col.table} in {col.sql()}"
            if not schema.has_column(table, name):
                cols = [c.name for c in schema.table(table).columns]
                return f"column {table}.{name} does not exist{_suggest(name, cols)}"
            continue
        if name.lower() in select_aliases or has_derived:
            continue
        if not any(schema.has_column(t, name) for t in set(used_tables)):
            cols = [c.name for t in set(used_tables) for c in schema.table(t).columns]
            where = ", ".join(sorted(set(used_tables))) or "the query"
            return f"column {name} does not exist in {where}{_suggest(name, cols)}"
    return ""


def verify(sql: str, schema: Schema, db_file: str | Path) -> VerifyResult:
    """Run the three checks in order and stop at the first failure."""
    tree, err = check_syntax(sql)
    if tree is None:
        return VerifyResult(False, "syntax", err)
    err = check_schema(tree, schema)
    if err:
        return VerifyResult(False, "schema", err)
    try:
        execute(db_file, sql)
    except ExecutionError as e:
        return VerifyResult(False, "execution", f"execution error: {e}")
    return VerifyResult(True)


def repair_messages(question: str, ddl: str, bad_sql: str, result: VerifyResult) -> list[dict[str, str]]:
    """Prompt that shows the failed query and the error and asks for a fixed query."""
    user = (
        f"Database schema:\n{ddl}\n\n"
        f"Question: {question}\n\n"
        f"This query failed the {result.stage} check:\n{bad_sql or '(no query)'}\n\n"
        f"Error: {result.message}\n\n"
        "Write a corrected query that answers the question."
    )
    return [{"role": "system", "content": SYSTEM_SQL}, {"role": "user", "content": user}]
