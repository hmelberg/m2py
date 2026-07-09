# Roadmap — safestat/openstat

*Levende dokument. Oppdatert 2026-07-09 (kveld). Punktene er ikke forpliktelser, men
prioritert idéliste. Kilder: designdok/reviews fra jamovi 2.0 fase 1–3
(docs/PLAN_jamovi_*.md, docs/jamovi-validation.md) + løpende samtaler og Hans' testing.*

## jamovi-modus — gjenstående arbeid

**Analyser (24 av ~26 i menyen; disse to gjenstår):**
- [ ] **Repeated Measures ANOVA** (anovaRM) — den tyngste gjenstående biten: krever
      RM-design-UI (definer faktorer med navn+nivåer via `rm`, tilordne målekolonner
      til celler via `rmCells`) + rmTerms/bsTerms (modellbyggeren gjenbrukes),
      kontraster og utvidet postHoc-form. Estimat: egen dedikert økt.
- [ ] **CFA** — faktor-definisjons-UI (`factors` = Array of Group {label, vars}:
      navngi latente faktorer og tilordne variabler; ligner rolleboksene med
      redigerbart navn + «legg til faktor»-knapp) + `resCov` (Pairs, finnes).
      FØRSTESTEG: lavaan-røyktest i webR (kjøring er utestet; lasting virker).
      Estimat: én økt, forutsatt at lavaan kjører.

**Figurer (utsatt av Hans 9/7 — tas når han sier fra):**
- [ ] Bygge nyere `scatr` fra jamovi sitt GitHub-repo som wasm (rwasm-verktøyet;
      finnes IKKE ferdigbygget på r-universe — verifisert). Gir Bar/Box/Histogram/
      Line/Pareto som egne analyser med alle ~60 stilopsjonene (error bars, titler,
      akser, legend, fonter). Krever eget wasm-byggmiljø (emscripten) — den tyngste
      enkeltjobben i køen.
- [ ] Pareto Plot tilbake i menyen (avhenger av punktet over)

**Validering:**
- [ ] Manuell side-om-side-validering av TALLENE mot ekte jamovi-appen —
      sjekklisten med 9 rader står klar i docs/jamovi-validation.md (UX er testet
      av Hans 9/7; den numeriske gjennomgangen gjenstår)

**Teknisk gjeld (fra reviewene, småting):**
- [ ] Skille pliktige/valgfrie roller i «Velg variabler»-hintet (i dag kan hintet
      maskere reelle R-feil når en valgfri rolle står tom)
- [ ] `refLevels`: feilet nivå-henting gir permanent deaktivert nedtrekksliste
      uten retry (kun ved motorfeil; lav prioritet)
- [ ] NMXList: tømt valg sender `character(0)` — live-verifisert kun for
      jmv::mancova; de 6 andre analysene med NMXList deler antakelsen uverifisert
- [ ] Bilde-rekkefølgenøkler i `.jmv_serialize` (i dag ordre-basert matching mot
      captureGraphics; robust nok, men skjørt ved fremtidige jmv-endringer)
- [ ] `console.warn` ved bilde-underskudd i renderJmvResults (feilsøkingshjelp)
- [ ] Bayes factor-opsjonene (bf/bfPrior): krever wasm-bygg eller stub av `deSolve`
- [ ] Måle minnebruk på svake maskiner; `jamovi_v1`/«Jamovi light» er nødbrems

**Avklaringer (Hans bestemmer):**
- [ ] Output-rens ved modusbytte: jamovi-resultater tømmes også ved
      jamovi→python→jamovi (konsekvens av ønsket rensing ved inngang).
      Alternativ: bevare jamovi-resultatene over en tur innom andre moduser.
- [ ] Modus-gjenoppretting ved sidelast: appen kan i dag ikke starte rett i
      jamovi-modus (lazy-registrering; faller tilbake til standardmodus).
      Ville kreve at MODE_MODULES-moduler lastes før restoreEditorMode.

**Ferdig (jamovi fase 1–3, alt merget 2026-07-09):** ekte jmv 2.7.7 i webR (pinnet
v0.6.0, SW-cachet); 24 analyser inkl. ANCOVA/MANCOVA/Friedman/Log-Linear/Factor-
gruppen; u.yaml-genererte dialoger m/ grupper, grid, nøsting, enable-avhengigheter,
NMXList-checkparts og radiogrupper; modellbygger (interaksjoner/post hoc/blocks);
refLevels-velger m/ nivåer fra data; live-oppdatering uten Kjør-knapp; skjult
toppmeny m/ bryter; ikoner + finpolish; «Jamovi light» (v1) som egen modus;
websocket-stub for contTables; kopier-knapp på tabeller og figurer; datasett-synk
på tvers av moduser; output-rens ved inngang.

## AI-assistenten

- [ ] **Auto-retting for python- og r-modus i v2-flyten** (i dag kun microdata).
      Backend er klar (`kode-svar-v2` tar `prior_script`+`errors` uansett modus);
      det som mangler er klientvalidator. To nivåer:
      - Nivå 1 (liten jobb, start her — python først): syntakssjekk via
        `compile()` i Pyodide / `parse()` i webR + kolonnenavn-sjekk mot aktivt
        datasett (`lastDatasetInfo`). Flytt `if (mode === 'microdata')`-grenen i
        `runFastQueryV2` til en modus-dispatch.
      - Nivå 2 (senere, hvis nivå 1 ikke fanger nok): sandkasse-prøvekjøring mot
        kopi av aktivt datasett med timeout; send runtime-feilen til
        reparasjonsrunden. Utfordringer: bivirkninger, nettkall, kjøretid.
- [ ] Vurdere Send⚗︎-flyten (v2) også for openstat-brukere på ikke-micro-URL-er
      (i dag går de til data-svar som er admin-gated — bevisst valg 9/7, men verdt
      å revurdere hvis vanlige brukere trenger AI-hjelp uten egen nøkkel)

## Pakkeinstallasjon (python/r)

*Status i dag: autoinstallasjon er PÅ i begge språk — Python: `loadPackagesFromImports`
+ micropip-fallback per import (index.html preRun); R: `library()`-overstyring som
kjører `webr::install()`. Service workeren cacher pakke-hostene (offline etter første gang).*

Mål: brukeren skal kunne installere alt fra Pyodide-wheels til ting man kan
prøve fra PyPI eller GitHub. Nivåene:

- [ ] **`# requires:`-direktiv** (husets direktiv-stil à la `# load`) med:
      - versjonspinning (`plotnine==0.13`)
      - alias-kart for navne-mismatch (`sklearn`→scikit-learn, `PIL`→pillow, `cv2`→opencv)
      - eksplisitte kilder, se nivåene under
- [ ] **Python-kilder**, i økende dristighet:
      1. Pyodide-bundlede pakker (auto, virker i dag)
      2. PyPI rene Python-wheels via micropip (auto, virker i dag)
      3. Wheel-URL: `micropip.install('https://…/pakke.whl')` — inkl. wheels fra
         GitHub-releases (raw/objects.githubusercontent har CORS)
      4. GitHub-repo uten wheel (kun ren Python): hent zip → `pyodide.unpackArchive`
         → sys.path; direktivsyntaks f.eks. `# requires: github:bruker/repo`
      (Grense: pakker med ubygget C/Fortran kan ikke installeres i nettleseren.)
- [ ] **R-kilder**:
      1. repo.r-wasm.org-binærer (auto, virker i dag)
      2. **r-universe**: nesten alle CRAN- og GitHub-R-pakker finnes som wasm-binærer
         der — `webr::install(pkg, repos='https://<bruker>.r-universe.dev')`;
         direktivet kan ta `bruker/repo` og utlede universe-URL-en
      3. Egenbygde wasm-pakker med rwasm (som planlagt for nyere scatr)
      4. `require()`/`pkg::` trigges ikke av dagens `library()`-overstyring — dekkes
         av direktivet
- [ ] **`!pip install X`-høflighet**: preprosesser Jupyter-vane-linjer til
      micropip-kall (eller vis vennlig melding om at import auto-installerer)
- [ ] Tydelig feilmelding når en pakke ikke finnes som wasm (med peker til
      hva som faktisk støttes)

## Diverse / uavklart

- [ ] Pandas-basert GUI som egen modus (Hans' idé — holdes adskilt fra
      jamovi-modus, som skal forbli tro mot ekte jamovi/R)
- [ ] «Kjør»-knappen reinitialiserer Python-tolken hver gang (modus-uavhengig,
      eldre oppførsel) — datasett laget i jamovi overlever bytte til python-modus,
      men ikke et nytt «Kjør»-trykk der. Vurder varmere tolk-gjenbruk.
