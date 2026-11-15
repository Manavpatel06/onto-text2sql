"""Stage 2: ontology-grounded query planning.  Owner: Vian.

Given the question, the schema and the ontology, ask the LLM for a small JSON
plan and the key phrases with the ontology concepts each might refer to.
Config B passes this plan, plus the ontology text, into SQL generation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import ChatModel
from .ontology import Ontology
from .schema import Schema, to_ddl

_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)

SYSTEM_PLAN = (
    "You map a question about a SQLite database to a compact JSON query plan. "
    "Use only tables and columns that exist in the schema. "
    "Return one JSON object and no other text."
)


@dataclass
class KeyPhrase:
    phrase: str
    candidates: list[str] = field(default_factory=list)  # ontology keys, e.g. "orders.order_date"


@dataclass
class QueryPlan:
    target_attributes: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    joins: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    aggregation: str | None = None
    group_by: list[str] = field(default_factory=list)
    order_by: list[str] = field(default_factory=list)
    limit: int | None = None
    key_phrases: list[KeyPhrase] = field(default_factory=list)
    raw: str = ""  # model output, kept for debugging

    def as_text(self) -> str:
        """Short text version passed to SQL generation."""
        parts: list[str] = []
        if self.tables:
            parts.append("tables: " + ", ".join(self.tables))
        if self.joins:
            parts.append("joins: " + "; ".join(self.joins))
        if self.filters:
            parts.append("filter: " + "; ".join(self.filters))
        if self.target_attributes:
            parts.append("output: " + ", ".join(self.target_attributes))
        if self.aggregation:
            parts.append("aggregation: " + self.aggregation)
        if self.group_by:
            parts.append("group by: " + ", ".join(self.group_by))
        if self.order_by:
            parts.append("order by: " + ", ".join(self.order_by))
        if self.limit is not None:
            parts.append(f"limit: {self.limit}")
        if self.key_phrases:
            bits = []
            for phrase in self.key_phrases:
                targets = ", ".join(phrase.candidates) if phrase.candidates else "?"
                bits.append(f"{phrase.phrase} -> {targets}")
            parts.append("phrases: " + "; ".join(bits))
        return " | ".join(parts)


def plan_query(question: str, schema: Schema, ontology: Ontology, model: ChatModel) -> QueryPlan:
    """Call the model with a JSON-only prompt and parse into QueryPlan.

    Must not crash on malformed JSON: retry once, then return a QueryPlan
    with only `raw` filled so the pipeline can fall back to plain generation.
    """
    messages = plan_messages(question, to_ddl(schema), ontology.context_text())
    raw = model.complete(messages, temperature=0.0)
    plan = _parse_plan(raw)
    if plan is None:
        raw = model.complete(messages, temperature=0.0)
        plan = _parse_plan(raw)
        if plan is None:
            return QueryPlan(raw=raw)
    plan.raw = raw
    return plan


def plan_messages(question: str, ddl: str, ontology_text: str) -> list[dict[str, str]]:
    """Prompt for the planner. Separate from SQL generation so ablation A-D share one SQL prompt."""
    user = (
        f"Database schema:\n{ddl}\n\n"
        f"Schema descriptions:\n{ontology_text}\n\n"
        f"Question: {question}\n\n"
        "Return a JSON object with these keys:\n"
        '- "target_attributes": list of Table.column values or expressions to return\n'
        '- "tables": list of table names\n'
        '- "joins": list of short join descriptions\n'
        '- "filters": list of filter descriptions\n'
        '- "aggregation": string or null (count, sum, avg, min, max)\n'
        '- "group_by": list of strings\n'
        '- "order_by": list of strings\n'
        '- "limit": integer or null\n'
        '- "key_phrases": list of {"phrase": string, "candidates": ["Table.column", ...]}\n\n'
        "key_phrases are the short spans that pick out a column, a time, an aggregate, or a ranking. "
        "candidates are the schema columns that phrase could refer to."
    )
    return [
        {"role": "system", "content": SYSTEM_PLAN},
        {"role": "user", "content": user},
    ]


def _parse_plan(raw: str) -> QueryPlan | None:
    try:
        data = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    phrases = []
    for item in data.get("key_phrases") or []:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase") or "").strip()
        if not phrase:
            continue
        candidates = [str(c).strip() for c in (item.get("candidates") or []) if str(c).strip()]
        phrases.append(KeyPhrase(phrase=phrase, candidates=candidates))
    aggregation = data.get("aggregation")
    if aggregation is not None:
        aggregation = str(aggregation).strip() or None
    return QueryPlan(
        target_attributes=_str_list(data.get("target_attributes")),
        tables=_str_list(data.get("tables")),
        joins=_str_list(data.get("joins")),
        filters=_str_list(data.get("filters")),
        aggregation=aggregation,
        group_by=_str_list(data.get("group_by")),
        order_by=_str_list(data.get("order_by")),
        limit=_limit(data.get("limit")),
        key_phrases=phrases,
    )


def _extract_json(raw: str):
    text = _THINK.sub("", raw or "")
    fenced = _FENCE.search(text)
    blob = fenced.group(1) if fenced else text
    start = blob.find("{")
    end = blob.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    return json.loads(blob[start : end + 1])


def _str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _limit(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
