from pathlib import Path

import pytest
from rdflib import Graph

from ontosql.db import db_path
from ontosql.ontology import build_turtle, load_ontology
from ontosql.schema import extract_schema

SHOP_CSV = """table,column,pref_label,alt_labels,definition
customers,,customer,,A person who places orders.
customers,name,customer name,name,Name of the customer.
customers,city,city,,City where the customer lives.
orders,order_date,order date,date|purchase date,Date the customer placed the order.
orders,delivery_date,delivery date,date|arrival date,Date the order reached the customer.
orders,amount,order amount,amount|total,Amount charged for the order.
"""


def _shop(spider_dir: Path):
    return extract_schema(db_path(spider_dir, "shop"), "shop")


def _round_trip(spider_dir: Path, tmp_path: Path):
    csv_path = tmp_path / "shop.csv"
    ttl_path = tmp_path / "shop.ttl"
    csv_path.write_text(SHOP_CSV, encoding="utf-8")
    build_turtle(csv_path, _shop(spider_dir), ttl_path)
    Graph().parse(ttl_path, format="turtle")
    return load_ontology(ttl_path, "shop")


def test_csv_ttl_round_trip_keeps_labels(spider_dir, tmp_path):
    onto = _round_trip(spider_dir, tmp_path)
    by_key = {e.key: e for e in onto.entries}
    assert by_key["orders.order_date"].pref_label == "order date"
    assert by_key["orders.order_date"].alt_labels == ["date", "purchase date"]
    assert "placed the order" in by_key["orders.order_date"].definition
    assert by_key["orders.delivery_date"].pref_label == "delivery date"
    assert by_key["customers"].pref_label == "customer"
    text = onto.context_text()
    assert 'orders.order_date - "order date" (also: date, purchase date):' in text


def test_lookup_shared_synonym_and_specific_label(spider_dir, tmp_path):
    onto = _round_trip(spider_dir, tmp_path)
    dates = {e.key for e in onto.lookup("date")}
    assert dates == {"orders.order_date", "orders.delivery_date"}
    assert {e.key for e in onto.lookup("dates")} == dates
    assert [e.key for e in onto.lookup("delivery date")] == ["orders.delivery_date"]
    assert onto.lookup("not a column") == []


def test_unknown_column_raises(spider_dir, tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "table,column,pref_label,alt_labels,definition\norders,ship_date,ship date,,When it shipped.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown column"):
        build_turtle(csv_path, _shop(spider_dir), tmp_path / "bad.ttl")
