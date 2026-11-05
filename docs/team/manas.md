# Manas: database selection, schema extraction, ontology spreadsheet, Turtle conversion

Your output unblocks Vian, Saniya and Vatsal, so aim to finish first.

## Context

The project grounds Text-to-SQL in a small RDFS + SKOS ontology of each
database. Every column gets a readable label, synonyms and a one-line
definition. Two consumers:
* configs B-D paste `Ontology.context_text()` into the SQL prompt;
* ambiguity detection calls `Ontology.lookup(phrase)`: more than one hit means ambiguous.

## Files you own

* `code/ontosql/ontology.py` (stubs with TODOs are already there)
* `data/selected_dbs.txt`
* `data/ontology/<db_id>.csv` and generated `<db_id>.ttl`
* `code/tests/test_ontology.py` (new)

Schema extraction already exists: `ontosql.schema.extract_schema()` returns
tables, columns, primary keys and foreign keys; `ontosql schema --db <id>` prints it.

## Step 1: confirm the databases

Provisional: `dog_kennels`, `student_transcripts_tracking`, `wta_1` (reasons in
`data/README.md`). Keep, swap or cut to two, then update `data/selected_dbs.txt`.
Criteria: several tables, foreign-key joins, at least one pair of columns that
are easy to mix up (two dates, two amounts, winner/loser).

## Step 2: spreadsheets

`data/ontology/<db_id>.csv` with header `table,column,pref_label,alt_labels,definition`
(see `data/ontology/README.md`). One row per column; optional table rows with
empty `column`. Use the real Spider names (case-sensitive as in the schema).
Synonyms that are shared on purpose (e.g. `date` on every date column) are what
make ambiguity detectable; agree on them with Vian and Saniya.

## Step 3: implement `ontology.py`

```python
build_turtle(csv_path, schema, out_path) -> None
load_ontology(ttl_path, db_id) -> Ontology
Ontology.context_text() -> str
Ontology.lookup(phrase) -> list[OntologyEntry]
```

Turtle shape (prefix `:` = `http://example.org/<db_id>#`):

```turtle
:Dogs a rdfs:Class ; rdfs:label "dog" .
:date_adopted a rdf:Property ;
    rdfs:domain :Dogs ;
    skos:prefLabel "adoption date" ;
    skos:altLabel "date", "adopted on" ;
    skos:definition "Date the dog was adopted by an owner." .
:Dogs_owner_id a owl:ObjectProperty ; rdfs:domain :Dogs ; rdfs:range :Owners .
```

Use the IRI `:<Table>.<column>` or `:<Table>_<column>` consistently so two
tables with the same column name don't collide. `build_turtle` must raise if the
CSV names a table or column that isn't in the schema. Matching in `lookup`:
lowercase, strip punctuation, crude singularization ("dates" → "date"), match
against `pref_label` and every `alt_label`.

## Step 4: wire up

* `ontosql build-ontology --db <db_id>` already calls `build_turtle` (writes `data/ontology/<db_id>.ttl`).
* `pipeline.OntologyPipeline` loads `data/ontology/<db_id>.ttl` with `load_ontology`.

## Tests (`code/tests/test_ontology.py`)

Use the `spider_dir` fixture in `conftest.py` (a tiny `shop` DB with
`orders.order_date` and `orders.delivery_date`). Check: CSV → TTL → load round
trip keeps every label; `lookup("date")` returns both date columns;
`lookup("delivery date")` returns one; an unknown column in the CSV raises.

## Done when

* `data/ontology/<db_id>.ttl` exists for every selected DB and parses with rdflib.
* `pytest` green, including your new tests.
