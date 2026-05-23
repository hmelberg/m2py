import {
  detectLanguage,
  parsePersonvernComments,
  type ScriptContext,
} from "./_lib/parse-script-context.ts";
import { streamAnthropic } from "./_lib/anthropic.ts";
import { checkRateLimit } from "./_lib/rate-limit.ts";

// Prompt text inlined from ./prompts/_shared-principles.md
// (Deno Deploy does not bundle .md files at runtime; source of truth is the .md file)
const sharedPrinciples = `\
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
3. Populasjons-avgrensing — \`keep if\`/\`drop if\`-filtere.
4. Tidsperiode — er tidsvinduet snevert nok.
5. Sjeldne kombinasjoner — filterkjeder som krymper til sårbar undergruppe.
6. Koblingsbehov — er alle \`merge\`/\`import\` nødvendige.
7. Aggregat vs individnivå — tidlig nok \`collapse\`?
8. Direkte identifikatorer i transformasjoner.

IKKE VURDERT FRA SCRIPTET

Følgende krever kontekst utenfor scriptet og skal ikke gjettes på:
- Analyseplan og dokumentert begrunnelse.
- Tilgangsbegrensning og lagringstid.
- Mulighet for alternativer (syntetiske data, fjernanalyse).
- Senere gjenbruk.

NB: Disclosure-control i resultater (T1-T8) håndteres separat av m2py.
Fokuser på selve dataminimeringen i scriptet.`;

// Prompt text inlined from ./prompts/dm-quick.md
// (Deno Deploy does not bundle .md files at runtime; source of truth is the .md file)
const dmQuickTemplate = `\
Du vurderer om et forskningsscript som henter mikrodata fra microdata.no
praktiserer dataminimering — prinsippet om å hente og bruke kun det minimum
av data som trengs for problemstillingen.

{{SHARED_PRINCIPLES}}

KOMMENTARER OG TIDLIGERE ERKLÆRT KONTEKST

Scriptet kan inneholde kommentarer som beskriver formål, antakelser eller
begrunnelser. Les og bruk alle kommentarer aktivt.

Spesielt:
- Linjer i en \`// personvern blokk start ... slutt\`-blokk, og enkeltlinjer
  som starter med \`// personvern: <feltnavn>:\` der feltnavn er ett av
  formål / sentrale variabler / tidsperiode / geografi / sensitive grupper /
  alternativer vurdert, er strukturerte svar fra forskeren. Behandle som
  forskerens autoritative erklæring.
- Linjer som starter med \`// personvern: <fritekst>\` (eller fritekst inne i
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

{{SCRIPT}}`;

interface RequestBody {
  script: string;
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

export default async (request: Request): Promise<Response> => {
  const allowedOrigins = (Deno.env.get("M2PY_ALLOWED_ORIGINS") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const origin = request.headers.get("origin");
  if (allowedOrigins.length > 0 && (!origin || !allowedOrigins.includes(origin))) {
    return new Response("Forbidden", { status: 403 });
  }

  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const MAX_BODY_BYTES = 50_000;
  const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);
  if (contentLength > MAX_BODY_BYTES) {
    return new Response("Payload too large", { status: 413 });
  }

  const ip = request.headers.get("x-nf-client-connection-ip")
    ?? request.headers.get("x-forwarded-for")?.split(",")[0]?.trim()
    ?? "";
  const rate = await checkRateLimit("dm-vurder", ip);
  if (!rate.allowed) {
    return new Response("Rate limited", {
      status: 429,
      headers: { "Retry-After": String(rate.retryAfterSeconds) },
    });
  }

  let body: RequestBody;
  try {
    body = await request.json();
    if (typeof body.script === "string" && body.script.length > MAX_BODY_BYTES) {
      return new Response("Script too large", { status: 413 });
    }
  } catch (_) {
    return new Response("Invalid JSON", { status: 400 });
  }
  if (!body.script || typeof body.script !== "string") {
    return new Response("Missing script", { status: 400 });
  }

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }

  const ctx = parsePersonvernComments(body.script);
  const language = detectLanguage(body.script);
  const contextSection = renderContextSection(ctx);

  const prompt = dmQuickTemplate
    .replaceAll("{{SHARED_PRINCIPLES}}", () => sharedPrinciples)
    .replaceAll("{{CONTEXT_SECTION}}", () => contextSection)
    .replaceAll("{{LANGUAGE}}", () => language)
    .replaceAll("{{SCRIPT}}", () => body.script);

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
