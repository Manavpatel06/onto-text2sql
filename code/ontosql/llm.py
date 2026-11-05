"""Thin wrapper over any OpenAI-compatible chat endpoint (ASU Voyager, vLLM, etc.).

Configuration comes from environment variables (see .env.example):
  LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

Responses are cached on disk, keyed by (model, messages, temperature), so a
rerun of the same configuration is free and exactly reproducible.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Protocol

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "llm"


class ChatModel(Protocol):
    name: str

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str: ...


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class OpenAICompatibleModel:
    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        cache_dir: str | Path | None = DEFAULT_CACHE_DIR,
        max_retries: int = 5,
        timeout_s: float = 600.0,
    ) -> None:
        from openai import OpenAI  # imported lazily so tests run without the package configured

        load_dotenv()
        self.name = model or os.environ.get("LLM_MODEL", "")
        if not self.name:
            raise ValueError("set LLM_MODEL (or pass model=...)")
        self.client = OpenAI(
            base_url=base_url or os.environ.get("LLM_BASE_URL"),
            api_key=api_key or os.environ.get("LLM_API_KEY", "none"),
            timeout=timeout_s,
        )
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_retries = max_retries
        # Optional knobs for reasoning models (e.g. LLM_REASONING_EFFORT=none for short direct answers)
        self.extra: dict = {}
        if os.environ.get("LLM_REASONING_EFFORT"):
            self.extra["reasoning_effort"] = os.environ["LLM_REASONING_EFFORT"]
        self.max_tokens = int(os.environ["LLM_MAX_TOKENS"]) if os.environ.get("LLM_MAX_TOKENS") else None

    def _key(self, messages: list[dict[str, str]], temperature: float) -> str:
        blob = json.dumps(
            {"m": self.name, "msgs": messages, "t": temperature, "x": self.extra, "mt": self.max_tokens},
            sort_keys=True,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        key = self._key(messages, temperature)
        if self.cache_dir:
            f = self.cache_dir / f"{key}.json"
            if f.exists():
                return json.loads(f.read_text())["content"]
        delay = 5.0
        kwargs = {"model": self.name, "messages": messages, "temperature": temperature}
        if self.max_tokens:
            kwargs["max_tokens"] = self.max_tokens
        if self.extra:
            kwargs["extra_body"] = self.extra
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content or ""
                break
            except Exception as e:  # retry only transient errors (429, 5xx, connection)
                status = getattr(e, "status_code", None)
                if attempt == self.max_retries or (status is not None and status < 500 and status != 429):
                    raise
                time.sleep(delay)
                delay *= 2
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{key}.json").write_text(json.dumps({"content": content}))
        return content


def list_models(base_url: str | None = None, api_key: str | None = None) -> list[dict]:
    """Chat models available to the configured key (GET /v1/models)."""
    from openai import OpenAI

    load_dotenv()
    client = OpenAI(
        base_url=base_url or os.environ.get("LLM_BASE_URL"),
        api_key=api_key or os.environ.get("LLM_API_KEY", "none"),
    )
    out = []
    for m in client.models.list().data:
        d = m.model_dump() if hasattr(m, "model_dump") else dict(m)
        if d.get("model_type", "chat") == "chat":
            out.append(d)
    return out


class ScriptedModel:
    """Deterministic stand-in for tests and dry runs: returns canned replies in order,
    or computes them with a function of the messages."""

    def __init__(self, replies=None, fn=None, name: str = "scripted") -> None:
        self.replies = list(replies or [])
        self.fn = fn
        self.name = name
        self.calls: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.calls.append(messages)
        if self.fn is not None:
            return self.fn(messages)
        if not self.replies:
            raise RuntimeError("ScriptedModel ran out of replies")
        return self.replies.pop(0)
