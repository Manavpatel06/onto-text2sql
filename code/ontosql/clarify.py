"""Stage 4: targeted clarification questions.  Owner: Saniya.

Turn an AmbiguityResult into one question that names the competing readings
using their ontology definitions, e.g.

  By "last month", do you mean the date the order was placed (order date)
  or the date it reached the customer (delivery date)?

One round of clarification per question (proposal, Stage 4).
"""

from __future__ import annotations

from .ambiguity import AmbiguityResult
from .ontology import Ontology


def make_question(question: str, ambiguity: AmbiguityResult, ontology: Ontology) -> str:
    """Template-based by default. If several phrases are ambiguous, ask about the
    first one only (one round).  TODO(Saniya)"""
    raise NotImplementedError
