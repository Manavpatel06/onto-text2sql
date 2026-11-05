import csv
import json

import pytest

from ontosql.data import load_stress_set, validate_stress_item, write_jsonl
from ontosql.eval.error_analysis import export_errors
from ontosql.eval.metrics import ambiguity_prf, clarification_gain, paired_bootstrap, summarize
from ontosql.eval.report import build_tables
from ontosql.eval.scoring import load_scored, save_scored, score_run
from ontosql.types import Prediction


def _preds(cfg, sqls, asked=()):
    return [
        Prediction(example_id=i, config=cfg, pred_sql=s, asked_clarification=i in asked)
        for i, s in sqls.items()
    ]


GOOD = {
    "c1": "SELECT count(*) FROM customers",
    "c2": "SELECT name FROM customers WHERE city = 'Tempe'",
    "a1": "SELECT order_id FROM orders WHERE order_date LIKE '2026-10%'",
    "a2": "SELECT customer_id, sum(amount) FROM orders GROUP BY customer_id",
}
# config B guesses the wrong reading on both ambiguous questions
B_SQL = {**GOOD,
         "a1": "SELECT order_id FROM orders WHERE delivery_date LIKE '2026-10%'",
         "a2": "SELECT customer_id, count(*) FROM orders GROUP BY customer_id"}


def test_summary_and_ambiguity_metrics(spider_dir, examples):
    # C asks on both ambiguous items (correct) and on c2 (unnecessary)
    preds = _preds("C", GOOD, asked={"a1", "a2", "c2"})
    s = summarize(score_run(examples, preds, spider_dir))
    assert s["ex"] == 1.0 and s["validity"] == 1.0
    assert s["amb_recall"] == 1.0
    assert s["amb_precision"] == pytest.approx(2 / 3)
    assert s["ucr"] == 0.5


def test_invalid_and_missing_sql(spider_dir, examples):
    preds = _preds("A", {**GOOD, "c1": "SELEC count(*)", "c2": ""})
    scored = score_run(examples, preds, spider_dir)
    s = summarize(scored)
    assert s["validity"] == 0.5 and s["ex"] == 0.5
    assert s["ex_clear"] == 0.0 and s["ex_ambiguous"] == 1.0


def test_no_clarification_means_undefined_precision(spider_dir, examples):
    prf = ambiguity_prf(score_run(examples, _preds("B", B_SQL), spider_dir))
    assert prf.precision is None and prf.recall == 0.0 and prf.fn == 2


def test_clarification_gain_and_bootstrap(spider_dir, examples):
    b = score_run(examples, _preds("B", B_SQL), spider_dir)
    c = score_run(examples, _preds("C", GOOD, asked={"a1", "a2"}), spider_dir)
    assert clarification_gain(b, c) == 1.0
    bs = paired_bootstrap(b, c, n_boot=500)
    assert bs["diff"] == 0.5 and bs["n"] == 4
    assert bs["lo"] <= bs["diff"] <= bs["hi"]


def test_scored_roundtrip_and_report(tmp_path, spider_dir, examples):
    runs = tmp_path / "evaluations" / "runs"
    for cfg, sql, asked in (("A", B_SQL, ()), ("B", B_SQL, ()), ("C", GOOD, {"a1", "a2"})):
        scored = score_run(examples, _preds(cfg, sql, asked), spider_dir)
        save_scored(runs / cfg / "scored.jsonl", scored)
    assert load_scored(runs / "C" / "scored.jsonl")[2].example.interpretations[0]["id"] == "placed"

    tables = tmp_path / "evaluations" / "tables"
    summaries = build_tables(runs, tables)
    assert set(summaries) == {"A", "B", "C"}
    main = (tables / "main_results.md").read_text()
    assert "C. + Clarification" in main and "100.0" in main
    assert "\\begin{tabular}" in (tables / "main_results.tex").read_text()
    assert "Temporal" in (tables / "by_ambiguity_type.md").read_text()
    assert "C vs B" in (tables / "comparisons.md").read_text()

    from ontosql.eval.report import load_runs

    n = export_errors(tmp_path / "evaluations" / "error_analysis" / "errors.csv", load_runs(runs))
    assert n == 4  # A and B each miss both ambiguous questions
    rows = list(csv.DictReader((tmp_path / "evaluations" / "error_analysis" / "errors.csv").open()))
    assert rows[0]["suggested"] == "unresolved_ambiguity"


def test_stress_set_validation(tmp_path, examples):
    good = [e.to_dict() for e in examples]
    path = tmp_path / "stress.jsonl"
    write_jsonl(path, good)
    assert len(load_stress_set(path)) == 4

    bad = dict(good[2], intended="nope", ambiguity_type="vibes")
    problems = validate_stress_item(bad)
    assert any("intended" in p for p in problems)
    assert any("ambiguity_type" in p for p in problems)
    write_jsonl(path, [bad])
    with pytest.raises(ValueError):
        load_stress_set(path)
