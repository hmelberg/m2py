# pandas-paritet (P0+P1) implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lukke de fire skadeklassene i spec-en — stille gale svar, brutte
hverdagsidiomer, kvadratisk sortering og 144 KB unødig lastekostnad — og
deretter gi `.cat`, `.dt` og `.str` pandas-paritet på det som brukes.

**Architecture:** Alle endringer skrives i den dialektsikre delmengden
(CPython ∩ Brython ∩ MicroPython) og speiles i `brython/pandas_brython.py` og
`micropython/pandas_mpy.py`. Kategorier lagres som metadata ved siden av
verdiene, ikke som codes. Lat lasting skjer via et nytt `tokens`-felt i
`LIB_REGISTRY`.

**Spec:** `docs/superpowers/specs/2026-07-26-pandas-parity-design.md`

**Tech Stack:** ren python (ingen avhengigheter), JS i motorfilene,
differensialtester mot ekte pandas 2.3.3.

## Global Constraints

- **Dialektsikker python.** Ingen `slice()`-konstruktør (bruk `_mkslice` i
  mpy-fila), ingen `Counter`, ingen `itertools.chain.from_iterable`, ingen
  `functools` uten guard, ingen `re.IGNORECASE` uten `getattr`-sjekk, ingen
  `datetime.strptime`, ingen walrus i f-string, ingen `os.linesep`.
- **To filer, samme semantikk.** Hver oppgave lander i BEGGE
  `brython/pandas_brython.py` og `micropython/pandas_mpy.py`.
- **To repoer.** Filene er byte-identiske i `safestat/` og `openstat/`.
  Synk til safestat til slutt (Task 10), ikke underveis.
- **Ingen bakoverkompatibilitet.** Erstatt/slett fremfor å frysa gammel
  oppførsel — det finnes ingen brukere av shimmen utenfor appen.
- **Ingen push.** Push i openstat er kontrollørens beslutning.

**Testkommandoer** (alle tre må være grønne før en oppgave er ferdig):

```bash
cd /Users/hom/Documents/GitHub/openstat
python3 brython/tests/test_pandas_brython_diff.py
python3 micropython/tests/test_pandas_mpy.py
micropython micropython/tests/mpy_smoke_pandas.py
```

---

### Task 1: `drop` muterer ikke (P0-1)

**Files:**
- Modify: `brython/pandas_brython.py:2207` (`DataFrame.drop`), `:2688` (`groupby`)
- Modify: `micropython/pandas_mpy.py` (samme to metoder)
- Test: `brython/tests/test_pandas_brython_diff.py`

**Interfaces:**
- Produces: `DataFrame.drop(labels=None, axis=0, index=None, columns=None)`
  returnerer ny DataFrame og lar mottakeren være urørt. `labels=None` uten
  `index`/`columns` beholder dagens interne view-trimming (kallere finnes).

- [x] **Step 1: Failing test** — `test_drop_does_not_mutate` som sjekker at
  `df.drop('g', axis=1)` lar `df.columns` være uendret, mot ekte pandas.
- [x] **Step 2: Kjør, verifiser rødt.**
- [x] **Step 3:** Implementer kopi-semantikk, `axis=0`-default og
  `index=`/`columns=`. Rett `groupby` sine to `df.drop(...)`-kall til å
  tilordne resultatet.
- [x] **Step 4: Kjør alle tre testnivåene.**

### Task 2: dtype + astype med strengnavn (P0-2)

**Files:** begge pandas-filer; test i diff-fila.

**Interfaces:**
- Produces: `Series.dtype -> str`, `DataFrame.dtypes -> Series`,
  `_ASTYPE: dict[str, callable]`, `_infer_dtype(values) -> str`.

- [x] **Step 1:** Failing test `test_dtype_and_astype_names`.
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** `_infer_dtype` (bool før int — `bool` er subklasse av `int`),
  `dtype`/`dtypes`-properties, `_ASTYPE`-tabell brukt av `Series.astype` og
  `DataFrame.astype`.
- [x] **Step 4:** Kjør alle tre nivåene.

### Task 3: O(1) indeksoppslag (P0-3)

**Files:** begge pandas-filer; test i diff-fila.

**Interfaces:**
- Produces: `Series._pos_map() -> dict` (lazy, gjenbygget når `self.index`
  byttes ut — identitetssjekk). Brukes av `Series.index_of`.

- [x] **Step 1:** Failing test: `sort_values` på 2000 rader under en
  tidsgrense, pluss korrekthetstest for dupliserte etiketter (første
  forekomst vinner, som `tuple.index`).
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** Implementer `_pos_map` og bruk den i `index_of`.
- [x] **Step 4:** Kjør alle tre nivåene + benchmark som viser lineær vekst.

### Task 4: Lat plotly (P0-4)

**Files:**
- Modify: `js/brython-engine.js` (`LIB_REGISTRY`, `scanImports`)
- Modify: `js/micropython-engine.js` (samme)
- Modify: begge pandas-filer (modulnivå-import → `_px()`)
- Test: `brython/tests/test_engine_scan.py`

**Interfaces:**
- Produces: `LIB_REGISTRY[x].tokens: string[]` (valgfritt felt);
  `_px()` i pandas-filene som kaster tydelig feil hvis plotly ikke er lastet.

- [x] **Step 1:** Failing test i `test_engine_scan.py`: kode med `.plot`
  men uten `import plotly` skal gi `plotly_express_brython` i needed;
  kode uten `.plot` skal IKKE gi den.
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** `tokens`-felt + scan; fjern `deps`-oppføringen fra
  `pandas_*`; erstatt modulnivå-`import plotly_express_*` med `_px()`.
- [x] **Step 4:** Kjør testene + nettleser-røyk (`.plot` virker fortsatt,
  `import pandas` alene henter ikke plotly).

### Task 5: Categorical (P1-1)

**Files:** begge pandas-filer; test i diff-fila.

**Interfaces:**
- Produces: `CategoricalDtype(categories, ordered)`, `Series._cat`,
  `DataFrame._cats`, `Series.cat` (`CAT`-accessor), `_sort_key(ser)`.
  `cut`/`qcut` setter `_cat` med `ordered=True`.

- [x] **Step 1:** Failing test `test_categorical_order` med de to verifiserte
  divergensene fra spec-en (bins `[0,2,10,20]` og `labels=['lav','middels','høy']`).
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** Implementer. Sørg for at `_cat` følger `copy()`,
  `from_data()` og kolonne-get/set, og at `sort_values`, `value_counts`,
  `groupby` og `unique` bruker `_sort_key`.
- [x] **Step 4:** Kjør alle tre nivåene.

### Task 6: `_strptime` for MicroPython (P1-2a)

**Files:** begge pandas-filer; test i mpy-testfila.

**Interfaces:**
- Produces: `_strptime(s, fmt) -> datetime`, brukt av `to_datetime` når
  `datetime.strptime` mangler. Dekker `%Y %m %d %H %M %S %y %j %b %B`.

- [x] **Step 1:** Failing test som kaller `_strptime` direkte for hvert
  format og sammenlikner med `datetime.strptime` under CPython.
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** Implementer parseren; `to_datetime` velger `_strptime`
  når `getattr(datetime, 'strptime', None)` er None.
- [x] **Step 4:** Kjør alle tre nivåene (dato-testene guardet i unix-mpy).

### Task 7: `.dt`-utvidelse + `date_range` (P1-2b)

**Files:** begge pandas-filer; test i diff-fila.

**Interfaces:**
- Produces: `DT.quarter/dayofyear/day_of_year/days_in_month/is_month_start/
  is_month_end/is_quarter_start/is_quarter_end/is_year_start/is_year_end/
  is_leap_year/microsecond/time`, `DT.day_name()/month_name()/normalize()/
  floor(freq)/ceil(freq)/round(freq)/isocalendar()`,
  `date_range(start, end=None, periods=None, freq='D')`.

- [x] **Step 1:** Failing test mot ekte pandas for hver property.
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** Implementer (engelske navn, som pandas' standard-locale).
- [x] **Step 4:** Kjør alle tre nivåene.

### Task 8: `.str`-utvidelse (P1-3)

**Files:** begge pandas-filer; test i diff-fila.

**Interfaces:**
- Produces: `STR.extract/extractall/match/fullmatch/findall/count/pad/cat/
  repeat/slice_replace/wrap/removeprefix/removesuffix/join/partition/
  rpartition/get_dummies`; `STR.__getattr__` gir tydelig feilmelding for
  ukjente navn i stedet for `AttributeError` på `str`.

- [x] **Step 1:** Failing test mot ekte pandas per metode.
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** Implementer. `extract` returnerer DataFrame ved flere
  grupper, Series ved én (pandas-semantikk med `expand`-default).
- [x] **Step 4:** Kjør alle tre nivåene.

### Task 9: vindus- og aggregatverb (P1-4)

**Files:** begge pandas-filer; test i diff-fila.

**Interfaces:**
- Produces: `Series.shift/diff/pct_change/cumprod/cummax/cummin/agg/
  aggregate/transform/explode/to_frame/items`;
  `DataFrame.shift/diff/pct_change/cumsum/cumprod/cummax/cummin/agg/
  aggregate/transform/round/isin/mode/any/all/items/itertuples/
  select_dtypes/info`.

- [x] **Step 1:** Failing test mot ekte pandas per verb.
- [x] **Step 2:** Kjør, verifiser rødt.
- [x] **Step 3:** Implementer.
- [x] **Step 4:** Kjør alle tre nivåene.

### Task 10: budsjett-test og synk til safestat

**Files:**
- Create: `brython/tests/test_pandas_size_budget.py`
- Modify: `safestat/brython/pandas_brython.py`, `safestat/micropython/pandas_mpy.py`,
  `safestat/js/brython-engine.js`, `safestat/js/micropython-engine.js`

- [x] **Step 1:** Budsjett-test som feiler over fastsatt KB-grense.
- [x] **Step 2:** Kjør, verifiser grønt med margin.
- [x] **Step 3:** Kopier alle fire filer til safestat; verifiser at de er
  byte-identiske på tvers.
- [x] **Step 4:** Kjør testene i safestat også.

---

## Utfall (2026-07-26)

Alle ti oppgavene er utført og verifisert i BEGGE repoer. Sluttilstand:
999 tester grønne i openstat, 464 i safestat, MicroPython-røyken grønn, og
hele differensialsuiten grønn mot **begge** portene (`PANDAS_SHIM=mpy`).

### Avvik fra planen

**Task 1 ble større enn antatt.** `drop` viste seg å mutere mottakeren — det
sto ikke i den opprinnelige analysen, men falt ut av at groupby-probene
oppførte seg ustabilt. Tre interne kallere (`__delitem__`, `groupby`,
`set_index`) var avhengige av mutasjonen og fikk `_drop_inplace()`; den
offentlige `drop()` returnerer nå en kopi.

**Planen antok at groupby manglet flere nøkler og `agg(dict)`.** Begge deler
fantes allerede og virket; den opprinnelige feilobservasjonen var en
følgefeil av den muterende dropen. Ingen kode var nødvendig.

**Fire MicroPython-feller ble oppdaget først i røyktesten** — ingen av dem
synlige i CPython-testene:

1. `rx.groupindex` finnes ikke på kompilerte mønstre (→ `getattr`-guard).
2. Match-objekter mangler `.start()`/`.end()` (→ `_re_finditer` finner
   posisjonen med `str.find` på treffteksten i stedet).
3. `str.rjust`/`ljust`/`center`/`zfill` finnes ikke (→ `_pad_text`, som følger
   CPythons center-formel så `.str.pad(side='both')` er identisk med pandas).
4. **`{m,n}`-kvantorer matcher ingenting, uten å feile.** Dette er den verste
   av dem, fordi `.str.contains(r'\d{4}')` ga tomt resultat i stedet for en
   feilmelding — og det gjaldt allerede FØR dette arbeidet. `_re_compile()`
   kaster nå en tydelig ValueError med hva man skal skrive i stedet.

**Én ytelsesregresjon oppdaget og rettet.** Første versjon av
`_pos_map()` bygget dict-et ved ethvert oppslag, noe som gjorde
`df['kol'].loc[etikett]` i løkke 8x tregere (dict-bygging over hele indeksen
koster mer enn ett `tuple.index`-søk). Kartet bygges nå bare ved bulk-oppslag,
eller etter fire enkeltoppslag på samme indeks.

### Målte resultater

```
sort_values, N=4000    143,1 ms  →   2,9 ms     (51x, og nå lineær)
loc-oppslag i løkke      4,0 ms  →   3,9 ms     (ingen regresjon)
import pandas (uten plotting)
  nedlastet kilde        279 KB  →   181 KB     (-35 %)
  med plotting           279 KB  →   325 KB     (+17 %)
```

Filene vokste fra 135 til 181 KB (brython) og 148 til 194 KB (mpy).
`test_pandas_size_budget.py` gjør videre vekst synlig — taket er romslig og
kan heves når det er riktig, det er en fartsdump og ikke et forbud.
