"""Unit tests for duckdb_bridge — the pure SQL-parsing + parquet helpers used by
the DuckDB editor mode. No duckdb / no js imports: runs under plain pytest.
See docs/superpowers/specs/2026-06-28-duckdb-mode-design.md.
"""
import io

import pandas as pd

from duckdb_bridge import (
    split_sql_statements,
    extract_referenced_tables,
    extract_created_tables,
    build_preview_select,
    df_to_parquet_bytes,
)


def test_split_basic():
    assert split_sql_statements("SELECT 1; SELECT 2") == ["SELECT 1", "SELECT 2"]


def test_split_trailing_semicolon_and_blanks():
    assert split_sql_statements("SELECT 1;\n\n SELECT 2;\n") == ["SELECT 1", "SELECT 2"]


def test_split_ignores_semicolon_in_string():
    assert split_sql_statements("SELECT ';' AS x; SELECT 2") == ["SELECT ';' AS x", "SELECT 2"]


def test_split_ignores_semicolon_in_line_comment():
    sql = "SELECT 1 -- ; not a split\n; SELECT 2"
    assert split_sql_statements(sql) == ["SELECT 1 -- ; not a split", "SELECT 2"]


def test_split_ignores_semicolon_in_block_comment():
    sql = "SELECT 1 /* a ; b */ ; SELECT 2"
    assert split_sql_statements(sql) == ["SELECT 1 /* a ; b */", "SELECT 2"]


def test_referenced_tables_token_match_case_insensitive():
    sql = "SELECT * FROM Person p JOIN jobb USING (fnr)"
    known = ["person", "jobb", "kjoretoy"]
    assert extract_referenced_tables([sql], known) == ["person", "jobb"]


def test_referenced_tables_word_boundary():
    # 'person_year' must not be matched by the shorter 'person'
    sql = "SELECT * FROM person_year"
    assert extract_referenced_tables([sql], ["person", "person_year"]) == ["person_year"]


def test_referenced_tables_ignores_names_inside_strings_and_comments():
    sql = "SELECT 'person' AS lbl /* jobb */ FROM kjoretoy -- person\n"
    assert extract_referenced_tables([sql], ["person", "jobb", "kjoretoy"]) == ["kjoretoy"]


def test_created_tables_plain():
    assert extract_created_tables(["CREATE TABLE foo AS SELECT 1"]) == ["foo"]


def test_created_tables_or_replace_temp_ifnotexists_quoted():
    stmts = [
        "CREATE OR REPLACE TABLE bar AS SELECT 1",
        'CREATE TEMP TABLE IF NOT EXISTS "baz" AS SELECT 2',
        "create temporary table Qux as select 3",
    ]
    assert extract_created_tables(stmts) == ["bar", "baz", "Qux"]


def test_created_tables_dedup_preserves_order():
    stmts = ["CREATE TABLE a AS SELECT 1", "CREATE OR REPLACE TABLE a AS SELECT 2"]
    assert extract_created_tables(stmts) == ["a"]


def test_preview_select_plain():
    assert build_preview_select(["CREATE TABLE a AS SELECT 1", "SELECT * FROM a"]) == "SELECT * FROM a"


def test_preview_with_cte():
    stmts = ["WITH t AS (SELECT 1 AS n) SELECT n FROM t"]
    assert build_preview_select(stmts) == stmts[0]


def test_preview_none_when_last_is_ddl():
    assert build_preview_select(["SELECT 1", "CREATE TABLE a AS SELECT 1"]) is None


def test_preview_none_when_empty():
    assert build_preview_select([]) is None


def test_parquet_roundtrip_preserves_dtypes_and_nulls():
    df = pd.DataFrame({
        "i": pd.array([1, 2, None], dtype="Int64"),
        "f": [1.5, 2.5, 3.0],
        "s": ["a", None, "c"],
    })
    out = df_to_parquet_bytes(df)
    assert isinstance(out, (bytes, bytearray))
    back = pd.read_parquet(io.BytesIO(out))
    assert list(back.columns) == ["i", "f", "s"]
    assert back["s"].tolist() == ["a", None, "c"]
    assert back["f"].tolist() == [1.5, 2.5, 3.0]


def test_split_handles_escaped_single_quote():
    sql = "SELECT 'it''s; here' AS x; SELECT 2"
    assert split_sql_statements(sql) == ["SELECT 'it''s; here' AS x", "SELECT 2"]


def test_referenced_tables_ignores_table_name_inside_escaped_quote_string():
    sql = "SELECT 'O''Brien jobb' AS lbl FROM person"
    assert extract_referenced_tables([sql], ["person", "jobb"]) == ["person"]
