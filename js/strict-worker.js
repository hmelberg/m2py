// Dedikert Pyodide-worker for lokale STRICT-kjøringer (spec 2026-07-05-
// browser-strict-execution §V4): rammer og klartekst finnes bare i denne
// workeren, aldri i hovedtråden — innsyn krever debugger mot workeren, ikke
// bare konsollen. Selvstendig: laster egen Pyodide + pandas + cryptography +
// safepy.zip ved første kjøring, gjenbrukes varm etterpå.
//
// MODULE worker (2026-07-08, Pyodide v0.29.3 -> v314.0.2 upgrade): classic
// workers (importScripts()) are no longer supported by Pyodide as of the
// asm.js -> asm.mjs rename in 314.0.0 -- this file is now loaded as
// `new Worker(url, {type: 'module'})` (see index.html's runStrictInWorker),
// and pyodide.mjs (the ES-module build) is loaded via dynamic import()
// rather than importScripts()+a global loadPyodide(). Everything else
// (onmessage/postMessage/fetch/unpackArchive) is unchanged by this.
'use strict';

var pyReady = null;

function ensurePy(pyodideURL, zipURL) {
  if (pyReady) return pyReady;
  pyReady = (async function () {
    var { loadPyodide } = await import(pyodideURL + 'pyodide.mjs');
    var py = await loadPyodide({ indexURL: pyodideURL });
    // pandas/cryptography/scipy/statsmodels er offisielle Pyodide-pakker;
    // lifelines/pyfixest er rene python-pakker som må via micropip. Uten
    // disse feiler ols/logit/poisson/anova/corr_test (statsmodels) og
    // cox/kaplan_meier/logrank/rmst/weibull_aft (lifelines) med
    // ModuleNotFoundError i en STRICT-kjøring — se
    // docs/superpowers/2026-07-05-remaining-roadmap.md §3.
    await py.loadPackage(['pandas', 'cryptography', 'scipy', 'statsmodels', 'pyarrow', 'micropip']);
    // sqlite3 (2026-07-08, dialect="sqlite" — se safepy/sqlite_api.py): på
    // 0.29.3 var det "unvendret" (krevde nettopp denne loadPackage-linjen);
    // fra og med Pyodide 314.0.0 er det bundlet i stdlib som standard, og
    // finnes IKKE lenger som et eget, ved-navn-lastbart pakkenavn —
    // loadPackage(['sqlite3']) feiler da med "No known package with name
    // 'sqlite3'" i stedet for å no-op'e (funnet live under 314-oppgraderingen).
    // try/except gjør denne robust uansett pinned Pyodide-versjon.
    try {
      await py.loadPackage(['sqlite3']);
    } catch (e) { /* bundlet i stdlib på nyere Pyodide — ingenting å gjøre */ }
    // Same ArrowKeyError patch as index.html's ensurePyarrowFor (main
    // thread) — pandas' lazy patch_pyarrow() calls unregister_extension_type
    // ('arrow.py_extension_type'), which used to raise in the Pyodide
    // pyarrow build. Fixes the gap flagged 2026-07-08 (encrypted+parquet
    // strict runs go through this worker, not the main thread, and had no
    // equivalent patch) — worth fixing now that pyarrow is a real loadable
    // package here at v314.0.2, not micropip-only.
    await py.runPythonAsync(
      'import pyarrow as _pa\n' +
      'if not getattr(_pa, "_m2py_unreg_patched", False):\n' +
      '    _oru = _pa.unregister_extension_type\n' +
      '    def _safe_unreg(name, _o=_oru):\n' +
      '        try:\n' +
      '            return _o(name)\n' +
      '        except Exception:\n' +
      '            return None\n' +
      '    _pa.unregister_extension_type = _safe_unreg\n' +
      '    _pa._m2py_unreg_patched = True\n' +
      '    try:\n' +
      '        import pandas.core.arrays.arrow.extension_types\n' +
      '    except Exception:\n' +
      '        pass\n');
    // lifelines' own declared metadata still says "pandas<3.0,>=2.1" (stale
    // — not updated for pandas 3.x yet), so a plain micropip.install fails
    // outright at the version-resolution step before lifelines' code even
    // runs (found live during the 2026-07-08 Pyodide v314.0.2 upgrade,
    // which bundles pandas 3.0.2). Verified directly that lifelines 0.30.3
    // is functionally fine against pandas 3.0.2 (KaplanMeierFitter fit+
    // median_survival_time_ produced a correct result) — this is a metadata
    // staleness issue, not a real incompatibility, so: install lifelines'
    // actual transitive dependencies explicitly, then install lifelines
    // itself with deps=False to skip the outdated pandas-version gate,
    // rather than silently degrading a real, already-shipped feature
    // (cox/kaplan_meier/logrank/rmst/weibull_aft).
    await py.runPythonAsync(
      'import micropip as _mp\n' +
      'await _mp.install(["autograd", "formulaic", "interface_meta", "autograd-gamma"])\n' +
      'await _mp.install("lifelines", deps=False)');
    try {
      await py.runPythonAsync('import micropip as _mp\nawait _mp.install("pyfixest")');
    } catch (e) {
      // pyfixest sine avhengigheter (f.eks. maketables/narwhals) er ikke
      // nødvendigvis tilgjengelige i Pyodide ennå — degrader stille her;
      // feols/fepois gir en tydelig feilmelding når de faktisk kalles.
    }
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
  // Echo the caller's request id (B6, docs/REVIEW_2026-07-07.md §3) so the
  // main thread can dispatch this response to the right pending call even
  // when two runStrictInWorker() calls overlap.
  try {
    var py = await ensurePy(msg.pyodideURL, msg.zipURL);
    var out = await py.runPythonAsync(msg.glue);
    self.postMessage({ ok: true, result: out, id: msg.id });
  } catch (e) {
    self.postMessage({ ok: false, error: String(e && e.message ? e.message : e), id: msg.id });
  }
};
