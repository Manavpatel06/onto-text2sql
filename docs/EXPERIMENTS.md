# Experiment protocol

## Before the runs

- [x] `data/selected_dbs.txt` holds the databases (`dog_kennels`, `student_transcripts_tracking`, `wta_1`)
- [x] `data/ontology/<db_id>.ttl` exists for each of them
- [x] `ontosql check-stress --execute` passes (20 clear + 20 ambiguous, all SQL runs)
- [x] `pytest` is green
- [x] `.env` points at the agreed model (`qwen38-27b` on ASU Voyager, temperature 0, `LLM_REASONING_EFFORT=none`)

## Main ablation (stress set)

```bash
for c in A B C D; do
  ontosql run --config $c
  ontosql evaluate --config $c
done
```

## Simulated-user controls

These bound how much of the clarification gain could come from the simulated
user rather than from the system (grader feedback on the proposal):

```bash
ontosql run --config C --user wrong  --tag wrong       # states a reading that was NOT intended
ontosql run --config C --user oracle --tag oracle      # states the intended reading even if no option fits
ontosql run --config C --vague-rate 0.2 --tag vague20  # 20% of replies say nothing useful
ontosql evaluate --config C --tag wrong                 # (same for oracle, vague20)
```

Safeguards built into the realistic simulated user (`code/ontosql/simulated_user.py`):

| Risk | Safeguard |
|---|---|
| Leaking the answer | Replies come from the interpretation's English description or the option's ontology label. A leak check rejects any reply with SQL or a schema identifier and falls back to a reply with no information. |
| Rescuing a bad question | If none of the offered options is the intended reading, the user says "None of those" and adds nothing. |
| Free help on clear questions | If the system asks about a clear question, the reply contains no new information. |
| Formulaic replies | Several phrasings per reply type, picked by a seeded hash of the question id (repeatable, not identical). |
| Over-cooperative user | `--vague-rate` makes a share of replies uninformative. |

## Classical baselines (no LLM)

```bash
ontosql linking
```

Writes `tables/schema_linking.*` (TF-IDF and BM25 over column names, and over
names + ontology labels, against ontology matching; recall@1/3/5 and P/R/F1
against the columns each gold query reads) and `tables/ambiguity_detection.*`
(the ontology rule against a BM25 score-margin detector; also the flag rate
on the 222 clear Spider dev questions, which the rule was not developed on).

## Larger check on Spider dev (222 clear questions)

```bash
for c in A B D; do
  ontosql --runs-dir evaluations/runs_spider run --config $c --dataset spider --workers 6
  ontosql --runs-dir evaluations/runs_spider evaluate --config $c --dataset spider
done
ontosql --runs-dir evaluations/runs_spider --tables-dir evaluations/tables_spider report
```

All Spider dev questions are clear, so for config D this measures how often
the system asks unnecessarily on questions nobody tuned it for.

## Tables and error analysis

```bash
ontosql report    # tables/main_results, comparisons, by_ambiguity_type, simulated_user_controls
ontosql errors    # error_analysis/errors.csv with a suggested category per wrong answer
```

Label the `category` column (`schema_linking, join, aggregation, value_grounding,
unresolved_ambiguity, unnecessary_clarification, repair_failure, other`),
save as `errors_labelled.csv`, and rerun `ontosql report` for `tables/error_categories.*`.

## What goes in the report

* `tables/main_results.tex`: main table (EX, validity, ambiguity P/R/F1, UCR, CG)
* `tables/comparisons.md`: paired differences with 95% bootstrap CIs
* `tables/by_ambiguity_type.md`: which ambiguity types clarification fixes
* `tables/simulated_user_controls.md`: wrong / realistic / vague / oracle
* `tables/schema_linking.md`, `tables/ambiguity_detection.md`: classical baselines
* `tables_spider/main_results.md`: A, B, D on 222 clear Spider questions
* `tables/error_categories.md`: why each configuration fails
