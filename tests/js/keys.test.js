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

function promptStub(password, log) {
  return async (opts) => { (log || []).push(opts); return password; };
}

test('locked: set krever passord første gang (mode create), get virker i økten', async () => {
  const ls = makeLocalStorage();
  const log = [];
  const K = loadKeys(ls, promptStub('hemmelig123', log));
  await K.set('helse', 'K3Y-MATERIAL', 'locked');
  assert.equal(log[0].mode, 'create');                  // første ikke-åpne nøkkel → sett passord
  assert.equal(K.get('helse'), 'K3Y-MATERIAL');         // opplåst i økten
  const doc = JSON.parse(ls.getItem('md_keys'));
  assert.equal(doc.kdf.alg, 'PBKDF2-SHA-256');
  assert.equal(doc.kdf.iters, 600000);
  assert.ok(doc.verifier.ct);
  assert.ok(!('value' in doc.entries.helse));           // ingen klartekst i dokumentet
  assert.ok(doc.entries.helse.ct);
});

test('locked: ny økt er låst; resolve låser opp (mode unlock); lockNow låser igjen', async () => {
  const ls = makeLocalStorage();
  const K1 = loadKeys(ls, promptStub('pw1'));
  await K1.set('helse', 'K3Y', 'locked');
  // «Ny sidelasting»: ferskt modul-scope mot samme localStorage.
  const log = [];
  const K2 = loadKeys(ls, promptStub('pw1', log));
  assert.equal(K2.get('helse'), null);                  // låst → get gir null
  assert.equal(K2.status().hasPassword, true);
  assert.equal(K2.status().unlocked, false);
  assert.equal(await K2.resolve('helse', 'testkilde'), 'K3Y');
  assert.equal(log[0].mode, 'unlock');
  assert.equal(K2.get('helse'), 'K3Y');                 // nå i økt-cache
  assert.equal(log.length, 1);                          // bare ÉN prompt per økt
  await K2.resolve('helse');
  assert.equal(log.length, 1);
  K2.lockNow();
  assert.equal(K2.get('helse'), null);
});

test('locked: feil passord gir «feil passord», ikke søppel', async () => {
  const ls = makeLocalStorage();
  const K1 = loadKeys(ls, promptStub('riktig'));
  await K1.set('helse', 'K3Y', 'locked');
  const K2 = loadKeys(ls, promptStub('feil'));
  await assert.rejects(() => K2.resolve('helse'), /feil passord/);
  assert.equal(K2.get('helse'), null);                  // forble låst
});

test('avbrutt prompt (null) → avbrutt-feil', async () => {
  const ls = makeLocalStorage();
  const K = loadKeys(ls, async () => null);
  await assert.rejects(() => K.set('helse', 'K3Y', 'locked'), /avbrutt/);
});

test('setPolicy: open→locked krypterer, locked→open dekrypterer', async () => {
  const ls = makeLocalStorage();
  const K = loadKeys(ls, promptStub('pw'));
  await K.set('fred', 'abc');
  await K.setPolicy('fred', 'locked');
  let doc = JSON.parse(ls.getItem('md_keys'));
  assert.ok(!('value' in doc.entries.fred) && doc.entries.fred.ct);
  assert.equal(K.get('fred'), 'abc');                   // fortsatt opplåst i økten
  await K.setPolicy('fred', 'open');
  doc = JSON.parse(ls.getItem('md_keys'));
  assert.equal(doc.entries.fred.value, 'abc');
});

test('changePassword: re-krypterer alt; gammelt passord virker ikke lenger', async () => {
  const ls = makeLocalStorage();
  const K1 = loadKeys(ls, promptStub('gammel'));
  await K1.set('a', 'AAA', 'locked');
  await K1.changePassword('gammel', 'ny');
  assert.equal(K1.get('a'), 'AAA');                     // fortsatt opplåst
  const K2 = loadKeys(ls, promptStub('gammel'));
  await assert.rejects(() => K2.resolve('a'), /feil passord/);
  const K3 = loadKeys(ls, promptStub('ny'));
  assert.equal(await K3.resolve('a'), 'AAA');
  await assert.rejects(() => K1.changePassword('feilgammel', 'x'), /feil passord/);
});

test('resetEncrypted: sletter krypterte poster + kdf, beholder open', async () => {
  const ls = makeLocalStorage();
  const K = loadKeys(ls, promptStub('pw'));
  await K.set('open1', 'o');
  await K.set('locked1', 'l', 'locked');
  K.resetEncrypted();
  assert.equal(K.get('open1'), 'o');
  assert.equal(K.get('locked1'), null);
  assert.deepEqual(K.registered(), [{ name: 'open1', policy: 'open' }]);
  const doc = JSON.parse(ls.getItem('md_keys'));
  assert.ok(!doc.kdf && !doc.verifier);
  assert.equal(K.status().hasPassword, false);
});
