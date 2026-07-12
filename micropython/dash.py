"""dash v2 - MicroPython-adapter. Bygger ALDRI kort/layout-DOM selv;
alt gaar via window.Dash (js/dash.js). Data krysser grensen som JSON.

Divergerende kopi av brython/dash.py (kopiert 2026-07-12, Task 6, fra v3-
adapteren - commit "refactor(dash): brython-adapter sender raa number-
payload (v3)"). Denne fila kjoerer under unix-micropython/wasm-micropython
(Task 3-motoren), IKKE under Brython. Endringer her skal IKKE flyte
tilbake til brython/dash.py uten separat vurdering.

Dialektfeller fikset i denne porten:
  1. `from browser import window`: Brython-spesifikk. MicroPython-motoren
     (js/micropython-engine.js) eksponerer window paa `js`-modulen
     (jsffi), ikke `browser`. Erstattet med `from js import window`.
  2. `sys.stdout = buf` i Dash._run (fase 0-funn c_sys_stdout_assign:
     FEIL i baade unix- og wasm-bygg, se micropython/NOTAT_fase0.md) -
     MicroPython tillater ikke sys.stdout-bytte. Runneren skriver ALT via
     print, og motoren samler linjene i en delt buffer; callback-utskrift
     fanges i stedet ved aa merke/splitte DEN bufferen rundt kallet, via
     window.__mpyCaptureStart()/__mpyCaptureEnd() (js/micropython-engine.js).
     __mpyCaptureEnd() returnerer teksten som ble printet siden Start, med
     '\\n' mellom linjer (samme semantikk som buf.getvalue() ga - linjene
     fjernes ogsaa fra motorens hovedbuffer, saa de lekker ikke ut i
     script-nivaa-teksten). __mpyCaptureEnd() SPLITTER (fjerner) fra
     bufferen - kan derfor bare kalles EN gang per _run()-kall.

     RETTET (Task 6 critical review, denne runden): forrige versjon la
     `_payload(res, ...)`/`_dom_node(res)` i en `else:`-klausul (kjoert kun
     naar `card["func"](**vals)` IKKE kastet). En `else:`-klausul paa
     try/except fanges ALDRI av samme try sine except-grener - saa unntak
     fra `_payload`/`_dom_node` (f.eks. et objekt med en `to_html()` som
     kaster, eller et pending-SQL-unntak fra duckdb-broen kastet under
     rendering) propagerte ukontrollert ut av `_run()` i stedet for aa bli
     et `{"kind": "error", ...}`-kort - stikk i strid med
     `brython/dash.py`s `_run()`, der HELE `try`-blokka (funksjonskallet OG
     payload-byggingen) er dekket av EN felles `except BaseException as e`.
     Fikset ved aa flytte payload-byggingen tilbake INN i try-blokka (samme
     dekning som originalen), og bruke et NESTET `try/finally` rundt bare
     selve funksjonskallet for aa garantere at `__mpyCaptureEnd()` kalles
     NOYAKTIG en gang per `_run()`, uansett om funksjonskallet lykkes eller
     kaster - analogt med at originalens `sys.stdout = old` alltid kjorer,
     uansett utfall. (Ren `try/finally` rundt HELE
     kall+payload-byggingen duger ikke: `__mpyCaptureEnd()` baade LESER og
     TOMMER bufferen i ett destruktivt kall, mens originalens `buf` kan
     leses med `buf.getvalue()` naar som helst - ogsaa FOR den formelle
     "restore"-posisjonen. Siden avgjorelsen "tekst-kort vs.
     `_payload(res)`" trenger den fangede teksten FOR payload-byggingen (som
     igjen maa vaere inne i try for aa faa unntaksdekning), maa
     `__mpyCaptureEnd()` kalles rett etter funksjonskallet, ikke etter hele
     try-blokka - `_payload`/`_dom_node` skriver uansett aldri til den
     fangede stroemmen, saa dette bevarer originalens semantikk selv om
     "restore"-tidspunktet ikke er bokstavelig identisk.) `import
     sys`/`import io` er fjernet - ingenting annet i fila brukte dem.
  3. `_func_params(f)` brukte `f.__code__.co_varnames` for aa finne
     parameternavnene til en add()-et funksjon. MicroPython-funksjonsobjekter
     har IKKE `__code__` (verifisert - ingen co_varnames/co_argcount), bare
     `__name__`. `dash.add(<funksjon>)` kraster derfor under MicroPython med
     den opprinnelige koden. Fikset med et fallback-spor: naar `__code__`
     mangler (AttributeError), tekst-parses parameterlisten i stedet ut fra
     kildeloggen motoren fører (`window.__mpySource()`,
     js/micropython-engine.js sin `__scriptLog`/`run()`-hook) - let bakfra
     etter siste `def <navn>(`, slice til matchende ')' (parentesdybde,
     hopper over anforselstegn), splitt paa komma paa dybde 0, og strip
     *args/**kwargs/'/' samt annotasjoner/defaults fra hvert navn (se
     `_parse_params_from_source`/`_find_def_open_paren`/`_match_paren`/
     `_split_top_level` under). `__code__`-veien proves ALLTID foerst og
     brukes uendret der den finnes (CPython/pytest, ev. fremtidige
     MicroPython-bygg med `__code__`). Lambdas (`__name__ == '<lambda>'`)
     og funksjoner som ikke finnes i loggen kaster en tydelig norsk
     ValueError i stedet for aa stille returnere en tom parameterliste -
     en stille tom liste ville gitt et dashboard-kort som ignorerer alle
     widget-verdiene uten aa si ifra. Delfelle: MicroPython-`str` mangler
     `.isalnum()` (finnes i CPython) - ordgrense-sjekken i
     `_find_def_open_paren` bruker derfor `_is_ident_char` (isalpha()/
     isdigit()/'_'  i stedet).
"""
from js import window                # MicroPython: js-modulen (jsffi)
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
    """Duck-typet plotly-gjenkjenning. plotly_express_mpy.PlotlyFigure
    (matplotlib-shimmen bygger paa denne) har verken to_plotly_json() eller
    to_dict() - den eksponerer to_plotly_json_str(), samme metode
    micropython_runner.py bruker for __micro_transform_start_figure__-embedding.
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


def _number_payload(value, unit, fmt, ref, bra):
    """Number-payload v3: raa verdier — js/dash.js formaterer (norsk
    gruppering, delta). ref saniteres her: json.dumps av nan/inf gir
    literal NaN/Infinity som knekker JSON.parse i JS."""
    if ref is not None and (ref != ref or abs(ref) == float("inf")):
        ref = None
    return {"kind": "number", "value": value, "unit": unit or "",
            "fmt": fmt, "ref": ref, "bra": bra}



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


def _is_ident_char(c):
    """MicroPython-fella: str har IKKE .isalnum() (verifisert). isalpha()/
    isdigit() finnes, saa identifikator-tegn (for ordgrense-sjekk under)
    bygges av de to pluss understrek."""
    return c.isalpha() or c.isdigit() or c == "_"


def _match_paren(src, open_idx):
    """src[open_idx] maa vaere '('. Returnerer indeksen til den MATCHENDE
    ')' - teller parentes/brakett/brace-dybde og hopper over innhold i
    enkle/doble anforselstegn (\\-escape respekteres), saa defaults som
    `b=(1, 2)` eller `c="x,y"` ikke forstyrrer tellingen."""
    depth = 0
    quote = None
    i = open_idx + 1
    n = len(src)
    while i < n:
        c = src[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c == '"' or c == "'":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        i += 1
    raise ValueError("dash: ubalanserte parenteser i funksjonsdefinisjonen")


def _split_top_level(s, sep):
    """Splitt s paa sep, men KUN paa dybde 0 (parentes/brakett/brace) og
    utenfor anforselstegn - samme skjerming som _match_paren."""
    parts = []
    depth = 0
    quote = None
    start = 0
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c == '"' or c == "'":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return parts


def _find_def_open_paren(src, name):
    """Finn INDEKSEN TIL '(' for den SISTE (bakerste) `def <name>(`-
    definisjonen i src. src kan vaere flere scripts satt sammen (se
    js/micropython-engine.js sin __mpySource()) - "siste vinner" gjelder
    baade innad i ett script (omdefinering) og paa tvers av script-kjoeringer
    i loggen (nyeste script sist). Returnerer None hvis ingen match.
    Ordgrense-sjekk paa begge sider av <name> hindrer at f.eks. navnet
    'foo' feilaktig matcher `def foo2(` eller `def xfoo(`."""
    target = "def " + name
    bound = len(src)
    while True:
        idx = src.rfind(target, 0, bound)
        if idx == -1:
            return None
        before_ok = idx == 0 or not _is_ident_char(src[idx - 1])
        after = idx + len(target)
        j = after
        while j < len(src) and src[j] in " \t":
            j += 1
        if before_ok and j < len(src) and src[j] == "(":
            return j
        bound = idx  # ikke et gyldig treff her - let videre bakover foer det


def _parse_params_from_source(src, name):
    """Fallback-parser for MicroPython (ingen __code__): let bakfra etter
    `def <name>(`, slice ut parameterlisten til den matchende ')', splitt
    paa komma (dybde 0), og strip *args/**kwargs/'/' samt annotasjoner
    (etter ':') og defaults (etter '=') fra hvert gjenvaerende navn.
    Kaster ValueError (norsk feiltekst) hvis funksjonen ikke finnes -
    ALDRI stille tom liste, siden det ville gitt et dashboard-kort som
    stille ignorerer alle widget-verdier."""
    open_idx = _find_def_open_paren(src, name)
    if open_idx is None:
        raise ValueError(
            "dash: fant ikke parametrene til funksjonen '%s' — definer den "
            "med def paa toppnivaa i scriptet." % name)
    close_idx = _match_paren(src, open_idx)
    params_src = src[open_idx + 1:close_idx]
    out = []
    for tok in _split_top_level(params_src, ","):
        t = tok.strip()
        if not t or t.startswith("*") or t == "/":
            continue
        cut = len(t)
        for ch in (":", "="):
            p = t.find(ch)
            if p != -1 and p < cut:
                cut = p
        t = t[:cut].strip()
        if t:
            out.append(t)
    return out


def _func_params(f):
    """MicroPython-dialektfelle: funksjonsobjekter mangler __code__ (verifisert
    i fase 0 - ingen co_varnames/co_argcount), i motsetning til CPython/pytest
    (og ev. fremtidige MicroPython-bygg som FAAR __code__). __code__-veien
    proves derfor foerst og brukes uendret der den finnes; MicroPython faller
    til AttributeError og gaar videre til tekst-parsing av kildeloggen
    (window.__mpySource(), se js/micropython-engine.js) - se
    _parse_params_from_source over. Lambdas har __name__ == '<lambda>' og kan
    ikke identifiseres i kildeteksten paa denne maaten -> tydelig feil med
    hint om aa bruke def i stedet."""
    try:
        code = f.__code__
        return list(code.co_varnames[:code.co_argcount + code.co_kwonlyargcount])
    except AttributeError:
        pass
    name = getattr(f, "__name__", None)
    if not name or name == "<lambda>":
        raise ValueError(
            "dash: fant ikke parametrene til funksjonen '%s' — definer den "
            "med def (ikke lambda) paa toppnivaa i scriptet." % (name or "?"))
    try:
        source = window.__mpySource()
    except Exception:
        source = None
    if not source:
        raise ValueError(
            "dash: fant ikke parametrene til funksjonen '%s' — definer den "
            "med def paa toppnivaa i scriptet." % name)
    return _parse_params_from_source(source, name)


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
        node = None
        window.__mpyCaptureStart()
        try:
            try:
                res = card["func"](**vals)
            finally:
                # __mpyCaptureEnd() splitter (destruktivt) fra motorens
                # buffer - maa kalles NOYAKTIG en gang. Denne finally
                # garanterer det uansett om funksjonskallet lykkes eller
                # kaster, foer resten av try (payload-byggingen) faar
                # forsoke aa bruke teksten.
                tekst = window.__mpyCaptureEnd()
            if res is None and tekst.strip():
                p = {"kind": "text", "text": tekst.rstrip()}
            else:
                p = _payload(res, unit=card["unit"], fmt=card.get("fmt"),
                             ref=card.get("ref"), bra=card.get("bra", "opp"))
                if p["kind"] == "node":
                    node = _dom_node(res)
        except BaseException as e:
            if getattr(e, "__brython_pending__", False):
                # duckdb-broens replay-signal: replay virker bare for hele
                # script-kjøringer, ikke widget-callbacks. Forhåndskjør
                # spørringene på script-nivå så callbacks treffer cachen.
                p = {"kind": "error",
                     "message": ("SQL-sporringen er ikke i cache. Kjor den "
                                 "(for alle kontrollverdier) pa script-niva "
                                 "forst - widget-endringer kan ikke vente pa "
                                 "DuckDB.")}
            elif isinstance(e, Exception):
                p = {"kind": "error", "message": "%s: %s" % (type(e).__name__, e)}
            else:
                raise
        window.Dash.updateCard(cid, json.dumps(p), node)
