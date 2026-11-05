"""Result tables for the report and slides.

Reads evaluations/runs/<CONFIG>/scored.jsonl for every configuration that has
been run and writes, to evaluations/tables/:

  main_results.{md,tex,csv}     one row per configuration (proposal Table I/II)
  by_ambiguity_type.{md,csv}    EX on ambiguous questions per ambiguity type
  comparisons.{md,csv}          paired differences with 95% bootstrap CIs (B-A, C-B, D-C)
  error_categories.{md,csv}     counts from the hand-labelled error sheet, if filled in
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from ..types import AMBIGUOUS
from .metrics import clarification_gain, paired_bootstrap, summarize
from .scoring import load_scored

CONFIG_NAMES = {
    "A": "Direct baseline",
    "B": "+ Ontology context",
    "C": "+ Clarification",
    "D": "Full system (+ Verify)",
}
MAIN_COLS = [
    ("ex", "EX"),
    ("ex_clear", "EX (clear)"),
    ("ex_ambiguous", "EX (ambig.)"),
    ("validity", "Validity"),
    ("amb_precision", "Amb. P"),
    ("amb_recall", "Amb. R"),
    ("amb_f1", "Amb. F1"),
    ("ucr", "UCR"),
]


def _fmt(v: Optional[float], pct: bool = True) -> str:
    if v is None:
        return "-"
    return f"{100 * v:.1f}" if pct else f"{v:.3f}"


def _md(headers: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join([line, sep, *body]) + "\n"


def _tex(headers: list[str], rows: list[list[str]], caption: str, label: str) -> str:
    cols = "l" + "c" * (len(headers) - 1)
    esc = lambda s: s.replace("%", r"\%").replace("&", r"\&").replace("+", "+")
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\small",
        rf"\begin{{tabular}}{{{cols}}}",
        r"\hline",
        " & ".join(esc(h) for h in headers) + r" \\",
        r"\hline",
        *[" & ".join(esc(c) for c in r) + r" \\" for r in rows],
        r"\hline",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines) + "\n"


def _csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def load_runs(runs_dir: str | Path) -> dict:
    runs = {}
    for cfg in sorted(CONFIG_NAMES):
        f = Path(runs_dir) / cfg / "scored.jsonl"
        if f.exists():
            runs[cfg] = load_scored(f)
    return runs


def build_tables(runs_dir: str | Path, out_dir: str | Path) -> dict:
    runs = load_runs(runs_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if not runs:
        raise FileNotFoundError(f"no runs found under {runs_dir}")

    # main results
    headers = ["System"] + [h for _, h in MAIN_COLS] + ["CG"]
    rows, summaries = [], {}
    for cfg, scored in runs.items():
        s = summarize(scored)
        summaries[cfg] = s
        cg = clarification_gain(runs["B"], scored) if cfg in ("C", "D") and "B" in runs else None
        rows.append(
            [f"{cfg}. {CONFIG_NAMES[cfg]}"] + [_fmt(s[k]) for k, _ in MAIN_COLS] + [_fmt(cg)]
        )
    (out / "main_results.md").write_text(_md(headers, rows))
    (out / "main_results.tex").write_text(
        _tex(headers, rows, "Main results on the Ambiguity Stress Set (\\%).", "tab:main")
    )
    _csv(out / "main_results.csv", headers, rows)

    # EX by ambiguity type
    types = sorted(
        {s.example.ambiguity_type for r in runs.values() for s in r if s.example.kind == AMBIGUOUS}
        - {None}
    )
    if types:
        h2 = ["System"] + [t.capitalize() for t in types]
        r2 = []
        for cfg, scored in runs.items():
            by_t = defaultdict(list)
            for s in scored:
                if s.example.kind == AMBIGUOUS:
                    by_t[s.example.ambiguity_type].append(s.correct)
            r2.append(
                [f"{cfg}. {CONFIG_NAMES[cfg]}"]
                + [_fmt(sum(by_t[t]) / len(by_t[t]) if by_t[t] else None) for t in types]
            )
        (out / "by_ambiguity_type.md").write_text(_md(h2, r2))
        _csv(out / "by_ambiguity_type.csv", h2, r2)

    # paired comparisons
    h3 = ["Comparison", "n", "EX diff", "95% CI"]
    r3 = []
    for x, y in (("A", "B"), ("B", "C"), ("C", "D"), ("A", "D")):
        if x in runs and y in runs:
            bs = paired_bootstrap(runs[x], runs[y])
            if bs["diff"] is not None:
                r3.append(
                    [f"{y} vs {x}", str(bs["n"]), _fmt(bs["diff"]), f"[{_fmt(bs['lo'])}, {_fmt(bs['hi'])}]"]
                )
    if r3:
        (out / "comparisons.md").write_text(_md(h3, r3))
        _csv(out / "comparisons.csv", h3, r3)

    # error categories (from hand-labelled sheets)
    sheet = Path(runs_dir).parent / "error_analysis" / "errors_labelled.csv"
    if sheet.exists():
        counts: dict[str, Counter] = defaultdict(Counter)
        with sheet.open() as f:
            for r in csv.DictReader(f):
                if r.get("category"):
                    counts[r["config"]][r["category"].strip()] += 1
        cats = sorted({c for v in counts.values() for c in v})
        h4 = ["System"] + cats
        r4 = [[cfg] + [str(counts[cfg][c]) for c in cats] for cfg in sorted(counts)]
        (out / "error_categories.md").write_text(_md(h4, r4))
        _csv(out / "error_categories.csv", h4, r4)

    return summaries
