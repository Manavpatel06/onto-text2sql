"""Command line entry point.

  python -m ontosql run      --config A [--limit 5]       generate predictions
  python -m ontosql evaluate --config A                   execute + score a run
  python -m ontosql report                                 build result tables
  python -m ontosql errors                                 export wrong answers for labelling
  python -m ontosql check-stress                           validate the stress set file
  python -m ontosql schema   --db <db_id>                  print a database schema
  python -m ontosql build-ontology --db <db_id>            CSV -> Turtle in data/ontology/
  python -m ontosql get-spider [--all]                     download Spider into data/spider/
  python -m ontosql models                                 list chat models for the key in .env
  python -m ontosql demo [--port 7860]                     open the demo page
  python -m ontosql linking                                BM25/TF-IDF vs ontology schema linking (no LLM)

  run options: --user realistic|oracle|wrong, --vague-rate 0.2, --tag NAME, --workers 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .data import load_jsonl, load_spider, load_stress_set, write_jsonl
from .eval.error_analysis import export_errors
from .eval.metrics import summarize
from .eval.report import build_tables, load_runs
from .eval.scoring import load_scored, save_scored, save_summary, score_run
from .llm import load_dotenv
from .types import Prediction

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "spider_dir": ROOT / "data" / "spider",
    "stress": ROOT / "data" / "stress_set" / "stress_set.jsonl",
    "ontology_dir": ROOT / "data" / "ontology",
    "runs_dir": ROOT / "evaluations" / "runs",
    "tables_dir": ROOT / "evaluations" / "tables",
    "dbs_file": ROOT / "data" / "selected_dbs.txt",
}


def selected_dbs(args) -> list[str]:
    if args.dbs:
        return args.dbs.split(",")
    f = Path(DEFAULTS["dbs_file"])
    return [l.strip() for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")]


def load_examples(args) -> list:
    examples = []
    if args.dataset in ("stress", "all"):
        examples += load_stress_set(args.stress)
    if args.dataset in ("spider", "all"):
        examples += load_spider(args.spider_dir, selected_dbs(args), split="dev")
    if args.limit:
        examples = examples[: args.limit]
    return examples


def run_name(args) -> str:
    """Folder name for a run: the config, plus a tag for simulated-user variants (C-oracle, D-vague20)."""
    name = args.config.upper()
    return f"{name}-{args.tag}" if getattr(args, "tag", "") else name


def cmd_run(args) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from .baseline import SchemaCache
    from .llm import OpenAICompatibleModel
    from .pipeline import make_pipeline

    examples = load_examples(args)
    model = OpenAICompatibleModel(model=args.model)
    pipe = make_pipeline(
        args.config, model, SchemaCache(args.spider_dir), args.ontology_dir,
        user_mode=args.user, vague_rate=args.vague_rate, seed=args.seed,
    )
    out_dir = Path(args.runs_dir) / run_name(args)
    done = [0]

    def one(ex):
        p = pipe.predict(ex)
        done[0] += 1
        mark = "!" if p.error else ("?" if p.asked_clarification else ".")
        print(mark, end="" if done[0] % 50 else "\n", flush=True)
        return p

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        preds = list(pool.map(one, examples))  # keeps question order
    print()
    write_jsonl(out_dir / "predictions.jsonl", (p.to_dict() for p in preds))
    (out_dir / "run_info.json").write_text(
        json.dumps(
            {"config": args.config.upper(), "tag": args.tag, "model": model.name, "dataset": args.dataset,
             "n": len(preds), "dbs": selected_dbs(args) if args.dataset != "stress" else None,
             "simulated_user": {"mode": args.user, "vague_rate": args.vague_rate, "seed": args.seed}},
            indent=2,
        )
    )
    print(f"wrote {len(preds)} predictions to {out_dir / 'predictions.jsonl'}")


def cmd_evaluate(args) -> None:
    out_dir = Path(args.runs_dir) / run_name(args)
    preds = [Prediction.from_dict(r) for r in load_jsonl(out_dir / "predictions.jsonl")]
    examples = load_examples(args)
    scored = score_run(examples, preds, args.spider_dir, timeout_s=args.timeout)
    save_scored(out_dir / "scored.jsonl", scored)
    summary = summarize(scored)
    save_summary(out_dir / "summary.json", summary)
    gold_bad = [s.example.id for s in scored if (s.exec_error or "").startswith("GOLD FAILED")]
    if gold_bad:
        print(f"WARNING: gold SQL failed for {len(gold_bad)} items: {gold_bad[:10]}", file=sys.stderr)
    print(json.dumps(summary, indent=2))


def cmd_report(args) -> None:
    summaries = build_tables(args.runs_dir, args.tables_dir)
    print((Path(args.tables_dir) / "main_results.md").read_text())
    print(f"tables written to {args.tables_dir} for configs {', '.join(summaries)}")


def cmd_errors(args) -> None:
    runs = load_runs(args.runs_dir)
    path = Path(args.runs_dir).parent / "error_analysis" / "errors.csv"
    n = export_errors(path, runs)
    print(f"exported {n} rows to {path}; label the 'category' column and save as errors_labelled.csv")


def cmd_check_stress(args) -> None:
    if not Path(args.stress).exists():
        sys.exit(f"{args.stress} not found; see data/stress_set/README.md for the format")
    examples = load_stress_set(args.stress)
    from collections import Counter

    kinds = Counter(e.kind for e in examples)
    types = Counter(e.ambiguity_type for e in examples if e.ambiguity_type)
    print(f"OK: {len(examples)} items, {dict(kinds)}, ambiguity types {dict(types)}")
    if args.execute:
        from .db import ExecutionError, db_path, execute

        bad = 0
        for e in examples:
            sqls = [("gold", e.gold_sql)] + [(i["id"], i["sql"]) for i in e.interpretations]
            for name, sql in sqls:
                try:
                    execute(db_path(args.spider_dir, e.db_id), sql)
                except (ExecutionError, FileNotFoundError) as err:
                    bad += 1
                    print(f"  {e.id} [{name}] fails: {err}")
        print("all SQL executes" if not bad else f"{bad} queries failed")


def cmd_schema(args) -> None:
    from .db import db_path
    from .schema import extract_schema, to_ddl

    print(to_ddl(extract_schema(db_path(args.spider_dir, args.db), args.db)))


def cmd_build_ontology(args) -> None:
    from .db import db_path
    from .ontology import build_turtle
    from .schema import extract_schema

    onto = Path(args.ontology_dir)
    schema = extract_schema(db_path(args.spider_dir, args.db), args.db)
    build_turtle(onto / f"{args.db}.csv", schema, onto / f"{args.db}.ttl")
    print(f"wrote {onto / (args.db + '.ttl')}")


def cmd_get_spider(args) -> None:
    from .spider_download import get_spider

    get_spider(args.spider_dir, keep="all" if args.all else "dev")


def cmd_linking(args) -> None:
    from .db import db_path
    from .ontology import load_ontology
    from .schema import extract_schema
    from .schema_linking import run_ambiguity, run_linking, write_tables

    dbs = selected_dbs(args)
    schemas = {d: extract_schema(db_path(args.spider_dir, d), d) for d in dbs}
    ontos = {d: load_ontology(Path(args.ontology_dir) / f"{d}.ttl", d) for d in dbs}
    spider = load_spider(args.spider_dir, dbs, split="dev")
    stress = load_stress_set(args.stress)
    link = run_linking(spider + stress, schemas.get, ontos.get)
    amb = run_ambiguity(stress, spider, schemas.get, ontos.get)
    print(write_tables(link, amb, args.tables_dir))
    print(f"\ntables written to {args.tables_dir} (schema_linking.*, ambiguity_detection.*)")


def cmd_demo(args) -> None:
    from .demo_server import serve

    serve(port=args.port)


def cmd_models(args) -> None:
    from .llm import list_models

    for m in sorted(list_models(), key=lambda d: d.get("id", "")):
        flags = [k for k in ("supports_response_schema", "reasoning") if m.get(k)]
        ctx = m.get("context_window")
        status = m.get("status") or ""
        print(f"{m.get('id', '?'):40s} ctx={ctx or '?':<8} {' '.join(flags)} {status}".rstrip())


def main(argv=None) -> None:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(prog="ontosql")
    ap.add_argument("--spider-dir", default=DEFAULTS["spider_dir"])
    ap.add_argument("--stress", default=DEFAULTS["stress"])
    ap.add_argument("--ontology-dir", default=DEFAULTS["ontology_dir"])
    ap.add_argument("--runs-dir", default=DEFAULTS["runs_dir"])
    ap.add_argument("--tables-dir", default=DEFAULTS["tables_dir"])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def data_args(p):
        p.add_argument("--dataset", choices=["stress", "spider", "all"], default="stress")
        p.add_argument("--dbs", help="comma-separated db_ids (default: data/selected_dbs.txt)")
        p.add_argument("--limit", type=int, default=0)

    def run_args(p):
        p.add_argument("--tag", default="", help="suffix for the run folder, e.g. oracle -> runs/C-oracle")

    p = sub.add_parser("run")
    p.add_argument("--config", required=True, choices=list("ABCDabcd"))
    p.add_argument("--model", default=None, help="overrides LLM_MODEL")
    p.add_argument("--user", choices=["realistic", "oracle", "wrong"], default="realistic",
                   help="simulated user mode (configs C and D)")
    p.add_argument("--vague-rate", type=float, default=0.0, help="share of uninformative user replies")
    p.add_argument("--seed", type=int, default=0, help="seed for the simulated user's phrasing")
    p.add_argument("--workers", type=int, default=4, help="parallel requests to the model")
    run_args(p)
    data_args(p)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("evaluate")
    p.add_argument("--config", required=True, choices=list("ABCDabcd"))
    p.add_argument("--timeout", type=float, default=10.0)
    run_args(p)
    data_args(p)
    p.set_defaults(fn=cmd_evaluate)

    sub.add_parser("report").set_defaults(fn=cmd_report)

    p = sub.add_parser("linking", help="BM25/TF-IDF vs ontology schema linking and ambiguity detection (no LLM)")
    p.add_argument("--dbs", help="comma-separated db_ids (default: data/selected_dbs.txt)")
    p.set_defaults(fn=cmd_linking)
    sub.add_parser("errors").set_defaults(fn=cmd_errors)

    p = sub.add_parser("check-stress")
    p.add_argument("--execute", action="store_true", help="also run every gold/interpretation query")
    p.set_defaults(fn=cmd_check_stress)

    p = sub.add_parser("schema")
    p.add_argument("--db", required=True)
    p.set_defaults(fn=cmd_schema)

    p = sub.add_parser("get-spider")
    p.add_argument("--all", action="store_true", help="keep all 200 databases (1.8 GB), not just dev")
    p.set_defaults(fn=cmd_get_spider)

    sub.add_parser("models").set_defaults(fn=cmd_models)

    p = sub.add_parser("build-ontology")
    p.add_argument("--db", required=True)
    p.set_defaults(fn=cmd_build_ontology)

    p = sub.add_parser("demo", help="open the config B demo page")
    p.add_argument("--port", type=int, default=7860)
    p.set_defaults(fn=cmd_demo)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
