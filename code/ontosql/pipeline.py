"""Configurations B-D: ontology context, clarification, verification.

Each configuration adds one stage on top of the previous one (proposal Table I):

  A  direct baseline                     (ontosql.baseline.DirectBaseline)
  B  + ontology context and query plan
  C  + ambiguity detection, clarification and simulated user
  D  + verification and repair (max 2)

Clarification answers come from simulated_user, whose mode (realistic,
oracle, wrong) and vague_rate bound the effect of clarification; see
simulated_user.py. System integration owner: Vatsal.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import ambiguity, clarify, simulated_user, verify
from .baseline import DirectBaseline, SchemaCache
from .llm import ChatModel
from .ontology import Ontology, load_ontology
from .planning import plan_query
from .prompts import extract_sql, sql_messages
from .schema import to_ddl
from .types import Example, Prediction

MAX_REPAIRS = 2
CONFIGS = ("A", "B", "C", "D")


class OntologyPipeline:
    def __init__(
        self,
        config: str,
        model: ChatModel,
        schemas: SchemaCache,
        ontology_dir: str | Path,
        temperature: float = 0.0,
        user_mode: str = "realistic",
        vague_rate: float = 0.0,
        seed: int = 0,
    ) -> None:
        if config not in ("B", "C", "D"):
            raise ValueError(f"OntologyPipeline handles B, C, D (got {config})")
        self.config = config
        self.model = model
        self.schemas = schemas
        self.ontology_dir = Path(ontology_dir)
        self.temperature = temperature
        self.user_mode = user_mode
        self.vague_rate = vague_rate
        self.seed = seed
        self._ontologies: dict[str, Ontology] = {}

    @property
    def clarify(self) -> bool:
        return self.config in ("C", "D")

    @property
    def verify(self) -> bool:
        return self.config == "D"

    def ontology(self, db_id: str) -> Ontology:
        if db_id not in self._ontologies:
            self._ontologies[db_id] = load_ontology(self.ontology_dir / f"{db_id}.ttl", db_id)
        return self._ontologies[db_id]

    def _generate(self, ex: Example, ddl: str, onto_text: str, plan_text: str, clar: str) -> str:
        msgs = sql_messages(ex.question, ddl, extra_context=onto_text, plan=plan_text, clarification=clar)
        return extract_sql(self.model.complete(msgs, temperature=self.temperature))

    def analyse(self, ex: Example):
        """Plan, ambiguity result and clarification (None if clear) for one question.

        Used by the demo to ask a real person before any SQL is written.
        """
        schema = self.schemas.schema(ex.db_id)
        onto = self.ontology(ex.db_id)
        plan = plan_query(ex.question, schema, onto, self.model)
        amb = ambiguity.detect(ex.question, plan, onto)
        clar = clarify.make_clarification(ex.question, amb, onto) if amb.is_ambiguous else None
        return plan, amb, clar

    def predict(self, ex: Example, user_reply: str | None = None) -> Prediction:
        """Run the configuration on one question.

        `user_reply` replaces the simulated user with a real answer (demo use);
        it only matters when the question is flagged as ambiguous.
        """
        t0 = time.perf_counter()
        pred = Prediction(example_id=ex.id, config=self.config, pred_sql="")
        try:
            schema = self.schemas.schema(ex.db_id)
            ddl = to_ddl(schema)
            onto = self.ontology(ex.db_id)
            onto_text = onto.context_text()

            plan = plan_query(ex.question, schema, onto, self.model)
            plan_text = plan.as_text() if plan.key_phrases or plan.tables else ""
            pred.trace["plan"] = plan.raw

            clar_answer = ""
            if self.clarify:
                amb = ambiguity.detect(ex.question, plan, onto)
                pred.flagged_phrases = [p.phrase for p in amb.phrases]
                pred.trace["ambiguity"] = {
                    "flagged": {p.phrase: [c.key for c in p.candidates] for p in amb.phrases},
                    "settled": amb.settled,
                }
                if amb.is_ambiguous:
                    c = clarify.make_clarification(ex.question, amb, onto)
                    if user_reply is not None:
                        clar_answer = user_reply.strip()
                    else:
                        clar_answer = simulated_user.answer(
                            ex, c, mode=self.user_mode, vague_rate=self.vague_rate, seed=self.seed
                        )
                    pred.asked_clarification = True
                    pred.clarification_question = c.text
                    pred.user_answer = clar_answer
                    pred.trace["options"] = [o.key for o in c.options]
                    pred.trace["user_mode"] = "person" if user_reply is not None else self.user_mode
                    # proposal: the answer is appended and the plan is rebuilt
                    plan = plan_query(f"{ex.question} ({clar_answer})", schema, onto, self.model)
                    plan_text = plan.as_text() if plan.key_phrases or plan.tables else ""

            sql = self._generate(ex, ddl, onto_text, plan_text, clar_answer)

            if self.verify:
                db_file = self.schemas.db_file(ex.db_id)
                for _ in range(MAX_REPAIRS):
                    res = verify.verify(sql, schema, db_file)
                    if res.ok:
                        break
                    pred.n_repairs += 1
                    msgs = verify.repair_messages(ex.question, ddl, sql, res)
                    sql = extract_sql(self.model.complete(msgs, temperature=self.temperature))
                pred.trace["final_check"] = verify.verify(sql, schema, db_file).__dict__

            pred.pred_sql = sql
            if not sql:
                pred.error = "no SQL found in model output"
        except NotImplementedError as e:
            raise NotImplementedError(
                f"config {self.config} needs a stage that is not implemented yet: {e}"
            ) from e
        except Exception as e:
            pred.error = f"{type(e).__name__}: {e}"
        pred.latency_s = round(time.perf_counter() - t0, 3)
        return pred


def make_pipeline(
    config: str,
    model: ChatModel,
    schemas: SchemaCache,
    ontology_dir: str | Path,
    user_mode: str = "realistic",
    vague_rate: float = 0.0,
    seed: int = 0,
):
    config = config.upper()
    if config == "A":
        return DirectBaseline(model, schemas)
    if config in ("B", "C", "D"):
        return OntologyPipeline(
            config, model, schemas, ontology_dir, user_mode=user_mode, vague_rate=vague_rate, seed=seed
        )
    raise ValueError(f"unknown config {config}; expected one of {CONFIGS}")
