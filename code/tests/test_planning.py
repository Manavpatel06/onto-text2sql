import json
from pathlib import Path

from ontosql.baseline import SchemaCache
from ontosql.llm import ScriptedModel
from ontosql.ontology import build_turtle
from ontosql.pipeline import OntologyPipeline
from ontosql.planning import QueryPlan, plan_query
from ontosql.schema import extract_schema
from ontosql.db import db_path

from test_ontology import SHOP_CSV


PLAN = {
    "target_attributes": ["orders.order_id"],
    "tables": ["orders"],
    "joins": [],
    "filters": ["date in 2026-10"],
    "aggregation": None,
    "group_by": [],
    "order_by": [],
    "limit": None,
    "key_phrases": [
        {"phrase": "from October", "candidates": ["orders.order_date", "orders.delivery_date"]}
    ],
}


def _onto(spider_dir, tmp_path):
    schema = extract_schema(db_path(spider_dir, "shop"), "shop")
    csv_path = tmp_path / "shop.csv"
    ttl_path = tmp_path / "shop.ttl"
    csv_path.write_text(SHOP_CSV, encoding="utf-8")
    build_turtle(csv_path, schema, ttl_path)
    from ontosql.ontology import load_ontology

    return schema, load_ontology(ttl_path, "shop"), ttl_path.parent


def test_plan_query_parses_json(spider_dir, tmp_path, examples):
    schema, onto, _ = _onto(spider_dir, tmp_path)
    model = ScriptedModel([json.dumps(PLAN)])
    plan = plan_query(examples[2].question, schema, onto, model)
    assert plan.tables == ["orders"]
    assert plan.filters == ["date in 2026-10"]
    assert plan.key_phrases[0].phrase == "from October"
    assert plan.key_phrases[0].candidates == ["orders.order_date", "orders.delivery_date"]
    assert "tables: orders" in plan.as_text()
    assert "filter: date in 2026-10" in plan.as_text()
    assert "Schema descriptions:" in model.calls[0][-1]["content"]
    assert "order date" in model.calls[0][-1]["content"]


def test_malformed_json_falls_back(spider_dir, tmp_path, examples):
    schema, onto, _ = _onto(spider_dir, tmp_path)
    model = ScriptedModel(["not json at all", "still no json"])
    plan = plan_query(examples[2].question, schema, onto, model)
    assert isinstance(plan, QueryPlan)
    assert plan.tables == [] and plan.key_phrases == []
    assert plan.raw == "still no json"
    assert plan.as_text() == ""
    assert len(model.calls) == 2


def test_retry_accepts_second_reply(spider_dir, tmp_path, examples):
    schema, onto, _ = _onto(spider_dir, tmp_path)
    model = ScriptedModel(["nope", "```json\n" + json.dumps(PLAN) + "\n```"])
    plan = plan_query(examples[2].question, schema, onto, model)
    assert plan.tables == ["orders"]
    assert len(model.calls) == 2


def test_config_b_passes_ontology_and_plan_to_sql(spider_dir, tmp_path, examples):
    """Config B is ontology context plus the plan. It must not ask a clarification question."""
    _, _, onto_dir = _onto(spider_dir, tmp_path)
    model = ScriptedModel(
        [
            json.dumps(PLAN),
            "```sql\nSELECT order_id FROM orders WHERE order_date LIKE '2026-10%'\n```",
        ]
    )
    pipe = OntologyPipeline("B", model, SchemaCache(spider_dir), onto_dir)
    pred = pipe.predict(examples[2])
    assert pred.config == "B"
    assert pred.error is None
    assert pred.pred_sql.startswith("SELECT order_id")
    assert pred.asked_clarification is False
    sql_prompt = model.calls[1][-1]["content"]
    assert "Schema descriptions:" in sql_prompt
    assert "order date" in sql_prompt
    assert "Query plan:" in sql_prompt
    assert "tables: orders" in sql_prompt
