# Ontology-Grounded, Uncertainty-Aware Text2SQL

CSE 573 Semantic Web Mining, Fall 2026, Arizona State University
Group 26, Project 13: Saniya Mulla, Vian Yeh, Manas Khare, Vatsal Patel, Manav

Text-to-SQL systems usually assume the question is precise enough to translate
straight away. Real questions often are not ("show me the orders from last
month" when the table has both `order_date` and `delivery_date`). We ground the
system in a lightweight RDFS + SKOS ontology of each database schema and use it
two ways: as extra context for SQL generation, and as an explicit, interpretable
test for ambiguity. When a phrase maps to more than one schema element, the
system asks a targeted clarification question before writing SQL, then verifies
and repairs the query.

```
question ──► query plan + ontology match ──► ambiguous? ──yes──► clarification ──► simulated user
                                               │ no                                     │
                                               ▼                                        ▼
                                         SQL generation ◄───────────────────────────────┘
                                               │
                                     verify: syntax, schema, execution ──fail──► repair (max 2)
                                               │ pass
                                               ▼
                                        final SQL + result
```

## Repository layout

| Path | What's there |
|---|---|
| `code/ontosql/` | The pipeline package (baseline, stages, evaluation, CLI) |
| `code/tests/` | Unit and end-to-end tests on a small fixture database |
| `data/` | Spider download location, selected databases, ontology files, Ambiguity Stress Set |
| `evaluations/` | Run outputs, scored predictions, result tables, error analysis |
| `docs/` | Architecture, experiment protocol, per-member work packages |

## Ablation configurations

| Config | Ontology context | Clarification | Verification |
|---|---|---|---|
| A. Direct baseline | | | |
| B. + Ontology context | ✓ | | |
| C. + Clarification | ✓ | ✓ | |
| D. Full system | ✓ | ✓ | ✓ |

All configurations use the same model, temperature 0 and the same questions.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
ontosql get-spider                      # downloads Spider, keeps the dev split (~130 MB)
copy .env.example .env                  # macOS/Linux: cp; then paste your Voyager key
ontosql models                          # check which models your key can use
pytest                                  # should be all green
```

## Running experiments

```bash
ontosql run --config A                       # predictions -> evaluations/runs/A/predictions.jsonl
ontosql evaluate --config A                  # execute + score -> scored.jsonl, summary.json
ontosql report                               # tables -> evaluations/tables/
ontosql errors                               # wrong answers -> evaluations/error_analysis/errors.csv
```

Useful flags: `--dataset stress|spider|all` (default `stress`), `--limit 5` for a
quick smoke test, `--dbs dog_kennels,wta_1` to override `data/selected_dbs.txt`.
Model replies are cached in `.cache/llm/`, so re-running a configuration costs nothing.

Other commands: `ontosql check-stress --execute` validates the stress set and
runs every gold and interpretation query; `ontosql schema --db dog_kennels`
prints a schema.

## Metrics

| Metric | Definition |
|---|---|
| Execution Accuracy (EX) | Share of questions whose SQL returns the gold result; reported for clear and ambiguous questions separately |
| SQL Validity Rate | Share of generated queries that parse and execute |
| Ambiguity detection | Precision, recall and F1 of the clarification flag on the stress set |
| Unnecessary Clarification Rate (UCR) | Share of the clear stress-set questions where the system still asks |
| Clarification Gain (CG) | EX(C) minus EX(B) on ambiguous questions |

Result comparisons are reported with 95% paired-bootstrap confidence intervals,
since the stress set is small (about 40 questions).

## Status

| Component | Owner | Status |
|---|---|---|
| Direct baseline (A), evaluation pipeline, result tables | Manav | Done, tested |
| Database selection, schema extraction, ontology spreadsheet, Turtle conversion | Manas | Interface in place |
| Ontology-grounded query planning, ambiguity detection | Vian | Interface in place |
| Ambiguity Stress Set, clarification prompts, simulated user | Saniya | Format + examples in place |
| Verification and repair, ablation runs, integration, demo | Vatsal | Orchestration wired, checks to do |

Each member's work package, with interfaces and acceptance checks, is in `docs/team/`.

## Data

Spider 1.0 (Yu et al., EMNLP 2018) is distributed under CC BY-SA 4.0 and is not
committed here; `ontosql get-spider` downloads it.
