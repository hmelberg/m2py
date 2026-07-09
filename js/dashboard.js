// js/dashboard.js — dashboard-visning (spec docs/superpowers/specs/2026-07-09-dashboard-design.md)
// Ren parsing/planlegging øverst (node-testet, tests/js/dashboard.test.js);
// DOM/orkestrering nederst (kjører kun i nettleser). Modulen kjenner ikke
// Pyodide/webR — all kjøring og output-rendering går via ctx {mode, run,
// renderOutput, t} bygget av buildDashboardCtx() i index.html.
(function (global) {
  'use strict';
  var D = {};

  // Samme marker-trippel som extractScriptOptions (#, //, --).
  var INPUT_RE = /^[ \t]*(?:#|\/\/|--)[ \t]*input[ \t]+(\S+)[ \t]*=[ \t]*(slider|dropdown|checkbox)\(([^)]*)\)[ \t]*$/;
  var CELL_RE = /^[ \t]*(?:#|\/\/|--)[ \t]*%%[ \t]*(.*)$/;
  var NAME_RE = /^[A-Za-z_]\w*$/;

  // "1990, 2024, step=1" / '"A", "B", label="X"' → {pos:[], kw:{}}.
  // Komma-splitting respekterer anførselstegn.
  function parseArgs(inner) {
    var pos = [], kw = {}, buf = '', inStr = null, parts = [];
    for (var i = 0; i < inner.length; i++) {
      var ch = inner[i];
      if (inStr) { buf += ch; if (ch === inStr && inner[i - 1] !== '\\') inStr = null; }
      else if (ch === '"' || ch === "'") { inStr = ch; buf += ch; }
      else if (ch === ',') { parts.push(buf); buf = ''; }
      else buf += ch;
    }
    if (buf.trim()) parts.push(buf);
    parts.forEach(function (p) {
      p = p.trim();
      if (!p) return;
      var eq = p.indexOf('=');
      var isKw = eq > 0 && NAME_RE.test(p.slice(0, eq).trim());
      var val = isKw ? p.slice(eq + 1).trim() : p;
      var parsed;
      if (/^(true|True|TRUE)$/.test(val)) parsed = true;
      else if (/^(false|False|FALSE)$/.test(val)) parsed = false;
      else if (val !== '' && !isNaN(Number(val))) parsed = Number(val);
      else parsed = val.replace(/^["']|["']$/g, '');
      if (isKw) kw[p.slice(0, eq).trim()] = parsed; else pos.push(parsed);
    });
    return { pos: pos, kw: kw };
  }

  function parseInput(name, type, inner, errors) {
    if (!NAME_RE.test(name)) { errors.push('ugyldig variabelnavn i #input: «' + name + '»'); return null; }
    var a = parseArgs(inner);
    var inp = { name: name, type: type, label: (typeof a.kw.label === 'string' && a.kw.label) ? a.kw.label : name };
    if (type === 'slider') {
      if (typeof a.pos[0] !== 'number' || typeof a.pos[1] !== 'number') {
        errors.push('slider krever min og maks: «' + name + '»'); return null;
      }
      inp.min = a.pos[0]; inp.max = a.pos[1];
      inp.step = (typeof a.kw.step === 'number') ? a.kw.step : 1;
      inp['default'] = (typeof a.kw['default'] === 'number') ? a.kw['default'] : inp.min;
    } else if (type === 'dropdown') {
      inp.choices = a.pos.map(String);
      if (!inp.choices.length) { errors.push('dropdown uten valg: «' + name + '»'); return null; }
      inp['default'] = (a.kw['default'] !== undefined) ? String(a.kw['default']) : inp.choices[0];
    } else { // checkbox — verdier er alltid bool (spec §5)
      inp['default'] = a.kw['default'] === true;
    }
    return inp;
  }

  // "Navn, wide, row=x, tab=Y, deps=a+b" → celle-attributter.
  function parseCellHeader(rest) {
    var cell = { name: '', wide: false, row: null, tab: null, deps: null };
    rest.split(',').forEach(function (p, i) {
      p = p.trim();
      if (!p) return;
      var eq = p.indexOf('=');
      if (eq > 0) {
        var k = p.slice(0, eq).trim().toLowerCase(), v = p.slice(eq + 1).trim();
        if (k === 'row') cell.row = v;
        else if (k === 'tab') cell.tab = v;
        else if (k === 'deps') cell.deps = v.split('+').map(function (s) { return s.trim(); }).filter(Boolean);
      } else if (/^(wide|bred)$/i.test(p)) cell.wide = true;
      else if (/^(half|halv)$/i.test(p)) cell.wide = false;
      else if (i === 0) cell.name = p;
    });
    return cell;
  }

  D.parse = function (script) {
    var lines = String(script || '').split(/\r?\n/);
    var errors = [], inputs = [], cells = [], seenInput = {};
    var optRe = /^\s*(?:#|\/\/|--)\s*options\.(\w+)\s*=\s*("[^"]*"|'[^']*'|\S+)\s*$/;
    var title = '', description = '';
    var firstInput = -1;
    for (var i = 0; i < lines.length; i++) {
      if (firstInput < 0 && INPUT_RE.test(lines[i])) firstInput = i;
      var om = lines[i].match(optRe);
      if (om) {
        var ov = om[2].replace(/^["']|["']$/g, '');
        if (om[1] === 'title') title = ov;
        if (om[1] === 'description') description = ov;
      }
    }
    // Setup-sonen: alt over første #input (direktiver inkludert — pipelinen
    // stripper selv #options.*-linjer). Uten #input er alt setup, ingen celler.
    var setupCode = (firstInput < 0 ? lines : lines.slice(0, firstInput)).join('\n');
    var cur = null;
    for (var j = (firstInput < 0 ? lines.length : firstInput); j < lines.length; j++) {
      var line = lines[j];
      var im = line.match(INPUT_RE);
      if (im) {
        var inp = parseInput(im[1], im[2], im[3], errors);
        if (inp) {
          if (seenInput[inp.name]) errors.push('#input «' + inp.name + '» er deklarert to ganger');
          seenInput[inp.name] = true;
          inputs.push(inp);
        }
        continue;
      }
      var cm = line.match(CELL_RE);
      if (cm) {
        cur = parseCellHeader(cm[1]);
        cur.code = '';
        cells.push(cur);
        continue;
      }
      // Kode før første #%% → én navnløs celle (bevisst forenkling av
      // spec §1.3, se plan-headeren).
      if (!cur) {
        if (line.trim()) { cur = { name: '', wide: false, row: null, tab: null, deps: null, code: line }; cells.push(cur); }
      } else {
        cur.code += (cur.code ? '\n' : '') + line;
      }
    }
    cells = cells.filter(function (c) { return (c.code || '').trim(); });
    return { title: title, description: description, inputs: inputs, setupCode: setupCode, cells: cells, errors: errors };
  };

  // Trygg serialisering (spec §5): tall som tall, bool som modus-literal,
  // strenger JSON-enkodet (gyldig literal i både python og R).
  D.assignStatement = function (mode, name, value) {
    var lit;
    if (typeof value === 'number') lit = String(value);
    else if (typeof value === 'boolean') lit = (mode === 'r') ? (value ? 'TRUE' : 'FALSE') : (value ? 'True' : 'False');
    else lit = JSON.stringify(String(value));
    return (mode === 'r') ? (name + ' <- ' + lit) : (name + ' = ' + lit);
  };

  // ── Invalidering (spec §3.1): konservativ tekstanalyse ────────────────────
  // Falske positiver koster bare en unødvendig kjøring; celler vi ikke kan
  // analysere trygt («opake») trekker med seg alt etterfølgende.
  var OPAQUE = {
    python: /\b(exec|eval|globals|locals|__import__)\s*\(/,
    r: /\b(assign|eval|get|source)\s*\(/
  };
  function assignedNames(code, mode) {
    var names = {}, m;
    if (mode === 'r') {
      var rre = /(?:^|[\n;({])\s*([A-Za-z_.][\w.]*)\s*(?:<<?-|=(?!=))/g;
      while ((m = rre.exec(code)) !== null) names[m[1]] = true;
      var arrow = /(?:->>?)\s*([A-Za-z_.][\w.]*)/g;
      while ((m = arrow.exec(code)) !== null) names[m[1]] = true;
    } else {
      var pre = /^[ \t]*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*(?:=(?!=)|\+=|-=|\*=|\/=)/gm;
      while ((m = pre.exec(code)) !== null) {
        m[1].split(',').forEach(function (n) { names[n.trim()] = true; });
      }
      var dre = /^[ \t]*(?:def|class)\s+([A-Za-z_]\w*)/gm;
      while ((m = dre.exec(code)) !== null) names[m[1]] = true;
      var fre = /^[ \t]*for\s+([A-Za-z_]\w*)/gm;
      while ((m = fre.exec(code)) !== null) names[m[1]] = true;
    }
    return Object.keys(names);
  }
  function mentionsAny(code, vars) {
    for (var i = 0; i < vars.length; i++) {
      var esc = vars[i].replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      if (new RegExp('\\b' + esc + '\\b').test(code)) return true;
    }
    return false;
  }
  // Hvilke celler må re-kjøres når changedVars er endret? Rekkefølge bevart.
  D.planReruns = function (cells, changedVars, mode) {
    var m = (mode === 'r') ? 'r' : 'python';
    var dirty = {}, out = [], anyRerun = false, opaqueRan = false;
    changedVars.forEach(function (v) { dirty[v] = true; });
    for (var i = 0; i < cells.length; i++) {
      var c = cells[i], rerun;
      var dirtyList = Object.keys(dirty);
      var opaque = !c.deps && OPAQUE[m].test(c.code || '');
      if (c.deps) rerun = c.deps.some(function (d) { return dirty[d]; });
      else if (opaqueRan) rerun = true;
      else if (opaque) rerun = anyRerun || mentionsAny(c.code || '', dirtyList);
      else rerun = mentionsAny(c.code || '', dirtyList);
      if (rerun) {
        out.push(i);
        anyRerun = true;
        assignedNames(c.code || '', m).forEach(function (n) { dirty[n] = true; });
        if (opaque) opaqueRan = true;
      }
    }
    return out;
  };

  // ── Layout-gruppering (spec §1.3/§3): celler → kort/rader/fanesett ───────
  // row= samler naboer med samme radnavn; sammenhengende tab=-celler danner
  // ett fanesett (celle uten tab bryter settet).
  D.groupLayout = function (cells) {
    var out = [], i = 0;
    while (i < cells.length) {
      var c = cells[i];
      if (c.row) {
        var idx = [i], name = c.row;
        while (i + 1 < cells.length && cells[i + 1].row === name) idx.push(++i);
        out.push({ kind: 'row', name: name, indexes: idx });
      } else if (c.tab) {
        var tabs = [], curLabel = null;
        while (i < cells.length && cells[i].tab) {
          if (cells[i].tab !== curLabel) { curLabel = cells[i].tab; tabs.push({ label: curLabel, indexes: [] }); }
          tabs[tabs.length - 1].indexes.push(i); i++;
        }
        i--; out.push({ kind: 'tabs', tabs: tabs });
      } else out.push({ kind: 'card', index: i });
      i++;
    }
    return out;
  };

  // ── Debounce + maks én ventende batch (spec §3) ──────────────────────────
  // Siste verdier vinner; kjøringer er strengt sekvensielle (én runtime).
  D.createQueue = function (execute, delayMs) {
    var pending = null, timer = null, running = false;
    function flush() {
      timer = null;
      if (running || !pending) return;
      var batch = pending; pending = null; running = true;
      Promise.resolve(execute(batch))['catch'](function () {}).then(function () {
        running = false;
        if (pending && !timer) flush();
      });
    }
    return { change: function (name, value) {
      pending = pending || {};
      pending[name] = value;
      if (timer) clearTimeout(timer);
      timer = setTimeout(flush, delayMs);
    } };
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = D;
  global.Dashboard = D;
})(typeof window !== 'undefined' ? window : globalThis);
