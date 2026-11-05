"""Stage 6: self-verification and repair.  Owner: Vatsal.

Three checks before a query is returned:
  1. syntax      - the SQL parses (sqlglot, dialect="sqlite")
  2. schema      - every table and column referenced exists in the schema/ontology
  3. execution   - it runs on a read-only copy without error (ontosql.db.execute)

On failure the error message goes back to the generator; at most 2 repairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import Schema


@dataclass
class VerifyResult:
    ok: bool
    stage: str = ""  # "syntax" | "schema" | "execution" | "" when ok
    message: str = ""  # human-readable error fed back to the model


def verify(sql: str, schema: Schema, db_file: str | Path) -> VerifyResult:
    """Run the three checks in order and stop at the first failure.  TODO(Vatsal)"""
    raise NotImplementedError


def repair_messages(question: str, ddl: str, bad_sql: str, result: VerifyResult) -> list[dict[str, str]]:
    """Prompt that shows the failed query and the error and asks for a fixed query.  TODO(Vatsal)"""
    raise NotImplementedError
