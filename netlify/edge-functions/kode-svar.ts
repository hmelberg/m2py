import { streamAnthropic } from "./_lib/anthropic.ts";
import { extractByokKey, gate, upstreamErrorResponse } from "./_lib/auth.ts";
import { abbrevType, cleanDescription, extractValidPeriod, renderLabels } from "./_lib/catalog-format.ts";

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
    - \`import db/VAR_NAVN [YYYY-MM-DD] [as alias] [, opsjoner]\` — Fast (uten dato),
      Tverrsnitt / Akkumulert (med ÉN dato). Opsjoner etter komma:
      \`outer_join\` (full union — ta med enheter som mangler i datasettet),
      \`inner_join\` (kun enheter i begge), \`values(kode, …)\` (kun gitte
      kodeverdier), \`values_from(datasett)\` (kun enheter i et annet datasett).
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
  **KRITISK navnekrav for \`reshape-to-panel\`:** de wide variablene MÅ hete
  \`<prefiks><tall>\` der suffikset er tall/dato (blir \`panel@date\`-verdien) —
  f.eks. \`lonn2014\`, \`lonn2018\` for \`reshape-to-panel lonn\`. Bokstav-suffiks
  som \`lonn_pre\`/\`lonn_post\` MATCHER IKKE og gir feil. Importer derfor med
  års-suffiks med én gang: \`import db/INNTEKT_WLONN 2014-12-31 as lonn2014\`,
  \`import db/INNTEKT_WLONN 2018-12-31 as lonn2018\` (eller \`rename\` til slike
  navn før reshape). Etterpå er \`panel@date\` 2014/2018 — bruk den i \`if\`:
  \`replace post = 1 if panel@date == 2018\`. (Alternativ uten reshape:
  \`import-panel db/INNTEKT_WLONN 2014-12-31 2018-12-31\` lager long-format direkte.)
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
- \`Tverrsnitt\` — verdi ved ett tidspunkt; ÉN dato (snapshot-datoen i taggen).
  \`import db/INNTEKT_WBRUTTOFORM 2022-01-01 as form22\`
- \`Akkumulert\` — sum akkumulert fram til datoen; ÉN dato. Bruk årsslutt for
  helårstall: \`import db/INNTEKT_WLONN 2022-12-31 as lonn22\`.
- \`Forløp\` — hendelses-/forløpsdata. To former, BEGGE krever dato:
  - tilstand/verdi ved ÉN dato (vanligst for kontekstvariabler som utdanning,
    bosted, sivilstand): \`import db/NUDB_BU 2020-08-31 as utd\`
  - hele forløpet som panel: \`import-event db/VAR <fra> to <til>\`

ALDRI \`import db/VAR\` UTEN dato for andre enn Fast-variabler. Importerer du en
Tverrsnitt-, Akkumulert- ELLER Forløp-variabel uten dato, FEILER scriptet
(«… krever en importdato»). **Sjekk alltid katalog-taggen for hver variabel** —
bare \`[fast]\` skal være uten dato; \`[tverrsnitt]\`, \`[akkumulert]\` og
\`[forløp]\` krever alltid en dato innenfor variabelens gyldighetsperiode.

**Importrekkefølge — start med en KOMPLETT variabel.** microdata.no left-joiner
hver import på det aktive datasettet, så den FØRSTE importen definerer
populasjonen. Mange registervariabler (særlig inntekt, lønn, stønader og
hendelser) er MISSING for store deler av befolkningen — f.eks. har lønn missing
for barn, eldre og alle uten arbeidsforhold (kan være > 70 % missing totalt).
Starter du med en slik variabel, blir hele datasettet et lite, skjevt utvalg.
Begynn derfor alltid med en hel-populasjons-variabel som anker — typisk
\`BEFOLKNING_KJOENN\` eller \`BEFOLKNING_FOEDSELS_AAR_MND\` (begge \`Fast\`, dekker
alle) — og importer inntekt/stønader/hendelser ETTERPÅ. Da beholder du full
populasjon, og missing i de glisne variablene blir synlig som missing (test med
\`sysmiss(x)\`) i stedet for å forsvinne ut av utvalget.

**\`outer_join\` når en variabel kan ha enheter som ikke er i datasettet.** Standard
import er left join: bare enheter som alt finnes i datasettet beholdes. Vil du ta
med enheter som har gyldig verdi for den NYE variabelen men ikke for den første,
bruk \`, outer_join\` — da blir det full union (de nye enhetene får missing på de
tidligere variablene). \`, inner_join\` gir motsatt kun snittet (enheter i begge).
Anker-først-regelen er likevel hovedrådet; \`outer_join\` er for de tilfellene der
du bevisst vil utvide populasjonen.

**Ikke gjett temporalitet ut fra navnet.** Et navn som ser ut som en konstant
identifikator kan likevel være Tverrsnitt. Relasjoner som ikke endres er Fast
(\`BEFOLKNING_FAR_FNR\`, \`BEFOLKNING_MOR_FNR\` → ingen dato), men relasjoner som
kan endre seg over tid er Tverrsnitt og KREVER dato: \`BEFOLKNING_EKT_FNR\`
(ektefelle), \`BEFOLKNING_SAMB_FNR\` (samboer), bosted, arbeidsgiver. Les
katalog-taggen for nettopp den variabelen — ikke kopier dato-bruk fra et
beslektet eksempel.`;

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

**Variabelomfang.** Etter \`use <datasett>\` er bare variablene i det aktive
datasettet tilgjengelige. Variabler fra andre datasett må merges inn FØR de
kan brukes — å referere til dem direkte er en kjøretidsfeil.

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
## Merge og flere datasett

### Det aktive datasettet
Hver kommando jobber mot ÉN dataset — det aktive. \`create-dataset X\` gjør X
aktivt; \`use Y\` bytter til Y. \`import\`, \`generate\`, \`summarize\`,
\`regress\` osv. ser KUN variabler i det aktive. En variabel som ligger i et
annet datasett kan IKKE refereres direkte — det er en kjøretidsfeil.

**Konsekvens:** Trenger du flere variabler fra samme register på samme
enhetstype, importér dem rett inn i samme datasett. Ikke splitt i flere
datasett bare for å merge dem igjen.

### merge-syntaksen

    merge <var-liste> into <mål> [on <nøkkel>]

Merge DYTTER fra det aktive datasettet INN i \`<mål>\`. Du kan ikke "pulle"
fra mål-siden ved å være i målet. Hjelpemiddel: \`merge X into Y\` betyr "fra
her (aktiv) inn til Y med X".

\`on <var>\` — felles nøkkel som finnes i BEGGE datasett. Bare ÉN variabel
i \`on\`; for sammensatt join bygg en composite key først.

### Standardsekvens for merge

    use kilde              // gjør datasettet SOM HAR variabelen aktivt
    merge x into mål on k  // dyttes inn i mål
    use mål                // bytt tilbake for å analysere mål videre

### Den vanligste merge-feilen
Å skrive \`merge x into mål\` mens \`x\` ligger i et ANNET datasett enn det
aktive. Da finnes ikke \`x\` å dytte. Symptom: feilmelding om at variabelen
ikke finnes.

**Sjekkliste FØR hver \`merge\`:**
1. Hvilket datasett HAR variabelen jeg merger? → \`use\` det først.
2. Hva er målet? → \`into <det>\`.
3. Hva er den felles nøkkelen? → \`on <nøkkel>\` (én variabel, finnes i begge).
4. Trenger jeg å analysere målet etterpå? → \`use <mål>\` etter merge.

**Andre vanlige feil — IKKE skriv:**
- \`merge x from kilde\` (\`from\` finnes ikke i syntaksen)
- \`merge x into mål\` når \`x\` ikke er i aktiv (samme feil som over)
- \`merge x into mål on k1 k2\` (kun én nøkkel i \`on\`)

### Når du faktisk trenger flere datasett
- Ulike enhetstyper (Person vs Jobb vs Hendelse) — hold separat, collapse til
  enhetstypen du analyserer på, så merge.
- Variabler om relaterte personer (foreldre/barn/ektefelle) — hent variablene
  for "den andre personen" i et eget datasett, så merge på relasjonsnøkkelen.

### clone-units — start ny gren fra samme populasjon
Når du vil analysere en delpopulasjon med ANDRE variabler enn originalen, uten
å ødelegge originalen:

    use stor_populasjon
    keep if alder >= 65
    clone-units stor_populasjon eldre  // 'eldre' = bare ID-er for filtrert pop
    use eldre
    import db/HELSE_KAT as helsekat    // andre variabler for samme personer

### clone-dataset — snapshot før destruktiv operasjon
\`collapse\`, \`keep if\`, \`drop if\` endrer det aktive datasettet permanent.
Vil du beholde originalen:

    clone-dataset persondata persondata_kopi
    collapse (mean) inntekt, by(kommune)  // kopien er urørt

### collapse vs aggregate (lett å forveksle)
- \`collapse (stat) var -> navn, by(grp)\` ERSTATTER det aktive datasettet med
  én rad per by-gruppe. Bare aggregerte kolonner + by-variabelen overlever.
  \`->\` navngir utdata-VARIABELEN, ikke et nytt datasett.
- \`aggregate (stat) var -> navn, by(grp)\` BEVARER alle rader og legger til en
  ny kolonne med aggregatet broadcast til alle radene i gruppen.

Trenger du både et aggregert datasett OG originalen: \`clone-dataset\` først,
deretter \`collapse\`.`;

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
import db/BEFOLKNING_FAR_FNR as fnr_far   // Fast → ingen dato (EKT_FNR/SAMB_FNR er derimot Tverrsnitt → krever dato)
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
## Nøkkelvariabler — kun for kobling, aldri analyse

Plattformen avviser bruk av nøkkelvariabler i analyse/transformasjons-
kommandoer med feilmeldingen *"Variabelen X er en nøkkelvariabel og kan
ikke brukes i analyser og transformasjoner"*. Tre kilder til nøkkelstatus:

### 1. Importerte pseudonymer
Variabler som identifiserer individer er krypterte pseudonymer. Ser ut som
heltall, men er ikke tall. Navnekonvensjon: ender på \`_FNR\`
(\`BEFOLKNING_MOR_FNR\`, \`NUDB_KURS_FNR\`, ...). Også alt markert
\`is_pseudonym\` i katalogen.

### 2. by-variabelen i et collapsed datasett
Etter \`collapse (stat) v -> w, by(K)\` blir K rad-identifikatoren i det nye
datasettet og arver nøkkelstatus. Også \`rename K NYTT_NAVN\` etterpå
endrer ikke statusen — den nye kolonnen er fortsatt nøkkel.

### 3. Eneste kolonne etter clone-units
\`clone-units A B\` lager B med kun populasjons-ID-en. Den kolonnen ER
nøkkelen.

### Tillatt
- som \`by()\`-nøkkel i \`collapse\` / \`aggregate\`
- som \`on\`-nøkkel i \`merge\`
- som radidentifikator i sin egen rolle

### Forbudt (scriptet feiler)
- aritmetikk, sammenligninger, \`string()\`, \`sysmiss()\`
- \`summarize\`, \`tabulate\`, \`generate\` med nøkkelen i uttrykket
- som forklaringsvariabel i regresjon

### Vanlige feilmønstre
- \`tabulate K\` etter \`collapse ..., by(K)\` — K er nå nøkkel, ikke en
  kategori. Vil du beskrive K-fordelingen, gjør det FØR \`collapse\`, eller
  i et ikke-collapsed søsterdatasett (\`clone-dataset\` først).
- \`generate ny = K + 1\` eller \`replace ny = K\` — pseudonymer kan ikke
  brukes i uttrykk.
- \`tabulate <variabel som er klonet/renamed fra en nøkkel>\` — sjekk
  hvordan variabelen ble skapt; nøkkelstatusen følger med.

### Sjekke om en person har en relasjon/hendelse
Bruk \`sysmiss()\` på en ikke-pseudonym attributt for den relaterte enheten
(f.eks. mors fødselsår), ikke selve FNR-en.`;

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
usikker, si det heller enn å gjette i stillhet.

**Foretrekk numerisk kode fremfor etikett.** Bruk \`destring\` + numerisk
sammenligning som standard. \`inlabels()\` er kun aktuelt når etikettene er
eksplisitt vist i katalogen (≤12 kategorier) og koden er ukjent. Gjett
aldri etiketttekst. Legg alltid til en kommentar med etiketten slik at
det fremgår hva koden betyr:
\`keep if kjonn == 1  // 1 = Mann\``;

const DATE_QUIRKS = `\
## Dato-format-fallgruver

Mange SSB-dato-variabler lagres som **heltall**, ikke ISO-datoer:
- \`BEFOLKNING_FOEDSELS_AAR_MND\` er \`YYYYMM\` (198403 = mars 1984).
- Noen er \`YYYYMMDD\` (20220115). NPR-datoer (f.eks. \`INNDATO\`) er heltall —
  dager siden 1970-01-01.
- Trekk ut år: \`gen year = int(date_var/10000)\` (YYYYMMDD) eller
  \`int(date_var/100)\` (YYYYMM). Filtrering som \`keep if uh <= 2009\` på et
  YYYYMM-felt dropper ALLE rader — bruk \`<= 200912\` eller trekk ut året.
- Katalog-feltet \`data_type\` viser formatet (\`date:yyyymm\`, \`date:yyyymmdd\`).
**Gyldighetsperiode / gyldige importdatoer.** For \`Tverrsnitt\`- og
\`Akkumulert\`-variabler viser katalog-taggen de FAKTISKE gyldige importdatoene
som \`<første>…<siste>\` (f.eks. \`2015-02-16…2025-02-16\`). Plattformen godtar
KUN datoer fra dette årlige rutenettet: samme måned-dag som vist, ett år om
gangen, fra første til siste år. Regler:
- Bruk nøyaktig den viste måned-dagen. Gjett ALDRI \`-01-01\`, \`-11-01\` eller en
  annen dag — \`2022-11-01\` mot rutenettet \`…-02-16\` gir
  «… har ingen gyldig importdato».
- Hold året innenfor \`[første … siste]\`. Vil brukeren ha «nyeste» tall, bruk
  siste viste år; ALDRI et år etter siste (f.eks. \`2022\` når siste er \`2014\`).
- Mangler taggen måned-dag (bart år-spenn som \`1993–2023\`, eller \`Fast\`/∞),
  valideres ikke dato på samme måte — velg da et år i spennet.
- Er du i tvil, kopier den FØRSTE eller SISTE viste datoen ordrett; begge er
  garantert gyldige.

**Avsluttede og versjonerte variabler — velg riktig årgang.** Samme begrep finnes
ofte i FLERE varianter med ULIKE gyldighetsperioder: en eldre er avsluttet, en
nyere (eller en med annet register-prefiks) har tatt over. Variantene kan dessuten ha ulik ENHETSTYPE. Eksempel for «sektor»:
\`REGSYS_FRTK_SEKTOR_2014\` er **Person** men dekker bare 2015–2019;
\`ARBLONN_FRTK_SEKTOR_2014\` er **Jobb** og dekker 2015–2025. Et årstall i navnet
(\`_2014\`) er en KLASSIFISERINGS-versjon, IKKE sluttåret — les alltid den faktiske
gyldighetsperioden OG enhetstypen i taggen.
- Velg den varianten hvis gyldighetsperiode DEKKER året brukeren vil ha. Trenger
  du 2022-tall, finn varianten som er gyldig i 2022 — ikke en avsluttet variabel.
- Velg riktig ENHETSTYPE: i et Person-datasett, foretrekk Person-varianten
  (\`import\` direkte). For sektor i 2019 → \`REGSYS_FRTK_SEKTOR_2014 2019-11-16\`
  (Person). En Jobb-variabel kan IKKE importeres direkte i et Person-datasett —
  den må inn i et eget Jobb-datasett, collapse til én verdi per person, så merge.
- Hvis Person-varianten er avsluttet og bare en Jobb-variant dekker det ønskede
  året (f.eks. sektor i 2022 → kun \`ARBLONN_FRTK_SEKTOR_2014\`, Jobb), bygg det
  via eget Jobb-datasett + collapse + merge — ikke ved å tvinge den inn i
  person-datasettet eller velge et år utenfor gyldighetsområdet.
- Tving ALDRI en dato inn i en avsluttet variabel (gir «ingen gyldig importdato»,
  og i static-modus en hard feil). Ser du at siste gyldige år er før det ønskede,
  bytt variabel i stedet for å bytte år.

**Tverrsnitt vs. Akkumulert.** \`Tverrsnitt\` = øyeblikksbilde på den viste
måned-dagen. \`Akkumulert\` = sum akkumulert t.o.m. datoen, og taggen viser
ÅRSSLUTT-datoen (f.eks. \`1993-12-31…2023-12-31\`): bruk \`<år>-12-31\` for
helårstall — inntekt opptjent i år Y er \`Y-12-31\`. (\`Y-01-01\` godtas også, men
er året før; foretrekk årsslutt.) Kuttes serien før årsslutt viser taggen den
faktiske slutt-dagen (\`…-09-30\`) — bruk den.`;

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
import db/BEFOLKNING_FAR_FNR as fnr_far   // Fast → ingen dato (EKT_FNR/SAMB_FNR er derimot Tverrsnitt → krever dato)
import db/BEFOLKNING_MOR_FNR as fnr_mor

create-dataset foreldredata
import db/INNTEKT_WLONN 2019-01-01 as inntekt_far
clone-variables inntekt_far -> inntekt_mor
merge inntekt_far into persondata on fnr_far     // fars PERSONID_1 ↔ barnets fnr_far
merge inntekt_mor into persondata on fnr_mor

use persondata
regress inntekt inntekt_far inntekt_mor
\`\`\``;

const INFERENCE_RULES = `\
## Inferens og kausal analyse

Når spørsmålet gjelder **effekt, årsak, virkning eller sammenheng**: still deg i rollen som ekspert på kvasi-eksperimentelle metoder i observasjonsdata. Velg den enkleste metoden som identifikasjonsstrategien tillater, og oppgi den sentrale antakelsen.

**Analytisk strategi — tenk gjennom dette FØR metodevalg:**
- **Konfunderende variabler.** En rå forskjell er sjelden svaret. Kjør først den enkle sammenligningen, deretter en justert modell som kontrollerer for de bakenforliggende faktorene som er RELEVANTE FOR NETTOPP DETTE SPØRSMÅLET og som finnes i katalogen — ikke en fast liste. (Alder, kjønn og utdanning er bare mulige eksempler; for mange spørsmål er noen av dem irrelevante.) Vis hvordan estimatet flytter seg fra rått til justert, og si i en kommentar hvilke du kontrollerer for og hvorfor.
- **Heterogenitet.** Effekter varierer ofte mellom grupper. Ta med ÉN grov, godt befolket oppdeling der det er naturlig (interaksjon \`a##b\` eller analyse innen undergrupper) — men hold gruppene grove nok til å overleve personvernreglene (≥ 1000 i populasjon, unngå små celler; se personvern-blokken). Foreslå dypere oppdelinger i prosa heller enn å sprenge utvalget.
- **Variabelvalg og avtrykk i registeret.** Den mest åpenbare variabelen er ikke alltid den beste — verken konseptuelt eller statistisk. Spør: hvilket avtrykk setter fenomenet i registrene? Den direkte etiketterte variabelen kan (a) være konseptuelt forurenset (f.eks. «arv» som også fanger gaver) eller (b) dekke få personer. Et konstruert mål bygd fra beslektede variabler — datoer, hendelser, familiepekere, tilhørende stønader (f.eks. «året etter siste forelders død» som arvetidspunkt, eller sykdomsrelaterte ytelser som signal på sykdom) — kan være både renere og dekke langt flere. Vei det etiketterte målet mot et indirekte/proxy-mål på BÅDE gyldighet og antall enheter, og oppgi proxyens sentrale antakelse.

**Faktor- og interaksjonssyntaks** (regress, regress-panel, logit, probit, poisson, negative-binomial, mlogit):
- \`i.var\` — kategorisk → dummyer (referansekategori droppes). \`c.var\` — behandle kategorisk som kontinuerlig.
- \`a#b\` — interaksjon; \`a##b\` — full kryssing (hovedeffekter + interaksjon). \`c.x#c.y\` for to metriske.
- \`if\`-uttrykk støttes: \`regress y x if inntekt > 500000\`.
- Vanlige opsjoner (etter komma): \`robust\`, \`cluster(v)\`, \`level(90)\`, \`noconstant\`, \`control(...)\`.

**OLS:** \`regress depvar varliste\` — også \`ov\`/\`vif\`/\`het_bp\` (diagnostikk), \`standardize\`, \`margins()\`. Predikering: \`regress-predict ..., predicted(p) residuals(r) cooksd(c)\`.

**Faste effekter / panel** (krever paneldatasett — \`import-panel\`/\`import-event\`/\`reshape-to-panel\`):
- \`regress-panel depvar varliste\` — \`fe\` (standard), \`re\`, \`be\`, \`pooled\`. \`hausman depvar varliste\` velger FE vs RE (P<0.05 ⇒ FE). FE antar streng eksogenitet; fjerner all tidskonstant forveksling per enhet.

**Diff-in-diff:** \`regress-panel-diff depvar gruppe behandling [varliste]\` — \`gruppe\`=1 behandlingsgruppe/0 kontroll, \`behandling\`=1 fra og med behandlingstidspunkt/0 før. ATET = interaksjonskoeffisienten. Antar **parallelle trender**. (Ekvivalent: \`regress-panel depvar gruppe##behandling ..., pooled\`.)

**Instrumentvariabler:** \`ivregress depvar exog (endog = instrumenter) exog\` — f.eks. \`ivregress innt05 mann gift (formuehøy = alder)\`. Opsjoner: \`tsls\` (standard), \`liml\`, \`gmm\`, \`firststage\`, \`endog\`, \`overid\`. Sjekk førstetrinns-F (svakt instrument < ~10). Antar instrumentet **relevant og eksogent**.

**Regresjonsdiskontinuitet:** \`rdd depvar runvar [varliste]\` med \`cutoff(0)\`, \`polynomial(1)\`, \`fuzzy(treat_dummy)\`. Antar at enheter ikke kan manipulere seg presist over terskelen.

**Binært utfall:** \`logit\`/\`probit depvar varliste\` — \`or\` (oddsratio, logit), \`mfx(dydx)\`, \`margins(dummy)\`. **Telledata:** \`poisson\` (forventning≈varians) eller \`negative-binomial\` (overdispersjon); \`irr\` (rate-ratio), \`exposure(v)\`. **Nominelt >2 kat.:** \`mlogit\`. Alle har \`…-predict\` (\`probabilities()\`/\`predicted()\`/\`residuals()\`).

**Lønnsgap-dekomponering:** \`oaxaca depvar varliste by gruppevar\` (Blinder-Oaxaca). **Flernivå:** \`regress-mml depvar varliste by nivå2 [nivå1]\` (opptil 3 nivåer).

**Forløp/overlevelse:** \`cox hendelse varighet [varliste]\` (+ \`hazard\`), \`kaplan-meier\`, \`weibull\`.

**Visualisering:** \`coefplot\` etter regress/logit/probit/poisson.

Personvern (T9): regresjonskonstanten skjules hvis kategorikombinasjoner gir < 5 enheter — hold kategoriene grove.`;

const VISUALIZATION_RULES = `\
## Visualisering — vis resultater som figurer, ikke bare tall

Tall og figurer utfyller hverandre. Når et resultat egner seg grafisk, lag GJERNE
både tabellen/regresjonen OG en figur i samme script. Tilgjengelige plott (full
syntaks står i kommando-referansen — her er bare når du bør gripe til dem):
- \`barchart (stat) var [, over(grp) by(grp) stack horizontal]\` — grafisk versjon
  av \`tabulate\`/\`summarize\`. \`count\`/\`percent\` for kategoriske (kun ÉN variabel);
  \`mean\`/\`median\`/\`sum\`/\`min\`/\`max\`/\`sd\` for numeriske. \`over(grp)\` viser
  statistikken FORDELT på grupper — det naturlige verktøyet for å vise heterogenitet
  (f.eks. \`barchart (mean) lonn, over(kjonn)\`); \`over(a, b)\` krysser to grupper;
  \`stack\` komprimerer mange kategorier til én søyle per gruppe.
- \`boxplot var [, over(grp)]\` — fordeling/spredning per gruppe.
- \`histogram var [, discrete]\` — fordeling for én variabel (bruk \`, discrete\` for
  kategoriske). NB: \`scatter\` finnes IKKE (T4).
- \`coefplot <regresjon …>\` — koeffisienter med konfidensintervall etter
  regress/logit/probit/poisson.
- \`hexbin xvar yvar [, gridsize() groups()]\` — tetthet for to variabler.

Figurer følger de SAMME personvernreglene som tabeller (grove grupper, ingen små
celler). Ikke lag figurer bare for syns skyld — velg den som faktisk gjør
resultatet lettere å lese, og presenter helst tall og figur sammen.`;

const MISSING_VALUES = `\
## Missing-verdier — KRITISK for inntekt, trygd og stønader

Mange registervariabler er MISSING (ikke 0) for personer uten record i registeret:
inntekt er missing for dem uten den inntektstypen (barn, folk uten lønn osv.),
og trygd/stønad (\`uføregrad\`, dagpenger, pensjon …) er missing for ALLE som
ikke mottar ytelsen — der har et flertall missing og bare mottakerne en verdi.

**Regresjon og mange analyser ekskluderer hele enheten hvis NOEN variabel er
missing.** En variabel med mye missing som ikke kodes om, krymper derfor
analyse-utvalget dramatisk (regresjonen kjøres på et lite, skjevt utvalg). Tenk
alltid gjennom missing FØR du kjører \`regress\`/\`logit\`/\`correlate\`.

**Recode-mønstre (bruk \`sysmiss(x)\`):**
- Andel/dummy for en stønad — missing betyr «mottar ikke», så kod til 0:
  \`\`\`
  import db/UFOERP2011FDT_GRAD 2010-01-01 as uforegrad
  generate ufor = 1
  replace ufor = 0 if sysmiss(uforegrad)   // ufor = 1 for mottakere, 0 ellers
  \`\`\`
- Inntekt der nullinntekt skal telle med (ellers droppes alle med inntekt = 0):
  \`replace inntekt = 0 if sysmiss(inntekt)\`
- Vil du derimot BEHOLDE missing som «ikke relevant» (f.eks. uføregrad kun blant
  uføre), lar du den stå missing — men vær da klar over utvalgskrympingen over.

Velg bevisst per variabel: 0 (tell ikke-mottakere med) eller fortsatt missing
(analyser kun dem med gyldig verdi). Si fra i en kommentar hva du valgte og
hvorfor. Test alltid med \`sysmiss(x)\` — aldri \`x == .\` (ulovlig i sammenligning).`;

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
  INFERENCE_RULES,
  VISUALIZATION_RULES,
  MISSING_VALUES,
  NPR_RULES,
  OUTPUT_INSTRUCTION,
].join("\n\n");

// ── Runtime-fetched, module-cached catalog + command reference.
//    Same static files the site (and Pyodide) already serve. Cached in
//    module scope so warm invocations reuse them; the rendered prefix is
//    byte-stable across instances, so Anthropic's cache hits across requests.

export type GenMode = "microdata" | "python" | "r";

export function coerceMode(m: unknown): GenMode {
  return m === "python" || m === "r" ? m : "microdata";
}

const SYSTEM_INTRO_PY = `\
Du er en ekspert-assistent som skriver PYTHON-kode for å analysere norske
registerdata fra microdata.no. Du svarer på norsk og engelsk, i brukerens språk.
Data hentes fra microdata.no-variabler via en \`#micro\`-blokk (se under) og
analyseres med pandas/statsmodels osv. Lag et komplett, kjørbart script: (a) en
\`#micro\`-blokk som importerer KUN variabler som finnes i katalogen nedenfor
(aldri finn opp variabelnavn), (b) en \`#python\`-blokk som gjør analysen. Bruk
eksakte variabelnavn fra katalogen.`;

const SYSTEM_INTRO_R = `\
Du er en ekspert-assistent som skriver R-kode for å analysere norske registerdata
fra microdata.no. Du svarer på norsk og engelsk, i brukerens språk. Data hentes
fra microdata.no-variabler via en \`#micro\`-blokk (se under) og analyseres med
tidyverse/base R. Lag et komplett, kjørbart script: (a) en \`#micro\`-blokk som
importerer KUN variabler som finnes i katalogen nedenfor (aldri finn opp
variabelnavn), (b) en \`#r\`-blokk som gjør analysen. Bruk eksakte variabelnavn.`;

const LANG_PREAMBLE_PY = `\
## Python-miljø

Skriv idiomatisk Python. Forhåndslastet: pandas, numpy, scipy, statsmodels,
matplotlib, seaborn, plotly. Trenger du andre pakker, installer med
\`import micropip; await micropip.install("pakke")\`. Du står fritt til å velge
verktøy: pandas/statsmodels for analyse, matplotlib/seaborn/plotly for figurer.`;

const LANG_PREAMBLE_R = `\
## R-miljø

Skriv idiomatisk R. tidyverse (dplyr, ggplot2, tidyr, …) og base R er
tilgjengelig. Trenger du andre pakker, installer med \`webr::install("pakke")\`.
Du står fritt til å velge verktøy: dplyr/base for analyse, ggplot2 for figurer.`;

const MICRO_IMPORT_BRIDGE = `\
## Last microdata-data inn i Python/R (#micro-bro)

Registerdata hentes i en \`#micro\`-blokk med microdata.no sin import-syntaks, og
blir tilgjengelig som en DataFrame (Python) / data.frame (R):

\`\`\`
#micro
require no.ssb.fdb:53 as fd
create-dataset folk
import fd/BEFOLKNING_KJOENN as kjonn
import fd/INNTEKT_WLONN 2022-01-01 as inntekt

#python
folk.groupby("kjonn")["inntekt"].agg(["mean", "median", "count"])
\`\`\`

Regler:
- Datasett-navnet (\`folk\`) blir variabelen i Python/R; kolonnene er import-
  ALIASENE (\`kjonn\`, \`inntekt\`), ikke de rå variabelnavnene.
- Missing blir NaN (Python) / NA (R).
- Importér KUN i \`#micro\`-blokken; all bearbeiding/analyse skjer i
  \`#python\`/\`#r\`-blokken. Importér gjerne flere variabler i samme datasett og
  koble/filtrer videre i pandas/dplyr.
- Import-kommando avhenger av temporalitet (se Databank-oppsett): \`Fast\` uten
  dato, \`Tverrsnitt\`/\`Akkumulert\` med ÉN dato innenfor variabelens gyldige
  datoer. Feil dato gir importfeil — dette gjelder fortsatt i \`#micro\`.`;

const INFERENCE_STRATEGY_PYR = `\
## Analytisk strategi (effekt-/sammenligningsspørsmål)

- **Konfunderende variabler.** Vis først den enkle sammenligningen, deretter en
  justert modell (statsmodels \`ols\`/\`logit\` eller R \`lm\`/\`glm\`) som kontrollerer
  for de bakenforliggende faktorene som er RELEVANTE for nettopp dette spørsmålet
  og finnes i katalogen — ikke en fast liste. Vis hvordan estimatet flytter seg
  fra rått til justert.
- **Heterogenitet.** Effekter varierer mellom grupper; ta med ÉN grov, godt
  befolket oppdeling (interaksjon eller stratifisert analyse) der det er naturlig.
- **Variabelvalg og avtrykk i registeret.** Den mest åpenbare variabelen er ikke
  alltid den beste — verken konseptuelt eller for antall enheter. Vurder også
  indirekte/proxy-mål bygd fra datoer, hendelser, familiepekere eller stønader
  (f.eks. «året etter siste forelders død» som arvetidspunkt), og oppgi proxyens
  antakelse.`;

const OUTPUT_PY = `\
## Svarformat

Svar i markdown, på brukerens språk. Gi en kort forklaring (1–3 setninger),
deretter ÉN kjørbar kodeblokk med \`#micro\` (datainnlasting) etterfulgt av
\`#python\` (analysen), i en \`\`\`python-blokk. Bruk eksakte variabelnavn fra
katalogen. Presenter gjerne både tall og figur (matplotlib/seaborn/plotly). Ikke
pakk svaret i JSON.`;

const OUTPUT_R = `\
## Svarformat

Svar i markdown, på brukerens språk. Gi en kort forklaring (1–3 setninger),
deretter ÉN kjørbar kodeblokk med \`#micro\` (datainnlasting) etterfulgt av \`#r\`
(analysen), i en \`\`\`r-blokk. Bruk eksakte variabelnavn fra katalogen. Presenter
gjerne både tall og figur (ggplot2). Ikke pakk svaret i JSON.`;

// Shared data-knowledge blocks reused for Python/R (microdata-DSL analysis
// blocks are intentionally excluded; the #micro bridge + OUTPUT_* frame that
// only #micro is used for import and the analysis is pandas/R).
const PYR_SHARED_BLOCKS = [
  DATABANK_CHEATSHEET,
  DATASET_STRUCTURE,
  RELATIONS_LINKS,
  PSEUDONYM_RULES,
  TYPE_RULES,
  DATE_QUIRKS,
  PRIVACY_RULES,
  MISSING_VALUES,
  NPR_RULES,
  INFERENCE_STRATEGY_PYR,
];

interface PrefixParts {
  catalogBlock?: string;
  kommuneBlock?: string;
  commandBlock?: string;
  functionBlock?: string;
}

// Pure prefix assembly. microdata uses the exact legacy composition (byte-stable
// v1 parity). python/r use shared data blocks + language preamble + #micro bridge
// and omit the microdata command/function reference and analysis grammar.
export function assemblePrefix(mode: GenMode, parts: PrefixParts): string {
  const cat = parts.catalogBlock ?? "";
  const kom = parts.kommuneBlock ?? "";
  if (mode === "python" || mode === "r") {
    const isPy = mode === "python";
    const blocks = [
      isPy ? SYSTEM_INTRO_PY : SYSTEM_INTRO_R,
      isPy ? LANG_PREAMBLE_PY : LANG_PREAMBLE_R,
      MICRO_IMPORT_BRIDGE,
      ...PYR_SHARED_BLOCKS,
      isPy ? OUTPUT_PY : OUTPUT_R,
      cat,
      kom,
    ];
    return blocks.filter((s) => s && s.length > 0).join("\n\n");
  }
  // microdata (default) — identical to the legacy buildCachedPrefix join.
  return [RULE_BLOCKS, cat, kom, parts.commandBlock ?? "", parts.functionBlock ?? "", CANONICAL_EXAMPLES]
    .filter((s) => s && s.length > 0)
    .join("\n\n");
}

const _cachedPrefix: Record<GenMode, string | null> = { microdata: null, python: null, r: null };

const DATABANK_ALIAS: Record<string, string> = {
  "no.ssb.fdb": "db",
  "no.fhi.npr": "fnpr",
};

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
    "ARBEIDSMÅTE: katalogen er stor. Identifiser FØRST hvilke(t) register-prefiks",
    "(klynge) som er relevant for spørsmålet, les den klyngen nøye, og velg",
    "variabler derfra — i stedet for å skumme hele listen. Husk at den mest",
    "åpenbare variabelen ikke alltid er den beste; vurder også indirekte mål",
    "(datoer, hendelser, stønader, familiepekere) som fanger fenomenet.",
    "",
    "Radformat: `NAVN [type, temporalitet, enhetstype, gyldig-datoer] — beskrivelse {verdier}`",
    "- type: `alfa` = alfanumerisk (streng — ingen numeriske operasjoner);",
    "  `num` = numerisk; `·date:yyyymm`/`·date:yyyymmdd` = heltalls-dato-format.",
    "- temporalitet → import-kommando: `Fast` = `import` uten dato;",
    "  `Tverrsnitt`/`Akkumulert` = `import` med ÉN dato; `Forløp` =",
    "  `import-event db/VAR <fra> to <til>` (paneldata). Ingen `Event`-type.",
    "- gyldig-datoer vises som `<første>…<siste>` (med `…`):",
    "  • `Tverrsnitt`: de FAKTISKE gyldige importdatoene — et ÅRLIG øyeblikksbilde",
    "    på samme måned-dag som vist (f.eks. `2015-02-16…2025-02-16`). Importer",
    "    med `<år>-<måned-dag>`, år i intervallet. ALDRI en annen måned-dag (ikke",
    "    `-01-01`/`-11-01` når datoene viser `-02-16`) og ALDRI år utenfor",
    "    intervallet — begge gir kjøretidsfeil.",
    "  • `Akkumulert`: verdi akkumulert T.O.M. datoen. Taggen viser ÅRSSLUTT-datoen",
    "    (f.eks. `1993-12-31…2023-12-31` = helårstall; `…-09-30` for serier som",
    "    kuttes i Q3). Bruk `<år>-<årsslutt-måned-dag>` for hele årets sum — det",
    "    mest intuitive (inntekt for år Y = `Y-12-31`). `<år>-01-01` godtas også,",
    "    men er forrige års sum; foretrekk årsslutt-datoen.",
    "  • `Forløp`: hele gyldighetsvinduet for `import-event ... <fra> to <til>`",
    "    (endepunktene kan ha ulik måned-dag). Hold `<fra>`/`<til>` i vinduet.",
    "  • Bart år-spenn (`1993–2023`) eller `Fast`/∞: måned-dag valideres ikke;",
    "    velg en hvilken som helst dato i spennet.",
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
      const period = extractValidPeriod(desc, temp);
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
  if (start < 0) return "";
  // Filen inneholder et nr. 2 objekt (MICRODATA_FUNCTION_HELP) — brace-match
  // KUN det første objektet. lastIndexOf("}") ville spenne over begge og få
  // JSON.parse til å feile (→ tom kommando-referanse).
  let depth = 0, end = -1, instr: string | null = null, esc = false;
  for (let k = start; k < jsText.length; k++) {
    const ch = jsText[k];
    if (instr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === instr) instr = null;
    } else if (ch === '"' || ch === "'") {
      instr = ch;
    } else if (ch === "{") {
      depth++;
    } else if (ch === "}") {
      depth--;
      if (depth === 0) { end = k; break; }
    }
  }
  if (end <= start) return "";
  const rawObj = jsText.slice(start, end + 1);
  const objText = rawObj
    .replace(/^\s*\/\/.*$/gm, "")    // full-line comments (// Kategori)
    .replace(/,(\s*[}\]])/g, "$1");  // trailing commas
  let help: Record<string, { syntax?: string; description?: string; options?: string[] }>;
  try {
    help = JSON.parse(objText);
  } catch {
    return "";   // graceful: grammar cheatsheet still covers core commands
  }

  const lines: string[] = ["## Kommando-referanse (syntaks — beskrivelse)", ""];
  const renderRow = (name: string) => {
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
  };

  // Gå gjennom objektet i fil-rekkefølge: "// Kategori"-kommentarer blir
  // overskrifter (###), og hver "navn": { ... } blir en kommando-rad. Bevarer
  // den semantiske grupperingen fra command_help.js i referansen.
  const seen = new Set<string>();
  for (const line of rawObj.split("\n")) {
    const hm = line.match(/^\s*\/\/\s*(.+?)\s*$/);
    if (hm) { lines.push("", `### ${hm[1]}`); continue; }
    const km = line.match(/^\s*"([\w-]+)"\s*:\s*\{/);
    if (km && help[km[1]] && !seen.has(km[1])) { seen.add(km[1]); renderRow(km[1]); }
  }
  // Sikkerhetsnett: kommandoer uten kategori-kommentar havner til slutt.
  for (const name of Object.keys(help)) {
    if (!seen.has(name)) renderRow(name);
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

export async function buildCachedPrefix(origin: string, mode: GenMode = "microdata"): Promise<string> {
  const cached = _cachedPrefix[mode];
  if (cached !== null) return cached;

  let catalogBlock = "";
  let kommuneBlock = "";
  try {
    const metaText = await fetchText(origin, "/variable_metadata.json");
    const meta = JSON.parse(metaText);
    catalogBlock = renderCatalog(meta);
    kommuneBlock = renderKommuneCodes(meta);
  } catch (_e) {
    catalogBlock = "";   // degrade: rules-only prompt is still usable
  }

  // command/function reference is microdata-only.
  let commandBlock = "";
  let functionBlock = "";
  if (mode === "microdata") {
    try {
      commandBlock = renderCommands(await fetchText(origin, "/command_help.js"));
    } catch (_e) {
      commandBlock = "";
    }
    try {
      functionBlock = renderFunctions(await fetchText(origin, "/functions.py"));
    } catch (_e) {
      functionBlock = "";
    }
  }

  const prefix = assemblePrefix(mode, { catalogBlock, kommuneBlock, commandBlock, functionBlock });
  _cachedPrefix[mode] = prefix;
  return prefix;
}

// ====================================================================
// EDGE FUNCTION HANDLER
// ====================================================================

export default async (request: Request): Promise<Response> => {
  const gateResp = await gate(request, { endpoint: "kode-svar", maxBodyBytes: 50_000, allowByok: true });
  if (gateResp) return gateResp;

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

  const byokKey = extractByokKey(request);
  const apiKey = byokKey ?? Deno.env.get("ANTHROPIC_API_KEY");
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
    return upstreamErrorResponse(e, byokKey);
  }
};
