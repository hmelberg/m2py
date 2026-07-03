# Design: Egen Anthropic-nøkkel (BYOK) som alternativ til innlogging/delt kode

**Dato:** 2026-07-03
**Status:** Godkjent i brainstorming, klar for implementasjonsplan

## Mål

Brukere uten innlogging eller delt tilgangskode skal kunne bruke alle
AI-funksjonene i appen (rask AI / kode-svar, tolk resultater, personvern-
vurdering / dm-vurder, og web-AI-søk) ved å legge inn sin egen Anthropic
API-nøkkel. Nøkkelen brukes i stedet for serverens `ANTHROPIC_API_KEY`, slik
at kostnadene går på brukerens egen konto.

Web-AI-søk (`data-svar`) har til nå vært admin-only fordi agentisk søk er
dyrt på server-nøkkelen. Med egen nøkkel forsvinner kostnadsargumentet, så
BYOK-brukere får også web-modus.

## Valgt arkitektur

BYOK **via edge-funksjonene** (ikke direkte nettleser→Anthropic): frontend
sender brukerens nøkkel i headeren `X-Anthropic-Key`; edge-funksjonene godtar
den som alternativ til Bearer-token og bruker den i stedet for env-nøkkelen.
Dette gjenbruker all eksisterende server-side prompt- og responslogikk.
Nøkkelen passerer serveren over TLS, men lagres og logges aldri.

Alternativet (direkte kall til api.anthropic.com fra nettleseren) ble
forkastet: promptene og logikken (særlig dm-vurder) ligger server-side og
måtte vært duplisert og offentliggjort.

## Endringer

### 1. Frontend

**`index.html` — aiCfg-modalen (utlogget-tilstand, `#aiCfgLoggedOut`):**

- Nytt passordfelt «Egen Anthropic API-nøkkel» (`id="aiCfgAnthropicKey"`,
  `type="password"`, placeholder `sk-ant-…`).
- Hjelpetekst med lenke til <https://console.anthropic.com/settings/keys> og
  en kort forklaring: nøkkelen lagres kun i nettleseren, kall går via appens
  server men nøkkelen lagres/logges ikke der, og kostnader belastes brukerens
  egen Anthropic-konto.
- Lagres/fjernes via eksisterende «Lagre innstillinger»-knapp (`aiCfgSave`).

**`js/ai-chat.js`:**

- Ny localStorage-nøkkel `md_anthropic_key`; `state.anthropicKey` (getter,
  samme mønster som `state.apiKey`).
- Autentiseringssjekkene (`isAuthed` m.fl.) godtar `anthropicKey` på lik
  linje med innloggingstoken/service-token, slik at AI-knappene aktiveres.
- Header-bygging for alle kallsteder (`/api/kode-svar`, `/api/kode-svar-v2`,
  `/api/tolk-resultat`, `/api/data-svar`): innloggingstoken har forrang;
  hvis ikke innlogget og `anthropicKey` er satt, sendes
  `X-Anthropic-Key: <nøkkel>` (ingen Authorization-header).
- `webModeAvailable()` (js/ai-chat.js:37-39) endres fra
  `isAdmin && (python|r|duckdb)` til
  `(isAdmin || anthropicKey satt) && (python|r|duckdb)`. Synligheten
  re-evalueres når nøkkelen lagres/fjernes i innstillingene (samme kall som
  i dag gjøres ved admin-statussynk, ai-chat.js:1437).
- Feilmeldingen ved 403 fra data-svar («Web-modus er kun tilgjengelig for
  admin.») utvides til å nevne egen nøkkel som alternativ.

**`index.html` — dm-vurder-kallet (index.html:1147):**

- Samme header-logikk: `X-Anthropic-Key` når ikke innlogget og nøkkel satt.

**`js/i18n/en.js`:**

- Engelske oversettelser for alle nye tekster (feltetikett, hjelpetekst,
  feilmeldinger), etter eksisterende `data-i18n`-mønster.

### 2. Edge-funksjonene

**`netlify/edge-functions/_lib/auth.ts`:**

- Ny hjelpefunksjon `extractByokKey(request)`: leser `X-Anthropic-Key`,
  godtar kun format `^sk-ant-[A-Za-z0-9_-]+$` og lengde ≤ 250 tegn; ellers
  behandles den som fraværende.
- `runGate` og `runAdminGate`: hvis gyldig BYOK-header finnes, hoppes
  token-presence (steg 1) og auth/admin-validering (steg 5) over.
  Metode-, content-length- og **rate-limit-sjekkene beholdes** (steg 2–4),
  slik at proxyen ikke kan misbrukes anonymt.
- Nøkkelen logges aldri (ingen `console.*` med header-innhold).

**Alle fem endepunktene (`kode-svar.ts`, `kode-svar-v2.ts`,
`tolk-resultat.ts`, `data-svar.ts`, `dm-vurder.ts`):**

- `const apiKey = extractByokKey(request) ?? Deno.env.get("ANTHROPIC_API_KEY")`.
- I `data-svar` brukes BYOK-nøkkelen for **alle** Anthropic-kall i den
  agentiske løkka (generering + web-søk-verktøyet), slik at også
  per-søk-gebyret belastes brukeren.
- Feilhåndtering: 401 fra Anthropic upstream med BYOK-nøkkel returneres som
  401 med tekst «Ugyldig Anthropic-nøkkel» (frontend viser denne direkte).
  Uten BYOK beholdes dagens oppførsel (502).

### 3. Testing

- TDD: nye Deno-tester i `_lib/auth.test.ts` skrives først:
  - `runGate` slipper gjennom med gyldig BYOK-header uten Bearer-token.
  - `runAdminGate` slipper gjennom med gyldig BYOK-header uten admin.
  - Ugyldig format (feil prefiks, for lang, tom) → 401 som før.
  - Rate-limit håndheves fortsatt på BYOK-veien.
  - `extractByokKey`-enhetstester.
- Kjøres med eksisterende Deno-testoppsett i `netlify/edge-functions/_lib/`.
- Frontend verifiseres manuelt: `netlify dev` fungerer ikke lokalt
  (Deno/Node 26-problemet); UI-delen sjekkes ved å åpne `index.html` direkte
  (felt, lagring, knappesynlighet), og full ende-til-ende-test gjøres mot
  deploy preview.

## Sikkerhetsvurdering

- Nøkkelen lagres i `localStorage` (samme risikonivå som eksisterende
  `mdapi_token` og `md_ai_api_key`); feltet er `type="password"`.
- Server-side: nøkkelen holdes kun i minnet per request, logges aldri,
  skrives aldri til Blobs/cache. `_authCache` brukes ikke for BYOK.
- Rate-limiting per IP gjelder uendret, så endepunktene kan ikke brukes som
  åpen proxy i stor skala.
- Prompt-caching (`cacheTtl`) er per API-nøkkel hos Anthropic og lekker
  ikke mellom brukere.

## Bevisst utelatt (YAGNI)

- Ingen direkte nettleser→Anthropic-modus.
- Ingen kryptering av nøkkelen i localStorage.
- Ingen endringer i admin-/delt kode-/magic-link-flyten.
- Ingen server-side validering av nøkkelen utover formatsjekk (Anthropic
  gir 401 ved ugyldig nøkkel).
- Ingen modellvalg for BYOK-brukere; samme modeller som i dag
  (`ANTHROPIC_MODEL`-env styrer fortsatt).
