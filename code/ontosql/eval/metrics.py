"""Metrics from the proposal's evaluation plan (Table II).

  EX   Execution Accuracy, overall and split by clear / ambiguous
  SVR  SQL Validity Rate: generated queries that parse and execute
  Ambiguity detection precision / recall / F1 (stress set only)
  UCR  Unnecessary Clarification Rate: clear stress-set questions where the system asked anyway
  CG   Clarification Gain: EX(C) - EX(B) on ambiguous questions
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from ..types import AMBIGUOUS, CLEAR, Scored


def _rate(num: int, den: int) -> Optional[float]:
    return num / den if den else None


@dataclass
class PRF:
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]
    tp: int
    fp: int
    fn: int


def ambiguity_prf(scored: Sequence[Scored]) -> PRF:
    """Ambiguity flag (= system asked for clarification) vs. stress-set label."""
    items = [s for s in scored if s.example.source == "stress"]
    tp = sum(1 for s in items if s.prediction.asked_clarification and s.example.kind == AMBIGUOUS)
    fp = sum(1 for s in items if s.prediction.asked_clarification and s.example.kind == CLEAR)
    fn = sum(1 for s in items if not s.prediction.asked_clarification and s.example.kind == AMBIGUOUS)
    p = _rate(tp, tp + fp)
    r = _rate(tp, tp + fn)
    f1 = 2 * p * r / (p + r) if p is not None and r is not None and (p + r) > 0 else None
    return PRF(p, r, f1, tp, fp, fn)


def summarize(scored: Sequence[Scored]) -> dict:
    """All single-configuration metrics for one run."""
    n = len(scored)
    clear = [s for s in scored if s.example.kind == CLEAR]
    amb = [s for s in scored if s.example.kind == AMBIGUOUS]
    stress_clear = [s for s in clear if s.example.source == "stress"]
    prf = ambiguity_prf(scored)
    lat = sorted(s.prediction.latency_s for s in scored)
    return {
        "n": n,
        "n_clear": len(clear),
        "n_ambiguous": len(amb),
        "ex": _rate(sum(s.correct for s in scored), n),
        "ex_clear": _rate(sum(s.correct for s in clear), len(clear)),
        "ex_ambiguous": _rate(sum(s.correct for s in amb), len(amb)),
        "validity": _rate(sum(s.valid for s in scored), n),
        "amb_precision": prf.precision,
        "amb_recall": prf.recall,
        "amb_f1": prf.f1,
        "ucr": _rate(sum(s.prediction.asked_clarification for s in stress_clear), len(stress_clear)),
        "avg_repairs": _rate(sum(s.prediction.n_repairs for s in scored), n),
        "median_latency_s": lat[len(lat) // 2] if lat else None,
    }


def clarification_gain(run_b: Sequence[Scored], run_c: Sequence[Scored]) -> Optional[float]:
    """EX(C) - EX(B) on ambiguous questions, matched by example id."""
    b = {s.example.id: s for s in run_b if s.example.kind == AMBIGUOUS}
    c = {s.example.id: s for s in run_c if s.example.kind == AMBIGUOUS}
    ids = sorted(set(b) & set(c))
    if not ids:
        return None
    return (sum(c[i].correct for i in ids) - sum(b[i].correct for i in ids)) / len(ids)


def paired_bootstrap(
    run_x: Sequence[Scored],
    run_y: Sequence[Scored],
    stat: Callable[[Sequence[Scored]], float] = lambda r: sum(s.correct for s in r) / len(r),
    n_boot: int = 2000,
    seed: int = 0,
) -> dict:
    """Difference stat(Y) - stat(X) with a 95% CI from resampling the same question ids.

    With only ~40 questions, report the interval, not just the point estimate.
    """
    x = {s.example.id: s for s in run_x}
    y = {s.example.id: s for s in run_y}
    ids = sorted(set(x) & set(y))
    if not ids:
        return {"diff": None, "lo": None, "hi": None, "n": 0}
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_boot):
        sample = [rng.choice(ids) for _ in ids]
        diffs.append(stat([y[i] for i in sample]) - stat([x[i] for i in sample]))
    diffs.sort()
    lo = diffs[math.floor(0.025 * n_boot)]
    hi = diffs[min(n_boot - 1, math.ceil(0.975 * n_boot) - 1)]
    point = stat([y[i] for i in ids]) - stat([x[i] for i in ids])
    return {"diff": point, "lo": lo, "hi": hi, "n": len(ids)}
