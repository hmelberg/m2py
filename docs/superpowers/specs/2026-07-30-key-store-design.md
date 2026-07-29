# Central key store with per-key policies — design

**Date:** 2026-07-30 (revised same day after review: run-scoped secret prompt;
account sync as phase 2)
**Status:** Approved (design). Not yet implemented.
**Scope decision:** Full three-policy model in v1 (open/locked/secret); one master
password; unlocked state lives in JS memory only (reload = re-prompt); `secret`
prompts once per *run*, not per key. Phase 2: zero-knowledge sync of the store via
the existing login (Anvil). Built in safestat first, ported to openstat afterwards.

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
  password once per session), `secret` (encrypted, password once per run, never
  cached beyond the run). "Encrypt everything" is not a separate system: it is a
  default-policy setting plus a bulk action.
- **Unlock lifetime = the tab** (Hans 2026-07-30). The derived master key lives in
  a JS closure only — never sessionStorage. Reload asks again. Auto-lock timers
  rejected for v1 (YAGNI).
- **One master password** for both `locked` and `secret`. Set lazily — first time a
  key is given a non-open policy.
- **`secret` prompts once per run, not per key encounter** (Hans 2026-07-30).
  Within a single run, per-key prompting adds zero security — same run, same code,
  same trust decision — only annoyance. The run is the natural authorization unit
  (mirrors strict's per-run grants). The prompt lists *which* secret keys the run
  needs (the load list is resolved before execution, so the set is known up front).
  Decrypted secret material lives in a run-scoped cache dropped in a `finally`.
- **Account sync (phase 2): the store syncs as an encrypted blob via the existing
  login — zero-knowledge.** The Anvil backend (`mdataapi.anvil.app`) stores the v2
  JSON document as-is; `locked`/`secret` entries are ciphertext and the master
  password never leaves the client. Gains: roaming across machines, survives
  site-data clearing, backup. Deliberately NOT plaintext-on-server: the bearer
  token sits in localStorage, so login-only unlock would collapse all key security
  to token security plus server trust. Consequence to state in UI: `open` entries
  are server-readable when synced — mark them `locked` if that matters.
- **Login does not replace the master password.** Same reasoning as above; the
  password is the only credential that never touches localStorage or the server.
- **Per-use server fetch for `secret` keys REJECTED.** Hostile in-page code holds
  the same bearer token and can make the same call, so it blocks nothing; it adds
  per-run latency and an Anvil dependency. The one real benefit — a server-side
  audit log per run — already exists where it matters: the strict V3 flow
  (`/_/api/local_run_authorize`). Rule of thumb: need server-audited per-run keys →
  make the source strict; otherwise the local prompt is enough.
- **Flexibility is deliberately minimal**: the three policies are the only
  user-facing concept. Sync is invisible (happens when logged in), there are no
  per-key passwords and no configurable prompt scopes.
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
| `await Keys.resolve(name, ctx)` | Async. `open` → value; `locked` → unlock store via password modal if needed, then value; `secret` → value from the current run scope (see `runScope`), prompting once per run. `ctx` (e.g. dataset alias) is shown in the prompt so the user knows what they are authorizing. |
| `await Keys.runScope(secretNames, fn)` | Wraps one script run. If `secretNames` is non-empty, prompts **once** (dialog lists the names), decrypts those entries into a run-scoped cache, runs `fn`, and drops the cache in a `finally`. `resolve` for a `secret` entry outside a run scope prompts for that single use. |
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
  dataset keys) — their lifetime is the run scope only. `locked`/`open` values may
  cache as today. The run pipeline (index.html, where the deps object is built)
  computes the set of secret names the load list needs and wraps execution in
  `Keys.runScope(names, …)`.
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
  shows *which keys* and *for what* (the run's secret-key names, dataset alias /
  API call), registered via `Keys.attachPrompt`. Reuses the existing
  `keyPromptBackdrop` styling.
- The AI modal's Anthropic field stays but reads/writes through `Keys`
  (policy preserved on edit).
- All strings via i18n (`data-i18n`), Norwegian + English.

### 3.5 Phase 2 — account sync (Anvil)

For logged-in users the whole `md_keys` document syncs to the existing backend
(`mdataapi.anvil.app`, bearer token as for `/auth/me`):

- Two endpoints: `GET/PUT /_/api/keystore` — whole-document, with an `updated`
  timestamp for a simple newest-wins merge (conflicts are implausible for a
  single-user store; no per-entry merging).
- Sync triggers: after login, after any store mutation, on app start when logged
  in. Offline/logged-out use is unaffected — localStorage remains the working copy.
- Zero-knowledge: the server stores the document as-is; encrypted entries stay
  ciphertext (see Decision log). The keys modal shows a status line
  («synces til konto» / «kun lokalt»).
- Phased separately because it needs Anvil-side changes (the known pull-friction);
  v1 is complete and useful without it.

### 3.6 Testing

Deno tests (pattern: `tests/js/encfile-roundtrip.test.js`):

- KDF + envelope roundtrip; wrong password → verifier error, not garbage.
- Policy behavior: `get` returns null for locked/secret; `resolve` prompts (fake
  prompt fn); `secret` prompts once per `runScope`, is dropped when the scope ends
  (also on throw), and never enters any session cache.
- Migrations: `md_anthropic_key` and flat openstat `md_keys` → v2.
- `scrubKeys`: name references unmasked, literals masked.
- data-loader: `key(<navn>)` resolves via store; `secret` bypasses `__encKeyCache`;
  strict path never touches `Keys`.

## 4. Out of scope / roadmap

- WebAuthn/passkey PRF unlock (design leaves the unlock function pluggable).
- Auto-lock after N minutes of inactivity.
- Encrypted export/import of the store — mainly relevant for logged-out users once
  phase 2 sync exists; until then keys are per-browser and die with site-data
  clearing ("re-enter them").
- Server-side plaintext vault / per-use server fetch (both rejected — see
  Decision log).
- openstat port: extend existing `js/keys.js` to v2 format + named lookup for
  `secret_key="<navn>"` in the pythonic syntax; registry-driven keys keep using
  `Keys.get(src.id)` (locked entries there require a session unlock first).
- Pythonic directive syntax in safestat (separate track; name lookup carries over).
