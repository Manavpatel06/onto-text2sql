"""Simulated user that answers clarification questions.  Owner: Saniya.

Answers with the intended interpretation recorded in the Ambiguity Stress Set,
so clarification can be evaluated automatically and repeatably.
"""

from __future__ import annotations

from .types import Example


def answer(example: Example, clarification_question: str) -> str:
    """Return the intended interpretation's description as the user's reply.

    For a clear question (the system asked when it shouldn't have), reply with
    a neutral restatement such as the original question, so we measure the
    cost of the unnecessary interruption rather than leaking the gold SQL.

    Never return gold SQL. TODO(Saniya)
    """
    raise NotImplementedError
