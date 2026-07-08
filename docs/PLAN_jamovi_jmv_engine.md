# Design: jamovi-modus 2.0 — ekte jmv i webR (fase 1)

*Dato: 2026-07-08 · Status: til gjennomsyn · Forfatter: Claude + Hans*

## Mål

jamovi-modus skal bruke jamovi sin egen R-pakke (`jmv` + `scatr`) i webR i stedet for
håndskrevet R. Da blir tabeller, figurer, farger og opsjoner identiske med ekte jamovi,
og å legge til en ny analyse går fra «skriv 50 linjer R» til «pek på jamovi sin egen
YAML-definisjon».

Sikkerhetskopi av dagens motor ligger i `js/modes/jamovi_v1.js` + `css/modes/jamovi_v1.css`
(begge repoer). Git-historikken bevarer også alt.

## Bakgrunn: fase 0-spike (bestått 2026-07-08)

- `webr::install(c('jmv','scatr'))` fungerer i nettleseren (webR latest, R 4.6).
  ~170 MB første gang (39 s målt), **4 s fra cache** ved neste besøk.
- `library(jmv)` 1,3 s; analyser 0,3–1,6 s inkl. figurer; ~82 MB R-objekter.
- Figurene er ekte jamovi-ggplot2 med riktig palett (blå/grå/gull), outlier-etiketter,
  konfidensbånd, legend — løser «svake farger»-problemet ved roten.
- Tabeller kan hentes som data frames via `results$<element>$asDF` → HTML-rendering
  med eksisterende jamovi-CSS.
- Opsjonsnavnene i jamovi sine YAML-definisjoner er identiske med R-argumentene
  (verifisert for ttestIS, descriptives, scatr-plottene).

## Arkitektur

Fem komponenter. Alt lever i `js/modes/jamovi.js` + én generert spec-fil + ett
generator-skript. Databroen (parquet til webR `data`, verdietiketter, aktivt datasett)
er uendret.

### 1. Spec-generator (build-time, kjøres manuelt ved behov)

`tools/gen_jmv_specs.py` leser jamovi sine egne definisjonsfiler og skriver
`js/modes/jmv_specs.js` (én JS-fil med et JSON-objekt).

- Kilde: `jamovi-full.yaml` fra jmv- og scatr-modulene. Kopieres inn i repoet under
  `tools/jmv_yaml/` (vendored) slik at genereringen er reproduserbar uten å ha
  jamovi installert. Førstegangs-kilde: `/Applications/jamovi.app/Contents/Resources/modules/*/jamovi-full.yaml`.
- Per analyse: `name`, `ns` (jmv/scatr), `menuGroup`, `menuSubgroup`, `menuTitle`,
  `menuSubtitle` + full opsjonsliste (`name`, `type`, `title`, `default`, `options`
  for List-typer, min/max for tall).
- Kun analysene i fase 1-menyen (under) tas med i genereringen; resten filtreres
  bort med en eksplisitt liste i skriptet.

### 2. Motor: lasting og kjøring

- `ensureJmvLoaded()`: lazy — kjøres første gang brukeren åpner en analyse.
  Viser fremdrift i statuslinjen («Laster jamovi-motoren … ~170 MB første gang,
  går raskt neste gang»). Installerer `jmv` + `scatr`, kjører `library()`, setter flagg.
- Kall-bygger: dialogtilstand → R-kallstreng, f.eks.
  `jmv::ttestIS(data = data, vars = c('len'), group = 'supp', welchs = TRUE)`.
  Opsjoner som har default-verdi utelates (kortere, mer lesbar syntaks-logg).
- Måltype-overstyringer (Variabler-fanen) oversettes til
  `data[[v]] <- factor(data[[v]])` før kallet, slik jamovi gjør med nominale variabler.
- Kjøres via eksisterende `shelter.captureR(kode, {captureGraphics})` — samme
  mekanisme som i dag fanger både tekst og figurer.

### 3. Resultat-serialisering (R-hjelper)

En R-hjelpefunksjon `.jmv_serialize(results)` (defineres én gang ved lasting) går
rekursivt gjennom jmvcore-resultattreet og returnerer JSON:

```
{ items: [ { type: 'table', title, df: <asDF-data>, notes: [...] }
         , { type: 'image', title }              ← selve bildet kommer fra captureGraphics, i rekkefølge
         , { type: 'group', title, items: [...] } ] }
```

- Tabeller: `$asDF` + tittel + fotnoter. Klassene som håndteres: `Table`, `Image`,
  `Group`/`Array` (rekursjon), `Html`/`Preformatted` (som tekst).
- **Første implementasjonsoppgave er å validere denne traverseringen** mot
  descriptives/ttestIS/contTables. Fallback hvis noe ikke lar seg traversere:
  vis jamovi sin egen tekst-output (`print(results)`) i `<pre>` — stygt, men korrekt.
- JS-rendrer JSON-en med dagens `jmv-result-table`-CSS (booktabs-stil): p-verdi-
  formatering og tallformatering gjenbrukes fra dagens kode.

### 4. Dialog-generator

Genererer opsjonspanelet fra spec i stedet for håndskrevne `optionSections`:

- Roller (`Variables`, `Variable`, `Pairs`) → dagens rolleboks-UI (uendret utseende).
  Måltype-filter utledes av YAML-feltene (`suggested`/`permitted`).
- `Bool` → checkbox · `List` → radio/select · `Number`/`Integer` → tallfelt ·
  `String` → tekstfelt · `Level` → nedtrekksliste med gruppens nivåer.
- Gruppering i seksjoner: håndkuratert seksjonskart per analyse (som i dag, men
  navnene peker nå på ekte jmv-opsjoner). Analyser uten kart får flat liste i
  YAML-rekkefølge. (Pixel-lik layout fra jamovi sine u.yaml-filer er fase 2+.)
- **Live-oppdatering som ekte jamovi**: ingen «Kjør»-knapp — resultatkortet
  opprettes når nok roller er fylt, og oppdateres med ~400 ms debounce hver gang
  en opsjon endres. (Analysene tar 0,3–1,6 s, så dette kjennes responsivt.)

### 5. Meny (fase 1-omfang)

| Gruppe | Analyser (jmv/scatr-navn) |
|---|---|
| Exploration | descriptives · scat (Scatter) · pareto |
| T-Tests | ttestIS · ttestPS · ttestOneS |
| ANOVA | anovaOneW · anova · anovaNP (Kruskal-Wallis) |
| Regression | corrMatrix · linReg · logRegBin |
| Frequencies | propTestN (χ² GOF) · contTables |
| Figurer-fanen | Histogram/Box/Bar/Violin (via descriptives-plottopsjoner) · Scatter (scat) · Pareto · Line Plot (beholdes fra v1-motor) |

Fase 2 (senere): RM ANOVA, ANCOVA/MANCOVA, faktoranalysene, partial correlation,
logRegMulti/Ord, skjult toppmeny, ikonpolish, evt. nyere scatr bygget som wasm
(gir Bar/Box/Hist/Line med alle ~60 stilopsjoner).

## Øvrige beslutninger

- **Fallback/angre**: v1-motoren ligger urørt i `jamovi_v1.js`. Bytte tilbake =
  endre én linje i `MODE_MODULES` i index.html. Ingen runtime-veksling mellom
  motorene (unødig kompleksitet); unntak: Line Plot-koden kopieres inn.
- **Caching**: `sw.js` får cache-first-regel for `webr.r-wasm.org` og
  `repo.r-wasm.org` slik at de 170 MB overlever nettleser-opprydding og appen
  virker offline etter første lasting.
- **webR-versjon**: appen bruker i dag `/latest/` — pinnes til konkret versjon
  samtidig (én linje), så en ny webR-utgivelse ikke plutselig endrer oppførsel.
- **Språk**: jmv-output er engelsk, som ekte jamovi. Dialog-rammene (knapper,
  seksjonsnavn) forblir norske som i dag.
- **Feilhåndtering**: R-feil vises i resultatkortet (rød tekst), aldri som alert.
  Tomme roller → kortet viser tomme jamovi-tabeller, akkurat som ekte jamovi.
- **Synk**: implementeres og testes i safestat, kopieres filvis til openstat
  (identiske apper).

## Risiko

| Risiko | Håndtering |
|---|---|
| 170 MB første lasting skremmer | Lazy + tydelig melding + sw-cache; appen ellers uendret rask |
| Resultattre-traversering har ukjente hjørner | Første oppgave; `print()`-fallback finnes alltid |
| webR/repo endrer seg | Pinne versjon; vendored YAML |
| Minne på svake maskiner | Måles i fase 2; v1 er tilgjengelig som nødbrems |

## Verifisering

Hver analyse i fase 1-menyen kjøres i appen mot lsj-eksempeldataene og sammenlignes
side om side med samme analyse i ekte jamovi (samme tall, samme kolonner, samme
figurtype). Spike-siden gjenbrukes som røyk-test for motoren.
