// tests/js/data-directives-use.test.js — segmentnivå-use + kortform
// (plan 2026-07-11-segment-use-cross-runtime).
const test = require('node:test');
const assert = require('node:assert');
require('../../js/data-directives.js');
const DD = globalThis.DataDirectives;

test('parseUse: explicit from still works', () => {
  const r = DD.parseUse('# use df from python');
  assert.deepEqual(r.uses, [{ name: 'df', from: 'python' }]);
  assert.deepEqual(r.errors, []);
});

test('parseUse: short form gives from null', () => {
  const r = DD.parseUse('# use df');
  assert.deepEqual(r.uses, [{ name: 'df', from: null }]);
});

test('parseUse: invalid source still errors', () => {
  const r = DD.parseUse('# use df from stata');
  assert.equal(r.uses.length, 0);
  assert.equal(r.errors.length, 1);
});

test('runtimeFamily: microdata and pyodide share the python family', () => {
  assert.equal(DD.runtimeFamily('microdata'), 'python');
  assert.equal(DD.runtimeFamily('pyodide'), 'python');
  assert.equal(DD.runtimeFamily('duckdb'), 'duckdb');
  assert.equal(DD.runtimeFamily('r'), 'r');
});

test('parseSegmentUses: short form infers nearest preceding foreign segment', () => {
  const r = DD.parseSegmentUses([
    { kind: 'pyodide', text: "df = 1" },
    { kind: 'r', text: "# use df\nsummary(df)" },
  ]);
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.segments[1].uses, [{ name: 'df', from: 'python' }]);
  assert.equal(r.segments[1].text.includes('use df'), false);
  assert.equal(r.segments[1].text.includes('summary(df)'), true);
});

test('parseSegmentUses: py -> r -> py chain infers both directions', () => {
  const r = DD.parseSegmentUses([
    { kind: 'pyodide', text: 'df = 1' },
    { kind: 'r', text: '# use df\ndf2 <- df' },
    { kind: 'pyodide', text: '# use df2\nprint(df2)' },
  ]);
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.segments[1].uses, [{ name: 'df', from: 'python' }]);
  assert.deepEqual(r.segments[2].uses, [{ name: 'df2', from: 'r' }]);
});

test('parseSegmentUses: microdata does not satisfy inference for a pyodide block (same family)', () => {
  const r = DD.parseSegmentUses([
    { kind: 'microdata', text: 'create-dataset d' },
    { kind: 'pyodide', text: '# use d\nprint(d)' },
  ]);
  assert.equal(r.errors.length, 1);
  assert.match(r.errors[0], /angi kilden/);
});

test('parseSegmentUses: explicit from wins over inference', () => {
  const r = DD.parseSegmentUses([
    { kind: 'pyodide', text: 'x = 1' },
    { kind: 'duckdb', text: 'SELECT 1' },
    { kind: 'r', text: '# use tall from duckdb\nsummary(tall)' },
  ]);
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.segments[2].uses, [{ name: 'tall', from: 'duckdb' }]);
});

test('parseSegmentUses: use from own family errors', () => {
  const r = DD.parseSegmentUses([
    { kind: 'r', text: '# use df from r\nsummary(df)' },
  ]);
  assert.equal(r.errors.length, 1);
  assert.match(r.errors[0], /allerede i r/);
});

test('parseSegmentUses: no preceding foreign segment errors with guidance', () => {
  const r = DD.parseSegmentUses([{ kind: 'r', text: '# use df\nsummary(df)' }]);
  assert.equal(r.errors.length, 1);
  assert.match(r.errors[0], /from python\|r\|duckdb/);
});

test('parseSegmentUses: -- and // comment prefixes work (SQL/R style)', () => {
  const r = DD.parseSegmentUses([
    { kind: 'pyodide', text: 'df = 1' },
    { kind: 'duckdb', text: '-- use df\nSELECT * FROM df' },
  ]);
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.segments[1].uses, [{ name: 'df', from: 'python' }]);
});
