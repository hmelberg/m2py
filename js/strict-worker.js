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
    await py.loadPackage(['pandas', 'cryptography']);
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
