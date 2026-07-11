# duckdb_brython.py — duckdb-API-subsett for Brython-modus.
# duckdb.sql("SELECT ...").df() over appens delte DuckDB-WASM-instans.
#
# Async-broen: DuckDB-WASM er asynkron (worker), brukerkoden kjører synkront.
# _run_sql slår synkront opp i motorens per-run-cache (window.__brythonDuckSync);
# ved miss er spørringen lagt i kø og vi kaster _PendingSQL. Motoren
# (js/brython-engine.js) kjører køen mot DuckDB, cacher resultatene og
# RE-KJØRER hele scriptet (replay) — neste pass finner svaret i cachen.
#
# NB: alle "tilkoblinger" deler appens ene DuckDB-katalog. Tabeller fra
# CREATE TABLE overlever til neste SQL-modus-kjøring rydder katalogen —
# bruk CREATE OR REPLACE TABLE i scripts som skal kjøres flere ganger.
import json as _json
import pandas_brython as _pd

try:
    from browser import window as _window   # Brython (nettleser)
except ImportError:                          # CPython (pytest)
    _window = None

# CPython-krok for tester: funksjon sql-tekst -> {kolonne: [verdier]}
_executor = None


class _PendingSQL(BaseException):
    """Replay-signal til motoren. BaseException med vilje: brukerkodens
    `except Exception` skal ikke sluke signalet. Runneren gjenkjenner
    attributtet __brython_pending__ (generisk protokoll, se _execute_code)."""
    __brython_pending__ = True


def _run_sql(q):
    if _executor is not None:
        return _executor(q)
    if _window is None:
        raise RuntimeError('duckdb_brython kan ikke kjøre SQL utenfor '
                           'nettleseren (sett duckdb_brython._executor i tester)')
    # Protokollen er ALLTID en JSON-streng ({pending}|{cols}|{error}) —
    # JS null krysser IKKE til Python None i Brython 3.12 (verifisert),
    # så et null-for-miss-design ville feilet stille.
    d = _json.loads(_window.__brythonDuckSync(q))
    if d.get('pending'):       # ikke i cache — motoren har lagt den i kø
        raise _PendingSQL(q)
    if d.get('error') is not None:
        raise RuntimeError('duckdb-feil: ' + str(d['error']))
    # Brython-felle (verifisert 2026-07-11): json.loads gir JS-backede
    # floats som knekker format('g') — og aritmetikk vasker IKKE taint.
    # Kun str-rundtur gir en ekte float (tapsfritt: str(float) er repr).
    return {k: [float(str(v)) if isinstance(v, float) else v for v in vals]
            for k, vals in d['cols'].items()}


class Relation:
    """Resultatet av duckdb.sql(...): kolonnedata med pandas-uthenting."""

    def __init__(self, cols, sql_text):
        self._cols = cols
        self._sql = sql_text

    @property
    def columns(self):
        return list(self._cols.keys())

    def fetchall(self):
        names = list(self._cols.keys())
        if not names:
            return []
        n = len(self._cols[names[0]])
        return [tuple(self._cols[c][i] for c in names) for i in range(n)]

    def fetchone(self):
        rows = self.fetchall()
        return rows[0] if rows else None

    def df(self):
        # None (SQL NULL via JSON) -> pandas_brython-nan, som i _bind_datasets
        cols = {k: [_pd.nan if v is None else v for v in vals]
                for k, vals in self._cols.items()}
        return _pd.DataFrame(cols)

    fetchdf = df

    def to_html(self):
        return self.df().to_html()

    def __repr__(self):
        names = list(self._cols.keys())
        n = len(self._cols[names[0]]) if names else 0
        return '<duckdb_brython.Relation: %d rader, kolonner %r>' % (n, names)


def _sql_impl(q):
    if not isinstance(q, str):
        raise TypeError('duckdb.sql: spørringen må være en streng')
    if not q.strip():
        raise ValueError('duckdb.sql: tom spørring')
    return Relation(_run_sql(q), q)


def sql(q):
    return _sql_impl(q)


query = sql


class _Connection:
    """Minimal connect()-flate for opplæringskode; deler appens katalog.
    Metodene kaller _sql_impl, ALDRI globale sql()/query() — Brython-felle 1
    (metodenavn == globalt funksjonsnavn blir stille no-op)."""

    def sql(self, q):
        return _sql_impl(q)

    def query(self, q):
        return _sql_impl(q)

    def execute(self, q):
        return _sql_impl(q)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def connect(*args, **kwargs):
    return _Connection()
