import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
import matplotlib_brython as plt
import seaborn_brython as sns

DF = {
    'alder':   [25.0, 32.0, 41.0, 28.0, 55.0, 47.0],
    'inntekt': [420.0, 500.0, 610.0, 455.0, 720.0, 650.0],
    'region':  ['N', 'S', 'N', 'S', 'N', 'S'],
}


def setup_function(_fn):
    plt.figure()


def test_scatterplot_draws_into_current_figure():
    sns.scatterplot(data=DF, x='alder', y='inntekt')
    fig = plt.gcf()
    assert len(fig.data) == 1
    assert fig.data[0]['type'] == 'scatter'
    assert fig.data[0]['x'] == DF['alder']

def test_scatterplot_hue_gives_groups_and_legend():
    sns.scatterplot(data=DF, x='alder', y='inntekt', hue='region')
    fig = plt.gcf()
    assert len(fig.data) == 2                      # én trace per region
    names = {t.get('name') for t in fig.data}
    assert names == {'N', 'S'}
    assert fig.layout['showlegend'] is True

def test_axis_titles_from_pe_layout_not_overwriting():
    plt.xlabel('Egen tittel')
    sns.scatterplot(data=DF, x='alder', y='inntekt')
    lay = plt.gcf().layout
    assert lay['xaxis']['title'] == {'text': 'Egen tittel'}   # min vinner

def test_composes_with_plt(capsys):
    sns.lineplot(data=DF, x='alder', y='inntekt')
    plt.title('Kombinert')
    plt.show()
    out = capsys.readouterr().out
    assert 'figure__' in out and 'Kombinert' in out

def test_regplot_adds_trend_trace():
    sns.regplot(data=DF, x='alder', y='inntekt')
    fig = plt.gcf()
    assert len(fig.data) >= 2                      # punkter + OLS-linje
    modes = [t.get('mode', '') for t in fig.data]
    assert any('lines' in m for m in modes)

def test_vectors_directly_without_data():
    sns.scatterplot(x=[1.0, 2.0, 3.0], y=[2.0, 4.0, 6.0])
    assert plt.gcf().data[0]['y'] == [2.0, 4.0, 6.0]

def test_histplot_bins_and_hue():
    sns.histplot(data=DF, x='inntekt', bins=5)
    t = plt.gcf().data[0]
    assert t['type'] == 'histogram'
    assert t.get('nbinsx') == 5
    plt.figure()
    sns.histplot(data=DF, x='inntekt', hue='region')
    assert len(plt.gcf().data) == 2

def test_boxplot_and_violinplot():
    sns.boxplot(data=DF, x='region', y='inntekt')
    assert plt.gcf().data[0]['type'] == 'box'
    plt.figure()
    sns.violinplot(data=DF, x='region', y='inntekt')
    assert plt.gcf().data[0]['type'] == 'violin'

def test_heatmap():
    sns.heatmap([[1.0, 0.5], [0.5, 1.0]])
    types = [t.get('type') for t in plt.gcf().data]
    assert 'heatmap' in types

def test_noops_and_stubs():
    sns.set_theme(style='whitegrid')
    sns.set(style='darkgrid')                     # aliaset
    sns.despine()
    with pytest.raises(NotImplementedError, match='støttes ikke'):
        sns.kdeplot(data=DF, x='inntekt')
    with pytest.raises(NotImplementedError):
        sns.pairplot(DF)
    with pytest.raises(NotImplementedError):
        sns.jointplot(data=DF, x='alder', y='inntekt')

def test_countplot_frequencies_in_appearance_order():
    sns.countplot(data=DF, x='region')
    t = plt.gcf().data[0]
    assert t['type'] == 'bar'
    assert t['x'] == ['N', 'S']                    # opptredensrekkefølge
    assert t['y'] == [3, 3]

def test_barplot_group_means_and_ci():
    d = {'g': ['a', 'a', 'b', 'b', 'b'], 'v': [1.0, 3.0, 10.0, 20.0, 30.0]}
    sns.barplot(data=d, x='g', y='v')
    t = plt.gcf().data[0]
    assert t['type'] == 'bar'
    assert t['x'] == ['a', 'b']
    assert t['y'] == pytest.approx([2.0, 20.0])    # GJENNOMSNITT, ikke sum
    # 1.96*SE: a: sd=sqrt(2), se=1 -> 1.96 ; b: sd=10, se=10/sqrt(3)
    err = t['error_y']['array']
    assert err[0] == pytest.approx(1.96, rel=1e-9)
    assert err[1] == pytest.approx(1.96 * 10.0 / (3 ** 0.5), rel=1e-9)

def test_barplot_no_errorbar_and_hue():
    d = {'g': ['a', 'b', 'a', 'b'], 'h': ['x', 'x', 'y', 'y'],
         'v': [1.0, 2.0, 3.0, 4.0]}
    sns.barplot(data=d, x='g', y='v', errorbar=None)
    assert 'error_y' not in plt.gcf().data[0]
    plt.figure()
    sns.barplot(data=d, x='g', y='v', hue='h')
    fig = plt.gcf()
    assert len(fig.data) == 2
    assert {t['name'] for t in fig.data} == {'x', 'y'}
    assert fig.layout['showlegend'] is True
    byname = {t['name']: t for t in fig.data}
    assert byname['x']['y'] == pytest.approx([1.0, 2.0])
    assert byname['y']['y'] == pytest.approx([3.0, 4.0])

def test_heatmap_accepts_dataframe():
    import pandas_brython as pd
    df = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [2.0, 4.0, 5.9]})
    plt.figure()
    sns.heatmap(df.corr())
    types = [t.get('type') for t in plt.gcf().data]
    assert 'heatmap' in types
    import json
    json.dumps(plt.gcf().to_plotly_json_str() and 1)   # serialiserbar (via str)

def test_barplot_errorbar_variants():
    d = {'g': ['a', 'a', 'a'], 'v': [1.0, 2.0, 3.0]}   # sd=1.0, se=1/sqrt(3)
    plt.figure()
    sns.barplot(data=d, x='g', y='v', errorbar='sd')
    assert plt.gcf().data[0]['error_y']['array'][0] == pytest.approx(1.0)
    plt.figure()
    sns.barplot(data=d, x='g', y='v', errorbar='se')
    assert plt.gcf().data[0]['error_y']['array'][0] == pytest.approx(1.0 / 3 ** 0.5)
    with pytest.raises(ValueError, match='støttes ikke'):
        sns.barplot(data=d, x='g', y='v', errorbar='pi')
