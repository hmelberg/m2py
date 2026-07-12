# MicroPython-modus — design

Dato: 2026-07-12
Status: godkjent av Hans (brainstorming-økt samme dag)

## Mål

En ny redigeringsmodus `micropython` ved siden av Brython-modusen, drevet av den
offisielle MicroPython WebAssembly-porten. Gevinsten er lastetid og kjørefart:
~400 KB wasm som booter på titalls millisekunder (mot Brythons ~800 KB core +
~4 MB stdlib), og en bytekode-VM som kjører rene Python-løkker flere ganger
raskere enn Brython. Hovedbruksområdet er **raske publiserte dashboards med
microdata** — pandas-groupby/filter + plotly + dash som laster nesten
øyeblikkelig.

Vedtatte veivalg:

- **Ny modus ved siden av Brython** — Brython-modusen beholdes uendret.
- **Egne kopier av shimene** i en `micropython/`-mappe; de får divergere fritt
  fra Brython-variantene (ikke felles kilde/kompatlag).
- **V1-omfang = dashboard-kjernen:** pandas, plotly express, dash, duckdb-bro.
  De sju andre shimene (numpy, scipy.stats, statsmodels, matplotlib, seaborn,
  sklearn) porteres senere ved behov.

## Arkitektur

### Motor — `js/micropython-engine.js`

Speiler `js/brython-engine.js` tett; samme offentlige kontrakt:

- `MicroPythonEngine.load()` — én gangs boot. Laster den offisielle wasm-porten
  fra jsdelivr (`@micropython/micropython-webassembly-pyscript`, ES-modul med
  `loadMicroPython()`), henter og kjører `micropython/micropython_runner.py`.
  Merk: ES-modul — lastes med dynamisk `import()`, ikke `addScript()`.
- `MicroPythonEngine.run(script, {loads})` — resolver ALLTID `{text, error}`,
  aldri reject (samme kontrakt som BrythonEngine.run; index.html håndterer bare
  resolved).
- Egen `LIB_REGISTRY` (v1: `pandas_mpy`, `plotly_express_mpy`, `dash`,
  `duckdb_mpy`) med samme `scanImports()`/`ensureLibs()`-mekanikk: lazy fetch av
  `micropython/<navn>.py`, registrering via runnerens `_register_module()` +
  aliaser, `deps` for modulnivå-imports, `js`-deps som `{url, global}`-objekter
  (dash → `js/dash.js` / `Dash`).
- Samme DuckDB-replay-bro som Brython: per-run closure
  `window.__mpyDuckSync(sql)` med cache/pending-kø, pending-markør,
  `MAX_DUCK_PASSES`-replay med `_snapshot()`/`_rollback()`. Gjenbruker
  `__brythonDuck`-hjelperen i index.html (register/query) uendret.
- Utdata er embed-marker-tekst (`__micro_transform_start_` …) slik at
  `buildOutputNodes()`/`renderOutput()` i index.html er uendret.
- Datasett: gjenbruk `buildDatasetSpec`-mønsteret (csv/json/parquet via
  `__brythonParquetColumns`), pluss embed-tags `mpydata_<navn>` for
  publiserte dashboards (parallelt med `brythondata_`).

### Runner — `micropython/micropython_runner.py`

Port av `brython/brython_runner.py` med samme grensesnitt:
`_execute_code`, `_get_last_error`, `_snapshot`/`_rollback`, `_bind_datasets`,
`_register_module`/`_alias_module`, `show()`, samt REPL-semantikken
(trailing-expression-deteksjon). Den compile-baserte logikken (uten `ast`)
fungerer i MicroPython — `compile()`/`eval`-modus støttes i wasm-bygget.
Eksponering mot JS skjer via interpreter-globals (`interpreter.globals.get`)
i stedet for Brythons `runPythonSource`-modulobjekt.

### Shimer — `micropython/`-mappe (kopier)

| Kilde (brython/) | Kopi (micropython/) | Kjente porteringspunkter |
|---|---|---|
| pandas_brython.py | pandas_mpy.py | `from browser import window` → `import js`; `import csv` → polyfill/egen parser; `window.__pyapp_assets`-base64-dekoding via `binascii` |
| plotly_express_brython.py | plotly_express_mpy.py | `from browser import window, document, html` → `js`-ekvivalenter; `datetime`-bruk (linje ~129) sjekkes mot micropython-lib; `re`-bruken (linje ~434) verifiseres mot MicroPythons begrensede re |
| dash.py | dash.py (kopi) | Ren Python over `Dash`-JS-globalen; forventet nesten uendret |
| duckdb_brython.py | duckdb_mpy.py | `window.__brythonDuckSync` → `js.__mpyDuckSync`; JSON-strengkontrakten beholdes |

Dialekt-feller dokumenteres i filhodene etter samme stil som Brython-fellene
(json-floats/null≠None gjelder IKKE MicroPython; nye feller som manglende
`{:,}`-tusenskiller i format-minispråket og re-uten-lookahead føres opp der de
oppdages).

### Modus-registrering (index.html)

- Én rad i `modeRegistry`: `micropython: { id, label: 'MicroPython',
  hlConfig: PY_HL_CFG, handleTab: handlePythonTab, onActivate: load(),
  runSelf: … }` — `runSelf` speiler Brython-radens (DataLoader-resolve,
  purgePlots/tøm output før kjøring, dash-DOM-unntaket ved renderOutput).
- Én rad i `RUNTIME_FOR_MODE`: `micropython: 'micropython'`.
- Modusknapp i velgeren + eksempelseksjon `data-section-mode="micropython"`
  med et lite v1-sett: basics, plotly-galleri, dashboard.
- UI-prinsipp: safestat leder; openstat får modusen via vanlig
  safestat-først-sync (`sync_check.sh`). Ingen hardkodede unntak — eventuell
  gating skjer via samme modus-styrte mekanisme som andre moduser.

## Faseplan

- **Fase 0 (gate):** Last wasm-porten i en testside; kjør den *uporterte*
  pandas-kopien og noter alle feil; mål boot-tid mot Brython. Videre bare hvis
  hullene er polyfill-bare.
- **Fase 1:** Motor + runner + pandas-port → tabeller i output.
- **Fase 2:** plotly express-port → grafer.
- **Fase 3:** dash + duckdb-bro → raskt dashboard (hovedmålet).
- **Fase 4:** Eksempler, `mpydata_`-publisering, felle-dokumentasjon,
  sync til openstat.

## Testing

Speil `brython/tests/`-oppsettet: en `micropython/tests/`-mappe med samme
kjøremønster, minst røyk-tester for pandas-kjernen (read_csv, groupby, filter),
plotly-JSON-generering og duckdb-replay. Fase 0-spiken gir den første
feillisten som testene bygges fra.

## Risikoer og avgrensninger

- **`re`-begrensninger** (ingen lookahead, færre karakterklasser) er største
  tekniske ukjente — avdekkes i fase 0.
- **stdlib-hull:** `csv` og `html` mangler helt; `datetime` bare delvis
  (micropython-lib). Polyfills er små, men reelle arbeidsposter.
- **Format-minispråket** mangler bl.a. `{:,}` — vanlig i statistikkvisning.
- Float er double-presisjon i wasm-bygget (OK for formålet); store heltall
  støttes (mpz).
- De sju øvrige shimene er eksplisitt UTENFOR v1.
- **Koordinering:** dashboard-endringer (pyodide/R får dash) ligger på den
  umergede branchen `dash-v2-runtimes`. MicroPython-modusen skal bygges MOT
  dash.js-API-et slik det ser ut ETTER at den branchen er merget — ikke start
  implementering av fase 3 (og helst ikke index.html-endringene i fase 1) før
  mergen er gjort. Brython-delene er stabile og trygge å kopiere fra nå.
