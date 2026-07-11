
try:
    from browser import window, document, html
except ImportError:          # CPython (tests) — DOM features unavailable
    window = document = html = None
import json

def data2dict(data):
    if isinstance(data, list):
        x = list(range(len(data)))
        y = data
        data=dict(x=x, y=y)
        return (data, "x", "y")
    elif isinstance(data, dict):
        x = list(data.keys())
        y = list(data.values())
        akey = x[0]
        if not isinstance(akey, list):
            #dict with single values
            data=dict(x=x, y=y)
    return data

def remove_none(d):
    # Rekursiv (2026-07-10): traces/layout fikk null-støy som
    # {"marker": {"color": null}} fordi nestede dicts ikke ble renset.
    out = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            v = remove_none(v)
        out[k] = v
    return out

def _is_nan(v):
    """True for None, float-nan og pandas_brython's NaN-sentinel
    (duck-typet på klassenavn for å unngå sirkulær import)."""
    if v is None:
        return True
    if type(v).__name__ == 'NaN':
        return True
    return isinstance(v, float) and v != v

def _unique_ordered(values, sort=True):
    """Unike verdier med nan utelatt — nan-trygg erstatning for set()-
    baserte grupperinger (NaN-sentinelen er unhashable, så set(values)
    krasjet på ethvert datasett med manglende verdier). Sortert som px;
    blandede typer faller tilbake til opptredensrekkefølge."""
    uniq = []
    seen = set()
    for v in values:
        if _is_nan(v):
            continue
        key = v if isinstance(v, (int, float, str, bool)) else str(v)
        if key not in seen:
            seen.add(key)
            uniq.append(v)
    if sort:
        try:
            uniq = sorted(uniq)
        except TypeError:
            pass
    return uniq

def _apply_category_order(categories, category_orders, key):
    """px' category_orders={kolonne: [rekkefølge]}: nevnte kategorier først
    i angitt rekkefølge, unevnte etterpå i opprinnelig rekkefølge."""
    if not category_orders or not key or key not in category_orders:
        return categories
    wanted = [c for c in category_orders[key] if c in categories]
    rest = [c for c in categories if c not in wanted]
    return wanted + rest

def _series_xy(data, x, y):
    """Series-input (to_dict gir {'index': ..., 'values': ...}): bruk
    indeksen som x og verdiene som y når x/y ikke er oppgitt — gjør
    df.groupby('g')['v'].mean() direkte plottbar (før: søppel-akser)."""
    if (isinstance(data, dict) and x is None and y is None
            and set(data.keys()) == {'index', 'values'}):
        return 'index', 'values'
    return x, y

def _hover_fields(hover_name_vals, hover_data_map, indices=None):
    """px-lik hover: hovertext = hover_name-kolonnen (fet tittel i tooltip),
    customdata = per-punkt-rader av hover_data-kolonnene, og hovertemplate
    som viser x/y + kolonnene. (Før: hoverinfo='name' SKJULTE x/y, og
    customdata var {kolonne: liste} — et format plotly.js ikke forstår.)"""
    out = {}
    extra = []
    if hover_name_vals:
        vals = hover_name_vals if indices is None else [hover_name_vals[i] for i in indices]
        out['hovertext'] = vals
    if hover_data_map:
        cols = [c for c in hover_data_map.keys() if hover_data_map[c] is not None]
        if cols:
            src = [hover_data_map[c] for c in cols]
            n = len(src[0])
            idxs = list(range(n)) if indices is None else indices
            out['customdata'] = [[s[i] for s in src] for i in idxs]
            for _ci, c in enumerate(cols):
                extra.append(str(c) + '=%{customdata[' + str(_ci) + ']}')
    if hover_name_vals or extra:
        tmpl = ('<b>%{hovertext}</b><br>' if hover_name_vals else '')
        tmpl += 'x=%{x}<br>y=%{y}'
        if extra:
            tmpl += '<br>' + '<br>'.join(extra)
        out['hovertemplate'] = tmpl + '<extra></extra>'
    return out

def _apply_axis_options(layout, log_x=False, log_y=False, range_x=None, range_y=None):
    """px-aliasene log_x/log_y/range_x/range_y → layout.(x|y)axis."""
    if log_x or range_x is not None:
        ax = layout.setdefault('xaxis', {})
        if log_x:
            ax['type'] = 'log'
        if range_x is not None:
            ax['range'] = list(range_x)
    if log_y or range_y is not None:
        ay = layout.setdefault('yaxis', {})
        if log_y:
            ay['type'] = 'log'
        if range_y is not None:
            ay['range'] = list(range_y)
    return layout

# Ensure all objects are JSON serializable (notably convert tuples to lists)
def json_safe(obj):
    import math
    import datetime
    # pandas_brython's NaN-sentinel -> null (før: TypeError ved serialisering,
    # som knakk plotting av ethvert datasett med manglende verdier)
    if type(obj).__name__ == 'NaN':
        return None
    # Tuples -> lists
    if isinstance(obj, tuple):
        return [json_safe(x) for x in obj]
    # Lists
    if isinstance(obj, list):
        return [json_safe(x) for x in obj]
    # Dicts
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    # Datetime objects -> strings
    if isinstance(obj, datetime.datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, datetime.date):
        return obj.strftime('%Y-%m-%d')
    if isinstance(obj, datetime.time):
        return obj.strftime('%H:%M:%S')
    # Numbers: sanitize NaN/inf
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj

def ensure_data_dict(data):
    """Return a dict-like data mapping for our px functions.
    - If data is already a dict, return it.
    - If it has to_dict(), use it (e.g., our pandas-like DataFrame/Series).
    - Otherwise, return data unchanged (functions must handle lists/None).
    """
    if isinstance(data, dict):
        return data
    if hasattr(data, 'to_dict'):
        try:
            return data.to_dict()
        except Exception:
            pass
    return data

# Default color sequences for plots
DEFAULT_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

class PlotlyFigure:
    """Basic Plotly figure wrapper that supports common methods"""
    
    def __init__(self, plot_data):
        """Initialize with plot data dictionary"""
        self.plot_data = plot_data
        self.data = plot_data.get('data', [])
        self.layout = plot_data.get('layout', {})
        self.config = plot_data.get('config', {})
        self.type = plot_data.get('type', 'plotly')
    
    @staticmethod
    def _expand_underscores(kwargs):
        """Plotly's underscore-magi: xaxis_title=... → {'xaxis': {'title': ...}}.
        (Før ble 'xaxis_title' lagt inn som ugyldig toppnivå-nøkkel.)"""
        out = {}
        for k, v in kwargs.items():
            parts = k.split('_')
            # Bare kjente containere ekspanderes; resten beholdes som-de-er
            if len(parts) > 1 and parts[0] in (
                    'xaxis', 'yaxis', 'legend', 'title', 'font', 'margin',
                    'coloraxis', 'hoverlabel', 'grid'):
                if parts[0] not in out:    # ikke setdefault — Brython-felle:
                    out[parts[0]] = {}      # AST-vakten godtar bare streng-litteral-nøkler
                node = out[parts[0]]
                node['_'.join(parts[1:])] = v
            else:
                out[k] = v
        return out

    def update_layout(self, **kwargs):
        """Update layout properties"""
        for k, v in self._expand_underscores(kwargs).items():
            if isinstance(v, dict) and isinstance(self.layout.get(k), dict):
                self.layout[k].update(v)
            else:
                self.layout[k] = v
        return self

    def update_traces(self, **kwargs):
        """Update trace properties for all traces"""
        expanded = {}
        for k, v in kwargs.items():
            parts = k.split('_')
            if len(parts) > 1 and parts[0] in ('marker', 'line', 'error'):
                if parts[0] not in expanded:
                    expanded[parts[0]] = {}
                expanded[parts[0]]['_'.join(parts[1:])] = v
            else:
                expanded[k] = v
        for trace in self.data:
            for k, v in expanded.items():
                if isinstance(v, dict) and isinstance(trace.get(k), dict):
                    trace[k].update(v)
                else:
                    trace[k] = v
        return self
    
    def add_trace(self, trace):
        """Add a new trace to the figure"""
        self.data.append(trace)
        return self
    
    def add_annotation(self, **kwargs):
        """Add an annotation to the layout"""
        if 'annotations' not in self.layout:
            self.layout['annotations'] = []
        self.layout['annotations'].append(kwargs)
        return self
    
    def add_shape(self, **kwargs):
        """Add a shape to the layout"""
        if 'shapes' not in self.layout:
            self.layout['shapes'] = []
        self.layout['shapes'].append(kwargs)
        return self
    
    def add_hline(self, y, **kwargs):
        """Add a horizontal line"""
        return self.add_shape(
            type="line",
            x0=0, x1=1, y0=y, y1=y,
            xref="paper", yref="y",
            **kwargs
        )
    
    def add_vline(self, x, **kwargs):
        """Add a vertical line"""
        return self.add_shape(
            type="line",
            x0=x, x1=x, y0=0, y1=1,
            xref="x", yref="paper",
            **kwargs
        )
    
    def show(self):
        """Display the figure (same as __str__)"""
        return str(self)
    
    def _build_plot_data(self):
        """Assemble the JSON-safe plot data dict (data/layout/config)."""
        # Norsk tallformat (pe.defaults.norsk): desimalkomma + hardt
        # mellomrom som tusenskiller, via plotly.js' layout.separators.
        if defaults.norsk and 'separators' not in self.layout:
            self.layout['separators'] = ', '
        # Add data attributes for CSS styling
        plot_data = {
            "type": self.type,
            "data": self.data,
            "layout": self.layout,
            "config": self.config
        }

        # Check if this is a faceted plot
        if 'grid' in self.layout and self.layout['grid']:
            grid = self.layout['grid']
            if 'rows' in grid and 'columns' in grid:
                plot_data['data-faceted'] = 'true'
                plot_data['data-rows'] = str(grid['rows'])
                plot_data['data-cols'] = str(grid['columns'])

        return plot_data

    def to_plotly_json_str(self):
        """Full figure spec as a JSON string (data/layout/config) for plotly.js."""
        return json.dumps(json_safe(self._build_plot_data()))

    def __str__(self):
        """Convert to web2 plot string"""
        return "<PlotlyFigure: use show() or leave as last expression>"

    def _repr_html_(self):
        """HTML representation for Jupyter notebooks"""
        return str(self)
    
    def __repr__(self):
        """Called when object is displayed in output cell - return plot string"""
        return str(self)
    
    def _show(self):
        """Brython-specific method for display"""
        return str(self)

# Module-wide sizing defaults (user-overridable)
class _Defaults:
    def __init__(self, height: int | None = 520, width: int | None = None, static: bool = False,
                 norsk: bool = False):
        # Global defaults used when function args are None
        self.height = height
        self.width = width
        # If True, plots render as non-interactive by default
        self.static = static
        # Norsk tallformat (desimalkomma, mellomrom som tusenskiller) —
        # `pe.defaults.norsk = True` gjelder alle figurer. Utover px, men
        # billig siden vi eier oversettelsen til plotly.js.
        self.norsk = norsk

defaults = _Defaults()
# Convenience alias to match suggested API (px.default.static)
default = defaults

# Dimension resolution removed - let CSS handle all sizing

def resolve_static(static: bool | None) -> bool:
    """Return static flag using module default when value is None."""
    return defaults.static if static is None else static

# Built-in templates for professional appearance
TEMPLATES = {
    'plotly': {
        'layout': {
            'template': 'plotly',
            'font': {'family': 'Arial, sans-serif'},
            'plot_bgcolor': 'white',
            'paper_bgcolor': 'white'
        }
    },
    'plotly_white': {
        'layout': {
            'template': 'plotly_white',
            'font': {'family': 'Arial, sans-serif'},
            'plot_bgcolor': 'white',
            'paper_bgcolor': 'white'
        }
    },
    'plotly_dark': {
        'layout': {
            'template': 'plotly_dark',
            'font': {'family': 'Arial, sans-serif'},
            'plot_bgcolor': '#242424',
            'paper_bgcolor': '#242424'
        }
    },
    'simple_white': {
        'layout': {
            'template': 'simple_white',
            'font': {'family': 'Arial, sans-serif'},
            'plot_bgcolor': 'white',
            'paper_bgcolor': 'white',
            'xaxis': {'showgrid': True, 'gridcolor': '#f0f0f0'},
            'yaxis': {'showgrid': True, 'gridcolor': '#f0f0f0'}
        }
    },
    'ggplot2': {
        'layout': {
            'template': 'ggplot2',
            'font': {'family': 'Arial, sans-serif'},
            'plot_bgcolor': '#f8f9fa',
            'paper_bgcolor': 'white'
        }
    }
}

def build_category_colors(categories, color_discrete_sequence=None, color_discrete_map=None):
    """Deterministisk {kategori: farge}: tildeling i kategorienes rekkefølge,
    som px. (Erstattet hash-basert tildeling 2026-07-10 — den ga kollisjoner,
    ignorerte sekvens-rekkefølgen og var ikke-deterministisk på tvers av
    CPython-økter pga. hash-randomisering.)"""
    seq = color_discrete_sequence or DEFAULT_COLORS
    colors = {}
    _next = 0
    for cat in categories:
        if color_discrete_map and cat in color_discrete_map:
            colors[cat] = color_discrete_map[cat]
        else:
            colors[cat] = seq[_next % len(seq)]
            _next += 1
    return colors

def get_color_for_category(category, color_discrete_sequence=None, color_discrete_map=None,
                           _colors=None):
    """Bakoverkompatibel wrapper: bruk build_category_colors() der hele
    kategorilisten er kjent; denne slår opp i et ferdig map når gitt,
    ellers faller den tilbake til første farge (aldri hash)."""
    if _colors and category in _colors:
        return _colors[category]
    if color_discrete_map and category in color_discrete_map:
        return color_discrete_map[category]
    seq = color_discrete_sequence or DEFAULT_COLORS
    return seq[0]

def is_continuous_color(color_data):
    """Check if color data is continuous (numeric)"""
    if not color_data:
        return False
    try:
        # Try to convert first few values to float
        for val in color_data[:10]:  # Check first 10 values
            if val is not None:
                float(val)
        return True
    except (ValueError, TypeError):
        return False

def format_column_name(column_name):
    """Convert column name to readable axis label (Plotly Express style)"""
    if not column_name:
        return None
    
    # Convert snake_case to Title Case
    import re
    # Split on underscores and capitalize each word
    words = re.split(r'[_\-]', str(column_name))
    formatted = ' '.join(word.capitalize() for word in words if word)
    
    return formatted

def create_faceted_layout(facet_row=None, facet_col=None, facet_col_wrap=None, title=None, height=None, width=None, labels=None, template=None, data=None, x_col=None, y_col=None):
    """Create layout for faceted plots"""
    layout = {}
    
    _wrapped = False
    if facet_row or facet_col:
        # Get unique values for faceting
        if facet_row:
            row_values = _unique_ordered(data.get(facet_row) if data else [], sort=False)
            n_rows = len(row_values)
        else:
            n_rows = 1

        if facet_col:
            col_values = _unique_ordered(data.get(facet_col) if data else [], sort=False)
            if facet_col_wrap:
                n_cols = min(facet_col_wrap, len(col_values))
                if not facet_row and len(col_values) > n_cols:
                    # facet_col_wrap: panelene fordeles på flere rader
                    # (før: alle paneler i én rad med akser plotly.js ikke
                    # fant → paneler oppå hverandre).
                    n_rows = -(-len(col_values) // n_cols)
                    _wrapped = True
            else:
                n_cols = len(col_values)
        else:
            n_cols = 1
        
        # Calculate global data ranges for consistent axis scaling
        if data and x_col and y_col:
            x_data = data.get(x_col, [])
            y_data = data.get(y_col, [])
            if x_data and y_data:
                # Check if data is numeric for range calculations
                try:
                    # Try to convert to numeric for range calculation
                    x_numeric = [float(x) if isinstance(x, (int, float)) else None for x in x_data]
                    y_numeric = [float(y) if isinstance(y, (int, float)) else None for y in y_data]
                    
                    # Filter out None values (non-numeric data)
                    x_numeric = [x for x in x_numeric if x is not None]
                    y_numeric = [y for y in y_numeric if y is not None]
                    
                    if x_numeric and y_numeric:
                        x_min, x_max = min(x_numeric), max(x_numeric)
                        y_min, y_max = min(y_numeric), max(y_numeric)
                        # Add small padding to ranges
                        x_padding = (x_max - x_min) * 0.05
                        y_padding = (y_max - y_min) * 0.05
                        x_range = [x_min - x_padding, x_max + x_padding]
                        y_range = [y_min - y_padding, y_max + y_padding]
                    else:
                        x_range = None
                        y_range = None
                except (ValueError, TypeError):
                    # If conversion fails, don't set ranges (let Plotly auto-scale)
                    x_range = None
                    y_range = None
            else:
                x_range = None
                y_range = None
        else:
            x_range = None
            y_range = None
        
        # Set subplot layout - this is the key for actual subplots
        layout['grid'] = {
            'rows': n_rows,
            'columns': n_cols,
            'pattern': 'independent'
        }

        # Proporsjonal padding: fast 0.05 ga inverterte domener
        # ([0.05, 0.033]) når panelbredden ble mindre enn 0.1 (≥10 paneler).
        pad_c = min(0.05, 0.35 / n_cols)
        pad_r = min(0.05, 0.35 / n_rows)

        def _col_domain(col_idx):
            return [col_idx / n_cols + pad_c, (col_idx + 1) / n_cols - pad_c]

        def _row_domain(row_idx):
            return [1 - (row_idx + 1) / n_rows + pad_r, 1 - row_idx / n_rows - pad_r]

        # Create subplot axes for each facet. Ved wrap får hvert panel både
        # x- og y-akse (flere rader trenger egne y-akser).
        both_axes = (n_rows > 1 and n_cols > 1)
        n_panels = (len(col_values) if _wrapped
                    else n_rows * n_cols if both_axes
                    else max(n_rows, n_cols))
        for panel in range(1, n_panels + 1):
            if n_rows <= 1 and n_cols <= 1:
                break
            row_idx = (panel - 1) // n_cols if (both_axes or _wrapped) else 0
            col_idx = (panel - 1) % n_cols if (both_axes or _wrapped or n_cols > 1) else 0
            if both_axes or _wrapped:
                layout[f'xaxis{panel}'] = {
                    'domain': _col_domain(col_idx),
                    'anchor': f'y{panel}',
                    'title': labels.get(x_col, '') if labels and x_col else None,
                    'showgrid': True,
                    'zeroline': False,
                    'range': x_range
                }
                layout[f'yaxis{panel}'] = {
                    'domain': _row_domain(row_idx),
                    'anchor': f'x{panel}',
                    'title': labels.get(y_col, '') if labels and y_col else None,
                    'showgrid': True,
                    'zeroline': False,
                    'range': y_range
                }
            elif n_rows > 1:
                # Only row faceting
                layout[f'yaxis{panel}'] = {
                    'domain': _row_domain(panel - 1),
                    'anchor': 'x',
                    'title': labels.get(y_col, '') if labels and y_col else None,
                    'showgrid': True,
                    'zeroline': False,
                    'range': y_range
                }
            else:
                # Only column faceting (typo-fiks 2026-07-10: betingelsen
                # sjekket y_col for x-aksens tittel)
                layout[f'xaxis{panel}'] = {
                    'domain': _col_domain(panel - 1),
                    'anchor': 'y',
                    'title': labels.get(x_col, '') if labels and x_col else None,
                    'showgrid': True,
                    'zeroline': False,
                    'range': x_range
                }
        
        # Let CSS handle all sizing - no dimension calculations needed
        # CSS will set appropriate heights based on data-faceted attribute
    
    # Add axis labels - either from explicit labels or auto-generate from column names
    x_label = None
    y_label = None
    color_label = None
    
    if labels and isinstance(labels, dict):
        # Handle explicit labels parameter
        # Check for generic x/y keys first
        if 'x' in labels:
            x_label = labels['x']
        if 'y' in labels:
            y_label = labels['y']
        if 'color' in labels:
            color_label = labels['color']
        
        # If no generic keys found, try to infer from data column names
        # Use the actual x and y column names if provided
        if x_label is None and x_col and x_col in labels:
            x_label = labels[x_col]
        elif x_label is None and data is not None:
            # Fallback: look for the first non-color/size/text column
            for key, value in labels.items():
                if key in data and key not in ['color', 'size', 'text', 'hover_name', 'hover_data']:
                    x_label = value
                    break
        
        if y_label is None and y_col and y_col in labels:
            y_label = labels[y_col]
        elif y_label is None and data is not None:
            # Fallback: look for the second non-color/size/text column
            found_x = False
            for key, value in labels.items():
                if key in data and key not in ['color', 'size', 'text', 'hover_name', 'hover_data']:
                    if not found_x:
                        found_x = True
                    else:
                        y_label = value
                        break
    else:
        # Auto-generate axis labels from column names (Plotly Express default behavior)
        if x_col:
            x_label = format_column_name(x_col)
        if y_col:
            y_label = format_column_name(y_col)
    
    # Apply the labels
    if x_label:
        layout['xaxis'] = {'title': x_label}
    if y_label:
        layout['yaxis'] = {'title': y_label}
    if color_label:
        layout['coloraxis'] = {'title': color_label}
    
    # For faceted plots, apply labels to all subplot axes
    if facet_row or facet_col:
        # Use the same auto-generation logic for faceted plots
        if labels and isinstance(labels, dict):
            # Apply explicit labels to all subplot axes
            if 'x' in labels:
                layout['xaxis'] = {'title': labels['x']}
            elif data is not None:
                # Try to find x label from column names
                for key, value in labels.items():
                    if key in data and key != 'color' and key != 'size' and key != 'text':
                        layout['xaxis'] = {'title': value}
                        break
                        
            if 'y' in labels:
                layout['yaxis'] = {'title': labels['y']}
            elif data is not None:
                # Try to find y label from column names
                found_x = False
                for key, value in labels.items():
                    if key in data and key != 'color' and key != 'size' and key != 'text':
                        if not found_x:
                            found_x = True
                        else:
                            layout['yaxis'] = {'title': value}
                            break
        else:
            # Auto-generate axis labels for faceted plots too
            if x_col:
                layout['xaxis'] = {'title': format_column_name(x_col)}
            if y_col:
                layout['yaxis'] = {'title': format_column_name(y_col)}
    
    # Apply template if specified
    if template and template in TEMPLATES:
        template_layout = TEMPLATES[template]['layout']
        layout.update(template_layout)
    
    layout.update({
        'title': title,
        'height': height,
        'width': width
    })
    
    return layout

def create_marginal_traces(data, x, y, marginal_x=None, marginal_y=None, color=None, 
                          color_discrete_sequence=None, color_discrete_map=None):
    """Create marginal plot traces (histogram, box, violin, or rug)"""
    marginal_traces = []
    
    if marginal_x:
        if marginal_x == 'histogram':
            trace = {
                "type": "histogram",
                "x": data.get(x),
                "yaxis": "y2",
                "xaxis": "x2",
                "showlegend": False,
                "marker": {"color": "rgba(0,0,0,0.3)"}
            }
            marginal_traces.append(trace)
        elif marginal_x == 'box':
            trace = {
                "type": "box",
                "x": data.get(x),
                "yaxis": "y2",
                "xaxis": "x2",
                "showlegend": False,
                "marker": {"color": "rgba(0,0,0,0.3)"}
            }
            marginal_traces.append(trace)
        elif marginal_x == 'violin':
            trace = {
                "type": "violin",
                "x": data.get(x),
                "yaxis": "y2",
                "xaxis": "x2",
                "showlegend": False,
                "marker": {"color": "rgba(0,0,0,0.3)"}
            }
            marginal_traces.append(trace)
        elif marginal_x == 'rug':
            trace = {
                "type": "scatter",
                "x": data.get(x),
                "y": [0] * len(data.get(x)),
                "mode": "markers",
                "marker": {"size": 2, "color": "rgba(0,0,0,0.3)"},
                "yaxis": "y2",
                "xaxis": "x2",
                "showlegend": False
            }
            marginal_traces.append(trace)
    
    if marginal_y:
        if marginal_y == 'histogram':
            trace = {
                "type": "histogram",
                "y": data.get(y),
                "xaxis": "x3",
                "yaxis": "y3",
                "showlegend": False,
                "marker": {"color": "rgba(0,0,0,0.3)"}
            }
            marginal_traces.append(trace)
        elif marginal_y == 'box':
            trace = {
                "type": "box",
                "y": data.get(y),
                "xaxis": "x3",
                "yaxis": "y3",
                "showlegend": False,
                "marker": {"color": "rgba(0,0,0,0.3)"}
            }
            marginal_traces.append(trace)
        elif marginal_y == 'violin':
            trace = {
                "type": "violin",
                "y": data.get(y),
                "xaxis": "x3",
                "yaxis": "y3",
                "showlegend": False,
                "marker": {"color": "rgba(0,0,0,0.3)"}
            }
            marginal_traces.append(trace)
        elif marginal_y == 'rug':
            trace = {
                "type": "scatter",
                "y": data.get(y),
                "x": [0] * len(data.get(y)),
                "mode": "markers",
                "marker": {"size": 2, "color": "rgba(0,0,0,0.3)"},
                "xaxis": "x3",
                "yaxis": "y3",
                "showlegend": False
            }
            marginal_traces.append(trace)
    
    return marginal_traces

def create_marginal_layout(marginal_x=None, marginal_y=None, height=None, width=None):
    """Create layout for plots with marginal distributions"""
    layout = {}
    
    if marginal_x or marginal_y:
        # Let CSS handle all sizing - no dimension calculations needed
        
        # Set up secondary axes for marginal plots
        if marginal_x:
            # Marginal x-axis (above main plot)
            layout['xaxis2'] = {
                'domain': [0, 0.85],  # Same width as main plot
                'position': 0.85,      # Position above main plot
                'showticklabels': False,
                'showgrid': False,
                'anchor': 'y2'
            }
            layout['yaxis2'] = {
                'domain': [0.85, 1],  # Above main plot
                'showticklabels': False,
                'showgrid': False,
                'anchor': 'x2'
            }
        
        if marginal_y:
            # Marginal y-axis (right of main plot)
            layout['xaxis3'] = {
                'domain': [0.85, 1],  # Right of main plot
                'showticklabels': False,
                'showgrid': False,
                'anchor': 'y3'
            }
            layout['yaxis3'] = {
                'domain': [0, 0.85],  # Same height as main plot
                'showticklabels': False,
                'showgrid': False,
                'anchor': 'x3'
            }
        
        # Adjust main plot domain to make room for marginals
        layout['xaxis'] = {'domain': [0, 0.85]}
        layout['yaxis'] = {'domain': [0, 0.85]}
    
    layout.update({
        'height': height,
        'width': width
    })
    
    return layout

def generate_traces(data, chart_type, x, y, color, text, hover_name, hover_data, title, height, width,
                   color_discrete_sequence=None, color_discrete_map=None,
                   # Enhanced axis customization
                   xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):
    traces = []
    layout = {}
    if data is not None:
        data = ensure_data_dict(data)

    x_data = data.get(x)
    y_data = data.get(y)
    color_data = data.get(color)
    _cat_colors = build_category_colors(_unique_ordered(color_data or [], sort=False), color_discrete_sequence, color_discrete_map)
    text_data = data.get(text)
    hover_name_data = data.get(hover_name)
    hover_data_dict = {k: data.get(k) for k in hover_data or []}

    if color_data is None or isinstance(color_data, str):
        trace = remove_none({
            "type": chart_type,
            "x": x_data,
            "y": y_data,
            "marker": {"color": color_data} if color_data else None,
            "text": text_data,
            **_hover_fields(hover_name_data, hover_data_dict)
        })
        traces.append(trace)
    else:
        color_categories = _unique_ordered(color_data, sort=False)
        for color_val in color_categories:
            filtered_indices = [i for i, c in enumerate(color_data) if c == color_val]
            filtered_x = [x_data[i] for i in filtered_indices]
            filtered_y = [y_data[i] for i in filtered_indices]
            filtered_text = [text_data[i] for i in filtered_indices] if text_data else None
            filtered_hover_name = [hover_name_data[i] for i in filtered_indices] if hover_name_data else None
            filtered_hover_data = {k: [v[i] for i in filtered_indices] for k, v in hover_data_dict.items()} if hover_data_dict else None

            # Get color for this category
            category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])

            trace = remove_none({
                "type": chart_type,
                "x": filtered_x,
                "y": filtered_y,
                "name": str(color_val),
                "marker": {"color": category_color},
                "text": filtered_text,
                **_hover_fields(filtered_hover_name, filtered_hover_data)
            })
            traces.append(trace)

    # Let CSS handle all sizing - no dimension calculations needed
    layout = remove_none({
        "title": title,
    })

    # Auto-generate axis labels from column names (Plotly Express default behavior)
    if x and not xaxis_title:
        layout['xaxis'] = {'title': format_column_name(x)}
    if y and not yaxis_title:
        layout['yaxis'] = {'title': format_column_name(y)}

    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range

    return traces, layout

def area(data, x=None, y=None, color=None, text=None, hover_name=None, hover_data=None,
         title=None, height=None, width=None, config=None, static=None,
         # Enhanced axis customization
         xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):

    traces = []
    layout = {}
    data = ensure_data_dict(data)
    x, y = _series_xy(data, x, y)
    
    x_data = data.get(x)

    if isinstance(y, list):
        for y_col in y:
            y_data = data.get(y_col)
            trace = remove_none({
                "type": "scatter",
                "mode": "lines+markers",
                "stackgroup": "one",  # this line is the key to stacking
                "x": x_data,
                "y": y_data,
                "name": y_col,
                "text": data.get(text),
                "hoverinfo": "name" if hover_name else None,
                "customdata": {k: data.get(k) for k in hover_data or []}
            })
            traces.append(trace)
    else:
        y_data = data.get(y)
        trace = remove_none({
            "type": "scatter",
            "mode": "lines+markers",
            "x": x_data,
            "y": y_data,
            "marker": {"color": color} if color else None,
            "text": data.get(text),
            "hoverinfo": "name" if hover_name else None,
            "customdata": {k: data.get(k) for k in hover_data or []}
        })
        traces.append(trace)

    # Let CSS handle all sizing - no dimension calculations needed
    layout = remove_none({
        "title": title,
    })

    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range

    # Return JSON string with special prefix for JavaScript detection
    import json
    # Clean None values from layout/config to avoid explicit nulls overriding Plotly defaults
    clean_layout = remove_none(layout)
    clean_config = remove_none(config or {})
    if resolve_static(static):
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": clean_layout,
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def bar(data, x=None, y=None, color=None, text=None, hover_name=None, hover_data=None,
        title=None, height=None, width=None, barmode=None, color_discrete_sequence=None, color_discrete_map=None,
        color_continuous_scale=None, color_continuous_midpoint=None,
        facet_row=None, facet_col=None, facet_col_wrap=None, labels=None, template=None, config=None, static=None,
        orientation=None,
        text_auto=False, opacity=None, log_x=False, log_y=False,
        range_x=None, range_y=None, category_orders=None,
        # Enhanced axis customization
        xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):

    traces = []
    layout = {}
    data = ensure_data_dict(data)
    x, y = _series_xy(data, x, y)
    if x is None and isinstance(data, dict):
        x_data=list(data.keys())
        # For wide-form detection, y may be a list; don't fetch here to avoid unhashable errors
        y_data=None if isinstance(y, list) else list(data.values())
        
    elif isinstance(data, list):
        data_dict, x_col, y_col = data2dict(data)
        data = data_dict
        x = x_col
        y = y_col
        x_data = data.get(x)
        y_data = data.get(y)
    else:
        x_data = data.get(x)
        if isinstance(y, list):
            y_data = None
        else:
            # (Før: data.get(y, data) — manglende y ga hele data-dicten som
            # y-verdier. Nå None, som gir tydelig tom trace i stedet.)
            y_data = data.get(y)

    color_data = data.get(color)
    _cat_colors = build_category_colors(
        _apply_category_order(_unique_ordered(color_data or [], sort=False), category_orders, color),
        color_discrete_sequence, color_discrete_map)
    text_data = data.get(text)
    hover_name_data = data.get(hover_name)
    hover_data_dict = {k: data.get(k) for k in hover_data or []}

    # Handle faceting with proper subplot assignment
    if facet_row or facet_col:
        # Get unique values for faceting
        if facet_row:
            row_values = data.get(facet_row)
            unique_rows = _unique_ordered(row_values, sort=False)
            n_rows = len(unique_rows)
        else:
            n_rows = 1
            
        if facet_col:
            col_values = data.get(facet_col)
            unique_cols = _unique_ordered(col_values, sort=False)
            if facet_col_wrap:
                n_cols = min(facet_col_wrap, len(unique_cols))
                if not facet_row and len(unique_cols) > n_cols:
                    # wrap: paneler over flere rader (matcher layouten)
                    n_rows = -(-len(unique_cols) // n_cols)
            else:
                n_cols = len(unique_cols)
        else:
            n_cols = 1
        
        # Create traces for each facet
        subplot_idx = 1
        for row_idx, row_val in enumerate(unique_rows if facet_row else [None]):
            for col_idx, col_val in enumerate(unique_cols if facet_col else [None]):
                # Determine which data belongs to this facet
                if facet_row and facet_col:
                    # Both row and column faceting
                    indices = [i for i, (r, c) in enumerate(zip(row_values, col_values)) if r == row_val and c == col_val]
                    facet_name = f"{row_val}-{col_val}"
                elif facet_row:
                    # Only row faceting
                    indices = [i for i, v in enumerate(row_values) if v == row_val]
                    facet_name = f"Row: {row_val}"
                elif facet_col:
                    # Only column faceting
                    indices = [i for i, v in enumerate(col_values) if v == col_val]
                    facet_name = f"Column: {col_val}"
                else:
                    indices = list(range(len(x_data)))
                    facet_name = "main"
                
                if indices:
                    facet_x = [x_data[i] for i in indices]
                    facet_y = [y_data[i] for i in indices]
                    facet_color = [color_data[i] for i in indices] if color_data else None
                    
                    if facet_color is None or isinstance(facet_color, str):
                        # Handle continuous color scale
                        marker_config = {}
                        if facet_color:
                            marker_config["color"] = facet_color
                        elif color_continuous_scale and is_continuous_color(facet_color):
                            marker_config["color"] = facet_color
                            marker_config["colorscale"] = color_continuous_scale
                            if color_continuous_midpoint is not None:
                                marker_config["cmid"] = color_continuous_midpoint
                        
                        trace = remove_none({
                            "type": "bar",
                            "x": facet_x if (orientation is None or orientation == 'v') else facet_y,
                            "y": facet_y if (orientation is None or orientation == 'v') else facet_x,
                            "orientation": orientation,
                            "name": facet_name,
                            "marker": marker_config if marker_config else None,
                            "text": [text_data[i] for i in indices] if text_data else None,
                            **_hover_fields(hover_name_data, hover_data_dict, indices)
                        })
                        
                        # Assign to subplot if faceting
                        if n_rows > 1 or n_cols > 1:
                            if n_rows > 1 and n_cols > 1:
                                trace["xaxis"] = f"x{subplot_idx}"
                                trace["yaxis"] = f"y{subplot_idx}"
                            elif n_rows > 1:
                                trace["yaxis"] = f"y{subplot_idx}"
                            elif n_cols > 1:
                                trace["xaxis"] = f"x{subplot_idx}"
                        
                        traces.append(trace)
                    else:
                        # Handle color within facet
                        color_categories = _unique_ordered(facet_color, sort=False)
                        for color_val in color_categories:
                            color_indices = [i for i, c in enumerate(facet_color) if c == color_val]
                            color_x = [facet_x[i] for i in color_indices]
                            color_y = [facet_y[i] for i in color_indices]
                            
                            category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])
                            
                            trace = remove_none({
                                "type": "bar",
                                "x": color_x if (orientation is None or orientation == 'v') else color_y,
                                "y": color_y if (orientation is None or orientation == 'v') else color_x,
                                "orientation": orientation,
                                "name": f"{facet_name}-{color_val}",
                                "marker": {"color": category_color},
                                "text": [text_data[i] for i in [indices[j] for j in color_indices]] if text_data else None,
                                "hoverinfo": "name" if hover_name_data else None,
                                "customdata": {k: [v[i] for i in [indices[j] for j in color_indices]] for k, v in hover_data_dict.items()} if hover_data_dict else None
                            })
                            
                            # Assign to subplot if faceting - use same subplot index for all colors within a facet
                            if n_rows > 1 or n_cols > 1:
                                if n_rows > 1 and n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_rows > 1:
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"
                            
                            traces.append(trace)
                            # Don't increment subplot_idx here - all colors within a facet use the same subplot
                # Panel-telleren følger rutenett-cellen, ikke om cellen
                # har data (fikset 2026-07-10 — manglende kombinasjoner
                # forskjøv alle etterfølgende paneler).
                subplot_idx += 1
    else:
        # No faceting - original logic
        multiple_traces = False
        if isinstance(y, list):
            # Wide-form: create one trace per y column
            for y_col in y:
                y_col_data = data.get(y_col)
                trace = remove_none({
                    "type": "bar",
                    "x": x_data if (orientation is None or orientation == 'v') else y_col_data,
                    "y": y_col_data if (orientation is None or orientation == 'v') else x_data,
                    "orientation": orientation,
                    "name": str(y_col)
                })
                traces.append(trace)
            multiple_traces = len(y) > 1
        elif color_data is None or isinstance(color_data, str):
            # Handle continuous color scale
            marker_config = {}
            if color_data:
                marker_config["color"] = color_data
            elif color_continuous_scale and is_continuous_color(color_data):
                marker_config["color"] = color_data
                marker_config["colorscale"] = color_continuous_scale
                if color_continuous_midpoint is not None:
                    marker_config["cmid"] = color_continuous_midpoint
            
            trace = remove_none({
                "type": "bar",
                "x": x_data if (orientation is None or orientation == 'v') else y_data,
                "y": y_data if (orientation is None or orientation == 'v') else x_data,
                "orientation": orientation,
                "marker": marker_config if marker_config else None,
                "text": text_data,
                **_hover_fields(hover_name_data, hover_data_dict)
            })
            traces.append(trace)
        else:
            color_categories = _unique_ordered(color_data, sort=False)
            for color_val in color_categories:
                filtered_indices = [i for i, c in enumerate(color_data) if c == color_val]
                filtered_x = [x_data[i] for i in filtered_indices]
                filtered_y = [y_data[i] for i in filtered_indices]
                filtered_text = [text_data[i] for i in filtered_indices] if text_data else None
                filtered_hover_name = [hover_name_data[i] for i in filtered_indices] if hover_name_data else None
                filtered_hover_data = {k: [v[i] for i in filtered_indices] for k, v in hover_data_dict.items()} if hover_data_dict else None

                # Get color for this category
                category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])

                trace = remove_none({
                    "type": "bar",
                    "x": filtered_x if (orientation is None or orientation == 'v') else filtered_y,
                    "y": filtered_y if (orientation is None or orientation == 'v') else filtered_x,
                    "orientation": orientation,
                    "name": str(color_val),
                    "marker": {"color": category_color},
                    "text": filtered_text,
                    **_hover_fields(filtered_hover_name, filtered_hover_data)
                })
                traces.append(trace)
            multiple_traces = len(color_categories) > 1

    # Create layout with faceting support
    layout = create_faceted_layout(facet_row, facet_col, facet_col_wrap, title, height, width, labels, template, data, x, y)
    layout = _apply_axis_options(layout, log_x, log_y, range_x, range_y)
    # px-argumenter som gjelder alle bar-traces (2026-07-10)
    if opacity is not None:
        for _tr in traces:
            _tr['opacity'] = opacity
    if text_auto:
        for _tr in traces:
            _tr['texttemplate'] = '%{x}' if orientation == 'h' else '%{y}'
            _tr['textposition'] = 'auto'
    
    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range
    
    # Add bar-specific layout options
    if barmode:
        layout['barmode'] = barmode
    else:
        # Default to stacked when multiple traces present (PX-like behavior)
        if 'barmode' not in layout and len(traces) > 1:
            layout['barmode'] = 'relative'
    layout['autosize'] = True
    layout['hovermode'] = 'closest'
    
    # Return PlotlyFigure object
    import json
    clean_layout = remove_none(layout)
    clean_config = remove_none(config or {})
    if resolve_static(static):
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": clean_layout,
        "config": clean_config
    }
    return PlotlyFigure(plot_data)
    
def box(data, x=None, y=None, color=None, text=None, hover_name=None, hover_data=None,
        title=None, height=None, width=None, color_discrete_sequence=None, color_discrete_map=None, config=None, static=None,
        points=None, log_x=False, log_y=False, range_x=None, range_y=None,
        # Enhanced axis customization
        xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):

    data = ensure_data_dict(data)
    traces, layout = generate_traces(
        data, "box", x, y, color, text, hover_name, hover_data, title, height, width,
        color_discrete_sequence, color_discrete_map,
        xaxis_title, yaxis_title, xaxis_range, yaxis_range)
    # px setter boxmode='group' ved x+color — plotly.js-defaulten gir
    # overlappende bokser (fikset 2026-07-10).
    if x is not None and color is not None and len(traces) > 1:
        layout['boxmode'] = 'group'
    if points is not None:
        for _tr in traces:
            _tr['boxpoints'] = points if points is not False else False
    layout = _apply_axis_options(layout, log_x, log_y, range_x, range_y)

    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_layout = remove_none(layout)
    clean_config = remove_none(config or {})
    if resolve_static(static):
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": clean_layout,
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def choropleth(data, lat=None, lon=None, locations=None, locationmode='country names', 
               geojson=None, featureidkey="id", color=None, 
               title='Choropleth Map', labels=None, 
               color_continuous_scale='Viridis', range_color=None, 
               projection='mercator', scope='world', center=None, 
               fitbounds=None, basemap_visible=True, width=800, height=600, config=None, static=None,
               # Enhanced axis customization
               xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):
    
    data = ensure_data_dict(data)
    traces = []
    
    locations_data = list(data.get(locations, []))
    lat_data = list(data.get(lat, []))
    lon_data = list(data.get(lon, []))
    color_data = list(data.get(color, []))

    trace = remove_none({
        "type": "choropleth",
        "lat": lat_data if lat_data else None,
        "lon": lon_data if lon_data else None,
        "locations": locations_data if locations_data else None,
        "locationmode": locationmode,
        "geojson": geojson,
        "featureidkey": featureidkey,
        "z": color_data if color_data else None,
        "colorscale": color_continuous_scale,
        "zmin": range_color[0] if range_color else None,
        "zmax": range_color[1] if range_color else None,
        "name": labels if isinstance(labels, str) else None
    })

    traces.append(trace)

    # Let CSS handle all sizing - no dimension calculations needed
    layout = remove_none({
        "title": title,
        "geo": remove_none({
            "scope": scope,
            "projection": {"type": projection} if projection else None,
            "center": center,
            "fitbounds": fitbounds,
            "showland": basemap_visible
        })
    })

    # Enhanced axis customization for geographic plots
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range
    
    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_layout = remove_none(layout)
    clean_config = remove_none(config or {})
    if resolve_static(static):
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": clean_layout,
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def histogram(data, x=None, y=None, color=None, text=None, hover_name=None, hover_data=None,
        title=None, height=None, width=None, color_discrete_sequence=None, color_discrete_map=None, 
        facet_row=None, facet_col=None, facet_col_wrap=None, labels=None, template=None, config=None, static=None,
        histnorm=None, orientation=None, nbins=None, n_bins=None,
        # Enhanced axis customization
        xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):

    traces = []
    layout = {}
    data = ensure_data_dict(data)

    x_data = data.get(x)
    y_data = data.get(y) if y else None  # Make sure to handle y=None case
    color_data = data.get(color)
    _cat_colors = build_category_colors(_unique_ordered(color_data or [], sort=False), color_discrete_sequence, color_discrete_map)
    text_data = data.get(text)
    hover_name_data = data.get(hover_name)
    hover_data_dict = {k: data.get(k) for k in hover_data or []}

    # Handle faceting with proper subplot assignment
    if facet_row or facet_col:
        # Get unique values for faceting
        if facet_row:
            row_values = data.get(facet_row)
            unique_rows = _unique_ordered(row_values, sort=False)
            n_rows = len(unique_rows)
        else:
            n_rows = 1
            
        if facet_col:
            col_values = data.get(facet_col)
            unique_cols = _unique_ordered(col_values, sort=False)
            if facet_col_wrap:
                n_cols = min(facet_col_wrap, len(unique_cols))
                if not facet_row and len(unique_cols) > n_cols:
                    # wrap: paneler over flere rader (matcher layouten)
                    n_rows = -(-len(unique_cols) // n_cols)
            else:
                n_cols = len(unique_cols)
        else:
            n_cols = 1
        
        # Create traces for each facet
        subplot_idx = 1
        for row_idx, row_val in enumerate(unique_rows if facet_row else [None]):
            for col_idx, col_val in enumerate(unique_cols if facet_col else [None]):
                # Determine which data belongs to this facet
                if facet_row and facet_col:
                    # Both row and column faceting
                    indices = [i for i, (r, c) in enumerate(zip(row_values, col_values)) if r == row_val and c == col_val]
                    facet_name = f"{row_val}-{col_val}"
                elif facet_row:
                    # Only row faceting
                    indices = [i for i, v in enumerate(row_values) if v == row_val]
                    facet_name = f"Row: {row_val}"
                elif facet_col:
                    # Only column faceting
                    indices = [i for i, v in enumerate(col_values) if v == col_val]
                    facet_name = f"Column: {col_val}"
                else:
                    indices = list(range(len(x_data)))
                    facet_name = "main"
                
                if indices:
                    facet_x = [x_data[i] for i in indices]
                    facet_y = [y_data[i] for i in indices] if y_data else None
                    facet_color = [color_data[i] for i in indices] if color_data else None
                    
                    if facet_color is None or isinstance(facet_color, str):
                        bins_param = nbins if nbins is not None else n_bins
                        trace = remove_none({
                            "type": "histogram",
                            "x": facet_x if (orientation is None or orientation == 'v') else facet_y,
                            "y": facet_y if (orientation is None or orientation == 'v') else facet_x,
                            "orientation": orientation,
                            "histnorm": histnorm,
                            "nbinsx": bins_param if (orientation is None or orientation == 'v') else None,
                            "nbinsy": bins_param if orientation == 'h' else None,
                            "name": facet_name,
                            "marker": {"color": facet_color if facet_color else None},
                            "text": [text_data[i] for i in indices] if text_data else None,
                            **_hover_fields(hover_name_data, hover_data_dict, indices)
                        })

                        # Assign to subplot if faceting
                        if n_rows > 1 or n_cols > 1:
                            if n_rows > 1 and n_cols > 1:
                                trace["xaxis"] = f"x{subplot_idx}"
                                trace["yaxis"] = f"y{subplot_idx}"
                            elif n_rows > 1:
                                trace["yaxis"] = f"y{subplot_idx}"
                            elif n_cols > 1:
                                trace["xaxis"] = f"x{subplot_idx}"

                        traces.append(trace)
                    else:
                        # Handle color within facet
                        color_categories = _unique_ordered(facet_color, sort=False)
                        for color_val in color_categories:
                            color_indices = [i for i, c in enumerate(facet_color) if c == color_val]
                            color_x = [facet_x[i] for i in color_indices]
                            color_y = [facet_y[i] for i in color_indices] if facet_y else None
                            
                            category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])
                            
                            # Handle nbins parameter (use n_bins if nbins is provided)
                            bins_param = nbins if nbins is not None else n_bins
                            
                            trace = remove_none({
                                "type": "histogram",
                                "x": color_x if (orientation is None or orientation == 'v') else color_y,
                                "y": color_y if (orientation is None or orientation == 'v') else color_x,
                                "orientation": orientation,
                                "histnorm": histnorm,
                                "nbinsx": bins_param if (orientation is None or orientation == 'v') else None,
                                "nbinsy": bins_param if orientation == 'h' else None,
                                "name": f"{facet_name}-{color_val}",
                                "marker": {"color": category_color},
                                "text": [text_data[i] for i in [indices[j] for j in color_indices]] if text_data else None,
                                "hoverinfo": "name" if hover_name_data else None,
                                "customdata": {k: [v[i] for i in [indices[j] for j in color_indices]] for k, v in hover_data_dict.items()} if hover_data_dict else None
                            })
                            
                            # Assign to subplot if faceting - use same subplot index for all colors within a facet
                            if n_rows > 1 or n_cols > 1:
                                if n_rows > 1 and n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_rows > 1:
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"
                            
                            traces.append(trace)
                            # Don't increment subplot_idx here - all colors within a facet use the same subplot
                # Panel-telleren følger rutenett-cellen, ikke om cellen har
                # data (fikset 2026-07-10 — manglende kombinasjoner forskjøv
                # alle etterfølgende paneler).
                subplot_idx += 1
    else:
        # No faceting - original logic
        if color_data is None or isinstance(color_data, str):
            # Single color case
            # Handle nbins parameter (use n_bins if nbins is provided)
            bins_param = nbins if nbins is not None else n_bins

            trace = remove_none({
                "type": "histogram",
                "x": x_data if (orientation is None or orientation == 'v') else y_data,
                "y": y_data if (orientation is None or orientation == 'v') else x_data,  # y None unless specified
                "orientation": orientation,
                "histnorm": histnorm,
                "nbinsx": bins_param if (orientation is None or orientation == 'v') else None,
                "nbinsy": bins_param if orientation == 'h' else None,
                "marker": {"color": color_data} if color_data else None,
                "text": text_data,
                **_hover_fields(hover_name_data, hover_data_dict)
            })
            traces.append(trace)
        else:
            # Multiple colors case - split data by color categories
            color_categories = _unique_ordered(color_data, sort=False)
            for color_val in color_categories:
                filtered_indices = [i for i, c in enumerate(color_data) if c == color_val]
                filtered_x = [x_data[i] for i in filtered_indices]
                filtered_y = [y_data[i] for i in filtered_indices] if y_data else None
                filtered_text = [text_data[i] for i in filtered_indices] if text_data else None
                filtered_hover_name = [hover_name_data[i] for i in filtered_indices] if hover_name_data else None
                filtered_hover_data = {k: [v[i] for i in filtered_indices] for k, v in hover_data_dict.items()} if hover_data_dict else None

                # Get color for this category
                category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])

                # Handle nbins parameter (use n_bins if nbins is provided)
                bins_param = nbins if nbins is not None else n_bins
                
                trace = remove_none({
                    "type": "histogram",
                    "x": filtered_x if (orientation is None or orientation == 'v') else filtered_y,
                    "y": filtered_y if (orientation is None or orientation == 'v') else filtered_x,
                    "orientation": orientation,
                    "histnorm": histnorm,
                    "nbinsx": bins_param if (orientation is None or orientation == 'v') else None,
                    "nbinsy": bins_param if orientation == 'h' else None,
                    "name": str(color_val),
                    "marker": {"color": category_color},
                    "text": filtered_text,
                    **_hover_fields(filtered_hover_name, filtered_hover_data)
                })
                traces.append(trace)

    # Create layout with faceting support
    layout = create_faceted_layout(facet_row, facet_col, facet_col_wrap, title, height, width, labels, template, data, x, y)
    # px stabler fargegrupper i histogram (barmode='relative'); plotly.js-
    # defaulten er 'group' (fikset 2026-07-10).
    if color is not None and len(traces) > 1 and 'barmode' not in layout:
        layout['barmode'] = 'relative'
    
    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range
    
    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def clean_dict(d):
    return {k: clean_dict(v) if isinstance(v, dict) else v for k, v in d.items() if v is not None}

def to_camel(snake_str):
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])
    
def to_camel_case(d):
    if not isinstance(d, dict):
        return d
    return {to_camel(k): to_camel_case(v) for k, v in d.items() if v is not None}

def create_gauge_config(range=None, steps=None, threshold=None, shape='angular', 
                       bar_color=None, bar_thickness=None, background_color=None, 
                       border_color=None, border_width=None, **kwargs):
    """Helper function to create gauge configuration."""
    config = {}
    if range is not None:
        config['axis'] = {'range': range}
    if steps is not None:
        config['steps'] = steps
    if threshold is not None:
        if isinstance(threshold, (int, float)):
            config['threshold'] = {'value': threshold}
        else:
            config['threshold'] = threshold
    if shape is not None:
        config['shape'] = shape
    if bar_color is not None:
        if 'bar' not in config:
            config['bar'] = {}
        config['bar']['color'] = bar_color
    if bar_thickness is not None:
        if 'bar' not in config:
            config['bar'] = {}
        config['bar']['thickness'] = bar_thickness
    if background_color is not None:
        config['backgroundColor'] = background_color
    if border_color is not None:
        config['borderColor'] = border_color
    if border_width is not None:
        config['borderWidth'] = border_width
    config.update(kwargs)
    return config

def create_delta_config(reference=None, relative=False, value_format=None, 
                       increasing_color=None, decreasing_color=None, **kwargs):
    """Helper function to create delta configuration."""
    config = {'relative': relative}
    if reference is not None:
        config['reference'] = reference
    if value_format is not None:
        config['valueFormat'] = value_format
    if increasing_color is not None:
        config['increasing'] = {'color': increasing_color}
    if decreasing_color is not None:
        config['decreasing'] = {'color': decreasing_color}
    config.update(kwargs)
    return config

def create_number_config(value_format=None, prefix=None, suffix=None, 
                        font_size=None, font_family=None, font_color=None, **kwargs):
    """Helper function to create number configuration."""
    config = {}
    if value_format is not None:
        config['valueFormat'] = value_format
    if prefix is not None:
        config['prefix'] = prefix
    if suffix is not None:
        config['suffix'] = suffix
    if any([font_size, font_family, font_color]):
        config['font'] = {}
        if font_size is not None:
            config['font']['size'] = font_size
        if font_family is not None:
            config['font']['family'] = font_family
        if font_color is not None:
            config['font']['color'] = font_color
    config.update(kwargs)
    return config

# Card styling templates
CARD_TEMPLATES = {
    'dashboard': {
        'background': 'white',
        'border_color': '#e0e0e0',
        'border_width': 1,
        'border_radius': None,  # Not implemented in Plotly shapes
        'shadow': True,
        'padding': 20,
        'opacity': 1.0
    },
    'minimal': {
        'background': 'transparent',
        'border_color': 'lightgray',
        'border_width': 0.5,
        'border_radius': None,  # Not implemented in Plotly shapes
        'shadow': False,
        'padding': 10,
        'opacity': 1.0
    },
    'modern': {
        'background': '#f8f9fa',
        'border_color': '#dee2e6',
        'border_width': 1,
        'border_radius': None,  # Not implemented in Plotly shapes
        'shadow': True,
        'padding': 25,
        'opacity': 1.0
    },
    'corporate': {
        'background': '#ffffff',
        'border_color': '#d1d5db',
        'border_width': 2,
        'border_radius': None,  # Not implemented in Plotly shapes
        'shadow': True,
        'padding': 30,
        'opacity': 1.0
    },
    'none': {
        'background': 'transparent',
        'border_color': 'transparent',
        'border_width': 0,
        'border_radius': None,  # Not implemented in Plotly shapes
        'shadow': False,
        'padding': 0,
        'opacity': 1.0
    }
}

def _get_card_config(card_style, card_background, card_border_color, card_border_width,
                    card_border_radius, card_shadow, card_padding, card_opacity):
    """Get card configuration with template defaults and overrides."""
    
    # Get template defaults
    template = CARD_TEMPLATES.get(card_style, CARD_TEMPLATES['dashboard'])
    
    # Apply overrides
    config = template.copy()
    if card_background is not None:
        config['background'] = card_background
    if card_border_color is not None:
        config['border_color'] = card_border_color
    if card_border_width is not None:
        config['border_width'] = card_border_width
    if card_border_radius is not None:
        config['border_radius'] = card_border_radius
    if card_shadow is not None:
        config['shadow'] = card_shadow
    if card_padding is not None:
        config['padding'] = card_padding
    if card_opacity is not None:
        config['opacity'] = card_opacity
    
    return config

def _calculate_domain(i, num_indicators, rows, cols):
    """Calculate domain for indicator at index i."""
    if num_indicators == 1:
        # Single indicator takes full space
        return [0, 1], [0, 1]
    
    row = i // cols
    col = i % cols
    
    # Simple domain calculation without margins
    x_start = col / cols
    x_end = (col + 1) / cols
    y_start = 1 - ((row + 1) / rows)
    y_end = 1 - (row / rows)
    
    return [x_start, x_end], [y_start, y_end]

def indicator(data=None, value=None, mode='number', title=None,
              # Simple parameters for common cases
              gauge_range=None, gauge_color=None, gauge_steps=None, gauge_threshold=None,
              delta_reference=None, delta_relative=False,
              number_format=None, number_prefix=None, number_suffix=None,
              # Layout control
              layout='auto', rows=None, cols=None,
              # Card styling
              card_style='dashboard', card_background=None, card_border_color=None,
              card_border_width=None, card_border_radius=None, card_shadow=None,
              card_padding=None, individual_cards=True, card_opacity=None,
              # Text styling
              text_color=None, title_color=None, number_color=None,
              # Styling
              height=None, width=None, config=None, static=None, template=None,
              # Advanced (as dicts for complex cases)
              number_config=None, delta_config=None, gauge_config=None):
    """
    Create indicator charts following Plotly Express patterns.
    
    Unlike other charts, indicators display a single value, so:
    - No x/y parameters (no axes)
    - No faceting (single value display)
    - No color mapping for data grouping
    - Simplified data handling
    
    Parameters:
    -----------
    data : dict, list, pandas.DataFrame, or None
        Data source. Can be:
        - List of values: [42, 58, 73] creates multiple indicators
        - Dict with values: {'Sales': 42, 'Profit': 58} creates indicators with titles
        - DataFrame: specify value and title columns
        - None: use value parameter directly
    value : str, numeric, or None
        Column name (if data provided) or numeric value for the indicator.
    mode : str, default 'number'
        Indicator mode: 'number', 'delta', 'gauge', 'number+delta', 'number+gauge', 'delta+gauge', 'number+delta+gauge'
    title : str, list, or None
        Title for the indicator(s). Can be a single title or list of titles for multiple indicators.
    
    Gauge Parameters:
    ----------------
    gauge_range : list, optional
        Range for gauge mode: [min, max]
    gauge_color : str, optional
        Color for gauge bar
    gauge_steps : list, optional
        Steps for gauge: [{'range': [0, 50], 'color': 'lightgray'}]
    gauge_threshold : numeric or dict, optional
        Threshold value or configuration
    
    Delta Parameters:
    ----------------
    delta_reference : numeric, optional
        Reference value for delta calculations
    delta_relative : bool, default False
        Whether to show relative delta (percentage) or absolute
    
    Number Parameters:
    -----------------
    number_format : str, optional
        Number formatting (e.g., '.2f', '$0,0')
    number_prefix : str, optional
        Prefix for number display
    number_suffix : str, optional
        Suffix for number display
    
    Layout Parameters:
    -----------------
    layout : str, default 'auto'
        Layout for multiple indicators: 'auto', 'row', 'column', 'grid'
    rows : int, optional
        Number of rows for grid layout
    cols : int, optional
        Number of columns for grid layout
    
    Card Styling Parameters:
    -----------------------
    card_style : str, default 'dashboard'
        Predefined card style: 'dashboard', 'minimal', 'modern', 'corporate', 'none'
    card_background : str, optional
        Card background color (overrides template)
    card_border_color : str, optional
        Card border color (overrides template)
    card_border_width : int, optional
        Card border width in pixels (overrides template)
    card_border_radius : int, optional
        Card border radius for rounded corners (overrides template)
        Note: Currently not implemented due to Plotly limitations
    card_shadow : bool, optional
        Enable/disable card shadow (overrides template)
    card_padding : int, optional
        Card internal padding in pixels (overrides template)
    individual_cards : bool, default True
        Each indicator gets its own card (True) or shared card (False)
    card_opacity : float, optional
        Card transparency (0.0 to 1.0, overrides template)
    
    Text Styling Parameters:
    -----------------------
    text_color : str, optional
        General text color
    title_color : str, optional
        Title text color
    number_color : str, optional
        Number text color
    
    Advanced Parameters:
    -------------------
    number_config : dict, optional
        Advanced number configuration
    delta_config : dict, optional
        Advanced delta configuration
    gauge_config : dict, optional
        Advanced gauge configuration
    """
    
    traces = []
    layout = {}
    
    # Handle data input
    if data is not None:
        data = ensure_data_dict(data)
        
        if isinstance(data, list):
            # List of values - create multiple indicators
            values = data
            titles = [str(i+1) for i in range(len(values))] if title is None else title
            if isinstance(titles, str):
                titles = [f"{titles} {i+1}" for i in range(len(values))]
        elif isinstance(data, dict):
            if value is None:
                # Dict with single values - use keys as titles, values as values
                values = list(data.values())
                titles = list(data.keys())
            else:
                # Dict with specified value column
                values = data.get(value, [])
                titles = data.get(title, []) if title and isinstance(title, str) else title
                if isinstance(titles, str):
                    titles = [f"{titles} {i+1}" for i in range(len(values))]
        else:
            # Single value
            values = [value] if value is not None else [0]
            titles = [title] if title else ["Indicator"]
    else:
        # Direct value
        values = [value] if value is not None else [0]
        titles = [title] if title else ["Indicator"]
    
    # Ensure we have lists and they're not empty
    if not isinstance(values, list):
        values = [values]
    if not isinstance(titles, list):
        titles = [titles]
    
    # Ensure lists are not empty
    if not values:
        values = [0]
    if not titles:
        titles = ["Indicator"]
    
    # Ensure titles list matches values list length
    if len(titles) != len(values):
        if len(titles) == 1:
            # Single title, replicate for all values
            titles = [titles[0] + f" {i+1}" for i in range(len(values))]
        else:
            # Pad or truncate titles to match values length
            if len(titles) < len(values):
                titles.extend([f"Indicator {i+1}" for i in range(len(titles), len(values))])
            else:
                titles = titles[:len(values)]
    
    # Create traces for each indicator
    num_indicators = len(values)
    
    # Check if user provided explicit cols/rows parameters first
    user_cols = cols
    user_rows = rows
    
    # Auto-set cols based on data length if not explicitly specified
    if num_indicators > 1 and user_cols is None and user_rows is None:
        cols = num_indicators  # Default to row layout with all indicators
    
    # Determine layout with better defaults
    if layout == 'auto':
        if num_indicators == 1:
            layout_type = 'single'
        elif user_cols is not None or user_rows is not None:
            # User specified cols or rows, use grid layout
            layout_type = 'grid'
        elif cols == num_indicators:
            # Auto-set cols equals num_indicators, use row layout
            layout_type = 'row'
        else:
            layout_type = 'grid'  # Use grid for other cases
    else:
        layout_type = layout
    
    # Calculate subplot positions
    if layout_type == 'single':
        rows = 1
        cols = 1
    elif layout_type == 'row':
        rows = 1
        cols = num_indicators
    elif layout_type == 'column':
        rows = num_indicators
        cols = 1
    elif layout_type == 'grid':
        if user_cols is not None:
            # User specified cols
            cols = user_cols
            rows = (num_indicators + cols - 1) // cols
        elif user_rows is not None:
            # User specified rows
            rows = user_rows
            cols = (num_indicators + rows - 1) // rows
        else:
            # Auto-calculate grid - prefer wider layouts
            cols = min(num_indicators, 4)  # Max 4 columns for readability
            rows = (num_indicators + cols - 1) // cols
    
    # Ensure rows and cols are never None
    if rows is None:
        rows = 1
    if cols is None:
        cols = 1
    
    # Create traces using domain approach
    for i, (val, title_text) in enumerate(zip(values, titles)):
        # Calculate domain for this indicator using helper function
        domain_x, domain_y = _calculate_domain(i, num_indicators, rows, cols)
        
        # Create trace
        trace = {
            'type': 'indicator',
            'mode': mode,
            'value': val,
            'domain': {'x': domain_x, 'y': domain_y}
        }
        
        traces.append(trace)
    
    # Configure all traces with styling and parameters
    for i, trace in enumerate(traces):
        val = values[i] if i < len(values) else values[0]
        title_text = titles[i] if i < len(titles) else titles[0]
        
        # Get card styling configuration
        card_config = _get_card_config(card_style, card_background, card_border_color,
                                      card_border_width, card_border_radius, card_shadow,
                                      card_padding, card_opacity)
        
        # Add title with text styling
        if title_text:
            title_conf = {'text': str(title_text)}
            if title_color:
                title_conf['font'] = {'color': title_color}
            trace['title'] = title_conf
        
        # Add number configuration with text styling
        number_conf = {}
        if number_config:
            number_conf.update(number_config)
        if number_format:
            number_conf['valueFormat'] = number_format
        if number_prefix:
            number_conf['prefix'] = number_prefix
        if number_suffix:
            number_conf['suffix'] = number_suffix
        if number_color:
            number_conf['font'] = number_conf.get('font', {})
            number_conf['font']['color'] = number_color
        if number_conf:
            trace['number'] = number_conf
        
        # Add delta configuration with sensible defaults
        delta_conf = {}
        if delta_config:
            delta_conf.update(delta_config)
        if delta_reference is not None:
            delta_conf['reference'] = delta_reference
        elif 'delta' in mode and isinstance(val, (int, float)):
            # Sensible default delta reference based on value
            if val > 0:
                # Use a reasonable reference (e.g., 80% of current value)
                delta_conf['reference'] = val * 0.8
            else:
                # For negative values, use 0 as reference
                delta_conf['reference'] = 0
        
        if 'delta' in mode:
            delta_conf['relative'] = delta_relative
        
        if delta_conf:
            trace['delta'] = delta_conf
        
        # Add gauge configuration with sensible defaults
        gauge_conf = {}
        if gauge_config:
            gauge_conf.update(gauge_config)
        else:
            # Use simple parameters to build gauge config
            if gauge_range:
                gauge_conf['axis'] = {'range': gauge_range}
            elif 'gauge' in mode:
                # Sensible default gauge range based on value
                if isinstance(val, (int, float)) and val >= 0:
                    if val <= 1:
                        # Likely a percentage or ratio
                        gauge_conf['axis'] = {'range': [0, 1]}
                    elif val <= 100:
                        # Likely a percentage or score
                        gauge_conf['axis'] = {'range': [0, 100]}
                    else:
                        # Larger number, use a reasonable range
                        max_val = max(100, val * 1.2)
                        gauge_conf['axis'] = {'range': [0, max_val]}
                else:
                    # Default range
                    gauge_conf['axis'] = {'range': [0, 100]}
            
            if gauge_color:
                gauge_conf['bar'] = {'color': gauge_color}
            elif 'gauge' in mode and not gauge_conf.get('bar'):
                # Default gauge color
                gauge_conf['bar'] = {'color': 'blue'}
            
            if gauge_steps:
                gauge_conf['steps'] = gauge_steps
            
            if gauge_threshold is not None:
                if isinstance(gauge_threshold, (int, float)):
                    gauge_conf['threshold'] = {'value': gauge_threshold}
                else:
                    gauge_conf['threshold'] = gauge_threshold
            elif 'gauge' in mode and isinstance(val, (int, float)):
                # Sensible default threshold (80% of max)
                gauge_range = gauge_conf.get('axis', {}).get('range', [0, 100])
                max_range = gauge_range[1] if isinstance(gauge_range, list) else 100
                threshold_val = max_range * 0.8
                gauge_conf['threshold'] = {'value': threshold_val}
        
        if gauge_conf:
            trace['gauge'] = gauge_conf
    
    # Create layout with automatic sizing for multiple indicators
    layout = {}
    
    # Set width and height
    if width is not None:
        layout['width'] = width
    if height is not None:
        layout['height'] = height
    
    # Auto-adjust size for multiple indicators if not specified
    if width is None and num_indicators > 1:
        # Adjust width based on number of columns
        layout['width'] = 200 * cols + 100  # 200px per indicator + padding
    
    if height is None and num_indicators > 1:
        # Adjust height based on number of rows
        layout['height'] = 150 * rows + 100  # 150px per indicator + padding
    
    
    # Add card styling to layout
    if card_style != 'none':
        card_config = _get_card_config(card_style, card_background, card_border_color,
                                      card_border_width, card_border_radius, card_shadow,
                                      card_padding, card_opacity)
        
        # Set overall background
        if card_config['background'] != 'transparent':
            layout['plot_bgcolor'] = card_config['background']
            layout['paper_bgcolor'] = card_config['background']
        
        # Add card shapes for indicators
        if individual_cards or num_indicators == 1:
            shapes = []
            
            # Calculate padding offset (convert pixels to relative coordinates)
            padding_offset = (card_config['padding'] / 1000) if card_config['padding'] > 0 else 0
            
            for i, (val, title_text) in enumerate(zip(values, titles)):
                # Calculate domain for this indicator using helper function
                domain_x, domain_y = _calculate_domain(i, num_indicators, rows, cols)
                
                # Apply padding to create smaller cards
                if padding_offset > 0:
                    domain_x = [domain_x[0] + padding_offset, domain_x[1] - padding_offset]
                    domain_y = [domain_y[0] + padding_offset, domain_y[1] - padding_offset]
                
                # Add shadow effect first (so it appears behind)
                if card_config['shadow']:
                    shadow_offset = 0.008  # Shadow offset
                    shadow_shape = {
                        'type': 'rect',
                        'x0': domain_x[0] + shadow_offset,
                        'x1': domain_x[1] + shadow_offset,
                        'y0': domain_y[0] - shadow_offset,
                        'y1': domain_y[1] - shadow_offset,
                        'fillcolor': 'rgba(0,0,0,0.15)',
                        'opacity': 0.8,
                        'layer': 'below',
                        'line': {'width': 0}
                    }
                    shapes.append(shadow_shape)
                
                # Create main card shape
                shape = {
                    'type': 'rect',
                    'x0': domain_x[0],
                    'x1': domain_x[1],
                    'y0': domain_y[0],
                    'y1': domain_y[1],
                    'fillcolor': card_config['background'],
                    'opacity': card_config['opacity'],
                    'layer': 'below',
                    'line': {
                        'color': card_config['border_color'],
                        'width': card_config['border_width']
                    }
                }
                
                # Note: Plotly shapes don't support border_radius directly
                # For rounded corners, we'd need to use SVG paths or multiple shapes
                # For now, we'll document this limitation
                
                shapes.append(shape)
            
            layout['shapes'] = shapes
    
    # Remove None values
    layout = {k: v for k, v in layout.items() if v is not None}
    
    # Return PlotlyFigure
    import json
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def line(data=None, x=None, y=None, color=None, text=None, hover_name=None, hover_data=None,
         title=None, height=None, width=None, line_shape=None, config=None, line_color=None, static=None,
         color_discrete_sequence=None, color_discrete_map=None,
         color_continuous_scale=None, color_continuous_midpoint=None,
         facet_row=None, facet_col=None, facet_col_wrap=None, labels=None, template=None,
         markers=False, line_dash=None,
         # Enhanced axis customization
         xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None,
         log_x=False, log_y=False, range_x=None, range_y=None, category_orders=None):
    traces = []
    layout = {}
    data = ensure_data_dict(data)
    x, y = _series_xy(data, x, y)
    
    if isinstance(data, list):
        data_dict, x_col, y_col = data2dict(data)
        data = data_dict
        x = x_col
        y = y_col
        x_data = data.get(x)
        y_data = data.get(y)
        y_keys = [y]
        hover_name_data = None
        hover_data_dict = {}
    
    elif (x is None) & (y is None) & (isinstance(data, dict)):
        #data = {'1999':55, '2000':33, '2001':44, '2002':22}
        x_data=list(data.keys())
        y_data=list(data.values())
        data={"values": y_data}
        y_keys=["values"]
        y="values"
        hover_name_data = hover_name
        hover_data_dict = hover_data
        
    else:
        if data is not None:
            x_data = data.get(x, data)
            hover_name_data = data.get(hover_name)
            hover_data_dict = {k: data.get(k) for k in hover_data or []}
        else:
            x_data = x
            hover_name_data = hover_name
            hover_data_dict = hover_data

        if isinstance(y, list):
            y_keys = y if data is not None else [y]
        else:
            y_keys = [y]

    # Default color array
    default_color_array = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
    color_array = line_color if line_color is not None else default_color_array

    # color= som KOLONNE grupperer i én trace per kategori (px-semantikk,
    # gjeninnført 2026-07-10 — grupperingen forsvant i en tidligere
    # omskriving og color ble tolket som literal CSS-farge). En verdi som
    # ikke er kolonnenavn behandles fortsatt som literal farge.
    color_is_column = bool(color is not None and isinstance(data, dict) and color in data)
    if color_is_column:
        _line_cvals = list(data.get(color))
        _line_cats = _apply_category_order(_unique_ordered(_line_cvals, sort=False),
                                           category_orders, color)
        _line_cmap = build_category_colors(_line_cats, color_discrete_sequence, color_discrete_map)
    _line_mode = "lines+markers" if markers else "lines"

    def _line_opts(idx, cat=None):
        opts = {}
        if cat is not None:
            opts['color'] = _line_cmap.get(cat, DEFAULT_COLORS[0])
        elif color is not None and not color_is_column:
            opts['color'] = color
        else:
            opts['color'] = color_array[idx % len(color_array)]
        if isinstance(line_shape, list):
            opts['shape'] = line_shape[idx]
        elif line_shape is not None:
            opts['shape'] = line_shape
        if line_dash is not None and not (isinstance(data, dict) and line_dash in data):
            opts['dash'] = line_dash
        return opts

    # Handle faceting with proper subplot assignment
    if facet_row or facet_col:
        # Get unique values for faceting
        if facet_row:
            row_values = data.get(facet_row)
            unique_rows = _unique_ordered(row_values, sort=False)
            n_rows = len(unique_rows)
        else:
            n_rows = 1
            
        if facet_col:
            col_values = data.get(facet_col)
            unique_cols = _unique_ordered(col_values, sort=False)
            if facet_col_wrap:
                n_cols = min(facet_col_wrap, len(unique_cols))
                if not facet_row and len(unique_cols) > n_cols:
                    # wrap: paneler over flere rader (matcher layouten)
                    n_rows = -(-len(unique_cols) // n_cols)
            else:
                n_cols = len(unique_cols)
        else:
            n_cols = 1
        
        # Create traces for each facet
        subplot_idx = 1
        for row_idx, row_val in enumerate(unique_rows if facet_row else [None]):
            for col_idx, col_val in enumerate(unique_cols if facet_col else [None]):
                # Determine which data belongs to this facet
                if facet_row and facet_col:
                    # Both row and column faceting
                    indices = [i for i, (r, c) in enumerate(zip(row_values, col_values)) if r == row_val and c == col_val]
                    facet_name = f"{row_val}-{col_val}"
                elif facet_row:
                    # Only row faceting
                    indices = [i for i, v in enumerate(row_values) if v == row_val]
                    facet_name = f"Row: {row_val}"
                elif facet_col:
                    # Only column faceting
                    indices = [i for i, v in enumerate(col_values) if v == col_val]
                    facet_name = f"Column: {col_val}"
                else:
                    indices = list(range(len(x_data)))
                    facet_name = "main"
                
                if indices:
                    facet_x = [x_data[i] for i in indices]

                    # Create traces for each y column within this facet
                    for idx, y_key in enumerate(y_keys):
                        facet_y = [data.get(y_key)[i] for i in indices] if data is not None else y_key

                        if color_is_column:
                            facet_c = [_line_cvals[i] for i in indices]
                            groups = [(cat, [j for j, cv in enumerate(facet_c) if cv == cat])
                                      for cat in _line_cats]
                            groups = [(cat, idxs) for cat, idxs in groups if idxs]
                        else:
                            groups = [(None, list(range(len(facet_x))))]

                        for cat, idxs in groups:
                            trace = {
                                "type": "scatter",
                                "mode": _line_mode,
                                "x": [facet_x[j] for j in idxs],
                                "y": [facet_y[j] for j in idxs],
                                "name": str(cat) if cat is not None else f"{facet_name}-{y_key}",
                                "line": _line_opts(idx, cat),
                            }
                            if cat is not None:
                                # Én legendeoppføring per kategori, ikke per panel
                                trace["legendgroup"] = str(cat)
                                trace["showlegend"] = (subplot_idx == 1)
                            if hover_name_data is not None:
                                trace["hoverinfo"] = "name"

                            # Assign to subplot if faceting
                            if n_rows > 1 or n_cols > 1:
                                if n_rows > 1 and n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_rows > 1:
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"

                            traces.append(trace)

                # Panel-telleren følger rutenett-cellen, ikke om cellen har
                # data — inne i `if indices:` forskjøv manglende
                # kombinasjoner alle etterfølgende paneler (fikset 2026-07-10).
                subplot_idx += 1
    else:
        # No faceting
        for idx, y_key in enumerate(y_keys):
            y_data = data.get(y_key) if data is not None else y_key

            if color_is_column:
                for cat in _line_cats:
                    idxs = [j for j, cv in enumerate(_line_cvals) if cv == cat]
                    if not idxs:
                        continue
                    trace = {"type": "scatter", "mode": _line_mode,
                             "x": [x_data[j] for j in idxs],
                             "y": [y_data[j] for j in idxs],
                             "name": str(cat),
                             "line": _line_opts(idx, cat)}
                    if hover_name_data is not None:
                        trace["hoverinfo"] = "name"
                    traces.append(trace)
                continue

            # Construct trace
            trace = {"type": "scatter", "mode": _line_mode, "x": x_data, "y": y_data, "name": str(y_key)}
            trace["line"] = _line_opts(idx)

            if hover_name_data is not None:
                trace["hoverinfo"] = "name"

            if hover_data_dict:
                trace["customdata"] = hover_data_dict

            traces.append(trace)

    # Create layout with faceting support
    layout = create_faceted_layout(facet_row, facet_col, facet_col_wrap, title, height, width, labels, template, data, x, y)
    layout = _apply_axis_options(layout, log_x, log_y, range_x, range_y)

    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}

        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range

    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def scatter(data=None, x=None, y=None, color=None, size=None,
                                   text=None, hover_name=None, hover_data=None,
                                   title=None, height=None, width=None, marker_symbol=None,
                                   color_discrete_sequence=None, color_discrete_map=None,
                                   color_continuous_scale=None, color_continuous_midpoint=None,
                                   facet_row=None, facet_col=None, facet_col_wrap=None, labels=None, template=None,
                                   marginal_x=None, marginal_y=None, config=None, static=None,
                                   trendline=None, opacity=None,
                                   log_x=False, log_y=False, range_x=None, range_y=None,
                                   category_orders=None, error_y=None, error_x=None,
                                   # Enhanced axis customization
                                   xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None,
                                   # Enhanced size and symbol mapping
                                   size_max=None, size_min=None, symbol=None, symbol_map=None):
    
    traces = []
    layout = {}
    data = ensure_data_dict(data)
    x, y = _series_xy(data, x, y)

    if (x is None) & (y is None) & (isinstance(data, dict)):
        #data = {1999:55, 2000:33, 2001:44, 2002:22}
        x_data=list(data.keys())
        y_data=list(data.values())
    
    elif data is None:
        x_data=x
        y_data=y
        data={}
        
    else:
        x_data = data.get(x)
        y_data = data.get(y)
    
    color_data = data.get(color)
    _cat_colors = build_category_colors(
        _apply_category_order(_unique_ordered(color_data or [], sort=False), category_orders, color),
        color_discrete_sequence, color_discrete_map)
    size_data = data.get(size)
    text_data = data.get(text)
    hover_name_data = data.get(hover_name)
    hover_data_dict = {k: data.get(k) for k in hover_data or []}

    # Handle faceting with proper subplot assignment
    if facet_row or facet_col:
        # Get unique values for faceting
        if facet_row:
            row_values = data.get(facet_row)
            unique_rows = _unique_ordered(row_values, sort=False)
            n_rows = len(unique_rows)
        else:
            n_rows = 1
            
        if facet_col:
            col_values = data.get(facet_col)
            unique_cols = _unique_ordered(col_values, sort=False)
            if facet_col_wrap:
                n_cols = min(facet_col_wrap, len(unique_cols))
                if not facet_row and len(unique_cols) > n_cols:
                    # wrap: paneler over flere rader (matcher layouten)
                    n_rows = -(-len(unique_cols) // n_cols)
            else:
                n_cols = len(unique_cols)
        else:
            n_cols = 1
        
        # Create traces for each facet
        subplot_idx = 1
        for row_idx, row_val in enumerate(unique_rows if facet_row else [None]):
            for col_idx, col_val in enumerate(unique_cols if facet_col else [None]):
                # Determine which data belongs to this facet
                if facet_row and facet_col:
                    # Both row and column faceting
                    indices = [i for i, (r, c) in enumerate(zip(row_values, col_values)) if r == row_val and c == col_val]
                    facet_name = f"{row_val}-{col_val}"
                elif facet_row:
                    # Only row faceting
                    indices = [i for i, v in enumerate(row_values) if v == row_val]
                    facet_name = f"Row: {row_val}"
                elif facet_col:
                    # Only column faceting
                    indices = [i for i, v in enumerate(col_values) if v == col_val]
                    facet_name = f"Column: {col_val}"
                else:
                    indices = list(range(len(x_data)))
                    facet_name = "main"
                
                if indices:
                    facet_x = [x_data[i] for i in indices]
                    facet_y = [y_data[i] for i in indices]
                    facet_color = [color_data[i] for i in indices] if color_data else None
                    facet_size = [size_data[i] for i in indices] if size_data else None
                    
                    if facet_color is None or isinstance(facet_color, str):
                        # Enhanced marker creation with size and symbol mapping
                        marker_dict = {}
                        
                        # Handle color
                        if facet_color:
                            marker_dict["color"] = facet_color
                        
                        # Handle size mapping
                        if facet_size:
                            if size_max is not None or size_min is not None:
                                # Normalize size data
                                size_max_val = size_max if size_max is not None else max(facet_size)
                                size_min_val = size_min if size_min is not None else min(facet_size)
                                
                                # Scale to reasonable marker sizes (5-30)
                                normalized_sizes = [
                                    5 + (s - size_min_val) / (size_max_val - size_min_val) * 25 
                                    for s in facet_size
                                ]
                                marker_dict["size"] = normalized_sizes
                            else:
                                marker_dict["size"] = facet_size
                        
                        # Handle symbol mapping
                        if symbol:
                            symbol_data = [data.get(symbol)[i] for i in indices]
                            if symbol_map:
                                # Use custom symbol mapping
                                marker_dict["symbol"] = [symbol_map.get(s, 'circle') for s in symbol_data]
                            else:
                                # Auto-assign symbols
                                default_symbols = ['circle', 'square', 'diamond', 'cross', 'x', 
                                                 'triangle-up', 'triangle-down']
                                unique_symbols = _unique_ordered(symbol_data, sort=False)
                                symbol_assignments = {}
                                for i, val in enumerate(unique_symbols):
                                    symbol_assignments[val] = default_symbols[i % len(default_symbols)]
                                marker_dict["symbol"] = [symbol_assignments[s] for s in symbol_data]
                        elif marker_symbol:
                            marker_dict["symbol"] = marker_symbol
                        
                        trace = remove_none({
                            "type": "scatter",
                            "mode": "markers",
                            "x": facet_x,
                            "y": facet_y,
                            "name": facet_name,
                            "marker": marker_dict
                        })
                        
                        # Assign to subplot if faceting
                        if n_rows > 1 or n_cols > 1:
                            if n_rows > 1 and n_cols > 1:
                                trace["xaxis"] = f"x{subplot_idx}"
                                trace["yaxis"] = f"y{subplot_idx}"
                            elif n_rows > 1:
                                trace["yaxis"] = f"y{subplot_idx}"
                            elif n_cols > 1:
                                trace["xaxis"] = f"x{subplot_idx}"
                        
                        traces.append(trace)
                    else:
                        # Handle color within facet
                        color_categories = _unique_ordered(facet_color, sort=False)
                        for color_val in color_categories:
                            color_indices = [i for i, c in enumerate(facet_color) if c == color_val]
                            color_x = [facet_x[i] for i in color_indices]
                            color_y = [facet_y[i] for i in color_indices]
                            color_size = [facet_size[i] for i in color_indices] if facet_size else None
                            
                            category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])
                            
                            trace = remove_none({
                                "type": "scatter",
                                "mode": "markers",
                                "x": color_x,
                                "y": color_y,
                                "name": f"{facet_name}-{color_val}",
                                "marker": {
                                    "color": category_color,
                                    "size": color_size,
                                    "symbol": marker_symbol if marker_symbol else None
                                }
                            })
                            
                            # Assign to subplot if faceting - use same subplot index for all colors within a facet
                            if n_rows > 1 or n_cols > 1:
                                if n_rows > 1 and n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_rows > 1:
                                    trace["yaxis"] = f"y{subplot_idx}"
                                elif n_cols > 1:
                                    trace["xaxis"] = f"x{subplot_idx}"
                            
                            traces.append(trace)
                            # Don't increment subplot_idx here - all colors within a facet use the same subplot
                # Panel-telleren følger rutenett-cellen, ikke om cellen
                # har data (fikset 2026-07-10 — manglende kombinasjoner
                # forskjøv alle etterfølgende paneler).
                subplot_idx += 1
    else:
        # No faceting - original logic
        _continuous = (color_data is not None and not isinstance(color_data, str)
                       and is_continuous_color(color_data))
        if color_data is None or isinstance(color_data, str) or _continuous:
            # Enhanced marker creation with size and symbol mapping
            marker_dict = {}

            # Handle color
            if _continuous:
                # Numerisk color-kolonne → én trace med kontinuerlig
                # fargeskala + colorbar (px-semantikk; før: én trace per
                # tallverdi med tilfeldige farger).
                marker_dict["color"] = [None if _is_nan(v) else v for v in color_data]
                marker_dict["colorscale"] = color_continuous_scale or "Viridis"
                marker_dict["showscale"] = True
                marker_dict["colorbar"] = {"title": {"text": (labels or {}).get(color) or format_column_name(color)}}
                if color_continuous_midpoint is not None:
                    marker_dict["cmid"] = color_continuous_midpoint
            elif color_data:
                marker_dict["color"] = color_data

            # Handle size mapping
            if size_data:
                if size_max is not None or size_min is not None:
                    # Normalize size data
                    size_max_val = size_max if size_max is not None else max(size_data)
                    size_min_val = size_min if size_min is not None else min(size_data)
                    
                    # Scale to reasonable marker sizes (5-30)
                    if size_max_val > size_min_val:
                        normalized_sizes = [
                            5 + (s - size_min_val) / (size_max_val - size_min_val) * 25 
                            for s in size_data
                        ]
                        marker_dict["size"] = normalized_sizes
                    else:
                        # All values are the same - use a default size
                        marker_dict["size"] = [15] * len(size_data)
                else:
                    # Auto-scale large values to reasonable marker sizes
                    if size_data and max(size_data) > 100:
                        size_max_val = max(size_data)
                        size_min_val = min(size_data)
                        if size_max_val > size_min_val:
                            # Normal scaling when there's a range
                            normalized_sizes = [
                                5 + (s - size_min_val) / (size_max_val - size_min_val) * 25 
                                for s in size_data
                            ]
                            marker_dict["size"] = normalized_sizes
                        else:
                            # All values are the same - use a default size
                            marker_dict["size"] = [15] * len(size_data)
                    else:
                        marker_dict["size"] = size_data
            
            # Handle symbol mapping
            if symbol:
                symbol_data = data.get(symbol)
                if symbol_map:
                    # Use custom symbol mapping
                    marker_dict["symbol"] = [symbol_map.get(s, 'circle') for s in symbol_data]
                else:
                    # Auto-assign symbols
                    default_symbols = ['circle', 'square', 'diamond', 'cross', 'x', 
                                     'triangle-up', 'triangle-down']
                    unique_symbols = _unique_ordered(symbol_data, sort=False)
                    symbol_assignments = {}
                    for i, val in enumerate(unique_symbols):
                        symbol_assignments[val] = default_symbols[i % len(default_symbols)]
                    marker_dict["symbol"] = [symbol_assignments[s] for s in symbol_data]
            elif marker_symbol:
                marker_dict["symbol"] = marker_symbol
            
            trace = remove_none({
                "type": "scatter",
                "mode": "markers",
                "x": x_data,
                "y": y_data,
                "marker": marker_dict,
                "text": text_data,
                **_hover_fields(hover_name_data, hover_data_dict)
            })
            traces.append(trace)
        else:
            color_categories = _apply_category_order(_unique_ordered(color_data, sort=False), category_orders, color)
            for color_val in color_categories:
                filtered_indices = [i for i, c in enumerate(color_data) if c == color_val]
                filtered_x = [x_data[i] for i in filtered_indices]
                filtered_y = [y_data[i] for i in filtered_indices]
                filtered_size = [size_data[i] for i in filtered_indices] if size_data else None
                filtered_text = [text_data[i] for i in filtered_indices] if text_data else None
                filtered_hover_name = [hover_name_data[i] for i in filtered_indices] if hover_name_data else None
                filtered_hover_data = {k: [v[i] for i in filtered_indices] for k, v in hover_data_dict.items()} if hover_data_dict else None

                # Get color for this category
                category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])

                # Enhanced marker creation with size and symbol mapping
                marker_dict = {"color": category_color}
                
                # Handle size mapping
                if filtered_size:
                    if size_max is not None or size_min is not None:
                        # Normalize size data
                        size_max_val = size_max if size_max is not None else max(filtered_size)
                        size_min_val = size_min if size_min is not None else min(filtered_size)
                        
                        # Scale to reasonable marker sizes (5-30)
                        if size_max_val > size_min_val:
                            normalized_sizes = [
                                5 + (s - size_min_val) / (size_max_val - size_min_val) * 25 
                                for s in filtered_size
                            ]
                            marker_dict["size"] = normalized_sizes
                        else:
                            # All values are the same - use a default size
                            marker_dict["size"] = [15] * len(filtered_size)
                    else:
                        # Auto-scale large values to reasonable marker sizes
                        if filtered_size and max(filtered_size) > 100:
                            size_max_val = max(filtered_size)
                            size_min_val = min(filtered_size)
                            if size_max_val > size_min_val:
                                # Normal scaling when there's a range
                                normalized_sizes = [
                                    5 + (s - size_min_val) / (size_max_val - size_min_val) * 25 
                                    for s in filtered_size
                                ]
                                marker_dict["size"] = normalized_sizes
                            else:
                                # All values are the same - use a default size
                                marker_dict["size"] = [15] * len(filtered_size)
                        else:
                            marker_dict["size"] = filtered_size
                
                # Handle symbol mapping
                if symbol:
                    symbol_data = [data.get(symbol)[i] for i in filtered_indices]
                    if symbol_map:
                        # Use custom symbol mapping
                        marker_dict["symbol"] = [symbol_map.get(s, 'circle') for s in symbol_data]
                    else:
                        # Auto-assign symbols
                        default_symbols = ['circle', 'square', 'diamond', 'cross', 'x', 
                                         'triangle-up', 'triangle-down']
                        unique_symbols = _unique_ordered(symbol_data, sort=False)
                        symbol_assignments = {}
                        for i, val in enumerate(unique_symbols):
                            symbol_assignments[val] = default_symbols[i % len(default_symbols)]
                        marker_dict["symbol"] = [symbol_assignments[s] for s in symbol_data]
                elif marker_symbol:
                    marker_dict["symbol"] = marker_symbol
                
                trace = remove_none({
                    "type": "scatter",
                    "mode": "markers",
                    "x": filtered_x,
                    "y": filtered_y,
                    "name": str(color_val),
                    "marker": marker_dict,
                    "text": filtered_text,
                    **_hover_fields(filtered_hover_name, filtered_hover_data)
                })
                traces.append(trace)

    # px-argumenter som gjelder alle datatraces (2026-07-10)
    if opacity is not None:
        for _tr in traces:
            _tr['opacity'] = opacity
    if error_y is not None and data.get(error_y) is not None and len(traces) == 1:
        traces[0]['error_y'] = {'type': 'data', 'array': list(data.get(error_y))}
    if error_x is not None and data.get(error_x) is not None and len(traces) == 1:
        traces[0]['error_x'] = {'type': 'data', 'array': list(data.get(error_x))}

    # trendline='ols' — enkel lineær regresjon i ren Python, én linje per
    # farge-/panel-trace (px-navnet «OLS trendline» beholdes).
    if trendline == 'ols':
        _tl = []
        for _tr in traces:
            pairs = [(a, b) for a, b in zip(_tr.get('x') or [], _tr.get('y') or [])
                     if not _is_nan(a) and not _is_nan(b)
                     and isinstance(a, (int, float)) and isinstance(b, (int, float))]
            n = len(pairs)
            if n < 2:
                continue
            sx = sum(a for a, _b in pairs)
            sy = sum(b for _a, b in pairs)
            sxx = sum(a * a for a, _b in pairs)
            sxy = sum(a * b for a, b in pairs)
            den = n * sxx - sx * sx
            if den == 0:
                continue
            slope = (n * sxy - sx * sy) / den
            intercept = (sy - slope * sx) / n
            xs_sorted = sorted(a for a, _b in pairs)
            _mc = (_tr.get('marker') or {}).get('color')
            line_tr = {
                'type': 'scatter', 'mode': 'lines',
                'x': xs_sorted,
                'y': [slope * a + intercept for a in xs_sorted],
                'name': ((str(_tr.get('name')) + ' ') if _tr.get('name') else '') + 'OLS trendline',
                'showlegend': False,
                'line': {'color': _mc if isinstance(_mc, str) else DEFAULT_COLORS[0]},
            }
            if _tr.get('xaxis'):
                line_tr['xaxis'] = _tr['xaxis']
            if _tr.get('yaxis'):
                line_tr['yaxis'] = _tr['yaxis']
            _tl.append(line_tr)
        traces.extend(_tl)

    # Add marginal plots if requested
    if marginal_x or marginal_y:
        marginal_traces = create_marginal_traces(data, x, y, marginal_x, marginal_y, color,
                                               color_discrete_sequence, color_discrete_map)
        traces.extend(marginal_traces)

    # Create layout with faceting support
    layout = create_faceted_layout(facet_row, facet_col, facet_col_wrap, title, height, width, labels, template, data, x, y)
    layout = _apply_axis_options(layout, log_x, log_y, range_x, range_y)
    
    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range
    
    # Add marginal layout if needed
    if marginal_x or marginal_y:
        marginal_layout = create_marginal_layout(marginal_x, marginal_y, height, width)
        layout.update(marginal_layout)
    

   
    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def violin(data, x=None, y=None, color=None, text=None, hover_name=None, hover_data=None,
           title=None, height=None, width=None, color_discrete_sequence=None, color_discrete_map=None, config=None, static=None,
           # Enhanced axis customization
           xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):
    
    traces = []
    layout = {}
    data = ensure_data_dict(data)

    x_data = data.get(x)
    y_data = data.get(y)
    color_data = data.get(color)
    _cat_colors = build_category_colors(_unique_ordered(color_data or [], sort=False), color_discrete_sequence, color_discrete_map)
    text_data = data.get(text)
    hover_name_data = data.get(hover_name)
    hover_data_dict = {k: data.get(k) for k in hover_data or []}

    if color_data is None or isinstance(color_data, str):
        trace = remove_none({
            "type": "violin",
            "x": x_data,
            "y": y_data,
            "marker": {"color": color_data} if color_data else None,
            "text": text_data,
            **_hover_fields(hover_name_data, hover_data_dict)
        })
        traces.append(trace)
    else:
        color_categories = _unique_ordered(color_data, sort=False)
        for color_val in color_categories:
            filtered_indices = [i for i, c in enumerate(color_data) if c == color_val]
            filtered_x = [x_data[i] for i in filtered_indices]
            filtered_y = [y_data[i] for i in filtered_indices]
            filtered_text = [text_data[i] for i in filtered_indices] if text_data else None
            filtered_hover_name = [hover_name_data[i] for i in filtered_indices] if hover_name_data else None
            filtered_hover_data = {k: [v[i] for i in filtered_indices] for k, v in hover_data_dict.items()} if hover_data_dict else None

            # Get color for this category
            category_color = _cat_colors.get(color_val, DEFAULT_COLORS[0])

            trace = remove_none({
                "type": "violin",
                "x": filtered_x,
                "y": filtered_y,
                "name": str(color_val),
                "marker": {"color": category_color},
                "text": filtered_text,
                **_hover_fields(filtered_hover_name, filtered_hover_data)
            })
            traces.append(trace)

    # Let CSS handle all sizing - no dimension calculations needed
    layout = remove_none({
        "title": title,
    })
    # px setter violinmode='group' ved x+color (fikset 2026-07-10).
    if x is not None and color is not None and len(traces) > 1:
        layout['violinmode'] = 'group'

    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range
    
    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def pie(data=None, values=None, names=None, color=None, title=None,
        height=None, width=None, config=None, static=None,
        hole=None, opacity=None,
        # Enhanced axis customization
        xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):
    
    traces = []
    layout = {}
    
    # Handle case where data is not provided but values and names are
    if data is None and values is not None and names is not None:
        # Create data dict from values and names lists
        if isinstance(values, list) and isinstance(names, list):
            data = {'values': values, 'names': names}
            values_col = 'values'
            names_col = 'names'
        else:
            # If values and names are not lists, treat them as column names that need data
            raise ValueError("When data is None, both values and names must be lists")
    elif data is not None:
        # Use provided data and column names
        data = ensure_data_dict(data)
        values_col = values
        names_col = names
    else:
        raise ValueError("Either data must be provided, or both values and names must be provided")

    values_data = data.get(values_col)
    names_data = data.get(names_col)
    color_data = data.get(color)
    
    trace = remove_none({
        "type": "pie",
        "values": values_data,
        "labels": names_data,
        "marker": {"colors": color_data} if color_data else None,
        "hole": hole,          # px: hole=0.4 gir donut
        "opacity": opacity,
    })

    traces.append(trace)
    
    # Let CSS handle all sizing - no dimension calculations needed
    layout = remove_none({
        "title": title,
    })

    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range
    
    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def scatter_3d(data=None, x=None, y=None, z=None, color=None, size=None,
                text=None, hover_name=None, hover_data=None,
                title=None, height=None, width=None, config=None, static=None,
                # Enhanced axis customization
                xaxis_title=None, yaxis_title=None, zaxis_title=None,
                xaxis_range=None, yaxis_range=None, zaxis_range=None):
    
    traces = []
    layout = {}
    data = ensure_data_dict(data)

    # Handle case where data is not provided but x, y, and z are
    if data is None and x is not None and y is not None and z is not None:
        # Create data dict from x, y, and z lists
        if isinstance(x, list) and isinstance(y, list) and isinstance(z, list):
            data = {'x': x, 'y': y, 'z': z}
            x_col = 'x'
            y_col = 'y'
            z_col = 'z'
        else:
            # If x, y, z are not lists, treat them as column names that need data
            raise ValueError("When data is None, x, y, and z must be lists")
    elif data is not None:
        # Use provided data and column names
        x_col = x
        y_col = y
        z_col = z
    else:
        raise ValueError("Either data must be provided, or x, y, and z must be provided")
    
    x_data = data.get(x_col)
    y_data = data.get(y_col)
    z_data = data.get(z_col)
    color_data = data.get(color)
    size_data = data.get(size)
    text_data = data.get(text)
    hover_name_data = data.get(hover_name)
    hover_data_dict = {k: data.get(k) for k in hover_data or []}

    # Handle case where color is passed directly as a list (not as a column name)
    if color_data is None and color is not None and isinstance(color, list):
        color_data = color

    # Handle case where size is passed directly as a list (not as a column name)
    if size_data is None and size is not None and isinstance(size, list):
        size_data = size

    # Handle case where text is passed directly as a list (not as a column name)
    if text_data is None and text is not None and isinstance(text, list):
        text_data = text

    # Handle case where hover_data is passed directly as a list (not as a column name)
    if hover_data is not None and isinstance(hover_data, list):
        # Convert hover_data list to a dictionary with indices as keys
        hover_data_dict = {f"hover_{i}": hover_data[i] for i in range(len(hover_data))}

    if color_data is None or isinstance(color_data, str):
        trace = remove_none({
            "type": "scatter3d",
            "mode": "markers",
            "x": x_data,
            "y": y_data,
            "z": z_data,
            "marker": {
                "color": color_data if color_data else None,
                "size": size_data if size_data else None
            },
            "text": text_data,
            **_hover_fields(hover_name_data, hover_data_dict)
        })
        traces.append(trace)
    else:
        # Handle color data that might contain lists or other unhashable types
        try:
            # Convert all color values to strings to make them hashable
            color_strings = [str(c) for c in color_data]
            color_categories = _unique_ordered(color_strings, sort=False)
        except (TypeError, AttributeError):
            # Fallback: treat as single color
            color_categories = [str(color_data)]
       
        for color_val in color_categories:
            # Find indices where color matches (using original color_data)
            filtered_indices = [i for i, c in enumerate(color_data) if str(c) == color_val]
            filtered_x = [x_data[i] for i in filtered_indices]
            filtered_y = [y_data[i] for i in filtered_indices]
            filtered_z = [z_data[i] for i in filtered_indices]
            filtered_size = [size_data[i] for i in filtered_indices] if size_data else None
            filtered_text = [text_data[i] for i in filtered_indices] if text_data else None
            filtered_hover_name = [hover_name_data[i] for i in filtered_indices] if hover_name_data else None
            filtered_hover_data = {k: [v[i] for i in filtered_indices] for k, v in hover_data_dict.items()} if hover_data_dict else None

            trace = remove_none({
                "type": "scatter3d",
                "mode": "markers",
                "x": filtered_x,
                "y": filtered_y,
                "z": filtered_z,
                "name": str(color_val),
                "marker": {
                    "size": filtered_size
                },
                "text": filtered_text,
                **_hover_fields(filtered_hover_name, filtered_hover_data)
            })
            traces.append(trace)

    layout = remove_none({
        "title": title,
        "height": height,
        "width": width,
        "scene": {
            "xaxis": {"title": xaxis_title or "X"},
            "yaxis": {"title": yaxis_title or "Y"},
            "zaxis": {"title": zaxis_title or "Z"}
        }
    })

    # Enhanced axis customization for 3D plots
    if xaxis_range or yaxis_range or zaxis_range:
        if xaxis_range:
            layout['scene']['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['scene']['yaxis']['range'] = yaxis_range
        if zaxis_range:
            layout['scene']['zaxis']['range'] = zaxis_range
    
    # Return JSON string with special prefix for JavaScript detection
    import json
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

def imshow(data, title=None, height=None, width=None, config=None, static=None,
           # Enhanced axis customization
           xaxis_title=None, yaxis_title=None, xaxis_range=None, yaxis_range=None):
    
    traces = []
    layout = {}
    
    # Handle different data types
    if isinstance(data, list):
        # If data is a list of lists (2D array)
        if all(isinstance(row, list) for row in data):
            z_data = data
        else:
            # If data is a flat list, try to reshape it
            z_data = [data]
    elif hasattr(data, 'tolist'):
        # Handle numpy arrays
        z_data = data.tolist()
    else:
        z_data = data
    
    trace = remove_none({
        "type": "heatmap",
        "z": z_data,
    })
    
    traces.append(trace)
    
    layout = remove_none({
        "title": title,
        "height": height,
        "width": width,
    })

    # Enhanced axis customization
    if xaxis_title or yaxis_title or xaxis_range or yaxis_range:
        if 'xaxis' not in layout:
            layout['xaxis'] = {}
        if 'yaxis' not in layout:
            layout['yaxis'] = {}
            
        if xaxis_title:
            layout['xaxis']['title'] = xaxis_title
        if yaxis_title:
            layout['yaxis']['title'] = yaxis_title
        if xaxis_range:
            layout['xaxis']['range'] = xaxis_range
        if yaxis_range:
            layout['yaxis']['range'] = yaxis_range
    
    # Return PlotlyFigure so callers can use to_plotly_json_str() like other px functions
    clean_config = config or {}
    if resolve_static(static):
        clean_config = dict(clean_config)
        clean_config["staticPlot"] = True
    plot_data = {
        "type": "plotly",
        "data": traces,
        "layout": remove_none(layout),
        "config": clean_config
    }
    return PlotlyFigure(plot_data)

# Add a simple test function to verify the module works