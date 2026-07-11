# Dash v2-forbedringer — implementasjonsplan (parallelle strømmer)

**Goal:** Tre pakker på dash v2: (A) skjønnhetsfeil-fiksene fra review-oppfølgingslisten, (B) KPI-delta + tallformat, (C) widget-state i delings-URLen.

**Architecture:** Tre parallelle, filmessig disjunkte strømmer med presise kontrakter seg imellom (payload-format og `initialValues`-API definert her er bindende). Strøm 1: pandas-shimmen. Strøm 2: JS-siden (js/dash.js, css, app.css, index.html). Strøm 3: Python-adapteren (brython/dash.py) + eksempeldemo. Deretter parallell browser-verifisering, helhets-review, synk til openstat.

**Branch:** `dash-v2-forbedringer` i safestat (base 41694bd). Ikke push før alt er godkjent.

## Global Constraints

- Ingen nye avhengigheter; node-tester med `node --test tests/js/dash.test.js`; ren/DOM-splitt og UMD-idiom i js/dash.js beholdes; JSON-strenger over Python↔JS-grensen.
- dash.py bygger aldri DOM; CSS kun temavariabler (nye tokens legges i ALLE 4 temablokker i app.css — husk auto-blokkene ~689/692; js-deps i LIB_REGISTRY er `{url, global}`-objekter).
- Eksisterende eksempler (bry10/11/17-20) skal fortsatt virke uendret der de ikke eksplisitt oppdateres.

## Bindende kontrakter (begge sider implementerer NØYAKTIG dette)

### K1: number-payload v2 (python produserer, JS rendrer)

```
{kind: 'number', value: <råtall>, unit: str,
 text: str|null,          // ferdigformatert visning; null => JS bruker fmtNumber(value)
 delta: null | {text: str, dir: 'opp'|'ned'|'flat', good: bool}}
```

- Python-API: `add(x, title=, unit=, fmt=None, ref=None, bra="opp")` (fmt/ref/bra gjelder kun tall-payloads, både statiske og funksjonsretur).
- `fmt` er en Python format-spec (f.eks. `",.1f"`); etter `format(value, fmt)` oversettes engelsk gruppering til norsk: `,`→mellomrom (U+202F smalt hardt mellomrom), `.`→`,`.
- `ref` gir delta: diff = value − ref; dir = 'opp' hvis diff > 0, 'ned' hvis < 0, ellers 'flat'; `good` = (dir == bra) eller dir == 'flat'; delta.text = diff formatert med samme fmt (eller fmtNumber-ekvivalent), med eksplisitt fortegn (+/−).
- Ikke-endelige verdier (nan/inf): som i dag → tekst-payload (delta droppes).
- JS-render: `.dash-kpi-delta`-span etter verdien med pil ▲/▼/– og klasse `dash-kpi-delta--good` / `--bad` (flat → good). Farger: good → `var(--success)`, bad → `var(--danger)`. NYTT token `--success` i app.css: light-blokker `#16a34a`, dark-blokker `#9ece6a`.

### K2: URL-state (JS eier alt; python henter startverdier)

- State = `{ "shared": {navn: råverdi}, "cards": {"<n>": {navn: råverdi}} }` der `<n>` er løpenummer for addCard-kall MED controls (0-basert, per dash). Råverdier = samme typer som onChange rapporterer (tall/bool/indeks-int/streng).
- Serialisering: kompakt JSON → base64url (uten padding). Hash-parameter `ds`.
- **Hash-sameksistens:** `js/notebook-links.js` sin `classifyHash` og index.html sin hash-håndtering må IKKE forstyrres. Implementeringen skal lese begge og velge en trygg innkoding (f.eks. suffiks `;ds=<verdi>` som strippes fra hashen før all annen klassifisering, og som dash.js leser direkte fra `location.hash`). Akseptansekrav: `#output=<url>;ds=...` åpner output-only MED gjenopprettede verdier; alle eksisterende hash-former uendret.
- Oppdatering: ved hver onChange-flush oppdaterer dash.js `ds`-parameteren med `history.replaceState` (debounced sammen med eksisterende debounce).
- Gjenoppretting: `Dash.create` leser `ds` én gang; `addControls`/`addCard` bruker matchende verdier som widgetenes startverdier (DOM settes FØR `initial` beregnes).
- **NYTT API `Dash.initialValues(id)`** → JSON-streng `{navn: råverdi}`: for et cardId → kortets effektive startverdier; for et dashId → den delte stripens. Tom `{}` hvis ingen. dash.py kaller dette rett etter addCard/addControls og mapper via `from_raw` før første `_run`, slik at første render bruker gjenopprettet state (ikke Python-defaults).

### K3: play-widget (animasjon — «spill av verdiene som film»)

- Widget-spec: `{type:'play', name, min, max, step, default, interval, loop, label}` (interval i ms, default 600, minimum 200; loop default false).
- JS-render: som slider + ▶-knapp (toggler til ⏸). Ved avspilling: verdien økes med step per interval-tick, slider og verdivisning følger med, hver tick rapporterer via normal `report()` (debouncen på 150 ms er ok for interval ≥ 200). Ved max: stopp (eller hopp til min og fortsett hvis loop). Pause ved klikk, og ved manuell slider-endring.
- Python: `dash.play(min, max, step=None, default=None, interval=600, loop=False, label=None)` — kun eksplisitt form (ingen implisitt kwarg-mapping). `from_raw` som slider.
- URL-state: verdien lagres som slider; avspillingstilstand lagres IKKE.
- Demo: i bry18 byttes terskel-slideren til `dash.play(-5, 10, step=1, label="Terskel (spill av)")` — kurven + KPI-ene animeres.

## Strømmer og tasks

### Strøm 1 — pandas-shimmen (`brython/pandas_brython.py`)
Legg til på Series: `nunique()`, `tolist()`, `to_html()` (enkel to-kolonners tabell: index + verdier, med Series-navn som header hvis satt; samme html-stil som DataFrame.to_html). Følg filens eksisterende mønstre. Verifiser med CPython-snutt (klassene er ren Python): konstruer liten Series, assert nunique/tolist/to_html-innhold. Sjekk også at `dash._infer` da takler Series som dropdown-kwarg (tolist-duck-typing) — nevn i rapport, ikke test i browser her.
**Filer:** kun `brython/pandas_brython.py`. Commit: `feat(brython): Series.nunique/tolist/to_html`.

### Strøm 2 — JS-siden (`js/dash.js`, `css/dash.css`, `app.css`, `index.html`, `tests/js/dash.test.js`)
1. K1-render (`.dash-kpi-delta`, text-override i renderPayload) + `--success` i app.css (alle 4 blokker) + CSS for delta.
2. K2 komplett (les/skriv/strip `ds`, initialValues-API, replaceState) — statens serialisering/parsing som RENE funksjoner (`D.encodeState`/`D.decodeState`) med node-tester (round-trip, ugyldig input → null, base64url uten padding).
3. Funksjonskort re-plasseres ved første payload i auto-layout: oppdater `style.gridColumn`/`style.order` etter faktisk kind (mosaikk-plassering røres ikke).
4. `addControls` kalt på nytt ERSTATTER eksisterende toppstripe (ikke ny stripe).
5. Temabytte: MutationObserver på `body`s `data-theme` → `Plotly.relayout(el, {'font.color': <ny --text>})` for tilkoblede figurer.
6. Mosaikk-rader: `grid-template-rows: repeat(<rows>, minmax(96px, auto))` ved create.
7. K3: play-widget i `buildControl` (timer i widget-scope, ryddes når kortet/dashen fjernes eller ved pause; ▶/⏸-knapp stylet i dash.css).
**Commit:** `feat(dash): KPI-delta, URL-state, play-widget, re-plassering, tema-font, controls-erstatning`.

### Strøm 3 — Python-adapteren (`brython/dash.py`, `examples/bry17_dashboard_kostnad.txt`, `examples/bry18_dashboard_fordeling.txt`)
1. K1-produksjon: `fmt`/`ref`/`bra`-kwargs på add() (statisk + funksjonskort; funksjonskort: delta beregnes per re-kjøring), norsk formattering, nan-vern beholdes.
2. K2-integrasjon: kall `window.Dash.initialValues(...)` etter addCard/addControls, map via `from_raw`, bruk i første `_run` og som `card["vals"]`-start.
3. `_infer`-feilmeldinger med hint (Series/dict/ukjent → «bruk list(...)» osv.).
4. `_func_params` inkluderer keyword-only-parametre (`co_varnames[:co_argcount + co_kwonlyargcount]`).
5. `controls()` kalt to ganger: python-siden må ikke akkumulere dupliserte on_change-bindinger (JS erstatter stripen; python re-registrerer hele settet).
6. K3: `dash.play(...)`-konstruktør (Widget med kind 'play').
7. Demo i bry17: gi «Totalkostnad 5 aar» `fmt=",.1f"` og `ref=` (f.eks. kostnad ved 50 % opptak som referanse) slik at delta vises. Demo i bry18: terskel byttes til `dash.play(-5, 10, step=1, label="Terskel (spill av)")`. Behold pedagogikken.
**Verifisering:** `python3 -m py_compile`; browser-testing skjer i verifiseringsbølgen. Commit: `feat(dash): fmt/ref/bra, initialValues, feilmeldingshint, kwonly, controls-recall`.

### Verifiseringsbølge (2 parallelle browser-agenter, ulike tool-stacker)
- Regresjon: alle 6 dashboard-eksempler rendrer uten feil (bry10/11/17/18/19/20).
- Nytt: bry17 viser delta-pil som skifter good/bad når opptak-slider krysser referansen; norsk tallformat; bry18: ▶-knappen animerer terskel-verdien (kurve + KPI oppdateres per tick, ⏸ stopper, stopp ved max); endre kontroller → `ds=` dukker opp i URL; kopier URL, åpne i ny fane → verdier og render gjenopprettet; `#output=<url>;ds=...` virker; vanlige lenker uten ds uendret; temabytte oppdaterer plott-fontfarge uten re-kjøring; funksjons-KPI i auto-layout (lag adhoc-test i editor: `d.add(lambda n: n, n=(1,5))` uten layout → 3-kolonners flis øverst etter første render).
- Node-tester: alle suiter.

### Slutt-review (1 agent, mest kapable modell) → ev. fix-bølge (1 agent) → openstat-synk (1 agent)
Synk: kopier delte filer verbatim (js/dash.js, css/dash.css, brython/dash.py, brython/pandas_brython.py, tests/js/dash.test.js, examples/bry17), anker-baserte app.css- (--success i 4 blokker) og index.html-redigeringer, node-tester + kort browser-røyk. Commit «synk fra safestat: …» på branch i openstat.

## Akseptansekriterier (helheten)

1. Alle 6 eksempler + adhoc-testene over passerer i browser uten konsollfeil.
2. Node-tester grønne (inkl. nye encode/decodeState-tester).
3. `d.add(serie)` gir tabell; `d.add(f, valg=serie)` gir nedtrekk (via tolist).
4. Delings-URL med ds-state gjenoppretter både delte og per-kort-verdier ved lasting.
5. Ingen regresjon i vanlige (ikke-dashboard) kjøringer og eksisterende delingslenker.
