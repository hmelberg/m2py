// Dedikert Pyodide-worker for lokale STRICT-kjøringer (spec 2026-07-05-
// browser-strict-execution §V4): rammer og klartekst finnes bare i denne
// workeren, aldri i hovedtråden — innsyn krever debugger mot workeren, ikke
// bare konsollen. Selvstendig: laster egen Pyodide + pandas + cryptography +
// safepy.zip ved første kjøring, gjenbrukes varm etterpå.
'use strict';

var pyReady = null;

function ensurePy(pyodideURL, zipURL) {
  if (pyReady) return pyReady;
  pyReady = (async function () {
    importScripts(pyodideURL + 'pyodide.js');
    var py = await loadPyodide({ indexURL: pyodideURL });
    // pandas/cryptography/scipy/statsmodels/sqlite3 er offisielle Pyodide-
    // pakker; lifelines/pyfixest er rene python-pakker som må via micropip.
    // Uten disse feiler ols/logit/poisson/anova/corr_test (statsmodels) og
    // cox/kaplan_meier/logrank/rmst/weibull_aft (lifelines) med
    // ModuleNotFoundError i en STRICT-kjøring — se
    // docs/superpowers/2026-07-05-remaining-roadmap.md §3. sqlite3 er
    // uvendret fra Pyodides stdlib på denne pinnede versjonen (2026-07-08 —
    // dialect="sqlite", se safepy/sqlite_api.py) — uten den feiler enhver
    // strict-kjøring i denne workeren med kun krypterte kilder (fsLoads=
    // false) med "ModuleNotFoundError: No module named 'sqlite3'".
    await py.loadPackage(['pandas', 'cryptography', 'scipy', 'statsmodels', 'sqlite3', 'micropip']);
    await py.runPythonAsync('import micropip as _mp\nawait _mp.install("lifelines")');
    try {
      await py.runPythonAsync('import micropip as _mp\nawait _mp.install("pyfixest")');
    } catch (e) {
      // pyfixest sine avhengigheter (f.eks. maketables/narwhals) er ikke
      // nødvendigvis tilgjengelige i Pyodide ennå — degrader stille her;
      // feols/fepois gir en tydelig feilmelding når de faktisk kalles.
    }
    // KJENT, IKKE FIKSET HER (2026-07-08 — funnet ved siden av sqlite3-
    // fiksen over, ikke forårsaket av den): buildStrictGlue kaller
    // _pd.read_parquet(_buf) også for KRYPTERTE kilder (safepy-enc-v1) med
    // format="parquet" — denne workeren har ingen pyarrow-install/patch
    // (index.html sin ensurePyarrowFor, kun for hovedtråden). En strict-
    // kjøring med bare krypterte parquet-kilder (fsLoads=false, altså denne
    // workeren) feiler derfor trolig med samme "pyarrow required"-feil som
    // hovedtråden hadde før ensurePyarrowFor — uprøvd/upåvirket av dagens
    // endring, siden ingen av dagens tester går via denne banen.
    var resp = await fetch(zipURL);
    if (!resp.ok) throw new Error('kunne ikke laste strict-motoren — prøv igjen');
    py.unpackArchive(await resp.arrayBuffer(), 'zip', { extractDir: '/home/pyodide/' });
    py.runPython("import sys\nsys.path.insert(0, '/home/pyodide')");
    return py;
  })().catch(function (e) {
    pyReady = null;   // ikke cache en feilet init — «prøv igjen» skal faktisk prøve igjen
    throw e;
  });
  return pyReady;
}

self.onmessage = async function (ev) {
  var msg = ev.data || {};
  try {
    var py = await ensurePy(msg.pyodideURL, msg.zipURL);
    var out = await py.runPythonAsync(msg.glue);
    self.postMessage({ ok: true, result: out });
  } catch (e) {
    self.postMessage({ ok: false, error: String(e && e.message ? e.message : e) });
  }
};
