# Remaining roadmap — access control + verb consistency

Date: 2026-07-05
Updated: 2026-07-06 — reconciled against `docs/superpowers/specs/2026-07-06-remote-columnar-sources-design.md` (see §4 and "Recommended order" below).
Status: planning map (not a build plan). Effort: S ≈ hours, M ≈ 1–2 days, L ≈ needs its own brainstorm+spec.

Snapshot of what's DONE this cycle (all on `main`/`master`):
- Unified `connect`/`load` grammar; `require` kept as legacy alias.
- Encrypted external sources (`safepy-enc-v1` AES envelopes; three key modes).
- Protection levels + `local_mode` (none/strict/open); grant-driven routing.
- Browser-STRICT execution V1–V4 (safepy in Pyodide; per-run authorize/log;
  decrypt-at-run; worker isolation).
- Audience model (owner/listed/authenticated/anyone) enforced local + remote.
- Self-service registration incl. AES + HE artifacts (deldata.html).
- **Project A — variable-level `import`/`create-dataset`/`join`** (was listed
  below as "the headline unbuilt piece" as of 2026-07-05; shipped since — see
  §1a). Parser (`js/data-directives.js`: `CREATE_RE`/`IMPORT_RE`/`JOIN_RE`/
  `parseAssembly`), pandas executor (`safepy/safepy/assembly.py`, mirrored in
  `microdata-api`), and `index.html` wiring (`_asmSpec`/`_pyLoads`,
  `buildAssemblyPreamble`) all confirmed present and end-to-end connected for
  python/r/duckdb modes.

What follows is everything still deferred, grouped and sequenced.

---

## 0. Verify what's built (do this first) — effort M, no design

Everything above is tested against stubs/fixtures, NOT the live Anvil server.
Nothing has run end-to-end on deployed infrastructure. Highest value per hour.

- Deploy microdata-api to Anvil; confirm the `sources` table auto-created the
  new columns (`enc_key`, `access_policy`, `local_mode`, `he_key`).
- E2E: encrypt a CSV → push to GitHub → register in deldata.html → run modes
  1/2/3 locally, a protected remote run, a strict-local run, and an HE run;
  negative tests (non-allowlisted user; tampered file; anonymous vs "anyone").
- Confirm `sync_to_api.py --apply` (now also builds the zip) → Anvil sync path.

**Gate for everything else** — building more on an unverified base compounds risk.

---

## 1. Verb consistency (the original questions)

### 1a. Project A — variable-level `import` + `create-dataset … join()` — **DONE** (was: effort L, brainstorm first)
Shipped 2026-07-05/06 — see the snapshot above. `# create-dataset panel,
key(pid)` then `# import h/income into panel` merges the column into `panel`
on `pid`, in every dialect mode, over real connected sources. Design record:
`docs/superpowers/specs/2026-07-05-variable-level-assembly-design.md`
("approved in dialogue", D1–D7).

Resolved (v1, per that design doc):
- `import` extracts by **load-whole-source-then-select** (D6) — no pushdown
  yet. Pushdown is the explicit subject of the follow-on design in §4 below.
- Join semantics: single key, left-onto-accumulator default, overridable
  inner/outer/left (D5).
- One `create-dataset` builds one named dataset; no `use <name>` switching in
  v1 (not needed — multiple `create-dataset` blocks coexist by name).
- Assembly runs where the data routes (browser for open/strict, server shim
  for protected/remote) — reuses existing grant-driven routing (D3).

Still open, carried into the follow-on design (§4): the `from X import Y`
alternative syntax (undecided), and the `<table>.<column>` path grammar for
duckdb sources — **owner has since indicated the dot form
(`alias/table.column`) is acceptable**, so that question is effectively
resolved in favor of dot; not yet reflected in the design doc's prose.

### 1b. Microdata-mode source parity — effort M
Microdata mode still rejects URLs and registered/encrypted sources (knows only
the SSB catalog + synthetic engine). Make `require`/`connect` there accept the
same sources as dialect modes. Removes the "microdata is the odd one out" wart.
Interacts with 1a (both touch microdata `require` routing) — sequence after or
alongside Project A's brainstorm.

---

## 2. Access-control completeness

### 2a. Access-request / grant workflow — effort M
When the audience check denies a caller, today they hit a dead-end message.
Add: denied user can request access; owner sees pending requests in deldata.html
and approves/denies (approval appends their email to `access_policy.emails`).
Closes the loop on the audience model just built. Self-contained; no brainstorm.

### 2b. Owner-supplied storage tokens (private repos) — effort M
The `credentials` seam from the 2026-06-29 safestat spec: register a source
whose bytes sit behind a private-GitHub token (or similar), stored Fernet-
wrapped like `enc_key`, used server-side to fetch, never handed to the client.
Lets owners keep data in private repos. Orthogonal to the crypto work.

---

## 3. Browser-STRICT rounding-out (from the browser-strict spec's deferred list)

- **polars-STRICT + duckdb-STRICT in the browser** — effort S/M. Both packages
  are in Pyodide; the engine already supports the dialects. Mostly wiring +
  the duckdb async seam (a known pattern from static-data mode).
- **Strict-local runs → remote quotas** — effort S. Currently logged but not
  counted against BUDGETS; wire in once real usage is observed.
- **"Release aggregate to session"** — effort M, small design question. Let a
  released, suppressed result become an open DataFrame for further free
  analysis in the same session.
- **Hybrid `#micro` + strict sources in one script** — effort M. Currently
  refused; would need the segment loop to route per-segment.
- **lifelines/pyfixest in the browser** — effort S. micropip where possible;
  degrade with a clear message otherwise.

---

## 4. Remote columnar sources — DuckDB/SQLite files + column pushdown

Full design: `docs/superpowers/specs/2026-07-06-remote-columnar-sources-design.md`
(draft, 2026-07-06). Reconciles with — and supersedes — this section's earlier
framing of "DuckDB-as-browser-store" as one speculative L-effort blob. It's
actually two separable pieces with very different cost/risk, and the design
doc's own §1→§3 order makes the split explicit: connecting to a source is a
prerequisite for pruning reads from it, not a side effect of the executor
swap.

### 4a. `.duckdb`/`.sqlite` as connectable source kinds — **DONE** (2026-07-06)
New source `kind`s, `kind()` directive option, dot-grammar `alias/table.column`
addressing, DuckDB-wasm table extraction feeding the (at the time) unchanged
pandas `safepy.assembly`. Shipped and verified live in a real browser —
`.duckdb` works correctly (including a real bug found and fixed: dangling
`ATTACH` catalogs across repeated extractions). **`.sqlite` does not work** —
not a bug in this codebase, a confirmed open upstream duckdb-wasm bug
([duckdb/duckdb-wasm#1972](https://github.com/duckdb/duckdb-wasm/issues/1972)):
`ATTACH ... (TYPE sqlite)` reports success but the table catalog comes back
empty. Reproduced identically across duckdb-wasm 1.29.0 (pinned), 1.32.0
(latest stable), and 1.33.1-dev (bleeding edge) — a version bump will not fix
this. Fallback if sqlite becomes a real need: **sql.js-httpvfs** as a
separate engine just for that case (design doc §9).

### 4b. DuckDB-backed assembly executor (network-level column/table pruning) — **DONE** (2026-07-06)
Replaced the "materialize whole source, then pandas" step with a real SQL
compiler (`js/assembly-duckdb.js`) that runs `import`/`join`/`create-dataset`
as pushdown queries directly against DuckDB-wasm — `read_parquet(url)`,
`ATTACH`, real `JOIN`s — only materializing the final named datasets.
Verified live through the actual app UI: a python-mode script joining a
parquet source with duckdb-table columns returned correct results, and the
browser's Network panel confirmed **`206 Partial Content`** responses for
both source files — genuine range requests, not full downloads. Falls back
to the existing pandas path automatically for anything that doesn't qualify
(protected/anvil sources, CSV, sqlite per 4a's finding). Full writeup,
including two real pre-existing Pyodide/pyarrow bugs found and fixed along
the way, in `docs/superpowers/plans/2026-07-06-remote-columnar-sources.md`.

---

## 5. Speculative / on-demand (only when a concrete need appears)

- **Remote-only enforcement by non-Anvil authorities** (federated / third-party
  registries) — effort L, speculative. The `/source_access` resolution step is
  the seam where another authority could answer later.
- **`auth(type, handle)` secret-handle mechanism** (2026-06-28 manifest spec) —
  effort M. A separate credential-indirection idea; does not collide with
  `key()`. Only if a concrete secret-store use case appears.
- **Per-column symmetric encryption** — not needed while decryption is local
  and whole-file. Parked.

---

## Recommended order

1. **§0 verify on deployed Anvil** — still not done, still the gate for
   trusting everything else (all the encryption/protection/STRICT-execution
   machinery is only tested against stubs/fixtures, never real infrastructure)
   — and more has been built on top of it since this was last flagged
   (Project A, remote columnar sources). Highest-value next step.
2. ~~§1a Project A~~ — **done**.
3. ~~§4a/§4b remote columnar sources~~ — **done** (duckdb+parquet; sqlite
   blocked on an upstream bug, see above).
4. **§2a access-request** + **§1b microdata parity** — cheap completeness wins,
   can run in parallel with §0.
5. **§3 browser-STRICT rounding-out** — as usage warrants (polars/duckdb strict
   is the most-requested-shaped).
6. **§2b private-repo tokens** — when an owner actually needs it.
7. **§5 speculative items** — only on concrete demand.
