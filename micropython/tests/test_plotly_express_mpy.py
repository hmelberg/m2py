import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas_mpy as pd
import plotly_express_mpy as pe

DF = pd.DataFrame({'x': [1, 2, 3, 4], 'y': [10, 20, 15, 30], 'g': ['a', 'a', 'b', 'b']})

def test_scatter_returns_json_figure():
    fig = pe.scatter(DF, x='x', y='y', color='g', title='t')
    s = fig.to_plotly_json_str()
    spec = json.loads(s)
    assert 'data' in spec and 'layout' in spec
    assert len(spec['data']) >= 1

def test_no_plotlyplot_prefix_anywhere():
    fig = pe.bar(DF, x='g', y='y')
    assert not fig.to_plotly_json_str().startswith('plotlyplot:')
    assert not str(fig).startswith('plotlyplot:')

def test_chart_families():
    for fn, kw in [(pe.line, dict(x='x', y='y')), (pe.histogram, dict(x='y')),
                   (pe.box, dict(x='g', y='y')), (pe.pie, dict(names='g', values='y'))]:
        spec = json.loads(fn(DF, **kw).to_plotly_json_str())
        assert 'data' in spec, fn.__name__

def test_violin_accepts_dataframe():
    fig = pe.violin(DF, x='g', y='y')
    spec = json.loads(fig.to_plotly_json_str())
    assert 'data' in spec

def test_scatter_3d_accepts_dataframe():
    df3d = pd.DataFrame({'x': [1, 2, 3, 4], 'y': [10, 20, 15, 30], 'z': [5, 3, 8, 1]})
    fig = pe.scatter_3d(df3d, x='x', y='y', z='z')
    spec = json.loads(fig.to_plotly_json_str())
    assert 'data' in spec

def test_imshow_returns_json_figure():
    fig = pe.imshow([[1, 2], [3, 4]])
    spec = json.loads(fig.to_plotly_json_str())
    assert 'data' in spec

if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn(); print('PASS', name)
