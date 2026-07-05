# Encrypted external sources + unified connect/load — design

Date: 2026-07-05
Status: approved (brainstorm with owner, 2026-07-05)
Repos: m2py (primary surface), microdata-api (Anvil server)

## Goal

Let a data owner keep an encrypted data file wherever they want (e.g. a GitHub
repo), register only its *location, fingerprint and access policy* with Anvil,
and let authorized analysts use that data **locally in the browser** — import
it, analyse it — with the same script working unchanged when routed to remote
execution. Three access modes, chosen by the owner:

1. **key-only** — analyst has the decryption key; no login, no registration,
   Anvil uninvolved.
2. **key + whitelist** — analyst must be logged in AND on the source's
   allowlist AND supply the key. Anvil stores no key; it gates the location.
3. **whitelist-only** — analyst must be logged in and on the allowlist; Anvil
   stores the key (wrapped) and releases it after the permission check.

Orthogonal to the access mode, every registered source carries a **protection
level** (`public` / `protected` / `sensitive`), declared by the owner at
registration. Key release for local analysis applies **only to public-level
sources**. Protected and sensitive sources — encrypted or not — are
**remote-only**: the script runs on Anvil under the restricted engines with
logging, quotas and output suppression, and rows never reach the browser.
Self-service registration covers plain (unencrypted) URL files too, so an
ordinary online csv/parquet can be marked remote-only the same way.

Alongside this, the script vocabulary is unified: `connect` names a source,
`load` materializes a table. This sets the frame for the later language-cleanup
project (variable-level `import`, `create-dataset ... join()`), which is
**not** built here.

## Decisions (with rationale)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Key-release trust model.** Anvil is a permission + key authority. After login + allowlist check it releases the key (mode 3) or just the location (mode 2); the browser fetches the ciphertext from the owner's URL and decrypts locally. Data never transits Anvil. | Matches the existing `kind="encrypted_url"` seam (microdata-api `source_registry.py:10-13`); no server bandwidth for data; plaintext exists only in the analyst's browser. |
| D2 | **AES-256-GCM whole-file envelope, `safepy-enc-v1`.** | Native in browsers (WebCrypto, zero JS deps) and standard in Python (`cryptography`). Whole-file because symmetric decryption is local anyway — variable selection happens after decryption; per-column crypto is only needed for HE. |
| D3 | **Self-service registration by owners** (any logged-in user). | This *is* the improvement: owner keeps the data, tells Anvil where it is and who may use it. Also starts roadmap stage 3 (self-service). |
| D4 | **Key input: `key(<literal>)` and `key(ask)`.** | Literal for the quick low-stakes case (owner's explicit wish); `ask` prompts in the UI and keeps keys out of scripts saved to GitHub / sent to the AI. |
| D5 | **Local + remote parity in v1.** | Same script must behave the same locally and on Anvil; the server side is small because the HE plumbing (fingerprint check, wrapped keys, `load_encrypted_source`) already exists to copy. |
| D6 | **Unified `connect`/`load` vocabulary; `require` kept as compatibility alias.** | One mental model for every mode; ends the require/load/connect overlap without breaking existing scripts; reserves `import`/`create-dataset` for the follow-on language project. |
| D7 | **Protection level is declared by the owner at registration and is orthogonal to encryption and key custody.** Public → local analysis (key release) allowed; protected/sensitive → remote-only under the strict, suppressed, logged engines; format `he` → remote-only under the HE facade. | Encrypted-but-protected data gets compute-to-data guarantees (logged scripts, restricted commands, suppressed outputs) instead of key release. Reuses the existing level machinery unchanged, and self-registration of plain URL files gives remote-only marking for unencrypted data too. |

## 1. Language

All directives live in comments, using the active mode's comment marker
(`#` in py/pandas/polars, `--` in duckdb, `//` where applicable) — same
mechanism as today's `connect`/`load` in `js/data-directives.js`.

```
directive   := connect | load | require

connect     := "connect" target ["as" alias] ["," option]*
load        := "load" (alias["/" path] | url) "as" NAME ["," option]*
require     := "require" target "as" NAME ["," option]*     # legacy alias, unchanged behavior

target      := registry-id | url | anvil-name
option      := "key(" (literal | "ask") ")"
             | "exec(" ("local" | "remote") ")"
```

Target resolution, in order:

1. **Registry id** (entry in `data/data-sources.json`, e.g. `ssb`, `eurostat`)
   → web registry. Unchanged.
2. **URL** (`http(s)://`) → direct fetch. If the bytes sniff as a
   `safepy-enc-v1` envelope, a key is required: from `key(...)`, else the UI
   prompts as if `key(ask)`.
3. **Bare name** → Anvil source registry. The source's registered
   level/policy decides what happens (public → download; encrypted +
   allowlisted → key release; protected/sensitive → remote compute, as today).

Option semantics:

- `key(...)` on `connect` applies to everything loaded from that connection;
  on a `load <url>` shorthand it applies to that file.
- `key(ask)`: modal password prompt on run; key held in memory for the
  session (keyed by fingerprint), never in localStorage, never echoed.
- `exec(local|remote)` moves from `require` to `connect`, same meaning as
  today. Server-side forcing rules unchanged (non-public → remote).

`load` always produces a **whole table** (DataFrame; view in duckdb mode).
Variable-level assembly is a different verb with different semantics
(`import` merges on a join key) and is deferred — see §8.

`require` survives exactly as routed today: bare name → Anvil
compute-to-data routing; URL → alias for load. Docs and examples migrate to
`connect`/`load`.

### Examples

Public web data (unchanged behavior):

```python
#py
# connect ssb as s
# load s/tabell/07459 as befolkning
# load https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv as co2
```

Mode 1 — encrypted file at any URL, key in script, no login:

```python
#py
# load https://raw.githubusercontent.com/hans/depot/main/helse.enc.json as df, key(qL7xK2mN9pR4sT6v...)
df.groupby("kommune").size()
```

Mode 1 with the key out of the script:

```python
#py
# connect https://x.no/helse.enc.json as h, key(ask)
# load h as df
```

Mode 3 — registered, whitelist-only (no key anywhere in the script):

```python
#py
# connect helse2025 as h
# load h as df
df["alder"].describe()
```

Mode 2 — registered, whitelist AND analyst-supplied key:

```python
#py
# connect kreftregister as k, key(ask)
# load k as df
```

DuckDB mode:

```sql
#duckdb
-- connect helse2025 as h
SELECT kommune, count(*) FROM h GROUP BY kommune
```

(v1 materializes `h` to a frame registered as a view, like `#micro` datasets
today; lazy column pushdown is deferred.)

Remote parity — same script, forced to the server:

```python
#py
# connect kreftregister as k, exec(remote)
# load k as df
result_counts = df.groupby("fylke").size()
```

Legacy scripts keep working:

```python
#py
# require helse2025 as db
# require https://x.no/d.csv as df
```

## 2. Envelope format: `safepy-enc-v1`

A sibling of `safepy-he-v1`, deliberately boring:

```json
{
  "format": "safepy-enc-v1",
  "cipher": "AES-256-GCM",
  "payload_format": "csv",
  "iv": "<base64, 12 bytes>",
  "ciphertext": "<base64>",
  "fingerprint": "<sha256 hex of ciphertext bytes>"
}
```

- `payload_format`: `csv` or `parquet` (the plaintext bytes are the file
  as-is).
- **Key**: 256-bit, presented once as a base64url string (~43 chars) — easy
  to paste into `key(...)`, a prompt field, or the registration form.
- **Fingerprint**: SHA-256 of the ciphertext; registered with Anvil and
  re-checked before every use, so a file swapped at its URL (e.g. edited on
  GitHub) is refused — same protection the HE path has
  (`source_registry.load_encrypted_source`).

Owner tooling:

- `encrypt.html` gets a second tab ("Krypter fil") next to the HE
  column-picker: pick any csv/parquet, encrypt fully in-browser via WebCrypto
  (the file never leaves the machine — same promise as today), download
  `<name>.enc.json`, show key + fingerprint once. New module
  `js/enc-crypto.js` (~80 lines: encrypt, decrypt, fingerprint), shared with
  the loader.
- A ~15-line documented Python snippet for owners who prefer a script; kept
  in the docs and covered by the shared fixtures (§7).

## 3. Anvil: registration, policy, key release (microdata-api)

`sources` table additions (existing columns reused: `level`, `kind`,
`location`, `format`, `encrypted`, `fingerprint`, `owner_email`; `he_key`
pattern copied):

- `enc_key` — AES key, Fernet-wrapped at rest (same as `he_key`). Nullable:
  **null = mode 2** (Anvil never sees the key), **set = mode 3**.
- `access_policy` — per-source allowlist:
  `{"emails": [...], "domains": ["fhi.no"]}`. This is the owner's list for
  *this dataset* — separate from the global `email_whitelist` that gates
  login. The owner is always implicitly included.
- New `kind: "encrypted_url"` — the seam already commented in
  `source_registry.py:10-13`. `format` remains the payload format;
  `encrypted=True`.

Mode → registration mapping (**modes 2–3 key release applies to
`level="public"` sources only** — see the level table below):

| Mode | Registered? | `enc_key` stored? | Login + policy required? | Anvil releases |
|---|---|---|---|---|
| 1 key-only | no (raw URL) | — | no | nothing (Anvil uninvolved) |
| 2 key + whitelist | yes | no | yes | location only |
| 3 whitelist-only | yes | yes | yes | location + key |

### Protection level × execution

The owner declares the level at registration; it is stored on the source row
and never trusted from a request (existing invariant). Level decides *where*
the script may run and what the browser may receive; encryption decides the
at-rest format; key custody (`enc_key` stored or not) decides who supplies
the key. All three are orthogonal:

| Level | Local (browser) | Remote engine | Output rules |
|---|---|---|---|
| `public` | allowed — `/source_access` releases location (+ key per mode) | unrestricted dialect run | raw preview (`head(50)`) allowed, no suppression |
| `protected` | refused — never location, never key | safepy STRICT dialects (pandas/polars/r/duckdb, `profile="strict"`) | scripts logged, quotas, result-side suppression |
| `sensitive` | refused — never location, never key | safepy STRICT + input pre-recipe (`microdata_no` profile) | as protected, plus secondary suppression; api-key principals refused |
| format `he` (any level) | refused (ciphertext useless without authority) | HE facade dialects (`he`, `r-he`, …): `group_agg`, `value_counts`, `crosstab`, `ols` only | k-gated authority decryption (existing Plane B) |

For protected/sensitive encrypted sources, remote runs decrypt in memory with
the stored `enc_key`, or with a per-run `source_keys` entry when the owner
chose not to store the key (§5). This is the "three kinds of remote":
public-unrestricted, strict-safepy, and the restricted HE language — all
selected by registry metadata, no grammar change.

Plain (unencrypted) URL files are registrable the same way (`kind="url"`,
which already exists): an owner can publish an ordinary csv/parquet URL and
mark it `protected` — making it remote-only with logged scripts and
suppressed outputs, no encryption involved.

**New endpoint** `GET /source_access?id=<name>` (Bearer token required):

- Checks the caller's verified email against `access_policy` (exact email,
  then `@domain`).
- Returns `{location, payload_format, fingerprint, key?}` (`key` only for
  mode 3).
- Unauthorized or anonymous → **404, not 401/403** — no existence leak, same
  rule as `/source_info` (`api_endpoints.py:708-713`).
- Every response that includes a key writes an `audit_log` row (principal,
  source_id, action `key_released`).

**Self-service registration**: new page in m2py (working name
`deldata.html`), logged-in users only. Fields: dataset name, URL (ciphertext
or plain file), **protection level (public/protected/sensitive)**,
fingerprint (encrypted files), payload format, access mode (2/3), key (mode 3
only, or protected/sensitive with stored key), allowed emails/domains. Server endpoint validates by fetching the URL and checking
the envelope + fingerprint before activating. `encrypt.html` gets a
"Registrer hos Anvil →" hand-off that pre-fills fingerprint and format.
Owners can list, edit, and deactivate their own sources. File *upload*
remains the existing admin-only path — unchanged in v1.

## 4. Browser resolution flow (m2py)

Extends the two existing JS modules; no new architecture:

1. `js/data-directives.js`: `connect` learns bare-name targets (→ Anvil
   lookup) and `key(...)` / `exec(...)` options.
2. Bare name → `GET /source_access` with the session token
   (`window.mdAuth.token`). Not logged in → open the existing magic-code
   login prompt, then retry. 404 → clear error (§6).
   **Non-public source** → the response grants nothing local
   (`{"remote_only": true}`); the run handler routes the whole script to
   remote execution with the sources list, exactly as bare-name protected
   sources route today. `exec(local)` on such a source is refused with a
   clear message (existing forcing rule).
3. Browser fetches the ciphertext from the owner's URL. GitHub raw is
   CORS-open; other hosts fall back to the existing `/api/hent` proxy (same
   `viaProxy` mechanism as registry sources with `cors:false`).
4. `js/data-loader.js`: `sniffFormat` learns the `safepy-enc-v1` envelope →
   `js/enc-crypto.js` verifies the fingerprint, decrypts with WebCrypto
   AES-GCM, hands plaintext csv/parquet bytes to the existing binding path
   (pyodide / webr / duckdb).
5. `key(ask)`: modal password field on run; session-memory cache keyed by
   fingerprint.

Scope: everywhere `connect`/`load` work today — pandas/polars/duckdb/r modes
and `#py` segments of hybrid scripts. Microdata mode unchanged in v1 (still
rejects URLs).

## 5. Remote parity (microdata-api)

Server mirror of §4 step 4, copying the HE plumbing:

- `source_registry.load_dataframe` handles `kind="encrypted_url"`: fetch
  ciphertext from `location`, check fingerprint against the registered
  value, decrypt in memory — key = Fernet-unwrapped `enc_key`, or, for mode
  2, taken from a new optional `source_keys: {source_id: key}` field on the
  `/run_extended` request — parse payload → DataFrame. Plaintext is never
  persisted.
- Levels and locations still come from the registry only, never the request
  (invariant from `safepy_shim.py:49`). Protected/sensitive sources keep
  their suppression policies — **encryption is orthogonal to sensitivity
  level**.
- The three remote regimes (see §3 level table) need no new engine work:
  public → unrestricted dialect run with raw preview; protected/sensitive →
  safepy STRICT dialects with logging/quotas/suppression (the decrypted
  frame enters the same path as plaintext); `format="he"` → the HE facade
  dialects, auto-switched by `safepy_shim` as today. The only new code is
  the AES decrypt step in `load_dataframe`.
- **Key scrubbing**: `script_head` is stored in the audit log today, so a
  `key(<literal>)` in a script would be logged. All logging and AI-prompt
  paths scrub `key(...)` arguments to `key(***)` — browser side and server
  side. `source_keys` values are never logged.

## 6. Error handling

| Situation | Behavior |
|---|---|
| Wrong key / corrupt file | GCM authentication fails cleanly → "Feil nøkkel eller ødelagt fil" (GCM guarantees no partial/garbled decrypt) |
| Fingerprint mismatch | Refuse before decrypting: "Filen er endret siden den ble registrert" |
| Bare name, not logged in | Open magic-code login prompt, then retry resolution |
| Logged in, not on allowlist | 404 from `/source_access` → "Fant ikke kilden eller du mangler tilgang — kontakt eieren" |
| CORS-blocked ciphertext host | Automatic fallback through `/api/hent` proxy |
| `key(literal)` in a script being saved to GitHub / sent to AI | Scrubbed to `key(***)`; editor hint suggests `key(ask)` |
| Anvil unreachable | Mode 1 keeps working — it never touches Anvil |

### Threat model (honest note for docs, same spirit as `media_crypto.py`)

- Mode 3 places key custody with Anvil: an Anvil-account compromise exposes
  those keys. Mode 2 exists precisely for owners who won't accept that.
- Neither mode protects against a *malicious authorized analyst*: once
  decrypted in their browser, they have the rows. This feature is **access
  control + at-rest protection, not output protection**. Data needing
  output protection belongs at `protected`/`sensitive` level on the
  remote/suppressed path (or the HE path).

## 7. Testing

- **Round-trip unit tests** (Python, microdata-api, next to `test_he.py`):
  encrypt → envelope → decrypt for csv and parquet; wrong-key failure;
  fingerprint-mismatch refusal; Fernet wrap/unwrap of `enc_key`.
- **Shared wire-format fixtures** `tests/fixtures_enc/` (like
  `fixtures_he/`): the JS encryptor and Python decryptor are tested against
  the same bytes.
- **Endpoint tests** for `/source_access`: anonymous → 404; wrong email →
  404; allowed email → payload with/without key per mode; audit row written
  on key release.
- **JS**: fixture-based test that `enc-crypto.js` decrypts `fixtures_enc`
  files (node WebCrypto).
- **E2E demo (manual, doubles as documentation)**: encrypt a sample csv in
  `encrypt.html`, push to a GitHub repo, register via `deldata.html`, run
  the §1 examples for modes 1, 3, 2 and remote; negative test with a
  second, non-allowlisted user.

## 8. Deliberately deferred

- `import` / `create-dataset <name>, join(<col>)` variable-level assembly —
  the follow-on language project; grammar reserved here so v1 doesn't
  collide. Microdata mode keeps its implicit entity-id when `join()` is
  absent.
- DuckDB lazy column pushdown, duckdb-file `ATTACH`, duckdb-as-browser-store
  — revisit only if files outgrow memory.
- Microdata-mode URL/encrypted sources (currently rejected there) — language
  project.
- Owner-supplied storage tokens (private GitHub repos) — the `credentials`
  seam in the 2026-06-29 safestat spec; explicitly not v1.
- Access-request/grant workflow (`AccessRequest`) — v1 error message points
  to the owner instead.
- `auth(type, handle)` secret-handle mechanism (2026-06-28 manifest spec) —
  untouched; `key()` is separate and does not collide.
- Per-column symmetric encryption — unnecessary while decryption is local
  and whole-file.
- Remote-only enforcement by authorities other than Anvil (federated or
  third-party registries) — the level lives on the Anvil source row in v1;
  the resolution step is the seam where another authority could answer
  `/source_access` later.
