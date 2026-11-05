# Evaluations

| Path | Written by | Contents |
|---|---|---|
| `runs/<CONFIG>/predictions.jsonl` | `ontosql run` | One `Prediction` per question |
| `runs/<CONFIG>/run_info.json` | `ontosql run` | Model, dataset, size |
| `runs/<CONFIG>/scored.jsonl` | `ontosql evaluate` | Prediction + validity + correctness |
| `runs/<CONFIG>/summary.json` | `ontosql evaluate` | All metrics for that configuration |
| `tables/` | `ontosql report` | Markdown, LaTeX and CSV tables for the report and slides |
| `error_analysis/errors.csv` | `ontosql errors` | Wrong answers to label by hand |
| `error_analysis/errors_labelled.csv` | team | Labelled copy, read by `ontosql report` |

Model used for the final runs: _fill in_.
