"""Stage 3: ontology-based ambiguity detection.  Owner: Vian.

Rule from the proposal: a key phrase is ambiguous if the ontology maps it to
more than one schema element and nothing else in the question settles which
one is meant. U(q, S, O) = number of such phrases; ask when U > 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ontology import Ontology, OntologyEntry
from .planning import QueryPlan


@dataclass
class AmbiguousPhrase:
    phrase: str
    candidates: list[OntologyEntry] = field(default_factory=list)


@dataclass
class AmbiguityResult:
    phrases: list[AmbiguousPhrase] = field(default_factory=list)

    @property
    def score(self) -> int:
        return len(self.phrases)

    @property
    def is_ambiguous(self) -> bool:
        return self.score > 0


def detect(question: str, plan: QueryPlan, ontology: Ontology) -> AmbiguityResult:
    """Return the phrases that stay ambiguous after context is considered.

    "Settled by context" examples to handle: the other candidate's table is
    not in the plan; the question names the column explicitly elsewhere.

    TODO(Vian)
    """
    raise NotImplementedError
