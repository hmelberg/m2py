# Plan: bygg statiske datafiler fra generatormotoren

Status: **F1 + F2 implementert og verifisert** (2026-06-08). Additivt — rører
**ikke** den eksisterende lazy genereringen i appen. Mål: produsere et
gjenbrukbart, realistisk øyeblikks-datasett (~100 000 personer) som *kan* lastes
inn senere i stedet for å generere på nytt hver gang.

## Implementert så langt

- [mockdata_export.py](../mockdata_export.py) — driver `MockDataEngine` som
  appens `import`-kommando og bygger tabellene. F1: `build_person` /
  `build_person_year`. F2: `build_entity_table` (jobb/kjoretoy/kurs),
  `build_npr_table`, og `build_all`.
- [build_static_data.py](../build_static_data.py) — CLI som skriver
  `static_data/*.parquet` + `microdata.duckdb` + `person.csv` + `manifest.json`.
- [export_data.html](../export_data.html) — in-browser variant (F1) via Pyodide.
- **Pivot:** maskinen har likevel et ekte Python (`C:\ProgramData\anaconda3`,
  Py 3.13 + numpy/pandas/pyarrow/duckdb), så lokal CLI er primær byggevei;
  in-browser-siden beholdes som alternativ. Se [[project_no_local_runtime]].
- **Verifisert:** aldersprofil på lønn (topp 45–54), kjønnsgap (~89 %),
  inntekt↔formue (Spearman 0.21), entydige FK-er (0 foreldreløse rader),
  dekningsgrad jobb/kjøretøy/kurs = 72/56/45 % (matcher `p_has`).
- **Kjent begrensning (akseptert):** innen-person tidsvariasjon er svak — motoren
  er en tverrsnitts-snapshot-generator; `as_of` flytter kun det deterministiske
  snittet (alderskurve/trend), ikke det idiosynkratiske trekket. ~52 % har
  identisk lønn alle år. Valgt: aksepter for nå (se F4-alternativ).

## Beslutninger (avklart med bruker 2026-06-08)

- **Format:** Parquet per tabell (primær) + én **DuckDB**-fil som bunter alt med
  fremmednøkler. CSV-kopier kun av små/kjernetabeller for øyekontroll.
- **Kjøring:** **In-browser eksportside** som gjenbruker appens Pyodide-bunt
  (ingen lokal Python-installasjon nødvendig).
- **Omfang v1:** Full relasjonell modell — `person`, `person_year`, `jobb`,
  `kjoretoy`, `kurs`, `npr`, `trafikkulykke`, `kommune`.

## Nøkkelinnsikt: kjør den eksisterende motoren, ikke reimplementer

All realisme og kryss-variabel-korrelasjon ligger allerede i koden og er
**deterministisk per `unit_id`**:

- `mockdata_core.latent_z(unit_id)` — delt latent N(0,1) per person som binder
  lønn ↔ formue ↔ utdanning.
- `unit_seed(unit_id, salt)` — reproduserbar RNG per (person, formål).
- `mockdata_realism` — 4-lags realisme (hard_rules → effects → stratified →
  by_date/trend) på 58 variabler; `as_of`-dato styrer trend/regime over tid.
- `MockDataEngine` (m2py.py:2014) — `_generate_variable_values`,
  `_generate_multi_record_entity`, `_generate_npr_variable`, `_generate_panel`,
  `_person_universe`. Drivere (`age`/`gender`/`education`/`latent_z`)
  syn-genereres deterministisk når de mangler.

Eksportøren instansierer `MockDataEngine(default_rows=100000)` og materialiserer
kolonnene motoren produserer. Holder seg automatisk i synk med
`variable_metadata.json`.

## Skjema: relasjonell stjerne (speiler microdata.no sin enhetsmodell)

| Tabell | Granularitet | Innhold |
|---|---|---|
| `person` | 1 rad/person (100k) | Konstante (`temporalitet=Fast`) Person-variabler: id, fødselsår-mnd, kjønn, … |
| `person_year` | person × år (f.eks. 2010–2023) | Tidsvarierende Person-variabler: inntekt, formue, bostedskommune, utdanningsnivå-ved-tid |
| `jobb` | 1 rad/arbeidsforhold | FK → person (`ARBEIDSFORHOLD_PERSON`), ~0.72 dekning, 1–5 per person |
| `kjoretoy` | 1 rad/kjøretøy | FK → person (`KJORETOY_KJORETOYID_FNR`), ~0.55 dekning |
| `kurs` | 1 rad/kurs | FK → person (`NUDB_KURS_FNR`) |
| `npr` | 1 rad/behandlingsopphold | FK → person (`NPRID`), episodemodell |
| `trafikkulykke` | 1 rad/ulykke (+ person-kobling) | enhetstype Trafikkulykke / Person i trafikkulykke |
| `kommune` | 1 rad/kommune | Dimensjon (112 Kommune-variabler) |

Tilordning drives av metadata: `enhetstype` → tabell (via
`_ENHETSTYPE_TO_ENTITY`), `temporalitet` → person vs. person_year
(Fast → dim, Akkumulert/årlig → fakta).

## Genereringsrekkefølge (viktig for konsistens)

1. **Personunivers:** `unit_id = 1..100000`.
2. **Drivere først:** materialiser `BEFOLKNING_FOEDSELS_AAR_MND` (alder),
   `BEFOLKNING_KJOENN`, utdanningsnivå — slik at lagrede verdier er *de samme*
   som mater nedstrøms variabler.
3. **Konstante person-variabler** → `person`-tabellen (context_df = drivere).
4. **Tidsvarierende person-variabler** → `person_year`: løkke over år, kall
   generering med `as_of=år` (trend/by_date slår inn).
5. **Multi-record-enheter** (`jobb`, `kjoretoy`, `kurs`) via
   `_generate_multi_record_entity` — bygger 1:N med FK til person.
6. **NPR/trafikkulykke** via episodegeneratorene.
7. **Kommune-dimensjon.**
8. Skriv Parquet → bunt DuckDB → CSV for kjernetabeller.

Sparsomme variabler (`_SPARSE_FRACTION`) gir naturlig NULL for delpopulasjoner.

## Leveranser

- `export_data.html` — eksportside. Gjenbruker `loadPyodideAndM2py`-mønsteret
  (Pyodide 0.29.3, numpy/pandas/scipy, `micropip.install("pyarrow")`), fetcher
  `m2py.py`/`mockdata_*`/`variable_metadata.json`, kjører eksport-Python,
  tilbyr nedlasting.
- `mockdata_export.py` — ren Python-modul (importerbar i Pyodide *og* lokalt
  senere) som bygger hver tabell fra `MockDataEngine`. Holdes UI-fri.
- Output i `static_data/`: `person.parquet`, `person_year.parquet`,
  `jobb.parquet`, … + `microdata.duckdb` + CSV av `person`/`kommune`.
- DuckDB-bunting i nettleser via **duckdb-wasm** (leser Parquet-buffere →
  `CREATE TABLE AS SELECT` → eksporter `.duckdb`). Fallback: lever Parquet +
  generert `load.sql`/`schema.sql`.

## Reproduserbarhet og versjonering

- Determinisme kommer gratis fra `unit_id`-hashing; ingen global `Math.random`.
- Stemple output med `{n_persons, year_range, metadata_version, generated_at}`
  i en `manifest.json` ved siden av filene (tidsstempel settes i JS, ikke i
  Pyodide — `Date.now()` finnes ikke i scriptmotoren her).

## Ytelse / risiko

- `generate_numeric`/`generate_categorical` er vektorisert over hele arrays →
  100k går greit per variabel.
- `person_year` = 100k × år × tidsvariabler kan bli stort; begrens
  tidsvariabel-settet og årsspennet (konfigurerbart). Parquet håndterer bredt/
  sparsomt godt; CSV ville sprengt.
- NPR/multi-record bruker løkker → vurder chunking hvis tregt.
- duckdb-wasm-bunting i nettleser er det mest usikre steget; Parquet+SQL-fallback
  fjerner blokkeringen.

## Faseplan

1. **F1 — kjerne:** ✅ `person` + `person_year`. Parquet + CSV. Verifisert.
2. **F2 — enheter:** ✅ `jobb`, `kjoretoy`, `kurs`, `npr` med FK-er + DuckDB-bunt
   + `manifest.json`. Verifisert (0 foreldreløse rader).
3. **F3 — pakking:** delvis. Lokal CLI dekker Parquet+DuckDB+manifest. Gjenstår:
   oppdater `export_data.html` til å inkludere F2-tabellene + (valgfri)
   duckdb-wasm-bunting hvis in-browser-bygg ønskes.

### Egne registre bygget direkte i eksportøren (motoren modellerer dem ikke)

- ✅ **`trafikkulykke` + `person_i_trafikkulykke`:** ulykkesregister +
  M:N-bro (FK til både `trafikkulykke` og `person`). `build_trafikkulykke`.
  Verifisert: begge FK-er, bro-rader == `TRAFULYK_ANTALL_PERS`, kjønn 100 %
  konsistent med person-tabellen.
- ✅ **`malepunkt` (Elhub):** målepunkt-register, 1:N til person via
  `ELHUB_PERS_MALEPUNKTID_FNR`. `build_malepunkt`. Forbruk/produksjon
  synt-genereres (lognormal husholdning ~18 MWh; produksjon hurdle ~8 %),
  siden metadata mangler `std`. Pris­område/type matcher metadata-fordelingen.

- ✅ **`kommune` + `kommune_year` (KOSTRA):** kodelistenøklet dimensjon (665
  kommuner, dekker alle bostedskoder på tvers av reform-epoker) + KOSTRA-fakta
  (112 variabler). `build_kommune`. Befolkning utledes fra hvor de syntetiske
  personene bor → `kommune` blir forelder for `person_year.BOSATT_KOMMUNE`
  (0 foreldreløse). Lønnsutgifter skalerer med befolkning; per-innbygger-tall
  bruker metadata-snitt. **Modellbasert, ikke kalibrert mot ekte KOSTRA-nivå**
  (metadata hadde bare placeholder min/max). Verifisert: realistiske
  befolkningstall (Oslo ~667k), alle FK-er rene.

- ✅ **Bred Person-tabell:** `build_person_wide` materialiserer alle
  Person-variabler (Fast + Akkumulert + Tverrsnitt; Forløp ekskludert) som ett
  tverrsnitt ved en referansedato — 438 kolonner, 0 skip ved test. CLI:
  `--person-scope all`. Bruker en slank driver-kontekst for fart; drivere
  (fødselsdato/kjønn/utdanning) genereres med samme `as_of`-konvensjon som
  resten, så alder er konsistent på tvers av tabeller. Inkluderer 10
  `*_FNR`-familielenker (far/mor/ektefelle…) som peker til ekte person-IDer.

- ✅ **Bred latent struktur (fler-faktor copula):** `apply_latent_structure`
  gir hver person deterministiske latente faktorer (ses=`latent_z`, helse,
  urban, familie + reell alder) og **omstokker** kvantitetskolonner slik at de
  rang-korrelerer med faktorene. **Marginaler bevares eksakt** (permutasjon av
  eksisterende verdier — verifisert 0 endrede). Realisme-ankrene (inntekt/formue
  med alderskurver) stokkes IKKE, men de uavhengige beløpsvariablene justeres mot
  *samme* `latent_z` ankrene bruker, så de korrelerer med inntekt/formue.
  Pengeklassifisering (`_norway_classify_money_demo`) styrer fortegn (inntekt/
  formue +, sosialhjelp/bostøtte −, pensjon → alder, student → ung, uføre →
  helse). 128 kolonner omstokket; nominale koder/drivere/FK-er urørt. CLI på som
  standard ved `--person-scope all`; av med `--no-latent-structure`.

- ✅ **Dynamisk person_year (livsløps-mikrosimulering):**
  `build_person_year_dynamic` gir hver person en årlig tilstandsmaskin
  (utdanning → sysselsatt ↔ arbeidsledig → ufør → pensjonist → død) med
  alders-/SES-/helse-avhengige overgangshasarder. Motorens årlige lønn (alders-
  kurve + latent) brukes som *potensiell* lønn; tilstanden gater den og legger på
  AR(1)-transitoriske sjokk. Verifisert @100k: inntekts-autokorrelasjon 0.97 →
  **0.93** (ikke lenger frosset), uførhet dropper lønn til ~5 % men uføretrygd
  løfter totalinntekt til ~60 %, pensjon ved 67, dødelighet. Nye kolonner:
  `alder`, `livsstatus`, `DAGPENGER`, `UFORETRYGD`, `ALDERSPENSJON`. Tverrsnittet
  (person @2023) synkes mot panelets referanseår (0 avvik). CLI: `--dynamic-panel`.

- ✅ **Livsløps-koblede enheter (jobb + kjøretøy over tid):**
  `simulate_life_states` deler tilstands-trajektorien med både panelet og
  enhetene. `build_jobb_coupled`: hver jobb-rad er et arbeidsforhold-spell med
  `ARB_START`/`ARB_SLUTT` som følger personens sysselsatte år (jobbskifter,
  pågående jobber = SLUTT NaN). Verifisert: 0 jobbholdere som aldri var
  sysselsatt, start≤slutt = 1.0, ~2 jobber per sysselsatt over 9 år.
  `build_kjoretoy_temporal`: eierperioder (`EIER_FRA_AAR`/`_TIL_AAR`) med utskifting
  (~6 års hold), flere/nyere biler for høy-SES (eiere snitt-SES +0.21 vs −0.02).
  Brukes automatisk når `--dynamic-panel` er på.

- ✅ **Koder vs. labels + dtype-troskap (microdata-konvensjon):** dataene lagrer
  *koder*, ikke labels (labels ligger i `value_labels`). microdata.no lagrer
  alfanumeriske variabler som **streng-koder med ledende nuller** (`kommune ==
  '0301'`, `kjonn == "1"`, `invkat == 'A'` — bekreftet av eksempel-scriptene og
  [ANALYSIS_summarize_if_condition.md](ANALYSIS_summarize_if_condition.md)).
  `normalize_for_microdata`:
  - **Troskap:** kolonner med kodeliste lagres som streng-koder via kodeboka
    (gjenoppretter ledende nuller). Retter inkonsistensen der kommunekoder lå som
    `float 301.0` → `'0301'`; kommune-FK kjøres nå på streng (ingen CAST).
  - **Størrelse:** ekte numeriske kolonner (Numerisk) nedkastes int64→int16/32 og
    float64→float32 (~58 % mindre numerisk fotavtrykk, semantikk uendret); Parquet
    skrives med zstd. Streng-kodene røres ikke (allerede dictionary-kodet).
  Merk: int-koding av alfanumeriske koder ble *forkastet* — det ville brutt
  ledende nuller og bokstavkoder, og scriptene matcher mot `'0301'`.

- ✅ **Gyldighetsperiode i kodeboka (Q1):** `variables`-tabellen har nå
  `valid_from`/`valid_to` parset fra beskrivelsen (495 variabler med endelig
  vindu). Statiske filer er en *cache* for 2015–2023; utenfor vinduet bør
  konsumenten falle tilbake til motor-generering (motoren støtter vilkårlig dato).
- ✅ **Avdøde i registeret (Q2):** `BEFOLKNING_DOEDS_DATO` er nå null for levende,
  satt for døde (panel-dødsfall i vinduet; en konfigurerbar avdød-bestand døde før
  panelet, ingen person_year-rader). `import kjonn` returnerer alle inkl. døde;
  filtrer levende = `DOEDS_DATO IS NULL`. CLI: `--dead-fraction 0.4` (skalert ned
  fra FDBs ~0.5; avdød-bestanden er lett — bare kjønn/fødsel/død, resten NaN).
- ✅ **Avledede kodebøker (Q3):** `fylke` (fylke_nr→navn på tvers av reform-epoker),
  `icd10_kapittel` (bokstav→kapittel for ICD-rollup), `kommune_crosswalk`
  (pre2020→2020→2024, 425 rader, fra `build_kommune_eras`). Mønster: små
  oppslagstabeller ved siden av `value_labels` — kopier formen for å legge til
  flere. Kodeboka er komplett ift. metadata (lange koder med); ekte fulle
  kodelister er F5-berikelse.

### Gjenstående

- **Mulig utvidelse:** `malepunkt_year` (Akkumulert forbruk per år 2020→) og
  ekte KOSTRA-kalibrering (via F5-metadata-berikelse).
- **Ytelse:** bred person ≈ 14 min @100k (per-enhet Python-løkker i motorens
  pengegeneratorer). OK for engangsbygg; kan optimaliseres senere ved
  vektorisering i m2py.

### Senere faser

4. **F4 — longitudinell realisme (valgfri):** dekomponer numeriske variabler i
   permanent person-komponent + liten transitorisk årssjokk, så inntekt
   varierer realistisk år-til-år. Egen lag i eksportøren; rører ikke appen.
5. **F5 — metadata-berikelse fra microdata.no:** hent fordelinger/verdiområder/
   temporalitet fra discovery-sidene (38 listesider +
   `/discovery/variable/<bank>/<v>/<NAVN>`) for å gi flere variabler ekte
   `realism`-blokker i stedet for generisk fallback.
6. **F6 — «last inn fra fil» i appen:** sti så datasettene kan brukes i stedet
   for live-generering.
