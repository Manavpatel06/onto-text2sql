# Vatsal: verification and repair, ablation runs, integration, demo

## Files you own

* `code/ontosql/verify.py`: `verify()`, `repair_messages()`
* `code/ontosql/pipeline.py`: orchestration for B-D is already wired; you own it from here
* `code/tests/test_verify.py`, `code/tests/test_pipeline.py` (new)
* the demo (any simple UI)

## Part 1: verification (config D)

```python
verify(sql, schema, db_file) -> VerifyResult(ok, stage, message)
repair_messages(question, ddl, bad_sql, result) -> list[dict]
```

Checks in order, stop at first failure:
1. **syntax**: `sqlglot.parse_one(sql, read="sqlite")`; catch `sqlglot.errors.ParseError`.
2. **schema**: collect `exp.Table` and `exp.Column` nodes; every table must
   exist (`schema.table(name)`); every column must exist in one of the
   referenced tables. Resolve aliases (`T1.name` → the table aliased `T1`).
   Ignore select-list aliases and `*`.
3. **execution**: `ontosql.db.execute(db_file, sql)`; catch `ExecutionError`.

`message` should be specific ("column Dogs.date_left does not exist; did you
mean date_departed?" via `difflib.get_close_matches`). `repair_messages` reuses
`prompts.SYSTEM_SQL` and shows schema, question, failed SQL and the error.
`pipeline.py` already loops up to `MAX_REPAIRS = 2`.

## Part 2: integration

`pipeline.OntologyPipeline.predict()` calls everyone's stages in order. Once
Manas, Vian and Saniya merge, run each config with `--limit 3` first. Write an
integration test with `ScriptedModel` and the `shop` fixture covering:
ambiguous question → clarification asked → answer used → SQL; and a bad query
repaired once.

## Part 3: ablation runs

Follow `docs/EXPERIMENTS.md`: run and evaluate A, B, C, D on the stress set,
then `ontosql report`. Same model and temperature for all runs; record the
model in `evaluations/README.md`.

## Part 4: demo (due for the Nov 30 demo session)

Smallest useful version: a Streamlit or plain HTML/Flask page: pick a database,
type a question, see the plan, the clarification question (answer it yourself),
the final SQL and the result table. The course requires the GitHub link on the
last demo slide.

## Done when

* All four configs run end-to-end on the stress set.
* `evaluations/tables/main_results.md` has rows A-D.
* `pytest` green.
