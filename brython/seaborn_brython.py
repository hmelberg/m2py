# seaborn_brython — seaborn-shim over plotly_express_brython.
# Importeres som `import seaborn as sns` (alias i LIB_REGISTRY).
#
# sns-funksjonene tegner inn i matplotlib_brythons GJELDENDE figur (som ekte
# seaborn tegner på matplotlibs akser), så mønsteret
#     sns.histplot(...); plt.title(...); plt.show()
# virker uendret. Figurene bygges via plotly_express_brython (all hue-/
# fargelogikk gjenbrukes derfra) og sporene skjøtes inn i plt-staten.
#
# NB modulens egen felle: seaborn-API-et krever `sns.set(...)` — aliaset
# `set = set_theme` NEDERST i fila skygger innebygde set(). Ingen intern
# kode bruker bare set(); telling/deduplisering gjøres med dict/liste.
import math
import plotly_express_brython as _pe
import matplotlib_brython as _plt


def _col(data, name):
    """Kolonne som liste. `name` kan også være en vektor direkte (som i
    seaborn); data kan være dict-of-lists eller pandas_brython-DataFrame."""
    if isinstance(name, (list, tuple)):
        return list(name)
    if hasattr(name, 'tolist'):
        return list(name.tolist())
    if data is None:
        raise ValueError('oppgi data= eller send vektorer direkte')
    try:
        ser = data[name]
    except Exception:
        raise ValueError('ukjent kolonne: %r' % (name,))
    if hasattr(ser, 'tolist'):
        return list(ser.tolist())
    if hasattr(ser, 'values') and not isinstance(ser, (list, tuple)):
        vals = ser.values
        return list(vals() if callable(vals) else vals)
    return list(ser)


def _merge_into_current(fig):
    """Skjøt en PlotlyFigure fra pe inn i matplotlibs gjeldende figur.
    Layout-nøkler kopieres bare når de ikke alt er satt (brukerens
    plt.xlabel() o.l. vinner). setdefault med variabel nøkkel er forbudt
    (Brython-felle 2) — derfor eksplisitte if-not-in-løkker."""
    lay = _plt._state['layout']
    for key, value in fig.layout.items():
        if key in ('xaxis', 'yaxis') and isinstance(value, dict):
            if key not in lay:
                lay[key] = {}
            sub = lay[key]
            for k2, v2 in value.items():
                if k2 not in sub:
                    sub[k2] = v2
        elif key not in lay:
            lay[key] = value
    for t in fig.data:
        _plt._state['traces'].append(t)
    named = [t for t in _plt._state['traces'] if t.get('name')]
    if len(named) >= 2 and 'showlegend' not in lay:
        lay['showlegend'] = True


def _as_pe_data(data, cols):
    """pe-funksjonene vil ha (data, kolonnenavn). Har brukeren sendt
    vektorer direkte, bygges en midlertidig dict med genererte navn."""
    if data is not None:
        return data, cols
    built = {}
    names = []
    for i, c in enumerate(cols):
        if c is None:
            names.append(None)
            continue
        nm = 'x' if i == 0 else ('y' if i == 1 else 'serie%d' % i)
        built[nm] = _col(None if isinstance(c, (list, tuple)) or
                         hasattr(c, 'tolist') else data, c)
        names.append(nm)
    return built, names


def scatterplot(data=None, x=None, y=None, hue=None, **kwargs):
    if data is None:
        d, (xn, yn) = _as_pe_data(None, [x, y])
        _merge_into_current(_pe.scatter(d, x=xn, y=yn))
        return
    _merge_into_current(_pe.scatter(data, x=x, y=y, color=hue))


def lineplot(data=None, x=None, y=None, hue=None, **kwargs):
    if data is None:
        d, (xn, yn) = _as_pe_data(None, [x, y])
        _merge_into_current(_pe.line(d, x=xn, y=yn))
        return
    _merge_into_current(_pe.line(data, x=x, y=y, color=hue))


def regplot(data=None, x=None, y=None, **kwargs):
    """Spredningsplott med OLS-linje (pe sin trendline='ols')."""
    if data is None:
        d, (xn, yn) = _as_pe_data(None, [x, y])
        _merge_into_current(_pe.scatter(d, x=xn, y=yn, trendline='ols'))
        return
    _merge_into_current(_pe.scatter(data, x=x, y=y, trendline='ols'))


def histplot(data=None, x=None, hue=None, bins=None, **kwargs):
    if data is None:
        d, (xn,) = _as_pe_data(None, [x])
        _merge_into_current(_pe.histogram(d, x=xn, nbins=bins))
        return
    _merge_into_current(_pe.histogram(data, x=x, color=hue, nbins=bins))


def boxplot(data=None, x=None, y=None, hue=None, **kwargs):
    _merge_into_current(_pe.box(data, x=x, y=y, color=hue))


def violinplot(data=None, x=None, y=None, hue=None, **kwargs):
    _merge_into_current(_pe.violin(data, x=x, y=y, color=hue))


def heatmap(data, **kwargs):
    """Varmekart av en matrise (liste av rader, ndarray eller DataFrame)."""
    if hasattr(data, 'tolist'):
        data = data.tolist()
    elif hasattr(data, 'values') and not isinstance(data, (list, tuple, dict)):
        vals = data.values
        rows = vals() if callable(vals) else vals
        data = [list(r) for r in rows]
    _merge_into_current(_pe.imshow(data))


def set_theme(*args, **kwargs):
    """Akseptert no-op — Plotly-temaet styres av appen."""
    pass


def despine(*args, **kwargs):
    pass


def kdeplot(*args, **kwargs):
    raise NotImplementedError('kdeplot støttes ikke i Brython-utgaven — '
                              'bruk sns.histplot i stedet')


def pairplot(*args, **kwargs):
    raise NotImplementedError('pairplot støttes ikke i Brython-utgaven — '
                              'lag enkeltplott med sns.scatterplot')


def jointplot(*args, **kwargs):
    raise NotImplementedError('jointplot støttes ikke i Brython-utgaven — '
                              'bruk sns.regplot i stedet')


def _appearance_groups(keys, values=None):
    """Grupper verdiene per nøkkel i OPPTREDENSREKKEFØLGE (som seaborn for
    objekt-kolonner). Uten values telles forekomster. Ingen set()-bruk —
    aliaset sns.set skygger innebygde set()."""
    order = []
    groups = {}
    for i, k in enumerate(keys):
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(values[i] if values is not None else 1)
    return order, groups


def countplot(data=None, x=None, hue=None, **kwargs):
    xs = _col(data, x)
    if hue is None:
        order, groups = _appearance_groups(xs)
        trace = {'type': 'bar', 'x': order,
                 'y': [len(groups[k]) for k in order]}
        _plt._state['traces'].append(_plt._clean(trace))
    else:
        hs = _col(data, hue)
        horder, _ = _appearance_groups(hs)
        xorder, _ = _appearance_groups(xs)
        for hv in horder:
            counts = {}
            for xv, h in zip(xs, hs):
                if h == hv:
                    counts[xv] = counts.get(xv, 0) + 1
            trace = {'type': 'bar', 'x': xorder,
                     'y': [counts.get(k, 0) for k in xorder], 'name': hv}
            _plt._state['traces'].append(_plt._clean(trace))
        if 'showlegend' not in _plt._state['layout']:
            _plt._state['layout']['showlegend'] = True
    _sns_axis_titles(x if isinstance(x, str) else None, 'count')


def barplot(data=None, x=None, y=None, hue=None, errorbar='ci', **kwargs):
    """Som seaborn: GJENNOMSNITT per kategori, feilstrek avhengig av
    errorbar: 'ci'/('ci', 95) ~= 1.96*SE (seaborn bruker bootstrap-CI —
    dette er en dokumentert tilnærming), 'sd' = standardavvik,
    'se' = standardfeil, None = ingen feilstreker."""
    kind = errorbar[0] if isinstance(errorbar, (list, tuple)) else errorbar
    if kind not in ('ci', 'sd', 'se', None):
        raise ValueError("barplot: errorbar=%r støttes ikke — bruk 'ci', "
                          "'sd', 'se' eller None" % (errorbar,))
    xs = _col(data, x)
    ys = [float(v) for v in _col(data, y)]
    if hue is None:
        subsets = [(None, xs, ys)]
    else:
        hs = _col(data, hue)
        horder, _ = _appearance_groups(hs)
        subsets = []
        for hv in horder:
            fx = [a for a, h in zip(xs, hs) if h == hv]
            fy = [b for b, h in zip(ys, hs) if h == hv]
            subsets.append((hv, fx, fy))
    xorder, _ = _appearance_groups(xs)
    for name, fx, fy in subsets:
        order, groups = _appearance_groups(fx, fy)
        means = []
        errs = []
        for k in xorder:
            vals = groups.get(k, [])
            if not vals:
                means.append(None)
                errs.append(0.0)
                continue
            m = sum(vals) / len(vals)
            means.append(m)
            if len(vals) > 1:
                sd = math.sqrt(sum((v - m) ** 2 for v in vals)
                               / (len(vals) - 1))
                se = sd / math.sqrt(len(vals))
            else:
                sd = 0.0
                se = 0.0
            if kind == 'sd':
                errs.append(sd)
            elif kind == 'se':
                errs.append(se)
            else:
                errs.append(1.96 * se)
        trace = {'type': 'bar', 'x': xorder, 'y': means, 'name': name}
        if kind is not None:
            trace['error_y'] = {'type': 'data', 'array': errs}
        _plt._state['traces'].append(_plt._clean(trace))
    if hue is not None and 'showlegend' not in _plt._state['layout']:
        _plt._state['layout']['showlegend'] = True
    _sns_axis_titles(x if isinstance(x, str) else None,
                     y if isinstance(y, str) else None)


def _sns_axis_titles(xname, yname):
    """Sett aksetitler fra kolonnenavn — bare når de ikke alt er satt."""
    lay = _plt._state['layout']
    if xname is not None:
        if 'xaxis' not in lay:
            lay['xaxis'] = {}
        if 'title' not in lay['xaxis']:
            lay['xaxis']['title'] = {'text': xname}
    if yname is not None:
        if 'yaxis' not in lay:
            lay['yaxis'] = {}
        if 'title' not in lay['yaxis']:
            lay['yaxis']['title'] = {'text': yname}


# NB: seaborn-API-et krever sns.set(...) — dette aliaset SKYGGER innebygde
# set() for all kode under denne linja. Derfor ligger det sist i fila, og
# ingen intern kode bruker bare set().
set = set_theme
