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

test('resolve: register-medlemmer med relative url-er behandles som URL, ikke register-id', () => {
  const reg = [{ id: 'demo-rel', navn: 'Rel', kind: 'federated',
    members: [
      { id: 'nord', url: 'static_data/federert/nord/person.parquet' },
      { id: 'vest', url: 'static_data/federert/vest/person.parquet' },
    ] }];
  const items = DD.resolve(DD.parse('# connect demo-rel as h\n# load h as df'), reg);
  assert.ok(!items[0].error, items[0].error);
  assert.equal(items[0].federated[0].url, 'static_data/federert/nord/person.parquet');
  assert.equal(items[0].federated[0].id, 'nord');
});

test('resolve: connect-nivå key() arves av medlemmene', () => {
  const items = resolveScript('# connect federert(https://a.no/d, https://b.no/d) as h, key(hemmelig)\n# load h/t.enc as df');
  assert.equal(items[0].federated[0].key, 'hemmelig');
  assert.equal(items[0].federated[1].key, 'hemmelig');
});
