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

// ---------- K2: encodeState / decodeState (URL-state, rene funksjoner) ----------

test('encodeState/decodeState: rundtur med shared + cards', () => {
  const state = {
    shared: { n: 42, aktiv: true, navn: 'ærlig test' },
    cards: { '0': { terskel: -5.5 }, '1': { valg: 2 } }
  };
  const encoded = D.encodeState(state);
  assert.strictEqual(typeof encoded, 'string');
  assert.ok(encoded.length > 0);
  const decoded = D.decodeState(encoded);
  assert.deepStrictEqual(decoded, state);
});

test('encodeState: base64url uten padding, "+" eller "/"', () => {
  // Payload valgt for å sannsynliggjøre + og / i standard base64.
  const state = { shared: { x: 111111111, y: 999999999, s: '>>>???///+++' }, cards: {} };
  const encoded = D.encodeState(state);
  assert.match(encoded, /^[A-Za-z0-9_-]+$/);
  assert.ok(!encoded.includes('+'));
  assert.ok(!encoded.includes('/'));
  assert.ok(!encoded.includes('='));
  assert.deepStrictEqual(D.decodeState(encoded), state);
});

test('decodeState: ugyldig input gir null', () => {
  assert.strictEqual(D.decodeState(null), null);
  assert.strictEqual(D.decodeState(undefined), null);
  assert.strictEqual(D.decodeState(''), null);
  assert.strictEqual(D.decodeState(123), null);
  assert.strictEqual(D.decodeState('ikke-gyldig-base64!!!'), null);
  assert.strictEqual(D.decodeState('####'), null);
  // Gyldig base64url, men JSON-innholdet er en array, ikke et objekt.
  const arrEncoded = D.encodeState([1, 2, 3]);
  assert.strictEqual(D.decodeState(arrEncoded), null);
});

test('encodeState/decodeState: tomt objekt rundtur', () => {
  const encoded = D.encodeState({});
  assert.match(encoded, /^[A-Za-z0-9_-]+$/);
  assert.deepStrictEqual(D.decodeState(encoded), {});
});

// ---------- Number-payload v3: formatNumber + computeDelta ----------

test('formatNumber: default — heltall grupperes med U+202F', () => {
  assert.strictEqual(D.formatNumber(1234567), '1\u202f234\u202f567');
});

test('formatNumber: default — 2 desimaler uten etternuller, komma', () => {
  assert.strictEqual(D.formatNumber(3.14159), '3,14');
  assert.strictEqual(D.formatNumber(2.5), '2,5');
  assert.strictEqual(D.formatNumber(2.0), '2');
});

test('formatNumber: negativ bruker ekte minustegn', () => {
  assert.strictEqual(D.formatNumber(-1234.5), '\u22121\u202f234,5');
});

test('formatNumber: fmt ",.1f" — gruppert, 1 desimal', () => {
  assert.strictEqual(D.formatNumber(12345.678, ',.1f'), '12\u202f345,7');
});

test('formatNumber: fmt ".0f" — ingen gruppering', () => {
  assert.strictEqual(D.formatNumber(12345.678, '.0f'), '12346');
});

test('formatNumber: fmt ".1%" — prosent', () => {
  assert.strictEqual(D.formatNumber(0.1234, '.1%'), '12,3%');
});

test('formatNumber: ukjent fmt faller tilbake til default (kaster aldri)', () => {
  assert.strictEqual(D.formatNumber(1234.5, 'kroner'), '1\u202f234,5');
});

test('formatNumber: ikke-tall passeres som streng', () => {
  assert.strictEqual(D.formatNumber(NaN), 'NaN');
  assert.strictEqual(D.formatNumber(Infinity), 'Infinity');
});

test('computeDelta: retning, fortegn og god/dårlig', () => {
  const d = D.computeDelta(120, 100, null, 'opp');
  assert.deepStrictEqual(d, { text: '+20', dir: 'opp', good: true });
  const n = D.computeDelta(80, 100, null, 'opp');
  assert.deepStrictEqual(n, { text: '\u221220', dir: 'ned', good: false });
  const f = D.computeDelta(100, 100, null, 'ned');
  assert.deepStrictEqual(f, { text: '+0', dir: 'flat', good: true });
});

test('computeDelta: null/ikke-endelig ref gir null', () => {
  assert.strictEqual(D.computeDelta(5, null, null, 'opp'), null);
  assert.strictEqual(D.computeDelta(5, undefined, null, 'opp'), null);
  assert.strictEqual(D.computeDelta(5, Infinity, null, 'opp'), null);
});

test('computeDelta: bruker fmt på differansen', () => {
  const d = D.computeDelta(0.35, 0.30, '.1%', 'opp');
  assert.strictEqual(d.text, '+5,0%');
});

test('payloadCols: html-tabell bruker cols, strukturert bruker columns.length', () => {
  assert.strictEqual(D.payloadCols({ kind: 'table', html: '<table/>', cols: 9 }), 9);
  assert.strictEqual(D.payloadCols({ kind: 'table', columns: ['a', 'b'], rows: [] }), 2);
  assert.strictEqual(D.payloadCols({ kind: 'number', value: 1 }), 0);
});
