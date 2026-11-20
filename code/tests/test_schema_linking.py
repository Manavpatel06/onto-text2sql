from ontosql.db import db_path
from ontosql.ontology import build_turtle, load_ontology
from ontosql.schema import extract_schema
from ontosql.schema_linking import (
    BM25, TFIDF, column_docs, gold_columns, margin_flag, ontology_links, ranked, run_ambiguity, run_linking, tokens,
)
from ontosql.types import AMBIGUOUS, CLEAR, Example

from test_ontology import SHOP_CSV


def _setup(spider_dir, tmp_path):
    schema = extract_schema(db_path(spider_dir, "shop"), "shop")
    csv_path, ttl = tmp_path / "shop.csv", tmp_path / "shop.ttl"
    csv_path.write_text(SHOP_CSV, encoding="utf-8")
    build_turtle(csv_path, schema, ttl)
    return schema, load_ontology(ttl, "shop")


def test_gold_columns_skip_join_keys(spider_dir, tmp_path):
    schema, _ = _setup(spider_dir, tmp_path)
    sql = "SELECT T1.name FROM customers AS T1 JOIN orders AS T2 ON T1.customer_id = T2.customer_id WHERE T2.amount > 10"
    assert gold_columns(sql, schema) == {"customers.name", "orders.amount"}
    assert gold_columns("SELECT count(*) FROM customers", schema) == set()


def test_retrieval_ranks_matching_column_first(spider_dir, tmp_path):
    schema, onto = _setup(spider_dir, tmp_path)
    q = tokens("What is the delivery date of each order?")
    for index in (BM25(column_docs(schema, None)), TFIDF(column_docs(schema, onto))):
        assert ranked(index.scores(q))[0] == "orders.delivery_date"


def test_ontology_links_and_runner(spider_dir, tmp_path):
    schema, onto = _setup(spider_dir, tmp_path)
    assert ontology_links("Which customer names are in Tempe?", onto) == ["customers.name"]
    ex = [
        Example("1", "shop", "List the customer names.", "SELECT name FROM customers", source="spider"),
        Example("2", "shop", "Show the delivery dates.", "SELECT delivery_date FROM orders", source="stress"),
    ]
    res = run_linking(ex, {"shop": schema}.get, {"shop": onto}.get)
    assert set(res) == {"spider", "stress", "all"}
    best = res["all"]["Ontology matching (SKOS labels + context rules)"]
    assert best.recall_at[1] == 1.0 and best.f1 == 1.0


def test_ambiguity_baselines(spider_dir, tmp_path):
    schema, onto = _setup(spider_dir, tmp_path)
    amb = Example("a", "shop", "List the orders with a date in October.", "SELECT order_id FROM orders",
                  kind=AMBIGUOUS, source="stress")
    clear = Example("c", "shop", "List the customer names.", "SELECT name FROM customers", kind=CLEAR, source="stress")
    rows = run_ambiguity([amb, clear], [clear], {"shop": schema}.get, {"shop": onto}.get)
    rule = rows[0]
    assert rule["tp"] == 1 and rule["fp"] == 0 and rule["spider_flag_rate"] == 0.0
    assert isinstance(margin_flag(amb.question, BM25(column_docs(schema, onto)), 0.1), bool)
