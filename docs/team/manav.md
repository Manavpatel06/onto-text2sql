# Manav: direct baseline, evaluation pipeline, result tables

## Status: implemented and tested

| File | What it does |
|---|---|
| `code/ontosql/baseline.py` | Config A: schema DDL + question → one SQL query |
| `code/ontosql/prompts.py` | Shared generation prompt and robust SQL extraction from model output |
| `code/ontosql/llm.py` | OpenAI-compatible client (Voyager), disk cache, `ScriptedModel` for tests |
| `code/ontosql/db.py`, `schema.py` | Read-only execution with timeout; schema extraction and DDL |
| `code/ontosql/data.py` | Spider and stress-set loaders, stress-set validation |
| `code/ontosql/eval/exec_match.py` | Execution match (multiset or ordered, column-permutation tolerant, numeric normalization) |
| `code/ontosql/eval/metrics.py` | EX (all/clear/ambiguous), validity, ambiguity P/R/F1, UCR, CG, paired bootstrap |
| `code/ontosql/eval/scoring.py` | Execute predictions, save/load scored runs |
| `code/ontosql/eval/report.py` | Main table (md/tex/csv), per-type table, CI comparisons, error categories |
| `code/ontosql/eval/error_analysis.py` | Export wrong answers with a suggested category for hand labelling |
| `code/ontosql/cli.py` | `run`, `evaluate`, `report`, `errors`, `check-stress`, `schema`, `build-ontology` |

Verified: 21 tests pass; gold SQL for all 222 Spider dev questions on the three
provisional databases scores EX = 100% through the evaluator; a full
`run → evaluate → report → errors` cycle works against an OpenAI-compatible endpoint.

## Remaining steps

1. Get a Voyager API key (https://docs.rc.asu.edu/ai/api/), put it in `.env`, pick the model with the team.
2. Smoke test: `ontosql run --config A --dataset spider --limit 5` then `ontosql evaluate --config A --dataset spider --limit 5`.
3. Baseline on Spider dev for the selected DBs (sanity number for the slides):
   `ontosql --runs-dir evaluations/runs_spider run --config A --dataset spider` and `evaluate`.
4. When Saniya's stress set lands: `ontosql run --config A`, `evaluate`, `report`.
5. After Vatsal's ablation runs: `ontosql report` and `ontosql errors`; coordinate error labelling.
6. Put `evaluations/tables/*.tex` into the final report.

## Acceptance checks

* `pytest` green.
* `evaluations/tables/main_results.md` has one row per configuration that has been run.
* No `GOLD FAILED` warnings during `evaluate`.
