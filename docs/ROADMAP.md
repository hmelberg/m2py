# Roadmap — safestat/openstat

*Levende dokument. Oppdatert 2026-07-09. Punktene er ikke forpliktelser, men
prioritert idéliste. Kilder: designdok/reviews fra jamovi 2.0 fase 1
(docs/PLAN_jamovi_jmv_engine.md, docs/jamovi-validation.md) + løpende samtaler.*

## jamovi-modus fase 2

**Figurer (størst synlig gevinst først):**
- [ ] Bygge nyere `scatr` fra jamovi sitt GitHub-repo som wasm (rwasm-verktøyet).
      Gir Bar/Box/Histogram/Line/Pareto som egne analyser med alle ~60
      stilopsjonene (error bars, titler, akser, legend, fonter).
- [ ] Pareto Plot tilbake i menyen (røk ut av fase 1 — finnes ikke i CRAN/wasm-scatr 1.0.1)

**Flere analyser (resten av jamovi-menyen):**
- [x] ANCOVA, Partial Correlation, logRegMulti/Ord, McNemar, Reliability, PCA, EFA (implementert 2026-07-09)
- [x] ANOVA: Friedman (implementert 2026-07-09)
- [ ] ANOVA: Repeated Measures, MANCOVA
- [ ] Factor: CFA (CFA krever at lavaan-kjeden fungerer i webR)
- [x] Frequencies: Log-Linear (implementert 2026-07-09)

**UI/layout (fase 3 — prioritet 1 per Hans 9/7: dialogene skal se bra ut og ha god struktur):**
- [x] **Dialog-layout fra jamovi sine u.yaml-kildefiler** (verifisert tilgjengelig på
      raw.githubusercontent.com/jamovi/jmv/master/jamovi/<analyse>.u.yaml): utvid
      spec-generatoren til å lese u.yaml og generere ekte jamovi-struktur —
      to-kolonne grid (LayoutBox cell column/row), gruppe-etiketter (Label),
      nøstede/innrykkede under-opsjoner (CheckBox children, f.eks. CI-bredde under
      CI-checkbox), enable-avhengigheter. Erstatter dagens håndkuraterte
      JMV_SECTIONS som oppleves rotete. (implementert 2026-07-09, branch jamovi-fase3-dialoger)
- [x] Visuell polish av panelet: luft, justering, konsistent typografi, rolleboks-høyder (implementert 2026-07-09)
- [x] Ikoner i analysemenyen (jamovi-lignende SVG-er) (implementert 2026-07-09)
- [x] Skjult toppmeny i jamovi-modus (datasettvelger ligger alt i jamovi-linjen;
      modusbytte/fil-handlinger må inn i jamovi-hamburgeren) (implementert 2026-07-09)
- [x] `Level`-opsjonstype i dialogene (f.eks. referansenivå i logistisk regresjon) (implementert 2026-07-09 som refLevels-velger med nivåer fra data)

**Teknisk gjeld fra fase 1-reviewene:**
- [x] Model Builder-UI for `blocks`/`modelTerms` (i dag syntetiseres én blokk av
      alle kovariater i linReg/logRegBin; ingen blokk-inndeling/interaksjonsledd) (implementert 2026-07-09: term-bygger med interaksjoner, post hoc-ledd og blokk-kall)
- [ ] Skille pliktige/valgfrie roller i «Velg variabler»-hintet (i dag kan hintet
      maskere reelle R-feil når en valgfri rolle står tom)
- [ ] Bilde-rekkefølgenøkler i `.jmv_serialize` (i dag ordre-basert matching mot
      captureGraphics; robust nok, men skjørt ved fremtidige jmv-endringer)
- [ ] `console.warn` ved bilde-underskudd i renderJmvResults (feilsøkingshjelp)
- [ ] Bayes factor-opsjonene (bf/bfPrior): krever wasm-bygg eller stub av `deSolve`
- [ ] Måle minnebruk på svake maskiner; `jamovi_v1` er nødbrems

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
      3. Egenbygde wasm-pakker med rwasm (som planlagt for nyere scatr i jamovi fase 2)
      4. `require()`/`pkg::` trigges ikke av dagens `library()`-overstyring — dekkes
         av direktivet
- [ ] **`!pip install X`-høflighet**: preprosesser Jupyter-vane-linjer til
      micropip-kall (eller vis vennlig melding om at import auto-installerer)
- [ ] Tydelig feilmelding når en pakke ikke finnes som wasm (med peker til
      hva som faktisk støttes)

## Diverse / uavklart

- [ ] Pandas-basert GUI som egen modus (Hans' idé — holdes adskilt fra
      jamovi-modus, som skal forbli tro mot ekte jamovi/R)
