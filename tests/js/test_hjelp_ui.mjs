/* Nav-filteret i hjelpesidene: ren funksjon, node-testet uten DOM.
   Mønsteret følger js/cells.js — ren halvdel testbar, DOM-halvdel ikke. */
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// Hent ut matchNav fra hjelp.html sin inline script-blokk. Vi mater blokken et
// falskt window-objekt; IIFE-en henger API-et på det, og `document` er guardet
// bort, så ingen DOM trengs.
const html = readFileSync(new URL('../../hjelp.html', import.meta.url), 'utf8');
const m = html.match(/\/\* SYNC:START felles-js \*\/([\s\S]*?)\/\* SYNC:END \*\//);
assert.ok(m, 'fant ikke felles-js-blokken i hjelp.html');
const fakeWindow = {};
new Function('window', m[1])(fakeWindow);
assert.ok(fakeWindow.HjelpUI, 'blokken hengte ikke HjelpUI på window');
const { matchNav, pickActiveId } = fakeWindow.HjelpUI;

test('tom query viser alt', () => {
  assert.deepEqual(matchNav('', ['Editor', 'Moduser', 'Strict']), [0, 1, 2]);
});

test('filtrerer på delstreng, uavhengig av store bokstaver', () => {
  assert.deepEqual(matchNav('mod', ['Editor', 'Moduser', 'Strict']), [1]);
  assert.deepEqual(matchNav('MOD', ['Editor', 'Moduser', 'Strict']), [1]);
});

test('ingen treff gir tom liste', () => {
  assert.deepEqual(matchNav('zzz', ['Editor', 'Moduser']), []);
});

test('trimmer whitespace', () => {
  assert.deepEqual(matchNav('  strict  ', ['Editor', 'Strict']), [1]);
});

test('kun whitespace oppfører seg som tom query og viser alt', () => {
  assert.deepEqual(matchNav('   ', ['Editor', 'Moduser', 'Strict']), [0, 1, 2]);
});

test('tom labels-liste gir tom liste, uansett query', () => {
  assert.deepEqual(matchNav('foo', []), []);
});

test('flere treff beholder rekkefølgen i input, ikke alfabetisk rekkefølge', () => {
  // 'Zebra' står alfabetisk sist men er indeks 0 — en implementasjon som
  // sorterer treffene alfabetisk ville returnert [1, 2, 0] her, ikke [0, 1, 2].
  assert.deepEqual(matchNav('e', ['Zebra', 'Editor', 'Moduser']), [0, 1, 2]);
});

test('matcher norske bokstaver æøå, uavhengig av store bokstaver', () => {
  assert.deepEqual(
    matchNav('ØRING', ['Avsløringskontroll', 'Spørsmålsløkka']),
    [0]
  );
});

// pickActiveId: scrollspyens beslutningsfunksjon, trukket ut som ren
// funksjon nettopp for å kunne testes uten IntersectionObserver/DOM.
// Task 10 (browser-verifisering) fant at det gamle mønsteret — fjern
// highlight ubetingelet, sett den betinget — tømte highlighten hver gang
// ingenting overlappet det smale observasjonsbåndet (typisk øverst og
// nederst på siden). Fikset ved å beholde forrige aktive id når ingenting
// intersecter nå.

test('ingenting intersecter nå: beholder forrige aktive', () => {
  assert.equal(pickActiveId('tillit', []), 'tillit');
});

test('ny intersection: flytter til den (første i observatørens rekkefølge)', () => {
  assert.equal(pickActiveId('tillit', ['kilder', 'strict-py']), 'kilder');
});

test('aller første kall, ingenting intersecter ennå: returnerer ingenting', () => {
  assert.equal(pickActiveId(null, []), null);
});
