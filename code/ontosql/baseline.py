"""Configuration A: direct Text-to-SQL baseline.

Question + serialized schema in, one SQL query out. No ontology, no
clarification, no verification. Every other configuration is compared
against this one.
"""

from __future__ import annotations

import time
from pathlib import Path

from .db import db_path
from .llm import ChatModel
from .prompts import extract_sql, sql_messages
from .schema import Schema, extract_schema, sample_rows, to_ddl
from .types import Example, Prediction


class SchemaCache:
    """Extract each database schema once per run."""

    def __init__(self, spider_dir: str | Path) -> None:
        self.spider_dir = Path(spider_dir)
        self._schemas: dict[str, Schema] = {}
        self._rows: dict[str, str] = {}

    def db_file(self, db_id: str) -> Path:
        return db_path(self.spider_dir, db_id)

    def schema(self, db_id: str) -> Schema:
        if db_id not in self._schemas:
            self._schemas[db_id] = extract_schema(self.db_file(db_id), db_id)
        return self._schemas[db_id]

    def rows(self, db_id: str, n: int = 3) -> str:
        if db_id not in self._rows:
            self._rows[db_id] = sample_rows(self.db_file(db_id), self.schema(db_id), n)
        return self._rows[db_id]


class DirectBaseline:
    config = "A"

    def __init__(
        self,
        model: ChatModel,
        schemas: SchemaCache,
        include_sample_rows: bool = False,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.schemas = schemas
        self.include_sample_rows = include_sample_rows
        self.temperature = temperature

    def predict(self, ex: Example) -> Prediction:
        t0 = time.perf_counter()
        ddl = to_ddl(self.schemas.schema(ex.db_id))
        extra = self.schemas.rows(ex.db_id) if self.include_sample_rows else ""
        messages = sql_messages(ex.question, ddl, extra_context=extra)
        try:
            raw = self.model.complete(messages, temperature=self.temperature)
            sql, err = extract_sql(raw), None
            if not sql:
                err = "no SQL found in model output"
        except Exception as e:  # keep the run going; record the failure
            raw, sql, err = "", "", f"llm error: {e}"
        return Prediction(
            example_id=ex.id,
            config=self.config,
            pred_sql=sql,
            latency_s=round(time.perf_counter() - t0, 3),
            error=err,
            trace={"raw_output": raw},
        )
