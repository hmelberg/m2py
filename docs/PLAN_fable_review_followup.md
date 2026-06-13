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
Non-security UX/reliability (index.html unless noted).

- [ ] Memoize in-flight Pyodide bootstrap promise (~L7758) and `__ensureDuckDB`.
- [ ] TTS tutorial hang (~L7229) — length-based fallback timeout +
      `speechSynthesis.resume()` keep-alive; fix male-voice regex matching female
      voices; voiceschanged 400ms clobbering.
- [ ] GitHub save cross-branch overwrite (~L10637) — guard `cur.branch !== s.branch`.
- [ ] dm-vurder SSE error masked as success (~L2082-2130) — flag + break, skip the
      "Ferdig" render.
- [ ] Streaming readers leak (~L9588, L2087) — try/finally; AbortController on Anvil
      path; restore setStdout/setStderr in finally; request-token guard for stale
      modal repaints.
- [ ] Plotly never purged (~L6298 partial) — `Plotly.purge()` before `innerHTML=''`;
      WebR shelter purge in finally.
- [ ] forklar-widgets.js 60ms setInterval leak (~L41); quiz out-of-range correct
      index soft-locks modal (~L714).
- [ ] Line-number gutter rebuilds N listeners per keystroke (~L2682) — delegate.
- [ ] Smalls: SSE buffer never flushed; `res.json()` before `res.ok` (~L1805);
      identical `/[æøå]/i.test ? 'no':'no'` branches (~L8780); sw.js opaque-response
      quota + resolveWith undefined.

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
- [ ] Delete `r2m/py2m/` (Netlify rewrite to `py2m/`) or add `diff -rq` CI guard.
- [ ] py2m `*`-formula hijack (formula.py) — only expand `*` at top level of formula.
- [ ] Prune dead code: `_parse_named_agg_keywords`, `_extract_by_vars`,
      `_lifelines_kind_from_fit`, unreachable `_series_hist`.
- [ ] CI: run_manual_scripts with `sys.exit(1)` on CRASH; `deno test` for
      `_lib/`; cross-repo + py2m-copy diff guards.
- [ ] Docs: root README (tests / build_static_data.py / generate_manifest.py);
      reconcile PLAN.md "ikke implementert" vs shipped share-link; remove edge
      README's nonexistent `/api/dm-quick`.
- [ ] Misc: build_kommune_eras.py force UTF-8 stdout; remove stale poc_static.html;
      pin microdata-api requirements.txt; sw.js comment that Pyodide version lives
      in 3 places + bump CACHE on precache change.

---

### Cross-cutting themes (from the review, still relevant)
- Dominant failure mode = **silent degradation** (`except: pass`/silent fallback).
  Every fix above should fail loudly or warn visibly.
- Dominant structural risk = **copy-without-sync** (m2py.py ×2, r2m/py2m copy,
  prompts ×N, auth code ×3) — Phases 1 & 5 attack this directly.
