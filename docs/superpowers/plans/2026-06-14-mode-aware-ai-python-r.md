# Mode-aware AI (Python/R) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the v2 "Spør raskt" AI emit Python or R code (loading microdata via a `#micro` hybrid block) when the editor is in those modes, leaving v1 and microdata mode unchanged.

**Architecture:** A pure `assemblePrefix(mode, parts)` builds the system prefix per mode from existing shared data-blocks plus new Python/R prompt constants; `buildCachedPrefix` gains a `mode` param and a per-mode cache. The v2 handler reads `mode` from the request; the client sends `activeEditorMode` and, for Python/R, skips m2py repair but keeps variable-name grounding on the `#micro` block.

**Tech Stack:** Deno edge functions (TypeScript), Anthropic Messages API, vanilla JS in `index.html`, Deno test.

---

## Design refinements vs spec (read first)

- **`INFERENCE_RULES` is NOT split.** To guarantee microdata byte-parity, microdata mode keeps `RULE_BLOCKS` (incl. the whole `INFERENCE_RULES`) untouched. Python/R get a fresh, language-appropriate `INFERENCE_STRATEGY_PYR` constant instead of a split-out half. Safer than splitting; satisfies the spec's parity goal.
- **Python/R prompt constants live in `kode-svar.ts`** (next to `buildCachedPrefix`, which does the assembly), not in `kode-svar-v2.ts`. The v2 handler only reads `mode` and passes it through. Keeps all prompt assembly + caching in one place.
- **Byte-parity is by construction:** `assemblePrefix("microdata", …)` uses the exact same array `[RULE_BLOCKS, catalog, kommune, command, function, CANONICAL_EXAMPLES].filter().join("\n\n")` as today.

## File structure

| File | Responsibility | Change |
|---|---|---|
| `netlify/edge-functions/kode-svar.ts` | Prompt constants + assembly + cache | **Modify**: add `GenMode`, Python/R constants, `assemblePrefix()`, mode-aware `buildCachedPrefix()` |
| `netlify/edge-functions/_lib/prompt-assembly.test.ts` | Tests for per-mode composition | **Create** |
| `netlify/edge-functions/kode-svar-v2.ts` | v2 handler | **Modify**: read/validate `mode`, pass to `buildCachedPrefix`, mode-correct editor-script fence |
| `index.html` | Client | **Modify**: send `mode`; branch validation/repair (Python/R = name-grounding only) |
| `netlify/edge-functions/prompts/kode-svar.md` | Source-doc note | **Modify** |

---

## Task 1: Python/R prompt constants + `assemblePrefix()`

**Files:**
- Modify: `netlify/edge-functions/kode-svar.ts`
- Create: `netlify/edge-functions/_lib/prompt-assembly.test.ts`

- [ ] **Step 1: Add the mode type, Python/R constants, and `assemblePrefix` before `let _cachedPrefix`**

In `kode-svar.ts`, immediately BEFORE the line `let _cachedPrefix: string | null = null;` (≈736), insert:

```typescript
export type GenMode = "microdata" | "python" | "r";

export function coerceMode(m: unknown): GenMode {
  return m === "python" || m === "r" ? m : "microdata";
}

const SYSTEM_INTRO_PY = `\
Du er en ekspert-assistent som skriver PYTHON-kode for å analysere norske
registerdata fra microdata.no. Du svarer på norsk og engelsk, i brukerens språk.
Data hentes fra microdata.no-variabler via en \`#micro\`-blokk (se under) og
analyseres med pandas/statsmodels osv. Lag et komplett, kjørbart script: (a) en
\`#micro\`-blokk som importerer KUN variabler som finnes i katalogen nedenfor
(aldri finn opp variabelnavn), (b) en \`#python\`-blokk som gjør analysen. Bruk
eksakte variabelnavn fra katalogen.`;

const SYSTEM_INTRO_R = `\
Du er en ekspert-assistent som skriver R-kode for å analysere norske registerdata
fra microdata.no. Du svarer på norsk og engelsk, i brukerens språk. Data hentes
fra microdata.no-variabler via en \`#micro\`-blokk (se under) og analyseres med
tidyverse/base R. Lag et komplett, kjørbart script: (a) en \`#micro\`-blokk som
importerer KUN variabler som finnes i katalogen nedenfor (aldri finn opp
variabelnavn), (b) en \`#r\`-blokk som gjør analysen. Bruk eksakte variabelnavn.`;

const LANG_PREAMBLE_PY = `\
## Python-miljø

Skriv idiomatisk Python. Forhåndslastet: pandas, numpy, scipy, statsmodels,
matplotlib, seaborn, plotly. Trenger du andre pakker, installer med
\`import micropip; await micropip.install("pakke")\`. Du står fritt til å velge
verktøy: pandas/statsmodels for analyse, matplotlib/seaborn/plotly for figurer.`;

const LANG_PREAMBLE_R = `\
## R-miljø

Skriv idiomatisk R. tidyverse (dplyr, ggplot2, tidyr, …) og base R er
tilgjengelig. Trenger du andre pakker, installer med \`webr::install("pakke")\`.
Du står fritt til å velge verktøy: dplyr/base for analyse, ggplot2 for figurer.`;

const MICRO_IMPORT_BRIDGE = `\
## Last microdata-data inn i Python/R (#micro-bro)

Registerdata hentes i en \`#micro\`-blokk med microdata.no sin import-syntaks, og
blir tilgjengelig som en DataFrame (Python) / data.frame (R):

\`\`\`
#micro
require no.ssb.fdb:53 as fd
create-dataset folk
import fd/BEFOLKNING_KJOENN as kjonn
import fd/INNTEKT_WLONN 2022-01-01 as inntekt

#python
folk.groupby("kjonn")["inntekt"].agg(["mean", "median", "count"])
\`\`\`

Regler:
- Datasett-navnet (\`folk\`) blir variabelen i Python/R; kolonnene er import-
  ALIASENE (\`kjonn\`, \`inntekt\`), ikke de rå variabelnavnene.
- Missing blir NaN (Python) / NA (R).
- Importér KUN i \`#micro\`-blokken; all bearbeiding/analyse skjer i
  \`#python\`/\`#r\`-blokken. Importér gjerne flere variabler i samme datasett og
  koble/filtrer videre i pandas/dplyr.
- Import-kommando avhenger av temporalitet (se Databank-oppsett): \`Fast\` uten
  dato, \`Tverrsnitt\`/\`Akkumulert\` med ÉN dato innenfor variabelens gyldige
  datoer. Feil dato gir importfeil — dette gjelder fortsatt i \`#micro\`.`;

const INFERENCE_STRATEGY_PYR = `\
## Analytisk strategi (effekt-/sammenligningsspørsmål)

- **Konfunderende variabler.** Vis først den enkle sammenligningen, deretter en
  justert modell (statsmodels \`ols\`/\`logit\` eller R \`lm\`/\`glm\`) som kontrollerer
  for de bakenforliggende faktorene som er RELEVANTE for nettopp dette spørsmålet
  og finnes i katalogen — ikke en fast liste. Vis hvordan estimatet flytter seg
  fra rått til justert.
- **Heterogenitet.** Effekter varierer mellom grupper; ta med ÉN grov, godt
  befolket oppdeling (interaksjon eller stratifisert analyse) der det er naturlig.
- **Variabelvalg og avtrykk i registeret.** Den mest åpenbare variabelen er ikke
  alltid den beste — verken konseptuelt eller for antall enheter. Vurder også
  indirekte/proxy-mål bygd fra datoer, hendelser, familiepekere eller stønader
  (f.eks. «året etter siste forelders død» som arvetidspunkt), og oppgi proxyens
  antakelse.`;

const OUTPUT_PY = `\
## Svarformat

Svar i markdown, på brukerens språk. Gi en kort forklaring (1–3 setninger),
deretter ÉN kjørbar kodeblokk med \`#micro\` (datainnlasting) etterfulgt av
\`#python\` (analysen), i en \`\`\`python-blokk. Bruk eksakte variabelnavn fra
katalogen. Presenter gjerne både tall og figur (matplotlib/seaborn/plotly). Ikke
pakk svaret i JSON.`;

const OUTPUT_R = `\
## Svarformat

Svar i markdown, på brukerens språk. Gi en kort forklaring (1–3 setninger),
deretter ÉN kjørbar kodeblokk med \`#micro\` (datainnlasting) etterfulgt av \`#r\`
(analysen), i en \`\`\`r-blokk. Bruk eksakte variabelnavn fra katalogen. Presenter
gjerne både tall og figur (ggplot2). Ikke pakk svaret i JSON.`;

// Shared data-knowledge blocks reused for Python/R (microdata-DSL analysis
// blocks are intentionally excluded; the #micro bridge + OUTPUT_* frame that
// only #micro is used for import and the analysis is pandas/R).
const PYR_SHARED_BLOCKS = [
  DATABANK_CHEATSHEET,
  DATASET_STRUCTURE,
  RELATIONS_LINKS,
  PSEUDONYM_RULES,
  TYPE_RULES,
  DATE_QUIRKS,
  PRIVACY_RULES,
  MISSING_VALUES,
  NPR_RULES,
  INFERENCE_STRATEGY_PYR,
];

interface PrefixParts {
  catalogBlock?: string;
  kommuneBlock?: string;
  commandBlock?: string;
  functionBlock?: string;
}

// Pure prefix assembly. microdata uses the exact legacy composition (byte-stable
// v1 parity). python/r use shared data blocks + language preamble + #micro bridge
// and omit the microdata command/function reference and analysis grammar.
export function assemblePrefix(mode: GenMode, parts: PrefixParts): string {
  const cat = parts.catalogBlock ?? "";
  const kom = parts.kommuneBlock ?? "";
  if (mode === "python" || mode === "r") {
    const isPy = mode === "python";
    const blocks = [
      isPy ? SYSTEM_INTRO_PY : SYSTEM_INTRO_R,
      isPy ? LANG_PREAMBLE_PY : LANG_PREAMBLE_R,
      MICRO_IMPORT_BRIDGE,
      ...PYR_SHARED_BLOCKS,
      isPy ? OUTPUT_PY : OUTPUT_R,
      cat,
      kom,
    ];
    return blocks.filter((s) => s && s.length > 0).join("\n\n");
  }
  // microdata (default) — identical to the legacy buildCachedPrefix join.
  return [RULE_BLOCKS, cat, kom, parts.commandBlock ?? "", parts.functionBlock ?? "", CANONICAL_EXAMPLES]
    .filter((s) => s && s.length > 0)
    .join("\n\n");
}
```

- [ ] **Step 2: Write the composition test**

Create `netlify/edge-functions/_lib/prompt-assembly.test.ts`:

```typescript
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { assemblePrefix, coerceMode } from "../kode-svar.ts";

const PARTS = { catalogBlock: "CATX", kommuneBlock: "KOMX", commandBlock: "CMDX", functionBlock: "FNX" };

Deno.test("microdata prefix includes catalog, command, function, grammar and canonical examples", () => {
  const out = assemblePrefix("microdata", PARTS);
  assertEquals(out.includes("CATX"), true);
  assertEquals(out.includes("CMDX"), true);
  assertEquals(out.includes("FNX"), true);
  assertEquals(out.includes("KOMX"), true);
  assertEquals(out.includes("minimal grammatikk"), true);          // GRAMMAR_CHEATSHEET
  assertEquals(out.includes("Komplette eksempel-scripts"), true);  // CANONICAL_EXAMPLES
});

Deno.test("python prefix has Python preamble + #micro bridge + catalog, omits command/function/grammar", () => {
  const out = assemblePrefix("python", PARTS);
  assertEquals(out.includes("Python-miljø"), true);
  assertEquals(out.includes("#micro-bro"), true);
  assertEquals(out.includes("CATX"), true);
  assertEquals(out.includes("KOMX"), true);
  assertEquals(out.includes("CMDX"), false);
  assertEquals(out.includes("FNX"), false);
  assertEquals(out.includes("minimal grammatikk"), false);
  assertEquals(out.includes("Komplette eksempel-scripts"), false);
});

Deno.test("r prefix has R preamble, omits command/function", () => {
  const out = assemblePrefix("r", PARTS);
  assertEquals(out.includes("R-miljø"), true);
  assertEquals(out.includes("#micro-bro"), true);
  assertEquals(out.includes("CMDX"), false);
});

Deno.test("coerceMode validates the enum, defaulting to microdata", () => {
  assertEquals(coerceMode("python"), "python");
  assertEquals(coerceMode("r"), "r");
  assertEquals(coerceMode("microdata"), "microdata");
  assertEquals(coerceMode("bogus"), "microdata");
  assertEquals(coerceMode(undefined), "microdata");
});
```

- [ ] **Step 3: Run the test (expect pass — Step 1 already implemented assemblePrefix)**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/prompt-assembly.test.ts`
Expected: 4 tests PASS. (If a microdata-only marker string in the test doesn't match the real constant text, adjust the asserted substring to one that exists in `GRAMMAR_CHEATSHEET`/`CANONICAL_EXAMPLES`.)

- [ ] **Step 4: Type-check**

Run: `cd netlify/edge-functions && deno check kode-svar.ts`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/kode-svar.ts netlify/edge-functions/_lib/prompt-assembly.test.ts
git commit -m "feat(edge): mode-aware assemblePrefix + Python/R prompt blocks"
```

---

## Task 2: Make `buildCachedPrefix` mode-aware with a per-mode cache

**Files:**
- Modify: `netlify/edge-functions/kode-svar.ts`

- [ ] **Step 1: Replace the `_cachedPrefix` declaration with a per-mode map**

In `kode-svar.ts`, change:

```typescript
let _cachedPrefix: string | null = null;
```

to:

```typescript
const _cachedPrefix: Record<GenMode, string | null> = { microdata: null, python: null, r: null };
```

- [ ] **Step 2: Rewrite `buildCachedPrefix` to take `mode` and use `assemblePrefix`**

Replace the whole function body (the current `export async function buildCachedPrefix(origin: string): Promise<string> { … }`) with:

```typescript
export async function buildCachedPrefix(origin: string, mode: GenMode = "microdata"): Promise<string> {
  const cached = _cachedPrefix[mode];
  if (cached !== null) return cached;

  let catalogBlock = "";
  let kommuneBlock = "";
  try {
    const metaText = await fetchText(origin, "/variable_metadata.json");
    const meta = JSON.parse(metaText);
    catalogBlock = renderCatalog(meta);
    kommuneBlock = renderKommuneCodes(meta);
  } catch (_e) {
    catalogBlock = "";   // degrade: rules-only prompt is still usable
  }

  // command/function reference is microdata-only.
  let commandBlock = "";
  let functionBlock = "";
  if (mode === "microdata") {
    try {
      commandBlock = renderCommands(await fetchText(origin, "/command_help.js"));
    } catch (_e) {
      commandBlock = "";
    }
    try {
      functionBlock = renderFunctions(await fetchText(origin, "/functions.py"));
    } catch (_e) {
      functionBlock = "";
    }
  }

  const prefix = assemblePrefix(mode, { catalogBlock, kommuneBlock, commandBlock, functionBlock });
  _cachedPrefix[mode] = prefix;
  return prefix;
}
```

- [ ] **Step 3: Type-check and run the full edge suite**

Run: `cd netlify/edge-functions && deno check *.ts _lib/*.ts && deno test --allow-all _lib/`
Expected: type-check clean; all tests PASS (v1 default `buildCachedPrefix(origin)` still resolves to `mode="microdata"`).

- [ ] **Step 4: Commit**

```bash
git add netlify/edge-functions/kode-svar.ts
git commit -m "feat(edge): buildCachedPrefix(origin, mode) with per-mode cache"
```

---

## Task 3: v2 handler reads and applies `mode`

**Files:**
- Modify: `netlify/edge-functions/kode-svar-v2.ts`

- [ ] **Step 1: Import `coerceMode` / `GenMode`**

In `kode-svar-v2.ts`, change the import:

```typescript
import { buildCachedPrefix } from "./kode-svar.ts";
```

to:

```typescript
import { buildCachedPrefix, coerceMode, type GenMode } from "./kode-svar.ts";
```

- [ ] **Step 2: Add `mode` to the request body type**

Change the `RequestBody` interface to add:

```typescript
interface RequestBody {
  question: string;
  lang?: "no" | "en";
  script?: string;
  prior_script?: string;
  errors?: string;
  mode?: GenMode;
}
```

- [ ] **Step 3: Resolve the mode and pass it to `buildCachedPrefix`**

Replace:

```typescript
  const origin = new URL(request.url).origin;
  const system = await buildCachedPrefix(origin);
```

with:

```typescript
  const origin = new URL(request.url).origin;
  const mode: GenMode = coerceMode(body.mode);
  const system = await buildCachedPrefix(origin, mode);
```

- [ ] **Step 4: Make the editor-script fence match the mode**

The editor script is microdata in microdata mode but Python/R otherwise. Replace:

```typescript
    scriptContext ? `**Gjeldende skript i editor (kontekst):**\n\`\`\`microdata\n${scriptContext}\n\`\`\`\n` : ``,
```

with:

```typescript
    scriptContext ? `**Gjeldende skript i editor (kontekst):**\n\`\`\`${mode === "microdata" ? "microdata" : mode}\n${scriptContext}\n\`\`\`\n` : ``,
```

(The `priorScript` fence stays `microdata`: repair only runs in microdata mode.)

- [ ] **Step 5: Type-check + full edge suite**

Run: `cd netlify/edge-functions && deno check *.ts _lib/*.ts && deno test --allow-all _lib/`
Expected: clean; all PASS.

- [ ] **Step 6: Manual smoke test (Python mode)**

With `netlify dev` running:
```bash
curl -N -X POST http://localhost:8888/api/kode-svar-v2 \
  -H "Content-Type: application/json" -H "Authorization: Bearer $M2PY_ACCESS_TOKEN" \
  -d '{"question":"Gjennomsnittlig lønn etter kjønn 2022","lang":"no","mode":"python"}'
```
Expected: a streamed answer containing a ```python block with a `#micro` import section (real variable names) followed by `#python` pandas code. Repeat with `"mode":"r"` → `#r` dplyr. Repeat with no `mode` → microdata (unchanged).

- [ ] **Step 7: Commit**

```bash
git add netlify/edge-functions/kode-svar-v2.ts
git commit -m "feat(edge): v2 handler resolves editor mode → Python/R generation"
```

---

## Task 4: Client sends `mode` and branches validation/repair

**Files:**
- Modify: `index.html` (`runFastQueryV2`, ≈9800-9920 after prior changes)

- [ ] **Step 1: Add a code-extraction helper for Python/R grounding**

In `index.html`, immediately before `function findUnknownVarNames(script) {`, insert:

```javascript
      // Concatenate all fenced code-block bodies (any language) so name-grounding
      // can scan the #micro import inside a python/r answer without prose noise.
      function extractAllCode(md) {
        if (!md) return '';
        const re = /```\w*\s*\n([\s\S]*?)```/g;
        let m, out = [];
        while ((m = re.exec(md)) !== null) out.push(m[1]);
        return out.join('\n');
      }
```

- [ ] **Step 2: Compute `mode` and send it in the payload**

In `runFastQueryV2`, replace:

```javascript
        const payload = { question: text, lang, script: scriptContext || '' };
        const { accumulated, tokens } = await streamKodeSvarV2(payload, bubble, signal);
```

with:

```javascript
        const mode = (typeof activeEditorMode !== 'undefined' && activeEditorMode) ? activeEditorMode : 'microdata';
        const payload = { question: text, lang, script: scriptContext || '', mode };
        const { accumulated, tokens } = await streamKodeSvarV2(payload, bubble, signal);
```

- [ ] **Step 3: Branch the validation/repair tail on mode**

In `runFastQueryV2`, replace the entire microdata validation/repair block — from the comment `// Validate; on failure, attempt ONE repair round, then badge.` down to the `}` that closes the `while (script) {` loop (i.e. the block ending with `script = extractFirstMicrodataBlock(r2.accumulated);` followed by its closing `}`) — with a mode switch:

```javascript
        if (mode === 'microdata') {
          // Validate; on failure, attempt ONE repair round, then badge.
          let script = extractFirstMicrodataBlock(accumulated);
          let repaired = false;
          let finalBubble = bubble;
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
                { question: text, lang, script: scriptContext || '', mode, prior_script: script, errors: errStr },
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
            meta.tokens.input += r2.tokens.input; meta.tokens.output += r2.tokens.output;
            meta.tokens.cacheRead += r2.tokens.cacheRead; meta.tokens.cacheCreate += r2.tokens.cacheCreate;
            script = extractFirstMicrodataBlock(r2.accumulated);
          }
        } else {
          // Python/R: no m2py repair. Ground variable names in the #micro block only.
          const unknown = findUnknownVarNames(extractAllCode(accumulated));
          if (unknown.length) {
            const warn = renderValidationWarnings({
              passed: false,
              errors: unknown.map(n => ({ kind: 'unknown_variable', token: n, message: 'finnes ikke i katalogen' })),
            });
            if (warn) bubble.appendChild(warn);
          }
        }
        return meta;
```

- [ ] **Step 4: Syntax-check the inline scripts**

Run (from repo root):
```bash
python3 - <<'PY'
import re, subprocess, tempfile, os
html = open('index.html', encoding='utf-8').read()
blocks=[b for a,b in re.findall(r'<script\b([^>]*)>(.*?)</script>', html, re.S|re.I) if 'src=' not in a.lower()]
bad=0
for i,b in enumerate(blocks):
    f=tempfile.NamedTemporaryFile('w',suffix='.js',delete=False,encoding='utf-8'); f.write(b); f.close()
    r=subprocess.run(['node','--check',f.name],capture_output=True,text=True); os.unlink(f.name)
    if r.returncode: bad+=1; print(f"block {i}:\n{r.stderr[:800]}")
print("OK" if not bad else f"{bad} failed")
PY
```
Expected: `OK`.

- [ ] **Step 5: Browser load check**

Serve and load:
```bash
(python3 -m http.server 8777 >/tmp/h.log 2>&1 &) ; sleep 1
```
Navigate to `http://localhost:8777/index.html` (Playwright MCP), confirm only the benign `favicon.ico` 404 in console and that the page loads. Then stop the server (`pkill -f "http.server 8777"`).

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(ui): v2 sends editor mode; Python/R skip m2py repair, keep name-grounding"
```

---

## Task 5: Docs note + final verification

**Files:**
- Modify: `netlify/edge-functions/prompts/kode-svar.md`

- [ ] **Step 1: Add a note to the change log in `kode-svar.md`**

In `netlify/edge-functions/prompts/kode-svar.md`, inside the `KUN v2`-paragraph (the comment block), append:

```markdown
Modus-bevisst generering (2026-06-14): `buildCachedPrefix(origin, mode)` gir
microdata/python/r-varianter. Python/R = felles data-blokker + pakke-preamble +
`#micro`-bro + språk-`SYSTEM_INTRO`/`OUTPUT` (ingen kommando-/funksjons-referanse
eller microdata-analyse-grammatikk). Klienten sender editor-modus; Python/R kjører
ikke m2py-repair, kun navne-grounding på `#micro`-importen. microdata uendret.
```

- [ ] **Step 2: Full verification sweep**

Run:
```bash
cd netlify/edge-functions && deno check *.ts _lib/*.ts && deno test --allow-all _lib/
```
Expected: type-check clean; all unit tests PASS.

- [ ] **Step 3: Confirm v1 untouched**

Confirm the `kode-svar.ts` default export still calls `buildCachedPrefix(origin)` (no mode) — `grep -n "buildCachedPrefix(origin)" netlify/edge-functions/kode-svar.ts` should show the v1 handler call unchanged; `assemblePrefix("microdata", …)` reproduces the legacy composition (locked by Task 1 tests).

- [ ] **Step 4: Commit**

```bash
git add netlify/edge-functions/prompts/kode-svar.md
git commit -m "docs(edge): note mode-aware Python/R generation in kode-svar-v2"
```

---

## Self-review notes (coverage vs spec)

- **Mode passed client→server:** Task 4 Step 2 (payload `mode`), Task 3 Steps 1-3 (read/coerce/use).
- **Prompt partitioning (shared vs microdata, new Python/R blocks):** Task 1 (`assemblePrefix`, `PYR_SHARED_BLOCKS`, the new constants).
- **3-variant per-mode cache:** Task 2 (`_cachedPrefix` record).
- **microdata byte-parity:** Task 1 microdata branch = legacy array; locked by the composition test (Task 1 Step 2).
- **Picker untouched:** no change to picker/grounding code in any task.
- **Python/R: no repair, keep name-grounding:** Task 4 Step 3 `else` branch + `extractAllCode` (Step 1).
- **Editor-script fence matches mode:** Task 3 Step 4.
- **`SVARFORMAT_TILLEGG` stays (language-agnostic):** unchanged — still applied for all modes.
- **Fallback unknown mode → microdata:** `coerceMode` (Task 1), used in Task 3.
- **Tests:** per-mode composition + coerceMode unit-tested (Task 1); handler/client verified by type-check + manual (Tasks 3-4), matching repo conventions.
