"""Ambiguity detection, clarification, simulated user, verification and configs C/D."""

import json

import pytest

from ontosql.ambiguity import detect
from ontosql.baseline import SchemaCache
from ontosql.clarify import make_clarification, make_question
from ontosql.db import db_path
from ontosql.llm import ScriptedModel
from ontosql.ontology import build_turtle, load_ontology
from ontosql.pipeline import make_pipeline
from ontosql.schema import extract_schema
from ontosql.simulated_user import answer, leaks
from ontosql.types import AMBIGUOUS, CLEAR, Example
from ontosql.verify import repair_messages, verify

from test_ontology import SHOP_CSV

DATE_Q = "List the orders with a date in October 2026."
AMB = Example(
    "amb-date", "shop", DATE_Q,
    "SELECT order_id FROM orders WHERE order_date LIKE '2026-10%'",
    kind=AMBIGUOUS, source="stress", ambiguity_type="temporal", ambiguous_phrase="date",
    interpretations=[
        {"id": "placed", "description": "orders placed in October 2026",
         "sql": "SELECT order_id FROM orders WHERE order_date LIKE '2026-10%'"},
        {"id": "delivered", "description": "orders delivered in October 2026",
         "sql": "SELECT order_id FROM orders WHERE delivery_date LIKE '2026-10%'"},
    ],
    intended="placed",
)
CLEAR_EX = Example("clear-1", "shop", "How many customers are there?", "SELECT count(*) FROM customers",
                   kind=CLEAR, source="stress")


@pytest.fixture
def shop(spider_dir, tmp_path):
    schema = extract_schema(db_path(spider_dir, "shop"), "shop")
    csv_path, ttl = tmp_path / "shop.csv", tmp_path / "shop.ttl"
    csv_path.write_text(SHOP_CSV, encoding="utf-8")
    build_turtle(csv_path, schema, ttl)
    return schema, load_ontology(ttl, "shop"), tmp_path


# ------------------------------------------------------------- ambiguity

def test_shared_synonym_is_ambiguous(shop):
    _, onto, _ = shop
    res = detect(DATE_Q, None, onto)
    assert res.is_ambiguous and res.score == 1
    assert res.phrases[0].phrase == "date"
    assert {c.key for c in res.phrases[0].candidates} == {"orders.order_date", "orders.delivery_date"}


def test_preferred_label_settles(shop):
    _, onto, _ = shop
    assert not detect("List the orders with a delivery date in October.", None, onto).is_ambiguous


def test_distinctive_word_settles(shop):
    _, onto, _ = shop
    res = detect("Which orders were delivered, and on what date?", None, onto)
    assert not res.is_ambiguous


def test_aggregate_word(shop):
    _, onto, _ = shop
    res = detect("What is the total for the orders?", None, onto)
    assert res.is_ambiguous and res.phrases[0].kind == "aggregation"
    assert not detect("How many orders are there in total?", None, onto).is_ambiguous
    assert not detect("What is the total order amount?", None, onto).is_ambiguous


# ------------------------------------------------------------- clarification + simulated user

def test_clarification_names_both_readings(shop):
    _, onto, _ = shop
    c = make_clarification(DATE_Q, detect(DATE_Q, None, onto), onto)
    assert '"date"' in c.text and "order date" in c.text and "delivery date" in c.text
    assert {o.key for o in c.options} == {"orders.order_date", "orders.delivery_date"}
    assert make_question(DATE_Q, detect(DATE_Q, None, onto), onto) == c.text


def test_simulated_user_modes(shop):
    _, onto, _ = shop
    c = make_clarification(DATE_Q, detect(DATE_Q, None, onto), onto)
    real = answer(AMB, c)
    assert "placed" in real and not leaks(real, AMB)
    assert "delivered" in answer(AMB, c, mode="wrong")
    assert "placed" in answer(AMB, c, mode="oracle")
    # all replies vague at rate 1.0, none of them informative
    assert "placed" not in answer(AMB, c, vague_rate=1.0)
    # clear question asked anyway: no new information
    assert "placed" not in answer(CLEAR_EX, c) and "customer" not in answer(CLEAR_EX, c).lower()


def test_user_says_neither_when_options_miss(shop):
    _, onto, _ = shop
    c = make_clarification(DATE_Q, detect(DATE_Q, None, onto), onto)
    c.options = [o for o in c.options if o.key == "orders.delivery_date"]
    reply = answer(AMB, c)
    assert "placed" not in reply and "delivered" not in reply


def test_leak_check():
    assert leaks("I mean order_date", AMB)
    assert leaks("SELECT order_id FROM orders", AMB)
    assert not leaks("I mean the address where the student lives now.", AMB)


# ------------------------------------------------------------- verification

def test_verify_checks(spider_dir, shop):
    schema, _, _ = shop
    f = db_path(spider_dir, "shop")
    assert verify("SELECT name FROM customers", schema, f).ok
    assert verify("SELECT T1.name FROM customers AS T1 JOIN orders AS T2 ON T1.customer_id = T2.customer_id", schema, f).ok
    assert verify("SELEC name FROM customers", schema, f).stage == "syntax"
    r = verify("SELECT nmae FROM customers", schema, f)
    assert r.stage == "schema" and "did you mean name" in r.message
    assert verify("SELECT name FROM customer", schema, f).stage == "schema"
    assert verify("DELETE FROM customers", schema, f).stage == "syntax"
    assert verify("SELECT name FROM customers WHERE city > (SELECT 1, 2)", schema, f).stage == "execution"
    msgs = repair_messages("q?", "DDL", "SELECT nmae FROM customers", r)
    assert "did you mean name" in msgs[-1]["content"] and "SELECT nmae" in msgs[-1]["content"]


# ------------------------------------------------------------- configs C and D end to end

PLAN = json.dumps({"tables": ["orders"], "target_attributes": ["orders.order_id"], "key_phrases": []})


def _model_for(sqls):
    """Plan requests get a plan; SQL requests pop the next scripted query."""
    queue = list(sqls)

    def fn(messages):
        if "JSON" in messages[0]["content"]:
            return PLAN
        return f"```sql\n{queue.pop(0)}\n```"

    return ScriptedModel(fn=fn)


def test_config_c_asks_and_uses_answer(spider_dir, shop):
    _, _, onto_dir = shop
    model = _model_for(["SELECT order_id FROM orders WHERE order_date LIKE '2026-10%'"])
    pred = make_pipeline("C", model, SchemaCache(spider_dir), onto_dir).predict(AMB)
    assert pred.error is None and pred.asked_clarification
    assert "placed" in pred.user_answer
    assert pred.trace["options"]
    sql_prompt = model.calls[-1][-1]["content"]
    assert "Clarification from the user" in sql_prompt and "placed" in sql_prompt


def test_config_c_does_not_ask_clear(spider_dir, shop):
    _, _, onto_dir = shop
    model = _model_for(["SELECT count(*) FROM customers"])
    pred = make_pipeline("C", model, SchemaCache(spider_dir), onto_dir).predict(CLEAR_EX)
    assert not pred.asked_clarification and pred.pred_sql == "SELECT count(*) FROM customers"


def test_config_d_repairs(spider_dir, shop):
    _, _, onto_dir = shop
    model = _model_for(["SELECT count(*) FROM customer", "SELECT count(*) FROM customers"])
    pred = make_pipeline("D", model, SchemaCache(spider_dir), onto_dir).predict(CLEAR_EX)
    assert pred.n_repairs == 1 and pred.pred_sql == "SELECT count(*) FROM customers"
    assert pred.trace["final_check"]["ok"] is True
    assert "did you mean customers" in model.calls[-1][-1]["content"]
