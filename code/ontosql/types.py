"""Shared record types passed between pipeline stages.

Every stage reads and writes these dataclasses, so each team member can work
on their module independently as long as they keep these shapes stable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

CLEAR = "clear"
AMBIGUOUS = "ambiguous"


@dataclass
class Example:
    """One evaluation question.

    `kind` is "clear" or "ambiguous". Ambiguous items come from the Ambiguity
    Stress Set and carry their interpretations plus the intended one.
    """

    id: str
    db_id: str
    question: str
    gold_sql: str
    kind: str = CLEAR
    source: str = "spider"  # "spider" or "stress"
    ambiguity_type: Optional[str] = None  # column | temporal | aggregation | reference
    ambiguous_phrase: Optional[str] = None
    interpretations: list[dict[str, Any]] = field(default_factory=list)
    intended: Optional[str] = None  # id of the intended interpretation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Example":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Prediction:
    """What a pipeline configuration produced for one Example."""

    example_id: str
    config: str
    pred_sql: str
    asked_clarification: bool = False
    clarification_question: Optional[str] = None
    user_answer: Optional[str] = None
    flagged_phrases: list[str] = field(default_factory=list)
    n_repairs: int = 0
    latency_s: float = 0.0
    error: Optional[str] = None
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Prediction":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Scored:
    """A Prediction joined with its Example and the execution check."""

    example: Example
    prediction: Prediction
    valid: bool  # predicted SQL parsed and executed without error
    correct: bool  # execution result matches gold
    exec_error: Optional[str] = None
