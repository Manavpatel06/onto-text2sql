# Ontology-Grounded, Uncertainty-Aware Text2SQL

CSE 573 Semantic Web Mining, Fall 2026, Arizona State University
Group 26, Project 13: Saniya Mulla, Vian Yeh, Manas Khare, Vatsal Patel, Manav

Text-to-SQL lets someone ask a relational database a question in ordinary language and get an SQL query back. Large language models write that SQL well when the question is precise and the column names already say what they mean. Real questions often fail one of those conditions. A name like `amt_2` or `dt_close` does not say what is stored there, and a phrase like "from March 2018" can point at more than one date column. The query that comes back can run and still answer a different question from the one the person asked.

This project treats that as a decision under uncertainty. Each database gets a small Semantic Web ontology, written in RDFS and SKOS, that gives every table and column a label, synonyms, and a definition. The ontology is used twice. It is extra context when the model writes SQL, and it is an explicit test for ambiguity: if a phrase in the question matches more than one schema element, and nothing else in the question settles which one, the system should ask one clarification question before it writes SQL. A later check then tests the query for syntax, schema, and execution errors and repairs it at most twice.

The decision rule is

```
U(q, S, O) = number of phrases in q that the ontology maps to more than one schema element

if U = 0:  write SQL
if U > 0:  ask one clarification, append the answer, then write SQL
```

`U` is a count, not a learned confidence score. The reason a question was flagged can be read off the ontology.

## Where earlier methods stop

Most Text-to-SQL work assumes one intended query can be read off the question, and it leaves the meaning of the schema inside the column names.

| Line of work | What it does well | What it leaves open |
|---|---|---|
| Schema-aware parsers (Seq2SQL, SQLNet, RAT-SQL) | Encode tables, columns, and the links between question tokens and the schema | The names themselves stay unexplained. `date_adopted` and `date_departed` are just two different strings. |
| Intermediate forms and constrained decoding (IRNet / SemQL, PICARD) | Plan first, then reject SQL that would be invalid | A query can be valid and still be the wrong reading of the question. |
| Staged LLM pipelines (DIN-SQL) | Split linking, decomposition, generation, and self-correction into prompts | Self-correction repairs a broken query. It does not decide that the question was too vague to answer. |
| Conversational benchmarks (SParC, CoSQL) | Study follow-up questions across turns | They do not decide, for a single question, whether the system should ask before it answers. |

The shared gap is that no method pairs an explicit schema ontology with a rule for when to ask. Without the ontology, the model has to guess what a column means. Without the rule, it has to guess even when two columns are equally plausible, and the guess comes back as SQL that executes.

## How this method uses the ontology

The ontology is a spreadsheet the team fills in, one row per column: a preferred label, synonyms separated by `|`, and a one-line definition. A short script turns that sheet into Turtle. Tables become classes, columns become properties, and foreign keys become relationships between classes. Shared synonyms are written only where a person could honestly mean either column. On `dog_kennels`, both `date_adopted` and `date_departed` carry the synonym `date`, and each keeps its own definition.

That one fact does two jobs.

- **Context.** Config B pastes the labels, synonyms, and definitions into the SQL prompt, next to the usual `CREATE TABLE` text. The model sees "adoption date" and "Date the dog was adopted by an owner" instead of only `date_adopted`.
- **Ambiguity test.** `lookup("date")` returns every column that lists `date`. Two or more hits means the phrase is ambiguous. `lookup("adoption date")` returns one column, so that phrase is settled. The clarification question, when it is asked, is built from those definitions: "By 'from March 2018', do you mean the date the dog was adopted, or the date it left the kennel?"

A clear question never takes that branch. The ontology still supplies the meanings, a query plan records the tables, filters, and phrases, and SQL is written in one pass. That is the path the demo below runs.

## Architecture

The full pipeline from the project proposal. A clear question goes straight from the plan to SQL. An ambiguous question takes one clarification, answered in the experiments by a simulated user who never sees the gold SQL. Every generated query is checked, and a failing query is repaired at most twice.

![Architecture of the ontology-grounded Text-to-SQL system. A natural-language question goes to query planning and ontology matching. If the question is ambiguous, the system asks a clarification, a simulated user answers, and the plan is rebuilt. SQL is then generated and checked for syntax, schema, and execution. A failure is repaired at most twice. A passing query is the final SQL and result.](docs/figures/architecture.png)

Each stage can be switched off, so a gain can be tied to the stage that produced it. Every configuration uses the same model, temperature 0, the same questions, and the same SQL prompt. Stages add context. They do not rewrite the prompt.

| Config | Ontology context | Clarification | Verification | What it answers |
|---|---|---|---|---|
| A. Direct baseline | | | | Schema DDL and the question only |
| B. + Ontology | yes | | | Do labels, definitions, and a plan raise accuracy on their own? |
| C. + Clarification | yes | yes | | Can ontology matching find ambiguous questions, and does one question fix them without interrupting clear ones? |
| D. Full system | yes | yes | yes | Do syntax, schema, and execution checks add anything through self-repair? |

## Demo

`ontosql demo` opens a local page for config B, the path a clear question takes. Pick a database and the ontology spreadsheet for that database loads. The sample questions are the clear items from the stress set. Run one and the page shows the spreadsheet rows the plan used, the plan, the SQL, and the result table.

The question in these shots is "Which states have both owners and professionals living there?" on `dog_kennels`. The plan names `Owners.state` and `Professionals.state`. The SQL joins the two tables on state. The result is Wisconsin, Indiana, and Mississippi, the same rows as the gold query. Nothing is asked back, because the question was treated as clear.

![Demo page. The header is ASU maroon and gold. The database is WTA tennis, a clear sample question is selected from a dropdown, and the ontology spreadsheet lists table, column, preferred label, synonyms, and definition.](docs/figures/demo-interface.png)

![Demo result for a clear dog-kennels question. The banner says the question was treated as clear. A table lists the spreadsheet columns the plan used. The query plan, the SQL selecting distinct states shared by owners and professionals, and the output rows Wisconsin, Indiana, and Mississippi are shown. The result matches the gold SQL.](docs/figures/demo-result.png)

```bash
ontosql demo
```

Then open http://127.0.0.1:7860. A question that has not been run before takes about 15 seconds. A repeated question returns immediately, because model replies are cached.

## What is in place

| Piece | Status |
|---|---|
| Config A, execution match, metrics, result tables | Done. On the 222 Spider dev questions for the three databases, `qwen38-27b` scores 75.2% execution accuracy and 99.5% of queries are valid. Gold SQL scores 222/222, so the evaluator itself is sound. |
| Databases, ontology spreadsheets, Turtle | Done for `dog_kennels`, `student_transcripts_tracking`, and `wta_1`. |
| Query planning and config B | Done. The plan is JSON (tables, joins, filters, key phrases). Bad JSON is retried once, then generation continues without a plan. |
| Ambiguity stress set | Done. 20 clear Spider questions and 20 ambiguous rewrites (5 each of column, temporal, aggregation, and reference). Every interpretation executes, and the two readings of an ambiguous item return different rows. |
| Demo | Done for the clear-question path (config B). |
| Ambiguity detection, clarification, simulated user, verification and repair | Interfaces are wired. The stage bodies are the remaining work for configs C and D. |

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

`.env` needs `LLM_API_KEY` and `LLM_MODEL`. The runs so far use `qwen38-27b` on ASU Voyager, temperature 0.

## Running experiments

```bash
ontosql run --config A                       # predictions -> evaluations/runs/A/predictions.jsonl
ontosql evaluate --config A                  # execute + score -> scored.jsonl, summary.json
ontosql report                               # tables -> evaluations/tables/
ontosql errors                               # wrong answers -> evaluations/error_analysis/errors.csv
```

A short config B check on the stress set:

```bash
ontosql run --config B --dataset stress --limit 3
ontosql evaluate --config B --dataset stress --limit 3
```

Useful flags: `--dataset stress|spider|all` (default `stress`), `--limit 5` for a
quick smoke test, `--dbs dog_kennels,wta_1` to override `data/selected_dbs.txt`.
Model replies are cached in `.cache/llm/`, so re-running a configuration costs nothing.

Other commands: `ontosql check-stress --execute` validates the stress set and
runs every gold and interpretation query; `ontosql schema --db dog_kennels`
prints a schema; `ontosql build-ontology --db dog_kennels` regenerates Turtle
from the spreadsheet.

## Metrics

| Metric | Definition |
|---|---|
| Execution Accuracy (EX) | Share of questions whose SQL returns the gold result; reported for clear and ambiguous questions separately |
| SQL Validity Rate | Share of generated queries that parse and execute |
| Ambiguity detection | Precision, recall and F1 of the clarification flag on the stress set |
| Unnecessary Clarification Rate (UCR) | Share of the clear stress-set questions where the system still asks |
| Clarification Gain (CG) | EX(C) minus EX(B) on ambiguous questions |

Result comparisons are reported with 95% paired-bootstrap confidence intervals, since the stress set is about 40 questions. Exact string match on the SQL is not used. Equivalent queries can be written many ways, and execution accuracy already checks the answer.

## Repository layout

| Path | What's there |
|---|---|
| `code/ontosql/` | The pipeline package (baseline, ontology, planning, evaluation, demo, CLI) |
| `demo/` | The config B demo page |
| `code/tests/` | Unit tests on a small fixture database |
| `data/ontology/` | Spreadsheets and generated Turtle for the three databases |
| `data/stress_set/` | The 40-question Ambiguity Stress Set |
| `evaluations/` | Run outputs, scored predictions, result tables |
| `docs/` | Architecture, experiment protocol, per-member work packages, figures for this page |

Each member's work package, with interfaces and acceptance checks, is in `docs/team/`.

## Data

The experiments use three Spider dev databases chosen because their columns are easy to mix up: `dog_kennels` (five date columns), `student_transcripts_tracking` (several dates and repeated detail columns), and `wta_1` (winner/loser pairs and several dates).

Spider 1.0 (Yu et al., EMNLP 2018) is distributed under CC BY-SA 4.0 and is not committed here. `ontosql get-spider` downloads it.
