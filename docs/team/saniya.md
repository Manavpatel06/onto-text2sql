# Saniya: Ambiguity Stress Set, clarification prompts, simulated user

The stress set is the main benchmark; everyone's numbers depend on it, so it comes first.

## Files you own

* `data/stress_set/stress_set.jsonl`
* `code/ontosql/clarify.py`: `make_question()`
* `code/ontosql/simulated_user.py`: `answer()`
* `code/tests/test_clarify.py` (new)

## Part 1: the stress set (~40 items)

Format and rules: `data/stress_set/README.md`; three real examples in
`data/stress_set/stress_set.example.jsonl`.

* 20 **clear**: copy from Spider dev (`data/spider/dev.json`) for the databases in
  `data/selected_dbs.txt`. Pick a mix (joins, aggregation, nesting).
* 20 **ambiguous**: 5 each of `column`, `temporal`, `aggregation`, `reference`.
  Rewrite a clear question so one phrase fits two schema elements. For each,
  write every plausible interpretation with its SQL, and mark the intended one
  (its SQL is the gold).
* Each interpretation must give a different result on the database, or the item can't discriminate.
* Validate: `ontosql check-stress --execute` must print `all SQL executes`.
* Coordinate synonyms with Manas: if "date" should be ambiguous in your
  question, it must be an alt label on both date columns in the ontology.

## Part 2: clarification question

```python
make_question(question, ambiguity, ontology) -> str
```

Use the ontology definitions of the competing candidates; name the phrase and
the options. Template is fine (and reproducible):

> By "from March 2018", do you mean the date the dog was adopted (adoption date) or the date it left the kennel (departure date)?

One round only: if several phrases are flagged, ask about the first.

## Part 3: simulated user

```python
answer(example, clarification_question) -> str
```

* Ambiguous item: return the intended interpretation's `description`
  (e.g. "dogs adopted in March 2018").
* Clear item (system asked unnecessarily): return the original question
  restated, giving no new information.
* Never return SQL.

## Tests

Clarify: question mentions the phrase and both candidates' labels. Simulated
user: returns the intended description; never contains "SELECT".

## Done when

* `stress_set.jsonl` has ~40 valid items and `check-stress --execute` passes.
* `pytest` green.
