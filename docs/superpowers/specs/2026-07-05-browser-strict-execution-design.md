# Browser-STRICT execution — safepy locally, in versions

Date: 2026-07-05
Status: approved in dialogue (owner, 2026-07-05); versioned delivery
Repos: m2py (browser engine + UI), microdata-api (grants + audit), safepy (engine, unchanged where possible)
Builds on: `2026-07-05-encrypted-external-sources-design.md` (grammar, /source_access, key custody)

## Goal

Run the safepy STRICT capability facade (pandas, translated-R; later polars,
duckdb) **inside the browser** (Pyodide), so that:

1. A script behaves identically in local development and remote execution —
   same restricted verbs, same suppression dots, same refusals (the
   microdata.no development loop: write locally, run remotely, no surprises).
2. A data owner can register a source as **"local, but strict-only"**: rows
   may reach an authorized analyst's browser, but only into the facade —
   with every run authorized and logged server-side.

## Honest threat model (governs every version)

Once plaintext exists in the browser, the analyst's machine is the trust
boundary. A determined user with DevTools can read frames out of memory —
**no version of this design prevents that, and none claims to.** The security
value delivered is, in order:

1. **Attribution + audit** — every key release and every run is tied to a
   logged-in, whitelisted identity and logged server-side (the deterrence
   model real microdata systems rest on).
2. **In-language containment** — inside a gated script there is no route to
   raw rows (the STRICT facade is a capability sandbox; this is already true
   and tested).
3. **Casual-circumvention hardening** — worker isolation and
   decrypt-only-at-run shrink the window where plaintext is inspectable from
   "always, in the main thread" to "during a run, inside a worker".

Explicit non-goals, permanently: obfuscation, anti-debugging, encrypted
in-memory frames during execution, any claim of row-proofness in the browser.
Data that needs row-proofness is registered `local: none` and runs remotely.
The UI and docs state this plainly wherever strict-local appears.

## The two registration dimensions

Registration (deldata.html + owner_sources) gains a second axis:

| Dimension | Choices | Meaning |
|---|---|---|
| `level` | public / protected / sensitive | What remote execution enforces (suppression, quotas, input recipes) — unchanged |
| `local_mode` (new) | **none** / **strict** / **open** | Whether rows may reach the browser at all, and under which engine |

Defaults: public → open, protected/sensitive → none. The new cell is
protected/sensitive + `local_mode: "strict"` — the owner knowingly trades
row-proofness for convenience and gets the full audit trail in return.

`/source_access` grant gains `local_profile: "open" | "strict"` and `level`:

| level | local_mode | Grant answer |
|---|---|---|
| public | open (default) | grant, `local_profile: "open"` — today's behavior |
| public | strict | grant, `local_profile: "strict"` |
| public | none | `remote_only` |
| protected/sensitive | strict | grant, `local_profile: "strict"`, `level` carried (facade uses the matching policy tier) |
| protected/sensitive | none (default) | `remote_only` — unchanged |

Key custody (mode 2/3) is orthogonal and unchanged.

## Facade boundary = run boundary

A strict run routes the **whole script** through `safepy.run(script, frames,
level=<from grant>, profile="strict", dialect=<mode>)` in Pyodide, instead of
free execution. Consequences:

- **Nothing crosses back.** Released, mediated output is rendered; no
  DataFrames from a strict run enter the open session namespace. The
  "derivatives are strict too" problem dissolves — derivatives never escape
  the facade. ("Release aggregate to session" is a possible later feature,
  deliberately deferred.)
- **Most-restrictive wins.** Mixing a strict source with open sources in one
  script pulls the entire run into strict (same rule as the server).
- **Hybrid scripts** (`#micro` + strict source in one script) are refused in
  v1-v3 with a clear message; single-dialect scripts only.
- **Sidebar badge**: datasets loaded under a strict grant show "kun strict" in
  the dataset overview (from the grant, via the run catalog).

## Versions

### V1 — Engine parity (pandas + R STRICT in Pyodide)

The core: safepy runs in the browser.

- **Package delivery**: extend `m2py/sync_to_api.py` with a `--web` target
  that zips the safepy package (same manifest as the Anvil sync, GENERATED
  header included) into `m2py/vendor/safepy.zip`. index.html lazily fetches
  and `pyodide.unpackArchive(...)`s it on the first strict run.
- **Adapter**: new `m2py/safepy_local.py` (runs inside Pyodide) — converts a
  `SafeResult` into the exact client result shape `renderSafeStatResult`
  already consumes (`{code, err, figs, results, datasetInfo, audit}`). It is
  the browser twin of `safepy_shim._to_client_shape` and is pure Python,
  unit-tested in CPython.
- **Run routing**: a strict run is triggered manually in v1 (an options flag
  `# options.profile = strict`, useful for development and teaching against
  ANY local data) — grant-driven routing arrives in V2.
- **Dialects**: pandas and R (translated — no R runtime needed). polars and
  duckdb are in Pyodide's package list; they follow after the core proves out
  (see Deferred).
- **Noise salt**: `SAFEPY_NOISE_SALT` is set to a random per-session value in
  the browser (client-visible, hence decorative — documented as such).

### V2 — Grant-driven policy

The owner's registration decides; the app obeys.

- `sources` gains `local_mode` (none/strict/open); registration form gets the
  second dimension with plain-language explanations and defaults by level.
- `source_access.access_decision` implements the grant table above
  (returns `local_profile` + `level`).
- Loader/run handler: a strict grant forces the strict run path with the
  granted level; `local_profile: "open"` behaves as today; strict grant +
  polars/duckdb/hybrid script → clear Norwegian error naming the limitation.
- Sidebar badge for strict-loaded datasets.
- Mixing rule enforced (any strict source ⇒ strict run).

### V3 — Accountability (per-run authorization + logging)

Every local strict run is visible to the owner.

- New endpoint `POST /local_run_authorize` `{source_ids, script}`:
  re-authenticates, re-checks the per-source allowlist, writes an
  `audit_log` row (`action: "local_strict_run"`, scrubbed `script_head`,
  principal, source_ids, level), and returns the per-run `source_keys`.
- For strict sources, `/source_access` stops returning the key — location
  and metadata only; **keys flow exclusively through per-run authorization.**
- **No key caching**: the session key cache is bypassed for strict sources;
  every run re-authorizes. (Key releases were already audited; now every
  run is, and "key released but no run logged" is a visible anomaly.)
- Quotas: v3 logs only; wiring strict-local runs into the existing BUDGETS
  is a follow-up decision once usage is observed.

### V4 — Hardening (shrink the plaintext window)

Raises the casual-circumvention bar; changes no security claims.

- **Ciphertext-in-memory**: for strict sources the browser holds only the
  envelope. Decryption happens at run start, inside the run context; frames
  are built, the facade runs, then plaintext objects and the key are dropped
  (del + gc) before the run returns. Plaintext bytes are never written to
  the Pyodide FS for strict sources. Between runs, the console finds only
  ciphertext.
- **Worker isolation**: the strict run executes in a dedicated Web Worker
  Pyodide instance with no DOM access; frames never exist in the main
  thread. Inspection now requires attaching a debugger to a worker rather
  than typing `df` in the console.
- Both are hardening, not prevention — the threat-model section ships
  verbatim in the docs.

## Error handling (all versions)

| Situation | Behavior |
|---|---|
| Strict grant, script uses a verb outside the facade | safepy's own refusal, rendered like a remote refusal (identical message locally and remotely) |
| Strict source in polars/duckdb mode (pre-Deferred) | "kilden «X» krever strict-modus — støttes foreløpig i python/r" |
| Strict source in a hybrid (#micro) script | "strict-kilder kan ikke blandes med #micro-segmenter (ennå)" |
| `/local_run_authorize` denied (V3) | 404-style refusal, same no-existence-leak rule |
| safepy.zip fetch fails | "kunne ikke laste strict-motoren — prøv igjen" (run refused, never falls back to open execution) |

The last row is a hard invariant: **a strict source never executes under the
open engine, under any failure mode.**

## Testing

- Engine: already covered (safepy CPython suite, 692 tests) — the browser
  runs the same files.
- `safepy_local.py` adapter: pure, unit-tested in CPython against fixture
  SafeResults (twin-tested with `safepy_shim._to_client_shape` outputs).
- Grants: extend `test_source_access.py` for the level × local_mode table;
  `test_owner_sources.py` for the new field.
- `/local_run_authorize`: pure decision + audit-row tests, endpoint wrapper
  matching `/source_access` conventions.
- Browser integration: Playwright pass per version (strict run renders
  suppressed output; refusal messages; V4: plaintext absent from FS and
  main-thread globals between runs).

## Deferred

- polars-STRICT and duckdb-STRICT in the browser (both packages exist in
  Pyodide; add after V2 proves the core; duckdb needs no wasm-bridge seam
  since native duckdb runs inside Pyodide).
- lifelines/pyfixest regression extras in the browser (micropip where
  possible; degrade with a clear message otherwise).
- "Release aggregate to session" (letting a released, suppressed result
  become an open DataFrame for further free analysis).
- Strict-local runs counting against remote quotas (BUDGETS).
- Hybrid scripts mixing #micro segments and strict sources.
- Anti-debugging / obfuscation: never (non-goal).
