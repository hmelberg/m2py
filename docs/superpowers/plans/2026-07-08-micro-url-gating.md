# Micro-URL Gating + Settings Cleanup + AI-by-URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show microdata-specific UI only when the URL contains "micro", clean up Settings, and route the AI Send button by the same rule (BYOK everywhere).

**Architecture:** One pure helper `urlHasMicro()` in the shared `js/notebook-links.js` drives a boot-time `applyMicroGating()` that toggles four buttons and four Settings fields. The AI Send handlers reroute by `urlHasMicro()` (micro → microdata `kode-svar`; non-micro → agentic `data-svar` in the active mode's language), the fast/anvil setting is deleted, and the Anvil full-vurdering path becomes one button gated to `safestat && admin && micro`.

**Tech Stack:** Vanilla browser JS (IIFE modules, `window.*`), Node 26 `node --test`, Playwright (headless verification). No engine change, no new deps.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-08-micro-url-gating-design.md`.
- **Both repos:** build in SafeStat (`/Users/hom/Documents/GitHub/safestat`), port to OpenStat (`/Users/hom/Documents/GitHub/openstat`). Only difference is `M2PY_APP`.
- **Rule:** `urlHasMicro(href)` = the substring "micro" (case-insensitive) appears in `href` **before any `#`**. Callers pass `location.href`.
- **Gate on urlHasMicro (show iff true):** `oversettBtn`, `btnDmQuick`, `menuSokData`, `menuOfflineBtn`, and the four Settings fields containing `menuDisclosureControl`, `menuDataSource`, the label-format select, and the import row-limit input.
- **This REPLACES the editor-mode gating shipped in 8fbb13d (SafeStat) / 9cdec1b + b06b3dc (OpenStat)** — remove that mode-based logic for `oversettBtn`/`btnDmQuick` (and the OpenStat `setTimeout` TDZ workaround), since gating is now URL-based and mode-independent.
- **AI:** BYOK via `md_anthropic_key` → Netlify edge functions. Micro Send → `sendMessage(true)` (kode-svar). Non-micro Send → `sendWebMessage()` (data-svar). Remove the fast/anvil `menuAiMode` setting. The Anvil path (`sendMessage(false)`) becomes a button gated to `M2PY_APP==='safestat' && isAdmin && urlHasMicro()`.
- **Template-literal rule:** escape backticks inside JS template literals as `\``; verify each `index.html` edit with `node --check` on the extracted largest inline `<script>`.
- **Deferred (NOT in this plan):** the "data visibility" button port and the sidebar icon.

---

## Task 1: `urlHasMicro()` helper

**Files:**
- Modify: `js/notebook-links.js`
- Test: `tests/js/notebook-links.test.js`

**Interfaces:**
- Produces: `NotebookLinks.urlHasMicro(href: string) -> boolean` — true iff "micro" (case-insensitive) appears in `href` before the first `#`.

- [ ] **Step 1: Write the failing test** (append to the existing test file):

```js
test('urlHasMicro: host or path before # containing micro', () => {
  assert.equal(NL.urlHasMicro('https://micro.safestat.app/'), true);
  assert.equal(NL.urlHasMicro('https://microdata.run/app'), true);
  assert.equal(NL.urlHasMicro('https://x.app/micro/y'), true);
});
test('urlHasMicro: false when micro only after the fragment, or absent', () => {
  assert.equal(NL.urlHasMicro('https://openstat.app/#micro-anchor'), false);
  assert.equal(NL.urlHasMicro('https://safestat.app/'), false);
  assert.equal(NL.urlHasMicro('http://localhost:8080/'), false);
  assert.equal(NL.urlHasMicro(''), false);
  assert.equal(NL.urlHasMicro(null), false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/notebook-links.test.js`
Expected: FAIL — `NL.urlHasMicro is not a function`.

- [ ] **Step 3: Implement** (inside the IIFE, before the export line):

```js
  NL.urlHasMicro = function (href) {
    var s = String(href == null ? '' : href).split('#')[0].toLowerCase();
    return s.indexOf('micro') !== -1;
  };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/js/notebook-links.test.js`
Expected: PASS (all prior + 2 new).

- [ ] **Step 5: Commit**

```bash
git add js/notebook-links.js tests/js/notebook-links.test.js
git commit -m "feat(micro-gating): urlHasMicro helper"
```

---

## Task 2: `applyMicroGating()` — gate buttons + settings; remove mode-based gating

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `NotebookLinks.urlHasMicro`.
- Produces: a boot-time `applyMicroGating()` that sets `display` on the gated elements.

- [ ] **Step 1: Remove the earlier mode-based gating.** In `updateModeButtonsUi` (search `Oversett: for now only in microdata mode`), revert the `oversettBtn` line to a no-op there (it will be handled by `applyMicroGating`) — delete the `_shows`/`oversettBtn` display lines and the comment. In the ask-visibility code, revert the `btnDmQuick` display to its pre-8fbb13d form (remove `&& activeEditorMode === 'microdata'`) and remove the `mdUpdateAskVisibility()` call added to `switchEditorMode`. (These elements are now gated once by URL, not per mode.)

- [ ] **Step 2: Add `applyMicroGating()`** near the other boot helpers in the inline script:

```js
    function applyMicroGating() {
      var micro = !!(window.NotebookLinks && window.NotebookLinks.urlHasMicro(location.href));
      // Buttons: shown only when the URL has "micro".
      ['oversettBtn', 'btnDmQuick', 'menuSokData', 'menuOfflineBtn'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.style.display = micro ? '' : 'none';
      });
      // Settings fields (hide the whole .settings-field wrapper):
      ['menuDisclosureControl', 'menuDataSource', 'settingLabelFormat', 'settingImportLimit'].forEach(function (id) {
        var el = document.getElementById(id);
        var field = el && el.closest ? el.closest('.settings-field') : null;
        if (field) field.style.display = micro ? '' : 'none';
      });
    }
    applyMicroGating();
```

- [ ] **Step 3: Confirm the settings-field child ids.** Grep the label-format select and import-row-limit input ids (near the `.settings-field` wrappers around index.html:597-628). If they are not `settingLabelFormat` / `settingImportLimit`, use their real ids in the array above. (They exist — find them: `grep -n 'settings-field' -A3 index.html | grep -E "id=\"setting|label-format|importLimit|rowLimit"`.)

- [ ] **Step 4: Verify inline script parses**

Run:
```bash
python3 - <<'PY'
import re,subprocess,sys
html=open('index.html').read()
big=max(re.findall(r'<script>(.*?)</script>',html,re.S),key=len)
open('/tmp/_inline.js','w').write(big)
r=subprocess.run(['node','--check','/tmp/_inline.js'],capture_output=True,text=True)
print('OK' if r.returncode==0 else r.stderr); sys.exit(r.returncode)
PY
```
Expected: `OK`.

- [ ] **Step 5: Headless verify (Playwright).** Serve locally (`python3 -m http.server 8290`), navigate to `http://localhost:8290/` (no micro) and assert the four buttons + four settings fields are `display:none`; then navigate to `http://localhost:8290/#x` after overriding — simpler: in-page, call `NotebookLinks.urlHasMicro('https://micro.x/')` returns true, and re-run `applyMicroGating()` with a stubbed check to confirm they show. Record the observed displays.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(micro-gating): gate Oversett/Vurder personvern/Søk om data/offline + 4 settings on urlHasMicro"
```

---

## Task 3: Remove the AI-svar (fast/anvil) setting

**Files:**
- Modify: `index.html` (settings markup), `js/ai-chat.js` (cycling JS)

**Interfaces:**
- Produces: no `menuAiMode` control; `state.aiMode` is no longer user-cycled (Task 4 stops reading it for routing).

- [ ] **Step 1: Delete the settings field.** Remove the entire `.settings-field` block containing `id="menuAiMode"` (the `AI-svar` label + button + settings-hint) at `index.html:684-687`.

- [ ] **Step 2: Remove the cycling handler.** In `js/ai-chat.js`, delete the `menuAiMode` click handler and its label-refresh (search `menuAiMode`), and any code that updates its text. Leave `state.aiMode`/`md_ai_mode` getter/setter in place (harmless) but it is no longer written by a UI control.

- [ ] **Step 3: Verify**

Run: `node --check js/ai-chat.js` → clean. Inline-script `node --check` (Task 2 heredoc) → `OK`. `grep -c "menuAiMode" index.html js/ai-chat.js` → 0.

- [ ] **Step 4: Commit**

```bash
git add index.html js/ai-chat.js
git commit -m "feat(micro-gating): remove the fast/anvil AI-svar setting"
```

---

## Task 4: Route the AI Send by URL + Anvil admin button

**Files:**
- Modify: `js/ai-chat.js`, `index.html`

**Interfaces:**
- Consumes: `NotebookLinks.urlHasMicro`, existing `sendMessage(fast, useV2)`, `sendWebMessage()`.
- Produces: URL-routed Send; a `#aiSendAnvilBtn` gated to `safestat && admin && micro`.

- [ ] **Step 1: Reroute the primary Send + Enter.** In `js/ai-chat.js`, the primary send button (`aiSendFastBtn` click, ~line 1630) and the Enter handler (~line 1709) currently call `sendMessage(!state.anvilMode)`. Replace BOTH with a URL router:

```js
      function routeSend() {
        if (window.NotebookLinks && window.NotebookLinks.urlHasMicro(location.href)) {
          sendMessage(true);          // micro: microdata code generation (kode-svar)
        } else {
          sendWebMessage();           // non-micro: agentic data-svar in the active mode's language
        }
      }
```
and call `routeSend()` where `sendMessage(!state.anvilMode)` was (both sites).

- [ ] **Step 2: Subsume the Web button.** The old `aiSendWebBtn` behavior is now the non-micro primary Send. Hide it permanently: in `syncWebBtnVisibility()` (search it) set `dom.aiSendWebBtn.style.display = 'none'` unconditionally (or remove the button markup at `index.html:337` and its click wiring at `js/ai-chat.js:1638`). Keep `sendWebMessage()` itself — `routeSend()` calls it.

- [ ] **Step 3: Add the Anvil admin button.** In `index.html`, next to the send buttons (~`index.html:331-337`), add:

```html
        <button type="button" class="ai-send-fast-btn ai-send-anvil-btn" id="aiSendAnvilBtn" style="display:none;" data-i18n-title title="Anvil: full vurdering med reparasjonsloop (kun admin, microdata)" aria-label="Send (Anvil)">Anvil</button>
```
Wire it in `js/ai-chat.js` (near the other send-button wiring ~1630-1638):

```js
        if (dom.aiSendAnvilBtn) dom.aiSendAnvilBtn.addEventListener('click', function () { sendMessage(false); });
```
(add `'aiSendAnvilBtn'` to the `dom` id list at `js/ai-chat.js:63`).

- [ ] **Step 4: Gate the Anvil button.** In `index.html`'s `applyMicroGating()` (Task 2), also toggle it:

```js
      var anvil = document.getElementById('aiSendAnvilBtn');
      var isAdmin = !!(window.mdAuth && window.mdAuth.user && window.mdAuth.user.is_admin);
      if (anvil) anvil.style.display = (micro && isAdmin && (window.M2PY_APP === 'safestat')) ? '' : 'none';
```
Also re-apply this when auth changes: call `applyMicroGating()` from wherever login state updates (search `mdUpdateAskVisibility` / the auth callback; add an `applyMicroGating()` call there). In OpenStat `M2PY_APP !== 'safestat'` so it stays hidden regardless.

- [ ] **Step 5: No-key behavior (unchanged, confirm).** `sendMessage`/`sendWebMessage` already gate on `auth.token || state.apiKey || state.anthropicKey` and call `auth.showLogin()` when absent. That satisfies BYOK-no-key = prompt. No change needed; confirm by reading both gates.

- [ ] **Step 6: Verify**

Run: `node --check js/ai-chat.js` → clean. Inline `node --check` → `OK`.
Headless (Playwright), no-micro localhost: assert `#aiSendWebBtn` hidden, `#aiSendAnvilBtn` hidden, and that clicking the primary send (with a stubbed key) invokes the data-svar path (spy on `window.fetch` for `/api/data-svar`). Record results. (Full AI round-trips need real keys — those are deferred to manual QA; the routing + visibility are what this verifies.)

- [ ] **Step 7: Commit**

```bash
git add js/ai-chat.js index.html
git commit -m "feat(micro-gating): route AI Send by URL (micro=kode-svar, else=data-svar); Anvil button admin+micro only"
```

---

## Task 5: Port to OpenStat

**Files (in `/Users/hom/Documents/GitHub/openstat`):**
- Copy: `js/notebook-links.js`, `tests/js/notebook-links.test.js` (identical to SafeStat).
- Modify: `index.html`, `js/ai-chat.js` — apply Tasks 2-4 edits, searching OpenStat's anchors.

**Interfaces:** identical; `M2PY_APP === 'openstat'` means the Anvil button never shows.

- [ ] **Step 1: Copy the shared helper + tests.**

```bash
S=/Users/hom/Documents/GitHub/safestat; O=/Users/hom/Documents/GitHub/openstat
cp "$S/js/notebook-links.js" "$O/js/notebook-links.js"
cp "$S/tests/js/notebook-links.test.js" "$O/tests/js/notebook-links.test.js"
```

- [ ] **Step 2: Apply Tasks 2-4 to OpenStat** — the same `applyMicroGating()` (buttons + settings + Anvil-gate), removal of the mode-based `oversettBtn`/`btnDmQuick` gating AND the OpenStat `setTimeout` TDZ workaround (b06b3dc) and the `dmB` toggle in `updateModeButtonsUi` added in 9cdec1b; remove the `menuAiMode` setting; reroute Send by URL. OpenStat lacks `aiSendWebBtn`/`aiSendAnvilBtn`? Check: if OpenStat has no `aiSendWebBtn`, `sendWebMessage()` must still exist for `routeSend()`'s non-micro path — verify OpenStat has `sendWebMessage` (it does, from the notebook-links AI work). Do NOT add the Anvil button markup in OpenStat (no admin), OR add it but it stays hidden via the `M2PY_APP` gate — prefer NOT adding it to keep OpenStat lean.

- [ ] **Step 3: Gates**

Run: `node --test tests/js/notebook-links.test.js` → pass. `node --check js/ai-chat.js` + inline `node --check` → OK. `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_polars_backend.py` (SafeStat venv) → only pre-existing failures.
Headless (Playwright) on OpenStat local: no-micro → four buttons + settings hidden, no Anvil button; primary Send routes to data-svar.

- [ ] **Step 4: Commit (OpenStat)**

```bash
git add js/notebook-links.js tests/js/notebook-links.test.js index.html js/ai-chat.js
git commit -m "feat(micro-gating): URL-gated microdata UI + AI-by-URL (ported from SafeStat)"
```

---

## Self-review notes

- **Spec coverage:** Part 1 helper → Task 1; Part 2 buttons+settings gating (replacing mode-based) → Task 2; Part 3 remove AI-svar → Task 3, route by URL + BYOK no-key + Anvil admin button → Task 4; both repos → Task 5. Deferred items (data-button, icon) correctly excluded.
- **Type consistency:** `urlHasMicro(href)→bool` used identically in Tasks 2 & 4; `applyMicroGating()` defined in Task 2, extended in Task 4; `routeSend()` calls the existing `sendMessage`/`sendWebMessage`.
- **Verify-first anchors:** Task 2 Step 3 flags confirming the two settings-field child ids; Task 4 Step 2 flags confirming OpenStat has `sendWebMessage`. Both are locate-the-anchor steps, not placeholders.
- **Risk:** Task 4 rewires live AI dispatch — the surgical approach (reroute handlers, hide Web button, add Anvil button) avoids touching the underlying flow functions. Warrants the Playwright visibility/routing check + manual AI round-trip QA (deferred, needs real keys).
