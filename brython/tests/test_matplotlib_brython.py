import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import matplotlib_brython as plt

ES = '__micro_transform_start_'
EE = '__micro_transform_end__'


def setup_function(_fn):
    plt.figure()   # nullstiller modulstaten mellom tester


def test_plot_x_y_builds_line_trace():
    plt.plot([1, 2, 3], [4, 5, 6])
    fig = plt.gcf()
    assert len(fig.data) == 1
    t = fig.data[0]
    assert t['type'] == 'scatter' and t['mode'] == 'lines'
    assert t['x'] == [1, 2, 3] and t['y'] == [4, 5, 6]
    assert t['line']['color'] == '#1f77b4'          # C0 i tab10-syklusen

def test_plot_y_only_gets_index_x():
    plt.plot([10, 20, 30])
    t = plt.gcf().data[0]
    assert t['x'] == [0, 1, 2] and t['y'] == [10, 20, 30]

def test_plot_fmt_string_color_marker_dash():
    plt.plot([1, 2], [3, 4], 'ro--')
    t = plt.gcf().data[0]
    assert t['line']['color'] == 'red'
    assert t['line']['dash'] == 'dash'
    assert t['mode'] == 'lines+markers'
    assert t['marker']['symbol'] == 'circle'

def test_plot_repeated_triples_and_color_cycle():
    plt.plot([1, 2], [3, 4], [1, 2], [5, 6])
    fig = plt.gcf()
    assert len(fig.data) == 2
    assert fig.data[0]['line']['color'] == '#1f77b4'
    assert fig.data[1]['line']['color'] == '#ff7f0e'  # C1

def test_labels_and_title():
    plt.plot([1], [1])
    plt.title('Tittel')
    plt.xlabel('X-akse')
    plt.ylabel('Y-akse')
    lay = plt.gcf().layout
    assert lay['title'] == {'text': 'Tittel'}
    assert lay['xaxis']['title'] == {'text': 'X-akse'}
    assert lay['yaxis']['title'] == {'text': 'Y-akse'}

def test_figure_figsize_inches_to_px():
    plt.figure(figsize=(7, 4))
    lay = plt.gcf().layout
    assert lay['width'] == 700 and lay['height'] == 400

def test_show_prints_embed_marker_and_resets(capsys):
    plt.plot([1, 2], [3, 4])
    plt.show()
    out = capsys.readouterr().out
    assert (ES + 'figure__') in out and EE in out
    payload = out.split(ES + 'figure__')[1].split(EE)[0].strip()
    spec = json.loads(payload)
    assert spec['data'][0]['y'] == [3, 4]
    assert spec['layout']['showlegend'] is False      # ingen legend() kalt
    plt.show()                                        # tom stat → ingenting
    assert capsys.readouterr().out == ''

def test_values_accepts_range_and_duck_typed_series():
    class FakeSeries:                                  # pandas_brython-duck
        def tolist(self):
            return [7, 8]
    plt.plot(range(2), FakeSeries())
    t = plt.gcf().data[0]
    assert t['x'] == [0, 1] and t['y'] == [7, 8]

def test_gcf_returns_live_current_figure():
    plt.plot([1], [1])
    fig = plt.gcf()
    fig.update_layout(xaxis_title='Levende')   # PlotlyFigure-mutatorer virker på gjeldende figur
    assert plt.gcf().layout['xaxis']['title'] == 'Levende'

def test_scatter_markers_color_size_alpha():
    plt.scatter([1, 2], [3, 4], s=12, c='green', alpha=0.5, label='pts')
    t = plt.gcf().data[0]
    assert t['type'] == 'scatter' and t['mode'] == 'markers'
    assert t['marker']['color'] == 'green'
    assert t['marker']['size'] == 12
    assert t['marker']['opacity'] == 0.5
    assert t['name'] == 'pts'

def test_scatter_numeric_c_becomes_colorscale():
    plt.scatter([1, 2], [3, 4], c=[0.1, 0.9])
    m = plt.gcf().data[0]['marker']
    assert m['color'] == [0.1, 0.9]
    assert m['colorscale'] == 'Viridis' and m['showscale'] is True

def test_bar_and_barh():
    plt.bar(['a', 'b'], [3, 4])
    plt.barh(['c', 'd'], [5, 6])
    f = plt.gcf()
    assert f.data[0]['type'] == 'bar' and f.data[0]['y'] == [3, 4]
    assert f.data[1]['orientation'] == 'h' and f.data[1]['x'] == [5, 6]

def test_hist_bins_and_density():
    plt.hist([1, 1, 2, 3], bins=3, density=True)
    t = plt.gcf().data[0]
    assert t['type'] == 'histogram' and t['nbinsx'] == 3
    assert t['histnorm'] == 'probability density'

def test_boxplot_single_and_multiple():
    plt.boxplot([1, 2, 3])
    assert plt.gcf().data[0]['type'] == 'box'
    plt.figure()
    plt.boxplot([[1, 2], [3, 4]], labels=['A', 'B'])
    f = plt.gcf()
    assert len(f.data) == 2
    assert f.data[0]['name'] == 'A' and f.data[1]['y'] == [3, 4]

def test_pie_values_labels_and_legend_default():
    plt.pie([30, 70], labels=['a', 'b'])
    f = plt.gcf()
    assert f.data[0]['type'] == 'pie'
    assert f.data[0]['values'] == [30, 70] and f.data[0]['labels'] == ['a', 'b']
    assert f.layout['showlegend'] is True    # pie-unntaket fra Task 2

def test_xlim_ylim_scalar_and_tuple():
    plt.plot([1], [1])
    plt.xlim(0, 10)
    plt.ylim((2, 8))
    lay = plt.gcf().layout
    assert lay['xaxis']['range'] == [0, 10]
    assert lay['yaxis']['range'] == [2, 8]

def test_xlim_partial_preserves_other_limit():
    plt.plot([1], [1])
    plt.xlim(0, 10)
    plt.xlim(2)                      # bare venstre — høyre beholdes
    assert plt.gcf().layout['xaxis']['range'] == [2, 10]

def test_legend_and_grid():
    plt.plot([1], [1], label='serie')
    plt.legend()
    plt.grid(False)
    lay = plt.gcf().layout
    assert lay['showlegend'] is True
    assert lay['xaxis']['showgrid'] is False and lay['yaxis']['showgrid'] is False

def test_xticks_rotation_and_labels():
    plt.bar(['a', 'b'], [1, 2])
    plt.xticks([0, 1], ['Alfa', 'Beta'], rotation=45)
    ax = plt.gcf().layout['xaxis']
    assert ax['tickvals'] == [0, 1]
    assert ax['ticktext'] == ['Alfa', 'Beta']
    assert ax['tickangle'] == -45

def test_savefig_renders_like_show(capsys):
    plt.plot([1, 2], [3, 4])
    plt.savefig('fig.png')
    out = capsys.readouterr().out
    assert (ES + 'figure__') in out

def test_subplots_1x1_delegates(capsys):
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot([1, 2], [3, 4])
    ax.set_title('Aksetittel')
    ax.set_xlabel('x')
    ax.legend()
    f = plt.gcf()
    assert f.layout['width'] == 600
    assert f.layout['title'] == {'text': 'Aksetittel'}
    assert f.layout['xaxis']['title'] == {'text': 'x'}
    assert f.layout['showlegend'] is True
    fig.show()
    assert (ES + 'figure__') in capsys.readouterr().out

def test_subplots_grid_raises():
    import pytest
    with pytest.raises(NotImplementedError):
        plt.subplots(2, 2)

def test_xlim_keyword_and_getter_forms():
    plt.plot([1], [1])
    plt.xlim(left=0, right=10)
    assert plt.xlim() == [0, 10]            # getter — endrer ingenting
    assert plt.gcf().layout['xaxis']['range'] == [0, 10]
    plt.ylim(bottom=1, top=5)
    assert plt.ylim() == [1, 5]

def test_ax_set_xlim_keywords():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [1, 2])
    ax.set_xlim(left=0, right=3)
    assert plt.gcf().layout['xaxis']['range'] == [0, 3]
