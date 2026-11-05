# Vian: ontology-grounded query planning and ambiguity detection

Depends on Manas's `Ontology` (you can start with a hand-built `Ontology` object in tests).

## Context

Config B adds ontology context and a query plan; config C adds the ambiguity
check that decides whether to ask a clarification question. The proposal's
rule: U(q, S, O) = number of key phrases the ontology maps to more than one
schema element that nothing else in the question disambiguates. Ask iff U > 0.
No learned score, no threshold; the rule is meant to be transparent.

## Files you own

* `code/ontosql/planning.py`: `plan_query()`, `QueryPlan.as_text()`
* `code/ontosql/ambiguity.py`: `detect()`
* `code/tests/test_planning.py`, `code/tests/test_ambiguity.py` (new)

## Interfaces (already declared; keep the names)

```python
plan_query(question, schema, ontology, model) -> QueryPlan
QueryPlan.as_text() -> str            # short text passed to SQL generation
detect(question, plan, ontology) -> AmbiguityResult   # .phrases, .score, .is_ambiguous
```

## Steps

1. **Planning prompt.** Give the model the question, `to_ddl(schema)` and
   `ontology.context_text()`; ask for JSON only:
   `{target_attributes, tables, joins, filters, aggregation, group_by, order_by, limit, key_phrases: [{phrase, candidates: ["Table.column", ...]}]}`.
   Parse it into `QueryPlan`. On bad JSON retry once, then return
   `QueryPlan(raw=<output>)` so the pipeline falls back to plain generation.
2. **`as_text()`**: a few lines, e.g. `tables: Dogs, Owners | filter: date in 2018-03 | output: Dogs.name`.
3. **Detection.** Don't trust the model's candidates alone: for each key phrase
   (and n-grams of the question as a backstop) call `ontology.lookup(phrase)`.
   A phrase is ambiguous if lookup returns ≥ 2 entries and context doesn't
   settle it. Settled when: the question also contains another phrase that
   matches exactly one of the candidates; or only one candidate's table appears
   in the plan.
4. Return `AmbiguityResult(phrases=[AmbiguousPhrase(phrase, candidates), ...])`.

## Tests

Use `ontosql.llm.ScriptedModel` to return fixed JSON, so tests run offline.
Cover: "orders from October" → ambiguous (order_date vs delivery_date);
"orders delivered in October" → not ambiguous; malformed JSON → fallback plan.

## Done when

* On Saniya's stress set, `ontosql run --config C` + `evaluate` gives ambiguity
  precision/recall in `summary.json` (target: recall ≥ 0.8, UCR ≤ 0.15).
* `pytest` green.
