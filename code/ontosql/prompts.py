"""Prompt templates and SQL extraction shared by all configurations.

Keep the generation prompt identical across configs A-D except for the extra
context each stage adds, so that ablation differences come from the stages and
not from prompt wording.
"""

from __future__ import annotations

import re

SYSTEM_SQL = (
    "You translate questions about a SQLite database into one SQLite query. "
    "Use only tables and columns that exist in the schema. "
    "Return only the SQL query inside a ```sql code block, with no explanation."
)


def sql_messages(
    question: str,
    ddl: str,
    extra_context: str = "",
    plan: str = "",
    clarification: str = "",
) -> list[dict[str, str]]:
    parts = [f"Database schema:\n{ddl}"]
    if extra_context:
        parts.append(f"Schema descriptions:\n{extra_context}")
    if plan:
        parts.append(f"Query plan:\n{plan}")
    q = question
    if clarification:
        q = f"{question}\n(Clarification from the user: {clarification})"
    parts.append(f"Question: {q}")
    return [
        {"role": "system", "content": SYSTEM_SQL},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


_FENCE = re.compile(r"```(?:sql|sqlite)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_LEAD = re.compile(r"^\s*(?:sql|sqlite|query|answer)\s*:\s*", re.IGNORECASE)
_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_START = re.compile(r"\b(SELECT|WITH)\b", re.IGNORECASE)


def extract_sql(text: str) -> str:
    """Pull a single SQL statement out of a model reply.

    Handles fenced code blocks, "SQL:" prefixes, trailing prose and trailing
    semicolons. Returns "" if nothing that looks like a query is found.
    """
    if not text:
        return ""
    # reasoning models may prepend their thinking
    text = _THINK.sub("", text)
    m = _FENCE.search(text)
    candidate = m.group(1) if m else text
    candidate = _LEAD.sub("", candidate.strip())
    s = _START.search(candidate)
    if not s:
        return ""
    candidate = candidate[s.start():]
    # keep only the first statement
    candidate = candidate.split(";")[0]
    # drop prose after a blank line (common when there is no fence)
    candidate = re.split(r"\n\s*\n", candidate)[0]
    return " ".join(candidate.split()).strip()
