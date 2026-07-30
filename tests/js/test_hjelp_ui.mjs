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
const { matchNav } = fakeWindow.HjelpUI;

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

test('flere treff beholder rekkefølgen', () => {
  assert.deepEqual(matchNav('e', ['Editor', 'Moduser', 'Referanse']), [0, 1, 2]);
});
