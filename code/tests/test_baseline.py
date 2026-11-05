from ontosql.baseline import DirectBaseline, SchemaCache
from ontosql.db import db_path
from ontosql.llm import ScriptedModel
from ontosql.prompts import extract_sql
from ontosql.schema import extract_schema, to_ddl


def test_extract_sql_variants():
    assert extract_sql("```sql\nSELECT a FROM t;\n```") == "SELECT a FROM t"
    assert extract_sql("SQL: select a\nfrom t") == "select a from t"
    assert extract_sql("Here you go:\n```\nSELECT 1\n```\nThis counts rows.") == "SELECT 1"
    assert extract_sql("SELECT a FROM t\n\nThis query returns a.") == "SELECT a FROM t"
    assert extract_sql("WITH x AS (SELECT 1) SELECT * FROM x;") == "WITH x AS (SELECT 1) SELECT * FROM x"
    assert extract_sql("I cannot answer that.") == ""
    assert extract_sql("") == ""


def test_schema_extraction(spider_dir):
    s = extract_schema(db_path(spider_dir, "shop"), "shop")
    assert [t.name for t in s.tables] == ["customers", "orders"]
    assert s.has_column("orders", "delivery_date")
    assert not s.has_column("orders", "ship_date")
    fk = s.foreign_keys[0]
    assert (fk.table, fk.column, fk.ref_table, fk.ref_column) == ("orders", "customer_id", "customers", "customer_id")
    ddl = to_ddl(s)
    assert "CREATE TABLE orders" in ddl
    assert "FOREIGN KEY (customer_id) REFERENCES customers(customer_id)" in ddl


def test_baseline_prompt_and_prediction(spider_dir, examples):
    model = ScriptedModel(["```sql\nSELECT count(*) FROM customers;\n```"])
    pipe = DirectBaseline(model, SchemaCache(spider_dir))
    p = pipe.predict(examples[0])
    assert p.config == "A"
    assert p.pred_sql == "SELECT count(*) FROM customers"
    assert p.error is None and not p.asked_clarification
    user_msg = model.calls[0][-1]["content"]
    assert "CREATE TABLE customers" in user_msg
    assert examples[0].question in user_msg
    # the baseline must not see any ontology or plan context
    assert "Schema descriptions" not in user_msg and "Query plan" not in user_msg


def test_baseline_records_failures(spider_dir, examples):
    pipe = DirectBaseline(ScriptedModel(["Sorry, I don't know."]), SchemaCache(spider_dir))
    p = pipe.predict(examples[0])
    assert p.pred_sql == "" and "no SQL" in p.error

    def boom(_):
        raise RuntimeError("503")

    p = DirectBaseline(ScriptedModel(fn=boom), SchemaCache(spider_dir)).predict(examples[0])
    assert p.pred_sql == "" and "llm error" in p.error


def test_extract_sql_ignores_reasoning_block():
    reply = "<think>Maybe SELECT * FROM x?</think>\n```sql\nSELECT name FROM Dogs\n```"
    assert extract_sql(reply) == "SELECT name FROM Dogs"
