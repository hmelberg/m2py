// tests/js/examples-menu.test.js — ren grupperingslogikk for eksempel-menyen.
const test = require('node:test');
const assert = require('node:assert');
require('../../js/examples-menu.js');
const EM = globalThis.ExamplesMenu;

const MANIFEST = {
  micropython: [
    { file: 'micropython/01_a.txt', label: 'A', group: null },
    { file: 'micropython/02_b.txt', label: 'B', group: null },
    { file: 'micropython/10_avansert/01_c.txt', label: 'C', group: '10 — Avansert' },
  ],
};

test('groupForMode: unknown mode gives empty array', () => {
  assert.deepEqual(EM.groupForMode(MANIFEST, 'r'), []);
  assert.deepEqual(EM.groupForMode({}, 'micropython'), []);
});

test('groupForMode: flat + categorised in first-appearance order', () => {
  assert.deepEqual(EM.groupForMode(MANIFEST, 'micropython'), [
    { group: null, examples: [
      { file: 'micropython/01_a.txt', label: 'A' },
      { file: 'micropython/02_b.txt', label: 'B' },
    ] },
    { group: '10 — Avansert', examples: [
      { file: 'micropython/10_avansert/01_c.txt', label: 'C' },
    ] },
  ]);
});

test('groupForMode: missing group treated as null', () => {
  const m = { micropython: [{ file: 'micropython/01_a.txt', label: 'A' }] };
  assert.deepEqual(EM.groupForMode(m, 'micropython'),
    [{ group: null, examples: [{ file: 'micropython/01_a.txt', label: 'A' }] }]);
});
