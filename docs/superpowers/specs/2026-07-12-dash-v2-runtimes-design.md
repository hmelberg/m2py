# Dash v2 — pyodide- og webR-runtime (fase 2)

**Dato:** 2026-07-12
**Status:** Design godkjent i brainstorm, klar for implementasjonsplan
**Bygger på:** `2026-07-11-dash-v2-design.md` (§9 «Senere faser»). Merk: §9 antok
at pyodide kjørte i worker — det stemmer ikke; pyodide kjører på hovedtråden i
safestat (strict-worker brukes kun for krypterte kilder). webR er derimot ekte
async (worker bak kanal).

## 1. Mål

Dashboardet skal kjennes likt i brython-, pyodide- og R-modus: samme API-overflate
(`dashboard(tittel, layout)`, `d.add(...)`/`d$add(...)`, `d.controls(...)`,
samme widget-typer: slider, dropdown, checkbox, textfield, numberfield, play),
samme utseende, samme URL-state-deling. DuckDB styrer datasettene i bunn, men
brukeren starter i ett av de tre språkene.

Bakoverkompatibilitet er **ikke** et krav (ingen eksterne brukere ennå).

## 2. Besluttede veivalg (fra brainstorm)

1. **Pyodide: egen adapter-kopi** (`pyodide/dash.py`), ikke delt fil med
   brython. Callbacks krysser grensen som PyProxy og kalles direkte fra JS ved
   widget-endring (hovedtråd — ingen kø, ingen serialisering av funksjoner).
2. **R: «deklarer i R, bygg i JS».** `webr/dash.R` samler deklarasjoner i et
   R-side-register; en JS-glue bygger dashboardet etter script-kjøringen og
   re-kjører funksjonskort async via `evalR` med kø, siste-vinner-vern og
   busy-tilstand. Ingen progressiv kortbygging.
3. **Delt logikk flyttes ned i motoren:** norsk tallformat + delta-beregning
   (number-payload blir rå) og en ny strukturert tabell-payload. `html`-
   tabellvarianten beholdes. Widget-inferens forblir i adapterne
   (språkspesifikk typesemantikk).
4. **R-inferens er typebasert** (speiler Python der det gir mening, se §5.2).

## 3. Motorendringer: `js/dash.js`

### 3.1 Number-payload v3 (erstatter v2 — ingen bakoverkompat)

Adapterne sender rå verdier; motoren formaterer:

```
{kind:"number", value, unit, fmt, ref, bra}
```

- Motoren beregner visningstekst (norsk gruppering med smalt hardt mellomrom
  U+202F, komma som desimalskille) og delta mot `ref` (pil, fortegn med ekte
  minustegn, god/dårlig etter `bra`). Dagens `_fmt_norsk`/`_delta`-logikk i
  brython/dash.py flyttes hit og slettes der.
- `fmt` er en python-format-spec-streng; JS-tolkeren dekker delmengden som
  faktisk brukes: gruppering (`,`), faste desimaler (`.Nf`), prosent (`%`),
  og kombinasjoner (`,.1f`). Ukjent spec → fall tilbake til default-format
  (aldri kast).
- Fikser kjent inkonsistens: U+00A0 (JS) vs U+202F (python) i tusenskille —
  én implementasjon, U+202F.
- Ikke-endelige verdier (nan/inf): adapterne sender fortsatt tekst-payload
  (som i dag) — motoren trenger ikke gjette.

### 3.2 Strukturert tabell-payload

Ny variant ved siden av `html`-varianten:

```
{kind:"table", columns:["navn", ...], rows:[[...], ...]}
```

Motoren bygger og styler tabellen selv (samme `.dash`-tabellutseende: zebra,
sticky header, scroll). Radbygging er ren logikk → node-testes. `cols` for
auto-span avledes av `columns.length`. Python-adapterne kan fortsatt sende
`html` der `to_html` er gratis; R og brython-Series bruker strukturert.

### 3.3 Busy-API

`Dash.setBusy(cardId)` slår på eksisterende `dash-card--loading`-shimmer til
neste `updateCard`. Brukes av R-gluen under async re-kjøring; brython/pyodide
trenger den ikke (synkrone kall).

## 4. Pyodide-adapter: `pyodide/dash.py`

Egen kopi med samme offentlige API som brython-adapteret. Forskjeller:

- **FFI:** `import js` i stedet for `from browser import window`; callbacks
  pakkes med `pyodide.ffi.create_proxy` før de sendes til `Dash.addCard`/
  `Dash.addControls`. Modul-nivå register over utdelte proxies destrueres ved
  neste `dashboard()`-kall (hindrer lekkasje over re-runs).
- **Payload-dispatch med ekte biblioteker:**
  - plotly `Figure` → `fig.to_json()` (NaN-trygg) → `{kind:"figure", spec}`
  - matplotlib `Figure`/`Axes` (inkl. `df.plot()`-retur) → `savefig` til PNG
    data-URI → `{kind:"image"}`; figsize/DPI settes ved render slik at bildet
    fyller innholdsflaten (spec v1 §7)
  - numpy-skalarer normaliseres til `int`/`float` før number-payload
  - `DataFrame` → `to_html` (html-variant); `Series` → strukturert tabell
- **Ellers identisk semantikk:** print-fangst, error-kort, K2 `initialValues`,
  delte kontroller, widget-inferens (tuple→slider osv.).

### 4.1 Integrasjon i python-modus (index.html)

- Lazy last ved behov: når scriptet importerer `dash` — hent `pyodide/dash.py`
  og skriv den til pyodides filsystem slik at `import dash` virker; last
  `js/dash.js` (script-tag, samme fil som brython bruker) og Plotly om de
  ikke alt er lastet.
- Samme DOM-vern som brython-stien: `purgePlots` + tøm `#outputArea` FØR
  kjøring; etterpå, hvis `.dash` finnes i outputArea, append tekstoutput i
  stedet for `renderOutput` sin tømming (som ellers ville slettet dashboardet).

## 5. R-adapter: `webr/dash.R` + JS-glue

### 5.1 R-siden (`webr/dash.R`)

Injiseres i R-økten (evalR av filens innhold) første gang et script bruker
dash. Definerer:

- `dashboard(title = "", layout = NULL)` → miljø-objekt med `$add(...)` og
  `$controls(...)` (samme kall-følelse som Python-adapternes `d.add`).
- Widget-hjelperne `slider()`, `dropdown()`, `checkbox()`, `textfield()`,
  `numberfield()`, `play()` med samme signaturer som Python.
- Et R-side-register (miljø) med dashboards, kort (inkl. funksjonsobjekter og
  parameternavn via `formals()`), widget-specs og delte kontroller.
- `dash_run(cid, values_json)`: konverterer råverdier (jsonlite) til R-verdier
  (dropdown-indeks → originalverdi osv.), kaller kortets funksjon, og:
  - retur er tall/streng/data.frame → payload-JSON (number rå / markdown /
    strukturert tabell)
  - retur er ggplot → `print()` (tegner til enhet); base-plot tegnes av
    funksjonen selv → gluen bruker fanget bilde
  - feil → `tryCatch` → `{kind:"error"}`-payload
- Statiske `add(x)` (tall, streng, data.frame) beregner payload umiddelbart
  R-side og legges i registeret som literal. Statiske plott-objekter
  registreres som kjørbare (realiseres via samme capture-sti som funksjonskort).

### 5.2 Implisitt kwarg→widget-mapping i R (typebasert)

| verdi | widget |
|---|---|
| numerisk vektor lengde 2–3 | slider (min, max[, steg]) |
| character-/factor-vektor | dropdown |
| numerisk vektor lengde >3 | dropdown |
| `TRUE`/`FALSE` (lengde 1) | checkbox |
| enkelt tall | tallfelt |
| enkelt streng | tekstfelt |
| eksplisitt widget | som angitt |

Kant (dokumentert): numerisk dropdown med 2–3 valg krever eksplisitt
`dropdown()` — samme unntak som Python-tuppelen.

### 5.3 JS-gluen

Egen liten modul (`js/dash-webr.js`) eller seksjon ved R-kjøreløypa:

- Etter `runHybridR`: sjekk om registeret finnes (evalR), hent det som JSON
  (jsonlite er allerede i bruk i R-stien), bygg dashboardet via `Dash.create`/
  `addCard`/`addControls`. Literal-payloads rendres direkte; kjørbare kort
  monteres i loading-tilstand og realiseres via første `dash_run`.
- **Re-kjøring:** widget-endring → enqueue `evalR` av
  `dash_run(cid, values_json)` i en Shelter-`captureR` (tekst + plott fanges).
  Payload-JSON fra retur; fanget plott-bilde overstyrer som `{kind:"image"}`.
  Per-kort siste-vinner-vern (nyere forespørsel gjør eldre resultat dødt),
  `Dash.setBusy(cid)` mens kjøringen pågår. Shelter-allokeringer frigjøres per
  kall (eksisterende mønster i R-stien).
- **Delte kontroller:** gluen kjenner hvert korts parameternavn fra registeret
  og re-kjører kortene med navneoverlapp — samme regel som brython.
- **K2/URL-state:** motoren gjenoppretter widget-verdier fra `#…;ds=`; gluen
  leser `Dash.initialValues(cid)` før første `dash_run`, så første render
  matcher delt lenke. Ingen R-side-endring nødvendig.
- Play-widget som tikker fortere enn evalR rekker: mellomframes droppes av
  siste-vinner-vernet (akseptert).

## 6. Feilhåndtering

- Pyodide: exception i kortfunksjon → `{kind:"error"}`-kort (rød stripe),
  dashboardet ellers uberørt — som brython.
- R: feil i kortfunksjon fanges i `dash_run` (tryCatch) → error-payload;
  evalR-/kanalfeil på gluenivå → error-kort + `console.warn`.

## 7. Rydding og slanking (samme arbeid)

- `brython/dash.py`: `_fmt_norsk`, `_fmt_default_norsk`, `_delta`,
  `_number_payload`-formateringen slettes; number-payload sendes rå (§3.1).
- Series-repr-fallbacken i brython erstattes med strukturert tabell-payload
  der det er mulig (tetter kjent hull fra oppfølgingslisten).

## 8. Testing og verifisering

- **Node-tester:** fmt-tolkeren (python-format-spec-delmengden), delta-
  beregning, strukturert tabell-radbygging (ren halvdel av dash.js).
- **Nye eksempler:** ett pyodide-dashboard og ett R-dashboard med samme
  innhold som et eksisterende bry-eksempel, så likheten på tvers er synlig.
- **Browser-røyk samlet til slutt** (token-økonomi): pyodide-eksempel,
  R-eksempel, bry17–22-regresjon (payload-kontrakten er endret!), output-only,
  lys/mørk tema, URL-state-deling.
- safestat leder; openstat synkes etterpå etter vanlig konvensjon
  (safestat-først-sync, `sync_check.sh`).

## 9. Bevisste avgrensninger

- Ingen progressiv kortbygging i R — dashboardet vises når scriptet er ferdig.
- DuckDB-dashboards i pyodide/R er utenfor scope (brython + bry22-mønsteret
  dekker behovet inntil videre).
- Ingen bakoverkompat på payload-kontrakten; brython-adapter og alle
  eksempler oppdateres i samme bølge.

## 10. Suksesskriterier

1. Samme dashboard-script-idiom gir visuelt likt resultat i brython-, python-
   og R-modus (eksemplene i §8 demonstrerer det).
2. Widget-endring i R-modus gir oppdatert kort med shimmer underveis og uten
   stale render ved raske endringer.
3. `pyodide/dash.py` og `webr/dash.R` bygger aldri kort-DOM selv — alt går
   via `Dash.*` (grensesnitt-disiplin som i v1).
4. Netto Python-linjer i brython/dash.py går ned (formatering flyttet til JS).
