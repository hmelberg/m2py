const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadEncCrypto() {
  const code = fs.readFileSync(path.join(__dirname, '..', '..', 'js', 'enc-crypto.js'), 'utf8');
  const sandbox = { window: {}, crypto: globalThis.crypto, TextEncoder, TextDecoder, btoa, atob, console };
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  return sandbox.window.EncCrypto;
}

test('safepy-enc-v1 round-trips the hospital CSV', async () => {
  const EC = loadEncCrypto();
  const csv = fs.readFileSync(path.join(__dirname, '..', '..', 'data', 'hospital_admissions.csv'));
  const bytes = new Uint8Array(csv);
  const res = await EC.encryptBytes(bytes, 'csv');       // {envelope, key, ...}
  assert.ok(EC.isEnvelope(res.envelope));
  const back = await EC.decryptEnvelope(res.envelope, res.key);
  assert.deepEqual(Buffer.from(back), Buffer.from(bytes));
});
