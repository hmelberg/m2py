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
