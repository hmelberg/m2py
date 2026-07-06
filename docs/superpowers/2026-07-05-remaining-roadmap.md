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

### 4a. `.duckdb`/`.sqlite` as connectable source kinds — effort M, do this first
New source `kind`s (`duckdb_url`, alongside existing csv/parquet/json), an
explicit `kind()` directive option to bypass fragile sniffing, and a
`load db/table as x` path (dot grammar for `table.column`, per the owner's
2026-07-06 confirmation — resolves the design doc's §10/open-questions dot-
vs-slash question). Whole table/column is still materialized via the
existing duckdb-wasm engine and handed to the **current, unchanged pandas
`safepy.assembly`** (D6's "load-whole-then-select" already covers this — no
network-pruning yet, just a new source type). SQLite rides the same
`ATTACH '<url>' (TYPE sqlite)` mechanism at near-zero incremental cost (design
doc §9). Low risk: doesn't touch the tested assembly executor at all.

### 4b. DuckDB-backed assembly executor (network-level column/table pruning) — effort L, do this after 4a, on demand
Replaces `safepy.assembly`'s pandas implementation with a DuckDB engine so
`import`/`join`/`create-dataset` compile to pushdown queries
(`read_parquet(url)`, `ATTACH`, `SELECT <col> FROM ...`) instead of a full
download — design doc §3. This is the part that's genuinely risky (replaces
shipped, tested code) and genuinely speculative in value: the benefit is
"skip downloading bytes you don't need," which only matters once a source is
large enough that full-download-then-select is actually slow or memory-
heavy. That trigger condition — files outgrowing browser memory / download
time becoming a real complaint — hasn't been confirmed as live yet, so this
stays gated on demand, same as the original assessment. Do not start this
before 4a ships, since 4a's `.duckdb`/`.sqlite` source support is exactly
what 4b would prune reads from.
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

1. **§0 verify on deployed Anvil** — unblocks trusting everything else.
2. ~~§1a Project A brainstorm~~ — **done**, see snapshot above.
3. **§4a `.duckdb`/`.sqlite` source kinds** — the concrete, low-risk half of
   the new design doc; delivers "connect to duckdb/sqlite via URL and import
   columns from them" without touching the tested assembly executor.
4. **§2a access-request** + **§1b microdata parity** — cheap completeness wins.
5. **§3 browser-STRICT rounding-out** — as usage warrants (polars/duckdb strict
   is the most-requested-shaped).
6. **§2b private-repo tokens** — when an owner actually needs it.
7. **§4b DuckDB-backed assembly executor (network pruning)** — only once a
   concrete need appears (large files, real download-time complaints); still
   gated on demand, per the original assessment — just no longer bundled with
   4a's independent, lower-risk source-kind work.
