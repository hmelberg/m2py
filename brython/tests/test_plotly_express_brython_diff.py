# Differensial- og regresjonstester for plotly_express_brython.
# Fasit: ekte plotly express (installert lokalt) via normaliserte utdrag —
# antall traces, navn, x/y-verdier, moduser — IKKE hele spec-en (px legger
# inn store layout-defaults). Kjøres under CPython:
#   python3 brython/tests/test_plotly_express_brython_diff.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas_brython as bpd
import plotly_express_brython as pe

try:
    import pandas as rpd
    import plotly.express as px
    HAS_PX = True
except ImportError:
    HAS_PX = False


def spec_of(fig):
    return json.loads(fig.to_plotly_json_str())


def norm_traces(spec):
    out = []
    for t in spec['data']:
        out.append((t.get('name'), list(t.get('x') or []), list(t.get('y') or [])))
    return out


def px_traces(fig):
    return [(t.name if t.name else None,
             [v for v in (t.x if t.x is not None else [])],
             [v for v in (t.y if t.y is not None else [])]) for t in fig.data]


D = {"aar": [2020, 2021, 2022] * 2, "antall": [1, 2, 3, 4, 5, 6],
     "region": ["A"] * 3 + ["B"] * 3}


def test_line_color_grouping_matches_px():
    if not HAS_PX:
        return
    mine = norm_traces(spec_of(pe.line(bpd.DataFrame(D), x="aar", y="antall", color="region")))
    ref = px_traces(px.line(rpd.DataFrame(D), x="aar", y="antall", color="region"))
    assert mine == ref, (mine, ref)


def test_scatter_color_grouping_matches_px():
    if not HAS_PX:
        return
    mine = norm_traces(spec_of(pe.scatter(bpd.DataFrame(D), x="aar", y="antall", color="region")))
    ref = px_traces(px.scatter(rpd.DataFrame(D), x="aar", y="antall", color="region"))
    assert mine == ref, (mine, ref)


def test_nan_everywhere_serializes():
    d = {"x": [1, 2, 3], "y": [1.0, bpd.nan, 3.0], "g": ["a", bpd.nan, "b"]}
    df = bpd.DataFrame(d)
    for fig in [pe.scatter(df, x="x", y="y", color="g"),
                pe.line(df, x="x", y="y"),
                pe.bar(df, x="x", y="y"),
                pe.histogram(df, x="y"),
                pe.box(df, x="g", y="y"),
                pe.scatter(df, x="x", y="y", facet_col="g")]:
        spec = spec_of(fig)          # må ikke kaste
        assert 'data' in spec


def test_deterministic_color_order():
    df = bpd.DataFrame({"x": [1, 2, 3], "y": [1, 2, 3], "g": ["c1", "c2", "c3"]})
    spec = spec_of(pe.scatter(df, x="x", y="y", color="g",
                              color_discrete_sequence=["red", "green", "blue"]))
    assert [t["marker"]["color"] for t in spec["data"]] == ["red", "green", "blue"]
    # color_discrete_map respekteres, resten følger sekvensen
    spec2 = spec_of(pe.scatter(df, x="x", y="y", color="g",
                               color_discrete_map={"c2": "black"}))
    cols = {t["name"]: t["marker"]["color"] for t in spec2["data"]}
    assert cols["c2"] == "black" and cols["c1"] != cols["c3"]


def test_continuous_color_single_trace():
    df = bpd.DataFrame({"x": [1, 2, 3, 4], "y": [4, 3, 2, 1], "v": [10, 20, 30, 40]})
    spec = spec_of(pe.scatter(df, x="x", y="y", color="v"))
    assert len(spec["data"]) == 1, "numerisk color skal gi ÉN trace"
    m = spec["data"][0]["marker"]
    assert m["color"] == [10, 20, 30, 40] and m.get("colorscale") and m.get("showscale")


def test_group_modes():
    d = {"g": ["a", "a", "b", "b"], "v": [1, 2, 3, 4], "k": ["x", "y", "x", "y"]}
    df = bpd.DataFrame(d)
    assert spec_of(pe.box(df, x="g", y="v", color="k"))["layout"].get("boxmode") == "group"
    assert spec_of(pe.violin(df, x="g", y="v", color="k"))["layout"].get("violinmode") == "group"
    assert spec_of(pe.histogram(df, x="v", color="k"))["layout"].get("barmode") == "relative"


def test_hover_fields():
    df = bpd.DataFrame({"x": [1, 2], "y": [3, 4], "navn": ["Oslo", "Bergen"], "ekstra": [9, 8]})
    spec = spec_of(pe.scatter(df, x="x", y="y", hover_name="navn", hover_data=["ekstra"]))
    t = spec["data"][0]
    assert t.get("hovertext") == ["Oslo", "Bergen"]
    assert t.get("customdata") == [[9], [8]], "customdata skal være per-punkt-rader"
    assert "hovertemplate" in t and "%{hovertext}" in t["hovertemplate"]


def test_facet_missing_combo_no_shift():
    # (a,x) mangler: panelnummereringen skal likevel følge rutenettet
    d = {"x": [1, 2, 3], "y": [1, 2, 3],
         "r": ["a", "b", "b"], "c": ["v", "v", "w"]}
    spec = spec_of(pe.scatter(bpd.DataFrame(d), x="x", y="y", facet_row="r", facet_col="c"))
    by_name = {t["name"]: t for t in spec["data"]}
    # ruter: (a,v)=1, (a,w)=2, (b,v)=3, (b,w)=4 — b-v skal ha akse 3
    assert by_name["b-v"]["xaxis"] == "x3", by_name


def test_facet_wrap_axes_exist():
    d = {"x": list(range(6)), "y": list(range(6)), "g": ["a", "b", "c", "d", "e", "f"]}
    spec = spec_of(pe.scatter(bpd.DataFrame(d), x="x", y="y", facet_col="g", facet_col_wrap=3))
    lay = spec["layout"]
    assert lay["grid"]["rows"] == 2 and lay["grid"]["columns"] == 3
    for t in spec["data"]:
        ax = t.get("xaxis", "x")
        n = ax[1:] or "1"
        key = "xaxis" if n == "1" else "xaxis" + n
        assert key in lay, f"trace refererer {ax} som ikke finnes i layout"


def test_many_facets_no_domain_inversion():
    n = 12
    d = {"x": list(range(n)), "y": list(range(n)), "g": [f"k{i}" for i in range(n)]}
    spec = spec_of(pe.scatter(bpd.DataFrame(d), x="x", y="y", facet_col="g"))
    for k, v in spec["layout"].items():
        if k.startswith("xaxis") and isinstance(v, dict) and "domain" in v:
            a, b = v["domain"]
            assert a < b, f"invertert domene i {k}: {v['domain']}"


def test_trendline_ols():
    df = bpd.DataFrame({"x": [1, 2, 3, 4], "y": [2.0, 4.0, 6.0, 8.0]})
    spec = spec_of(pe.scatter(df, x="x", y="y", trendline="ols"))
    tl = [t for t in spec["data"] if "OLS" in (t.get("name") or "")]
    assert len(tl) == 1
    ys = tl[0]["y"]
    assert abs(ys[0] - 2.0) < 1e-9 and abs(ys[-1] - 8.0) < 1e-9, ys


def test_series_input():
    df = bpd.DataFrame({"g": ["a", "a", "b"], "v": [1, 3, 5]})
    s = df.groupby("g")["v"].mean()
    spec = spec_of(pe.bar(s))
    t = spec["data"][0]
    assert t["x"] == ["a", "b"] and t["y"] == [2.0, 5.0], t


def test_px_aliases_and_pie_hole():
    df = bpd.DataFrame({"x": [1, 10, 100], "y": [1, 2, 3]})
    lay = spec_of(pe.scatter(df, x="x", y="y", log_x=True, range_y=[0, 5], opacity=0.5))["layout"]
    assert lay["xaxis"]["type"] == "log" and lay["yaxis"]["range"] == [0, 5]
    spec = spec_of(pe.pie(bpd.DataFrame({"n": ["a", "b"], "v": [1, 2]}), values="v", names="n", hole=0.4))
    assert spec["data"][0]["hole"] == 0.4
    barspec = spec_of(pe.bar(df, x="x", y="y", text_auto=True))
    assert barspec["data"][0].get("texttemplate") == "%{y}"


def test_update_layout_underscore():
    fig = pe.scatter(bpd.DataFrame({"x": [1], "y": [1]}), x="x", y="y")
    fig.update_layout(xaxis_title="Tid", legend_title="Grupper")
    assert fig.layout["xaxis"]["title"] == "Tid"
    assert fig.layout["legend"]["title"] == "Grupper"


def test_norsk_tallformat():
    pe.defaults.norsk = True
    try:
        spec = spec_of(pe.scatter(bpd.DataFrame({"x": [1], "y": [1]}), x="x", y="y"))
        assert spec["layout"]["separators"] == ", "  # desimalkomma + hardt mellomrom
    finally:
        pe.defaults.norsk = False


def test_no_null_noise_in_traces():
    df = bpd.DataFrame({"x": [1, 2], "y": [3, 4]})
    spec = spec_of(pe.scatter(df, x="x", y="y"))
    def no_nulls(d):
        for k, v in d.items():
            assert v is not None, f"null-verdi for {k}"
            if isinstance(v, dict):
                no_nulls(v)
    for t in spec["data"]:
        no_nulls(t)


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn(); print('PASS', name)
    print('ALLE PLOTLY-DIFF-TESTER GRØNNE' + ('' if HAS_PX else ' (uten px-fasit)'))
