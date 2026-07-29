# Federert fase 0 (pull-federation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `federert(...)` / registry-defined federated source expands into N member fetches plus an automatic DuckDB union (with a `__member` provenance column), so every mode analyzes the members as one dataset.

**Architecture:** Parsing/resolution stays pure in `js/data-directives.js` (a federated connect resolves to ONE load item carrying a `federated: [subitems]` list). `js/federate.js` is a new pure SQL planner (no duckdb-wasm dependency, mirroring `js/assembly-duckdb.js`). `js/data-loader.js` fans out member fetches through the existing fetch/decrypt/cache machinery and calls an injected `deps.unionExec` to merge; `index.html` provides the only real executor, backed by the existing `__ensureDuckDB()` singleton. Because the merged result is a single parquet load item, **no per-mode binding code changes**.

**Tech Stack:** ES5-style IIFE browser modules (match existing `js/*.js`), duckdb-wasm (`UNION ALL BY NAME`), Node `node:test` for JS tests, pandas for the demo split script.

**Spec:** `docs/superpowers/specs/2026-07-29-federated-sources-design.md` §3–§4 (Phase 0 only).

## Global Constraints

- JS modules use the existing ES5 IIFE style (`var`, `function`, no arrow functions, `global.X = {...}` export) — match `js/data-directives.js`.
- User-facing error messages are Norwegian, lowercase-start, guillemets around identifiers («…») — match existing messages.
- JS tests: `tests/js/*.test.js`, Node `node:test` + `require('node:assert')`, module loaded via `require('../../js/<file>.js')` then `globalThis.<Export>`. Run: `node --test tests/js/`.
- Phase 0 tier enforcement (spec §3): a member with `level: "sensitive"` is refused at resolve time; node/anvil members are refused with a Phase-1 message.
- Never put data keys in `data/data-sources.json` (it is public); keys come only from `key(...)` directives or `promptKey`.
- Supported member formats in v1: `csv` and `parquet` (post-decryption). Anything else → Norwegian error.
- Commit after every task; no pushes (safestat pushes are Hans's call).

---

### Task 1: Parse `federert(...)` connect lines

**Files:**
- Modify: `js/data-directives.js` (regexes at top, `parse()` at line ~48)
- Test: `tests/js/data-directives-federert.test.js` (new)

**Interfaces:**
- Produces: `DataDirectives.parse(script).connects[i]` gains an optional `federated: string[]` field (member targets, trimmed). `target` is `null` for federated connects. Task 2's `resolve()` consumes this.

- [ ] **Step 1: Write the failing tests**

Create `tests/js/data-directives-federert.test.js`:

```js
// tests/js/data-directives-federert.test.js — federert(...)-kilder, fase 0
// (spec 2026-07-29-federated-sources-design §3–4).
const test = require('node:test');
const assert = require('node:assert');
require('../../js/data-directives.js');
const DD = globalThis.DataDirectives;

test('parse: federert() med mellomrom og as-alias', () => {
  const r = DD.parse('# connect federert(https://a.no/d, https://b.no/d) as helse');
  assert.equal(r.errors.length, 0);
  assert.equal(r.connects.length, 1);
  assert.equal(r.connects[0].alias, 'helse');
  assert.equal(r.connects[0].target, null);
  assert.deepEqual(r.connects[0].federated, ['https://a.no/d', 'https://b.no/d']);
});

test('parse: federert() uten mellomrom fanges ikke av vanlig connect', () => {
  const r = DD.parse('# connect federert(reg-a,reg-b) as h');
  assert.equal(r.connects.length, 1);
  assert.deepEqual(r.connects[0].federated, ['reg-a', 'reg-b']);
});

test('parse: federert() med options-hale', () => {
  const r = DD.parse('# connect federert(a, b) as h, key(ask), kind(parquet)');
  assert.equal(r.connects[0].options.key, 'ask');
  assert.equal(r.connects[0].options.kind, 'parquet');
});

test('parse: tom federert() gir feil', () => {
  const r = DD.parse('# connect federert() as h');
  assert.equal(r.connects.length, 0);
  assert.equal(r.errors.length, 1);
  assert.ok(r.errors[0].indexOf('federert') >= 0);
});

test('parse: federert krever alias', () => {
  const r = DD.parse('# connect federert(a, b)');
  assert.equal(r.connects.length, 0);
  assert.equal(r.errors.length, 1);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/data-directives-federert.test.js`
Expected: FAIL (federated undefined / connects mismatch — plain CONNECT_RE mis-parses these lines today).

- [ ] **Step 3: Implement parsing**

In `js/data-directives.js`, add below `LOAD_RE` (line 17):

```js
  // Fase 0 federert (spec 2026-07-29-federated-sources-design §3):
  //   # connect federert(<medlem>[, <medlem>...]) as alias [, key(...)][, kind(...)]
  // Medlem = URL eller register-id. Må matches FØR CONNECT_RE (uten mellomrom
  // i listen ville CONNECT_RE ellers slukt hele "federert(a,b)" som target).
  var CONNECT_FED_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*connect[ \t]+federert\(([^)]*)\)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;
```

In `parse()` (line 48), before the `CONNECT_RE` loop add:

```js
    CONNECT_FED_RE.lastIndex = 0;
    while ((m = CONNECT_FED_RE.exec(script)) !== null) {
      var members = m[1].split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      if (!members.length) { errors.push('federert() krever minst ett medlem: ' + m[0].trim()); continue; }
      if (!m[2]) { errors.push('connect federert(...) krever "as <alias>"'); continue; }
      connects.push({ target: null, federated: members, alias: m[2], options: parseOptions(m[3]) });
    }
```

And in the existing `CONNECT_RE` loop, skip lines the federated regex owns (first line inside the `while`):

```js
      if (/^federert\(/i.test(m[1])) continue;   // eies av CONNECT_FED_RE (også feiltilfellene)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/data-directives-federert.test.js` → PASS (5/5).
Also run the full suite to catch regressions: `node --test tests/js/` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add js/data-directives.js tests/js/data-directives-federert.test.js
git commit -m "feat(federert): parse connect federert(...) member lists"
```

---

### Task 2: `resolve()` expands federated sources (inline + registry), with tier enforcement

**Files:**
- Modify: `js/data-directives.js` (`resolve()` at line ~74, `findRegistrySource` nearby)
- Test: `tests/js/data-directives-federert.test.js` (extend)

**Interfaces:**
- Consumes: Task 1's `connects[i].federated`.
- Produces: `DataDirectives.resolve(parsed, registry)` returns, for a load whose connect is federated, ONE item:
  `{ alias, federated: [{ id, url, viaProxy, kind, key }...], overlap?, entity? }`
  or `{ alias, error }`. Registry entries with `kind: "federated"` and `members: [{id, url, level?, kind?}]` expand the same way. Task 4 consumes `item.federated`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/js/data-directives-federert.test.js`:

```js
const REG = [
  { id: 'reg-a', navn: 'A', base_url: 'https://a.no/data', cors: true },
  { id: 'reg-auth', navn: 'B', base_url: 'https://b.no/data', auth: { type: 'apikey' } },
  { id: 'reg-sens', navn: 'S', base_url: 'https://s.no/data', level: 'sensitive' },
  { id: 'demo-fed', navn: 'Demo', kind: 'federated', overlap: 'possible', entity: 'person_id',
    members: [
      { id: 'nord', url: 'https://nord.no/person.parquet' },
      { id: 'vest', url: 'https://vest.no/person.parquet' },
    ] },
  { id: 'fed2', navn: 'F2', kind: 'federated', members: [{ id: 'x', url: 'https://x.no/f.csv' }] },
];

function resolveScript(script) {
  return DD.resolve(DD.parse(script), REG);
}

test('resolve: inline federert med URL-medlemmer og sti-appending', () => {
  const items = resolveScript('# connect federert(https://a.no/d, https://b.no/d) as h\n# load h/person.parquet as df');
  assert.equal(items.length, 1);
  assert.equal(items[0].alias, 'df');
  assert.equal(items[0].federated.length, 2);
  assert.equal(items[0].federated[0].url, 'https://a.no/d/person.parquet');
  assert.equal(items[0].federated[0].id, 'm1');
  assert.equal(items[0].federated[1].id, 'm2');
});

test('resolve: inline federert med register-id-medlemmer', () => {
  const items = resolveScript('# connect federert(reg-a, reg-auth) as h\n# load h/t.csv as df');
  assert.equal(items[0].federated[0].url, 'https://a.no/data/t.csv');
  assert.equal(items[0].federated[0].id, 'reg-a');
  assert.equal(items[0].federated[1].viaProxy, true);
});

test('resolve: register-definert federert kilde, load uten sti', () => {
  const items = resolveScript('# connect demo-fed as h\n# load h as df');
  assert.equal(items[0].federated.length, 2);
  assert.equal(items[0].federated[0].url, 'https://nord.no/person.parquet');
  assert.equal(items[0].federated[0].id, 'nord');
  assert.equal(items[0].overlap, 'possible');
  assert.equal(items[0].entity, 'person_id');
});

test('resolve: sensitive-medlem nektes (fase 0-tier)', () => {
  const items = resolveScript('# connect federert(reg-a, reg-sens) as h\n# load h/t.csv as df');
  assert.ok(items[0].error);
  assert.ok(items[0].error.indexOf('reg-sens') >= 0);
});

test('resolve: ukjent register-id som medlem gir feil (ingen stille anvil)', () => {
  const items = resolveScript('# connect federert(reg-a, finnes-ikke) as h\n# load h/t.csv as df');
  assert.ok(items[0].error);
  assert.ok(items[0].error.indexOf('finnes-ikke') >= 0);
});

test('resolve: nestet federert medlem gir feil', () => {
  const items = resolveScript('# connect federert(reg-a, fed2) as h\n# load h/t.csv as df');
  assert.ok(items[0].error);
});

test('resolve: connect-nivå key() arves av medlemmene', () => {
  const items = resolveScript('# connect federert(https://a.no/d, https://b.no/d) as h, key(hemmelig)\n# load h/t.enc as df');
  assert.equal(items[0].federated[0].key, 'hemmelig');
  assert.equal(items[0].federated[1].key, 'hemmelig');
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/data-directives-federert.test.js`
Expected: new tests FAIL («ukjent kilde-alias» / no `federated` on items).

- [ ] **Step 3: Implement resolution**

In `js/data-directives.js`, add a helper above `resolve()`:

```js
  // Fase 0: gjør ett federert medlem om til et sub-item for fetch-laget.
  // rest = valgfri sti fra load-linjen — appendes når medlemmet er en base
  // (samme relative layout hos hver dataholder er det naturlige for
  // horisontal federering). level 'sensitive' nektes her (spec §3: pull-
  // tier er aldri nok for sensitive — krever node, som er fase 1).
  function resolveFederatedMember(target, idx, rest, opts, registry) {
    var sub = { id: 'm' + (idx + 1), url: '', viaProxy: false,
                key: opts.key, kind: opts.kind };
    var level = null;
    if (isUrlish(target)) {
      sub.url = target;
    } else {
      var src = findRegistrySource(registry, target);
      if (!src) return { error: 'ukjent federert medlem «' + target + '» (ikke i registeret, og ikke en URL)' };
      if (src.kind === 'federated' || src.members) return { error: 'federert medlem «' + target + '» er selv federert — nesting støttes ikke' };
      sub.id = src.id;
      sub.url = src.base_url;
      sub.viaProxy = !!src.auth || src.cors === false;
      level = src.level || null;
    }
    if (level === 'sensitive') return { error: 'federert medlem «' + target + '» er sensitivt — pull-federering (fase 0) er ikke lov; krever node-medlem (fase 1)' };
    if (level) sub.level = level;
    if (rest) {
      if (sub.url.charAt(sub.url.length - 1) !== '/') sub.url += '/';
      sub.url += rest;
    }
    return sub;
  }
```

In `resolve()`'s map callback, after `var conn = byAlias[head];` and the missing-connect guard (line ~88), insert the federated branches **before** the existing `copts`-handling continues (the registry-compound branch replaces the `findRegistrySource` path when the entry is federated):

```js
      var copts = conn.options || {};
      // Fase 0 federert: inline federert(...)-connect ELLER register-oppslag
      // med kind:'federated' — begge gir ETT item med federated-liste.
      var fedTargets = null, fedMeta = {};
      if (conn.federated) {
        fedTargets = conn.federated.map(function (t) { return { target: t }; });
      } else if (!isUrlish(conn.target)) {
        var srcMaybe = findRegistrySource(registry, conn.target);
        if (srcMaybe && (srcMaybe.kind === 'federated' || srcMaybe.members)) {
          fedTargets = (srcMaybe.members || []).map(function (mm) { return { target: mm.url || mm.id, member: mm }; });
          fedMeta = srcMaybe;
        }
      }
      if (fedTargets) {
        var mopts = { key: lopts.key || copts.key, kind: lopts.kind || copts.kind };
        var subs = [], fedErr = null;
        fedTargets.forEach(function (ft, fi) {
          if (fedErr) return;
          var sub = resolveFederatedMember(ft.target, fi, rest, mopts, registry);
          if (sub.error) { fedErr = sub.error; return; }
          if (ft.member) {
            if (ft.member.id) sub.id = ft.member.id;
            if (ft.member.kind) sub.kind = ft.member.kind;
            if (ft.member.level === 'sensitive') { fedErr = 'federert medlem «' + sub.id + '» er sensitivt — pull-federering (fase 0) er ikke lov; krever node-medlem (fase 1)'; return; }
            if (ft.member.level) sub.level = ft.member.level;
          }
          subs.push(sub);
        });
        if (fedErr) return { alias: l.alias, error: fedErr };
        var fedItem = { alias: l.alias, federated: subs };
        if (fedMeta.overlap) fedItem.overlap = fedMeta.overlap;
        if (fedMeta.entity) fedItem.entity = fedMeta.entity;
        return fedItem;
      }
```

(The existing `var copts = conn.options || {};` line is replaced by this block's first line — don't duplicate it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/data-directives-federert.test.js` → PASS (12/12).
Run: `node --test tests/js/` → all PASS (no regressions in use/segment tests).

- [ ] **Step 5: Commit**

```bash
git add js/data-directives.js tests/js/data-directives-federert.test.js
git commit -m "feat(federert): resolve inline and registry federated sources with tier enforcement"
```

---

### Task 3: `js/federate.js` — pure union planner + schema check

**Files:**
- Create: `js/federate.js`
- Modify: `js/assembly-duckdb.js:136` (export `CSV_OPTS`)
- Test: `tests/js/federate.test.js` (new)

**Interfaces:**
- Consumes: `AssemblyDuckdb.CSV_OPTS` (newly exported; the pandas-mimicking read_csv options at `js/assembly-duckdb.js:22`).
- Produces:
  - `Federate.planUnion(files)` — `files: [{id, format('csv'|'parquet'), fileName}]` → `{ describes: [{id, sql}], unionSql }`. `unionSql` selects `*, '<id>' AS __member` per member joined with `UNION ALL BY NAME`.
  - `Federate.checkSchemas(schemas)` — `schemas: [{id, columns: string[]}]`; throws a Norwegian error naming the drifting member and its missing/extra columns; returns undefined when consistent (column ORDER may differ — only the name sets are compared).

- [ ] **Step 1: Write the failing tests**

Create `tests/js/federate.test.js`:

```js
// tests/js/federate.test.js — ren union-planlegger for federerte kilder
// (spec 2026-07-29-federated-sources-design §4; mønster fra assembly-duckdb).
const test = require('node:test');
const assert = require('node:assert');
require('../../js/assembly-duckdb.js');
require('../../js/federate.js');
const F = globalThis.Federate;

const FILES = [
  { id: 'nord', format: 'parquet', fileName: 'fed_h_0.parquet' },
  { id: 'vest', format: 'csv', fileName: 'fed_h_1.csv' },
];

test('planUnion: __member-kolonne og UNION ALL BY NAME', () => {
  const p = F.planUnion(FILES);
  assert.ok(p.unionSql.indexOf("'nord' AS __member") >= 0);
  assert.ok(p.unionSql.indexOf("'vest' AS __member") >= 0);
  assert.ok(p.unionSql.indexOf('UNION ALL BY NAME') >= 0);
  assert.ok(p.unionSql.indexOf("read_parquet('fed_h_0.parquet')") >= 0);
  assert.ok(p.unionSql.indexOf("read_csv('fed_h_1.csv'") >= 0);
});

test('planUnion: describes per medlem', () => {
  const p = F.planUnion(FILES);
  assert.equal(p.describes.length, 2);
  assert.equal(p.describes[0].id, 'nord');
  assert.ok(p.describes[0].sql.indexOf('DESCRIBE') === 0);
});

test('planUnion: ukjent format gir norsk feil', () => {
  assert.throws(() => F.planUnion([{ id: 'x', format: 'sqlite', fileName: 'f' }]), /støttes ikke/);
});

test('checkSchemas: likt sett i annen rekkefølge er OK', () => {
  F.checkSchemas([
    { id: 'a', columns: ['x', 'y'] },
    { id: 'b', columns: ['y', 'x'] },
  ]);
});

test('checkSchemas: drift nevner medlem og kolonner', () => {
  assert.throws(
    () => F.checkSchemas([
      { id: 'a', columns: ['x', 'y'] },
      { id: 'b', columns: ['x', 'z'] },
    ]),
    (e) => e.message.indexOf('«b»') >= 0 && e.message.indexOf('y') >= 0 && e.message.indexOf('z') >= 0
  );
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/federate.test.js`
Expected: FAIL — `Cannot find module '../../js/federate.js'`.

- [ ] **Step 3: Implement**

In `js/assembly-duckdb.js` line 136, change the export to:

```js
  global.AssemblyDuckdb = { canPushdown: canPushdown, compile: compile, CSV_OPTS: CSV_OPTS };
```

Create `js/federate.js`:

```js
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/federate.test.js` → PASS (5/5). Full suite: `node --test tests/js/` → PASS.

- [ ] **Step 5: Commit**

```bash
git add js/federate.js js/assembly-duckdb.js tests/js/federate.test.js
git commit -m "feat(federert): pure union planner with schema-drift check"
```

---

### Task 4: `data-loader.js` fan-out fetch + injected `unionExec`

**Files:**
- Modify: `js/data-loader.js` (`fetchResolvedItems` line ~121, `resolveSourcesOnly` line ~290)
- Test: `tests/js/data-loader-federert.test.js` (new)

**Interfaces:**
- Consumes: Task 2's `item.federated` subitems (`{id, url, viaProxy, kind, key, level}`); existing `fetchBytes`/`sniffFormat`/`maybeDecrypt` internals.
- Produces: `fetchResolvedItems` handles federated items by fetching every member through the shared cache/decrypt path, then calling `deps.unionExec(alias, memberLoads, meta)` where `memberLoads: [{id, bytes, format}]` and `meta: {overlap?, entity?}`; it must return `{bytes: Uint8Array, format: 'parquet'}`. The final load object is `{alias, bytes, format: 'parquet', federated: true, overlap?, level?}` (level = most restrictive member level, orden `public < protected < sensitive`). Missing `deps.unionExec` → Norwegian error. `resolveSourcesOnly` skips federated items in `descriptors` (so `canPushdown` is false and assembly falls back to full materialization).

- [ ] **Step 1: Write the failing tests**

Create `tests/js/data-loader-federert.test.js`:

```js
// tests/js/data-loader-federert.test.js — fan-out + unionExec for federerte
// kilder (spec 2026-07-29-federated-sources-design §4). Fake fetch/union.
const test = require('node:test');
const assert = require('node:assert');
require('../../js/data-directives.js');
require('../../js/data-loader.js');
const DL = globalThis.DataLoader;

const REG = [
  { id: 'demo-fed', navn: 'Demo', kind: 'federated', overlap: 'possible',
    members: [
      { id: 'nord', url: 'https://nord.no/person.csv' },
      { id: 'vest', url: 'https://vest.no/person.csv', level: 'protected' },
    ] },
];

function fakeFetch(urls) {
  return async (url) => {
    urls.push(url);
    return {
      ok: true,
      headers: { get: () => 'text/csv' },
      arrayBuffer: async () => new TextEncoder().encode('x,y\n1,2\n').buffer,
    };
  };
}

const SCRIPT = '# connect demo-fed as h\n# load h as df';

test('federert: henter alle medlemmer og kaller unionExec', async () => {
  DL._resetCacheForTests();
  const urls = [];
  let called = null;
  const r = await DL.resolveAndFetchLoads(SCRIPT, {
    fetchImpl: fakeFetch(urls), registry: REG,
    unionExec: async (alias, members, meta) => {
      called = { alias, members, meta };
      return { bytes: new Uint8Array([1]), format: 'parquet' };
    },
  });
  assert.deepEqual(urls.sort(), ['https://nord.no/person.csv', 'https://vest.no/person.csv']);
  assert.equal(called.alias, 'df');
  assert.equal(called.members.length, 2);
  assert.equal(called.members[0].id, 'nord');
  assert.equal(called.members[0].format, 'csv');
  assert.equal(called.meta.overlap, 'possible');
  assert.equal(r.loads.length, 1);
  assert.equal(r.loads[0].format, 'parquet');
  assert.equal(r.loads[0].federated, true);
  assert.equal(r.loads[0].overlap, 'possible');
  assert.equal(r.loads[0].level, 'protected');   // mest restriktive medlem
});

test('federert: mangler unionExec gir norsk feil', async () => {
  DL._resetCacheForTests();
  await assert.rejects(
    DL.resolveAndFetchLoads(SCRIPT, { fetchImpl: fakeFetch([]), registry: REG }),
    /unionExec/
  );
});

test('federert: sensitive medlem stoppes allerede i resolve-laget', async () => {
  DL._resetCacheForTests();
  const reg = [{ id: 'f', navn: 'F', kind: 'federated',
    members: [{ id: 's', url: 'https://s.no/d.csv', level: 'sensitive' }] }];
  await assert.rejects(
    DL.resolveAndFetchLoads('# connect f as h\n# load h as df',
      { fetchImpl: fakeFetch([]), registry: reg, unionExec: async () => ({}) }),
    /sensitivt/
  );
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/js/data-loader-federert.test.js`
Expected: FAIL (federated items fall through the normal single-fetch path / no unionExec handling).

- [ ] **Step 3: Implement**

In `js/data-loader.js`, inside `fetchResolvedItems`, add a helper before the final `return Promise.all(...)` and a federated branch at the top of its map callback:

```js
    var LEVEL_ORDER = { public: 0, protected: 1, sensitive: 2 };
    function maxLevel(members) {
      var lv = null;
      members.forEach(function (m) {
        if (m.level && (!lv || LEVEL_ORDER[m.level] > LEVEL_ORDER[lv])) lv = m.level;
      });
      return lv;
    }
```

and in the map callback (`localItems.map(async function (item) { ... })`), first thing:

```js
      if (item.federated) {
        // Fase 0 federert (spec §4): hvert medlem gjennom samme fetch/
        // decrypt/cache-vei som et vanlig load-item, deretter union via
        // injisert executor (index.html = duckdb-wasm; tester = fake).
        if (!deps.unionExec) throw new Error('federert kilde «' + item.alias + '» krever union-motoren (unionExec mangler)');
        var memberLoads = await Promise.all(item.federated.map(async function (mem) {
          var mf = await fetchBytes(mem);
          var mfmt = sniffFormat(mf.resp, mem.url, mem.kind);
          var mdec = await maybeDecrypt(mem, mf.buf, mfmt, deps);
          return { id: mem.id, bytes: mdec.bytes, format: mdec.format };
        }));
        var meta = {};
        if (item.overlap) meta.overlap = item.overlap;
        if (item.entity) meta.entity = item.entity;
        var merged = await deps.unionExec(item.alias, memberLoads, meta);
        var fedOut = { alias: item.alias, bytes: merged.bytes, format: 'parquet', federated: true };
        if (item.overlap) fedOut.overlap = item.overlap;
        var fedLv = maxLevel(item.federated);
        if (fedLv) fedOut.level = fedLv;
        return fedOut;
      }
```

In `resolveSourcesOnly` (line ~291), extend the descriptor guard:

```js
      if (r.error || r.anvil || r.federated) return; // aldri pushdown-kandidater
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/js/data-loader-federert.test.js` → PASS (3/3). Full suite: `node --test tests/js/` → PASS.

- [ ] **Step 5: Commit**

```bash
git add js/data-loader.js tests/js/data-loader-federert.test.js
git commit -m "feat(federert): member fan-out fetch and injected unionExec in data loader"
```

---

### Task 5: index.html wiring — real DuckDB executor + deps injection

**Files:**
- Modify: `index.html` (near `__ensureDuckDB`'s definition; every deps object passed to `resolveAndFetchLoads`/`resolveAssemblyOrLoads`/`fetchResolvedItems` — find them with `grep -n "authorizeStrict:" index.html`)
- Modify: `index.html` `<script src=...>` block — add `js/federate.js` after `js/assembly-duckdb.js`.

**Interfaces:**
- Consumes: `Federate.planUnion`/`checkSchemas` (Task 3), `__ensureDuckDB()` (existing), `deps.unionExec` contract (Task 4).
- Produces: `__federatedUnion(alias, members, meta)` available to every mode's deps.

- [ ] **Step 1: Find the wiring points**

Run: `grep -n "authorizeStrict:" index.html` and `grep -n "__ensureDuckDB" index.html | head -3`.
Expected: ~4–6 deps sites (python/duckdb ~3711/3743, R ~8486, safestat-require ~9690, possibly AI/preview paths) plus the `__ensureDuckDB` definition.

- [ ] **Step 2: Implement the executor**

Below `__ensureDuckDB`'s definition add (adjust `db.connect()`/`copyFileToBuffer` calls to exactly match how `resolveAssemblyOrLoads` at `index.html:8427-8440` uses the singleton — same API, same cleanup style):

```js
    // Fase 0 federert (spec 2026-07-29-federated-sources-design §4): den ENE
    // virkelige unionExec — medlemsbytes inn, én parquet ut, med __member-
    // kolonne og skjemasjekk. Ren plan fra js/federate.js.
    async function __federatedUnion(alias, members, meta) {
      var db = await __ensureDuckDB();
      var conn = await db.connect();
      var files = members.map(function (m, i) {
        return { id: m.id, format: m.format, fileName: 'fed_' + alias + '_' + i + '.' + m.format };
      });
      try {
        for (var i = 0; i < members.length; i++) {
          await db.registerFileBuffer(files[i].fileName, members[i].bytes);
        }
        var plan = window.Federate.planUnion(files);
        var schemas = [];
        for (var j = 0; j < plan.describes.length; j++) {
          var dres = await conn.query(plan.describes[j].sql);
          schemas.push({ id: plan.describes[j].id,
            columns: dres.toArray().map(function (row) { return row.column_name; }) });
        }
        window.Federate.checkSchemas(schemas);
        if (meta && meta.overlap === 'possible') {
          console.info('federert «' + alias + '»: medlemmer kan overlappe — tellinger er episodenivå');
        }
        var outName = 'fed_' + alias + '_union.parquet';
        await conn.query("COPY (" + plan.unionSql + ") TO '" + outName + "' (FORMAT PARQUET)");
        var bytes = await db.copyFileToBuffer(outName);
        try { await db.dropFile(outName); } catch (e) { /* best-effort */ }
        return { bytes: bytes, format: 'parquet' };
      } finally {
        for (var k = 0; k < files.length; k++) {
          try { await db.dropFile(files[k].fileName); } catch (e) { /* best-effort */ }
        }
        await conn.close();
      }
    }
```

- [ ] **Step 3: Inject into every deps site**

At each deps object found in Step 1, add one line: `unionExec: __federatedUnion,` (respect each site's naming — some use `_deps`, `_rDeps` etc.). Also add the script tag `<script src="js/federate.js"></script>` immediately after the `assembly-duckdb.js` one.

If `__federatedUnion` is defined in a different scope than a deps site (check!), hoist it to the same top-level scope as `__ensureDuckDB` — both must be reachable from all mode runners.

- [ ] **Step 4: Static check + full JS suite**

Run: `node --test tests/js/` → PASS.
Run: `node -e "const s=require('fs').readFileSync('index.html','utf8'); if(!/js\/federate\.js/.test(s)) throw new Error('script tag missing'); console.log('unionExec sites:', (s.match(/unionExec: __federatedUnion/g)||[]).length)"`
Expected: prints the same count as deps sites found in Step 1.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(federert): duckdb-wasm union executor wired into all mode deps"
```

---

### Task 6: Demo data, registry entry, docs example

**Files:**
- Create: `scripts/build_federert_demo.py`
- Create: `static_data/federert/{nord,vest,sor}/person.parquet` (generated, committed)
- Modify: `data/data-sources.json` (append demo entry)
- Modify: `docs/directive-language-examples.md` (new section)

**Interfaces:**
- Consumes: `static_data/person.parquet` (existing synthetic table — verify its id column name with `python3 -c "import pandas as pd; print(pd.read_parquet('static_data/person.parquet').columns.tolist())"` and use the real id column for `entity`).
- Produces: registry id `demo-federert` usable as `# connect demo-federert as h` + `# load h as df`.

- [ ] **Step 1: Write the split script**

Create `scripts/build_federert_demo.py`:

```python
"""Split static_data/person.parquet into three disjoint "region" members for
the demo-federert source (spec 2026-07-29-federated-sources-design §7).
Deterministic thirds by row order — rerunning build_static_data.py then this
keeps members in sync with the unsplit table (the equality invariant the
federated union is tested against)."""
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
df = pd.read_parquet(ROOT / "static_data" / "person.parquet")
n = len(df)
cuts = [0, n // 3, 2 * n // 3, n]
for name, a, b in zip(["nord", "vest", "sor"], cuts, cuts[1:]):
    out = ROOT / "static_data" / "federert" / name
    out.mkdir(parents=True, exist_ok=True)
    df.iloc[a:b].to_parquet(out / "person.parquet", index=False)
    print(f"{name}: {b - a} rader")
print(f"totalt: {n} rader")
```

- [ ] **Step 2: Run it and verify the invariant**

Run: `python3 scripts/build_federert_demo.py`
Expected: three member counts summing to the total.
Verify: `python3 -c "
import pandas as pd, glob
parts = pd.concat([pd.read_parquet(p) for p in sorted(glob.glob('static_data/federert/*/person.parquet'))])
full = pd.read_parquet('static_data/person.parquet')
assert len(parts) == len(full), (len(parts), len(full))
print('OK', len(full))"`

- [ ] **Step 3: Registry entry**

Append to the array in `data/data-sources.json` (match the file's existing field style; NO keys/secrets — public file):

```json
{
  "id": "demo-federert",
  "navn": "Demo: federert persontabell (3 regioner)",
  "utgiver": "safestat",
  "kind": "federated",
  "partition": "horizontal",
  "entity": "<REAL_ID_COLUMN>",
  "overlap": "none",
  "members": [
    { "id": "nord", "url": "static_data/federert/nord/person.parquet" },
    { "id": "vest", "url": "static_data/federert/vest/person.parquet" },
    { "id": "sor",  "url": "static_data/federert/sor/person.parquet" }
  ]
}
```

(`<REAL_ID_COLUMN>` = the id column found in this task's Interfaces check.) Validate: `python3 -c "import json; json.load(open('data/data-sources.json')); print('json ok')"`.

- [ ] **Step 4: Docs example**

Add to `docs/directive-language-examples.md` (follow the file's existing section format):

```markdown
## Federert kilde (fase 0 — pull)

Tre regioner, samme tabell, analysert som ett datasett. `__member` viser
hvilken region hver rad kom fra.

    # connect demo-federert as helse
    # load helse as personer
    print(len(personer))
    print(personer["__member"].value_counts())

Egendefinert, inline: `# connect federert(https://a.no/data, https://b.no/data) as h`
+ `# load h/person.parquet as df` (stien appendes til hvert medlem).
Skjemaene må stemme overens (kolonnenavn), ellers nektes kjøringen.
Sensitive medlemmer nektes i pull-federering — de krever node-medlemmer (fase 1).
```

- [ ] **Step 5: Commit**

```bash
git add scripts/build_federert_demo.py static_data/federert data/data-sources.json docs/directive-language-examples.md
git commit -m "feat(federert): demo federated source split from synthetic person table"
```

---

### Task 7: End-to-end verification (browser smoke)

**Files:** none (verification only; fix-forward anything found, as its own commits)

- [ ] **Step 1: Full test suites**

Run: `node --test tests/js/` → all PASS.
Run: `python3 -m pytest tests/ -x -q` → all PASS (nothing python-side changed; guard against accidental breakage from the registry/demo files).

- [ ] **Step 2: Serve and smoke in browser**

Serve the repo root: `python3 -m http.server 8123` (plain static server is enough — the demo members are same-origin relative URLs; no proxy needed). In Chrome (hard reload with cache ignored — known Chrome-caches-js/ trap): open `http://localhost:8123/`, in **python mode** run:

```
# connect demo-federert as helse
# load helse as personer
print(len(personer))
print(sorted(personer["__member"].unique()))
```

Expected: row count equals the unsplit `person.parquet` count from Task 6 Step 2, and members `['nord', 'sor', 'vest']`.

- [ ] **Step 3: Negative smoke**

Same page, run a script with a schema-drifting inline source (e.g. `# connect federert(static_data/federert/nord/person.parquet, static_data/fylke.parquet) as h` + `# load h as df`): expected Norwegian schema-drift error naming the member, not a crash.

- [ ] **Step 4: Mark plan complete**

Update this plan's checkboxes; note any deviations at the bottom of the file. Commit:

```bash
git add docs/superpowers/plans/2026-07-29-federert-fase0.md
git commit -m "docs(federert): mark phase 0 plan executed"
```

---

## Self-review notes

- Spec §4 coverage: directive expansion (T1–T2), auto-union with `__member` (T3, T5), duckdb-native multi-URL path (not needed as a special case — union covers all modes uniformly; pushdown explicitly disabled for federated in T4), encrypted members (reuse of `maybeDecrypt` in T4's member loop), tier/level enforcement from day one (T2 + T4 test).
- Spec §3 overlap footnote: Phase 0 carries `overlap` on the load object and logs a console note (T5); the result-level footnote is Phase 1 rendering work — noted as a deliberate deferral.
- Type consistency: `federated` subitem shape `{id, url, viaProxy, kind, key, level}` produced in T2 and consumed as such in T4; `unionExec(alias, members, meta)` contract identical in T4 (fake) and T5 (real); `planUnion(files)` takes `{id, format, fileName}` in both T3 and T5.
