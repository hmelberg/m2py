// scripts/encrypt_hospital.mjs
// Encrypts data/hospital_admissions.csv into a safepy-enc-v1 envelope using
// the app's own js/enc-crypto.js (via a minimal Node vm shim), so the
// deployed app can decrypt it. Writes data/hospital_admissions.enc.json and
// prints the demo key + fingerprint.
//
// Run: node scripts/encrypt_hospital.mjs
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, '..');

const code = fs.readFileSync(path.join(root, 'js', 'enc-crypto.js'), 'utf8');
const sandbox = { window: {}, crypto: globalThis.crypto, TextEncoder, TextDecoder, btoa, atob, console };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const EC = sandbox.window.EncCrypto;

const csv = new Uint8Array(fs.readFileSync(path.join(root, 'data', 'hospital_admissions.csv')));
const res = await EC.encryptBytes(csv, 'csv');

fs.writeFileSync(path.join(root, 'data', 'hospital_admissions.enc.json'), JSON.stringify(res.envelope));

console.log('DEMO KEY (paste into the example):', res.key);
console.log('fingerprint:', res.envelope.fingerprint);
