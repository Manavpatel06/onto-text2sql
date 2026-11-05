"""Stage 2: ontology-grounded query planning.  Owner: Vian.

Given the question, the schema and the ontology, ask the LLM for a small JSON
plan and the key phrases with the ontology concepts each might refer to.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .llm import ChatModel
from .ontology import Ontology
from .schema import Schema


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
        """Short text version passed to SQL generation.  TODO(Vian)"""
        raise NotImplementedError


def plan_query(question: str, schema: Schema, ontology: Ontology, model: ChatModel) -> QueryPlan:
    """Call the model with a JSON-only prompt and parse into QueryPlan.

    Must not crash on malformed JSON: retry once, then return a QueryPlan
    with only `raw` filled so the pipeline can fall back to plain generation.

    TODO(Vian)
    """
    raise NotImplementedError
