import { detectLanguage } from "./_lib/parse-script-context.ts";
import { streamAnthropic } from "./_lib/anthropic.ts";
import { checkRateLimit } from "./_lib/rate-limit.ts";

interface RequestBody {
  script?: string;
  output: string;
  språk?: "auto" | "microdata" | "python" | "r";
}

// Inlined from ./prompts/tolk-resultat.md (Deno Deploy bundler tar ikke .md i runtime;
// source of truth er .md-filen — hold synkront).
const TOLK_TEMPLATE = `\
Du er en statistikk-kyndig assistent som tolker resultatene fra en analyse på
microdata.no (eller tilsvarende i Python/R). Forklar resultatene for en forsker:
hva analysen gjorde, hva tallene og tabellene faktisk viser, hovedmønstre, og
relevante forbehold.

VIKTIG KONTEKST
- Dataene er ØVINGSDATA (syntetiske), ikke ekte registerdata. Ikke presenter
  mønstre som ekte funn om virkeligheten — beskriv hva resultatet viser i datasettet.
- Tall kan være avsløringskontrollert (avrundet, små celler skjult, vinsorisert).
  Tolk med forbehold der det er relevant.
- Output inneholder ofte både kommandoene (echo) og resultatene. Bruk kommandoene
  til å forstå hva som ble gjort.

microdata.no-output (når relevant):
- summarize → gjennomsnitt, std.avvik, min/maks, antall.
- tabulate → frekvens-/krysstabell. correlate → korrelasjoner.
- regress / logit / probit / poisson → koeffisienter, standardfeil, p-verdier.
- collapse / aggregate → aggregerte verdier per gruppe.

SPRÅK
{{LANGUAGE}}

OUTPUT (norsk, markdown, konsist)

## Hva analysen gjorde
<1–3 setninger basert på kommandoene>

## Resultater
<de viktigste tallene/mønstrene, punktvis; pek på konkrete verdier>

## Forbehold
<usikkerhet, avsløringskontroll, syntetiske data — kun det som er relevant>

REGLER
- Vær konkret og pek på faktiske tall.
- Ikke overdriv; si fra om noe er uklart eller mangler.
- Ikke gjenta hele outputen — tolk den.

SCRIPT (kommandoer)

{{SCRIPT}}

OUTPUT (resultater)

{{OUTPUT}}`;

function languageInstruction(requested: string, detected: string): string {
  if (requested === "microdata") return "Output er fra microdata.no-DSL.";
  if (requested === "python") return "Output er fra Python.";
  if (requested === "r") return "Output er fra R.";
  return `Detektert språk: ${detected}.`;
}

export default async (request: Request): Promise<Response> => {
  const ANVIL_VALIDATE_URL = Deno.env.get("M2PY_ANVIL_VALIDATE_URL")
    ?? "https://mdataapi.anvil.app/_/api/auth/me";
  const sharedToken = Deno.env.get("M2PY_ACCESS_TOKEN");

  const authHeader = request.headers.get("authorization") ?? "";
  const presentedToken = authHeader.startsWith("Bearer ")
    ? authHeader.slice(7).trim()
    : "";

  if (!presentedToken) {
    return new Response("Unauthorized: missing token", { status: 401 });
  }

  let authenticated = false;
  if (sharedToken && presentedToken === sharedToken) {
    authenticated = true;
  }
  if (!authenticated) {
    try {
      const anvilResp = await fetch(ANVIL_VALIDATE_URL, {
        method: "GET",
        headers: { "Authorization": `Bearer ${presentedToken}` },
      });
      if (anvilResp.ok) {
        const data = await anvilResp.json();
        if (data && (data.user || data.principal_kind === "service_token" || data.principal_kind === "anonymous")) {
          authenticated = true;
        }
      }
    } catch (_e) {
      // network error to Anvil — treat as unauthorized
    }
  }
  if (!authenticated) {
    return new Response("Unauthorized", { status: 401 });
  }

  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const MAX_BODY_BYTES = 120_000;
  const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);
  if (contentLength > MAX_BODY_BYTES) {
    return new Response("Payload too large", { status: 413 });
  }

  const ip = request.headers.get("x-nf-client-connection-ip")
    ?? request.headers.get("x-forwarded-for")?.split(",")[0]?.trim()
    ?? "";
  const rate = await checkRateLimit("tolk-resultat", ip);
  if (!rate.allowed) {
    return new Response("Rate limited", {
      status: 429,
      headers: { "Retry-After": String(rate.retryAfterSeconds) },
    });
  }

  let body: RequestBody;
  try {
    body = await request.json();
  } catch (_) {
    return new Response("Invalid JSON", { status: 400 });
  }
  if (!body.output || typeof body.output !== "string" || !body.output.trim()) {
    return new Response("Missing output", { status: 400 });
  }

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }

  // Truncate defensively so a huge output can't blow the prompt.
  const MAX_CHARS = 30_000;
  const script = (body.script ?? "").slice(0, MAX_CHARS);
  const output = body.output.slice(0, MAX_CHARS);
  const requested = body.språk ?? "auto";
  const detected = detectLanguage(output || script);

  const prompt = TOLK_TEMPLATE
    .replaceAll("{{LANGUAGE}}", () => languageInstruction(requested, detected))
    .replaceAll("{{SCRIPT}}", () => script || "(ingen kommandoer sendt)")
    .replaceAll("{{OUTPUT}}", () => output);

  try {
    const stream = await streamAnthropic({ apiKey, model, prompt, maxTokens: 1800 });
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
