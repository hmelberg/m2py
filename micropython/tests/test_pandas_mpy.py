import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas_mpy as pd

def test_import_and_basic_frame():
    df = pd.DataFrame({'a': [1, 2, 3], 'b': ['x', 'y', 'x']})
    assert len(df) == 3
    assert list(df['a']) == [1, 2, 3]

def test_read_csv_stringio():
    df = pd.read_csv(io.StringIO("a,b\n1,x\n2,y\n"))
    assert len(df) == 2

def test_groupby_and_to_html():
    df = pd.DataFrame({'g': ['a', 'a', 'b'], 'v': [1, 2, 3]})
    counts = df.groupby('g').size()
    html = df.to_html()
    assert '<table' in html

def test_gap_verbs_raise_clear_error():
    # 2026-07-10: merge/join/pivot_table/melt/corr er implementert (se
    # test_pandas_mpy_diff.py); bare MultiIndex-/tidsserie-avhengige
    # verb er igjen som gap.
    df = pd.DataFrame({'a': [1]})
    for verb in ['pivot', 'rolling', 'resample']:
        try:
            getattr(df, verb)()
            raise AssertionError(verb + ' should raise NotImplementedError')
        except NotImplementedError as e:
            assert 'Brython' in str(e), verb + ': message must name Brython mode'

def test_former_gap_verbs_now_implemented():
    for verb in ['merge', 'crosstab', 'get_dummies', 'pivot_table', 'melt']:
        fn = getattr(pd, verb)
        assert callable(fn) and fn.__name__ != verb or fn.__name__ == verb
        assert 'NotImplementedError' not in (fn.__doc__ or '') and not getattr(fn, '_is_gap', False)
    for verb in ['merge', 'join', 'pivot_table', 'melt', 'corr']:
        assert getattr(pd.DataFrame, verb).__doc__ is None or 'Brython-modus' not in getattr(pd.DataFrame, verb).__doc__

def test_read_csv_type_inference():
    df = pd.read_csv(io.StringIO("a,b,c\n1,x,1.5\n2,y,\n"))
    assert list(df['a']) == [1, 2], 'int inference'
    assert isinstance(list(df['c'])[0], float), 'float inference'
    assert list(df['b']) == ['x', 'y'], 'strings preserved'
    missing = list(df['c'])[1]
    assert missing is pd.nan, 'empty numeric cell becomes nan sentinel'
    assert len(df.dropna()) == 1, 'dropna sees the nan'
    assert df['a'].mean() == 1.5, 'mean works on inferred ints'

def test_groupby_mean_with_missing_values():
    df = pd.read_csv(io.StringIO("g,v\na,1\na,\nb,3\n"))
    out = df.groupby('g').mean()
    html = out.to_html()
    assert '<table' in html

def test_float_display_formatting():
    df = pd.DataFrame({'g': ['a', 'b'], 'v': [5.005999999999999, 620000.0]})
    html = df.to_html()
    assert '5.006' in html and '5.005999' not in html, 'float noise rounded in to_html'
    assert '620000.0' in html, 'integral float keeps .0'
    txt = str(df)
    assert '5.006' in txt and '5.005999' not in txt, 'float noise rounded in str()'
    # data itself is untouched
    assert list(df['v'])[0] == 5.005999999999999


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn(); print('PASS', name)
