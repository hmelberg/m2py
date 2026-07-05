# Remaining roadmap — access control + verb consistency

Date: 2026-07-05
Status: planning map (not a build plan). Effort: S ≈ hours, M ≈ 1–2 days, L ≈ needs its own brainstorm+spec.

Snapshot of what's DONE this cycle (all on `main`/`master`):
- Unified `connect`/`load` grammar; `require` kept as legacy alias.
- Encrypted external sources (`safepy-enc-v1` AES envelopes; three key modes).
- Protection levels + `local_mode` (none/strict/open); grant-driven routing.
- Browser-STRICT execution V1–V4 (safepy in Pyodide; per-run authorize/log;
  decrypt-at-run; worker isolation).
- Audience model (owner/listed/authenticated/anyone) enforced local + remote.
- Self-service registration incl. AES + HE artifacts (deldata.html).

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

### 1a. Project A — variable-level `import` + `create-dataset … join()` — effort L, BRAINSTORM FIRST
The headline unbuilt piece; directly answers the original design questions.
Today: microdata mode assembles datasets variable-by-variable with an implicit
person-id; dialect modes (py/r/duckdb) only `load` whole tables. Unify them:
`# create-dataset panel, join(pid)` then `# import h/income as inc` merges the
column into `panel` on `pid`, in every mode, over real connected sources.

Open design questions (why it needs a brainstorm, not just a plan):
- How `import` extracts one column from a connected source: load-whole-then-
  select (simple) vs parquet/duckdb column pushdown (lazy) vs server-side
  extraction for protected/remote sources.
- Join semantics: inner/outer/left; the emulator's `import` already has
  `outer_join`/`inner_join` — reconcile with an explicit `join(col)`.
- Multiple `create-dataset` blocks + `use <name>` switching — extend the
  emulator's model to dialect modes, or a fresh uniform model.
- Browser pandas-merge vs compute-to-data for protected sources.
- Grammar was already reserved in the encrypted-sources spec so it won't
  collide with connect/load.

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

## 4. Speculative / on-demand (only when a concrete need appears)

- **DuckDB-as-browser-store / lazy column pushdown / `ATTACH`** — effort L.
  The "radical" idea. Revisit only if files outgrow browser memory; the v1
  benefit is near-zero because encrypted data must be fully decrypted locally
  anyway.
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
2. **§1a Project A brainstorm** — the real verb-consistency payoff; kick off the
   design while §0 runs.
3. **§2a access-request** + **§1b microdata parity** — cheap completeness wins.
4. **§3 browser-STRICT rounding-out** — as usage warrants (polars/duckdb strict
   is the most-requested-shaped).
5. **§2b private-repo tokens** — when an owner actually needs it.
6. **§4** — only on concrete demand.
