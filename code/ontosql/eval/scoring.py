"""Join predictions with examples, execute, and persist scored runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from ..data import load_jsonl, write_jsonl
from ..db import db_path
from ..types import Example, Prediction, Scored
from .exec_match import check


def score_run(
    examples: Sequence[Example],
    predictions: Sequence[Prediction],
    spider_dir: str | Path,
    timeout_s: float = 10.0,
) -> list[Scored]:
    by_id = {p.example_id: p for p in predictions}
    out = []
    for ex in examples:
        p = by_id.get(ex.id)
        if p is None:
            continue
        if not p.pred_sql:
            out.append(Scored(ex, p, valid=False, correct=False, exec_error=p.error or "no SQL"))
            continue
        valid, correct, err = check(db_path(spider_dir, ex.db_id), p.pred_sql, ex.gold_sql, timeout_s)
        out.append(Scored(ex, p, valid=valid, correct=correct, exec_error=err))
    return out


def save_scored(path: str | Path, scored: Sequence[Scored]) -> None:
    write_jsonl(
        path,
        (
            {
                "example": s.example.to_dict(),
                "prediction": s.prediction.to_dict(),
                "valid": s.valid,
                "correct": s.correct,
                "exec_error": s.exec_error,
            }
            for s in scored
        ),
    )


def load_scored(path: str | Path) -> list[Scored]:
    return [
        Scored(
            example=Example.from_dict(r["example"]),
            prediction=Prediction.from_dict(r["prediction"]),
            valid=r["valid"],
            correct=r["correct"],
            exec_error=r.get("exec_error"),
        )
        for r in load_jsonl(path)
    ]


def save_summary(path: str | Path, summary: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(summary, indent=2))
