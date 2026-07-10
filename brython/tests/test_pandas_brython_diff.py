# Differensialtester: kjør samme operasjon i pandas_brython og ekte pandas,
# sammenlikn normaliserte resultater. Modulen er ren Python, så alt som er
# grønt her har pandas-*semantikken* riktig (sorteringsrekkefølge, how=outer,
# ddof, nan-håndtering …). Kjøres under CPython (ekte pandas kreves):
#   python3 brython/tests/test_pandas_brython_diff.py
# NB: fanger ikke Brython-spesifikke stdlib-hull — det gjør nettleser-røyktesten.
import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas_brython as bpd
import pandas as rpd


# ── Harness ────────────────────────────────────────────────────────────────

def _norm(v):
    """Normaliser en verdi for sammenlikning på tvers av bibliotekene."""
    if v is bpd.nan:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return round(v, 9)
    if isinstance(v, tuple):
        return tuple(_norm(x) for x in v)
    if hasattr(v, 'item'):          # numpy-skalar
        return _norm(v.item())
    return v


def _norm_series(s):
    if isinstance(s, bpd.Series):
        return ([_norm(i) for i in (s.index or [])], [_norm(v) for v in s.values])
    return ([_norm(i) for i in list(s.index)], [_norm(v) for v in list(s)])


def _norm_frame(df, ignore_index=False):
    if isinstance(df, bpd.DataFrame):
        cols = [_norm(c) for c in df.columns]
        idx = [_norm(i) for i in df.index]
        rows = [[_norm(v) for v in row] for row in df.values]
    else:
        cols = [_norm(c) for c in list(df.columns)]
        idx = [_norm(i) for i in list(df.index)]
        rows = [[_norm(v) for v in row] for row in df.itertuples(index=False)]
    if ignore_index:
        idx = list(range(len(idx)))
    return (cols, idx, rows)


def assert_same(op, data=None, ignore_index=False, label=''):
    """Kjør op(pd, DATA-kopi) med begge bibliotekene og sammenlikn."""
    b = op(bpd, dict(data) if data else None)
    r = op(rpd, dict(data) if data else None)
    if isinstance(b, bpd.Series) or isinstance(r, rpd.Series):
        bn, rn = _norm_series(b), _norm_series(r)
        if ignore_index:
            bn, rn = bn[1], rn[1]
    elif isinstance(b, bpd.DataFrame) or isinstance(r, rpd.DataFrame):
        bn, rn = _norm_frame(b, ignore_index), _norm_frame(r, ignore_index)
    else:
        bn, rn = _norm(b), _norm(r)
    assert bn == rn, '%s\n  brython: %r\n  pandas:  %r' % (label or op, bn, rn)


# Golden-datasett: blandede typer, nan, duplikater — samme form som
# _bind_datasets leverer fra CSV.
DATA = {
    'g': ['a', 'b', 'a', 'c', 'b', 'a'],
    'h': ['x', 'x', 'y', 'y', 'x', 'y'],
    'v': [1, 5, 3, 2, 4, 6],
    'w': [1.5, 2.5, 3.5, 0.5, 4.5, 2.0],
}


# ── Punkt 3/4: aggregat-bugfikser + value_counts ──────────────────────────

def test_sum_mean_dropna_false():
    s = [1.0, 2.0, 3.0]
    assert_same(lambda pd, d: pd.Series(s).sum(), label='sum')
    assert_same(lambda pd, d: pd.Series(s).mean(), label='mean')
    # dropna=False uten nan skal være identisk med default (krasjet før)
    assert bpd.Series(s).sum(dropna=False) == 6.0
    assert bpd.Series(s).mean(dropna=False) == 2.0
    # med nan og dropna=False: pandas gir nan
    assert _norm(bpd.Series([1.0, bpd.nan]).sum(dropna=False)) is None
    assert _norm(bpd.Series([1.0, bpd.nan]).mean(dropna=False)) is None


def test_value_counts_sorted_and_normalize():
    vals = ['b', 'a', 'c', 'c', 'c', 'a']
    b = bpd.Series(vals).value_counts()
    r = rpd.Series(vals).value_counts()
    assert list(b.values) == list(r) and list(b.index) == list(r.index)
    bn = bpd.Series(vals).value_counts(normalize=True)
    rn = rpd.Series(vals).value_counts(normalize=True)
    assert [_norm(v) for v in bn.values] == [_norm(v) for v in rn]


# ── Punkt 1: GroupBy ───────────────────────────────────────────────────────

def test_groupby_getitem_single_col():
    assert_same(lambda pd, d: pd.DataFrame(d).groupby('g')['v'].mean(), DATA)
    assert_same(lambda pd, d: pd.DataFrame(d).groupby('g')['v'].sum(), DATA)


def test_groupby_agg_str_and_dict():
    assert_same(lambda pd, d: pd.DataFrame(d)[['g', 'v', 'w']].groupby('g').agg('mean'), DATA)
    assert_same(lambda pd, d: pd.DataFrame(d).groupby('g').agg({'v': 'sum', 'w': 'mean'}), DATA)


def test_groupby_multicol_by():
    b = bpd.DataFrame(dict(DATA)).groupby(['g', 'h'])['v'].sum()
    r = rpd.DataFrame(dict(DATA)).groupby(['g', 'h'])['v'].sum()
    assert [_norm(i) for i in b.index] == [_norm(i) for i in r.index.tolist()]
    assert [_norm(v) for v in b.values] == [_norm(v) for v in list(r)]


def test_groupby_sorted_groups():
    assert_same(lambda pd, d: pd.DataFrame(d).groupby('g')['v'].count(), DATA)


# ── Punkt 2: merge ─────────────────────────────────────────────────────────

LEFT = {'k': ['a', 'b', 'c', 'a'], 'x': [1, 2, 3, 4]}
RIGHT = {'k': ['a', 'b', 'd'], 'y': [10, 20, 40]}

def test_merge_inner_left_outer():
    for how in ('inner', 'left', 'right', 'outer'):
        assert_same(lambda pd, d, how=how: pd.merge(pd.DataFrame(LEFT), pd.DataFrame(RIGHT), on='k', how=how),
                    ignore_index=True, label='merge how=' + how)


def test_merge_suffixes_and_left_on():
    l = {'k': ['a', 'b'], 'v': [1, 2]}
    r = {'j': ['a', 'b'], 'v': [10, 20]}
    assert_same(lambda pd, d: pd.merge(pd.DataFrame(l), pd.DataFrame(r), left_on='k', right_on='j'),
                ignore_index=True)


def test_dataframe_merge_method():
    assert_same(lambda pd, d: pd.DataFrame(LEFT).merge(pd.DataFrame(RIGHT), on='k'), ignore_index=True)


# ── Punkt 8: pivot_table + crosstab ───────────────────────────────────────

def test_pivot_table_mean_and_sum():
    for agg in ('mean', 'sum', 'count'):
        assert_same(lambda pd, d, agg=agg: pd.DataFrame(d).pivot_table(index='g', columns='h', values='v', aggfunc=agg),
                    DATA, label='pivot_table ' + agg)


def test_pivot_table_no_columns():
    assert_same(lambda pd, d: pd.DataFrame(d).pivot_table(index='g', values='v', aggfunc='sum'), DATA)


def test_crosstab():
    assert_same(lambda pd, d: pd.crosstab(pd.Series(DATA['g']), pd.Series(DATA['h'])), None)


# ── Punkt 5: dt + to_datetime ─────────────────────────────────────────────

def test_to_datetime_and_dt():
    dates = ['2024-01-15', '2024-06-30', '2023-12-01']
    assert_same(lambda pd, d: pd.to_datetime(pd.Series(dates)).dt.year, ignore_index=False)
    assert_same(lambda pd, d: pd.to_datetime(pd.Series(dates)).dt.month)
    assert_same(lambda pd, d: pd.to_datetime(pd.Series(dates)).dt.day)
    assert_same(lambda pd, d: pd.to_datetime(pd.Series(dates)).dt.dayofweek)
    assert_same(lambda pd, d: pd.to_datetime(pd.Series(dates)).dt.strftime('%Y/%m'))


# ── Punkt 6: str-accessor ─────────────────────────────────────────────────

def test_str_methods():
    s = ['Alpha', 'beta', bpd.nan, 'Gamma']
    rs = ['Alpha', 'beta', float('nan'), 'Gamma']
    b = bpd.Series(s).str.contains('a')
    r = rpd.Series(rs).str.contains('a')
    assert [_norm(v) for v in b.values] == [_norm(v) for v in list(r)]
    assert_same(lambda pd, d: pd.Series(['Aa', 'bB']).str.lower())
    assert_same(lambda pd, d: pd.Series(['Aa', 'bB']).str.upper())
    assert_same(lambda pd, d: pd.Series([' x ', 'y']).str.strip())
    assert_same(lambda pd, d: pd.Series(['ab', 'cde']).str.len())
    assert_same(lambda pd, d: pd.Series(['a-b', 'c-d']).str.replace('-', '+'))
    assert_same(lambda pd, d: pd.Series(['ax', 'bx']).str.startswith('a'))


# ── Punkt 7: Series-småmetoder ────────────────────────────────────────────

def test_series_small_methods():
    v = [3, 1, 2, 1, 5]
    assert_same(lambda pd, d: pd.Series(v).map({1: 'en', 2: 'to'}), label='map dict')
    assert_same(lambda pd, d: pd.Series(v).isin([1, 5]), label='isin')
    assert_same(lambda pd, d: pd.Series([1.0, float('nan') if pd is rpd else bpd.nan]).notna(), label='notna')
    assert_same(lambda pd, d: pd.Series(v).head(3), label='head')
    assert_same(lambda pd, d: pd.Series(v).tail(2), label='tail')
    assert_same(lambda pd, d: pd.Series([1.234, 5.678]).round(1), label='round')
    assert_same(lambda pd, d: pd.Series([-1, 2, -3]).abs(), label='abs')
    assert_same(lambda pd, d: pd.Series(v).count(), label='count')
    assert_same(lambda pd, d: pd.Series(v, index=[4, 2, 0, 1, 3]).sort_index(), label='sort_index')
    assert_same(lambda pd, d: pd.Series(v).nlargest(2), label='nlargest')
    assert_same(lambda pd, d: pd.Series(v).nsmallest(2), label='nsmallest')
    assert_same(lambda pd, d: pd.Series(v).cumsum(), label='cumsum')
    assert_same(lambda pd, d: pd.Series(v).rank(), label='rank')
    assert_same(lambda pd, d: pd.Series([1, 2, 2, 3]).mode(), label='mode')


def test_series_describe():
    b = bpd.Series([1.0, 2.0, 3.0, 4.0]).describe()
    r = rpd.Series([1.0, 2.0, 3.0, 4.0]).describe()
    assert [_norm(i) for i in b.index] == list(r.index)
    assert [_norm(v) for v in b.values] == [_norm(v) for v in list(r)]


# ── Punkt 9: corr ─────────────────────────────────────────────────────────

def test_corr():
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    c = [2.0, 1.0, 4.0, 3.0, 6.0]
    assert_same(lambda pd, d: pd.Series(a).corr(pd.Series(c)), label='Series.corr')
    assert_same(lambda pd, d: pd.DataFrame({'a': a, 'c': c}).corr(), label='DataFrame.corr')


# ── Punkt 10/11: melt + get_dummies ───────────────────────────────────────

def test_melt():
    d = {'id': [1, 2], 'x': [10, 20], 'y': [30, 40]}
    assert_same(lambda pd, dd: pd.melt(pd.DataFrame(d), id_vars=['id'], value_vars=['x', 'y']),
                ignore_index=True)
    assert_same(lambda pd, dd: pd.DataFrame(d).melt(id_vars=['id']), ignore_index=True)


def test_get_dummies():
    b = bpd.get_dummies(bpd.Series(['a', 'b', 'a']))
    r = rpd.get_dummies(rpd.Series(['a', 'b', 'a']), dtype=int)
    assert _norm_frame(b) == _norm_frame(r)
    b2 = bpd.get_dummies(bpd.Series(['a', 'b']), prefix='k')
    assert list(b2.columns) == ['k_a', 'k_b']


# ── Punkt 12: cut/qcut (egenskapstest — pandas returnerer Categorical) ────

def test_cut_qcut():
    x = [1, 4, 6, 9]
    b = bpd.cut(bpd.Series(x), bins=[0, 5, 10])
    r = rpd.cut(rpd.Series(x), bins=[0, 5, 10])
    assert [str(v) for v in b.values] == [str(v) for v in list(r)]
    lab = bpd.cut(bpd.Series(x), bins=[0, 5, 10], labels=['lav', 'høy'])
    assert list(lab.values) == ['lav', 'lav', 'høy', 'høy']
    q = bpd.qcut(bpd.Series([1, 2, 3, 4]), 2, labels=['lav', 'høy'])
    assert list(q.values) == ['lav', 'lav', 'høy', 'høy']


# ── Punkt 13: nan-aritmetikk ──────────────────────────────────────────────

def test_nan_arithmetic():
    n = bpd.nan
    for expr in (lambda: n - 1, lambda: 1 - n, lambda: n / 2, lambda: 2 / n,
                 lambda: -n, lambda: abs(n), lambda: 2 * n, lambda: n ** 2, lambda: 2 ** n):
        assert expr() is n, expr
    s = bpd.Series([1.0, n, 3.0]) - 1
    assert _norm_series(s)[1] == [0.0, None, 2.0]
    s2 = bpd.Series([1.0, n]) * 2
    assert _norm_series(s2)[1] == [2.0, None]


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn(); print('PASS', name)
    print('ALLE DIFF-TESTER GRØNNE')
