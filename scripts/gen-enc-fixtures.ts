// Regenerates safepy/tests/fixtures_enc/ from js/enc-crypto.js (the production
// encryptor). Run after any change to the JS module:
//   deno run --allow-read --allow-write scripts/gen-enc-fixtures.ts
const src = await Deno.readTextFile(new URL("../js/enc-crypto.js", import.meta.url));
(0, eval)(src);
// deno-lint-ignore no-explicit-any
const EC = (globalThis as any).EncCrypto;

const plain = new TextEncoder().encode("kommune,alder\nOslo,44\nBergen,37\n");
const { envelope, key } = await EC.encryptBytes(plain, "csv");

const out = new URL("../../safepy/tests/fixtures_enc/", import.meta.url);
await Deno.mkdir(out, { recursive: true });
await Deno.writeTextFile(new URL("fixture_envelope.json", out), JSON.stringify(envelope, null, 1) + "\n");
await Deno.writeTextFile(new URL("fixture_key.txt", out), key + "\n");
await Deno.writeFile(new URL("fixture_plain.csv", out), plain);
console.log("wrote fixtures_enc — fingerprint:", envelope.fingerprint);
