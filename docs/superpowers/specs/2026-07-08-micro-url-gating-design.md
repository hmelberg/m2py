# Micro-URL gating + settings cleanup + AI-by-URL

**Date:** 2026-07-08
**Applies to:** SafeStat and OpenStat (same change in both).
**Status:** design, pending implementation plan.
**Parked (separate decision):** whether to split microdata into its own repo/edition, or merge SafeStat+OpenStat into one codebase. This spec treats "microdata" as a **runtime edition selected by the URL**, which is compatible with any of those later choices.

## Summary

Make microdata-specific UI appear only when the URL (before any `#`) contains
"micro", clean up the Settings panel, and route the AI Send button by the same
rule. A single pure helper `urlHasMicro()` drives all of it.

## Decisions (from the user)

- **Rule:** show microdata-specific UI iff the URL *before the fragment* contains
  the substring "micro" (case-insensitive). So `micro.safestat.app`,
  `microdata.run`, `micro.openstat.app` → show; `openstat.app`, `safestat.app`,
  `py.openstat.app`, `localhost` → hide. This **replaces** the editor-mode rule
  shipped earlier (commits 8fbb13d / 9cdec1b) for Oversett + Vurder personvern.
- **Gate these on `urlHasMicro()`** (visible only when true): Oversett
  (`oversettBtn`), Vurder personvern (`btnDmQuick`), Søk om data (`menuSokData`),
  Vis offline Python (`menuOfflineBtn`).
- **Hide these Settings items unless `urlHasMicro()`**: Disclosure control +
  thresholds (`menuDisclosureControl` + the thresholds field), Data source
  (`menuDataSource`), Label format (tabulate), Import row limit.
- **Remove the AI-svar setting entirely** (`menuAiMode` + its label) from
  Settings, both repos.
- **AI is BYOK everywhere.** The user's `md_anthropic_key` powers all AI via the
  Netlify edge functions → Anthropic; no Anvil in the default AI paths. With no
  key, the AI Send is disabled and points to the key setting (existing BYOK
  mechanism). Non-AI Anvil features (login, `deldata.html` source registration,
  remote/compute-to-data execution) are **unchanged** — only the AI path moves.
- **AI Send routed by `urlHasMicro()`** (replaces the removed fast/anvil choice):
  - **micro** → `/api/kode-svar` (microdata code generation), BYOK; the micro AI
    suite `dm-vurder` (privacy evaluation) and `tolk-resultat` (result
    interpretation) also run BYOK.
  - **non-micro** → the agentic `/api/data-svar` flow, BYOK: search for data →
    generate a script **in the active editor mode's language** (`activeEditorMode`
    ∈ python/r/duckdb, not microdata) → run it → revise in a loop (the old "Web"
    button's behavior, now the default Send).
- **The one Anvil-calling AI button** (the full-vurdering-via-`mdataapi.anvil.app`
  path) is kept but gated to **`M2PY_APP === 'safestat' && isAdmin &&
  urlHasMicro()`**: SafeStat only (OpenStat has no admin concept → never shown),
  admin only, micro only.

## Deferred (need the user to identify before building)

- **"Data visibility" button** to port SafeStat→OpenStat: OpenStat already has
  `menuDataSource`, `menuVisData`, and extra `menuShowIndividata` buttons, so the
  specific button is unclear. NOT in this spec — pending the user pointing at it.
- **"Better icon for sidebar"**: which sidebar (right dataset panel `sidebarRight`,
  hamburger `☰`, or AI panel) and which icon is undecided. NOT in this spec.

---

## Part 1 — `urlHasMicro()` helper

Add to the shared pure module `js/notebook-links.js` (browser + Node, unit-tested
alongside the existing resolvers):

```js
NL.urlHasMicro = function (href) {
  var s = String(href == null ? '' : href).split('#')[0].toLowerCase();
  return s.indexOf('micro') !== -1;
};
```

Callers pass `location.href`. Unit tests: `https://micro.safestat.app/` → true;
`https://microdata.run/app` → true; `https://openstat.app/#micro-anchor` → false
(fragment ignored); `https://safestat.app/` → false; `https://localhost:8080/`
→ false; path match `https://x.app/micro/y` → true.

## Part 2 — Gate buttons + settings

All gating reads `window.NotebookLinks.urlHasMicro(location.href)` once at boot and
applies `style.display`. A single boot function `applyMicroGating()` toggles every
gated element, called after DOM/settings wiring (it does not depend on
`activeEditorMode`, so no TDZ concern — unlike the earlier mode-based attempt).

- **Buttons** (`oversettBtn`, `btnDmQuick`, `menuSokData`, `menuOfflineBtn`):
  `el.style.display = micro ? <shown> : 'none'`. For `oversettBtn`, drop the old
  `translate.showsButton`/`activeEditorMode` logic — it is now purely
  `urlHasMicro()`. For `btnDmQuick`, remove the `activeEditorMode` checks added in
  8fbb13d/9cdec1b (and the OpenStat `setTimeout` TDZ workaround b06b3dc): the
  button no longer depends on mode, so the TDZ problem disappears and the
  mode-change re-evaluation hooks (`mdUpdateAskVisibility` call in
  `switchEditorMode`, the `dmB` toggle in `updateModeButtonsUi`) are removed.
- **Settings fields**: hide the four fields' containers (`.settings-field`
  wrapping each) when `!micro`. Gate by the field's stable child id
  (`menuDisclosureControl`, `menuDataSource`, the label-format select, the import
  row-limit input) → hide the closest `.settings-field` ancestor.

Because the gate is URL-based and fixed for the page's lifetime, it is applied
once at boot; no per-mode re-evaluation is needed.

## Part 3 — AI: BYOK everywhere, routed by URL

### Remove the fast/anvil setting
Delete the `AI-svar` label + `menuAiMode` button (and its settings-hint) from the
Settings markup in both repos, and the JS that cycles/binds it
(`effectiveAiMode` cycling, the `menuAiMode` click handler and its label-refresh).
`state.aiMode` / `md_ai_mode` localStorage is no longer user-facing; AI is BYOK.

### Route the Send button by URL (BYOK)
All flows authenticate with the user's `md_anthropic_key` (BYOK) to the Netlify
edge functions. The Send dispatch chooses the flow by `urlHasMicro()`:
- **micro** → `/api/kode-svar` (microdata code generation). The micro AI suite
  `/api/dm-vurder` (privacy evaluation) and `/api/tolk-resultat` (result
  interpretation) also run BYOK.
- **non-micro** → the agentic `/api/data-svar` flow: search for data → generate a
  script **in `activeEditorMode`'s language** (python/r/duckdb) → run it → revise
  in a loop. This is the old "Web" button, now the default Send. The S2
  confirmation gate (already built) governs its auto-run.

The separate Web button (`aiSendWebBtn`) and its `webModeEligible()` admin gate are
subsumed: on non-micro the main Send *is* the data-svar flow, available to any
user who has entered a key. No operator cost — the user's key pays.

### No-key behavior
If `md_anthropic_key` is empty, the Send button is disabled (or shows a short
"add your API key in Settings" affordance) rather than calling any endpoint.

### The one Anvil AI button
The full-vurdering path that calls `mdataapi.anvil.app` is retained as a single
button gated to `M2PY_APP === 'safestat' && isAdmin && urlHasMicro()`. In OpenStat
`isAdmin` is never true (no login), so it never appears there. (Identify the exact
current control during implementation — it is the "anvil"-mode Send path; it moves
from the removed fast/anvil cycle to this standalone gated button.)

---

## Architecture & components

| Unit | Responsibility | Location |
|---|---|---|
| `urlHasMicro(href)` | pure URL→bool, before-fragment substring | `js/notebook-links.js` (+ tests) |
| `applyMicroGating()` | toggle all gated buttons + settings fields once at boot | `index.html` boot path |
| AI Send router | BYOK; micro→kode-svar, non-micro→data-svar (mode-language, run+revise); disabled without a key | `js/ai-chat.js` |
| AI-svar removal | delete `menuAiMode` markup + cycling JS | `index.html` + `js/ai-chat.js` |
| Anvil AI button | single control gated to `safestat && isAdmin && urlHasMicro()` | `index.html` + `js/ai-chat.js` |

## Testing

- **Unit (`node --test`)**: `urlHasMicro()` truth table (Part 1).
- **`node --check`** on the inline script after markup/JS edits.
- **Headless (Playwright)**: load with a `?`-less localhost URL (no micro) → the
  four buttons + four settings hidden, AI-svar setting gone; then load a URL whose
  host/path contains "micro" (e.g. serve at a path or override `location` in-page)
  → they appear. Both repos.
- **Regression**: `pytest` (no engine change → only pre-existing failures);
  existing notebook-links/example-loads JS tests still pass.

## Rollout

Same change in both repos (no repo-specific values except the pre-existing
`M2PY_APP`). Build in SafeStat, apply the identical edits to OpenStat.

## Out of scope

- The repo-split / edition-merge decision (parked).
- The "data visibility" button port and the sidebar icon (deferred pending the
  user identifying them).
- Any change to the microdata AI's internals — only the *routing* changes.
