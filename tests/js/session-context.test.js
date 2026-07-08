// tests/js/session-context.test.js — nivå/sted-avledning, exec-omskriving,
// HE-verb pre-flight (js/session-context.js). Samme node:test + vm-mønster
// som example-loads.test.js: modulene evalueres inn i én sandbox.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs'); const path = require('node:path'); const vm = require('node:vm');
const root = path.join(__dirname, '..', '..');

function loadSC() {
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  for (const f of ['data-directives.js', 'session-context.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'js', f), 'utf8'), sandbox);
  }
  return sandbox.window.SessionContext;
}
const SC = loadSC();

// ── derive: nivå ──────────────────────────────────────────────────────────

test('åpent script uten kilder: open/local, ikke valgbart', () => {
  const d = SC.derive('summarize inntekt', 'safestat', {});
  assert.equal(d.level, 'open');
  assert.equal(d.place, 'local');
  assert.equal(d.placeChoosable, false);
});

test('URL-require i safestat: open, tvunget lokal', () => {
  const d = SC.derive('require https://x.no/d.csv as df\nsummarize df', 'safestat', {});
  assert.equal(d.level, 'open');
  assert.equal(d.place, 'local');
  assert.equal(d.placeChoosable, false);
});

test('#options.profile = strict gir restricted', () => {
  const d = SC.derive('# options.profile = strict\nimport pandas as pd', 'python', {});
  assert.equal(d.level, 'restricted');
  assert.equal(d.levelReasons[0].why, 'profile-strict');
});

test('-- options.profile = strict (duckdb) gir restricted', () => {
  const d = SC.derive('-- options.profile = strict\nSELECT 1', 'duckdb', {});
  assert.equal(d.level, 'restricted');
});

test('navngitt kilde uten metadata: unknown', () => {
  const d = SC.derive('# require pasienter as df', 'python', {});
  assert.equal(d.level, 'unknown');
  assert.deepEqual(d.sourceIds, ['pasienter']);
});

test('strict-grant gir restricted', () => {
  const meta = { pasienter: { public: false, local_profile: 'strict' } };
  const d = SC.derive('# require pasienter as df', 'python', meta);
  assert.equal(d.level, 'restricted');
  assert.equal(d.levelReasons[0].why, 'grant-strict');
});

test('protected grant-level gir restricted', () => {
  const d = SC.derive('require pasienter as df', 'safestat', { pasienter: { public: true, level: 'protected' } });
  assert.equal(d.level, 'restricted');
  assert.equal(d.levelReasons[0].why, 'level-protected');
});

test('he-konvolutt gir he-nivå, og he vinner over restricted', () => {
  const meta = {
    helse: { public: false, kind: 'safepy-he-v1' },
    annet: { public: false, level: 'sensitive' }
  };
  const d = SC.derive('# require helse as h\n# require annet as a', 'python', meta);
  assert.equal(d.level, 'he');
});

test('unknown vinner over open, restricted vinner over unknown', () => {
  const dU = SC.derive('# require ukjent as u\n# load https://x.no/d.csv as df', 'python', {});
  assert.equal(dU.level, 'unknown');
  const dR = SC.derive('# require ukjent as u\n# options.profile = strict', 'python', {});
  assert.equal(dR.level, 'restricted');
});

test('utkommentert require i safestat-modus teller IKKE', () => {
  const d = SC.derive('# require pasienter as df\nsummarize x', 'safestat', {});
  assert.equal(d.level, 'open');
  assert.equal(d.sourceIds.length, 0);
});

// ── derive: sted ──────────────────────────────────────────────────────────

test('navngitt require i dialekt-modus: tvunget remote', () => {
  const d = SC.derive('# require pasienter as df', 'python', { pasienter: { public: true, default_exec: 'local' } });
  assert.equal(d.place, 'remote');
  assert.equal(d.placeChoosable, false);
});

test('public kilde i safestat: valgbar, default lokal', () => {
  const d = SC.derive('require folk as df', 'safestat', { folk: { public: true, default_exec: 'local' } });
  assert.equal(d.place, 'local');
  assert.equal(d.placeChoosable, true);
});

test('exec(remote) respekteres på valgbar linje', () => {
  const d = SC.derive('require folk as df, exec(remote)', 'safestat', { folk: { public: true, default_exec: 'local' } });
  assert.equal(d.place, 'remote');
  assert.equal(d.placeChoosable, true);
});

test('ikke-public kilde i safestat: tvunget remote', () => {
  const d = SC.derive('require pasienter as df', 'safestat', { pasienter: { public: false } });
  assert.equal(d.place, 'remote');
  assert.equal(d.placeChoosable, false);
});

test('strict_remote (for stor) kilde: tvunget remote', () => {
  const d = SC.derive('require stor as df', 'safestat', { stor: { public: true, default_exec: 'strict_remote' } });
  assert.equal(d.place, 'remote');
  assert.equal(d.placeChoosable, false);
});

test('he-kilde: alltid tvunget remote (kan ikke aggregeres lokalt)', () => {
  const d = SC.derive('require helse as h', 'safestat', { helse: { kind: 'safepy-he-v1' } });
  assert.equal(d.level, 'he');
  assert.equal(d.place, 'remote');
  assert.equal(d.placeChoosable, false);
});

test('microdata-modus: aldri valgbar (ingen exec-støtte)', () => {
  const d = SC.derive('require no.ssb.fdb as db', 'microdata', { 'no.ssb.fdb': { public: true, default_exec: 'local' } });
  assert.equal(d.placeChoosable, false);
});

test('connect mot public grant: valgbar, default lokal', () => {
  const d = SC.derive('# connect minkilde\n# load minkilde as df', 'python', { minkilde: { public: true } });
  assert.equal(d.place, 'local');
  assert.equal(d.placeChoosable, true);
});

test('connect remote_only: tvunget remote', () => {
  const d = SC.derive('# connect stor\n# load stor as df', 'python', { stor: { public: true, remote_only: true } });
  assert.equal(d.place, 'remote');
  assert.equal(d.placeChoosable, false);
});

test('blandet tvunget + valgbar: ikke valgbar samlet', () => {
  const meta = { folk: { public: true, default_exec: 'local' }, pasienter: { public: false } };
  const d = SC.derive('require folk as f\nrequire pasienter as p', 'safestat', meta);
  assert.equal(d.place, 'remote');
  assert.equal(d.placeChoosable, false);
});

// ── applyExec ─────────────────────────────────────────────────────────────

const FOLK_META = { folk: { public: true, default_exec: 'local' } };

test('applyExec skriver exec(remote) på valgbar linje', () => {
  const s = 'require folk as df\nsummarize df';
  const out = SC.applyExec(s, 'remote', 'safestat', FOLK_META);
  assert.match(out.split('\n')[0], /, exec\(remote\)$/);
  assert.equal(out.split('\n')[1], 'summarize df');
});

test('applyExec(value=default) skriver IKKE exec — holder scriptet rent', () => {
  const s = 'require folk as df';
  assert.equal(SC.applyExec(s, 'local', 'safestat', FOLK_META), s);
});

test('applyExec-rundtur: remote så null gir originalen tilbake', () => {
  const s = 'require folk as df\nsummarize df';
  const there = SC.applyExec(s, 'remote', 'safestat', FOLK_META);
  const back = SC.applyExec(there, null, 'safestat', FOLK_META);
  assert.equal(back, s);
});

test('applyExec erstatter eksisterende exec, dupliserer ikke', () => {
  const s = 'require folk as df, exec(remote)';
  const out = SC.applyExec(s, 'remote', 'safestat', FOLK_META);
  assert.equal((out.match(/exec\(/g) || []).length, 1);
});

test('applyExec rører ikke tvungne linjer', () => {
  const s = 'require pasienter as p';
  const out = SC.applyExec(s, 'remote', 'safestat', { pasienter: { public: false } });
  assert.equal(out, s);
});

// ── checkHeVerbs ──────────────────────────────────────────────────────────

test('checkHeVerbs godtar de fire fasade-verbene + kommentarer + require', () => {
  const s = [
    '# require helse as data',
    'require helse as data',
    'group_agg data, mean(inntekt) by(kjonn)',
    'value_counts data, kjonn',
    'crosstab data, kjonn utdanning',
    'ols data, inntekt ~ alder'
  ].join('\n');
  assert.equal(SC.checkHeVerbs(s).ok, true);
});

test('checkHeVerbs avviser andre verb med linjenummer', () => {
  const s = '# require helse as data\nscatter data, x y';
  const r = SC.checkHeVerbs(s);
  assert.equal(r.ok, false);
  assert.equal(r.offending[0].lineNo, 2);
  assert.match(r.offending[0].text, /^scatter/);
});

// ── metaFor / noteFetchedLoad ─────────────────────────────────────────────

test('metaFor cacher, web-registry er public, 404 blir unknown', async () => {
  SC._resetCacheForTests();
  let calls = 0;
  const fetchImpl = async (url) => {
    calls++;
    if (url.includes('finnes')) return { ok: true, json: async () => ({ public: false }) };
    return { ok: false };
  };
  const deps = { apiBase: 'https://api.x', fetchImpl, webRegistry: [{ id: 'webkilde' }] };
  const meta = await SC.metaFor(['finnes', 'borte', 'webkilde'], deps);
  assert.equal(meta.finnes.public, false);
  assert.equal(meta.borte.unknown, true);
  assert.equal(meta.webkilde.public, true);
  assert.equal(calls, 2);              // webkilde traff aldri nettet
  await SC.metaFor(['finnes', 'borte'], deps);
  assert.equal(calls, 2);              // memoisert
});

test('noteFetchedLoad oppgraderer nivået etter kjøring', () => {
  SC._resetCacheForTests();
  SC.noteFetchedLoad('helse', { envelopeKind: 'safepy-he-v1' });
  const d = SC.derive('# require helse as h', 'python', SC.cachedMeta());
  assert.equal(d.level, 'he');
});
