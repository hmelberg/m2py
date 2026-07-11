# Dash v2 — objektbasert dashboard med interact-modell

**Dato:** 2026-07-11
**Status:** Design godkjent i brainstorm, klar for implementasjonsplan
**Erstatter:** Dashboard-visningen fra `2026-07-09-dashboard-design.md` (slettes, se §8)

## 1. Mål og motivasjon

Dagens dashboard (kommentar-direktiver `#input`/`#%%` + `dashboard.js`) har for grove
layout-primitiver (halv/full bredde, tvungen lik bredde i rader, ujevne korthøyder,
bitmap-plott med dødrom) og et forfatterskap som verken er helt enkelt eller særlig
kraftig. Målet med v2:

1. **Lett:** Et eksisterende script blir dashboard ved å legge til få linjer
   (`dash = dashboard("Navn")` + `dash.add(x)` per objekt).
2. **Kraftig nok:** Interaktivitet (funksjon + kwargs → kontroller) og presis layout
   (mosaikk-streng) er tilgjengelig, men alltid valgfritt.
3. **Proft utseende by default:** Designet auto-layout og gjennomarbeidet CSS gjør
   at den late stien ser bra ut uten at brukeren lærer noe.
4. **Mindre kodebase:** Ny motor + sletting av gammel gir netto færre linjer og
   færre spesialkoblinger i `index.html`.

Bakoverkompatibilitet er eksplisitt **ikke** et krav (ingen eksterne brukere ennå;
egne eksempler skrives om).

## 2. Besluttede veivalg

- **Ren erstatting:** gammel dashboard-motor, -visning og -CSS slettes. Ingen
  parallelle systemer, ingen oversettelse av gammel direktiv-syntaks.
- **Brython først:** fase 1 dekker kun Brython-modus. Pyodide/R (og evt. SQL) er
  senere faser, men arkitekturen legges til rette nå (se §3 og §9).
- **Ikke egen visningsmodus:** et dashboard er et script hvis output er et
  dashboard. Deling/«uten kode» bruker eksisterende output-only-visning.
  Spesialkoblingene for dashboard-visning i `index.html` slettes.
- **Én verb-API:** alt legges til med `add()`; dispatch på objekttype.
- **safestat leder,** openstat synkes etterpå etter vanlig konvensjon.

## 3. Arkitektur: JS-motor + tynne runtime-adaptere

To lag med et rent payload-grensesnitt mellom seg:

### 3.1 Motor: `js/dash.js` (ny)

Språknøytral. Eier alt visuelt og alt UI-state:

- Mosaikk-parsing → CSS `grid-template-areas` (§6)
- Auto-layout når ingen mosaikk er angitt (§6.3)
- Kort, KPI-fliser, widget-bygging, toppstripe for delte kontroller
- Tilstander per kort: loading (shimmer), running, error
- Debounce/kø for widget-endringer (brukes ikke av Brython-stien, men bor her
  for fremtidige worker-runtimes)

Internt API (kalles av adaptere, aldri av brukere):

```js
Dash.create({title, layout})                 // -> dashId, monterer i output-området
Dash.addCard(dashId, {content, area, title, controls, onChange})
Dash.updateCard(cardId, payload)             // nytt innhold etter re-kjøring
Dash.addControls(dashId, controls, onChange) // delte kontroller i toppstripe
```

`content`/`payload` er typede objekter — motoren vet ikke hvor de kom fra:

```
{kind: "markdown", text}      {kind: "table", html}
{kind: "number", value, unit} {kind: "image", src}   // matplotlib/data-URI/URL
{kind: "text", text}          {kind: "node", el}     // escape-luke (kun Brython)
{kind: "error", message}
```

Som i v1 skilles en ren, Node-testbar halvdel (mosaikk-parsing, auto-layout-plan,
widget-spec-bygging) fra DOM-halvdelen.

### 3.2 Adapter fase 1: `dash.py` (Brython-modul, lazy-lastet)

Tynn. Implementerer bruker-API-et (§4), gjør type-dispatch (§5), konverterer
objekter til payloads, og wirer funksjons-rekjøring som direkte kall (Brython
kjører i siden — ingen serialisering, ingen kø). Matplotlib-figurer hentes via
eksisterende matplotlib-shim i brython-engine.

**Disiplin:** `dash.py` bygger aldri kort-DOM selv; alt går via `Dash.*`-API-et.
Det er dette som gjør Pyodide/R-adaptere mulige senere uten motorendringer.

## 4. Bruker-API

```python
dash = dashboard("Salg 2026")                 # valgfritt: layout="""...""" (§6)

dash.add(x)                                   # type-dispatch, se §5
dash.add(x, title="Fordeling")                # valgfri korttittel
dash.add(x, at="plot")                        # plassering i mosaikk-område

dash.add(hist, art=["setosa", "versicolor"], bins=(5, 50))
#   funksjon + kwargs -> interaktivt kort; kontroller bor I kortet

dash.add(hist, bins=slider(5, 50, step=5, label="Antall bins"))
#   eksplisitt widget når kortformen ikke strekker til

dash.controls(år=(2020, 2026), region=["Nord", "Sør"])
#   delte kontroller i toppstripe; re-kjører alle funksjonskort som har
#   parameter med samme navn
```

Alle kwargs er valgfrie. Læringstrappen er: `add(x)` → `title=` → funksjon+kwargs
→ eksplisitte widgets → `layout`/`at=`. Ingen trinn ugyldiggjør forrige.

### 4.1 Interaktive kort (funksjonsgrenen)

- Funksjonen kalles med default-verdier ved `add()` (første render).
- Hver kontroll-endring kaller funksjonen på nytt med gjeldende verdier og
  erstatter kortets innhold via `updateCard`. Returverdien type-dispatches som
  i §5 (en funksjon kan returnere figur, df, tall, streng...).
- `print()`-output fra funksjonen fanges og vises som tekst-payload dersom
  funksjonen returnerer `None` (så `print(len(sub))`-stilen virker).
- Exception i funksjonen → `{kind:"error"}`-payload vist i kortet (rød stripe +
  melding), dashboardet ellers uberørt.
- Avhengigheter er eksplisitte (funksjonens parameternavn) — ingen tekstbasert
  re-run-analyse à la v1 `planReruns`.

### 4.2 Implisitt kwarg→widget-mapping

| kwarg-verdi | widget | default-verdi |
|---|---|---|
| liste/array | nedtrekksmeny | første element |
| tuple `(min, max)` eller `(min, max, step)` | slider | min |
| `bool` | checkbox | verdien selv |
| `str` | tekstfelt | verdien selv |
| `int`/`float` | tallfelt | verdien selv |
| eksplisitt widget (§4.3) | som angitt | widgetens default |

### 4.3 Eksplisitte widgets

`slider(min, max, step=, default=, label=)`, `dropdown(*valg, default=, label=)`,
`checkbox(default=, label=)`, `textfield(default=, label=)`, `numberfield(...)`.
Samme navn som brukeren kjenner fra v1 der de fantes. Én implementasjon i
motoren; Python-siden lager bare widget-specs.

## 5. `add(x)` — dispatch-tabell

| `x` | kort | payload |
|---|---|---|
| `str` | markdown-rendret tekst | `markdown` |
| `str` som er URL/sti til bilde eller `data:image/...` | bilde | `image` |
| `int`/`float` | KPI-flis (`title=` som etikett, `unit=` valgfritt) | `number` |
| DataFrame/Series | tabell (`to_html`-basert, stylet av motoren) | `table` |
| matplotlib Figure/Axes (inkl. returverdi fra `df.plot()`) | plott | `image` |
| callable | interaktivt kort (§4.1) | (funksjonens retur, rekursivt) |
| DOM-element | settes inn direkte (escape-luke) | `node` |
| annet | `repr()` som tekst | `text` |

Rekkefølgen over er også prioritetsrekkefølgen ved tvil (f.eks. sjekkes
bilde-heuristikken før generell streng→markdown).

## 6. Layout

### 6.1 Mosaikk-streng

```python
dash = dashboard("Salg", layout="""
    kpi1 kpi2 kpi3 kpi3
    plot plot plot tabell
    plot plot plot tabell
""")
dash.add(hist, at="plot")
```

- Hver linje = grid-rad; navn skilt med whitespace; antall kolonner = antall
  navn per linje (inntil 12; flere → oppsettfeil).
- Samme navn i flere celler gir større område — horisontalt og vertikalt.
  Områder må være rektangulære (valideres; brudd → tydelig feilmelding med
  linjenummer). `.` = tom celle (CSS-konvensjon).
- Implementasjon: nesten direkte oversettelse til `grid-template-areas` +
  `grid-area: navn`. Radhøyde: `auto`-rader med `minmax()` slik at plott-områder
  får fornuftig høyde.
- `add(x, at="navn")` plasserer kortet; `add` uten `at=` fyller udisponerte
  områder i lesefølge; flere kort enn områder → appendes under gridet med
  auto-layout (og en konsollmerknad).

### 6.2 Uten layout: designet auto-layout

- 12-kolonners underliggende grid.
- KPI-fliser (`number`) samles i én rad øverst, hver 2–3 kolonner bred.
- Tekst/markdown: full bredde.
- Plott: 6 kolonner (to i bredden), fast aspektforhold på innholdsflaten.
- Tabeller: 6 eller 12 kolonner etter kolonnetall i tabellen.
- Rekkefølge = `add()`-rekkefølge innen hver gruppe.

### 6.3 Kort-anatomi

Kort = valgfri tittellinje + (for funksjonskort) kontrollstripe + innholdsflate.
Kontroller til et funksjonskort bor **i kortet**, ikke i toppstripen — bare
`dash.controls()` legger noe i toppstripen.

## 7. Utseende (hoveddelen av «proft»-løftet)

Ett nytt `css/dash.css` med bevisst design. Krav:

- Spacing-skala (f.eks. 4/8/16/24px) brukt konsekvent; felles kortpadding.
- Typografisk hierarki: dashboard-tittel, korttittel, KPI-tall (stor,
  tabular-nums), etikett/enhet (liten, dempet).
- Kort: svak elevasjon/ramme, konsistent hjørneradius, lik høyde innen grid-rad
  (grid gjør dette; innhold fyller kortet med `object-fit`/scroll ved behov).
- Plott: innholdsflaten har fast aspektforhold; figurbredde bestemmes ved
  render slik at bitmap fyller flaten uten letterboxing (be shimmen om riktig
  figsize/DPI før tegning i stedet for å klemme bildet etterpå).
- Tabeller: stylet `.dash`-tabell (zebra, kompakt, sticky header, scroll ved
  overflow) — ikke rå `to_html`-utseende.
- Arver appens temavariabler (lys/mørk følger med gratis).

## 8. Sletting (del av samme arbeid)

- `js/dashboard.js`, `css/dashboard.css`, `tests/js/dashboard.test.js`
- `index.html`-koblinger: view-dropdown-tvang (`__dashViewOverride`),
  run-knapp-grenen som trunkerer script til setup-sonen,
  `buildDashboardCtx()`, finally-hooken, `dashboardPendingParsed`
- Gamle eksempler (`ex_dashboard_iris.py`, `bry10/bry11`-knappene) skrives om
  til nytt API; `dashstatlink/names.json` oppdateres til de omskrevne filene
  (husk ~5 min raw-CDN-cache).

`notebook-links.js` beholdes uendret (deling er visnings-agnostisk).

## 9. Senere faser (ikke fase 1, men arkitekturen tillater dem)

- **Pyodide:** samme `dash.py`-API; deklarasjoner serialiseres ut av workeren,
  widget-endring → «kall funksjon X med verdier» via runtime-køen i motoren.
- **R (webR):** `dashboard()/add()`-ekvivalenter i R; samme payload-format.
- **DuckDB/SQL:** kort som query-mal med plassholdere
  (`dash.add("SELECT ... WHERE year = {{år}}", år=(2020,2026))`) der endring
  re-kjører queryen; gjenbruker eksisterende SQL→plott-render-sti. Inntil da er
  Brython-wrapperen (Brython-script som spør DuckDB og `add()`-er resultatet)
  en fungerende mellomløsning fra fase 1.

## 10. Testing

- **Node-tester** for den rene halvdelen av `dash.js`: mosaikk-parsing
  (rektangel-validering, `.`-celler, kolonnetelling), auto-layout-plan,
  kwarg→widget-spec.
- **Brython-side:** omskrevet iris-eksempel + ett «alle korttyper»-eksempel som
  manuell røyk-test (Hans tester småting manuelt).
- Verifisering i browser før ferdigmelding (kjør begge eksempler, sjekk
  output-only-visning og lys/mørk tema).

## 11. Suksesskriterier

1. Iris-eksemplet i nytt API er kortere enn v1-varianten og ser vesentlig
   bedre ut (jevne kort, ingen letterboxing, KPI-fliser).
2. Et vanlig Brython-script blir dashboard ved å legge til `dashboard()` +
   `add()`-linjer — ingen andre endringer.
3. Netto linjetall i repoet går ned (ny motor + CSS < slettet kode + koblinger).
4. `dash.py` inneholder ingen DOM-bygging av kort/layout (grensesnitt-disiplin).
