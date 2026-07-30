// tests/js/keys.test.js — klient-side nøkkellager med policyer
// (spec 2026-07-30-key-store-design). Kjøres med: node --test tests/js/keys.test.js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function makeLocalStorage(init) {
  const m = new Map(Object.entries(init || {}));
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    _dump: () => Object.fromEntries(m),
  };
}

// Hver kall = ferskt modul-scope (som en sidelasting): egen _master/_session.
function loadKeys(ls, promptFn) {
  const code = fs.readFileSync(path.join(__dirname, '..', '..', 'js', 'keys.js'), 'utf8');
  const sandbox = {
    window: { localStorage: ls },
    crypto: globalThis.crypto,
    TextEncoder, TextDecoder, btoa, atob, console,
  };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  const K = sandbox.window.Keys;
  if (promptFn) K.attachPrompt(promptFn);
  return K;
}

test('open: set/get/remove/registered/policy', async () => {
  const ls = makeLocalStorage();
  const K = loadKeys(ls);
  await K.set('fred', 'abc123');                       // default policy = open
  assert.equal(K.get('fred'), 'abc123');
  assert.equal(K.policy('fred'), 'open');
  assert.deepEqual(K.registered(), [{ name: 'fred', policy: 'open' }]);
  const doc = JSON.parse(ls.getItem('md_keys'));
  assert.equal(doc.v, 2);
  assert.equal(doc.entries.fred.value, 'abc123');      // klartekst for open
  K.remove('fred');
  assert.equal(K.get('fred'), null);
});

test('navnevalidering: ulovlige tegn og reservert «ask» avvises', async () => {
  const K = loadKeys(makeLocalStorage());
  await assert.rejects(() => K.set('har mellomrom', 'x'), /ugyldig nøkkelnavn/);
  await assert.rejects(() => K.set('a'.repeat(33), 'x'), /ugyldig nøkkelnavn/);
  await assert.rejects(() => K.set('ask', 'x'), /reservert/);
  await assert.rejects(() => K.set('ASK', 'x'), /reservert/);
});

test('migrering: md_anthropic_key flyttes inn som open-post', () => {
  const ls = makeLocalStorage({ md_anthropic_key: 'sk-ant-123' });
  const K = loadKeys(ls);
  assert.equal(K.get('anthropic'), 'sk-ant-123');
  assert.equal(ls.getItem('md_anthropic_key'), null);
});

test('migrering: flatt openstat-format (uten v) blir v2 med policy open', () => {
  const ls = makeLocalStorage({ md_keys: JSON.stringify({ anthropic: 'sk-1', fred: 'f-2' }) });
  const K = loadKeys(ls);
  assert.equal(K.get('anthropic'), 'sk-1');
  assert.equal(K.get('fred'), 'f-2');
  assert.equal(JSON.parse(ls.getItem('md_keys')).v, 2);
});

test('ukjent navn: get/policy gir null, registered tom', () => {
  const K = loadKeys(makeLocalStorage());
  assert.equal(K.get('finnesikke'), null);
  assert.equal(K.policy('finnesikke'), null);
  assert.deepEqual(K.registered(), []);
});
