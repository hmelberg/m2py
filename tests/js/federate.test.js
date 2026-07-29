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

function nodeFetch(behavior) {
  // behavior: {id: {polls: N, result: {...}} | {fail: msg}}
  const polls = {};
  return async (url, init) => {
    const m = url.match(/^https:\/\/(\w+)\.no/);
    const id = m[1];
    const b = behavior[id];
    if (url.indexOf('run_extended_status') >= 0) {
      polls[id] = (polls[id] || 0) + 1;
      if (b.fail) return { ok: true, json: async () => ({ status: 'failed', error: b.fail }) };
      const done = polls[id] >= (b.polls || 1);
      return { ok: true, json: async () => (done ? { status: 'completed', result: b.result } : { status: 'running' }) };
    }
    return { ok: true, json: async () => ({ task_id: 't_' + id }) };
  };
}

test('runNodes: samler resultater i inputrekkefølge', async () => {
  const res = await F.runNodes(
    [{ id: 'nord', api: 'https://nord.no', body: { x: 1 } },
     { id: 'vest', api: 'https://vest.no', body: { x: 2 } }],
    { fetchImpl: nodeFetch({ nord: { polls: 2, result: { stats: ['a'] } },
                             vest: { polls: 1, result: { stats: ['b'] } } }),
      pollMs: 1 });
  assert.deepEqual(res.map(r => r.id), ['nord', 'vest']);
  assert.deepEqual(res[0].result.stats, ['a']);
});

test('runNodes: nettverksfeil (fetch kaster) navngir medlemmet', async () => {
  await assert.rejects(
    F.runNodes([{ id: 'nord', api: 'https://nord.no', body: {} }],
      { fetchImpl: async () => { throw new TypeError('Failed to fetch'); }, pollMs: 1 }),
    /«nord».*Failed to fetch/);
});

test('runNodes: én node feiler -> hele kjøringen feiler med medlemsnavn', async () => {
  await assert.rejects(
    F.runNodes(
      [{ id: 'nord', api: 'https://nord.no', body: {} },
       { id: 'vest', api: 'https://vest.no', body: {} }],
      { fetchImpl: nodeFetch({ nord: { polls: 1, result: {} },
                               vest: { fail: 'kilde nede' } }),
        pollMs: 1 }),
    /«vest».*kilde nede/);
});
