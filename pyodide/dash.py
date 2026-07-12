"""dash v2 - pyodide-adapter (spec 2026-07-12-dash-v2-runtimes-design.md §4).
Egen kopi av brython/dash.py-moensteret - IKKE delt fil (besluttet i brainstorm).
Bygger ALDRI kort/layout-DOM selv; alt gaar via window.Dash (js/dash.js).
Data krysser grensen som JSON-strenger; callbacks krysser som PyProxy
(pyodide kjoerer paa hovedtraaden - direkte kall, ingen koe)."""
import io
import json
import sys

from js import window

try:
    from pyodide.ffi import create_proxy
except ImportError:          # CPython (pytest med js-stub): ingen proxy noedvendig
    def create_proxy(f):
        return f


# ---- proxy-livssyklus: destruer callbacks for dashboards hvis DOM er borte ----

_live = []   # [(dash_id, [proxies])]


def _reap():
    keep = []
    for dash_id, proxies in _live:
        alive = False
        try:
            alive = bool(window.Dash.isAlive(dash_id))
        except Exception:
            pass
        if alive:
            keep.append((dash_id, proxies))
        else:
            for p in proxies:
                try:
                    p.destroy()
                except Exception:
                    pass
    _live[:] = keep


def dashboard(title="", layout=None):
    return Dash(title, layout)


class Widget:
    def __init__(self, kind, values=None, **spec):
        self.kind = kind
        self.spec = {k: v for k, v in spec.items() if v is not None}
        self.values = values  # dropdown: original-objektene (indeks -> verdi)

    def to_spec(self, name):
        d = dict(self.spec)
        d["type"] = self.kind
        d["name"] = name
        return d

    def default(self):
        if self.kind == "dropdown":
            return self.values[self.spec.get("index", 0)]
        if self.kind in ("slider", "play"):
            return self.spec.get("default", self.spec["min"])
        return self.spec.get("default")

    def from_raw(self, raw):
        """JS-raaverdi -> Python-verdi."""
        if self.kind == "dropdown":
            return self.values[int(raw)]
        if self.kind in ("slider", "numberfield", "play"):
            v = float(raw)
            bounds = [self.spec.get(k) for k in ("min", "max", "step", "default")]
            ints = all(isinstance(b, int) for b in bounds if b is not None)
            return int(v) if ints and v == int(v) else v
        if self.kind == "checkbox":
            return bool(raw)
        return raw


def slider(min, max, step=None, default=None, label=None):
    return Widget("slider", min=min, max=max, step=step,
                  default=default if default is not None else min, label=label)


def play(min, max, step=None, default=None, interval=600, loop=False, label=None):
    return Widget("play", min=min, max=max, step=step,
                  default=default if default is not None else min,
                  interval=interval, loop=loop, label=label)


def dropdown(*options, default=None, label=None):
    if len(options) == 1 and isinstance(options[0], (list, tuple)):
        opts = list(options[0])
    else:
        opts = list(options)
    idx = opts.index(default) if default in opts else 0
    return Widget("dropdown", values=opts,
                  options=[str(o) for o in opts], index=idx, label=label)


def checkbox(default=False, label=None):
    return Widget("checkbox", default=bool(default), label=label)


def textfield(default="", label=None):
    return Widget("textfield", default=str(default), label=label)


def numberfield(default=0, min=None, max=None, step=None, label=None):
    return Widget("numberfield", default=default, min=min, max=max,
                  step=step, label=label)


def _scalar(value):
    """numpy-skalar -> python int/float/bool (json.dumps taaler ikke numpy)."""
    if type(value).__module__ == "numpy" and hasattr(value, "item") \
            and not hasattr(value, "__len__"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _infer(name, value):
    """Implisitt kwarg->widget-mapping (spec v1 4.2). Rekkefolgen betyr noe:
    bool foer int (bool er subklasse av int)."""
    value = _scalar(value)
    if isinstance(value, Widget):
        return value
    if isinstance(value, bool):
        return checkbox(default=value)
    if isinstance(value, tuple) and len(value) in (2, 3) \
            and all(isinstance(v, (int, float)) for v in value):
        return slider(*value)
    if isinstance(value, (list, set)) or hasattr(value, "tolist"):
        seq = value.tolist() if hasattr(value, "tolist") else list(value)
        return dropdown(*seq)
    if isinstance(value, str):
        return textfield(default=value)
    if isinstance(value, (int, float)):
        return numberfield(default=value)
    if isinstance(value, tuple):
        raise ValueError(
            "dash: %s=%r er en tuppel, men ikke (min,max[,steg]) med tall. "
            "Bruk list(...) rundt verdien for aa lage en nedtrekksmeny." % (name, value))
    if isinstance(value, dict):
        raise ValueError(
            "dash: %s=%r er en dict - ikke stottet direkte som kontroll. "
            "Bruk list(...) rundt noklene eller verdiene for aa lage en nedtrekksmeny."
            % (name, value))
    raise ValueError(
        "dash: kan ikke lage kontroll av %s=%r (type %s). "
        "Bruk list(...) rundt verdien for en nedtrekksmeny, eller oppgi en "
        "widget eksplisitt (dash.slider/dropdown/checkbox/textfield/"
        "numberfield/play)." % (name, value, type(value).__name__))


def _figure_spec(x):
    """Ekte plotly: Figure har to_json() (NaN-trygg JSON-streng).
    data+layout-guarden hindrer at pandas-objekter (som ogsaa har to_json,
    men ikke .layout) treffer grenen."""
    if hasattr(x, "to_json") and hasattr(x, "data") and hasattr(x, "layout"):
        try:
            d = json.loads(x.to_json())
            if isinstance(d, dict) and "data" in d:
                return d
        except Exception:
            pass
    if isinstance(x, dict) and "data" in x and "layout" in x:
        return x
    return None


def _mpl_image(x):
    """Ekte matplotlib Figure/Axes (inkl. df.plot()-retur) -> PNG data-URI.
    Forsokes kun naar scriptet alt har importert matplotlib."""
    if "matplotlib" not in sys.modules:
        return None
    fig = x if hasattr(x, "savefig") else getattr(x, "figure", None)
    if fig is None or not hasattr(fig, "savefig"):
        return None
    import base64
    import matplotlib.pyplot as plt
    fig.set_size_inches(7.2, 4.4)   # fyller innholdsflaten uten letterboxing (v1 §7)
    fig.set_dpi(100)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def _number_payload(value, unit, fmt, ref, bra):
    """Number-payload v3: raa verdier - js/dash.js formaterer. ref saniteres:
    json.dumps av nan/inf gir literal NaN/Infinity som knekker JSON.parse."""
    ref = _scalar(ref)
    if ref is not None and (ref != ref or abs(ref) == float("inf")):
        ref = None
    return {"kind": "number", "value": value, "unit": unit or "",
            "fmt": fmt, "ref": ref, "bra": bra}


def _payload(x, unit=None, fmt=None, ref=None, bra="opp"):
    """add(x)-dispatch (spec v1 §5). Rekkefolgen er prioritetsrekkefolgen."""
    x = _scalar(x)
    if x is None:
        return {"kind": "text", "text": ""}
    if isinstance(x, bool):
        return {"kind": "text", "text": str(x)}
    if isinstance(x, (int, float)):
        if x != x or abs(x) == float("inf"):
            return {"kind": "text", "text": str(x)}
        return _number_payload(x, unit, fmt, ref, bra)
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("data:image") or (
                s.split("?")[0].lower().endswith(_IMG_EXT)
                and (s.startswith("http") or "/" in s) and "\n" not in s):
            return {"kind": "image", "src": s}
        return {"kind": "markdown", "text": x}
    fig = _figure_spec(x)
    if fig is not None:
        return {"kind": "figure", "spec": fig}
    src = _mpl_image(x)
    if src:
        return {"kind": "image", "src": src}
    if hasattr(x, "to_html"):
        try:
            ncols = len(list(getattr(x, "columns", []) or []))
        except Exception:
            ncols = 0
        return {"kind": "table", "html": x.to_html(), "cols": ncols}
    if hasattr(x, "to_frame"):      # pandas Series (har ikke egen to_html)
        try:
            return {"kind": "table", "html": x.to_frame().to_html(), "cols": 1}
        except Exception:
            pass
    if hasattr(x, "nodeType"):      # DOM-element via JsProxy (escape-luke)
        return {"kind": "node"}
    return {"kind": "text", "text": repr(x)}


def _dom_node(x):
    return x


def _func_params(f):
    code = f.__code__
    return list(code.co_varnames[:code.co_argcount + code.co_kwonlyargcount])


def _initial_raw(id_):
    """Lagrede raa-startverdier (K2/URL-state) via window.Dash.initialValues."""
    try:
        raw_json = window.Dash.initialValues(id_)
    except Exception:
        return {}
    if not raw_json:
        return {}
    try:
        raw = json.loads(raw_json)
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _map_raw(raw, widgets):
    out = {}
    for n, r in raw.items():
        if n in widgets:
            try:
                out[n] = widgets[n].from_raw(r)
            except Exception:
                pass
    return out


class Dash:
    def __init__(self, title="", layout=None):
        self._cards = {}       # card_id -> dict(func, widgets, unit, ...)
        self._shared = {}      # navn -> Widget
        self._shared_vals = {} # navn -> Python-verdi
        self._proxies = []
        self.id = window.Dash.create(json.dumps({"title": title, "layout": layout}))
        _reap()
        _live.append((self.id, self._proxies))

    def _proxy(self, f):
        p = create_proxy(f)
        self._proxies.append(p)
        return p

    # ---- offentlig API ----

    def add(self, x, title=None, at=None, unit=None, fmt=None, ref=None,
            bra="opp", **kwargs):
        if callable(x) and not isinstance(x, Widget):
            self._add_func(x, title, at, unit, kwargs, fmt=fmt, ref=ref, bra=bra)
            return
        p = _payload(x, unit=unit, fmt=fmt, ref=ref, bra=bra)
        opts = {"title": title, "area": at, "content": p}
        node = _dom_node(x) if p["kind"] == "node" else None
        window.Dash.addCard(self.id, json.dumps(opts), None, node)

    def controls(self, **kwargs):
        # re-registrerer HELE settet hver gang; addControls erstatter
        # toppstripa i JS, saa gamle closures fyres aldri igjen.
        for name, value in kwargs.items():
            w = _infer(name, value)
            self._shared[name] = w
            self._shared_vals[name] = w.default()
        specs = [w.to_spec(n) for n, w in self._shared.items()]

        def on_change(values_json):
            raw = json.loads(values_json)
            for n, r in raw.items():
                if n in self._shared:
                    self._shared_vals[n] = self._shared[n].from_raw(r)
            for cid, card in self._cards.items():
                if set(card["params"]) & set(self._shared):
                    self._run(cid)

        window.Dash.addControls(self.id, json.dumps(specs), self._proxy(on_change))
        self._shared_vals.update(_map_raw(_initial_raw(self.id), self._shared))
        for cid, card in self._cards.items():
            if set(card["params"]) & set(self._shared):
                self._run(cid)

    # ---- internt ----

    def _add_func(self, func, title, at, unit, kwargs, fmt=None, ref=None, bra="opp"):
        widgets = {n: _infer(n, v) for n, v in kwargs.items()}
        specs = [w.to_spec(n) for n, w in widgets.items()]
        card = {
            "func": func,
            "widgets": widgets,
            "unit": unit,
            "fmt": fmt,
            "ref": ref,
            "bra": bra,
            "params": _func_params(func),
            "vals": {n: w.default() for n, w in widgets.items()},
        }
        holder = {}

        def on_change(values_json):
            raw = json.loads(values_json)
            for n, r in raw.items():
                if n in widgets:
                    card["vals"][n] = widgets[n].from_raw(r)
            self._run(holder["cid"])

        opts = {"title": title, "area": at, "controls": specs, "content": None}
        cid = window.Dash.addCard(self.id, json.dumps(opts),
                                  self._proxy(on_change) if specs else None, None)
        holder["cid"] = cid
        self._cards[cid] = card
        if specs:
            card["vals"].update(_map_raw(_initial_raw(cid), widgets))
        self._run(cid)
        return cid

    def _run(self, cid):
        card = self._cards[cid]
        vals = dict(card["vals"])
        for n in card["params"]:
            if n not in vals and n in self._shared_vals:
                vals[n] = self._shared_vals[n]
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        node = None
        try:
            res = card["func"](**vals)
            if res is None and buf.getvalue().strip():
                p = {"kind": "text", "text": buf.getvalue().rstrip()}
            else:
                p = _payload(res, unit=card["unit"], fmt=card.get("fmt"),
                             ref=card.get("ref"), bra=card.get("bra", "opp"))
                if p["kind"] == "node":
                    node = _dom_node(res)
        except Exception as e:
            p = {"kind": "error", "message": "%s: %s" % (type(e).__name__, e)}
        finally:
            sys.stdout = old
        window.Dash.updateCard(cid, json.dumps(p), node)
