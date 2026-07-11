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

  if (typeof module !== 'undefined' && module.exports) module.exports = D;
  global.Dash = D;
})(typeof window !== 'undefined' ? window : globalThis);
