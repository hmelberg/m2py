import {
  detectLanguage,
  parsePersonvernComments,
  parsePersonvernDirectives,
  type Language,
  type ScriptContext,
} from "./_lib/parse-script-context.ts";
import { streamAnthropic } from "./_lib/anthropic.ts";
import { checkRateLimit } from "./_lib/rate-limit.ts";

interface RequestBody {
  script: string;
  kontekst?: string;          // user-provided context text (free-form)
  språk?: "auto" | "microdata" | "python" | "r";
  detaljnivå?: "kort" | "lang";
  ønsker_revidert_script?: boolean;
}

// ====================================================================
// PROMPT TEMPLATES — kept in sync with prompts/ directory (source docs)
// ====================================================================

// Inlined from ./prompts/_shared-principles.md
// (Deno Deploy does not bundle .md files at runtime; source of truth is the .md file)
const SHARED_PRINCIPLES = `\
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
- Personvernforordningen art. 9: særlige kategorier (sensitive opplysninger)
  krever sterkere begrunnelse og høyere terskel.

Kalibreringsregel: personvernforordningen gir ikke ett endelig svar på hva
som er "nødvendig" — det avhenger av formålet. Formuler observasjoner som
muligheter for minimering, ikke som lovbrudd. Endelig vurdering ligger hos
forsker og dataansvarlig.

VURDERINGSDIMENSJONER

1. Ubrukte variabler — importert men aldri brukt
2. Variabel-granularitet — ICD-kode-detaljnivå, dato-oppløsning, geografi,
   inntekt, alder
3. Populasjons-avgrensing — \`keep if\`/\`drop if\`-filtere
4. Tidsperiode — er tidsvinduet snevert nok
5. Sjeldne kombinasjoner — filterkjeder som krymper til sårbar undergruppe
6. Koblingsbehov — er alle \`merge\`/\`import\` nødvendige
7. Aggregat vs individnivå — tidlig nok \`collapse\`?
8. Direkte identifikatorer i transformasjoner

SENSITIV-VURDERING (separat fra vanlig minimerings-vurdering)

Sjekk om scriptet bruker variabler som regnes som særlig sensitive:
- Etnisitet, opprinnelsesland, statsborgerskap
- Religion eller livssyn
- Seksuell legning eller praksis
- Helseopplysninger knyttet til særskilt sensitive temaer:
  abort (NCSP-koder for provoserte aborter, abortdiagnoser),
  kjønnssykdommer (HIV, syfilis, gonoré, klamydia, hepatitt),
  rusmisbruk og psykiatri (særlige diagnoser),
  vold, overgrep, selvmordsforsøk
- Lov- og straffeopplysninger

Dersom slike variabler brukes:
- Påpek dem eksplisitt i en egen seksjon "Særlig sensitive variabler"
- Vurder om de er essensielle for formålet eller kan unngås
- Krev høyere begrunnelsesterskel i vurderingen
- Henvis til personvernforordningen art. 9 når relevant

IKKE VURDERT FRA SCRIPTET

Følgende krever kontekst utenfor scriptet og skal ikke gjettes på:
- Analyseplan og dokumentert begrunnelse
- Tilgangsbegrensning og lagringstid (art. 5(1)(e))
- Mulighet for alternativer (syntetiske data, fjernanalyse)
- Senere gjenbruk (art. 5(1)(b))

NB: Disclosure-control i resultater (T1-T8) håndteres separat av m2py.
Fokuser på selve dataminimeringen i scriptet.`;

// Inlined from ./prompts/dm-vurder.md
// (Deno Deploy does not bundle .md files at runtime; source of truth is the .md file)
const DM_VURDER_TEMPLATE = `\
Du vurderer om et forskningsscript som henter mikrodata fra microdata.no
praktiserer dataminimering — prinsippet om å hente og bruke kun det minimum
av data som trengs for problemstillingen.

{{SHARED_PRINCIPLES}}

KOMMENTARER OG TIDLIGERE ERKLÆRT KONTEKST

Scriptet kan inneholde kommentarer som beskriver formål, antakelser eller
begrunnelser. Les og bruk alle kommentarer aktivt. Spesielt:

- Linjer i en \`// personvern blokk start ... slutt\`-blokk er strukturerte
  svar fra forskeren. Behandle som forskerens autoritative erklæring.
- Linjer som starter med \`// personvern: <fritekst>\` er forskerens egne
  begrunnelser. Vektes sterkt mot tilsvarende observasjon.

Disse er trukket ut i seksjonen TIDLIGERE ERKLÆRT KONTEKST nedenfor sammen
med formål-tekst forskeren eventuelt har spesifisert i UI-en. Hvis en
observasjon allerede er begrunnet der, ikke gjenta den som et problem —
vurder heller om begrunnelsen virker tilstrekkelig.

{{CONTEXT_SECTION}}

KATEGORISER SCRIPTET FØRST

- A) Full analyse — import + tydelig analyse
- B) Synlig hensikt — import + transformasjon, analyse mangler
- C) Ren import — kun import-linjer + minimale rename

SPRÅK

{{LANGUAGE}}

{{DETAIL_LEVEL}}

OUTPUT (norsk, markdown)

## Klassifisering
Kategori: <A|B|C>
Språk: <microdata|R|python|mixed>
Antatt analyseintensjon: <kort, eller "ikke synlig fra scriptet">

## Samlet vurdering
Setninger som plasserer scriptet på skala (god/akseptabel/forbedringspotensial),
forankret i relevante hjemler. Bruk typisk art. 5(1)(c) og hregl § 6 for
helsedata; art. 89(1) der aggregering/pseudonymisering er aktuelt; art. 5(1)(b)
der variabler virker hentet uten kobling til uttrykkelig formål. Bare hjemler
som styrker vurderingen.

## Observasjoner
- **<variabel, linjenr eller mønster>** — <problem>
  - Forslag: <konkret endring>
  - Sikkerhet: <høy | medium | lav>

Sortér etter sikkerhet. Hopp over kategorier uten observasjoner.

## Særlig sensitive variabler
(Kun hvis scriptet bruker variabler under GDPR art. 9 — se SENSITIV-VURDERING.)

- **<variabel>** — <kategori>
  - Vurdering: <essensielt for formålet, eller kan unngås>

{{REVISION_BLOCK}}

REGLER
- Vær konkret. Pek på variabelnavn eller linjenummer.
- Ikke produser forslag bare for å produsere.
- Markér sikkerhet ærlig.
- Du ser kun scriptet — si fra om vurderingen ville endret seg med mer kontekst.

SCRIPT

{{SCRIPT}}`;

// Inlined from ./prompts/_microdata-syntax.md
// (Deno Deploy does not bundle .md files at runtime; source of truth is the .md file)
const MICRODATA_SYNTAX = `\
<!-- KOPI: microdata-syntaks-reglene her er en kopi av kjernen i
microdata-api/server_code/prompts.py (GRAMMAR_CHEATSHEET, PRIVACY_RULES,
PSEUDONYM_RULES, TYPE_RULES m.fl.). Hold synkront. -->

MICRODATA.NO-SYNTAKS — REGLER FOR REVIDERT SCRIPT

Hvis du foreslår endringer i microdata-DSL-del av scriptet, må endringene
være gyldig prod-syntaks:

GENERELLE REGLER
- \`import all from <register>\` eller \`import variables (V1, V2) from <register>\`
- \`keep if <expr>\` / \`drop if <expr>\` — populasjons-filter
- \`generate <var> = <expr>\` — ny variabel
- \`replace <var> = <expr> if <cond>\` — endre verdi
- \`summarize <var> [if <cond>]\` — beskrivende statistikk
- \`tabulate <var> [<var2>]\` — frekvenstabell
- \`collapse (mean|sum|sd|count|median|min|max|p25|p75) <var>, by(<key>)\` — aggregering
- \`merge <var-list> into <dataset> [on <key>]\` — kobling

STRICT EMULATION (avvist i prod)
- \`collapse (first|last)\` er IKKE støttet
- Multi-key \`by(k1 k2)\` eller \`on(k1 k2)\` er IKKE støttet — bruk composite key
- For-løkke-ellipsis (\`for y in 1998, ..., 2009\`) er IKKE støttet — bruk range \`1998:2009\`
- Parens rundt iterator-listen er IKKE støttet
- \`for y in 1998 : 2009\` (range) eller \`for y in 1998, 1999, 2000\` (komma) er OK

PSEUDONYM-REGLER
- Variabler med _FNR-suffiks (eller markert is_pseudonym i metadata) er
  pseudonymer.
- Pseudonymer kan KUN brukes som nøkkel i \`collapse(by)\` eller \`merge(on)\`.
- Aldri i \`generate\`, \`replace\`, sammenligninger, \`string()\`, \`sysmiss()\`.

TYPE-REGLER
- Alfanumeriske (string) variabler kan IKKE brukes i numeriske operasjoner:
  \`mean\`, \`sum\`, \`min\`, \`max\`, \`sd\`, \`median\`, persentiler — verken i
  \`collapse\` eller \`summarize\`.
- Bruk \`tabulate\` eller \`count\` for strenger.

MISSING VALUES
- \`generate x = .\` (tildeling til missing) er OK.
- \`if x == .\` (sammenligning) er IKKE støttet — bruk \`if sysmiss(x)\`.

REGISTERVARIABLER
- Bruk eksisterende variabelnavn fra registrene — ikke oppfinn nye.
- For grovere geografi: BEFOLKNING_KOMMUNENR (finest) → BEFOLKNING_FYLKE → BEFOLKNING_LANDSDEL.
- For fødselsdato: BEFOLKNING_FOEDEAAR (år) → BEFOLKNING_FOEDSELS_AAR_MND (år+mnd) → BEFOLKNING_FOEDEDATO (full).`;

const DETAIL_LEVEL_KORT = `\
RAPPORT-FORMAT: KORT

- Maks 3–5 observasjoner, sorter etter sikkerhet (høy først).
- Samlet vurdering: 1–2 setninger.
- Ingen "Spørsmål til forsker"-seksjon. Hvis kontekst mangler, nevn det i
  selve vurderingen.
- Sensitive variabler: alltid med, selv om det betyr én ekstra observasjon.`;

const DETAIL_LEVEL_LANG = `\
RAPPORT-FORMAT: LANG

- Gå gjennom alle relevante vurderingsdimensjoner.
- Samlet vurdering: 2–4 setninger med lovreferanser.
- Inkluder "Spørsmål til forsker"-seksjon hvis kontekst mangler (maks 3 spørsmål).
- Sensitive variabler: alltid med en egen seksjon hvis funnet.`;

const REVISION_INSTRUCTION_GENERIC = `\

## Revidert script

Avslutt svaret med en "## Revidert script"-seksjon. Foreslå konservative
endringer der du er rimelig sikker:

- Bare endringer med høy eller medium sikkerhet
- Bevar analytisk intensjon — endre granularitet, ikke struktur
- Sett en "// personvern: <forklaring>"-kommentar (eller "# personvern: ..."
  for Python/R) rett over hver endret linje
- Hvis scriptet ser godt minimert ut, skriv kort: "Ingen endringer foreslås."

Returner reviderte kode i en \`\`\`<språk>-blokk.`;

const REVISION_INSTRUCTION_MICRODATA = MICRODATA_SYNTAX + "\n\n" + REVISION_INSTRUCTION_GENERIC;

// ====================================================================
// HELPER FUNCTIONS
// ====================================================================

function renderContextSection(ctx: ScriptContext, userText: string): string {
  const parts: string[] = ["TIDLIGERE ERKLÆRT KONTEKST"];
  if (userText && userText.trim()) {
    parts.push("", "Bruker-spesifisert formål og bakgrunn:", userText.trim());
  }
  if (Object.keys(ctx.structured).length > 0) {
    parts.push("", "Strukturert (fra personvern-blokk):");
    for (const [field, value] of Object.entries(ctx.structured)) {
      parts.push(`- ${field}: ${value}`);
    }
  }
  if (ctx.freetext.length > 0) {
    parts.push("", "Fritekst (fra personvern:-linjer):");
    for (const f of ctx.freetext) {
      parts.push(`- (linje ${f.line}) ${f.text}`);
    }
  }
  if (parts.length === 1) {
    return "(Ingen kontekst spesifisert. Vurder ut fra scriptet alene.)";
  }
  return parts.join("\n");
}

function languageInstruction(requested: string, detected: Language): string {
  if (requested === "auto") {
    return `Detektert språk: ${detected}. Vurder kode i dette språket.`;
  }
  if (requested === "microdata") return "Forskeren har eksplisitt angitt: microdata.no-DSL.";
  if (requested === "python") return "Forskeren har eksplisitt angitt: Python.";
  if (requested === "r") return "Forskeren har eksplisitt angitt: R.";
  return `Detektert språk: ${detected}.`;
}

// ====================================================================
// EDGE FUNCTION HANDLER
// ====================================================================

export default async (request: Request): Promise<Response> => {
  const expectedToken = Deno.env.get("M2PY_ACCESS_TOKEN");
  if (expectedToken) {
    const authHeader = request.headers.get("authorization") ?? "";
    const presentedToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
    if (presentedToken !== expectedToken) {
      return new Response("Unauthorized", { status: 401 });
    }
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

  // Detect language and parse script directives
  const detected = detectLanguage(body.script);
  const directives = parsePersonvernDirectives(body.script);

  // Directive takes priority when set (regardless of value); body falls back to false
  const wantRevisedScript = directives.revider_script !== undefined
    ? directives.revider_script
    : (body.ønsker_revidert_script ?? false);
  const requestedLanguage = body.språk ?? "auto";
  const effectiveLanguage = requestedLanguage === "auto" ? detected : requestedLanguage;
  const detailLevel = body.detaljnivå === "lang" ? DETAIL_LEVEL_LANG : DETAIL_LEVEL_KORT;

  // Inject microdata syntax cheatsheet only when needed
  const includeMicrodataSyntax =
    wantRevisedScript && (effectiveLanguage === "microdata" || effectiveLanguage === "mixed");
  const revisionBlock = wantRevisedScript
    ? (includeMicrodataSyntax ? REVISION_INSTRUCTION_MICRODATA : REVISION_INSTRUCTION_GENERIC)
    : "";

  const ctx = parsePersonvernComments(body.script);
  const contextSection = renderContextSection(ctx, body.kontekst ?? "");

  const prompt = DM_VURDER_TEMPLATE
    .replaceAll("{{SHARED_PRINCIPLES}}", () => SHARED_PRINCIPLES)
    .replaceAll("{{CONTEXT_SECTION}}", () => contextSection)
    .replaceAll("{{LANGUAGE}}", () => languageInstruction(requestedLanguage, detected))
    .replaceAll("{{DETAIL_LEVEL}}", () => detailLevel)
    .replaceAll("{{REVISION_BLOCK}}", () => revisionBlock)
    .replaceAll("{{SCRIPT}}", () => body.script);

  try {
    const maxTokens = wantRevisedScript ? 3500 : 2000;
    const stream = await streamAnthropic({ apiKey, model, prompt, maxTokens });
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
