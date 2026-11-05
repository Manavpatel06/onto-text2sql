import pytest

from ontosql.db import ExecutionError, db_path, execute
from ontosql.eval.exec_match import check, has_top_level_order_by, results_match


def test_multiset_ignores_order_without_order_by():
    assert results_match([(1,), (2,)], [(2,), (1,)], ordered=False)


def test_order_matters_with_order_by():
    assert not results_match([(1,), (2,)], [(2,), (1,)], ordered=True)
    assert results_match([(1,), (2,)], [(1,), (2,)], ordered=True)


def test_duplicates_count():
    assert not results_match([(1,), (1,)], [(1,), (2,)], ordered=False)


def test_column_permutation_accepted():
    assert results_match([("a", 1), ("b", 2)], [(1, "a"), (2, "b")], ordered=False)


def test_numeric_normalization():
    assert results_match([(2.0,)], [(2,)], ordered=False)
    assert results_match([(0.1 + 0.2,)], [(0.3,)], ordered=False)


def test_width_and_length_mismatch():
    assert not results_match([(1, 2)], [(1,)], ordered=False)
    assert not results_match([(1,)], [], ordered=False)
    assert results_match([], [], ordered=False)


def test_top_level_order_by_detection():
    assert has_top_level_order_by("SELECT a FROM t ORDER BY a")
    assert not has_top_level_order_by("SELECT a FROM (SELECT a FROM t ORDER BY a)")
    assert not has_top_level_order_by("SELECT 'ORDER BY' FROM t")


def test_check_end_to_end(spider_dir):
    f = db_path(spider_dir, "shop")
    assert check(f, "SELECT COUNT(*) FROM customers", "SELECT count(*) FROM customers") == (True, True, None)
    valid, correct, err = check(f, "SELECT count(*) FROM orders", "SELECT count(*) FROM customers")
    assert valid and not correct
    valid, correct, err = check(f, "SELECT nope FROM customers", "SELECT name FROM customers")
    assert not valid and not correct and "no such column" in err


def test_gold_failure_is_reported(spider_dir):
    valid, correct, err = check(db_path(spider_dir, "shop"), "SELECT 1", "SELECT broken FROM nowhere")
    assert err.startswith("GOLD FAILED")


def test_database_is_read_only(spider_dir):
    with pytest.raises(ExecutionError):
        execute(db_path(spider_dir, "shop"), "DELETE FROM customers")
    assert execute(db_path(spider_dir, "shop"), "SELECT count(*) FROM customers") == [(3,)]


def test_timeout(spider_dir):
    slow = (
        "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
        "SELECT count(*) FROM c"
    )
    with pytest.raises(ExecutionError, match="timeout"):
        execute(db_path(spider_dir, "shop"), slow, timeout_s=0.2)
