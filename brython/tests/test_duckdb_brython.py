# Enhetstester for duckdb_brython med injisert executor (CPython).
# Browser-broen (window.__brythonDuckSync) emuleres med et fake window-objekt.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
import duckdb_brython as duckdb
import pandas_brython as pd


@pytest.fixture(autouse=True)
def _reset_hooks():
    duckdb._executor = None
    saved_window = duckdb._window
    yield
    duckdb._executor = None
    duckdb._window = saved_window


COLS = {'navn': ['a', 'b', 'c'], 'verdi': [1, 2, None]}


def test_sql_returns_relation_with_columns_in_order():
    duckdb._executor = lambda q: dict(COLS)
    rel = duckdb.sql('SELECT * FROM t')
    assert rel.columns == ['navn', 'verdi']


def test_fetchall_row_tuples_and_fetchone():
    duckdb._executor = lambda q: dict(COLS)
    rel = duckdb.sql('SELECT * FROM t')
    assert rel.fetchall() == [('a', 1), ('b', 2), ('c', None)]
    assert rel.fetchone() == ('a', 1)


def test_fetchone_empty_result_is_none():
    duckdb._executor = lambda q: {'x': []}
    assert duckdb.sql('SELECT 1 WHERE false').fetchone() is None
    assert duckdb.sql('SELECT 1 WHERE false').fetchall() == []


def test_df_converts_none_to_nan():
    duckdb._executor = lambda q: dict(COLS)
    df = duckdb.sql('SELECT * FROM t').df()
    assert list(df.columns) == ['navn', 'verdi']
    vals = list(df['verdi'])
    assert vals[0] == 1 and vals[1] == 2
    assert pd.isna(vals[2])


def test_fetchdf_is_df_alias_and_to_html_renders_table():
    duckdb._executor = lambda q: dict(COLS)
    rel = duckdb.sql('SELECT * FROM t')
    assert rel.fetchdf().shape == rel.df().shape
    assert '<table' in rel.to_html()
    assert 'navn' in rel.to_html()


def test_query_alias_and_connect_surface():
    duckdb._executor = lambda q: {'n': [7]}
    assert duckdb.query('SELECT 7').fetchone() == (7,)
    con = duckdb.connect()
    assert con.sql('SELECT 7').fetchone() == (7,)
    assert con.query('SELECT 7').fetchone() == (7,)
    assert con.execute('SELECT 7').fetchone() == (7,)
    con.close()
    with duckdb.connect() as c2:
        assert c2.sql('SELECT 7').fetchone() == (7,)


def test_executor_receives_query_text():
    seen = []

    def ex(q):
        seen.append(q)
        return {'x': [1]}

    duckdb._executor = ex
    duckdb.sql('SELECT 42')
    assert seen == ['SELECT 42']


def test_sql_rejects_nonstring_and_empty():
    duckdb._executor = lambda q: {}
    with pytest.raises(TypeError):
        duckdb.sql(123)
    with pytest.raises(ValueError):
        duckdb.sql('   ')


def test_no_executor_outside_browser_raises_norwegian():
    with pytest.raises(RuntimeError) as e:
        duckdb.sql('SELECT 1')
    assert 'nettleseren' in str(e.value)


def _wire_fake_window(responses):
    class _FakeWindow:
        pass

    w = _FakeWindow()
    w.calls = []

    def sync(q):
        w.calls.append(q)
        # protokollen er alltid en JSON-streng; miss = {"pending": true}
        return responses.get(q, '{"pending": true}')

    setattr(w, '__brythonDuckSync', sync)
    return w


def test_browser_cache_miss_raises_pending():
    duckdb._window = _wire_fake_window({})
    with pytest.raises(duckdb._PendingSQL):
        duckdb.sql('SELECT 1')


def test_pending_is_baseexception_not_exception():
    assert issubclass(duckdb._PendingSQL, BaseException)
    assert not issubclass(duckdb._PendingSQL, Exception)
    assert duckdb._PendingSQL.__brython_pending__ is True


def test_browser_cache_hit_returns_cols():
    duckdb._window = _wire_fake_window({'SELECT 1': '{"cols": {"a": [1]}}'})
    assert duckdb.sql('SELECT 1').fetchall() == [(1,)]


def test_browser_cached_error_raises_runtime_norwegian():
    duckdb._window = _wire_fake_window({'SELECT x': '{"error": "Binder Error: x"}'})
    with pytest.raises(RuntimeError) as e:
        duckdb.sql('SELECT x')
    assert 'duckdb-feil' in str(e.value)
