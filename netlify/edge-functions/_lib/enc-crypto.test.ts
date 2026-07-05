import { assertEquals, assertRejects } from "https://deno.land/std@0.224.0/assert/mod.ts";

// js/enc-crypto.js is a plain browser script: evaluate it and read the global.
const src = await Deno.readTextFile(new URL("../../../js/enc-crypto.js", import.meta.url));
(0, eval)(src);
// deno-lint-ignore no-explicit-any
const EC = (globalThis as any).EncCrypto;

Deno.test("round-trip + self-consistent fingerprint", async () => {
  const data = new TextEncoder().encode("a,b\n1,2\n");
  const { envelope, key } = await EC.encryptBytes(data, "csv");
  assertEquals(envelope.format, "safepy-enc-v1");
  assertEquals(envelope.cipher, "AES-256-GCM");
  assertEquals(envelope.payload_format, "csv");
  assertEquals(await EC.envelopeFingerprint(envelope), envelope.fingerprint);
  const out = await EC.decryptEnvelope(envelope, key);
  assertEquals(new TextDecoder().decode(out), "a,b\n1,2\n");
});

Deno.test("wrong key rejects with norsk melding", async () => {
  const { envelope } = await EC.encryptBytes(new TextEncoder().encode("x"), "csv");
  await assertRejects(() => EC.decryptEnvelope(envelope, EC.generateKey()), Error, "feil nøkkel");
});

Deno.test("key shape: 43 chars base64url, no padding", () => {
  const k = EC.generateKey();
  assertEquals(k.length, 43);
  if (/[+/=]/.test(k)) throw new Error("nøkkelen skal være base64url uten padding");
});

Deno.test("isEnvelope negative cases", () => {
  if (EC.isEnvelope({ format: "safepy-he-v1" })) throw new Error("he er ikke enc");
  if (EC.isEnvelope(null)) throw new Error("null er ikke envelope");
});
