# Differensialtester: samme SQL gjennom duckdb_brython (med executor koblet
# til EKTE duckdb, konvertert til kolonnedict slik __arrowToColumns gjør)
# skal gi samme rader/kolonner som ekte duckdb direkte.
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from decimal import Decimal
import pytest

real_duckdb = pytest.importorskip('duckdb')
import duckdb_brython
import pandas_brython as pd

SETUP = [
    "CREATE OR REPLACE TABLE folk (navn VARCHAR, alder INT, lonn DOUBLE)",
    "INSERT INTO folk VALUES ('Kari', 34, 550000.0), ('Ola', 51, NULL), "
    "('Per', 34, 480000.5), ('Anne', 28, 610000.0)",
]


@pytest.fixture()
def con():
    c = real_duckdb.connect()
    for s in SETUP:
        c.execute(s)
    prev = duckdb_brython._executor

    def ex(q):
        cur = c.execute(q)
        cols = [d[0] for d in cur.description] if cur.description else []
        out = {name: [] for name in cols}
        for row in cur.fetchall():
            for name, v in zip(cols, row):
                if isinstance(v, Decimal):
                    v = float(v)          # speiler __decimalToNumber i JS
                out[name].append(v)
        return out

    duckdb_brython._executor = ex
    yield c
    duckdb_brython._executor = prev
    c.close()


def test_select_star_matches_real(con):
    q = 'SELECT * FROM folk ORDER BY navn'
    ours = duckdb_brython.sql(q)
    theirs = con.execute(q)
    assert ours.columns == [d[0] for d in theirs.description]
    assert ours.fetchall() == theirs.fetchall()


def test_groupby_aggregate_matches_real(con):
    q = ('SELECT alder, count(*) AS n, sum(lonn) AS sumlonn '
         'FROM folk GROUP BY alder ORDER BY alder')
    ours = duckdb_brython.sql(q).fetchall()
    theirs = [tuple(float(v) if isinstance(v, Decimal) else v for v in r)
              for r in con.execute(q).fetchall()]
    assert ours == theirs


def test_df_matches_real_df_with_nan_for_null(con):
    q = 'SELECT navn, lonn FROM folk ORDER BY navn'
    ours = duckdb_brython.sql(q).df()
    theirs = con.execute(q).df()
    assert list(ours.columns) == list(theirs.columns)
    ours_lonn = list(ours['lonn'])
    theirs_lonn = list(theirs['lonn'])
    for o, t in zip(ours_lonn, theirs_lonn):
        if isinstance(t, float) and math.isnan(t):
            assert pd.isna(o)
        else:
            assert o == t
    assert list(ours['navn']) == list(theirs['navn'])


def test_fetchone_matches_real(con):
    q = 'SELECT count(*) FROM folk'
    assert duckdb_brython.sql(q).fetchone() == con.execute(q).fetchone()


def test_where_and_expressions_match_real(con):
    q = ("SELECT navn, alder * 2 AS dobbel FROM folk "
         "WHERE lonn IS NOT NULL AND alder BETWEEN 30 AND 40 ORDER BY navn")
    assert duckdb_brython.sql(q).fetchall() == con.execute(q).fetchall()
