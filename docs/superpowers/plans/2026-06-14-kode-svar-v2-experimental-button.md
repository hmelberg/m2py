# "Spør raskt" v2 — Experimental AI Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate, clearly-experimental "Send (eksperimentell)" AI button that generates microdata.no scripts via a 2-pass LLM (variable-picker → generation) plus a client-driven auto-repair round, without changing the existing "Send"/v1 path.

**Architecture:** A new edge function `/api/kode-svar-v2` runs a cheap "variable picker" model pass that selects the ~20 most relevant variables (grounded against the real catalog), renders them — with full codelists — into the per-request user turn, then streams generation using v1's exact cached system prefix (full catalog kept as fallback). The browser validates the emitted script in Pyodide+m2py; on failure it re-calls once with the error text (auto-repair). Pure logic lives in dependency-light `_lib/` modules (Deno-unit-tested in CI); v1 is touched only by moving four pure formatter functions into a shared module and adding one `export`.

**Tech Stack:** Deno edge functions (TypeScript, URL imports), Anthropic Messages API (streaming + non-streaming), vanilla JS in `index.html`, Pyodide+m2py local validation, Deno test (`deno test --allow-all _lib/`).

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `netlify/edge-functions/_lib/catalog-format.ts` | Pure catalog field formatters (`abbrevType`, `extractValidPeriod`, `cleanDescription`, `renderLabels`) | **Create** (moved verbatim from `kode-svar.ts`) |
| `netlify/edge-functions/_lib/catalog-format.test.ts` | Unit tests for the formatters | **Create** |
| `netlify/edge-functions/kode-svar.ts` | v1 handler | **Modify**: import the 4 formatters instead of defining them; add `export` to `buildCachedPrefix` |
| `netlify/edge-functions/_lib/anthropic.ts` | Anthropic client | **Modify**: add non-streaming `messageAnthropic()` |
| `netlify/edge-functions/_lib/anthropic.test.ts` | Anthropic client tests | **Modify**: add `messageAnthropic` tests |
| `netlify/edge-functions/_lib/variable-picker.ts` | Picker logic: name-list render, response parse, name grounding, focused-block render | **Create** |
| `netlify/edge-functions/_lib/variable-picker.test.ts` | Unit tests for picker logic | **Create** |
| `netlify/edge-functions/kode-svar-v2.ts` | v2 handler: gate → pick → ground → focused block → stream gen | **Create** |
| `netlify.toml` | Routes | **Modify**: add `/api/kode-svar-v2` edge route |
| `index.html` | Client | **Modify**: new button, dom ref, `sendMessage(fast, useV2)`, `runFastQueryV2`, repair loop |
| `netlify/edge-functions/README.md` | Docs | **Modify**: document the new endpoint + curl |

Pure modules (`catalog-format.ts`, `variable-picker.ts`) import only `catalog-format.ts` / nothing — no Netlify/auth deps — so their tests run fast and are CI-covered. `kode-svar-v2.ts` is a thin orchestrator with no unit test (verified by type-check + manual curl).

---

## Task 1: Extract catalog formatters into a shared, tested module

Move four pure functions out of `kode-svar.ts` verbatim so both v1 and the v2 picker can use them, and lock their behavior with a golden test (this is the v1-parity guard).

**Files:**
- Create: `netlify/edge-functions/_lib/catalog-format.ts`
- Create: `netlify/edge-functions/_lib/catalog-format.test.ts`
- Modify: `netlify/edge-functions/kode-svar.ts` (remove the 4 defs at lines ~715-796; add import)

- [ ] **Step 1: Create the shared module with the four functions moved verbatim**

Create `netlify/edge-functions/_lib/catalog-format.ts`:

```typescript
// Pure catalog-field formatters shared by the v1 prompt builder (kode-svar.ts)
// and the v2 variable picker (variable-picker.ts). No Netlify/auth deps so the
// tests stay fast and run under `deno test --allow-all _lib/`.

// "Numerisk (heltall)"/"Numerisk (desimaltall)" → "num"; "Alfanumerisk" → "alfa".
export function abbrevType(microdataDatatype: string, dataType: string): string {
  const mdt = (microdataDatatype || "").toLowerCase();
  let cls = "";
  if (mdt.startsWith("alfa")) cls = "alfa";
  else if (mdt.startsWith("num")) cls = "num";
  else cls = (microdataDatatype || dataType || "").trim();
  const dt = (dataType || "").toLowerCase();
  if (dt.startsWith("date")) return `${cls || "num"}·${dataType}`;
  return cls || dataType;
}

// Returns "2015-02-16…2025-02-16" (annual grid), "2011-01-01…2017-12-31"
// (free Forløp window), "1993–2023"/"1993–" (coarse year span), or "".
export function extractValidPeriod(description: string, temporalitet = ""): string {
  const full = (description || "").match(
    /Gyldighetsperiode:\s*(\d{4})-(\d{2}-\d{2})\s*[–—-]\s*(\d{4})-(\d{2}-\d{2})/i,
  );
  if (full) {
    const [, startYear, startMD, endYear, endMD] = full;
    const temp = temporalitet.toLowerCase();
    if (temp === "tverrsnitt") {
      return `${startYear}-${startMD}…${endYear}-${startMD}`;
    }
    if (temp === "akkumulert") {
      return `${startYear}-${endMD}…${endYear}-${endMD}`;
    }
    return `${startYear}-${startMD}…${endYear}-${endMD}`;
  }
  const m = (description || "").match(/Gyldighetsperiode:\s*([0-9]{4})[^.]*?(?:[–—-]\s*([0-9]{4}))?/i);
  if (!m) return "";
  const start = m[1];
  const end = m[2];
  if ((description || "").includes("Gyldighetsperiode") && /∞/.test(description) && !end) {
    return `${start}–`;
  }
  if (start && end) return `${start}–${end}`;
  if (start) return `${start}–`;
  return "";
}

// Strip the structured boilerplate tail so only the human description remains.
export function cleanDescription(description: string, shortTitle: string): string {
  let d = (description || "").trim();
  const cut = d.search(/\s*(Enhetstype:|Temporalitet:|Gyldighetsperiode:)/i);
  if (cut >= 0) d = d.slice(0, cut).trim();
  d = d.replace(/\s+/g, " ").trim();
  if (!d) d = (shortTitle || "").trim();
  if (d.length > 200) d = d.slice(0, 197) + "...";
  return d;
}

// Inline enum labels only for low-cardinality variables (≤12); big codelists
// would blow the token budget, so skip them. (v2 focused block uses its own
// uncapped renderer.)
export function renderLabels(labels: unknown): string {
  if (!labels || typeof labels !== "object") return "";
  const entries = Object.entries(labels as Record<string, unknown>);
  if (entries.length === 0 || entries.length > 12) return "";
  const parts = entries.map(([k, val]) => `${k}=${String(val)}`);
  return ` {${parts.join(", ")}}`;
}
```

- [ ] **Step 2: Write the failing test**

Create `netlify/edge-functions/_lib/catalog-format.test.ts`:

```typescript
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { abbrevType, cleanDescription, extractValidPeriod, renderLabels } from "./catalog-format.ts";

Deno.test("abbrevType maps classes and surfaces date format", () => {
  assertEquals(abbrevType("Alfanumerisk", ""), "alfa");
  assertEquals(abbrevType("Numerisk (heltall)", ""), "num");
  assertEquals(abbrevType("Numerisk (heltall)", "date:yyyymm"), "num·date:yyyymm");
});

Deno.test("extractValidPeriod uses start month-day for Tverrsnitt", () => {
  const d = "Noe. Gyldighetsperiode: 2015-02-16 – 2025-09-30";
  assertEquals(extractValidPeriod(d, "Tverrsnitt"), "2015-02-16…2025-02-16");
});

Deno.test("extractValidPeriod uses end month-day for Akkumulert", () => {
  const d = "Gyldighetsperiode: 1993-12-31 – 2023-12-31";
  assertEquals(extractValidPeriod(d, "Akkumulert"), "1993-12-31…2023-12-31");
});

Deno.test("extractValidPeriod keeps true window for Forløp", () => {
  const d = "Gyldighetsperiode: 2011-01-01 – 2017-12-31";
  assertEquals(extractValidPeriod(d, "Forløp"), "2011-01-01…2017-12-31");
});

Deno.test("extractValidPeriod falls back to coarse year span", () => {
  assertEquals(extractValidPeriod("Gyldighetsperiode: 1993–2023", ""), "1993–2023");
});

Deno.test("cleanDescription strips boilerplate tail and truncates", () => {
  assertEquals(cleanDescription("Kjønn. Enhetstype: Person", ""), "Kjønn.");
  assertEquals(cleanDescription("", "Kort tittel"), "Kort tittel");
  assertEquals(cleanDescription("x".repeat(250), "").length, 200);
});

Deno.test("renderLabels inlines ≤12 labels and skips big codelists", () => {
  assertEquals(renderLabels({ "1": "Mann", "2": "Kvinne" }), " {1=Mann, 2=Kvinne}");
  const big: Record<string, string> = {};
  for (let i = 0; i < 13; i++) big[String(i)] = "x";
  assertEquals(renderLabels(big), "");
});
```

- [ ] **Step 3: Run the test to verify it passes (module already created in Step 1)**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/catalog-format.test.ts`
Expected: all tests PASS (7 passed).

- [ ] **Step 4: Update v1 `kode-svar.ts` to import the moved functions**

In `netlify/edge-functions/kode-svar.ts`:
1. Add to the top imports (after line 2):

```typescript
import { abbrevType, cleanDescription, extractValidPeriod, renderLabels } from "./_lib/catalog-format.ts";
```

2. Delete the four now-duplicate definitions in the file: `function abbrevType(...)` (≈lines 715-725), `function extractValidPeriod(...)` (≈lines 741-774), `function cleanDescription(...)` (≈lines 778-786), and `function renderLabels(...)` (≈lines 790-796). Leave their explanatory comments OR delete them with the functions — either is fine; do not change any other code.

- [ ] **Step 5: Verify v1 still type-checks and the module graph is intact**

Run: `cd netlify/edge-functions && deno check kode-svar.ts`
Expected: no errors (no "duplicate identifier", no "cannot find name abbrevType").

- [ ] **Step 6: Commit**

```bash
git add netlify/edge-functions/_lib/catalog-format.ts netlify/edge-functions/_lib/catalog-format.test.ts netlify/edge-functions/kode-svar.ts
git commit -m "refactor(edge): extract catalog formatters to shared _lib/catalog-format.ts"
```

---

## Task 2: Add a non-streaming `messageAnthropic()` for the picker pass

The picker needs a single completion (a JSON array of names), not a stream. Add a sibling to `streamAnthropic` that reuses `fetchWithRetry` and returns parsed text + usage.

**Files:**
- Modify: `netlify/edge-functions/_lib/anthropic.ts`
- Modify: `netlify/edge-functions/_lib/anthropic.test.ts`

- [ ] **Step 1: Write the failing test**

Add to `netlify/edge-functions/_lib/anthropic.test.ts`:

```typescript
import { messageAnthropic } from "./anthropic.ts";

Deno.test("messageAnthropic returns text and usage from a non-streamed response", async () => {
  const fakeResponse = new Response(
    JSON.stringify({
      content: [{ type: "text", text: '["BEFOLKNING_KJOENN","INNTEKT_WLONN"]' }],
      usage: { input_tokens: 100, output_tokens: 12 },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
  const fetchImpl = () => Promise.resolve(fakeResponse);

  const out = await messageAnthropic(
    { apiKey: "k", model: "m", prompt: "q", system: "s", maxTokens: 64 },
    { fetchImpl },
  );
  assertEquals(out.text, '["BEFOLKNING_KJOENN","INNTEKT_WLONN"]');
  assertEquals(out.usage.outputTokens, 12);
});

Deno.test("messageAnthropic throws on non-OK upstream", async () => {
  const fetchImpl = () => Promise.resolve(new Response("boom", { status: 500 }));
  let threw = false;
  try {
    await messageAnthropic({ apiKey: "k", model: "m", prompt: "q" }, { fetchImpl });
  } catch (_e) {
    threw = true;
  }
  assertEquals(threw, true);
});
```

(`assertEquals` is already imported at the top of the existing test file.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/anthropic.test.ts`
Expected: FAIL — "messageAnthropic is not a function" / module has no export `messageAnthropic`.

- [ ] **Step 3: Implement `messageAnthropic`**

Add to `netlify/edge-functions/_lib/anthropic.ts` (after the `streamAnthropic` function):

```typescript
export interface AnthropicMessageResult {
  text: string;
  usage: {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    cacheCreationTokens: number;
  };
}

/**
 * Single, non-streaming completion. Used by the v2 variable-picker pass, which
 * needs the full result (a JSON array of variable names) before generation can
 * start. Reuses fetchWithRetry for timeout + 429/529 backoff. `deps` is
 * injectable for tests.
 */
export async function messageAnthropic(
  opts: AnthropicStreamOptions,
  deps: RetryDeps = {},
): Promise<AnthropicMessageResult> {
  const useLongTtl = opts.cacheTtl === "1h";
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-api-key": opts.apiKey,
    "anthropic-version": ANTHROPIC_VERSION,
  };
  if (opts.system && useLongTtl) {
    headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11";
  }
  const requestBody: Record<string, unknown> = {
    model: opts.model,
    max_tokens: opts.maxTokens ?? 1024,
    stream: false,
    messages: [{ role: "user", content: opts.prompt }],
  };
  if (opts.system) {
    requestBody.system = [
      {
        type: "text",
        text: opts.system,
        cache_control: useLongTtl ? { type: "ephemeral", ttl: "1h" } : { type: "ephemeral" },
      },
    ];
  }

  const resp = await fetchWithRetry(
    ANTHROPIC_API,
    { method: "POST", headers, body: JSON.stringify(requestBody) },
    deps,
  );
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    console.error(`Anthropic API error ${resp.status}: ${detail}`);
    throw new Error(`Anthropic API error ${resp.status}`);
  }
  const json = await resp.json();
  const text = Array.isArray(json?.content)
    ? json.content.filter((b: { type?: string }) => b?.type === "text")
        .map((b: { text?: string }) => b.text ?? "").join("")
    : "";
  const u = json?.usage ?? {};
  return {
    text,
    usage: {
      inputTokens: u.input_tokens ?? 0,
      outputTokens: u.output_tokens ?? 0,
      cacheReadTokens: u.cache_read_input_tokens ?? 0,
      cacheCreationTokens: u.cache_creation_input_tokens ?? 0,
    },
  };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/anthropic.test.ts`
Expected: PASS (including the two new tests).

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/anthropic.ts netlify/edge-functions/_lib/anthropic.test.ts
git commit -m "feat(edge): add non-streaming messageAnthropic for v2 picker pass"
```

---

## Task 3: Picker response parsing + name grounding

Two pure functions: parse the picker model's reply into a name list, and ground that list against the real catalog (drop hallucinated names, dedupe, cap at 20).

**Files:**
- Create: `netlify/edge-functions/_lib/variable-picker.ts`
- Create: `netlify/edge-functions/_lib/variable-picker.test.ts`

- [ ] **Step 1: Write the failing test**

Create `netlify/edge-functions/_lib/variable-picker.test.ts`:

```typescript
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { groundNames, parsePickerResponse } from "./variable-picker.ts";

Deno.test("parsePickerResponse reads a clean JSON array", () => {
  assertEquals(parsePickerResponse('["A","B","C"]'), ["A", "B", "C"]);
});

Deno.test("parsePickerResponse extracts an array from prose/fences", () => {
  const reply = 'Her er de relevante:\n```json\n["INNTEKT_WLONN", "BEFOLKNING_KJOENN"]\n```';
  assertEquals(parsePickerResponse(reply), ["INNTEKT_WLONN", "BEFOLKNING_KJOENN"]);
});

Deno.test("parsePickerResponse returns [] on junk", () => {
  assertEquals(parsePickerResponse("ingen liste her"), []);
  assertEquals(parsePickerResponse(""), []);
  assertEquals(parsePickerResponse("[not, valid, json]"), []);
});

Deno.test("groundNames keeps only real names, dedupes, and caps", () => {
  const meta = { variables: { A: {}, B: {}, C: {} } };
  assertEquals(groundNames(["A", "X", "B", "A"], meta, 20), ["A", "B"]);
  assertEquals(groundNames(["A", "B", "C"], meta, 2), ["A", "B"]);
  assertEquals(groundNames(["nope"], meta, 20), []);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/variable-picker.test.ts`
Expected: FAIL — cannot find module / no exports `parsePickerResponse`, `groundNames`.

- [ ] **Step 3: Implement the two functions**

Create `netlify/edge-functions/_lib/variable-picker.ts`:

```typescript
import { abbrevType, cleanDescription, extractValidPeriod } from "./catalog-format.ts";

export interface CatalogMeta {
  variables?: Record<string, Record<string, unknown>>;
}

// Extract a JSON array of strings from the picker reply. The reply may be a
// bare array, fenced (```json ... ```), or wrapped in prose. We scan for the
// first '[' ... matching ']' and JSON.parse it; anything else → [].
export function parsePickerResponse(text: string): string[] {
  if (!text) return [];
  const start = text.indexOf("[");
  if (start < 0) return [];
  let depth = 0, end = -1, instr = false, esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (instr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') instr = false;
    } else if (ch === '"') instr = true;
    else if (ch === "[") depth++;
    else if (ch === "]") { depth--; if (depth === 0) { end = i; break; } }
  }
  if (end < 0) return [];
  try {
    const arr = JSON.parse(text.slice(start, end + 1));
    if (!Array.isArray(arr)) return [];
    return arr.filter((x): x is string => typeof x === "string").map((s) => s.trim()).filter(Boolean);
  } catch {
    return [];
  }
}

// Keep only names that exist in the catalog, preserving order, de-duplicated,
// capped at `cap`. This is the grounding step: hallucinated names are dropped.
export function groundNames(names: string[], meta: CatalogMeta, cap = 20): string[] {
  const variables = meta?.variables ?? {};
  const seen = new Set<string>();
  const out: string[] = [];
  for (const name of names) {
    if (!Object.prototype.hasOwnProperty.call(variables, name)) continue;
    if (seen.has(name)) continue;
    seen.add(name);
    out.push(name);
    if (out.length >= cap) break;
  }
  return out;
}
```

(`abbrevType`, `cleanDescription`, `extractValidPeriod` are imported now because Task 4 adds the renderers that use them in this same file.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/variable-picker.test.ts`
Expected: PASS (4 tests). Note: `deno check` of this file will warn about unused imports until Task 4 — that is expected; do not remove them.

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/variable-picker.ts netlify/edge-functions/_lib/variable-picker.test.ts
git commit -m "feat(edge): picker response parsing + catalog name grounding"
```

---

## Task 4: Render the picker name-list and the focused variable block

`renderNameList` is the cheap catalog given to the picker (name + short description + tag). `renderFocusedBlock` is the rich block injected into the generation user turn for the picked variables — with **uncapped** codelists (the picker's main value over the already-present prefix catalog).

**Files:**
- Modify: `netlify/edge-functions/_lib/variable-picker.ts`
- Modify: `netlify/edge-functions/_lib/variable-picker.test.ts`

- [ ] **Step 1: Write the failing test**

Add to `netlify/edge-functions/_lib/variable-picker.test.ts`:

```typescript
import { renderFocusedBlock, renderNameList } from "./variable-picker.ts";

const META = {
  variables: {
    BEFOLKNING_KJOENN: {
      databank: "no.ssb.fdb",
      microdata_datatype: "Alfanumerisk",
      data_type: "",
      temporalitet: "Fast",
      enhetstype: "Person",
      short_title: "Kjønn",
      description: "Personens kjønn. Enhetstype: Person",
      labels: { "1": "Mann", "2": "Kvinne" },
    },
    NUS2000: {
      databank: "no.ssb.fdb",
      microdata_datatype: "Alfanumerisk",
      data_type: "",
      temporalitet: "Tverrsnitt",
      enhetstype: "Person",
      short_title: "Utdanning",
      description: "Utdanningskode. Gyldighetsperiode: 2000-10-01 – 2020-10-01",
      labels: Object.fromEntries(Array.from({ length: 30 }, (_, i) => [String(i), "niva" + i])),
    },
  },
};

Deno.test("renderNameList lists every variable name with a tag", () => {
  const out = renderNameList(META);
  assertEquals(out.includes("BEFOLKNING_KJOENN"), true);
  assertEquals(out.includes("NUS2000"), true);
  assertEquals(out.includes("Kjønn"), true);
});

Deno.test("renderFocusedBlock includes full (uncapped) codelist for picked vars", () => {
  const out = renderFocusedBlock(["NUS2000"], META);
  // 30 labels — would be skipped by the ≤12 cap in the prefix catalog, but the
  // focused block must show them all.
  assertEquals(out.includes("niva29"), true);
  assertEquals(out.includes("NUS2000"), true);
  assertEquals(out.includes("Tverrsnitt"), true);
});

Deno.test("renderFocusedBlock returns empty string for no picks", () => {
  assertEquals(renderFocusedBlock([], META), "");
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/variable-picker.test.ts`
Expected: FAIL — no exports `renderNameList`, `renderFocusedBlock`.

- [ ] **Step 3: Implement the two renderers**

Append to `netlify/edge-functions/_lib/variable-picker.ts`:

```typescript
function tagFor(v: Record<string, unknown>): string {
  const dataType = String(v.data_type ?? "");
  const mdt = String(v.microdata_datatype ?? "");
  const temp = String(v.temporalitet ?? "");
  const ehtp = String(v.enhetstype ?? "");
  const period = extractValidPeriod(String(v.description ?? ""), temp);
  const parts = [abbrevType(mdt, dataType), temp, ehtp];
  if (period) parts.push(period);
  return `[${parts.filter(Boolean).join(", ")}]`;
}

// Compact catalog for the picker model: one line per variable, grouped by bank.
// Enough signal (name, tag, short description) to judge relevance; cheap enough
// to send as a stable, cacheable system block.
export function renderNameList(meta: CatalogMeta): string {
  const variables = meta?.variables ?? {};
  const lines: string[] = [
    "## Variabelliste (velg fra disse navnene)",
    "",
    "Hver linje: `NAVN [type, temporalitet, enhetstype, gyldig-datoer] — kort beskrivelse`.",
    "",
  ];
  const names = Object.keys(variables).sort((a, b) => a.localeCompare(b));
  for (const name of names) {
    const v = variables[name];
    const text = cleanDescription(String(v.description ?? ""), String(v.short_title ?? ""));
    lines.push(text ? `- \`${name}\` ${tagFor(v)} — ${text}` : `- \`${name}\` ${tagFor(v)}`);
  }
  return lines.join("\n");
}

// Uncapped label rendering for a single variable (the focused block needs the
// full codelist even for big classifications like NUS/NACE/ICD).
function renderLabelsFull(labels: unknown): string {
  if (!labels || typeof labels !== "object") return "";
  const entries = Object.entries(labels as Record<string, unknown>);
  if (entries.length === 0) return "";
  return ` {${entries.map(([k, val]) => `${k}=${String(val)}`).join(", ")}}`;
}

// Rich block for the picked variables, injected at the top of the generation
// user turn. Returns "" when there are no picks (caller then omits the block).
export function renderFocusedBlock(names: string[], meta: CatalogMeta): string {
  const variables = meta?.variables ?? {};
  const picked = names.filter((n) => Object.prototype.hasOwnProperty.call(variables, n));
  if (picked.length === 0) return "";
  const lines: string[] = [
    "## Mest relevante variabler for dette spørsmålet",
    "",
    "Disse er valgt som mest relevante for spørsmålet (med fullstendig kodeliste).",
    "Bruk dem hvis de passer — men hele katalogen er fortsatt tilgjengelig i",
    "systemkonteksten, så velg andre variabler derfra om disse ikke dekker behovet.",
    "",
  ];
  for (const name of picked) {
    const v = variables[name];
    const text = cleanDescription(String(v.description ?? ""), String(v.short_title ?? ""));
    const labels = renderLabelsFull(v.labels);
    lines.push(text ? `- \`${name}\` ${tagFor(v)} — ${text}${labels}` : `- \`${name}\` ${tagFor(v)}${labels}`);
  }
  return lines.join("\n");
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/variable-picker.test.ts`
Expected: PASS (7 tests total). Also run `deno check _lib/variable-picker.ts` — expected: no errors (imports now all used).

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/variable-picker.ts netlify/edge-functions/_lib/variable-picker.test.ts
git commit -m "feat(edge): render picker name-list and focused variable block"
```

---

## Task 5: The `kode-svar-v2` edge function + route

Thin orchestrator: gate → fetch+cache catalog meta and picker name-list → picker pass → ground → focused block → stream generation with v1's cached prefix.

**Files:**
- Modify: `netlify/edge-functions/kode-svar.ts` (add `export` to `buildCachedPrefix`)
- Create: `netlify/edge-functions/kode-svar-v2.ts`
- Modify: `netlify.toml`

- [ ] **Step 1: Export the v1 prefix builder**

In `netlify/edge-functions/kode-svar.ts`, change the line (≈1111):

```typescript
async function buildCachedPrefix(origin: string): Promise<string> {
```

to:

```typescript
export async function buildCachedPrefix(origin: string): Promise<string> {
```

Run: `cd netlify/edge-functions && deno check kode-svar.ts` → expected: no errors.

- [ ] **Step 2: Create the v2 handler**

Create `netlify/edge-functions/kode-svar-v2.ts`:

```typescript
import { messageAnthropic, streamAnthropic } from "./_lib/anthropic.ts";
import { gate } from "./_lib/auth.ts";
import { buildCachedPrefix } from "./kode-svar.ts";
import {
  type CatalogMeta,
  groundNames,
  parsePickerResponse,
  renderFocusedBlock,
  renderNameList,
} from "./_lib/variable-picker.ts";

// ====================================================================
// kode-svar-v2 — experimental 2-pass assistant.
//   Pass 1 (picker): a cheap model selects the most relevant variable names
//     from the full name list; we ground them against the real catalog.
//   Pass 2 (generation): same cached system prefix as v1 (full catalog kept as
//     fallback), with the picked variables — full codelists — injected into the
//     user turn. Auto-repair is client-driven (browser validates via Pyodide).
// ====================================================================

interface RequestBody {
  question: string;
  lang?: "no" | "en";
  script?: string;
  prior_script?: string;   // present on a repair round
  errors?: string;         // validator error text on a repair round
}

const PICKER_INSTRUCTIONS = `\
Du er en variabel-velger for microdata.no. Du får en liste over alle tilgjengelige
variabler og et brukerspørsmål. Velg de inntil 20 variablene som er mest relevante
for å besvare spørsmålet (inkluder nøkkel-/koblingsvariabler som trengs, f.eks.
person-ref eller familie-pekere). Svar KUN med et JSON-array av eksakte
variabelnavn fra listen, uten forklaring. Eksempel: ["BEFOLKNING_KJOENN","INNTEKT_WLONN"]`;

let _cachedMeta: CatalogMeta | null = null;
let _cachedNameList: string | null = null;

async function loadCatalog(origin: string): Promise<{ meta: CatalogMeta; nameList: string }> {
  if (_cachedMeta && _cachedNameList) return { meta: _cachedMeta, nameList: _cachedNameList };
  const res = await fetch(new URL("/variable_metadata.json", origin).toString());
  if (!res.ok) throw new Error(`fetch catalog → ${res.status}`);
  const meta = (await res.json()) as CatalogMeta;
  _cachedMeta = meta;
  _cachedNameList = renderNameList(meta);
  return { meta, nameList: _cachedNameList };
}

export default async (request: Request): Promise<Response> => {
  const gateResp = await gate(request, { endpoint: "kode-svar-v2", maxBodyBytes: 50_000 });
  if (gateResp) return gateResp;

  let body: RequestBody;
  try {
    body = await request.json();
  } catch (_) {
    return new Response("Invalid JSON", { status: 400 });
  }
  const question = (body.question ?? "").trim();
  if (!question) return new Response("Missing question", { status: 400 });

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  const pickerModel = Deno.env.get("PICKER_MODEL") ?? "claude-haiku-4-5-20251001";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }

  const origin = new URL(request.url).origin;
  const system = await buildCachedPrefix(origin);
  const lang = body.lang === "en" ? "en" : "no";
  const scriptContext = (body.script ?? "").trim();
  const priorScript = (body.prior_script ?? "").trim();
  const errors = (body.errors ?? "").trim();

  // ── Pass 1: pick relevant variables (best-effort; degrade to no block). ──
  let focusedBlock = "";
  try {
    const { meta, nameList } = await loadCatalog(origin);
    const pickPromptParts = [
      `Spørsmål: ${question}`,
      priorScript ? `\nForrige skript som feilet:\n${priorScript}` : ``,
      errors ? `\nValideringsfeil:\n${errors}` : ``,
    ].filter(Boolean);
    const picked = await messageAnthropic({
      apiKey,
      model: pickerModel,
      system: `${PICKER_INSTRUCTIONS}\n\n${nameList}`,
      prompt: pickPromptParts.join("\n"),
      cacheTtl: "1h",
      maxTokens: 512,
    });
    const names = groundNames(parsePickerResponse(picked.text), meta, 20);
    focusedBlock = renderFocusedBlock(names, meta);
  } catch (e) {
    console.error(`v2 picker failed, degrading to no focused block: ${e}`);
    focusedBlock = "";
  }

  // ── Pass 2: stream generation with the (unchanged) cached prefix. ──
  const userTurn = [
    `# Brukerforespørsel`,
    ``,
    `**Språk:** ${lang}`,
    ``,
    focusedBlock ? `${focusedBlock}\n` : ``,
    scriptContext ? `**Gjeldende skript i editor (kontekst):**\n\`\`\`microdata\n${scriptContext}\n\`\`\`\n` : ``,
    priorScript ? `**Forrige skript som feilet — fiks feilene under, ikke gjenta dem:**\n\`\`\`microdata\n${priorScript}\n\`\`\`\n` : ``,
    errors ? `**Valideringsfeil å rette:**\n${errors}\n` : ``,
    `**Spørsmål:** ${question}`,
  ].filter((s) => s !== ``).join("\n");

  try {
    const stream = await streamAnthropic({
      apiKey,
      model,
      prompt: userTurn,
      system,
      cacheTtl: "1h",
      maxTokens: 8192,
    });
    return new Response(stream, {
      headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
    });
  } catch (e) {
    return new Response(`Upstream error: ${e}`, { status: 502 });
  }
};
```

- [ ] **Step 3: Add the route in `netlify.toml`**

Append to `netlify.toml` (after the existing `kode-svar` block, ≈lines 53-55):

```toml
[[edge_functions]]
  function = "kode-svar-v2"
  path = "/api/kode-svar-v2"
```

- [ ] **Step 4: Type-check the whole edge surface**

Run: `cd netlify/edge-functions && deno check *.ts _lib/*.ts`
Expected: no errors.

- [ ] **Step 5: Run the full edge test suite (nothing regressed)**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/`
Expected: all tests PASS.

- [ ] **Step 6: Manual smoke test against a local dev server**

Start: `netlify dev` (needs `.env` with `ANTHROPIC_API_KEY`, `M2PY_ACCESS_TOKEN`; optionally `PICKER_MODEL`).
Run:
```bash
curl -N -X POST http://localhost:8888/api/kode-svar-v2 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $M2PY_ACCESS_TOKEN" \
  -d '{"question":"Gjennomsnittlig lønn etter kjønn i 2022","lang":"no"}'
```
Expected: a stream of `data: {"type":"text",...}` lines ending in a `data: {"type":"done",...}` line; the markdown contains a ```microdata block that imports real variables (e.g. `BEFOLKNING_KJOENN`, `INNTEKT_WLONN`).

- [ ] **Step 7: Commit**

```bash
git add netlify/edge-functions/kode-svar.ts netlify/edge-functions/kode-svar-v2.ts netlify.toml
git commit -m "feat(edge): add experimental kode-svar-v2 (2-pass picker + generation)"
```

---

## Task 6: Client — add the experimental button and wire dispatch

Add the button next to "Send", a dom ref, and route it through `sendMessage(fast, useV2)` without changing existing callers.

**Files:**
- Modify: `index.html` (button markup ≈1222; dom list ≈9120; `sendMessage` signature ≈9551; fast branch ≈9580-9596; wiring ≈10069)

- [ ] **Step 1: Add the button markup**

In `index.html`, after the existing send button (line 1224 `aria-label="Send">Send</button>`), add:

```html
        <button type="button" class="ai-send-fast-btn ai-send-v2-btn" id="aiSendV2Btn"
          title="Eksperimentell: 2-stegs variabelvalg + auto-retting (kan være tregere)"
          aria-label="Send (eksperimentell)">Send⚗︎</button>
```

- [ ] **Step 2: Register the dom ref**

In the dom-id list (line 9120, the array containing `'aiSendFastBtn','aiAbortBtn'`), add `'aiSendV2Btn'`:

```javascript
         'aiThread','aiInput','aiSendFastBtn','aiSendV2Btn','aiAbortBtn',
```

- [ ] **Step 3: Add the `useV2` parameter to `sendMessage` and branch in the fast path**

Change the signature (line 9551) from `async function sendMessage(fast) {` to:

```javascript
      async function sendMessage(fast, useV2) {
```

Inside the `if (fast) {` block (line 9585), change the single call:

```javascript
            const meta = await runFastQuery(text, lang, includeScript ? dom.scriptInput.value : '', thinkingNode, ctrl.signal);
```

to:

```javascript
            const meta = useV2
              ? await runFastQueryV2(text, lang, includeScript ? dom.scriptInput.value : '', thinkingNode, ctrl.signal)
              : await runFastQuery(text, lang, includeScript ? dom.scriptInput.value : '', thinkingNode, ctrl.signal);
```

- [ ] **Step 4: Wire the button click**

After the existing wiring (line 10069 `dom.aiSendFastBtn.addEventListener('click', sendCurrent);`), add:

```javascript
        if (dom.aiSendV2Btn) dom.aiSendV2Btn.addEventListener('click', () => sendMessage(true, true));
```

- [ ] **Step 5: Add a minimal style for the experimental button (optional but keeps it visually distinct)**

Find the CSS rule for `.ai-send-fast-btn` and add a sibling rule nearby (search `.ai-send-fast-btn {` in the `<style>`); add:

```css
    .ai-send-v2-btn { opacity: 0.85; }
    .ai-send-v2-btn:hover { opacity: 1; }
```

- [ ] **Step 6: Verify the page loads without console errors**

Run a local static server: `python3 -m http.server 8000` and open `http://localhost:8000/index.html`.
Expected: the AI panel shows two send buttons; opening DevTools console shows no `runFastQueryV2 is not defined` yet — that is expected until Task 7 (the button will only error if clicked). Do not click it yet.

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "feat(ui): add experimental v2 AI send button and dispatch wiring"
```

---

## Task 7: Client — `runFastQueryV2` (single pass, picker "thinking" state)

A copy of `runFastQuery` pointed at `/api/kode-svar-v2`, with an intermediate "Finner relevante variabler…" state (first bytes are delayed by the picker). No repair yet — that's Task 8. Factor the per-request streaming into a helper so Task 8 can re-call it.

**Files:**
- Modify: `index.html` (add functions after `runFastQuery`, ≈9778)

- [ ] **Step 1: Add `streamKodeSvarV2` and `runFastQueryV2` after `runFastQuery`**

In `index.html`, immediately after the end of `runFastQuery` (the `}` on line 9778), insert:

```javascript
      // One streaming request to /api/kode-svar-v2. Renders markdown live into
      // `bubble`. Returns { accumulated, tokens }. Mirrors runFastQuery's stream
      // parsing; factored out so the repair round can call it again.
      async function streamKodeSvarV2(payload, bubble, signal) {
        const auth = window.mdAuth;
        const token = auth && auth.token;
        const headers = token
          ? { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' }
          : { 'X-API-Key': state.apiKey, 'Content-Type': 'application/json' };
        const resp = await fetch('/api/kode-svar-v2', {
          method: 'POST', headers, body: JSON.stringify(payload), signal,
        });
        if (resp.status === 401) {
          if (token && auth) { auth.logout(); auth.showLogin(); }
          throw new Error('Innloggingen er utløpt. Logg inn på nytt.');
        }
        if (!resp.ok || !resp.body) {
          throw new Error('HTTP ' + resp.status + ' ' + (await resp.text()));
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', accumulated = '', _lastRender = 0;
        let inputTokens = 0, outputTokens = 0, cacheRead = 0, cacheCreate = 0;
        let firstByte = false;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let nl;
          while ((nl = buffer.indexOf('\n\n')) >= 0) {
            const event = buffer.slice(0, nl);
            buffer = buffer.slice(nl + 2);
            const dataLine = event.split('\n').find(l => l.startsWith('data:'));
            if (!dataLine) continue;
            let obj;
            try { obj = JSON.parse(dataLine.slice(5).trim()); } catch (_) { continue; }
            if (obj.type === 'text') {
              if (!firstByte) { firstByte = true; bubble.textContent = ''; }
              accumulated += obj.text;
              const _now = Date.now();
              if (_now - _lastRender > 70) {
                _lastRender = _now;
                streamRenderMd(bubble, accumulated);
                scrollToBottom();
              }
            } else if (obj.type === 'done') {
              inputTokens = obj.inputTokens || 0;
              outputTokens = obj.outputTokens || 0;
              cacheRead = obj.cacheReadTokens || 0;
              cacheCreate = obj.cacheCreationTokens || 0;
            } else if (obj.type === 'error') {
              throw new Error(obj.message || 'Ukjent feil fra server');
            }
          }
        }
        return { accumulated, tokens: { input: inputTokens, output: outputTokens, cacheRead, cacheCreate } };
      }

      async function runFastQueryV2(text, lang, scriptContext, thinkingNode, signal) {
        const t0 = Date.now();
        thinkingNode.innerHTML = '';
        const bubble = document.createElement('div');
        bubble.className = 'ai-bubble';
        bubble.textContent = 'Finner relevante variabler…';
        thinkingNode.appendChild(bubble);

        const payload = { question: text, lang, script: scriptContext || '' };
        const { accumulated, tokens } = await streamKodeSvarV2(payload, bubble, signal);

        // Final render + actions (reuse v1 helpers).
        if (md) { try { bubble.innerHTML = md.render(accumulated || ''); } catch (_) { bubble.textContent = accumulated; } }
        else { bubble.textContent = accumulated; }
        attachCodeBlockActions(bubble);
        bubble._rawMd = accumulated;

        const meta = { intent: 'raskt-v2', model: 'kode-svar-v2', latency_ms: Date.now() - t0, tokens };
        appendMeta(thinkingNode, meta);
        attachResponseInsertBar(thinkingNode, accumulated);

        // Non-blocking local validation (repair is added in the next task).
        const script = extractFirstMicrodataBlock(accumulated);
        if (script) {
          validateMicrodataLocal(script).then(vr => {
            if (vr.skipped || vr.passed) return;
            const warn = renderValidationWarnings(vr);
            if (warn) bubble.appendChild(warn);
          }).catch(() => {});
        }
        return meta;
      }
```

- [ ] **Step 2: Manual test — the experimental button streams an answer**

With `netlify dev` running (so `/api/kode-svar-v2` is live) and the site open through it (`http://localhost:8888`), log in, type "Gjennomsnittlig lønn etter kjønn i 2022", and click **Send⚗︎**.
Expected: bubble first shows "Finner relevante variabler…", then streams a markdown answer with a ```microdata block; a token/latency meta line appears; on an invalid script a ⚠ warning appears below.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(ui): runFastQueryV2 streaming with picker thinking state"
```

---

## Task 8: Client — auto-repair round + variable-name grounding (B)

After validation fails, build an error string (including any `db/NAME` tokens not in `microdataVariableNames`) and re-call once with `prior_script` + `errors`. Cap at one repair.

**Files:**
- Modify: `index.html` (`runFastQueryV2` body from Task 7; add a name-check helper)

- [ ] **Step 1: Add a name-grounding helper above `runFastQueryV2`**

Insert before `runFastQueryV2`:

```javascript
      // Collect db/NAME (or alias/NAME) tokens whose NAME is not in the loaded
      // catalog — the cheapest, most damaging failure (invented variable names).
      function findUnknownVarNames(script) {
        if (!script || typeof microdataVariableNames === 'undefined' || !microdataVariableNames.length) return [];
        const known = new Set(microdataVariableNames);
        const re = /\b[a-zA-Z_]\w*\/([A-Z][A-Z0-9_]+)\b/g;
        const bad = new Set();
        let m;
        while ((m = re.exec(script)) !== null) {
          if (!known.has(m[1])) bad.add(m[1]);
        }
        return Array.from(bad);
      }

      // Turn a validation result + unknown-name list into a compact error string
      // for the repair prompt. Returns '' when there is nothing to fix.
      function buildRepairErrors(vr, unknownNames) {
        const parts = [];
        if (unknownNames && unknownNames.length) {
          parts.push('Ukjente variabelnavn (finnes ikke i katalogen): ' + unknownNames.join(', '));
        }
        if (vr && !vr.skipped && !vr.passed && Array.isArray(vr.errors)) {
          for (const e of vr.errors) {
            const tok = e.token ? (e.token + ': ') : '';
            parts.push('- ' + tok + (e.message || e.kind || 'feil'));
          }
        }
        return parts.join('\n');
      }
```

- [ ] **Step 2: Replace the validation tail of `runFastQueryV2` with a repair-aware version**

In `runFastQueryV2` (from Task 7), replace everything from `// Non-blocking local validation` through `return meta;` with:

```javascript
        // Validate; on failure, attempt ONE repair round, then badge.
        let script = extractFirstMicrodataBlock(accumulated);
        let repaired = false;
        let finalBubble = bubble;
        let finalAccumulated = accumulated;
        while (script) {
          let vr;
          try { vr = await validateMicrodataLocal(script); } catch (_) { vr = { skipped: true }; }
          const unknown = findUnknownVarNames(script);
          const hasErrors = (!vr.skipped && !vr.passed) || unknown.length > 0;
          if (!hasErrors || repaired) {
            if (hasErrors) {
              const warn = renderValidationWarnings(
                vr.skipped ? { passed: false, errors: unknown.map(n => ({ kind: 'unknown_variable', token: n, message: 'finnes ikke i katalogen' })) } : vr
              );
              if (warn) finalBubble.appendChild(warn);
            }
            break;
          }
          // One repair round: new bubble, re-call with prior script + errors.
          repaired = true;
          const note = document.createElement('div');
          note.className = 'ai-thinking';
          note.textContent = 'Retter feil og prøver på nytt…';
          thinkingNode.appendChild(note);
          const repairBubble = document.createElement('div');
          repairBubble.className = 'ai-bubble';
          thinkingNode.appendChild(repairBubble);
          const errStr = buildRepairErrors(vr, unknown);
          let r2;
          try {
            r2 = await streamKodeSvarV2(
              { question: text, lang, script: scriptContext || '', prior_script: script, errors: errStr },
              repairBubble, signal,
            );
          } catch (e) {
            note.remove();
            repairBubble.textContent = '✗ ' + (e && e.message ? e.message : String(e));
            break;
          }
          note.remove();
          if (md) { try { repairBubble.innerHTML = md.render(r2.accumulated || ''); } catch (_) { repairBubble.textContent = r2.accumulated; } }
          else { repairBubble.textContent = r2.accumulated; }
          attachCodeBlockActions(repairBubble);
          repairBubble._rawMd = r2.accumulated;
          attachResponseInsertBar(thinkingNode, r2.accumulated);
          finalBubble = repairBubble;
          finalAccumulated = r2.accumulated;
          meta.tokens.input += r2.tokens.input; meta.tokens.output += r2.tokens.output;
          meta.tokens.cacheRead += r2.tokens.cacheRead; meta.tokens.cacheCreate += r2.tokens.cacheCreate;
          script = extractFirstMicrodataBlock(r2.accumulated);
        }
        return meta;
```

- [ ] **Step 3: Manual test — repair fires and resolves**

With `netlify dev` running and the site open through it: ask a question likely to trip a rule (e.g. "Andel uføre blant menn over 60 i 2010 fordelt på kommune" — exercises missing-value + small-cell rules). 
Expected behaviors to confirm:
1. A normal answer streams.
2. If the first script fails local validation, "Retter feil og prøver på nytt…" appears and a second answer streams.
3. After the (single) repair, either a clean result or a ⚠ warning — never more than one repair round.
4. Ask a clearly valid simple question ("Tabell over kjønn") → no repair round appears (no spurious retries).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat(ui): v2 auto-repair round + invented-variable-name grounding"
```

---

## Task 9: Docs + full verification sweep

**Files:**
- Modify: `netlify/edge-functions/README.md`

- [ ] **Step 1: Document the new endpoint**

In `netlify/edge-functions/README.md`, add `kode-svar-v2` to the endpoint list near the top and add a curl example mirroring the existing `kode-svar` one:

```markdown
- `kode-svar-v2` → `/api/kode-svar-v2` — eksperimentell 2-stegs variant: en
  «variabel-velger»-modell (env `PICKER_MODEL`, standard rask) plukker relevante
  variabler som vises med full kodeliste i generasjons-prompten; klienten kjører
  én auto-rettingsrunde mot lokal Pyodide-validering. v1 (`kode-svar`) er urørt.
```

- [ ] **Step 2: Run the complete edge test + type-check suite**

Run:
```bash
cd netlify/edge-functions && deno check *.ts _lib/*.ts && deno test --allow-all _lib/
```
Expected: type-check clean; all unit tests PASS.

- [ ] **Step 3: Confirm the Python/m2py suite is unaffected (baseline)**

Run the project's pytest suite (per `memory/m2py-test-workflow.md`).
Expected: same baseline as before this work (6 PARTIALs), no new failures — this work touched no Python.

- [ ] **Step 4: Confirm v1 is byte-for-byte behaviorally unchanged**

With `netlify dev` running, send the SAME question through the original **Send** button and confirm it still streams via `/api/kode-svar` (DevTools Network tab shows the v1 endpoint), unchanged from before.

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/README.md
git commit -m "docs(edge): document experimental kode-svar-v2 endpoint"
```

---

## Self-review notes (coverage check against the spec)

- **A (auto-repair):** Task 8 (client repair round, capped at 1) + Task 5 (handler accepts `prior_script`/`errors`).
- **B (name grounding):** Task 8 `findUnknownVarNames` against `microdataVariableNames`, fed into the repair errors.
- **C (2-pass picker):** Tasks 3–4 (parse/ground/render) + Task 5 (handler pass 1) + Task 2 (`messageAnthropic`).
- **Keep full catalog as fallback:** Task 5 generation uses the unchanged `buildCachedPrefix`; focused block is additive in the user turn.
- **Configurable fast picker model:** Task 5 `PICKER_MODEL` env, default Haiku.
- **Caching stays intact:** focused block is in the user turn, never the system prefix (Task 5); v1 prefix builder untouched except an additive `export`.
- **Graceful degradation:** Task 5 picker `try/catch` → no block → v1-equivalent generation.
- **v1 untouched:** only changes to `kode-svar.ts` are the formatter import (Task 1) and one `export` (Task 5); verified by Task 9 Step 4.
- **Tests:** pure logic unit-tested in `_lib/` (Tasks 1–4); handler + client verified by type-check + manual (Tasks 5–9), consistent with this repo having no JS/browser test harness.
```
