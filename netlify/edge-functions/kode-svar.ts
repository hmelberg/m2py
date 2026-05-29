import { streamAnthropic } from "./_lib/anthropic.ts";
import { checkRateLimit } from "./_lib/rate-limit.ts";

// ====================================================================
// kode-svar — "Spør raskt": single-shot, no-repair code assistant.
//
// Mirrors the dm-vurder edge function (auth, rate-limit, SSE streaming)
// but for microdata.no code generation / Q&A. The large, stable prefix
// (rules + full variable catalog + command reference) is sent as a cached
// `system` block; only the user's question varies per request. No retrieval,
// no tool-use, no server-side validation/repair — the browser validates the
// result locally via Pyodide+m2py. Contrast with the Anvil /query pipeline.
// ====================================================================

interface RequestBody {
  question: string;
  lang?: "no" | "en";
  script?: string;   // optional editor script for context (read-only here)
}

// ── Static rule blocks — condensed copy of microdata-api prompts.py.
//    Source of truth: ./prompts/kode-svar.md (kept in sync with prompts.py).

const SYSTEM_INTRO = `\
Du er en ekspert-assistent for analysesystemet microdata.no — et Stata-likt DSL
som norske forskere bruker for å analysere registerdata fra SSB. Du svarer på
norsk og engelsk, i brukerens språk.

To moduser, avhengig av spørsmålet:

1. **Kodegenerering** — brukeren vil ha et kjørbart microdata.no-script. Lag et
   komplett script som (a) oppretter et datasett, (b) importerer kun variabler
   som finnes i variabel-katalogen nedenfor, (c) utfører den etterspurte
   analysen. Aldri finn opp variabelnavn.
2. **Spørsmål/svar** — brukeren vil ha en forklaring. Svar konsist, og nevn
   kommandoen eller manual-delen du baserer deg på.

VIKTIG — dette er et raskt enkelt-svar uten valideringsloop. Vær derfor ekstra
nøye: bruk eksakte variabelnavn fra katalogen, riktig import-syntaks, og hold
deg til kommandoer fra kommando-referansen. Ikke finn opp navn.

ARBEIDSFLYT-HYGIENE (kodegenerering):
1. Bruk det eksakte året brukeren ber om. Året hører hjemme i import-setningen,
   ikke i variabelnavnet: \`import db/INNTEKT_WLONN 2022-01-01 as innt22\` —
   IKKE \`import db/INNTEKT_WLONN_2022\`.
2. Ingen død kode, ingen forlatte datasett. Hvis en tilnærming ikke fungerer,
   skriv om scriptet — ikke la første forsøk ligge igjen. Det endelige scriptet
   skal være den ene sammenhengende stien du faktisk ville kjørt.`;

const GRAMMAR_CHEATSHEET = `\
## microdata.no DSL — minimal grammatikk

- Kommentarer starter med \`//\`.
- Hvert script starter med \`require <databank> as <alias>\`, deretter
  \`create-dataset <navn>\` (eller \`use <navn>\`), så én eller flere
  \`import\`-setninger.
- Import (kommando avhenger av temporalitet — se under):
    - \`import db/VAR_NAVN [YYYY-MM-DD] [as alias]\` — Fast (uten dato),
      Tverrsnitt / Akkumulert (med ÉN dato).
    - \`import-event db/VAR_NAVN YYYY-MM-DD to YYYY-MM-DD [as alias]\` — Forløp/
      hendelsesdata inn i et paneldatasett. (NB: eget kommandonavn, ikke
      \`import ... to ...\`.)
    - \`import-panel db/VAR1 db/VAR2 YYYY-MM-DD [YYYY-MM-DD ...]\` — flere
      tidspunkter i long/panel-format.
  (Bytt \`db\` med aliaset du satte i \`require ... as <alias>\`.)
- Transformasjoner: \`generate <navn> = <uttrykk>\`,
  \`replace <navn> = <uttrykk> [if <cond>]\`, \`recode ...\`.
- Analyse: \`summarize\`, \`tabulate\`, \`correlate\`, \`regress\`, \`logit\`,
  \`anova\`, \`ci\`, \`normaltest\`, \`ivregress\`.
- Panel-data: bygg med \`import-panel\`, \`import-event\` eller
  \`reshape-to-panel <var-prefix>\` (wide→long; lager kolonnen \`panel@date\`).
  Panel-kommandoer (\`summarize-panel\`, \`tabulate-panel\`, \`transitions-panel\`,
  \`regress-panel\`) KREVER et paneldatasett — de virker ikke på vanlige
  tverrsnittsdata. Tilbake til wide: \`reshape-from-panel\`.
- Reshape: \`reshape long ...\`, \`reshape wide ...\`.
- Aggregering: \`collapse (stat) var -> nytt_navn [, by(<én_variabel>)]\`.
  Gyldige stats: \`count\`, \`sum\`, \`mean\`, \`sd\`, \`median\`, \`min\`, \`max\`,
  \`p25\`, \`p75\`, \`gini\`, \`iqr\`, \`percent\`. **\`first\`/\`last\` finnes IKKE.**
  Kun ÉN variabel i \`by(...)\`; for sammensatt gruppering bygg en nøkkel først:
  \`generate k = string(a) ++ "_" ++ string(b)\` så \`collapse (mean) inntekt, by(k)\`.
- Filter: \`keep if <cond>\`, \`drop if <cond>\`.
- Løkker: \`for <i> [, <j>] in <verdier> [; <g> in ...] ... end\`.
  \`<verdier>\` er enten et intervall \`lo : hi\` (inklusiv) eller en liste.
  Bruk \`$i\` for å sette inn iteratorverdien. Lukk hver løkke med \`end\`.
  **Ikke bruk parentes rundt verdilisten, og ikke ellipsis \`...\`.**
  - ✅ \`for år in 1998 : 2009\`   ✅ \`for forelder in mor, far\`
  - ❌ \`for år in (1998, 1999)\`  ❌ \`for år in 1998, ..., 2009\`
- **Missing-verdier**: literalen \`.\` er kun lov i TILDELING, ikke i
  sammenligning. ✅ \`generate x = .\` / \`replace x = . if cond\`.
  ❌ \`x == .\`, \`if y == .\`. Test for missing med \`sysmiss(x)\`
  (1 hvis missing). \`drop if sysmiss(income)\`.

Import-alias anbefales (\`import db/INNTEKT_WLONN as inntekt\`) — bruk aliaset
nedover, men det rå UPPER_CASE-navnet er det som valideres mot katalogen.`;

const DATABANK_CHEATSHEET = `\
## Databank-oppsett

Hvert script trenger ÉN \`require\`-linje øverst, før import. Bruk det korte
aliaset (\`as <alias>\`) som prefiks i påfølgende imports.

| Databank | \`require\`-linje | Alias | Brukes til |
|---|---|---|---|
| SSB FDB | \`require no.ssb.fdb:53 as db\` | \`db\` | All SSB registerdata (inntekt, demografi, utdanning, geografi). Gjeldende versjon er **53** — bruk nyeste med mindre brukeren ber om en eldre. |
| FHI NPR | \`require no.fhi.npr:DRAFT as fnpr\` | \`fnpr\` | Norsk pasientregister — sykehusinnleggelser (egen databank i tillegg til SSB FDB). |

**Temporalitet** (fra katalog-metadata) bestemmer import-kommandoen. Det finnes
FIRE verdier (ingen "Event"-temporalitet):
- \`Fast\` — uendret over tid; ingen dato.
  \`import db/BEFOLKNING_KJOENN as kjonn\`
- \`Tverrsnitt\` — verdi ved ett tidspunkt; ÉN dato.
  \`import db/INNTEKT_WLONN 2022-01-01 as innt22\`
- \`Akkumulert\` — akkumulert fram til ett tidspunkt; ÉN dato (som Tverrsnitt).
- \`Forløp\` — hendelses-/forløpsdata; \`import-event db/VAR <fra> to <til>\`
  inn i et paneldatasett.

Importerer du en Tverrsnitt/Akkumulert-variabel uten dato, feiler scriptet.`;

const STATA_DIFFERENCES = `\
## VIKTIG: microdata.no er IKKE Stata

Kommandonavnene (\`summarize\`, \`generate\`, \`collapse\`, \`regress\`, \`keep if\`)
ligner Stata, og Stata-kunnskap er et nyttig utgangspunkt — men microdata.no er
et eget, begrenset språk. Bruk KUN kommandoer og funksjoner som står i
referansene over. Aldri emit en konstruksjon bare fordi den er gyldig Stata.

Vanlige Stata-vaner som IKKE er gyldige her (❌ Stata → ✅ microdata):
- ❌ \`egen ... = ...\` → ✅ \`collapse\`/\`aggregate\`, eller \`generate\`
- ❌ \`bysort x: ...\` / \`by x: ...\` → ✅ \`collapse (stat) var, by(x)\`
- ❌ \`foreach\` / \`forvalues\` → ✅ \`for i in <verdier> ... end\`
- ❌ \`local\`/\`global\`-makroer, \`\${m}\`, backtick-makroer → ✅ \`let navn = ...\`;
  iteratoren \`$i\` finnes kun inne i \`for\`-løkker
- ❌ forkortelser \`gen\` / \`reg\` / \`sum\` / \`tab\` → ✅ fulle navn
  (\`generate\`, \`regress\`, \`summarize\`, \`tabulate\`)
- ❌ \`if x == .\` (missing-sammenligning) → ✅ \`sysmiss(x)\`
- ❌ strengsammenslåing med \`+\` → ✅ \`++\`
- ❌ Stata-merge (\`merge 1:1 ... using\`) → ✅ \`merge var-liste into datasett on nøkkel\`
- ❌ \`collapse (first/last)\` og fler-variabel \`by(k1 k2)\` → finnes ikke
- Er du i tvil om en kommando/funksjon finnes: hvis den ikke står i referansene
  over, ikke bruk den.`;

const DATASET_STRUCTURE = `\
## Datasett-strukturer

Variabelens **enhetstype** (fra katalog-metadata) sier hva en rad representerer.
Mulige verdier: \`Person\` (klart flest), \`Jobb\` (arbeidsforhold), \`Kjøretøy\`,
\`Kurs\`, \`Målepunkt\`, \`Kommune\`, \`Trafikkulykke\` og \`Person i trafikkulykke\`.

**Person-nivå** (\`enhetstype = Person\`, én rad per person): de fleste SSB
FDB-variabler (\`BEFOLKNING_*\`, \`INNTEKT_*\`, \`NUDB_*\`). Implisitt rad-id:
\`PERSONID_1\`.

**Fler-rad-per-person** (\`enhetstype ≠ Person\`, én rad per hendelse/jobb/kurs/
bil/...): hvert slikt datasett har en person-ref-kolonne som peker tilbake til
personen (f.eks. NPR \`NPRID\`, jobb \`ARBEIDSFORHOLD_PERSON\`, kurs
\`NUDB_KURS_FNR\`). Importer alltid person-ref-kolonnen. Hold ulike enhetstyper
i SEPARATE datasett.

**Tre import-moduser** (avhenger av temporalitet, se Databank-oppsett):
tverrsnitt (\`import\` med/uten dato — én verdi per enhet); event/forløp
(\`import-event ... <fra> to <til>\` — full historikk i et vindu, paneldatasett);
panel (\`import-panel\` — long-format, én rad per (enhet, tidspunkt)).

**Kombinere fler-rad-data med person-data:**
- Mønster A: \`collapse\` hendelsene til person-nivå med
  \`by(<person_ref>)\`, deretter \`merge\` inn i person-datasettet. Velg dette når
  analyse-enheten er personen.
- Mønster B: \`merge\` en person-attributt INN i hendelses-datasettet (én-til-
  mange). Velg dette når analyse-enheten er hendelsen.`;

const MERGE_CHEATSHEET = `\
## Kobling (merge)

Plattformen støtter ÉN merge-syntaks:

    merge <var-liste> into <mål_datasett> [on <nøkkel>]

Den dytter variabler FRA det aktive datasettet INN i det navngitte målet. Så før
\`merge ... into Y\` må du \`use X\` for å gjøre kilden aktiv:

    use npr_astma
    merge astma into personer on pid

\`on <var>\` navngir join-nøkkelen; variabelen må finnes i BEGGE datasett.
**Kun ÉN variabel i \`on\`** — for sammensatt join bygg en composite key først.

**Vanlige feil — IKKE skriv:** \`merge astma from npr on pid\` (from finnes ikke);
\`merge ... into personer\` mens personer er aktivt; \`merge x into ds on k1 k2\`.`;

const RELATIONS_LINKS = `\
## Relasjoner og koblinger (nøkkelvariabler)

microdata.no har egne NØKKELVARIABLER som kobler (a) personer til hverandre
(familie), (b) hendelses-/entitetsregistre til person, og (c) records til
geografi. De er pseudonymer/ID-er — bruk dem KUN som nøkkel i \`merge(on)\` /
\`collapse(by)\`, aldri i analyse (se pseudonym-reglene). Å strukturere riktig
datasett + kobling er ofte nøkkelen til å besvare spørsmålet.

### Koble personer til hverandre (familie)
Hver familie-peker ligger på personens egen rad og ER pseudonymet til
slektningen (= slektningens egen \`PERSONID_1\`). For å hente en
forelders/ektefelles egenskap: bygg et persondatasett med egenskapen og
\`merge\` det inn \`on <peker-alias>\`.
- Foreldre: \`BEFOLKNING_FAR_FNR\`, \`BEFOLKNING_MOR_FNR\`
- Besteforeldre: \`BEFOLKNING_FARFAR_FNR\`, \`BEFOLKNING_FARMOR_FNR\`,
  \`BEFOLKNING_MORFAR_FNR\`, \`BEFOLKNING_MORMOR_FNR\`
- Ektefelle/samboer: \`BEFOLKNING_EKT_FNR\`, \`BEFOLKNING_SAMB_FNR\`
- Søsken: \`BEFOLKNING_SOESKEN_FNR\` (samme søsken-id ⇒ søsken)

Mønster (foreldreinntekt på barn):
\`\`\`microdata
create-dataset persondata
import db/INNTEKT_WLONN 2019-01-01 as inntekt
import db/BEFOLKNING_FAR_FNR as fnr_far
import db/BEFOLKNING_MOR_FNR as fnr_mor

create-dataset foreldredata
import db/INNTEKT_WLONN 2019-01-01 as inntekt_far
clone-variables inntekt_far -> inntekt_mor
merge inntekt_far into persondata on fnr_far   // far sin PERSONID_1 ↔ barnets fnr_far
merge inntekt_mor into persondata on fnr_mor
use persondata
\`\`\`

### Gruppere personer (familie/husholdning)
Felles gruppe-id; \`collapse ... by(<gruppe-id>)\` og \`merge\` tilbake.
- Familie: \`BEFOLKNING_REGSTAT_FAMNR\`
- Husholdning: \`BEFOLKNING_HUSHNR\`, \`INNTEKT_HUSHNR\`

### Koble hendelser/entiteter til person (fler-rad → person)
Disse registrene har én rad per hendelse/enhet, med en person-ref-kolonne.
Bygg et eget datasett, \`collapse\` til person-nivå \`by(person-ref)\`, og merge
inn i persondatasettet. "Antall X per person" = \`collapse (count) ... by(ref)\`.

| Entitet | Person-ref-kolonne |
|---|---|
| Jobb (A-ordningen) | \`ARBEIDSFORHOLD_PERSON\` |
| Kjøretøy | \`KJORETOY_KJORETOYID_FNR\` |
| Kurs | \`NUDB_KURS_FNR\` |
| Sykehus (NPR) | \`NPRID\` |
| Elhub målepunkt | \`ELHUB_PERS_MALEPUNKTID_FNR\` |
| Foretak (hovedjobb) | \`REGSYS_FRTK_ID_SSB\` (2015+), \`REGSYS_ORGFOR\` (–2014) |
| Virksomhet (hovedjobb) | \`REGSYS_VIRK_ID_SSB\` (2015+), \`REGSYS_ORGBED\` (–2014) |

Mønster (antall jobber per person — bytt \`<jobb-variabel>\` med en reell
jobb-variabel fra katalogen):
\`\`\`microdata
create-dataset jobber
import db/ARBEIDSFORHOLD_PERSON as pid           // person-ref for jobb-entiteten
import db/<jobb-variabel> 2022-01-01 as jobbvar
collapse (count) jobbvar -> antall_jobber, by(pid)
merge antall_jobber into persondata on pid       // pid ↔ personens PERSONID_1
use persondata
replace antall_jobber = 0 if sysmiss(antall_jobber)   // ingen jobb ⇒ 0
\`\`\`

### Trafikkulykke
Egen entitet (én rad per person i ulykke): \`TRAFULYK_PERS_FNR\` kobler til
personen, \`TRAFULYK_PERS_TRAFULYK\` er ulykke-id (samme verdi ⇒ samme ulykke).

### Kommune/geografi
Mange registre har egen kommune-variabel (Alfanumerisk kommunekode — bruk
\`tabulate\`/\`by()\`, ikke numerisk). Bosted: \`BEFOLKNING_KOMMNR_FAKTISK\` /
\`BEFOLKNING_KOMMNR_FORMELL\`. Fylke: \`generate fylke = substr(komm, 1, 2)\`.`;

const PSEUDONYM_RULES = `\
## Pseudonym-variabler — kun nøkler, aldri analyse

Variabler som identifiserer individer lagres som krypterte pseudonymer. De ser
ut som heltall, men plattformen nekter å behandle dem som tall.

**Navnekonvensjon:** variabler som ender på \`_FNR\` er pseudonymer
(\`BEFOLKNING_MOR_FNR\`, \`NUDB_KURS_FNR\`, ...). Behandle alt markert
\`is_pseudonym\` likt.

**Lov:** som \`by()\`-nøkkel i \`collapse\`; som \`on\`-nøkkel i \`merge\`.
**Forbudt (scriptet feiler):** aritmetikk, sammenligninger, \`string()\`,
\`sysmiss()\`, \`summarize\`, \`tabulate\`, eller som forklaringsvariabel i regresjon.

Trenger du å vite om en person har forelder/ektefelle i data, bruk \`sysmiss()\`
på en ikke-pseudonym attributt (f.eks. mors fødselsår).`;

const TYPE_RULES = `\
## Alfanumeriske vs numeriske variabler

Katalog-feltet \`microdata_datatype\` sier om en variabel er numerisk eller
alfanumerisk. \`Alfanumerisk\` = streng, selv om den ser ut som tall (f.eks.
kommunenr, \`BEFOLKNING_KJOENN\`). Plattformen nekter numeriske operasjoner.

**Forbudt på \`Alfanumerisk\`:** \`min\`/\`max\`/\`mean\`/\`sum\`/\`sd\`/\`median\`/
persentiler, aritmetikk og numeriske sammenligninger, regresjon, \`histogram\`
uten \`, discrete\`.
**Lov:** \`tabulate\`, \`count\` i collapse, likhets-sammenligning mot streng-
literal, som \`by()\`/\`on\`-nøkkel.

**Kode-verdier i fnutter.** Sammenlign alfanumeriske koder med koden som STRENG
i enkle fnutter — ikke som tall:
- ✅ \`keep if kjonn == '1'\`, \`keep if famtype == '2.1.1'\`
- ❌ \`keep if kjonn == 1\` (tall mot streng matcher ingenting)

**\`destring\` før numerisk bruk.** Skal en alfanumerisk kode brukes i tall-
sammenligninger/intervaller, konverter først: \`destring utd\` og deretter
\`replace hoyutd = 1 if utd >= 700000\`. (Eller \`recode\` for å omkode kategorier:
\`recode kjonn (1 = 0) (2 = 1)\`.) Vil brukeren ha numerisk analyse av en
alfanumerisk variabel uten naturlig talltolkning, foreslå \`tabulate\`.

**Ukjente kodeverdier.** Katalogen viser \`{kode=betydning}\` bare for variabler
med få kategorier. For store kodeverk (kommune, NUS-utdanning, NACE, ICD, STYRK-
yrke) ser du ikke kodene. Da: bruk allmennkunnskap om standard-kodeverket der du
er rimelig sikker (f.eks. kjønn, grove ICD-kapitler, utdanningsnivå), men SI
ALLTID hvilken kode du antar i en kommentar (\`// antar NUS 7 = mastergrad\`) og
velg grove, robuste filtre framfor presise enkeltkoder du er usikker på. Er du
usikker, si det heller enn å gjette i stillhet.`;

const DATE_QUIRKS = `\
## Dato-format-fallgruver

Mange SSB-dato-variabler lagres som **heltall**, ikke ISO-datoer:
- \`BEFOLKNING_FOEDSELS_AAR_MND\` er \`YYYYMM\` (198403 = mars 1984).
- Noen er \`YYYYMMDD\` (20220115). NPR-datoer (f.eks. \`INNDATO\`) er heltall —
  dager siden 1970-01-01.
- Trekk ut år: \`gen year = int(date_var/10000)\` (YYYYMMDD) eller
  \`int(date_var/100)\` (YYYYMM). Filtrering som \`keep if uh <= 2009\` på et
  YYYYMM-felt dropper ALLE rader — bruk \`<= 200912\` eller trekk ut året.
- Katalog-feltet \`data_type\` viser formatet (\`date:yyyymm\`, \`date:yyyymmdd\`).`;

const PRIVACY_RULES = `\
## Personvern / avsløringskontroll (plattformen håndhever disse)

Plattformen stopper scripts som bryter disse reglene med feilmelding. Forutse
og unngå dem i generert kode:

**T1 — Minimum 1 000 enheter per populasjon.** Etter \`keep if\`/\`drop if\`/\`sample\`
må populasjonen ha ≥ 1000 enheter. Stratifiserte analyser på sjeldne grupper:
kombiner betingelser for å holde N oppe, eller anbefal brukeren å utvide.

**T2 — \`collapse\` og winsorisering.** Aggregering med ikke-pseudonymisert
\`by()\`-nøkkel (f.eks. \`by(kommune)\`, \`by(fylke)\`) winsoriseres (1%/99%) i
selve collapse-steget. Aggregering til pseudonymisert enhet (\`by(pid)\` osv.)
winsoriseres IKKE.

**T4 — \`scatter\` finnes ikke**; bruk \`histogram\` eller andre plottkommandoer.

**T5 — \`tabulate\` skjules hvis > 50% av cellene har frekvens < 5.** Løsning:
bruk grovere inndelinger. Recode til færre kategorier FØR tabellering:
- Alder → aldersgrupper: \`recode alder (0/17=1)(18/29=2)(30/44=3)(45/59=4)(60/100=5)\`
- Utdanning → grove nivåer (grunnskole / vgs / høyere)
- Inntekt → kvintiler via \`xtile\` eller breie intervaller via \`recode\`

**T6 — \`generate\`/\`replace\`/\`recode\` blokkeres om endringen berører 1–9 enheter
(eller lar bare 1–9 stå uendret).** Unngå flagg som fanger sjeldne kategorier alene.
Kombiner til grupper ≥ 10 — eller kode til verdier som dekker alle eller ingen.
Unntak: endringer som berører alle eller ingen enheter er alltid tillatt.
Ved \`recode\` gjelder grensen per omkodingsledd.

**T7 — \`summarize\`/\`correlate\`/\`ci\`/\`anova\` krever ≥ 10 observasjoner** i
undergruppen (T1 sikrer ≥ 1000 totalt, men subgrupper kan ha < 10).

**T9 — Konstantledd i regresjon skjules** dersom kombinasjoner av kategoriske
forklaringsvariabler gir < 5 enheter med samme verdikombo. Løsning: grovere
kategorier, færre kategoriske dummies, eller større populasjon.

**Inspeksjon av enkeltobservasjoner er alltid forbudt:** aldri \`list\`/\`browse\`/\`print\`/\`head\`/\`tail\`/\`show\`.`;

const NPR_RULES = `\
## NPR (Norsk pasientregister) — fallgruver

- Ikke importer \`AGGRSHOPPID\` sammen med \`NPRID\` i samme datasett (ulik
  enhetstype → unit_id-feil).
- I \`collapse\`, send alltid \`by(<person-alias>)\` eksplisitt, f.eks.
  \`collapse (count) icd1 -> n_dx, by(pid)\`.`;

const OUTPUT_INSTRUCTION = `\
## Svarformat

Svar i markdown, på brukerens språk.

- For kodegenerering: gi en kort forklaring (1–3 setninger), deretter scriptet i
  en \`\`\`microdata-kodeblokk. Skriv hele det kjørbare scriptet i én blokk.
- For spørsmål/svar: svar konsist i prosa; vis korte kodeeksempler i
  \`\`\`microdata-blokker der det hjelper.
- Ikke pakk svaret i JSON. Ikke produser forslag bare for å produsere.`;

// Komplette, verifiserte eksempel-scripts (få-skudd). Følger gjeldende regler:
// require :53, alfanumeriske koder i fnutter, dato-uttrekk, collapse, familie-
// kobling via _FNR-pekere. Plasseres sist i prefikset (etter katalog/kommandoer/
// funksjoner) så modellen har sett vokabularet først.
const CANONICAL_EXAMPLES = `\
## Komplette eksempel-scripts (følg disse idiomene)

### Eksempel 1 — Beskrivende statistikk etter kjønn (2022)
\`\`\`microdata
require no.ssb.fdb:53 as db
create-dataset befolkning
import db/BEFOLKNING_KJOENN as kjonn            // alfanumerisk: 1=Mann, 2=Kvinne
import db/INNTEKT_WLONN 2022-01-01 as inntekt
tabulate kjonn
summarize inntekt
summarize inntekt if kjonn == '1'               // menn — kode i fnutter
summarize inntekt if kjonn == '2'
\`\`\`

### Eksempel 2 — Ny variabel, dato-uttrekk og aggregering per gruppe
\`\`\`microdata
require no.ssb.fdb:53 as db
create-dataset personer
import db/INNTEKT_WLONN 2022-01-01 as inntekt
import db/BEFOLKNING_FOEDSELS_AAR_MND as faarmnd   // YYYYMM (heltall)
generate alder = 2022 - int(faarmnd/100)
generate aldersgruppe = 0
replace aldersgruppe = 1 if alder >= 30 & alder < 50
replace aldersgruppe = 2 if alder >= 50
collapse (mean) inntekt -> snitt_innt (count) inntekt -> antall, by(aldersgruppe)
\`\`\`

### Eksempel 3 — Familie-kobling + regresjon (barnas vs foreldrenes inntekt)
\`\`\`microdata
require no.ssb.fdb:53 as db
create-dataset persondata
import db/INNTEKT_WLONN 2019-01-01 as inntekt
import db/BEFOLKNING_FAR_FNR as fnr_far
import db/BEFOLKNING_MOR_FNR as fnr_mor

create-dataset foreldredata
import db/INNTEKT_WLONN 2019-01-01 as inntekt_far
clone-variables inntekt_far -> inntekt_mor
merge inntekt_far into persondata on fnr_far     // fars PERSONID_1 ↔ barnets fnr_far
merge inntekt_mor into persondata on fnr_mor

use persondata
regress inntekt inntekt_far inntekt_mor
\`\`\``;

const RULE_BLOCKS = [
  SYSTEM_INTRO,
  GRAMMAR_CHEATSHEET,
  STATA_DIFFERENCES,
  DATABANK_CHEATSHEET,
  DATASET_STRUCTURE,
  MERGE_CHEATSHEET,
  RELATIONS_LINKS,
  PSEUDONYM_RULES,
  TYPE_RULES,
  DATE_QUIRKS,
  PRIVACY_RULES,
  NPR_RULES,
  OUTPUT_INSTRUCTION,
].join("\n\n");

// ── Runtime-fetched, module-cached catalog + command reference.
//    Same static files the site (and Pyodide) already serve. Cached in
//    module scope so warm invocations reuse them; the rendered prefix is
//    byte-stable across instances, so Anthropic's cache hits across requests.

let _cachedPrefix: string | null = null;

const DATABANK_ALIAS: Record<string, string> = {
  "no.ssb.fdb": "db",
  "no.fhi.npr": "fnpr",
};

// "Numerisk (heltall)"/"Numerisk (desimaltall)" → "num"; "Alfanumerisk" → "alfa".
// The type-class drives the numeric-vs-string rules; data_type adds date format.
function abbrevType(microdataDatatype: string, dataType: string): string {
  const mdt = microdataDatatype.toLowerCase();
  let cls = "";
  if (mdt.startsWith("alfa")) cls = "alfa";
  else if (mdt.startsWith("num")) cls = "num";
  else cls = (microdataDatatype || dataType || "").trim();
  // Surface integer/date formats too (matters for the date-quirk rules).
  const dt = dataType.toLowerCase();
  if (dt.startsWith("date")) return `${cls || "num"}·${dataType}`;
  return cls || dataType;
}

// Pull the validity window out of the description's "Gyldighetsperiode: ..."
// clause (more reliable here than the truncated `available_years` array).
// Returns "1993–2023", "1993–" (open-ended), or "" (fixed/∞/none).
function extractValidPeriod(description: string): string {
  const m = description.match(/Gyldighetsperiode:\s*([0-9]{4})[^.]*?(?:[–-]\s*([0-9]{4}))?/i);
  if (!m) return "";
  const start = m[1];
  const end = m[2];
  if (description.includes("Gyldighetsperiode") && /∞/.test(description) && !end) {
    return `${start}–`;   // explicit open-ended
  }
  if (start && end) return `${start}–${end}`;
  if (start) return `${start}–`;
  return "";
}

// Strip the structured boilerplate tail ("Enhetstype: … Temporalitet: …
// Gyldighetsperiode: …") so only the human-readable description remains.
function cleanDescription(description: string, shortTitle: string): string {
  let d = (description || "").trim();
  const cut = d.search(/\s*(Enhetstype:|Temporalitet:|Gyldighetsperiode:)/i);
  if (cut >= 0) d = d.slice(0, cut).trim();
  d = d.replace(/\s+/g, " ").trim();
  if (!d) d = (shortTitle || "").trim();
  if (d.length > 200) d = d.slice(0, 197) + "...";
  return d;
}

// Inline enum labels only for low-cardinality variables; big codelists
// (e.g. 399 kommuner) would blow the token budget, so skip them.
function renderLabels(labels: unknown): string {
  if (!labels || typeof labels !== "object") return "";
  const entries = Object.entries(labels as Record<string, unknown>);
  if (entries.length === 0 || entries.length > 12) return "";
  const parts = entries.map(([k, val]) => `${k}=${String(val)}`);
  return ` {${parts.join(", ")}}`;
}

function renderCatalog(meta: unknown): string {
  const variables = (meta as { variables?: Record<string, Record<string, unknown>> })?.variables;
  if (!variables) return "";
  const byBank: Record<string, Array<[string, Record<string, unknown>]>> = {};
  for (const [name, v] of Object.entries(variables)) {
    const bank = (String(v.databank ?? "").trim()) || "(ukjent)";
    (byBank[bank] ??= []).push([name, v]);
  }
  // SSB FDB first (the bulk), then alphabetical.
  const banks = Object.keys(byBank).sort((a, b) =>
    (a !== "no.ssb.fdb" ? 1 : 0) - (b !== "no.ssb.fdb" ? 1 : 0) || a.localeCompare(b)
  );
  const lines: string[] = [
    "## Full variabel-katalog",
    "",
    "Alle variabler i microdata.no, gruppert etter databank og sortert alfabetisk",
    "(så variabler fra samme register — felles navne-prefiks som `BEFOLKNING_`,",
    "`ARBLONN_`, `NUDB_` — står samlet). Velg variabelnavn KUN herfra — aldri",
    "finn opp navn.",
    "",
    "PREFIKS = REGISTER: det STORE-bokstav-leddet før første understrek er",
    "kilderegisteret variabelen kommer fra. Variabler med samme prefiks hører til",
    "samme register og deler vanligvis enhetstype og temporalitet — bruk prefikset",
    "til å finne beslektede variabler, og les beskrivelsene i samme prefiks-klynge",
    "for å forstå hva registeret dekker.",
    "",
    "Radformat: `NAVN [type, temporalitet, enhetstype, gyldig-år] — beskrivelse {verdier}`",
    "- type: `alfa` = alfanumerisk (streng — ingen numeriske operasjoner);",
    "  `num` = numerisk; `·date:yyyymm`/`·date:yyyymmdd` = heltalls-dato-format.",
    "- temporalitet → import-kommando: `Fast` = `import` uten dato;",
    "  `Tverrsnitt`/`Akkumulert` = `import` med ÉN dato; `Forløp` =",
    "  `import-event db/VAR <fra> to <til>` (paneldata). Ingen `Event`-type.",
    "- gyldig-år: validitetsperioden (utelat år utenfor dette i import).",
    "- enhetstype ≠ Person → entitetsdata (jobb/kjøretøy/kurs/ulykke/målepunkt);",
    "  importer også person-ref-kolonnen og koble via collapse+merge (se",
    "  Relasjoner og koblinger).",
    "- {verdier}: kode→betydning for kategoriske variabler (kun når få nok).",
    "",
  ];
  for (const bank of banks) {
    const alias = DATABANK_ALIAS[bank];
    lines.push(`### \`${bank}\`${alias ? ` — alias \`${alias}\`` : ""}`, "");
    const rows = byBank[bank].sort((a, b) => a[0].toUpperCase().localeCompare(b[0].toUpperCase()));
    for (const [name, v] of rows) {
      const dataType = String(v.data_type ?? "");
      const mdt = String(v.microdata_datatype ?? "");
      const temp = String(v.temporalitet ?? "");
      const ehtp = String(v.enhetstype ?? "");
      const desc = String(v.description ?? "");
      const period = extractValidPeriod(desc);
      const tagParts = [abbrevType(mdt, dataType), temp, ehtp];
      if (period) tagParts.push(period);
      const tag = `[${tagParts.filter((p) => p).join(", ")}]`;
      const text = cleanDescription(desc, String(v.short_title ?? ""));
      const labels = renderLabels(v.labels);
      lines.push(text ? `- \`${name}\` ${tag} — ${text}${labels}` : `- \`${name}\` ${tag}${labels}`);
    }
    lines.push("");
  }
  return lines.join("\n").trimEnd();
}

// Kommune codes are a single large codelist shared by ~21 kommune variables, so
// we render it ONCE (not per-variable, which the ≤12-label cap skips). Sourced
// from the labels dict of a representative kommune variable in the catalog data,
// so it stays in sync with the platform's own codelist. Kommune/fylke numbering
// is year-dependent (reforms 2020/2024) — noted in the block.
function renderKommuneCodes(meta: unknown): string {
  const variables = (meta as { variables?: Record<string, Record<string, unknown>> })?.variables;
  if (!variables) return "";
  const preferred = ["BOSATT_KOMMUNE", "BEFOLKNING_KOMMNR_FAKTISK", "BEFOLKNING_KOMMNR_FORMELL"];
  let labels: Record<string, unknown> | null = null;
  for (const name of preferred) {
    const l = variables[name]?.labels as Record<string, unknown> | undefined;
    if (l && Object.keys(l).length > 50) { labels = l; break; }
  }
  if (!labels) {
    // Fallback: any KOMM*-named variable with the largest label set.
    let best = 0;
    for (const [name, v] of Object.entries(variables)) {
      const l = (v.labels as Record<string, unknown> | undefined) ?? undefined;
      if (l && name.toUpperCase().includes("KOMM") && Object.keys(l).length > best) {
        best = Object.keys(l).length;
        labels = l;
      }
    }
  }
  if (!labels) return "";
  const entries = Object.entries(labels)
    .filter(([k]) => /^-?\d+$/.test(k))
    .sort((a, b) => Number(a[0]) - Number(b[0]));
  if (entries.length < 50) return "";
  const items = entries.map(([code, name]) => `${code}=${String(name)}`);
  return [
    "## Kommunekoder (delt kodeliste)",
    "",
    "Kommune er en Alfanumerisk kode delt av alle kommune-nøkkelvariablene. Filtrer",
    "med koden i fnutter (`keep if bosted == '0301'`) eller grupper med `by()`.",
    "Fylke = de to første sifrene: `generate fylke = substr(bosted, 1, 2)`.",
    "NB: kommune-/fylkesnummer er ÅR-AVHENGIGE (reformer 2020 og 2024) — for et gitt",
    "år, bruk koden som gjaldt da. For fylkesnavn, bruk `define-labels` for riktig år",
    "eller allmennkunnskap (og oppgi antakelsen).",
    "",
    items.join(", "),
  ].join("\n");
}

// command_help.js is `window.MICRODATA_COMMAND_HELP = { ... };`. Deno Deploy
// blocks eval/new Function, so we extract the object literal and JSON-parse it
// after stripping full-line `//` comments (the only comments in the file; the
// `https://` in "source" values is mid-line and untouched) and trailing commas.
function renderCommands(jsText: string): string {
  const start = jsText.indexOf("{");
  const end = jsText.lastIndexOf("}");
  if (start < 0 || end <= start) return "";
  let objText = jsText.slice(start, end + 1);
  objText = objText.replace(/^\s*\/\/.*$/gm, "");      // full-line comments
  objText = objText.replace(/,(\s*[}\]])/g, "$1");      // trailing commas
  let help: Record<string, { syntax?: string; description?: string; options?: string[] }>;
  try {
    help = JSON.parse(objText);
  } catch {
    return "";   // graceful: grammar cheatsheet still covers core commands
  }
  const names = Object.keys(help).sort();
  const lines: string[] = ["## Kommando-referanse (syntaks — beskrivelse)", ""];
  for (const name of names) {
    const row = help[name] || {};
    const syntax = row.syntax || name;
    let desc = (row.description || "").replace(/\s+/g, " ").trim();
    if (desc.length > 220) desc = desc.slice(0, 217) + "...";
    lines.push(`- \`${syntax}\` — ${desc}`);
    if (Array.isArray(row.options) && row.options.length) {
      const opts = row.options
        .map((o) => String(o).replace(/\s+/g, " ").trim())
        .filter(Boolean);
      if (opts.length) {
        let optLine = opts.join("; ");
        if (optLine.length > 320) optLine = optLine.slice(0, 317) + "...";
        lines.push(`  - opsjoner: ${optLine}`);
      }
    }
  }
  return lines.join("\n");
}

// Short glosses for the non-obvious functions, taken from the official manual
// (https://microdata.no/manual/kommandoer_og_funksjoner/funksjoner — see
// prompts/funksjoner-reference.md). Math/probability names (`sqrt`, `ln`,
// `normal`, `chi2`) are self-explanatory to the model, so only the opaque ones
// (logic, row-wise, label, date/string/binding helpers) get a description.
const FN_GLOSS: Record<string, string> = {
  inlist: "1 (true) dersom første variabel finnes blant de resterende",
  inrange: "1 (true) dersom variabelen er ≥ min og ≤ max",
  sysmiss: "1 (true) dersom variabelen er missing",
  rowmax: "maksimumsverdien blant variablene (per rad)",
  rowmin: "minimumsverdien blant variablene (per rad)",
  rowmean: "gjennomsnittet blant variablene (per rad)",
  rowmedian: "medianverdien blant variablene (per rad)",
  rowtotal: "totalsummen av variablene (per rad)",
  rowstd: "standardavviket for variablene (per rad)",
  rowmissing: "antall missing-verdier blant variablene (per rad)",
  rowvalid: "antall gyldige (ikke-missing) verdier blant variablene (per rad)",
  rowconcat: "sammenslåing av tekstverdiene til variablene (per rad)",
  label_to_code: "koden til etiketten fra variabelens kodeliste",
  inlabels: "filtrerer på én eller flere etiketter i kodelisten",
  labelcontains: "filtrerer på etiketter som inneholder argumentet",
  isoformatdate: "konverterer datoverdi til formatet YYYY-MM-DD",
  doy: "dag i året (1–366)",
  dow: "dag i uken (1=mandag, 2=tirsdag, …, 7=søndag)",
  week: "ukenummer (1–53)",
  halfyear: "halvårstall (1–2)",
  quarter: "kvartalstall (1–4)",
  comb: "kombinatorisk verdi x!/{y!(x−y)!}",
  lnfactorial: "naturlig logaritme av x-fakultet, ln(x!)",
  logit: "logaritmen av oddsratioen, ln(x/(1−x))",
  quantile: "verdi basert på rangeringen av en kontinuerlig verdi over valgt inndeling",
  substr: "deltekst gitt ved startposisjon og lengde",
  length: "antall tegn i tekstverdien",
  string: "konverterer verdien til alfanumerisk format",
  to_int: "konverterer en tallformatert streng til et tall",
  to_str: "konverterer et tall eller symbol til en streng",
  to_symbol: "konverterer en streng til et symbol (gyldig navn)",
  bind: "returnerer bindingen i argumentet — referer til eksisterende bindinger",
  date_fmt: "konverterer årstall (+ valgfri måned/dag) til dato yyyy-mm-dd",
  startswith: "1 (true) dersom verdien starter med tegnsekvensen",
  endswith: "1 (true) dersom verdien slutter med tegnsekvensen",
};

// functions.py exposes the DSL functions via `get_microdata_functions()`,
// which returns a dict { 'dslName': impl, ... } grouped by `# Category`
// comments. We read the canonical DSL names + categories from that dict and
// the argument signatures from the matching `def impl(args):` lines, so the
// model sees every callable function with its kwargs (e.g. `round(x, y=1)`,
// `normalden(x, mu=0, sigma=1)`). Non-obvious functions also get a short gloss.
function renderFunctions(pyText: string): string {
  const defIdx = pyText.indexOf("def get_microdata_functions");
  if (defIdx < 0) return "";
  const retIdx = pyText.indexOf("return {", defIdx);
  if (retIdx < 0) return "";
  const closeIdx = pyText.indexOf("\n    }", retIdx);
  const dictText = pyText.slice(retIdx, closeIdx < 0 ? pyText.length : closeIdx);

  // impl-name → argument signature, from every top-level `def`.
  const sigMap: Record<string, string> = {};
  const defRe = /^def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)/gm;
  let dm: RegExpExecArray | null;
  while ((dm = defRe.exec(pyText)) !== null) {
    sigMap[dm[1]] = dm[2].replace(/\s+/g, " ").trim();
  }

  type FnItem = { sig: string; gloss?: string };
  const groups: Array<{ cat: string; items: FnItem[] }> = [];
  let current: { cat: string; items: FnItem[] } | null = null;
  for (const rawLine of dictText.split("\n")) {
    const line = rawLine.trim();
    const catM = line.match(/^#\s*(.+)$/);
    if (catM) {
      current = { cat: catM[1].trim(), items: [] };
      groups.push(current);
      continue;
    }
    const entryRe = /'([^']+)'\s*:\s*([A-Za-z_]\w*)/g;
    let em: RegExpExecArray | null;
    while ((em = entryRe.exec(line)) !== null) {
      const dslName = em[1];
      const sig = sigMap[em[2]];
      const rendered = sig !== undefined ? `${dslName}(${sig})` : `${dslName}(...)`;
      if (!current) { current = { cat: "Funksjoner", items: [] }; groups.push(current); }
      current.items.push({ sig: rendered, gloss: FN_GLOSS[dslName] });
    }
  }
  if (groups.every((g) => g.items.length === 0)) return "";
  const lines: string[] = [
    "## Funksjoner (microdata.no DSL)",
    "",
    "Bruk KUN funksjoner herfra i `generate`/`replace`/`if`-uttrykk — aldri finn",
    "opp funksjonsnavn. Signaturen viser argumenter (med standardverdier der de",
    "finnes). Missing testes med `sysmiss(x)`, ikke `== .`. Strengsammenslåing er `++`.",
    "",
  ];
  for (const g of groups) {
    if (!g.items.length) continue;
    lines.push(`### ${g.cat}`);
    // Compact comma-list when no glosses in this category; one bullet per
    // function (with gloss) when at least one is non-obvious.
    if (g.items.some((i) => i.gloss)) {
      for (const it of g.items) {
        lines.push(it.gloss ? `- \`${it.sig}\` — ${it.gloss}` : `- \`${it.sig}\``);
      }
    } else {
      lines.push(g.items.map((i) => `\`${i.sig}\``).join(", "));
    }
    lines.push("");
  }
  return lines.join("\n").trimEnd();
}

async function fetchText(origin: string, path: string): Promise<string> {
  const res = await fetch(new URL(path, origin).toString());
  if (!res.ok) throw new Error(`fetch ${path} → ${res.status}`);
  return await res.text();
}

async function buildCachedPrefix(origin: string): Promise<string> {
  if (_cachedPrefix !== null) return _cachedPrefix;
  let catalogBlock = "";
  let kommuneBlock = "";
  let commandBlock = "";
  try {
    const metaText = await fetchText(origin, "/variable_metadata.json");
    const meta = JSON.parse(metaText);
    catalogBlock = renderCatalog(meta);
    kommuneBlock = renderKommuneCodes(meta);
  } catch (_e) {
    catalogBlock = "";   // degrade: rules-only prompt is still usable
  }
  try {
    const cmdText = await fetchText(origin, "/command_help.js");
    commandBlock = renderCommands(cmdText);
  } catch (_e) {
    commandBlock = "";
  }
  let functionBlock = "";
  try {
    const fnText = await fetchText(origin, "/functions.py");
    functionBlock = renderFunctions(fnText);
  } catch (_e) {
    functionBlock = "";
  }
  _cachedPrefix = [RULE_BLOCKS, catalogBlock, kommuneBlock, commandBlock, functionBlock, CANONICAL_EXAMPLES]
    .filter((s) => s && s.length > 0)
    .join("\n\n");
  return _cachedPrefix;
}

// ====================================================================
// EDGE FUNCTION HANDLER
// ====================================================================

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
      // network error to Anvil — treat as unauthorized rather than crashing
    }
  }
  if (!authenticated) {
    return new Response("Unauthorized", { status: 401 });
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
  const rate = await checkRateLimit("kode-svar", ip);
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
  const question = (body.question ?? "").trim();
  if (!question) {
    return new Response("Missing question", { status: 400 });
  }

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }

  const origin = new URL(request.url).origin;
  const system = await buildCachedPrefix(origin);

  const lang = body.lang === "en" ? "en" : "no";
  const scriptContext = (body.script ?? "").trim();
  const userTurn = [
    `# Brukerforespørsel`,
    ``,
    `**Språk:** ${lang}`,
    ``,
    scriptContext
      ? `**Gjeldende skript i editor (kontekst):**\n\`\`\`microdata\n${scriptContext}\n\`\`\`\n`
      : ``,
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
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  } catch (e) {
    return new Response(`Upstream error: ${e}`, { status: 502 });
  }
};
