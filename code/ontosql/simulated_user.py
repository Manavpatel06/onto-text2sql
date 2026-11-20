"""Simulated user that answers clarification questions.  Owner: Saniya.

The simulated user knows what it meant (the intended interpretation recorded
in the Ambiguity Stress Set) and answers the clarification question the way a
person would, in plain language. It is built so it cannot make the system look
better than it is:

* No leaks. Replies are written from the interpretation's English description
  or the option's ontology label. They never contain SQL, table names or
  column identifiers; `leaks()` checks every reply.
* It only answers what was asked. If none of the offered options is what the
  user meant, the reply says so and adds nothing ("None of those, really."),
  so a badly targeted question gets no free help. A clear question that was
  asked about anyway gets a reply with no new information.
* Not formulaic. Several phrasings per reply type, picked by a seeded hash of
  the question id, so runs are repeatable but replies vary.
* Optional vagueness. With `vague_rate`, that fraction of replies is
  uninformative ("Either is fine, I'm not sure."), chosen deterministically.

Modes, for bounding the effect of clarification:
  realistic  the default, described above
  oracle     always states the intended reading, even if no option fits (upper bound)
  wrong      states a reading that was NOT intended (control: should hurt accuracy)
"""

from __future__ import annotations

import hashlib
import re
from typing import Union

from .clarify import Clarification, Option
from .types import AMBIGUOUS, Example

MODES = ("realistic", "oracle", "wrong")

_PICK = [
    "I mean {d}.",
    "{D}.",
    "Sorry, I meant {d}.",
    "The {l} one: {d}.",
]
_STATE = ["I mean {d}.", "{D}.", "What I want is {d}."]
_NONE = ["None of those, really.", "Neither of those.", "Hmm, not any of those."]
_NO_INFO = ["I just mean what I asked.", "Nothing more specific than the question.", "Just what I asked, please."]
_VAGUE = ["Either is fine, I'm not sure.", "I don't know, whichever.", "Not sure, any of them."]

_SQL_WORDS = re.compile(r"(\bselect\s|\bgroup by\b|\border by\b|\b(count|sum|avg|min|max)\s*\()", re.IGNORECASE)


def _h(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


def _choose(templates: list[str], example: Example, salt: str, seed: int) -> str:
    return templates[_h(example.id, salt, str(seed)) % len(templates)]


def _fill(t: str, d: str, label: str = "") -> str:
    d = d.strip().rstrip(".")
    return t.format(d=d, D=d[:1].upper() + d[1:], l=label or "first")


def leaks(reply: str, example: Example) -> bool:
    """True if a reply contains SQL or a schema identifier (anything with an underscore)."""
    if "_" in reply or _SQL_WORDS.search(reply):
        return True
    gold = example.gold_sql.lower()
    return any(tok.lower() in gold for tok in re.findall(r"[A-Za-z]+\.[A-Za-z]+", reply))


def _used(option: Option, sql: str) -> bool:
    sql = sql.lower()
    table, _, col = option.key.partition(".")
    if table == "AGG":
        return {"count": "count(", "sum": "sum(", "avg": "avg("}.get(col, "@@") in sql.replace(" (", "(")
    # the column, read from its own table (first_name of Owners is not first_name of Professionals)
    return (
        re.search(rf"\b{re.escape(col.lower())}\b", sql) is not None
        and re.search(rf"\b{re.escape(table.lower())}\b", sql) is not None
    )


def intended_option(example: Example, clarification: Clarification) -> Option | None:
    """The offered option that matches what the user meant, if any.

    An option matches when the intended interpretation uses it and at least
    one other interpretation does not (so it actually tells the readings apart).
    """
    interps = {i["id"]: i for i in example.interpretations}
    intended = interps.get(example.intended)
    if not intended:
        return None
    others = [i["sql"] for k, i in interps.items() if k != example.intended]
    hits = [o for o in clarification.options if _used(o, intended["sql"]) and not all(_used(o, s) for s in others)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:  # prefer the option fewest other readings use
        return min(hits, key=lambda o: sum(_used(o, s) for s in others))
    return None


def answer(
    example: Example,
    clarification: Union[Clarification, str],
    mode: str = "realistic",
    vague_rate: float = 0.0,
    seed: int = 0,
) -> str:
    """Reply to a clarification question. Never returns SQL or schema identifiers."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    interps = {i["id"]: i for i in example.interpretations}
    intended = interps.get(example.intended)

    if example.kind != AMBIGUOUS or not intended:
        reply = _choose(_NO_INFO, example, "noinfo", seed)
    elif mode == "oracle":
        reply = _fill(_choose(_STATE, example, "state", seed), intended["description"])
    elif mode == "wrong":
        wrong = next(i for k, i in interps.items() if k != example.intended)
        reply = _fill(_choose(_STATE, example, "state", seed), wrong["description"])
    else:
        if vague_rate > 0 and (_h(example.id, "vague", str(seed)) % 1000) / 1000 < vague_rate:
            reply = _choose(_VAGUE, example, "vague", seed)
        elif isinstance(clarification, Clarification):
            opt = intended_option(example, clarification)
            if opt is None:
                reply = _choose(_NONE, example, "none", seed)
            else:
                reply = _fill(_choose(_PICK, example, "pick", seed), intended["description"], opt.label)
        else:  # plain-text question: no structured options to check against
            reply = _fill(_choose(_STATE, example, "state", seed), intended["description"])

    if leaks(reply, example):  # never let a leak through; fall back to no information
        reply = _choose(_NO_INFO, example, "noinfo", seed)
    return reply
