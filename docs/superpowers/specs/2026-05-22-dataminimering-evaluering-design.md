# Dataminimering: AI-evaluering av script

**Status:** Spec — implementering ikke startet
**Dato:** 2026-05-22
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

## Mål og avgrensning

**Mål:**

- Tilby forskeren en rask, lavterskel vurdering av om et script praktiserer
  dataminimering.
- Tilby en grundigere vurdering med strukturerte oppfølgings­spørsmål når
  forskeren ønsker det.
- Tilby en revisjons-funksjon som genererer et konservativt revidert script
  med konkrete forslag til endringer der det er godt begrunnet.
- Forankre vurderingen i konkret norsk og europeisk lovverk slik at forslagene
  har juridisk relevans.
- Persistere forskerens svar i scriptet selv, slik at det er én sannhetskilde
  som lever sammen med koden.

**Ikke-mål:**

- Erstatte forskerens, dataansvarliges eller REKs vurdering. Verktøyet skal
  støtte refleksjon, ikke konkludere med "lovlig" eller "ulovlig".
- Vurdere ting som ikke er synlig fra scriptet: REK-vedtak, tilgangs­
  begrensninger, lagringstid, samtykker, analyseplan.
- Duplisere disclosure-control-sjekkene som allerede ligger i m2py
  (T1-T8, winsorisering, små celler etc.).

## To moduser: kjapp og grundig

| Modus | Trigger | Bruk |
| --- | --- | --- |
| **Kjapp** | Knapp "Vurder dataminimering" | Mens forskeren skriver, raske sjekker |
| **Grundig** | Knapp "Grundig vurdering" | Før innsending, REK-søknad eller publisering |

Begge moduser tar utgangspunkt i scriptet i editoren (inkludert alle kommentarer)
og eksisterende personvern-kommentarer (se neste seksjon).

**Kjapp** sender script direkte til AI med en evaluerings-prompt.

**Grundig** kjøres i to steg:
1. AI utleder kontekst fra scriptet og pre-fyller et skjema med seks felter
2. Forskeren bekrefter/justerer/skipper felter, og AI gir endelig vurdering med
   skjemaets svar som tilleggskontekst

I grundig-modus kan forskeren velge å lagre svarene som personvern-kommentarer
øverst i scriptet (default på), slik at neste vurdering kan bygge videre på dem.

## Revisjons-funksjon (dm-revise)

Etter en vurdering (kjapp eller grundig) kan forskeren be om et konkret
revidert script. AI produserer en konservativ versjon med foreslåtte endringer
der den er rimelig sikker på at de forbedrer dataminimering uten å forringe
analysen.

### Prinsipper

1. **Konservativ.** Bare endringer AI er rimelig sikker på. Sikkerhet "lav"
   ekskluderes helt — bedre å la noe stå urørt enn å foreslå noe usikkert.
2. **Bevarer analytisk intensjon.** Endre granularitet, ikke struktur.
   Variabler og operasjoner som er sentrale beholdes. OK å bytte ICD-full
   til 3-tegns; ikke OK å fjerne en variabel som inngår i regresjon selv om
   relevansen er uklar.
3. **Begrunnelse per endring.** Hver endret linje får en
   `// personvern: <forklaring>`-fritekst-kommentar rett over, slik at
   forskeren kan vurdere og evt. reversere enkeltvis.
4. **Aldri oppfinn variabler.** Hvis AI foreslår en grovere variabel, må den
   eksistere i tilgjengelig register.
5. **Bygger på eksisterende vurdering.** Revisjonen forutsetter at en
   vurdering (kjapp eller grundig) nettopp er gjort. Vurderingens markdown
   sendes inn som primær kilde til hva som bør endres.
6. **Ingen endringer er OK.** Hvis scriptet ser godt minimert ut, returneres
   det uendret med en kort note.

### Språkbasert promptvalg (én backend)

Én backend (Claude via Anthropic API), men to prompt-varianter avhengig av
detektert språk. Microdata-DSL krever full syntaks-kunnskap embedded i
prompten; Python/R trenger ikke det og slipper dermed unna ~2–3K ekstra
tokens.

```
Browser
  │
  └──► /.netlify/edge-functions/dm-revise
          │
          ├── detekter språk (heuristisk)
          │
          ├── [microdata | mixed] → bruk dm-revise-microdata.md
          │                         (full microdata-cheatsheet i prompten)
          │
          └── [python | r]        → bruk dm-revise-pyr.md
                                    (lett prompt, kjenner ikke microdata-
                                    syntaksen i dybden; nevner bare at
                                    Python/R-script kan ha en
                                    microdata-import-blokk øverst)
          │
          ▼
       Anthropic API
```

Begge prompter inkluderer `_shared-principles.md` (rettslig grunnlag,
vurderingsdimensjoner) og prinsippene under "Revisjons-funksjon".

**Hvorfor mixed → microdata-prompt:** microdata-delen er den vanskelige.
microdata-prompten inneholder også vanlig Python/R-evne (Claude er fluent
der uansett).

### Python/R-script og microdata-import-blokk

Python/R-script på microdata.no har typisk en *microdata-import-blokk*
øverst som requester variabler. Det er hovedstedet for dataminimering i
slike script — fjerne variabler som ikke brukes senere er hovedhandlingen.
Selve syntaksen for blokken framgår av scriptet AI får tilsendt; vi trenger
ikke skrive ut blokkformatet i prompten.

Dette nevnes eksplisitt i `dm-revise-pyr.md` slik at AI vet hvor den skal
se etter minimerings-muligheter selv uten dyp microdata-syntaks-kunnskap.

### Språkdeteksjon (heuristikk)

Implementeres i `parse-script-context.ts`. Vekter signaler:

```
microdata: `import all from`, `collapse (mean)`, `tabulate`, `summarize`,
           `keep if`, `//` som dominerende kommentartegn
python:    `import x`, `def `, `from x import`, `#` dominerende,
           ingen microdata-nøkkelord
r:         `library()`, `<-`, `data.frame`, `#` dominerende,
           ingen microdata-nøkkelord
mixed:     microdata-signaler + python/r-signaler over terskel
```

Ved tvil: default til "mixed" → microdata-prompt (tryggeste valg).

### Output-struktur

```json
{
  "revised_script": "...",
  "changes": [
    {
      "line_old": 12,
      "line_count_old": 2,
      "line_new": 14,
      "summary": "ICD-koder kuttet til 3-tegnsnivå",
      "rationale": "Scriptet skiller ikke på underkode",
      "confidence": "høy"
    }
  ],
  "no_changes_explanation": null,
  "language_detected": "microdata",
  "prompt_variant": "microdata"
}
```

`no_changes_explanation` er `null` hvis det er endringer, eller en kort
forklaring hvis ingen endringer foreslås.

## Rettslig grunnlag

Vurderingen forankres i:

- **Personvernforordningen art. 5(1)(c)** — dataminimering
- **Helseregisterloven § 6** — graden av personidentifikasjon
- **Personvernforordningen art. 89(1)** — vitenskapelig forskning og garantier
- **Personvernforordningen art. 5(1)(b)** — formålsbegrensning

Disse refereres i AI-promptens "Rettslig grunnlag"-seksjon og i den samlede
vurderingen som AI produserer. Lovteksten er gjengitt i `docs/lovverk/`.

**Kalibreringsregel:** personvernforordningen gir ingen endelig svar på hva
som er "nødvendig" — avhenger av formålet. AI skal formulere observasjoner
som muligheter for minimering, ikke som lovbrudd. Endelig avgjørelse ligger
hos forsker og dataansvarlig.

## Personvern-kommentarer (script-side persistens)

Forskerens kontekst og svar lagres som kommentarer i scriptet selv. Dette gjør
scriptet til én sannhetskilde, versjonskontrollerbar sammen med koden.

### Syntaks: to former

**Blokk-form** (genereres av grundig-modus):

```
// personvern blokk start
// formål: Studere sammenheng mellom utdanning og inntekt for kohorten 1970-1980
// sentrale variabler: NUDB_UTDNIVAA (eksponering), INNTEKT (utfall), KJOENN (kovariat)
// tidsperiode: 1970-1980 fordi kohorten skal være ferdig utdannet ved analyseslutt
// geografi: kommune nødvendig for å se regionale forskjeller
// sensitive grupper: nei
// alternativer vurdert: SSB-tabell A-04 var for grovkornet
// personvern blokk slutt
```

**Enkeltlinje-form** (for ad hoc-notater eller manuell bruk):

```
// personvern: formål: Studere noe annet enn over
// personvern: kuttet datoer til måned for å unngå unødig presisjon
```

Begge former kan eksistere samtidig.

### Kommentartegn

Både `//` (microdata.no-DSL) og `#` (Python, R) støttes overalt. Generatoren
bruker det dominerende tegnet i scriptet (default `//`).

### Feltnavn (kanoniske)

| Feltnavn | Innhold |
| --- | --- |
| `formål` | Forskningsformål, 1–3 setninger |
| `sentrale variabler` | Hovedeksponering, utfall, kovariater, koblings­variabler |
| `tidsperiode` | Hvorfor disse årene? |
| `geografi` | Hvorfor dette geografiske detaljnivået? |
| `sensitive grupper` | Ja/nei + valgfri begrunnelse |
| `alternativer vurdert` | SSB-tabeller, syntetiske data, fjernanalyse |

Innholdet etter `personvern:` (i enkeltlinje-form) eller etter feltnavnet
(i blokk-form) klassifiseres som **strukturert** hvis feltnavnet matcher en av
de seks kanoniske, ellers som **fritekst**.

### Parser-semantikk

To-modus state-machine:

```
Utenfor blokk:
  → "// personvern blokk start"     ⇒ enter blokk-modus
  → "// personvern: <innhold>"      ⇒ enkeltlinje (strukturert/fritekst)
  → andre linjer                    ⇒ ignorer

Inne i blokk:
  → "// personvern blokk slutt"     ⇒ exit blokk-modus
  → "// <feltnavn>: <verdi>"        ⇒ strukturert hvis kjent feltnavn
  → "// <annet>"                    ⇒ fritekst med blokk-tilknytning
  → ikke-kommentar-linje            ⇒ implicit close (tolerant)
```

**Konflikt­håndtering:** flere definisjoner av samme felt → siste vinner
(lese-rekkefølge ovenfra og ned). Flere blokker tillates, ingen "smart merge".

### Generator-oppførsel (re-kjøring av grundig)

Når sjekkboks "Lagre svar som personvern-kommentarer" er på:

1. Fjern alle eksisterende `// personvern blokk start ... slutt`-blokker
2. Fjern enkeltlinje `// personvern: <feltnavn>: ...` der feltnavn er kjent
3. Behold all fritekst (`// personvern: <fritekst>`)
4. Behold frittstående fritekst fra gamle blokker som konvertes til enkeltlinje
5. Skriv ny blokk øverst i scriptet:
   - For microdata-DSL: helt øverst, før første ikke-kommentar-linje
   - For Python/R: etter eventuell shebang og `import`/`library()`/`from`-
     blokk, før første kjørende linje
   - Tom linje etter blokken
6. Hopp over felter brukeren ikke fylte ut

## AI-promptdesign

Alle prompter på Netlify-siden, lagret som markdown-filer i
`netlify/edge-functions/prompts/`:

- `dm-quick.md` — kjapp script-only vurdering
- `dm-prefill.md` — grundig steg 1: utled feltverdier
- `dm-thorough.md` — grundig steg 2: endelig vurdering med utfylt skjema
- `dm-revise-microdata.md` — revisjon når språk er microdata eller mixed.
  Inneholder full microdata-syntaks-cheatsheet
- `dm-revise-pyr.md` — revisjon når språk er Python eller R. Lett prompt,
  nevner microdata-import-blokk som hovedsted for minimering
- `_shared-principles.md` — felles rettslig grunnlag og vurderingsdimensjoner,
  inkluderes av de øvrige
- `_microdata-syntax.md` — microdata-syntaks-cheatsheet, inkluderes kun av
  `dm-revise-microdata.md`. **Kopi av `microdata-api/server_code/prompts.py`
  sine `GRAMMAR_CHEATSHEET`, `PRIVACY_RULES`, `PSEUDONYM_RULES`, `TYPE_RULES`
  m.fl.** Sync-merknad i topplinjen sier at filen skal holdes synkron med
  prompts.py

### Felles seksjon (`_shared-principles.md`)

```
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

VURDERINGSDIMENSJONER (synlig fra scriptet)

1. Ubrukte variabler — importert men aldri brukt
2. Variabel-granularitet — ICD-kode-detaljnivå, dato-oppløsning, geografi,
   inntekt, alder
3. Populasjons-avgrensing — `keep if`/`drop if`-filtere
4. Tidsperiode — er tidsvinduet snevert nok
5. Sjeldne kombinasjoner — filterkjeder som krymper til sårbar undergruppe
6. Koblingsbehov — er alle `merge`/`import` nødvendige
7. Aggregat vs individnivå — tidlig nok `collapse`?
8. Direkte identifikatorer i transformasjoner

IKKE VURDERT FRA SCRIPTET

Følgende krever kontekst utenfor scriptet og skal ikke gjettes på:
- Analyseplan og dokumentert begrunnelse
- Tilgangsbegrensning og lagringstid (art. 5(1)(e))
- Mulighet for alternativer (syntetiske data, fjernanalyse)
- Senere gjenbruk (art. 5(1)(b))

NB: Disclosure-control i resultater (T1-T8) håndteres separat av m2py.
Fokuser på selve dataminimeringen i scriptet.
```

### `dm-quick.md` (kjapp)

Inkluderer `_shared-principles.md`, pluss:

```
KOMMENTARER OG TIDLIGERE ERKLÆRT KONTEKST

Scriptet kan inneholde kommentarer som beskriver formål, antakelser eller
begrunnelser. Les og bruk alle kommentarer aktivt.

Spesielt:
- Linjer i en `// personvern blokk start ... slutt`-blokk, og enkeltlinjer
  som starter med `// personvern: <feltnavn>:` der feltnavn er ett av
  formål / sentrale variabler / tidsperiode / geografi / sensitive grupper /
  alternativer vurdert, er strukturerte svar fra forskeren. Behandles som
  forskerens autoritative erklæring.
- Linjer som starter med `// personvern: <fritekst>` (eller fritekst inne i
  blokk) er forskerens egne begrunnelser. Vektes sterkt mot tilsvarende
  observasjon.

Disse er trukket ut i seksjonen TIDLIGERE ERKLÆRT KONTEKST nedenfor. Hvis en
observasjon allerede er begrunnet der, ikke gjenta den som et problem — eller
pek heller på om begrunnelsen virker tilstrekkelig.

KATEGORISER SCRIPTET FØRST

- A) Full analyse — import + tydelig analyse
- B) Synlig hensikt — import + transformasjon, analyse mangler
- C) Ren import — kun import-linjer + minimale rename

SPRÅK

Detekter: microdata.no-DSL, R, Python eller mixed.

OUTPUT (norsk, markdown)

## Klassifisering
Kategori: <A|B|C>
Språk: <microdata|R|python|mixed>
Antatt analyseintensjon: <kort, eller "ikke synlig fra scriptet">

## Samlet vurdering
<2-4 setninger med skala (god/akseptabel/forbedringspotensial), forankret i
relevante hjemler. Bruk typisk art. 5(1)(c) og hregl § 6 for helsedata-script;
art. 89(1) der aggregering/pseudonymisering er aktuelt; art. 5(1)(b) der
variabler virker hentet uten kobling til uttrykkelig formål. Ikke alle
hjemler trenger nevnes — bare de som styrker vurderingen.>

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
```

### `dm-prefill.md` (grundig steg 1)

Lettere prompt:

```
Du leser et microdata.no/R/Python-script og skal utlede svar på seks
spørsmål om dataminimering. Returner JSON med ett objekt per felt.

For hvert felt, gi:
- value: <din beste tolkning, eller null hvis ikke nok info>
- source: "comment" | "guessed" | "empty"
  - "comment": verdien er hentet direkte fra en personvern-kommentar
  - "guessed": utledet fra scriptet uten eksplisitt kommentar
  - "empty": ingen rimelig tolkning mulig
- confidence: "høy" | "medium" | "lav"

Felter (JSON-nøkler i snake_case ASCII):
1. formaal
2. sentrale_variabler (objekt: { eksponering, utfall, kovariater, kobling })
3. tidsperiode
4. geografi (bare relevant hvis script bruker geografi)
5. sensitive_grupper (bool + begrunnelse)
6. alternativer (liste eller null)

Disse er JSON-nøklene i API-kontrakten. I script-kommentarer brukes de
norske formene med mellomrom (formål, sentrale variabler, tidsperiode,
geografi, sensitive grupper, alternativer vurdert) — frontend mapper
mellom dem.

Hvis personvern-kommentarer finnes, prioriter dem fremfor utledning.
```

Output skal være ren JSON, parses av frontend.

### `dm-thorough.md` (grundig steg 2)

Samme struktur som `dm-quick.md`, men med ekstra input-seksjon:

```
SKJEMA UTFYLT AV FORSKER

Forskeren har bekreftet eller justert følgende svar på direkte spørsmål.
Disse er autoritative og skal brukes som hovedgrunnlag for vurderingen:

[felter pre-fylt og bekreftet/redigert]

Tomme felter betyr at forskeren valgte å ikke svare; behandle som "ikke
oppgitt" og spør i "Spørsmål til forsker"-seksjonen om det er kritisk.
```

Pluss output-format med en ekstra seksjon:

```
## Personvern-blokk for scriptet
<den oppdaterte blokk-formen som skal skrives inn i scriptet>
```

Den siste seksjonen brukes av frontend til å skrive personvern-kommentarene
tilbake.

### `dm-revise-pyr.md` (Python/R-revisjon)

```
Du har lest et Python- eller R-script og en tidligere dataminimerings-
vurdering av samme script. Din oppgave er å foreslå et revidert script
som reduserer datamengden der det er forsvarlig og godt begrunnet.

KONTEKST: MICRODATA-IMPORT-BLOKK

Python/R-script på microdata.no har typisk en microdata-import-blokk
øverst i scriptet, der variabler hentes inn fra registre. Dette er
hovedstedet for dataminimering i Python/R-script — å fjerne variabler
som ikke brukes senere, eller foreslå grovere alternativer der det
holder. Du ser den eksakte syntaksen i scriptet du får; bruk den som
mal når du foreslår endringer.

Utover import-blokken er resten av scriptet vanlig Python eller R, og
du har full evne til å vurdere det.

PRINSIPPER

1. Konservativ. Endre kun der du er rimelig sikker på at endringen
   forbedrer dataminimering uten å forringe analysen. Hvis det er
   usikkerhet, ikke endre.

2. Bevar analytisk intensjon. Variabler og operasjoner som er
   strukturelt sentrale i analysen, beholdes. Endre granularitet,
   ikke struktur.

3. Begrunn hver endring. Sett inn en `# personvern: <forklaring>`-
   fritekst-kommentar rett over hver endret linje.

4. Aldri introdusere variabler du ikke ser i scriptet eller som ikke
   åpenbart finnes i konteksten.

5. Hvis scriptet ser godt minimert ut, returner det uendret med kort note.

INPUT
- Scriptet (i sin helhet, med eksisterende kommentarer)
- Tidligere vurdering (markdown) — primær kilde til hva som bør endres
- Eventuell personvern-kontekst fra grundig-modus

OUTPUT (JSON)
{
  "revised_script": "...",
  "changes": [
    { "line_old": ..., "line_count_old": ..., "line_new": ...,
      "summary": "...", "rationale": "...", "confidence": "høy"|"medium" }
  ],
  "no_changes_explanation": null
}

REGLER
- Bare høy eller medium sikkerhet. Aldri lav.
- Ingen kosmetiske endringer.
- Bevar eksisterende personvern-kommentarer (blokk og fritekst).
- Hvis kort eller åpenbart minimalt: foreslå ingen endringer.
```

### `dm-revise-microdata.md` (microdata- og mixed-revisjon)

Samme strukturelle innhold som `dm-revise-pyr.md`, men med to forskjeller:

1. **Inkluderer `_microdata-syntax.md`** øverst — full cheatsheet over
   gyldige konstruksjoner, strict-emulation-regler, disclosure-control-
   regler, pseudonym-regler, type-regler. Denne filen holdes synkron med
   `microdata-api/server_code/prompts.py`.

2. **Strengere regler om syntaks:**

```
NÅR DU FORESLÅR ENDRINGER I ET MICRODATA-SCRIPT

- Alle endringer må være gyldig microdata.no-syntaks som kjører i prod.
  Se SYNTAKSREGLER over for autoritativ liste.
- Respekter strict emulation: ingen `collapse (first/last)`, ingen
  multi-key by/on, ingen for-løkke-ellipsis, ingen parens rundt
  iterator-listen.
- Pseudonymer (variabler med _FNR-suffiks) kun som nøkkel i
  collapse(by) eller merge(on) — aldri i transformasjoner eller
  sammenligninger.
- Bruk eksisterende registervariabler — ikke oppfinn navn. Hvis du
  foreslår grovere geografi, bruk faktiske variabler (BEFOLKNING_FYLKE,
  etc.).
- Sett inn `// personvern: <forklaring>` rett over hver endret linje.
- I mixed-script: behandle microdata-DSL-delen med reglene over,
  Python/R-delen med vanlig fluent evne.
```

`_microdata-syntax.md` topplinje:

```markdown
<!-- KOPI: microdata-syntaks-reglene i denne filen er en kopi fra
microdata-api/server_code/prompts.py (GRAMMAR_CHEATSHEET, PRIVACY_RULES,
PSEUDONYM_RULES, TYPE_RULES m.fl.). Endrer du regler her, oppdater også
prompts.py — og motsatt. -->
```

## Arkitektur (Netlify Edge Functions)

```
Browser (m2py/index.html, hostet på Netlify)
   │
   │ Kjapp:
   ├──► POST /.netlify/edge-functions/dm-quick   (streamed SSE)
   │ ◄── markdown chunks, akkumulert i modal
   │
   │ Grundig steg 1:
   ├──► POST /.netlify/edge-functions/dm-prefill (vanlig JSON)
   │ ◄── { fields: {...} }
   │     vises i skjema-modal med forhåndsvisning
   │
   │ Grundig steg 2:
   ├──► POST /.netlify/edge-functions/dm-thorough (streamed SSE)
   │ ◄── markdown + personvern-blokk chunks
   │     render + (opt-in) skriv blokk inn i editor
   │
   │ Revisjon (etter en vurdering):
   ├──► POST /.netlify/edge-functions/dm-revise  (vanlig JSON, ~15-30s)
   │     │
   │     ├── detekter språk
   │     ├── velg prompt-variant:
   │     │    [microdata|mixed] → dm-revise-microdata.md (full syntaks)
   │     │    [python|r]        → dm-revise-pyr.md (lett)
   │     └── kall Anthropic API
   │ ◄── { revised_script, changes, ... }
   │     vises i diff-modal, evt. erstatter editor

Netlify env vars:
   ANTHROPIC_API_KEY        = sk-ant-...
   ANTHROPIC_MODEL          = claude-sonnet-4-6
   M2PY_ALLOWED_ORIGINS     = https://m2py.netlify.app,http://localhost:8888
```

**Hvorfor Edge Functions framfor vanlige Functions:**

- Native streaming-støtte løser timeout-problemet
  (kjapp ~10–15s, grundig ~15–25s overgår vanlig 10s-timeout)
- Bedre UX — tekst dukker opp gradvis
- Gratis på alle Netlify-planer

**Hvorfor ikke Anvil (microdata-api):**

- Anvil-AI-en er for microdata.no-prod-brukere. Dataminimering er m2py-spesifikk.
- Holder ansvars­områdene ryddig adskilt — egen prompt, egen versjonering.
- Netlify er samme stack som m2py-hostingen, åpen for forks med egne API-nøkler.

## Datakontrakter

### `dm-quick` (Edge Function, streaming)

```
POST /.netlify/edge-functions/dm-quick
Content-Type: application/json

Request body:
{
  "script": "...",
  "active_columns": ["BEFOLKNING_KJOENN", ...]   // valgfritt
}

Response: text/event-stream
data: {"type": "text", "text": "## Klassif..."}
data: {"type": "text", "text": "ikasjon\n..."}
data: {"type": "done", "input_tokens": 1234, "output_tokens": 567}
```

### `dm-prefill` (Edge Function, vanlig JSON)

```
POST /.netlify/edge-functions/dm-prefill

Request body:
{
  "script": "...",
  "active_columns": [...]
}

Response: application/json
{
  "fields": {
    "formaal":           { "value": "...", "source": "comment", "confidence": "høy" },
    "sentrale_variabler":{ "value": {...},  "source": "guessed", "confidence": "medium" },
    "tidsperiode":       { "value": "...", "source": "empty",   "confidence": "lav" },
    "geografi":          { "value": "...", "source": "guessed", "confidence": "medium" },
    "sensitive_grupper": { "value": "...", "source": "empty",   "confidence": "lav" },
    "alternativer":      { "value": "...", "source": "empty",   "confidence": "lav" }
  },
  "model": "...",
  "input_tokens": 1234,
  "output_tokens": 234
}
```

### `dm-thorough` (Edge Function, streaming)

```
POST /.netlify/edge-functions/dm-thorough

Request body:
{
  "script": "...",
  "active_columns": [...],
  "context": {
    "formaal": "...",
    "sentrale_variabler": {...},
    "tidsperiode": "...",
    "geografi": "...",
    "sensitive_grupper": "...",
    "alternativer": "..."
  }
}

Response: text/event-stream
data: {"type": "text", "text": "## Klassif..."}
...
data: {"type": "personvern-blokk", "lines": ["// personvern blokk start", ...]}
data: {"type": "done", "input_tokens": 2345, "output_tokens": 1234}
```

### `dm-revise` (Edge Function, JSON med språkbasert promptvalg)

Ikke streamet — synkron med ~15–30s svartid.

```
POST /.netlify/edge-functions/dm-revise

Request body:
{
  "script": "...",
  "vurdering": "...",         // markdown fra forrige kjapp/grundig
  "context": {...}            // valgfritt, fra grundig-modus
}

Response: application/json
{
  "revised_script": "...",
  "changes": [
    {
      "line_old": 12,
      "line_count_old": 2,
      "line_new": 14,
      "summary": "ICD-koder kuttet til 3-tegnsnivå",
      "rationale": "Scriptet skiller ikke på underkode",
      "confidence": "høy"
    }
  ],
  "no_changes_explanation": null,
  "language_detected": "microdata",
  "prompt_variant": "microdata",
  "input_tokens": ...,
  "output_tokens": ...
}
```

## Frontend: UI og flyt

### Knapper i hamburger-meny

Ny seksjon "Personvern":

```
─────────────────────────────
Personvern
  Vurder dataminimering
  Grundig vurdering
─────────────────────────────
```

Begge disablet hvis editor er tom eller bruker ikke har gitt AI-consent.

### Førstegangs-consent

Ved første klikk på enten knapp, vis modal:

```
Dataminimering-vurdering bruker AI fra Anthropic.

Scriptet ditt sendes til Anthropic for vurdering. Variabelnavn og
kommentarer overføres. Faktiske mikrodata (verdier) sendes ikke —
m2py kjører lokalt i nettleseren, og analyse av selve dataene
skjer ikke som del av denne funksjonen.

[Avbryt] [Aksepter og fortsett]
```

Lagre `microdata_dm_consent='1'` i localStorage. Mulighet for tilbakekall
fra hamburger-meny ("Avregistrer AI-bruk").

### Kjapp-modus modal

Resultat-modal:
- Tittel: "Dataminimering-vurdering"
- Body: rendret markdown, oppdatert mens stream pågår
- Footer: "Avbryt" (kutter stream), "Kopier", "Generer revidert script", "Lukk"
- Trykker man Avbryt midt i stream, stoppes fetch-en og man ser delvis svar
- "Generer revidert script" er disablet til stream er ferdig

### Grundig-modus modal

Trinn 1 — skjema-modal:
- Tittel: "Grundig dataminimerings-vurdering"
- Hjelp­tekst: "AI har lest scriptet og fylt ut det den klarte å utlede. Bekreft eller juster, og hopp over felter der spørsmålet ikke er relevant."
- Seks felt-grupper:
  - Hver med tekstinput/textarea (avhengig av lengde)
  - Pre-fylt verdi
  - Liten badge: "Fra kommentar (høy sikkerhet)" / "Utledet fra script (medium)" / "Tomt"
  - "Hopp over"-checkbox
- Sjekkboks: "Lagre svarene som personvern-kommentarer øverst i scriptet" (default på)
- Forhåndsvisning av personvern-blokk, oppdateres live
- Footer: "Avbryt", "Vurder nå"

Trinn 2 — resultat-modal (samme som kjapp):
- Markdown med vurdering
- Hvis sjekkboks var på: skriv personvern-blokk inn i editor ved fullført stream
- Toast: "Personvern-svar lagret som kommentarer. Ctrl+Z for å angre."
- "Generer revidert script"-knapp tilgjengelig som i kjapp-modal

### Revisjons-modal (etter klikk på "Generer revidert script")

Spinner med tekst "Genererer revidert script (~20s)" mens kallet kjører.
Når svar mottatt, vis diff-modal:

- Tittel: "Foreslått revidert script"
- Warning-banner øverst: "⚠ AI kan gjøre feil. Bekreft at endringene ikke
  bryter analysen din."
- Liste over endringer, hver vist som:
  - Header: "Endring N av M (linje X–Y)"
  - Den foreslåtte `// personvern:`-kommentar-linjen
  - Diff-visning: rød fjernet linje + grønn ny linje
  - Sikkerhet-badge: "Høy" / "Medium"
  - Rationale i liten skrift under
- Sammendrag nederst: "N endringer, X med høy sikkerhet, Y med medium"
- Footer: "Avbryt", "Vis hele scriptet" (åpner ny modal med revidert script
  for kopiering), "Erstatt scriptet"

Hvis ingen endringer foreslås:
- Vis `no_changes_explanation` i stedet for diff
- Footer: bare "Lukk"

Hvis endringer > 5, "Erstatt scriptet" krever ekstra bekreftelse:
"Dette erstatter scriptet med {N} foreslåtte endringer. Er du sikker?"

Etter erstatning:
- Toast: "Scriptet erstattet. Ctrl+Z for å angre. Anbefalt: kjør vurdering på nytt."

### Språk-vist i UI

`language_detected` fra responsen vises diskré i diff-modalen:
"Språk: microdata" / "Python" / "R" / "mixed". Hjelper feilsøking hvis
revisjons-kvalitet er rar (forteller hvilken prompt-variant som ble brukt).

### Editor-modifikasjon

Når vi skriver personvern-blokk:
- Fjern eksisterende blokk(er) og strukturerte enkeltlinjer (matcher kjente
  feltnavn)
- Bevar all fritekst og frittstående blokk-fritekst (konverteres til
  enkeltlinjer ved behov)
- Plasser ny blokk øverst i scriptet, etter eventuell shebang og
  `import`/`library()`/`from`-header
- Tom linje etter blokken
- Editorens native undo skal kunne rulle tilbake i én operasjon

## Personvern (brukernes data sendt til AI)

- Scriptet sendes til Anthropic via Edge Function. Anthropic-policy:
  API-input brukes ikke til trening som default.
- Edge Function lagrer ikke scriptet utover funksjons­kallets levetid.
- `active_columns`-hint inneholder bare kolonnenavn fra aktivt mock-datasett
  — ingen verdier.
- Førstegangs-consent (se over) gjør dette eksplisitt for brukeren.

## Sikkerhet og misbrukshåndtering

Lagvis:

1. **Origin-sjekk** i hver Edge Function — kun tillat kall fra m2py-domenet
   (konfigurert via `M2PY_ALLOWED_ORIGINS`). Trivielt å omgå, stopper enkleste
   misbruk.
2. **Per-IP rate limit** — 10 vurderinger / time / IP. Implementeres med
   Netlify Blobs eller in-memory cache for MVP.
3. **Maks request-størrelse** — avvis scripts > 50 KB.
4. **Daglig budsjett-cap** i Anthropic-konsollen som sikkerhetsnett.

## Kostnader

- Kjapp: ~3K input + ~1.5K output tokens med Sonnet ≈ $0.01–0.02
- Grundig: ~4K input + ~2K output × 2 funksjons­kall ≈ $0.03–0.06
- Revisjon (Python/R-variant): ~3K input + ~3K output ≈ $0.03–0.05
- Revisjon (microdata-variant): ~6K input (inkluderer cheatsheet) + ~3K
  output ≈ $0.05–0.08

Estimat ved 100 vurderinger/dag + 20 revisjoner/dag (anslag, opt-in):
~$60–100/mnd. Overkommelig for hobbyprosjekt ved monitorering.
Anthropic-budsjett-cap som sikkerhet.

## Avgrensninger for MVP

Ikke med:

- Ingen inline-markering av variabler i editoren ved observasjoner
- Ingen vurderingshistorikk
- Ingen statisk forsjekk før AI-kall
- Ingen streaming-rendering av markdown med live formatering — rå tekst
  mens stream pågår, full render ved ferdig
- Ingen multi-script-vurdering (kun aktivt script)
- Soft-auth eller bruker-spesifikk API-nøkkel — vurderes hvis bruk vokser
- Ingen per-endring accept/reject i revisjons-modalen (all-or-nothing)
- Ingen streaming av revisjons-svar (synkron 15–30s med spinner)

## Implementeringsrekkefølge

Tre milepæler. Hver kan slås sammen til én PR eller deles i flere.

### Milepæl 1 — Kjapp-modus ende-til-ende

- Sjekk/migrere m2py til Netlify hvis ikke der allerede
- Sett opp `dm-quick.js` Edge Function med basic prompt
- Implementer parser-modul `parse-script-context.ts`
- Sett opp Anthropic env-var
- Frontend: hamburger-knapp, consent-flow, kjapp-modal med streaming
- Test ende-til-ende, iterer på prompten
- Origin-sjekk, rate limit, body-size-limit

### Milepæl 2 — Grundig-modus

- `dm-prefill.js` Edge Function
- `dm-thorough.js` Edge Function
- Frontend: skjema-modal med pre-fylling og forhåndsvisning
- Generator-logikk for personvern-blokk i editor
- Test full to-stegs-flyt

### Milepæl 3 — Revisjons-funksjon + polering

- Lag `_microdata-syntax.md` ved å kopiere relevante deler fra
  `microdata-api/server_code/prompts.py`. Topplinje med sync-merknad
- Lag `dm-revise-microdata.md` og `dm-revise-pyr.md`
- Lag `dm-revise.js` Edge Function med språkdeteksjon og prompt-valg
- Frontend: "Generer revidert script"-knapp og diff-modal
- Editor-erstatning + toast / undo-meldinger
- Dokumentasjon i `hjelp.html`
- Hjelp-tekst i UI
- Monitorering av kostnader / bruksstatistikk

## Åpne spørsmål

- **Verifiser at m2py er på Netlify.** Hvis ikke (f.eks. GitHub Pages),
  vurder migrasjon før Milepæl 1.
- **Modellvalg:** Sonnet (cost-effective, raskere) eller Opus (dypere
  vurdering, dyrere). Anbefaling: start med Sonnet og oppgrader hvis
  vurderings­kvaliteten er for tynn.
- **Hjemmel-felt i observasjoner:** denne speccen plasserer lov­referanser
  i "Samlet vurdering" og ikke per observasjon. Hvis brukerne savner mer
  konkret referanse per punkt, kan vi legge til et valgfritt
  `Hjemmel:`-felt senere.
- **Per-endring accept/reject i diff-modal:** ikke i MVP (all-or-nothing
  erstatning). Vurder senere hvis forskere savner finkornet kontroll.
- **Streaming for dm-revise:** vurderes hvis ~20s synkron føles for treg
  i bruk.
- **Sync av microdata-syntaks-regler:** `_microdata-syntax.md` (Netlify) og
  `prompts.py` (Anvil) må holdes synkron. For MVP gjøres dette manuelt med
  klar sync-merknad. Hvis drift blir et problem, vurder CI-sjekk eller
  felles kildefil. Hvis microdata-revisjons-kvalitet er dårlig: vurder å
  flytte microdata-revisjon til Anvil i runde 2.

## Referanser

- `docs/lovverk/dataminimering.md` — utdrag, Helsedirektoratet Faktaark 57
- `docs/lovverk/formalsbegrensning.md` — utdrag
- `docs/lovverk/lagringsbegrensning.md` — utdrag
- `docs/lovverk/personvernprinsippene.md` — oversikt
- https://www.helsedirektoratet.no/normen/personvernprinsippene-faktaark-57
- Personvernforordningen art. 5, 89(1)
- Helseregisterloven § 6
- Helseforskningsloven § 32
