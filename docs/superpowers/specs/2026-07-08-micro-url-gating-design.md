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
- **AI Send routed by URL** (replaces the removed fast/anvil choice): non-micro →
  the Web/data AI (`/api/data-svar`, agentic web search + python/r/duck script
  generation); micro → the microdata AI (`/api/kode-svar`, microdata code
  generation). See the cost note.

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

## Part 3 — Remove AI-svar setting + route AI by URL

### Remove the setting
Delete the `AI-svar` label + `menuAiMode` button (and its settings-hint) from the
Settings markup in both repos, and the JS that cycles/binds it
(`effectiveAiMode` cycling, the `menuAiMode` click handler and its label-refresh).
`state.aiMode` / `md_ai_mode` localStorage is no longer user-facing.

### Route the Send button by URL
The AI Send dispatch chooses the flow by `urlHasMicro()`:
- **micro** → `/api/kode-svar` (microdata code generation — today's "fast" flow).
- **non-micro** → `/api/data-svar` (agentic web search + python/r/duck script
  generation — today's "Web" flow, with the S2 confirmation gate already built).

The separate admin-gated Web button (`aiSendWebBtn`) and `webModeEligible()` are
subsumed: on non-micro the main Send *is* the web flow.

### Cost note (must be confirmed)
`/api/data-svar` is agentic (web search, higher token cost) and today is
admin/BYOK-gated. Making it the default non-micro path exposes it to all users.
Current protection is per-IP rate limiting (10/hr, fails open) + the S2 gate.
**Decision to confirm:** either (a) accept that with the existing rate limit, or
(b) keep a fallback — non-micro users who are not admin/BYOK get the cheaper
`/api/kode-svar` flow instead, and only admin/BYOK get `data-svar`. This spec's
default is **(b)**: gate `data-svar` behind `webModeEligible()` as today, and use
`kode-svar` as the non-micro fallback for everyone else — so nothing gets more
expensive without privilege, while micro always uses the microdata AI.

---

## Architecture & components

| Unit | Responsibility | Location |
|---|---|---|
| `urlHasMicro(href)` | pure URL→bool, before-fragment substring | `js/notebook-links.js` (+ tests) |
| `applyMicroGating()` | toggle all gated buttons + settings fields once at boot | `index.html` boot path |
| AI Send router | pick kode-svar vs data-svar by `urlHasMicro()` + `webModeEligible` fallback | `js/ai-chat.js` |
| AI-svar removal | delete `menuAiMode` markup + cycling JS | `index.html` + `js/ai-chat.js` |

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
