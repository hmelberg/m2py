// tests/js/data-loader-keys.test.js — key(<navn>) slår opp i nøkkellageret;
// secret-nøkler går via runScope og ALDRI via promptKey/økt-cache; strict
// rører aldri lageret (spec 2026-07-30-key-store-design §3.3).
const test = require('node:test');
const assert = require('node:assert');
require('../../js/data-directives.js');
require('../../js/enc-crypto.js');
require('../../js/data-loader.js');
const DL = globalThis.DataLoader;
const EC = globalThis.EncCrypto;

async function encryptedFetch() {
  // Én ekte safepy-enc-v1-konvolutt; fetch-svar er JSON-konvolutten.
  const enc = await EC.encryptBytes(new TextEncoder().encode('x,y\n1,2\n'), 'csv');
  const body = JSON.stringify(enc.envelope);
  const fetchImpl = async () => ({
    ok: true,
    headers: { get: (h) => (h === 'content-type' ? 'application/json' : null) },
    arrayBuffer: async () => new TextEncoder().encode(body).buffer,
  });
  return { fetchImpl, key: enc.key };
}

test('key(<navn>): treff i lageret → Keys.resolve, promptKey kalles ikke', async () => {
  DL._resetCacheForTests();
  const { fetchImpl, key } = await encryptedFetch();
  const calls = { resolve: [], runScopes: [] };
  const fakeKeys = {
    policy: (n) => (n === 'minfil' ? 'secret' : null),
    resolve: async (n, ctx) => { calls.resolve.push([n, ctx]); return key; },
    runScope: async (names, fn) => { calls.runScopes.push(names); return fn(); },
  };
  const items = [{ alias: 'df', url: 'https://x.no/enc1.json', key: 'minfil' }];
  const loads = await DL.fetchResolvedItems(items, {
    fetchImpl, keys: fakeKeys,
    promptKey: async () => { throw new Error('promptKey skal ikke kalles'); },
  });
  assert.equal(new TextDecoder().decode(loads[0].bytes), 'x,y\n1,2\n');
  assert.deepEqual(calls.resolve, [['minfil', 'df']]);
  assert.deepEqual(calls.runScopes, [['minfil']]);     // secret → runScope rundt kjøringen
});

test('key(<literal uten treff>): brukes som selve nøkkelen (som før)', async () => {
  DL._resetCacheForTests();
  const { fetchImpl, key } = await encryptedFetch();
  const fakeKeys = {
    policy: () => null,
    resolve: async () => { throw new Error('resolve skal ikke kalles'); },
    runScope: async (names, fn) => fn(),
  };
  const items = [{ alias: 'df', url: 'https://x.no/enc2.json', key }];
  const loads = await DL.fetchResolvedItems(items, { fetchImpl, keys: fakeKeys });
  assert.equal(new TextDecoder().decode(loads[0].bytes), 'x,y\n1,2\n');
});

test('strict: nøkkellageret røres ALDRI', async () => {
  DL._resetCacheForTests();
  const { fetchImpl, key } = await encryptedFetch();
  const poison = new Proxy({}, { get() { throw new Error('strict skal ikke røre Keys'); } });
  const items = [{ alias: 'df', url: 'https://x.no/enc3.json', anvil: 'kilde1',
    grant: { local_profile: 'strict', location: 'https://x.no/enc3.json' } }];
  const loads = await DL.fetchResolvedItems(items, {
    fetchImpl, keys: poison,
    authorizeStrict: async () => ({ kilde1: key }),
  });
  // V4: strict returnerer konvolutt+nøkkel for dekryptering INNE i kjøringen.
  assert.ok(loads[0].envelope);
  assert.equal(loads[0].key, key);
});
