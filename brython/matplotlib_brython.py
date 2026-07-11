# matplotlib_brython — matplotlib.pyplot-shim på toppen av PlotlyFigure.
# Brukes som `import matplotlib.pyplot as plt` (aliaser i LIB_REGISTRY) eller
# direkte som matplotlib_brython. Bygger plotly-traces i en modulglobal
# "gjeldende figur"; show() skriver samme embed-markør-protokoll som
# brython_runner._fmt, så index.html rendrer uendret.
from plotly_express_brython import PlotlyFigure, remove_none

# Embed-markører — stabil app-protokoll (samme konstanter i brython_runner.py
# og index.html buildOutputNodes)
_EMBED_S = '__micro_transform_start_'
_EMBED_E = '__micro_transform_end__'

# matplotlibs standard fargesyklus (tab10, C0..C9)
_COLOR_CYCLE = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

_FMT_COLORS = {'b': 'blue', 'g': 'green', 'r': 'red', 'c': 'cyan',
               'm': 'magenta', 'y': 'yellow', 'k': 'black', 'w': 'white'}
_FMT_MARKERS = {'o': 'circle', 's': 'square', '^': 'triangle-up',
                'v': 'triangle-down', 'd': 'diamond', '*': 'star',
                'x': 'x', '+': 'cross', '.': 'circle'}
_FMT_DASH = {'-': 'solid', '--': 'dash', ':': 'dot', '-.': 'dashdot'}

_state = {'traces': [], 'layout': {}, 'color_i': 0}


def _reset():
    _state['traces'] = []
    _state['layout'] = {}
    _state['color_i'] = 0


def _next_color():
    c = _COLOR_CYCLE[_state['color_i'] % len(_COLOR_CYCLE)]
    _state['color_i'] += 1
    return c


def _values(v):
    """list-ifiser: lister, tupler, range og pandas_brython-Series (duck-typet
    på tolist/values, så ingen import av pandas_brython trengs)."""
    if v is None:
        return None
    if hasattr(v, 'tolist'):
        return list(v.tolist())
    if hasattr(v, 'values') and not isinstance(v, dict):
        vals = v.values
        return list(vals() if callable(vals) else vals)
    return list(v)


def _clean(d):
    return remove_none(d)


def _parse_fmt(fmt):
    """'ro--' -> (farge, markør, dash). Alle deler valgfrie; tokolonne-dasher
    ('--', '-.') må plukkes før enkelttegn."""
    color = marker = dash = None
    rest = fmt or ''
    for two in ('--', '-.'):
        if two in rest:
            dash = _FMT_DASH[two]
            rest = rest.replace(two, '', 1)
            break
    for ch in rest:
        if ch in _FMT_COLORS and color is None:
            color = _FMT_COLORS[ch]
        elif ch in _FMT_MARKERS and marker is None:
            marker = _FMT_MARKERS[ch]
        elif ch in ('-', ':') and dash is None:
            dash = _FMT_DASH[ch]
    return color, marker, dash


def figure(figsize=None, **kwargs):
    """Start en ny (tom) gjeldende figur. figsize i tommer -> px (dpi=100)."""
    _reset()
    if figsize:
        _state['layout']['width'] = int(figsize[0] * 100)
        _state['layout']['height'] = int(figsize[1] * 100)


def plot(*args, **kwargs):
    """plt.plot(y) | plot(x, y) | plot(x, y, 'r--') | gjentatte (x, y, fmt)."""
    args = list(args)
    while args:
        x = _values(args.pop(0))
        y = None
        fmt = ''
        if args and not isinstance(args[0], str):
            y = _values(args.pop(0))
        if args and isinstance(args[0], str):
            fmt = args.pop(0)
        if y is None:
            x, y = list(range(len(x))), x
        color, marker, dash = _parse_fmt(fmt)
        color = kwargs.get('color', color) or _next_color()
        trace = {'type': 'scatter', 'x': x, 'y': y,
                 'mode': 'lines+markers' if marker else 'lines',
                 'line': {'color': color, 'dash': dash or 'solid',
                          'width': kwargs.get('linewidth', 2)},
                 'name': kwargs.get('label')}
        if marker:
            trace['marker'] = {'symbol': marker, 'color': color}
        _state['traces'].append(_clean(trace))


def scatter(x, y, s=None, c=None, alpha=None, label=None, **kwargs):
    marker = {}
    if isinstance(c, str):
        marker['color'] = c
    elif c is not None:
        # tallverdier -> kontinuerlig fargeskala (som plt gjør med cmap)
        marker['color'] = _values(c)
        marker['colorscale'] = 'Viridis'
        marker['showscale'] = True
    else:
        marker['color'] = _next_color()
    if s is not None:
        # NB: matplotlib-s er areal i pt^2, plotly-size er diameter i px —
        # verdien sendes videre som-den-er (godt nok for undervisningsbruk)
        marker['size'] = s if isinstance(s, (int, float)) else _values(s)
    if alpha is not None:
        marker['opacity'] = alpha
    _state['traces'].append(_clean({'type': 'scatter', 'x': _values(x),
                                    'y': _values(y), 'mode': 'markers',
                                    'marker': marker, 'name': label}))


def bar(x, height, color=None, label=None, **kwargs):
    _state['traces'].append(_clean({'type': 'bar', 'x': _values(x),
                                    'y': _values(height),
                                    'marker': {'color': color or _next_color()},
                                    'name': label}))


def barh(y, width, color=None, label=None, **kwargs):
    _state['traces'].append(_clean({'type': 'bar', 'x': _values(width),
                                    'y': _values(y), 'orientation': 'h',
                                    'marker': {'color': color or _next_color()},
                                    'name': label}))


def hist(x, bins=None, color=None, label=None, density=False, **kwargs):
    t = {'type': 'histogram', 'x': _values(x),
         'marker': {'color': color or _next_color()}, 'name': label}
    if isinstance(bins, int):
        t['nbinsx'] = bins
    if density:
        t['histnorm'] = 'probability density'
    _state['traces'].append(_clean(t))


def _is_listlike(v):
    return hasattr(v, '__len__') and not isinstance(v, str) or hasattr(v, 'tolist')


def boxplot(x, labels=None, **kwargs):
    series_list = list(x) if _is_listlike(x) and len(x) and _is_listlike(list(x)[0]) else [x]
    for i, series in enumerate(series_list):
        name = labels[i] if labels is not None and i < len(labels) else None
        _state['traces'].append(_clean({'type': 'box', 'y': _values(series),
                                        'name': name}))


def pie(x, labels=None, colors=None, autopct=None, **kwargs):
    # autopct ignoreres — plotly viser prosent i hover/tekst selv
    _state['traces'].append(_clean({'type': 'pie', 'values': _values(x),
                                    'labels': _values(labels) if labels is not None else None,
                                    'marker': {'colors': list(colors)} if colors else None}))


def title(s, **kwargs):
    _state['layout']['title'] = {'text': s}


def xlabel(s, **kwargs):
    _state['layout'].setdefault('xaxis', {})['title'] = {'text': s}


def ylabel(s, **kwargs):
    _state['layout'].setdefault('yaxis', {})['title'] = {'text': s}


def xlim(a=None, b=None, **kwargs):
    """xlim(min, max) | xlim((min, max)) | xlim(left=..., right=...).
    Uten argumenter: getter som i matplotlib — returnerer gjeldende range."""
    if isinstance(a, (list, tuple)):
        a, b = a
    if a is None:
        a = kwargs.get('left')
    if b is None:
        b = kwargs.get('right')
    ax = _state['layout'].setdefault('xaxis', {})
    if a is None and b is None:
        return ax.get('range')
    prev = ax.get('range') or [None, None]
    ax['range'] = [a if a is not None else prev[0],
                   b if b is not None else prev[1]]


def ylim(a=None, b=None, **kwargs):
    """ylim(min, max) | ylim((min, max)) | ylim(bottom=..., top=...).
    Uten argumenter: getter som i matplotlib — returnerer gjeldende range."""
    if isinstance(a, (list, tuple)):
        a, b = a
    if a is None:
        a = kwargs.get('bottom')
    if b is None:
        b = kwargs.get('top')
    ax = _state['layout'].setdefault('yaxis', {})
    if a is None and b is None:
        return ax.get('range')
    prev = ax.get('range') or [None, None]
    ax['range'] = [a if a is not None else prev[0],
                   b if b is not None else prev[1]]


def legend(**kwargs):
    _state['layout']['showlegend'] = True


def grid(visible=True, **kwargs):
    _state['layout'].setdefault('xaxis', {})['showgrid'] = bool(visible)
    _state['layout'].setdefault('yaxis', {})['showgrid'] = bool(visible)


def xticks(ticks=None, labels=None, rotation=None, **kwargs):
    ax = _state['layout'].setdefault('xaxis', {})
    if ticks is not None:
        ax['tickvals'] = _values(ticks)
    if labels is not None:
        ax['ticktext'] = _values(labels)
    if rotation is not None:
        ax['tickangle'] = -rotation      # mpl roterer mot klokka, plotly med


def yticks(ticks=None, labels=None, rotation=None, **kwargs):
    ax = _state['layout'].setdefault('yaxis', {})
    if ticks is not None:
        ax['tickvals'] = _values(ticks)
    if labels is not None:
        ax['ticktext'] = _values(labels)
    if rotation is not None:
        ax['tickangle'] = -rotation


def tight_layout(**kwargs):
    pass


def savefig(*args, **kwargs):
    """Filskriving finnes ikke i nettleseren — render figuren i stedet, så
    undervisningskode som slutter med savefig() ikke mister figuren."""
    show()


class _Axes:
    """Tynn delegering til modulfunksjonene — nok til fig, ax = plt.subplots().
    NB: kaller _-aliasene, ikke globalene direkte — se Brython-fellen nederst."""
    def plot(self, *a, **kw): _plot(*a, **kw)
    def scatter(self, *a, **kw): _scatter(*a, **kw)
    def bar(self, *a, **kw): _bar(*a, **kw)
    def barh(self, *a, **kw): _barh(*a, **kw)
    def hist(self, *a, **kw): _hist(*a, **kw)
    def boxplot(self, *a, **kw): _boxplot(*a, **kw)
    def pie(self, *a, **kw): _pie(*a, **kw)
    def set_title(self, s, **kw): _title(s)
    def set_xlabel(self, s, **kw): _xlabel(s)
    def set_ylabel(self, s, **kw): _ylabel(s)
    def set_xlim(self, *a, **kw): _xlim(*a, **kw)
    def set_ylim(self, *a, **kw): _ylim(*a, **kw)
    def legend(self, **kw): _legend()
    def grid(self, visible=True, **kw): _grid(visible)


class _FigureHandle:
    def show(self): _show()
    def savefig(self, *a, **kw): _savefig(*a, **kw)
    def tight_layout(self, **kw): pass


def subplots(nrows=1, ncols=1, figsize=None, **kwargs):
    """Kun 1x1 — flerpanel: bruk plotly_express_brython-facets i stedet."""
    if nrows != 1 or ncols != 1:
        raise NotImplementedError(
            'subplots med flere paneler støttes ikke — '
            'bruk facet_row/facet_col i plotly_express_brython')
    figure(figsize=figsize)
    return _FigureHandle(), _Axes()


def gcf():
    """Gjeldende figur som PlotlyFigure — LEVENDE, som i matplotlib: mutasjoner
    på den returnerte figuren (f.eks. update_layout) gjelder gjeldende figur
    frem til neste figure()/show()."""
    if _state['traces'] and 'showlegend' not in _state['layout']:
        # matplotlib viser ikke legend uten legend() — unntak: pie har
        # etiketter i legenden i plotly, så den beholdes synlig.
        _state['layout']['showlegend'] = any(
            t.get('type') == 'pie' for t in _state['traces'])
    return PlotlyFigure({'data': _state['traces'],
                         'layout': _state['layout'], 'config': {}})


def show():
    """Render gjeldende figur (embed-markør på stdout) og nullstill."""
    if not _state['traces'] and not _state['layout']:
        return
    fig = gcf()
    print(_EMBED_S + 'figure__' + '\n' + fig.to_plotly_json_str() + '\n' + _EMBED_E)
    _reset()


# Brython-felle (verifisert i nettleser 2026-07-11): når et metodenavn er likt
# navnet på en global funksjon, løser Brython navnet FEIL inne i metodekroppen
# og kallet blir stille en no-op (CPython er korrekt). Delegerende metoder i
# _Axes/_FigureHandle kaller derfor globalene via disse ikke-kolliderende
# aliasene. Aliasene ligger sist i fila så alle funksjonene finnes.
_plot, _scatter, _bar, _barh = plot, scatter, bar, barh
_hist, _boxplot, _pie = hist, boxplot, pie
_title, _xlabel, _ylabel = title, xlabel, ylabel
_xlim, _ylim, _legend, _grid = xlim, ylim, legend, grid
_figure, _show, _savefig = figure, show, savefig
