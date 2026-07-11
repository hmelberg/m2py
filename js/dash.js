/* dash.js — dash v2-motor (spec: docs/superpowers/specs/2026-07-11-dash-v2-design.md)
   Ren halvdel (øverst): mosaikk-parsing + auto-layout-plan. Node-testet, ingen DOM.
   DOM-halvdel (nederst): mount, kort, widgets, payload-rendering. Kun browser.
   Adaptere (brython/dash.py m.fl.) kaller det globale `Dash`-API-et; all data
   krysser grensen som JSON-strenger, pluss rå callbacks og DOM-noder. */
(function (global) {
  'use strict';
  var D = {};

  // ---------- ren halvdel ----------

  D.parseMosaic = function (str) {
    if (!str || !String(str).trim()) return { error: 'layout er tom' };
    var rows = String(str).split('\n')
      .map(function (l) { return l.trim(); })
      .filter(function (l) { return l.length; })
      .map(function (l) { return l.split(/\s+/); });
    var cols = rows[0].length;
    if (cols > 12) return { error: 'layout: maks 12 kolonner, fikk ' + cols };
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].length !== cols) {
        return { error: 'layout linje ' + (i + 1) + ': ventet ' + cols +
                 ' navn, fikk ' + rows[i].length };
      }
    }
    var box = {};
    rows.forEach(function (row, r) {
      row.forEach(function (name, c) {
        if (name === '.') return;
        var b = box[name] || (box[name] = { r0: r, r1: r, c0: c, c1: c });
        if (r < b.r0) b.r0 = r; if (r > b.r1) b.r1 = r;
        if (c < b.c0) b.c0 = c; if (c > b.c1) b.c1 = c;
      });
    });
    for (var name in box) {
      var b = box[name];
      for (var r = b.r0; r <= b.r1; r++) {
        for (var c = b.c0; c <= b.c1; c++) {
          if (rows[r][c] !== name) {
            return { error: 'layout: omraadet "' + name +
                     '" er ikke rektangulaert (linje ' + (r + 1) + ')' };
          }
        }
      }
    }
    return {
      columns: cols,
      rows: rows.length,
      names: Object.keys(box),
      gridTemplateAreas: rows.map(function (row) {
        return '"' + row.join(' ') + '"';
      }).join(' ')
    };
  };

  D.autoSpan = function (kind, cols) {
    if (kind === 'number') return 3;
    if (kind === 'markdown' || kind === 'text') return 12;
    if (kind === 'table') return (cols && cols > 6) ? 12 : 6;
    return 6; // figure, image, node, error
  };

  D.autoOrder = function (kind) {
    return kind === 'number' ? 0 : 1;
  };

  // ---------- DOM-halvdel (kun browser) ----------
  var _seq = 0;
  var _dashes = {};  // dashId -> {root, grid, overflow, mosaic, used:{}}
  var _cards = {};   // cardId -> {node, content, placed, figEl}
  var _md = null;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function mdToHtml(text) {
    if (!_md && global.markdownit) _md = global.markdownit({ linkify: true });
    return _md ? _md.render(String(text)) : null;
  }

  function debounce(fn, ms) {
    var t = null;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, args); }, ms);
    };
  }

  function fmtNumber(v) {
    if (typeof v !== 'number' || !isFinite(v)) return String(v);
    var x = Number.isInteger(v) ? v : +v.toFixed(2);
    return x.toLocaleString('nb-NO');
  }

  function themeColor(name, fallback) {
    try {
      var c = getComputedStyle(document.body).getPropertyValue(name).trim();
      return c || fallback;
    } catch (e) { return fallback; }
  }

  D.renderPayload = function (p, nodeEl) {
    var kind = p && p.kind;
    if (kind === 'markdown') {
      var html = mdToHtml(p.text);
      if (html != null) {
        var d = el('div', 'dash-md');
        d.innerHTML = html;
        return d;
      }
      return el('pre', 'dash-text', p.text);
    }
    if (kind === 'text') return el('pre', 'dash-text', p.text);
    if (kind === 'number') {
      var k = el('div', 'dash-kpi');
      k.appendChild(el('span', 'dash-kpi-value', fmtNumber(p.value)));
      if (p.unit) k.appendChild(el('span', 'dash-kpi-unit', p.unit));
      return k;
    }
    if (kind === 'table') {
      var w = el('div', 'dash-table-wrap');
      w.innerHTML = p.html;
      return w;
    }
    if (kind === 'image') {
      var img = el('img', 'dash-img');
      img.src = p.src;
      return img;
    }
    if (kind === 'figure') {
      var f = el('div', 'dash-figure');
      var spec = p.spec || {};
      var layout = Object.assign({
        autosize: true,
        margin: { t: 28, r: 12, b: 36, l: 44 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: themeColor('--text', '#333') }
      }, spec.layout || {});
      setTimeout(function () {
        if (global.Plotly && f.isConnected) {
          global.Plotly.newPlot(f, spec.data || [], layout,
            { responsive: true, displayModeBar: false });
        }
      }, 0);
      return f;
    }
    if (kind === 'node' && nodeEl) return nodeEl;
    if (kind === 'error') {
      var e = el('div', 'dash-error');
      e.appendChild(el('strong', null, 'Feil: '));
      e.appendChild(el('span', null, p.message));
      return e;
    }
    return el('pre', 'dash-text', JSON.stringify(p));
  };

  function buildControl(spec, report) {
    var wrap = el('label', 'dash-widget');
    wrap.appendChild(el('span', 'dash-widget-label', spec.label || spec.name));
    var input, initial;
    if (spec.type === 'slider') {
      input = el('input');
      input.type = 'range';
      input.min = spec.min; input.max = spec.max;
      if (spec.step != null) input.step = spec.step;
      input.value = spec.default;
      initial = Number(spec.default);
      var out = el('span', 'dash-widget-value', fmtNumber(initial));
      input.addEventListener('input', function () {
        out.textContent = fmtNumber(Number(input.value));
        report(spec.name, Number(input.value));
      });
      wrap.appendChild(input);
      wrap.appendChild(out);
    } else if (spec.type === 'dropdown') {
      input = el('select');
      (spec.options || []).forEach(function (o) {
        input.appendChild(el('option', null, o));
      });
      input.selectedIndex = spec.index || 0;
      initial = spec.index || 0;
      input.addEventListener('change', function () {
        report(spec.name, input.selectedIndex);
      });
      wrap.appendChild(input);
    } else if (spec.type === 'checkbox') {
      input = el('input');
      input.type = 'checkbox';
      input.checked = !!spec.default;
      initial = !!spec.default;
      input.addEventListener('change', function () {
        report(spec.name, input.checked);
      });
      wrap.classList.add('dash-widget--check');
      wrap.insertBefore(input, wrap.firstChild);
    } else if (spec.type === 'numberfield') {
      input = el('input');
      input.type = 'number';
      if (spec.min != null) input.min = spec.min;
      if (spec.max != null) input.max = spec.max;
      if (spec.step != null) input.step = spec.step;
      input.value = spec.default;
      initial = Number(spec.default);
      input.addEventListener('change', function () {
        report(spec.name, Number(input.value));
      });
      wrap.appendChild(input);
    } else { // textfield
      input = el('input');
      input.type = 'text';
      input.value = spec.default != null ? spec.default : '';
      initial = String(input.value);
      input.addEventListener('change', function () {
        report(spec.name, input.value);
      });
      wrap.appendChild(input);
    }
    return { node: wrap, name: spec.name, initial: initial };
  }

  function buildControls(specs, onChange, cls) {
    var bar = el('div', cls);
    var values = {};
    var fire = debounce(function () {
      if (typeof onChange === 'function') onChange(JSON.stringify(values));
    }, 150);
    function report(name, value) { values[name] = value; fire(); }
    specs.forEach(function (spec) {
      var c = buildControl(spec, report);
      values[c.name] = c.initial;
      bar.appendChild(c.node);
    });
    return bar;
  }

  D.create = function (optsJson) {
    // Rydd registeret for stale oppforinger fra tidligere kjoringer for samme
    // rerun-syklus (outputArea.innerHTML = '' fjerner DOM-noder uten a rydde
    // _dashes/_cards, ellers vokser registeret ubegrenset og gamle Plotly-
    // instanser lekker).
    for (var did in _dashes) {
      if (_dashes[did].root && !_dashes[did].root.isConnected) delete _dashes[did];
    }
    for (var cid in _cards) {
      if (_cards[cid].node && !_cards[cid].node.isConnected) delete _cards[cid];
    }
    var opts = JSON.parse(optsJson || '{}');
    var container = document.getElementById('outputArea');
    var root = el('div', 'dash');
    if (opts.title) {
      var head = el('header', 'dash-header');
      head.appendChild(el('h1', 'dash-title', opts.title));
      root.appendChild(head);
    }
    var mosaic = null;
    if (opts.layout) {
      var m = D.parseMosaic(opts.layout);
      if (m.error) {
        root.appendChild(el('div', 'dash-error', m.error));
      } else {
        mosaic = m;
      }
    }
    var grid = el('div', 'dash-grid');
    if (mosaic) {
      grid.style.gridTemplateAreas = mosaic.gridTemplateAreas;
      grid.style.gridTemplateColumns = 'repeat(' + mosaic.columns + ', 1fr)';
    } else {
      grid.style.gridTemplateColumns = 'repeat(12, 1fr)';
    }
    root.appendChild(grid);
    container.appendChild(root);
    var id = 'dash' + (++_seq);
    _dashes[id] = { root: root, grid: grid, overflow: null, mosaic: mosaic, used: {} };
    return id;
  };

  function placeCard(dash, rec, kind, cols) {
    if (rec.placed) return;
    if (dash.mosaic) {
      var area = rec.area;
      if (!area) {
        area = dash.mosaic.names.find(function (n) { return !dash.used[n]; });
      } else if (dash.used[area]) {
        area = null;   // eksplisitt at= peker på et allerede brukt omraade -> overflow, ikke dobbel-tildeling
      }
      if (area && dash.mosaic.names.indexOf(area) !== -1) {
        dash.used[area] = true;
        rec.node.style.gridArea = area;
        dash.grid.appendChild(rec.node);
      } else {
        if (!dash.overflow) {
          dash.overflow = el('div', 'dash-grid dash-grid--overflow');
          dash.overflow.style.gridTemplateColumns = 'repeat(12, 1fr)';
          dash.root.appendChild(dash.overflow);
          if (rec.area) console.warn('dash: omraadet "' + rec.area +
            '" finnes ikke i layout eller er allerede brukt; kortet legges under gridet');
        }
        rec.node.style.gridColumn = 'span ' + D.autoSpan(kind, cols);
        dash.overflow.appendChild(rec.node);
      }
    } else {
      rec.node.style.gridColumn = 'span ' + D.autoSpan(kind, cols);
      rec.node.style.order = D.autoOrder(kind);
      dash.grid.appendChild(rec.node);
    }
    rec.placed = true;
  }

  D.addCard = function (dashId, optsJson, onChange, nodeEl) {
    var dash = _dashes[dashId];
    var opts = JSON.parse(optsJson || '{}');
    var card = el('section', 'dash-card');
    if (opts.title) card.appendChild(el('h3', 'dash-cardtitle', opts.title));
    if (opts.controls && opts.controls.length) {
      card.appendChild(buildControls(opts.controls, onChange, 'dash-cardbar'));
    }
    var content = el('div', 'dash-content');
    card.appendChild(content);
    var cardId = 'dashcard' + (++_seq);
    var rec = { node: card, content: content, placed: false,
                area: opts.area || null, dashId: dashId };
    _cards[cardId] = rec;
    if (opts.content) {
      D.updateCard(cardId, JSON.stringify(opts.content), nodeEl); // plasserer også
    } else {
      card.classList.add('dash-card--loading');
      placeCard(dash, rec, 'figure', 0); // foreløpig plassering for funksjonskort
    }
    return cardId;
  };

  D.updateCard = function (cardId, payloadJson, nodeEl) {
    var rec = _cards[cardId];
    if (!rec) return;
    var p = JSON.parse(payloadJson);
    if (rec.figEl && global.Plotly) { try { global.Plotly.purge(rec.figEl); } catch (e) {} }
    rec.content.innerHTML = '';
    var node = D.renderPayload(p, nodeEl);
    rec.figEl = (p.kind === 'figure') ? node : null;
    rec.content.appendChild(node);
    rec.node.classList.remove('dash-card--loading');
    rec.node.classList.toggle('dash-card--error', p.kind === 'error');
    if (rec.dashId && !rec.placed) {
      placeCard(_dashes[rec.dashId], rec, p.kind, p.cols || 0);
    }
  };

  D.addControls = function (dashId, specsJson, onChange) {
    var dash = _dashes[dashId];
    var specs = JSON.parse(specsJson || '[]');
    var bar = buildControls(specs, onChange, 'dash-controls');
    dash.root.insertBefore(bar, dash.grid);
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = D;
  global.Dash = D;
})(typeof window !== 'undefined' ? window : globalThis);
