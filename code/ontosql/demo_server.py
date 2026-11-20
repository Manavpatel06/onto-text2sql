"""Local demo page for the full system (config D) with a real person answering.

Start it with `ontosql demo`. A clear question goes straight to SQL. An
ambiguous one comes back first with the clarification question and its
options; the person's answer is then used exactly as the simulated user's
answer is in `ontosql run --config D`, and the query is verified and repaired.
"""

from __future__ import annotations

import csv
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .baseline import SchemaCache
from .data import load_stress_set
from .db import ExecutionError, connect_readonly, db_path
from .eval.exec_match import check
from .llm import OpenAICompatibleModel, load_dotenv
from .pipeline import make_pipeline
from .planning import _parse_plan

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "demo" / "index.html"
LABELS = {
    "dog_kennels": "Dog kennels",
    "student_transcripts_tracking": "Student transcripts",
    "wta_1": "WTA tennis",
}
MAX_ROWS = 100


def selected_db_ids() -> list[str]:
    path = ROOT / "data" / "selected_dbs.txt"
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def read_ontology_csv(db_id: str) -> list[dict[str, str]]:
    path = ROOT / "data" / "ontology" / f"{db_id}.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def result_table(spider_dir: Path, db_id: str, sql: str) -> tuple[list[str], list[list], bool, str | None]:
    """Run the generated SQL and return column names, rows, truncation, and any error."""
    if not sql.strip():
        return [], [], False, "no SQL was produced"
    conn = connect_readonly(db_path(spider_dir, db_id))
    try:
        cur = conn.execute(sql)
        columns = [desc[0] for desc in cur.description] if cur.description else []
        fetched = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(fetched) > MAX_ROWS
        rows = [[_cell(value) for value in row] for row in fetched[:MAX_ROWS]]
        return columns, rows, truncated, None
    except Exception as exc:
        message = str(exc)
        if isinstance(exc, ExecutionError):
            message = str(exc)
        return [], [], False, message
    finally:
        conn.close()


def _cell(value):
    if value is None:
        return None
    return value if isinstance(value, (int, float, str)) else str(value)


class Demo:
    def __init__(self) -> None:
        load_dotenv(ROOT / ".env")
        self.spider_dir = ROOT / "data" / "spider"
        self.ontology_dir = ROOT / "data" / "ontology"
        self.examples = load_stress_set(ROOT / "data" / "stress_set" / "stress_set.jsonl")
        self.db_ids = selected_db_ids()
        self.model = OpenAICompatibleModel()
        self.pipeline = make_pipeline("D", self.model, SchemaCache(self.spider_dir), self.ontology_dir)

    def ask(self, db_id: str, question: str, answer: str | None = None) -> dict:
        from .types import Example

        example = Example(id="demo", db_id=db_id, question=question.strip(), gold_sql="", kind="clear", source="stress")
        if answer is None:
            _plan, amb, clar = self.pipeline.analyse(example)
            if clar is not None:
                return {
                    "needs_clarification": True,
                    "question": question.strip(),
                    "clarification": clar.text,
                    "phrase": clar.phrase,
                    "kind": clar.kind,
                    "options": [{"key": o.key, "label": o.label, "description": o.description} for o in clar.options],
                    "highlighted": sorted({k for o in clar.options for k in [o.key] if not k.startswith("AGG.")}),
                    "flagged": [p.phrase for p in amb.phrases],
                    "settled": amb.settled,
                    "model": self.model.name,
                }
        prediction = self.pipeline.predict(example, user_reply=answer)
        plan = _parse_plan(prediction.trace.get("plan") or "")
        phrases = []
        highlighted: list[str] = []
        plan_text = ""
        if plan is not None:
            plan_text = plan.as_text()
            for phrase in plan.key_phrases:
                phrases.append({"phrase": phrase.phrase, "candidates": phrase.candidates})
                highlighted.extend(phrase.candidates)

        columns, rows, truncated, exec_error = ([], [], False, None)
        if prediction.pred_sql and not prediction.error:
            columns, rows, truncated, exec_error = result_table(self.spider_dir, db_id, prediction.pred_sql)

        gold = self._gold_for(db_id, question)
        matches_gold = None
        if gold and prediction.pred_sql and not prediction.error:
            _valid, correct, _err = check(db_path(self.spider_dir, db_id), prediction.pred_sql, gold)
            matches_gold = correct

        if prediction.asked_clarification:
            handling = (
                f'Ambiguous: "{", ".join(prediction.flagged_phrases)}" matched more than one meaning in the ontology. '
                f'The system asked first and used your answer: "{prediction.user_answer}".'
            )
        else:
            handling = (
                "Treated as a clear question. Every phrase was settled by the ontology and the rest of the question, "
                "so SQL was written without asking anything."
            )
        check_info = prediction.trace.get("final_check") or {}
        if prediction.n_repairs:
            handling += f" The first query failed a check and was repaired {prediction.n_repairs} time(s)."

        return {
            "db_id": db_id,
            "question": question.strip(),
            "needs_clarification": False,
            "asked_clarification": prediction.asked_clarification,
            "clarification": prediction.clarification_question,
            "user_answer": prediction.user_answer,
            "n_repairs": prediction.n_repairs,
            "check": check_info,
            "handling": handling,
            "plan_text": plan_text,
            "phrases": phrases,
            "highlighted": sorted(set(highlighted)),
            "sql": prediction.pred_sql,
            "error": prediction.error,
            "exec_error": exec_error,
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
            "row_count": len(rows),
            "latency_s": prediction.latency_s,
            "matches_gold": matches_gold,
            "model": self.model.name,
        }

    def _gold_for(self, db_id: str, question: str) -> str | None:
        key = " ".join(question.split())
        for example in self.examples:
            if example.db_id == db_id and " ".join(example.question.split()) == key:
                return example.gold_sql
        return None


def make_handler(demo: Demo):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            print(f"[demo] {self.address_string()} {fmt % args}")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                self._send(200, PAGE.read_text(encoding="utf-8").encode("utf-8"), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/meta":
                self._json(200, {
                    "model": demo.model.name,
                    "databases": [{"id": db_id, "label": LABELS.get(db_id, db_id)} for db_id in demo.db_ids],
                })
                return
            db_id = (query.get("db") or [""])[0]
            if db_id not in demo.db_ids:
                self._json(400, {"error": "unknown database"})
                return
            if parsed.path == "/api/ontology":
                rows = read_ontology_csv(db_id)
                self._json(200, {"columns": list(rows[0].keys()) if rows else [], "rows": rows})
                return
            if parsed.path == "/api/samples":
                samples = [
                    {"id": ex.id, "question": ex.question, "kind": ex.kind}
                    for ex in demo.examples
                    if ex.db_id == db_id
                ]
                self._json(200, {"questions": samples})
                return
            self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/ask":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "expected JSON"})
                return
            db_id = str(payload.get("db_id") or "")
            question = str(payload.get("question") or "").strip()
            if db_id not in demo.db_ids:
                self._json(400, {"error": "unknown database"})
                return
            if not question:
                self._json(400, {"error": "type a question first"})
                return
            answer = payload.get("answer")
            answer = str(answer).strip() if answer is not None else None
            try:
                self._json(200, demo.ask(db_id, question, answer))
            except Exception as exc:
                self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


def serve(port: int = 7860) -> None:
    if not PAGE.exists():
        raise SystemExit(f"demo page not found: {PAGE}")
    demo = Demo()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(demo))
    print(f"Demo ready at http://127.0.0.1:{port}  (model {demo.model.name}, full system, config D)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
