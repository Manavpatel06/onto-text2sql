# Schema ontologies

For each selected database:

1. Fill in `<db_id>.csv` (one row per column, plus optional table rows with an empty `column`):

   ```
   table,column,pref_label,alt_labels,definition
   Dogs,date_adopted,adoption date,date|adopted on|adoption day,Date the dog was adopted by an owner.
   Dogs,date_departed,departure date,date|left on|departure day,Date the dog left the kennel.
   ```

   `alt_labels` are separated by `|`. Put deliberately shared synonyms (like `date`) where a
   person really could mean either column; that is what ambiguity detection relies on.

2. Generate Turtle: `ontosql build-ontology --db <db_id>` (writes `<db_id>.ttl`).

Vocabulary: W3C Direct Mapping for tables/columns/foreign keys, RDFS for
classes/properties/labels, SKOS for `prefLabel`, `altLabel`, `definition`.
