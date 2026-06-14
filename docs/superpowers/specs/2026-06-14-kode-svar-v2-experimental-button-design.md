# Design: "Spør raskt" v2 — experimental AI button (retrieval + auto-repair)

Date: 2026-06-14
Status: Approved (pending written-spec review)
Branch: dev

## Goal

Improve the AI that generates microdata.no scripts from a user's analytical
question, **without touching the working v1 path**. Ship the improvement behind
a separate, clearly-experimental button so it can be A/B-compared against the
current "Send" button and rolled back by deleting one button + one route.

The two failures we are targeting (per user):

- **A — scripts that fail to run** (wrong temporality dates, invalid commands,
  pseudonym misuse, privacy-rule violations). Fix: a client-driven auto-repair
  round using the local Pyodide+m2py validator that already runs in the browser.
- **C — runs fine but picks a poor / wrong-suited variable** (deprecated
  variant, wrong unit-type, a better-matching register missed). Fix: a two-pass
  LLM "variable picker" that surfaces the most relevant ~20 variables (with full
  descriptions + expanded codelists) in the foreground for the question.

**B — invented variable names** folds into A: a non-existent name is just one
more thing the validator (and a cheap client-side name check against the
already-loaded `microdataVariableNames`) flags, feeding the same repair round.

## Non-goals

- No change to v1 runtime behavior (`/api/kode-svar`, `runFastQuery`).
- No embeddings / vector index (picker is LLM-based per decision).
- No server-side validation/repair (m2py is Python; the edge runtime is Deno —
  validation stays client-side, so repair is necessarily client-driven).
- No Python / m2py changes; the existing pytest + manual suite is unaffected.

## Architecture (parallel, isolated path)

| Concern | v1 (unchanged) | v2 (new) |
|---|---|---|
| Route | `/api/kode-svar` | `/api/kode-svar-v2` |
| Edge fn | `kode-svar.ts` | `kode-svar-v2.ts` |
| Client fn | `runFastQuery()` | `runFastQueryV2()` |
| Button | "Send" | "Send (eksperimentell)" |
| Passes | 1 (generation) | 2 (picker → generation) + ≤1 repair |
| Catalog | full, in cached prefix | full, in cached prefix (kept as fallback) |

v2 **reuses** v1's prompt builder. The render functions/constants in
`kode-svar.ts` (`RULE_BLOCKS`, `renderCatalog`, `renderKommuneCodes`,
`renderCommands`, `renderFunctions`, `buildCachedPrefix`, and the catalog data
access) get an `export` keyword added — purely additive, non-behavioral — and
`kode-svar-v2.ts` imports them. No duplication, no logic change to v1.

## Request flow

```
client clicks "Send (eksperimentell)"
  → POST /api/kode-svar-v2 { question, lang, script }
     PASS 1 — picker (non-streamed, awaited):
        cheap model gets the full variable NAME list (name — short_title — tag)
        + the question → returns a JSON array of ~20 relevant variable names
        → edge filters returned names against the real catalog (drops any
          hallucinated names) → if any survive, render a focused block with FULL
          tag + description + EXPANDED codelist for each picked variable
     PASS 2 — generation (streamed, SSE):
        same cached system prefix as v1 (full catalog included)
        + user turn = focused block + question + editor script
  → client renders markdown live (reuses v1 SSE parser)
  → client validates the first ```microdata block locally (Pyodide+m2py)  [A]
     and checks every db/NAME token against microdataVariableNames           [B]
  → if errors AND not yet repaired:
        re-POST { question, lang, script, prior_script, errors }
        → stream once more → re-validate
  → badge: clean (no badge), or ⚠ with remaining errors
  → repair capped at 1 round
```

## Caching decision (critical)

- The **full catalog stays in the cached `system` prefix**, byte-identical to
  v1, so it is a safe fallback and still benefits from Anthropic prompt caching
  (1h TTL, same as v1).
- The picker's **focused block goes in the per-request user turn**, NOT the
  prefix, so it never breaks prefix byte-stability / cache hits.
- The picker's concrete value on top of the already-present catalog: (1) pulls
  the right ~20 variables into the model's foreground, and (2) expands the
  hidden codelists (the ~8 vars with >12 labels + kommune) for exactly the
  variables this question needs (v1 caps inline labels at 12).

## Components

### Edge: picker pass
- New non-streaming helper `messageAnthropic()` in `_lib/anthropic.ts`,
  mirroring `streamAnthropic` (same retry/timeout via `fetchWithRetry`),
  returning `{ text, usage }`.
- Picker system block (cacheable, stable): selection instructions + the full
  variable NAME list (`NAME — short_title [tag]`). User turn: the question
  (plus, on repair, the prior script + errors as extra context — re-picking with
  the failure in view can choose a better variable).
- Output contract: a JSON array of variable-name strings. Parse defensively;
  on parse failure, treat as "no picks".
- **Grounding:** intersect returned names with the real catalog keys; drop the
  rest. Cap at N≈20.
- Model: new env `PICKER_MODEL`, default a fast/cheap model (e.g. Haiku);
  configurable. Generation model stays `ANTHROPIC_MODEL` (default sonnet).

### Edge: focused-block renderer
- For each grounded, picked variable: full `[type, temporalitet, enhetstype,
  valid-dates]` tag + cleaned description + the FULL codelist (bypassing v1's
  ≤12 cap), plus the shared kommune list if a kommune variable is picked.
- Emitted as a `## Mest relevante variabler for dette spørsmålet` section at the
  top of the user turn.

### Edge: generation pass
- `streamAnthropic` with v1's exact cached prefix as `system` and the augmented
  user turn. SSE wire format identical to v1.

### Edge: handler `kode-svar-v2.ts`
- Same `gate()` auth + rate-limit as v1.
- Body: `{ question, lang?, script?, prior_script?, errors? }`.
- Orchestrates: pick → ground → render block → stream generation.

### Client: `runFastQueryV2()` + button
- New "Send (eksperimentell)" button in `.ai-input-wrap` (index.html:1218),
  new dom ref, wired to the v2 handler; shares `state.sending`, the abort
  controller, and the disable plumbing with the existing button.
- Shows a brief "Finner relevante variabler…" state while pass 1 runs (first
  bytes are delayed by the picker).
- After stream + local validation: if the validator or the name-grounding check
  reports errors and `repaired === false`, re-POST with `prior_script` + the
  error text, stream again, re-validate, then badge. Max 1 repair.
- Name-grounding (B): extract `db/NAME` / `<alias>/NAME` tokens from the emitted
  script, check each against `microdataVariableNames`; any miss is added to the
  error text fed to repair.

## Error handling / graceful degradation

- Picker fails / times out / junk JSON / all names hallucinated → no focused
  block → generation runs on the full cached catalog alone → effectively v1
  behavior. **Never worse than today.**
- Repair capped at 1 round; if still failing, non-blocking ⚠ badge with the
  errors (same UX as v1's current warning).
- Abort propagates through both passes (picker call honors the AbortSignal).
- Generation upstream error → 502 → same client error path as v1.

## Cost / latency

- v2 ≈ 2 sequential model calls per answer (picker + generation), + 1 extra
  generation only on answers that fail validation and trigger repair.
- Picker output is tiny (~20 names), so its latency is small; default fast
  picker model keeps cost/latency down. Acceptable for an opt-in button.

## Testing

- Deno unit tests next to existing `_lib/*.test.ts`:
  - picker JSON parsing (valid array, junk, partial),
  - name-grounding filter (drops hallucinated names, caps at N),
  - focused-block rendering (full codelist expansion, kommune inclusion),
  - **byte-equality test: the exported v1 prefix builder produces output
    identical before/after the `export` refactor** (guards v1 parity).
- Manual:
  - same question on both buttons, compare output;
  - a deliberately-erroring question → confirm repair fires and fixes it;
  - forced picker failure (bad `PICKER_MODEL` or empty result) → confirm
    degradation to v1-like behavior.
- Existing pytest + manual m2py suite: unchanged, must still pass (baseline:
  6 PARTIALs).

## Rollout / rollback

- Additive only: new route + new button. v1 fully intact.
- Rollback = remove the button and the `[[edge_functions]]` route entry.
- Once validated, the path to promotion is: make v2 the default "Send" behavior
  and remove the old path (separate follow-up, not in this spec).

## Open follow-ups (out of scope here)

- Optionally drop the full catalog from the v2 prefix once the picker is proven
  (cheaper/sharper, riskier) — deferred; we keep the catalog for now.
- Quality telemetry on which scripts fail local validation, to keep tightening
  the rule blocks.
