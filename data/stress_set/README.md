# Ambiguity Stress Set

`stress_set.jsonl`, one JSON object per line. Target: 20 clear + 20 ambiguous
questions over the databases in `../selected_dbs.txt`.
`stress_set.example.jsonl` shows the format with three real rows on `dog_kennels`.

## Fields

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Unique, e.g. `dk-amb-07` |
| `db_id` | yes | Spider database id |
| `question` | yes | Natural-language question |
| `gold_sql` | yes | SQL for the intended reading (for clear items: Spider's gold) |
| `kind` | yes | `clear` or `ambiguous` |
| `ambiguity_type` | ambiguous only | `column`, `temporal`, `aggregation` or `reference` |
| `ambiguous_phrase` | ambiguous only | The phrase that causes the ambiguity |
| `interpretations` | ambiguous only | At least 2 objects `{id, description, sql}` |
| `intended` | ambiguous only | `id` of the intended interpretation; its `sql` must equal `gold_sql` |

## Rules

* Clear items: take them from Spider dev for the selected databases, unchanged.
* Ambiguous items: rewrite a clear question so one phrase matches more than one schema element.
  Keep the wording natural. Spread the 20 across the four types (5 each).
* Every interpretation must return a *different* result on the database,
  otherwise the ambiguity cannot change the score.
* Check with `ontosql check-stress --execute` before committing.
