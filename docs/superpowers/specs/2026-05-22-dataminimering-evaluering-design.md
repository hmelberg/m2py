# Dataminimering: AI-evaluering av script

**Status:** Spec — revidert 2026-05-23 (forenklet design)
**Dato:** 2026-05-22 (opprettet), 2026-05-23 (revidert)
**Eier:** Hans Melberg

## Kontekst og motivasjon

m2py er en hobbysimulator av microdata.no. Forskere som bruker microdata.no skal
i prinsippet praktisere dataminimering — hente og bruke kun det minimum av data
som trengs for forskningsformålet. Dette følger av personvernforordningen
art. 5(1)(c), helseregisterloven § 6 og helseforskningsloven § 32. I praksis er
det vanskelig å vurdere selv om eget script gjør dette godt nok.

Denne speccen beskriver en AI-basert vurderingsfunksjon i m2py som hjelper
forskeren reflektere over om scriptet henter og bruker minimum nødvendig data,
og foreslår konkrete forbedringer der det er rom for det.

**Designnotat (2026-05-23):** Tidligere spec hadde to separate moduser (kjapp og
grundig) pluss en egen revisjons-funksjon. Etter Milepæl 1 ble dette evaluert og
forenklet til *én enhetlig flyt* med valgfri kontekst-spesifisering og valgfri
revidert script. Se "Designhistorikk" nederst for opprinnelig design.

## Mål og avgrensning

**Mål:**

- Tilby forskeren én sammenhengende vurdering av om et script praktiserer
  dataminimering, med valgfri tilleggskontekst og valgfri revidert script som
  output i samme svar.
- Eksplisitt flagging av særlig sensitive variabler (etnisitet, abort,
  kjønnssykdommer, psykiatri, vold/overgrep, lov-/straffeopplysninger).
- Forankre vurderingen i konkret norsk og europeisk lovverk slik at forslagene
  har juridisk relevans.
- Persistere forskerens kontekst i scriptet selv (valgfritt), slik at scriptet
  er én sannhetskilde som lever sammen med koden.

**Ikke-mål:**

- Erstatte forskerens, dataansvarliges eller REKs vurdering. Verktøyet skal
  støtte refleksjon, ikke konkludere med "lovlig" eller "ulovlig".
- Vurdere ting som ikke er synlig fra scriptet: REK-vedtak, tilgangs­
  begrensninger, lagringstid, samtykker, analyseplan.
- Duplisere disclosure-control-sjekkene som allerede ligger i m2py
  (T1-T8, winsorisering, små celler etc.).

## Enhetlig flyt: én knapp, én forespørsel

Én hamburger-meny-knapp "Vurder dataminimering" åpner én modal med valgfrie
innstillinger. Brukeren konfigurerer ett kall, AI returnerer alt i én
streamed respons.

### Hovedmodal

```
┌─────────────────────────────────────────────────┐
│ Vurder dataminimering                           │
│                                                 │
│ Språk: [Automatisk ▾]                           │
│        (auto / microdata / R / Python)          │
│                                                 │
│ Rapport: ◉ Kort  ○ Lang                         │
│                                                 │
│ ☐ Generer også revidert script                  │
│                                                 │
│ Formål og bakgrunn:                             │
│   [Spesifiser formål / kontekst]                │
│   (Hvis ikke spesifisert, vurderer AI ut fra    │
│    scriptet alene.)                             │
│                                                 │
│              [Avbryt]  [Vurder]                 │
└─────────────────────────────────────────────────┘
```

**Innstillinger:**

| Felt | Verdier | Default | Effekt |
| --- | --- | --- | --- |
| Språk | auto / microdata / R / Python | auto | Påvirker prompt-variant (microdata-syntaks inkluderes ved microdata/auto+microdata) og output-klassifisering |
| Rapport | Kort / Lang | Kort | Påvirker prompt-instruks for ordrikedom; kort = 3-5 observasjoner uten "Spørsmål til forsker", lang = alt |
| Revidert script | Av / På | Av | Når på: AI legger til en `## Revidert script`-seksjon på slutten av svaret, og prompten utvides med konservative revisjons-instrukser |

### Sekundær modal: spesifiser formål

Klikk "Spesifiser formål / kontekst" åpner:

```
┌─────────────────────────────────────────────────┐
│ Formål og kontekst                              │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ (Pre-fylt fra eksisterende personvern-  │     │
│ │ blokk i scriptet — strippet `//` —      │     │
│ │ eller tom med placeholder-eksempel.)    │     │
│ │                                         │     │
│ │ Eksempler på hva som er nyttig:         │     │
│ │ - Formålet med analysen                 │     │
│ │ - Hvorfor denne tidsperioden            │     │
│ │ - Hvorfor dette geografiske nivået      │     │
│ │ - Sensitive grupper analysert           │     │
│ └─────────────────────────────────────────┘     │
│                                                 │
│ ☑ Lagre dette som // personvern-blokk           │
│   i scriptet                                    │
│                                                 │
│              [Avbryt]  [Bruk]                   │
└─────────────────────────────────────────────────┘
```

Pre-utfylling: hvis scriptet har en `// personvern blokk start ... slutt`-blokk,
løftes innholdet inn (stripped for kommentartegn). Brukeren kan redigere fritt.

"Lagre som personvern-blokk" er default på — neste vurdering plukker da opp
konteksten automatisk.

### "Sentrale variabler" bevisst utelatt

Tidligere design hadde et felt for "sentrale variabler". Det er nå droppet
fordi:

- Det fremgår direkte av scriptet hvilke variabler som brukes
- AI kan selv identifisere eksponering / utfall / kovariater fra
  bruks-mønstre (`collapse by`, `summarize`, regresjons-argumenter etc.)
- Det reduserer skjema-tyngden og friksjonen i flyten

### Sensitive variabler flagges av AI

AI instrueres å eksplisitt sjekke for og flagge særlig sensitive variabler:

- Etnisitet, opprinnelsesland, statsborgerskap
- Religion
- Seksuell legning eller praksis
- Helseopplysninger knyttet til særlig sensitive temaer:
  abort (NCSP-koder for provoserte aborter, abortdiagnoser),
  kjønnssykdommer (HIV, syfilis, gonoré, klamydia, hepatitt),
  rusmisbruk og psykiatri (særskilte diagnoser),
  vold, overgrep, selvmordsforsøk
- Lov-/straffeopplysninger

Når slike variabler brukes, gir AI dem en egen seksjon "Særlig sensitive
variabler" i outputen og henviser til **GDPR art. 9** (særlige kategorier).

### Revidert script som valgfri output

Sjekkbokset "Generer også revidert script" utvider prompten med konservative
revisjons-instrukser. AI legger til en `## Revidert script`-seksjon på
slutten av svaret med:

- Reviderte kodeblokk i `microdata`/`python`/`r`-fenced format
- Endringer kommenteres in-line med `// personvern: <forklaring>` (eller `#` for
  Python/R)
- Bare endringer AI er rimelig sikker på (høy/medium sikkerhet)
- Hvis scriptet ser godt minimert ut, en kort note ("Ingen endringer foreslås")

Frontend ser etter `## Revidert script`-markøren og rendrer seksjonen separat
med en "Erstatt scriptet"-knapp.

For microdata-script er ekstra prompt-kontekst (full syntaks-cheatsheet) bare
nødvendig når revidert script er aktivt — sparer tokens i de fleste tilfeller.

### Direktiv i script-kommentar (avansert)

Brukeren kan også styre via kommentar i scriptet selv:

```
// personvern: revider-script: ja
```

Backend parser denne og setter `ønsker_revidert_script: true` i requesten —
overstyrer (eller komplementerer) sjekkboksen. Lar power-users sette
preferanser i template-scripts.

## Rettslig grunnlag

Vurderingen forankres i:

- **Personvernforordningen art. 5(1)(c)** — dataminimering
- **Helseregisterloven § 6** — graden av personidentifikasjon
- **Personvernforordningen art. 89(1)** — vitenskapelig forskning og garantier
- **Personvernforordningen art. 5(1)(b)** — formålsbegrensning
- **Personvernforordningen art. 9** — særlige kategorier (sensitive variabler)

Disse refereres i AI-promptens "Rettslig grunnlag"-seksjon og i den samlede
vurderingen som AI produserer. Lovteksten er gjengitt i `docs/lovverk/`.

**Kalibreringsregel:** personvernforordningen gir ingen endelig svar på hva
som er "nødvendig" — avhenger av formålet. AI skal formulere observasjoner
som muligheter for minimering, ikke som lovbrudd. Endelig avgjørelse ligger
hos forsker og dataansvarlig.

## Personvern-kommentarer (script-side persistens)

Forskerens kontekst lagres som kommentarer i scriptet selv. Dette gjør
scriptet til én sannhetskilde, versjonskontrollerbar sammen med koden.

### Syntaks

**Blokk-form** (genereres når "Lagre som personvern-blokk" er på):

```
// personvern blokk start
// formål: Studere sammenheng mellom utdanning og inntekt for kohorten 1970-1980
// tidsperiode: 1970-1980 fordi kohorten skal være ferdig utdannet
// geografi: kommune nødvendig for å se regionale forskjeller
// sensitive grupper: nei
// alternativer vurdert: SSB-tabell A-04 var for grovkornet
// personvern blokk slutt
```

Eller fritt sammenhengende tekst innenfor blokken (uten feltnavn):

```
// personvern blokk start
// Formål: studere sammenheng mellom utdanning og inntekt for kohort 1970-1980.
// Tidsperioden valgt fordi kohorten skal være ferdig utdannet ved analyseslutt.
// Kommune nødvendig for regionale forskjeller.
// personvern blokk slutt
```

**Enkeltlinje-form** for ad hoc-notater:

```
// personvern: kuttet datoer til måned for å unngå unødig presisjon
// personvern: revider-script: ja
```

Begge former kan eksistere samtidig. Både `//` og `#` som kommentartegn
støttes.

### Kjente feltnavn (kanoniske)

| Feltnavn | Innhold |
| --- | --- |
| `formål` | Forskningsformål, 1–3 setninger |
| `tidsperiode` | Hvorfor disse årene? |
| `geografi` | Hvorfor dette geografiske detaljnivået? |
| `sensitive grupper` | Ja/nei + valgfri begrunnelse |
| `alternativer vurdert` | SSB-tabeller, syntetiske data, fjernanalyse |

NB: `sentrale variabler` er ikke lenger et kanonisk felt — AI utleder fra
scriptet selv.

Strukturerte felter parses for pre-utfylling i sekundær-modalen. Innhold i
blokken som ikke matcher kjente feltnavn behandles som fritekst og brukes som
kontekst i sin helhet.

### Parser-semantikk

To-modus state-machine. Detaljer som tidligere — se eksisterende
`netlify/edge-functions/_lib/parse-script-context.ts`.

### Generator-oppførsel

Når "Lagre som personvern-blokk" er på i sekundær-modalen:

1. Fjern eksisterende `// personvern blokk start ... slutt`-blokk(er)
2. Fjern enkeltlinje `// personvern: <feltnavn>: ...` der feltnavn er kjent
3. Behold fritekst-enkeltlinjer (`// personvern: <fritekst>`)
4. Skriv ny blokk øverst i scriptet:
   - microdata-DSL: helt øverst, før første ikke-kommentar-linje
   - Python/R: etter shebang og `import`/`library()`-header
   - Tom linje etter blokken
5. Innhold er teksten brukeren skrev i sekundær-modalen, prefiks-pakket med
   `//` (eller `#`)

## AI-promptdesign

Én hoved-prompt med placeholders. Innholdet varierer basert på request-felter
(språk, detaljnivå, revidert script).

### Filstruktur

```
netlify/edge-functions/prompts/
  dm-vurder.md            — hoved-prompt med alle placeholders
  _shared-principles.md   — rettslig grunnlag + vurderingsdimensjoner
  _microdata-syntax.md    — full microdata-cheatsheet, inkluderes kun når
                            revidert script er på OG språk er microdata/mixed.
                            Kopi av prompts.py med sync-merknad.
```

Inline-konstanter i `dm-vurder.ts` brukes som faktisk prompt-tekst (Deno Deploy
bundler ikke `.md`-filer automatisk). Filene er kildedokumentasjon —
oppdateres når TypeScript-konstantene oppdateres.

### Placeholders i dm-vurder.md

| Placeholder | Verdi |
| --- | --- |
| `{{SHARED_PRINCIPLES}}` | Innhold fra _shared-principles.md |
| `{{LANGUAGE}}` | "microdata" / "python" / "r" / "auto-detektert: <X>" |
| `{{DETAIL_LEVEL}}` | Variant-tekst basert på "kort" eller "lang" |
| `{{CONTEXT_SECTION}}` | Brukerens formål-tekst, eller "(ikke spesifisert)" |
| `{{REVISION_BLOCK}}` | Tom hvis revidert script er av; ellers instrukser + microdata-syntaks (når relevant) |
| `{{SCRIPT}}` | Scriptet selv |

### Detaljnivå-varianter

**Kort:**

```
RAPPORT-FORMAT: KORT

- Maks 3–5 observasjoner, sorter etter sikkerhet (høy først).
- Samlet vurdering: 1–2 setninger.
- Ingen "Spørsmål til forsker"-seksjon. Hvis kontekst mangler, nevn det i
  selve vurderingen.
- Sensitive variabler: alltid med, selv om det betyr én ekstra observasjon.
```

**Lang:**

```
RAPPORT-FORMAT: LANG

- Gå gjennom alle relevante vurderingsdimensjoner.
- Samlet vurdering: 2–4 setninger med lovreferanser.
- Inkluder "Spørsmål til forsker"-seksjon hvis kontekst mangler (maks 3
  spørsmål).
- Sensitive variabler: alltid med en egen seksjon hvis funnet.
```

### Output-struktur

Markdown, norsk. Felles for begge detaljnivåer:

```
## Klassifisering
Språk: <microdata|R|python|mixed>
Antatt analyseintensjon: <kort, eller "ikke synlig fra scriptet">

## Samlet vurdering
<forankret i relevante hjemler>

## Observasjoner
- **<variabel, linjenr eller mønster>** — <problem>
  - Forslag: <konkret endring>
  - Sikkerhet: <høy | medium | lav>

## Særlig sensitive variabler   ← kun hvis funnet
- **<variabel>** — <kategori under GDPR art. 9>
  - Vurdering: <om essensielt, eller om kan unngås>

## Spørsmål til forsker    ← kun i lang-modus + når kontekst mangler

## Revidert script    ← kun hvis revidert script er på
```microdata
<revidert script>
```
```

### Direktiv-parsing fra script-kommentarer

Hvis scriptet inneholder `// personvern: revider-script: ja` (eller `#`),
parses dette på serversiden og settes `ønsker_revidert_script: true`
uavhengig av sjekkbokset i UI. Lar brukeren styre dette per script.

## Arkitektur (Netlify Edge Functions)

Ett endepunkt. Streamet SSE.

```
Browser (m2py/index.html på Netlify)
   │
   ├──► POST /api/dm-vurder
   │     │
   │     ├── auth-token-sjekk (M2PY_ACCESS_TOKEN)
   │     ├── body-størrelse-sjekk (50 KB)
   │     ├── per-IP rate limit (10/time)
   │     ├── parse personvern-direktiver fra scriptet
   │     ├── bygg prompt med språk + detaljnivå + revisjon
   │     └── stream fra Anthropic API
   │ ◄── SSE: data: {"type":"text","text":"..."} ...
   │     data: {"type":"done","inputTokens":N,"outputTokens":N}
   │
   │ Etter strøm er ferdig:
   │     - Render som markdown
   │     - Hvis "## Revidert script"-seksjon: extract, vis i egen blokk
   │     - Hvis "Lagre som personvern-blokk" var aktivt: skriv blokken
   │       inn i editoren

Netlify env vars:
   ANTHROPIC_API_KEY     = sk-ant-...
   ANTHROPIC_MODEL       = claude-sonnet-4-6
   M2PY_ACCESS_TOKEN     = <delt-token-streng>
```

### Endpoint-rename

`dm-quick` (eksisterende fra Milepæl 1) renames til `dm-vurder` ved
implementering av denne reviderte designen. Gammel route i `netlify.toml`
oppdateres tilsvarende. Frontend justeres til å POST mot `/api/dm-vurder`.

### Hvorfor ett endepunkt

- En enkelt mental modell: én knapp, én forespørsel, ett svar
- Ingen separat dm-prefill / dm-thorough / dm-revise — alt løses ved
  variant-prompt og output-seksjon-marker
- Lavere kostnad enn separate kall (færre runde-turer, færre input-tokens
  pga gjenbrukt prompt-prefiks)

## Datakontrakt

### `dm-vurder` (Edge Function, streaming)

```
POST /api/dm-vurder
Content-Type: application/json
Authorization: Bearer <M2PY_ACCESS_TOKEN>

Request body:
{
  "script": "...",
  "kontekst": "Formål: studere...",      // valgfri, kan være tom string
  "språk": "auto",                        // "auto" | "microdata" | "python" | "r"
  "detaljnivå": "kort",                   // "kort" | "lang"
  "ønsker_revidert_script": false
}

Response: text/event-stream
data: {"type": "text", "text": "## Klassif..."}
data: {"type": "text", "text": "ikasjon\n..."}
data: {"type": "done", "inputTokens": 1234, "outputTokens": 567}
```

### Feilrespons

```
401: ugyldig eller manglende M2PY_ACCESS_TOKEN
413: body > 50 KB
429: rate limited (header: Retry-After: <seconds>)
500: server-konfigurasjonsfeil (manglende ANTHROPIC_API_KEY etc.)
502: Anthropic upstream-feil
```

Klient håndterer non-200 ved å vise feilmelding i status-feltet i resultat-
modalen.

## Frontend: UI og flyt

### Knapper i hamburger-meny

Personvern-seksjonen har nå tre knapper:

```
Personvern
  Vurder dataminimering    ← åpner hovedmodal
  Sett tilgangsnøkkel      ← engangs-setup for token (se Sikkerhet)
  Avregistrer AI-bruk      ← fjerner consent + token
```

"Grundig vurdering" (fra opprinnelig design) er fjernet.

### Førstegangs-consent

Samme tekst som Milepæl 1, uendret. Vises ved første klikk hvis ikke
allerede gitt.

### Hovedmodal (Vurder dataminimering)

Som beskrevet over. State i komponenten:

```js
{
  språk: 'auto',              // dropdown
  detaljnivå: 'kort',          // radio buttons
  ønsker_revidert_script: false,  // checkbox
  kontekst: ''                 // populated by secondary modal
}
```

"Spesifiser formål / kontekst"-knappen viser:
- Hvis `kontekst` er tom: "Spesifiser formål / kontekst"
- Hvis `kontekst` har innhold: "Endre formål / kontekst (<antall> tegn)"

Knappen åpner sekundær modal.

### Sekundær modal (spesifiser formål)

Tekstområde + sjekkboks for å lagre som blokk.

Pre-utfylling ved første åpning:
- Parser eksisterende `// personvern blokk start ... slutt` fra scriptet
- Stripper kommentartegn (` // ` → `  `, eller `# ` → `  `)
- Hvis ingen blokk finnes: tom + placeholder med eksempler

"Bruk" lukker modalen og lagrer teksten i hovedmodal-state.

Sjekkboksen "Lagre som // personvern-blokk i scriptet" er **default på**.
Effekten gjelder først etter at hovedmodalen er sendt og strøm er ferdig
(da skriver frontend blokken inn i editoren med generator-logikken).

### Resultat-modal

Strømming og rendering som i Milepæl 1. Ny logikk når strøm er ferdig:

1. Hvis akkumulert tekst inneholder `## Revidert script`-seksjon:
   - Splitt: hovedvurdering før, kodeblokk etter
   - Render hovedvurdering som markdown i body
   - Vis kodeblokk i en egen "Revidert script"-seksjon under, med
     "Erstatt scriptet"-knapp som overskriver editorens innhold
   - Toast: "Scriptet erstattet. Ctrl+Z for å angre."
2. Hvis ikke: render hele akkumulert tekst som markdown (som Milepæl 1)
3. Hvis "Lagre som personvern-blokk" var aktivt og brukeren spesifiserte
   kontekst: kall generator-logikken for å skrive blokken inn i editoren

## Sikkerhet og tilgangskontroll

### Token-basert tilgang (delt site-token)

Erstatter Origin-sjekken fra Milepæl 1. En delt streng (M2PY_ACCESS_TOKEN
env var) brukes som tilgangsnøkkel.

**Flyt:**

1. Du genererer en token og setter `M2PY_ACCESS_TOKEN` i Netlify env vars
2. Du deler tokenen privat (FHI-epost) til folk du vil gi tilgang
3. Bruker går til hamburger → Personvern → "Sett tilgangsnøkkel"
4. Modal ber om å lime inn token; lagres i `localStorage` som
   `microdata_dm_token`
5. Hver request til `/api/dm-vurder` sender `Authorization: Bearer <token>`
6. Edge Function sammenligner mot `M2PY_ACCESS_TOKEN`. Mismatch → 401.

**Frontend ved 401:** Tøm `localStorage` for tokenet, vis modal "Tilgangs­
nøkkelen er ugyldig eller utløpt. Be administrator om en ny nøkkel."

**Rotasjon:** Sett ny verdi i Netlify env vars, deploy. Alle gamle tokens
blir ugyldige umiddelbart. Du sender ny token-streng til de som skal ha
fortsatt tilgang.

**Hvorfor ikke Origin-sjekk:** Origin-sjekken er klønete (krever vedlikehold
av URL-liste, fungerer dårlig på branch deploys og deploy previews) og
beskytter ikke mot scripted misbruk (Origin kan spoofes). Token er enklere
å vedlikeholde og gir reell autentisering.

### Andre sikkerhetslag

Beholdt fra Milepæl 1:

- **Body-størrelse-grense**: 50 KB (innkommende JSON)
- **Per-IP rate limit**: 10 kall/time/IP via Netlify Blobs

Ny:

- **Anthropic budget cap**: sett i Anthropic-konsollen (anbefalt $5–10/dag som
  sikkerhetsnett mot katastrofal misbruk)

### Ikke vurdert i Milepæl 2

- IP-binding av tokens (kompliserer UX uten klar gevinst — IP-er endres)
- Per-bruker-tilgang via eksisterende Anvil-auth (planlegges i Milepæl 3)

## Milepæl 3 — Gjenbruk Anvil-auth for unified tilgang

Milepæl 2 leverer en delt site-token. Milepæl 3 dropper denne i UI-en til
fordel for å gjenbruke m2py sin eksisterende Anvil-baserte innloggings-
infrastruktur. Hvis brukeren allerede er logget inn i m2py (for å lagre
script, bruke AI-hjelp, etc.), gir samme innlogging også tilgang til
dataminimering-vurdering — ingen separat token-håndtering.

**Bakgrunn:** m2py bruker allerede Anvil-app `microdata-api` for autentisering
via magic-link-mail. `auth.py` har komplett system: `issue_magic_code`,
`consume_magic_code`, `send_magic_link_email` (via `anvil.email.send`),
session-tokens (`issue_session_token`), email-whitelist (`anvil.yaml`),
bootstrap-admins. Frontend har `window.mdAuth` med innlogget bruker.

Når denne infrastrukturen allerede finnes, er det ingen grunn å bygge en
parallell tilgangsnøkkel-mekanisme bare for dataminimering.

### Kjernemodell

- Bruker logger inn i m2py via eksisterende magic-link-flyt (én gang per
  browser; krever klikk på lenke i mail)
- `window.mdAuth.session.token` settes i localStorage
- Når bruker klikker "Vurder dataminimering", sender frontend dette
  tokenet i `Authorization: Bearer <token>`
- Edge Function validerer mot Anvil — hvis OK, gi tilgang

Ingen ny mail-flyt, ingen ny token-paste-modal, ingen ny consent-flow for
dataminimering spesifikt. Brukeren ser én Logg inn-knapp som hører til
m2py som helhet.

### Multi-maskin

Brukere som vil bruke m2py på flere maskiner må logge inn på hver av dem
via magic-link. Dette er Anvil-systemets nåværende oppførsel — endres ikke
av denne milepælen. (Hvis vi senere vil legge til paste-bart token for
flere maskiner, gjør vi det som en utvidelse av m2py-auth generelt, ikke
av dataminimering spesifikt.)

### Anvil-endepunkt for token-validering — gjenbruk eksisterende

`microdata-api/server_code/auth_endpoints.py` har allerede
`@anvil.server.http_endpoint("/auth/me", methods=["GET"], enable_cors=True)`
som validerer Bearer-tokenet og returnerer brukerinfo (inkl. email) eller
401. Vi gjenbruker dette direkte — ingen Anvil-side endring nødvendig.

Edge Function kaller `GET <anvil-base>/_/api/auth/me` med Authorization-
headeren videresendt fra brukerens request. Anvil returnerer:

```json
{
  "principal_kind": "user",
  "user": { "email": "...", ... }
}
```

eller 401 hvis token er ugyldig.

### Edge Function-endringer

`dm-vurder.ts` token-sjekken endres til:

```typescript
const token = extractBearerToken(request);

// Sjekk M2PY_ACCESS_TOKEN først (dev/admin fallback, beholdes fra M2)
const sharedToken = Deno.env.get("M2PY_ACCESS_TOKEN");
if (sharedToken && token === sharedToken) {
  // OK — dev fallback
} else {
  // Valider mot Anvil
  const anvilUrl = Deno.env.get("M2PY_ANVIL_VALIDATE_URL");
  const resp = await fetch(anvilUrl, {
    method: "POST",
    headers: { "Authorization": `Bearer ${token}` }
  });
  if (!resp.ok) return new Response("Unauthorized", { status: 401 });
  const data = await resp.json();
  if (!data.valid) return new Response("Unauthorized", { status: 401 });
  // Optional: store data.email for logging/audit
}
```

Beholdes:
- Body-størrelse-grense
- Per-IP rate limit
- Alle andre prompt-/respons-detaljer

Endrer:
- M2PY_ALLOWED_ORIGINS — kan slettes (har vært ubrukt siden M2)
- Token-sjekken: nå Anvil-validering primært, M2PY_ACCESS_TOKEN som fallback

Ny env-var:
- `M2PY_ANVIL_VALIDATE_URL` — full URL til Anvils validate-session-endepunkt

### Frontend-endringer

**Hamburger-meny:** "Sett tilgangsnøkkel" og "Avregistrer AI-bruk" fjernes.
Dataminimering-knappen står alene under Personvern-seksjonen.

**`runDmVurder`:** bytt fra `getDmToken()` til `window.mdAuth?.session?.token`:

```javascript
const session = window.mdAuth && window.mdAuth.session;
const token = session && session.token;
if (!token) {
  alert('Du må være logget inn i m2py for å bruke dataminimering. Bruk Logg inn-knappen.');
  return;
}
headers['Authorization'] = `Bearer ${token}`;
```

**`btnDmQuick`-handler:** sjekker `window.mdAuth?.user` før den åpner
dm-options-modal. Hvis ikke innlogget, vis enten en alert eller trigger
m2py sin eksisterende login-modal.

**Token-relatert kode:** `DM_TOKEN_KEY`, `getDmToken`, `setDmToken`,
`showDmTokenSetup`, `dmTokenBackdrop` — alle fjernes.

**localStorage-key `microdata_dm_token`:** ryddes ved første sideload etter
deploy (engangs migrasjon-jobb).

### M2PY_ACCESS_TOKEN beholdes som backdoor

`M2PY_ACCESS_TOKEN`-env-varen og sjekken mot den i Edge Function beholdes.
Brukes til:
- Lokal utvikling (du har det allerede i `.env`)
- Nødtilgang hvis Anvil er nede
- Demo-bruk uten Anvil-login

Brukes IKKE i UI — ingen knapp for å sette den fra browser. Eksisterer kun
som "skjult" backend-mekanisme for power-users som vet om den.

### Sikkerhetsbetraktninger

- **Anvil-whitelisten gir tilgang.** Hvis bruker er logget inn i m2py, er
  vedkommende allerede i Anvil sin email_whitelist. Ingen ekstra sjekk
  nødvendig på m2py-siden.
- **Rate-limit på dm-vurder beholdes** (10/time/IP). Anvil har sine egne
  rate-limits på session-utstedelse.
- **Anthropic budget cap** som ytre sikkerhetsnett.
- **Session-token-tyveri:** hvis noen får tak i en Anvil-session-token,
  får de tilgang til både m2py og dataminimering. Anvil har egne
  utløps-/revokerings-mekanismer som vi arver.

### Implementering — Milepæl 3 tasks

Anvil har allerede `/auth/me` — ingen Anvil-side endring. 6 tasks:

1. **Edge Function: bytt token-sjekken** i `dm-vurder.ts` til Anvil-
   validering (med M2PY_ACCESS_TOKEN som fallback). Legg til
   `M2PY_ANVIL_VALIDATE_URL` env-var (eksempel:
   `https://mdataapi.anvil.app/_/api/auth/me`).
2. **Frontend: oppdater `runDmVurder`** til å lese `window.mdAuth.session.token`
   i stedet for `getDmToken`. Fjern token-relatert kode (`DM_TOKEN_KEY`,
   `showDmTokenSetup`, `dmTokenBackdrop` etc.).
3. **Frontend: oppdater `btnDmQuick`-handler** til å sjekke login-status og
   trigge login-modal om nødvendig.
4. **Frontend: meny-cleanup** — fjern "Sett tilgangsnøkkel" og "Avregistrer
   AI-bruk"-knappene.
5. **Migrasjon-snippet:** rydde `microdata_dm_token` fra localStorage ved
   første sideload etter deploy.
6. **Dokumentasjon:** oppdater hjelp.html — "krever innlogging i m2py" i
   stedet for "trenger tilgangsnøkkel". Fjern token-paste-instrukser.

## Personvern (brukerens data sendt til AI)

- Scriptet sendes til Anthropic via Edge Function. Anthropic-policy:
  API-input brukes ikke til trening som default.
- Edge Function lagrer ikke scriptet utover funksjons­kallets levetid.
- Førstegangs-consent gjør dette eksplisitt for brukeren.

## Kostnader

Per vurdering:
- Kort, uten revidert script: ~3K input + ~1K output = $0.01–0.02
- Lang, uten revidert script: ~3K input + ~2K output = $0.02–0.03
- Kort med revidert script (microdata): ~5K input + ~2K output = $0.03–0.05
- Lang med revidert script (microdata): ~5K input + ~3K output = $0.05–0.07

Estimat ved 100 vurderinger/dag (anslag, opt-in): ~$30–60/mnd ved blandet bruk.
Anthropic-budsjettcap som sikkerhetsnett.

## Avgrensninger for MVP

Ikke med:

- Ingen inline-markering av variabler i editoren ved observasjoner
- Ingen vurderingshistorikk
- Ingen per-endring accept/reject (revidert script er all-or-nothing)
- Ingen statisk forsjekk før AI-kall
- Ingen streaming-rendering av markdown med live formatering — rå tekst
  mens stream pågår, full render ved ferdig
- Ingen multi-script-vurdering (kun aktivt script)
- Ingen per-bruker-tokens (delt token i v1)
- Ingen magic-link/epost-auth (vurder senere)

## Implementeringsrekkefølge

- **Milepæl 1 — Kjapp-modus:** ✅ Levert
- **Milepæl 2 — Forenklet flyt:** ✅ Levert
- **Milepæl 3 — Selvbetjent tilgang via epost-kode:** Planlagt (se egen
  seksjon over)

### Milepæl 2 (oppsummering, levert)

1. Backend: bytt `dm-quick.ts` til `dm-vurder.ts` (rename + utvid prompt-bygging
   med språk/detaljnivå/revisjon)
2. Backend: legg til token-auth, fjern Origin-sjekk
3. Backend: parser-utvidelse for `// personvern: revider-script: ja`-direktiv
4. Frontend: ny hovedmodal med innstillinger
5. Frontend: sekundær modal for kontekst-spesifikasjon
6. Frontend: token-setup modal + "Sett tilgangsnøkkel"-knapp
7. Frontend: resultat-modal med splitting av Revidert script-seksjon og
   "Erstatt scriptet"-knapp
8. Frontend: generator-logikk for å skrive personvern-blokk
9. Dokumentasjon: oppdater `hjelp.html` med ny flyt

### Milepæl 3 (planlagt)

Se egen "Milepæl 3 — Selvbetjent tilgang via epost-verifisert kode"-
seksjon over for full design og 10 task-liste.

## Åpne spørsmål

- **Modellvalg:** Sonnet (cost-effective) eller Opus (dypere vurdering).
  Anbefaling: start med Sonnet og oppgrader hvis vurderings­kvaliteten er
  for tynn.
- **Token-distribusjon:** Milepæl 2 leverer delt token (manuell utdeling).
  Milepæl 3 dropper det til fordel for gjenbruk av eksisterende m2py
  Anvil-auth — innlogging i m2py = tilgang til alt, inkludert dataminimering.
- **Hvis Anthropic returnerer Revidert script mid-stream:** edge case der
  AI inkluderer kode-blokken før den er ferdig. Frontend bør ikke splitte
  før strøm er fullstendig ferdig.
- **Sync av microdata-syntaks-regler:** `_microdata-syntax.md` (Netlify) og
  `prompts.py` (Anvil) må holdes synkron. Hvis drift blir et problem,
  vurder CI-sjekk eller felles kildefil.

## Designhistorikk

**Opprinnelig design (2026-05-22):**
- To moduser: Kjapp (én-kallflyt) og Grundig (to-stegs med skjema-prefill)
- Separat dm-revise endepunkt for revidert script
- Origin-basert tilgangskontroll (M2PY_ALLOWED_ORIGINS)
- Skjema med 6 felter inkludert "sentrale variabler"

**Revidert design (2026-05-23) etter Milepæl 1-erfaring:**
- Én sammenslått flyt med valgfri kontekst-spesifikasjon
- Valgfri revidert script som output-seksjon i samme svar (ingen separat
  endepunkt)
- Token-basert tilgangskontroll
- "Sentrale variabler" droppet — utledes av AI fra scriptet
- Eksplisitt sensitiv-variabel-flagging (GDPR art. 9)
- Detaljnivå: kort/lang
- Eksplisitt språkvalg som dropdown i UI

## Referanser

- `docs/lovverk/dataminimering.md` — utdrag, Helsedirektoratet Faktaark 57
- `docs/lovverk/formalsbegrensning.md` — utdrag
- `docs/lovverk/lagringsbegrensning.md` — utdrag
- `docs/lovverk/personvernprinsippene.md` — oversikt
- https://www.helsedirektoratet.no/normen/personvernprinsippene-faktaark-57
- Personvernforordningen art. 5, 9, 89(1)
- Helseregisterloven § 6
- Helseforskningsloven § 32
