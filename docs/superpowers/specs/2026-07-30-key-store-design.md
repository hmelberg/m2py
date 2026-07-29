# Central key store with per-key policies — design

**Date:** 2026-07-30
**Status:** Approved (design). Not yet implemented.
**Scope decision:** Full three-policy model in v1 (open/locked/secret); one master
password; unlocked state lives in JS memory only (reload = re-prompt). Built in
safestat first, ported to openstat afterwards.

## 1. Problem

SafeStat has no central place for keys. The Anthropic key sits alone in the legacy
`md_anthropic_key` localStorage slot; dataset decryption keys (safepy-enc-v1) must be
typed into scripts (`key(<literal>)`) or re-entered via the prompt dialog every
session; future API-keyed sources (FRED-style, cf. openstat) have nowhere to live.
openstat solved the *storage* part in 2026-07-23 (`js/keys.js`, plaintext `md_keys`,
accepted risk) — but safestat's audience is health data on shared office machines,
where **at-rest protection matters**: a plaintext localStorage entry is readable by
anyone with access to the browser profile, disk backups, or browser sync.

The user-facing goals:

1. One place to manage keys — a **«Nøkler…»** entry in the hamburger menu.
2. Scripts reference keys **by name** (`key(minfred)`), never by value — shareable
   scripts contain no secrets.
3. Optional encryption at rest with **one master password** (better one shared
   password than remembering every key).
4. Keys marked **secret** require the password on *every run* that uses them.

## 2. Decision log

- **Three policies, one mechanism** (Hans 2026-07-30). Each entry has a policy:
  `open` (plaintext, no friction — the openstat default), `locked` (encrypted,
  password once per session), `secret` (encrypted, password on every use, never
  cached). "Encrypt everything" is not a separate system: it is a default-policy
  setting plus a bulk action.
- **Unlock lifetime = the tab** (Hans 2026-07-30). The derived master key lives in
  a JS closure only — never sessionStorage. Reload asks again. Auto-lock timers
  rejected for v1 (YAGNI).
- **One master password** for both `locked` and `secret`. Set lazily — first time a
  key is given a non-open policy.
- **PBKDF2-SHA-256 (600k iterations), not Argon2** — WebCrypto has PBKDF2 natively;
  Argon2 would add a WASM dependency for marginal gain at this threat level.
- **Forgotten password = encrypted entries are gone; re-enter the keys.** Acceptable
  because keys, unlike data, can be re-issued. The UI must say this explicitly.
- **Honest threat model** (do not oversell): encryption protects *at rest* — shared
  machines, disk/backup/sync exposure. It does **not** protect against code running
  in the page while a key is decrypted: main-thread Pyodide reaches everything via
  `import js`. `secret` narrows the exposure window to the run itself; the actual
  guarantee for sensitive sources remains the **strict profile, which is untouched**
  (stored/prompted keys are never used there — V3 grants/V4 in-run decryption only).
  Note the escalation: because the password modal is in-page DOM, hostile in-page
  code can also *spoof or keylog the prompt itself* — one hostile run during an
  unlock can expose the master password and hence every encrypted key. This is
  inherent to any in-page dialog and is the strongest argument for the WebAuthn
  PRF roadmap item (browser-native, unspoofable credential UI).
- **Server-side vault stays rejected** — openstat spec 2026-07-23 Decision log
  showed a vault with a read-back endpoint is security-equivalent to localStorage
  under main-thread Pyodide. Not reopened.
- **WebAuthn/passkey PRF unlock**: out of scope for v1, but the unlock path is a
  single function (`password → master key`), so a hardware-backed method can slot in
  later without format changes.
- **safestat first, openstat port after** (UI principle: safestat leads). openstat's
  existing flat `md_keys` migrates to the v2 format with `policy: "open"`; its
  registry-driven `sourceKeyHeader` keeps working unchanged for open/unlocked keys.

## 3. Design

### 3.1 Store format — `js/keys.js` (new module)

One localStorage entry `md_keys` (same name as openstat, so the future sync is a
format migration, not a new slot):

```json
{
  "v": 2,
  "kdf": { "alg": "PBKDF2-SHA-256", "iters": 600000, "salt": "<b64>" },
  "verifier": { "iv": "<b64>", "ct": "<b64>" },
  "entries": {
    "fred":      { "policy": "open",   "value": "abc123…", "created": "2026-07-30" },
    "helse2026": { "policy": "secret", "iv": "<b64>", "ct": "<b64>", "created": "2026-07-30" }
  }
}
```

- `open` entries store `value` in plaintext; `locked`/`secret` entries store a
  per-entry AES-256-GCM envelope (`iv` + `ct`), all under the same derived key.
- `kdf` + `verifier` are absent until the first non-open key exists (no password
  ceremony before it is needed). The verifier is the fixed string
  `"safestat-keys-verifier"` encrypted under the master key — it distinguishes
  *wrong password* from *corrupt store*.
- Entry names: `[a-zA-Z0-9_-]{1,32}`, i.e. short human words — syntactically
  disjoint from real key material (43-char base64url dataset keys, long API keys),
  which keeps name-vs-literal resolution (§3.3) unambiguous in practice.
  The name `ask` is **reserved** (it collides with the `key(ask)` prompt syntax
  and would be silently shadowed by it).
- Migrations on first load: `md_anthropic_key` → `entries.anthropic` (`open`,
  legacy slot removed); an openstat-style flat `md_keys` object (no `v` field) →
  same treatment per key.

### 3.2 API — `window.Keys`

| Call | Behavior |
|---|---|
| `Keys.get(name)` | Sync. Plaintext for `open` entries and for `locked` entries already unlocked this session (decrypted cache in the closure). `null` for anything still locked and for all `secret` entries. Signature-compatible with openstat. |
| `await Keys.resolve(name, ctx)` | Async. `open` → value; `locked` → unlock store via password modal if needed, then value; `secret` → prompt, decrypt transiently, return value **without caching**. `ctx` (e.g. dataset alias) is shown in the prompt so the user knows what they are authorizing. |
| `Keys.set(name, value, policy)` | Create/update. Non-open policies require the store to be unlocked (or trigger first-time password setup). |
| `Keys.setPolicy(name, policy)` | Re-encrypt/decrypt one entry between policies. |
| `Keys.remove(name)` / `Keys.registered()` | As in openstat (`registered()` returns names + policies). |
| `Keys.changePassword(oldPw, newPw)` | Decrypt all envelopes with old, re-encrypt with new. |
| `Keys.lockNow()` | Drop derived key + decrypted cache. |
| `Keys.attachPrompt(fn)` | Dependency injection: `index.html` registers the password-modal function; the module itself stays UI-free and Deno-testable (same pattern as `enc-crypto.js`). |

Crypto lives in the same module (WebCrypto only, no dependencies), structured to run
under Deno-eval in tests like `enc-crypto.js`.

### 3.3 Script and runtime integration

- **`key(<navn>)` name lookup.** In `maybeDecrypt`/data-loader, resolution order for
  a non-strict source becomes: `key(ask)` → prompt (as today); value exactly matches
  a stored entry name → `await Keys.resolve(name, alias)`; otherwise → literal key
  (as today). No new syntax.
- **`secret` keys never enter `__encKeyCache`** (the per-session prompt cache for
  dataset keys). `locked`/`open` values may cache as today.
- **Strict profile: no change.** The strict branch never consults `Keys` — grants
  and explicit literals only, exactly as now (data-loader `maybeDecrypt`).
- **`scrubKeys` masking:** a `key(<literal>)` whose literal exactly matches a stored
  entry name is a *reference*, not a secret — left unmasked so shared/AI-visible
  scripts keep working. Everything else masks to `key(***)` as today.
- **Anthropic key:** `getAnthropicKey()` switches to the store (migration in §3.1).
  Call paths that are already async use `await Keys.resolve('anthropic')`; any
  remaining sync path uses `Keys.get` and, when the store is locked, fails with a
  clear message pointing to «Nøkler…» in the menu (unlock once, then it works).

### 3.4 UI — «Nøkler…» in the hamburger menu

New menu item `menuKeys` (grouped with Innstillinger), opening a dedicated modal:

- **Key list:** name, masked value (`••••` + last 4 chars for open/unlocked), policy
  dropdown (`åpen` / `låst` / `hemmelig`), delete button. Changing policy calls
  `Keys.setPolicy` (may trigger password setup/unlock).
- **Add key:** name, value, policy (default from the setting below).
- **Master password section:** set/change password; «Lås nå» (when unlocked);
  «Glemt passord?» → after an explicit double confirm, deletes all encrypted entries
  and resets `kdf`/`verifier` (open entries survive).
- **Defaults:** «standardpolicy for nye nøkler» selector + bulk action
  «krypter alle åpne nøkler» (sets all `open` → `locked`).
- **Password prompt modal** (shared by session unlock and per-run `secret` prompts):
  shows *which key* and *for what* (dataset alias / API call), registered via
  `Keys.attachPrompt`. Reuses the existing `keyPromptBackdrop` styling.
- The AI modal's Anthropic field stays but reads/writes through `Keys`
  (policy preserved on edit).
- All strings via i18n (`data-i18n`), Norwegian + English.

### 3.5 Testing

Deno tests (pattern: `tests/js/encfile-roundtrip.test.js`):

- KDF + envelope roundtrip; wrong password → verifier error, not garbage.
- Policy behavior: `get` returns null for locked/secret; `resolve` prompts (fake
  prompt fn); `secret` re-prompts on every call and never caches.
- Migrations: `md_anthropic_key` and flat openstat `md_keys` → v2.
- `scrubKeys`: name references unmasked, literals masked.
- data-loader: `key(<navn>)` resolves via store; `secret` bypasses `__encKeyCache`;
  strict path never touches `Keys`.

## 4. Out of scope / roadmap

- WebAuthn/passkey PRF unlock (design leaves the unlock function pluggable).
- Auto-lock after N minutes of inactivity.
- Encrypted export/import of the store (keys are per-browser and die with
  site-data clearing; today the answer is "re-enter them").
- Server-side vault (rejected — see Decision log).
- openstat port: extend existing `js/keys.js` to v2 format + named lookup for
  `secret_key="<navn>"` in the pythonic syntax; registry-driven keys keep using
  `Keys.get(src.id)` (locked entries there require a session unlock first).
- Pythonic directive syntax in safestat (separate track; name lookup carries over).
