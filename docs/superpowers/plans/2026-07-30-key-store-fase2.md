# Key Store Phase 2 (Account Sync) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zero-knowledge sync of the `md_keys` document to the Anvil backend for logged-in users, per spec `docs/superpowers/specs/2026-07-30-key-store-design.md` §3.5.

**Architecture:** Server side (repo `~/Documents/GitHub/microdata-api`): a `keystores` Data Table + `server_code/keystore.py` with GET/POST `/keystore` endpoints (pure validation logic testable without Anvil, endpoints behind the `_ANVIL` guard — the repo's standard pattern). Client side (repo `safestat`): `keys.js` stamps `doc.updated` and exposes `onChange`/`rawDoc`/`updatedAt`/`replaceDoc`; new `js/keys-sync.js` does newest-wins sync on app start, after login (one-line hook in `login.js`), and debounced after every mutation; keys modal gets a sync-status line and honest help text.

**Tech Stack:** Anvil server modules (Python, pytest), vanilla JS IIFE + node:test/vm.

## Global Constraints

- Zero-knowledge: server stores the document AS-IS; master password never leaves the client (spec §2/§3.5).
- Newest-wins on `doc.updated` — ISO-8601 UTC strings compared lexicographically; the CLIENT decides, the server only stores (avoids server-side datetime parsing).
- Endpoints use POST (not PUT) for writes — every existing endpoint in microdata-api is GET/POST; avoids CORS-preflight uncertainty for PUT.
- `replaceDoc` must NOT fire `onChange` (server-originated change → push loop) and must `lockNow()` (session cache may belong to the old document).
- Size cap 64 kB on the stored document.
- Anvil deploy requires Hans's manual pull — server changes are pushed to the microdata-api repo and wait there.
- Commit per task; push both repos at the end (Hans pulls Anvil afterwards).

---

### Task 1 (microdata-api): `keystores` table + `keystore.py` + tests

**Files:**
- Modify: `anvil.yaml` (add `keystores` to `db_schema`, after the `files:` table)
- Create: `server_code/keystore.py`
- Create: `tests/test_keystore.py`

**Interfaces:**
- Produces: `GET /_/api/keystore` → `{"doc": str|null, "updated": str|null}`; `POST /_/api/keystore` body `{"doc": "<md_keys-json>"}` → `{"ok": true, "updated": str}` (400 on invalid doc, 401/403 without logged-in user). Pure fn `keystore.validate_doc(raw) -> updated_str` raises `ValueError` (Norwegian messages).

- [ ] **Step 1:** Add to `anvil.yaml` `db_schema` (same shape as `auth_tokens`):

```yaml
  keystores:
    client: none
    columns:
    - admin_ui: {}
      client_hidden: null
      name: email
      type: string
    - admin_ui: {}
      client_hidden: null
      name: doc
      type: string
    - admin_ui: {}
      client_hidden: null
      name: updated
      type: string
    indexes: []
    server: full
    title: keystores
```

- [ ] **Step 2:** Write failing tests `tests/test_keystore.py` (repo pattern: pure logic, no Anvil):

```python
"""Ren validering for kontosynk av nøkkellageret (safestat key store fase 2)."""
import json

import pytest

import keystore


def _doc(**kw):
    base = {"v": 2, "entries": {"fred": {"policy": "open", "value": "x"}},
            "updated": "2026-07-30T10:00:00.000Z"}
    base.update(kw)
    return json.dumps(base)


def test_valid_doc_returns_updated():
    assert keystore.validate_doc(_doc()) == "2026-07-30T10:00:00.000Z"


def test_rejects_non_json():
    with pytest.raises(ValueError, match="gyldig JSON"):
        keystore.validate_doc("{ikke json")


def test_rejects_wrong_version_and_shape():
    with pytest.raises(ValueError, match="v2"):
        keystore.validate_doc(json.dumps({"v": 1, "entries": {}, "updated": "x"}))
    with pytest.raises(ValueError, match="v2"):
        keystore.validate_doc(json.dumps(["liste"]))


def test_rejects_missing_entries_or_updated():
    with pytest.raises(ValueError, match="entries"):
        keystore.validate_doc(json.dumps({"v": 2, "updated": "x"}))
    with pytest.raises(ValueError, match="updated"):
        keystore.validate_doc(json.dumps({"v": 2, "entries": {}}))


def test_rejects_oversized_doc():
    big = _doc(entries={"a": {"policy": "open", "value": "x" * 70000}})
    with pytest.raises(ValueError, match="for stort"):
        keystore.validate_doc(big)


def test_rejects_empty():
    with pytest.raises(ValueError, match="mangler"):
        keystore.validate_doc("")
```

Run: `cd ~/Documents/GitHub/microdata-api && python3 -m pytest tests/test_keystore.py -q` — expect import error.

- [ ] **Step 3:** Create `server_code/keystore.py`:

```python
"""Kontosynk av nøkkellageret (safestat key store fase 2; spec §3.5 i
safestat-repoets docs/superpowers/specs/2026-07-30-key-store-design.md).

Zero-knowledge: serveren lagrer md_keys-dokumentet AS-IS. locked/secret-poster
er AES-GCM-ciphertext under brukerens hovedpassord, som aldri forlater
klienten; kun open-poster er lesbare her. Newest-wins på `updated` gjøres av
KLIENTEN (ISO-strenger sammenlignes leksikografisk) — serveren lagrer bare.

  GET  /keystore                    → {"doc": str|null, "updated": str|null}
  POST /keystore  {"doc": "<json>"} → {"ok": true, "updated": str}
"""

from __future__ import annotations

import json

MAX_DOC_BYTES = 65536


def validate_doc(raw) -> str:
    """Valider klientens md_keys-dokument; returner `updated` (ISO-streng).
    Kaster ValueError med norsk melding ved ugyldig dokument."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("doc mangler")
    if len(raw.encode("utf-8")) > MAX_DOC_BYTES:
        raise ValueError(f"dokumentet er for stort (maks {MAX_DOC_BYTES // 1024} kB)")
    try:
        doc = json.loads(raw)
    except Exception:
        raise ValueError("doc er ikke gyldig JSON")
    if not isinstance(doc, dict) or doc.get("v") != 2:
        raise ValueError("doc må være md_keys v2")
    if not isinstance(doc.get("entries"), dict):
        raise ValueError("doc mangler entries")
    updated = doc.get("updated")
    if not isinstance(updated, str) or not updated:
        raise ValueError("doc mangler updated-tidsstempel")
    return updated


# ---------------------------------------------------------------------------
# HTTP endpoints (Anvil). Kept below the pure logic so tests never import anvil.

try:
    import anvil.server
    from anvil.tables import app_tables
    import auth
    import http_utils
    _ANVIL = True
except Exception:            # ren testkjøring
    _ANVIL = False


if _ANVIL:
    _json = http_utils.json_response
    _load_body = http_utils.load_body

    def _require_user():
        principal, err = auth.authenticate_or_fail()
        if err:
            return None, err
        user = auth.principal_user(principal)
        if user is None:
            return None, _json({"error": "krever innlogget bruker"}, status=403)
        return user, None

    @anvil.server.http_endpoint("/keystore", methods=["GET"],
                                cross_site_session=False, enable_cors=True)
    def http_keystore_get():
        user, err = _require_user()
        if err:
            return err
        row = app_tables.keystores.get(email=user["email"])
        if row is None:
            return _json({"doc": None, "updated": None})
        return _json({"doc": row["doc"], "updated": row["updated"]})

    @anvil.server.http_endpoint("/keystore", methods=["POST", "PUT"],
                                cross_site_session=False, enable_cors=True)
    def http_keystore_put():
        user, err = _require_user()
        if err:
            return err
        body = _load_body()
        try:
            updated = validate_doc(body.get("doc"))
        except ValueError as exc:
            return _json({"error": str(exc)}, status=400)
        row = app_tables.keystores.get(email=user["email"])
        if row is None:
            app_tables.keystores.add_row(email=user["email"],
                                         doc=body["doc"], updated=updated)
        else:
            row.update(doc=body["doc"], updated=updated)
        return _json({"ok": True, "updated": updated})
```

- [ ] **Step 4:** `python3 -m pytest tests/test_keystore.py -q` → 6 passed; run the full suite `python3 -m pytest tests/ -q` → all pass.
- [ ] **Step 5:** Commit in microdata-api: `feat(keystore): account-synced key store endpoints (safestat fase 2)`.

---

### Task 2 (safestat): `keys.js` — updated-stamp, onChange, rawDoc/updatedAt/replaceDoc

**Files:**
- Modify: `js/keys.js`
- Modify: `tests/js/keys.test.js` (append)

**Interfaces:**
- Produces: every mutation (any `writeDoc`) stamps `doc.updated = new Date().toISOString()` and fires `onChange`-listeners. `Keys.onChange(fn)`, `Keys.rawDoc() → string|null`, `Keys.updatedAt() → string|null`, `Keys.replaceDoc(rawJson)` (validates v2, writes verbatim, `lockNow()`, does NOT fire onChange, throws `ugyldig nøkkeldokument`).

- [ ] **Step 1:** Append failing tests:

```js
test('sync-flater: updated stemples, onChange fyrer ved mutasjon', async () => {
  const ls = makeLocalStorage();
  const K = loadKeys(ls);
  let fired = 0;
  K.onChange(() => { fired++; });
  assert.equal(K.updatedAt(), null);
  await K.set('a', 'x');
  const u1 = K.updatedAt();
  assert.ok(u1 && fired === 1);
  K.remove('a');
  assert.ok(fired === 2);
  assert.ok(K.updatedAt() >= u1);
  K.get('a');                                          // lesing fyrer ikke
  assert.equal(fired, 2);
});

test('replaceDoc: erstatter verbatim, låser, fyrer IKKE onChange', async () => {
  const ls = makeLocalStorage();
  const K = loadKeys(ls, promptStub('pw'));
  await K.set('l', 'L', 'locked');
  assert.equal(K.get('l'), 'L');                       // opplåst økt
  let fired = 0;
  K.onChange(() => { fired++; });
  const remote = JSON.stringify({ v: 2, entries: { b: { policy: 'open', value: 'y' } }, updated: '9999-01-01T00:00:00.000Z' });
  K.replaceDoc(remote);
  assert.equal(fired, 0);
  assert.equal(K.rawDoc(), remote);                    // byte-likt
  assert.equal(K.get('b'), 'y');
  assert.equal(K.status().unlocked, false);            // lockNow kjørte
  assert.throws(() => K.replaceDoc('{ikke json'), /ugyldig nøkkeldokument/);
  assert.throws(() => K.replaceDoc(JSON.stringify({ v: 1 })), /ugyldig nøkkeldokument/);
});
```

- [ ] **Step 2:** In `keys.js`: add `var _listeners = [];` next to the other module state; change `writeDoc` to stamp+notify; add the four functions; extend the export.

```js
  function writeDoc(doc) {
    doc.updated = new Date().toISOString();
    global.localStorage.setItem(LS, JSON.stringify(doc));
    for (var i = 0; i < _listeners.length; i++) {
      try { _listeners[i](); } catch (e) {}
    }
  }
```

```js
  // -- kontosynk-flater (fase 2, spec §3.5) -------------------------------
  function onChange(fn) { _listeners.push(fn); }
  function rawDoc() { return global.localStorage.getItem(LS); }
  function updatedAt() { return readDoc().updated || null; }
  // Erstatt hele dokumentet med serverens versjon. Fyrer IKKE onChange
  // (endringen KOM fra serveren — ellers push-løkke) og låser lageret:
  // økt-cachen kan stamme fra det gamle dokumentet.
  function replaceDoc(raw) {
    var doc = null;
    try { doc = JSON.parse(raw); } catch (e) {}
    if (!doc || doc.v !== 2 || typeof doc.entries !== 'object' || !doc.entries)
      throw new Error('ugyldig nøkkeldokument');
    global.localStorage.setItem(LS, raw);
    lockNow();
  }
```

- [ ] **Step 3:** `node --test tests/js/keys.test.js` → 19 pass. Commit: `feat(keys): sync surfaces — updated stamp, onChange, replaceDoc`.

---

### Task 3 (safestat): `js/keys-sync.js` + login hook + tests

**Files:**
- Create: `js/keys-sync.js`
- Modify: `index.html` (script tag after `js/keys.js`)
- Modify: `js/login.js` (`persistLogin`: `if (window.KeysSync) window.KeysSync.syncNow();`)
- Create: `tests/js/keys-sync.test.js`

**Interfaces:**
- Consumes: `Keys.onChange/rawDoc/updatedAt/replaceDoc`, `mdAuth.token/isLoggedIn/apiBase`.
- Produces: `window.KeysSync` with `syncNow() → Promise<'off'|'pulled'|'pushed'|'uptodate'|'error'>`, `pushNow()`, `status() → {active, last}`, `active()`, `_configure(deps, debounceMs)` (test injection). Auto: syncs on DOMContentLoaded, pushes debounced (1500 ms) on every Keys-mutation.

- [ ] **Step 1:** Failing tests `tests/js/keys-sync.test.js` — vm sandbox loading `keys.js` + `keys-sync.js`, fake fetch/auth via `_configure`; cases: (a) logged out → `'off'`, zero fetches; (b) remote newer → `'pulled'` + doc replaced; (c) local newer/remote empty → `'pushed'` + POST body contains local doc; (d) mutation → debounced POST (debounce 10 ms); (e) `replaceDoc` triggers no POST.
- [ ] **Step 2:** Implement `js/keys-sync.js` (deps read lazily so `_configure` wins; `document`-guard for vm), add script tag + login hook.
- [ ] **Step 3:** `node --test tests/js/*.test.js` all green. Commit: `feat(keys): account sync of the key store (newest-wins, zero-knowledge)`.

---

### Task 4 (safestat): UI — sync status + honest help text

**Files:**
- Modify: `index.html` (keys modal: new `keysSyncStatus` line; replace the help text)
- Modify: `js/keys-ui.js` (`refresh()` sets sync status)
- Modify: `js/i18n/en.js` (replace old help entry, add new strings)

- [ ] **Step 1:** Replace modal help text with: «Nøkler lagres i denne nettleseren og synces til kontoen din når du er logget inn. Låste/hemmelige nøkler er kryptert også på serveren; åpne nøkler kan leses der — sett dem til låst om det betyr noe. Policy: åpen = klartekst; låst = passord én gang per økt; hemmelig = passord ved hver kjøring. I script refererer key(navn) til nøkkelen uten å avsløre den.» Add `<div class="ai-modal-help" id="keysSyncStatus" style="margin-bottom:6px;"></div>` below it.
- [ ] **Step 2:** In `refresh()`: set `keysSyncStatus` to «Synces til konto» when `KeysSync.active()`, else «Kun lokalt (logg inn for synk)».
- [ ] **Step 3:** Update `en.js` (remove the stale help key, add the new ones). Run suite; commit: `feat(keys): sync status line + honest storage text in keys modal`.

---

### Task 5: Verification + docs + push

- [ ] Full JS suite + microdata-api pytest suite.
- [ ] Browser smoke (logged out): keys modal shows «Kun lokalt …»; no `/keystore` requests fire; store works as before.
- [ ] Update spec §3.5 status + Status header (phase 2 implemented client+server, awaiting Anvil pull); update memory file.
- [ ] Push safestat and microdata-api. Report that the endpoint goes live when Hans pulls in Anvil, and how to verify after pull (log in → add key → check keystores table / second browser).

## Self-review notes

- POST instead of PUT is a deliberate deviation from spec §3.5's «GET/PUT» — documented in Global Constraints (CORS/preflight consistency with the rest of the API); endpoint accepts PUT too.
- `replaceDoc` verbatim-write keeps the server copy byte-identical (fingerprint-friendly); `updated` comparison is string-based, no clock parsing anywhere.
- Migration writeDoc at module load fires onChange before any listener exists → harmless; sync boot happens later and does a full `syncNow`.
