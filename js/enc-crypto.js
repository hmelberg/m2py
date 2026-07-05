// safepy-enc-v1: hel-fil AES-256-GCM-konvolutt (spec 2026-07-05-encrypted-
// external-sources-design.md §2). Python-tvillingen er safepy/encfile.py;
// wire-formatet låses av safepy/tests/fixtures_enc/ som REGENERERES fra denne
// modulen (scripts/gen-enc-fixtures.ts). Ingen avhengigheter: WebCrypto.
// Kjører som browser-script (window.EncCrypto) og under Deno-eval i tester.
(function (global) {
  'use strict';

  var FORMAT = 'safepy-enc-v1';

  function b64encode(bytes) {
    var s = '';
    for (var i = 0; i < bytes.length; i += 0x8000)
      s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
  }
  function b64decode(str) {
    var bin = atob(str);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  function keyToBytes(key) {
    var s = (key || '').trim().replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    var raw;
    try { raw = b64decode(s); } catch (e) { throw new Error('ugyldig nøkkel (må være base64url)'); }
    if (raw.length !== 32) throw new Error('ugyldig nøkkel (må være 256 bit base64url)');
    return raw;
  }
  function bytesToKey(raw) {
    return b64encode(raw).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  async function sha256hex(bytes) {
    var d = await crypto.subtle.digest('SHA-256', bytes);
    return Array.prototype.map.call(new Uint8Array(d), function (b) {
      return b.toString(16).padStart(2, '0');
    }).join('');
  }

  function generateKey() {
    var raw = new Uint8Array(32);
    crypto.getRandomValues(raw);
    return bytesToKey(raw);
  }

  function isEnvelope(obj) {
    return !!obj && typeof obj === 'object' && !Array.isArray(obj) && obj.format === FORMAT;
  }

  async function encryptBytes(bytes, payloadFormat, key) {
    if (payloadFormat !== 'csv' && payloadFormat !== 'parquet')
      throw new Error('payload_format må være csv eller parquet');
    key = key || generateKey();
    var iv = new Uint8Array(12);
    crypto.getRandomValues(iv);
    var ck = await crypto.subtle.importKey('raw', keyToBytes(key), 'AES-GCM', false, ['encrypt']);
    var ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: iv }, ck, bytes));
    var envelope = {
      format: FORMAT,
      cipher: 'AES-256-GCM',
      payload_format: payloadFormat,
      iv: b64encode(iv),
      ciphertext: b64encode(ct),
      fingerprint: await sha256hex(ct),
    };
    return { envelope: envelope, key: key };
  }

  async function decryptEnvelope(envelope, key) {
    if (!isEnvelope(envelope)) throw new Error('ikke en safepy-enc-v1-fil');
    var ck = await crypto.subtle.importKey('raw', keyToBytes(key), 'AES-GCM', false, ['decrypt']);
    try {
      var pt = await crypto.subtle.decrypt(
        { name: 'AES-GCM', iv: b64decode(envelope.iv) }, ck, b64decode(envelope.ciphertext));
      return new Uint8Array(pt);
    } catch (e) {
      throw new Error('feil nøkkel eller ødelagt fil');
    }
  }

  // sha256 REGNET PÅ NYTT fra ciphertext — feltet i konvolutten er bekvemmelighet,
  // aldri sannhet. Sammenlignes mot registrert fingerprint (bytte-vern).
  async function envelopeFingerprint(envelope) {
    return sha256hex(b64decode(envelope.ciphertext));
  }

  global.EncCrypto = {
    generateKey: generateKey,
    encryptBytes: encryptBytes,
    decryptEnvelope: decryptEnvelope,
    envelopeFingerprint: envelopeFingerprint,
    isEnvelope: isEnvelope,
  };
})(typeof window !== 'undefined' ? window : globalThis);
