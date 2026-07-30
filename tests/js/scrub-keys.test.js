// tests/js/scrub-keys.test.js — navnereferanser i key(...) er IKKE hemmeligheter
// og maskeres ikke (spec 2026-07-30-key-store-design §3.3).
const test = require('node:test');
const assert = require('node:assert');
require('../../js/data-directives.js');
const DD = globalThis.DataDirectives;

test('literal maskeres, ask beholdes (uendret adferd)', () => {
  delete globalThis.Keys;
  const s = '# connect x as h, key(SUPERHEMMELIG)\n# load y as df, key(ask)';
  const out = DD.scrubKeys(s);
  assert.ok(out.includes('key(***)'));
  assert.ok(out.includes('key(ask)'));
  assert.ok(!out.includes('SUPERHEMMELIG'));
});

test('lagret navn beholdes umaskert; ukjent navn maskeres', () => {
  globalThis.Keys = { policy: (n) => (n === 'minfred' ? 'secret' : null) };
  try {
    const out = DD.scrubKeys('# load y as df, key(minfred)\n# load z as e, key(annet)');
    assert.ok(out.includes('key(minfred)'));
    assert.ok(out.includes('key(***)'));
    assert.ok(!out.includes('key(annet)'));
  } finally { delete globalThis.Keys; }
});

test('siterte navn beholdes også: key("minfred")', () => {
  globalThis.Keys = { policy: (n) => (n === 'minfred' ? 'locked' : null) };
  try {
    const out = DD.scrubKeys('# load y as df, key("minfred")');
    assert.ok(out.includes('minfred'));
    assert.ok(!out.includes('***'));
  } finally { delete globalThis.Keys; }
});
