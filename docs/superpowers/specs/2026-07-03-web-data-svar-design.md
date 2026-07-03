# Web-modus: generelle dataspørsmål med åpne kilder — design

Dato: 2026-07-03. Status: design godkjent i samtale; venter på spec-review.

## Mål

En tredje AI-modus, **«Web»**, ved siden av «Rask» (kode-svar) og «Anvil»:
brukeren stiller et hvilket som helst spørsmål, og AI-en genererer et kjørbart
script (i aktiv editor-modus: python/r/duckdb) som **laster ned åpne data fra
verifiserte kilder og analyserer dem med vitenskapelig metode** (kausal
identifikasjon, konfundering, heterogenitet, usikkerhet). Nøkkelproblemet som
skiller dette fra microdata-assistenten: det finnes ingen variabelkatalog å
front-laste — datakildene må **oppdages** per spørsmål.

Avgrensning: microdata-modus er urørt (katalog-forankret som i dag). Web-modus
gjelder python/r/duckdb.

## Vedtatte hovedvalg

1. **Arkitektur B**: én agentisk edge-funksjon med server-side tool-loop
   (ikke front-lastet enkeltkall, ikke fysisk oppdelt pipeline).
2. **Egen knapp**: tredje AI-modus «Web» (`md_ai_mode: 'fast' | 'anvil' | 'web'`).
3. **Kun admin**: knappen vises bare for `user.is_admin`; endepunktet håndhever
   admin server-side (skjult knapp er ikke sikkerhet).
4. **CORS-proxy**: ja — `/api/hent`, SSRF-herdet generell GET-proxy.
5. **Reparasjon**: automatisk, inntil **3 runder** mot faktiske kjørefeil.
   Iterasjon i discovery skjer gratis inne i tool-loopen; egne critique-pass på
   plan/generering er vurdert som marginale og droppes.
6. **Flerkilde**: prompten oppmuntrer eksplisitt til å kombinere flere kilder
   (join på år, landkode, kommunenummer); registeret dokumenterer join-nøkler.
7. **Kuratert-men-dynamisk**: et register over nøkkelkilder (kan utvides over
   tid) + fritt websøk etter relevante datafiler (CSV o.l.) som kan brukes
   dersom de er svært relevante — men bare etter probe-verifisering.
8. **connect/load-linjer er leveringsmekanismen** for data som kan hentes
   med én forespørsel (GET direkte, eller POST innpakket via proxyen):
   `# connect <kilde> as alias` (koble til kilden) + `# load <url> as NAVN`
   (uttrekket) — se terminologi i 5c. Ikke ad-hoc nedlastingskode. Dagens
   D1-form (`# require <url> as navn` som uttrekk) forblir gyldig (legacy),
   og microdata-modusens require/import er urørt.
9. **Variabel-nivå uttrekk, ikke bare hele datasett**: nasjonale byrå-API-er
   (PxWeb, Eurostat, WB) støtter uttak av utvalgte variabler/dimensjoner —
   pipelinen bygger analysedatasett fra variabler, som i microdata-tankegangen.

## Pipeline (én agentisk samtale, faset av systemprompten)

```
Spørsmål ──▶ 1 TOLK: estimand, enhet, geografi/periode,
             identifikasjonsstrategi, data-ønskeliste
         ──▶ 2 FINN (tool-loop, budsjett ~12 kall):
             search_catalog / web_search → kandidat-tabeller
             table_metadata → variabler/dimensjoner/kodelister i tabellen
             → bygg variabel-nivå spørrings-URL (kun de variablene,
               periodene og geografiene analysen trenger)
             probe → finnes endepunktet? kolonnenavn? CORS?
             (tomt søk → synonymer/annet språk/annen kilde;
              feilet probe → neste kandidat — planen revideres naturlig)
         ──▶ 3 GENERER: script i aktiv modus, mot OBSERVERTE skjemaer:
             kilder som `# connect <base|register-id> as alias`,
             uttrekk som `# load <url-eller-alias/sti> as navn`
             (GET direkte; POST-API-er GET-innpakket via /api/hent;
              editoren materialiserer som DataFrame/tabell),
             merge/join til ÉN analysedataframe der det er nyttig,
             flertrinns-interaksjoner som kode i scriptet;
             /api/hent-omvei der probe fant manglende CORS;
             rå → justert estimat, antakelser oppgitt, kilder sitert
         ──▶ 4 KJØR & REPARER (klient): syntakssjekk → auto-kjør →
             feil + feilklasse tilbake til endepunktet, maks 3 runder
```

Grunnprinsippet: **aldri generer mot antatte skjemaer.** Datasett-ID-er og
kolonnenavn kommer fra probe-resultater, ikke modellhukommelse. Det dreper den
dominerende feilmoden (hallusinerte tabell-ID-er/kolonner) ved roten.

## Komponenter

### 1. `netlify/edge-functions/data-svar.ts` (ny)

Agentisk endepunkt. Auth-gate som i dag **pluss** admin-krav: `/auth/me`-svaret
må ha `user.is_admin === true` (utvid `_lib/auth.ts` til å returnere
brukerobjektet, ikke bare boolean; behold positiv-cache med samme TTL).

Request: `{ question, mode: 'python'|'r'|'duckdb', history?, repair?: {script, error, round} }`.
Response: SSE-strøm med to hendelsestyper i tillegg til dagens `text`/`done`:
`{"type":"progress","text":"Søker i SSB-katalogen …"}` (én per tool-kall, vises
som statuslinjer i chatten) og til slutt `{"type":"sources","sources":[...]}`
(kildemanifest: url, tittel, verifisert-av-probe: ja/nei, via-proxy: ja/nei).

Modell: samme som kode-svar (Sonnet-klassen) med `web_search` som hosted tool
og `search_catalog`/`table_metadata`/`probe` som klient-tools i loopen. Maks ~12 tool-kall,
deretter tvinges generering (ærlig degradering: «fant ikke data for X» heller
enn fabrikkering).

### 2. `_lib/anthropic.ts`: tool-loop-støtte (utvidelse)

I dag: kun enkeltkall. Nytt: `runToolLoop(opts)` — ikke-strømmende turer så
lenge modellen kaller tools, strømmende siste tur (svaret). Emitterer
progress-callback per tool-kall. `web_search` er Anthropic-hosted (ingen
implementasjon her); `search_catalog`/`probe` dispatches til `_lib/tools/`.

### 3. `_lib/tools/` (ny)

- `search-catalog.ts` — adaptere per kildetype, valgt via registeret:
  PxWeb (SSB), Eurostat, Verdensbanken, OECD SDMX, data.norge.no (CKAN/DCAT).
  Én funksjon per adapter: `(query) → [{id, tittel, periode, geografi, url}]`.
- `table-metadata.ts` — variabel-nivå oppslag for en truffet tabell:
  `(kilde, tabell_id) → {variabler: [{navn, label, koder/verdier, tid}]}`
  (PxWeb metadata-endepunkt, Eurostat/SDMX datastruktur, WB indikator-info).
  Gir modellen det den trenger for å bygge en **minimal spørrings-URL** som
  henter bare de variablene/periodene/geografiene analysen trenger — samme
  «bygg datasett fra variabler»-tankegang som microdata-importen.
- `probe.ts` — begrenset GET (timeout ~10 s, les maks ~256 kB): content-type,
  HTTP-status, utledet skjema (kolonnenavn + et par eksempelrader for
  CSV/JSON-stat/SDMX-JSON), og CORS-vurdering (`access-control-allow-origin`)
  → «direkte fetch» eller «via /api/hent». Samme SSRF-vern som proxyen.
- Web-søk-funn har regel i systemprompten: **må probes før bruk i script.**

### 4. `data/data-sources.json` (ny) — registeret

Skjema per kilde:

```json
{
  "id": "ssb",
  "navn": "Statistisk sentralbyrå (PxWebApi)",
  "utgiver": "SSB",
  "tillit": "offisiell",              // offisiell | etablert | funnet
  "tilgang": "pxweb",                 // pxweb | sdmx | rest | ckan | fil
  "base_url": "https://data.ssb.no/api/pxwebapi/v2/",
  "sok_endepunkt": ".../tables?query={q}&lang=no",
  "cors": true,
  "join_nokler": ["kommunenummer", "fylkesnummer", "år"],
  "oppskrift": { "python": "…", "r": "…", "duckdb": "…" },
  "sporrings_url_mal": "…/table/{id}?valueCodes[{var}]={koder}&format=csv",
  "auth": { "type": "api_key", "env": "FRED_API_KEY", "plassering": "query:api_key" },
  "quirks": "JSON-stat2; maks 800k celler per uttak; …"
}
```

**Kilder som krever API-nøkkel** (`auth`-feltet): nøkler lagres som
Netlify-miljøvariabler (edge-funksjonene leser `Deno.env`) og injiseres
**kun server-side** — i tool-laget (search/metadata/probe) og i `/api/hent`.
Nøkkelen skal aldri stå i genererte script eller nå nettleseren: keyed kilder
hentes alltid via proxyen (`/api/hent?url=…` uten nøkkel; proxyen slår opp i
registeret og legger på nøkkelen). Injisering skjer BARE når URL-verten
matcher registeroppføringens vert — ellers kunne en vilkårlig URL lure
proxyen til å sende nøkkelen til fremmed vert. Netlify-env er riktig hjem for
nøklene (samme trust-domene som edge-funksjonene, ingen ekstra rundtur);
Anvil er alternativet den dagen vi trenger *runtime-redigerbar* lagring
(f.eks. dynamisk register eller bruker-spesifikke nøkler) — ikke nødvendig nå.

`sporrings_url_mal` dokumenterer hvordan et **variabel-nivå uttrekk**
materialiseres som én GET-URL (PxWebApi v2 GET med valueCodes, Eurostats
CSV/TSV-endepunkt med dimensjonsfiltre, WB `…/indicator/{id}?format=json`).
En slik URL er load-bar (se «Levering» under); API-er som krever POST
(PxWeb v1, f.eks. StatFin) blir load-bare via proxyens GET-innpakking
(loader-utvidelse 3 under «Levering»).

Seed-liste: SSB, Eurostat, Verdensbanken, OECD, WHO GHO, Our World in Data
(grapher-CSV), FRED (ikke-CORS → proxy), Norges Bank, NAV, FHI,
data.norge.no, raw.githubusercontent.com (fil-kilde, discovery via websøk),
Wikipedia (tabeller via `/api/hent` + `pd.read_html` — se 5d).
Registeret renderes kompakt inn i den cachede system-prefiksen (navn, hva
kilden dekker, søkbarhet, join-nøkler) — oppskrifter og detaljer hentes av
tool-laget, ikke front-lastet i sin helhet. «Funnet»-tillitsnivået er veien
for promotering: kilder oppdaget via websøk som viser seg gode, legges inn
manuelt (admin) med `tillit: "funnet"`.

**Registeret er en levende kunnskapsbase om «hvordan snakke med» hver kilde.**
`oppskrift`, `sporrings_url_mal` og `quirks` fylles på etter hvert som vi
lærer API-ene å kjenne (rate-limits, kodelister, datoformater, fallgruver).
Konkret rutine: når en reparasjonsrunde avdekker en kilde-quirk (feil
datoformat, celletak, uventet kolonnenavn), noteres den i registeret så neste
generering slipper samme feil. Manuelt/admin i første omgang; kan senere
halvautomatiseres (AI-en foreslår register-oppdatering etter vellykket repair).

### 5. `netlify/edge-functions/hent.ts` (ny) — CORS-proxy `/api/hent?url=…`

Ren allowlist er for rigid når funne CSV-er kan ligge hvor som helst; i stedet
generell men herdet: kun GET; kun http(s) mot offentlige verter (blokker
private/link-lokale IP-områder, også etter DNS-oppslag og redirects); ingen
videresending av auth-/cookie-headere; størrelsestak ~50 MB (strømmet, avbryt
over taket); timeout; `Access-Control-Allow-Origin` mot eget origin. Samme
auth-gate som AI-endepunktene (Bearer-token) + admin-krav så lenge featuren er
admin-only, så proxyen ikke er et åpent relé.

Nøkkel-injisering: for kilder med `auth` i registeret legger proxyen på
API-nøkkelen fra Netlify-env — kun når URL-verten matcher registeroppføringen
(se registerseksjonen). FRED i seed-lista er første bruker av dette.

### 5b. Levering: connect/load-linjer (utvidet D1-mekanisme)

Alt som kan hentes med én forespørsel deklareres i genererte script som
load-linjer (`#`/`--`/`//` per språk; terminologi og to-nivå-form i 5c):

```
# load https://data.ssb.no/…/tabell?valueCodes[Region]=…&format=csv as arbeidsledighet
# load https://raw.githubusercontent.com/owid/…/co2.csv as co2
```

Editoren henter URL-ene og materialiserer dem som DataFrame (python),
data.frame (r) eller tabell (duckdb) med aliaset som navn — nøyaktig slik
URL-require fungerer i dag (D1). Gevinster: scriptet forblir en selvdokumenterende,
reproduserbar enhet (kilde-URL-er står øverst); ingen per-språk
nedlastingskode for enkle uttrekk; og ruting/proxy håndteres ett sted.
Nødvendig utvidelse av loaderen: **fallback til `/api/hent`** når
direkte fetch feiler på CORS (probe-resultatet forteller genereringen hvilke
kilder det gjelder, så scriptet kan også skrive proxy-URL-en eksplisitt).
Proxy-kall fra editoren sender brukerens Bearer-token (samme auth som
AI-endepunktene) — load mot offentlige CORS-åpne URL-er er uendret og
krever ingen innlogging.

**Nødvendige loader-utvidelser (i scope, dagens tilstand i parentes):**

1. **Innholdsbasert format-deteksjon.** Dagens loader matcher kun URL-er som
   slutter på `.csv`/`.parquet` (`index.html`-regexen) — API-URL-er som
   `…/data?valueCodes[…]=…&outputFormat=csv` matcher ikke. Nytt: match enhver
   http(s)-URL og avgjør format via respons `Content-Type` (evt.
   format-hint i URL-en). Uten dette er ingen API-URL load-bar.
2. **Lokal materialisering i dialekt-modusene.** URL-fetch → WASM-FS →
   DataFrame finnes i dag bare på safestat-stien; i python/r/duckdb-modus er
   en `# require <url>`-kommentar ikke materialisert lokalt. Implementeres
   for alle tre moduser (alias → DataFrame/data.frame/tabell), med
   `/api/hent`-fallback ved CORS-feil.
3. **GET-innpakking av POST-API-er via proxyen.** Eldre PxWeb v1-installasjoner
   (f.eks. Statistics Finland/StatFin) krever POST med JSON-spørring — ingen
   enkelt GET-URL finnes. `/api/hent` utvides med en `body`-parameter:
   `# load /api/hent?url=<endepunkt>&body=<url-enkodet-json> as tyollisyys`
   — proxyen gjør POST-en server-side og strømmer svaret tilbake. Dermed er
   selv POST-API-er load-bare, og alle datakilder i et generert script står
   deklarert øverst på én selvdokumenterende linje. Samme SSRF-vern;
   `body` sendes kun som `application/json`, størrelsesbegrenset.

Flertrinns-interaksjoner som ikke lar seg uttrykke som én (ev. innpakket)
forespørsel skrives fortsatt som kode i scriptet med kilde-URL i kommentar.

### 5c. To-nivå kildedeklarasjon og terminologi

**Behovet:** flere uttrekk fra samme kilde skal ikke gjenta base-URL-en
(spesielt stygt for proxy-innpakkede POST-kilder). Løsning: en valgfri
kildedeklarasjon som uttrekkslinjene refererer til — ren statisk
prefiks-substitusjon i parseren, før noe hentes. Målet kan være en full
base-URL **eller en register-id** (henter `base_url` fra `data-sources.json`;
keyed kilder får dermed proxy-ruting og nøkkelinjisering automatisk).

**Terminologi-diskusjon.** Microdata-DSL-en (microdata.no sitt språk — ikke
vårt å endre) bruker `require <databank> as fd` om kilden og
`import fd/VARIABEL as alias` om uttrekk av enkeltvariabler (alias = kolonne).
D1-direktivet (`# require <url> as alias`) bruker derimot `require` om
*uttrekket*. Å gjenbruke `require` i web-direktivene — uansett rolle — gir
ordkollisjon med subtilt ulik betydning på tvers av moduser. Valget falt på
`connect`: ordet sier presist hva linja gjør (etabler et håndtak til kilden,
ingen data flyttes), og `require` forblir microdatas ord alene.

`import` som uttrekksverb ble vurdert og forkastet av én avgjørende grunn:
direktivene bor i *kommentarer*, og `# import <X> as <Y>` er nøyaktig hva en
utkommentert python-import ser ut som (`# import pandas as pd` — svært vanlig
i ekte script). Parseren måtte hatt lekk heuristikk for å skille dem, og en
utkommentert kodelinje kunne utløst datahenting. `load` har ikke denne
formen i noe av vertsspråkene (R's `load(...)` og DuckDBs `LOAD ext` matcher
ikke `X as Y`-mønsteret), leser naturlig («load data into the session»), og
unngår den falske parallellen til microdatas import, som binder en *kolonne*
der load binder en *hel ramme*.

**Beslutning: `connect` (kilde) + `load` (uttrekk).**

```
# connect https://data.ssb.no/api/pxwebapi/v2/tables as ssb   ← kilde (base-URL)
# connect fred                                                 ← kilde (register-id; alias = id)
# load ssb/07459/data?valueCodes[Alder]=15-74&outputFormat=csv as ledighet
# load fred/series/observations?series_id=UNRATE as us_ledighet
# load https://raw.githubusercontent.com/owid/…/co2.csv as co2   ← direkte uttrekk, implisitt kilde
```

- `# connect <base-url|register-id> [as alias]` — deklarerer en kilde.
  Tilsvarer rollen microdatas `require no.ssb.fdb:53 as fd` har.
- `# load <alias>/<sti+spørring> as navn` — uttrekk under en kilde;
  `# load <full-url> as navn` — enkeltstående uttrekk. Bredere enn
  microdatas import: ett uttrekk kan gi flere variabler/kolonner eller en
  hel CSV, og aliaset binder en **hel ramme** (DataFrame/data.frame/tabell),
  ikke en kolonne. Denne forskjellen sies eksplisitt i dokumentasjon og
  AI-prompt (én linje per modus), ikke gjemmes.
- Mental modell: **connect = koble til kilden, load = hent data derfra
  under et navn.**

**Bakoverkompatibilitet (krav):** dagens deployede `# require <url|navn> as
alias` med uttrekks-semantikk (D1) skal fortsette å virke uendret — parseren
godtar `require` som legacy-alias for uttrekk på ubestemt tid, og i
microdata-modus er `require`/`import` selvsagt urørt (konformitet med
microdata.no). Dokumentasjon og AI-prompt lærer kun bort connect/load.
Implementasjonskrav: `connect`/`load`-formene finnes ikke i dag og må
bygges — parser-regexene (`deriveSafeStatExecutor`, `maybeRunRemote` m.fl.,
en håndfull steder i `index.html`) utvides til å gjenkjenne alle tre verbene;
serveren berøres ikke (den mottar ferdig-resolverte kilder).

**Mulige tillegg (samme opsjons-hale som D1 allerede planlegger):**
`, exec(local|remote)` (finnes), `format(csv|json-stat|parquet)` (hint når
Content-Type er tvetydig), `via(proxy)` (tving proxy-ruting), og på sikt
`body({...})` som penere alternativ til URL-enkodet POST-innpakking.
Promptregelen fra flerkilde-avsnittet står: ett uttrekk per tabell med flere
variabler i samme uttrekk der API-et tillater det — kildedeklarasjonen
reduserer gjentakelse *på tvers av* uttrekk, ikke innenfor ett.

### 5d. Datatilfangst-stigen: også data uten endepunkt

Mye data finnes ikke bak en fetch-bar URL: tabeller i Wikipedia-artikler og
PDF-er, små referansetabeller, og fakta i modellens egen kunnskap. Disse
slippes inn — men gjennom en eksplisitt **tillitsstige** som håndheves i
prompten og synliggjøres i kildemanifestet:

1. **Probet endepunkt** (`# load …`) — alltid foretrukket. Merk: Wikipedia-
   tabeller ER load-bare: `# load /api/hent?url=<wiki-url> as raw` +
   `pd.read_html(raw)` (lxml via micropip) — reproduserbart, full proveniens.
   Wikipedia ligger i registeret med denne oppskriften.
2. **Transkribert fra hentet innhold** — modellen kan skrive små tabeller
   (< ~50 rader) inline i scriptet NÅR den faktisk har lest kilden i
   tool-loopen (hosted `web_fetch` henter side-/PDF-innhold inn i konteksten).
   Krav: kilde-URL i kommentar ved datablokken + merket «transkribert, ikke
   maskinelt verifisert».
3. **Modellkunnskap** — kun stabile referansefakta (ISO-koder, kjente
   datoer/klassifiseringer), merket «fra modellkunnskap — verifiser», og
   ALDRI som utfallsvariabel i en analyse. Utfall skal komme fra nivå 1–2.

Inline-konvensjon per språk: python
`data_<navn> = """..."""` + `pd.read_csv(io.StringIO(data_<navn>))`;
R `read.csv(text = "...")`; duckdb via `#py`-hybrid eller VALUES-liste.
Killer-bruksområdet er lim-tabellene kausale design trenger (reformdatoer,
tiltaks-/kontrollklassifisering, regiongrupperinger) — små, sjelden i
statistikk-API-er, og avgjørende for DiD/event-studier.

Inline-blokker føres i kildemanifestet med eget tillitsmerke (nivå 2/3), så
det alltid er synlig hva analysen hviler på. Verktøytillegg: hosted
`web_fetch` inn i TOOL_DEFS ved siden av `web_search`. Prompten lærer også
bort søkehåndverk (`site:data.norge.no`, `filetype:csv`, norsk+engelsk søk).

### 6. Frontend (`js/ai-chat.js`, `index.html`)

- Web er en egen, dedikert send-knapp (`#aiSendWebBtn`) ved siden av
  Send/Send⚗︎ — ikke en tredje syklus-verdi på hurtigmeny-bryteren «AI-svar:»
  (den forblir fast/anvil). Knappen rendres kun når `user.is_admin` og aktiv
  editor-modus er python/r/duckdb (`webModeEligible()`); den skjules i
  microdata-modus og for ikke-admin-brukere, og bruker ikke `md_ai_mode`.
- Progress-linjer fra SSE (`type:"progress"`) vises løpende, kildemanifest
  (`type:"sources"`) vises under svaret med verifisert-merke per kilde.
- Auto-reparasjon: etter generering kjøres syntakssjekk (Pyodide-parse for
  python — som v2), deretter auto-kjøring i aktiv runtime. Ved feil sendes
  `{repair: {script, error, round}}` tilbake til `/api/data-svar`; maks 3
  runder; deretter ærlig feilmelding med hva som ble forsøkt. Feilklasser i
  repair-prompten: nettverk/CORS → bytt til proxy eller alternativ kilde
  (kan re-probe); skjemafeil → re-probe og rett kolonner; logikkfeil → rett koden.

### 7. Promptinnhold (`data-svar.ts`-konstanter, kilde-doc i `prompts/`)

- **Vitenskapelig kjerne**: utvidet versjon av `INFERENCE_STRATEGY_PYR` for
  fulle python/R-økosystemer: rå → justert sammenligning; konfundere valgt for
  akkurat dette spørsmålet; ÉN grov heterogenitets-oppdeling; DiD/event-study,
  IV, RDD, faste effekter, syntetisk kontroll (statsmodels/linearmodels/
  `fixest`); robuste/klyngede standardfeil; usikkerhet alltid rapportert;
  ærlighet om beskrivelse vs. årsak når identifikasjon ikke er mulig.
- **Kilderegler**: siter hver kilde med URL i script-kommentar; merk
  probe-verifisert vs. modellkunnskap; aldri fabrikker datasett-ID; finner du
  ingenting — si det, og foreslå omformuleringer.
- **Flerkilde og sammenslåing**: kombinasjon oppmuntres. Mønsteret: hver
  load-linje gir én DataFrame per variabel/serie; **første analysesteg er å
  merge/joine dem til ÉN analysedataframe** når det er mulig og nyttig (join
  på år, landkode, kommunenummer — nøkler fra registeret), i stedet for å
  analysere fragmenter hver for seg. Harmoniser koder (ISO-land, NUTS,
  kommunenummer) og enheter eksplisitt før join; kommenter join-type og
  hvorfor (inner/left), og sjekk radtall før/etter (stille rad-tap er en
  klassisk feilkilde).
- **Minimal-uttrekk**: hent variablene analysen trenger (variabel-nivå
  spørring via `table_metadata`), ikke hele tabeller — mindre data, klarere
  script, snillere mot kilde-API-ene.
- **Levering**: kilder som `# connect <base|register-id> as alias`, uttrekk
  som `# load <url|alias/sti> as navn` øverst (POST-API-er GET-innpakket
  via proxyen); flertrinns-kall som kode med kilde-URL i kommentar.
- **Språkregler per modus**: python (pandas/statsmodels/matplotlib …, micropip
  ved behov), r (tidyverse/fixest …, webr::install), duckdb (httpfs-lesing av
  CSV/parquet direkte i SQL; analyse i SQL eller hybrid med #py).

**Prompt-utviklingsplan** (samme metode som kode-svar-promptene):

1. **Kilde-dokument først**: `prompts/data-svar.md` som kildedok (mønsteret
   fra `kode-svar.md`) — TS-konstantene i `data-svar.ts` er render-målet.
   Blokkstruktur som i dag (SYSTEM_INTRO / INFERENCE / KILDEREGLER / …) så
   blokker kan gjenbrukes og diffes enkeltvis.
2. **Arv, ikke nyskriv**: start fra det som beviselig virker —
   `INFERENCE_STRATEGY_PYR` (utvides), `VISUALIZATION_RULES`-tankegangen,
   språk-preamblene. Nye blokker skrives kun for det som er genuint nytt
   (kilderegler, discovery-fasing, connect/load-levering, flerkilde-merge).
3. **Evalsett-drevet iterasjon**: hver promptendring kjøres mot evalsettet
   (~10 spørsmål, se Testing) før deploy; feilmønstre fra evalene og fra
   reparasjonsrunder i bruk omsettes til nye promptregler eller
   register-quirks — samme loop som «levende kunnskapsbase».
4. **Cache-disiplin**: registeret + regelblokkene renderes byte-stabilt inn i
   cached system-prefiks (mønsteret fra `buildCachedPrefix`); per-spørsmål
   innhold (spørsmål, tool-resultater, repair) ligger i user-turns så
   prefikset cacher på tvers av forespørsler.
5. **Endringslogg i kildedok**: daterte endringsnotater øverst i
   `prompts/data-svar.md` (som i `kode-svar.md`) så prompt-historikken er
   sporbar og porterbar.

## Feilhåndtering

- Tool-feil (nede kilde-API, timeout) → modellen fortsetter med andre kilder;
  progress-linja viser feilen kort.
- Tomt discovery-resultat etter budsjettet → ærlig «fant ikke data»-svar med
  hva som ble søkt og forslag til omformulering. Ingen fabrikkering.
- Proxy-avslag (privat IP, for stor fil) → tydelig feiltekst som repair-runden
  kan reagere på.
- 3 feilede reparasjonsrunder → svaret leveres med feilbeskrivelse og siste
  script, merket som ikke-kjørende.

## Testing

- `_lib/tools/*.test.ts`: adaptere mot fixture-svar (PxWeb/Eurostat/WB/OECD/
  CKAN), probe-skjemautledning (CSV/JSON-stat), SSRF-vern (private IP-er,
  redirects, størrelsestak) — samme mønster som eksisterende `*.test.ts`.
- `_lib/anthropic`-loop: enhetstest med mock-modell (tool-kall → svar).
- Evalsett: ~10 realistiske spørsmål (norsk + internasjonalt, én- og
  flerkilde) sjekket for: fant verifisert kilde, scriptet kjører, kildene er
  reelle. Kjøres manuelt/halvautomatisk ved promptendringer.

## Utenfor scope (nå)

- Åpning for ikke-admin-brukere (krever kost-/misbruksvurdering av proxy og
  tool-loop; repair kan da gjøres knappstyrt).
- Automatisk promotering av funne kilder inn i registeret.
- Microdata som én av kildene i Web-modus (mulig senere: #micro-bro).
- Caching av probe-/katalogresultater på tvers av forespørsler.
