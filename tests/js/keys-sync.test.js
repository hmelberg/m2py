// tests/js/keys-sync.test.js — kontosynk av nøkkellageret (fase 2, spec §3.5):
// newest-wins på doc.updated; push debounced ved mutasjon; replaceDoc (pull)
// trigger ALDRI push; utlogget = ingen nettverkskall.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function makeLocalStorage() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
  };
}

function fakeFetch(remote) {
  // remote: {doc, updated} som GET returnerer. Registrerer alle kall.
  const calls = [];
  const fn = async (url, opts) => {
    calls.push({ url, method: (opts && opts.method) || 'GET', body: opts && opts.body });
    if (!opts || !opts.method || opts.method === 'GET') {
      return { ok: true, json: async () => remote };
    }
    return { ok: true, json: async () => ({ ok: true }) };
  };
  return { fn, calls };
}

function load(ls, { remote, loggedIn = true, debounce = 10 } = {}) {
  const sandbox = {
    window: { localStorage: ls },
    crypto: globalThis.crypto,
    TextEncoder, TextDecoder, btoa, atob, console,
    setTimeout, clearTimeout,
  };
  vm.createContext(sandbox);
  for (const f of ['keys.js', 'keys-sync.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', '..', 'js', f), 'utf8'), sandbox);
  }
  const K = sandbox.window.Keys;
  const S = sandbox.window.KeysSync;
  const { fn, calls } = fakeFetch(remote || { doc: null, updated: null });
  S._configure({
    keys: K,
    auth: { isLoggedIn: loggedIn, token: 'tok-123', apiBase: () => 'https://api.test' },
    fetchImpl: fn,
  }, debounce);
  return { K, S, calls };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test('utlogget: syncNow er off og gjør ingen nettverkskall', async () => {
  const { S, calls } = load(makeLocalStorage(), { loggedIn: false });
  assert.equal(await S.syncNow(), 'off');
  assert.equal(calls.length, 0);
  assert.equal(S.status().active, false);
});

test('pull: server nyere → replaceDoc, status pulled', async () => {
  const remoteDoc = JSON.stringify({ v: 2, entries: { b: { policy: 'open', value: 'y' } }, updated: '9999-01-01T00:00:00.000Z' });
  const { K, S, calls } = load(makeLocalStorage(), { remote: { doc: remoteDoc, updated: '9999-01-01T00:00:00.000Z' } });
  await K.set('a', 'x');                         // lokal, eldre enn 9999
  await sleep(40);                               // la mutasjons-pushen passere
  calls.length = 0;
  assert.equal(await S.syncNow(), 'pulled');
  assert.equal(K.get('b'), 'y');
  assert.equal(K.get('a'), null);                // erstattet, ikke flettet
  assert.equal(calls.length, 1);                 // kun GET
  assert.ok(calls[0].url.endsWith('/_/api/keystore'));
});

test('push: lokal nyere/server tom → POST med hele dokumentet', async () => {
  const { K, S, calls } = load(makeLocalStorage());
  await K.set('a', 'x');
  await sleep(40);
  calls.length = 0;
  assert.equal(await S.syncNow(), 'pushed');
  const post = calls.find((c) => c.method === 'POST');
  assert.ok(post, 'POST mangler');
  const body = JSON.parse(post.body);
  assert.ok(body.doc.includes('"a"'));
  assert.ok(JSON.parse(body.doc).updated);
});

test('likt tidsstempel → uptodate, ingen POST', async () => {
  const ls = makeLocalStorage();
  const { K, S, calls } = load(ls);
  await K.set('a', 'x');
  await sleep(40);
  const raw = K.rawDoc();
  const upd = K.updatedAt();
  const second = load(ls, { remote: { doc: raw, updated: upd } });
  assert.equal(await second.S.syncNow(), 'uptodate');
  assert.equal(second.calls.filter((c) => c.method === 'POST').length, 0);
});

test('mutasjon → debounced push; pull (replaceDoc) pusher IKKE', async () => {
  const { K, S, calls } = load(makeLocalStorage());
  await K.set('a', 'x');
  await sleep(40);
  const posts = calls.filter((c) => c.method === 'POST').length;
  assert.equal(posts, 1);                        // én debounced push for mutasjonen
  calls.length = 0;
  K.replaceDoc(JSON.stringify({ v: 2, entries: {}, updated: '9999-01-01T00:00:00.000Z' }));
  await sleep(40);
  assert.equal(calls.length, 0);                 // server-originert endring → stille
});

test('nettverksfeil → status error, ingen krasj', async () => {
  const ls = makeLocalStorage();
  const sandbox = { window: { localStorage: ls }, crypto: globalThis.crypto, TextEncoder, TextDecoder, btoa, atob, console, setTimeout, clearTimeout };
  vm.createContext(sandbox);
  for (const f of ['keys.js', 'keys-sync.js'])
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', '..', 'js', f), 'utf8'), sandbox);
  sandbox.window.KeysSync._configure({
    keys: sandbox.window.Keys,
    auth: { isLoggedIn: true, token: 't', apiBase: () => 'https://api.test' },
    fetchImpl: async () => { throw new Error('nede'); },
  }, 10);
  assert.equal(await sandbox.window.KeysSync.syncNow(), 'error');
  assert.equal(sandbox.window.KeysSync.status().last, 'error');
});
