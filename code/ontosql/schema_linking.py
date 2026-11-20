"""Classical schema-linking baselines vs. ontology matching.

Grader feedback on the proposal asked for a classical retrieval baseline
(TF-IDF or BM25) for schema linking, compared quantitatively against the
Semantic Web ontology matching. This module does that comparison without any
LLM calls:

  * gold columns are read from each gold SQL query (join keys used only in
    ON conditions are left out, since no question names them);
  * each column is a short document. "names" documents hold only the table
    and column identifiers split into words; "names + ontology" documents add
    the SKOS preferred/alternative labels and the definition;
  * BM25 and TF-IDF rank all columns of the database for the question;
  * ontology matching links the question's phrases to columns through the
    SKOS labels (ambiguity.detect), keeping the candidates left after the
    context rules.

Also compares ambiguity detection: the ontology rule against a classical
"score margin" detector (flag a question when BM25's top two columns score
within tau of each other).
"""

from __future__ import annotations

import csv
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import sqlglot
from sqlglot import exp

from .ambiguity import _STOP, detect, split_identifier, stem, words
from .ontology import Ontology
from .schema import Schema
from .types import AMBIGUOUS, Example

K_VALUES = (1, 3, 5)
SET_K = 3  # ranked methods are scored as a set using their top-3 columns
TAUS = (0.05, 0.1, 0.2, 0.3)


# ---------------------------------------------------------------- gold columns

def gold_columns(sql: str, schema: Schema) -> set[str]:
    """Columns a gold query reads, as "Table.column" keys (join-only keys excluded)."""
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return set()
    alias: dict[str, str] = {}
    used: list[str] = []
    for t in tree.find_all(exp.Table):
        real = schema.table(t.name)
        if real is None:
            continue
        used.append(real.name)
        alias[(t.alias or t.name).lower()] = real.name
        alias[t.name.lower()] = real.name
    join_only: set[int] = set()
    for j in tree.find_all(exp.Join):
        on = j.args.get("on")
        if on is not None:
            join_only |= {id(c) for c in on.find_all(exp.Column)}
    out: set[str] = set()
    for col in tree.find_all(exp.Column):
        if id(col) in join_only or not col.name or col.name == "*":
            continue
        tables = [alias[col.table.lower()]] if col.table and col.table.lower() in alias else sorted(set(used))
        for t in tables:
            real = schema.table(t)
            if real is None:
                continue
            match = next((c.name for c in real.columns if c.name.lower() == col.name.lower()), None)
            if match:
                out.add(f"{real.name}.{match}")
                break
    return out


# ---------------------------------------------------------------- retrieval

def tokens(text: str) -> list[str]:
    return [stem(w) for w in words(text) if w not in _STOP or w in ("date", "name", "code", "description")]


def column_docs(schema: Schema, ontology: Ontology | None) -> dict[str, list[str]]:
    by_key = {e.key: e for e in ontology.entries} if ontology else {}
    table_label = {e.table: e for e in ontology.entries if not e.column} if ontology else {}
    docs = {}
    for t in schema.tables:
        for c in t.columns:
            key = f"{t.name}.{c.name}"
            text = " ".join(split_identifier(t.name) + split_identifier(c.name))
            e = by_key.get(key)
            if e is not None:
                text += " " + " ".join([e.pref_label, *e.alt_labels, e.definition])
            te = table_label.get(t.name)
            if te is not None:
                text += " " + " ".join([te.pref_label, *te.alt_labels])
            docs[key] = tokens(text)
    return docs


class BM25:
    def __init__(self, docs: dict[str, list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.docs, self.k1, self.b = docs, k1, b
        self.avgdl = sum(len(d) for d in docs.values()) / max(1, len(docs))
        df = Counter(t for d in docs.values() for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = {k: Counter(d) for k, d in docs.items()}

    def scores(self, query: list[str]) -> dict[str, float]:
        out = {}
        for k, d in self.docs.items():
            tf, dl, s = self.tf[k], len(d), 0.0
            for q in query:
                if q in tf:
                    f = tf[q]
                    s += self.idf[q] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out[k] = s
        return out


class TFIDF:
    def __init__(self, docs: dict[str, list[str]]) -> None:
        n = len(docs)
        df = Counter(t for d in docs.values() for t in set(d))
        self.idf = {t: math.log((1 + n) / (1 + f)) + 1 for t, f in df.items()}
        self.vecs = {k: self._vec(d) for k, d in docs.items()}

    def _vec(self, toks: list[str]) -> dict[str, float]:
        tf = Counter(toks)
        v = {t: c * self.idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def scores(self, query: list[str]) -> dict[str, float]:
        q = self._vec(query)
        return {k: sum(w * v.get(t, 0.0) for t, w in q.items()) for k, v in self.vecs.items()}


def ranked(scores: dict[str, float]) -> list[str]:
    return [k for k, s in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0])) if s > 0]


def ontology_links(question: str, ontology: Ontology) -> list[str]:
    """Columns the ontology matching links the question to (after the context rules), in question order."""
    res = detect(question, None, ontology)
    out: list[str] = []
    for keys in res.resolved.values():
        for k in keys:
            if k not in out and not k.startswith("AGG."):
                out.append(k)
    return out


# ---------------------------------------------------------------- evaluation

@dataclass
class LinkScores:
    n: int
    recall_at: dict[int, float]
    precision: float
    recall: float
    f1: float


def _prf(pred: set[str], gold: set[str]) -> tuple[float, float]:
    tp = len(pred & gold)
    return (tp / len(pred) if pred else 0.0), (tp / len(gold) if gold else 0.0)


def score_method(items: Sequence[tuple[list[str], set[str]]], set_from_rank: bool) -> LinkScores:
    """items: (ranked or linked columns, gold columns) per question with non-empty gold."""
    rec_at = {k: 0.0 for k in K_VALUES}
    ps, rs = [], []
    for pred, gold in items:
        for k in K_VALUES:
            rec_at[k] += len(set(pred[:k]) & gold) / len(gold)
        chosen = set(pred[:SET_K]) if set_from_rank else set(pred)
        p, r = _prf(chosen, gold)
        ps.append(p)
        rs.append(r)
    n = len(items)
    P, R = sum(ps) / n, sum(rs) / n
    return LinkScores(n, {k: v / n for k, v in rec_at.items()}, P, R, 2 * P * R / (P + R) if P + R else 0.0)


METHODS: list[tuple[str, str, bool]] = [
    # (name, documents, scored as top-k set?)
    ("TF-IDF, column names", "names", True),
    ("BM25, column names", "names", True),
    ("TF-IDF, names + ontology labels", "onto", True),
    ("BM25, names + ontology labels", "onto", True),
    ("Ontology matching (SKOS labels + context rules)", "match", False),
]


def run_linking(
    examples: Iterable[Example],
    schema_for: Callable[[str], Schema],
    ontology_for: Callable[[str], Ontology],
) -> dict[str, dict[str, LinkScores]]:
    """Scores per dataset ("spider", "stress", "all") per method."""
    per_set: dict[str, dict[str, list]] = {}
    indexes: dict[tuple[str, str], object] = {}
    for ex in examples:
        schema, onto = schema_for(ex.db_id), ontology_for(ex.db_id)
        gold = gold_columns(ex.gold_sql, schema)
        if not gold:
            continue
        q = tokens(ex.question)
        for name, docs, _ in METHODS:
            if docs == "match":
                pred = ontology_links(ex.question, onto)
            else:
                key = (ex.db_id, name)
                if key not in indexes:
                    d = column_docs(schema, onto if docs == "onto" else None)
                    indexes[key] = BM25(d) if name.startswith("BM25") else TFIDF(d)
                pred = ranked(indexes[key].scores(q))
            for split in (ex.source, "all"):
                per_set.setdefault(split, {}).setdefault(name, []).append((pred, gold))
    out: dict[str, dict[str, LinkScores]] = {}
    for split, by_method in per_set.items():
        out[split] = {
            name: score_method(by_method[name], set_from_rank) for name, _, set_from_rank in METHODS if name in by_method
        }
    return out


def margin_flag(question: str, index: BM25, tau: float) -> bool:
    """Classical ambiguity detector: top two BM25 columns score within tau of each other."""
    r = sorted(index.scores(tokens(question)).values(), reverse=True)
    if len(r) < 2 or r[0] <= 0:
        return False
    return r[1] >= (1 - tau) * r[0]


def run_ambiguity(
    stress: Sequence[Example],
    clear_extra: Sequence[Example],
    schema_for: Callable[[str], Schema],
    ontology_for: Callable[[str], Ontology],
) -> list[dict]:
    """Ambiguity detection on the stress set, plus the flag rate on extra clear questions."""
    idx: dict[str, BM25] = {}

    def bm25(db: str) -> BM25:
        if db not in idx:
            idx[db] = BM25(column_docs(schema_for(db), ontology_for(db)))
        return idx[db]

    detectors: list[tuple[str, Callable[[Example], bool]]] = [
        ("Ontology rule (SKOS labels + context)", lambda e: detect(e.question, None, ontology_for(e.db_id)).is_ambiguous)
    ]
    for tau in TAUS:
        detectors.append((f"BM25 score margin, tau={tau}", lambda e, t=tau: margin_flag(e.question, bm25(e.db_id), t)))

    rows = []
    for name, fn in detectors:
        tp = sum(1 for e in stress if e.kind == AMBIGUOUS and fn(e))
        fp = sum(1 for e in stress if e.kind != AMBIGUOUS and fn(e))
        fn_ = sum(1 for e in stress if e.kind == AMBIGUOUS and not fn(e))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn_) if tp + fn_ else 0.0
        extra = sum(1 for e in clear_extra if fn(e)) / len(clear_extra) if clear_extra else None
        rows.append({"detector": name, "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
                     "tp": tp, "fp": fp, "fn": fn_, "spider_flag_rate": extra})
    return rows


# ---------------------------------------------------------------- tables

def _pct(x) -> str:
    return "-" if x is None else f"{100 * x:.1f}"


def write_tables(link: dict[str, dict[str, LinkScores]], amb: list[dict], out_dir: str | Path) -> str:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    headers = ["Questions", "Method", "n", "R@1", "R@3", "R@5", "P", "R", "F1"]
    rows = []
    for split in ("spider", "stress", "all"):
        for name, s in link.get(split, {}).items():
            rows.append([split, name, str(s.n), *(_pct(s.recall_at[k]) for k in K_VALUES), _pct(s.precision), _pct(s.recall), _pct(s.f1)])
    md = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    note = (
        f"\nR@k: share of gold columns in the top k. P/R/F1: ranked methods use their top {SET_K} columns; "
        "ontology matching uses the columns it links. Join keys used only in ON conditions are excluded from the gold columns.\n"
    )
    (out / "schema_linking.md").write_text("\n".join(md) + "\n" + note)
    with (out / "schema_linking.csv").open("w", newline="") as f:
        csv.writer(f).writerows([headers, *rows])

    h2 = ["Detector", "P", "R", "F1", "TP", "FP", "FN", "Flag rate on clear Spider dev"]
    r2 = [[a["detector"], _pct(a["precision"]), _pct(a["recall"]), _pct(a["f1"]), str(a["tp"]), str(a["fp"]),
           str(a["fn"]), _pct(a["spider_flag_rate"])] for a in amb]
    md2 = ["| " + " | ".join(h2) + " |", "|" + "---|" * len(h2)] + ["| " + " | ".join(r) + " |" for r in r2]
    note2 = (
        "\nStress set: 20 ambiguous, 20 clear. The last column is the share of the 222 Spider dev questions "
        "on the same databases (all clear) that each detector flags, i.e. unnecessary clarifications on unseen questions. "
        "The ontology rule was developed while building the stress set, so its stress-set scores are optimistic; "
        "the Spider column is the out-of-sample check.\n"
    )
    (out / "ambiguity_detection.md").write_text("\n".join(md2) + "\n" + note2)
    with (out / "ambiguity_detection.csv").open("w", newline="") as f:
        csv.writer(f).writerows([h2, *r2])
    return "\n".join(md) + "\n\n" + "\n".join(md2)
