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
