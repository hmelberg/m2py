// Fase 0 federert (spec 2026-07-29-federated-sources-design §4): ren
// SQL-planlegger for medlems-union — samme deling som assembly-duckdb.js
// (ren kompilator her, index.html kjører resultatet mot duckdb-wasm).
// CSV leses med AssemblyDuckdb.CSV_OPTS så NA/typeregler er identiske med
// monteringsveien. Fase 1 (combine-laget for node-medlemmer) bygger videre
// på denne modulen.
(function (global) {
  'use strict';

  function quoteLit(s) { return "'" + String(s).replace(/'/g, "''") + "'"; }

  function memberRef(f) {
    if (f.format === 'parquet') return 'read_parquet(' + quoteLit(f.fileName) + ')';
    if (f.format === 'csv') return 'read_csv(' + quoteLit(f.fileName) + ', ' + global.AssemblyDuckdb.CSV_OPTS + ')';
    throw new Error('federert: medlemsformat «' + f.format + '» støttes ikke (kun csv/parquet i fase 0)');
  }

  // files: [{id, format, fileName}] -> { describes: [{id, sql}], unionSql }
  // __member: proveniens-kolonne (spec §4) så per-medlem-nedbryting bevares.
  function planUnion(files) {
    var describes = files.map(function (f) {
      return { id: f.id, sql: 'DESCRIBE SELECT * FROM ' + memberRef(f) };
    });
    var unionSql = files.map(function (f) {
      return 'SELECT *, ' + quoteLit(f.id) + ' AS __member FROM ' + memberRef(f);
    }).join(' UNION ALL BY NAME ');
    return { describes: describes, unionSql: unionSql };
  }

  // schemas: [{id, columns}] — nekt ved drift (spec §3: skjemasjekk ved
  // connect). Kolonnerekkefølge er fri (BY NAME); bare navnesettet teller.
  function checkSchemas(schemas) {
    var ref = schemas[0];
    for (var i = 1; i < schemas.length; i++) {
      var missing = ref.columns.filter(function (c) { return schemas[i].columns.indexOf(c) < 0; });
      var extra = schemas[i].columns.filter(function (c) { return ref.columns.indexOf(c) < 0; });
      if (missing.length || extra.length) {
        throw new Error('federert: «' + schemas[i].id + '» har annet skjema enn «' + ref.id + '»'
          + (missing.length ? ' — mangler: ' + missing.join(', ') : '')
          + (extra.length ? ' — ekstra: ' + extra.join(', ') : ''));
      }
    }
  }

  global.Federate = { planUnion: planUnion, checkSchemas: checkSchemas };
})(typeof window !== 'undefined' ? window : globalThis);
