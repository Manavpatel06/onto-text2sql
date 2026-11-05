import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ontosql.types import AMBIGUOUS, CLEAR, Example  # noqa: E402


def _build_shop(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY,
            name TEXT,
            city TEXT
        );
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            customer_id INTEGER REFERENCES customers(customer_id),
            order_date TEXT,
            delivery_date TEXT,
            amount REAL
        );
        INSERT INTO customers VALUES (1, 'Ana', 'Tempe'), (2, 'Bo', 'Mesa'), (3, 'Cy', 'Tempe');
        INSERT INTO orders VALUES
            (10, 1, '2026-09-28', '2026-10-02', 20.0),
            (11, 1, '2026-10-05', '2026-10-09', 35.5),
            (12, 2, '2026-10-20', '2026-11-01', 12.0),
            (13, 3, '2026-09-15', '2026-09-30', 50.0);
        """
    )
    conn.commit()
    conn.close()


@pytest.fixture
def spider_dir(tmp_path: Path) -> Path:
    _build_shop(tmp_path / "database" / "shop" / "shop.sqlite")
    return tmp_path


@pytest.fixture
def examples() -> list[Example]:
    return [
        Example("c1", "shop", "How many customers are there?", "SELECT count(*) FROM customers",
                kind=CLEAR, source="stress"),
        Example("c2", "shop", "List customer names in Tempe.",
                "SELECT name FROM customers WHERE city = 'Tempe'", kind=CLEAR, source="stress"),
        Example(
            "a1", "shop", "Show the orders from October 2026.",
            "SELECT order_id FROM orders WHERE order_date LIKE '2026-10%'",
            kind=AMBIGUOUS, source="stress", ambiguity_type="temporal", ambiguous_phrase="from October",
            interpretations=[
                {"id": "placed", "description": "orders placed in October",
                 "sql": "SELECT order_id FROM orders WHERE order_date LIKE '2026-10%'"},
                {"id": "delivered", "description": "orders delivered in October",
                 "sql": "SELECT order_id FROM orders WHERE delivery_date LIKE '2026-10%'"},
            ],
            intended="placed",
        ),
        Example(
            "a2", "shop", "What is the total for each customer?",
            "SELECT customer_id, sum(amount) FROM orders GROUP BY customer_id",
            kind=AMBIGUOUS, source="stress", ambiguity_type="aggregation", ambiguous_phrase="total",
            interpretations=[
                {"id": "sum", "description": "sum of order amounts",
                 "sql": "SELECT customer_id, sum(amount) FROM orders GROUP BY customer_id"},
                {"id": "count", "description": "number of orders",
                 "sql": "SELECT customer_id, count(*) FROM orders GROUP BY customer_id"},
            ],
            intended="sum",
        ),
    ]
