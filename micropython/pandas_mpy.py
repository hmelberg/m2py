# pandas_mpy.py — MicroPython-modus pandas-port.
#
# Divergerende kopi av brython/pandas_brython.py (kopiert 2026-07-12). Denne
# fila kjører under unix-micropython/wasm-micropython (Task 3-motoren), IKKE
# under Brython. Endringer her skal IKKE flyte tilbake til pandas_brython.py
# uten separat vurdering, og motsatt: porter fra pandas_brython.py hit må
# sjekkes mot dialektfellene under.
#
# Dialektfeller fikset i denne porten (fase 0-funn + Task 4-skanning, se
# micropython/NOTAT_fase0.md og .superpowers/sdd/task-4-report.md):
#   1. Walrus-operator (`:=`) inne i et f-string-uttrykk
#      (opprinnelig linje 1028, Series._repr_html_): MicroPython-parseren
#      feiler med SyntaxError på denne konstruksjonen. Tilordningen er
#      flyttet ut av f-strengen til en vanlig linje foran.
#   2. `import base64`: MicroPython har ingen base64-modul, men har
#      binascii. Erstattet med try/except-shim som bruker
#      binascii.a2b_base64 for b64decode.
#   3. wasm-buildets binascii.a2b_base64 krever bytes, ikke str (fase 0-funn,
#      se NOTAT_fase0.md pkt. c_binascii_base64) — shimmen encoder str til
#      bytes først.
#   4. `import csv`: MicroPython har ingen csv-modul. read_csv bruker nå
#      _parse_csv_text(), en minimal RFC-4180-parser, i stedet for
#      csv.reader. Brython-spesifikk _csv.QUOTE_STRINGS/QUOTE_NOTNULL-
#      lappingen er fjernet siden den ikke er relevant utenfor Brython.
#
# Følgende ble funnet ved Task 4s egen skanning (`micropython -c "import
# pandas_mpy"` kjørt iterativt til modulen lastet rent, deretter samme
# metode på røyktesten — se task-4-report.md for full utskrift):
#   5. `slice(start, stop[, step])` som direkte konstruktørkall feiler med
#      `TypeError: can't create 'slice' instances` — MicroPythons slice-type
#      lages kun via subscript (`x[a:b:c]`). Alle 30+ `slice(...)`-kall er
#      erstattet med `_mkslice(...)`, en hjelpefunksjon som bruker subscript
#      internt. Dekker kun 2-/3-argument-formen (den eneste som brukes her).
#   6. `functools`, `copy`, `itertools`, `html`: mangler helt i
#      unix-micropython-bygget (finnes i wasm-bygget, bekreftet via Node mot
#      /tmp/mpyspike). Guardet med try/except-shims (functools.reduce,
#      functools.partial, copy.copy, html.escape) slik at modulen laster i
#      begge miljøer. itertools.chain er i tillegg erstattet helt (se pkt. 7)
#      siden selve klassemetoden mangler også i wasm-bygget.
#   7. `itertools.chain.from_iterable`/`itertools.chain(*x)`: selv i
#      wasm-bygget der itertools finnes, er ikke chain en klasse med
#      from_iterable-klassemetode (chain(*x) returnerer bare en generator).
#      Begge bruksmåtene erstattet med den selvstendige _chain_from_iterable().
#   8. `collections.Counter`: mangler i BÅDE unix- og wasm-bygg (samme
#      ImportError-melding i begge, bekreftet via Node). Erstattet helt med
#      en selvstendig _Counter(dict)-klasse (most_common(), arver
#      get/values/items/len/sannhetsverdi fra dict).
#   9. `os.linesep`: mangler i BÅDE unix- og wasm-bygg. Erstattet med
#      modulnivå-konstanten `_LINESEP = getattr(os, 'linesep', '\n')`.
#  10. `re.IGNORECASE`: mangler i unix-bygget (bekreftet). STR.contains()
#      sitt case-insensitive regex-søk sjekker nå `getattr(re,
#      'IGNORECASE', None)` og bruker et ekte re.IGNORECASE-flagg når det
#      finnes (samme oppførsel som pandas_brython.py); småbokstav-
#      normaliseringen av mønster og streng er en fallback som KUN brukes
#      når flagget faktisk mangler (unix-micropython), og gjelder derfor
#      ikke lenger ubetinget.
#  11. `from datetime import datetime`: feiler helt (ImportError) i
#      unix-bygget (wasm-bygget HAR en datetime-klasse, men den mangler
#      strptime — ikke separat fikset, se avvikslisten i task-4-report.md).
#      Guardet med try/except; to_datetime()/.dt-accessoren blir
#      ikke-funksjonelle under unix-micropython (feiler høylytt med
#      NotImplementedError i stedet for et kryptisk isinstance()-TypeError),
#      men resten av modulen laster og virker uansett.
#  12. Slice-tildeling på rå Python-lister (`data[a:b] = value`) godtar bare
#      list/tuple som RHS i MicroPython — en vilkårlig iterable (f.eks. en
#      Series) gir `TypeError: object 'X' isn't a tuple or list` (CPython
#      godtar enhver iterable). Fikset på begge interne stedene dette
#      forekommer (ILocDF.__setitem__, "Sets a 1D section", og
#      ILocSer.__setitem__, slice-grenen): eksplisitt `list(value)`-
#      normalisering rett før tildelingen.
#  13. Funksjonsobjekter tillater ikke tilordning av `__name__` i MicroPython
#      (`_raise.__name__ = name` i `_brython_gap` feilet). Guardet med
#      try/except — rent kosmetisk under CPython/Brython (bedre
#      tracebacker), trygt å hoppe over under MicroPython.
#  14. (Task 5) `.plot`-aksessoren gjorde `import plotly_express_brython as
#      px` — en ren kopi-feil fra pandas_brython.py, usett i CPython-testene
#      siden importen er try/except-guardet og ingen test faktisk kaller
#      `.plot.*`. Nå som Task 5 har levert micropython/plotly_express_mpy.py,
#      byttet til plotly_express_mpy. Per 2026-07-26 er importen FLYTTET UT av
#      modulnivå til den late _px(): pandas_mpy har ikke lenger plotly som
#      deps i LIB_REGISTRY, og motoren laster plotly på token-treffet '.plot'
#      i brukerkoden i stedet.
#  15. (2026-07-26, paritetsarbeidet) MicroPythons re-modul mangler
#      finditer, fullmatch og .groups/.groupindex på kompilerte mønstre.
#      .str-metodene går derfor via _re_finditer/_full_match/_group_count,
#      og datoene via _strptime siden wasm-buildets datetime mangler
#      strptime. Se docs/superpowers/specs/2026-07-26-pandas-parity-design.md
#
# (Se filhode-kommentarene ved hvert enkelt endringspunkt for detaljer.)

try:
    from functools import reduce
except ImportError:              # MicroPython (unix-bygg mangler functools helt)
    def reduce(function, iterable, initializer=None):
        it = iter(iterable)
        value = initializer if initializer is not None else next(it)
        for element in it:
            value = function(value, element)
        return value
try:
    from copy import copy
except ImportError:              # MicroPython (unix-bygg mangler copy helt)
    def copy(obj):
        if isinstance(obj, list):
            return obj[:]
        if isinstance(obj, tuple):
            return obj[:]
        if isinstance(obj, dict):
            return dict(obj)
        if isinstance(obj, set):
            return set(obj)
        return obj
# MicroPython-felle: itertools mangler helt i unix-bygget, og selv i
# wasm-bygget der itertools finnes er ikke itertools.chain en klasse med et
# from_iterable-klassemetode — chain(*iterables) returnerer en generator uten
# det attributtet. Begge chain-bruksmåtene er derfor erstattet med denne
# selvstendige hjelpefunksjonen (droppet import itertools helt).
def _chain_from_iterable(iterables):
    for it in iterables:
        for item in it:
            yield item

# MicroPython-felle: `slice(start, stop, step)` som direkte konstruktør-kall
# feiler med `TypeError: can't create 'slice' instances` — MicroPythons
# innebygde slice-type kan bare lages via subscript-syntaks (`x[a:b:c]`),
# ikke ved å kalle `slice(...)` som en vanlig funksjon. pandas_brython.py
# bruker `slice(...)`-kall over 30 steder til intern indeksering; alle er
# erstattet med kall til denne hjelpefunksjonen, som lager slice-objektet
# via subscript på et dummy-objekt i stedet. Merk: dekker kun de 2- og
# 3-argument-formene som brukes i denne fila (`slice(a, b)` / `slice(a, b,
# c)`) — IKKE 1-argument-formen `slice(x)` (som ekte CPython tolker som
# `slice(None, x, None)`); den formen forekommer ikke i denne fila.
class _SliceMakerHelper:
    def __getitem__(self, item):
        return item


_slice_maker = _SliceMakerHelper()


def _mkslice(start=None, stop=None, step=None):
    return _slice_maker[start:stop:step]


try:
    import csv
except:
    print("no csv")
try:
    import functools
except ImportError:              # MicroPython (unix-bygg mangler functools helt)
    class functools:
        @staticmethod
        def partial(func, *args, **kwargs):
            def _partial(*more_args, **more_kwargs):
                merged = dict(kwargs)
                merged.update(more_kwargs)
                return func(*(args + more_args), **merged)
            return _partial
import os
import sys
# MicroPython-felle: _LINESEP finnes ikke (verken unix- eller wasm-bygg).
_LINESEP = getattr(os, 'linesep', '\n')

# plotly importeres IKKE på modulnivå (2026-07-26). Den er 149 KB kilde som
# før ble hentet på hver eneste `import pandas_mpy`, uansett om brukeren
# plottet. Motoren laster den nå på token-treff '.plot' i brukerkoden
# (LIB_REGISTRY.tokens i js/micropython-engine.js), og Plot-metodene henter
# modulen via _px() ved første kall — da ligger den i sys.modules.
_px_mod = None


def _px():
    global _px_mod
    if _px_mod is None:
        try:
            import plotly_express_mpy as _m
        except ImportError:
            raise RuntimeError(
                "plott krever plotly_express_mpy, som ikke ble lastet. "
                "Motoren laster den når koden nevner '.plot' — skriv f.eks. "
                "df.plot.bar(...) direkte, eller legg til "
                "'import plotly_express_mpy' øverst.")
        _px_mod = _m
    return _px_mod
try:
    from datetime import datetime
except ImportError:              # MicroPython (unix-bygg mangler datetime helt)
    # to_datetime()/.dt-accessoren blir ikke-funksjonelle uten datetime, men
    # resten av modulen (DataFrame/Series-kjernen) skal fortsatt laste og
    # virke. Kjent, dokumentert hull — se filhode og task-4-report.md.
    datetime = None
try:
    import functools
except ImportError:              # MicroPython (unix-bygg mangler functools helt)
    class functools:
        @staticmethod
        def partial(func, *args, **kwargs):
            def _partial(*more_args, **more_kwargs):
                merged = dict(kwargs)
                merged.update(more_kwargs)
                return func(*(args + more_args), **merged)
            return _partial
# MicroPython-felle: collections.Counter finnes ikke (verken unix- eller
# wasm-bygg — bekreftet med samme ImportError i begge). Selvstendig
# minimal erstatning i stedet for `from collections import Counter`;
# støtter konstruksjon fra iterable, most_common(n), og arver
# get()/values()/items()/len()/sannhetsverdi fra dict.
class _Counter(dict):
    def __init__(self, iterable=None):
        dict.__init__(self)
        if iterable is not None:
            for item in iterable:
                self[item] = self.get(item, 0) + 1

    def most_common(self, n=None):
        items = list(self.items())
        items.sort(key=lambda kv: kv[1], reverse=True)  # stabil: ties beholder rekkefølge
        return items if n is None else items[:n]
import random
try:
    import html
except ImportError:              # MicroPython (unix-bygg mangler html helt)
    class html:
        @staticmethod
        def escape(s, quote=True):
            s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if quote:
                s = s.replace('"', '&quot;').replace("'", '&#x27;')
            return s
import math
import json
import re

# Simple display controls for __str__ output
DISPLAY_MAX_ROWS = 60
DISPLAY_MAX_COLS = 10
DISPLAY_COL_SEP = "  "
DISPLAY_COL_WIDTH = None       # int or None; when set, cap column cell widths
DISPLAY_INDEX_WIDTH = None     # int or None; when set, cap index cell width
DISPLAY_TRUNC_MARK = "…"       # used when truncating cell text

def _fmt_cell(val):
    # Display formatting for cell values (like pandas): floats show at most
    # 6 significant digits so accumulated float noise (5.005999999999999)
    # renders as 5.006. Integral floats keep a trailing .0 (620000.0), and
    # data is never mutated — this is display only.
    if isinstance(val, float):
        if val == val and abs(val) != float('inf') and val == int(val) and abs(val) < 1e15:
            return f"{val:.1f}"
        return f"{val:.6g}"
    return str(val)


def _truncate_cell(text, width):
    s = _fmt_cell(text)
    if width is None:
        return s
    if width <= 0:
        return ""
    if len(s) <= width:
        return s
    if width == 1:
        return DISPLAY_TRUNC_MARK
    return s[: width - 1] + DISPLAY_TRUNC_MARK

    
try:
  import js
  from js import window
  #print("pyodide")
except:
  try:
    import browser
    from browser import window
    #print("no pyodide")
  except:
    # Under plain CPython (e.g. tests), neither pyodide's `js` nor
    # Brython's `browser` module is available. Fall back to None so the
    # module still imports cleanly; the only consumer is read_csv's
    # asset branch, which is guarded separately.
    window = None

try:
    import base64
except ImportError:              # MicroPython: binascii dekker b64decode
    import binascii
    class base64:
        @staticmethod
        def b64decode(s):
            # wasm-buildets binascii.a2b_base64 krever bytes, ikke str
            # (fase 0-funn, se NOTAT_fase0.md pkt. c_binascii_base64).
            if isinstance(s, str):
                s = s.encode()
            return binascii.a2b_base64(s)


class NaN:
    def __eq__(self, *args):
        return False

    def __lt__(self, *args):
        return False

    def __le__(self, *args):
        return False

    def __gt__(self, *args):
        return False

    def __ge__(self, *args):
        return False

    def __str__(self):
        return "NaN"

    def __repr__(self):
        return self.__str__()

    def __add__(self, other):
        return self

    def __radd__(self, other):
        return self

    def __sub__(self, other):
        return self

    def __rsub__(self, other):
        return self

    def __truediv__(self, other):
        return self

    def __rtruediv__(self, other):
        return self

    def __floordiv__(self, other):
        return self

    def __rfloordiv__(self, other):
        return self

    def __mul__(self, other):
        return self

    def __rmul__(self, other):
        return self

    def __pow__(self, other):
        return self

    def __rpow__(self, other):
        return self

    def __mod__(self, other):
        return self

    def __rmod__(self, other):
        return self

    def __neg__(self):
        return self

    def __pos__(self):
        return self

    def __abs__(self):
        return self

    def __float__(self):
        return float('nan')


nan = NaN()


# ── dtype-lag ──────────────────────────────────────────────────────────────
# Spec: docs/superpowers/specs/2026-07-26-pandas-parity-design.md
#
# dtype er en VANLIG STRENG, ikke et dtype-objekt: MicroPython kan ikke trygt
# subklasse str, og alt som betyr noe i praksis (str(s.dtype) == 'int64',
# s.dtype == 'object') oppfører seg likt. Utledes ved aksess, ikke cachet —
# det er O(n), samme klasse som sum(), og dtype kalles aldri i indre løkker.
# Caching ville krevd invalidering på tvers av view/data-delingen.

def _is_na(v):
    """nan-sentinelen, None, eller en ekte float-nan."""
    if v is nan or v is None:
        return True
    return isinstance(v, float) and v != v


def _infer_dtype(values):
    """Verdiliste → pandas-dtype-navn som streng."""
    seen_bool = seen_int = seen_float = seen_str = seen_dt = seen_other = False
    has_na = False
    n = 0
    for v in values:
        n += 1
        if _is_na(v):
            has_na = True
        elif isinstance(v, bool):          # FØR int: bool er subklasse av int
            seen_bool = True
        elif isinstance(v, int):
            seen_int = True
        elif isinstance(v, float):
            seen_float = True
        elif isinstance(v, str):
            seen_str = True
        elif datetime is not None and isinstance(v, datetime):
            seen_dt = True
        else:
            seen_other = True
    if n == 0:
        return 'object'
    kinds = 0
    for flag in (seen_bool, seen_int or seen_float, seen_str, seen_dt, seen_other):
        if flag:
            kinds += 1
    if kinds > 1 or seen_str or seen_other:
        return 'object'
    if seen_dt:
        return 'datetime64[ns]'
    if seen_bool:
        return 'object' if has_na else 'bool'
    if seen_int or seen_float:
        # pandas promoterer int→float så snart nan er med
        return 'float64' if (seen_float or has_na) else 'int64'
    return 'object' if has_na else 'object'


# Navn → callable for astype(). 'category' og 'datetime64[ns]' er
# spesialtilfeller og håndteres i Series.astype, ikke her.
_ASTYPE = {
    'int': int, 'int8': int, 'int16': int, 'int32': int, 'int64': int,
    'uint8': int, 'uint16': int, 'uint32': int, 'uint64': int, 'Int64': int,
    'float': float, 'float16': float, 'float32': float, 'float64': float,
    'Float64': float,
    'str': str, 'string': str, 'unicode': str,
    'bool': bool, 'boolean': bool,
    'object': None,          # None = identitet
}


def _astype_fn(dtype):
    """
    dtype (callable eller navn) → (callable_eller_None, spesialnøkkel).
    Kaster TypeError med en tydelig melding for ukjente navn — før
    2026-07-26 fikk man «'str' object is not callable», som var kryptisk.
    """
    if callable(dtype):
        return dtype, None
    name = str(dtype)
    if name == 'category':
        return None, 'category'
    if name.startswith('datetime64'):
        return None, 'datetime'
    if name in _ASTYPE:
        return _ASTYPE[name], None
    raise TypeError(
        "astype: ukjent dtype %r. Støttede navn: %s, 'category', 'datetime64[ns]'."
        % (dtype, ', '.join(sorted(_ASTYPE))))


# ── Categorical ────────────────────────────────────────────────────────────
# Kategori-info lagres som METADATA ved siden av verdiene (Series._cat,
# DataFrame._cats), ikke som codes-heltall: datamodellen er en flat 1-D liste
# i kolonne-major, og å bytte verdiene med codes ville berørt hele modellen.
# Verdiene i data forblir etikettene selv. Gevinsten er riktig REKKEFØLGE i
# sort_values/groupby/value_counts — ikke minne eller fart.

class CategoricalDtype:
    def __init__(self, categories, ordered=False):
        self.categories = tuple(categories)
        self.ordered = bool(ordered)

    def __str__(self):
        return 'category'

    def __repr__(self):
        return "CategoricalDtype(categories=%r, ordered=%r)" % (
            list(self.categories), self.ordered)

    def __eq__(self, other):
        if isinstance(other, str):
            return other == 'category'
        return (isinstance(other, CategoricalDtype)
                and self.categories == other.categories
                and self.ordered == other.ordered)

    def code_of(self, value):
        """Posisjon i categories, eller -1 for nan/ukjent (som pandas)."""
        if _is_na(value):
            return -1
        try:
            return self.categories.index(value)
        except ValueError:
            return -1


class CAT:
    """.cat-accessoren. Krever at serien har _cat satt."""

    def __init__(self, obj):
        self.obj = obj
        if getattr(obj, '_cat', None) is None:
            raise AttributeError("Can only use .cat accessor with a 'category' dtype")

    @property
    def categories(self):
        return self.obj._cat.categories

    @property
    def ordered(self):
        return self.obj._cat.ordered

    @property
    def codes(self):
        cat = self.obj._cat
        return self.obj.__class__([cat.code_of(v) for v in self.obj.values],
                                  self.obj.index)

    def _with(self, dtype):
        res = self.obj.copy()
        res._cat = dtype
        return res

    def rename_categories(self, new):
        old = self.obj._cat
        if isinstance(new, dict):
            mapping = dict(new)
            names = tuple(mapping.get(c, c) for c in old.categories)
        else:
            names = tuple(new)
            mapping = dict(zip(old.categories, names))
        res = self.obj.apply(lambda v: v if _is_na(v) else mapping.get(v, v))
        res._cat = CategoricalDtype(names, old.ordered)
        return res

    def add_categories(self, new):
        if not isinstance(new, (list, tuple)):
            new = [new]
        old = self.obj._cat
        return self._with(CategoricalDtype(old.categories + tuple(new), old.ordered))

    def remove_categories(self, drop):
        if not isinstance(drop, (list, tuple)):
            drop = [drop]
        old = self.obj._cat
        keep = tuple(c for c in old.categories if c not in drop)
        res = self.obj.apply(lambda v: nan if v in drop else v)
        res._cat = CategoricalDtype(keep, old.ordered)
        return res

    def as_ordered(self):
        return self._with(CategoricalDtype(self.obj._cat.categories, True))

    def as_unordered(self):
        return self._with(CategoricalDtype(self.obj._cat.categories, False))

    def reorder_categories(self, new, ordered=None):
        old = self.obj._cat
        return self._with(CategoricalDtype(
            new, old.ordered if ordered is None else ordered))


def _sort_key(ser):
    """
    Sorteringsnøkkel for en serie: kategoriposisjon for kategoriske serier,
    ellers verdien selv. Uten dette sorteres cut()-etiketter alfabetisk —
    '(10, 20]' før '(2, 10]', og 'høy' før 'lav'.
    """
    cat = getattr(ser, '_cat', None)
    if cat is None:
        return None
    return cat.code_of


# ── datohjelpere ───────────────────────────────────────────────────────────
# Ren aritmetikk, ingen avhengigheter: MicroPython-wasm HAR en datetime-klasse
# men mangler strptime, og timedelta kan ikke forutsettes. Alt her regner på
# (år, måned, dag) og proleptiske gregorianske dagnummer i stedet.

_MONTH_NAMES = ('January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December')
_DAY_NAMES = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
              'Saturday', 'Sunday')
_MONTH_ABBR = tuple(m[:3] for m in _MONTH_NAMES)
_DAYS_BEFORE = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def _is_leap(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _days_in_month(year, month):
    if month == 2:
        return 29 if _is_leap(year) else 28
    return 31 if month in (1, 3, 5, 7, 8, 10, 12) else 30


def _day_of_year(year, month, day):
    n = _DAYS_BEFORE[month - 1] + day
    if month > 2 and _is_leap(year):
        n += 1
    return n


def _to_ordinal(year, month, day):
    """Proleptisk gregoriansk dagnummer (1 == 0001-01-01), som date.toordinal."""
    y = year - 1
    return y * 365 + y // 4 - y // 100 + y // 400 + _day_of_year(year, month, day)


def _from_ordinal(n):
    """Invers av _to_ordinal → (år, måned, dag)."""
    year = (n * 400) // 146097 + 1
    while _to_ordinal(year, 1, 1) > n:
        year -= 1
    while _to_ordinal(year + 1, 1, 1) <= n:
        year += 1
    rest = n - _to_ordinal(year, 1, 1) + 1
    month = 1
    while month < 12 and rest > _days_in_month(year, month):
        rest -= _days_in_month(year, month)
        month += 1
    return year, month, rest


_STRPTIME_WIDTH = {'Y': 4, 'm': 2, 'd': 2, 'H': 2, 'M': 2, 'S': 2, 'y': 2,
                   'j': 3, 'f': 6}


def _strptime(text, fmt):
    """
    Minimal strptime for %Y %m %d %H %M %S %y %j %b %B %f og literaler.

    MicroPython-wasm har en datetime-klasse UTEN strptime, så to_datetime var
    i praksis ute av drift der. Denne brukes når datetime.strptime mangler
    (og testes mot stdlib-strptime under CPython).
    """
    if datetime is None:
        raise NotImplementedError('_strptime: datetime-klassen mangler i denne bygningen')
    fields = {'Y': 1900, 'm': 1, 'd': 1, 'H': 0, 'M': 0, 'S': 0, 'f': 0}
    doy = None
    si = 0
    fi = 0
    n = len(text)
    while fi < len(fmt):
        ch = fmt[fi]
        if ch != '%':
            if si >= n or text[si] != ch:
                raise ValueError('time data %r does not match format %r' % (text, fmt))
            si += 1
            fi += 1
            continue
        fi += 1
        if fi >= len(fmt):
            raise ValueError('stray %% in format %r' % fmt)
        code = fmt[fi]
        fi += 1
        if code == '%':
            if si >= n or text[si] != '%':
                raise ValueError('time data %r does not match format %r' % (text, fmt))
            si += 1
            continue
        if code in ('b', 'B'):
            names = _MONTH_ABBR if code == 'b' else _MONTH_NAMES
            found = None
            for i, name in enumerate(names):
                if text[si:si + len(name)].lower() == name.lower():
                    found = i + 1
                    si += len(name)
                    break
            if found is None:
                raise ValueError('time data %r does not match format %r' % (text, fmt))
            fields['m'] = found
            continue
        if code not in _STRPTIME_WIDTH:
            raise ValueError('_strptime: direktivet %%%s støttes ikke' % code)
        width = _STRPTIME_WIDTH[code]
        start = si
        while si < n and si - start < width and text[si].isdigit():
            si += 1
        if si == start:
            raise ValueError('time data %r does not match format %r' % (text, fmt))
        value = int(text[start:si])
        if code == 'y':
            fields['Y'] = value + (2000 if value < 69 else 1900)
        elif code == 'j':
            doy = value
        else:
            fields[code] = value
    if si != n:
        raise ValueError('unconverted data remains: %r' % text[si:])
    if doy is not None:
        year, month, day = _from_ordinal(_to_ordinal(fields['Y'], 1, 1) + doy - 1)
        fields['Y'], fields['m'], fields['d'] = year, month, day
    return datetime(fields['Y'], fields['m'], fields['d'],
                    fields['H'], fields['M'], fields['S'], fields['f'])


_FREQ_SECONDS = {'D': 86400, 'd': 86400, 'H': 3600, 'h': 3600,
                 'T': 60, 'min': 60, 'S': 1, 's': 1, 'W': 604800}


def _freq_seconds(freq):
    """pandas-frekvensalias → sekunder. Tall foran aliaset støttes ('15min')."""
    text = str(freq).strip()
    num = ''
    while text and text[0].isdigit():
        num += text[0]
        text = text[1:]
    if text not in _FREQ_SECONDS:
        raise ValueError(
            "ukjent frekvens %r. Støttede: %s (evt. med tall foran, f.eks. '15min')"
            % (freq, ', '.join(sorted(_FREQ_SECONDS))))
    return int(num or 1) * _FREQ_SECONDS[text]


def _parse_dt(text, fmt):
    """strptime via stdlib når den finnes, ellers _strptime."""
    native = getattr(datetime, 'strptime', None) if datetime is not None else None
    if native is not None:
        return native(text, fmt)
    return _strptime(text, fmt)


# ── regex-hjelpere ─────────────────────────────────────────────────────────
# MicroPythons re-modul er en delmengde: ingen finditer, ingen fullmatch,
# ingen .groups/.groupindex på det kompilerte mønsteret, og IGNORECASE
# mangler i unix-bygget. Alt .str-koden trenger går derfor via disse.

def _ignorecase():
    return getattr(re, 'IGNORECASE', 0)


_RE_BRACES_OK = None


def _has_brace_quantifier(pat):
    """Finnes en {m,n}-kvantor i mønsteret? (Literal { teller ikke.)"""
    i = pat.find('{')
    while i != -1:
        if i + 1 < len(pat) and pat[i + 1].isdigit():
            return True
        i = pat.find('{', i + 1)
    return False


def _re_compile(pat, flags=0):
    """
    re.compile med vakt mot MicroPythons STILLE regex-hull: {m,n}-kvantorer
    matcher ingenting i stedet for å feile, så `.str.contains(r'\\d{4}')` ga
    tomt resultat uten et eneste hint om hvorfor. Vakten koster én probe én
    gang, og er en no-op i CPython/Brython.
    """
    global _RE_BRACES_OK
    if _RE_BRACES_OK is None:
        try:
            _RE_BRACES_OK = re.compile('a{2}').search('aa') is not None
        except Exception:
            _RE_BRACES_OK = False
    if not _RE_BRACES_OK and _has_brace_quantifier(pat):
        raise ValueError(
            "regex-mønsteret %r bruker en {m,n}-kvantor, som re-modulen i "
            "denne kjøremotoren ikke støtter — den ville matchet ingenting. "
            "Gjenta tegnet i stedet, f.eks. \\d\\d\\d\\d for \\d{4}." % pat)
    return re.compile(pat, flags)


def _re_finditer(rx, text):
    """
    Alle treff, som liste av match-objekter. Egen løkke over rx.search på
    resten av strengen fordi MicroPythons re verken har finditer ELLER
    .start()/.end() på match-objektet (bekreftet mot unix-bygget v1.28.0).
    Posisjonen finnes derfor med str.find på selve treffteksten — riktig
    fordi search alltid gir treffet lengst til venstre.
    """
    out = []
    pos = 0
    n = len(text)
    while pos <= n:
        rest = text[pos:]
        m = rx.search(rest)
        if m is None:
            break
        out.append(m)
        matched = m.group(0)
        at = rest.find(matched)
        if at < 0:
            break
        step = at + len(matched) if matched else at + 1   # tomt treff: flytt én
        if step <= 0:
            step = 1
        pos += step
    return out


def _pad_text(text, width, fillchar, side):
    """
    str.rjust/ljust/center finnes ikke i MicroPython — padding gjøres manuelt.
    'both' følger CPythons center-formel (ekstra tegn til venstre når
    marg & width er odde), så .str.pad(side='both') er identisk med pandas.
    """
    marg = width - len(text)
    if marg <= 0:
        return text
    if side == 'left':
        return fillchar * marg + text
    if side == 'right':
        return text + fillchar * marg
    left = marg // 2 + (marg & width & 1)
    return fillchar * left + text + fillchar * (marg - left)


def _full_match(rx, text):
    """
    re.fullmatch-erstatning (mangler i MicroPython). Sammenlikner treffteksten
    med hele strengen i stedet for å bruke .end(), som heller ikke finnes.
    """
    m = rx.match(text)
    return m is not None and m.group(0) == text


def _count_groups(pat):
    """
    Antall fangstgrupper i et mønster. Leses ut av mønsterteksten fordi
    det kompilerte objektet ikke har .groups i alle dialekter.
    """
    n = 0
    i = 0
    size = len(pat)
    while i < size:
        c = pat[i]
        if c == '\\':
            i += 2
            continue
        if c == '[':                  # tegnklasse — hopp til lukkende ]
            i += 1
            if i < size and pat[i] == '^':
                i += 1
            if i < size and pat[i] == ']':
                i += 1
            while i < size and pat[i] != ']':
                if pat[i] == '\\':
                    i += 1
                i += 1
        elif c == '(':
            nxt = pat[i + 1:i + 2]
            if nxt != '?':
                n += 1
            elif pat[i + 1:i + 4] == '?P<':
                n += 1
        i += 1
    return n


def _group_count(rx, pat):
    got = getattr(rx, 'groups', None)
    return _count_groups(pat) if got is None else got


def is_bool(key):
    """
    Checks if the first value in some kind of item is a boolean value
    """
    try:
        item0 = key.iloc[0]
    except AttributeError:
        if isinstance(key, (list, tuple, set)):
            item0 = key[0]
        else:
            item0 = key
    if isinstance(item0, bool):
        return True
    return False


def is_2d_bool(key):
    """
    Checks if an object is a 2D bool key
    """
    try:
        item0 = key.iloc[0, 0]
    except AttributeError:
        try:
            item0 = key[0][0]
        except:
            return False
    if isinstance(item0, bool):
        return True
    return False


def invert(item):
    """
    Copies and inverts a list or nested list
    :param item: a nd iterable of boolean values
    :return: ~item
    """
    res = []
    if hasattr(item[0], "__len__"):
        for i in range(len(item)):
            res.append(invert(item[i]))
    else:
        res = [not val for val in item]
        return res
    return res


def concat(items, axis=0, join="outer", ignore_index=False):
    """
    Concatenates DataFrames or Series

    :param items: list, Series or DataFrames
    :param axis: int, default 0
    :param join: str, 'inner' or 'outer'
    :param ignore_index: bool, default False
    :return: DataFrame
    """
    if hasattr(items[0], "columns"):
        return concat_df(items, axis, join, ignore_index)
    else:
        return concat_ser(items, axis, join, ignore_index)


def concat_df(items, axis=0, join="outer", ignore_index=False):
    """
    Concatenates two or more dataframes

    :param other: DataFrame or Series
    :param ignore_index: Bool, If false, will create a new index
    :return: DataFrame
    """
    # append top and bottom
    if axis == 0:
        join_on = "columns"
        index_on = "index"
    else:
        join_on = "index"
        index_on = "columns"

    # build columns
    indices = [getattr(item, join_on) for item in items]
    if join == "outer":
        indices = list(reduce(lambda x, y: list_union(x, y), indices))
    else:
        indices = list(reduce(lambda x, y: list_intersection(x, y), indices))

    # Create data, with nans if there are new columns
    data = []
    for idx in indices:
        temp = []
        for item in items:
            if idx in getattr(item, join_on):
                if axis == 0:
                    temp += item[idx].values
                else:
                    temp += item.loc[idx, :].values
            else:
                if axis == 0:
                    length = item.shape[0]
                else:
                    length = item.shape[1]
                temp += [nan] * length
        data.append(temp)

    # new index. index if axis=0, columns if axis=1
    if ignore_index:
        index = None
    else:
        index = []
        for item in items:
            index += getattr(item, index_on)

    if axis == 0:
        return items[0].class_init({k: v for k, v in zip(indices, data)}, index=index)
    return items[0].class_init(data, columns=index, index=indices)


def concat_ser(items, axis=0, join="outer", ignore_index=False):
    """
    Concatenates two or more Series

    :param items: list, Series
    :param axis: int, default 0
    :param join: str, 'inner' or 'outer'
    :param ignore_index: bool, default False
    :return: DataFrame
    """

    # axis is zero, just append series to self
    if axis == 0:
        data = []
        index = []
        for item in items:
            data += item.values
            index += item.index
        return items[0].__class__(data, index=index, name=items[0].name)

    # otherwise...
    # generate new columns or index  based on join type
    new_index = [item.index for item in items]
    if join == "outer":
        new_index = list(reduce(lambda x, y: list_union(x, y), new_index))
    else:
        new_index = list(reduce(lambda x, y: list_intersection(x, y), new_index))

    # make the data
    data = []
    for item in items:
        data.append([item[idx] if idx in item.index else nan for idx in new_index])

    # make the index
    if ignore_index:
        columns = None
    else:
        columns = [item.name for item in items]
    return DataFrame(list(zip(*data)), columns=columns, index=new_index)


def list_intersection(a, b):
    """
    Returns the intersection of two lists
    """
    return [item for item in a if item in b]


def list_union(a, b):
    """
    Returns a deduped union of two lists
    """
    c = list(copy(a))
    for item in b:
        if item not in a:
            c.append(item)
    return c



"""
Contains the .loc and .iloc indexers for both DataFrames and Series
"""


class ILocDF:
    """
    ILoc indexer for dataframes
    """

    def __init__(self, obj=None):
        """
        Initializes the indexer
        :param obj: Series
        """
        if obj is None:
            return
        self.obj = obj

    def __getitem__(self, items):
        """
        Getitem for DataFrames based on index number
        """
        data = self.obj.data
        index = self.obj.index
        columns = self.obj.columns
        step = self.obj.step
        view = self.obj.view
        name = None
        # if it's a tuple, its multiple indicies. Otherwise, its one item, so
        # make a dummy index
        if isinstance(items, tuple):
            items = list(items)
        else:
            items = [items, _mkslice(None, None)]

        if is_2d_bool(items[0]):
            if isinstance(items[0], self.obj.__class__):
                items[0] = items[0].values

            df_cp = self.obj.copy()
            df_cp[invert(items[0])] = nan
            return df_cp
        data_items = copy(items)

        # convert to bool, or bound
        for i, item in enumerate(items):
            if isinstance(item, self.obj.ITERABLE_1D):
                # if it's a boolean
                if is_bool(item):
                    items[i] = [_ci for _ci, val in enumerate(item) if val]
                data_items[i] = self.obj.bound_iterable_to_df(items[i], axis=i)

            elif isinstance(item, slice):
                items[i] = self.obj.convert_slice(item, axis=i)
                data_items[i] = self.obj.bound_slice_to_df(items[i], axis=i)
            elif isinstance(item, int):
                data_items[i] = self.obj.bound_int_to_df(item, axis=i)

        #################
        # Returns an item
        #################
        if isinstance(items[0], int) and isinstance(items[1], int):
            # eg [1, 0]
            return data[data_items[0] + step * data_items[1]]
        ##################
        # Returns a Series
        ##################
        if isinstance(items[0], slice) and isinstance(items[1], int):
            # eg [1:3, 0]
            index = index[items[0]]
            name = columns[items[1]]
            view = _mkslice(
                data_items[0].start + data_items[1] * step,
                data_items[0].stop + data_items[1] * step,
                1,
            )
        elif isinstance(items[0], int) and isinstance(items[1], slice):
            # eg .iloc[0, 1:3]
            name = index[items[0]]
            index = columns[items[1]]
            start = data_items[0] + step * data_items[1].start
            stop = data_items[0] + step * data_items[1].stop
            view = _mkslice(start, stop, step)
        elif isinstance(items[0], int) and isinstance(items[1], self.obj.ITERABLE_1D):
            # eg .iloc[0, [1, 2, 3]]
            name = index[items[0]]
            index = tuple(columns[i] for i in items[1])
            data = [data[data_items[0] + step * i] for i in data_items[1]]
            # returns a copy of the data, so index starts at zero
            view = _mkslice(0, len(items[1]))
        elif isinstance(items[0], self.obj.ITERABLE_1D) and isinstance(items[1], int):
            # eg .iloc[[1, 2, 3], 0]
            name = columns[items[1]]
            index = tuple(index[i] for i in items[0])
            data = [data[i + step * data_items[i][1]] for i in data_items[i][0]]
            view = _mkslice(0, len(items[0]))

        #####################
        # Returns a DataFrame
        #####################
        elif isinstance(items[0], slice) and isinstance(items[1], slice):
            # e.g. .iloc[1:3, :]
            name = columns[items[1]]
            index = index[items[0]]
            view = tuple(data_items)
        elif isinstance(items[0], self.obj.ITERABLE_1D) and isinstance(items[1], slice):
            # e.g. .iloc[[1, 2], :]
            # iterate through row
            ndata = []
            for col_index in range(data_items[1].start, data_items[1].stop):
                ndata.extend([data[i + col_index * step] for i in data_items[0]])
            data = ndata
            name = columns[items[1]]
            index = tuple(index[i] for i in items[0])
            step = len(index)
            # retuns a copy, so view starts at zero
            view = (_mkslice(0, step), _mkslice(0, len(name)))
        elif isinstance(items[0], slice) and isinstance(items[1], self.obj.ITERABLE_1D):
            # e.g. .iloc[:, [1,2]
            ndata = []
            for i in data_items[1]:
                ndata.extend(
                    data[data_items[0].start + i * step : data_items[0].stop + i * step]
                )
            data = ndata
            index = index[items[0]]
            name = tuple(columns[i] for i in items[1])
            step = len(index)
            # return a copy, view starts at zero
            view = (_mkslice(0, step), _mkslice(0, len(name)))
        elif isinstance(items[0], self.obj.ITERABLE_1D) and isinstance(
            items[1], self.obj.ITERABLE_1D
        ):
            # e.g. .iloc[:, [1,2]
            ndata = []
            for i in data_items[1]:
                ndata.extend([data[j + i * step] for j in data_items[0]])
            data = ndata
            index = tuple(index[i] for i in items[0])
            name = tuple(columns[i] for i in items[1])
            step = len(index)
            # return a copy, view starts at zero
            view = (_mkslice(0, step), _mkslice(0, len(name)))

        if isinstance(index, tuple) and isinstance(name, (str, int)):
            return self.obj.series_from_data(data, index, name, view)
        if isinstance(index, tuple) and isinstance(name, tuple):
            return self.obj.from_data(data, index, name, view, step)
        raise IndexError(
            "Unhandled params in DF .iloc getitem. Perhaps your are not referencing by index"
        )

    def __setitem__(self, items, value):
        """
        Setitem for DataFrames based on index number
        """
        data = self.obj.data
        step = self.obj.step

        # if it's a tuple, its multiple indicies. Otherwise, make a dummy index
        if isinstance(items, tuple):
            items = list(items)
        else:
            items = [items, _mkslice(None, None)]
        data_items = copy(items)

        # convert to bool, or bound

        for i, item in enumerate(items):
            if is_2d_bool(item):
                pass
            elif isinstance(item, self.obj.ITERABLE_1D):
                # if it's a boolean
                if is_bool(item):
                    items[i] = [_ci for _ci, val in enumerate(item) if val]
                data_items[i] = self.obj.bound_iterable_to_df(items[i], axis=i)
            elif isinstance(item, slice):
                items[i] = self.obj.convert_slice(item, axis=i)
                data_items[i] = self.obj.bound_slice_to_df(items[i], axis=i)
            elif isinstance(item, int):
                data_items[i] = self.obj.bound_int_to_df(item, axis=i)

        del items

        #################
        # Sets an item
        #################
        if isinstance(data_items[0], int) and isinstance(data_items[1], int):
            # eg [1, 0]
            data[data_items[0] + step * data_items[1]] = value
        ##################
        # Sets a 1D section
        ##################
        if isinstance(data_items[0], slice) and isinstance(data_items[1], int):
            # eg [1:3, 0]
            if not isinstance(value, self.obj.ITERABLE_1D):
                value = [value] * (data_items[0].stop - data_items[0].start)
            try:
                value = value[list(self.obj.index)]
            except TypeError:
                pass
            # MicroPython-felle: list-slice-assignment (`data[a:b] = value`)
            # godtar bare list/tuple som RHS — en Series, set eller annen
            # vilkårlig iterable gir `TypeError: object 'X' isn't a tuple or
            # list` (CPython godtar enhver iterable her). Normaliser
            # eksplisitt til list rett før tildelingen.
            if not isinstance(value, (list, tuple)):
                value = list(value)
            data[
                data_items[0].start
                + step * data_items[1] : data_items[0].stop
                + data_items[1] * step
            ] = value

        if isinstance(data_items[0], int) and isinstance(data_items[1], slice):
            # eg .iloc[0, 1:3]
            start = data_items[0] + step * data_items[1].start
            stop = data_items[0] + step * data_items[1].stop
            if not isinstance(value, self.obj.ITERABLE_1D):
                value = [value] * (data_items[1].stop - data_items[1].start)
            try:
                value = value[list(self.obj.columns)]
            except TypeError:
                pass
            for i, val in zip(range(start, stop, step), value):
                data[i] = val
        if isinstance(data_items[0], int) and isinstance(
            data_items[1], self.obj.ITERABLE_1D
        ):
            # eg .iloc[0, [1, 2, 3]]
            if not isinstance(value, self.obj.ITERABLE_1D):
                value = [value] * (len(data_items[1]))
            for i, val in zip(items[1], value):
                data[data_items[0] + step * i] = val

        if isinstance(data_items[0], self.obj.ITERABLE_1D) and isinstance(
            data_items[1], int
        ):
            # eg .iloc[[1, 2, 3], 0]
            if not isinstance(value, self.obj.ITERABLE_1D):
                value = [value] * (len(data_items[0]))
            for i, val in zip(data_items[0], value):
                data[i + step * data_items[1]] = val

        #####################
        # Sets a 2D section
        #####################
        # warning: everything below is very messy.

        if isinstance(data_items[0], slice) and isinstance(data_items[1], slice):
            # e.g. .iloc[1:3, :]
            # there is almost certainly a better way to do this
            k = 0

            # convert the value to a flat list for assignment
            if isinstance(value, self.obj.ITERABLE_1D):
                value = list(_chain_from_iterable(value))
            else:
                value = [value] * (
                    (data_items[1].stop - data_items[1].start)
                    * (data_items[0].stop - data_items[0].start)
                )

            for i in range(data_items[0].start, data_items[0].stop):
                for j in range(data_items[1].start, data_items[1].stop):
                    data[i + j * step] = value[k]
                    k += 1

        # handle a 2d boolean key
        if is_2d_bool(data_items[0]):
            try:
                data_items[0] = data_items[0].values
            except AttributeError:
                pass

            for i, row in enumerate(data_items[0]):
                for j, col in enumerate(row):
                    if col:
                        self.obj.data[
                            self.obj.bound_int_to_df(i, axis=0)
                            + self.obj.bound_int_to_df(j, axis=1) * self.obj.step
                        ] = value

        elif isinstance(data_items[0], self.obj.ITERABLE_1D) and isinstance(
            data_items[1], slice
        ):
            # e.g. .iloc[[1, 2], :]
            # there is almost certainly a better way to do this
            k = 0
            if isinstance(value, self.obj.ITERABLE_1D):
                value = list(_chain_from_iterable(value))
            else:
                value = [value] * (
                    (data_items[1].stop - data_items[1].start) * len(data_items[0])
                )

            for i in data_items[0]:
                for j in range(data_items[1].start, data_items[1].stop):
                    data[i + j * step] = value[k]
                    k += 1
        if isinstance(data_items[0], slice) and isinstance(
            data_items[1], self.obj.ITERABLE_1D
        ):
            # e.g. .iloc[:, [1,2]
            k = 0
            if isinstance(value, self.obj.ITERABLE_1D):
                value = list(_chain_from_iterable(value))
            else:
                value = [value] * (
                    (data_items[0].stop - data_items[0].start) * len(data_items[1])
                )

            for i in range(data_items[0].start, data_items[0].stop):
                for j in data_items[1]:
                    data[i + j * step] = value[k]
                    k += 1
        if isinstance(data_items[0], self.obj.ITERABLE_1D) and isinstance(
            data_items[1], self.obj.ITERABLE_1D
        ):
            # e.g. .iloc[:, [1,2]
            k = 0
            if isinstance(value, self.obj.ITERABLE_1D):
                value = list(_chain_from_iterable(value))
            else:
                value = [value] * (len(data_items[0]) * len(data_items[1]))
            for i in data_items[0]:
                for j in data_items[1]:
                    data[i + j * step] = value[k]
                    k += 1


class ILocSer:
    """
    ILoc indexer for Series
    """

    ITERABLE_1D = (list, set, tuple)

    def __init__(self, obj):
        """
        Initializes the indexer
        :param obj: Series
        """
        self.obj = obj

    def __getitem__(self, item):
        """
        Setitem for Series based on index number
        """
        if isinstance(item, slice):
            item = _mkslice(
                item.start if item.start is not None else 0,
                item.stop if item.stop is not None else len(self.obj),
            )
            view = self.obj.bound_slice(item)
            index = self.obj.index[item]
            return self.obj.from_data(self.obj.data, index, self.obj.name, view)

        if isinstance(item, self.ITERABLE_1D + (self.obj.__class__,)):
            if is_bool(item):
                item = [_ci for _ci, val in enumerate(item) if val]

            index = self.obj.index
            index = [index[i] if i is not None else None for i in item]
            data = self.obj.values
            data = [data[i] if i is not None else nan for i in item]
            view = _mkslice(0, len(index), 1)
            return self.obj.from_data(data, index, self.obj.name, view)
        return self.obj.values[item]

    def __setitem__(self, item, value):
        """
        Setitem for Series based on index number
        """
        # convert to bool, or bound
        if isinstance(item, self.ITERABLE_1D + (self.obj.__class__,)):
            # if it's a boolean
            if is_bool(item):
                item = [_ci for _ci, val in enumerate(item) if val]
            data_item = self.obj.bound_iterable(item)
            if not isinstance(value, self.ITERABLE_1D + (self.obj.__class__,)):
                value = [value] * len(self.obj)

            for i, val in zip(data_item, value):
                self.obj.data[i] = val

        elif isinstance(item, slice):
            item = _mkslice(
                item.start if item.start is not None else 0,
                item.stop if item.stop is not None else len(self.obj),
            )
            data_item = self.obj.bound_slice(item)
            if not isinstance(value, self.ITERABLE_1D + (self.obj.__class__,)):
                value = [value] * ((data_item.stop - data_item.start) // data_item.step)

            # MicroPython-felle #12: list-slice-assignment (`data[a:b] =
            # value`) godtar bare list/tuple som RHS — en Series eller annen
            # vilkårlig iterable gir `TypeError: object 'X' isn't a tuple or
            # list` (CPython godtar enhver iterable her). Normaliser
            # eksplisitt til list rett før tildelingen (samme mønster som
            # ILocDF.__setitem__, "Sets a 1D section").
            if not isinstance(value, (list, tuple)):
                value = list(value)

            self.obj.data[data_item] = value

        else:
            # check the bounds
            if item >= len(self.obj):
                raise IndexError(
                    "You requested index %s but series is only %s items."
                    % (item, len(self.obj))
                )
            data_item = self.obj.bound_int(item)
            self.obj.data[data_item] = value


class LocSer:
    """
    Loc indexer for Series
    """

    ITERABLE_1D = (list, set, tuple)

    def __init__(self, obj):
        """
        Initializes the indexer
        :param obj: Series
        """
        self.obj = obj

    def __setitem__(self, items, value, what=None):
        """
        Setitem for Series based on index names
        """
        iloc_items = self.obj.index_of(items)

        # if index_of returned none, create it
        if iloc_items is None:
            self.obj.extend(items, num=1)
            self.__setitem__(items, value)
        else:
            self.obj.iloc.__setitem__(iloc_items, value)

    def __getitem__(self, items):
        """
        Getitem for Series based on index names
        """
        if is_bool(items):
            return self.obj.iloc[items]
        iloc_items = self.obj.index_of(items)
        if iloc_items is None:
            raise KeyError("%s not found in index." % items)
        ser = self.obj.iloc[iloc_items]
        if isinstance(ser, self.obj.__class__):
            ser.index = tuple(items)
        return ser


class LocDF:
    """
    Loc indexer for DataFrames
    """

    ITERABLE_1D = (list, set, tuple)

    def __init__(self, obj):
        """
        Initializes the indexer
        :param obj: DataFrame
        """
        self.obj = obj

    def __getitem__(self, items):
        """
        Getitem for DataFrames based on index names
        """
        if isinstance(items, tuple):
            if is_2d_bool(items[0]):
                return self.obj.iloc[items]
            # items arrive as slice and series
            iloc_items = tuple(
                self.obj.index_of(item, axis=i) for (i, item) in enumerate(items)
            )
        else:
            if is_2d_bool(items):
                return self.obj.iloc[items]
            iloc_items = self.obj.index_of(items)
        # can't use None in iloc_items. Fails with a series
        if any(elem is None for elem in iloc_items):
            raise KeyError(
                "One or more items not found. Index: %s, Column: %s"
                % (items[0], items[1])
            )
        return self.obj.iloc[iloc_items]

    def __setitem__(self, items, value):
        """
        Setitem for Series based on index names
        """
        # if it's a dataframe, send straight to iloc. It's a boolean key
        if is_2d_bool(items):
            self.obj.iloc.__setitem__(items, value)
            return

        if isinstance(items, tuple):
            if len(items) > 1 and is_2d_bool(items[1]):
                self.obj.iloc.__setitem__(items[1], value)
                return
            iloc_items = tuple(
                self.obj.index_of(item, axis=i) for (i, item) in enumerate(items)
            )
        else:
            iloc_items = (self.obj.index_of(items),)

        # if the index isn't found, add an empty row/column and call it again
        if iloc_items[0] is None:
            # adding a row will break the view. Make a copy.
            self.obj.drop()
            self.obj.add_empty_series(items[0], axis=0)
            self.__setitem__(items, value)
        elif len(items) > 1 and iloc_items[1] is None:
            self.obj.add_empty_series(items[1], axis=1)
            self.__setitem__(items, value)
        else:
            self.obj.iloc.__setitem__(iloc_items, value)




class AtSer:
    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, label):
        return self.obj.loc[label]

    def __setitem__(self, label, value):
        self.obj.loc.__setitem__(label, value)


class IAtSer:
    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, i):
        return self.obj.iloc[i]

    def __setitem__(self, i, value):
        self.obj.iloc.__setitem__(i, value)


class AtDF:
    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, key):
        if not isinstance(key, tuple) or len(key) != 2:
            raise KeyError(".at requires a (row_label, col_label) tuple")
        return self.obj.loc[key]

    def __setitem__(self, key, value):
        if not isinstance(key, tuple) or len(key) != 2:
            raise KeyError(".at requires a (row_label, col_label) tuple")
        self.obj.loc.__setitem__(key, value)


class IAtDF:
    def __init__(self, obj):
        self.obj = obj

    def __getitem__(self, key):
        if not isinstance(key, tuple) or len(key) != 2:
            raise KeyError(".iat requires a (row_pos, col_pos) tuple")
        return self.obj.iloc[key]

    def __setitem__(self, key, value):
        if not isinstance(key, tuple) or len(key) != 2:
            raise KeyError(".iat requires a (row_pos, col_pos) tuple")
        self.obj.iloc.__setitem__(key, value)


"""
Contains the Series class
"""



class Series:
    """
    view: the actual view of the data, including step
    """

    ITERABLE_1D = (list, set, tuple)

    @classmethod
    def from_data(cls, data, index, name=None, view=_mkslice(None, None), cat=None):
        """
        Creates a Series from data and an index.
        cat: CategoricalDtype som følger med videre (se _cat).
        """
        self = cls()
        self.data = data  # full 1D dataset.
        self.index = tuple(index)  # index, unique to series
        self.name = name
        self.view = view  # data[view] = the values
        self.iloc = ILocSer(self)
        self.loc = LocSer(self)
        self._cat = cat
        return self

    def __init__(self, data=None, index=None, name=None):
        view = None
        if hasattr(data, 'tolist') and not isinstance(data, (Series, DataFrame)):
            data = data.tolist()          # numpy_brython-ndarray o.l. -> lister
        if isinstance(data, self.__class__):
            data = data.data
            index = data.index
            name = data.name
            view = data.view
        elif isinstance(data, (list, set, tuple)):
            data = list(data)
            view = _mkslice(0, len(data), 1)
        elif isinstance(data, dict):
            name, data = next(iter(data.items()))
            view = _mkslice(0, len(data), 1)

        if data and index is None:
            index = tuple(range(len(data)))
        self.data = data
        self.view = view
        self.index = tuple(index) if index else None
        self.name = name
        self.iloc = ILocSer(self)
        self.loc = LocSer(self)
        self.str = STR(self)
        self.dt = DT(self)
        self.plot = Plot(self)
        self.at = AtSer(self)
        self.iat = IAtSer(self)
        self._cat = None          # CategoricalDtype når serien er kategorisk
        self._pos = None          # {etikett: posisjon}-cache, se _pos_map()
        self._pos_for = None      # indekstuppelen _pos ble bygget fra
        self._pos_calls = 0       # enkeltoppslag siden sist bygg (se index_of)

    @property
    def dtype(self):
        if self._cat is not None:
            return self._cat
        return _infer_dtype(self.values)

    @property
    def cat(self):
        return CAT(self)

    def __setitem__(self, key, value):
        self.loc.__setitem__(key, value)

    def __getitem__(self, item):
        return self.loc.__getitem__(item)

    def __str__(self):
        try:
            max_rows = DISPLAY_MAX_ROWS
            values = list(self.values)
            n = len(values)
            # Determine rows to show
            if n <= max_rows:
                show_indices = list(range(n))
                truncated = False
            else:
                head = max_rows // 2
                tail = max_rows - head
                show_indices = list(range(head)) + list(range(n - tail, n))
                truncated = True

            # Compute index width
            index_labels = [self.index[i] for i in show_indices]
            if DISPLAY_INDEX_WIDTH is not None:
                index_width = int(DISPLAY_INDEX_WIDTH)
            else:
                index_width = max([len(str(x)) for x in index_labels] + [0])

            lines = []
            for i in show_indices:
                idx_str = str(self.index[i]).ljust(index_width)
                # honor fixed column width for Series values if set
                val_str = _truncate_cell(values[i], DISPLAY_COL_WIDTH)
                lines.append(f"{idx_str}{DISPLAY_COL_SEP}{val_str}")
            if truncated:
                lines.insert(len(show_indices)//2, "...")

            if self.name is not None:
                lines.append(f"Name: {self.name}")
            return _LINESEP.join(lines)
        except Exception:
            # Fallback to previous simple format
            return (
                "Series Name: "
                + str(self.name)
                + _LINESEP
                + _LINESEP.join(
                    "%s: %s" % (item[0], item[1])
                    for item in zip(self.index, self.data[self.view])
                )
            )

    def __repr__(self):
        return str(self)

    def _repr_html_(self):
        """
        HTML table-like representation for rich frontends.
        """
        try:
            headers = "<tr><th>index</th><th>values</th></tr>"
            rows = []
            for idx, val in zip(self.index or [], self.values or []):
                idx_html = html.escape(str(idx))
                val_html = html.escape(_fmt_cell(val))
                rows.append(f"<tr><th>{idx_html}</th><td>{val_html}</td></tr>")
            # MicroPython-felle: walrus-tilordning (`:=`) inne i et f-string-
            # uttrykk feiler med SyntaxError under kompilering (fase 0-funn).
            # Tilordningen er derfor flyttet til en vanlig linje foran.
            name_suffix = '' if self.name is None else ' ' + html.escape(str(self.name))
            title = f"<caption>Series{name_suffix}</caption>"
            return "<table>" + title + "<thead>" + headers + "</thead><tbody>" + "".join(rows) + "</tbody></table>"
        except Exception:
            return None

    def index_of(self, item):
        """
        Returns the integer index of values in the index.
        If it is a tuple and it's not found, raises KeyError.
        If it is another kind of iterable and not found, adds None

        :param item: slice, iterable, any hashable object

        :return: list, slice, int
        """
        names = self.index
        pos = None

        if isinstance(item, self.ITERABLE_1D + (self.__class__,)):
            pos = self._pos_map()

            items = []
            for i in item:
                p = pos.get(i, -1)
                if p >= 0:
                    items.append(p)
                elif isinstance(item, tuple):
                    raise KeyError("%s not found in index." % i)
                else:
                    items.append(None)
            return items
        elif isinstance(item, slice):
            pos = self._pos_map()
            start = None if item.start is None else pos.get(item.start, -1)
            stop = None if item.stop is None else pos.get(item.stop, -1)
            if start == -1 or stop == -1:
                raise KeyError(
                    "At least one of the following values is not in the index: %s %s"
                    % (item.start, item.stop)
                )
            return _mkslice(start, stop)
        else:
            # Enkeltoppslag: å bygge et dict over hele indeksen koster mer enn
            # ETT tuple.index-søk, så kartet brukes bare hvis det alt finnes.
            # Etter noen oppslag på samme indeks lønner det seg likevel — da
            # bygges det (typisk `for etikett in ...: s.loc[etikett]`).
            if self._pos is not None and self._pos_for is names:
                p = self._pos.get(item, -1)
                return None if p < 0 else p
            self._pos_calls += 1
            if self._pos_calls >= 4:
                p = self._pos_map().get(item, -1)
                return None if p < 0 else p
            try:
                return names.index(item)
            except ValueError:
                return None

    def _pos_map(self):
        """
        {etikett: posisjon}-oppslag, bygget latent og gjenbrukt så lenge
        self.index er den SAMME tuppelen (identitetssjekk, ikke likhet).

        Uten dette gjør index_of tuple.index() — O(n) per oppslag — og
        DataFrame.sort_values, som slår opp n etiketter per kolonne, blir
        kvadratisk: 4x data ga 15x tid før denne endringen.

        Dupliserte etiketter: FØRSTE forekomst vinner, samme som tuple.index.
        """
        names = self.index
        if self._pos_for is not names or self._pos is None:
            self._pos_calls = 0
            pos = {}
            i = 0
            for label in (names or ()):
                try:
                    if label not in pos:
                        pos[label] = i
                except TypeError:          # uhashbar etikett (liste o.l.)
                    pass
                i += 1
            self._pos = pos
            self._pos_for = names
        return self._pos

    @property
    def values(self):
        return self.data[self.view]

    def __lt__(self, other):
        ser = self.copy()
        ser.data = [item < other for item in ser.data]
        return ser

    def __le__(self, other):
        ser = self.copy()
        ser.data = [item <= other for item in ser.data]
        return ser

    def __gt__(self, other):
        ser = self.copy()
        ser.data = [item > other for item in ser.data]
        return ser

    def __ge__(self, other):
        ser = self.copy()
        ser.data = [item >= other for item in ser.data]
        return ser

    def __eq__(self, other):
        other = self._coerce_binop_other(other)
        if isinstance(other, (self.ITERABLE_1D, type(self))):
            if isinstance(other, type(self)):
                if other.index != self.index:
                    raise ValueError(
                        "Can only compare identically-labeled Series objects"
                    )
                else:
                    data = [item == o for item, o in zip(self, other)]
            else:
                data = [item == o for item, o in zip(self, other)]
        else:
            data = [item == other for item in self]

        ser = self.copy()
        ser.data = data
        return ser

    def __ne__(self, other):
        ser = self.copy()
        ser.data = [item != other for item in ser.data]
        return ser

    def drop(self, labels=None):
        """
        Trims the series, breaking any shared data with others

        column_index: a column to drop
        :return:
        """
        to_delete = self.view.stop
        if labels in self.index:
            to_delete = self.index.index(labels)

        self.data = (
            self.data[self.view][0:to_delete] + self.data[self.view][to_delete + 1 :]
        )
        self.index = self.index[0:to_delete] + self.index[1 + to_delete :]

        #    and adjust our indexing
        self.view = _mkslice(0, len(self.index), 1)
        return self

    def copy(self):
        ser = self.from_data(
            self.data[self.view], self.index, self.name, _mkslice(0, len(self.index), 1),
            cat=self._cat
        )
        return ser

    def extend(self, index_name, value=None, num=1):
        self.drop()
        self.data.extend([nan] * num)
        if isinstance(index_name, self.ITERABLE_1D + (self.__class__,)):
            self.index = self.index + tuple(index_name)
        else:
            self.index = self.index + (index_name,)
        self.view = _mkslice(self.view.start, self.view.stop + num, 1)

    def __len__(self):
        return len(self.index)

    def __next__(self):
        for i in range(len(self)):
            try:
                yield self.iloc[i]
            except IndexError:
                return

    def __iter__(self):
        for val in self.values:
            yield val

    def bound_slice(self, slc):
        """
        Converts a slice to the actual slice used to reference the
        data. Does not raise bounds error.
        """
        start = slc.start
        stop = slc.stop

        if start is None:
            start = 0
        if stop is None:
            stop = len(self)
        if start < 0:
            start = max(self.view.stop + start * self.view.step, self.view.start)
        else:
            start = min(self.view.start + start * self.view.step, self.view.stop)
        if stop < 0:
            stop = max(self.view.stop + stop * self.view.step, self.view.start)
        else:
            stop = min(self.view.start + stop * self.view.step, self.view.stop)

        return _mkslice(start, stop, self.view.step)

    def bound_int(self, idx):
        """
        Converts an index to the actual index of the underlying
        data. Does not raise out of range errors.
        :param idx: int, desired index.values data
        :return: int, actual index of data
        """
        if idx < 0:
            idx = len(self) + idx
        idx = self.view.start + idx * self.view.step
        return idx

    def bound_iterable(self, iterable):
        """
        Converts an iterable of desired indecies to actual index numbers
        :param iterable:
        :return: list, a lit of index of the underlying data
        """
        return [self.bound_int(item) for item in iterable]

    def astype(self, dtype, copy=True):
        """
        astype(int) OG astype('int') — strengformen er den vanlige i pandas og
        feilet før 2026-07-26 med «'str' object is not callable», fordi
        argumentet ble kalt direkte. Se _astype_fn/_ASTYPE.
        """
        fn, special = _astype_fn(dtype)
        if special == 'category':
            res = self.copy()
            cats = _sorted_unique([v for v in res.values if not _is_na(v)])
            res._cat = CategoricalDtype(cats, False)
            return res
        if special == 'datetime':
            res = to_datetime(self)
        elif fn is None:                    # 'object' = identitet
            res = self.copy()
        else:
            res = self.apply(lambda v: v if _is_na(v) else fn(v))
        if copy:
            return res
        self.iloc[:] = res.values

    def apply(self, func, *args, **kwargs):
        cp = self.copy()
        for i, val in enumerate(cp.values):
            cp.iloc[i] = func(val, *args, **kwargs)
        return cp

    def sort_values(self, ascending=True, na_position="last"):
        """
        sort_values sorts a series using the python built-in sorted function.
        :param ascending: bool, whether or not sorted values should be ascending
        :param na_position: str, 'first' or 'last'
        :return: Series, sorted
        """
        # remove nans
        indices = [_ci for _ci, x in enumerate(self.values) if x is nan]
        nan_index = [self.index[i] for i in indices]
        new_values = self.values
        new_index = list(self.index)
        for i, idx in enumerate(indices):
            del new_values[idx - i]
            del new_index[idx - i]

        reverse = not ascending
        keyfn = _sort_key(self)
        if keyfn is None:
            pairs = sorted(zip(new_values, new_index), reverse=reverse)
        else:
            # Kategorisk: sorter på kategoriposisjon, ikke på etiketten.
            # Uten dette blir 'lav','middels','høy' til 'høy','lav','middels'.
            pairs = sorted(zip(new_values, new_index),
                           key=lambda pair: keyfn(pair[0]), reverse=reverse)
        new_values, new_index = zip(*pairs)

        if na_position == "last":
            new_values = list(new_values) + [nan] * len(nan_index)
            new_index = list(new_index) + list(nan_index)
        else:
            new_values = [nan] * len(nan_index) + list(new_values)
            new_index = list(nan_index) + list(new_index)

        # Eksplisitt view: from_data-defaulten _mkslice(None, None) har step=None,
        # som knekker iloc-aritmetikken på det sorterte resultatet.
        return self.from_data(list(new_values), new_index, name=self.name,
                              view=_mkslice(0, len(new_index), 1), cat=self._cat)

    def unique(self):
        # Bevarer rekkefølgen verdiene først opptrer i (som pandas.unique) —
        # set() ga vilkårlig rekkefølge og dermed ustabile groupby-resultater.
        # Kategoriske serier bruker kategorirekkefølgen, som pandas.
        vals = list(dict.fromkeys(self.values))
        keyfn = _sort_key(self)
        if keyfn is not None:
            vals = sorted(vals, key=keyfn)
        return vals

    def nunique(self, dropna=True):
        data = self.dropna().values if dropna else self.values
        return len(set(data))

    def tolist(self):
        return list(self.values)

    def to_html(self, index=True):
        # To-kolonners tabell: index + verdier. Samme html-stil som DataFrame.to_html.
        try:
            value_header = html.escape(str(self.name)) if self.name is not None else "values"
            header_cells = ([] if not index else ["<th></th>"]) + [f"<th>{value_header}</th>"]
            thead = "<tr>" + "".join(header_cells) + "</tr>"
            body_rows = []
            for idx, val in zip(self.index or [], self.values or []):
                cells = []
                if index:
                    cells.append(f"<th>{html.escape(str(idx))}</th>")
                cells.append(f"<td>{html.escape(_fmt_cell(val))}</td>")
                body_rows.append("<tr>" + "".join(cells) + "</tr>")
            return "<table><thead>" + thead + "</thead><tbody>" + "".join(body_rows) + "</tbody></table>"
        except Exception:
            return self._repr_html_() or ""

    def _coerce_binop_other(self, other):
        # numpy_brython-ndarray o.l. -> liste, slik at binops under
        # behandler den elementvis i stedet for som en skalar per celle.
        if (hasattr(other, 'tolist')
                and not isinstance(other, (self.__class__, DataFrame))):
            return other.tolist()
        return other

    def __add__(self, other):
        other = self._coerce_binop_other(other)
        cp = self.copy()
        if isinstance(other, self.ITERABLE_1D + (self.__class__,)):
            for i, val in enumerate(other):
                cp.data[i] += val
        else:
            for i in range(len(self)):
                cp.data[i] += other
        return cp

    def __sub__(self, other):
        other = self._coerce_binop_other(other)
        cp = self.copy()
        if isinstance(other, self.ITERABLE_1D + (self.__class__,)):
            for i, val in enumerate(other):
                cp.data[i] -= val
        else:
            for i in range(len(self)):
                cp.data[i] -= other
        return cp

    def __radd__(self, other):
        try:
            return self + other
        except:
            return self
        # if other is not 0:
        #     return self + other
        # else:
        #     return self

    def __mul__(self, other):
        other = self._coerce_binop_other(other)
        cp = self.copy()
        if isinstance(other, self.ITERABLE_1D + (self.__class__,)):
            for i, val in enumerate(other):
                cp.data[i] *= val
        else:
            for i in range(len(self)):
                cp.data[i] *= other
        return cp

    def __truediv__(self, other):
        other = self._coerce_binop_other(other)
        cp = self.copy()
        if isinstance(other, self.ITERABLE_1D + (self.__class__,)):
            for i, val in enumerate(other):
                cp.data[i] /= val
        else:
            for i in range(len(self)):
                cp.data[i] /= other
        return cp

    def __floordiv__(self, other):
        other = self._coerce_binop_other(other)
        cp = self.copy()
        if isinstance(other, self.ITERABLE_1D + (self.__class__,)):
            for i, val in enumerate(other):
                cp.data[i] //= val
        else:
            for i in range(len(self)):
                cp.data[i] //= other
        return cp

    def __pow__(self, other):
        other = self._coerce_binop_other(other)
        cp = self.copy()
        if isinstance(other, self.ITERABLE_1D + (self.__class__,)):
            for i, val in enumerate(other):
                cp.data[i] **= val
        else:
            for i in range(len(self)):
                cp.data[i] **= other
        return cp

    def dropna(self):
        cp = self.copy()
        cp = cp[~self.isna()]
        return cp

    def fillna(self, value=None, method=None):
        """
        Fill NA/NaN values.

        Supports scalar value, or method in {'ffill','pad','bfill','backfill'}.
        """
        cp = self.copy()
        # Forward/backward fill
        if method in ("ffill", "pad"):
            last_valid = None
            for i in range(len(cp)):
                if cp.data[i] is nan:
                    if last_valid is not None:
                        cp.data[i] = last_valid
                else:
                    last_valid = cp.data[i]
            return cp
        if method in ("bfill", "backfill"):
            next_valid = None
            for i in range(len(cp) - 1, -1, -1):
                if cp.data[i] is nan:
                    if next_valid is not None:
                        cp.data[i] = next_valid
                else:
                    next_valid = cp.data[i]
            return cp

        # Scalar fill
        for i in range(len(cp)):
            if cp.data[i] is nan:
                cp.data[i] = value
        return cp

    def isna(self):
        """
        Returns a bool of whether or not an item is a nan
        :return: Series
        """
        cp = self.copy()
        cp.data = [item is nan for item in self.values]
        return cp

    def clip(self, lower=None, upper=None):
        cp = self.copy()
        for i in range(len(cp)):
            val = cp.data[i]
            if val is nan:
                continue
            if lower is not None and val < lower:
                val = lower
            if upper is not None and val > upper:
                val = upper
            cp.data[i] = val
        return cp

    def between(self, left, right, inclusive="both"):
        include_left = inclusive in ("left", "both", True)
        include_right = inclusive in ("right", "both", True)
        cp = self.copy()
        out = []
        for val in cp.values:
            if val is nan:
                out.append(False)
                continue
            ok_left = val >= left if include_left else val > left
            ok_right = val <= right if include_right else val < right
            out.append(ok_left and ok_right)
        cp.data = out
        return cp

    def __invert__(self):
        cp = self.copy()
        for i in range(len(cp)):
            cp.data[i] = not cp.data[i]
        return cp

    def mean(self, dropna=True):
        values = self.dropna().values if dropna else self.values
        if len(values) == 0:
            return nan
        return sum(values) / len(values)

    def sum(self, dropna=True):
        values = self.dropna().values if dropna else self.values
        if len(values) == 0:
            return 0
        res = values[0]
        for item in values[1:]:
            res += item
        return res

    def value_counts(self, normalize=False, sort=True, ascending=False, dropna=True):
        values = self.dropna().values if dropna else self.values
        counted = _Counter(values)
        # most_common() gir pandas' synkende sortering; ties beholder
        # innsettingsrekkefølge (samme som pandas' stable sort).
        keyfn = _sort_key(self)
        if keyfn is not None:
            # Kategorisk: legg kategorirekkefølgen i bunn først, så bryter
            # ties på kategori og ikke på tilfeldig innsettingsrekkefølge.
            ordered = sorted(counted.items(), key=lambda kv: keyfn(kv[0]))
            items = sorted(ordered, key=lambda kv: -kv[1]) if sort else ordered
        else:
            items = counted.most_common() if sort else list(counted.items())
        if sort and ascending:
            items = items[::-1]
        idx = [k for k, _c in items]
        counts = [_c for _k, _c in items]
        if normalize:
            total = sum(counts)
            counts = [c / total for c in counts] if total else counts
        return Series(counts, index=idx, name='proportion' if normalize else 'count')
    
    def to_dict(self, orient="None", index=True):
      #columns=list(self.columns)
      #dikt = {columns[n]: data for n, data in enumerate(zip(*self.values))}
      #to do, naming
      dikt={}
      if index:
        dikt["index"]=self.index
      dikt["values"]=self.values
      return dikt
    
    def to_json(self, orient="records", index=False):
        if orient == "records":
            # JSON array of values (optionally with index as pairs)
            if index:
                data = [{"index": i, "value": v} for i, v in zip(self.index, self.values)]
            else:
                data = list(self.values)
            return json.dumps(data)
        elif orient == "index":
            data = {str(i): v for i, v in zip(self.index, self.values)}
            return json.dumps(data)
        else:
            # fallback
            return json.dumps(list(self.values))
    
    def min(self, dropna=True):
        values = self.dropna().values if dropna else self.values
        return min(values)

    def max(self, dropna=True):
        values = self.dropna().values if dropna else self.values
        return max(values)

    def median(self, dropna=True):
        values = self.dropna().values if dropna else self.values
        vals = list(values)
        vals.sort()
        n = len(vals)
        if n == 0:
            return nan
        mid = n // 2
        if n % 2 == 1:
            return vals[mid]
        return (vals[mid - 1] + vals[mid]) / 2

    def quantile(self, q=0.5, dropna=True):
        if q is None:
            q = 0.5
        values = self.dropna().values if dropna else self.values
        vals = list(values)
        if len(vals) == 0:
            return nan
        vals.sort()
        pos = (len(vals) - 1) * float(q)
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            return vals[lo]
        frac = pos - lo
        return vals[lo] * (1 - frac) + vals[hi] * frac

    def var(self, ddof=1, dropna=True):
        values = self.dropna().values if dropna else self.values
        n = len(values)
        if n == 0 or n - ddof <= 0:
            return nan
        mean_val = sum(values) / n
        ssd = 0
        for v in values:
            ssd += (v - mean_val) ** 2
        return ssd / (n - ddof)

    def std(self, ddof=1, dropna=True):
        v = self.var(ddof=ddof, dropna=dropna)
        if v is nan:
            return nan
        return math.sqrt(v)

    def idxmin(self, dropna=True):
        values = self.dropna().values if dropna else self.values
        if len(values) == 0:
            return None
        m = values[0]
        mi = 0
        for i, v in enumerate(values):
            if v < m:
                m = v
                mi = i
        return self.index[mi]

    def idxmax(self, dropna=True):
        values = self.dropna().values if dropna else self.values
        if len(values) == 0:
            return None
        m = values[0]
        mi = 0
        for i, v in enumerate(values):
            if v > m:
                m = v
                mi = i
        return self.index[mi]

    def replace(self, to_replace, value=None):
        cp = self.copy()
        if isinstance(to_replace, dict):
            mapping = to_replace
            cp.data = [mapping.get(v, v) for v in cp.values]
            return cp
        # scalar replace
        for i in range(len(cp)):
            if cp.data[i] == to_replace:
                cp.data[i] = value
        return cp

    def where(self, cond, other=nan):
        if isinstance(cond, Series):
            mask = cond.values
        else:
            mask = list(cond)
        cp = self.copy()
        for i in range(len(cp)):
            if not mask[i]:
                cp.data[i] = other
        return cp

    def mask(self, cond, other=nan):
        if isinstance(cond, Series):
            mask = cond.values
        else:
            mask = list(cond)
        cp = self.copy()
        for i in range(len(cp)):
            if mask[i]:
                cp.data[i] = other
        return cp

    # ── Fase 2-utvidelser (2026-07-10): små pandas-metoder ────────────────

    def map(self, arg, na_action=None):
        cp = self.copy()
        if isinstance(arg, dict):
            # Ikke-mappede nøkler blir nan (ulikt replace, som beholder verdien).
            cp.data = [nan if (v is nan or v not in arg) else arg[v] for v in cp.values]
        else:
            cp.data = [nan if (v is nan and na_action == 'ignore') else arg(v)
                       for v in cp.values]
        return cp

    def isin(self, values):
        vs = set(values)
        cp = self.copy()
        cp.data = [v in vs for v in cp.values]
        return cp

    def notna(self):
        return ~self.isna()

    notnull = notna

    def head(self, n=5):
        return self.iloc[:n]

    def tail(self, n=5):
        return self.iloc[-n:]

    def round(self, decimals=0):
        return self.apply(lambda v: v if v is nan else round(v, decimals))

    def abs(self):
        return self.apply(lambda v: v if v is nan else abs(v))

    def count(self):
        return len(self.dropna())

    def sort_index(self, ascending=True):
        pairs = sorted(zip(self.index, self.values),
                       key=lambda p: p[0], reverse=not ascending)
        return Series([v for _i, v in pairs], index=[i for i, _v in pairs],
                      name=self.name)

    def nlargest(self, n=5):
        return self.dropna().sort_values(ascending=False).iloc[:n]

    def nsmallest(self, n=5):
        return self.dropna().sort_values(ascending=True).iloc[:n]

    def cumsum(self):
        cp = self.copy()
        total, out = 0, []
        for v in cp.values:
            if v is nan:
                out.append(nan)          # pandas: nan forblir, summen fortsetter
            else:
                total += v
                out.append(total)
        cp.data = out
        return cp

    def _cum(self, fn, start):
        cp = self.copy()
        acc, out = start, []
        for v in cp.values:
            if _is_na(v):
                out.append(nan)          # pandas: nan forblir, akkumuleringen fortsetter
            else:
                acc = v if acc is None else fn(acc, v)
                out.append(acc)
        cp.data = out
        cp._cat = None
        return cp

    def cumprod(self):
        return self._cum(lambda a, b: a * b, None)

    def cummax(self):
        return self._cum(lambda a, b: a if a > b else b, None)

    def cummin(self):
        return self._cum(lambda a, b: a if a < b else b, None)

    def shift(self, periods=1, fill_value=None):
        """Flytt verdiene n plasser; hull fylles med nan (eller fill_value)."""
        vals = list(self.values)
        n = len(vals)
        pad = nan if fill_value is None else fill_value
        if periods > 0:
            out = [pad] * min(periods, n) + vals[:max(n - periods, 0)]
        elif periods < 0:
            k = -periods
            out = vals[min(k, n):] + [pad] * min(k, n)
        else:
            out = vals
        cp = self.copy()
        cp.data = out
        cp._cat = None
        return cp

    def diff(self, periods=1):
        prev = self.shift(periods).values
        out = [nan if (_is_na(a) or _is_na(b)) else a - b
               for a, b in zip(self.values, prev)]
        cp = self.copy()
        cp.data = out
        cp._cat = None
        return cp

    def pct_change(self, periods=1):
        prev = self.shift(periods).values
        out = []
        for a, b in zip(self.values, prev):
            if _is_na(a) or _is_na(b) or b == 0:
                out.append(nan)
            else:
                out.append((a - b) / b)
        cp = self.copy()
        cp.data = out
        cp._cat = None
        return cp

    def agg(self, func, *args, **kwargs):
        """
        agg('mean') | agg(['mean','max']) | agg(callable).
        Liste gir en Series indeksert på funksjonsnavn, som pandas.
        """
        if isinstance(func, (list, tuple)):
            names, vals = [], []
            for f in func:
                names.append(f if isinstance(f, str) else getattr(f, '__name__', str(f)))
                vals.append(self._agg_one(f, args, kwargs))
            return Series(vals, index=names)
        if isinstance(func, dict):
            raise TypeError('agg: dict støttes bare på DataFrame')
        return self._agg_one(func, args, kwargs)

    def _agg_one(self, func, args=(), kwargs=None):
        kwargs = kwargs or {}
        if isinstance(func, str):
            return getattr(self, func)(*args, **kwargs)
        return func(self, *args, **kwargs)

    aggregate = agg

    def transform(self, func, *args, **kwargs):
        """Elementvis når func er callable, ellers navnet på en Series-metode."""
        if isinstance(func, str):
            return getattr(self, func)(*args, **kwargs)
        return self.apply(func, *args, **kwargs)

    def explode(self):
        """Lister i cellene → én rad per element (nan for tomme lister)."""
        out, idx = [], []
        for label, v in zip(self.index, self.values):
            if isinstance(v, (list, tuple)):
                if len(v) == 0:
                    out.append(nan)
                    idx.append(label)
                else:
                    for item in v:
                        out.append(item)
                        idx.append(label)
            else:
                out.append(v)
                idx.append(label)
        return Series(out, index=idx, name=self.name)

    def to_frame(self, name=None):
        col = self.name if name is None else name
        if col is None:
            col = 0
        return DataFrame({col: list(self.values)}, index=list(self.index))

    def items(self):
        return zip(self.index, self.values)

    def rank(self, method='average', ascending=True):
        vals = list(self.values)
        order = sorted((i for i, v in enumerate(vals) if v is not nan),
                       key=lambda i: vals[i], reverse=not ascending)
        ranks = [nan] * len(vals)
        pos = 0
        while pos < len(order):
            j = pos
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[pos]]:
                j += 1
            for k in range(pos, j + 1):
                if method == 'min':
                    ranks[order[k]] = float(pos + 1)
                elif method == 'max':
                    ranks[order[k]] = float(j + 1)
                elif method == 'first':
                    ranks[order[k]] = float(k + 1)
                else:                    # 'average' (default)
                    ranks[order[k]] = (pos + j) / 2 + 1
            pos = j + 1
        cp = self.copy()
        cp.data = ranks
        return cp

    def mode(self):
        counted = _Counter(self.dropna().values)
        if not counted:
            return Series([])
        m = max(counted.values())
        vals = [k for k, c in counted.items() if c == m]
        try:
            vals = sorted(vals)          # pandas sorterer mode-resultatet
        except TypeError:
            pass
        return Series(vals)

    def describe(self):
        vals = self.dropna().values
        numeric = bool(vals) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals)
        if numeric:
            idx = ['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']
            data = [float(len(vals)), self.mean(), self.std(), self.min(),
                    self.quantile(0.25), self.quantile(0.5), self.quantile(0.75),
                    self.max()]
            return Series(data, index=idx, name=self.name)
        counted = _Counter(vals)
        top, freq = counted.most_common(1)[0] if counted else (nan, nan)
        return Series([len(vals), len(counted), top, freq],
                      index=['count', 'unique', 'top', 'freq'], name=self.name)

    def corr(self, other, method='pearson'):
        """
        Korrelasjon mot en annen serie (parvis dropna). Pearson eller Spearman.
        """
        pairs = [(a, b) for a, b in zip(self.values, other.values)
                 if a is not nan and b is not nan]
        n = len(pairs)
        if n < 2:
            return nan
        if method == 'spearman':
            ra = Series([a for a, _b in pairs]).rank()
            rb = Series([b for _a, b in pairs]).rank()
            return ra.corr(rb, method='pearson')
        xs = [a for a, _b in pairs]
        ys = [b for _a, b in pairs]
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        if vx == 0 or vy == 0:
            return nan
        return cov / math.sqrt(vx * vy)


class STR:
    """
    Streng-accessor med pandas-semantikk: nan og ikke-strenger passerer
    gjennom som nan i stedet for å krasje (den gamle blinde
    getattr(str, …)-fallbacken feilet på første nan).
    """
    def __init__(self, obj):
        self.obj = obj

    def _map(self, fn):
        return self.obj.apply(
            lambda v: nan if v is nan or not isinstance(v, str) else fn(v))

    def contains(self, pat, case=True, regex=True):
        if regex:
            if not case:
                _IC = getattr(re, 'IGNORECASE', None)
                if _IC is not None:
                    # re.IGNORECASE finnes (CPython/Brython/wasm-bygg med
                    # støtte) — bruk ekte flagg, samme oppførsel som
                    # pandas_brython.py.
                    rx = _re_compile(pat, _IC)
                    return self._map(lambda v: rx.search(v) is not None)
                # MicroPython-felle #10: re.IGNORECASE finnes ikke (unix-
                # bygget, bekreftet). Fallback: småbokstav-normaliser mønster
                # og streng i stedet for å sette et flagg. Dette er en
                # tilnærming, ikke identisk med ekte IGNORECASE (f.eks.
                # unicode-kanttilfeller), og gjelder KUN denne fallbacken —
                # ikke case=True-grenen.
                rx = _re_compile(pat.lower())
                return self._map(lambda v: rx.search(v.lower()) is not None)
            rx = _re_compile(pat)
            return self._map(lambda v: rx.search(v) is not None)
        if not case:
            p = pat.lower()
            return self._map(lambda v: p in v.lower())
        return self._map(lambda v: pat in v)

    def startswith(self, pat):
        return self._map(lambda v: v.startswith(pat))

    def endswith(self, pat):
        return self._map(lambda v: v.endswith(pat))

    def lower(self):
        return self._map(lambda v: v.lower())

    def upper(self):
        return self._map(lambda v: v.upper())

    def strip(self, to_strip=None):
        return self._map(lambda v: v.strip(to_strip))

    def title(self):
        return self._map(lambda v: v.title())

    def len(self):
        return self._map(lambda v: len(v))

    def replace(self, pat, repl, regex=False):
        if regex:
            rx = _re_compile(pat)
            return self._map(lambda v: rx.sub(repl, v))
        return self._map(lambda v: v.replace(pat, repl))

    def split(self, pat=None):
        return self._map(lambda v: v.split(pat))

    def get(self, i):
        return self.obj.apply(
            lambda v: v[i] if isinstance(v, (str, list, tuple))
            and -len(v) <= i < len(v) else nan)

    def slice(self, start=None, stop=None, step=None):
        return self._map(lambda v: v[start:stop:step])

    # ── pandas-egne strengmetoder ────────────────────────────────────────
    # Alt som finnes på Pythons str (zfill, isdigit, …) dekkes av
    # __getattr__-fallbacken nederst; her ligger det pandas har i tillegg.

    def extract(self, pat, flags=0, expand=True):
        """
        Regex-grupper → DataFrame (én kolonne per gruppe), eller Series når
        expand=False og mønsteret har nøyaktig én gruppe. Ingen treff → nan.
        """
        rx = _re_compile(pat, flags)
        groups = _group_count(rx, pat)
        if groups == 0:
            raise ValueError('extract: mønsteret må ha minst én gruppe')
        names = {}
        # MicroPython-felle: kompilerte mønstre har ikke groupindex
        for name, num in (getattr(rx, 'groupindex', None) or {}).items():
            names[num - 1] = name
        cols = [[] for _i in range(groups)]
        for v in self.obj.values:
            m = None if (_is_na(v) or not isinstance(v, str)) else rx.search(v)
            for gi in range(groups):
                cols[gi].append(nan if m is None or m.group(gi + 1) is None
                                else m.group(gi + 1))
        if groups == 1 and not expand:
            return Series(cols[0], index=list(self.obj.index), name=self.obj.name)
        out = {}
        for gi in range(groups):
            out[names.get(gi, gi)] = cols[gi]
        return DataFrame(out, index=list(self.obj.index))

    def extractall(self, pat, flags=0):
        """Alle treff per element → DataFrame med (indeks, match)-tupler."""
        rx = _re_compile(pat, flags)
        ngroups = _group_count(rx, pat)
        groups = ngroups or 1
        rows = []
        idx = []
        for label, v in zip(self.obj.index, self.obj.values):
            if _is_na(v) or not isinstance(v, str):
                continue
            for mi, m in enumerate(_re_finditer(rx, v)):
                vals = [m.group(gi + 1) for gi in range(groups)] if ngroups \
                    else [m.group(0)]
                rows.append([nan if x is None else x for x in vals])
                idx.append((label, mi))
        cols = {}
        for gi in range(groups):
            cols[gi] = [r[gi] for r in rows]
        return DataFrame(cols, index=idx)

    def match(self, pat, case=True, flags=0):
        rx = _re_compile(pat, flags if case else (flags | _ignorecase()))
        return self._map(lambda v: rx.match(v) is not None)

    def fullmatch(self, pat, case=True, flags=0):
        rx = _re_compile(pat, flags if case else (flags | _ignorecase()))
        return self._map(lambda v: _full_match(rx, v))

    def findall(self, pat, flags=0):
        rx = _re_compile(pat, flags)
        return self._map(lambda v: [m.group(0) for m in _re_finditer(rx, v)])

    def count(self, pat, flags=0):
        rx = _re_compile(pat, flags)
        return self._map(lambda v: len(_re_finditer(rx, v)))

    def pad(self, width, side='left', fillchar=' '):
        if side not in ('left', 'right', 'both'):
            raise ValueError("pad: side må være 'left', 'right' eller 'both'")
        return self._map(lambda v: _pad_text(v, width, fillchar, side))

    def center(self, width, fillchar=' '):
        return self.pad(width, 'both', fillchar)

    def ljust(self, width, fillchar=' '):
        return self.pad(width, 'right', fillchar)

    def rjust(self, width, fillchar=' '):
        return self.pad(width, 'left', fillchar)

    def zfill(self, width):
        # str.zfill mangler i MicroPython; negativt fortegn holdes først
        def _z(v):
            if v.startswith('-') or v.startswith('+'):
                return v[0] + _pad_text(v[1:], width - 1, '0', 'left')
            return _pad_text(v, width, '0', 'left')
        return self._map(_z)

    def cat(self, others=None, sep=None, na_rep=None):
        """
        others=None: slå sammen alle verdiene til ÉN streng (nan hoppes over
        med mindre na_rep er satt) — pandas-semantikk.
        """
        joiner = '' if sep is None else sep
        if others is None:
            parts = []
            for v in self.obj.values:
                if _is_na(v) or not isinstance(v, str):
                    if na_rep is None:
                        continue
                    parts.append(na_rep)
                else:
                    parts.append(v)
            return joiner.join(parts)
        other_vals = list(others.values) if isinstance(others, Series) else list(others)
        out = []
        for v, o in zip(self.obj.values, other_vals):
            if _is_na(v) or _is_na(o):
                out.append(na_rep if na_rep is not None else nan)
            else:
                out.append(str(v) + joiner + str(o))
        return Series(out, index=list(self.obj.index), name=self.obj.name)

    def repeat(self, repeats):
        if isinstance(repeats, (list, tuple, Series)):
            counts = list(repeats.values) if isinstance(repeats, Series) else list(repeats)
            out = []
            for v, c in zip(self.obj.values, counts):
                out.append(nan if (_is_na(v) or not isinstance(v, str)) else v * c)
            return Series(out, index=list(self.obj.index), name=self.obj.name)
        return self._map(lambda v: v * repeats)

    def slice_replace(self, start=None, stop=None, repl=''):
        s0 = 0 if start is None else start
        return self._map(lambda v: v[:s0] + repl + (v[stop:] if stop is not None else ''))

    def wrap(self, width):
        def _wrap(v):
            words = v.split()
            lines = []
            cur = ''
            for w in words:
                if cur and len(cur) + 1 + len(w) > width:
                    lines.append(cur)
                    cur = w
                else:
                    cur = w if not cur else cur + ' ' + w
            if cur:
                lines.append(cur)
            return '\n'.join(lines)
        return self._map(_wrap)

    def join(self, sep):
        return self._map(lambda v: sep.join(v))

    def partition(self, sep=' ', expand=True):
        return self._partition(sep, expand, False)

    def rpartition(self, sep=' ', expand=True):
        return self._partition(sep, expand, True)

    def _partition(self, sep, expand, from_right):
        rows = []
        for v in self.obj.values:
            if _is_na(v) or not isinstance(v, str):
                rows.append([nan, nan, nan])
            else:
                rows.append(list(v.rpartition(sep) if from_right else v.partition(sep)))
        if not expand:
            return Series([tuple(r) for r in rows], index=list(self.obj.index))
        return DataFrame({0: [r[0] for r in rows], 1: [r[1] for r in rows],
                          2: [r[2] for r in rows]}, index=list(self.obj.index))

    def get_dummies(self, sep='|'):
        """Strenger med skilletegn → 0/1-kolonner, én per unik del."""
        split_vals = []
        for v in self.obj.values:
            split_vals.append([] if (_is_na(v) or not isinstance(v, str))
                              else v.split(sep))
        keys = []
        for parts in split_vals:
            for p in parts:
                if p not in keys:
                    keys.append(p)
        keys = sorted(keys)
        out = {}
        for k in keys:
            out[k] = [1 if k in parts else 0 for parts in split_vals]
        return DataFrame(out, index=list(self.obj.index))

    def removeprefix(self, prefix):
        return self._map(lambda v: v[len(prefix):] if v.startswith(prefix) else v)

    def removesuffix(self, suffix):
        return self._map(
            lambda v: v[:len(v) - len(suffix)] if suffix and v.endswith(suffix) else v)

    def __getattr__(self, item):
        # Fallback for øvrige str-metoder — med nan-vakt, ulikt den gamle.
        # Ukjente navn ga før «type object 'str' has no attribute 'extract'»,
        # som pekte helt feil sted; nå navngis accessoren.
        str_fn = getattr(str, item, None)
        if str_fn is None:
            raise AttributeError(
                "'.str'-accessoren har ingen metode %r (verken pandas-egen "
                "eller en str-metode)" % item)
        def _call(*args, **kwargs):
            return self.obj.apply(
                lambda v: nan if v is nan or not isinstance(v, str)
                else str_fn(v, *args, **kwargs))
        return _call


class DT:
    """
    Dato-accessor med eksplisitte properties (den gamle getattr(datetime, …)
    ga descriptors, så .dt.year krasjet). nan passerer gjennom som nan.
    """
    def __init__(self, obj):
        self.obj = obj

    def _map(self, fn):
        return self.obj.apply(lambda v: nan if v is nan else fn(v))

    @property
    def year(self):
        return self._map(lambda v: v.year)

    @property
    def month(self):
        return self._map(lambda v: v.month)

    @property
    def day(self):
        return self._map(lambda v: v.day)

    @property
    def hour(self):
        return self._map(lambda v: v.hour)

    @property
    def minute(self):
        return self._map(lambda v: v.minute)

    @property
    def second(self):
        return self._map(lambda v: v.second)

    @property
    def dayofweek(self):
        return self._map(lambda v: v.weekday())

    weekday = dayofweek

    @property
    def date(self):
        return self._map(lambda v: v.date())

    @property
    def microsecond(self):
        return self._map(lambda v: v.microsecond)

    @property
    def time(self):
        return self._map(lambda v: v.time())

    @property
    def quarter(self):
        return self._map(lambda v: (v.month - 1) // 3 + 1)

    @property
    def dayofyear(self):
        return self._map(lambda v: _day_of_year(v.year, v.month, v.day))

    day_of_year = dayofyear

    @property
    def day_of_week(self):
        return self._map(lambda v: v.weekday())

    @property
    def days_in_month(self):
        return self._map(lambda v: _days_in_month(v.year, v.month))

    daysinmonth = days_in_month

    @property
    def is_leap_year(self):
        return self._map(lambda v: _is_leap(v.year))

    @property
    def is_month_start(self):
        return self._map(lambda v: v.day == 1)

    @property
    def is_month_end(self):
        return self._map(lambda v: v.day == _days_in_month(v.year, v.month))

    @property
    def is_quarter_start(self):
        return self._map(lambda v: v.day == 1 and v.month in (1, 4, 7, 10))

    @property
    def is_quarter_end(self):
        return self._map(
            lambda v: v.month in (3, 6, 9, 12) and v.day == _days_in_month(v.year, v.month))

    @property
    def is_year_start(self):
        return self._map(lambda v: v.month == 1 and v.day == 1)

    @property
    def is_year_end(self):
        return self._map(lambda v: v.month == 12 and v.day == 31)

    def day_name(self):
        # engelske navn, som pandas' standard-locale
        return self._map(lambda v: _DAY_NAMES[v.weekday()])

    def month_name(self):
        return self._map(lambda v: _MONTH_NAMES[v.month - 1])

    def normalize(self):
        return self._map(lambda v: datetime(v.year, v.month, v.day))

    def isocalendar(self):
        """DataFrame med year/week/day, som pandas."""
        rows = {'year': [], 'week': [], 'day': []}
        for v in self.obj.values:
            if _is_na(v):
                rows['year'].append(nan)
                rows['week'].append(nan)
                rows['day'].append(nan)
                continue
            iso_day = v.weekday() + 1
            # torsdagen i samme uke bestemmer ISO-året
            thursday = _to_ordinal(v.year, v.month, v.day) + (4 - iso_day)
            iso_year = _from_ordinal(thursday)[0]
            jan4 = _to_ordinal(iso_year, 1, 4)
            week1_monday = jan4 - ((jan4 - 1) % 7)
            rows['year'].append(iso_year)
            rows['week'].append((thursday - week1_monday) // 7 + 1)
            rows['day'].append(iso_day)
        return DataFrame(rows, index=list(self.obj.index))

    def _round_to(self, freq, mode):
        secs = _freq_seconds(freq)

        def _apply(v):
            total = (_to_ordinal(v.year, v.month, v.day) * 86400
                     + v.hour * 3600 + v.minute * 60 + v.second)
            rest = total % secs
            if rest:
                if mode == 'ceil':
                    total += secs - rest
                elif mode == 'floor':
                    total -= rest
                else:
                    total += (secs - rest) if rest * 2 >= secs else -rest
            days, rem = total // 86400, total % 86400
            y, m, d = _from_ordinal(days)
            return datetime(y, m, d, rem // 3600, (rem % 3600) // 60, rem % 60)
        return self._map(_apply)

    def floor(self, freq):
        return self._round_to(freq, 'floor')

    def ceil(self, freq):
        return self._round_to(freq, 'ceil')

    def round(self, freq):
        return self._round_to(freq, 'round')

    def strftime(self, fmt):
        return self._map(lambda v: v.strftime(fmt))



"""
Contains the DataFrame class
"""








class DataFrame:
    """
    The only mutable attribute is the data.
    Shape is equal to the view.
    If a row is added, data is recreated and step is also updated.
    If a column is added, data is appended *only* if the dataframe view covers
    the entire dataset (shape equals len index, columns). Otherwise, a copy is made
    View is a tuple of two slices, for the row and column. Steps are not taken into
    account in view, it is high level. This is contrary to Series
    step = len(index) = shape(0) = view[0].stop - view[0].start
    len(columns) = shape(1) = view[1].stop - view[1].start
    """

    ITERABLE_1D = (list, set, tuple, Series)

    def __init__(self, data=None, index=None, columns=None):
        self.columns = tuple(columns) if columns else tuple()  # type: tuple
        self.index = tuple(index) if index else tuple()  # type: tuple
        self.data = []  # type: list
        self.name = None  # type: str
        self.step = 0  # type: int
        self.shape = (0, 0)  # type: tuple
        self.view = (_mkslice(0, 0), _mkslice(0, 0))  # type: tuple
        self.iloc = ILocDF(self)  # type: ILocDF
        self.loc = LocDF(self)  # type: LocDF
        self.plot = Plot(self)
        self.at = AtDF(self)
        self.iat = IAtDF(self)
        self._cats = {}   # {kolonnenavn: CategoricalDtype}

        if data is None:
            return
        if hasattr(data, 'tolist') and not isinstance(data, (Series, DataFrame)):
            data = data.tolist()          # numpy_brython-ndarray o.l. -> lister
        if isinstance(data, dict):
            for _k, _v in data.items():
                if isinstance(_v, Series) and _v._cat is not None:
                    self._cats[_k] = _v._cat
            data = {k: (v.tolist() if hasattr(v, 'tolist')
                        and not isinstance(v, (Series, DataFrame)) else v)
                    for k, v in data.items()}
            self.step = len(data[list(data.keys())[0]])
            self.data = list(_chain_from_iterable(data.values()))
            self.columns = tuple(data.keys())
        elif isinstance(data, list):
            if isinstance(data[0], self.ITERABLE_1D):
                # if they are series, try to extract the data
                try:
                    self.index = tuple(d.name for d in data)
                    self.columns = data[0].index
                except AttributeError:
                    pass
                self.step = len(data)

                data = list(zip(*data))
                for item in data:
                    self.data.extend(item)

            elif isinstance(data[0], dict):
                for d_dict in data:
                    key, val = next(iter(d_dict.items()))
                    self.columns = self.columns + (key,)
                    self.data.extend(val)
                self.step = len(val)

        if len(self.columns) == 0:
            self.columns = tuple(_ci for _ci in range(len(self.data) // self.step))

        if len(self.index) == 0:
            self.index = tuple(_ci for _ci in range(self.step))
        self.shape = (self.step, len(self.columns))
        self.view = (_mkslice(0, self.shape[0]), _mkslice(0, self.shape[1]))

    @classmethod
    def from_data(cls, data, index, columns, view, step):
        self = cls()
        self.data = data
        self.columns = columns
        self.index = index
        self.view = view
        self.step = step
        self.shape = (
            self.view[0].stop - self.view[0].start,
            self.view[1].stop - self.view[1].start,
        )
        self.iloc = ILocDF(self)
        self.loc = LocDF(self)

        return self

    @classmethod
    def class_init(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    @classmethod
    def series_from_data(cls, *args):
        return Series.from_data(*args)

    def __str__(self):
        try:
            max_rows = DISPLAY_MAX_ROWS
            max_cols = DISPLAY_MAX_COLS
            vals = self.values
            n_rows = len(vals)
            n_cols = len(self.columns)

            # Determine rows to show
            if n_rows <= max_rows:
                show_row_idx = list(range(n_rows))
                rows_trunc = False
            else:
                head = max_rows // 2
                tail = max_rows - head
                show_row_idx = list(range(head)) + list(range(n_rows - tail, n_rows))
                rows_trunc = True

            # Determine cols to show
            if n_cols <= max_cols:
                show_col_idx = list(range(n_cols))
                cols_trunc = False
            else:
                show_col_idx = list(range(max_cols))
                cols_trunc = True

            # Compute widths (auto width unless fixed is provided)
            if DISPLAY_INDEX_WIDTH is not None:
                index_width = int(DISPLAY_INDEX_WIDTH)
            else:
                index_width = max([len(str(self.index[i])) for i in show_row_idx] + [0])

            col_widths = []
            for j in show_col_idx:
                if DISPLAY_COL_WIDTH is not None:
                    width = int(DISPLAY_COL_WIDTH)
                else:
                    col_name = str(self.columns[j])
                    width = len(col_name)
                    for i in show_row_idx:
                        width = max(width, len(_fmt_cell(vals[i][j])))
                col_widths.append(width)

            # Header
            header_cells = ["".ljust(index_width)]
            for j, w in zip(show_col_idx, col_widths):
                header_cells.append(_truncate_cell(self.columns[j], w).ljust(w))
            if cols_trunc:
                header_cells.append("...")
            header = DISPLAY_COL_SEP.join(header_cells)

            # Body
            body_lines = []
            for idx_pos, i in enumerate(show_row_idx):
                row_cells = [str(self.index[i]).ljust(index_width)]
                for j, w in zip(show_col_idx, col_widths):
                    row_cells.append(_truncate_cell(vals[i][j], w).ljust(w))
                if cols_trunc:
                    row_cells.append("...")
                body_lines.append(DISPLAY_COL_SEP.join(row_cells))
                if rows_trunc and idx_pos + 1 == len(show_row_idx) // 2:
                    body_lines.append("...")

            # Footer like pandas: show shape when truncated
            footer = None
            if rows_trunc or cols_trunc:
                footer = f"[{self.shape[0]} rows x {self.shape[1]} columns]"
            return _LINESEP.join([header] + body_lines + ([footer] if footer else []))
        except Exception:
            string = "DataFrame: " + _LINESEP + str(self.columns) + _LINESEP
            string += _LINESEP.join(str(d) for d in zip(self.index, self.values))
            return string

    def __getitem__(self, cols):
        # gets here as slice and series
        if isinstance(cols, tuple):
            return self.loc[cols]
        elif isinstance(cols, slice) or is_bool(cols) or is_2d_bool(cols):
            return self.loc[cols, :]
        res = self.loc[:, cols]
        # Kategori-metadata lever på framen (_cats) og må hektes på serien
        # som leveres ut, ellers mister df['grp'] kategorirekkefølgen.
        cats = self._cats
        if cats:
            if isinstance(res, Series):
                try:
                    if cols in cats:
                        res._cat = cats[cols]
                except TypeError:
                    pass
            elif isinstance(res, DataFrame):
                res._cats = dict((c, cats[c]) for c in res.columns if c in cats)
        return res
    
    def __getattr__(self, name):
        if name in self.columns:
            return self[name]
        else:
            raise AttributeError(f"'MyDataFrame' object has no attribute '{name}'")


    def __setitem__(self, key, value):
        """
        This implementation just adds a new columns
        """
        if hasattr(value, 'tolist') and not isinstance(value, (Series, DataFrame)):
            value = value.tolist()        # numpy_brython-ndarray o.l. -> lister
        # if two params were provided (i.e. if it's a tuple) forward it
        # if it is a slice or boolean, forward as row indexer
        # otherwise, forward as column indexer
        if isinstance(key, (tuple, self.__class__)):
            self.loc[key] = value
        elif isinstance(key, slice) or is_bool(key):
            self.loc[key, :] = value
        else:
            self.loc[:, key] = value

    def __delitem__(self, cols):
        # del df['kol'] SKAL mutere (som pandas) — derfor _drop_inplace, ikke drop()
        self._drop_inplace(cols, 1)

    def __lt__(self, other):
        df = self.copy()
        df.data = [item < other for item in df.data]
        return df

    def __le__(self, other):
        df = self.copy()
        df.data = [item <= other for item in df.data]
        return df

    def __gt__(self, other):
        df = self.copy()
        df.data = [item > other for item in df.data]
        return df

    def __ge__(self, other):
        df = self.copy()
        df.data = [item >= other for item in df.data]
        return df

    def __eq__(self, other):
        df = self.copy()
        df.data = [item == other for item in df.data]
        return df

    def __ne__(self, other):
        df = self.copy()
        df.data = [item != other for item in df.data]
        return df

    # Elementwise arithmetic with scalars (simple support)
    def _elemwise_scalar(self, other, op):
        df = self.copy()
        try:
            df.data = [op(item, other) if item is not nan else nan for item in df.data]
        except TypeError:
            # If other is not a scalar, fallback: raise
            raise TypeError("Only scalar operations are supported in this simplified DataFrame arithmetic")
        return df

    def __add__(self, other):
        return self._elemwise_scalar(other, lambda a, b: a + b)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        return self._elemwise_scalar(other, lambda a, b: a - b)

    def __rsub__(self, other):
        return self._elemwise_scalar(other, lambda a, b: other - a)

    def __mul__(self, other):
        return self._elemwise_scalar(other, lambda a, b: a * b)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        return self._elemwise_scalar(other, lambda a, b: a / b)

    def __rtruediv__(self, other):
        return self._elemwise_scalar(other, lambda a, b: other / a)

    def __floordiv__(self, other):
        return self._elemwise_scalar(other, lambda a, b: a // b)

    def __rfloordiv__(self, other):
        return self._elemwise_scalar(other, lambda a, b: other // a)

    def __pow__(self, other):
        return self._elemwise_scalar(other, lambda a, b: a ** b)

    def __rpow__(self, other):
        return self._elemwise_scalar(other, lambda a, b: other ** a)

    def __mod__(self, other):
        return self._elemwise_scalar(other, lambda a, b: a % b)

    def __rmod__(self, other):
        return self._elemwise_scalar(other, lambda a, b: other % a)

    def __iter__(self):
        return iter(self.columns)

    def __invert__(self):
        df_cp = self.copy()
        for i in range(len(df_cp.data)):
            df_cp.data[i] = not df_cp.data[i]
        return df_cp

    def __len__(self):
        return self.shape[0]

    def __repr__(self):
        return str(self)

    def _repr_html_(self):
        """
        HTML table-like representation for rich frontends.
        """
        try:
            # header
            header_cells = ["<th></th>"] + [f"<th>{html.escape(str(c))}</th>" for c in self.columns]
            thead = "<tr>" + "".join(header_cells) + "</tr>"

            # body rows
            body_rows = []
            values = self.values
            for i, row in enumerate(values):
                idx_html = html.escape(str(self.index[i])) if i < len(self.index) else ""
                cells = [f"<th>{idx_html}</th>"]
                for val in row:
                    cells.append(f"<td>{html.escape(_fmt_cell(val))}</td>")
                body_rows.append("<tr>" + "".join(cells) + "</tr>")
            caption = f"<caption>DataFrame ({self.shape[0]} x {self.shape[1]})</caption>"
            return "<table>" + caption + "<thead>" + thead + "</thead><tbody>" + "".join(body_rows) + "</tbody></table>"
        except Exception:
            return None

    def drop(self, labels=None, axis=0, index=None, columns=None):
        """
        Drop labels along the given axis and return a NEW DataFrame — mottakeren
        blir IKKE endret (pandas-semantikk; shimmen muterte fram til
        2026-07-26, så `df.drop('kol', axis=1)` ødela brukerens frame).

        axis: 0/'index' for rader (pandas-default), 1/'columns' for kolonner.
        index=/columns= er alternativet til labels+axis, som i pandas.

        Kall UTEN labels/index/columns beholder den interne view-trimmingen og
        muterer fortsatt — den grenen kalles bare på ferske objekter (copy(),
        add_empty_series, LocDF). Intern kode som vil droppe etiketter på
        stedet skal bruke _drop_inplace().
        """
        if labels is None and index is None and columns is None:
            return self._trim_to_view()
        if index is not None or columns is not None:
            cp = self.copy()
            if index is not None:
                cp._drop_inplace(index, 0)
            if columns is not None:
                cp._drop_inplace(columns, 1)
            return cp
        cp = self.copy()
        cp._drop_inplace(labels, axis)
        return cp

    def _trim_to_view(self):
        """Trimmer datasettet til gjeldende view. Muterer self."""
        if True:
            to_delete = self.view[1].stop
            num = 0

            # build new dataset without the columns outside view
            data_cols = []
            for col_index in range(self.view[1].start, to_delete):
                data_cols.append(
                    self.data[
                        self.view[0].start
                        + col_index * self.step : self.view[0].stop
                        + col_index * self.step
                    ]
                )
            for col_index in range(to_delete + num, self.view[1].stop):
                data_cols.append(
                    self.data[
                        self.view[0].start
                        + col_index * self.step : self.view[0].stop
                        + col_index * self.step
                    ]
                )
            self.data = []
            for col in data_cols:
                self.data.extend(col)
            self.columns = self.columns[0:to_delete] + self.columns[to_delete + num :]
            self.shape = (self.shape[0], self.shape[1] - num)
            self.view = (_mkslice(0, len(self.index)), _mkslice(0, len(self.columns)))
            self.step = len(self.index)
            return self

    def _drop_inplace(self, labels, axis=1):
        """
        Dropper etiketter og MUTERER self. Intern motor for drop(); brukes
        direkte av __delitem__, groupby og set_index, som alle trenger
        på-stedet-semantikk.
        """
        # Normalize axis
        if axis in ["columns", "column", "col", 1]:
            axis = 1
        elif axis in ["rows", "row", "index", 0]:
            axis = 0
        else:
            axis = 1

        # Normalize labels to a set
        if isinstance(labels, (list, tuple, set)):
            labels_set = set(labels)
        else:
            labels_set = {labels}

        if axis == 1:
            # drop columns
            keep_cols = [c for c in self.columns if c not in labels_set]
            # rebuild data with kept columns only
            data_cols = []
            for col_label in keep_cols:
                j = self.columns.index(col_label)
                data_cols.append(
                    self.data[
                        self.view[0].start
                        + j * self.step : self.view[0].stop
                        + j * self.step
                    ]
                )
            self.data = []
            for col in data_cols:
                self.data.extend(col)
            self.columns = tuple(keep_cols)
            self.shape = (len(self.index), len(self.columns))
            self.view = (_mkslice(0, len(self.index)), _mkslice(0, len(self.columns)))
            self.step = len(self.index)
            return self
        else:
            # drop rows
            keep_rows = [_ci for _ci, idx in enumerate(self.index) if idx not in labels_set]
            # rebuild data by selecting kept rows for each column
            data_cols = []
            for j in range(self.view[1].start, self.view[1].stop):
                col_vals = [
                    self.data[i + j * self.step]
                    for i in range(self.view[0].start, self.view[0].stop)
                    if (i - self.view[0].start) in keep_rows
                ]
                data_cols.append(col_vals)
            self.data = []
            for col in data_cols:
                self.data.extend(col)
            self.index = tuple(self.index[i] for i in keep_rows)
            self.shape = (len(self.index), len(self.columns))
            self.view = (_mkslice(0, len(self.index)), _mkslice(0, len(self.columns)))
            self.step = len(self.index)
            return self

    def copy(self):
        """
        Creates a copy of the dataframe and trims the data with _trim_to_view
        :return:
        """
        df = DataFrame.from_data(
            self.data, self.index, self.columns, self.view, self.step
        )
        df._trim_to_view()
        df._cats = dict(self._cats)
        return df

    def equals(self, other):
        return (self.values == other.values) and (self.shape == other.shape)

    @property
    def values(self):
        data_rows = []
        for row_index in range(self.view[0].start, self.view[0].stop):
            data_rows.append(
                self.data[
                    row_index
                    + self.step * self.view[1].start : row_index
                    + self.step * self.view[1].stop : self.step
                ]
            )
        return data_rows

    def bound_int_to_df(self, raw_int, axis):
        """
        Transforms an index int to the actual axis index of data,
        taking bounds into account
        e.g.
        [0,| 1, 2, 3, 4, 5, | 6]
        If `2` is given, it should access "3", thus index 2 is actually 3.
        -1 becomes 5
        6 would be an index error
        Slices are handled by a bound_slice_to_df

        :param raw_int:
        :param axis:
        :return:
        """
        if axis in [0, "row", "rows"]:
            view_min = self.view[0].start
            view_max = self.view[0].stop
        elif axis in [1, "column", "columns"]:
            view_min = self.view[1].start
            view_max = self.view[1].stop
        else:
            raise UserWarning

        # handle negative ints
        if raw_int < 0:
            start = view_max + raw_int
        else:
            start = view_min + raw_int

        # check bounds
        if start > view_max or start < view_min:
            raise IndexError

        return start

    def bound_slice_to_df(self, raw_slice, axis):
        """
        Transforms a slice to the actual axis view for the data
        :param raw_slice: relative slice
        :return: slice to underlying data
        """
        if axis in [0, "row", "rows"]:
            view_start = self.view[0].start
            view_stop = self.view[0].stop
        elif axis in [1, "column", "columns"]:
            view_start = self.view[1].start
            view_stop = self.view[1].stop
        else:
            pass

        if raw_slice.start:
            if raw_slice.start < 0:
                start = max(view_stop + raw_slice.start, view_start)
            else:
                start = min(view_start + raw_slice.start, view_stop)
        else:
            start = view_start

        if raw_slice.stop:
            if raw_slice.stop < 0:
                stop = max(view_stop + raw_slice.stop, view_start)
            else:
                stop = min(view_start + raw_slice.stop, view_stop)
        else:
            stop = view_stop
        return _mkslice(start, stop)

    def bound_iterable_to_df(self, raw_iter, axis):
        """
        Converts indicies to the actual data indicies
        :param raw_iter:
        :param axis:
        :return:
        """
        return [self.bound_int_to_df(item, axis) for item in raw_iter]

    def convert_slice(self, raw_slice, axis):
        """
        Removes the None from the slice and replaces it with length of rows or columns.
        doesn't adjust based on view
        :param raw_slice:
        :param axis:
        :return:
        """
        if axis in [0, "row", "rows"]:
            max_stop = len(self.index)
        elif axis in [1, "columns", "cols", "col"]:
            max_stop = len(self.columns)

        if not raw_slice.start:
            start = 0
        elif raw_slice.start < 0:
            start = max(0, max_stop + raw_slice.start)
        else:
            start = raw_slice.start

        if not raw_slice.stop:
            stop = max_stop
        elif raw_slice.stop < 0:
            stop = max(0, max_stop + raw_slice.stop)
        else:
            stop = raw_slice.stop
        return _mkslice(start, stop)

    def is_view(self):
        """
        Determines whether or not the dataframe is a view of another dataframe.
        Checks if the shape is the sshape of the entire data
        :return:
        """
        return self.shape[0] != self.step or self.shape[1] != len(self.data) / self.step

    def index_of(self, item, axis=0):
        """
        Returns the integer index of a column/index label
        :param item: iterable or label
        :param axis: 0 - search index; 1 - search column labels
        :return: list(int) or int
        """
        if axis in [0, "rows", "row"]:
            names = self.index
        else:
            names = self.columns
        if isinstance(item, self.ITERABLE_1D):
            # bypass for boolean
            if is_bool(item):
                return item
            return [names.index(i) for i in item]
        elif isinstance(item, slice):
            start = None if item.start is None else names.index(item.start)
            stop = None if item.stop is None else names.index(item.stop)
            return _mkslice(start, stop)
        else:
            try:
                return names.index(item)
            except ValueError:
                return None

    def add_empty_series(self, name, axis=0):
        """
        Adds a new row/column to a dataframe.

        If the dataframe is a view, it will make a copy of itself and trim its
        :param name: Index/column name
        :param axis: int; 0 - adds a row. 1 - adds a column
        :return: None. Does so in place.
        """
        # if its a view, make a copy
        if self.is_view():
            self.drop()

        # Add a row
        if axis == 0:
            self.index = self.index + (name,)
            ndata = []
            for i in range(self.shape[1]):
                ndata.extend(self.data[i * self.step : (i + 1) * self.step] + [nan])
            self.data = ndata
            self.shape = (self.shape[0] + 1, self.shape[1])
            self.view = (_mkslice(self.view[0].start, self.view[0].stop + 1), self.view[1])
            self.step = self.step + 1
        # add a column
        elif axis == 1:
            self.columns = self.columns + (name,)
            self.data = self.data + [nan] * self.shape[0]
            self.shape = (self.shape[0], self.shape[1] + 1)
            self.view = (self.view[0], _mkslice(self.view[1].start, self.view[1].stop + 1))

    def append(self, other, ignore_index=False):
        """
        Appends either a DataFrame or Series.

        :param other: DataFrame or Series
        :param ignore_index: Bool, If false, will create a new index
        :return: DataFrame
        """

        if isinstance(other, self.__class__):
            # Determine new columns
            columns = self.columns + tuple(
                col for col in other.columns if col not in self.columns
            )
            # Create data, with nans if there are new columns
            data_columns = []
            for col in columns:
                if col in self.columns:
                    temp = self[col].values
                else:
                    temp = [nan] * len(self)
                if col in other.columns:
                    temp += other[col].values
                else:
                    temp += [nan] * len(other)
                data_columns.append(temp)

            # new index
            if ignore_index:
                index = None
            else:
                index = self.index + other.index
        elif isinstance(other, self.ITERABLE_1D):
            if not ignore_index and other.name is None:
                raise TypeError(
                    "Can only append a Series/Array if ignore_index=True or if the Series has a name"
                )
            columns = self.columns + tuple(
                col for col in other.index if col not in self.columns
            )
            # generate new data
            data_columns = []
            for col in columns:
                # df data
                if col in self.columns:
                    temp = self[col].values
                else:
                    temp = [nan] * len(self)
                # iterable data
                if col in other.index:
                    temp.append(other[col])
                else:
                    temp.append(nan)
                data_columns.append(temp)

            # new index
            if ignore_index:
                index = None
            else:
                index = self.index + other.name
        # new dataframe
        return self.class_init(
            {k: v for k, v in zip(columns, data_columns)}, index=index
        )

    def applymap(self, func):
        cp = self.copy()
        cp.data = [func(item) for item in cp.data]
        return cp

    def apply(self, func, axis=0, dropna=True):

        res = []
        index = []
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows

        for item in iterator():
            item = list(item)
            try:
                # if the function is reducing and works on an iterable, try that
                if dropna:
                    item[1] = item[1].dropna()
                # it it was all nans, just put a nan there
                if len(item[1]) == 0:
                    res.append(nan)
                else:
                    res.append(func(item[1]))
            except TypeError:
                try:
                    # otherwise, elementwise
                    res.append(item[1].apply(func))
                except TypeError:
                    # otherwise, skip
                    continue

            index.append(item[0])
        if isinstance(res[0], Series):
            if axis == 0:
                return self.class_init(res).transpose()
            else:
                return self.class_init(res)
        else:
            return Series(res, index, name=self.name)

    def iterrows(self):
        for i in range(len(self)):
            try:
                yield (self.index[i], self.iloc[i, :])
            except:
                return

    def itercols(self):
        for i in range(len(self.columns)):
            try:
                yield (self.columns[i], self.iloc[:, i])
            except:
                return

    def iteritems(self):
        return self.itercols()

    def transpose(self):
        new_cols = self.index
        new_index = self.columns
        data = list(zip(*self.values))
        cp = self.class_init(data, columns=new_cols, index=new_index)
        return cp

    def sort_values(self, by, ascending=True, axis=0, na_position="last"):
        if axis == 0 and isinstance(by, (list, tuple)):
            # Multi-column sort of rows
            cols = list(by)
            if isinstance(ascending, (list, tuple)):
                asc_list = list(ascending)
            else:
                asc_list = [bool(ascending)] * len(cols)

            def key_for_row(i):
                keys = []
                for col, asc in zip(cols, asc_list):
                    val = self.loc[self.index[i], col]
                    if val is nan:
                        # push NaN last for ascending
                        keys.append((1, None) if asc else (-1, None))
                    else:
                        keys.append((0, val) if asc else (0, val))
                return tuple(keys)

            order = sorted(range(self.shape[0]), key=key_for_row)
            return self.iloc[order, :]
        else:
            if axis == 0:
                it = self.itercols
                ser = self.loc[:, by]
            else:
                it = self.iterrows
                ser = self.loc[by, :]

            new_index = ser.sort_values(ascending, na_position).index
            res = []
            cols = []

            for ser in it():
                res.append(ser[1].loc[new_index])
                cols.append(ser[0])

            cp = self.class_init(res, columns=cols)
            if axis == 0:
                cp = cp.transpose()
            return cp

    def reset_index(self, drop=False):
        cp = self.copy()
        if not drop:
            cp["index"] = cp.index
            cp = cp.loc[:, cp.columns[-1:] + cp.columns[:-1]]
        cp.index = tuple(_ci for _ci in range(len(self)))

        return cp

    def head(self, n=5):
        return self.iloc[:n, :]

    def tail(self, n=5):
        return self.iloc[-n:, :]

    def groupby(self, by, sort=True):
        """
        Simple groupby implementation.

        by: kolonnenavn eller liste av kolonnenavn. Liste gir flat indeks av
        tupler (ingen MultiIndex — bevisst). sort=True sorterer gruppenøklene
        som pandas; usammenliknbare nøkler faller tilbake til
        opptredensrekkefølge.
        """
        gb = GroupBy()
        gb.parent = self
        gb.by = by

        multi = isinstance(by, (list, tuple))
        keyfns = None
        if multi:
            key_cols = [list(self[b].values) for b in by]
            keys = list(dict.fromkeys(zip(*key_cols)))
            keyfns = [_sort_key(self[b]) for b in by]
            if not any(f is not None for f in keyfns):
                keyfns = None
        else:
            keys = self[by].unique()
            keyfns = _sort_key(self[by])
        if sort:
            try:
                if keyfns is None:
                    keys = sorted(keys)
                elif multi:
                    # kategoriske nøkkelkolonner sorteres på kategoriposisjon
                    keys = sorted(keys, key=lambda k: tuple(
                        (f(v) if f is not None else v) for f, v in zip(keyfns, k)))
                else:
                    keys = sorted(keys, key=keyfns)
            except TypeError:
                pass  # blandede typer: behold opptredensrekkefølge

        for item in keys:
            if multi:
                mask = self[by[0]] == item[0]
                for j in range(1, len(by)):
                    other = self[by[j]] == item[j]
                    mask.data = [a and b for a, b in zip(mask.values, other.values)]
                df = self.loc[mask, :]
                df.name = item
                for b in by:
                    df._drop_inplace(b, 1)
            else:
                df = self.loc[self[by] == item, :]
                df.name = item
                df._drop_inplace(by, 1)
            gb.dfs.append(df)
        return gb

    def mean(self, axis=0, dropna=True):
        return self.apply(lambda x: sum(x) / len(x), axis=axis, dropna=dropna)

    def sum(self, axis=0, dropna=True):
        if axis == 0:
            iterator = self.iterrows
        else:
            iterator = self.itercols

        res = None
        for item in iterator():
            if item is None:
                res = item[1]
            else:
                res += item[1]
        res.name = self.name
        return res
    
    def min(self, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.min(dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def max(self, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.max(dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def median(self, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.median(dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def quantile(self, q=0.5, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.quantile(q=q, dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def var(self, ddof=1, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.var(ddof=ddof, dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def std(self, ddof=1, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.std(ddof=ddof, dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def idxmin(self, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.idxmin(dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def idxmax(self, axis=0, dropna=True):
        if axis == 0:
            iterator = self.itercols
        else:
            iterator = self.iterrows
        vals = []
        idx = []
        for label, ser in iterator():
            vals.append(ser.idxmax(dropna=dropna))
            idx.append(label)
        return Series(vals, idx, name=self.name)

    def isna(self):
        cp = self.copy()
        cp.data = [item is nan for item in cp.data]
        return cp

    def notna(self):
        return ~self.isna()

    def fillna(self, value=None):
        """
        Fill NA/NaN values with a scalar or with a per-column dict.
        """
        cp = self.copy()
        # method-based fill per column
        if isinstance(value, str) and value in ("ffill", "pad", "bfill", "backfill"):
            method = value
            for j in range(cp.shape[1]):
                ser = cp.iloc[:, j]
                cp.iloc[:, j] = ser.fillna(method=method).values
            return cp
        if isinstance(value, dict):
            col_to_val = value
            for j, col in enumerate(cp.columns):
                fill_val = col_to_val.get(col, None)
                if fill_val is None:
                    continue
                for i in range(cp.shape[0]):
                    idx = i + j * cp.step
                    if cp.data[idx] is nan:
                        cp.data[idx] = fill_val
            return cp
        # scalar fill
        for k in range(len(cp.data)):
            if cp.data[k] is nan:
                cp.data[k] = value
        return cp

    def dropna(self, axis=0, how="any", subset=None):
        """
        Drop rows or columns containing NaN.
        axis: 0 rows, 1 columns
        how: 'any' or 'all'
        subset: list of column labels (for axis=0) or row labels (for axis=1)
        """
        if axis in ["columns", "column", 1]:
            axis = 1
        else:
            axis = 0

        if axis == 0:
            # determine columns to consider
            if subset is None:
                col_indices = list(range(self.shape[1]))
            else:
                if isinstance(subset, (list, tuple, set)):
                    col_indices = [self.columns.index(c) for c in subset]
                else:
                    col_indices = [self.columns.index(subset)]
            keep_rows = []
            for i in range(self.shape[0]):
                row_vals = [self.data[i + j * self.step] for j in col_indices]
                na_count = sum(1 for v in row_vals if v is nan)
                drop_row = (how == "any" and na_count > 0) or (
                    how == "all" and na_count == len(row_vals)
                )
                if not drop_row:
                    keep_rows.append(i)
            if len(keep_rows) == 0:
                # return an empty DataFrame with same columns
                return self.class_init({col: [] for col in self.columns}, index=[])
            return self.iloc[keep_rows, :]
        else:
            # axis == 1
            if subset is None:
                row_indices = list(range(self.shape[0]))
            else:
                # map row labels to positions
                if isinstance(subset, (list, tuple, set)):
                    row_indices = [self.index.index(r) for r in subset]
                else:
                    row_indices = [self.index.index(subset)]
            keep_cols = []
            for j in range(self.shape[1]):
                col_vals = [self.data[i + j * self.step] for i in row_indices]
                na_count = sum(1 for v in col_vals if v is nan)
                drop_col = (how == "any" and na_count > 0) or (
                    how == "all" and na_count == len(col_vals)
                )
                if not drop_col:
                    keep_cols.append(self.columns[j])
            return self.loc[:, keep_cols]

    def rename(self, columns=None, index=None, inplace=False):
        cp = self.copy()
        if columns is not None:
            if callable(columns):
                cp.columns = tuple(columns(c) for c in cp.columns)
            else:
                cp.columns = tuple(columns.get(c, c) for c in cp.columns)
        if index is not None:
            if callable(index):
                cp.index = tuple(index(i) for i in cp.index)
            else:
                cp.index = tuple(index.get(i, i) for i in cp.index)
        if inplace:
            self.data = cp.data
            self.columns = cp.columns
            self.index = cp.index
            self.shape = cp.shape
            self.view = cp.view
            self.step = cp.step
            return
        return cp

    def astype(self, dtype):
        """
        Cast DataFrame columns. Accepts a type or a dict of column->type.
        """
        cp = self.copy()
        if isinstance(dtype, dict):
            for col, dt in dtype.items():
                ser = cp.loc[:, col]
                ser2 = ser.astype(dt)
                cp.iloc[:, cp.columns.index(col)] = ser2.values
                if ser2._cat is not None:
                    cp._cats[col] = ser2._cat
                elif col in cp._cats:
                    del cp._cats[col]
        else:
            for j, col in enumerate(cp.columns):
                ser = cp.iloc[:, j]
                ser2 = ser.astype(dtype)
                cp.iloc[:, j] = ser2.values
                if ser2._cat is not None:
                    cp._cats[col] = ser2._cat
                elif col in cp._cats:
                    del cp._cats[col]
        return cp

    @property
    def dtypes(self):
        return Series([self[c].dtype for c in self.columns], index=list(self.columns))

    # ── kolonnevise verb ─────────────────────────────────────────────────
    # Alle disse er «samme Series-metode på hver kolonne»; _colwise holder
    # indeks og kolonnerekkefølge samlet ett sted.

    def _colwise(self, method, *args, **kwargs):
        out = {}
        for c in self.columns:
            out[c] = list(getattr(self[c], method)(*args, **kwargs).values)
        return DataFrame(out, index=list(self.index))

    def shift(self, periods=1, fill_value=None):
        return self._colwise('shift', periods, fill_value)

    def diff(self, periods=1):
        return self._colwise('diff', periods)

    def pct_change(self, periods=1):
        return self._colwise('pct_change', periods)

    def cumsum(self):
        return self._colwise('cumsum')

    def cumprod(self):
        return self._colwise('cumprod')

    def cummax(self):
        return self._colwise('cummax')

    def cummin(self):
        return self._colwise('cummin')

    def round(self, decimals=0):
        return self._colwise('round', decimals)

    def agg(self, func=None, *args, **kwargs):
        """
        agg('sum') → Series per kolonne. agg(['sum','mean']) → DataFrame med
        én rad per funksjon. agg({'kol': 'sum'}) → Series over de kolonnene.
        """
        if isinstance(func, dict):
            names, vals = [], []
            for col, f in func.items():
                names.append(col)
                vals.append(self[col]._agg_one(f))
            return Series(vals, index=names)
        if isinstance(func, (list, tuple)):
            rows = {}
            row_names = []
            for f in func:
                row_names.append(f if isinstance(f, str)
                                 else getattr(f, '__name__', str(f)))
            for c in self.columns:
                rows[c] = [self[c]._agg_one(f) for f in func]
            return DataFrame(rows, index=row_names)
        return Series([self[c]._agg_one(func, args, kwargs) for c in self.columns],
                      index=list(self.columns))

    aggregate = agg

    def transform(self, func, *args, **kwargs):
        return self._colwise('transform', func, *args, **kwargs)

    def isin(self, values):
        if isinstance(values, dict):
            out = {}
            for c in self.columns:
                allowed = values.get(c, [])
                out[c] = [v in allowed for v in self[c].values]
            return DataFrame(out, index=list(self.index))
        allowed = list(values.values) if isinstance(values, Series) else list(values)
        out = {}
        for c in self.columns:
            out[c] = [v in allowed for v in self[c].values]
        return DataFrame(out, index=list(self.index))

    def mode(self):
        cols = {}
        longest = 0
        for c in self.columns:
            vals = list(self[c].mode().values)
            cols[c] = vals
            longest = max(longest, len(vals))
        for c in self.columns:
            cols[c] = cols[c] + [nan] * (longest - len(cols[c]))
        return DataFrame(cols, index=list(range(longest)))

    def any(self, axis=0):
        if axis == 0:
            return Series([any(bool(v) for v in self[c].values) for c in self.columns],
                          index=list(self.columns))
        return Series([any(bool(v) for v in row) for row in self.values],
                      index=list(self.index))

    def all(self, axis=0):
        if axis == 0:
            return Series([all(bool(v) for v in self[c].values) for c in self.columns],
                          index=list(self.columns))
        return Series([all(bool(v) for v in row) for row in self.values],
                      index=list(self.index))

    def items(self):
        for c in self.columns:
            yield c, self[c]

    def itertuples(self, index=True, name='Pandas'):
        """Tupler per rad. Navngitte tupler finnes ikke i alle dialekter, så
        det returneres vanlige tupler — feltrekkefølgen er den samme."""
        for label, row in zip(self.index, self.values):
            yield tuple([label] + list(row)) if index else tuple(row)

    _NUMERIC_DTYPES = ('int64', 'float64', 'bool')

    def select_dtypes(self, include=None, exclude=None):
        def _match(dtype, spec):
            if spec is None:
                return None
            names = spec if isinstance(spec, (list, tuple)) else [spec]
            for want in names:
                want = str(want)
                if want in ('number', 'numeric'):
                    if dtype in ('int64', 'float64'):
                        return True
                elif want == dtype:
                    return True
            return False
        keep = []
        for c in self.columns:
            dtype = str(self[c].dtype)
            inc = _match(dtype, include)
            exc = _match(dtype, exclude)
            if (inc is None or inc) and not exc:
                keep.append(c)
        return self.loc[:, keep]

    def info(self):
        lines = ['<class \'pandas_shim.DataFrame\'>',
                 'RangeIndex: %d entries' % len(self.index),
                 'Data columns (total %d columns):' % len(self.columns)]
        for c in self.columns:
            ser = self[c]
            non_null = len([v for v in ser.values if not _is_na(v)])
            lines.append(' %-20s %d non-null  %s' % (str(c), non_null, ser.dtype))
        print('\n'.join(lines))

    def sort_index(self, axis=0, ascending=True):
        if axis in ["columns", "column", 1]:
            # sort columns
            new_cols = sorted(self.columns, reverse=not ascending)
            return self.loc[:, new_cols]
        else:
            new_index = sorted(self.index, reverse=not ascending)
            return self.loc[new_index, :]

    def count(self, axis=0, dropna=True):
        if axis in ["columns", "column", 1]:
            # count across rows per column -> Series indexed by columns
            counts = []
            for _, ser in self.itercols():
                if dropna:
                    counts.append(sum(1 for v in ser.values if v is not nan))
                else:
                    counts.append(len(ser))
            return Series(counts, list(self.columns), name=self.name)
        else:
            # count across columns per row -> Series indexed by index
            counts = []
            for _, ser in self.iterrows():
                if dropna:
                    counts.append(sum(1 for v in ser.values if v is not nan))
                else:
                    counts.append(len(ser))
            return Series(counts, list(self.index), name=self.name)

    def nunique(self, axis=0, dropna=True):
        if axis in ["columns", "column", 1]:
            vals = []
            for _, ser in self.itercols():
                data = ser.dropna().values if dropna else ser.values
                vals.append(len(set(data)))
            return Series(vals, list(self.columns), name=self.name)
        else:
            vals = []
            for _, ser in self.iterrows():
                data = ser.dropna().values if dropna else ser.values
                vals.append(len(set(data)))
            return Series(vals, list(self.index), name=self.name)

    def to_csv(self, path_or_buf=None, sep=",", index=True):
        rows = []
        header = ("" if not index else sep) + sep.join(str(c) for c in self.columns)
        rows.append(header)
        for i, row in enumerate(self.values):
            left = str(self.index[i]) + sep if index else ""
            rows.append(left + sep.join(str(v) for v in row))
        csv_str = "\n".join(rows)
        if path_or_buf is None:
            return csv_str
        try:
            # handle paths or file-like
            if hasattr(path_or_buf, "write"):
                path_or_buf.write(csv_str)
            else:
                with open(path_or_buf, "w", encoding="utf-8") as f:
                    f.write(csv_str)
        except Exception:
            # fallback: return string
            return csv_str

    def set_index(self, keys, drop=True):
        cp = self.copy()
        if isinstance(keys, (list, tuple)):
            # only support single key for simplicity
            if len(keys) != 1:
                raise NotImplementedError("set_index supports a single key")
            keys = keys[0]
        ser = cp.loc[:, keys]
        cp.index = tuple(ser.values)
        if drop:
            cp._drop_inplace(keys, 1)
        return cp

    def assign(self, **kwargs):
        cp = self.copy()
        for k, v in kwargs.items():
            if callable(v):
                values = v(cp)
            else:
                values = v
            cp.loc[:, k] = values
        return cp

    def sample(self, n=None, frac=None, replace=False, random_state=None):
        if random_state is not None:
            random.seed(random_state)
        if frac is not None:
            n = int(round(frac * self.shape[0]))
        if n is None:
            n = 1
        n = max(0, min(n, self.shape[0])) if not replace else n
        if replace:
            indices = [random.randrange(0, self.shape[0]) for _ in range(n)]
        else:
            indices = random.sample(range(self.shape[0]), n)
        return self.iloc[indices, :]

    def nlargest(self, n, columns):
        return self.sort_values(by=columns, ascending=False).head(n)

    def nsmallest(self, n, columns):
        return self.sort_values(by=columns, ascending=True).head(n)
    def to_dict(self, orient=None, index=False):
      dikt={}
      if index:
        dikt['index']=self.index
      columns=list(self.columns)
      data_dikt = {columns[n]: data for n, data in enumerate(zip(*self.values))}
      dikt.update(data_dikt)
      return dikt
    
    def to_html(self, index=True):
        # Build a simple HTML table; honor index flag
        try:
            header_cells = ([] if not index else ["<th></th>"]) + [f"<th>{html.escape(str(c))}</th>" for c in self.columns]
            thead = "<tr>" + "".join(header_cells) + "</tr>"
            body_rows = []
            for i, row in enumerate(self.values):
                cells = []
                if index:
                    cells.append(f"<th>{html.escape(str(self.index[i]))}</th>")
                for val in row:
                    cells.append(f"<td>{html.escape(_fmt_cell(val))}</td>")
                body_rows.append("<tr>" + "".join(cells) + "</tr>")
            return "<table><thead>" + thead + "</thead><tbody>" + "".join(body_rows) + "</tbody></table>"
        except Exception:
            return self._repr_html_() or ""

    def to_json(self, orient="records", index=True):
        if orient == "records":
            # list of row dicts
            records = []
            for i, row in enumerate(self.values):
                rec = {str(col): row[j] for j, col in enumerate(self.columns)}
                if index:
                    rec["index"] = self.index[i]
                records.append(rec)
            return json.dumps(records)
        elif orient == "columns":
            data = {str(col): [row[j] for row in self.values] for j, col in enumerate(self.columns)}
            if index:
                data["index"] = list(self.index)
            return json.dumps(data)
        elif orient == "index":
            data = {}
            for i, row in enumerate(self.values):
                data[str(self.index[i])] = {str(col): row[j] for j, col in enumerate(self.columns)}
            return json.dumps(data)
        else:
            # default to records
            return self.to_json(orient="records", index=index)

    def duplicated(self, subset=None, keep="first"):
        if subset is None:
            col_idx = list(range(self.shape[1]))
        else:
            if isinstance(subset, (list, tuple)):
                col_idx = [self.columns.index(c) for c in subset]
            else:
                col_idx = [self.columns.index(subset)]
        keys = []
        dup_mask = []
        seen = {}
        for i, row in enumerate(self.values):
            key = tuple("NaN" if row[j] is nan else row[j] for j in col_idx)
            if key in seen:
                dup_mask.append(True)
                seen[key].append(i)
            else:
                dup_mask.append(False)
                seen[key] = [i]
        if keep == False:
            # mark all duplicates True except uniques
            dup_mask = [len(seen[tuple("NaN" if r[j] is nan else r[j] for j in col_idx)]) > 1 for r in self.values]
        elif keep == "last":
            # only keep last occurrence as not duplicate
            dup_mask = [False] * self.shape[0]
            for inds in seen.values():
                if len(inds) > 1:
                    for idx in inds[:-1]:
                        dup_mask[idx] = True
        # else default: keep first (already marked)
        return Series(dup_mask, list(self.index), name=self.name)

    def drop_duplicates(self, subset=None, keep="first"):
        mask = ~self.duplicated(subset=subset, keep=keep).values
        keep_rows = [_ci for _ci, ok in enumerate(mask) if ok]
        return self.iloc[keep_rows, :]
    
    def describe(self):
        numeric_cols = []
        for label, ser in self.itercols():
            try:
                # consider numeric if all non-nan values are int/float
                vals = [v for v in ser.values if v is not nan]
                if all(isinstance(v, (int, float)) for v in vals):
                    numeric_cols.append(label)
            except Exception:
                continue
        stats = [
            ("count", lambda s: len([v for v in s.values if v is not nan])),
            ("mean", lambda s: s.mean()),
            ("std", lambda s: s.std()),
            ("min", lambda s: s.min()),
            ("25%", lambda s: s.quantile(0.25)),
            ("50%", lambda s: s.quantile(0.5)),
            ("75%", lambda s: s.quantile(0.75)),
            ("max", lambda s: s.max()),
        ]
        rows = []
        for stat_name, func in stats:
            row = []
            for col in numeric_cols:
                row.append(func(self.loc[:, col]))
            rows.append(row)
        return self.class_init(rows, index=[s[0] for s in stats], columns=numeric_cols)

    def clip(self, lower=None, upper=None):
        cp = self.copy()
        for j, _ in enumerate(cp.columns):
            cp.iloc[:, j] = cp.iloc[:, j].clip(lower=lower, upper=upper).values
        return cp

    def replace(self, to_replace, value=None):
        cp = self.copy()
        for j, col in enumerate(cp.columns):
            cp.iloc[:, j] = cp.iloc[:, j].replace(to_replace, value).values
        return cp

    def where(self, cond, other=nan):
        if isinstance(cond, DataFrame):
            mask_df = cond
        else:
            mask_df = self.class_init(cond, columns=self.columns, index=self.index)
        cp = self.copy()
        for j in range(cp.shape[1]):
            cp.iloc[:, j] = cp.iloc[:, j].where(mask_df.iloc[:, j].values, other).values
        return cp

    def mask(self, cond, other=nan):
        if isinstance(cond, DataFrame):
            mask_df = cond
        else:
            mask_df = self.class_init(cond, columns=self.columns, index=self.index)
        cp = self.copy()
        for j in range(cp.shape[1]):
            cp.iloc[:, j] = cp.iloc[:, j].mask(mask_df.iloc[:, j].values, other).values
        return cp

    def merge(self, right, how='inner', on=None, left_on=None, right_on=None,
              suffixes=('_x', '_y')):
        # Delegerer til modulfunksjonen merge() via alias — se Brython-fellen
        # nederst i filen (metodenavn == globalt navn er en stille no-op i
        # Brython 3.12).
        return _merge_fn(self, right, how=how, on=on, left_on=left_on,
                     right_on=right_on, suffixes=suffixes)

    def join(self, other, how='left', lsuffix='', rsuffix=''):
        """
        Indeks-basert join (pandas-semantikk: kobler på radetiketter).
        Støtter how='left' og 'inner'; kolonneoverlapp krever lsuffix/rsuffix.
        """
        if how not in ('left', 'inner'):
            raise NotImplementedError("join: bare how='left'/'inner' — bruk merge() for resten")
        overlap = set(self.columns) & set(other.columns)
        if overlap and not (lsuffix or rsuffix):
            raise ValueError('join: overlappende kolonner %r krever lsuffix/rsuffix'
                             % sorted(str(c) for c in overlap))
        rmap = {}
        for j, lbl in enumerate(other.index):
            if lbl not in rmap:        # ikke setdefault — Brython-felle:
                rmap[lbl] = []          # setdefault stringifiserer ikke-streng-nøkler
            rmap[lbl].append(j)
        lrows, rrows = self.values, other.values
        pairs = []                                   # (venstre rad, høyre rad|None, etikett)
        for i, lbl in enumerate(self.index):
            js = rmap.get(lbl)
            if js:
                for j in js:
                    pairs.append((i, j, lbl))
            elif how == 'left':
                pairs.append((i, None, lbl))
        out = {}
        for ci, c in enumerate(self.columns):
            name = (str(c) + lsuffix) if c in overlap else c
            out[name] = [lrows[i][ci] for i, _j, _l in pairs]
        for cj, c in enumerate(other.columns):
            name = (str(c) + rsuffix) if c in overlap else c
            out[name] = [rrows[j][cj] if j is not None else nan for _i, j, _l in pairs]
        return DataFrame(out, index=[lbl for _i, _j, lbl in pairs])

    def pivot_table(self, values=None, index=None, columns=None, aggfunc='mean',
                    fill_value=None):
        return _pivot_table_fn(self, values=values, index=index, columns=columns,
                           aggfunc=aggfunc, fill_value=fill_value)

    def melt(self, id_vars=None, value_vars=None, var_name='variable', value_name='value'):
        return _melt_fn(self, id_vars=id_vars, value_vars=value_vars,
                    var_name=var_name, value_name=value_name)

    def corr(self, method='pearson'):
        """
        Parvis korrelasjon mellom numeriske kolonner (parvis dropna).
        """
        numeric = []
        for label, ser in self.itercols():
            vals = ser.dropna().values
            if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
                numeric.append((label, ser))
        rows = []
        for _la, sa in numeric:
            row = []
            for _lb, sb in numeric:
                row.append(sa.corr(sb, method=method))
            rows.append(row)
        cols = [la for la, _s in numeric]
        return DataFrame({c: [rows[i][j] for i in range(len(cols))]
                          for j, c in enumerate(cols)}, index=cols)


class Plot:
    def __init__(self, data):
        self.data = data
    def _apply_common_kwargs(self, kwargs):
        figsize = kwargs.pop('figsize', None)
        if isinstance(figsize, (list, tuple)) and len(figsize) == 2:
            kwargs.setdefault('width', figsize[0]*96 if isinstance(figsize[0], (int, float)) else figsize[0])
            kwargs.setdefault('height', figsize[1]*96 if isinstance(figsize[1], (int, float)) else figsize[1])
        xlim = kwargs.pop('xlim', None)
        ylim = kwargs.pop('ylim', None)
        if xlim is not None:
            kwargs.setdefault('xaxis_range', list(xlim))
        if ylim is not None:
            kwargs.setdefault('yaxis_range', list(ylim))
        xlabel = kwargs.pop('xlabel', None)
        ylabel = kwargs.pop('ylabel', None)
        if xlabel is not None:
            kwargs.setdefault('xaxis_title', xlabel)
        if ylabel is not None:
            kwargs.setdefault('yaxis_title', ylabel)
        stacked = kwargs.pop('stacked', None)
        if stacked is not None:
            kwargs.setdefault('barmode', 'stack' if stacked else 'group')
        kwargs.pop('kind', None)
        return kwargs
    def area(self,x=None, y=None, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data= self.data.to_dict()
        if x is None:
          x="index"
          data["index"]=self.data.index
        if y is None:
          y="values"
          data["values"]=self.data.values
        return _px().area(data=data, x=x, y=y, **kwargs)
    def bar(self,x=None, y=None, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        #print("bardata1", self.data.index)
        data= self.data.to_dict()
        #print("bardata2", data, self.data.index)
        #print("data", data)
 
        if y is None:
          y="values"  #well, if many y eg. multiple lines ...
          #data2["values"]=data2["values"]
        if x is None:
          if self.data.index is None:
            #print("values", data["values"])
            data["index"]=list(range(len(data["values"]))) # well, if many y values ... check ...
          else:
            data["index"]=self.data.index
          x="index"

        return _px().bar(data=data, x=x, y=y, **kwargs)

    def box(self,x=None, y=None, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data= self.data.to_dict()
        if x is None:
          x="index"
          data["index"]=self.data.index
        if y is None:
          y="values"
          data["values"]=self.data.values
        return _px().box(data=data, x=x, y=y, **kwargs)
        
    def choropleth(self, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data= self.data.to_dict()
        return _px().choropleth(data=data, **kwargs)
    def map(self, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data= self.data.to_dict()
        return _px().choropleth(data=data, **kwargs)

    def histogram(self,x=None, y=None, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data = self.data.to_dict()
        # Prefer plotting the underlying values for a Series by default
        if x is None and y is None:
          if "values" in data:
            x = "values"
          else:
            # Fallback: use index if no explicit values key
            x = "index"
            data["index"] = self.data.index
        elif x is None:
          x = "index"
          data["index"] = self.data.index
        return _px().histogram(data=data, x=x, y=y, **kwargs)


    def line(self,x=None, y=None, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data= self.data.to_dict()
        #print("data", data)
        if x is None:
          x="index"
          data["index"]=self.data.index
        if y is None:
          if len(data)==1:
            y="values"
            data["values"]=self.data.values
          else:
            y=data.keys()
            y=[k for k in y if k!=x]
            #print("y", y)
        return _px().line(data=data, x=x, y=y, **kwargs)
    def scatter(self, x=None, y=None, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data= self.data.to_dict()
        if x is None:
          x="index"
          data["index"]=self.data.index
        if y is None:
          y="values"
          data["values"]=self.data.values
        return _px().scatter(data=data, x=x, y=y, **kwargs)
    def violin(self, x=None, y=None, **kwargs):
        kwargs = self._apply_common_kwargs(kwargs)
        data= self.data.to_dict()
        if x is None:
          x="index"
          data["index"]=self.data.index
        if y is None:
          y="values"
          data["values"]=self.data.values
        return _px().violin(data=data, x=x, y=y, **kwargs)
    def __call__(self, x=None, y=None, **kwargs):
        # pandas-like kind routing
        kind = kwargs.get('kind')
        if kind is not None:
            kind = str(kind).lower()
            kwargs.pop('kind')
            if kind == 'barh':
                kwargs['orientation'] = 'h'
                return self.bar(x=x, y=y, **kwargs)
            if kind in ('bar','line','area','box','hist','histogram','scatter'):
                return getattr(self, 'histogram' if kind=='hist' else kind)(x=x, y=y, **kwargs)
            if kind == 'pie':
                data_dict = self.data.to_dict()
                if 'values' not in data_dict:
                    data_dict['values'] = self.data.values
                data_dict['names'] = list(range(len(data_dict['values']))) if self.data.index is None else self.data.index
                kwargs = self._apply_common_kwargs(kwargs)
                return _px().pie(data_dict, values='values', names='names', **kwargs)
        kwargs = self._apply_common_kwargs(kwargs)
        data = self.data.to_dict()
        if x is None:
          x = "index"
          data["index"] = self.data.index
        if y is None:
          # If this is a Series-like dict, prefer the single 'values' column
          if "values" in data:
            y = "values"
          else:
            # Otherwise, plot all columns except the x-axis
            keys = list(data.keys())
            y = [k for k in keys if k != x]
        return _px().line(data=data, x=x, y=y, **kwargs)

    # aliases
    def hist(self, x=None, y=None, **kwargs):
        return self.histogram(x=x, y=y, **kwargs)
    def barh(self, x=None, y=None, **kwargs):
        kwargs['orientation'] = 'h'
        return self.bar(x=x, y=y, **kwargs)
    def pie(self, **kwargs):
        data_dict = self.data.to_dict()
        if 'values' not in data_dict:
            data_dict['values'] = self.data.values
        data_dict['names'] = list(range(len(data_dict['values']))) if self.data.index is None else self.data.index
        kwargs = self._apply_common_kwargs(kwargs)
        return _px().pie(data_dict, values='values', names='names', **kwargs)






class GroupBy:
    """
    GroupBy class for DataFrame
    """

    def __init__(self):
        """
        Collection of DataFrames
        """
        self.dfs = []
        self.parent = None
        self.by = None
        self.select = None  # kolonnevalg fra gb['kol'] / gb[['a','b']]

    def __getitem__(self, key):
        """
        gb['kol'] / gb[['a','b']]: aggregér bare utvalgte kolonner
        (pandas-mønsteret df.groupby('g')['v'].mean()).
        """
        gb = GroupBy()
        gb.parent = self.parent
        gb.by = self.by
        gb.dfs = self.dfs
        gb.select = key
        return gb

    def apply(self, func, axis=0, dropna=True):
        """
        Applies a method
        """
        res_ser = []
        for df in self.dfs:
            res_ser.append(df.apply(func, axis=axis, dropna=dropna))
        return DataFrame(res_ser)

    def __sum__(self):
        pass

    def __getattr__(self, item):
        """
        Returns a method containing a for loop of partialized
        methods, awaiting *args and **kwargs
        """
        return functools.partial(self.loop_func, method_name=item)

    def loop_func(self, method_name, *args, **kwargs):
        """
        The function to be executed with args and kwargs
        """
        res_ser = []
        res_idx = []
        for df in self.dfs:
            target = df if self.select is None else df[self.select]
            if isinstance(target, DataFrame):
                target.name = df.name
            out = getattr(target, method_name)(*args, **kwargs)
            res_ser.append(out)
            res_idx.append(df.name)
        # If outputs are Series, stack into DataFrame; else return Series of scalars per group
        if len(res_ser) > 0 and isinstance(res_ser[0], Series):
            return DataFrame(res_ser, index=res_idx)
        name = self.select if isinstance(self.select, str) else None
        return Series(res_ser, res_idx, name=name)

    def agg(self, func=None):
        """
        gb.agg('mean') | gb.agg({'v':'sum','w':'mean'}) | gb['v'].agg(['mean','sum']).
        Dict/liste gir flat kolonneindeks (kol_funk ved flere funksjoner per
        kolonne) — ingen MultiIndex, bevisst.
        """
        if isinstance(func, str):
            return self.loop_func(func)
        group_names = [df.name for df in self.dfs]
        if isinstance(func, dict):
            cols = {}
            for col, f in func.items():
                fs = f if isinstance(f, (list, tuple)) else [f]
                for fname in fs:
                    key = col if not isinstance(f, (list, tuple)) else col + '_' + fname
                    cols[key] = [getattr(df[col], fname)() for df in self.dfs]
            return DataFrame(cols, index=group_names)
        if isinstance(func, (list, tuple)):
            if not isinstance(self.select, str):
                raise NotImplementedError(
                    "agg(liste) støttes bare etter kolonnevalg, f.eks. gb['v'].agg(['mean','sum'])")
            cols = {fname: [getattr(df[self.select], fname)() for df in self.dfs]
                    for fname in func}
            return DataFrame(cols, index=group_names)
        if callable(func):
            vals = []
            for df in self.dfs:
                target = df if self.select is None else df[self.select]
                vals.append(func(target))
            name = self.select if isinstance(self.select, str) else None
            return Series(vals, group_names, name=name)
        raise TypeError('agg: støtter str, dict, liste eller callable')

    aggregate = agg

    def size(self):
        counts = []
        names = []
        for df in self.dfs:
            counts.append(len(df))
            names.append(df.name)
        return Series(counts, names, name=self.by)

import io


def _parse_csv_text(text, sep=','):
    """Minimal RFC-4180-parser (MicroPython har ingen csv-modul): håndterer
    sitering, doblede anførselstegn og CRLF. Erstatter csv.reader."""
    rows, row, field, in_q = [], [], [], False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if in_q:
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                in_q = False
            else:
                field.append(c)
        elif c == '"':
            in_q = True
        elif c == sep:
            row.append(''.join(field))
            field = []
        elif c == '\n':
            row.append(''.join(field))
            field = []
            rows.append(row)
            row = []
        elif c != '\r':
            field.append(c)
        i += 1
    if field or row:
        row.append(''.join(field))
        rows.append(row)
    return rows


def read_csv(filepath, sep=",", header=0, names=None, index_col=None):
    """
    Reads CSV data into a dataframe from a file path or StringIO object.
    """
    # MicroPython-felle: ingen csv-modul i MicroPython. read_csv leser hele
    # teksten og parser den med _parse_csv_text() (over) i stedet for
    # csv.reader. Brython-originalens QUOTE_STRINGS/QUOTE_NOTNULL-lapping av
    # _csv (arbeidsrundt for et Brython-stdlib-hull) er droppet — irrelevant
    # utenfor Brython.
    index = []
    columns = []
    data = []
    
    # If 'names' is provided, don't treat any row as the header
    if names is not None:
        header = None
        columns = names

    # Check if 'filepath' is a StringIO or file-like object (already opened in-memory)
    try:
        if window is not None and filepath in window.__pyapp_assets:
          #print("inside")
          file64=window.__pyapp_assets[filepath]
          decoded_bytes = base64.b64decode(file64)
          blob = io.StringIO(decoded_bytes.decode('utf-8'))
          filepath=blob
    except (ImportError, AttributeError):
        pass

    if isinstance(filepath, io.StringIO):
        #print("stringio")
        csvfile = filepath
    else:
        #print("else")
        # Handle 'filepath' as a file path string
        try:
            filepath = filepath.__fspath__()  # In case it's an os.PathLike object
        except AttributeError:
            pass
        csvfile = open(filepath, mode='r')  # Open the file if it's a path

    # Use the opened file or StringIO object with the RFC-4180 parser
    try:
        text = csvfile.read() if hasattr(csvfile, 'read') else csvfile
        for i, row in enumerate(_parse_csv_text(text, sep)):
            if isinstance(header, int) and header == i:
                if isinstance(index_col, int):
                    columns = row[:index_col] + row[index_col + 1 :]
                else:
                    columns = row
                continue

            if isinstance(index_col, int):
                index.append(row[index_col])
                data.append(row[:index_col] + row[index_col + 1 :])
            else:
                data.append(row)
    finally:
        # Close the file if it was opened from a path
        if not isinstance(filepath, io.StringIO):
            csvfile.close()

    # Type inference per column (like real pandas): try int, then float,
    # else keep str. Empty strings become the module's `nan` sentinel in
    # numeric columns — isna()/dropna() check `item is nan`, so None would
    # be invisible to them. Without this every CSV column is a string and
    # comparisons/means fail — the whole point of loading data.
    if data and data[0]:
        ncols = len(data[0])
        for c in range(ncols):
            raw = [row[c] for row in data if len(row) > ncols - 1]
            nonempty = [v for v in raw if v != '']
            if not nonempty:
                continue
            converted = None
            for conv in (int, float):
                try:
                    converted = [nan if v == '' else conv(v) for v in raw]
                    break
                except (ValueError, TypeError):
                    converted = None
            if converted is not None:
                k = 0
                for row in data:
                    if len(row) > ncols - 1:
                        row[c] = converted[k]
                        k += 1

    # Return the dataframe-like structure
    return DataFrame(data, columns=columns, index=index)

# ── Reshaping/kobling (fase 2-utvidelse 2026-07-10) ───────────────────────
# Radorienterte implementasjoner oppå .values/.columns — bevisst utenom
# view-mekanikken. Flat indeks (tupler ved flere nøkler), ingen MultiIndex.

def _sorted_unique(values):
    """Unike verdier, sortert som pandas; usammenliknbare typer faller
    tilbake til opptredensrekkefølge."""
    uniq = list(dict.fromkeys(values))
    try:
        return sorted(uniq)
    except TypeError:
        return uniq


def merge(left, right, how='inner', on=None, left_on=None, right_on=None,
          suffixes=('_x', '_y')):
    """
    Hash-join på nøkkelkolonner. how: inner/left/right/outer.
    nan-nøkler matcher aldri (nan == nan er False).
    """
    def _aslist(x):
        return list(x) if isinstance(x, (list, tuple)) else [x]

    lcols, rcols = list(left.columns), list(right.columns)
    if on is not None:
        lkeys = rkeys = _aslist(on)
    elif left_on is not None or right_on is not None:
        lkeys, rkeys = _aslist(left_on), _aslist(right_on)
        if len(lkeys) != len(rkeys):
            raise ValueError('merge: left_on og right_on må ha samme lengde')
    else:
        lkeys = rkeys = [c for c in lcols if c in rcols]
        if not lkeys:
            raise ValueError('merge: ingen felles kolonner å koble på')
    shared_keys = (lkeys == rkeys)

    lrows, rrows = left.values, right.values
    lpos = {c: i for i, c in enumerate(lcols)}
    rpos = {c: i for i, c in enumerate(rcols)}

    def keytup(row, pos, keys):
        return tuple(row[pos[k]] for k in keys)

    pairs = []                                   # (venstre rad|None, høyre rad|None)
    if how == 'right':
        # Følger høyre-radenes rekkefølge (pandas-semantikk).
        lmap = {}
        for i, row in enumerate(lrows):
            key = keytup(row, lpos, lkeys)
            if key not in lmap:        # ikke setdefault — Brython-felle:
                lmap[key] = []          # setdefault stringifiserer ikke-streng-nøkler
            lmap[key].append(i)
        for j, row in enumerate(rrows):
            matches = lmap.get(keytup(row, rpos, rkeys))
            if matches:
                for i in matches:
                    pairs.append((i, j))
            else:
                pairs.append((None, j))
    else:
        rmap = {}
        for j, row in enumerate(rrows):
            key = keytup(row, rpos, rkeys)
            if key not in rmap:
                rmap[key] = []
            rmap[key].append(j)
        matched_r = set()
        for i, row in enumerate(lrows):
            matches = rmap.get(keytup(row, lpos, lkeys))
            if matches:
                for j in matches:
                    pairs.append((i, j))
                    matched_r.add(j)
            elif how in ('left', 'outer'):
                pairs.append((i, None))
        if how == 'outer':
            pairs.extend((None, j) for j in range(len(rrows)) if j not in matched_r)
            # pandas sorterer nøklene leksikografisk ved how='outer'
            # (men bevarer rekkefølgen ved inner/left/right).
            def _pairkey(p):
                i, j = p
                if i is not None:
                    return keytup(lrows[i], lpos, lkeys)
                return keytup(rrows[j], rpos, rkeys)
            try:
                pairs.sort(key=_pairkey)
            except TypeError:
                pass

    r_out_cols = [c for c in rcols if not (shared_keys and c in rkeys)]
    overlap = set(lcols) & set(r_out_cols)

    out = {}
    for c in lcols:
        ci = lpos[c]
        col = []
        for i, j in pairs:
            if i is not None:
                col.append(lrows[i][ci])
            elif shared_keys and c in lkeys:
                # uparret høyre-rad: nøkkelverdien hentes fra høyresiden
                col.append(rrows[j][rpos[rkeys[lkeys.index(c)]]])
            else:
                col.append(nan)
        out[(str(c) + suffixes[0]) if c in overlap else c] = col
    for c in r_out_cols:
        cj = rpos[c]
        out[(str(c) + suffixes[1]) if c in overlap else c] = [
            rrows[j][cj] if j is not None else nan for _i, j in pairs]
    return DataFrame(out)


def pivot_table(data, values=None, index=None, columns=None, aggfunc='mean',
                fill_value=None):
    """
    Flat pivot: index/columns/values er kolonnenavn. aggfunc er navnet på en
    Series-metode ('mean', 'sum', …), 'count', eller en callable(Series).
    Kombinasjoner uten data blir nan (eller fill_value).
    """
    if index is None or values is None:
        raise NotImplementedError('pivot_table: index= og values= kreves')

    def _agg(ser):
        if callable(aggfunc):
            return aggfunc(ser)
        if aggfunc == 'count':
            return len(ser.dropna())
        return getattr(ser, aggfunc)()

    if columns is None:
        gb = data.groupby(index)
        vals = [_agg(df[values]) for df in gb.dfs]
        names = [df.name for df in gb.dfs]
        return DataFrame({values: vals}, index=names)

    ivals = list(data[index].values)
    cvals = list(data[columns].values)
    vvals = list(data[values].values)
    row_keys = _sorted_unique(ivals)
    col_keys = _sorted_unique(cvals)
    buckets = {}
    for rk, ck, v in zip(ivals, cvals, vvals):
        key = (rk, ck)
        if key not in buckets:      # ikke setdefault — Brython-felle:
            buckets[key] = []        # setdefault stringifiserer ikke-streng-nøkler
        buckets[key].append(v)
    out = {}
    for ck in col_keys:
        col = []
        for rk in row_keys:
            vs = buckets.get((rk, ck))
            if vs is None:
                col.append(nan if fill_value is None else fill_value)
            else:
                col.append(_agg(Series(vs)))
        out[ck] = col
    return DataFrame(out, index=row_keys)


def crosstab(index, columns):
    """
    Frekvenskrysstabell av to serier/lister. Tomme kombinasjoner blir 0.
    """
    ivals = list(index.values) if isinstance(index, Series) else list(index)
    cvals = list(columns.values) if isinstance(columns, Series) else list(columns)
    counts = _Counter(zip(ivals, cvals))
    row_keys = _sorted_unique(ivals)
    col_keys = _sorted_unique(cvals)
    out = {ck: [counts.get((rk, ck), 0) for rk in row_keys] for ck in col_keys}
    return DataFrame(out, index=row_keys)


def melt(frame, id_vars=None, value_vars=None, var_name='variable', value_name='value'):
    """
    Bred → lang: value_vars stables til (variable, value)-kolonner,
    id_vars gjentas. Samme radrekkefølge som pandas (variabel for variabel).
    """
    def _aslist(x):
        if x is None:
            return None
        return list(x) if isinstance(x, (list, tuple)) else [x]

    id_vars = _aslist(id_vars) or []
    value_vars = _aslist(value_vars) or [c for c in frame.columns if c not in id_vars]
    pos = {c: i for i, c in enumerate(frame.columns)}
    rows = frame.values
    out = {c: [] for c in id_vars}
    out[var_name] = []
    out[value_name] = []
    for vv in value_vars:
        for row in rows:
            for c in id_vars:
                out[c].append(row[pos[c]])
            out[var_name].append(vv)
            out[value_name].append(row[pos[vv]])
    return DataFrame(out)


def to_datetime(arg, format=None, errors='raise'):
    """
    Streng(er) → datetime. Prøver format= først, ellers vanlige formater
    (ISO først, deretter måned-først som pandas). errors='coerce' gir nan.
    """
    common = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d',
              '%m/%d/%Y', '%d.%m.%Y', '%Y%m%d']

    def parse(v):
        if v is nan or v is None or v == '':
            return nan
        if datetime is None:
            # MicroPython-felle: datetime-modulen mangler helt i
            # unix-micropython-bygget (fase 0-funn). to_datetime() er derfor
            # ikke-funksjonell der; feiler høylytt i stedet for et kryptisk
            # isinstance()-TypeError. Fungerer under wasm-bygget siden
            # datetime-klassen finnes der (se filhode).
            raise NotImplementedError(
                'to_datetime: datetime-modulen mangler i denne MicroPython-bygningen')
        if isinstance(v, datetime):
            return v
        s = str(v)
        for f in ([format] if format else common):
            try:
                return _parse_dt(s, f)
            except (ValueError, TypeError):
                pass
        if errors == 'coerce':
            return nan
        raise ValueError('to_datetime: kunne ikke tolke %r' % (v,))

    if isinstance(arg, Series):
        return arg.apply(parse)
    if isinstance(arg, (list, tuple)):
        return Series([parse(v) for v in arg])
    return parse(arg)


def date_range(start=None, end=None, periods=None, freq='D'):
    """
    Datoserie mellom start/end eller start + periods steg.

    Regner i sekunder på proleptiske dagnummer i stedet for timedelta —
    timedelta kan ikke forutsettes i MicroPython-bygget.
    """
    step = _freq_seconds(freq)

    def _secs(v):
        d = to_datetime(v) if isinstance(v, str) else v
        return (_to_ordinal(d.year, d.month, d.day) * 86400
                + d.hour * 3600 + d.minute * 60 + d.second)

    def _dt(total):
        days, rem = total // 86400, total % 86400
        y, m, d = _from_ordinal(days)
        return datetime(y, m, d, rem // 3600, (rem % 3600) // 60, rem % 60)

    if start is None:
        if end is None or periods is None:
            raise ValueError('date_range: oppgi start, eller end sammen med periods')
        last = _secs(end)
        return Series([_dt(last - step * i) for i in range(periods - 1, -1, -1)])
    first = _secs(start)
    if periods is not None:
        return Series([_dt(first + step * i) for i in range(periods)])
    if end is None:
        raise ValueError('date_range: oppgi enten end eller periods')
    stop = _secs(end)
    out = []
    cur = first
    while cur <= stop:
        out.append(_dt(cur))
        cur += step
    return Series(out)


def get_dummies(data, prefix=None, prefix_sep='_'):
    """
    Kategorisk serie/liste → 0/1-kolonner (én per unik verdi, sortert).
    """
    vals = list(data.values) if isinstance(data, Series) else list(data)
    keys = _sorted_unique([v for v in vals if v is not nan])
    out = {}
    for k in keys:
        name = k if prefix is None else '%s%s%s' % (prefix, prefix_sep, k)
        out[name] = [1 if v == k else 0 for v in vals]
    return DataFrame(out)


def _fmt_edge(v):
    return '%g' % v if isinstance(v, (int, float)) else str(v)


def cut(x, bins, labels=None, right=True, include_lowest=False):
    """
    Verdier → intervaller. bins: liste av kanter eller antall (int).
    labels=None gir '(a, b]'-strenger. Resultatet er ORDNET kategorisk
    (Series._cat), så sort_values/groupby/value_counts følger bin-rekkefølgen
    og ikke alfabetet — før 2026-07-26 ga cut(bins=[0,2,10,20]).sort_values()
    rekkefølgen (0, 2] , (10, 20] , (2, 10].
    Verdier utenfor kantene blir nan, som i pandas.
    """
    vals = list(x.values) if isinstance(x, Series) else list(x)
    nums = [v for v in vals if v is not nan]
    if isinstance(bins, int):
        lo, hi = min(nums), max(nums)
        span = (hi - lo) or 1
        edges = [lo + span * i / bins for i in range(bins + 1)]
        edges[0] = lo - span * 0.001     # pandas utvider nederste kant 0,1 %
    else:
        edges = list(bins)
    if include_lowest:
        edges = [edges[0] - 1e-9] + edges[1:]

    def label(i):
        if labels is not None and labels is not False:
            return labels[i]
        if right:
            return '(%s, %s]' % (_fmt_edge(edges[i]), _fmt_edge(edges[i + 1]))
        return '[%s, %s)' % (_fmt_edge(edges[i]), _fmt_edge(edges[i + 1]))

    def place(v):
        if v is nan:
            return nan
        for i in range(len(edges) - 1):
            if right:
                if edges[i] < v <= edges[i + 1]:
                    return label(i)
            else:
                if edges[i] <= v < edges[i + 1]:
                    return label(i)
        return nan

    out = [place(v) for v in vals]
    cat = CategoricalDtype([label(i) for i in range(len(edges) - 1)], True)
    if isinstance(x, Series):
        cp = x.copy()
        cp.data = out
        cp._cat = cat
        return cp
    res = Series(out)
    res._cat = cat
    return res


def qcut(x, q, labels=None):
    """
    Kvantilbasert cut: q er antall like store grupper eller en liste av
    kvantiler (0–1). Laveste verdi inkluderes (som i pandas).
    """
    vals = list(x.values) if isinstance(x, Series) else list(x)
    ser = Series([v for v in vals if v is not nan])
    qs = [i / q for i in range(q + 1)] if isinstance(q, int) else list(q)
    edges = [ser.quantile(p) for p in qs]
    edges[0] = edges[0] - abs(edges[0]) * 1e-9 - 1e-9
    return cut(x, edges, labels=labels)


def isna(obj):
    if isinstance(obj, Series):
        return obj.isna()
    if isinstance(obj, DataFrame):
        return obj.isna()
    return obj is nan or (isinstance(obj, float) and obj != obj)


def notna(obj):
    res = isna(obj)
    if isinstance(res, (Series, DataFrame)):
        return ~res
    return not res


def unique(values):
    if isinstance(values, Series):
        return values.unique()
    return list(dict.fromkeys(values))


# ── Brython-mode gaps ─────────────────────────────────────────────────────
# These pandas verbs are intentionally not implemented in the lightweight
# engine. They raise a clear error naming the escape hatch instead of an
# AttributeError, per the design spec (2026-07-10-brython-engine-design.md).
def _brython_gap(name):
    def _raise(self=None, *args, **kwargs):
        raise NotImplementedError(
            name + " er ikke tilgjengelig i Brython-modus — bytt til Python-modus (Pyodide) for full pandas.")
    try:
        _raise.__name__ = name
    except AttributeError:
        # MicroPython-felle: funksjonsobjekter tillater ikke tilordning av
        # __name__ (read-only i dette bygget). Rent kosmetisk under
        # CPython/Brython (bedre tracebacks) — trygt å hoppe over.
        pass
    return _raise

# (2026-07-10: merge, join, pivot_table, melt og corr er nå implementert —
# fjernet fra listen. MultiIndex-avhengige verb forblir bevisst gap.)
for _name in ['pivot', 'rolling', 'resample']:
    if not hasattr(DataFrame, _name):
        setattr(DataFrame, _name, _brython_gap(_name))


# Brython-felle (se matplotlib_brython.py nederst): metoder kan ikke referere
# globale funksjoner med samme navn som metoden — kall via alias.
_merge_fn, _pivot_table_fn, _melt_fn = merge, pivot_table, melt

