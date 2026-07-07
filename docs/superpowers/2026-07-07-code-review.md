# Codebase review — 2026-07-07

Read-only review across `safestat` (index.html + JS modules + core Python
files), `safepy`, and `microdata-api`. No code was changed as part of this
review. Five parallel agents did the reading; the two most severe claims
below were independently reproduced/verified by hand before being written up
here — everything marked **VERIFIED** was actually run, not just read.

## How to read this document

1. §1 is the one section to act on regardless of anything else — two
   real disclosure-control gaps, both cheap to fix.
2. §2–§4 are ordinary bugs, grouped by repo.
3. §5 is duplication/cleanup — no urgency, but named specifically enough to
   act on directly.
4. §6 is feature ideas, ranked by how cheap they are given what already
   exists.
5. §7 is a recommended order of operations.

---

## 1. Two disclosure-control gaps — fix these first

These are the only findings in this review that touch the actual
suppression guarantees the whole system exists to enforce. Everything else
here is ordinary software-engineering feedback; this section isn't.

### 1a. `safepy`: `group_agg`/`group_agg_multi` suppress on row count, not non-null count — **VERIFIED, live individual-value leak**

`safepy/safepy/safe.py:195`:
```python
counts = df.groupby(by, observed=True)[value].size()
```
`.size()` counts every row in the group, including rows where `value` is
`NaN`. The suppression threshold (`min_n`) is checked against this count,
not against how many rows actually *contributed* a value. Reproduced
directly:

```python
policy = resolve_policy(['protected'], suppression='light')  # min_n = 5
df = pd.DataFrame({'grp': ['A']*5, 'salary': [100000.0, None, None, None, None]})
SafeVerbs(policy).group_agg(df, 'grp', 'salary', 'mean')
# -> Released(values=[100000.0], cells_suppressed=0)
```
One real value, four `NaN`s, group size 5 clears `min_n=5` — the single
individual's raw salary is released as the "mean," completely unsuppressed.

The same flaw exists in `polars_api.py`'s `_native_group_agg` (`pl.len()`,
same issue) and in the HE plane's `_group_rows`/`blind_group_agg` (row/mask
count, not non-null count) — **3 of 4 backends**. It does *not* exist in
`pivot_table` (`safe.py:351`, which computes a separate `aggfunc="count"`
table) or in `duckdb_api.py:264-267` (which explicitly emits SQL
`COUNT(value)`, and SQL `COUNT()` skips `NULL`s) — proof this is a bug, not
a deliberate design choice, since two of the four backends already get it
right.

**Fix**: swap `.size()` for `.count()` (pandas/polars) and the HE row-count
for a non-null mask-sum, everywhere the result feeds a suppression decision
— except the `agg="size"` verb itself, where counting rows is the point.

Two related, smaller gaps in the same area, worth fixing in the same pass:
- **`SafeFrame.describe()` skips winsorization that `SafeColumn.describe()`
  applies** (`safeframe.py:1186-1198` vs `580-600`) — frame-level `.describe()`
  uses the raw mean/std; column-level winsorizes first. A user gets a less
  protected result by calling `df.describe()` instead of `df['col'].describe()`.
- **`.median()` doesn't get the order-statistic support check that
  `.quantile(0.5)` gets** (`safeframe.py:504-542` vs `285-302`) — `_order_stat`'s
  own docstring specifies the correct rule (`min(#≤v, #≥v) ≥ min_n`);
  `_reduce("median")` only checks the plain count, which for `n≈k` gives
  roughly half that support.

### 1b. `protect.py`: the deployed server copy is missing three correctness fixes already made in safestat's local copy — **VERIFIED**

There are three copies of `protect.py` in play:
- `~/Documents/GitHub/protect/protect.py` (2101 lines) — the standalone
  "canonical" repo; `safepy`'s `pyproject.toml` installs from here via git.
- `safestat/protect.py` (2191 lines) — a locally-patched fork with three
  real fixes made between 2026-06-13 and 2026-07-03.
- `microdata-api/server_code/protect.py` — the one actually running against
  real register microdata on the server. **Confirmed byte-identical to the
  old `protect` repo** (2107 lines = 2101 + a 6-line "generated copy" banner
  that `sync_to_api.py` adds) — none of safestat's fixes are present.

The three fixes missing from the deployed copy (confirmed by diffing the two
repos directly):
1. **Rank-swap used a raw row index as a rank position.** The old `swap`
   verb picked a "nearby" swap partner using the random row's raw index
   `i` directly as if it were a value-sorted rank; the fix computes an
   actual `rank_pos` array and indexes by that. The deployed version's
   swap partners are not reliably close in value — a weaker disclosure
   control than intended, silently.
2. **Dominance-rule (p-percent) check crashes on 1 contributor, and
   silently mis-suppresses on 2.** Old code: `if len(contribs) < 3: ...
   x1, x2 = contribs[0], contribs[1]` — raises `IndexError` on exactly 1
   contributor. The fix short-circuits on an empty list and makes
   `len(contribs) < 3` an unconditional suppress trigger (1–2 contributors
   is maximally disclosive and must always suppress, not only when
   `sum_rest==0`).
3. **`k_anonymize` never verified its own postcondition.** The old version
   could return data that isn't actually k-anonymous after
   `max_iterations`, with only a log line; the fix calls `risk()` after the
   loop and raises if `k_min < k`.

`sync_to_api.py:19-20,160-161` hardcodes the source of these fixes to a
path *outside version control* (`PROTECT_ROOT = HERE.parent / "protect"`,
i.e. the sibling repo, not `safestat/protect.py`) — so even a re-run of the
sync script would keep deploying the old code. `safepy`'s own
`pyproject.toml` has the identical problem (installs from the same stale
git repo).

**Fix**: port the three fixes from `safestat/protect.py` into the
`protect` repo (or better, make `protect` the single source of truth and
have safestat import it instead of forking), then re-run
`sync_to_api.py --apply`. Cheap — the fixes already exist and are already
tested in safestat's copy; this is a sync/deployment problem, not a design
problem.

---

## 2. `safestat` frontend (index.html + JS) — other bugs

1. **Missing English translations for every recently-added strict-execution
   and R-bridge error message.** At least 7 strings (e.g.
   `index.html:8463/8480`, `:8583`, `:7673-7674/7714`, `:9152`, `:9219`,
   `:9224`) have no entry in `js/i18n/en.js`. `t()` silently falls back to
   raw Norwegian when a key is missing (`js/i18n.js:46-60`), so an
   English-locale user hits untranslated Norwegian text on exactly the
   guardrail messages introduced most recently.
2. **`AssemblyDuckdb.compile()` can reject a valid join depending on
   declaration order** (`js/assembly-duckdb.js:56-91`). It orders datasets
   by "loads first, then creates in original script order" rather than a
   real topological sort; `parseAssembly` only checks that a joined-from
   dataset exists *anywhere* in the script, not that it's declared first.
   A script with `create-dataset B` before `create-dataset A`, where B
   later joins A, parses fine and then fails at pushdown-compile time
   (`"ukjent datasett «A» (join into «B»)"`, line 85) — a silent capability
   regression specific to the new DuckDB-pushdown path.
3. **"Be om tilgang" (request access) button can be double-clicked into
   sending duplicate requests** (`renderAccessDeniedError`,
   `index.html:5113-5128`) — I wrote this earlier in this same session.
   The button is only disabled inside the success callback (line 5124),
   not immediately on click, so a double-click before the network
   round-trip resolves fires two `POST /access_request` calls. Low
   severity (the backend already dedupes by email, per `access_requests.py`
   §3), but a one-line fix (`disabled = true` at the top of the handler).
4. **Stale comment pointing at the wrong line range** — `index.html:9266-9267`
   claims the pyarrow patch is "already applied" around line 7031-7048;
   that range is actually inside the plot-rendering helper. The real
   duplicate is in `_run_duck_sql` at `index.html:7186-7206`. Anyone
   following the comment to debug/dedupe the patch lands in the wrong code.

## 3. `microdata-api` — other bugs

1. **Read-modify-write races with no transaction anywhere in the codebase**
   (`grep -rn transaction server_code/` returns nothing). Two concrete
   instances: `access_requests.py:164-166`/`:194-195` (`pending_requests`
   list — a request landing between an owner's read and write in
   `/access_request/decide` can be silently clobbered), and the
   pre-existing `auth.py:213-217` (`shared_use_count` — concurrent
   redemptions of a shared code can each read the same stale count, so
   `max_uses` can be exceeded — a real quota bypass for the exact
   workshop-shared-code scenario this field exists for).
2. **`/access_request` doesn't check `caller_allowed` before queuing**
   (`access_requests.py:164`) — a caller who already has access (owner,
   listed, or an "anyone"/"authenticated" audience) can still trigger a
   pending entry and an owner-notification email; approving it is then a
   silent no-op that looks like it did something.
3. **`/access_request/decide` doesn't verify the email being
   approved/denied was ever actually pending** (`access_requests.py:194-198`)
   — an owner can approve an arbitrary email with no record it was
   requested. Not exploitable beyond what re-registration already allows,
   but it silently bypasses the auditable "request" step if that step is
   meant to be load-bearing.
4. **Best-effort `try/except: pass` wraps more than just the "send" step**
   in two places — `access_requests.py:135-148`'s `_notify_owner` wraps
   only the email send (fine), but `auth_endpoints.py:98-107` wraps *both*
   `auth.issue_magic_code` (a table write) and the send in one block. If
   code issuance itself throws, the response is still `{"ok": true}` and no
   code was created — indistinguishable from "check your spam folder."

## 4. `safestat` core Python files — other bugs

1. **`m2py_protection.py`'s hardcoded preset fallback has no automated
   check against `safepy.policy.PRESETS`**, despite its own comment saying
   it "MUST mirror" that dict. A future preset change in safepy silently
   goes stale in the Pyodide/test fallback path.
2. **`PandasProtect.suppress`'s model-suppression branch has a bare
   `except Exception: return result` catch-all** for any model shape other
   than the one it explicitly handles (statsmodels) — a future model
   wrapper could silently return unsuppressed output on a code path change
   rather than failing loudly.

---

## 5. Simplification / duplication

Grouped by the concrete cost of each, not just "this looks repeated."

**`safestat` (index.html)**
- The pyarrow install+patch logic (`ensurePyarrowFor`, `index.html:8437-8457`)
  is reimplemented inline two more times — `_run_duck_sql`
  (`:7186-7206`) and the `btnRun` handler's `_needsParquetSupport` block
  (`:9260-9287`, a near line-for-line copy). A future fix to the
  ArrowKeyError workaround needs three edits to land everywhere; missing
  one silently reintroduces the bug in that one path.
- The base64→tempfile→`nanoparquet::read_parquet`→cleanup R snippet (from
  this session's R-bridge-to-Parquet work) is duplicated verbatim between
  the assembly path (`:7704-7708`) and the `#micro` segment path
  (`:7821-7824`) — a 5-line `injectParquetIntoR(webR, varName, bytes)`
  helper removes both copies.
- R-mode's "resolve datasets for this run" logic (`:7668-7716`) is a
  hand-copied, capability-reduced subset of the same logic already shared
  by Python/DuckDB mode (`:9089-9147`) — it has no DuckDB-pushdown option
  and hardcodes its own (untranslated, see §2.1) error strings instead of
  reusing the shared ones. This is why item 5 in §6 below ("R assembly +
  strict/pushdown parity") is possible at all — the two paths already do
  the same thing, just not through the same code.

**`safestat` (core Python)**
- `mockdata_core.py`'s own docstring already flags its duplication of
  constants (`_DEMO_REF_YEAR`, `_NORWAY_LATENT_*`) that are also defined in
  `m2py.py:1028-1037`, "for now," pending a cleanup pass that never
  happened. Self-acknowledged, cheap, low-risk to finish.
- No fully dead modules were found — every file reviewed (`protect.py`,
  `m2py_protection.py`, `mockdata_core.py`/`mockdata_realism.py`,
  `statx_runner.py`, `duckdb_bridge.py`, `m2py_translate.py`,
  `functions.py`) has at least one confirmed live importer.

**`safepy`**
- The "count of contributing rows" computation now exists four separate
  times with no shared contract (pandas `.size()`, polars `pl.len()`, SQL
  `COUNT()`, HE row-count) — precisely how the §1a bug crept into two of
  the four independently. A single documented "non-null contributing
  count" helper, implemented once per backend against one shared test,
  would prevent this recurring.
- `_frame_reduce`/`describe`/`SafeColumn._reduce` re-derive the same
  winsorization/rounding logic inline in three places; the describe/reduce
  divergence in §1a is a direct symptom of this rather than a one-off typo.

**`microdata-api`**
- `_json`/`_load_body`/`_cell`/`_audit` are copy-pasted near-verbatim
  across `owner_sources.py`, `access_requests.py`, `api_endpoints.py`,
  `auth_endpoints.py`, and `admin_sources.py`/`admin_audit.py` (5 copies of
  `_json` alone). A shared `server_code/http_utils.py` removes roughly 80
  duplicated lines and closes the risk of one copy silently drifting from
  the rest.

---

## 6. Feature ideas, ranked by how cheap they are

The frontend feature-opportunity scan found a consistent pattern worth
naming up front: **several of the cheapest possible next features are
already named in the code's own comments** — `index.html:9219` says
`"strict-kilder støttes foreløpig i python/r — ikke duckdb-modus"` and
`index.html:7674` says `"strict-/kryptert-kilder med montering i R-modus
støttes ikke ennå"` — both sitting directly next to a sibling
implementation that already works.

1. **Cache fetched source bytes across runs, not just within one run.**
   `js/data-loader.js`'s registry-JSON cache (`_registryCache`) is already
   module-scoped and persists across runs; the actual fetched-bytes cache
   (`_bufCache`) is a local var scoped to a single call, so every Run
   re-downloads and (for duckdb/sqlite) re-extracts from scratch. Given
   how often scripts get re-run during iteration, this is likely the
   single highest-frequency friction point in the whole app. Hoist
   `_bufCache` to module scope, keyed by resolved URL, mirroring the
   pattern that already exists one line above it.
2. **Let DuckDB mode run strict-graded sources, matching Python/R.** The
   strict pipeline is already dialect-parameterized (`'python'`/`'r'`);
   DuckDB mode already shares Python's materialization code path. Add
   `dialect: 'duckdb'` alongside the existing branch.
3. **Let R-mode's assembly (`create-dataset`/`import`/`join`) accept
   strict/encrypted sources, matching Python's assembly.** Python's
   assembly path already threads strict sources through
   `runStrictLocal(..., spec: _asmSpec)`; R's non-assembly path already
   supports strict. This combines two already-working branches for R the
   way Python already combined them — directly enabled by fixing the
   duplication named in §5 above.
4. **Notify the requester when access is granted**, not just "request
   sent." Today the only way to find out is to blindly re-run the script.
   `fetchSourceAccess` already returns cleanly once approved — poll
   `/source_access` every ~20s after submitting and swap the status text,
   reusing the existing fetch. (Backend-side: also add the symmetric
   requester-notification email next to the existing owner-notification
   one in `access_requests.py`, and consider exposing request/decision
   *history* to the owner — the data is already written to `audit_log`,
   it just isn't queried back out anywhere.)
5. **Surface pending access requests inside the main app**, not only on
   `deldata.html` — a small badge/menu item on login using data
   `/sources/mine` already returns.
6. **Route SafeStat mode's ad-hoc URL fetch through the shared
   `DataLoader`** instead of its own hand-rolled regex fetch
   (`index.html:8725-8749`) — it currently silently ignores `key()`,
   `kind(duckdb|sqlite)`, encrypted envelopes, and strict grants, none of
   which apply in this one mode even though the shared pipeline (reused by
   three other modes this session) already supports all of them.
7. **A `revoke_email` endpoint symmetric to `grant_email`** in
   `access_requests.py` — today an owner can only remove access by
   re-running the full `/sources/register` with a trimmed email list.
8. Explicitly **not cheap**, flagged so it doesn't get bundled into any of
   the above by accident: full `connect`/`load` directive support in
   microdata-DSL mode (a different execution engine, not a small patch);
   unifying `mockdata_realism.py`'s Norway-specific model with a
   general per-country config; the HE-plane's missing-value gating fix
   (mirrors §1a but needs an extra homomorphic decrypt step per group).

**Status update, 2026-07-09 — items 1–6 all DONE:**
- 1 (cross-run byte cache), 2 (DuckDB-mode strict), 3 (R-mode assembly +
  strict/pushdown parity) — shipped in a run of follow-through work this
  session. Item 2 needed more than the one-line dialect swap the estimate
  assumed: `dialect="duckdb"` has no Pyodide wheel on this app's
  then-pinned v0.29.3, which led to first building a whole new
  `dialect="sqlite"` (safepy) as the interim path, then a full Pyodide
  v0.29.3 → v314.0.2 upgrade (real duckdb 1.5.1 + bundled sqlite3), which
  is what item 2 actually runs on now — `dialect="sqlite"` remains
  available in safepy, just no longer index.html's automatic default.
- 4 (notify requester) + 5 (surface pending requests in the main app) —
  shipped together: `access_requests.py` gained `_notify_requester`
  (email, symmetric to the existing `_notify_owner`), and `index.html`'s
  "Del data" menu item now shows a pending-request count badge (reuses
  `/sources/mine`, no second approve/deny UI built — clicking through to
  `deldata.html` still does the actual decision).
- 6 (SafeStat's ad-hoc fetch) — shipped: extracted
  `DataLoader.fetchResolvedItems(items, deps)` out of
  `resolveAndFetchLoads` so SafeStat mode's `require` statement (a real DSL
  statement, not a "#"-prefixed directive `DataDirectives.parse` can see)
  can reuse the same fetch/decrypt/cache machinery instead of a second,
  narrower hand-rolled `fetch()`. Verified live: a real CSV over an
  extensionless URL using `kind(csv)` now works — impossible before.
- **Item 8's HE-plane sub-claim was already stale when written**: the
  HE-plane missing-value gating fix landed in the *same* commit as the §1a
  plaintext fix (`safepy` commit `a3999da`, 2026-07-07) —
  `HEAuthority.group_agg` already decrypts the homomorphic mask-sum and
  gates on non-null contributing count before ever decrypting sum/sum²,
  for every aggregate except `size`. Tested
  (`tests/test_group_agg_nan_suppression.py`'s
  `test_he_group_agg_suppresses_on_non_null_count` /
  `..._sum_suppresses_on_non_null_count` /
  `..._size_still_reports_raw_row_count`, all passing). Nothing to do here;
  re-verified 2026-07-09 by direct investigation, not by trusting this doc.
- **On hold, by explicit request (2026-07-09)** — not abandoned, just not
  being picked up right now: item 8's other two sub-items (full
  `connect`/`load` in microdata-DSL mode; generalizing
  `mockdata_realism.py` beyond Norway-specific), and item 7 (`revoke_email`
  endpoint symmetric to `grant_email` — noted here but never actually
  started). Also still open, unrelated to this list: the upstream
  duckdb-wasm bug blocking client-side `.sqlite` table extraction
  (duckdb/duckdb-wasm#1972, see `docs/superpowers/2026-07-05-remaining-
  roadmap.md` §4a) — third-party, not fixable from this repo.

---

## 7. Recommended order of operations

1. **Fix the two disclosure-control gaps in §1** first, in isolation from
   everything else in this document. Both are small, well-understood
   patches with an existing reference fix to copy from (protect.py) or a
   one-line swap (`.size()` → `.count()`). Add a regression test for the
   exact reproduction in §1a before merging the fix, and add the
   protect-repo content-hash check mentioned in §1b so this class of
   "deployed copy silently diverges from the fixed copy" can't recur
   unnoticed.
2. Fix the microdata-api races in §3.1 (add `anvil.tables.transaction`
   around the pending-request and shared-code-redemption read-modify-write
   sequences) — small, mechanical, and closes a real quota-bypass.
3. Sweep the remaining §2/§3/§4 bugs — none are urgent individually, and
   most are one-line fixes (missing i18n keys, the double-click guard, the
   stale comment, the `caller_allowed` pre-check).
4. Take the §5 duplication items as a single cleanup pass once the above
   land — several of them (the R-mode resolve-datasets duplication
   especially) are exactly what's blocking §6 items 2–3, so fixing
   duplication and shipping features can be the same commit.
5. Pick up §6 features in the order listed — 1 (result cache) is the
   highest-leverage, lowest-risk one to do first; 2–3 (strict/pushdown
   parity for DuckDB and R) are natural follow-ons once §5's duplication
   is resolved; 4–5 (access-request loop-closing) directly finish the
   feature shipped earlier in this same session.
