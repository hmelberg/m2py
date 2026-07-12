// js/micropython-engine.js — rask Python-motor (MicroPython-wasm) for
// openstat/safestat. Speiler js/brython-engine.js; designspec:
// docs/superpowers/specs/2026-07-12-micropython-mode-design.md
//
// Boot: dynamisk import() av den offisielle wasm-portens ES-modul (pinnet
// 1.27.0), loadMicroPython med stdout-callback — runneren skriver ALT via
// print (MicroPython tillater ikke sys.stdout-bytte), motoren samler linjene
// i __stdoutBuf og bygger {text}. Lazy libs, duck-replay-broen og
// {text, error}-kontrakten er som i Brython-motoren.
//
// __scriptLog/__mpySource(): MicroPython-funksjonsobjekter mangler
// __code__ (co_varnames m.m. finnes ikke, kun __name__ — verifisert i
// fase 0). dash.py sin _func_params(f) må derfor kunne falle tilbake til
// å tekst-parse KILDEN til add()-ede funksjoner for å finne
// parameternavnene deres. run() logger scriptet (én gang per kall, IKKE
// per duck-replay-pass) til __scriptLog; __mpySource() eksponeres på
// global slik at dash.py kan hente hele loggen via window.__mpySource().
(function (global) {
  'use strict';

  var MPY_BASE = 'https://cdn.jsdelivr.net/npm/@micropython/micropython-webassembly-pyscript@1.27.0/';

  // Library registry — samme form som Brython-motorens (js-deps er
  // {url, global}-objekter, ikke strenger).
  var LIB_REGISTRY = {
    // pandas_mpy har (som pandas_brython) modulnivå try-import av plotly (df.plot)
    pandas_mpy:         { aliases: [], deps: ['plotly_express_mpy'], js: [] },
    plotly_express_mpy: { aliases: [], deps: [], js: [] },
    duckdb_mpy:         { aliases: ['duckdb'], deps: ['pandas_mpy'], js: [] },
    dash:               { aliases: [], deps: [], js: [{ url: 'js/dash.js', global: 'Dash' }] }
  };

  function scanImports(code) {
    // Identisk logikk som brython-engine.js scanImports (over-match ufarlig,
    // under-match gir høylytt ModuleNotFoundError).
    var needed = [];
    function add(rawName) {
      var name = rawName.split('.')[0];
      var canonical = LIB_REGISTRY.hasOwnProperty(name) ? name : null;
      if (!canonical) {
        for (var k in LIB_REGISTRY) {
          if (LIB_REGISTRY[k].aliases.indexOf(name) !== -1) { canonical = k; break; }
        }
      }
      if (canonical && needed.indexOf(canonical) === -1) needed.push(canonical);
    }
    var re = /^[ \t]*(?:from[ \t]+([A-Za-z_][A-Za-z0-9_.]*)|import[ \t]+([^#\r\n]+))/gm;
    var m, parts, i, t;
    while ((m = re.exec(code))) {
      if (m[1]) { add(m[1]); continue; }
      parts = m[2].split(',');
      for (i = 0; i < parts.length; i++) {
        t = parts[i].trim().split(/[ \t]/)[0];
        if (/^[A-Za-z_][A-Za-z0-9_.]*$/.test(t)) add(t);
      }
    }
    return needed;
  }

  var __registered = {};
  var __jsLoaded = {};
  var __stdoutBuf = [];
  var __captureMark = 0;
  var __scriptLog = [];

  // dash.py-kroker: MicroPython kan ikke bytte sys.stdout, så callback-
  // utskrift fanges ved å merke/splitte motorens stdout-buffer i stedet.
  global.__mpyCaptureStart = function () { __captureMark = __stdoutBuf.length; };
  global.__mpyCaptureEnd = function () {
    return __stdoutBuf.splice(__captureMark).join('\n');
  };

  // dash.py _func_params-fallback: MicroPython-funksjoner har IKKE
  // __code__ (co_varnames/co_argcount finnes ikke), bare __name__. dash.py
  // trenger likevel parameternavnene til add()-ede funksjoner for å vite
  // hvilke kwargs å kalle dem med. Løsning: motoren logger kildeteksten til
  // hvert run()-kall (én gang per run, ikke per duck-replay-pass), og
  // dash.py sitt fallback-spor tekst-parser DENNE loggen etter
  // `def <navn>(...)` for å finne parameterlisten når __code__ mangler.
  // __mpySource() returnerer alle loggede scripts som ÉN streng (nyeste
  // sist), skilt av et NUL-omsluttet skilletegn som ikke kan forekomme i
  // gyldig Python-kildetekst — enklere å konsumere fra Python enn en
  // JsProxy-array (som ville krevd iterering/indeksering over grensen).
  global.__mpySource = function () { return __scriptLog.join('\n\x00SCRIPT\x00\n'); };

  function addScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('Kunne ikke laste ' + src)); };
      document.head.appendChild(s);
    });
  }

  function fetchText(path) {
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error('Kunne ikke hente ' + path + ' (' + r.status + ')');
      return r.text();
    });
  }

  function loadJsDep(dep) {
    if (global[dep.global]) return Promise.resolve();
    if (!__jsLoaded[dep.url]) {
      __jsLoaded[dep.url] = addScript(dep.url).catch(function (e) {
        delete __jsLoaded[dep.url];
        throw e;
      });
    }
    return __jsLoaded[dep.url];
  }

  var __enginePromise = null;

  function load() {
    if (__enginePromise) return __enginePromise;
    __enginePromise = (async function () {
      var esm = await import(MPY_BASE + 'micropython.mjs');
      var mp = await esm.loadMicroPython({
        url: MPY_BASE + 'micropython.wasm',
        stdout: function (line) { __stdoutBuf.push(line); },
        linebuffer: true
      });
      var source = await fetchText('micropython/micropython_runner.py');
      mp.runPython(source);
      return {
        mp: mp,
        _execute_code: mp.globals.get('_execute_code'),
        _get_last_error: mp.globals.get('_get_last_error'),
        _register_module: mp.globals.get('_register_module'),
        _alias_module: mp.globals.get('_alias_module'),
        _snapshot: mp.globals.get('_snapshot'),
        _rollback: mp.globals.get('_rollback'),
        _bind_datasets: mp.globals.get('_bind_datasets')
      };
    })().catch(function (e) { __enginePromise = null; throw e; });
    return __enginePromise;
  }

  async function ensureLibs(mod, names, _visiting) {
    _visiting = _visiting || {};
    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      if (__registered[name]) continue;
      var entry = LIB_REGISTRY[name];
      if (!entry) throw new Error('Ukjent bibliotek i LIB_REGISTRY: ' + name);
      if (_visiting[name]) throw new Error('Sirkulær avhengighet i LIB_REGISTRY: ' + name);
      _visiting[name] = true;
      await ensureLibs(mod, entry.deps, _visiting);
      for (var j = 0; j < entry.js.length; j++) await loadJsDep(entry.js[j]);
      var source = await fetchText('micropython/' + name + '.py');
      var err = mod._register_module(name, source);
      if (err) throw new Error(String(err));
      for (var a = 0; a < entry.aliases.length; a++) {
        err = mod._alias_module(entry.aliases[a], name);
        if (err) throw new Error(String(err));
      }
      __registered[name] = true;
    }
  }

  var PENDING_MARKER = '__BRYTHON_PENDING__';   // delt protokoll med Brython-motoren
  var MAX_DUCK_PASSES = 10;

  // Per-run duckdb-bro — identisk protokoll som Brython-motorens
  // beginDuckBridge (JSON-streng {pending}|{cols}|{error}), eget globalnavn
  // så motorene ikke tråkker i hverandres closures.
  function beginDuckBridge(spec) {
    var cache = {};
    var pending = [];
    var registered = false;
    global.__mpyDuckSync = function (sqlText) {
      if (cache.hasOwnProperty(sqlText)) return cache[sqlText];
      if (pending.indexOf(sqlText) === -1) pending.push(sqlText);
      return '{"pending":true}';
    };
    return {
      hasPending: function () { return pending.length > 0; },
      flush: async function () {
        if (!global.__brythonDuck) {
          throw new Error('duckdb i MicroPython-modus krever DuckDB-hjelperen (__brythonDuck) i index.html');
        }
        if (!registered) {
          for (var name in spec) {
            await global.__brythonDuck.register(name, spec[name].kind, spec[name].payload);
          }
          registered = true;
        }
        var batch = pending;
        pending = [];
        for (var i = 0; i < batch.length; i++) {
          try {
            var cols = await global.__brythonDuck.query(batch[i]);
            cache[batch[i]] = JSON.stringify({ cols: cols });
          } catch (e) {
            cache[batch[i]] = JSON.stringify({ error: (e && e.message) || String(e) });
          }
        }
      }
    };
  }

  // Samme kildeoppsett som Brython-motorens buildDatasetSpec; embed-tags
  // heter mpydata_<navn>.
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
        throw new Error('formatet «' + l.format + '» (' + l.alias + ') støttes ikke i MicroPython-modus — bruk python/r');
      }
    }
    // Embedded data blocks (published dashboards, see index.html's
    // publishStandaloneDashboard()): a parsed value with a "kind" field is
    // read explicitly ({kind:'csv', payload:<csv-text>} binds via the same
    // read_csv path as a live # load; {kind:'columns', payload:{...}} is
    // already column-shaped). A value WITHOUT a "kind" field is treated as
    // raw columns — backward-compatible with tags written before this format.
    var nodes = document.querySelectorAll('script[type="application/json"][id^="mpydata_"]');
    for (i = 0; i < nodes.length; i++) {
      var name = nodes[i].id.slice('mpydata_'.length);
      if (spec[name]) continue;
      var parsed = JSON.parse(nodes[i].textContent);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && parsed.kind === 'csv') {
        spec[name] = { kind: 'csv', payload: parsed.payload };
      } else if (parsed && typeof parsed === 'object' && !Array.isArray(parsed) && parsed.kind === 'columns') {
        spec[name] = { kind: 'columns', payload: parsed.payload };
      } else {
        spec[name] = { kind: 'columns', payload: parsed };
      }
    }
    return spec;
  }

  // Siste kjørings resolverte datasett-spec, cachet slik at "Publiser
  // dashboard" (index.html) kan bake dem inn som mpydata_<navn>-tags uten å
  // kjøre scriptet på nytt. Samme mønster som brython-engine.js.
  var __lastSpec = {};

  async function run(script, opts) {
    // Kontrakt: run() resolver ALLTID {text, error} — aldri reject (samme
    // begrunnelse som i brython-engine.js run()).
    try {
      var mod = await load();
      var spec = await buildDatasetSpec(opts && opts.loads);
      __lastSpec = spec;
      var needed = scanImports(script);
      if (Object.keys(spec).length && needed.indexOf('pandas_mpy') === -1) {
        needed.push('pandas_mpy');   // _bind_datasets bygger DataFrames
      }
      await ensureLibs(mod, needed);
      var duck = beginDuckBridge(spec);
      __scriptLog.push(script);   // én gang per run(), IKKE per duck-replay-pass (se __mpySource over)
      mod._snapshot();
      var err = null, pass;
      for (pass = 0; pass < MAX_DUCK_PASSES; pass++) {
        if (pass > 0) mod._rollback();
        __stdoutBuf.length = 0;      // nytt pass = tom buffer (pending-pass forkastes)
        __captureMark = 0;
        if (Object.keys(spec).length) {
          var bindErr = mod._bind_datasets(JSON.stringify(spec));
          if (bindErr) return { text: '', error: String(bindErr) };
        }
        mod._execute_code(script);
        err = mod._get_last_error();
        if (err !== PENDING_MARKER) break;
        if (!duck.hasPending()) {
          return { text: '', error: 'duckdb_mpy: replay uten ventende spørringer (intern feil)' };
        }
        await duck.flush();
      }
      if (err === PENDING_MARKER) {
        return { text: '', error: 'duckdb-spørringene stabiliserer seg ikke etter ' +
                 MAX_DUCK_PASSES + ' pass — bygges SQL-tekstene av ikke-deterministiske ' +
                 'verdier (f.eks. random uten seed)?' };
      }
      var text = __stdoutBuf.join('\n');
      return { text: text, error: err ? String(err) : null };
    } catch (e) {
      return { text: '', error: (e && e.message) || String(e) };
    }
  }

  global.MicroPythonEngine = {
    load: load, run: run, _scanImports: scanImports,
    getLastDatasetSpec: function () { return __lastSpec; }
  };
})(typeof window !== 'undefined' ? window : globalThis);
