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
    // stripper selv #options.*-linjer). UTEN #input (typisk et vanlig script
    // vist som dashboard via visnings-dropdownen): direktivlinjene forblir
    // setup (pipelinen materialiserer loads derfra), mens hele scriptet blir
    // celler — ellers ble alt "setup" og dashboardet sto tomt.
    var setupCode, cellStart;
    if (firstInput < 0) {
      setupCode = lines.filter(function (l) { return /^[ \t]*(?:#|\/\/|--|$)/.test(l); }).join('\n');
      cellStart = 0;
    } else {
      setupCode = lines.slice(0, firstInput).join('\n');
      cellStart = firstInput;
    }
    var cur = null;
    for (var j = cellStart; j < lines.length; j++) {
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

  // ═══ Nettleser-delen: DOM + orkestrering ══════════════════════════════════
  // Alt under her rører DOM og kjører aldri i node-testene. Tilstanden bor i
  // ett _state-objekt så unmount() kan rydde fullstendig (isolasjonskravet).
  var _state = null;

  function el(tag, className, text) {
    var n = document.createElement(tag);
    if (className) n.className = className;
    if (text != null) n.textContent = text;   // alltid textContent (spec §5)
    return n;
  }

  function buildWidget(inp, tf) {
    var wrap = el('div', 'dash-widget' + (inp.type === 'checkbox' ? ' dash-widget--checkbox' : ''));
    var lab = el('label', null, inp.label);
    var ctrl, getVal;
    if (inp.type === 'slider') {
      ctrl = el('input');
      ctrl.type = 'range';
      ctrl.min = inp.min; ctrl.max = inp.max; ctrl.step = inp.step; ctrl.value = inp['default'];
      var out = el('output', null, String(inp['default']));
      getVal = function () { return Number(ctrl.value); };
      ctrl.addEventListener('input', function () {
        out.textContent = ctrl.value;
        D._onChange(inp.name, getVal());
      });
      wrap.appendChild(lab); wrap.appendChild(ctrl); wrap.appendChild(out);
    } else if (inp.type === 'dropdown') {
      ctrl = el('select');
      inp.choices.forEach(function (c) {
        var o = el('option', null, c);
        o.value = c;
        if (c === inp['default']) o.selected = true;
        ctrl.appendChild(o);
      });
      getVal = function () { return String(ctrl.value); };
      ctrl.addEventListener('change', function () { D._onChange(inp.name, getVal()); });
      wrap.appendChild(lab); wrap.appendChild(ctrl);
    } else { // checkbox
      ctrl = el('input');
      ctrl.type = 'checkbox';
      ctrl.checked = inp['default'] === true;
      getVal = function () { return !!ctrl.checked; };
      ctrl.addEventListener('change', function () { D._onChange(inp.name, getVal()); });
      wrap.appendChild(ctrl); wrap.appendChild(lab);
    }
    return wrap;
  }

  function buildCard(cell, idx, tf) {
    var card = el('div', 'dash-card dash-card--loading' + (cell.wide ? ' dash-card--wide' : ''));
    if (cell.name) card.appendChild(el('h3', null, cell.name));
    var body = el('div', 'dash-card-body');
    card.appendChild(body);
    _state.cards[idx] = { card: card, body: body };
    return card;
  }

  // Skjelettet rendres FØR runtime laster (spec §3): struktur på <1 sek.
  D.mountSkeleton = function (parsed, ui) {
    if (_state) D.unmount();
    var tf = ui.t || function (s) { return s; };
    _state = {
      parsed: parsed, ui: ui, ctx: null, queue: null, cards: {},
      values: {}, dirtyHidden: {}, chain: Promise.resolve(), t: tf
    };
    parsed.inputs.forEach(function (inp) { _state.values[inp.name] = inp['default']; });

    var root = el('div', 'dash-root');
    var header = el('div', 'dash-header');
    header.appendChild(el('h1', null, parsed.title || tf('Dashboard')));
    if (parsed.description) header.appendChild(el('p', null, parsed.description));
    root.appendChild(header);

    if (parsed.inputs.length) {
      var controls = el('div', 'dash-controls dash-controls--loading');
      parsed.inputs.forEach(function (inp) { controls.appendChild(buildWidget(inp, tf)); });
      root.appendChild(controls);
      _state.controls = controls;
    }

    var grid = el('div', 'dash-grid');
    _state.grid = grid;
    D.groupLayout(parsed.cells).forEach(function (g) {
      if (g.kind === 'card') {
        grid.appendChild(buildCard(parsed.cells[g.index], g.index, tf));
      } else if (g.kind === 'row') {
        var row = el('div', 'dash-row');
        g.indexes.forEach(function (i) { row.appendChild(buildCard(parsed.cells[i], i, tf)); });
        grid.appendChild(row);
      } else { // tabs
        var tabsWrap = el('div', 'dash-tabs');
        var bar = el('div', 'dash-tabbar');
        var panels = [];
        g.tabs.forEach(function (tab, ti) {
          var btn = el('button', null, tab.label);
          btn.type = 'button';
          btn.setAttribute('aria-selected', ti === 0 ? 'true' : 'false');
          var panel = el('div', 'dash-tabpanel');
          if (ti > 0) panel.hidden = true;
          tab.indexes.forEach(function (i) {
            panel.appendChild(buildCard(parsed.cells[i], i, tf));
            if (ti > 0) _state.dirtyHidden[i] = true;   // lat kjøring (spec §3)
          });
          btn.addEventListener('click', function () {
            bar.querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-selected', 'false'); });
            panels.forEach(function (p) { p.hidden = true; });
            btn.setAttribute('aria-selected', 'true');
            panel.hidden = false;
            D._onTabShown(tab.indexes);
          });
          bar.appendChild(btn);
          panels.push(panel);
          tabsWrap.appendChild(panel);
        });
        tabsWrap.insertBefore(bar, tabsWrap.firstChild);
        grid.appendChild(tabsWrap);
      }
    });
    root.appendChild(grid);

    var footer = el('div', 'dash-footer');
    var show = el('a', 'dash-showcode', tf('Vis koden'));
    show.addEventListener('click', function () { D.unmount(); });
    var progress = el('span', 'dash-progress', '');
    footer.appendChild(show);
    footer.appendChild(progress);
    root.appendChild(footer);
    _state.progress = progress;

    _state.root = root;
    ui.hideNode.hidden = true;
    ui.hideNode.parentNode.insertBefore(root, ui.hideNode);

    // Parse-feil er forfatterfeil — vis dem ærlig i et eget kort øverst.
    if (parsed.errors && parsed.errors.length) {
      var errCard = el('div', 'dash-card dash-error-card');
      errCard.appendChild(el('h3', null, tf('Feil i dashboard-direktivene')));
      var pre = el('pre', 'error', parsed.errors.join('\n'));
      errCard.appendChild(pre);
      grid.insertBefore(errCard, grid.firstChild);
    }
  };

  D.setProgress = function (text) {
    if (_state && _state.progress) _state.progress.textContent = text || '';
  };

  D.unmount = function () {
    if (!_state) return;
    if (_state.root && _state.root.parentNode) _state.root.parentNode.removeChild(_state.root);
    _state.ui.hideNode.hidden = false;
    if (_state.ui.onShowCode) _state.ui.onShowCode();
    _state = null;
  };

  // Feil i setup-sonen (spec §3): ett feilkort erstatter hele gridet.
  D.showSetupError = function (message) {
    if (!_state) return;
    var tf = _state.t;
    if (_state.controls) _state.controls.remove();
    _state.grid.textContent = '';
    var card = el('div', 'dash-card dash-error-card');
    card.appendChild(el('h3', null, tf('Kunne ikke laste dashboardet')));
    card.appendChild(el('pre', 'error', String(message || '')));
    var btn = el('button', 'dash-open-editor', tf('Åpne i editor'));
    btn.type = 'button';
    btn.addEventListener('click', function () { D.unmount(); });
    card.appendChild(btn);
    _state.grid.appendChild(card);
    D.setProgress('');
  };

  // Fylles inn av start() — før det oppdaterer endringer bare lagret verdi.
  D._onChange = function (name, value) {
    if (!_state) return;
    _state.values[name] = value;
    if (_state.queue) _state.queue.change(name, value);
  };
  D._onTabShown = function (indexes) {};   // erstattes av start()

  // ── Orkestrering (spec §3) ────────────────────────────────────────────────
  // Én kjørekjede: initial fylling, widget-batcher og late fane-kjøringer
  // serialiseres alle på _state.chain — aldri to ctx.run i flukt.
  function cardOf(i) { return _state.cards[i]; }

  async function runCell(i) {
    var s = _state;
    if (!s) return;
    var cell = s.parsed.cells[i], c = cardOf(i);
    c.card.classList.add('dash-card--running');
    c.card.classList.remove('dash-card--stale');
    var result = await s.ctx.run(cell.code);
    if (!_state) return;                       // unmount underveis
    s.ctx.renderOutput(result, c.body);
    c.card.classList.remove('dash-card--loading', 'dash-card--running');
    return result;
  }

  function isHidden(i) {
    var c = cardOf(i);
    return !!(c && c.card.closest('.dash-tabpanel[hidden]'));
  }

  function markStale(i) {
    var c = cardOf(i);
    c.card.classList.remove('dash-card--running', 'dash-card--loading');
    c.card.setAttribute('data-stale-label', _state.t('Utdatert'));
    c.card.classList.add('dash-card--stale');
  }

  async function runSet(indexes) {
    var s = _state;
    var failed = false;
    for (var k = 0; k < indexes.length; k++) {
      if (!_state) return;
      var i = indexes[k];
      if (isHidden(i)) { s.dirtyHidden[i] = true; continue; }   // lat (spec §3)
      if (failed) { markStale(i); continue; }                   // nedstrøms for feilet celle
      var res = await runCell(i);
      if (res && res.error) failed = true;
      delete s.dirtyHidden[i];
    }
  }

  D.start = async function (ctx) {
    if (!_state) return;
    var s = _state;
    s.ctx = ctx;
    D.setProgress(s.t('Kjører …'));

    // 1) Widget-defaults i én kjøring (spec §3 pkt 1).
    var assigns = s.parsed.inputs.map(function (inp) {
      return D.assignStatement(ctx.mode, inp.name, s.values[inp.name]);
    });
    if (assigns.length) {
      var r0 = await ctx.run(assigns.join('\n'));
      if (r0 && r0.error) throw new Error(r0.error);
    }

    // 2) Synlige celler i dokumentrekkefølge; skjulte faner venter.
    await runSet(s.parsed.cells.map(function (_, i) { return i; }));
    if (!_state) return;

    // 3) Åpne for interaksjon.
    if (s.controls) s.controls.classList.remove('dash-controls--loading');
    D.setProgress('');
    s.queue = D.createQueue(function (batch) {
      s.chain = s.chain.then(function () { return executeBatch(batch); })['catch'](function () {});
      return s.chain;
    }, 250);
    D._onTabShown = function (indexes) {
      var dirty = indexes.filter(function (i) { return s.dirtyHidden[i]; });
      if (!dirty.length) return;
      s.chain = s.chain.then(function () { return runSet(dirty); })['catch'](function () {});
    };
  };

  async function executeBatch(batch) {
    var s = _state;
    if (!s) return;
    var names = Object.keys(batch);
    var assigns = names.map(function (n) { return D.assignStatement(s.ctx.mode, n, batch[n]); });
    var set = D.planReruns(s.parsed.cells, names, s.ctx.mode);
    set.forEach(function (i) {
      if (!isHidden(i)) cardOf(i).card.classList.add('dash-card--running');
    });
    var r = await s.ctx.run(assigns.join('\n'));
    if (!_state) return;
    if (r && r.error) {
      set.forEach(function (i) { if (!isHidden(i)) markStale(i); });
      return;
    }
    await runSet(set);
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = D;
  global.Dashboard = D;
})(typeof window !== 'undefined' ? window : globalThis);
