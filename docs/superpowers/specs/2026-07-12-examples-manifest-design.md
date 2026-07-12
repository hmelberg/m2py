# Manifest-drevne eksempler (slutt på hardkoding i index.html)

**Dato:** 2026-07-12
**Status:** v2 — modal-basert (se «v2-revisjon» under). Datalaget (generator,
manifest, lat henting) fra v1 står; presentasjonen (dropdown) er erstattet.
**Gjelder:** safestat (leder) + openstat (synk etterpå)

> **v2-revisjon (2026-07-12, etter Hans' testing):** v1 bygde en modus-filtrert
> *dropdown* og lot den mode-blinde «Flere eksempler på web»-modalen (kun
> microdata-scripts) ligge ved siden av. I micropython-modus kunne man dermed nå
> microdata-eksempler — to systemer, ikke modus-relevant. v2 samler alt i ÉN
> modal, scoped til aktiv modus, drevet av per-modus-folderen. Se seksjonen
> «v2-revisjon: én modus-scoped modal» nedenfor; den overstyrer «index.html:
> dynamisk render + lat henting» og «Kategorier»-seksjonene i v1-teksten.

## Problem

Eksempel-knappene i «Eksempler»-menyen er hardkodet i `index.html` — én
`<button data-example="…" data-mode="…">` per eksempel, per modus. Å legge til
eller fjerne et eksempel krever en redigering av `index.html` i begge repoer.
Vi vil kunne legge til/fjerne eksempler ved å bare legge en fil i en mappe,
uten å røre `index.html`.

## Mål

- Eksempler oppdages fra filer i mapper, ikke fra hardkodet markup.
- Å legge til/fjerne et eksempel = legge til/fjerne en fil (+ regenerere et
  manifest via et skript du alt kjører i arbeidsflyten).
- Ingen økning i oppstartstid (boot-stien røres ikke).
- Grasiøs degradering hvis manifestet ikke kan lastes.

## Ikke-mål (YAGNI)

- Ingen kjøretids-mappelisting via GitHub-API (bryter `file://`, Netlify og
  andre verter; rate-limit 60/t/IP; ekstra oppstartslatens).
- Ingen git-hook (må installeres per klon; to synkede repoer = to hooks).
- Ingen vilkårlig dyp mappenesting — maks ett valgfritt undernivå.

## Bakgrunn: eksisterende mønster

`web_examples/` løser allerede akkurat dette for «Flere eksempler på web»:
`web_examples/generate_manifest.py` skanner kategorimapper og skriver
`web_examples/manifest.json`; `index.html` henter manifestet ved åpning av
web-eksempel-velgeren (`index.html:1734`) og bygger lista. Vi speiler dette
mønsteret for de innebygde per-modus-eksemplene.

## Arkitektur

Tre deler:

### 1. Mappestruktur

```
examples/
  manifest.json              (generert — ikke rediger for hånd)
  generate_manifest.py       (generator)
  micropython/
    01_pandas_basics.txt
    02_plotly.txt
    03_dashboard.txt
    04_csv_url.txt
  brython/
    …
  duckdb/
    …
```

- Én mappe per modus; mappenavnet ER modus-nøkkelen
  (`microdata|python|r|statx|duckdb|brython|micropython`, pluss `safestat` i
  safestat-repoet).
- **Kategorier via undermapper** (se «Kategorier» under): valgfritt ett
  undernivå, `examples/<modus>/<NN_kategori>/<fil>.txt`.
- Filnavn kan droppe dagens modus-prefiks (`mp`/`bry`/`sql`), siden mappa
  koder modus. Behold et numerisk sorteringsprefiks (`01_`, `02_`) for
  rekkefølge.

### 2. Generator: `examples/generate_manifest.py`

Gjenbruker konvensjonene fra `web_examples/generate_manifest.py`.

- Skanner `examples/<modus>/` (og ett undernivå).
- Modus utledes fra toppmappenavnet; ukjente mappenavn hoppes over.
- **Label-kilde (prioritert):**
  1. En dedikert `# label: <tekst>`-linje i de første ~5 linjene av fila.
  2. Ellers `#options.title = "…"` hvis satt.
  3. Ellers avledet fra filnavnet (strip `NN_`, `_`→mellomrom, kapitaliser).
  - `#options.title` styrer fortsatt dashboard-tittelen — den er en *fallback*
    for meny-label, ikke koblet til den.
- Skriver `examples/manifest.json`.

**Manifest-skjema** (baner er relative til `examples/`, siden klikk-handleren
gjør `fetch(base + 'examples/' + file)`):

```json
{
  "micropython": [
    { "file": "micropython/01_pandas_basics.txt", "label": "pandas_mpy — basics", "group": null },
    { "file": "micropython/04_csv_url.txt", "label": "Les en CSV fra en URL", "group": null }
  ],
  "brython": [ … ]
}
```

`group` er `null` for filer rett i modus-mappa, ellers kategori-labelen
(utledet fra undermappenavnet, samme `NN — Pen tittel`-regel som
`web_examples`).

## Kategorier (vist til brukeren)

Kategorier er **implisitte gjennom mappestrukturen** og førsteklasses i UI-et:

- Filer rett i `examples/<modus>/` vises som en flat liste (ingen seremoni for
  små modi — micropython med 4 eksempler forblir flatt).
- Legger du inn undermapper `examples/<modus>/<NN_kategori>/`, blir hver
  undermappe en **kategori-underoverskrift** i dropdownen, med sine eksempler
  under seg. En modus kan blande flate filer og kategoriserte undermapper.
- Kategori-rekkefølgen styres av `NN_`-prefikset på undermappa; labelen er
  `NN — Pen tittel` (samme `_folder_label`-regel som `web_examples`).
- Dette skalerer naturlig: brython (~23 eksempler) kan deles i kategorier,
  mens små modi slipper.

**Presentasjon:** vi gjenbruker dagens dropdown og legger kategoriene inn som
`.examples-dropdown-title`-underoverskrifter (samme klasse som «GitHub»-tittelen
i menyen). Vi tar IKKE i bruk web-eksemplenes to-panels-modal for den innebygde
menyen nå — den er tyngre for det vanlige «bare hent det ene eksempelet»-tilfellet.
Hvis en modus en dag vokser forbi det en dropdown takler, kan modalen
(`initWebExamples`, `index.html:1633`) gjenbrukes uendret. (YAGNI til da.)

### 3. `index.html`: dynamisk render + lat henting

- **Lat henting:** manifestet hentes ved *første åpning* av Eksempler-menyen
  (i `menuExamplesBtn`-klikkhandleren, ~`index.html:1586`), memoisert. Ikke ved
  oppstart. Boot-stien (motor-lasting) røres ikke → ingen oppstartskostnad.
- **Render:** for hver modus i manifestet, tøm den tilhørende
  `.examples-section[data-section-mode="<modus>"]` og bygg knapper med
  `data-example` (fil-bane), `data-mode` (modus) og label som tekst.
  `group`-verdier grupperes under en `.examples-dropdown-title`-underoverskrift.
- **Kjør i18n-passet** over dropdownen etter bygging (labels bærer `data-i18n`
  som i dag; ingen ordbok-oppføringer finnes for dem, så de passerer uendret —
  bekreftet mot `js/i18n.js` som slår opp på `textContent`).
- **Klikk via delegering:** dagens handler festes per knapp ved lasting
  (`index.html:1596`), så dynamiske knapper ville mangle handler. Bytt til én
  delegert `click`-lytter på `examplesDropdown` som leser `data-example`,
  `data-mode` og `textContent` — identisk oppførsel, men virker for knapper
  lagt til senere.
- **Synlighet per modus** (`updateExamplesVisibility`, `index.html:1582`) er
  uendret — den viser/skjuler `.examples-section` etter aktiv modus.

## Feilhåndtering / grasiøs degradering

- Feiler `fetch('examples/manifest.json')`: logg en advarsel og vis én deaktivert
  plassholder-knapp «Kunne ikke laste eksempler — last siden på nytt» i den
  aktive seksjonen. Resten av appen er upåvirket.
- **Under piloten** (kun micropython): behold dagens hardkodede
  micropython-knapper i `index.html` som sikkerhetsnett. Render-steget
  tømmer-og-bygger seksjonen fra manifestet ved åpning; feiler hentingen, blir
  de statiske knappene stående. Ved full utrulling fjernes de statiske knappene
  for migrerte modi (vi vedlikeholder ikke en parallell liste — det ville
  motvirke hele poenget), og plassholder-oppførselen over gjelder.

## Regenerering

- `python examples/generate_manifest.py`, kjørt manuelt eller som del av den
  eksisterende safestat→openstat-synk-arbeidsflyten (`sync_check.sh` e.l.).
- Feilmodus (glemte å regenerere → eksempelet vises ikke) er ufarlig og
  umiddelbart synlig i menyen.

## To repoer

- **safestat leder** (UI-leder, safestat-først-synk). Bygg og valider i
  safestat, synk til openstat.
- Generator-skriptet er byte-identisk i begge; mappene/manifestene skiller seg
  (openstat = safestat minus enkelte modi/eksempler). Kjøres per repo.

## Utrullingsplan

1. **Pilot — micropython (4 filer):**
   - Flytt `examples/mp0X_*.txt` → `examples/micropython/0X_*.txt`.
   - Skriv dagens kuraterte label inn i hver fil som `# label: …` (så ingen
     label går tapt).
   - Skriv `examples/generate_manifest.py`; generer `examples/manifest.json`.
   - Gjør micropython-seksjonen i `index.html` manifest-drevet: lat henting,
     delegert klikk, i18n-pass, plassholder-fallback. Behold de statiske
     micropython-knappene som sikkerhetsnett i denne fasen.
   - Verifiser: menyen bygger fra manifestet, klikk laster riktig fil,
     modus-bytte virker, fallback ved simulert hentefeil.
2. **Utrulling — øvrige modi:** migrer én modus om gangen på samme vis;
   bevar kuraterte labels via `# label:`. Fjern statiske knapper per migrert
   modus når den er verifisert.
3. **Synk til openstat** etter hvert steg.

## Bevar-disse (migreringsrisiko)

Noen labels finnes i dag *bare* i `index.html`, ikke i filene (f.eks. «Load a
CSV from GitHub», «Select columns → focused dataset»). Migreringen MÅ skrive
disse inn i filene som `# label:` før de statiske knappene fjernes, ellers går
de tapt. Ren filnavn-avledning ville stille degradere dem.

## Åpne detaljer (avklares i plan)

- Undernivå-gruppering: sortering av grupper (numerisk prefiks på undermappe).
- Nøyaktig plassholder-tekst og i18n-nøkkel for hentefeil.

---

# v2-revisjon: én modus-scoped modal

## Prinsipp

Ett system. Klikk på **«Eksempler»** åpner en **modal** (samme to-panels-komponent
som dagens web-eksempel-velger, `initWebExamples`), som viser KUN eksemplene for
**aktiv modus** — hentet fra `examples/<modus>/`-folderen via manifestet. Ingen
egen «Flere eksempler»-knapp; ingen modus-blind microdata-liste ved siden av.

## Datalag (uendret fra v1)

Generatoren, `examples/manifest.json`-skjemaet (`{ "<modus>": [{file, label,
group}] }`) og `js/examples-menu.js` (`groupForMode`) står. Lat henting av
manifestet (`{cache:'no-store'}`, kun ved første åpning) står.

## Fold `web_examples/` inn i `examples/microdata/` (valg a)

- Flytt hver kategorimappe `web_examples/<NN_kategori>/` →
  `examples/microdata/<NN_kategori>/`. Da blir microdata-modusens eksempler
  nettopp dagens web-bibliotek, med kategoriene som undermapper.
- `web_examples/`-mappa, `web_examples/generate_manifest.py` og
  `web_examples/manifest.json` pensjoneres etter flytting.
- **Label-markør:** web-eksemplene bruker `// Example: <tittel>` på linje 2.
  Utvid generatorens label-lesing til også å godta `Example:` som markør (samme
  prioritetsnivå som `# label:`), så de ~50 filene virker uendret etter flytting.
  Prioritet blir: `# label:`/`// Example:` → `#options.title` → filnavn.
  (Da slipper vi å redigere 50 filer; `# label:` forblir den dokumenterte
  konvensjonen for nye eksempler.)
- microdata-eksemplene laster i microdata-modus (manifest-modus = folder =
  `microdata`; `loadExampleFile`-hvitelista har alt `microdata`).

## Modal-presentasjon (fleksibel)

Modalen tilpasser seg antall eksempler og om modusen har kategorier:

- **Få eksempler, ingen kategorier** (f.eks. micropython, 4 flate filer): vis én
  enkel liste med scriptene — INGEN tomt kategori-panel. (Skjul venstre panel
  eller vis kun script-panelet.)
- **Kategorisert** (f.eks. microdata med undermapper): to paneler — kategorier
  til venstre, scripts til høyre (som dagens web-modal).
- **Mange eksempler**: begge paneler er **scrollbare** (`overflow-y:auto`).
  Modalen har begrenset høyde (f.eks. `max-height: 80vh`) og innholdet scroller
  inni — må virke enten det er 4 eller 150 eksempler, på liten som stor skjerm.
- Kategorier og rekkefølge kommer fra `group`/`NN_`-prefiks i manifestet (som v1).

Kilde til modalen er `ExamplesMenu.groupForMode(manifest, aktivModus)` — samme
grupperingsfunksjon som v1, nå konsumert av modalen i stedet for dropdownen.

## index.html-endringer (erstatter v1s dropdown-render)

- **Åpning:** `menuExamplesBtn`-klikk åpner modalen (ikke en dropdown). Henter
  manifestet lat (memoisert), bygger modal-innholdet for aktiv modus, viser
  modalen.
- **Generaliser `initWebExamples`** til å ta en gruppert eksempel-liste (fra
  `groupForMode`) i stedet for kun `web_examples/manifest.json`. Flat modus →
  én liste; kategorisert → to paneler; begge scrollbare.
- **Klikk på et eksempel:** gjenbruk `loadExampleFile(file, title, mode)` fra v1
  (laster fila, bytter modus, lukker modalen).
- **Fjern:** `menuWebExamples`-knappen, den gamle dropdown-render-koden
  (`renderExamplesFromManifest` mot `.examples-section`), de hardkodede
  `.examples-section`-knappene, og web-modalens gamle `web_examples/manifest.json`-
  lesing. `.examples-section`-containere/`updateExamplesVisibility` utgår.
- **Grasiøs degradering:** feiler manifest-hentingen, vis en melding i modalen
  («Kunne ikke laste eksempler — last siden på nytt»). Ingen stille tom modal.

## Utrullingsplan (v2)

Bygger videre på grenen `examples-manifest` (v1 Task 1–3 + generator står; v1s
dropdown-render fjernes):

1. Generator godtar `// Example:`-markør (+ test).
2. Flytt `web_examples/<kat>/` → `examples/microdata/<kat>/`; regenerer manifest;
   verifiser microdata-kategoriene + micropython står.
3. Modal-render: generaliser `initWebExamples`, åpne på «Eksempler», modus-scoped,
   adaptiv (flat=liste / kategorisert=to paneler), scrollbar; fjern
   dropdown-render + `menuWebExamples`-knapp + gammel web-modal-kilde.
4. Rydd bort `web_examples/` (mappe, generator, manifest) + død dropdown-CSS.
5. Synk til openstat.
6. Manuell browser-verifisering (Hans): hver modus viser kun sine egne
   eksempler; micropython = flat liste; microdata = kategorier, scrollbar;
   fallback ved blokkert manifest.

## Bevar (migreringsrisiko, v2)

- web-eksemplenes `// Example:`-labels må overleve flyttingen (derav generator-
  utvidelsen — ikke rør de 50 filenes innhold).
- Ingen andre modi mister eksempler: kun microdata får web-biblioteket; de
  øvrige modienes eksempler kommer fra sine egne foldere (brython/duckdb/… må
  migreres til `examples/<modus>/` for å vises i modalen — se plan; til de er
  migrert har de ingen modal-eksempler, så migrer alle modi i dette steget eller
  behold en overgangsliste).
