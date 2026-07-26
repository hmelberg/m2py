# pandas-paritet for brython/micropython-modus (design)

**Status:** APPROVED 2026-07-26 (Hans: «design det, deretter implementer p0 og p1»).

## Motivasjon

`brython/pandas_brython.py` (135 KB) og `micropython/pandas_mpy.py` (148 KB)
er ren-python-porter av pandas som gir brython- og micropython-modusene et
DataFrame-lag uten Pyodide. De dekker det meste av dagligbruken, men målt mot
ekte pandas 2.3.3 (2026-07-26, instansnivå så `__getattr__`-dispatch teller med):

| flate | dekket | mangler |
|---|---|---|
| Series | 59 av 210 | 151 |
| DataFrame | 65 av 209 | 144 |
| `.str` | 20 av 64 | 44 |
| `.dt` | 11 av 43 | 32 |

Tallet overdriver: mye av pandas' flate er `to_hdf`, `to_stata`, `tz_convert`
og aritmetikk-aliaser som ingen bruker interaktivt. Men innimellom ligger fire
klasser av problemer som betyr noe, og de er rangert her etter **skade**, ikke
etter antall:

1. **Stille gale svar.** `df.drop()` muterer mottakeren; `cut()` gir vanlige
   strenger så all sortering blir alfabetisk.
2. **Brutte hverdagsidiomer.** `astype('int')` feiler fordi `astype` kaller
   argumentet sitt direkte.
3. **Kvadratisk ytelse.** `DataFrame.sort_values` er O(n²).
4. **Lastekostnad.** Hver `import pandas` drar med seg 144 KB plotly.

## Ikke-mål

Bevisst utenfor scope, med begrunnelse:

- **MultiIndex.** Det er der pandas' kompleksitet eksploderer. Eksisterende
  valg (flat indeks av tupler i groupby) beholdes. Pyodide-modus er svaret
  for den som trenger ekte MultiIndex.
- **`pd.NA` vs `np.nan` og dtype-promotering.** Pandas er selv mest
  inkonsistent her. Shimmens `nan`-sentinel fungerer og beholdes uendret.
- **Egen array-type for strenger.** I en ren-python-motor er gevinsten null.
  Det holder at `dtype` rapporterer `'string'` og at `.str` er nan-sikker
  (den er allerede det).
- **Tidssoner, `Period`, `resample`.** `rolling`/`expanding`/`resample`
  vurderes senere som egen pakke (P2), ikke her.

## Arkitektur

### Dialekt og deling

`pandas_mpy.py` er en bevisst divergerende kopi (fellelisten står i filhodet:
ingen `slice()`-konstruktør, ingen `Counter`, `functools`/`copy`/`itertools`
kan mangle, `re.IGNORECASE` mangler i unix-bygget, ingen `csv`, ingen
`datetime.strptime`). Alle endringer i denne spec-en skrives derfor i den
**dialektsikre delmengden** — den som kjører uendret i CPython, Brython og
MicroPython — og speiles i begge filer.

Filene er i dag byte-identiske i `safestat/` og `openstat/`. Endringer går inn
i safestat først, deretter openstat (etablert rutine, `sync_check.sh`).

`shared/`-katalogen (fem moduler i dag: `ui_core`, `altair_core`,
`folium_core`, `lifelines_core`, `tabulator_core`, lastet via `path:`-
overstyring i begge registrene) er presedensen for kode som skrives én gang.
Denne spec-en flytter **ikke** pandas dit — kjernen er for sammenvevd med
dialektfellene til at en flytting lønner seg nå. Nye, selvstendige pakker
(P2: window-funksjoner) skal derimot legges i `shared/`.

### dtype-laget

`Series.dtype` returnerer en **vanlig streng**, ikke et dtype-objekt.
MicroPython kan ikke trygt subklasse `str`, og alt som betyr noe i praksis
(`str(s.dtype) == 'int64'`, `s.dtype == 'object'`) virker likt.

Verdiområde: `'int64'`, `'float64'`, `'bool'`, `'object'`, `'string'`,
`'category'`, `'datetime64[ns]'`.

Utledes ved aksess, ikke cachet. Det er O(n), samme klasse som `sum()`, og
`dtype` kalles aldri i indre løkker. Caching ville krevd invalidering på tvers
av view/data-delingen i datamodellen — mer risiko enn gevinst.

`astype` får en navnetabell fra streng til callable, slik at `astype('int')`,
`astype('float64')` og `astype({'a': 'str'})` virker. `astype('category')` og
`astype('datetime64[ns]')` er spesialtilfeller.

### Categorical som metadata, ikke som lagringsformat

Datamodellen er en flat 1-D liste i kolonne-major (`DataFrame.data`) og en
liste + indekstuppel + view-slice (`Series`). Å bytte verdiene ut med
`codes`-heltall ville berørt hele modellen.

I stedet lagres kategori-informasjon som **metadata ved siden av verdiene**:

```python
class CategoricalDtype:
    categories: tuple      # i definert rekkefølge
    ordered: bool
```

- `Series._cat` — `CategoricalDtype` eller `None`.
- `DataFrame._cats` — `{kolonnenavn: CategoricalDtype}`.

Verdiene i `data` forblir etikettene selv. Det gir:

- `cut`/`qcut` returnerer en Series med `_cat` satt og `ordered=True`, så
  `sort_values`, `groupby` og `value_counts` får riktig rekkefølge.
- `.cat.categories`, `.cat.codes`, `.cat.ordered` uten å endre lagringen.
- Ingen minne- eller fartsgevinst (den ville krevd ekte codes) — det er en
  akseptert kostnad for å slippe å skrive om datamodellen.

Metadata følger med i `copy()`, `from_data()`, kolonne-get/set og de
metodene som bevarer kategorier i pandas. Transformasjoner som pandas selv
dropper kategori-status for (`apply`, aritmetikk) dropper den også her.
Sorteringsnøkkel utledes av `_sort_key(ser)`: for kategoriske serier
`categories.index(v)`, ellers verdien selv.

### Lat lasting

`scanImports()` i begge motorene matcher i dag bare import-setninger.
Den utvides med et **token-felt** i `LIB_REGISTRY`:

```js
plotly_express_brython: { aliases: [], deps: [], js: [], tokens: ['.plot'] },
```

Finnes et token i brukerens kildekode, registreres biblioteket. Over-matching
er ufarlig (laster et bibliotek som ikke brukes) — samme avveining som
scanneren allerede gjør for importer i strenger.

`pandas_*` mister dermed sin harde `deps: ['plotly_express_*']`; modulnivå-
importen erstattes med en lat `_px()`-hjelper som `Plot`-metodene kaller.
Modulen ligger allerede i `sys.modules` når brukerkoden kjører, så
`_px()` er et synkront oppslag uten kostnad.

Bommer token-skanningen (f.eks. `getattr(df, 'plot')`), skal `_px()` kaste en
tydelig melding — samme mønster som `_brython_gap` bruker i dag, aldri en
naken `ModuleNotFoundError`.

Dette er mønsteret nye features KAN følge når de er selvstendige nok: P2-pakker
(`rolling`/`expanding`/`resample`) registreres med `tokens: ['.rolling(', …]`.

Det er bevisst ingen regel om at kjernen ikke får vokse. En feature som hører
hjemme på `Series`/`DataFrame` blir dårligere av å presses ut i en egen pakke,
og noen ganger er noen KB helt klart verdt det. Avveiningen er per tilfelle:
selvstendig og sjelden brukt → egen pakke; tett vevd inn i kjerne-API-et →
inn i kjernen. `test_pandas_size_budget.py` er en fartsdump som gjør veksten
synlig, ikke en grense som skal forsvares.

## Endringer

### P0 — skade og ytelse

**P0-1 `drop` muterer ikke.** I dag returnerer `DataFrame.drop()` riktig
resultat, men muterer også mottakeren:

```
shim  drop('g', axis=1): retur=('a',)  original etter=('a',)
ekte  drop('g', axis=1): retur=('a',)  original etter=('a','g')
```

I en notatbok betyr det at `df.drop('kol', axis=1)` ødelegger brukerens
DataFrame. Dessuten er standard-akse `1` der pandas har `0`, og
`index=`/`columns=`-argumentene mangler.

Fiksen: `drop` arbeider på en kopi og returnerer den; `axis` får default 0;
`index=`/`columns=` støttes. `DataFrame.groupby` bruker i dag den muterende
oppførselen internt (`df.drop(b)` uten tilordning) og må rettes samtidig.
Den interne `labels=None`-grenen (trimming til view) beholdes uendret — den
har andre kallere.

**P0-2 `astype` med strengnavn, `dtype`/`dtypes`.** Se dtype-laget over.

**P0-3 Oppslag i indeks blir O(1).** `Series.index_of` (linje 1033) gjør
`tuple.index(etikett)` — O(n) per oppslag. `DataFrame.sort_values` kaller
`ser.loc[ny_indeks]` per kolonne, altså n oppslag à O(n):

```
N            500    1000    2000    4000
sort_values  3.3     9.6    36.3   143.1 ms   (CPython; kvadratisk)
```

Under Brython, 20–50× tregere, er 143 ms fort 3–7 sekunder. Fiksen er et
lazy `{etikett: posisjon}`-dict, bygget forlengs så **første** forekomst
vinner (samme semantikk som `tuple.index` ved dupliserte etiketter), og
gjenbygget når `self.index` byttes ut (identitetssjekk, ikke likhet).

**P0-4 Lat plotly.** Se lat lasting over. Gevinst: 144 KB nedlasting og
Brython-kompilering spart på hver pandas-økt uten plotting.

### P1 — paritet

**P1-1 Categorical.** `CategoricalDtype`, `Series.cat`-accessor
(`categories`, `codes`, `ordered`, `rename_categories`, `add_categories`,
`remove_categories`, `as_ordered`, `as_unordered`), `astype('category')`,
og `cut`/`qcut` som setter `ordered=True`. Honoreres av `sort_values`,
`value_counts`, `groupby` og `unique`.

Verifisert divergens som dette lukker:

```
cut(x, bins=[0,2,10,20]).sort_values()
  shim: (0, 2] , (10, 20] , (2, 10]        ← leksikografisk
  ekte: (0, 2] , (2, 10] , (10, 20]

cut(..., labels=['lav','middels','høy']).sort_values()
  shim: høy, lav, middels                  ← alfabetisk
  ekte: lav, middels, høy
```

For aldersgrupper, inntektskvintiler og alvorlighetsgrader — kjernebruken —
er dagens oppførsel feil, og den ser riktig ut helt til noen ser etter.

**P1-2 `.dt` og datoer.** MicroPython-wasm har en `datetime`-klasse men
**ingen `strptime`**, så `to_datetime` er i praksis ute av drift der i dag.
Det løses med en egen `_strptime(s, fmt)` som dekker `%Y %m %d %H %M %S %y
%j %b %B` — ~40 linjer, ingen avhengigheter — brukt når `datetime.strptime`
mangler. Uten den er all `.dt`-utvidelse verdiløs i micropython-modus.

Deretter: `quarter`, `dayofyear`/`day_of_year`, `days_in_month`,
`is_month_start`/`is_month_end`, `is_quarter_start`/`is_quarter_end`,
`is_year_start`/`is_year_end`, `is_leap_year`, `day_name()`,
`month_name()`, `normalize()`, `floor()`, `ceil()`, `round()`,
`isocalendar()`, `time`, `microsecond`. Pluss `date_range()` på modulnivå.

`day_name()`/`month_name()` bruker engelske navn som pandas' standard-locale.

**P1-3 `.str`.** `__getattr__`-fallbacken dekker allerede alt som finnes på
Pythons `str` (`zfill`, `isdigit`, …), men gir en forvirrende feilmelding for
pandas-egne navn (`AttributeError: type object 'str' has no attribute
'extract'`). Legges til: `extract`, `extractall`, `match`, `fullmatch`,
`findall`, `count`, `pad`, `cat`, `repeat`, `slice_replace`, `wrap`,
`removeprefix`, `removesuffix`, `join`, `partition`, `rpartition`,
`get_dummies`. Fallbacken får en tydelig feilmelding for resten.

**P1-4 Vindus- og aggregatverb.** `shift`, `diff`, `pct_change`, `cumprod`,
`cummax`, `cummin` på Series og DataFrame; `cumsum` på DataFrame (finnes
bare på Series i dag); `agg`/`aggregate` og `transform` på begge;
`DataFrame.round`, `DataFrame.isin`, `DataFrame.mode`, `DataFrame.any`,
`DataFrame.all`, `Series.explode`, `Series.to_frame`, `Series.items`,
`DataFrame.items`, `DataFrame.itertuples`, `DataFrame.select_dtypes`,
`DataFrame.info`.

## Kvalitetssikring

`brython/tests/test_pandas_brython_diff.py` (270 linjer) kjører samme
operasjon i shimmen og i ekte pandas og sammenlikner normaliserte resultater.
Det er den **eneste** mekanismen som faktisk garanterer «lik vanlig pandas»,
og alt nytt skal inn der — differensialtest før implementasjon, ikke etter.

Tre nivåer, alle må være grønne før en oppgave regnes som ferdig:

1. `python3 brython/tests/test_pandas_brython_diff.py` — semantikk mot ekte pandas.
2. `python3 micropython/tests/test_pandas_mpy.py` — mpy-porten under CPython.
3. `micropython micropython/tests/mpy_smoke_pandas.py` — fanger dialektfellene
   (v1.28.0 finnes lokalt; unix-bygget mangler `datetime` helt, så
   dato-testene må være guardet der).

I tillegg en **budsjett-test** med romslig tak, slik at vekst i kjernefilene
blir et synlig og bevisst valg. Taket kan heves når det er riktig — det skal
begrunnes i commit-meldingen, ikke forsvares.
