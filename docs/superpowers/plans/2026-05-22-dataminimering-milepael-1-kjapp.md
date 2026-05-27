# Dataminimering Milepæl 1 — Kjapp-modus

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementer kjapp dataminimering-vurdering ende-til-ende: ny hamburger-meny-knapp, førstegangs-consent, streaming AI-svar fra Anthropic via Netlify Edge Function, og modal-visning av resultat.

**Architecture:** Browser kaller en Netlify Edge Function (Deno/TypeScript) som streamer fra Anthropic Messages API via Server-Sent Events. Edge Function transformerer Anthropic SSE til et enkelt klient-protokoll. En delt parser-modul ekstraherer personvern-kommentarer fra scriptet og detekterer språk, slik at vi kan injisere strukturert kontekst i prompten.

**Tech Stack:** Netlify Edge Functions (Deno + TypeScript), Anthropic Messages API (`claude-sonnet-4-6`), vanilla JS i `index.html`, localStorage for consent, Netlify Blobs for rate limit.

**Spec:** `docs/superpowers/specs/2026-05-22-dataminimering-evaluering-design.md`

---

## Filstruktur

Nye filer:
- `netlify/edge-functions/dm-quick.ts` — Edge Function
- `netlify/edge-functions/_lib/parse-script-context.ts` — parser-modul (delt med fremtidige funksjoner)
- `netlify/edge-functions/_lib/parse-script-context.test.ts` — Deno-tester
- `netlify/edge-functions/_lib/anthropic.ts` — tynn Anthropic-klient med streaming
- `netlify/edge-functions/_lib/rate-limit.ts` — per-IP rate limit via Netlify Blobs
- `netlify/edge-functions/prompts/_shared-principles.md` — delt prompt-fragment
- `netlify/edge-functions/prompts/dm-quick.md` — kjapp-prompt

Modifiserte filer:
- `netlify.toml` — legge til edge-function-deklarasjon
- `index.html` — hamburger-knapp, consent-modal, resultat-modal, fetch+stream-håndtering, M2PY_VERSION-bump
- `hjelp.html` — ny seksjon om dataminimering-funksjonen

Env-vars (settes i Netlify UI):
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MODEL` (default `claude-sonnet-4-6`)
- `M2PY_ALLOWED_ORIGINS` (kommaseparert)

---

### Task 1: Mappestruktur og netlify.toml-config

**Files:**
- Create: `netlify/edge-functions/_lib/.gitkeep`
- Create: `netlify/edge-functions/prompts/.gitkeep`
- Modify: `netlify.toml`

- [ ] **Step 1: Opprett mappestruktur**

```bash
mkdir -p netlify/edge-functions/_lib netlify/edge-functions/prompts
touch netlify/edge-functions/_lib/.gitkeep
touch netlify/edge-functions/prompts/.gitkeep
```

- [ ] **Step 2: Legg til edge-function-route i netlify.toml**

Legg til på slutten av filen:

```toml
[[edge_functions]]
  function = "dm-quick"
  path = "/api/dm-quick"
```

- [ ] **Step 3: Verifiser at filer er der**

Run: `ls netlify/edge-functions/_lib netlify/edge-functions/prompts`
Expected: begge mappene listes, hver med en `.gitkeep`

- [ ] **Step 4: Commit**

```bash
git add netlify/ netlify.toml
git commit -m "feat: dataminimering — sett opp edge-function-mappestruktur"
```

---

### Task 2: Parser — parsePersonvernComments (TDD)

Parser ekstraherer både blokk-form (`// personvern blokk start` … `slutt`) og enkeltlinje-form (`// personvern: …`), støtter både `//` og `#` som kommentartegn, og klassifiserer hver verdi som strukturert (kjent feltnavn) eller fritekst.

**Files:**
- Create: `netlify/edge-functions/_lib/parse-script-context.ts`
- Create: `netlify/edge-functions/_lib/parse-script-context.test.ts`

- [ ] **Step 1: Skriv tester først**

Innhold `netlify/edge-functions/_lib/parse-script-context.test.ts`:

```typescript
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { parsePersonvernComments } from "./parse-script-context.ts";

Deno.test("ingen kommentarer gir tom struktur", () => {
  const result = parsePersonvernComments("import all from BEFOLKNING\nkeep if alder >= 18");
  assertEquals(result.structured, {});
  assertEquals(result.freetext, []);
  assertEquals(result.hasAny, false);
});

Deno.test("enkeltlinje med kjent feltnavn er strukturert", () => {
  const script = "// personvern: formål: Studere utdanning og inntekt";
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Studere utdanning og inntekt");
  assertEquals(r.freetext, []);
  assertEquals(r.hasAny, true);
});

Deno.test("enkeltlinje uten kjent feltnavn er fritekst", () => {
  const script = "// personvern: kommune nødvendig for regionale analyser";
  const r = parsePersonvernComments(script);
  assertEquals(r.structured, {});
  assertEquals(r.freetext.length, 1);
  assertEquals(r.freetext[0].text, "kommune nødvendig for regionale analyser");
  assertEquals(r.freetext[0].line, 1);
});

Deno.test("blokk-form med strukturerte felter", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "// sentrale variabler: A, B",
    "// personvern blokk slutt",
    "import all from BEFOLKNING",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
  assertEquals(r.structured["sentrale variabler"], "A, B");
});

Deno.test("blokk med fritekst-linje", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "// fritekst-merknad uten feltnavn",
    "// personvern blokk slutt",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
  assertEquals(r.freetext.length, 1);
  assertEquals(r.freetext[0].text, "fritekst-merknad uten feltnavn");
});

Deno.test("# kommentartegn (Python/R) støttes", () => {
  const script = "# personvern: formål: Test fra Python";
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test fra Python");
});

Deno.test("manglende blokk-slutt — stopper ved ikke-kommentar-linje", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "import all from BEFOLKNING",
    "keep if alder >= 18",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
});

Deno.test("siste definisjon vinner ved konflikt", () => {
  const script = [
    "// personvern: formål: Gammel",
    "// personvern: formål: Ny",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Ny");
});
```

- [ ] **Step 2: Kjør testene — de skal feile**

Run: `deno test netlify/edge-functions/_lib/parse-script-context.test.ts`
Expected: FAIL, "module not found" (parse-script-context.ts finnes ikke ennå)

- [ ] **Step 3: Implementer parser**

Innhold `netlify/edge-functions/_lib/parse-script-context.ts`:

```typescript
const KNOWN_FIELDS = new Set([
  "formål",
  "sentrale variabler",
  "tidsperiode",
  "geografi",
  "sensitive grupper",
  "alternativer vurdert",
]);

const BLOCK_START_RE = /^\s*(?:\/\/+|#+)\s*personvern\s+blokk\s+start\s*$/i;
const BLOCK_END_RE = /^\s*(?:\/\/+|#+)\s*personvern\s+blokk\s+slutt\s*$/i;
const SINGLE_LINE_RE = /^\s*(?:\/\/+|#+)\s*personvern\s*:\s*(.*)$/i;
const BLOCK_INNER_RE = /^\s*(?:\/\/+|#+)\s*(.*)$/;
const NONCOMMENT_RE = /^\s*[^/#\s]/;

export interface ScriptContext {
  structured: Record<string, string>;
  freetext: { line: number; text: string }[];
  hasAny: boolean;
}

function classifyAndStore(
  raw: string,
  lineNumber: number,
  ctx: ScriptContext,
): void {
  const m = raw.match(/^([^:]+):\s*(.+)$/);
  if (m) {
    const field = m[1].trim().toLowerCase();
    const value = m[2].trim();
    if (KNOWN_FIELDS.has(field)) {
      ctx.structured[field] = value;
      ctx.hasAny = true;
      return;
    }
  }
  ctx.freetext.push({ line: lineNumber, text: raw.trim() });
  ctx.hasAny = true;
}

export function parsePersonvernComments(script: string): ScriptContext {
  const ctx: ScriptContext = { structured: {}, freetext: [], hasAny: false };
  const lines = script.split("\n");
  let inBlock = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;

    if (BLOCK_START_RE.test(line)) {
      inBlock = true;
      continue;
    }
    if (inBlock && BLOCK_END_RE.test(line)) {
      inBlock = false;
      continue;
    }
    if (inBlock) {
      if (NONCOMMENT_RE.test(line)) {
        inBlock = false;
        // fall through til vanlig parsing av denne linjen
      } else {
        const m = line.match(BLOCK_INNER_RE);
        if (m && m[1].trim()) {
          classifyAndStore(m[1], lineNo, ctx);
        }
        continue;
      }
    }

    const single = line.match(SINGLE_LINE_RE);
    if (single) {
      classifyAndStore(single[1], lineNo, ctx);
    }
  }

  return ctx;
}
```

- [ ] **Step 4: Kjør testene — de skal passere**

Run: `deno test netlify/edge-functions/_lib/parse-script-context.test.ts`
Expected: PASS for alle 8 tester

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/parse-script-context.ts netlify/edge-functions/_lib/parse-script-context.test.ts
git commit -m "feat: dataminimering — parser for personvern-kommentarer"
```

---

### Task 3: Parser — detectLanguage (TDD)

Heuristikk for å detektere om scriptet er microdata-DSL, Python, R, eller mixed. Vekter signaler.

**Files:**
- Modify: `netlify/edge-functions/_lib/parse-script-context.ts`
- Modify: `netlify/edge-functions/_lib/parse-script-context.test.ts`

- [ ] **Step 1: Skriv tester**

Legg til i `parse-script-context.test.ts`:

```typescript
import { detectLanguage } from "./parse-script-context.ts";

Deno.test("microdata-script detekteres", () => {
  const script = `
import all from BEFOLKNING
keep if alder >= 18
collapse (mean) inntekt, by(kommune)
`;
  assertEquals(detectLanguage(script), "microdata");
});

Deno.test("python-script detekteres", () => {
  const script = `
import pandas as pd
from sklearn import metrics
def analyze(df):
    return df.mean()
`;
  assertEquals(detectLanguage(script), "python");
});

Deno.test("r-script detekteres", () => {
  const script = `
library(dplyr)
df <- read.csv("data.csv")
df %>% filter(age >= 18)
`;
  assertEquals(detectLanguage(script), "r");
});

Deno.test("mixed-script detekteres", () => {
  const script = `
import all from BEFOLKNING
collapse (mean) inntekt
# Python-del nedenfor
import pandas as pd
df = pd.read_csv("output.csv")
`;
  assertEquals(detectLanguage(script), "mixed");
});

Deno.test("tomt script returnerer microdata som default", () => {
  assertEquals(detectLanguage(""), "microdata");
});
```

- [ ] **Step 2: Kjør testene — skal feile**

Run: `deno test netlify/edge-functions/_lib/parse-script-context.test.ts`
Expected: FAIL, "detectLanguage is not exported"

- [ ] **Step 3: Implementer detectLanguage**

Legg til på slutten av `parse-script-context.ts`:

```typescript
export type Language = "microdata" | "python" | "r" | "mixed";

const MICRODATA_PATTERNS = [
  /^\s*import\s+(all\s+)?(variables?\s+)?.*\s+from\s+\w+/im,
  /\bcollapse\s*\(\s*(mean|sum|sd|count|median|min|max|p\d+)/i,
  /^\s*tabulate\s+\w+/im,
  /^\s*summarize\s+\w+/im,
  /^\s*keep\s+if\s+/im,
  /^\s*drop\s+if\s+/im,
  /^\s*merge\s+\w+\s+(into|onto)\s+/im,
];

const PYTHON_PATTERNS = [
  /^\s*from\s+\w+\s+import\s+/m,
  /^\s*import\s+\w+(\s+as\s+\w+)?$/m,
  /^\s*def\s+\w+\s*\(/m,
  /^\s*class\s+\w+/m,
  /\bpd\.|np\.|pandas|numpy\b/i,
];

const R_PATTERNS = [
  /^\s*library\s*\(/m,
  /<-\s*[a-zA-Z0-9_(]/,
  /\bdata\.frame\b/,
  /%>%/,
  /^\s*require\s*\(/m,
];

function countMatches(script: string, patterns: RegExp[]): number {
  let n = 0;
  for (const p of patterns) if (p.test(script)) n++;
  return n;
}

export function detectLanguage(script: string): Language {
  if (!script.trim()) return "microdata";

  const m = countMatches(script, MICRODATA_PATTERNS);
  const p = countMatches(script, PYTHON_PATTERNS);
  const r = countMatches(script, R_PATTERNS);

  const hasMicrodata = m >= 1;
  const hasPython = p >= 2;
  const hasR = r >= 2;

  if (hasMicrodata && (hasPython || hasR)) return "mixed";
  if (hasMicrodata) return "microdata";
  if (hasPython && !hasR) return "python";
  if (hasR && !hasPython) return "r";
  if (hasPython && hasR) return p >= r ? "python" : "r";
  return "microdata";
}
```

- [ ] **Step 4: Kjør testene — skal passere**

Run: `deno test netlify/edge-functions/_lib/parse-script-context.test.ts`
Expected: PASS for alle 13 tester

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/parse-script-context.ts netlify/edge-functions/_lib/parse-script-context.test.ts
git commit -m "feat: dataminimering — språkdeteksjon heuristikk"
```

---

### Task 4: Prompt-filer (shared-principles og dm-quick)

Tekst-filer som Edge Function leser inn ved oppstart. Ingen tester — disse itereres manuelt ved evaluering i Task 15.

**Files:**
- Create: `netlify/edge-functions/prompts/_shared-principles.md`
- Create: `netlify/edge-functions/prompts/dm-quick.md`

- [ ] **Step 1: Skriv `_shared-principles.md`**

```markdown
RETTSLIG GRUNNLAG

Vurderingen forankres i:
- Personvernforordningen art. 5(1)(c) (dataminimering): personopplysninger
  skal være "adekvate, relevante og begrenset til det som er nødvendig for å
  oppnå formålene".
- Helseregisterloven § 6: graden av personidentifikasjon skal ikke overskride
  det som er nødvendig for formålet.
- Personvernforordningen art. 89(1): forskning krever egnede garantier som
  anonymisering eller pseudonymisering der det er mulig.
- Personvernforordningen art. 5(1)(b) (formålsbegrensning): relevant når en
  variabel virker hentet "for sikkerhets skyld".

Kalibreringsregel: personvernforordningen gir ikke ett endelig svar på hva
som er "nødvendig" — det avhenger av formålet. Formuler observasjoner som
muligheter for minimering, ikke som lovbrudd. Endelig vurdering ligger hos
forsker og dataansvarlig.

VURDERINGSDIMENSJONER

1. Ubrukte variabler — importert men aldri brukt.
2. Variabel-granularitet — ICD-kode-detaljnivå, dato-oppløsning, geografi,
   inntekt, alder.
3. Populasjons-avgrensing — `keep if`/`drop if`-filtere.
4. Tidsperiode — er tidsvinduet snevert nok.
5. Sjeldne kombinasjoner — filterkjeder som krymper til sårbar undergruppe.
6. Koblingsbehov — er alle `merge`/`import` nødvendige.
7. Aggregat vs individnivå — tidlig nok `collapse`?
8. Direkte identifikatorer i transformasjoner.

IKKE VURDERT FRA SCRIPTET

Følgende krever kontekst utenfor scriptet og skal ikke gjettes på:
- Analyseplan og dokumentert begrunnelse.
- Tilgangsbegrensning og lagringstid.
- Mulighet for alternativer (syntetiske data, fjernanalyse).
- Senere gjenbruk.

NB: Disclosure-control i resultater (T1-T8) håndteres separat av m2py.
Fokuser på selve dataminimeringen i scriptet.
```

- [ ] **Step 2: Skriv `dm-quick.md`**

```markdown
Du vurderer om et forskningsscript som henter mikrodata fra microdata.no
praktiserer dataminimering — prinsippet om å hente og bruke kun det minimum
av data som trengs for problemstillingen.

{{SHARED_PRINCIPLES}}

KOMMENTARER OG TIDLIGERE ERKLÆRT KONTEKST

Scriptet kan inneholde kommentarer som beskriver formål, antakelser eller
begrunnelser. Les og bruk alle kommentarer aktivt.

Spesielt:
- Linjer i en `// personvern blokk start ... slutt`-blokk, og enkeltlinjer
  som starter med `// personvern: <feltnavn>:` der feltnavn er ett av
  formål / sentrale variabler / tidsperiode / geografi / sensitive grupper /
  alternativer vurdert, er strukturerte svar fra forskeren. Behandle som
  forskerens autoritative erklæring.
- Linjer som starter med `// personvern: <fritekst>` (eller fritekst inne i
  blokk) er forskerens egne begrunnelser.

Disse er trukket ut i seksjonen TIDLIGERE ERKLÆRT KONTEKST nedenfor. Hvis en
observasjon allerede er begrunnet der, ikke gjenta den — pek heller på om
begrunnelsen virker tilstrekkelig.

{{CONTEXT_SECTION}}

KATEGORISER SCRIPTET FØRST

- A) Full analyse — import + tydelig analyse
- B) Synlig hensikt — import + transformasjon, analyse mangler
- C) Ren import — kun import-linjer + minimale rename

SPRÅK

Detektert språk: {{LANGUAGE}}

OUTPUT (norsk, markdown)

## Klassifisering
Kategori: <A|B|C>
Språk: <microdata|R|python|mixed>
Antatt analyseintensjon: <kort, eller "ikke synlig fra scriptet">

## Samlet vurdering
2–4 setninger med skala (god/akseptabel/forbedringspotensial), forankret i
relevante hjemler. Bruk typisk art. 5(1)(c) og hregl § 6 for helsedata;
art. 89(1) der aggregering/pseudonymisering er aktuelt; art. 5(1)(b) der
variabler virker hentet uten kobling til uttrykkelig formål. Ikke alle
hjemler trenger nevnes — bare de som styrker vurderingen.

## Observasjoner
- **<variabel, linjenr eller mønster>** — <problem>
  - Forslag: <konkret endring>
  - Sikkerhet: <høy | medium | lav>

Sortér etter sikkerhet. Hopp over kategorier uten observasjoner.

## Spørsmål til forsker
Kun hvis kategori B eller C. Maks 3 spørsmål.

REGLER
- Vær konkret. Pek på variabelnavn eller linjenummer.
- Ikke produser forslag bare for å produsere.
- Markér sikkerhet ærlig.
- Du ser kun scriptet — si fra om vurderingen ville endret seg med mer kontekst.

SCRIPT

{{SCRIPT}}
```

- [ ] **Step 3: Commit**

```bash
git add netlify/edge-functions/prompts/
git commit -m "feat: dataminimering — prompt-filer (shared + dm-quick)"
```

---

### Task 5: Anthropic-klient med streaming

Tynn wrapper for Anthropic Messages API. Transformerer Anthropic SSE til vårt enkle protokoll.

**Files:**
- Create: `netlify/edge-functions/_lib/anthropic.ts`

- [ ] **Step 1: Implementer klienten**

Innhold `netlify/edge-functions/_lib/anthropic.ts`:

```typescript
const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION = "2023-06-01";

export interface AnthropicStreamOptions {
  apiKey: string;
  model: string;
  prompt: string;
  maxTokens?: number;
}

export interface StreamEvent {
  type: "text" | "done" | "error";
  text?: string;
  inputTokens?: number;
  outputTokens?: number;
  message?: string;
}

export async function streamAnthropic(
  opts: AnthropicStreamOptions,
): Promise<ReadableStream<Uint8Array>> {
  const upstream = await fetch(ANTHROPIC_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": opts.apiKey,
      "anthropic-version": ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: opts.model,
      max_tokens: opts.maxTokens ?? 2000,
      stream: true,
      messages: [{ role: "user", content: opts.prompt }],
    }),
  });

  if (!upstream.ok || !upstream.body) {
    const body = await upstream.text();
    throw new Error(`Anthropic API error ${upstream.status}: ${body}`);
  }

  return transformAnthropicStream(upstream.body);
}

function transformAnthropicStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let buffer = "";
  let inputTokens = 0;
  let outputTokens = 0;

  return new ReadableStream({
    async start(controller) {
      const reader = upstream.getReader();
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let nlIdx;
          while ((nlIdx = buffer.indexOf("\n\n")) >= 0) {
            const event = buffer.slice(0, nlIdx);
            buffer = buffer.slice(nlIdx + 2);
            const dataLine = event.split("\n").find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            const payload = dataLine.slice(5).trim();
            if (!payload) continue;
            try {
              const obj = JSON.parse(payload);
              if (obj.type === "content_block_delta" && obj.delta?.type === "text_delta") {
                const out: StreamEvent = { type: "text", text: obj.delta.text };
                controller.enqueue(encoder.encode(`data: ${JSON.stringify(out)}\n\n`));
              } else if (obj.type === "message_start" && obj.message?.usage) {
                inputTokens = obj.message.usage.input_tokens ?? 0;
              } else if (obj.type === "message_delta" && obj.usage) {
                outputTokens = obj.usage.output_tokens ?? outputTokens;
              }
            } catch (_e) {
              // ignorerer ikke-JSON event-data
            }
          }
        }
        const done: StreamEvent = {
          type: "done",
          inputTokens,
          outputTokens,
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(done)}\n\n`));
      } catch (e) {
        const err: StreamEvent = { type: "error", message: String(e) };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(err)}\n\n`));
      } finally {
        controller.close();
      }
    },
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add netlify/edge-functions/_lib/anthropic.ts
git commit -m "feat: dataminimering — Anthropic streaming-klient"
```

---

### Task 6: Edge Function dm-quick (uten sikkerhetslag)

Edge Function leser script + active_columns, bygger kontekst-tekst fra parser, leser prompt-fil, kaller Anthropic via klienten, streamer tilbake.

**Files:**
- Create: `netlify/edge-functions/dm-quick.ts`

- [ ] **Step 1: Implementer Edge Function**

Innhold `netlify/edge-functions/dm-quick.ts`:

```typescript
import {
  detectLanguage,
  parsePersonvernComments,
  type ScriptContext,
} from "./_lib/parse-script-context.ts";
import { streamAnthropic } from "./_lib/anthropic.ts";

interface RequestBody {
  script: string;
  active_columns?: string[];
}

function renderContextSection(ctx: ScriptContext): string {
  if (!ctx.hasAny) return "(Ingen personvern-kommentarer funnet i scriptet.)";
  const out: string[] = ["TIDLIGERE ERKLÆRT KONTEKST"];
  if (Object.keys(ctx.structured).length > 0) {
    out.push("", "Strukturert (fra personvern-blokk eller `personvern:<felt>:`-linjer):");
    for (const [field, value] of Object.entries(ctx.structured)) {
      out.push(`- ${field}: ${value}`);
    }
  }
  if (ctx.freetext.length > 0) {
    out.push("", "Fritekst (fra `personvern:`-linjer):");
    for (const f of ctx.freetext) {
      out.push(`- (linje ${f.line}) ${f.text}`);
    }
  }
  return out.join("\n");
}

async function loadPrompt(name: string): Promise<string> {
  const url = new URL(`./prompts/${name}.md`, import.meta.url);
  return await Deno.readTextFile(url);
}

export default async (request: Request): Promise<Response> => {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  let body: RequestBody;
  try {
    body = await request.json();
  } catch (_) {
    return new Response("Invalid JSON", { status: 400 });
  }
  if (!body.script || typeof body.script !== "string") {
    return new Response("Missing script", { status: 400 });
  }

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    return new Response("Server misconfigured: ANTHROPIC_API_KEY missing", { status: 500 });
  }

  const ctx = parsePersonvernComments(body.script);
  const language = detectLanguage(body.script);
  const contextSection = renderContextSection(ctx);

  const [sharedPrinciples, dmQuickTemplate] = await Promise.all([
    loadPrompt("_shared-principles"),
    loadPrompt("dm-quick"),
  ]);

  const prompt = dmQuickTemplate
    .replace("{{SHARED_PRINCIPLES}}", sharedPrinciples)
    .replace("{{CONTEXT_SECTION}}", contextSection)
    .replace("{{LANGUAGE}}", language)
    .replace("{{SCRIPT}}", body.script);

  try {
    const stream = await streamAnthropic({ apiKey, model, prompt, maxTokens: 2000 });
    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  } catch (e) {
    return new Response(`Upstream error: ${e}`, { status: 502 });
  }
};
```

- [ ] **Step 2: Commit**

```bash
git add netlify/edge-functions/dm-quick.ts
git commit -m "feat: dataminimering — dm-quick edge function"
```

---

### Task 7: Lokal test av Edge Function med curl

Verifiserer ende-til-ende-flyten lokalt før vi rører frontend.

**Files:** ingen — kun verifisering

- [ ] **Step 1: Sett ANTHROPIC_API_KEY i en lokal `.env`-fil for Netlify CLI**

Forutsetter at Netlify CLI er installert (`npm install -g netlify-cli`).

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
echo ".env" >> .gitignore
```

- [ ] **Step 2: Start Netlify dev-server**

Run: `netlify dev`
Expected: server starter på `http://localhost:8888`

- [ ] **Step 3: Send test-kall i et annet terminal-vindu**

```bash
curl -N -X POST http://localhost:8888/api/dm-quick \
  -H "Content-Type: application/json" \
  -d '{
    "script": "// personvern: formål: Studere inntektsforskjeller\nimport all from BEFOLKNING\nkeep if alder >= 18\nsummarize INNTEKT, by(kommune)"
  }'
```

Expected: streamede `data: {"type":"text","text":"..."}`-linjer, etterfulgt av en `data: {"type":"done","inputTokens":...,"outputTokens":...}`-linje. Innholdet skal være en markdown-formatert vurdering med seksjonene Klassifisering, Samlet vurdering, og evt. Observasjoner.

- [ ] **Step 4: Hvis output er rart, iterér prompten**

Se Task 15 for systematisk evaluering. For nå holder det å se at protokollen virker og at responsen er rimelig norsk markdown.

- [ ] **Step 5: Commit `.gitignore`-endring**

```bash
git add .gitignore
git commit -m "chore: ignore .env"
```

---

### Task 8: Frontend — hamburger-meny-knapp og consent-state

Legger til to elementer i hamburger-menyen, men kun "Vurder dataminimering" gjøres aktiv i denne milepælen. Grundig-knappen følger i Milepæl 2.

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Finn nåværende hamburger-dropdown**

Run: `grep -n 'hamburgerDropdown' /Users/hom/Documents/GitHub/m2py/index.html | head -5`

Noter linjenummer for `<div class="hamburger-dropdown" id="hamburgerDropdown">`. Den ligger rundt linje 888.

- [ ] **Step 2: Legg til ny meny-seksjon**

Inne i `<div class="hamburger-dropdown" id="hamburgerDropdown">`, før `</div>` som lukker dropdown, legg til:

```html
<div class="menu-section-label" style="padding: 6px 14px; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-top: 1px solid var(--border); margin-top: 4px; padding-top: 8px;">Personvern</div>
<button type="button" id="btnDmQuick">Vurder dataminimering</button>
```

(Grundig-knappen legges til i Milepæl 2.)

- [ ] **Step 3: Bump M2PY_VERSION**

Finn linjen `window.M2PY_VERSION = '2026-05-20b';` og endre til `'2026-05-22a'`.

- [ ] **Step 4: Legg til localStorage-helper og state-hook**

Etter eksisterende script-tag-init, legg til:

```javascript
// --- Dataminimering: consent og state ---
const DM_CONSENT_KEY = 'microdata_dm_consent';
function hasDmConsent() { return localStorage.getItem(DM_CONSENT_KEY) === '1'; }
function setDmConsent(v) { localStorage.setItem(DM_CONSENT_KEY, v ? '1' : '0'); }
```

- [ ] **Step 5: Verifiser i browser**

Last `http://localhost:8888/` på nytt. Åpne hamburger-menyen — "Personvern"-overskrift og "Vurder dataminimering"-knapp skal vises. Knappen gjør ingenting ennå.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat: dataminimering — meny-knapp og consent-state"
```

---

### Task 9: Frontend — førstegangs-consent-modal

Modal vises ved første klikk på "Vurder dataminimering" hvis ikke consent er gitt.

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Legg til consent-modal HTML**

Inne i `<body>`, før `</body>`, legg til:

```html
<div id="dmConsentBackdrop" class="modal-backdrop" style="display:none;">
  <div class="modal" style="max-width: 540px;">
    <h2>AI-vurdering av dataminimering</h2>
    <p>
      Vurderingen bruker AI fra Anthropic. Når du klikker
      "Aksepter og fortsett", sendes scriptet og dets kommentarer til Anthropic
      for vurdering. <strong>Faktiske mikrodata-verdier sendes ikke</strong> —
      m2py kjører lokalt i nettleseren, og dataverdiene blir aldri en del av
      denne forespørselen.
    </p>
    <p>
      Variabelnavn, kommentarer og selve script-koden overføres. Anthropic bruker
      ikke API-input til trening som standard.
    </p>
    <p>
      Du kan tilbakekalle denne tillatelsen senere via hamburger-menyen.
    </p>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 16px;">
      <button type="button" id="dmConsentCancel">Avbryt</button>
      <button type="button" id="dmConsentAccept" class="primary">Aksepter og fortsett</button>
    </div>
  </div>
</div>
```

(Bruk eksisterende `.modal-backdrop` og `.modal` CSS-klasser hvis de finnes; ellers bruk inline-style som over.)

- [ ] **Step 2: Legg til JS-håndtering**

Etter consent-helperne fra Task 8:

```javascript
function showDmConsent(onAccept) {
  const backdrop = document.getElementById('dmConsentBackdrop');
  backdrop.style.display = 'flex';
  document.getElementById('dmConsentCancel').onclick = () => {
    backdrop.style.display = 'none';
  };
  document.getElementById('dmConsentAccept').onclick = () => {
    setDmConsent(true);
    backdrop.style.display = 'none';
    if (onAccept) onAccept();
  };
}
```

- [ ] **Step 3: Test i browser**

Last på nytt, åpne consent-modal manuelt fra konsollen: `showDmConsent()`. Verifiser at modalen vises, "Avbryt" lukker uten å sette consent, "Aksepter og fortsett" setter localStorage `microdata_dm_consent='1'`.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "feat: dataminimering — førstegangs-consent-modal"
```

---

### Task 10: Frontend — resultat-modal og SSE-leser

Modal som viser streamet svar fra Edge Function.

**Files:**
- Modify: `index.html`

- [ ] **Step 1: Legg til resultat-modal HTML**

Før `</body>`:

```html
<div id="dmResultBackdrop" class="modal-backdrop" style="display:none;">
  <div class="modal" style="max-width: 780px; max-height: 80vh; display: flex; flex-direction: column;">
    <h2>Dataminimering-vurdering</h2>
    <div id="dmResultBody" style="flex: 1; overflow-y: auto; padding: 8px 0; white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 13px; line-height: 1.5;"></div>
    <div id="dmResultStatus" style="font-size: 12px; color: var(--muted); padding: 4px 0;"></div>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top: 8px;">
      <button type="button" id="dmResultCancel">Avbryt</button>
      <button type="button" id="dmResultCopy">Kopier</button>
      <button type="button" id="dmResultClose" class="primary">Lukk</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Implementer SSE-leser**

Etter consent-koden:

```javascript
async function runDmQuick(script) {
  const backdrop = document.getElementById('dmResultBackdrop');
  const body = document.getElementById('dmResultBody');
  const status = document.getElementById('dmResultStatus');
  const cancelBtn = document.getElementById('dmResultCancel');
  const copyBtn = document.getElementById('dmResultCopy');
  const closeBtn = document.getElementById('dmResultClose');

  body.textContent = '';
  status.textContent = 'Henter vurdering…';
  backdrop.style.display = 'flex';
  cancelBtn.disabled = false;
  copyBtn.disabled = true;

  const controller = new AbortController();
  cancelBtn.onclick = () => controller.abort();
  closeBtn.onclick = () => { backdrop.style.display = 'none'; };

  let accumulated = '';
  let inputTokens = 0;
  let outputTokens = 0;

  try {
    const resp = await fetch('/api/dm-quick', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ script }),
      signal: controller.signal,
    });
    if (!resp.ok || !resp.body) {
      status.textContent = `Feil: ${resp.status} ${await resp.text()}`;
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
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
        try {
          const obj = JSON.parse(dataLine.slice(5).trim());
          if (obj.type === 'text') {
            accumulated += obj.text;
            body.textContent = accumulated;
          } else if (obj.type === 'done') {
            inputTokens = obj.inputTokens || 0;
            outputTokens = obj.outputTokens || 0;
          } else if (obj.type === 'error') {
            status.textContent = `Feil fra server: ${obj.message}`;
          }
        } catch (_) { /* ignore */ }
      }
    }
    status.textContent = `Ferdig. ${inputTokens} input / ${outputTokens} output tokens.`;
    cancelBtn.disabled = true;
    copyBtn.disabled = false;
  } catch (e) {
    if (e.name === 'AbortError') {
      status.textContent = 'Avbrutt.';
    } else {
      status.textContent = `Feil: ${e.message}`;
    }
  }

  copyBtn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(accumulated);
      copyBtn.textContent = 'Kopiert!';
      setTimeout(() => copyBtn.textContent = 'Kopier', 1500);
    } catch (_) { /* ignore */ }
  };
}
```

- [ ] **Step 3: Koble menyknapp til runDmQuick**

Etter de andre menyknapp-handlerne (søk etter `getElementById` for andre knapper i hamburger-menyen):

```javascript
document.getElementById('btnDmQuick').addEventListener('click', () => {
  document.getElementById('hamburgerDropdown').classList.remove('open');
  const editor = document.getElementById('scriptInput'); // bekrefte i kode at det er rett ID
  const script = (editor && editor.value || '').trim();
  if (!script) {
    alert('Editor er tom. Skriv et script først.');
    return;
  }
  if (!hasDmConsent()) {
    showDmConsent(() => runDmQuick(script));
  } else {
    runDmQuick(script);
  }
});
```

NB: Bekreft at script-editor sin element-ID er korrekt (`scriptInput` eller annet — sjekk eksisterende kode i `index.html` med `grep -n 'getElementById.*[Ss]cript' index.html`).

- [ ] **Step 4: Test i browser**

1. Last `http://localhost:8888/` (krever `netlify dev` kjørende)
2. Skriv et enkelt script i editor:
   ```
   import all from BEFOLKNING
   keep if alder >= 18
   summarize INNTEKT, by(kommune)
   ```
3. Åpne hamburger → Vurder dataminimering
4. Consent-modal vises → Aksepter
5. Resultat-modal vises med spinner-tekst, deretter streamed vurdering
6. Status nederst viser token-tall ved ferdig

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat: dataminimering — resultat-modal og SSE-leser i frontend"
```

---

### Task 11: Sikkerhet — origin-sjekk

Avviser kall fra andre opphav enn m2py-domenet (og localhost for utvikling).

**Files:**
- Modify: `netlify/edge-functions/dm-quick.ts`

- [ ] **Step 1: Legg til origin-sjekk øverst i handleren**

Finn `if (request.method !== "POST")` i dm-quick.ts, og legg til *foran* den:

```typescript
const allowedOrigins = (Deno.env.get("M2PY_ALLOWED_ORIGINS") ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);
const origin = request.headers.get("origin");
if (allowedOrigins.length > 0 && (!origin || !allowedOrigins.includes(origin))) {
  return new Response("Forbidden", { status: 403 });
}
```

- [ ] **Step 2: Sett env-var lokalt**

Legg til i `.env`:

```
M2PY_ALLOWED_ORIGINS=http://localhost:8888,https://m2py.netlify.app
```

(Erstatt produksjons-URL med faktisk m2py-domene.)

- [ ] **Step 3: Restart netlify dev og verifiser**

- Fra browser på `http://localhost:8888`: kjør Vurder dataminimering → skal fungere.
- Med curl uten Origin-header: skal returnere 403.

```bash
curl -X POST http://localhost:8888/api/dm-quick \
  -H "Content-Type: application/json" \
  -d '{"script":"test"}' \
  -w "\n%{http_code}\n"
```

Expected: `403`

```bash
curl -X POST http://localhost:8888/api/dm-quick \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8888" \
  -d '{"script":"test"}' \
  -w "\n%{http_code}\n" -N
```

Expected: streamed 200-respons

- [ ] **Step 4: Commit**

```bash
git add netlify/edge-functions/dm-quick.ts
git commit -m "feat: dataminimering — origin-sjekk på dm-quick"
```

---

### Task 12: Sikkerhet — body-størrelse-grense

Avviser scripts større enn 50 KB.

**Files:**
- Modify: `netlify/edge-functions/dm-quick.ts`

- [ ] **Step 1: Legg til content-length-sjekk**

Rett etter origin-sjekken:

```typescript
const MAX_BODY_BYTES = 50_000;
const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);
if (contentLength > MAX_BODY_BYTES) {
  return new Response("Payload too large", { status: 413 });
}
```

Og rett etter `body = await request.json()`:

```typescript
if (typeof body.script === "string" && body.script.length > MAX_BODY_BYTES) {
  return new Response("Script too large", { status: 413 });
}
```

- [ ] **Step 2: Test med stort payload**

```bash
python3 -c "print('x' * 60000)" > /tmp/big.txt
SCRIPT=$(cat /tmp/big.txt)
curl -X POST http://localhost:8888/api/dm-quick \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8888" \
  -d "{\"script\":\"$SCRIPT\"}" \
  -w "\n%{http_code}\n"
```

Expected: `413`

- [ ] **Step 3: Commit**

```bash
git add netlify/edge-functions/dm-quick.ts
git commit -m "feat: dataminimering — body-størrelse-grense"
```

---

### Task 13: Sikkerhet — per-IP rate limit via Netlify Blobs

Maks 10 kall per IP per time.

**Files:**
- Create: `netlify/edge-functions/_lib/rate-limit.ts`
- Modify: `netlify/edge-functions/dm-quick.ts`

- [ ] **Step 1: Implementer rate-limit-modul**

Innhold `netlify/edge-functions/_lib/rate-limit.ts`:

```typescript
import { getStore } from "https://esm.sh/@netlify/blobs@7";

const WINDOW_MS = 60 * 60 * 1000;
const MAX_CALLS = 10;

interface RateRecord {
  calls: number[];
}

export async function checkRateLimit(
  endpoint: string,
  ip: string,
): Promise<{ allowed: boolean; retryAfterSeconds: number }> {
  if (!ip) return { allowed: true, retryAfterSeconds: 0 };
  const store = getStore("rate-limits");
  const key = `${endpoint}:${ip}`;
  const now = Date.now();
  const record = (await store.get(key, { type: "json" })) as RateRecord ?? { calls: [] };
  record.calls = record.calls.filter((t) => now - t < WINDOW_MS);
  if (record.calls.length >= MAX_CALLS) {
    const oldest = record.calls[0];
    const retryAfter = Math.ceil((WINDOW_MS - (now - oldest)) / 1000);
    return { allowed: false, retryAfterSeconds: retryAfter };
  }
  record.calls.push(now);
  await store.setJSON(key, record);
  return { allowed: true, retryAfterSeconds: 0 };
}
```

- [ ] **Step 2: Integrer i dm-quick**

I `dm-quick.ts`, etter origin-sjekken og body-størrelse-sjekken:

```typescript
import { checkRateLimit } from "./_lib/rate-limit.ts";

// ... etter body-størrelse-sjekken:
const ip = request.headers.get("x-nf-client-connection-ip")
  ?? request.headers.get("x-forwarded-for")?.split(",")[0]?.trim()
  ?? "";
const rate = await checkRateLimit("dm-quick", ip);
if (!rate.allowed) {
  return new Response("Rate limited", {
    status: 429,
    headers: { "Retry-After": String(rate.retryAfterSeconds) },
  });
}
```

- [ ] **Step 3: Test ved å skyte 11 kall i rappert tempo**

```bash
for i in $(seq 1 11); do
  curl -s -X POST http://localhost:8888/api/dm-quick \
    -H "Content-Type: application/json" \
    -H "Origin: http://localhost:8888" \
    -d '{"script":"// test"}' \
    -w "%{http_code}\n" -o /dev/null
done
```

Expected: ti `200`, så `429`.

NB: Netlify Blobs i lokal `netlify dev` bruker en lokal emulator; oppførsel skal være lik produksjon.

- [ ] **Step 4: Commit**

```bash
git add netlify/edge-functions/
git commit -m "feat: dataminimering — per-IP rate limit via Netlify Blobs"
```

---

### Task 14: Dokumentasjon i hjelp.html

**Files:**
- Modify: `hjelp.html`

- [ ] **Step 1: Finn rett plassering**

Run: `grep -n '<h2\|<h3' /Users/hom/Documents/GitHub/m2py/hjelp.html | head -20`

Identifiser en passende plassering for ny seksjon (f.eks. etter avsnittet om Avsløringskontroll).

- [ ] **Step 2: Legg til ny seksjon**

```html
<h2 id="hjelp-dataminimering">Dataminimering-vurdering</h2>
<p>
  m2py kan be en AI vurdere om scriptet ditt praktiserer dataminimering —
  prinsippet om å hente og bruke kun det minimum av data som trengs for
  problemstillingen. Funksjonen er rådgivende; endelig vurdering ligger hos
  forsker og dataansvarlig.
</p>
<p>
  Vurderingen forankres i:
</p>
<ul>
  <li>Personvernforordningen art. 5(1)(c) — dataminimering</li>
  <li>Helseregisterloven § 6 — graden av personidentifikasjon</li>
  <li>Personvernforordningen art. 89(1) — vitenskapelig forskning</li>
</ul>
<p>
  Klikk på hamburger-menyen → "Vurder dataminimering". Første gang du bruker
  funksjonen vises en bekreftelse på at scriptet sendes til Anthropic for
  vurdering. Faktiske mikrodata-verdier sendes aldri.
</p>
<h3>Personvern-kommentarer i scriptet</h3>
<p>
  Du kan legge til strukturerte begrunnelser direkte i scriptet:
</p>
<pre>// personvern blokk start
// formål: Studere sammenheng mellom utdanning og inntekt
// sentrale variabler: NUDB_UTDNIVAA, INNTEKT
// tidsperiode: 1970-1980 fordi kohorten skal være ferdig utdannet
// geografi: kommune nødvendig for å se regionale forskjeller
// sensitive grupper: nei
// alternativer vurdert: SSB-tabell A-04 var for grovkornet
// personvern blokk slutt</pre>
<p>
  Enkeltlinjer fungerer også:
</p>
<pre>// personvern: kuttet datoer til måned for å unngå unødig presisjon</pre>
<p>
  Disse blir lest av AI-en som tilleggskontekst. Du kan også bruke
  <code>#</code> i stedet for <code>//</code> i Python/R-script.
</p>
```

- [ ] **Step 3: Verifiser i browser**

Last hjelp.html — sjekk at ny seksjon vises og at internlenker fungerer.

- [ ] **Step 4: Commit**

```bash
git add hjelp.html
git commit -m "docs: dataminimering — seksjon i hjelp.html"
```

---

### Task 15: Manuell evaluering med sample scripts

Iterér prompten ved å kjøre faktiske scripts gjennom funksjonen og se på svarene.

**Files:** ingen kode — kun verifisering og evt. justering av `dm-quick.md`

- [ ] **Step 1: Forbered 5 test-scripts av ulik karakter**

Lag filer `tests/manual/dm-quick-sample-1.txt` til `-5.txt`:

1. **Sample 1 — Full analyse, godt minimert.**
   ```
   // personvern: formål: Inntektsforskjeller mellom kjønn for kohorten 1970
   import variables KJOENN, INNTEKT from BEFOLKNING
   keep if BEFOLKNING_FOEDEAAR == 1970
   collapse (mean) INNTEKT, by(KJOENN)
   ```

2. **Sample 2 — Full analyse, overdetaljert.**
   ```
   import all from BEFOLKNING
   import all from NUDB
   keep if BEFOLKNING_FOEDEDATO >= 19700101
   collapse (mean) INNTEKT, by(BEFOLKNING_KOMMUNENR)
   ```

3. **Sample 3 — Ren import.**
   ```
   import all from BEFOLKNING
   import all from NUDB
   import all from INNTEKT_REG
   ```

4. **Sample 4 — Mixed (Python + microdata).**
   ```
   import all from BEFOLKNING
   collapse (mean) INNTEKT, by(KJOENN)
   # Python-side analyse
   import pandas as pd
   df = pd.read_csv("result.csv")
   df.plot()
   ```

5. **Sample 5 — Med personvern-blokk.**
   ```
   // personvern blokk start
   // formål: Test
   // sentrale variabler: INNTEKT
   // personvern blokk slutt
   import variables INNTEKT from BEFOLKNING
   summarize INNTEKT
   ```

- [ ] **Step 2: Kjør hvert sample manuelt via UI eller curl**

For hvert sample, send det inn og noter:
- Klassifisering (A/B/C) — er den riktig?
- Samlet vurdering — er nivået (god/akseptabel/forbedringspotensial) rimelig?
- Observasjoner — er de konkrete, korrekte, ikke-overdrevne?
- Spørsmål til forsker — relevante eller redundante?

- [ ] **Step 3: Iterér prompten ved behov**

Justér `netlify/edge-functions/prompts/dm-quick.md` basert på observerte svakheter. Kjør samplene igjen.

Typiske justeringer:
- Hvis AI gir for mange forslag på trivielle scripts: forsterk "Ikke produser forslag bare for å produsere".
- Hvis AI er for forsiktig: be om sterkere språkbruk på "høy sikkerhet".
- Hvis klassifisering bommer: gi flere eksempler i prompten.

- [ ] **Step 4: Commit evalueringsfilene og evt. prompt-justeringer**

```bash
git add tests/ netlify/edge-functions/prompts/
git commit -m "test: dataminimering — manuelle evalueringsscripts og prompt-justeringer"
```

- [ ] **Step 5: Bump M2PY_VERSION og deploy til Netlify**

Endre `M2PY_VERSION` i `index.html` til neste suffix (f.eks. `'2026-05-22b'`).

```bash
git add index.html
git commit -m "chore: bump M2PY_VERSION etter Milepæl 1"
git push
```

Verifiser i Netlify-konsollen at deploy går grønt og at env-vars er satt i prod (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `M2PY_ALLOWED_ORIGINS`). Test funksjonen i produksjon med et enkelt script.

---

## Verifisering før Milepæl 2

Etter at alle 15 task er ferdige, sjekk:

- [ ] **Ende-til-ende-flyt fungerer i prod:** Klikk Vurder dataminimering → consent vises → aksepter → resultat strømmer inn.
- [ ] **Sikkerhetsmekanismer virker:**
  - Origin-sjekk blokkerer kall uten gyldig origin.
  - Body-grense returnerer 413 ved stort script.
  - Rate limit returnerer 429 ved 11. kall.
- [ ] **Parser fanger personvern-kommentarer:** Et script med blokk-form gir AI-en strukturert kontekst i prompten (sjekk Anthropic-logs eller legg til midlertidig logging).
- [ ] **Avbryt fungerer:** Midt i strøm — klikk Avbryt → fetch kanselleres, delvis svar bevares.
- [ ] **Kostnad i Anthropic-konsoll:** Sjekk at ett kall koster ~$0.01–0.02 og at det er en daglig budsjett-cap satt.
- [ ] **Dokumentasjon synlig:** Seksjon i `hjelp.html` viser korrekt.

Når alt er grønt — skriv ny plan for Milepæl 2 (Grundig-modus).
