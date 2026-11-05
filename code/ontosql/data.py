"""Loading evaluation questions.

Two sources share the `Example` type:
  * Spider dev questions for the selected databases (clear questions)
  * The Ambiguity Stress Set (data/stress_set/stress_set.jsonl), 20 clear + 20 ambiguous

The stress set is the main benchmark in the proposal. Spider dev questions on
the same databases are an optional larger check of execution accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .types import AMBIGUOUS, CLEAR, Example

VALID_KINDS = {CLEAR, AMBIGUOUS}
VALID_AMBIGUITY_TYPES = {"column", "temporal", "aggregation", "reference"}


def load_spider(spider_dir: str | Path, db_ids: Iterable[str], split: str = "dev") -> list[Example]:
    """Questions from Spider's dev.json (or train_spider.json) for the given databases."""
    spider_dir = Path(spider_dir)
    fname = {"dev": "dev.json", "train": "train_spider.json"}[split]
    items = json.loads((spider_dir / fname).read_text())
    wanted = set(db_ids)
    out = []
    for i, it in enumerate(items):
        if it["db_id"] not in wanted:
            continue
        out.append(
            Example(
                id=f"spider-{split}-{i}",
                db_id=it["db_id"],
                question=it["question"],
                gold_sql=it["query"],
                kind=CLEAR,
                source="spider",
            )
        )
    return out


def load_jsonl(path: str | Path) -> list[dict]:
    rows = []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: bad JSON: {e}") from e
    return rows


def validate_stress_item(d: dict) -> list[str]:
    """Return a list of problems with one stress-set row (empty list = OK)."""
    problems = []
    for k in ("id", "db_id", "question", "gold_sql", "kind"):
        if not d.get(k):
            problems.append(f"missing {k}")
    kind = d.get("kind")
    if kind and kind not in VALID_KINDS:
        problems.append(f"kind must be one of {sorted(VALID_KINDS)}")
    if kind == AMBIGUOUS:
        if d.get("ambiguity_type") not in VALID_AMBIGUITY_TYPES:
            problems.append(f"ambiguity_type must be one of {sorted(VALID_AMBIGUITY_TYPES)}")
        interps = d.get("interpretations") or []
        if len(interps) < 2:
            problems.append("ambiguous items need >= 2 interpretations")
        ids = {i.get("id") for i in interps}
        if d.get("intended") not in ids:
            problems.append("intended must be the id of one interpretation")
        for i in interps:
            if not i.get("sql") or not i.get("description"):
                problems.append(f"interpretation {i.get('id')} needs sql and description")
    return problems


def load_stress_set(path: str | Path) -> list[Example]:
    rows = load_jsonl(path)
    errors = []
    for r in rows:
        for p in validate_stress_item(r):
            errors.append(f"{r.get('id', '?')}: {p}")
    if errors:
        raise ValueError("stress set has problems:\n  " + "\n  ".join(errors))
    return [Example.from_dict({**r, "source": "stress"}) for r in rows]


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
