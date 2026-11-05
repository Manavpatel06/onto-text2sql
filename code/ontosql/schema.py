"""Schema extraction from SQLite and serialization for prompts.

The direct baseline (config A) sees only this serialized schema. The ontology
stages (B-D) add labels, definitions and synonyms on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .db import connect_readonly


@dataclass
class Column:
    name: str
    type: str
    is_pk: bool = False


@dataclass
class ForeignKey:
    table: str
    column: str
    ref_table: str
    ref_column: str


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)


@dataclass
class Schema:
    db_id: str
    tables: list[Table] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)

    def table(self, name: str) -> Table | None:
        lname = name.lower()
        return next((t for t in self.tables if t.name.lower() == lname), None)

    def has_column(self, table: str, column: str) -> bool:
        t = self.table(table)
        return t is not None and any(c.name.lower() == column.lower() for c in t.columns)

    def all_columns(self) -> list[tuple[str, str]]:
        return [(t.name, c.name) for t in self.tables for c in t.columns]


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def extract_schema(db_file: str | Path, db_id: str | None = None) -> Schema:
    """Read tables, columns, primary keys and foreign keys from a SQLite file."""
    db_file = Path(db_file)
    schema = Schema(db_id=db_id or db_file.stem)
    conn = connect_readonly(db_file)
    try:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for name in names:
            cols = [
                Column(name=r[1], type=(r[2] or "").upper(), is_pk=bool(r[5]))
                for r in conn.execute(f"PRAGMA table_info({_q(name)})")
            ]
            schema.tables.append(Table(name=name, columns=cols))
            for r in conn.execute(f"PRAGMA foreign_key_list({_q(name)})"):
                # r: id, seq, table, from, to, on_update, on_delete, match
                ref_col = r[4]
                if ref_col is None:  # FK to the referenced table's primary key
                    pk = [
                        row[1]
                        for row in conn.execute(f"PRAGMA table_info({_q(r[2])})")
                        if row[5]
                    ]
                    ref_col = pk[0] if pk else ""
                fk = ForeignKey(table=name, column=r[3], ref_table=r[2], ref_column=ref_col)
                if fk not in schema.foreign_keys:  # Spider has some duplicated FKs
                    schema.foreign_keys.append(fk)
    finally:
        conn.close()
    return schema


def to_ddl(schema: Schema) -> str:
    """Serialize as CREATE TABLE statements, the format LLM prompts use most often."""
    blocks = []
    for t in schema.tables:
        lines = [f"  {c.name} {c.type}".rstrip() for c in t.columns]
        pks = [c.name for c in t.columns if c.is_pk]
        if pks:
            lines.append(f"  PRIMARY KEY ({', '.join(pks)})")
        for fk in schema.foreign_keys:
            if fk.table == t.name:
                lines.append(f"  FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table}({fk.ref_column})")
        blocks.append(f"CREATE TABLE {t.name} (\n" + ",\n".join(lines) + "\n);")
    return "\n\n".join(blocks)


def sample_rows(db_file: str | Path, schema: Schema, n: int = 3) -> str:
    """A few example rows per table, optional extra context for prompts."""
    conn = connect_readonly(db_file)
    out = []
    try:
        for t in schema.tables:
            rows = conn.execute(f"SELECT * FROM {_q(t.name)} LIMIT {int(n)}").fetchall()
            header = " | ".join(c.name for c in t.columns)
            body = "\n".join(" | ".join(str(v) for v in r) for r in rows)
            out.append(f"/* {t.name} */\n{header}\n{body}".rstrip())
    finally:
        conn.close()
    return "\n\n".join(out)
