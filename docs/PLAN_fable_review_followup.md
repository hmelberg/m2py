# Follow-up plan — Fable 5 code review (outstanding items)

Status snapshot: 2026-06-13. This plan covers only items from the Fable 5 review
that are **still outstanding** after the fixes already committed (engine
silent-wrong sweep, performance pass, py2m/r2m Phase 0–4, equivalence harness,
`.gitignore`/CI core). Each item was re-verified against current code before
inclusion. Line numbers are approximate (the files have since shifted) — search
by content.

Conventions: Python fixes get a failing test first (TDD), using `tests/` +
`tests/test_equivalence.py`. JS/edge fixes lean on manual verification. Commit
to `dev` on request.

---

## Phase 1 — Security batch (edge functions + microdata-api + frontend XSS)
Attacker-reachable today; highest leverage.

Slices A + B DONE (commit, this repo). Slice C (companion repo) still open.

- [x] **netlify/edge-functions/_lib/auth.ts** — extracted `gate()`; all three
      handlers use it. Timing-safe compare, rate-limit-before-Anvil ordering,
      Anvil 4s timeout, 5-min positive-validation cache, x-forwarded-for fallback
      dropped. Tests: _lib/auth.test.ts.
- [x] **rate-limit.ts** — fails open on Blobs error (was 500-storm); store
      injectable; race documented. Tests: _lib/rate-limit.test.ts.
- [x] **dm-vurder.ts** — ordering + timing-safe + timeout now via gate().
- [x] **dm-vurder.ts prompt injection** — script fenced; `// personvern:`
      comments reframed as claims to evaluate, not instructions.
- [x] **anthropic.ts** — fetchWithRetry (30s timeout, 429/529 retry/backoff);
      upstream error bodies logged server-side, not echoed. Tests: _lib/anthropic.test.ts.
- [x] **widgets/forklar-widgets.js** — `sanitizeMarkup()` strips script/iframe/
      object/embed/on*/javascript:/svg-foreignObject before innerHTML. Browser-verified.
- [x] **index.html escapeHtml** — already escapes `"`/`'` for attribute context (verified, no change).
- [x] **Cost rider** — `system` + `cache_control` prompt caching added to
      dm-vurder.ts and tolk-resultat.ts.
- [x] CI: `.github/workflows/edge-tests.yml` runs `deno check` + `deno test`.
- [ ] MINOR (deferred): m2py.py splices `tabulate` var names into tablehtml
      `data-var1/2` attributes unescaped (~L8774). Var names are identifiers so
      low risk, but html-escape for defence-in-depth.

### Phase 1 — Slice C (companion repo `microdata-api`, branch admin-shared-codes) — DONE
Committed + pushed to microdata-api (separate Anvil deploy). Runtime behaviour
confirmable only on deploy; verified locally via py_compile + pure window logic.
- [x] **auth_endpoints.py** — `/auth/email/request` rate-limited per-email
      (5/h) + per-IP (30/h) before issuing/sending; `/auth/email/verify`
      per-IP (30/10min). Magic codes kept multi-use/30-day (deliberate
      multi-device UX) — rate-limiting is the mitigation, not single-use.
- [x] **utils.py** — constant-time API-key compare (`hmac.compare_digest`);
      `check_rate_limit` now takes max_calls/window_sec + logs failures (no
      longer silent fail-open); `log_request` truncates question/script to
      4000 chars; `purge_old_eval_runs(90d)` retention helper (wire to an
      Anvil Scheduled Task; not client-callable).
- [ ] TODO (Anvil IDE, manual): create the daily Scheduled Task that calls
      `utils.purge_old_eval_runs`.

## Phase 2 — Disclosure-control & remaining engine correctness  ← STARTING HERE
The "researchers trust this for analysis + privacy" batch. Strong TDD fit.

Feature (requested 2026-06-13): **disclosure control optional, default OFF.**
- [x] Flipped default to OFF in m2py.py (`_is_disclosure_control` fallback `'0'`,
      directive-save fallback) and in index.html (`getDisclosureControl`, the
      apply-to-Python fallback, prev-value defaults, menu placeholder label).
      The hamburger switch (`menuDisclosureControl`) and the `// m2py:
      disclosure-control=on` / `dc=on` directive already existed — both verified.
      Tests: test_default_disclosure_control_is_off, test_directive_can_turn_disclosure_on.
      NOTE for Phase 5: decide whether the microdata-api copy keeps default ON
      (it validates scripts against platform restrictions).

m2py.py:
- [x] **`tabulate …, summarize()` bypasses small-cell disclosure check** — DONE.
      Extracted `_t5_small_cell_check()`; summarize volume tables (1D + crosstab)
      now run T5. Tests in test_silent_errors.py::TestTabulateSummarizeDisclosure.
      (Also fixed a test-isolation leak in test_equivalence.py.)
- [x] **lone-dot → np.nan rewrite corrupts string literals** — DONE. Added
      `_split_quote_segments`; dot comparison-check + np.nan rewrite now skip
      quoted text. Tests in test_regressions.py::TestLoneDotQuoteAware.
- [x] **for-each expansion raw substring replace** — DONE. Word-boundary regex
      substitution. Tests in test_regressions.py::TestForEachWordBoundary.
- [x] **destring `force`** — DONE. Without force, non-numeric values now abort
      the operation with a clear error (per manual); with force → missing. Real
      missing (NaN) is not treated as non-numeric. Tests: TestDestringForce.
- [x] **configure seed/alpha/cache write-only** — DONE (honest-logging variant).
      Values are still recorded but the log now says "(lagret, men påvirker ikke
      beregninger ennå)" instead of the misleading "Satt seed = 42". FOLLOW-UP:
      actually wire alpha→ci/regress and seed→sample if desired. Tests:
      TestConfigureHonest.
- [x] **nested `for … end`** — DONE. Detected during body collection and
      rejected cleanly with one FEIL pointing to the `;` multi-level syntax;
      the outer loop is skipped depth-aware so the body never partially runs
      (fixed in both run_script and run_script_async). Tests: TestNestedForRejected.
- [x] **top-level error message** — DONE. Now includes the exception type:
      `FEIL PÅ KOMMANDO 'x' (ValueError): …`. Test: TestCommandErrorMessage.

protect.py:
- [x] **_profile_k_anonymize** — DONE. Recomputes `risk()` after the loop; if
      `k_min < k` it logs a FAILED entry and raises ValueError instead of
      returning non-anonymous data silently. Test: TestKAnonymizeVerifiesTarget.
- [x] **rank swap wrong axis** — DONE. Builds the inverse permutation
      (`rank_pos`) so the random row index maps to its rank position; the swap
      window now holds the proximity guarantee on unsorted data. Test:
      TestRankSwapProximity (max rank-displacement 817→≤window).
- [x] **RiskReport t_max** — DONE. Implemented t-closeness as max total-variation
      distance per equivalence class against the global sensitive distribution.
      Test: TestTClosenessComputed.
- [x] **plot-jitter unseeded RNG** — DONE. `_suppress_plot` takes `random_state`
      and uses `_resolve_random_state`. Test: TestPlotJitterSeeded.
- [x] **verbs silently ignore share/unit_id** — DONE. coarsen/year/month reject a
      non-default `share` via `_reject_inert_share` (partial application of a
      deterministic verb → inconsistent data). unit_id/random_state stay
      documented-inert. Test: TestDeterministicVerbsRejectPartialShare.

## Phase 3 — Mock-data correctness & consistency (all of report §2)
Self-contained; governs whether generated data is reproducible/trustworthy.

- [x] Seed on `short_name` + date, not alias — DONE. `import X as y` now gives a
      person the same values as `import X` (alias-independent), while the SAME
      variable at different dates still varies (date is the legit differentiator,
      not the alias — caught a sankey regression when seeding on short_name alone).
      Fixed person path + multi-record path. Tests: TestAliasSeedConsistency.
- [x] NPR UTDATO can precede INNDATO — DONE. INNDATO is now deterministic per
      (person, episode) via `_norway_npr_inndato_days`; UTDATO derives the same
      baseline so UTDATO ≥ INNDATO regardless of import order. Tests: TestNprConsistency.
- [x] NPR gender from income latent-z — DONE. Uses `_norway_synth_kjonn_from_uid`
      so childbirth (O80) only lands on real females. Test in TestNprConsistency.
- [x] `_generate_variable_values` drifted from `generate()` — DONE (targeted,
      safe fix). The concrete symptom — multi-record entities (jobb/kjøretøy/
      kurs) getting RANDOM birth years instead of the deterministic per-person
      ones — is fixed by mirroring the main path's `_norway_demo_birth_year_from_uid`
      logic in the date:yyyymm branch. Test: TestMultiRecordDeterministicDates.
      NOTE: deliberately did NOT do the full "merge the two large methods into one
      shared helper" — that's pure maintainability with high regression risk and
      is better done as a dedicated refactor behind golden-output tests. Deferred.
- [x] `_generate_panel` corrupts zero-padded codes / crashes on alphanumeric —
      DONE. Added `_coerce_code_value` (mirrors the main path): alfanumerisk codes
      stay strings, numeric → int, non-numeric never crashes. Tests: TestPanelCodes.
- [x] Silent metadata/codelist load failure — DONE. Engine records fallbacks;
      interpreter logs a visible ADVARSEL after import (demo labels/distributions
      may differ from the real register). Tests: TestSilentMetadataFallback.
- [x] BONUS: manual-runner FEIL detection now matches the error-line prefix, not
      any "feil" substring (base64 figure payloads tripped false positives).
- [ ] Static build hard-codes 2023 (mockdata_export.py ~L1198); dead persons keep
      wealth/municipality post-death; date grid enumerates past valid_to (~L1309).
- [x] build_static_data.py additive writes — DONE. Cleans *.parquet/*.csv/*.duckdb
      first; manifest records every CLI arg (build_args). Verified with a small build.
- [x] static_source.py `LIMIT n` → `WHERE unit_id <= n` — DONE. Person universe is
      now exactly {1..n}, consistent with the entity `ref_col <= n` filter.
      Tests: TestStaticSourceLimit.

Phase 3 status: COMPLETE (9/9). The full generate()/_generate_variable_values
method merge was intentionally deferred (maintainability only, high risk) — the
behavioral drift it caused is fixed.

## Phase 4 — Frontend robustness
Non-security UX/reliability (index.html unless noted). Browser-verified via Chrome
DevTools (no JS unit harness).

- [x] Pyodide + `__ensureDuckDB` bootstrap races — DONE. Memoized the in-flight
      promise (cleared on failure for retry). Browser-verified: app boots + runs.
- [x] TTS tutorial hang — DONE. resume() keep-alive + length-based fallback
      timeout; male-voice regex uses word boundaries (`\bmale\b`) so it no longer
      matches "female"/"woman" (browser-verified).
- [x] GitHub save cross-branch overwrite — DONE. doSave() routes a repo OR branch
      mismatch to "Save As".
- [x] dm-vurder SSE error masked as success — DONE. Flag + break + return; no
      "Ferdig" on a server error.
- [x] stdout/stderr restore — DONE. Both run handlers restore setStdout/setStderr
      in `finally` (error paths too).
- [x] Plotly + WebR purge — ALREADY DONE (earlier leak commit): purgePlots() purges
      `.plotly-container` before every clear; WebR shelter purged in finally. Verified.
- [x] forklar-widgets 60ms setInterval leak + quiz soft-lock — DONE
      (pollAbort returns cancel; correctIndex clamped).
- [x] Line-number gutter — DONE. One delegated handler; add/remove only trailing
      spans (browser-verified: span count tracks lines, breakpoint toggle works).
- [x] Smalls — DONE: `res.json()` parsed defensively before `res.ok`; dead
      `? 'no':'no'` ternary removed; sw.js stops caching opaque responses + never
      resolves respondWith to undefined (CACHE v3→v4).
Phase 4 status: CLOSED. The high/medium-value items above are done and
browser-verified. The remaining tail (below) is consciously NOT being done —
all low-value error/edge paths, deemed not worth the change + verification cost.

- [~] WON'T DO (diffuse, error-path AI-stream robustness; all LOW value):
      (a) release the fetch reader in a finally on the AI streams (~L9709/L9801)
          — leaks a connection only on an error mid-stream;
      (b) request-token guard so a stale async response can't repaint a closed
          modal — rare visual glitch (fast open/close/reopen);
      (c) flush the trailing SSE buffer — drops the last event only if the stream
          ends without a final `\n\n` (the edge anthropic.ts always emits one);
      (d) AbortController on the Anvil AI path — DEPRIORITIZED: the user notes the
          direct-Anvil AI path is rarely used (the Netlify edge path is the norm
          and already has an AbortController), so the ~3-min hang is largely moot.
      Harder to verify (need to induce failures); fine to leave as a focused follow-up.

## Phase 5 — Cross-repo sync & hygiene cleanup
Lowest risk; run after Phases 2–3 so engine fixes are captured.

- [x] `sync_to_api.sh` — DONE. Copies m2py.py + functions.py to
      microdata-api/server_code/ with a "GENERATED COPY — edit in m2py" header;
      `--check` mode for drift detection (exit 1). Caught up the full ~2113-line
      drift; synced copies py_compile + import cleanly (MicroParser/MicroInterpreter).
      DECISION: synced verbatim, so the API validator now defaults disclosure OFF
      — correct, because its dry-run uses only 200 rows (`_DRY_RUN_DEFAULT_ROWS`);
      with disclosure ON the population rules (T1>=1000) would falsely reject
      valid scripts. No disclosure pin added. (CI guard: `--check` can be wired
      into a cross-repo job; not added as a standalone workflow because checking
      out the separate Anvil repo in CI is auth-fragile — the GENERATED header +
      script are the reliable guard.)
- [x] Delete `r2m/py2m/` — DONE. It was an unused, drifted 5161-line copy plus a
      duplicate `r2m/py2m_runner.html`; nothing in the app referenced them. Deleted
      both; added a Netlify 301 `/r2m/py2m_runner.html` → `/py2m/py2m_runner.html`.
- [x] py2m `*`-formula hijack — ALREADY FIXED (during py2m Phase work). Verified:
      `I(x*z)` → `generate _py2m_t1 = (x * z)` + `regress y x _py2m_t1` (not
      hijacked). formula.py `_expand_star_terms` only expands `*` at top level.
- [x] Prune dead code — DONE. Removed `_parse_named_agg_keywords`,
      `_extract_by_vars` (expander.py), `_lifelines_kind_from_fit` (transformer.py),
      unreachable `_series_hist` (commands.py). 236 tests still pass.
- [x] CI: run_manual_scripts now `sys.exit(1)` on CRASH **or** PARTIAL, and is run
      in m2py-tests.yml. `deno test` already in edge-tests.yml (Phase 1). (Cross-repo
      m2py.py diff guard = `sync_to_api.sh --check`; py2m-copy guard moot — copy deleted.)
- [x] Docs — DONE. Added a root README (layout + all the run commands + sync).
      Reconciled PLAN.md (the three verbs ship — share-link/open-URL/GitHub).
      Rewrote netlify/edge-functions/README.md to the real endpoints (dm-vurder/
      kode-svar/tolk-resultat + auth) — the old `/api/dm-quick` doesn't exist.
- [x] Misc — MOSTLY DONE. build_kommune_eras.py forces UTF-8 stdout; deleted
      stale poc_static.html; sw.js comment (bump CACHE on precache change; Pyodide
      version duplicated in 3 places). DEFERRED: pinning microdata-api/
      requirements.txt — risky without the actual Anvil-deployed versions; pinning
      to wrong versions could break the live app. Best done from the Anvil env.

---

### Cross-cutting themes (from the review, still relevant)
- Dominant failure mode = **silent degradation** (`except: pass`/silent fallback).
  Every fix above should fail loudly or warn visibly.
- Dominant structural risk = **copy-without-sync** (m2py.py ×2, r2m/py2m copy,
  prompts ×N, auth code ×3) — Phases 1 & 5 attack this directly.
