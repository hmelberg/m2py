# SafeStat → remote compute-to-data: vertical-slice design

> **Status:** approved design (brainstorming output). Supersedes the open
> questions in `2026-06-29-remote-compute-to-data-brief.md` for the first
> implementation pass.
> **Guardrail:** `docs/extended-mode-architecture.md` — read first; this design
> stays inside it (policy object, no emulator fork, no `if extended:`).

## Goal

Make remote analysis real as one **thin end-to-end vertical slice**: a SafeStat
script runs against real data held by a server, the data never leaves the
server, and the result comes back in the JSON shape SafeStat already renders.
Today `safeStatTarget = 'remote'` only prints a placeholder.

The slice runs against **one public CSV at a URL, fetched by the server**. Every
heavier capability (auth, logging, data-side protection, upload ingress) is
**designed here in full** and built as structured-but-pass-through seams, so the
follow-on work slots in without restructuring.

## The load-bearing decisions (settled in brainstorming)

1. **Client sends the microdata *script* + source bindings; the server
   translates and runs its own emitted code.** The server never executes
   client-supplied Python. This is the security property that makes
   compute-to-data on sensitive data tractable, and it is the natural home for
   server-side disclosure control. (Rejected: "client translates, server
   executes the artifact" — it forces the server to sandbox arbitrary
   client-supplied Python, and disclosure control could not trust the incoming
   code.)
2. **Executor is derived from source protection level, with the existing
   `local|remote` toggle kept as a developer override.** `deriveExecutor(sources)`
   defaults to local; a non-public source forces remote (most-restrictive-wins).
3. **One attribute — `ProtectionLevel` — drives executor, auth, logging, and the
   `protect` pre/post hooks.** Not separate switches. This is the central concept.
4. **Privacy controls are the existing `protect` package, not new code.** Its
   `protect(df, recipe=…)` / `profile("microdata_no")` are data-side;
   `suppress(target, …)` is result-side; `risk(...)` is the k-anonymity gate.
   `protect` is pandas-only, so in the structure it is the **pandas reference
   implementation of a `ProtectionAdapter` interface** (see Future direction),
   not the universal engine.
5. **The input language is a distinct axis (the "frontend").** Microdata script
   is the first frontend (it compiles to pandas/polars via the translator); raw
   Python, R, DuckDB SQL, and API calls are future frontends. The artifact and
   request carry a `language` field from day one so the contract is extensible;
   v1 implements `language="microdata"` only.
6. **Protection level is a property of the registered source, set by its owner —
   never a request parameter.** The request references a source by `source_id`;
   the server looks up its level/recipe/location/version. A requester cannot
   self-declare "public" to bypass controls. This requires a **source registry**
   (below). v1 ships the *minimal* registry (lookup + one seeded public source);
   the admin layer (revoke/update/version/upload UI) is deferred.
7. **Remote execution is asynchronous: submit → poll.** Real-data analysis can
   exceed Anvil's synchronous request limits, so `/run_extended` launches a
   background task and returns a `task_id`; the client polls `/task_status`
   (the pattern `/query` already uses) and renders when results are ready. The
   client `RemoteApiExecutor` is submit-and-poll from day one so the contract
   never has to change from sync to async later.

## Central concept: `ProtectionLevel`

Every **registered** source carries a protection level, set by its owner at
registration time (see Source registry), with a default. The level lives with
the source, not the request. Applied **most-restrictive-source-wins** across all
bound sources, it is the single selector for five behaviors:

| Level | Auth | Logging | Pre (data) protection | Post (result) protection | Executor |
|---|---|---|---|---|---|
| **public** | none | none | none | none | local *or* remote |
| **protected** *(default)* | login required | log script+user+time | optional `protect(recipe=…)` | `suppress` min-cell on tables | remote |
| **sensitive** | login required | log (retained N days) | `profile("microdata_no")` / recipe | `suppress` + `risk` gate | remote (forced) |

Level names and the retention period `N` are deliberately small and may be
revised; the *shape* (a single ordered level → a resolved policy) is fixed.

```python
# resolve_policy is the one place levels turn into behavior.
ProtectionPolicy = {
    "auth_required": bool,     # stage 2
    "log":           bool,     # stage 3
    "pre_recipe":    dict|None,# stage 5  (None = pass through)
    "post_suppress": dict|None,# stage 7  (None = pass through)
}
def resolve_policy(levels: list[str]) -> ProtectionPolicy: ...   # most-restrictive wins
```

## Data flow (the slice)

```
SafeStat editor (m2py / index.html)
  │  artifact = { language:"microdata", script, backend, printResults }
  │  sources  = [{ alias, source_id }]        ← references registry; NO url/level in the request
  ├─ deriveExecutor(sources) ─► local ─► LocalPyodideExecutor  (translate in-browser → Pyodide)  [unchanged]
  └─ remote (derived/toggle) ─► RemoteApiExecutor  (submit → poll)
        │  (a) POST /run_extended { script, sources:[{alias,source_id, key?}], backend, print_results }
        │      (Authorization: token — attached when any referenced source ≠ public;
        │       per-source `key` present only for encryption='at_rest' sources — transient, never logged) → { task_id }
        │  (b) GET  /task_status?id=task_id  (poll)                                     → { status, result? }
        ▼
   microdata-api (Anvil server)  —  background task launched by /run_extended:
        1. resolve sources by source_id (location, level, recipe, version); policy = resolve_policy(levels)
        2. authn + authz (public ⇒ pass; else validate token, then check user/IP vs source access_policy)
        3. log           (public ⇒ skip; else append {user,ts,script,source_ids})
        4. fetch sources (read_source(location[, credentials]))   [v1: public URL]
        4b. admissible?  (adapter.admissible(program) vs policy)  [microdata ⇒ trivially ok in v1]
        5. pre-protect   (public ⇒ skip; else adapter.pre(df, recipe/profile))
        6. translate+run (m2py_translate.translate(script) → exec on protected df)
        7. post-protect  (adapter.suppress(result) per level)  ← LIVE in v1, on STRUCTURED
        │                   result objects, BEFORE output_render serializes them
        8. return        _results / _figs JSON  (output_render.py)  → stored on the task for polling
        ▼
   SafeStat renders it  ← existing renderer, untouched
```

## Components & interfaces

### Client (m2py — `index.html`, replacing the `~7484` placeholder)

```js
// Executor.run(artifact, sources) -> Promise<Result>
//   artifact = { language, script, backend, printResults }
//   sources  = [{ alias, source_id }]
//   Result   = { results, figs, error }
LocalPyodideExecutor.run(artifact, sources)   // today's translate→Pyodide path, moved behind the seam (behavior-preserving)
RemoteApiExecutor.run(artifact, sources)      // POST /run_extended → task_id, then poll /task_status → Result
deriveExecutor(sources) -> 'local' | 'remote' // default local; non-public source forces remote; toggle overrides
```

`runSafeStatScript` becomes: *gather artifact → deriveExecutor → executor.run → render*.
`RemoteApiExecutor` owns the submit-and-poll loop, so `runSafeStatScript` still
just awaits one `Result`. A source's level is *not* known to the client; it asks
the server (or a cached registry lookup) only enough to decide local-vs-remote
and whether a token is required.

### Server (microdata-api)

- **`@http_endpoint("/run_extended", POST)`** in `api_endpoints.py` — parse body,
  **launch a background task** (`anvil.server.launch_background_task`), return
  `{task_id}`. Polled via the existing **`/task_status`** endpoint. Mirrors the
  CORS/`cross_site_session=False` posture of the existing endpoints. **The
  existing `/run` (emulator-on-mock) is untouched.**
- **`m2py_shim.run_extended(script, sources, backend, print_results) -> dict`** —
  the background-task body: resolve sources via the registry, run pipeline stages
  1–8, return `{results, figs, error?, datasets?}`.
- **Source registry lookup** — `resolve_source(source_id) -> {location, encryption,
  level, recipe, version, credentials, admins, org, access_policy, status}`;
  rejects revoked/unknown ids. Level/recipe/policy come from here, never from the
  request.
- **`resolve_policy(levels)`** + the stage functions (auth/log/pre are no-ops for
  public in v1; `adapter.suppress` post-protect is wired live).
- **Suppress hook point:** post-protect runs inside `run_extended` on the
  structured `_results` objects (DataFrames/tables) *before* `output_render.py`
  serializes them — `suppress` dispatches on input type and needs real objects.
- `read_source` (already in `m2py_runtime/sources.py`) fetches the public CSV in
  v1; the credentialed-URL and Anvil-stored paths extend it later.

### Source registry & administration

A registered source is the unit of governance. It is administered by one or more
**data-admins** (the uploader plus any co-custodians, and any member of its
owning organisation), and an analysis request only references it by `source_id`.
"Admin" throughout means *data-admin* (custodian of a dataset), not a global
system administrator.

```
Source = {
  source_id,            # stable reference
  admins,               # SET of users who may administer this dataset (the
                        #   uploader + any co-custodians). Multiple admins allowed.
  org,                  # optional owning organisation; its members are also admins
  kind,                 # 'url' | 'anvil_datatable' | 'anvil_datafile'
  location,             # URL, or a handle to the Anvil-stored data
  encryption,           # 'none' | 'at_rest' — at_rest means location holds CIPHERTEXT;
                        #   the consumer supplies the key per analysis (see below)
  credentials,          # optional: e.g. private-GitHub url + access token (data not copied to us)
  level,                # ProtectionLevel — set HERE, by the owner
  recipe,               # optional column→protect recipe / profile (per level)
  schema,               # optional; inferred if absent
  version,              # data has versions; updating data creates a new version
  status,               # 'active' | 'revoked'
  access_policy,        # WHO may run against this source (authorization, below)
}

# Authorization is per-source and rule-based — evaluated at stage 2 after authn.
AccessPolicy = {
  email_domains,        # e.g. ['fhi.no', 'uio.no'] — any user who registered with
                        #   such an address is allowed (domain is proven by the
                        #   email-verify auth flow, so it can be trusted)
  emails,               # explicitly allowed individual addresses
  ip_allow,             # allowed IPs / CIDR ranges (request-origin based)
  granted_users,        # users individually approved via an AccessRequest
}

# A user with no matching rule may ask a data-admin for access.
AccessRequest = { request_id, source_id, user, message, status, decided_by, decided_at }
#   status: 'pending' | 'granted' | 'denied'  — granting appends to granted_users

# Organisations administer many datasets; membership confers data-admin rights.
Organisation = { org_id, name, members }   # members are data-admins of every Source whose org == org_id

# Two distinct roles, do not conflate:
#   data-admin  = may ADMINISTER the dataset (mutate, set policy, view logs, decide requests)
#                 = a user in Source.admins  OR a member of Source.org
#   consumer    = may RUN analyses against it = matches Source.access_policy
```

**Storage in Anvil — two ingress kinds:**
- **Registered URL (+ optional credentials).** We store only the URL and, if
  needed, an access token (e.g. a private GitHub repo). The data itself stays at
  the source; the server fetches at run time. No data residency on our side.
- **Uploaded data.** Stored in an **Anvil Data Table** (structured rows, the
  natural fit) — or **Data Files / Blob media** if file upload proves workable
  (to be verified; Anvil Data Tables are the safe default).
- **Uploaded data, encrypted at rest (`encryption='at_rest'`).** The owner
  uploads **ciphertext**; Anvil stores only ciphertext, and **the key is never
  stored server-side**. To analyse, a logged-in, authorized consumer **supplies
  the decryption key in the request**; the server decrypts **in memory only**,
  runs the normal pipeline (stages 4→8), and never persists plaintext. So even a
  party with full Anvil/DataTable access cannot read the sensitive data without
  the key.
  - This is the **one legitimate request-borne secret** — a decryption key the
    user holds, not a trust-bypassing parameter like `level`. It is used
    transiently and **must never be logged** (stage 3 logs script + user +
    `source_id`, never the key).
  - **Threat model (honest):** protects the *at-rest / storage* boundary, **not**
    compute time — the server necessarily sees plaintext in memory to run the
    analysis. For a model where the server never sees plaintext at all (at the
    cost of only invertible computations), see `EncryptedLocalExecutor` in Future
    direction. The two are complementary, not redundant.

**Admin operations** (any data-admin of the source): register, update-data
(→ new version), change-level, change-recipe, manage `admins`/`org`, revoke,
delete. Revoked/unknown ids are rejected at `resolve_source`. Versioning lets
`version()` in a script pin a snapshot so past analyses stay reproducible after
data updates.

**Access control & log review** (any data-admin of the source):
- **Manage the access policy** per source — add/remove allowed email domains
  (`@fhi.no`, `@uio.no`), individual emails, and IP/CIDR ranges. Domain rules are
  trustworthy because the email-verify auth flow proves the address.
- **Review access requests** — a user without a matching rule can submit an
  `AccessRequest`; a data-admin sees a queue and grants/denies. Granting appends the
  user to `granted_users`.
- **Examine logs** — browse/filter the execution log (what script ran, by which
  user, against which source, when). The log is the audit trail the protected/
  sensitive levels already write (stage 3); the admin view is its reader.

**Authorization vs authentication.** Authentication ("who are you", the email→
token flow) already exists. This adds *authorization* ("may you use THIS source"),
evaluated per-source at stage 2 after the token is validated: the user passes if
their proven email matches `email_domains`/`emails`, the request IP matches
`ip_allow`, or they are in `granted_users`. Public sources skip the whole check.

**v1 vs deferred.** v1 ships the *minimal* registry: the `Source` table, a
`resolve_source` lookup, and **one seeded `public` URL source** — enough to make
"level is owned by the source" true from the first commit. The admin
operations, versioning, credentialed URLs, and Anvil upload are the **deferred
admin layer** (their own spec).

### Sync (`sync_to_api.py` in m2py — answers "is the server up to date?")

A checked-in manifest of canonical files → copy into sibling
`microdata-api/server_code/`, print an md5 drift report, fail loudly on silent
divergence. Run before each Anvil push. Manifest covers:
`m2py.py` (currently drifted), `m2py_translate.py` + `m2py_runtime/` (missing),
`protect.py` (missing). (Rejected: git submodule — too heavy for Anvil bundling;
runtime `pip install protect` — looser pinning than a vendored copy.)

**Clobber-safety (gap 5):** the server's `m2py.py` is currently *longer* than
source — it may carry Anvil-specific edits. Before `m2py.py` becomes a sync
target, confirm it is import-clean with **zero server-local edits** (move any
Anvil glue into a separate, non-synced shim such as `m2py_shim.py`). The sync
script only overwrites files on the manifest and reports — it must never silently
wipe a server-only adaptation. First run is a *report-only* diff, not a copy.

## Scope

**Build now (v1):**
- Client Executor seam: interface, `LocalPyodideExecutor` (behavior-preserving
  refactor of today's path), `RemoteApiExecutor` (**submit-and-poll**),
  `deriveExecutor`.
- Server `/run_extended` (launches a **background task**) + `run_extended` shim:
  translate + run the **real translator** on a public CSV source, return
  `_results`/`_figs` via `/task_status`.
- **Minimal source registry:** `Source` table + `resolve_source` + one seeded
  `public` URL source. Request references `source_id`; level resolved server-side.
- `resolve_policy` + pipeline scaffold with all 8 stages present.
- **`protect` post-`suppress` wired live** on result tables (privacy seam proven,
  not stubbed).
- `sync_to_api.py` + manifest (incl. `protect.py` and the translator stack);
  first run report-only.

**v1 discipline (refinements from the full design discussion):**
- **Strictly public-only.** No governance executes in v1. `resolve_policy`
  returns the all-pass policy for `public`; auth/authz/log/pre-protect are
  no-ops. Resist pulling any deferred item forward.
- **Registry storage is trivial.** The `Source` "table" is one seeded row (an
  Anvil Data Table with a single `public` source, or an equivalent lookup) with
  **no CRUD** — the contract that matters is *request sends `source_id`, server
  resolves the level*; admin mutation is the deferred layer.
- **Prove `suppress` is live, not just present.** Include a demonstration whose
  result has a small cell, so the post-protect stage visibly suppresses it —
  the privacy seam is exercised, not dead code.
- **Remote is reached via the toggle in v1.** The one public source derives
  `local`; the developer toggle forces the remote path so `/run_extended` is
  actually exercised end-to-end.
- **Build order (de-risk): ** (1) server `run_extended` translating+running the
  real translator on a hardcoded source, **synchronously**, with `suppress`, as
  the first green milestone; (2) wrap it in the background task + `/task_status`;
  (3) registry lookup by `source_id`; (4) client Executor seam + submit-and-poll.
  Each step keeps the suite green and the local path untouched.

**Designed, deferred to follow-on specs (seams exist, pass-through in v1):**
- **Admin layer:** register / update-data / change-level / revoke / delete,
  versioning, credentialed URLs (e.g. private GitHub + token), Anvil upload
  (Data Table vs Data Files), and the protection-level-at-upload UI.
- **Ownership model:** multiple data-admins per source + `Organisation` entities
  whose members administer all the org's datasets.
- **Access control & audit:** per-source `access_policy` (email-domain / email /
  IP allowlists), the `AccessRequest` grant/deny workflow, and the data-admin
  **log viewer** (what code ran, by whom, against which source).
- **Encryption-at-rest with client-held keys:** `encryption='at_rest'` sources,
  the per-request transient key (decrypt-in-memory, never stored/logged).
- Auth gate (authn) for non-public sources (reuse `auth.py` token validation +
  client token attach) + per-source authz check.
- Logging table + retention (scheduled deletion task).
- Pre-protect profiles per level (`protect` / `profile("microdata_no")`).
- `risk` gate / `sensitive` tier.
- Per-source kind dispatch (architecture doc's Step B convergence).
- Additional language frontends (Python / R / DuckDB SQL / API), the
  `admissible()` allowlist, and non-pandas `ProtectionAdapter`s (see Future
  direction). v1 ships `language="microdata"` + `PandasProtect` only.
- `EncryptedLocalExecutor` (see Future direction).

## Future direction: multi-language frontends & cross-engine protection

Not built in v1, but the v1 seams are shaped to admit it without restructuring.

**Four axes, not three.** The *input language* (frontend) joins Mode / Executor /
Backend. Microdata is the first frontend; future ones are raw Python, R, DuckDB
SQL, and API calls. `language` is in the artifact/request now; each frontend
turns its input into the same downstream request the pipeline already runs.

**Admissibility is enforced at the output boundary, not by command lists.** In a
Turing-complete language you cannot enumerate every way to leak a row
(`df.head()` is one of unboundedly many). The guarantee is structural:

- The program's **return channel is the only egress**, and every returned value
  passes through `adapter.suppress(...)` (aggregation / min-cell / `risk` gate)
  before serialization. Raw microdata rows therefore cannot leave for a
  protected source regardless of what the script does.
- `adapter.admissible(program)` (e.g. AST allowlist rejecting `head`/`print`/
  file-IO/network) is **defense-in-depth** — it shrinks the attack surface and
  gives clear user errors — but it is *not* the guarantee. This mirrors
  microdata.no: it checks outputs; it does not trust the script.

The permitted command subset is keyed on protection level + language, just like
the pre/post recipes.

**`ProtectionAdapter` — the cross-language seam.** Generalizes the v1 hooks:

```python
class ProtectionAdapter:                      # one per (language/engine)
    def admissible(self, program) -> list[Violation]: ...   # stage 4b
    def pre(self, data, recipe) -> data: ...                # stage 5  (data-side)
    def suppress(self, result) -> result: ...               # stage 7  (result-side)
PandasProtect(ProtectionAdapter)   # v1: wraps protect.py — the reference adapter
# later: RProtect, DuckDbProtect — must match PandasProtect's behavior
```

**DuckDB as the data spine (recommended hybrid, hard part left open).** When a
second language arrives, centralize the **data side** on DuckDB: it resolves
`import`/`require` (CSV/parquet/registry) and applies data-side transforms
(`winsorize`/`bin`/`coarsen` map cleanly to SQL), then hands a *protected
relation* to whichever frontend runs the analysis. This is language-agnostic and
matches the standing DuckDB-large-data aim. **Result-side protection and
admissibility stay per-language adapters** — regression objects, plots, and
arbitrary frames cannot all be expressed in SQL. Open question to resolve
*before* adding language #2 (not now): how much data-side protection lives in
DuckDB vs. the language adapter, and whether DuckDB is also the default execution
backend for the analysis itself.

**A third executor: `EncryptedLocalExecutor` (encrypted-local / unscramble-API).**
Already named in the guardrail doc's executor table. The user holds a **keyed,
reversibly-perturbed** copy of the data (e.g. an affine transform `y = a·x + b`
per column, or a bijective category relabeling) and computes **locally**; the
results come out scrambled; a small API call un-scrambles them with the key the
server holds. The server **never sees the data, only results to invert** — fast
(compute is local) and no data egress for computation.

It reveals the cleanest framing of an Executor: **the 8-stage pipeline is logical;
the executor maps each stage to a *location*.**

| Stage | `RemoteApiExecutor` | `EncryptedLocalExecutor` |
|---|---|---|
| fetch + data-side protect | server | n/a (data pre-scrambled, held local) |
| run analysis | server | **client (local, on scrambled data)** |
| decrypt / unscramble | — | **server (holds the key)** |
| result-side `suppress` | server | **server (post-decrypt — still required)** |

Two consequences, both reusing seams we already have:
- **`admissible()` gains a second job:** is the computation *invertible under this
  source's scramble*? Linear stats under an affine key pass; a median under a
  non-monotone key is rejected before running. "Works in some cases" = enforced,
  not trusted.
- **Result-side `suppress` still runs server-side, after decryption.** The
  unscramble endpoint is `decrypt → suppress → return`, not bare `decrypt` —
  otherwise a 2-cell decrypted table would leak. Same `ProtectionAdapter.suppress`.

**Caveat to record:** this is keyed reversible perturbation, **not** homomorphic
encryption. The user holds scrambled microdata locally, so security rests
entirely on **scramble strength** vs. auxiliary-data reconstruction — that is the
real boundary of "works in some cases," and it must be stated as the executor's
risk, not glossed.

## Guardrail compliance

- Builds on the **translator**, never forks the emulator.
- Parser/`m2py_runtime`/`m2py.py` helpers: **additive, behavior-preserving** only.
- All divergence behind `resolve_policy` / source-kind policy — **zero
  `if extended:`**.
- Default path (microdata / local / `/run`) is untouched and remains the baseline.

## Verification

- Translator/server: `python -m pytest -q` in m2py and in `protect` (112 tests)
  must not regress. **Capture the real green baseline in the actual env first** —
  the brief cites 531 passed / 1 xfailed, but local-env notes show pre-existing
  failures (plotly missing + pandas-3.0 parquet); reconcile before relying on it.
- New server test: `run_extended` against a public CSV fixture returns expected
  `_results`; a table result shows `suppress` applied.
- Browser: `node --check` on the inline `<script>`; manual reload exercising the
  remote toggle against a deployed `/run_extended`.

## Non-negotiable security property

The server only ever executes **its own translator-emitted code**, never
client-supplied Python. Every protection level depends on this holding — and in
v1 it holds *because* the only frontend is microdata (the server controls the
emitted code) and the only data is public.

**Scope of the guarantee (gap 2, stated honestly):** the "output boundary is the
sole egress" property is structural only when execution is confined. v1 runs the
translator-emitted code **in-process on Anvil, with no sandbox** — acceptable
because the code is server-controlled and the data is public. The moment
**direct-language frontends** (Python/R) run user-authored code against
non-public data, in-process `exec` would let a script open a socket or read
another file, and the output-boundary guarantee **fails without real execution
isolation**. A sandbox is therefore a hard prerequisite for direct-language
frontends on protected data — designed-for, explicitly **unbuilt** in v1.
