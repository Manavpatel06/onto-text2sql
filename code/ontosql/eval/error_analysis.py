"""Export failed predictions to a CSV for manual error labelling.

The proposal sorts every error into one of these categories. Fill the
`category` column by hand, save as errors_labelled.csv, then rerun `report`.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

from ..types import AMBIGUOUS, CLEAR, Scored

CATEGORIES = [
    "schema_linking",
    "join",
    "aggregation",
    "value_grounding",
    "unresolved_ambiguity",
    "unnecessary_clarification",
    "repair_failure",
    "other",
]


def suggest_category(s: Scored) -> str:
    """A rough first guess to speed up labelling; always check it by hand."""
    p = s.prediction
    if s.example.kind == CLEAR and p.asked_clarification:
        return "unnecessary_clarification"
    if s.example.kind == AMBIGUOUS and not p.asked_clarification and not s.correct:
        return "unresolved_ambiguity"
    if p.n_repairs > 0 and not s.valid:
        return "repair_failure"
    err = (s.exec_error or "").lower()
    if "no such column" in err or "no such table" in err:
        return "schema_linking"
    return ""


def export_errors(path: str | Path, runs: dict[str, Sequence[Scored]]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["config", "id", "db_id", "kind", "ambiguity_type", "question", "gold_sql",
             "pred_sql", "asked", "valid", "exec_error", "suggested", "category", "notes"]
        )
        for cfg, scored in sorted(runs.items()):
            for s in scored:
                wrong = not s.correct or (s.example.kind == CLEAR and s.prediction.asked_clarification)
                if not wrong:
                    continue
                w.writerow(
                    [cfg, s.example.id, s.example.db_id, s.example.kind, s.example.ambiguity_type or "",
                     s.example.question, s.example.gold_sql, s.prediction.pred_sql,
                     int(s.prediction.asked_clarification), int(s.valid), s.exec_error or "",
                     suggest_category(s), "", ""]
                )
                n += 1
    return n
