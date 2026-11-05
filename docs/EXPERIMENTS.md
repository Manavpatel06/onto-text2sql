# Experiment protocol

## Before the final runs

- [ ] `data/selected_dbs.txt` holds the final 2-3 databases
- [ ] `data/ontology/<db_id>.ttl` exists for each of them
- [ ] `ontosql check-stress --execute` passes (about 20 clear + 20 ambiguous, all SQL runs)
- [ ] `pytest` is green
- [ ] `.env` points at the agreed model; write the model name in `evaluations/README.md`

## Runs

```bash
for c in A B C D; do
  ontosql run --config $c
  ontosql evaluate --config $c
done
ontosql report
ontosql errors
```

Also run config A on Spider dev for the selected databases as a sanity check of
the baseline on a larger set:

```bash
ontosql --runs-dir evaluations/runs_spider run --config A --dataset spider
ontosql --runs-dir evaluations/runs_spider evaluate --config A --dataset spider
```

## Error analysis

1. `ontosql errors` writes `evaluations/error_analysis/errors.csv` with a suggested category.
2. Two people label the `category` column independently using:
   `schema_linking, join, aggregation, value_grounding, unresolved_ambiguity,
   unnecessary_clarification, repair_failure, other`.
3. Resolve disagreements, save as `errors_labelled.csv`, rerun `ontosql report`.

## What goes in the report

* `evaluations/tables/main_results.tex`: main table (EX, validity, ambiguity P/R/F1, UCR, CG)
* `evaluations/tables/comparisons.md`: B vs A, C vs B, D vs C with 95% CIs
* `evaluations/tables/by_ambiguity_type.md`: which ambiguity types clarification fixes
* `evaluations/tables/error_categories.md`: why each configuration fails
