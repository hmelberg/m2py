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
- [ ] ANOVA: Repeated Measures, ANCOVA, MANCOVA, Friedman
- [ ] Regresjon: Partial Correlation, multinomisk og ordinal logistisk
- [ ] Factor: Reliability, PCA, EFA, CFA (CFA krever at lavaan-kjeden fungerer i webR)
- [ ] Frequencies: McNemar (paired), Log-Linear

**UI/layout:**
- [ ] Skjult toppmeny i jamovi-modus (datasettvelger ligger alt i jamovi-linjen;
      modusbytte/fil-handlinger må inn i jamovi-hamburgeren)
- [ ] Ikoner i analysemenyen (jamovi-lignende SVG-er)
- [ ] Pixel-likere opsjonspaneler fra jamovi sine u.yaml-layoutfiler
- [ ] `Level`-opsjonstype i dialogene (f.eks. referansenivå i logistisk regresjon)

**Teknisk gjeld fra fase 1-reviewene:**
- [ ] Model Builder-UI for `blocks`/`modelTerms` (i dag syntetiseres én blokk av
      alle kovariater i linReg/logRegBin; ingen blokk-inndeling/interaksjonsledd)
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

## Diverse / uavklart

- [ ] Pandas-basert GUI som egen modus (Hans' idé — holdes adskilt fra
      jamovi-modus, som skal forbli tro mot ekte jamovi/R)
