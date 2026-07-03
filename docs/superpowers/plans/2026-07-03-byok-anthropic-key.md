# BYOK: Egen Anthropic-nøkkel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users supply their own Anthropic API key (`X-Anthropic-Key` header) as an alternative to login/shared code for all AI features, including the previously admin-only Web AI button.

**Architecture:** Frontend stores the key in `localStorage` (`md_anthropic_key`) and sends it as `X-Anthropic-Key` when no login token exists. The edge-function gates (`runGate`/`runAdminGate` in `netlify/edge-functions/_lib/auth.ts`) accept a well-formed BYOK header in place of token/admin auth (method, body-size, and rate-limit checks are kept). Handlers use the BYOK key instead of the env `ANTHROPIC_API_KEY`. Spec: `docs/superpowers/specs/2026-07-03-byok-anthropic-key-design.md`.

**Tech Stack:** Vanilla JS frontend (`index.html`, `js/ai-chat.js`), Deno edge functions (Netlify), Deno test.

## Global Constraints

- BYOK header name is exactly `X-Anthropic-Key`; localStorage key is exactly `md_anthropic_key`.
- Valid key format: `^sk-ant-[A-Za-z0-9_-]+$`, total length ≤ 250 chars; anything else is treated as absent.
- The key must NEVER appear in any `console.*` call, log line, cache, or Blob, server- or client-side.
- Precedence everywhere: login token (Bearer) first, then BYOK, then legacy service-token (`md_ai_api_key`).
- Method, content-length, and rate-limit checks in the gates apply to BYOK requests unchanged.
- All new user-visible Norwegian strings get an English entry in `js/i18n/en.js` (keys are the NFC, whitespace-collapsed Norwegian source strings — author multi-line HTML help text on ONE line in index.html so the DOM string matches the dictionary key).
- Tests run from `netlify/edge-functions/`: `deno test --allow-all _lib/`.
- Commit after each task, on branch `dev`.

---

### Task 1: `extractByokKey` + `upstreamErrorResponse` in auth.ts (TDD)

**Files:**
- Modify: `netlify/edge-functions/_lib/auth.ts`
- Test: `netlify/edge-functions/_lib/auth.test.ts`

**Interfaces:**
- Produces: `extractByokKey(request: Request): string | null` — returns the validated `X-Anthropic-Key` header value or `null`.
- Produces: `upstreamErrorResponse(e: unknown, byokKey: string | null): Response` — 401 «Ugyldig Anthropic-nøkkel» when a BYOK request hit an Anthropic 401 (the `_lib/anthropic.ts` helpers throw `Error("Anthropic API error 401")` in that case); 502 `Upstream error: …` otherwise.

- [ ] **Step 1: Write the failing tests**

In `netlify/edge-functions/_lib/auth.test.ts`, extend the import at the top of the file to include the two new names (keep the existing names as-is):

```ts
import {
  clientIp,
  extractByokKey,
  type GateDeps,
  runGate,
  timingSafeEqual,
  upstreamErrorResponse,
} from "./auth.ts";
```

Extend the existing `req()` helper's option object with a `byok` field. Add the parameter to the options type (`byok?: string;`) and this line next to the other `headers.set` calls:

```ts
  if (opts.byok !== undefined) headers.set("x-anthropic-key", opts.byok);
```

Append at the end of the file:

```ts
// ── BYOK: user-supplied Anthropic key ──

const GOOD_KEY = "sk-ant-api03-abc123_DEF-456";

Deno.test("extractByokKey: accepts well-formed sk-ant key", () => {
  assertEquals(extractByokKey(req({ byok: GOOD_KEY })), GOOD_KEY);
});

Deno.test("extractByokKey: trims surrounding whitespace", () => {
  assertEquals(extractByokKey(req({ byok: `  ${GOOD_KEY}  ` })), GOOD_KEY);
});

Deno.test("extractByokKey: rejects wrong prefix, bad chars, empty, absent", () => {
  assertEquals(extractByokKey(req({ byok: "sk-live-abc" })), null);
  assertEquals(extractByokKey(req({ byok: "sk-ant-abc def" })), null);
  assertEquals(extractByokKey(req({ byok: "sk-ant-abc!" })), null);
  assertEquals(extractByokKey(req({ byok: "" })), null);
  assertEquals(extractByokKey(req({})), null);
});

Deno.test("extractByokKey: rejects keys longer than 250 chars", () => {
  const long = "sk-ant-" + "a".repeat(244); // total 251
  assertEquals(extractByokKey(req({ byok: long })), null);
  const ok = "sk-ant-" + "a".repeat(243); // total 250
  assertEquals(extractByokKey(req({ byok: ok })), ok);
});

Deno.test("upstreamErrorResponse: BYOK + Anthropic 401 -> 401 Ugyldig", async () => {
  const resp = upstreamErrorResponse(new Error("Anthropic API error 401"), GOOD_KEY);
  assertEquals(resp.status, 401);
  assertEquals(await resp.text(), "Ugyldig Anthropic-nøkkel");
});

Deno.test("upstreamErrorResponse: BYOK + other error -> 502", () => {
  assertEquals(upstreamErrorResponse(new Error("Anthropic API error 529"), GOOD_KEY).status, 502);
});

Deno.test("upstreamErrorResponse: no BYOK -> always 502", () => {
  assertEquals(upstreamErrorResponse(new Error("Anthropic API error 401"), null).status, 502);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/auth.test.ts`
Expected: FAIL — `extractByokKey` / `upstreamErrorResponse` not exported.

- [ ] **Step 3: Implement in auth.ts**

In `netlify/edge-functions/_lib/auth.ts`, add after the `clientIp` function (line ~44):

```ts
/**
 * BYOK: user-supplied Anthropic key from the X-Anthropic-Key header. Only a
 * well-formed key (sk-ant-…, sane charset, ≤250 chars) counts; anything else
 * is treated as absent so the normal token path (and its 401) applies.
 * The value must never be logged or cached.
 */
export function extractByokKey(request: Request): string | null {
  const raw = (request.headers.get("x-anthropic-key") ?? "").trim();
  if (raw.length === 0 || raw.length > 250) return null;
  return /^sk-ant-[A-Za-z0-9_-]+$/.test(raw) ? raw : null;
}

/**
 * Map an upstream Anthropic failure to a client response. With BYOK, a 401
 * from Anthropic means the user's own key is invalid — surface that directly
 * instead of a generic 502 (the anthropic.ts helpers throw
 * `Error("Anthropic API error <status>")`).
 */
export function upstreamErrorResponse(e: unknown, byokKey: string | null): Response {
  if (byokKey && String(e).includes("Anthropic API error 401")) {
    return new Response("Ugyldig Anthropic-nøkkel", { status: 401 });
  }
  return new Response(`Upstream error: ${e}`, { status: 502 });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/auth.test.ts`
Expected: PASS (all new and existing tests).

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/auth.ts netlify/edge-functions/_lib/auth.test.ts
git commit -m "feat(byok): extractByokKey + upstreamErrorResponse helpers"
```

---

### Task 2: BYOK path through `runGate` and `runAdminGate` (TDD)

**Files:**
- Modify: `netlify/edge-functions/_lib/auth.ts:75-126` (`runBaseChecks`), `:132-164` (`runGate`), `:253-285` (`runAdminGate`)
- Test: `netlify/edge-functions/_lib/auth.test.ts`

**Interfaces:**
- Consumes: `extractByokKey` from Task 1.
- Produces: `runGate`/`runAdminGate` return `null` (pass) for requests carrying a valid BYOK header and no Bearer token, without calling `validateToken`/`fetchUser`; 405/413/429 checks still apply. `gate()` and `adminGate()` wrappers need no changes.

- [ ] **Step 1: Write the failing tests**

Extend the test-file import with `type AdminGateDeps, runAdminGate` (skip any name already imported). Append to `netlify/edge-functions/_lib/auth.test.ts`:

```ts
function makeByokAdminDeps(): AdminGateDeps & { calls: { fetchUser: number } } {
  const calls = { fetchUser: 0 };
  return {
    sharedToken: undefined,
    checkRateLimit: () => Promise.resolve({ allowed: true, retryAfterSeconds: 0 }),
    fetchUser: () => {
      calls.fetchUser++;
      return Promise.resolve({ ok: false, isAdmin: false });
    },
    now: () => 1000,
    cache: new Map<string, { exp: number; isAdmin: boolean }>(),
    calls,
  };
}

Deno.test("runGate: valid BYOK header, no bearer -> passes without validation", async () => {
  const deps = makeDeps();
  const resp = await runGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp, null);
  assertEquals(deps.calls.validate, 0);
});

Deno.test("runGate: malformed BYOK header, no bearer -> 401", async () => {
  const resp = await runGate(req({ byok: "not-a-key" }), { endpoint: "t", maxBodyBytes: 100 }, makeDeps());
  assertEquals(resp?.status, 401);
});

Deno.test("runGate: BYOK still method-checked -> 405", async () => {
  const resp = await runGate(req({ byok: GOOD_KEY, method: "GET" }), { endpoint: "t", maxBodyBytes: 100 }, makeDeps());
  assertEquals(resp?.status, 405);
});

Deno.test("runGate: BYOK still body-capped -> 413", async () => {
  const resp = await runGate(req({ byok: GOOD_KEY, contentLength: 999 }), { endpoint: "t", maxBodyBytes: 100 }, makeDeps());
  assertEquals(resp?.status, 413);
});

Deno.test("runGate: BYOK still rate-limited -> 429", async () => {
  const deps = makeDeps({
    checkRateLimit: () => Promise.resolve({ allowed: false, retryAfterSeconds: 7 }),
  });
  const resp = await runGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp?.status, 429);
});

Deno.test("runAdminGate: valid BYOK header, no bearer -> passes without admin", async () => {
  const deps = makeByokAdminDeps();
  const resp = await runAdminGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp, null);
  assertEquals(deps.calls.fetchUser, 0);
});

Deno.test("runAdminGate: no BYOK, non-admin token -> 403 (unchanged)", async () => {
  const deps = makeByokAdminDeps();
  deps.fetchUser = () => Promise.resolve({ ok: true, isAdmin: false });
  const resp = await runAdminGate(req({ token: "user-token" }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp?.status, 403);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/auth.test.ts`
Expected: FAIL — BYOK requests get 401 «missing token».

- [ ] **Step 3: Implement**

In `auth.ts`, give `runBaseChecks` a `requireToken` flag. Change the signature and check 1:

```ts
async function runBaseChecks(
  request: Request,
  opts: GateOptions,
  checkRateLimit: GateDeps["checkRateLimit"],
  requireToken = true,
): Promise<BaseCheckResult> {
  // 1. token presence (free) — skipped for BYOK requests, which carry the
  // user's own Anthropic key instead of an account token.
  const authHeader = request.headers.get("authorization") ?? "";
  const presentedToken = authHeader.startsWith("Bearer ")
    ? authHeader.slice(7).trim()
    : "";
  if (!presentedToken && requireToken) {
    return {
      presentedToken,
      failure: new Response("Unauthorized: missing token", { status: 401 }),
    };
  }
```

(checks 2–4 unchanged.)

In `runGate`, replace the opening lines:

```ts
export async function runGate(
  request: Request,
  opts: GateOptions,
  deps: GateDeps,
): Promise<Response | null> {
  const byokKey = extractByokKey(request);
  const { presentedToken, failure } = await runBaseChecks(
    request,
    opts,
    deps.checkRateLimit,
    /* requireToken */ byokKey === null,
  );
  if (failure) return failure;
  // BYOK: the user's own Anthropic key replaces account auth. Method, body
  // and rate-limit checks above still ran; the handler uses the key upstream.
  if (byokKey !== null) return null;
```

(step 5 auth logic unchanged below.)

Apply the same pattern to `runAdminGate` — same two lines (`const byokKey = …`, pass `byokKey === null`), and `if (byokKey !== null) return null;` right after the `if (failure) return failure;` line.

- [ ] **Step 4: Run the full _lib test suite**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/`
Expected: PASS — all tests, including pre-existing ones (no `runBaseChecks` caller regressions).

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/auth.ts netlify/edge-functions/_lib/auth.test.ts
git commit -m "feat(byok): runGate/runAdminGate accept X-Anthropic-Key as auth alternative"
```

---

### Task 3: Use the BYOK key in kode-svar, kode-svar-v2, tolk-resultat, dm-vurder

**Files:**
- Modify: `netlify/edge-functions/kode-svar.ts` (import line 2; apiKey ~line 1264; final catch ~line 1302)
- Modify: `netlify/edge-functions/kode-svar-v2.ts` (import line 2; apiKey ~line 114; FINAL catch ~line 188 — NOT the picker-fallback catch at ~157)
- Modify: `netlify/edge-functions/tolk-resultat.ts` (import line 3; apiKey ~line 90; catch ~line 131)
- Modify: `netlify/edge-functions/dm-vurder.ts` (import line 9; apiKey ~line 375; catch ~line 445)

**Interfaces:**
- Consumes: `extractByokKey`, `upstreamErrorResponse` from Task 1; gates from Task 2 already let BYOK requests through.
- Produces: each handler calls Anthropic with the user's key when present; env key otherwise.

- [ ] **Step 1: Apply the same three-part edit to each of the four files**

(a) Extend the auth import, e.g. in tolk-resultat.ts:

```ts
import { extractByokKey, gate, upstreamErrorResponse } from "./_lib/auth.ts";
```

(dm-vurder/kode-svar/kode-svar-v2 import `gate` the same way — add the two names alphabetically.)

(b) Replace the apiKey lookup (identical pattern in all four; shown for tolk-resultat.ts:90):

```ts
  const byokKey = extractByokKey(request);
  const apiKey = byokKey ?? Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }
```

(kode-svar-v2 also has the `pickerModel` line between — keep it. dm-vurder has surrounding lines per its file — only the `const apiKey = …` line changes plus the new `const byokKey = …` line above it.)

(c) Replace the final upstream catch (shown for tolk-resultat.ts:131-133; same for dm-vurder.ts:445-446, kode-svar.ts:~1302, kode-svar-v2.ts:188-189):

```ts
  } catch (e) {
    return upstreamErrorResponse(e, byokKey);
  }
```

Do NOT touch kode-svar-v2's picker catch (~line 157, `console.error("v2 picker failed…")`) — it degrades gracefully by design; if the key is invalid, pass 2 fails and is mapped there.

- [ ] **Step 2: Type-check all handlers**

Run: `cd netlify/edge-functions && deno check kode-svar.ts kode-svar-v2.ts tolk-resultat.ts dm-vurder.ts`
Expected: no errors.

- [ ] **Step 3: Run the test suite**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add netlify/edge-functions/kode-svar.ts netlify/edge-functions/kode-svar-v2.ts netlify/edge-functions/tolk-resultat.ts netlify/edge-functions/dm-vurder.ts
git commit -m "feat(byok): kode-svar/kode-svar-v2/tolk-resultat/dm-vurder use user's Anthropic key"
```

---

### Task 4: Use the BYOK key in data-svar (Web mode)

**Files:**
- Modify: `netlify/edge-functions/data-svar.ts` (import line 3; apiKey ~line 69)

**Interfaces:**
- Consumes: `extractByokKey`; `runAdminGate` BYOK path from Task 2 (so non-admins with a key get past `adminGate`).
- Produces: the whole agentic loop (generation + web-search tool) runs on the user's key — `apiKey` is passed once into `runAgenticStream`, so no other change is needed. Upstream errors surface as SSE `{type:'error'}` events (mapped client-side in Task 7).

- [ ] **Step 1: Edit data-svar.ts**

Import:

```ts
import { adminGate, extractByokKey } from "./_lib/auth.ts";
```

Replace the apiKey lookup (line ~69):

```ts
  const byokKey = extractByokKey(request);
  const apiKey = byokKey ?? Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("DATA_SVAR_MODEL") ?? Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }
```

- [ ] **Step 2: Type-check and test**

Run: `cd netlify/edge-functions && deno check data-svar.ts && deno test --allow-all _lib/`
Expected: no errors, tests PASS.

- [ ] **Step 3: Commit**

```bash
git add netlify/edge-functions/data-svar.ts
git commit -m "feat(byok): data-svar (Web mode) runs on the user's Anthropic key"
```

---

### Task 5: Settings UI — key field, state, save/load

**Files:**
- Modify: `index.html:282-289` (`#aiCfgLoggedOut`), `index.html:283-285` (intro text)
- Modify: `js/ai-chat.js:6-28` (LS keys + state), `:51-61` (cacheDom), `:1441-1458` (openSettings/saveSettings)
- Modify: `js/i18n/en.js` (new strings)

**Interfaces:**
- Produces: `state.anthropicKey` (getter, `''` when unset) — used by Tasks 6–7. localStorage key `md_anthropic_key`. Saving/removing the key calls `window.mdSyncWebBtnVisibility()`.

- [ ] **Step 1: index.html — add the field inside `#aiCfgLoggedOut`**

Replace the whole `#aiCfgLoggedOut` div (lines 282-289) with (note: help text on ONE line so the collapsed DOM string matches the i18n key):

```html
      <div id="aiCfgLoggedOut">
        <div class="ai-modal-help" style="margin-bottom:14px;" data-i18n>
          Du er ikke logget inn. AI-assistenten og online-lagring krever en konto eller egen Anthropic-nøkkel.
        </div>
        <div class="ai-modal-actions" style="margin-bottom:18px;">
          <button type="button" class="ai-modal-btn primary" id="aiCfgLogin" data-i18n>Logg inn</button>
        </div>
        <div style="margin-bottom:18px;">
          <label for="aiCfgAnthropicKey" data-i18n>Eller bruk egen Anthropic API-nøkkel</label>
          <input type="password" id="aiCfgAnthropicKey" placeholder="sk-ant-…" autocomplete="off">
          <div class="ai-modal-help" data-i18n-html>Har du egen Claude-konto? Lag en API-nøkkel på <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noopener">console.anthropic.com</a> og lim den inn her. Nøkkelen lagres kun i denne nettleseren; forespørsler går via appens server, men nøkkelen lagres eller logges ikke der. Forbruk belastes din egen Anthropic-konto. Gir også tilgang til Web-knappen i python/r/duckdb-modus.</div>
        </div>
      </div>
```

- [ ] **Step 2: js/ai-chat.js — LS key + state getter**

After line 7 (`const LS_KEY_APIKEY = …`):

```js
      const LS_KEY_ANTHROPIC = 'md_anthropic_key';   // BYOK: brukerens egen Anthropic-nøkkel
```

In the `state` object, after the `apiKey` getter (line 15):

```js
        get anthropicKey() { return localStorage.getItem(LS_KEY_ANTHROPIC) || ''; },
```

- [ ] **Step 3: js/ai-chat.js — cacheDom + openSettings + saveSettings**

In `cacheDom()` (line ~55), extend the id list: change `'aiSettingsBackdrop','aiCfgBaseUrl','aiCfgApiKey','aiCfgSave','aiCfgCancel',` to

```js
         'aiSettingsBackdrop','aiCfgBaseUrl','aiCfgApiKey','aiCfgAnthropicKey','aiCfgSave','aiCfgCancel',
```

In `openSettings()` (line ~1441), after `dom.aiCfgApiKey.value = state.apiKey;`:

```js
        if (dom.aiCfgAnthropicKey) dom.aiCfgAnthropicKey.value = state.anthropicKey;
```

Replace `saveSettings()` (lines 1452-1458):

```js
      function saveSettings() {
        const base = dom.aiCfgBaseUrl.value.trim() || DEFAULT_BASE;
        const key = dom.aiCfgApiKey.value.trim();
        localStorage.setItem(LS_KEY_BASE, base);
        localStorage.setItem(LS_KEY_APIKEY, key);
        const akey = dom.aiCfgAnthropicKey ? dom.aiCfgAnthropicKey.value.trim() : '';
        if (akey) localStorage.setItem(LS_KEY_ANTHROPIC, akey);
        else localStorage.removeItem(LS_KEY_ANTHROPIC);
        // BYOK-nøkkelen påvirker Web-knappens synlighet (webModeEligible).
        if (window.mdSyncWebBtnVisibility) window.mdSyncWebBtnVisibility();
        closeSettings();
      }
```

- [ ] **Step 4: js/i18n/en.js — add translations**

Append these entries inside the `window.M2PY_I18N.en = { … }` object (before the closing brace), and DELETE the old entry whose key is `"Du er ikke logget inn. AI-assistenten og online-lagring krever en konto."` (find it with `grep -n "krever en konto" js/i18n/en.js`):

```js
  // ── BYOK: egen Anthropic-nøkkel ──
  "Du er ikke logget inn. AI-assistenten og online-lagring krever en konto eller egen Anthropic-nøkkel.": "You are not logged in. The AI assistant and online storage require an account or your own Anthropic key.",
  "Eller bruk egen Anthropic API-nøkkel": "Or use your own Anthropic API key",
  "Har du egen Claude-konto? Lag en API-nøkkel på <a href=\"https://console.anthropic.com/settings/keys\" target=\"_blank\" rel=\"noopener\">console.anthropic.com</a> og lim den inn her. Nøkkelen lagres kun i denne nettleseren; forespørsler går via appens server, men nøkkelen lagres eller logges ikke der. Forbruk belastes din egen Anthropic-konto. Gir også tilgang til Web-knappen i python/r/duckdb-modus.": "Have your own Claude account? Create an API key at <a href=\"https://console.anthropic.com/settings/keys\" target=\"_blank\" rel=\"noopener\">console.anthropic.com</a> and paste it here. The key is stored only in this browser; requests pass through the app's server, but the key is never stored or logged there. Usage is billed to your own Anthropic account. Also unlocks the Web button in python/r/duckdb mode.",
```

- [ ] **Step 5: Verify in browser**

Open `index.html` directly in a browser (no server needed for this check). Open AI-sidebar → ⚙ settings: the new field is visible when logged out; paste `sk-ant-test123`, save, reopen — the field is pre-filled; check DevTools → Application → Local Storage has `md_anthropic_key`. Clear the field, save — the localStorage entry is gone. Switch language to English and confirm the new texts translate.

- [ ] **Step 6: Commit**

```bash
git add index.html js/ai-chat.js js/i18n/en.js
git commit -m "feat(byok): settings field for user's own Anthropic API key"
```

---

### Task 6: Send the key — headers, auth gates, error texts (fast/v2/tolk/dm-vurder)

**Files:**
- Modify: `js/ai-chat.js:409-421` (callApi), `:484-494` (sendMessage gate), `:620-636` (runFastQuery), `:721-733` (streamKodeSvarV2), `:905-925` (runInterpretQuery), `:1585-1591` (mdInterpretResults gate)
- Modify: `index.html:1135-1164` (runDmVurder)
- Modify: `js/i18n/en.js`

**Interfaces:**
- Consumes: `state.anthropicKey` from Task 5.
- Produces: `edgeAuthHeaders()` in ai-chat.js — `{'Authorization'| 'X-Anthropic-Key' | 'X-API-Key', 'Content-Type'}` per the global precedence rule. Used again by Task 7.

- [ ] **Step 1: Add the shared header helper**

In `js/ai-chat.js`, directly above `async function callApi(` (line ~409):

```js
      // Headers for edge-funksjonene (/api/*): innloggingstoken har forrang,
      // deretter brukerens egen Anthropic-nøkkel (BYOK), til slutt service-token.
      function edgeAuthHeaders() {
        const auth = window.mdAuth;
        const token = auth && auth.token;
        if (token) return { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
        if (state.anthropicKey) return { 'X-Anthropic-Key': state.anthropicKey, 'Content-Type': 'application/json' };
        return { 'X-API-Key': state.apiKey, 'Content-Type': 'application/json' };
      }
```

- [ ] **Step 2: Use it in the three edge-function callers**

In `runFastQuery` (lines 622-625), `streamKodeSvarV2` (lines 723-726) and `runInterpretQuery` (lines 907-910), replace the `const headers = token ? … : …;` ternary with:

```js
        const headers = edgeAuthHeaders();
```

(keep the `const auth = window.mdAuth; const token = auth && auth.token;` lines — the 401 branch below uses them.)

- [ ] **Step 3: BYOK-aware 401 handling in the same three functions**

Replace each `if (resp.status === 401) { … }` block (lines 633-636, 730-733, 922-925) with:

```js
        if (resp.status === 401) {
          if (token && auth) { auth.logout(); auth.showLogin(); }
          if (!token && state.anthropicKey) {
            throw new Error(T('Ugyldig Anthropic-nøkkel. Sjekk nøkkelen i AI-innstillingene.'));
          }
          throw new Error(T('Innloggingen er utløpt. Logg inn på nytt.'));
        }
```

- [ ] **Step 4: Accept the key in the client-side auth gates**

Line 490 (`sendMessage`) and line 1590 (`mdInterpretResults`) — change both to:

```js
        const isAuthed = (auth && auth.token) || state.apiKey || state.anthropicKey;
```

In `callApi` (line 412-415) — the Anvil API does NOT accept BYOK; give a precise error instead of «Ikke logget inn»:

```js
        if (!token && !state.apiKey) {
          if (state.anthropicKey) {
            // BYOK gjelder kun edge-funksjonene, ikke Anvil-APIet (full vurdering).
            throw new Error(T('Denne funksjonen krever innlogging — egen Anthropic-nøkkel gjelder kun Rask AI, tolkning og Web.'));
          }
          // Defer to caller to handle (sendMessage triggers login modal)
          throw new Error(T('Ikke logget inn'));
        }
```

- [ ] **Step 5: index.html — runDmVurder accepts the key**

Replace lines 1136-1146 (token check + headers) with:

```js
        // Get Anvil session token from mdAuth module; BYOK-nøkkel som alternativ.
        const token = window.mdAuth && window.mdAuth.token;
        const anthropicKey = localStorage.getItem('md_anthropic_key') || '';
        if (!token && !anthropicKey) {
          status.textContent = t('Du må være logget inn eller ha lagt inn egen Anthropic-nøkkel (AI-innstillinger) for å bruke dataminimering.');
          cancelBtn.disabled = true;
          return;
        }
        const headers = token
          ? { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }
          : { 'Content-Type': 'application/json', 'X-Anthropic-Key': anthropicKey };
```

And the 401 branch (lines 1161-1164):

```js
        if (resp.status === 401) {
          status.textContent = token
            ? t('Innloggingen er utløpt. Logg inn på nytt og prøv igjen.')
            : t('Ugyldig Anthropic-nøkkel. Sjekk nøkkelen i AI-innstillingene.');
          return;
        }
```

- [ ] **Step 6: i18n**

Append to the BYOK section in `js/i18n/en.js`:

```js
  "Ugyldig Anthropic-nøkkel. Sjekk nøkkelen i AI-innstillingene.": "Invalid Anthropic key. Check the key in the AI settings.",
  "Denne funksjonen krever innlogging — egen Anthropic-nøkkel gjelder kun Rask AI, tolkning og Web.": "This feature requires login — your own Anthropic key only covers Fast AI, interpretation and Web.",
  "Du må være logget inn eller ha lagt inn egen Anthropic-nøkkel (AI-innstillinger) for å bruke dataminimering.": "You must be logged in or have entered your own Anthropic key (AI settings) to use data minimisation.",
```

- [ ] **Step 7: Verify in browser**

Open `index.html`, log out, set a dummy key `sk-ant-test123`. The Send button must now attempt a request (check DevTools Network: `POST /api/kode-svar` carries `X-Anthropic-Key`, no `Authorization`) instead of opening the login modal. «Vurder personvern» (dm-vurder) likewise sends the header. (Responses will fail without a backend locally — the request shape is the verification.)

- [ ] **Step 8: Commit**

```bash
git add index.html js/ai-chat.js js/i18n/en.js
git commit -m "feat(byok): send X-Anthropic-Key to AI edge functions when not logged in"
```

---

### Task 7: Web AI button for BYOK users

**Files:**
- Modify: `js/ai-chat.js:30-40` (webModeEligible), `:1035-1037` + `:1051-1053` + `:1062-1066` + `:1101-1103` (runWebAnswer), `:1254-1262` (sendWebMessage gate)
- Modify: `index.html:263` (Web button title)
- Modify: `js/i18n/en.js`

**Interfaces:**
- Consumes: `state.anthropicKey`, `edgeAuthHeaders()`; server-side `runAdminGate` BYOK path (Task 2) and data-svar key use (Task 4).

- [ ] **Step 1: webModeEligible**

Replace the function (lines 35-40) — update the comment block above it (lines 30-34) to say "admin or BYOK" instead of "admin-only":

```js
      // Web mode requires admin OR a user-supplied Anthropic key (BYOK — the
      // agentic search then runs on the user's own account), and only makes
      // sense in python/r/duckdb editor modes (no `# connect`/`# load` story
      // for microdata). Surfaced only via its own send button
      // (syncWebBtnVisibility() shows/hides #aiSendWebBtn).
      function webModeEligible() {
        const auth = window.mdAuth;
        const isAdmin = !!(auth && auth.user && auth.user.is_admin);
        const hasByok = !!state.anthropicKey;
        const mode = (typeof activeEditorMode !== 'undefined' && activeEditorMode) ? activeEditorMode : 'microdata';
        return (isAdmin || hasByok) && (mode === 'python' || mode === 'r' || mode === 'duckdb');
      }
```

- [ ] **Step 2: runWebAnswer — auth, headers, error mapping**

Lines 1035-1037, replace with:

```js
        const auth = window.mdAuth;
        const token = auth && auth.token;
        if (!token && !state.anthropicKey) throw new Error(T('Web-modus krever innlogging eller egen Anthropic-nøkkel.'));
```

Lines 1051-1053 (the fetch headers):

```js
          const resp = await fetch('/api/data-svar', {
            method: 'POST',
            headers: edgeAuthHeaders(),
```

Lines 1062-1066 (401/403 branches):

```js
          if (resp.status === 401) {
            if (token && auth) { auth.logout(); auth.showLogin(); throw new Error(T('Innloggingen er utløpt. Logg inn på nytt.')); }
            throw new Error(T('Ugyldig Anthropic-nøkkel. Sjekk nøkkelen i AI-innstillingene.'));
          }
          if (resp.status === 403) throw new Error(T('Web-modus krever admin eller egen Anthropic-nøkkel.'));
```

In `handleWebEvent` (lines 1101-1103), map an invalid-key SSE error (data-svar surfaces upstream errors mid-stream, not as HTTP status):

```js
          } else if (ev.type === 'error') {
            let msg = ev.message || 'ukjent feil';
            if (!token && state.anthropicKey && msg.indexOf('Anthropic API error 401') !== -1) {
              msg = T('Ugyldig Anthropic-nøkkel. Sjekk nøkkelen i AI-innstillingene.');
            }
            throw new Error(msg);
          }
```

- [ ] **Step 3: sendWebMessage gate (lines 1258-1262)**

```js
        const auth = window.mdAuth;
        if (!(auth && auth.token) && !state.anthropicKey) {
          if (auth) auth.showLogin();
          return;
        }
```

- [ ] **Step 4: Button title (index.html:263)**

Change the `title` attribute of `#aiSendWebBtn` to:

```
Web: finn åpne data og generer script (krever admin eller egen Anthropic-nøkkel; python/r/duckdb-modus)
```

- [ ] **Step 5: i18n**

Run `grep -n "kun admin" js/i18n/en.js` — update the key of the old Web-button title entry to the new Norwegian string (and its translation), and remove any entry for the old 403 text `"Web-modus er kun tilgjengelig for admin."`. Append:

```js
  "Web: finn åpne data og generer script (krever admin eller egen Anthropic-nøkkel; python/r/duckdb-modus)": "Web: find open data and generate a script (requires admin or your own Anthropic key; python/r/duckdb mode)",
  "Web-modus krever innlogging eller egen Anthropic-nøkkel.": "Web mode requires login or your own Anthropic key.",
  "Web-modus krever admin eller egen Anthropic-nøkkel.": "Web mode requires admin or your own Anthropic key.",
```

- [ ] **Step 6: Verify in browser**

Open `index.html` logged out. Without a key + python mode: Web button hidden. Set key `sk-ant-test123` (save settings) — Web button appears immediately (saveSettings → mdSyncWebBtnVisibility) in python/r/duckdb mode, stays hidden in microdata mode. Remove the key — button disappears. Web send attempts `POST /api/data-svar` with `X-Anthropic-Key` header.

- [ ] **Step 7: Commit**

```bash
git add index.html js/ai-chat.js js/i18n/en.js
git commit -m "feat(byok): Web AI button available with user's own Anthropic key"
```

---

### Task 8: Full verification

- [ ] **Step 1: Server-side suite**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/ && deno check kode-svar.ts kode-svar-v2.ts tolk-resultat.ts dm-vurder.ts data-svar.ts hent.ts`
Expected: all tests PASS, no type errors.

- [ ] **Step 2: Grep guards**

- `grep -rn "md_anthropic_key" js/ index.html` — exactly the sites from Tasks 5-6 (state getter + runDmVurder).
- `grep -rn "x-anthropic-key" netlify/edge-functions/ --include='*.ts' -i` — only `auth.ts` reads the header; no `console` line contains the key variable (`grep -n "byokKey" netlify/edge-functions/*.ts netlify/edge-functions/_lib/auth.ts | grep -i console` → empty).

- [ ] **Step 3: Manual UI checklist (open index.html, both languages)**

1. Logged out, no key: Send opens login modal; Web button hidden; dm-vurder asks for login/key.
2. Key saved: Send/Tolk/dm-vurder fire requests with `X-Anthropic-Key`; Web button visible in python-mode.
3. Anvil-modus (menu «AI-svar: Anvil») with key only: clear error about login requirement, no crash.
4. Logged in (if feasible): Bearer header wins; behavior unchanged.

End-to-end with a real key is verified on the deploy preview after push (local `netlify dev` is not usable here).

- [ ] **Step 4: Final commit (docs)**

```bash
git add docs/superpowers/specs/2026-07-03-byok-anthropic-key-design.md docs/superpowers/plans/2026-07-03-byok-anthropic-key.md
git commit -m "docs(byok): design spec + implementation plan"
```
