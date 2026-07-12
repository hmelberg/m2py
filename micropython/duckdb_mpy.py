# duckdb_mpy.py — duckdb-API-subsett for MicroPython-modus.
# duckdb.sql("SELECT ...").df() over appens delte DuckDB-WASM-instans.
#
# Divergerende kopi av brython/duckdb_brython.py (kopiert 2026-07-12, Task 6).
# Denne fila kjører under unix-micropython/wasm-micropython (Task 3-motoren),
# IKKE under Brython. Endringer her skal IKKE flyte tilbake til
# duckdb_brython.py uten separat vurdering.
#
# Dialektfeller fikset i denne porten (se micropython/pandas_mpy.py filhode
# for den fulle fellelisten fra Task 4 — dette er de som traff denne fila):
#   1. `from browser import window`: Brython-spesifikk. MicroPython-motoren
#      (js/micropython-engine.js) eksponerer bro-globalen på `js`-modulen
#      (jsffi), ikke `browser`. Erstattet med try/except-shim rundt
#      `import js as _js`; CPython (pytest) mangler ekte `js`-modul.
#   2. Float-str-rundturen i _run_sql (Brython-felle: json.loads gir
#      JS-backede floats som knekker format('g')) er FJERNET — fase 0
#      verifiserte at MicroPythons json.loads gir ekte Python-floats
#      (c_json_floats: OK i både unix- og wasm-bygg, se NOTAT_fase0.md).
#   3. Repo-spesifikk CPython-testfelle (IKKE en MicroPython-dialektfelle,
#      men verifisert nødvendig ved `python3 -m pytest ... ` fra repo-roten):
#      repo-roten har en `js/`-mappe (js/dash.js, js/micropython-engine.js,
#      ...) uten `__init__.py`. Når pytest kjøres via `python3 -m pytest`
#      legges repo-roten på sys.path, og CPython finner da `js/` som et
#      TOMT namespace-package — `import js as _js` "lykkes" stille, uten
#      feil, selv uten nettleser. Samme mekanisme rammet
#      pandas_mpy.py (se dens filhode); der løses det av at
#      `from js import window` feiler videre (ekte ImportError). Her
#      brukes samme knep: `_js.window` tvinger fram AttributeError på
#      namespace-pakken (den mangler attributtet), mens ekte
#      jsffi/pyodide-js-moduler i nettleseren har et ekte `window`.
#
# Async-broen: DuckDB-WASM er asynkron (worker), brukerkoden kjører synkront.
# _run_sql slår synkront opp i motorens per-run-cache (js.__mpyDuckSync);
# ved miss er spørringen lagt i kø og vi kaster _PendingSQL. Motoren
# (js/micropython-engine.js) kjører køen mot DuckDB, cacher resultatene og
# RE-KJØRER hele scriptet (replay) — neste pass finner svaret i cachen.
#
# NB: alle "tilkoblinger" deler appens ene DuckDB-katalog. Tabeller fra
# CREATE TABLE overlever til neste SQL-modus-kjøring rydder katalogen —
# bruk CREATE OR REPLACE TABLE i scripts som skal kjøres flere ganger.
import json as _json
import pandas_mpy as _pd

try:
    import js as _js                 # MicroPython (og Pyodide)
    _js.window                       # felle 3 (se filhode): tving fram AttributeError
                                      # på repo-rotens js/-navnerompakke under CPython
except (ImportError, AttributeError):  # CPython (pytest)
    _js = None

# CPython-krok for tester: funksjon sql-tekst -> {kolonne: [verdier]}
_executor = None


class _PendingSQL(BaseException):
    """Replay-signal til motoren. BaseException med vilje: brukerkodens
    `except Exception` skal ikke sluke signalet. Runneren gjenkjenner
    attributtet __brython_pending__ (generisk protokoll — delt med
    duckdb_brython.py/brython_runner.py, se _execute_code)."""
    __brython_pending__ = True


def _run_sql(q):
    if _executor is not None:
        return _executor(q)
    if _js is None:
        raise RuntimeError('duckdb_mpy kan ikke kjøre SQL utenfor '
                           'nettleseren (sett duckdb_mpy._executor i tester)')
    # Protokollen er ALLTID en JSON-streng ({pending}|{cols}|{error}) —
    # samme kontrakt som Brython-broen (window.__brythonDuckSync), se
    # duckdb_brython.py-kommentaren for begrunnelsen.
    d = _json.loads(_js.__mpyDuckSync(q))
    if d.get('pending'):       # ikke i cache — motoren har lagt den i kø
        raise _PendingSQL(q)
    if d.get('error') is not None:
        raise RuntimeError('duckdb-feil: ' + str(d['error']))
    return d['cols']


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
        # None (SQL NULL via JSON) -> pandas_mpy-nan, som i _bind_datasets
        cols = {k: [_pd.nan if v is None else v for v in vals]
                for k, vals in self._cols.items()}
        return _pd.DataFrame(cols)

    fetchdf = df

    def to_html(self):
        return self.df().to_html()

    def __repr__(self):
        names = list(self._cols.keys())
        n = len(self._cols[names[0]]) if names else 0
        return '<duckdb_mpy.Relation: %d rader, kolonner %r>' % (n, names)


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
