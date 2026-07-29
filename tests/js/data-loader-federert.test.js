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
