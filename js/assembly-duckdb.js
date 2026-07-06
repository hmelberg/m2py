// Phase 2 (spec 2026-07-06-remote-columnar-sources-design §3): compile a
// mode-neutral AssemblySpec (from js/data-directives.js parseAssembly) into
// SQL that runs against a DuckDB-wasm connection, so import/join push column
// and table selection down to the query engine instead of materializing
// whole sources first. Pure compiler — no duckdb-wasm dependency, so this
// half is unit-testable without a real engine; index.html's pushdown wiring
// executes the output against a real connection.
(function (global) {
  'use strict';

  var PUSHDOWN_FORMATS = { parquet: true, duckdb: true, sqlite: true };

  function canPushdown(spec, descriptors) {
    return (spec.sources || []).every(function (s) {
      var d = descriptors[s];
      return d && PUSHDOWN_FORMATS[d.format];
    });
  }

  function quoteIdent(id) { return '"' + String(id).replace(/"/g, '""') + '"'; }
  function quoteLit(s) { return "'" + String(s).replace(/'/g, "''") + "'"; }

  // One ATTACH per unique duckdb/sqlite FILE URL (not per table) — several
  // tables from the same file share a single catalog attach (design doc §1).
  function buildAttaches(spec, descriptors) {
    var byUrl = {}, order = [];
    (spec.sources || []).forEach(function (s) {
      var d = descriptors[s];
      if (!d || (d.format !== 'duckdb' && d.format !== 'sqlite')) return;
      if (byUrl[d.url]) return;
      byUrl[d.url] = 'att_' + order.length;
      order.push(d.url);
    });
    var statements = order.map(function (url) {
      var alias = byUrl[url];
      var typeClause = descriptorFormatForUrl(descriptors, url) === 'sqlite' ? ' (TYPE sqlite)' : '';
      return 'ATTACH ' + quoteLit(url) + ' AS ' + alias + typeClause;
    });
    return { statements: statements, aliasByUrl: byUrl };
  }
  function descriptorFormatForUrl(descriptors, url) {
    for (var k in descriptors) if (descriptors[k].url === url) return descriptors[k].format;
    return null;
  }

  // A source's SQL "relation reference" — either a pushed-down read_parquet(url)
  // or a qualified reference into an already-ATTACHed duckdb/sqlite catalog.
  function relationRef(sourceKey, descriptors, aliasByUrl) {
    var d = descriptors[sourceKey];
    if (!d) throw new Error('ukjent kilde «' + sourceKey + '» i AssemblyDuckdb.compile');
    if (d.format === 'parquet') return "read_parquet(" + quoteLit(d.url) + ")";
    var attAlias = aliasByUrl[d.url];
    return attAlias + '.' + quoteIdent(d.table);
  }

  function compile(spec, descriptors) {
    var att = buildAttaches(spec, descriptors);
    var datasetStatements = [];

    var all = spec.datasets || [];
    var ordered = all.filter(function (d) { return 'load' in d; })
      .concat(all.filter(function (d) { return !('load' in d); }));

    ordered.forEach(function (ds) {
      if ('load' in ds) {
        var ref = relationRef(ds.load, descriptors, att.aliasByUrl);
        datasetStatements.push({ name: ds.name, sql: 'SELECT * FROM ' + ref });
        return;
      }
      var key = ds.key, sql = null;
      (ds.steps || []).forEach(function (step) {
        if (step.op === 'import') {
          var ref = relationRef(step.source, descriptors, att.aliasByUrl);
          var cols = step.columns.filter(function (c) { return c !== key; });
          var selectCols = [quoteIdent(key)].concat(cols.map(quoteIdent)).join(', ');
          var piece = '(SELECT ' + selectCols + ' FROM ' + ref + ')';
          if (sql === null) {
            sql = piece;
          } else {
            sql = '(SELECT acc.*, piece.* EXCLUDE (' + quoteIdent(key) + ') FROM (' + sql + ') acc ' +
              step.how.toUpperCase() + ' JOIN ' + piece + ' piece USING (' + quoteIdent(key) + '))';
          }
        } else if (step.op === 'join') {
          var otherSql = datasetStatements.find(function (s) { return s.name === step.from; });
          if (!otherSql) throw new Error('ukjent datasett «' + step.from + '» (join into «' + ds.name + '»)');
          sql = '(SELECT acc.*, other.* EXCLUDE (' + quoteIdent(step.on) + ') FROM (' + sql + ') acc ' +
            step.how.toUpperCase() + ' JOIN (' + otherSql.sql + ') other USING (' + quoteIdent(step.on) + '))';
        }
      });
      datasetStatements.push({ name: ds.name, sql: 'SELECT * FROM ' + sql });
    });

    return { attachStatements: att.statements, datasetStatements: datasetStatements };
  }

  global.AssemblyDuckdb = { canPushdown: canPushdown, compile: compile };
})(typeof window !== 'undefined' ? window : globalThis);
