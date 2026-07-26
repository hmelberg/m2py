# Kjøres under unix-micropython: micropython micropython/tests/mpy_smoke_pandas.py
# Dialekt-røyk for pandas_mpy — feiler høylytt med traceback ved dialektbrudd.
import sys
sys.path.insert(0, 'micropython')
import pandas_mpy as pd

df = pd.DataFrame({'by': ['Oslo', 'Bergen', 'Oslo'], 'v': [10, 20, 30]})
assert len(df) == 3
g = df.groupby('by')['v'].mean()
assert '<table' in df.to_html()
sub = df[df['v'] > 10]
assert len(sub) == 2
df['dobbel'] = df['v'] * 2
assert list(df['dobbel']) == [20, 40, 60]
from io import StringIO
df2 = pd.read_csv(StringIO('a,b\n1,"x,y"\n2,z\n'))
assert len(df2) == 2
s = pd.Series([1, 2, 3, 4, 5])
s.iloc[1:3] = pd.Series([100, 200])
assert list(s) == [1, 100, 200, 4, 5]
print('MPY-PANDAS-RØYK OK')

# ── Paritetsarbeidet 2026-07-26: dialekt-røyk for de nye kodestiene ───────
# CPython-testene fanger IKKE MicroPython-fellene; det er denne fila som gjør
# det. Spec: docs/superpowers/specs/2026-07-26-pandas-parity-design.md

# dtype + astype med strengnavn (P0-2)
assert str(pd.Series([1, 2, 3]).dtype) == 'int64'
assert str(pd.Series([1.5]).dtype) == 'float64'
assert str(pd.Series(['a']).dtype) == 'object'
assert list(pd.Series([1, 2]).astype('float64')) == [1.0, 2.0]
assert list(pd.Series([1.7, 2.2]).astype('int')) == [1, 2]
assert list(df.dtypes) == ['object', 'int64', 'int64']

# drop muterer ikke (P0-1)
_before = tuple(df.columns)
_out = df.drop('dobbel', axis=1)
assert tuple(df.columns) == _before, 'drop muterte mottakeren'
assert 'dobbel' not in tuple(_out.columns)

# O(1)-indeksoppslag (P0-3) — _pos_map bruker dict, ikke tuple.index
_s = pd.Series([10, 20, 30], index=['a', 'b', 'a'])
assert _s.index_of('a') == 0 and _s.index_of('b') == 1
assert _s.index_of('finnes-ikke') is None

# Categorical (P1-1) — ordnet rekkefølge, ikke alfabetisk
_c = pd.cut(pd.Series([1, 5, 15, 3, 12]), [0, 2, 10, 20],
            labels=['lav', 'middels', 'høy'])
assert list(_c.sort_values()) == ['lav', 'middels', 'middels', 'høy', 'høy'], \
    'kategorirekkefølge feilet: %r' % list(_c.sort_values())
assert str(_c.dtype) == 'category'
assert list(_c.cat.categories) == ['lav', 'middels', 'høy']
assert list(pd.Series(['b', 'a', 'b']).astype('category').cat.codes) == [1, 0, 1]

# .str — pandas-egne metoder over MicroPythons re-delmengde (P1-3).
# _re_finditer/_group_count finnes fordi re mangler finditer og .groups.
_ss = pd.Series(['Oslo-2020', 'bergen-1999', None])
# NB: MicroPythons re støtter IKKE {m,n}-kvantorer — mønsteret gjentar
# derfor \d i stedet. _re_compile kaster en tydelig feil for {n}-formen.
assert list(_ss.str.extract(r'(\d\d\d\d)')[0])[:2] == ['2020', '1999']
try:
    _ss.str.contains(r'\d{4}')
    _braces_ok = True
except ValueError as _e:
    _braces_ok = False
    assert 'kvantor' in str(_e), str(_e)

assert list(_ss.str.count('o'))[:2] == [1, 0]
assert list(_ss.str.findall(r'\d'))[1] == ['1', '9', '9', '9']
assert _ss.str.cat(sep='|') == 'Oslo-2020|bergen-1999'
assert list(_ss.str.pad(12, side='left', fillchar='.'))[0] == '...Oslo-2020'
try:
    _ss.str.finnes_ikke()
    raise AssertionError('forventet AttributeError')
except AttributeError as _e:
    assert 'finnes_ikke' in str(_e)

# Vindus- og aggregatverb (P1-4)
assert list(pd.Series([1, 2, 4]).diff())[1:] == [1, 2]
assert list(pd.Series([1, 2, 4]).cumprod()) == [1, 2, 8]
assert list(pd.Series([1, 2, 3]).agg(['sum', 'max'])) == [6, 3]
assert list(pd.Series([[1, 2], [3]]).explode()) == [1, 2, 3]
assert list(pd.DataFrame({'a': [1, 2]}).cumsum()['a']) == [1, 3]

# Datoer (P1-2). unix-micropython mangler datetime HELT; wasm-bygget har den
# uten strptime. Testen kjører derfor bare der datetime finnes.
try:
    import datetime as _dtmod
    _has_datetime = True
except ImportError:
    _has_datetime = False
if _has_datetime:
    _d = pd.to_datetime(pd.Series(['2020-03-15', '2024-02-29']))
    assert list(_d.dt.quarter) == [1, 1]
    assert list(_d.dt.days_in_month) == [31, 29]
    assert list(_d.dt.is_leap_year) == [True, True]
    assert list(_d.dt.day_name()) == ['Sunday', 'Thursday']
    assert len(pd.date_range('2020-01-30', periods=4)) == 4
    print('  (dato-testene kjørt — datetime finnes i denne bygningen)')
else:
    print('  (dato-testene hoppet over — datetime mangler i unix-bygget)')

# attrs (2026-07-26 runde 2): fri metadata på frame/serie. NB dialektrisiko —
# @property.setter må faktisk virke i MicroPython, ikke bare i CPython.
_a = pd.DataFrame({'x': [1, 2], 'y': ['a', 'b']})
assert _a.attrs == {}
_a.attrs['kilde'] = 'ssb/07459'
assert _a.copy().attrs == {'kilde': 'ssb/07459'}, 'attrs overlevde ikke copy()'
assert _a[['x']].attrs == {'kilde': 'ssb/07459'}, 'attrs overlevde ikke kolonnevalg'
assert _a['x'].attrs == {'kilde': 'ssb/07459'}, 'serien arvet ikke attrs'
assert _a.head(1).attrs == {'kilde': 'ssb/07459'}, 'attrs overlevde ikke head()'
_a.attrs = {'bare': 'denne'}          # setteren
assert _a.attrs == {'bare': 'denne'}, 'property-setteren virker ikke'
_b = pd.DataFrame({'x': [1]})
assert _b.attrs == {}, 'attrs lekker mellom framer'
_a.name = 'mitt_datasett'
assert _a.copy().name == 'mitt_datasett', 'name overlevde ikke copy()'
_s = pd.Series([3, 1, 2], name='v')
_s.attrs['enhet'] = 'kroner'
assert _s.sort_values().attrs == {'enhet': 'kroner'}, 'serie-attrs overlevde ikke sortering'

print('MPY-PANDAS-PARITET-RØYK OK')
