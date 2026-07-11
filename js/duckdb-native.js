// Pyodide-fri SQL-hjelpere for duckdb-modusens native kjørevei (fase 1,
// docs/superpowers/plans/2026-07-11-phase1-duckdb-native.md). 1:1-port av
// parsefunksjonene i duckdb_bridge.py — Python-utgaven forblir sannheten for
// fallback-veien (hybride/montering/remote), denne for rene SQL-kjøringer.
// Ingen DOM- eller duckdb-wasm-avhengighet: kjører under node --test.
(function (global) {
  'use strict';

  // Split a SQL script on top-level semicolons, ignoring those inside string
  // literals ('…'/"…"), -- line comments and /* … */ block comments. Returns
  // non-empty, trimmed statements (their own comments preserved).
  function splitSqlStatements(sql) {
    var stmts = [], buf = [];
    var i = 0, n = sql.length;
    var inSingle = false, inDouble = false, inLine = false, inBlock = false;
    while (i < n) {
      var c = sql[i];
      var nxt = i + 1 < n ? sql[i + 1] : '';
      if (inLine) {
        buf.push(c);
        if (c === '\n') inLine = false;
        i += 1;
      } else if (inBlock) {
        buf.push(c);
        if (c === '*' && nxt === '/') { buf.push(nxt); i += 2; inBlock = false; }
        else i += 1;
      } else if (inSingle) {
        if (c === "'" && nxt === "'") { buf.push(c); buf.push(nxt); i += 2; }
        else { buf.push(c); if (c === "'") inSingle = false; i += 1; }
      } else if (inDouble) {
        buf.push(c);
        if (c === '"') inDouble = false;
        i += 1;
      } else if (c === '-' && nxt === '-') { inLine = true; buf.push(c); i += 1; }
      else if (c === '/' && nxt === '*') { inBlock = true; buf.push(c); i += 1; }
      else if (c === "'") { inSingle = true; buf.push(c); i += 1; }
      else if (c === '"') { inDouble = true; buf.push(c); i += 1; }
      else if (c === ';') {
        var s = buf.join('').trim();
        if (s) stmts.push(s);
        buf = [];
        i += 1;
      } else { buf.push(c); i += 1; }
    }
    var tail = buf.join('').trim();
    if (tail) stmts.push(tail);
    return stmts;
  }

  // sql med -- og /* */-kommentarer fjernet, innholdet i '…'-strenger erstattet
  // med mellomrom, og "-tegn droppet (kvoterte identifikatorer overlever som
  // bare tokens). Brukes til identifikator-skanning og tom-script-sjekken.
  function scrub(sql) {
    var out = [];
    var i = 0, n = sql.length;
    var inSingle = false, inLine = false, inBlock = false;
    while (i < n) {
      var c = sql[i];
      var nxt = i + 1 < n ? sql[i + 1] : '';
      if (inLine) {
        if (c === '\n') { inLine = false; out.push(c); }
        i += 1;
      } else if (inBlock) {
        if (c === '*' && nxt === '/') { inBlock = false; i += 2; out.push(' '); }
        else i += 1;
      } else if (inSingle) {
        if (c === "'" && nxt === "'") i += 2;
        else if (c === "'") { inSingle = false; out.push(' '); i += 1; }
        else i += 1;
      } else if (c === '-' && nxt === '-') { inLine = true; i += 2; }
      else if (c === '/' && nxt === '*') { inBlock = true; i += 2; }
      else if (c === "'") { inSingle = true; i += 1; }
      else if (c === '"') { i += 1; }
      else { out.push(c); i += 1; }
    }
    return out.join('');
  }

  // NB: \w er ASCII-only i JS men unicode i Python — fortsettelsestegnene må
  // derfor være \p{L}\p{N}_ (med u-flagg) for at «lønn» o.l. skal matche som
  // i duckdb_bridge.py (review 2026-07-11 funn 3).
  var CREATE_RE = /\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"?([A-Za-z_][\p{L}\p{N}_]*)"?/giu;

  // Targets of CREATE [OR REPLACE] [TEMP] TABLE [IF NOT EXISTS] name.
  // Order-preserving, deduped, unquoted.
  function extractCreatedTables(statements) {
    var names = [];
    statements.forEach(function (stmt) {
      var scrubbed = scrub(stmt);
      var m;
      CREATE_RE.lastIndex = 0;
      while ((m = CREATE_RE.exec(scrubbed)) !== null) {
        if (names.indexOf(m[1]) === -1) names.push(m[1]);
      }
    });
    return names;
  }

  // The last statement if it begins with SELECT or WITH (a previewable result
  // set), else null.
  function buildPreviewSelect(statements) {
    if (!statements.length) return null;
    var last = statements[statements.length - 1];
    var head = scrub(last).replace(/^\s+/, '').toUpperCase();
    if (head.indexOf('SELECT') === 0 || head.indexOf('WITH') === 0) return last;
    return null;
  }

  // Tekst-tabell fra __arrowToColumns-kolonner ({navn: [verdier]}) — erstatter
  // DataFrame.to_string(index=False) i den native veien: høyrejusterte
  // kolonner med to mellomrom imellom, null → "NaN" som pandas viser det.
  function formatColumnsText(cols) {
    var names = Object.keys(cols);
    if (!names.length) return '';
    var nRows = cols[names[0]].length;
    var cells = names.map(function (name) {
      var out = [name];
      for (var r = 0; r < nRows; r++) {
        var v = cols[name][r];
        out.push(v === null || v === undefined ? 'NaN' : String(v));
      }
      return out;
    });
    var widths = cells.map(function (col) {
      return col.reduce(function (w, s) { return Math.max(w, s.length); }, 0);
    });
    var lines = [];
    for (var r = 0; r <= nRows; r++) {
      var line = cells.map(function (col, ci) {
        var s = col[r];
        return new Array(widths[ci] - s.length + 1).join(' ') + s;
      }).join('  ');
      lines.push(line.replace(/\s+$/, ''));
    }
    return lines.join('\n');
  }

  var api = {
    splitSqlStatements: splitSqlStatements,
    scrub: scrub,
    extractCreatedTables: extractCreatedTables,
    buildPreviewSelect: buildPreviewSelect,
    formatColumnsText: formatColumnsText
  };
  global.DuckdbNative = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
