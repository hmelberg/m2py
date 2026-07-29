// tests/js/data-directives-load.test.js — load-resolusjon av relative stier
// (2026-07-30: strict-eksemplene brukte «# load static_data/person.parquet
// as df», som ble tolket som alias/sti med ukjent alias «static_data»).
const test = require('node:test');
const assert = require('node:assert');
require('../../js/data-directives.js');
const DD = globalThis.DataDirectives;

function resolve1(script) {
  return DD.resolve(DD.parse(script), [])[0];
}

test('load: relativ sti med filendelse blir relativ URL (ingen connect nødvendig)', () => {
  const it = resolve1('# load static_data/person.parquet as df');
  assert.ok(!it.error, it.error);
  assert.equal(it.url, 'static_data/person.parquet');
  assert.equal(it.viaProxy, false);
});

test('load: ./-prefiks er alltid relativ URL', () => {
  const it = resolve1('# load ./data/fil.csv as df');
  assert.ok(!it.error, it.error);
  assert.equal(it.url, './data/fil.csv');
});

test('load: ukjent alias UTEN filendelse gir fortsatt tydelig feil', () => {
  const it = resolve1('# load helse/tabell as df');
  assert.ok(it.error);
  assert.ok(it.error.indexOf('helse') >= 0);
});

test('load: kjent connect-alias vinner over relativ-sti-tolkning', () => {
  const items = DD.resolve(DD.parse(
    '# connect https://a.no/data as static_data\n# load static_data/person.parquet as df'), []);
  assert.equal(items[0].url, 'https://a.no/data/person.parquet');
});
