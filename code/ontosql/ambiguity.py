"""Stage 3: ontology-based ambiguity detection.  Owner: Vian.

Rule from the proposal: a key phrase is ambiguous if the ontology maps it to
more than one schema element and nothing else in the question settles which
one is meant. U(q, S, O) = number of such phrases; ask when U > 0.

Two kinds of ambiguity are detected:

* schema      - a phrase matches several columns through their SKOS labels
                ("date" -> date_arrived, date_adopted, date_departed)
* aggregation - a phrase such as "total" can mean more than one aggregate
                (COUNT or SUM). The aggregate vocabulary below plays the same
                role as the column ontology: each operator has a preferred
                label and alternative labels, and a phrase that hits more than
                one operator is ambiguous unless a cue in the question settles it.

"Settled by context", checked in this order:
  1. the phrase is the preferred label of exactly one candidate
     ("departure date" names only Dogs.date_departed);
  2. a word that only one candidate's labels or column name contain appears
     elsewhere in the question ("adopted", "winners", "semester");
  3. the candidates are restricted to the tables the question mentions. One
     candidate left means settled; candidates in *different* mentioned tables
     mean the question refers to each of them ("states that have both owners
     and professionals"), so that is not ambiguous either.

The rule is deterministic and every flag can be explained; there is no
learned confidence score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ontology import Ontology, OntologyEntry
from .planning import QueryPlan

MAX_NGRAM = 4

# A small SKOS-style vocabulary for aggregate operators.
AGGREGATES: dict[str, dict] = {
    "count": {
        "label": "number",
        "alt": ["number of", "how many", "count", "total"],
        "definition": "how many there are",
    },
    "sum": {
        "label": "sum",
        "alt": ["sum", "total", "combined", "altogether"],
        "definition": "the values added together",
    },
    "avg": {
        "label": "average",
        "alt": ["average", "mean"],
        "definition": "the average value",
    },
}
# Unambiguous cues: if one of these appears, the operator is settled.
AGGREGATE_CUES: dict[str, list[str]] = {
    "count": ["how many", "number of", "count", "how often"],
    "sum": ["sum of", "add up", "added together", "money", "cost", "costs", "spent", "spend", "paid", "pay"],
    "avg": ["average", "mean"],
}

_STOP = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "by", "and", "or", "is", "are",
    "was", "were", "be", "with", "what", "which", "who", "whose", "how", "list", "show",
    "find", "give", "all", "each", "every", "their", "his", "her", "its", "that", "this",
    "these", "those", "have", "has", "do", "does", "did", "any", "s", "me", "there", "from",
    "most", "recent", "both", "not", "than", "more", "less",
    # generic schema words: shared by many candidates, never distinctive
    "id", "code", "date", "name", "number", "details", "other", "description", "type",
}


@dataclass
class AmbiguousPhrase:
    phrase: str
    candidates: list[OntologyEntry] = field(default_factory=list)
    kind: str = "schema"  # "schema" or "aggregation"
    start: int = 0  # word position in the question, for ordering


@dataclass
class AmbiguityResult:
    phrases: list[AmbiguousPhrase] = field(default_factory=list)
    linked: dict[str, list[str]] = field(default_factory=dict)  # phrase -> columns it could mean
    resolved: dict[str, list[str]] = field(default_factory=dict)  # phrase -> columns after settling
    settled: dict[str, str] = field(default_factory=dict)  # phrase -> why it was not flagged

    @property
    def score(self) -> int:
        return len(self.phrases)

    @property
    def is_ambiguous(self) -> bool:
        return self.score > 0


# ---------------------------------------------------------------- text helpers

def words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()


def stem(w: str) -> str:
    """Crude stem: drop a plural ending, keep the first 5 letters."""
    for suf in ("ies", "es", "s"):
        if len(w) > 4 and w.endswith(suf) and not w.endswith("ss"):
            w = w[: -len(suf)] + ("y" if suf == "ies" else "")
            break
    return w[:5] if len(w) >= 5 else w


_ORDINAL = {"first": "1", "second": "2", "third": "3", "fourth": "4"}


def _stems(text: str) -> set[str]:
    return {stem(w) for w in words(text) if w not in _STOP}


def _digits(text: str) -> set[str]:
    return {w for w in words(text) if w.isdigit()}


def _contains(haystack: list[str], phrase: str) -> bool:
    p = words(phrase)
    return bool(p) and any(haystack[i : i + len(p)] == p for i in range(len(haystack) - len(p) + 1))


def split_identifier(name: str) -> list[str]:
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    return words(name.replace("_", " "))


# ---------------------------------------------------------------- matching

def _table_labels(ontology: Ontology) -> dict[str, list[str]]:
    tables = {e.table for e in ontology.entries}
    labels: dict[str, list[str]] = {t: [t.replace("_", " ")] for t in tables}
    for e in ontology.entries:
        if not e.column:
            labels[e.table] += [e.pref_label, *e.alt_labels]
    return labels


def names_a_table(span: str, ontology: Ontology) -> str | None:
    """The table a phrase names ("dogs" -> Dogs), or None.

    Such a phrase refers to the table itself, not to a foreign-key column
    labelled with the table's name (Treatments.dog_id is labelled "dog").
    """
    sp = {stem(w) for w in words(span) if w not in _STOP}
    if not sp:
        return None
    for t, labs in _table_labels(ontology).items():
        for lab in labs:
            if {stem(w) for w in words(lab) if w not in _STOP} == sp:
                return t
    return None


def table_mentions(question: str, ontology: Ontology) -> set[str]:
    """Tables the question names, through the table's own name or its SKOS labels."""
    qstems = {stem(w) for w in words(question)}
    labels = _table_labels(ontology)
    found = set()
    for t, labs in labels.items():
        for lab in labs:
            ws = [w for w in words(lab) if w not in _STOP]
            if ws and all(stem(w) in qstems for w in ws):
                found.add(t)
                break
    return found


def phrase_matches(question: str, ontology: Ontology) -> list[tuple[int, int, str, list[OntologyEntry]]]:
    """All maximal question spans (1-4 words) that hit column entries in the ontology.

    Returns (start, end, phrase, column hits). A span inside a longer matching
    span is dropped, so "dog names" wins over "names".
    """
    ws = words(question)
    found = []
    for n in range(MAX_NGRAM, 0, -1):
        for i in range(len(ws) - n + 1):
            if n == 1 and ws[i] in _STOP and ws[i] not in ("date", "name", "description", "code"):
                continue
            span = " ".join(ws[i : i + n])
            hits = [e for e in ontology.lookup(span) if e.column]
            if hits:
                found.append((i, i + n, span, hits))
    found.sort(key=lambda t: (-(t[1] - t[0]), t[0]))
    kept: list[tuple[int, int, str, list[OntologyEntry]]] = []
    for s, e, span, hits in found:
        if any(s >= ks and e <= ke for ks, ke, _, _ in kept):
            continue
        kept.append((s, e, span, hits))
    kept.sort(key=lambda t: t[0])
    return kept


def aggregate_ops(span: str) -> list[str]:
    return [op for op, d in AGGREGATES.items() if span in d["alt"] or span == d["label"]]


def aggregate_entry(op: str) -> OntologyEntry:
    d = AGGREGATES[op]
    return OntologyEntry(table="AGG", column=op, pref_label=d["label"], alt_labels=list(d["alt"]), definition=d["definition"])


_SKIP = {"of", "the", "a", "an", "all", "each", "every", "their", "his", "her", "its", "s", "those", "these"}


def _adjacent_table(qws: list[str], start: int, end: int, cands: list[OntologyEntry]) -> str | None:
    """Table named directly after "<phrase> of (the)" or directly before "<table>'s <phrase>"."""
    def table_for(w: str) -> str | None:
        st = stem(w)
        for c in cands:
            if stem(c.table.lower().split("_")[-1]) == st:
                return c.table
        return None

    k = end
    if k < len(qws) and qws[k] == "of":
        while k < len(qws) and qws[k] in _SKIP:
            k += 1
        if k < len(qws):
            t = table_for(qws[k])
            if t:
                return t
    k = start - 1
    while k >= 0 and qws[k] in ("s",):
        k -= 1
    if k >= 0 and start - k <= 2:
        return table_for(qws[k])
    return None


def settle(question: str, span: str, start: int, end: int, cands: list[OntologyEntry],
           focus: set[str]) -> tuple[list[OntologyEntry], str]:
    """Narrow the candidates of one phrase using the rest of the question.

    Returns (remaining candidates, reason). An empty reason with 2+ remaining
    candidates means the phrase stays ambiguous.
    """
    qws = words(question)
    span_norm = " ".join(words(span))
    # 1. the phrase is the preferred label of exactly one candidate
    prefs = [" ".join(words(c.pref_label)) for c in cands]
    pref_hits = [c for c, p in zip(cands, prefs) if p == span_norm]
    if len(pref_hits) == 1 and len(set(prefs)) > 1:
        return pref_hits, "preferred label"
    # "full name" means first and last name together
    if start > 0 and qws[start - 1] == "full":
        return cands, "each named"
    # 2. a distinctive word elsewhere in the question
    other_stems = {stem(w) for k, w in enumerate(qws) if not (start <= k < end) and w not in _STOP}
    other_stems |= {_ORDINAL[w] for k, w in enumerate(qws) if w in _ORDINAL and not (start <= k < end)}
    span_stems = _stems(span)
    # SKOS labels count as evidence, plus numbers in the column name (line_1, line_2);
    # other identifier words do not (date_first_registered is not "first name")
    cand_stems = [
        (_stems(" ".join([c.pref_label, *c.alt_labels])) | _digits(" ".join(split_identifier(c.column))))
        - span_stems
        for c in cands
    ]
    # columns of one table: the table's own name ("order" in "order date") tells them apart from nothing
    if len({c.table for c in cands}) == 1:
        own = _stems(" ".join(split_identifier(cands[0].table)))
        cand_stems = [st - own for st in cand_stems]
    distinctive = []
    for i, st in enumerate(cand_stems):
        others = set().union(*(cand_stems[j] for j in range(len(cands)) if j != i))
        if (st - others) & other_stems:
            distinctive.append(cands[i])
    if len(distinctive) == 1:
        return distinctive, "distinctive word"
    if len(distinctive) > 1:
        return distinctive, "each named"
    # "names of the dogs", "the dog's name": the table named right next to the phrase
    near = _adjacent_table(qws, start, end, cands)
    if near:
        hit = [c for c in cands if c.table == near]
        if len(hit) == 1:
            return hit, "adjacent table"
        if hit:
            cands = hit
    # 3. restrict to mentioned tables
    in_focus = [c for c in cands if c.table in focus]
    if len(in_focus) == 1:
        return in_focus, "mentioned table"
    if len(in_focus) > 1:
        if len({c.table for c in in_focus}) == len(in_focus):
            return in_focus, "each mentioned table"
        cands = in_focus
    return cands, ""


# ---------------------------------------------------------------- detection

def detect(question: str, plan: QueryPlan | None, ontology: Ontology) -> AmbiguityResult:
    """Return the phrases that stay ambiguous after context is considered.

    `plan` may be None: the rule works on the question and the ontology alone.
    When a plan is given, its key phrases that occur in the question are
    checked too. The plan's own column choices are not used to settle
    anything, because the planner resolves ambiguity by guessing.
    """
    result = AmbiguityResult()
    qws = words(question)
    focus = table_mentions(question, ontology)
    matches = phrase_matches(question, ontology)

    if plan is not None:
        covered = {m[2] for m in matches}
        for kp in plan.key_phrases:
            span = " ".join(words(kp.phrase))
            if not span or span in covered or not _contains(qws, span):
                continue
            hits = [e for e in ontology.lookup(span) if e.column]
            if hits:
                n = len(span.split())
                i = next(k for k in range(len(qws) - n + 1) if qws[k : k + n] == span.split())
                matches.append((i, i + n, span, hits))
                covered.add(span)

    # phrases that name a table ("dogs", "courses") refer to the table itself
    # unless one of its column readings sits in another table the question mentions
    # ("each student's address" means a Students column, not the Addresses table)
    kept = []
    for m in matches:
        t = names_a_table(m[2], ontology)
        if t and not any(h.table in focus and h.table != t for h in m[3]):
            focus.add(t)
            result.settled[m[2]] = f"names table {t}"
        else:
            kept.append(m)
    matches = kept

    # a column named unambiguously anywhere puts its table in focus
    for _, _, _, hits in matches:
        if len(hits) == 1:
            focus.add(hits[0].table)

    for start, end, span, hits in sorted(matches, key=lambda m: m[0]):
        if span in result.linked:
            continue
        result.linked[span] = [h.key for h in hits]
        if len(hits) == 1:
            result.resolved[span] = [hits[0].key]
            continue
        remaining, why = settle(question, span, start, end, hits, focus)
        result.resolved[span] = [c.key for c in remaining]
        if aggregate_ops(span):
            continue  # the aggregate check below decides; columns only say what is totalled
        if len(remaining) <= 1 or why in ("each mentioned table", "each named"):
            result.settled[span] = why or "single candidate"
            continue
        result.phrases.append(AmbiguousPhrase(span, remaining, "schema", start))

    # aggregate words ("total")
    cued = [op for op, cues in AGGREGATE_CUES.items() if any(_contains(qws, c) for c in cues)]
    for i, w in enumerate(qws):
        ops = aggregate_ops(w)
        if len(ops) < 2:
            continue
        hit = [op for op in cued if op in ops]
        nxt = " ".join(qws[i + 1 : i + 3])
        if not hit and nxt and any(nxt.startswith(m[2]) for m in matches):
            hit = ["sum"]  # "total ranking points", "total cost": a total of a column
        if len(hit) == 1:
            result.settled[w] = f"aggregate cue ({hit[0]})"
            continue
        if not any(p.phrase == w for p in result.phrases):
            result.phrases.append(AmbiguousPhrase(w, [aggregate_entry(op) for op in ops], "aggregation", i))

    # aggregates first (they change the whole query), then question order
    result.phrases.sort(key=lambda p: (p.kind != "aggregation", p.start))
    return result
