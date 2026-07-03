import { messageAnthropic, streamAnthropic } from "./_lib/anthropic.ts";
import { extractByokKey, gate, upstreamErrorResponse } from "./_lib/auth.ts";
import { buildCachedPrefix, coerceMode, type GenMode } from "./kode-svar.ts";
import {
  type CatalogMeta,
  type CodelistMap,
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
  mode?: GenMode;          // editor mode: microdata (default) | python | r
}

const PICKER_INSTRUCTIONS = `\
Du er en variabel-velger for microdata.no. Du får en liste over alle tilgjengelige
variabler og et brukerspørsmål. Velg de inntil 25 variablene som er mest relevante
for å besvare spørsmålet.
- Inkluder nøkkel-/koblingsvariabler som trengs (person-ref, familie-pekere).
- Ta med IKKE BARE de bokstavlige treffene, men også MEKANISME-/PROXY-kandidater:
  variabler som fanger fenomenet INDIREKTE via avtrykket det setter i registrene
  (relevante datoer, hendelser, beslektede stønader/ytelser, familiepekere). F.eks.
  for «arv» også dødsdatoer + foreldre-pekere; for «syk forelder» også
  sykdomsrelaterte ytelser, ikke bare diagnosekoder.
- Inkluder også åpenbare konfunderende/kontrollvariabler som er relevante for
  spørsmålet (men ikke en fast liste — kun de som faktisk hører hjemme).
- Ved tvil, ta heller med en variabel for mye enn for lite (over-plukk).
Svar KUN med et JSON-array av eksakte variabelnavn fra listen, uten forklaring.
Eksempel: ["BEFOLKNING_KJOENN","INNTEKT_WLONN"]`;

// v2-only output-format addendum (v1's OUTPUT_INSTRUCTION is deliberately
// untouched — this is the pilot surface for the richer "considerations" section).
const SVARFORMAT_TILLEGG = `\
**Svarformat-tillegg (v2):** Hvis dette er et analyse-/effektspørsmål (IKKE et
enkelt oppslag eller rent faktaspørsmål), avslutt svaret med en kort seksjon
«Vurderinger og forslag» med 2–4 konkrete punkter som IKKE gjentar det scriptet
allerede gjør. Velg blant: en kontrollvariabel eller undergruppe verdt å legge
til (og hvorfor); et alternativt/indirekte (proxy) variabelvalg med den sentrale
antakelsen oppgitt; en mulig identifikasjonsstrategi (reform/regelendring som kan
utnyttes med diff-in-diff eller regresjonsdiskontinuitet — oppgi antatt år/terskel
og MERK at det må verifiseres); eller en presisering hvis du har tolket/snevret
inn spørsmålet (si eksplisitt hva du måler og hva som faller utenfor — bytt aldri
spørsmål i det stille). Hold seksjonen kort og reell, og hopp over den helt for
enkle spørsmål. Ikke gjett reformer, koder eller etiketter du er usikker på —
foreslå dem som noe-å-sjekke, ikke som fakta.`;

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

// Big classifications (STYRK, NACE, …) aren't enumerated in variable_metadata,
// but some have a /codelists/<NAME>.json file ({ ..., labels: {code: text} }).
// Fetch on demand for picked variables that lack a usable inline codelist.
// Module-cached (incl. negative results) so repeats are free. Best-effort:
// only the handful of exact-name matches resolve; misses are silent.
const _codelistCache: Record<string, Record<string, unknown> | null> = {};
async function loadCodelist(origin: string, name: string): Promise<Record<string, unknown> | null> {
  if (name in _codelistCache) return _codelistCache[name];
  try {
    const res = await fetch(new URL(`/codelists/${name}.json`, origin).toString());
    if (!res.ok) { _codelistCache[name] = null; return null; }
    const json = await res.json();
    const labels = json && typeof json === "object" ? json.labels : null;
    _codelistCache[name] = labels && typeof labels === "object" ? labels : null;
  } catch {
    _codelistCache[name] = null;
  }
  return _codelistCache[name];
}

function inlineLabelCount(v: Record<string, unknown> | undefined): number {
  const l = v?.labels;
  return l && typeof l === "object" ? Object.keys(l as Record<string, unknown>).length : 0;
}

export default async (request: Request): Promise<Response> => {
  const gateResp = await gate(request, { endpoint: "kode-svar-v2", maxBodyBytes: 50_000, allowByok: true });
  if (gateResp) return gateResp;

  let body: RequestBody;
  try {
    body = await request.json();
  } catch (_) {
    return new Response("Invalid JSON", { status: 400 });
  }
  const question = (body.question ?? "").trim();
  if (!question) return new Response("Missing question", { status: 400 });

  const byokKey = extractByokKey(request);
  const apiKey = byokKey ?? Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  const pickerModel = Deno.env.get("PICKER_MODEL") ?? "claude-haiku-4-5-20251001";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }

  const origin = new URL(request.url).origin;
  const mode: GenMode = coerceMode(body.mode);
  const system = await buildCachedPrefix(origin, mode);
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
    const names = groundNames(parsePickerResponse(picked.text), meta, 25);
    // On-demand codelists for picked vars whose inline labels are absent/short.
    const codelists: CodelistMap = {};
    const vars = meta.variables ?? {};
    await Promise.all(names.map(async (n) => {
      if (inlineLabelCount(vars[n]) > 12) return;   // already shown inline
      const cl = await loadCodelist(origin, n);
      if (cl && Object.keys(cl).length > 0) codelists[n] = cl;
    }));
    focusedBlock = renderFocusedBlock(names, meta, codelists);
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
    scriptContext ? `**Gjeldende skript i editor (kontekst):**\n\`\`\`${mode === "microdata" ? "microdata" : mode}\n${scriptContext}\n\`\`\`\n` : ``,
    priorScript ? `**Forrige skript som feilet — fiks feilene under, ikke gjenta dem:**\n\`\`\`microdata\n${priorScript}\n\`\`\`\n` : ``,
    errors ? `**Valideringsfeil å rette:**\n${errors}\n` : ``,
    SVARFORMAT_TILLEGG,
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
    return upstreamErrorResponse(e, byokKey);
  }
};
