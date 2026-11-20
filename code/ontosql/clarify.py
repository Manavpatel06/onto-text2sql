"""Stage 4: targeted clarification questions.  Owner: Saniya.

Turn an AmbiguityResult into one question that names the competing readings
using their ontology definitions, e.g.

  By "date", do you mean the date the dog was adopted by an owner (adoption date)
  or the date the dog left the kennel (departure date)?

One round of clarification per question (proposal, Stage 4): if several
phrases are flagged, only the first is asked about (aggregates first, then
question order; see ambiguity.detect).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ambiguity import AmbiguityResult
from .ontology import Ontology, OntologyEntry

MAX_OPTIONS = 4


@dataclass
class Option:
    key: str  # "Table.column" or "AGG.count"
    label: str  # what the user sees, e.g. "adoption date"
    description: str  # the ontology definition, as a phrase


@dataclass
class Clarification:
    text: str
    phrase: str
    kind: str  # "schema" or "aggregation"
    options: list[Option] = field(default_factory=list)

    def __str__(self) -> str:  # so it can be stored or printed like the plain question
        return self.text


def _as_phrase(definition: str) -> str:
    """First sentence of a definition, as a noun phrase: "Date the dog left." -> "the date the dog left"."""
    d = (definition or "").strip().split(". ")[0].rstrip(".")
    if not d:
        return ""
    d = d[0].lower() + d[1:]
    if not d.startswith(("the ", "a ", "an ", "how ", "whether ")):
        d = "the " + d
    return d


def _option(e: OntologyEntry) -> Option:
    return Option(key=e.key, label=e.pref_label, description=_as_phrase(e.definition))


def _join(parts: list[str]) -> str:
    if len(parts) <= 2:
        return " or ".join(parts)
    return ", ".join(parts[:-1]) + ", or " + parts[-1]


def make_clarification(question: str, ambiguity: AmbiguityResult, ontology: Ontology) -> Clarification | None:
    """Structured clarification for the first ambiguous phrase (None if nothing is ambiguous)."""
    if not ambiguity.phrases:
        return None
    amb = ambiguity.phrases[0]
    options = [_option(c) for c in amb.candidates[:MAX_OPTIONS]]
    if amb.kind == "aggregation":
        readings = [f"{o.description} ({o.label})" for o in options]
        text = f'By "{amb.phrase}", do you mean {_join(readings)}?'
    else:
        readings = [f"{o.description} ({o.label})" if o.description else o.label for o in options]
        text = f'By "{amb.phrase}", do you mean {_join(readings)}?'
    return Clarification(text=text, phrase=amb.phrase, kind=amb.kind, options=options)


def make_question(question: str, ambiguity: AmbiguityResult, ontology: Ontology) -> str:
    """Template-based clarification question (text only)."""
    c = make_clarification(question, ambiguity, ontology)
    return c.text if c else ""
