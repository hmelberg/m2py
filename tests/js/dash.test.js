const test = require('node:test');
const assert = require('node:assert');
const D = require('../../js/dash.js');

test('parseMosaic: enkel 2x2', () => {
  const m = D.parseMosaic('a b\nc d');
  assert.strictEqual(m.error, undefined);
  assert.strictEqual(m.columns, 2);
  assert.strictEqual(m.rows, 2);
  assert.deepStrictEqual(m.names.sort(), ['a', 'b', 'c', 'd']);
  assert.strictEqual(m.gridTemplateAreas, '"a b" "c d"');
});

test('parseMosaic: spenn horisontalt og vertikalt', () => {
  const m = D.parseMosaic(`
    kpi1 kpi2 kpi3 kpi3
    plot plot plot tab
    plot plot plot tab
  `);
  assert.strictEqual(m.error, undefined);
  assert.strictEqual(m.columns, 4);
  assert.strictEqual(m.rows, 3);
  assert.ok(m.names.includes('plot'));
});

test('parseMosaic: punktum er tom celle', () => {
  const m = D.parseMosaic('a . b\na . b');
  assert.strictEqual(m.error, undefined);
  assert.deepStrictEqual(m.names.sort(), ['a', 'b']);
  assert.strictEqual(m.gridTemplateAreas, '"a . b" "a . b"');
});

test('parseMosaic: ikke-rektangulaert omraade gir feil', () => {
  const m = D.parseMosaic('a a b\nc a b');
  assert.match(m.error, /rektangul/);
  assert.match(m.error, /"a"/);
});

test('parseMosaic: ulikt antall kolonner per linje gir feil', () => {
  const m = D.parseMosaic('a b c\nd e');
  assert.match(m.error, /linje 2/);
});

test('parseMosaic: mer enn 12 kolonner gir feil', () => {
  const m = D.parseMosaic('a b c d e f g h i j k l m');
  assert.match(m.error, /12/);
});

test('parseMosaic: tom streng gir feil', () => {
  assert.ok(D.parseMosaic('').error);
  assert.ok(D.parseMosaic(null).error);
});

test('autoSpan: KPI 3, plott/bilde 6, tekst/markdown 12', () => {
  assert.strictEqual(D.autoSpan('number'), 3);
  assert.strictEqual(D.autoSpan('figure'), 6);
  assert.strictEqual(D.autoSpan('image'), 6);
  assert.strictEqual(D.autoSpan('markdown'), 12);
  assert.strictEqual(D.autoSpan('text'), 12);
});

test('autoSpan: tabell 6 ved faa kolonner, 12 ved mange', () => {
  assert.strictEqual(D.autoSpan('table', 4), 6);
  assert.strictEqual(D.autoSpan('table', 9), 12);
  assert.strictEqual(D.autoSpan('table'), 6);
});

test('autoOrder: KPI foerst', () => {
  assert.strictEqual(D.autoOrder('number'), 0);
  assert.strictEqual(D.autoOrder('figure'), 1);
});
