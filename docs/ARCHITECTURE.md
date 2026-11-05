# Architecture and interfaces

This is the contract between modules. If you need to change a signature here,
tell the team first; several people code against it.

## Data flow

```
Example ─► [B] ontology.context_text() + planning.plan_query() ─► QueryPlan
        ─► [C] ambiguity.detect() ─► AmbiguityResult
                 └─ if ambiguous: clarify.make_question() ─► simulated_user.answer() ─► re-plan
        ─► SQL generation (prompts.sql_messages)
        ─► [D] verify.verify() ─► repair_messages() ─► regenerate (max 2)
        ─► Prediction
```

`pipeline.OntologyPipeline.predict()` runs these in order; config A
(`baseline.DirectBaseline`) skips everything except SQL generation.

## Shared types (`code/ontosql/types.py`)

* `Example`: id, db_id, question, gold_sql, kind (`clear`/`ambiguous`),
  source (`spider`/`stress`), ambiguity_type, ambiguous_phrase,
  interpretations (list of `{id, description, sql}`), intended.
* `Prediction`: example_id, config, pred_sql, asked_clarification,
  clarification_question, user_answer, flagged_phrases, n_repairs,
  latency_s, error, trace.
* `Scored`: Example + Prediction + valid + correct + exec_error.

## Module ownership

| Module | Owner | Main functions |
|---|---|---|
| `schema.py`, `db.py` | shared | `extract_schema`, `to_ddl`, `execute` (read-only, timeout) |
| `ontology.py` | Manas | `build_turtle`, `load_ontology`, `Ontology.context_text`, `Ontology.lookup` |
| `planning.py` | Vian | `plan_query` → `QueryPlan`, `QueryPlan.as_text` |
| `ambiguity.py` | Vian | `detect` → `AmbiguityResult` |
| `clarify.py`, `simulated_user.py` | Saniya | `make_question`, `answer` |
| `verify.py` | Vatsal | `verify` → `VerifyResult`, `repair_messages` |
| `pipeline.py` | Vatsal (integration) | `OntologyPipeline`, `make_pipeline` |
| `baseline.py`, `prompts.py`, `llm.py`, `eval/`, `cli.py` | Manav | baseline, metrics, scoring, tables |

## Rules that keep the ablation fair

1. Same model, temperature 0, same questions for A-D.
2. SQL generation always goes through `prompts.sql_messages`; stages add context, they don't rewrite the prompt.
3. All database access goes through `db.execute` (read-only, timeout).
4. The simulated user never sees or returns gold SQL.
5. Every new stage gets a unit test that runs without network access (use `llm.ScriptedModel`).
