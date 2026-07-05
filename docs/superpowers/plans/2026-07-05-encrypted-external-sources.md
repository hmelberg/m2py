# Encrypted External Sources + Unified connect/load — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Owners keep an AES-encrypted data file at any URL; Anvil holds only location + fingerprint + access policy (+ optionally the wrapped key) and releases the key to whitelisted, logged-in analysts for local in-browser analysis — with the same script working on remote execution, and protected/sensitive registered URL files forced remote.

**Architecture:** A new `safepy-enc-v1` AES-256-GCM envelope format implemented twice against shared fixtures (Python `safepy/encfile.py`, JS `js/enc-crypto.js`). The m2py `connect`/`load` comment directives gain `key()`/`exec()` options and bare-name (Anvil) targets; `js/data-loader.js` resolves grants via a new `/source_access` endpoint and decrypts locally. Server side: `source_registry.load_dataframe` learns `kind="encrypted_url"`, `safepy_shim` accepts per-run `source_keys`, and a new self-service registration surface (`owner_sources.py` + `deldata.html`) lets logged-in owners register sources with a protection level and per-source allowlist.

**Tech Stack:** WebCrypto (browser AES-GCM, zero new JS deps), Python `cryptography` (AESGCM + existing Fernet), Anvil Data Tables/HTTP endpoints, Deno tests for JS, pytest for Python.

**Spec:** `docs/superpowers/specs/2026-07-05-encrypted-external-sources-design.md` (m2py repo).

## Global Constraints

- **Repos:** m2py (client), microdata-api (server), safepy (format module; vendored into microdata-api by `m2py/sync_to_api.py`). All work committed to each repo's `dev` branch and pushed to `origin dev`.
- **No new JS dependencies, no build step.** JS modules use the existing `(function (global) { ... })(typeof window !== 'undefined' ? window : globalThis)` pattern so they run as browser script tags AND under Deno `eval` in tests.
- **Wire format lock:** `safepy/tests/fixtures_enc/` is regenerated ONLY from `js/enc-crypto.js` (via `m2py/scripts/gen-enc-fixtures.ts`); Python must decrypt those exact bytes.
- **Envelope format (spec §2, verbatim):** `{"format": "safepy-enc-v1", "cipher": "AES-256-GCM", "payload_format": "csv"|"parquet", "iv": <base64 12 bytes>, "ciphertext": <base64>, "fingerprint": <sha256 hex of ciphertext bytes>}`. Key = 32 bytes as base64url without padding.
- **Keys never persist in plaintext:** stored keys are Fernet-wrapped via `media_crypto` (like `he_key`); `key(<literal>)` is scrubbed to `key(***)` in audit logs and AI prompts (`key(ask)` is not a secret and is left alone); `source_keys` request values are never logged.
- **404, never 401/403,** for unknown/denied source lookups (no existence leak — same rule as `/source_info`).
- **Levels and locations come from the registry only, never the request** (existing invariant, `safepy_shim.py:49`).
- **User-facing messages in Norwegian** (error strings, UI copy), matching the existing codebase.
- **Microdata mode and the synthetic engine are untouched.** `require` keeps today's exact routing everywhere.
- Test commands: pytest from each repo root (`python -m pytest tests/ -x -q`); Deno tests via `cd netlify/edge-functions && deno test --allow-read _lib/<file>.test.ts`.

## File Structure

| File | Repo | Responsibility |
|---|---|---|
| `safepy/encfile.py` (new) | safepy | Python envelope encrypt/decrypt/fingerprint (reference impl for server) |
| `tests/test_encfile.py` (new), `tests/fixtures_enc/` (new) | safepy | Round-trip + JS-interop wire-format lock |
| `js/enc-crypto.js` (new) | m2py | WebCrypto envelope encrypt/decrypt/fingerprint (browser + owner tool) |
| `scripts/gen-enc-fixtures.ts` (new) | m2py | Regenerates `safepy/tests/fixtures_enc/` from the JS module |
| `netlify/edge-functions/_lib/enc-crypto.test.ts` (new) | m2py | Deno tests for the JS module |
| `js/data-directives.js` (modify) | m2py | `key()`/`exec()` options, bare-name→Anvil classification, `scrubKeys` |
| `js/data-loader.js` (modify) | m2py | `/source_access` resolution, envelope decrypt, `{loads, remote}` return |
| `index.html` (modify) | m2py | Wiring: script tag, key-prompt modal, remote routing with `source_keys` |
| `encrypt.html` (modify) | m2py | New "Vanlig kryptering (AES)" flow next to the HE flow |
| `deldata.html` (new) | m2py | Self-service source registration page |
| `server_code/source_registry.py` (modify) | microdata-api | `encrypted_url` load path; `enc_key`/`access_policy` row fields |
| `server_code/source_access.py` (new) | microdata-api | Pure access decision (policy check, grant/remote_only/denied) |
| `server_code/owner_sources.py` (new) | microdata-api | Self-service register/list/deactivate endpoints |
| `server_code/safepy_shim.py` (modify) | microdata-api | `source_keys` per-run key passthrough |
| `server_code/api_endpoints.py` (modify) | microdata-api | `/source_access` endpoint; `/run_extended` `source_keys` |
| `server_code/query_audit.py` (modify) | microdata-api | `scrub_keys` on logged scripts |
| `server_code/admin_sources.py` (modify) | microdata-api | Allow `kind="encrypted_url"` in admin CRUD |
| `tests/test_enc_sources.py`, `tests/test_source_access.py`, `tests/test_owner_sources.py` (new) | microdata-api | Server-side test suites |
| `examples/py30_encrypted_source.txt` (new) | m2py | Documented example script |

---

### Task 1: `safepy/encfile.py` — Python envelope module

**Files:**
- Create: `safepy/safepy/encfile.py`
- Test: `safepy/tests/test_encfile.py`

**Interfaces:**
- Produces (used by Tasks 3–6 server-side):
  - `FORMAT = "safepy-enc-v1"`
  - `generate_key() -> str` — 32 random bytes, base64url no padding
  - `encrypt_bytes(data: bytes, payload_format: str, key: str | None = None) -> tuple[dict, str]` — `(envelope, key)`
  - `decrypt_envelope(env: dict, key: str) -> bytes` — raises `ValueError("feil nøkkel eller ødelagt fil")` on bad key/tamper
  - `is_envelope(obj) -> bool`
  - `envelope_fingerprint(env: dict) -> str` — sha256 hex recomputed from ciphertext bytes

- [ ] **Step 1: Write the failing test**

`safepy/tests/test_encfile.py`:

```python
"""safepy-enc-v1: whole-file AES-256-GCM envelope (spec
m2py/docs/superpowers/specs/2026-07-05-encrypted-external-sources-design.md §2).
The JS twin is m2py/js/enc-crypto.js; tests/fixtures_enc/ locks the wire format."""
import json
import pathlib

import pytest

from safepy import encfile

PLAIN = b"kommune,alder\nOslo,44\nBergen,37\n"


def test_roundtrip_csv():
    env, key = encfile.encrypt_bytes(PLAIN, "csv")
    assert env["format"] == "safepy-enc-v1"
    assert env["cipher"] == "AES-256-GCM"
    assert env["payload_format"] == "csv"
    assert encfile.decrypt_envelope(env, key) == PLAIN


def test_roundtrip_parquet_bytes():
    data = b"\x00\x01binary-parquet-ish\xff" * 100
    env, key = encfile.encrypt_bytes(data, "parquet")
    assert encfile.decrypt_envelope(env, key) == data


def test_wrong_key_norsk_error():
    env, _ = encfile.encrypt_bytes(PLAIN, "csv")
    with pytest.raises(ValueError, match="feil nøkkel eller ødelagt fil"):
        encfile.decrypt_envelope(env, encfile.generate_key())


def test_tampered_ciphertext_refused():
    env, key = encfile.encrypt_bytes(PLAIN, "csv")
    import base64
    ct = bytearray(base64.b64decode(env["ciphertext"]))
    ct[0] ^= 0xFF
    bad = dict(env, ciphertext=base64.b64encode(bytes(ct)).decode("ascii"))
    with pytest.raises(ValueError, match="feil nøkkel eller ødelagt fil"):
        encfile.decrypt_envelope(bad, key)


def test_fingerprint_matches_and_recomputes():
    env, _ = encfile.encrypt_bytes(PLAIN, "csv")
    assert encfile.envelope_fingerprint(env) == env["fingerprint"]
    assert len(env["fingerprint"]) == 64


def test_key_shape():
    key = encfile.generate_key()
    assert "=" not in key and len(key) == 43        # 32 bytes base64url, no padding


def test_is_envelope():
    env, _ = encfile.encrypt_bytes(PLAIN, "csv")
    assert encfile.is_envelope(env)
    assert not encfile.is_envelope({"format": "safepy-he-v1"})
    assert not encfile.is_envelope(None)
    assert not encfile.is_envelope([1, 2])


def test_invalid_key_string():
    env, _ = encfile.encrypt_bytes(PLAIN, "csv")
    with pytest.raises(ValueError, match="ugyldig nøkkel"):
        encfile.decrypt_envelope(env, "for-kort")


def test_invalid_payload_format():
    with pytest.raises(ValueError, match="payload_format"):
        encfile.encrypt_bytes(PLAIN, "xlsx")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/test_encfile.py -x -q`
Expected: FAIL / collection error — `cannot import name 'encfile'`

- [ ] **Step 3: Write the implementation**

`safepy/safepy/encfile.py`:

```python
# safepy/encfile.py
"""safepy-enc-v1: whole-file AES-256-GCM envelope for ordinary (non-homomorphic)
encrypted data files.

A sibling of the safepy-he-v1 format (he.py) — deliberately boring. The owner
encrypts a csv/parquet file as-is; the ciphertext may live at any URL (the host
needs zero trust); the fingerprint is registered server-side so a swapped file
is refused. The JS twin (m2py/js/enc-crypto.js) is the production encryptor;
tests/fixtures_enc/ locks the wire format between the two.

Envelope: {"format": "safepy-enc-v1", "cipher": "AES-256-GCM",
           "payload_format": "csv"|"parquet", "iv": b64(12 bytes),
           "ciphertext": b64, "fingerprint": sha256hex(ciphertext bytes)}
Key: 32 bytes as base64url without padding (~43 chars).
"""
from __future__ import annotations

import base64
import hashlib
import os

FORMAT = "safepy-enc-v1"
_CIPHER = "AES-256-GCM"
_PAYLOAD_FORMATS = {"csv", "parquet"}


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def generate_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")


def _key_bytes(key: str) -> bytes:
    s = (key or "").strip()
    try:
        raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except Exception:
        raise ValueError("ugyldig nøkkel (må være base64url)")
    if len(raw) != 32:
        raise ValueError("ugyldig nøkkel (må være 256 bit base64url)")
    return raw


def encrypt_bytes(data: bytes, payload_format: str, key: str | None = None):
    """Encrypt a whole file. Returns (envelope_dict, key_str)."""
    if payload_format not in _PAYLOAD_FORMATS:
        raise ValueError(f"payload_format må være en av {sorted(_PAYLOAD_FORMATS)}")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = key or generate_key()
    iv = os.urandom(12)
    ct = AESGCM(_key_bytes(key)).encrypt(iv, data, None)
    env = {
        "format": FORMAT,
        "cipher": _CIPHER,
        "payload_format": payload_format,
        "iv": _b64e(iv),
        "ciphertext": _b64e(ct),
        "fingerprint": hashlib.sha256(ct).hexdigest(),
    }
    return env, key


def is_envelope(obj) -> bool:
    return isinstance(obj, dict) and obj.get("format") == FORMAT


def envelope_fingerprint(env: dict) -> str:
    """sha256 hex RECOMPUTED from the ciphertext bytes (never trust the field)."""
    return hashlib.sha256(_b64d(env["ciphertext"])).hexdigest()


def decrypt_envelope(env: dict, key: str) -> bytes:
    """Envelope + key -> plaintext bytes. GCM guarantees no partial decrypt."""
    if not is_envelope(env):
        raise ValueError("ikke en safepy-enc-v1-fil")
    if env.get("cipher") != _CIPHER:
        raise ValueError(f"ukjent cipher: {env.get('cipher')!r}")
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        return AESGCM(_key_bytes(key)).decrypt(_b64d(env["iv"]), _b64d(env["ciphertext"]), None)
    except InvalidTag:
        raise ValueError("feil nøkkel eller ødelagt fil")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/test_encfile.py -x -q`
Expected: 9 passed

- [ ] **Step 5: Run the full safepy suite (no regressions)**

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/ -x -q`
Expected: all pass

- [ ] **Step 6: Commit (safepy repo)**

```bash
cd /Users/hom/Documents/GitHub/safepy
git add safepy/encfile.py tests/test_encfile.py
git commit -m "feat(encfile): safepy-enc-v1 AES-256-GCM whole-file envelope"
```

---

### Task 2: `js/enc-crypto.js` + Deno tests + interop fixtures

**Files:**
- Create: `m2py/js/enc-crypto.js`
- Create: `m2py/netlify/edge-functions/_lib/enc-crypto.test.ts`
- Create: `m2py/scripts/gen-enc-fixtures.ts`
- Create (generated): `safepy/tests/fixtures_enc/fixture_envelope.json`, `fixture_key.txt`, `fixture_plain.csv`
- Modify: `safepy/tests/test_encfile.py` (add interop test)

**Interfaces:**
- Produces (used by Tasks 7–10): global `EncCrypto` with
  - `generateKey() -> string`
  - `encryptBytes(bytes: Uint8Array, payloadFormat: string, key?: string) -> Promise<{envelope, key}>`
  - `decryptEnvelope(envelope, key) -> Promise<Uint8Array>` — rejects `Error("feil nøkkel eller ødelagt fil")`
  - `envelopeFingerprint(envelope) -> Promise<string>` (recomputed from ciphertext)
  - `isEnvelope(obj) -> boolean`

- [ ] **Step 1: Write the failing Deno test**

`m2py/netlify/edge-functions/_lib/enc-crypto.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/enc-crypto.test.ts`
Expected: FAIL — cannot read `js/enc-crypto.js`

- [ ] **Step 3: Write the implementation**

`m2py/js/enc-crypto.js`:

```javascript
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
```

- [ ] **Step 4: Run Deno tests to verify they pass**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/enc-crypto.test.ts`
Expected: 4 passed

- [ ] **Step 5: Write the fixture generator**

`m2py/scripts/gen-enc-fixtures.ts`:

```typescript
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
```

Run: `cd /Users/hom/Documents/GitHub/m2py && deno run --allow-read --allow-write scripts/gen-enc-fixtures.ts`
Expected: `wrote fixtures_enc — fingerprint: <64 hex chars>`

- [ ] **Step 6: Add the Python interop test (JS-encrypted → Python-decrypted)**

Append to `safepy/tests/test_encfile.py`:

```python
_FIXTURES = pathlib.Path(__file__).parent / "fixtures_enc"


def test_js_interop_fixture():
    """The fixture was produced entirely by m2py/js/enc-crypto.js (WebCrypto).
    Python must decrypt those exact bytes — this locks the wire format."""
    env = json.loads((_FIXTURES / "fixture_envelope.json").read_text())
    key = (_FIXTURES / "fixture_key.txt").read_text().strip()
    plain = (_FIXTURES / "fixture_plain.csv").read_bytes()
    assert encfile.is_envelope(env)
    assert encfile.envelope_fingerprint(env) == env["fingerprint"]
    assert encfile.decrypt_envelope(env, key) == plain
```

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/test_encfile.py -x -q`
Expected: 10 passed

- [ ] **Step 7: Commit (both repos)**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/enc-crypto.js scripts/gen-enc-fixtures.ts netlify/edge-functions/_lib/enc-crypto.test.ts
git commit -m "feat(enc): js/enc-crypto.js — safepy-enc-v1 WebCrypto twin + fixture generator"
cd /Users/hom/Documents/GitHub/safepy
git add tests/fixtures_enc tests/test_encfile.py
git commit -m "test(encfile): JS-interop fixtures lock the safepy-enc-v1 wire format"
```

---

### Task 3: server `encrypted_url` load path (microdata-api)

**Files:**
- Run: `python /Users/hom/Documents/GitHub/m2py/sync_to_api.py --apply` (vendors `safepy/encfile.py` into `server_code/safepy/`)
- Modify: `microdata-api/server_code/source_registry.py`
- Modify: `microdata-api/server_code/admin_sources.py:24` (`VALID_KINDS`)
- Test: `microdata-api/tests/test_enc_sources.py`

**Interfaces:**
- Consumes: `safepy.encfile` (Task 1), `media_crypto.decrypt_bytes` (existing)
- Produces: `load_dataframe(src)` handles `src["kind"] == "encrypted_url"`; key precedence `src["_run_key"]` (plaintext, injected per-run) → Fernet-unwrapped `src["enc_key"]` → `ValueError`. `_row_to_source` adds `enc_key`, `access_policy`, `owner_email`, `name` fields.

- [ ] **Step 1: Vendor sync**

Run: `python /Users/hom/Documents/GitHub/m2py/sync_to_api.py --apply`
Expected: report lists `safepy/encfile.py` as new/updated; `microdata-api/server_code/safepy/encfile.py` exists with the GENERATED header.

- [ ] **Step 2: Write the failing test**

`microdata-api/tests/test_enc_sources.py`:

```python
"""Offline tests for safepy-enc-v1 sources (kind="encrypted_url"): the
load_dataframe decrypt path and safepy_shim per-run key passthrough.
No Anvil, no network — _raw_bytes is monkeypatched."""
import json
import os

import pandas as pd
import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("MEDIA_AT_REST_KEY", Fernet.generate_key().decode())

import media_crypto
import source_registry
from safepy import encfile


def _envelope():
    df = pd.DataFrame({"region": ["A"] * 30 + ["B"] * 30,
                       "salary": [30000 + i * 100 for i in range(60)]})
    env, key = encfile.encrypt_bytes(df.to_csv(index=False).encode(), "csv")
    return df, env, key


@pytest.fixture()
def enc_source(monkeypatch):
    df, env, key = _envelope()
    src = {
        "source_id": "enc_test",
        "kind": "encrypted_url",
        "location": "https://example.org/data.enc.json",
        "file": None,
        "format": "csv",
        "level": "public",
        "default_exec": "local",
        "encrypted": True,
        "fingerprint": encfile.envelope_fingerprint(env),
        "enc_key": media_crypto.encrypt_bytes(key.encode()).decode("ascii"),
        "access_policy": {"emails": ["ana@fhi.no"], "domains": []},
        "owner_email": "eier@fhi.no",
        "status": "active",
    }
    monkeypatch.setattr(source_registry, "_raw_bytes",
                        lambda s: json.dumps(env).encode())
    return df, env, key, src


def test_load_dataframe_stored_key(enc_source):
    df, _, _, src = enc_source
    out = source_registry.load_dataframe(src)
    assert list(out.columns) == ["region", "salary"]
    assert len(out) == 60


def test_load_dataframe_run_key_overrides(enc_source):
    _, _, key, src = enc_source
    out = source_registry.load_dataframe(dict(src, enc_key=None, _run_key=key))
    assert len(out) == 60


def test_load_dataframe_missing_key(enc_source):
    _, _, _, src = enc_source
    with pytest.raises(ValueError, match="nøkkel"):
        source_registry.load_dataframe(dict(src, enc_key=None))


def test_load_dataframe_wrong_run_key(enc_source):
    _, _, _, src = enc_source
    with pytest.raises(ValueError, match="feil nøkkel eller ødelagt fil"):
        source_registry.load_dataframe(
            dict(src, enc_key=None, _run_key=encfile.generate_key()))


def test_load_dataframe_refuses_swapped_file(enc_source, monkeypatch):
    _, _, key, src = enc_source
    env2, _ = encfile.encrypt_bytes(b"a,b\n1,2\n", "csv", key)
    monkeypatch.setattr(source_registry, "_raw_bytes",
                        lambda s: json.dumps(env2).encode())
    with pytest.raises(ValueError, match="fingerprint"):
        source_registry.load_dataframe(src)


def test_load_dataframe_not_an_envelope(enc_source, monkeypatch):
    _, _, _, src = enc_source
    monkeypatch.setattr(source_registry, "_raw_bytes", lambda s: b"a,b\n1,2\n")
    with pytest.raises(ValueError, match="safepy-enc-v1"):
        source_registry.load_dataframe(src)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_enc_sources.py -x -q`
Expected: FAIL — `load_dataframe` reads `m2py_runtime.sources.read_source` for the unknown kind (network error or read failure)

- [ ] **Step 4: Implement in `source_registry.py`**

In `_row_to_source` (after the `he_key` line):

```python
        "enc_key": _cell(row, "enc_key"),
        "access_policy": _cell(row, "access_policy"),
        "owner_email": _cell(row, "owner_email") or "",
        "name": _cell(row, "name") or row["source_id"],
```

In `load_dataframe`, insert BEFORE the final `read_source` fallback (after the `kind == "media"` block):

```python
    if src.get("kind") == "encrypted_url":
        return _load_enc_envelope(src)
```

Add at module level (below `load_dataframe`):

```python
def _load_enc_envelope(src: dict):
    """kind="encrypted_url": location holds a safepy-enc-v1 envelope. The key
    comes per-run (src["_run_key"], from the request) or Fernet-unwrapped from
    the row (enc_key). Plaintext exists only in memory (spec §5)."""
    import io
    import json
    import pandas as pd
    from safepy import encfile

    env = json.loads(_raw_bytes(src).decode("utf-8"))
    if not encfile.is_envelope(env):
        raise ValueError(
            f"kilden {src.get('source_id')!r} er ikke en safepy-enc-v1-fil")
    want = src.get("fingerprint")
    if want and encfile.envelope_fingerprint(env) != want:
        raise ValueError(
            f"kilden {src.get('source_id')!r} matcher ikke registrert fingerprint "
            f"— filen kan være byttet ut siden registrering")
    key = src.get("_run_key")
    if not key and src.get("enc_key"):
        from media_crypto import decrypt_bytes
        key = decrypt_bytes(src["enc_key"].encode("ascii")).decode("ascii")
    if not key:
        raise ValueError(
            f"kilden {src.get('source_id')!r} krever dekrypteringsnøkkel "
            f"(key(...) i scriptet, eller nøkkel lagret ved registrering)")
    data = encfile.decrypt_envelope(env, key)
    buf = io.BytesIO(data)
    fmt = env.get("payload_format") or src.get("format") or "csv"
    return pd.read_parquet(buf) if fmt == "parquet" else pd.read_csv(buf)
```

Also update the module docstring's "Future seam" paragraph — the seam is now implemented; reference the spec file. In `admin_sources.py` change:

```python
VALID_KINDS = {"url", "media", "encrypted_url"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_enc_sources.py -x -q`
Expected: 6 passed

- [ ] **Step 6: Full suite + commit**

```bash
cd /Users/hom/Documents/GitHub/microdata-api
python -m pytest tests/ -x -q     # expected: all pass
git add server_code/ tests/test_enc_sources.py
git commit -m "feat(sources): kind=encrypted_url — safepy-enc-v1 decrypt in memory (stored or per-run key)"
```

---

### Task 4: `source_keys` per-run keys + audit scrubbing (microdata-api)

**Files:**
- Modify: `microdata-api/server_code/safepy_shim.py:47` (`run_extended` signature + key injection)
- Modify: `microdata-api/server_code/api_endpoints.py` (`/run_extended` body + `bg_run_extended` passthrough)
- Modify: `microdata-api/server_code/query_audit.py` (`scrub_keys`, applied in `log_run`)
- Test: extend `microdata-api/tests/test_enc_sources.py`, `tests/test_query_audit.py`

**Interfaces:**
- Produces: `safepy_shim.run_extended(script, sources_req, dialect="pandas", on_progress=None, source_keys=None)`; `query_audit.scrub_keys(script: str) -> str` (replaces `key(<literal>)` with `key(***)`, leaves `key(ask)` alone).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_enc_sources.py`:

```python
def test_shim_source_keys_passthrough(enc_source, monkeypatch):
    import safepy_shim
    _, _, key, src = enc_source
    src = dict(src, enc_key=None, level="protected")
    monkeypatch.setattr(source_registry, "resolve_source",
                        lambda sid: dict(src, source_id=sid))
    out = safepy_shim.run_extended(
        "df.groupby('region')['salary'].mean()",
        [{"alias": "df", "source_id": "enc_test"}],
        dialect="pandas", source_keys={"enc_test": key})
    assert out["err"] is None
    assert out["_audit_level"] == "protected"


def test_shim_missing_source_key_fails_clean(enc_source, monkeypatch):
    import safepy_shim
    _, _, _, src = enc_source
    src = dict(src, enc_key=None, level="protected")
    monkeypatch.setattr(source_registry, "resolve_source",
                        lambda sid: dict(src, source_id=sid))
    out = safepy_shim.run_extended(
        "df.groupby('region')['salary'].mean()",
        [{"alias": "df", "source_id": "enc_test"}], dialect="pandas")
    assert out["err"] and "nøkkel" in out["err"]
```

Append to `tests/test_query_audit.py`:

```python
def test_scrub_keys():
    import query_audit
    s = "# connect x as h, key(qL7xK2mN9pR4sT6v)\n# load h as df, key( abc )\n# connect y as k, key(ask)\n"
    out = query_audit.scrub_keys(s)
    assert "qL7xK2mN9pR4sT6v" not in out and "abc" not in out
    assert out.count("key(***)") == 2
    assert "key(ask)" in out            # ikke en hemmelighet
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_enc_sources.py tests/test_query_audit.py -x -q`
Expected: FAIL — unexpected keyword `source_keys` / no attribute `scrub_keys`

- [ ] **Step 3: Implement**

`safepy_shim.py` — change the signature and inject the key inside the source loop (right after `src = resolve_source(sid)` succeeds):

```python
def run_extended(script, sources_req, dialect="pandas", on_progress=None,
                 source_keys=None):
```

```python
        if source_keys and sid in source_keys:
            # Per-run key (mode 2: owner never stored the key). Used in memory
            # by _load_enc_envelope; never logged (query_audit scrubs scripts,
            # and source_keys itself is never written anywhere).
            src = dict(src, _run_key=str(source_keys[sid]))
```

`query_audit.py` — add near the top (after existing imports; add `import re` if absent):

```python
_KEY_RE = re.compile(r"\b(key\()\s*(?!ask\s*\))[^)]*\)", re.IGNORECASE)


def scrub_keys(script: str) -> str:
    """key(<literal>) -> key(***) before a script is logged. key(ask) is not a
    secret and is left readable."""
    return _KEY_RE.sub(r"\1***)", script or "")
```

In `log_run`, wrap the script before truncation/storage — find the line that stores the script head (`script[:20000]` or similar) and apply `scrub_keys(script)` first.

`api_endpoints.py` — in `http_run_extended`, after `raw = bool(body.get("raw", False))`:

```python
    source_keys = body.get("source_keys") or {}
    if not isinstance(source_keys, dict) or \
            not all(isinstance(k, str) and isinstance(v, str)
                    for k, v in source_keys.items()):
        return _json({"error": "source_keys må være {source_id: nøkkel}"}, status=400)
```

Pass it through `launch_background_task(... , source_ids, source_keys)`, add the parameter to `bg_run_extended`'s signature, and inside `bg_run_extended` pass `source_keys=source_keys` to `safepy_shim.run_extended(...)` (the m2py-dialect branch does NOT take keys; an encrypted source there fails with the clear "krever dekrypteringsnøkkel" error from Task 3). Grep first to confirm the exact `bg_run_extended` definition site: `grep -n "def bg_run_extended" server_code/api_endpoints.py`.

- [ ] **Step 4: Run tests to verify they pass, full suite, commit**

```bash
cd /Users/hom/Documents/GitHub/microdata-api
python -m pytest tests/ -x -q     # expected: all pass
git add server_code/safepy_shim.py server_code/api_endpoints.py server_code/query_audit.py tests/
git commit -m "feat(run_extended): per-run source_keys for encrypted sources; key(...) scrubbed from audit logs"
```

---

### Task 5: `/source_access` — policy check + key release (microdata-api)

**Files:**
- Create: `microdata-api/server_code/source_access.py`
- Modify: `microdata-api/server_code/api_endpoints.py` (new endpoint, placed after `http_source_info`)
- Test: `microdata-api/tests/test_source_access.py`

**Interfaces:**
- Produces: `source_access.access_decision(src: dict, email: str | None) -> tuple[str, dict | None]` with status `"denied" | "remote_only" | "grant"`; grant payload `{remote_only: False, location, payload_format, fingerprint, encrypted, key?}`; HTTP `GET /source_access?id=<source_id>` (Bearer required) returning that payload, 404 on unknown/denied/anonymous.

- [ ] **Step 1: Write the failing test**

`microdata-api/tests/test_source_access.py`:

```python
"""Pure tests for the /source_access decision (spec §3): who gets what.
No Anvil — media_crypto uses the MEDIA_AT_REST_KEY env fallback."""
import os

from cryptography.fernet import Fernet

os.environ.setdefault("MEDIA_AT_REST_KEY", Fernet.generate_key().decode())

import media_crypto
import source_access


def _src(**kw):
    base = {"source_id": "s", "kind": "encrypted_url",
            "location": "https://x.example/e.json", "format": "csv",
            "level": "public", "fingerprint": "abc123", "enc_key": None,
            "access_policy": {"emails": ["ana@fhi.no"], "domains": ["uio.no"]},
            "owner_email": "eier@fhi.no", "status": "active"}
    base.update(kw)
    return base


def test_denied_wrong_email():
    assert source_access.access_decision(_src(), "x@y.no")[0] == "denied"


def test_denied_no_email():
    assert source_access.access_decision(_src(), None)[0] == "denied"


def test_allowed_exact_email_case_insensitive():
    assert source_access.access_decision(_src(), "Ana@FHI.no")[0] == "grant"


def test_allowed_domain():
    assert source_access.access_decision(_src(), "per@uio.no")[0] == "grant"


def test_owner_always_allowed():
    assert source_access.access_decision(_src(), "eier@fhi.no")[0] == "grant"


def test_empty_policy_means_owner_only():
    src = _src(access_policy={"emails": [], "domains": []})
    assert source_access.access_decision(src, "ana@fhi.no")[0] == "denied"
    assert source_access.access_decision(src, "eier@fhi.no")[0] == "grant"


def test_remote_only_for_protected_never_location_never_key():
    wrapped = media_crypto.encrypt_bytes(b"K1").decode("ascii")
    st, p = source_access.access_decision(
        _src(level="protected", enc_key=wrapped), "ana@fhi.no")
    assert st == "remote_only"
    assert p == {"remote_only": True, "default_exec": "remote"}


def test_grant_mode2_no_stored_key():
    st, p = source_access.access_decision(_src(), "ana@fhi.no")
    assert st == "grant" and "key" not in p
    assert p["location"] and p["fingerprint"] == "abc123"
    assert p["payload_format"] == "csv" and p["encrypted"] is True


def test_grant_mode3_releases_unwrapped_key():
    wrapped = media_crypto.encrypt_bytes(b"K1").decode("ascii")
    st, p = source_access.access_decision(_src(enc_key=wrapped), "ana@fhi.no")
    assert st == "grant" and p["key"] == "K1"


def test_no_policy_legacy_source_grants_any_login():
    st, p = source_access.access_decision(
        _src(access_policy=None, kind="url", encrypted=False), "hvem@somhelst.no")
    assert st == "grant" and p["encrypted"] is False
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_source_access.py -x -q`
Expected: FAIL — `No module named 'source_access'`

- [ ] **Step 3: Implement `source_access.py`**

```python
# microdata-api/server_code/source_access.py
"""Access decision for /source_access (spec 2026-07-05-encrypted-external-
sources-design.md §3): given a resolved source row and the caller's verified
email, decide denied / remote_only / grant — and what the grant contains.

Pure module (no Anvil imports at module level) so it is fully unit-testable.
Key release rules:
  - access_policy present  -> caller email must match (exact, @domain, or owner).
  - access_policy absent   -> legacy behavior: any logged-in caller passes
    (matches /source_info visibility for non-public sources).
  - level != public        -> remote_only: never location, never key.
  - level == public        -> grant location (+ Fernet-unwrapped key when the
    owner stored one — mode 3 whitelist-only).
"""
from __future__ import annotations


def email_allowed(email: str | None, policy: dict | None, owner_email: str = "") -> bool:
    if not email:
        return False
    email = email.strip().lower()
    if owner_email and email == owner_email.strip().lower():
        return True
    if policy is None:
        return False
    emails = [str(e).strip().lower() for e in (policy.get("emails") or [])]
    domains = [str(d).strip().lower().lstrip("@") for d in (policy.get("domains") or [])]
    if email in emails:
        return True
    return email.rsplit("@", 1)[-1] in domains


def access_decision(src: dict, email: str | None):
    """-> (status, payload); status in {"denied", "remote_only", "grant"}."""
    policy = src.get("access_policy")
    if policy is not None and not email_allowed(email, policy, src.get("owner_email") or ""):
        return "denied", None
    if src.get("level") != "public":
        return "remote_only", {"remote_only": True, "default_exec": "remote"}
    out = {
        "remote_only": False,
        "location": src.get("location"),
        "payload_format": src.get("format") or "csv",
        "fingerprint": src.get("fingerprint"),
        "encrypted": src.get("kind") == "encrypted_url",
    }
    if src.get("kind") == "encrypted_url" and src.get("enc_key"):
        from media_crypto import decrypt_bytes
        out["key"] = decrypt_bytes(src["enc_key"].encode("ascii")).decode("ascii")
    return "grant", out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_source_access.py -x -q`
Expected: 10 passed

- [ ] **Step 5: Add the HTTP endpoint**

In `api_endpoints.py`, directly after `http_source_info`:

```python
# ---------------------------------------------------------------------------
# /source_access  (per-source grant for LOCAL analysis: location + evt. nøkkel)
# Spec: m2py docs/superpowers/specs/2026-07-05-encrypted-external-sources-design.md §3.
# 404 (aldri 401/403) for ukjent, anonym eller ikke-autorisert — som /source_info.


@anvil.server.http_endpoint("/source_access", methods=["GET"],
                            cross_site_session=False, enable_cors=True)
def http_source_access(**kwargs):
    import source_registry
    import source_access
    sid = (kwargs.get("id") or "").strip()
    if not sid:
        return _json({"error": "missing 'id'"}, status=400)
    unknown = {"error": f"unknown source: {sid}"}
    try:
        src = source_registry.resolve_source(sid)
    except KeyError:
        return _json(unknown, status=404)
    principal, autherr = _authenticate_or_fail()
    if autherr:
        return _json(unknown, status=404)
    user = auth.principal_user(principal)
    email = user["email"] if user is not None else None
    status, payload = source_access.access_decision(src, email)
    if status == "denied":
        return _json(unknown, status=404)
    if payload.get("key"):
        # Hver nøkkelutlevering revideres (spec §3). Aldri selve nøkkelen.
        try:
            import datetime as _dt
            from anvil.tables import app_tables
            app_tables.audit_log.add_row(
                when=_dt.datetime.now(_dt.timezone.utc),
                who=email or auth.principal_alias(principal),
                action="key_released", detail=sid)
        except Exception:
            pass  # revisjon skal aldri blokkere selve utleveringen
    return _json(payload)
```

- [ ] **Step 6: Full suite + commit**

```bash
cd /Users/hom/Documents/GitHub/microdata-api
python -m pytest tests/ -x -q
git add server_code/source_access.py server_code/api_endpoints.py tests/test_source_access.py
git commit -m "feat(api): /source_access — policy-gated location/key release, 404 on denial, audited key releases"
```

---

### Task 6: self-service registration endpoints (microdata-api)

**Files:**
- Create: `microdata-api/server_code/owner_sources.py`
- Test: `microdata-api/tests/test_owner_sources.py`

**Interfaces:**
- Produces:
  - `owner_sources.validate_registration(fields: dict, raw: bytes) -> dict` (pure) — returns row values incl. `kind`, `fingerprint`, `access_policy`, plus `_store_key` (plaintext key to wrap, or None). Raises `ValueError` in Norwegian.
  - HTTP `POST /sources/register` (body: `{source_id, name, location, level, format, emails: [..], domains: [..], key?, store_key?: bool}`), `GET /sources/mine`, `POST /sources/deactivate` (`{source_id}`). All require a logged-in **user** principal (email); api-key/anonymous principals are refused 403.
- Consumes: `safepy.encfile`, `media_crypto.encrypt_bytes`, `source_registry._raw_bytes`, `auth.authenticate_or_fail` / `auth.principal_user`.

- [ ] **Step 1: Write the failing test**

`microdata-api/tests/test_owner_sources.py`:

```python
"""Pure tests for self-service registration validation (spec §3, deldata)."""
import os

import pandas as pd
import pytest
from cryptography.fernet import Fernet

os.environ.setdefault("MEDIA_AT_REST_KEY", Fernet.generate_key().decode())

import owner_sources
from safepy import encfile

CSV = b"kommune,alder\nOslo,44\nBergen,37\n"


def _fields(**kw):
    base = {"source_id": "helse2025", "name": "Helse 2025",
            "location": "https://raw.githubusercontent.com/x/y/main/d.enc.json",
            "level": "public", "format": "csv",
            "emails": ["ana@fhi.no"], "domains": ["uio.no"],
            "key": None, "store_key": False}
    base.update(kw)
    return base


def _env_raw(key=None):
    import json
    env, k = encfile.encrypt_bytes(CSV, "csv", key)
    return json.dumps(env).encode(), env, k


def test_encrypted_registration_mode2():
    raw, env, _ = _env_raw()
    v = owner_sources.validate_registration(_fields(), raw)
    assert v["kind"] == "encrypted_url"
    assert v["fingerprint"] == encfile.envelope_fingerprint(env)
    assert v["access_policy"] == {"emails": ["ana@fhi.no"], "domains": ["uio.no"]}
    assert v["_store_key"] is None
    assert v["level"] == "public" and v["default_exec"] == "local"


def test_encrypted_registration_mode3_stores_key():
    raw, _, key = _env_raw()
    v = owner_sources.validate_registration(_fields(key=key, store_key=True), raw)
    assert v["_store_key"] == key


def test_supplied_key_is_verified_against_file():
    raw, _, _ = _env_raw()
    with pytest.raises(ValueError, match="feil nøkkel"):
        owner_sources.validate_registration(
            _fields(key=encfile.generate_key(), store_key=True), raw)


def test_plain_csv_registration_protected_level():
    v = owner_sources.validate_registration(
        _fields(level="protected", location="https://x.example/d.csv"), CSV)
    assert v["kind"] == "url" and v["fingerprint"] is None
    assert v["level"] == "protected" and v["default_exec"] == "remote"


def test_unreadable_plain_file_refused():
    with pytest.raises(ValueError, match="kunne ikke lese"):
        owner_sources.validate_registration(_fields(), b"\x00\x01ikke-data")


def test_bad_level_refused():
    raw, _, _ = _env_raw()
    with pytest.raises(ValueError, match="level"):
        owner_sources.validate_registration(_fields(level="hemmelig"), raw)


def test_bad_source_id_refused():
    raw, _, _ = _env_raw()
    with pytest.raises(ValueError, match="source_id"):
        owner_sources.validate_registration(_fields(source_id="x y!"), raw)


def test_http_url_required():
    raw, _, _ = _env_raw()
    with pytest.raises(ValueError, match="http"):
        owner_sources.validate_registration(_fields(location="ftp://x/d"), raw)


def test_policy_normalized_lowercase():
    raw, _, _ = _env_raw()
    v = owner_sources.validate_registration(
        _fields(emails=[" Ana@FHI.no "], domains=["@UiO.no"]), raw)
    assert v["access_policy"] == {"emails": ["ana@fhi.no"], "domains": ["uio.no"]}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_owner_sources.py -x -q`
Expected: FAIL — `No module named 'owner_sources'`

- [ ] **Step 3: Implement `owner_sources.py`**

```python
# microdata-api/server_code/owner_sources.py
"""Self-service source registration (spec 2026-07-05-encrypted-external-
sources-design.md §3; m2py page deldata.html).

Any logged-in user can register a URL source: the server fetches the bytes,
validates them (safepy-enc-v1 envelope -> kind="encrypted_url" with recomputed
fingerprint; otherwise a readable csv/parquet -> kind="url"), and stores the
row with the owner's access policy. The decryption key is stored ONLY when the
owner explicitly asks (store_key, mode 3) and is Fernet-wrapped at rest.

validate_registration() is pure (no Anvil) and unit-tested; the HTTP endpoints
below wrap it. Owners may only overwrite/deactivate their own rows.
"""
from __future__ import annotations

import datetime as dt
import io
import json

MAX_BYTES = 50 * 1024 * 1024
VALID_LEVELS = {"public", "protected", "sensitive"}
VALID_FORMATS = {"csv", "parquet"}


def _utcnow():
    return dt.datetime.now(dt.timezone.utc)


def validate_registration(fields: dict, raw: bytes) -> dict:
    """fields + fetched bytes -> sources-row values (plus _store_key).
    Raises ValueError (norsk) on any problem."""
    from safepy import encfile

    sid = (fields.get("source_id") or "").strip()
    if not sid or not sid.replace("_", "").replace("-", "").isalnum():
        raise ValueError("source_id må være satt (bokstaver/tall/_/-)")
    level = (fields.get("level") or "").strip()
    if level not in VALID_LEVELS:
        raise ValueError(f"level må være en av {sorted(VALID_LEVELS)}")
    fmt = (fields.get("format") or "csv").strip()
    if fmt not in VALID_FORMATS:
        raise ValueError(f"format må være en av {sorted(VALID_FORMATS)}")
    location = (fields.get("location") or "").strip()
    if not location.startswith(("http://", "https://")):
        raise ValueError("location må være en http(s)-URL")

    emails = [str(e).strip().lower() for e in (fields.get("emails") or []) if str(e).strip()]
    domains = [str(d).strip().lower().lstrip("@") for d in (fields.get("domains") or []) if str(d).strip()]
    key = (fields.get("key") or "").strip() or None
    store_key = bool(fields.get("store_key")) and key is not None

    try:
        env = json.loads(raw.decode("utf-8"))
    except Exception:
        env = None

    if encfile.is_envelope(env):
        kind = "encrypted_url"
        fingerprint = encfile.envelope_fingerprint(env)
        fmt = env.get("payload_format") or fmt
        if key:
            encfile.decrypt_envelope(env, key)   # raises "feil nøkkel..." if wrong
    else:
        kind = "url"
        fingerprint = None
        try:
            import pandas as pd
            buf = io.BytesIO(raw)
            df = pd.read_parquet(buf) if fmt == "parquet" else pd.read_csv(buf)
            if df is None or len(df.columns) == 0:
                raise ValueError("tom")
        except ValueError:
            raise ValueError(f"kunne ikke lese filen som {fmt} (og den er ikke "
                             f"en safepy-enc-v1-fil)")
        except Exception:
            raise ValueError(f"kunne ikke lese filen som {fmt} (og den er ikke "
                             f"en safepy-enc-v1-fil)")

    return {
        "source_id": sid,
        "name": (fields.get("name") or sid).strip(),
        "kind": kind,
        "location": location,
        "format": fmt,
        "level": level,
        "default_exec": "local" if level == "public" else "remote",
        "fingerprint": fingerprint,
        # alltid en policy for selvregistrerte kilder: tomme lister = kun eier
        "access_policy": {"emails": emails, "domains": domains},
        "_store_key": key if store_key else None,
    }


# ---------------------------------------------------------------------------
# HTTP endpoints (Anvil). Kept below the pure logic so tests never import anvil.

try:
    import anvil.server
    from anvil.tables import app_tables
    import auth
    _ANVIL = True
except Exception:            # pure test run
    _ANVIL = False


if _ANVIL:

    def _json(body, status=200):
        import anvil.server as _s
        r = _s.HttpResponse(status=status, body=json.dumps(body))
        r.headers["Content-Type"] = "application/json"
        return r

    def _require_user():
        """Logged-in user principal (email) or an error response."""
        principal, err = auth.authenticate_or_fail()
        if err:
            return None, err
        user = auth.principal_user(principal)
        if user is None:
            return None, _json({"error": "krever innlogget bruker"}, status=403)
        return user, None

    def _audit(email, action, detail):
        try:
            app_tables.audit_log.add_row(when=_utcnow(), who=email,
                                         action=action, detail=detail)
        except Exception:
            pass

    def _own_summary(row):
        def cell(name, default=None):
            try:
                return row[name]
            except Exception:
                return default
        return {"source_id": row["source_id"], "name": cell("name") or row["source_id"],
                "kind": row["kind"], "location": row["location"] or "",
                "format": cell("format") or "csv", "level": row["level"],
                "status": row["status"], "has_key": bool(cell("enc_key")),
                "access_policy": cell("access_policy") or {}}

    @anvil.server.http_endpoint("/sources/register", methods=["POST"],
                                cross_site_session=False, enable_cors=True)
    def http_sources_register():
        user, err = _require_user()
        if err:
            return err
        try:
            body = json.loads((anvil.server.request.body_json and
                               json.dumps(anvil.server.request.body_json)) or
                              anvil.server.request.body.get_bytes().decode("utf-8"))
        except Exception:
            return _json({"error": "ugyldig JSON"}, status=400)

        location = (body.get("location") or "").strip()
        if not location.startswith(("http://", "https://")):
            return _json({"error": "location må være en http(s)-URL"}, status=400)
        try:
            from source_registry import _raw_bytes
            raw = _raw_bytes({"kind": "url", "location": location})
        except Exception as exc:
            return _json({"error": f"kunne ikke hente filen: {exc}"}, status=400)
        if len(raw) > MAX_BYTES:
            return _json({"error": "filen er større enn 50 MB"}, status=400)

        try:
            values = validate_registration(body, raw)
        except ValueError as exc:
            return _json({"error": str(exc)}, status=400)

        store_key = values.pop("_store_key")
        if store_key:
            from media_crypto import encrypt_bytes
            values["enc_key"] = encrypt_bytes(store_key.encode("utf-8")).decode("ascii")
        row = app_tables.sources.get(source_id=values["source_id"])
        if row is not None and (row["status"] != "deleted" and
                                (_own_summary(row), row)[1] and
                                (row["owner_email"] or "") != user["email"]):
            return _json({"error": "source_id er allerede i bruk av en annen eier"},
                         status=409)
        now = _utcnow()
        values.update(status="active", updated=now, owner_email=user["email"])
        if row is None:
            app_tables.sources.add_row(created=now, **values)
        else:
            for k, v in values.items():
                row[k] = v
        _audit(user["email"], "source_register", values["source_id"])
        return _json({"ok": True, "source_id": values["source_id"],
                      "kind": values["kind"], "fingerprint": values["fingerprint"],
                      "level": values["level"]})

    @anvil.server.http_endpoint("/sources/mine", methods=["GET"],
                                cross_site_session=False, enable_cors=True)
    def http_sources_mine(**kwargs):
        user, err = _require_user()
        if err:
            return err
        rows = app_tables.sources.search(owner_email=user["email"])
        return _json({"sources": [_own_summary(r) for r in rows
                                  if r["status"] != "deleted"]})

    @anvil.server.http_endpoint("/sources/deactivate", methods=["POST"],
                                cross_site_session=False, enable_cors=True)
    def http_sources_deactivate():
        user, err = _require_user()
        if err:
            return err
        try:
            body = json.loads(anvil.server.request.body.get_bytes().decode("utf-8"))
        except Exception:
            return _json({"error": "ugyldig JSON"}, status=400)
        sid = (body.get("source_id") or "").strip()
        row = app_tables.sources.get(source_id=sid)
        if row is None or (row["owner_email"] or "") != user["email"]:
            return _json({"error": f"ukjent kilde: {sid}"}, status=404)
        row["status"] = "deleted"
        row["updated"] = _utcnow()
        _audit(user["email"], "source_deactivate", sid)
        return _json({"ok": True})
```

Implementation note: while implementing, compare the body-parse idiom with `api_endpoints._load_body()` (`api_endpoints.py:52`) and reuse that exact idiom (import it or copy it verbatim) instead of the ad-hoc parse above if it differs — the tests don't cover Anvil request parsing, so match the proven pattern.

- [ ] **Step 4: Run tests, full suite, commit**

```bash
cd /Users/hom/Documents/GitHub/microdata-api
python -m pytest tests/test_owner_sources.py -x -q    # expected: 9 passed
python -m pytest tests/ -x -q                          # expected: all pass
git add server_code/owner_sources.py tests/test_owner_sources.py
git commit -m "feat(api): self-service source registration — /sources/register|mine|deactivate"
```

---

### Task 7: `data-directives.js` — options, Anvil targets, scrubKeys (m2py)

**Files:**
- Modify: `m2py/js/data-directives.js`
- Test: `m2py/netlify/edge-functions/_lib/data-directives.test.ts` (extend)

**Interfaces:**
- Produces (consumed by Task 8/9):
  - `parse(script)` — connects/loads entries gain `options: {key?: string, exec?: 'local'|'remote'}` (`key` value `'ask'` for `key(ask)`/`key()`)
  - `resolve(parsed, registry)` item shapes: URL/registry as before plus `key?`, `exec?`; NEW Anvil shape `{alias, anvil: <source_id>, key?, exec?}` for bare names not in the registry
  - `scrubKeys(script) -> string` — `key(<literal>)` → `key(***)`, `key(ask)` untouched

- [ ] **Step 1: Extend the Deno test (failing)**

Append to `data-directives.test.ts`:

```typescript
Deno.test("options: key() and exec() parse on connect and load", () => {
  const script = [
    "# connect helse2025 as h, key(ask)",
    "# connect kilde2 as k, key(qL7xK2mN9pR4sT6v), exec(remote)",
    "# load https://x.example/d.enc.json as df, key(abcDEF123)",
  ].join("\n");
  const p = DD.parse(script);
  assertEquals(p.connects[0].options, { key: "ask" });
  assertEquals(p.connects[1].options, { key: "qL7xK2mN9pR4sT6v", exec: "remote" });
  assertEquals(p.loads[0].options, { key: "abcDEF123" });
});

Deno.test("resolve: bare name not in registry becomes anvil source", () => {
  const script = [
    "# connect helse2025 as h, key(ask)",
    "# load h as df",
    "# connect ssb as s",
    "# load s/tables as t",
  ].join("\n");
  const r = DD.resolve(DD.parse(script), REG);
  assertEquals(r[0], { alias: "df", anvil: "helse2025", key: "ask", exec: undefined });
  assertEquals(r[1].viaProxy, false);            // ssb stays a registry source
  if (r[1].anvil) throw new Error("registry-id skal ikke bli anvil-kilde");
});

Deno.test("resolve: load-level key overrides connect-level key", () => {
  const p = DD.parse("# connect helse2025 as h, key(K1)\n# load h as df, key(K2)");
  const r = DD.resolve(p, REG);
  assertEquals(r[0].key, "K2");
});

Deno.test("scrubKeys: literals masked, ask kept", () => {
  const s = "# connect x as h, key(hemmelig123)\n# connect y as k, key(ask)";
  const out = DD.scrubKeys(s);
  if (out.includes("hemmelig123")) throw new Error("nøkkel lekket");
  if (!out.includes("key(***)")) throw new Error("mangler maskering");
  if (!out.includes("key(ask)")) throw new Error("key(ask) skal bevares");
});
```

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/data-directives.test.ts`
Expected: new tests FAIL

- [ ] **Step 2: Implement**

Replace the regexes and add option parsing in `js/data-directives.js`:

```javascript
  var CONNECT_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*connect[ \t]+(\S+)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;
  var LOAD_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*(load|require)[ \t]+(\S+)[ \t]+as[ \t]+([A-Za-z_]\w*)((?:[ \t]*,[ \t]*\w+\([^)]*\))*)[ \t]*$/gim;

  // ", key(<literal>|ask)" og ", exec(local|remote)" — spec §1.
  function parseOptions(tail) {
    var opts = {}, re = /(\w+)\(([^)]*)\)/g, m;
    while ((m = re.exec(tail || '')) !== null) {
      var name = m[1].toLowerCase(), val = m[2].trim();
      if (name === 'key') opts.key = val || 'ask';
      else if (name === 'exec') opts.exec = val.toLowerCase();
    }
    return opts;
  }

  // key(<literal>) -> key(***) før scriptet logges eller sendes til AI.
  // key(ask) er ingen hemmelighet og beholdes.
  function scrubKeys(script) {
    return String(script || '').replace(/\b(key\()\s*(?!ask\s*\))[^)]*\)/gi, '$1***)');
  }
```

In `parse()`: connects push `{ target: target, alias: alias, options: parseOptions(m[3]) }`; loads push `{ verb: verb, target: m[2], alias: m[3], options: parseOptions(m[4]), line: m[0].trim() }` (group numbers shift by the new capture groups — connect: target=1, alias=2, tail=3; load: verb=1, target=2, alias=3, tail=4).

In `resolve()`, replace the unknown-registry-id error with Anvil classification, and thread `key`/`exec` through (load option wins over connect option):

```javascript
  function resolve(parsed, registry) {
    var byAlias = {};
    parsed.connects.forEach(function (c) { byAlias[c.alias] = c; });
    return parsed.loads.map(function (l) {
      var lopts = l.options || {};
      if (isUrlish(l.target)) {
        return { alias: l.alias, url: l.target,
                 viaProxy: l.target.indexOf('/api/hent?') === 0,
                 key: lopts.key, exec: lopts.exec };
      }
      var slash = l.target.indexOf('/');
      var head = slash > 0 ? l.target.slice(0, slash) : l.target;
      var rest = slash > 0 ? l.target.slice(slash + 1) : '';
      var conn = byAlias[head];
      if (!conn) return { alias: l.alias, url: '', viaProxy: false, error: 'ukjent kilde-alias «' + head + '» (mangler connect-linje?)' };
      var copts = conn.options || {};
      var key = lopts.key || copts.key, exec = lopts.exec || copts.exec;
      var base, viaProxy = false;
      if (isUrlish(conn.target)) {
        base = conn.target;
      } else {
        var src = findRegistrySource(registry, conn.target);
        if (!src) {
          // Ikke i web-registeret: en registrert Anvil-kilde (spec §1, regel 3).
          return { alias: l.alias, anvil: conn.target, key: key, exec: exec };
        }
        base = src.base_url;
        viaProxy = !!src.auth || src.cors === false;
      }
      if (rest) {
        if (base.charAt(base.length - 1) !== '/') base += '/';
        base += rest;
      }
      return { alias: l.alias, url: base, viaProxy: viaProxy, key: key, exec: exec };
    });
  }
```

NOTE the `if (rest)` change: `# load h as df` (no path) against a URL/anvil connect must not append a trailing slash. Verify the two pre-existing resolve tests still pass unchanged; if the trailing-slash expectation differs, keep the old behavior for `rest !== ''` exactly.

Export: `global.DataDirectives = { parse: parse, resolve: resolve, scrubKeys: scrubKeys };`

- [ ] **Step 3: Run all directive tests**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/data-directives.test.ts`
Expected: all pass (old + 4 new)

- [ ] **Step 4: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/data-directives.js netlify/edge-functions/_lib/data-directives.test.ts
git commit -m "feat(directives): key()/exec() options, bare-name anvil targets, scrubKeys"
```

---

### Task 8: `data-loader.js` — grants, decryption, `{loads, remote}` (m2py)

**Files:**
- Modify: `m2py/js/data-loader.js`
- Test: `m2py/netlify/edge-functions/_lib/data-loader.test.ts` (extend; read it first and keep existing tests passing)

**Interfaces:**
- Consumes: `DataDirectives.parse/resolve` (Task 7), `EncCrypto` (Task 2), `/source_access` (Task 5)
- Produces: `DataLoader.resolveAndFetchLoads(script, deps) -> Promise<{loads: [{alias, bytes, format}], remote: [{alias, sourceId, key?}]}>`. New deps: `apiBase` (string), `promptKey(alias) -> Promise<string>`. Errors are Norwegian `Error`s.

- [ ] **Step 1: Extend the Deno test (failing)**

The test file evaluates both `data-directives.js` and `data-loader.js` and injects `fetchImpl`. Add (adjusting to the file's existing helper style after reading it):

```typescript
// last inn også enc-crypto for dekrypteringsstien
const encSrc = await Deno.readTextFile(new URL("../../../js/enc-crypto.js", import.meta.url));
(0, eval)(encSrc);
const EC = (globalThis as any).EncCrypto;
const DL = (globalThis as any).DataLoader;

function jsonResp(obj: unknown, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
}

Deno.test("anvil grant: fetch + decrypt with released key (mode 3)", async () => {
  const plain = new TextEncoder().encode("a,b\n1,2\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = (url: string) => {
    if (url.includes("/source_access?id=helse2025"))
      return Promise.resolve(jsonResp({ remote_only: false, location: "https://x.example/d.enc.json",
        payload_format: "csv", fingerprint: envelope.fingerprint, encrypted: true, key }));
    if (url === "https://x.example/d.enc.json")
      return Promise.resolve(jsonResp(envelope));
    throw new Error("uventet URL: " + url);
  };
  const out = await DL.resolveAndFetchLoads("# connect helse2025 as h\n# load h as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.remote, []);
  assertEquals(out.loads[0].format, "csv");
  assertEquals(new TextDecoder().decode(out.loads[0].bytes), "a,b\n1,2\n");
});

Deno.test("anvil remote_only routes to remote list", async () => {
  const fetchImpl = () => Promise.resolve(jsonResp({ remote_only: true, default_exec: "remote" }));
  const out = await DL.resolveAndFetchLoads("# connect kreft as k, key(ask)\n# load k as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.loads, []);
  assertEquals(out.remote, [{ alias: "df", sourceId: "kreft", key: "ask" }]);
});

Deno.test("anvil 404 gives norsk tilgangsfeil", async () => {
  const fetchImpl = () => Promise.resolve(jsonResp({ error: "unknown source: x" }, 404));
  await assertRejects(
    () => DL.resolveAndFetchLoads("# connect ukjent as u\n# load u as df",
      { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" }),
    Error, "mangler tilgang");
});

Deno.test("mode 1: url envelope + key literal decrypts without anvil", async () => {
  const plain = new TextEncoder().encode("x,y\n9,8\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = () => Promise.resolve(jsonResp(envelope));
  const out = await DL.resolveAndFetchLoads(
    `# load https://x.example/d.enc.json as df, key(${key})`,
    { fetchImpl, registry: [] });
  assertEquals(new TextDecoder().decode(out.loads[0].bytes), "x,y\n9,8\n");
});

Deno.test("envelope without key prompts via promptKey(ask)", async () => {
  const plain = new TextEncoder().encode("q\n1\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = () => Promise.resolve(jsonResp(envelope));
  let asked = "";
  const out = await DL.resolveAndFetchLoads(
    "# load https://x.example/d.enc.json as df, key(ask)",
    { fetchImpl, registry: [], promptKey: (alias: string) => { asked = alias; return Promise.resolve(key); } });
  assertEquals(asked, "df");
  assertEquals(new TextDecoder().decode(out.loads[0].bytes), "q\n1\n");
});

Deno.test("grant fingerprint mismatch is refused (byttet fil)", async () => {
  const { envelope, key } = await EC.encryptBytes(new TextEncoder().encode("a\n1\n"), "csv");
  const fetchImpl = (url: string) => {
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: "feilfinger", encrypted: true, key }));
    return Promise.resolve(jsonResp(envelope));
  };
  await assertRejects(
    () => DL.resolveAndFetchLoads("# connect s as s\n# load s as df",
      { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" }),
    Error, "endret siden den ble registrert");
});
```

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/data-loader.test.ts`
Expected: existing tests need the return-shape update too — update the OLD tests in the same file from `result[i]` to `result.loads[i]` as part of this step; new tests FAIL against old code.

- [ ] **Step 2: Implement in `data-loader.js`**

Rework `resolveAndFetchLoads`:

```javascript
  // Hoved-API: {loads: [{alias, bytes, format}], remote: [{alias, sourceId, key}]}
  // Kaster norsk Error ved direktiv-/tilgangs-/nøkkelfeil.
  async function resolveAndFetchLoads(script, deps) {
    deps = deps || {};
    var fetchImpl = deps.fetchImpl || (typeof fetch !== 'undefined' ? fetch.bind(global) : null);
    var DD = global.DataDirectives;
    if (!DD || !fetchImpl) return { loads: [], remote: [] };
    var parsed = DD.parse(script);
    if (!parsed.loads.length) return { loads: [], remote: [] };
    var registry = deps.registry || await loadRegistry(fetchImpl);
    var resolved = DD.resolve(parsed, registry);
    var bad = resolved.filter(function (r) { return r.error; });
    if (bad.length) throw new Error('Direktivfeil: ' + bad.map(function (b) { return b.error; }).join('; '));

    var remote = [];
    var localItems = [];
    for (var i = 0; i < resolved.length; i++) {
      var item = resolved[i];
      if (item.anvil) {
        if (item.exec === 'local') {
          // exec(local) på en anvil-kilde: bare gyldig når grant gir lokal — sjekkes under
        }
        var grant = await fetchSourceAccess(item, deps, fetchImpl);
        if (grant.remote_only) {
          if (item.exec === 'local') throw new Error('«' + item.anvil + '» er ikke offentlig — kan ikke kjøres lokalt (kjøres på server).');
          remote.push({ alias: item.alias, sourceId: item.anvil, key: item.key });
          continue;
        }
        item.url = grant.location;
        item.grant = grant;
        item.viaProxy = false;
      } else if (item.exec === 'remote') {
        throw new Error('exec(remote) krever en registrert kilde (navn), ikke URL: ' + item.alias);
      }
      localItems.push(item);
    }

    var loads = await Promise.all(localItems.map(async function (item) {
      var resp = await fetchLoadTarget(item, fetchImpl, deps.authToken || null, deps.anthropicKey || null);
      var buf = new Uint8Array(await resp.arrayBuffer());
      var format = sniffFormat(resp, item.url);
      var dec = await maybeDecrypt(item, buf, format, deps);
      return { alias: item.alias, bytes: dec.bytes, format: dec.format };
    }));
    return { loads: loads, remote: remote };
  }

  async function fetchSourceAccess(item, deps, fetchImpl) {
    var base = (deps.apiBase || '').replace(/\/+$/, '');
    if (!base) throw new Error('ingen API-base konfigurert for kilden «' + item.anvil + '»');
    var headers = deps.authToken ? { 'Authorization': 'Bearer ' + deps.authToken } : {};
    var r = await fetchImpl(base + '/_/api/source_access?id=' + encodeURIComponent(item.anvil), { headers: headers });
    if (r.status === 404) throw new Error('Fant ikke kilden «' + item.anvil + '» eller du mangler tilgang — logg inn, eller kontakt eieren.');
    if (!r.ok) throw new Error('source_access ' + r.status + ' for «' + item.anvil + '»');
    return r.json();
  }

  // safepy-enc-v1: sniffFormat sier json — sjekk konvolutt, verifiser
  // fingerprint (bytte-vern) og dekrypter lokalt (WebCrypto).
  async function maybeDecrypt(item, buf, format, deps) {
    var EC = global.EncCrypto;
    if (!EC || format !== 'json') return { bytes: buf, format: format };
    var env;
    try { env = JSON.parse(new TextDecoder().decode(buf)); } catch (e) { return { bytes: buf, format: format }; }
    if (!EC.isEnvelope(env)) return { bytes: buf, format: format };
    var computed = await EC.envelopeFingerprint(env);
    if (env.fingerprint && computed !== env.fingerprint)
      throw new Error('«' + item.alias + '»: ødelagt fil (fingerprint stemmer ikke)');
    if (item.grant && item.grant.fingerprint && computed !== item.grant.fingerprint)
      throw new Error('«' + item.alias + '»: filen er endret siden den ble registrert — kontakt eieren');
    var key = (item.key && item.key !== 'ask') ? item.key
            : (item.grant && item.grant.key) ? item.grant.key
            : deps.promptKey ? await deps.promptKey(item.alias)
            : null;
    if (!key) throw new Error('«' + item.alias + '» er kryptert og krever nøkkel — bruk key(...) eller key(ask)');
    var plain = await EC.decryptEnvelope(env, key);
    return { bytes: plain, format: env.payload_format || 'csv' };
  }
```

Keep `loadRegistry`, `proxyHeaders`, `fetchLoadTarget`, `sniffFormat` as they are. Export unchanged name: `global.DataLoader = { resolveAndFetchLoads: resolveAndFetchLoads, _sniffFormat: sniffFormat };`

- [ ] **Step 3: Run loader + directive tests**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/data-loader.test.ts _lib/data-directives.test.ts _lib/enc-crypto.test.ts`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/data-loader.js netlify/edge-functions/_lib/data-loader.test.ts
git commit -m "feat(loader): /source_access grants, local safepy-enc-v1 decrypt, {loads, remote} return shape"
```

---

### Task 9: index.html wiring — modal, call sites, remote routing, AI scrub (m2py)

**Files:**
- Modify: `m2py/index.html` (script tag; key modal; call sites at ~`index.html:8526-8539` and ~`index.html:7375`; `runSafeStatRemote` at `index.html:8003`)
- Modify: `m2py/js/ai-chat.js` (scrub keys where the editor script enters AI prompts)

**Interfaces:**
- Consumes: `DataLoader.resolveAndFetchLoads` V2 (Task 8), `DataDirectives.scrubKeys` (Task 7), `/run_extended` `source_keys` (Task 4)
- Produces: `mdPromptKey(alias) -> Promise<string>` (modal + session cache); `runSafeStatRemote(script, ctx, sources, reason, dialect, sourceKeys)` sends `body.source_keys`.

- [ ] **Step 1: Load `enc-crypto.js`**

Find the existing script includes: `grep -n 'js/data-loader.js' index.html`. Add on the line before it:

```html
    <script src="js/enc-crypto.js"></script>
```

- [ ] **Step 2: Key-prompt modal**

Add near the login modal markup (find with `grep -n 'loginBackdrop' index.html`, place the new backdrop after the login one):

```html
    <div class="modal-backdrop" id="keyPromptBackdrop">
      <div class="modal" role="dialog" aria-modal="true" style="max-width:420px">
        <h3 data-i18n>Dekrypteringsnøkkel</h3>
        <p style="font-size:13px;opacity:.8"><span data-i18n>Kilden</span> «<span id="keyPromptAlias"></span>» <span data-i18n>er kryptert. Lim inn nøkkelen (deles aldri med serveren).</span></p>
        <input type="password" id="keyPromptInput" autocomplete="off" style="width:100%">
        <div style="display:flex;gap:.6rem;justify-content:flex-end;margin-top:.8rem">
          <button id="keyPromptCancel" class="secondary" data-i18n>Avbryt</button>
          <button id="keyPromptOk" data-i18n>Bruk nøkkel</button>
        </div>
      </div>
    </div>
```

Match the exact modal/backdrop class names used by the login modal (inspect that markup and copy its classes so styling works). Add the JS (near `getAuthToken`, `index.html:2927`):

```javascript
    // key(ask): modal passordfelt; nøkkelen caches KUN i minnet for økten.
    var __encKeyCache = {};
    function mdPromptKey(alias) {
      if (__encKeyCache[alias]) return Promise.resolve(__encKeyCache[alias]);
      return new Promise(function (resolve, reject) {
        var bd = document.getElementById('keyPromptBackdrop');
        var input = document.getElementById('keyPromptInput');
        document.getElementById('keyPromptAlias').textContent = alias;
        input.value = '';
        bd.classList.add('open');
        input.focus();
        function done(ok) {
          bd.classList.remove('open');
          okBtn.removeEventListener('click', onOk);
          cancelBtn.removeEventListener('click', onCancel);
          if (!ok) return reject(new Error(t('avbrutt — ingen nøkkel oppgitt for «{alias}»', { alias: alias })));
          var v = input.value.trim();
          input.value = '';
          if (!v) return reject(new Error(t('tom nøkkel for «{alias}»', { alias: alias })));
          __encKeyCache[alias] = v;
          resolve(v);
        }
        var okBtn = document.getElementById('keyPromptOk');
        var cancelBtn = document.getElementById('keyPromptCancel');
        function onOk() { done(true); }
        function onCancel() { done(false); }
        okBtn.addEventListener('click', onOk);
        cancelBtn.addEventListener('click', onCancel);
      });
    }
```

(Adapt `classList.add('open')` to however the login backdrop is shown — reuse its exact mechanism.)

- [ ] **Step 3: `runSafeStatRemote` gains `sourceKeys`**

At `index.html:8003`, change the signature and body:

```javascript
    async function runSafeStatRemote(script, ctx, sources, reason, dialect, sourceKeys) {
```

```javascript
      var body = { script: script, sources: sources, backend: 'pandas', raw: safeStatFormat === 'raw' };
      if (dialect) body.dialect = dialect;
      if (sourceKeys && Object.keys(sourceKeys).length) body.source_keys = sourceKeys;
```

- [ ] **Step 4: Update the python/duckdb call site (`index.html:8526-8539`)**

Replace the block with:

```javascript
        var _pyLoads = [];
        if (activeEditorMode === 'python' || activeEditorMode === 'duckdb') {
          var _dlDeps = { authToken: getAuthToken(), anthropicKey: getAnthropicKey(),
                          apiBase: (window.mdAuth && window.mdAuth.apiBase) ? window.mdAuth.apiBase()
                            : (localStorage.getItem('md_ai_api_base') || 'https://mdataapi.anvil.app'),
                          promptKey: mdPromptKey };
          var _dl = await window.DataLoader.resolveAndFetchLoads(effectiveScript, _dlDeps);
          if (_dl.remote.length) {
            // Ikke-offentlig registrert kilde via connect: hele scriptet kjøres
            // på serveren (spec §4). Nøkler reiser i source_keys, aldri i script.
            var _rSources = [], _rKeys = {};
            for (var _ri = 0; _ri < _dl.remote.length; _ri++) {
              var _r = _dl.remote[_ri];
              _rSources.push({ alias: _r.alias, source_id: _r.sourceId });
              if (_r.key === 'ask') _rKeys[_r.sourceId] = await mdPromptKey(_r.alias);
              else if (_r.key) _rKeys[_r.sourceId] = _r.key;
            }
            var _stripped = effectiveScript.replace(/^[ \t]*(?:#|--|\/\/)[ \t]*(?:connect|load|require)\s+\S+[^\n]*\n?/gim, '');
            await runSafeStatRemote(_stripped, _ctx, _rSources, t('ikke-offentlig kilde'),
              activeEditorMode === 'duckdb' ? 'duckdb' : 'python', _rKeys);
            return;
          }
          var _rawLoads = _dl.loads;
          if (activeEditorMode === 'duckdb') {
            var _htmlLoad = _rawLoads.find(function (l) { return l.format === 'html'; });
            if (_htmlLoad) throw new Error(t('html-kilder støttes ikke i duckdb-modus ({alias}) — bruk python/r', { alias: _htmlLoad.alias }));
          }
          if (_rawLoads.length) py.FS.mkdirTree('/home/pyodide/_webdata');
          _pyLoads = _rawLoads.map(function (l) {
            var _path = '/home/pyodide/_webdata/' + l.alias + '.' + l.format;
            py.FS.writeFile(_path, l.bytes);
            return { alias: l.alias, format: l.format, path: _path };
          });
        }
```

- [ ] **Step 5: Update the R call site (`index.html:7375`)**

```javascript
      var _dlR = await window.DataLoader.resolveAndFetchLoads(src, { authToken: getAuthToken(), anthropicKey: getAnthropicKey(),
        apiBase: (window.mdAuth && window.mdAuth.apiBase) ? window.mdAuth.apiBase()
          : (localStorage.getItem('md_ai_api_base') || 'https://mdataapi.anvil.app'),
        promptKey: mdPromptKey });
      if (_dlR.remote.length) throw new Error(t('ikke-offentlige kilder i R-modus kjøres via require-direktivet (server) — connect/load støtter det ikke her ennå'));
      var _loadsR = _dlR.loads;
```

(Keep the rest of the R flow that consumes `_loadsR` unchanged; check the variable name matches.)

- [ ] **Step 6: Scrub keys before AI prompts**

`grep -n 'editor.getValue\|currentScript\|scriptContent' js/ai-chat.js | head -20` — at each place where the user's script text is embedded into an AI request payload, wrap it:

```javascript
      var scriptForAI = (window.DataDirectives && window.DataDirectives.scrubKeys)
        ? window.DataDirectives.scrubKeys(rawScript) : rawScript;
```

- [ ] **Step 7: Manual smoke test in the browser**

Serve locally (`cd /Users/hom/Documents/GitHub/m2py && python -m http.server 8000`), open `http://localhost:8000/index.html`, Python mode, and run:

```python
#py
# load https://raw.githubusercontent.com/mwaskom/seaborn-data/master/penguins.csv as df
df.head()
```

Expected: still works (regression check of the V2 return shape). Then verify the key modal appears for an encrypted URL (create a test envelope by opening the browser console and calling `EncCrypto.encryptBytes(new TextEncoder().encode('a,b\n1,2\n'),'csv')`, or defer full encrypted-flow verification to Task 12's E2E).

- [ ] **Step 8: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add index.html js/ai-chat.js
git commit -m "feat(app): encrypted-source wiring — key modal, connect remote routing with source_keys, AI key scrub"
```

---

### Task 10: encrypt.html — "Vanlig kryptering (AES)" flow (m2py)

**Files:**
- Modify: `m2py/encrypt.html`

**Interfaces:**
- Consumes: `EncCrypto.encryptBytes` (Task 2)
- Produces: downloadable `<navn>.enc.json`, one-time key display, fingerprint display, hand-off link `deldata.html?fingerprint=<hex>&format=<csv|parquet>&name=<basename>`

- [ ] **Step 1: Add a mode selector and the AES card**

At the top of `<main>` (after the `<h1>`/lead paragraph), add:

```html
  <section class="card">
    <h2>Velg krypteringstype</h2>
    <label><input type="radio" name="encmode" value="he" checked>
      Homomorf (safepy-he-v1) — analyse uten dekryptering, kun aggregater frigis</label><br>
    <label><input type="radio" name="encmode" value="aes">
      Vanlig kryptering (safepy-enc-v1, AES-256-GCM) — hele filen krypteres;
      autoriserte brukere dekrypterer lokalt i nettleseren</label>
  </section>

  <section class="card hide" id="aesCard">
    <h2>Krypter fil (AES)</h2>
    <input type="file" id="aesFile" accept=".csv,.parquet,text/csv">
    <p class="muted" id="aesInfo"></p>
    <div class="actions">
      <button id="aesEncryptBtn" disabled>Krypter</button>
      <span id="aesStatus"></span>
    </div>
    <div class="hide" id="aesResult">
      <p class="warn"><strong>Nøkkelen vises kun én gang.</strong>
        Del den bare med dem som skal lese dataene — eller lagre den hos
        tjenesten ved registrering (da slipper brukerne å taste den).</p>
      <p><strong>Nøkkel:</strong></p><div class="fp" id="aesKeyOut"></div>
      <p><strong>Fingeravtrykk</strong> (registreres hos tjenesten som bytte-vern):</p>
      <div class="fp" id="aesFpOut"></div>
      <div class="actions">
        <a class="download" id="aesDl"><button>Last ned kryptert fil (.enc.json)</button></a>
        <a id="aesRegisterLink"><button class="secondary">Registrer hos tjenesten →</button></a>
      </div>
    </div>
  </section>
```

- [ ] **Step 2: Wire the flow in the module script**

The existing `<script type="module">` at `encrypt.html:149`; add `<script src="js/enc-crypto.js"></script>` BEFORE it, and inside the module script append:

```javascript
// ---- AES-modus (safepy-enc-v1) ----
const EC = window.EncCrypto;
const $$ = (id) => document.getElementById(id);
let aesBytes = null, aesName = "", aesFormat = "csv";

document.querySelectorAll('input[name="encmode"]').forEach((r) =>
  r.addEventListener("change", () => {
    const aes = document.querySelector('input[name="encmode"]:checked').value === "aes";
    $$("aesCard").classList.toggle("hide", !aes);
    // de eksisterende HE-kortene har id configCard/resultCard + første fil-kort
    document.querySelectorAll("main > .card").forEach((c) => {
      if (c.id !== "aesCard" && !c.querySelector('input[name="encmode"]'))
        c.classList.toggle("hide", aes);
    });
  }));

$$("aesFile").addEventListener("change", async (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  aesBytes = new Uint8Array(await f.arrayBuffer());
  aesName = f.name.replace(/\.(csv|parquet)$/i, "");
  aesFormat = /\.parquet$/i.test(f.name) ? "parquet" : "csv";
  $$("aesInfo").textContent = `${f.name} — ${(f.size / 1024).toFixed(1)} kB (${aesFormat})`;
  $$("aesEncryptBtn").disabled = false;
});

$$("aesEncryptBtn").addEventListener("click", async () => {
  $$("aesStatus").textContent = "Krypterer…";
  const { envelope, key } = await EC.encryptBytes(aesBytes, aesFormat);
  const blob = new Blob([JSON.stringify(envelope)], { type: "application/json" });
  $$("aesDl").href = URL.createObjectURL(blob);
  $$("aesDl").download = `${aesName}.enc.json`;
  $$("aesKeyOut").textContent = key;
  $$("aesFpOut").textContent = envelope.fingerprint;
  $$("aesRegisterLink").href = `deldata.html?fingerprint=${envelope.fingerprint}&format=${aesFormat}&name=${encodeURIComponent(aesName)}`;
  $$("aesResult").classList.remove("hide");
  $$("aesStatus").textContent = "Ferdig — filen forlot aldri maskinen.";
});
```

(While implementing: check the actual card ids/classes in `encrypt.html` and adjust the toggle selector so ONLY the HE cards hide; keep it simple and robust.)

- [ ] **Step 3: Manual verification**

Serve locally, open `encrypt.html`, switch to AES, encrypt a small CSV, download, then in the browser console verify round-trip:
`EncCrypto.decryptEnvelope(JSON.parse(<downloaded text>), "<shown key>")` decodes to the original bytes.

- [ ] **Step 4: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add encrypt.html
git commit -m "feat(encrypt): AES safepy-enc-v1 whole-file flow beside HE, with deldata hand-off"
```

---

### Task 11: `deldata.html` — self-service registration page (m2py)

**Files:**
- Create: `m2py/deldata.html`
- Create: `m2py/examples/py30_encrypted_source.txt`

**Interfaces:**
- Consumes: `POST /sources/register`, `GET /sources/mine`, `POST /sources/deactivate` (Task 6); token from `localStorage['mdapi_token']`, base from `localStorage['md_ai_api_base']` (default `https://mdataapi.anvil.app`) — same keys as `js/login.js:6-9`.

- [ ] **Step 1: Create the page**

`m2py/deldata.html` (styling: copy the `<style>` block from `encrypt.html` for visual consistency):

```html
<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Del data — registrer kilde</title>
<!-- kopier <style>-blokken fra encrypt.html hit -->
</head>
<body>
<main>
  <h1>Del data</h1>
  <p class="lead">
    Registrer en datafil du har lagt ut på nett (f.eks. GitHub). Du beholder
    filen selv — tjenesten lagrer bare adressen, fingeravtrykket og hvem som
    skal ha tilgang. Krypter filen først med <a href="encrypt.html">krypteringsverktøyet</a>.
  </p>

  <section class="card" id="loginGate">
    <p>Du må være innlogget for å registrere kilder.
       <a href="index.html">Logg inn i hovedappen</a> og kom tilbake hit.</p>
  </section>

  <section class="card hide" id="regCard">
    <h2>Registrer kilde</h2>
    <div class="row">
      <div><label>Kilde-id (navn i script)</label><input id="fSourceId" placeholder="helse2025"></div>
      <div><label>Visningsnavn</label><input id="fName" placeholder="Helsedata 2025"></div>
    </div>
    <label>URL til filen (kryptert .enc.json, eller vanlig csv/parquet)</label>
    <input id="fLocation" placeholder="https://raw.githubusercontent.com/…/helse.enc.json" style="width:100%">
    <div class="row">
      <div><label>Beskyttelsesnivå</label>
        <select id="fLevel">
          <option value="public">public — kan analyseres lokalt hos autoriserte brukere</option>
          <option value="protected">protected — kun server-kjøring, undertrykte resultater</option>
          <option value="sensitive">sensitive — som protected + input-vern</option>
        </select></div>
      <div><label>Format (for ukrypterte filer)</label>
        <select id="fFormat"><option value="csv">csv</option><option value="parquet">parquet</option></select></div>
    </div>
    <label>Hvem får tilgang? E-poster (kommaseparert)</label>
    <input id="fEmails" placeholder="ana@fhi.no, per@uio.no" style="width:100%">
    <label>…og/eller e-postdomener</label>
    <input id="fDomains" placeholder="fhi.no, uio.no" style="width:100%">
    <label>Dekrypteringsnøkkel (valgfritt)</label>
    <input id="fKey" type="password" autocomplete="off" style="width:100%">
    <label><input type="checkbox" id="fStoreKey">
      Lagre nøkkelen hos tjenesten (autoriserte brukere slipper å taste den).
      Uten lagring må brukerne få nøkkelen av deg og bruke key(...) i scriptet.</label>
    <div class="actions">
      <button id="registerBtn">Registrer</button>
      <span id="regStatus"></span>
    </div>
  </section>

  <section class="card hide" id="mineCard">
    <h2>Mine kilder</h2>
    <div id="mineList"></div>
  </section>
</main>

<script>
(function () {
  var API = (localStorage.getItem('md_ai_api_base') || 'https://mdataapi.anvil.app').replace(/\/+$/, '');
  var TOKEN = localStorage.getItem('mdapi_token') || '';
  var $ = function (id) { return document.getElementById(id); };
  function hdrs(json) {
    var h = { 'Authorization': 'Bearer ' + TOKEN };
    if (json) h['Content-Type'] = 'application/json';
    return h;
  }
  function splitList(s) {
    return (s || '').split(',').map(function (x) { return x.trim(); }).filter(Boolean);
  }

  // querystring-prefill fra encrypt.html
  var qs = new URLSearchParams(location.search);
  if (qs.get('name')) { $('fSourceId').value = qs.get('name').toLowerCase().replace(/[^a-z0-9_-]/g, '_'); $('fName').value = qs.get('name'); }
  if (qs.get('format')) $('fFormat').value = qs.get('format');

  async function refreshMine() {
    var r = await fetch(API + '/_/api/sources/mine', { headers: hdrs(false) });
    if (!r.ok) return;
    var data = await r.json();
    var html = (data.sources || []).map(function (s) {
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:.4rem 0;border-bottom:1px solid #eee">'
        + '<span><strong>' + s.source_id + '</strong> · ' + s.level + ' · ' + s.kind
        + (s.has_key ? ' · nøkkel lagret' : '') + '</span>'
        + '<button class="secondary" data-sid="' + s.source_id + '">Deaktiver</button></div>';
    }).join('') || '<p class="muted">Ingen registrerte kilder ennå.</p>';
    $('mineList').innerHTML = html;
    $('mineList').querySelectorAll('button[data-sid]').forEach(function (b) {
      b.addEventListener('click', async function () {
        await fetch(API + '/_/api/sources/deactivate', { method: 'POST', headers: hdrs(true),
          body: JSON.stringify({ source_id: b.getAttribute('data-sid') }) });
        refreshMine();
      });
    });
    $('mineCard').classList.remove('hide');
  }

  async function init() {
    if (!TOKEN) return;                       // loginGate blir stående
    var me = await fetch(API + '/_/api/auth/me', { headers: hdrs(false) });
    if (!me.ok) return;
    $('loginGate').classList.add('hide');
    $('regCard').classList.remove('hide');
    refreshMine();
  }

  $('registerBtn').addEventListener('click', async function () {
    $('regStatus').textContent = 'Registrerer…';
    var body = {
      source_id: $('fSourceId').value.trim(),
      name: $('fName').value.trim(),
      location: $('fLocation').value.trim(),
      level: $('fLevel').value,
      format: $('fFormat').value,
      emails: splitList($('fEmails').value),
      domains: splitList($('fDomains').value),
      key: $('fKey').value.trim() || null,
      store_key: $('fStoreKey').checked,
    };
    var r = await fetch(API + '/_/api/sources/register', { method: 'POST', headers: hdrs(true), body: JSON.stringify(body) });
    var data = await r.json().catch(function () { return {}; });
    if (!r.ok || data.error) { $('regStatus').textContent = 'Feil: ' + (data.error || r.status); return; }
    $('fKey').value = '';
    $('regStatus').textContent = 'Registrert som «' + data.source_id + '» (' + data.kind + '). '
      + 'Bruk i script: # connect ' + data.source_id + ' as kilde';
    refreshMine();
  });

  init();
})();
</script>
</body>
</html>
```

- [ ] **Step 2: Example script**

`m2py/examples/py30_encrypted_source.txt`:

```
#py
# Kryptert kilde på nett (safepy-enc-v1) — tre måter:
#
# 1) Nøkkel i scriptet (enkelt, minst sikkert):
# load https://raw.githubusercontent.com/<bruker>/<repo>/main/helse.enc.json as df, key(LIM-INN-NØKKEL)
#
# 2) Nøkkel via ledetekst (nøkkelen havner aldri i scriptet):
# connect https://raw.githubusercontent.com/<bruker>/<repo>/main/helse.enc.json as h, key(ask)
# load h as df
#
# 3) Registrert kilde (eieren har delt tilgang med deg — logg inn først):
# connect helse2025 as h
# load h as df

df.head()
```

- [ ] **Step 3: Manual verification + commit**

Serve locally, open `deldata.html` — logged-out gate shows. (Full logged-in flow is Task 12.)

```bash
cd /Users/hom/Documents/GitHub/m2py
git add deldata.html examples/py30_encrypted_source.txt
git commit -m "feat(deldata): self-service source registration page + example script"
```

---

### Task 12: End-to-end verification + push

**Files:** none new — verification and deploy.

- [ ] **Step 1: Full test suites, all three repos**

```bash
cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/ -x -q
cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/ -x -q
cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/
```
Expected: all pass.

- [ ] **Step 2: E2E demo (spec §7) — requires deployed server or local Anvil**

1. `encrypt.html`: encrypt a sample CSV (AES flow), download `.enc.json`, note key + fingerprint.
2. Push the `.enc.json` to a public GitHub repo (or any URL).
3. `deldata.html` (logged in): register it — `level=public`, your own email in the allowlist, once WITHOUT storing the key (mode 2) and once WITH (mode 3, different source_id).
4. `index.html`, Python mode, run mode-1 (`# load <url> as df, key(<key>)`), mode-3 (`# connect <id3> as h` — no key anywhere), and mode-2 (`# connect <id2> as k, key(ask)` — prompt appears) scripts. All should show `df.head()` output.
5. Re-register one source as `level=protected`, rerun: the run goes remote, results come back suppressed.
6. Negative: log in as a non-allowlisted user (or remove your email) → clear "mangler tilgang" error.
7. Tamper test: edit one character of the ciphertext on GitHub → "endret siden den ble registrert".

- [ ] **Step 3: Anvil schema note**

Anvil creates `enc_key`/`access_policy` columns on first write, but confirm in the Anvil editor after deploy that the `sources` table shows them (and add to `anvil.yaml` on next schema sync). Document in the commit message if a manual step was needed.

- [ ] **Step 4: Push everything**

```bash
cd /Users/hom/Documents/GitHub/safepy && git push origin dev
cd /Users/hom/Documents/GitHub/microdata-api && git push origin dev
cd /Users/hom/Documents/GitHub/m2py && git push origin dev
```

---

## Self-Review Notes

- **Spec coverage:** §1 grammar → Tasks 7–9; §2 format/tooling → Tasks 1, 2, 10; §3 registration/policy/`/source_access` → Tasks 5, 6, 11; §4 browser flow → Tasks 8, 9; §5 remote parity + scrubbing → Tasks 3, 4; §6 error handling → embedded in Tasks 3–9 error strings; §7 testing → per-task tests + Task 12; §8 deferred items → not implemented (correct).
- **Known simplifications vs spec:** R-mode remote routing via connect errors with a pointer to `require` (spec's remote parity is fully served by python/duckdb modes + `require` in all modes); editor "gentle hint" for `key()` on GitHub save is deferred to a follow-up (scrubbing in AI prompts and audit logs IS implemented).
- **Type consistency check:** `source_keys` = `{source_id: key}` everywhere (loader → `runSafeStatRemote` → `/run_extended` → `bg_run_extended` → `safepy_shim` → `src["_run_key"]`); grant payload field names (`remote_only`, `location`, `payload_format`, `fingerprint`, `encrypted`, `key`) match between `source_access.py`, its tests, and `data-loader.js`.
