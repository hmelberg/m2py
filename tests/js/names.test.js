// tests/js/names.test.js — ren oppslagslogikk i js/names.js
const test = require('node:test');
const assert = require('node:assert');
const N = require('../../js/names.js');

test('pick: string values, object values, miss', () => {
  const reg = { a: 'hans.demo.x.py', b: { url: 'https://x.example/b.py' }, c: 42 };
  assert.equal(N.pick(reg, 'a'), 'hans.demo.x.py');
  assert.equal(N.pick(reg, 'b'), 'https://x.example/b.py');
  assert.equal(N.pick(reg, 'c'), null);   // ukjent form → miss, ikke krasj
  assert.equal(N.pick(reg, 'nope'), null);
  assert.equal(N.pick(null, 'a'), null);
  assert.equal(N.pick('streng', 'a'), null);
});
