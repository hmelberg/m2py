"""dash v2 - Brython-adapter. Bygger ALDRI kort/layout-DOM selv;
alt gaar via window.Dash (js/dash.js). Data krysser grensen som JSON."""
from browser import window
import sys
import io
import json


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
    """Avspillbar slider (K3): verdien animeres min->max (evt. loop) i UI-et.
    Kun eksplisitt form - ingen implisitt kwarg-mapping til denne."""
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


def _infer(name, value):
    """Implisitt kwarg->widget-mapping (spec 4.2). Rekkefolgen betyr noe:
    bool foer int (bool er subklasse av int)."""
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
        "Bruk list(...) rundt verdien for en nedtrekksmeny (funker ogsaa paa "
        "pandas Series via .tolist()), eller oppgi en widget eksplisitt "
        "(dash.slider/dropdown/checkbox/textfield/numberfield/play)."
        % (name, value, type(value).__name__))


def _figure_spec(x):
    """Duck-typet plotly-gjenkjenning. plotly_express_brython.PlotlyFigure
    (matplotlib-shimmen bygger paa denne) har verken to_plotly_json() eller
    to_dict() - den eksponerer to_plotly_json_str(), samme metode
    brython_runner.py bruker for __micro_transform_start_figure__-embedding.
    Den strengen er allerede kjoert gjennom json_safe() (NaN-sentinel,
    datetime, osv. -> JSON-trygge verdier), saa den prioriteres foran
    raa .data/.layout-attributter som ikke faar den saneringen."""
    if hasattr(x, "to_plotly_json_str"):
        try:
            d = json.loads(x.to_plotly_json_str())
            if isinstance(d, dict) and "data" in d:
                return d
        except Exception:
            pass
    for m in ("to_plotly_json", "to_dict"):
        if hasattr(x, m):
            try:
                d = getattr(x, m)()
                if isinstance(d, dict) and "data" in d and "layout" in d:
                    return d
            except Exception:
                pass
    if isinstance(x, dict) and "data" in x and "layout" in x:
        return x
    if hasattr(x, "data") and hasattr(x, "layout") and not hasattr(x, "to_html"):
        try:
            return {"data": list(x.data), "layout": dict(x.layout)}
        except Exception:
            pass
    return None


_IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")

_NNBSP = " "          # smalt hardt mellomrom (norsk tusenskille)
_MINUS = "−"          # minustegn (ikke bindestrek), for eksplisitt fortegn


def _fmt_norsk(value, fmt):
    """format(value, fmt) med engelsk gruppering oversatt til norsk:
    ','->smalt hardt mellomrom (tusenskille), '.'->',' (desimalskille)."""
    s = format(value, fmt)
    return s.translate(str.maketrans({",": _NNBSP, ".": ","}))


def _fmt_default_norsk(value):
    """fmtNumber-ekvivalent (js/dash.js sin fmtNumber) naar ingen fmt er oppgitt:
    heltall vises som heltall, ellers avrundet til 2 desimaler uten
    unodvendige etternuller - deretter norsk gruppering/desimalskille."""
    r = round(value, 2)
    if r == int(r):
        s = format(int(r), ",")
    else:
        s = format(r, ",.2f").rstrip("0").rstrip(".")
    return s.translate(str.maketrans({",": _NNBSP, ".": ","}))


def _delta(value, ref, fmt, bra):
    # Guard against non-finite ref (nan/inf)
    if ref != ref or abs(ref) == float("inf"):
        return None
    diff = value - ref
    if diff > 0:
        direction = "opp"
    elif diff < 0:
        direction = "ned"
    else:
        direction = "flat"
    good = (direction == bra) or direction == "flat"
    text = _fmt_norsk(abs(diff), fmt) if fmt else _fmt_default_norsk(abs(diff))
    sign = "+" if diff >= 0 else _MINUS
    return {"text": sign + text, "dir": direction, "good": bool(good)}


def _number_payload(value, unit, fmt, ref, bra):
    return {
        "kind": "number",
        "value": value,
        "unit": unit or "",
        "text": _fmt_norsk(value, fmt) if fmt else None,
        "delta": _delta(value, ref, fmt, bra) if ref is not None else None,
    }


def _initial_raw(id_):
    """Hent lagrede raa-startverdier for et card-/dash-id via window.Dash.initialValues
    (K2). Robust mot at JS-siden mangler funksjonen (eldre bygg) eller returnerer
    noe uventet - da brukes python-defaultene som vanlig."""
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


def _payload(x, unit=None, fmt=None, ref=None, bra="opp"):
    """add(x)-dispatch (spec 5). Rekkefolgen er prioritetsrekkefolgen."""
    if x is None:
        return {"kind": "text", "text": ""}
    if isinstance(x, bool):
        return {"kind": "text", "text": str(x)}
    if isinstance(x, (int, float)):
        if x != x or abs(x) == float("inf"):   # nan / inf — json.dumps -> literal NaN/Infinity, JSON.parse crashes in JS
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
    if hasattr(x, "to_html"):
        try:
            ncols = len(list(getattr(x, "columns", []) or []))
        except Exception:
            ncols = 0
        return {"kind": "table", "html": x.to_html(), "cols": ncols}
    if hasattr(x, "elt") or hasattr(x, "nodeType"):
        return {"kind": "node"}
    return {"kind": "text", "text": repr(x)}


def _dom_node(x):
    return getattr(x, "elt", x)


def _func_params(f):
    code = f.__code__
    return list(code.co_varnames[:code.co_argcount + code.co_kwonlyargcount])


class Dash:
    def __init__(self, title="", layout=None):
        self._cards = {}       # card_id -> dict(func, widgets, unit, last)
        self._shared = {}      # navn -> Widget
        self._shared_vals = {} # navn -> Python-verdi
        self.id = window.Dash.create(json.dumps({"title": title, "layout": layout}))

    # ---- offentlig API ----

    def add(self, x, title=None, at=None, unit=None, fmt=None, ref=None, bra="opp", **kwargs):
        if callable(x) and not isinstance(x, Widget):
            self._add_func(x, title, at, unit, kwargs, fmt=fmt, ref=ref, bra=bra)
            return
        p = _payload(x, unit=unit, fmt=fmt, ref=ref, bra=bra)
        opts = {"title": title, "area": at, "content": p}
        node = _dom_node(x) if p["kind"] == "node" else None
        window.Dash.addCard(self.id, json.dumps(opts), None, node)

    def controls(self, **kwargs):
        # re-registrerer HELE settet hver gang (self._shared akkumuleres over kall);
        # window.Dash.addControls erstatter hele toppstripa i JS, saa den gamle
        # on_change-closuren under blir aldri kalt igjen (ingen dobbel-fyring).
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

        window.Dash.addControls(self.id, json.dumps(specs), on_change)
        # K2: gjenopprett delte startverdier fra delings-URL-en (om noen), foer
        # kortene under kjoeres paa nytt for foerste gang med disse verdiene.
        self._shared_vals.update(_map_raw(_initial_raw(self.id), self._shared))
        # kort lagt til foer controls(): kjoer paa nytt med delte (evt. gjenopprettede) defaults
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
                                  on_change if specs else None, None)
        holder["cid"] = cid
        self._cards[cid] = card
        if specs:
            # K2: gjenopprett kortets egne startverdier fra delings-URL-en (om noen)
            # foer foerste kjoering, slik at foerste render matcher den delte lenken.
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
