# Evaluations

| Path | Written by | Contents |
|---|---|---|
| `runs/<CONFIG>/predictions.jsonl` | `ontosql run` | One `Prediction` per question (stress set). Tagged folders such as `C-oracle`, `C-wrong`, `C-vague20` are simulated-user controls |
| `runs_spider/<CONFIG>/` | `ontosql --runs-dir evaluations/runs_spider ...` | The same files for the 222 Spider dev questions |
| `runs/<CONFIG>/run_info.json` | `ontosql run` | Model, dataset, size |
| `runs/<CONFIG>/scored.jsonl` | `ontosql evaluate` | Prediction + validity + correctness |
| `runs/<CONFIG>/summary.json` | `ontosql evaluate` | All metrics for that configuration |
| `tables/` | `ontosql report`, `ontosql linking` | Markdown, LaTeX and CSV tables for the report and slides |
| `tables_spider/` | `ontosql report` on `runs_spider` | Tables for the Spider dev runs |
| `error_analysis/errors.csv` | `ontosql errors` | Wrong answers to label by hand |
| `error_analysis/errors_labelled.csv` | team | Labelled copy, read by `ontosql report` |

Model used for all runs: `qwen38-27b` on ASU Voyager (https://openai.rc.asu.edu/v1), temperature 0,
`LLM_REASONING_EFFORT=none`. Model replies are cached in `.cache/llm/` (not committed), so reruns on the same machine are exact.
