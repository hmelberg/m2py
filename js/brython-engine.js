// js/brython-engine.js — lightweight Python engine (Brython) for openstat/safestat.
// Design: docs/superpowers/specs/2026-07-10-brython-engine-design.md
//
// Loads Brython 3.12 from CDN, registers pandas_brython/plotly_express_brython
// as text/python script tags (id MUST equal module name — that is how Brython
// resolves imports), compiles brython_runner.py once via __BRYTHON__.runPythonSource,
// and exposes run(). Output is embed-marker text; index.html renders it via
// buildOutputNodes().
//
// Bootstrap mirrors code2web's proven pattern (web2.html), verified against
// code2web/web2.html and the actual Brython 3.12.0 source (jsdelivr) rather
// than assumed — see divergences from the task-4 brief's draft, documented
// inline below and in .superpowers/sdd/task-4-report.md:
//
//  1. brython() is called with NO arguments, exactly like code2web's
//     ensureBrythonLoaded(). The brief's draft called `window.brython({debug:0,
//     ids:[]})`; decompiling brython.min.js shows brython() only ever reads
//     options.debug / .args / .breakpoint / .indexedDB / .python_extension —
//     there is no `ids` option, so that key would silently do nothing. We
//     drop it rather than ship a fictional option.
//  2. Script tags for pandas_brython/plotly_express_brython are registered
//     BEFORE brython() runs, and brython() is called only AFTER stdlib has
//     finished loading (core THEN stdlib THEN module tags THEN brython()).
//     code2web's own ensureBrythonLoaded() calls brython() right after core
//     loads, before stdlib finishes — but that path never registers any
//     text/python script tags (its "shared module" is run later via
//     runPythonSource, not import-resolved), so the ordering there is
//     untested for module compilation. The proven script-tag-registration
//     pattern lives in code2web's export/bundling code (web2.html ~13523),
//     which always adds `<script type="text/python" id="<module>">` tags to
//     the document BEFORE Brython's own DOMContentLoaded-triggered scan runs
//     — i.e. tags-before-brython() is the real contract. We combine that
//     with a full core+stdlib load first, since our modules (unlike
//     code2web's shared module) get eagerly compiled during the brython()
//     scan and may need real stdlib imports (io, re, json, math, ...)
//     available at that time.
//  3. __BRYTHON__.runPythonSource(source, name) is called with the module
//     name as the second argument, matching the brief's draft. code2web's
//     own live-cell path calls runPythonSource(src, {}) for its shared
//     module — but decompiling brython.min.js shows the second parameter is
//     `script_id` (used only as a compile-unit name; Brython auto-generates
//     one only when it is literally `undefined`). A real string is the
//     correct/intended usage; code2web's `{}` is not a documented pattern to
//     imitate, just a value that happens not to be `undefined`. We pass
//     'brython_runner' for a meaningful compiled name.
//
// Confirmed by inspecting the actual jsdelivr brython@3.12.0 bundle:
//   - runPythonSource=function(src,script_id){if(script_id===undefined){...
//   - brython=function(options){...} only reads debug/args/breakpoint/
//     indexedDB/python_extension from options — no `ids` key exists.
//   - script.id is the value used to key registered/defined modules —
//     confirming the id-must-equal-module-name import contract.
//
// CORRECTION (found via real-browser testing, not just source reading): the
// earlier claim here — that Brython scans script[type="text/python"] tags
// "at call time" via a synchronous querySelectorAll with no MutationObserver
// dependency — is WRONG. Brython's script-tag registry is actually populated
// through a MutationObserver callback, which Chrome/Firefox schedule as a
// microtask fired only once the current task yields. Appending our
// <script id="pandas_brython"> tag synchronously and then calling
// global.brython() in the very next line does NOT give that observer
// callback a chance to run first, so brython() starts its module scan before
// our tags are registered — `import pandas_brython` then fails with
// ModuleNotFoundError in a real browser (this never showed up in
// `node --check`, which only parses the file). The fix is to yield a real
// macrotask (a `setTimeout(0)`, not just a microtask like `Promise.resolve()`
// — those run before the observer's microtask too) between registering the
// tags and calling brython(), so the MutationObserver has run by the time
// the scan starts. See the `await new Promise(setTimeout(...))` below.
(function (global) {
  'use strict';

  var BRYTHON_CORE = 'https://cdn.jsdelivr.net/npm/brython@3.12.0/brython.min.js';
  var BRYTHON_STDLIB = 'https://cdn.jsdelivr.net/npm/brython@3.12.0/brython_stdlib.js';
  var PY_LIBS = ['pandas_brython', 'plotly_express_brython'];

  var __enginePromise = null;

  function addScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('Kunne ikke laste ' + src)); };
      document.head.appendChild(s);
    });
  }

  function addPyModule(name, source) {
    if (document.getElementById(name)) return;
    var s = document.createElement('script');
    s.type = 'text/python';
    s.id = name;                       // id == module name (Brython import contract)
    s.textContent = source;
    document.head.appendChild(s);
  }

  function fetchText(path) {
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error('Kunne ikke hente ' + path + ' (' + r.status + ')');
      return r.text();
    });
  }

  function load() {
    if (__enginePromise) return __enginePromise;
    __enginePromise = (async function () {
      await addScript(BRYTHON_CORE);
      await addScript(BRYTHON_STDLIB);
      var sources = await Promise.all(
        PY_LIBS.concat(['brython_runner']).map(function (m) { return fetchText('brython/' + m + '.py'); }));
      PY_LIBS.forEach(function (m, i) { addPyModule(m, sources[i]); });
      // Race fix (see file-header comment above): Brython's script-tag
      // registry is filled in by a MutationObserver callback, which the
      // browser schedules asynchronously. Without this yield, brython() can
      // run its module scan before the observer has registered the tags we
      // just appended, and `import pandas_brython` fails with
      // ModuleNotFoundError. A macrotask yield (setTimeout, not a
      // microtask/Promise.resolve — those still run before the observer's
      // callback) reliably lets that callback run first.
      await new Promise(function (r) { setTimeout(r, 0); });
      global.brython();                // no-args, matching code2web's proven invocation
      var mod = global.__BRYTHON__.runPythonSource(sources[PY_LIBS.length], 'brython_runner');
      return mod;
    })().catch(function (e) { __enginePromise = null; throw e; });
    return __enginePromise;
  }

  // Convert resolveAndFetchLoads results + embedded blocks to the runner's
  // {name: {kind, payload}} spec. CSV/JSON parse in Python; parquet converts
  // via the DuckDB-WASM helper exported by index.html (lazy — only if used).
  async function buildDatasetSpec(loads) {
    var spec = {};
    var i, l;
    for (i = 0; i < (loads || []).length; i++) {
      l = loads[i];
      if (!l.bytes) continue;
      if (l.format === 'csv') {
        spec[l.alias] = { kind: 'csv', payload: new TextDecoder().decode(l.bytes) };
      } else if (l.format === 'json') {
        spec[l.alias] = { kind: 'columns', payload: JSON.parse(new TextDecoder().decode(l.bytes)) };
      } else if (l.format === 'parquet') {
        if (typeof global.__brythonParquetColumns !== 'function') {
          throw new Error('parquet-kilden «' + l.alias + '» støttes ikke: DuckDB-hjelperen mangler');
        }
        spec[l.alias] = { kind: 'columns', payload: await global.__brythonParquetColumns(l.bytes) };
      } else {
        throw new Error('formatet «' + l.format + '» (' + l.alias + ') støttes ikke i Brython-modus — bruk python/r');
      }
    }
    // Embedded data blocks (published dashboards): checked after # load so an
    // explicit load wins over a baked-in copy with the same name.
    var nodes = document.querySelectorAll('script[type="application/json"][id^="brythondata_"]');
    for (i = 0; i < nodes.length; i++) {
      var name = nodes[i].id.slice('brythondata_'.length);
      if (!spec[name]) spec[name] = { kind: 'columns', payload: JSON.parse(nodes[i].textContent) };
    }
    return spec;
  }

  async function run(script, opts) {
    // Contract: run() ALWAYS resolves {text, error} — never rejects. Callers
    // (index.html's mode dispatch) only handle a resolved promise; load()
    // failures (script/fetch errors) and buildDatasetSpec() throws
    // (unsupported format, missing DuckDB parquet helper) previously
    // rejected here, which would surface as an unhandled rejection instead
    // of the Norwegian error text meant for the user. Catch everything and
    // fold it into the same {text, error} shape.
    try {
      var mod = await load();
      var spec = await buildDatasetSpec(opts && opts.loads);
      if (Object.keys(spec).length) {
        var bindErr = mod._bind_datasets(JSON.stringify(spec));
        if (bindErr) return { text: '', error: String(bindErr) };
      }
      var text = mod._execute_code(script);
      var err = mod._get_last_error();
      return { text: String(text == null ? '' : text), error: err ? String(err) : null };
    } catch (e) {
      return { text: '', error: (e && e.message) || String(e) };
    }
  }

  global.BrythonEngine = { load: load, run: run };
})(typeof window !== 'undefined' ? window : globalThis);
