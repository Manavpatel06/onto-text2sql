# Data

| Path | Contents | Committed? |
|---|---|---|
| `spider/` | Spider 1.0 (dev.json, tables.json, database/*.sqlite). Get it with `ontosql get-spider`. | No (gitignored, ~130 MB dev split) |
| `selected_dbs.txt` | The 2-3 Spider databases used in the experiments, one per line | Yes |
| `ontology/` | `<db_id>.csv` spreadsheets and generated `<db_id>.ttl` ontologies | Yes |
| `stress_set/` | The Ambiguity Stress Set (`stress_set.jsonl`) | Yes |

## Database selection

Current provisional choice (all in Spider dev, chosen because they have
several easily confused columns):

| db_id | Dev questions | Tables | Why |
|---|---|---|---|
| `dog_kennels` | 82 | 8 | Five date columns (`date_arrived`, `date_adopted`, `date_departed`, `date_of_birth`, `date_of_treatment`); owners and professionals share name and address columns |
| `student_transcripts_tracking` | 78 | 11 | Several dates (`date_first_registered`, `date_left`, `transcript_date`); repeated `other_details` columns |
| `wta_1` | 62 | 3 | Paired columns (`winner_*` / `loser_*`), several dates (`tourney_date`, `birth_date`, `ranking_date`) |

Gold SQL for all 222 dev questions on these databases executes cleanly with our evaluator.
