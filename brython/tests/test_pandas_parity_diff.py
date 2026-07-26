# Differensialtester for pandas-paritetsarbeidet (P0+P1).
# Spec: docs/superpowers/specs/2026-07-26-pandas-parity-design.md
#
# Gjenbruker harnessen i test_pandas_brython_diff.py: hver test kjører samme
# operasjon i shimmen og i ekte pandas og sammenlikner normaliserte
# resultater. Kjøres under CPython (ekte pandas kreves):
#   python3 brython/tests/test_pandas_parity_diff.py
import sys, os, math, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
import pandas as rpd

# Samme testsett kjøres mot BEGGE portene: PANDAS_SHIM=mpy velger
# micropython/pandas_mpy.py. Portene er divergerende kopier, så det er den
# eneste måten å vite at de faktisk har samme semantikk.
if os.environ.get('PANDAS_SHIM') == 'mpy':
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'micropython'))
    import pandas_mpy as bpd
else:
    import pandas_brython as bpd


def _norm(v):
    """
    Normaliser for sammenlikning på tvers av bibliotekene. Egen kopi (ikke
    importert fra test_pandas_brython_diff) fordi den der er bundet til
    pandas_brython sin nan-sentinel — med PANDAS_SHIM=mpy ville mpy-nan blitt
    stående og alle nan-sammenlikninger sett ut som avvik.
    """
    if v is bpd.nan:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return round(v, 9)
    if isinstance(v, (tuple, list)):
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
    """Som harnessen i test_pandas_brython_diff, men mot valgt shim."""
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
    assert bn == rn, '%s\n  shim:   %r\n  pandas: %r' % (label or op, bn, rn)

DATA = {
    'g': ['a', 'b', 'a', 'c', 'b', 'a'],
    'h': ['x', 'x', 'y', 'y', 'x', 'y'],
    'v': [1, 5, 3, 2, 4, 6],
    'w': [1.5, 2.5, 3.5, 0.5, 4.5, 2.0],
}


# ── P0-1: drop muterer ikke ────────────────────────────────────────────────

def test_drop_does_not_mutate():
    for pd in (bpd, rpd):
        df = pd.DataFrame(dict(DATA))
        before_cols = tuple(df.columns)
        out = df.drop('g', axis=1)
        assert tuple(df.columns) == before_cols, '%s: drop(axis=1) muterte mottakeren' % pd
        assert 'g' not in tuple(out.columns)
        df2 = pd.DataFrame(dict(DATA))
        before_idx = tuple(df2.index)
        out2 = df2.drop(0, axis=0)
        assert tuple(df2.index) == before_idx, '%s: drop(axis=0) muterte mottakeren' % pd
        assert 0 not in tuple(out2.index)


def test_drop_axis_default_and_kwargs():
    # pandas-default er axis=0 (rader)
    assert_same(lambda pd, d: pd.DataFrame(d).drop(0), DATA, label='drop default axis')
    assert_same(lambda pd, d: pd.DataFrame(d).drop(columns='g'), DATA, label='drop columns=')
    assert_same(lambda pd, d: pd.DataFrame(d).drop(index=[0, 2]), DATA, label='drop index=')
    assert_same(lambda pd, d: pd.DataFrame(d).drop(index=[0], columns=['g']), DATA,
                label='drop index= + columns=')
    assert_same(lambda pd, d: pd.DataFrame(d).drop(['g', 'h'], axis=1), DATA,
                label='drop liste av kolonner')


def test_delitem_still_mutates():
    # del df['kol'] SKAL mutere (pandas gjør det)
    for pd in (bpd, rpd):
        df = pd.DataFrame(dict(DATA))
        del df['g']
        assert 'g' not in tuple(df.columns)


def test_groupby_after_drop_still_works():
    # regresjon: groupby brukte den muterende dropen internt
    assert_same(lambda pd, d: pd.DataFrame(d).groupby('g')['v'].mean(), DATA)
    assert_same(lambda pd, d: pd.DataFrame(d).groupby(['g', 'h'])['v'].sum(), DATA,
                label='groupby to nøkler')
    df = bpd.DataFrame(dict(DATA))
    df.groupby('g').mean()
    assert tuple(df.columns) == ('g', 'h', 'v', 'w'), 'groupby muterte kildeframen'


# ── P0-2: dtype og astype med strengnavn ───────────────────────────────────

def test_series_dtype():
    cases = [([1, 2, 3], 'int64'), ([1.0, 2.5], 'float64'), (['a', 'b'], 'object'),
             ([True, False], 'bool'), ([1, 'a'], 'object')]
    for vals, expected in cases:
        assert str(bpd.Series(vals).dtype) == expected, vals
        assert str(rpd.Series(vals).dtype) == expected, ('pandas selv', vals)


def test_dataframe_dtypes():
    b = bpd.DataFrame(dict(DATA)).dtypes
    r = rpd.DataFrame(dict(DATA)).dtypes
    assert list(b.index) == list(r.index)
    assert [str(v) for v in b.values] == [str(v) for v in r]


def test_astype_string_names():
    assert_same(lambda pd, d: pd.Series([1, 2, 3]).astype('float64'), label="astype('float64')")
    assert_same(lambda pd, d: pd.Series([1.7, 2.2]).astype('int'), label="astype('int')")
    assert_same(lambda pd, d: pd.Series([1, 0]).astype('bool'), label="astype('bool')")
    b = bpd.Series([1, 2]).astype('str')
    r = rpd.Series([1, 2]).astype('str')
    assert list(b.values) == list(r)
    bd = bpd.DataFrame(dict(DATA)).astype({'v': 'float64'})
    rd = rpd.DataFrame(dict(DATA)).astype({'v': 'float64'})
    assert _norm_frame(bd) == _norm_frame(rd)
    assert str(bd['v'].dtype) == 'float64'


# ── P0-3: O(1) indeksoppslag ───────────────────────────────────────────────

def test_index_of_duplicate_labels_first_wins():
    s = bpd.Series([10, 20, 30], index=['a', 'b', 'a'])
    assert s.index_of('a') == 0, 'første forekomst skal vinne, som tuple.index'
    assert s.index_of('b') == 1
    assert s.index_of('mangler') is None


def test_sort_values_is_not_quadratic():
    def timed(n):
        # Beste av tre: én enkelt måling er for utsatt for planleggerstøy når
        # testsuiten kjører parallelt, og minimum er det stabile estimatet.
        data = {'a': list(range(n)), 'b': [(i * 7919) % n for i in range(n)]}
        best = None
        for _ in range(3):
            df = bpd.DataFrame(dict(data))
            t = time.perf_counter()
            df.sort_values('b')
            dt = time.perf_counter() - t
            best = dt if best is None else min(best, dt)
        return best
    timed(400)                      # oppvarming: første kall betaler import-
                                    # og cache-kostnader som ellers skjevfordeles
    t1000, t4000 = timed(1000), timed(4000)
    # Kvadratisk oppførsel ga 15x da denne testen ble skrevet; lineær-
    # logaritmisk gir 4-5x. Grensen er romslig for å tåle en travel maskin.
    ratio = t4000 / max(t1000, 1e-6)
    assert ratio < 9, 'sort_values ser kvadratisk ut: 4x data ga %.1fx tid' % ratio


def test_sort_values_correct():
    assert_same(lambda pd, d: pd.DataFrame(d).sort_values('v'), DATA)
    assert_same(lambda pd, d: pd.DataFrame(d).sort_values('w', ascending=False), DATA)


# ── P1-1: Categorical ──────────────────────────────────────────────────────

def test_cut_sorts_by_bin_order_not_alphabetically():
    x = [1, 5, 15, 3, 12]
    bins = [0, 2, 10, 20]
    b = list(dict.fromkeys(str(v) for v in bpd.cut(bpd.Series(x), bins).sort_values().values))
    r = list(dict.fromkeys(str(v) for v in rpd.cut(rpd.Series(x), bins).sort_values()))
    assert b == r, 'bin-rekkefølge: %r vs %r' % (b, r)


def test_cut_labels_sort_in_label_order():
    x = [1, 5, 15, 3, 12]
    bins = [0, 2, 10, 20]
    labs = ['lav', 'middels', 'høy']
    b = list(dict.fromkeys(bpd.cut(bpd.Series(x), bins, labels=labs).sort_values().values))
    r = list(dict.fromkeys(str(v) for v in rpd.cut(rpd.Series(x), bins, labels=labs).sort_values()))
    assert b == r, 'etikettrekkefølge: %r vs %r' % (b, r)


def test_categorical_accessor():
    s = bpd.Series(['b', 'a', 'b']).astype('category')
    r = rpd.Series(['b', 'a', 'b']).astype('category')
    assert str(s.dtype) == 'category'
    assert list(s.cat.categories) == list(r.cat.categories)
    assert list(s.cat.codes) == list(r.cat.codes)
    assert s.cat.ordered == bool(r.cat.ordered)


def test_categorical_value_counts_and_groupby_order():
    x = [1, 5, 15, 3, 12]
    bins = [0, 2, 10, 20]
    labs = ['lav', 'middels', 'høy']
    bc = bpd.cut(bpd.Series(x), bins, labels=labs)
    rc = rpd.cut(rpd.Series(x), bins, labels=labs)
    assert list(bc.value_counts().index) == [str(i) for i in rc.value_counts().index]
    bdf = bpd.DataFrame({'grp': bc, 'v': x})
    rdf = rpd.DataFrame({'grp': rc, 'v': x})
    assert list(bdf.groupby('grp')['v'].sum().index) == \
        [str(i) for i in rdf.groupby('grp', observed=True)['v'].sum().index]


# ── P1-2: datoer ───────────────────────────────────────────────────────────

DATES = ['2020-03-15', '2021-11-02', '2024-02-29', '2020-01-01']


def test_strptime_fallback_matches_stdlib():
    from datetime import datetime as _dt
    cases = [('2020-03-15', '%Y-%m-%d'), ('15.03.2020', '%d.%m.%Y'),
             ('2020-03-15 14:30:05', '%Y-%m-%d %H:%M:%S'), ('20200315', '%Y%m%d'),
             ('03/15/2020', '%m/%d/%Y'), ('99-01-02', '%y-%m-%d')]
    for s, fmt in cases:
        assert bpd._strptime(s, fmt) == _dt.strptime(s, fmt), (s, fmt)


def test_dt_properties():
    b = bpd.to_datetime(bpd.Series(DATES))
    r = rpd.to_datetime(rpd.Series(DATES))
    for prop in ('year', 'month', 'day', 'quarter', 'dayofweek', 'dayofyear',
                 'days_in_month', 'is_leap_year', 'is_month_start', 'is_month_end',
                 'is_quarter_start', 'is_year_start'):
        bv = [_norm(v) for v in getattr(b.dt, prop).values]
        rv = [_norm(v) for v in list(getattr(r.dt, prop))]
        assert bv == rv, '%s: %r vs %r' % (prop, bv, rv)


def test_dt_methods():
    b = bpd.to_datetime(bpd.Series(DATES))
    r = rpd.to_datetime(rpd.Series(DATES))
    assert list(b.dt.day_name().values) == list(r.dt.day_name())
    assert list(b.dt.month_name().values) == list(r.dt.month_name())
    assert [str(v) for v in b.dt.normalize().values] == [str(v) for v in r.dt.normalize()]


def test_date_range():
    b = bpd.date_range('2020-01-30', periods=4)
    r = rpd.date_range('2020-01-30', periods=4)
    assert [str(v) for v in b] == [str(v) for v in r]


# ── P1-3: strenger ─────────────────────────────────────────────────────────

STRINGS = ['Oslo-2020', 'bergen-1999', None, 'TRONDHEIM-2024']


def test_str_extract_and_match():
    b, r = bpd.Series(STRINGS), rpd.Series(STRINGS)
    be = b.str.extract(r'(\d{4})')
    re_ = r.str.extract(r'(\d{4})')
    assert [_norm(v) for v in be[0].values] == [_norm(v) for v in re_[0]]
    assert [_norm(v) for v in b.str.match(r'[A-Z]').values] == \
           [_norm(v) for v in r.str.match(r'[A-Z]')]
    assert [_norm(v) for v in b.str.count('o').values] == \
           [_norm(v) for v in r.str.count('o')]


def test_str_misc():
    b, r = bpd.Series(STRINGS), rpd.Series(STRINGS)
    assert [_norm(v) for v in b.str.findall(r'\d').values] == \
           [_norm(v) for v in r.str.findall(r'\d')]
    assert [_norm(v) for v in b.str.pad(12, side='left', fillchar='.').values] == \
           [_norm(v) for v in r.str.pad(12, side='left', fillchar='.')]
    assert b.str.cat(sep='|') == r.str.cat(sep='|')
    assert [_norm(v) for v in b.str.repeat(2).values] == [_norm(v) for v in r.str.repeat(2)]


def test_str_unknown_attribute_message():
    try:
        bpd.Series(['a']).str.finnes_ikke()
    except AttributeError as e:
        assert 'finnes_ikke' in str(e) and 'str' in str(e).lower()
    else:
        raise AssertionError('forventet AttributeError')


# ── P1-4: vindus- og aggregatverb ──────────────────────────────────────────

def test_shift_diff_pct_change():
    assert_same(lambda pd, d: pd.Series(d['v']).shift(1), DATA, label='shift')
    assert_same(lambda pd, d: pd.Series(d['v']).shift(-2), DATA, label='shift negativ')
    assert_same(lambda pd, d: pd.Series(d['v']).diff(), DATA, label='diff')
    assert_same(lambda pd, d: pd.Series(d['w']).pct_change(), DATA, label='pct_change')
    assert_same(lambda pd, d: pd.DataFrame(d)[['v', 'w']].diff(), DATA, label='df.diff')


def test_cumulative():
    assert_same(lambda pd, d: pd.Series(d['v']).cumprod(), DATA, label='cumprod')
    assert_same(lambda pd, d: pd.Series(d['v']).cummax(), DATA, label='cummax')
    assert_same(lambda pd, d: pd.Series(d['v']).cummin(), DATA, label='cummin')
    assert_same(lambda pd, d: pd.DataFrame(d)[['v', 'w']].cumsum(), DATA, label='df.cumsum')


def test_agg_and_transform():
    assert_same(lambda pd, d: pd.Series(d['v']).agg('mean'), DATA, label='ser.agg str')
    b = bpd.Series(DATA['v']).agg(['mean', 'max'])
    r = rpd.Series(DATA['v']).agg(['mean', 'max'])
    assert _norm_series(b) == _norm_series(r)
    bt = bpd.Series(DATA['v']).transform(lambda v: v * 2)
    rt = rpd.Series(DATA['v']).transform(lambda v: v * 2)
    assert _norm_series(bt) == _norm_series(rt)
    ba = bpd.DataFrame(dict(DATA))[['v', 'w']].agg('sum')
    ra = rpd.DataFrame(dict(DATA))[['v', 'w']].agg('sum')
    assert _norm_series(ba) == _norm_series(ra)


def test_frame_helpers():
    assert_same(lambda pd, d: pd.DataFrame(d)[['v', 'w']].round(0), DATA, label='df.round')
    assert_same(lambda pd, d: pd.DataFrame(d)['g'].to_frame(), DATA, label='to_frame')
    b = bpd.DataFrame(dict(DATA)).isin([1, 'a'])
    r = rpd.DataFrame(dict(DATA)).isin([1, 'a'])
    assert _norm_frame(b) == _norm_frame(r)
    assert list(bpd.DataFrame(dict(DATA)).select_dtypes('number').columns) == \
        list(rpd.DataFrame(dict(DATA)).select_dtypes('number').columns)
    bi = [tuple(t) for t in bpd.DataFrame(dict(DATA)).itertuples(index=False)]
    ri = [tuple(t) for t in rpd.DataFrame(dict(DATA)).itertuples(index=False)]
    assert bi == ri


def test_explode():
    b = bpd.Series([[1, 2], [3], []]).explode()
    r = rpd.Series([[1, 2], [3], []]).explode()
    assert _norm_series(b) == _norm_series(r)




# ── attrs: fri metadata på frame/serie (2026-07-26, runde 2) ───────────────
# pandas' attrs er den slotten som er MENT for kildehenvisning, lisens,
# hentetidspunkt o.l., og den propagerer bedre enn ryktet: den overlever
# kolonnevalg, copy(), groupby-aggregat og to_frame(), og arves av serier
# hentet ut av framen. Shimen speiler den oppførselen.

def test_attrs_exists_and_defaults_empty():
    for pd in (bpd, rpd):
        df = pd.DataFrame(dict(DATA))
        assert df.attrs == {}, pd
        assert pd.Series([1, 2]).attrs == {}, pd


def test_attrs_propagates_like_pandas():
    for pd in (bpd, rpd):
        df = pd.DataFrame(dict(DATA))
        df.attrs['kilde'] = 'ssb/07459'
        assert df.copy().attrs == {'kilde': 'ssb/07459'}, ('copy', pd)
        assert df[['v', 'w']].attrs == {'kilde': 'ssb/07459'}, ('kolonnevalg', pd)
        assert df['v'].attrs == {'kilde': 'ssb/07459'}, ('serie arver', pd)
        assert df['v'].to_frame().attrs == {'kilde': 'ssb/07459'}, ('to_frame', pd)
        assert df.head(2).attrs == {'kilde': 'ssb/07459'}, ('head', pd)
        assert df.sort_values('v').attrs == {'kilde': 'ssb/07459'}, ('sort_values', pd)


def test_attrs_is_not_shared_between_frames():
    # Egen dict per objekt — ellers ville metadata lekke mellom datasett.
    for pd in (bpd, rpd):
        a, b = pd.DataFrame({'x': [1]}), pd.DataFrame({'x': [1]})
        a.attrs['kilde'] = 'A'
        assert b.attrs == {}, pd
        c = a.copy()
        c.attrs['kilde'] = 'C'
        assert a.attrs['kilde'] == 'A', ('kopi deler dict', pd)


def test_series_attrs_survives_operations():
    for pd in (bpd, rpd):
        s = pd.Series([3, 1, 2], name='v')
        s.attrs['enhet'] = 'kroner'
        assert s.copy().attrs == {'enhet': 'kroner'}, pd
        assert s.sort_values().attrs == {'enhet': 'kroner'}, pd
        assert s.head(2).attrs == {'enhet': 'kroner'}, pd


def test_dataframe_name_survives_copy_and_selection():
    # DataFrame.name fantes, men forsvant ved copy()/kolonnevalg — den var
    # dermed ubrukelig som brukermetadata. (pandas har ikke df.name i det
    # hele tatt, så dette testes bare mot shimen.)
    df = bpd.DataFrame(dict(DATA))
    df.name = 'mitt_datasett'
    assert df.copy().name == 'mitt_datasett'
    assert df[['v', 'w']].name == 'mitt_datasett'


def test_groupby_still_uses_name_for_group_keys():
    # Regresjonsvakt: GroupBy.loop_func leser df.name som gruppenøkkel.
    df = bpd.DataFrame(dict(DATA))
    df.name = 'mitt_datasett'
    gb = df.groupby('g')
    assert [d.name for d in gb.dfs] == ['a', 'b', 'c']
    assert list(gb['v'].sum().index) == ['a', 'b', 'c']


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            try:
                fn()
                print('PASS', name)
            except Exception as e:
                failed += 1
                print('FAIL', name, '->', type(e).__name__, str(e)[:160])
    print('ALLE PARITETSTESTER GRØNNE' if not failed else '%d TESTER RØDE' % failed)
    sys.exit(1 if failed else 0)
