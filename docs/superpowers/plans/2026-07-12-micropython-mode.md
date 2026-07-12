# MicroPython-modus — implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ny redigeringsmodus `micropython` (rask wasm-Python) med pandas + plotly express + dash + duckdb, ved siden av Brython-modusen.

**Architecture:** `js/micropython-engine.js` speiler `js/brython-engine.js` (samme `{text, error}`-kontrakt, lazy LIB_REGISTRY, duck-replay-bro); shimene er egne kopier i `micropython/` som får divergere fra Brython-variantene. Viktigste arkitekturforskjell: stdout fanges av motoren via `loadMicroPython({stdout})` — ikke av runneren (MicroPython tillater ikke `sys.stdout`-bytte).

**Tech Stack:** MicroPython WebAssembly-port `@micropython/micropython-webassembly-pyscript@1.27.0` (jsdelivr, ES-modul, 105 KB mjs + 424 KB wasm), ren Python-shimer, pytest (CPython) + unix-micropython (`brew install micropython`) for dialekt-tester.

**Spec:** `docs/superpowers/specs/2026-07-12-micropython-mode-design.md`

## Global Constraints

- Pin CDN-versjonen: `@micropython/micropython-webassembly-pyscript@1.27.0` (1.28.x er «-6»/preview-suffikset — ustabilt navneskjema).
- Brython-modusen røres IKKE — ingen endringer i `brython/` eller `js/brython-engine.js`.
- Embed-marker-protokollen er delt og uendret: `__micro_transform_start_` / `__micro_transform_end__`, pending-markør `__BRYTHON_PENDING__`, pending-attributt `__brython_pending__` (gjenbrukes med vilje så protokollen er én).
- All UI-tekst og feilmeldinger på norsk, samme stil som Brython-motoren.
- **Merge-gate:** Task 7 og 8 (index.html + eksempler/sync) starter IKKE før branchen `dash-v2-runtimes` er merget til master. Task 1–6 er uavhengige av den.
- Arbeid på branch `micropython-mode` fra master; push etter hver task (`git push -u origin micropython-mode`).
- Kjør `pytest` fra repo-roten: `python3 -m pytest micropython/tests/ -v`.
- Dialekt-tester kjøres med unix-porten: `micropython <fil>` (installeres i Task 1).

---

### Task 1: Fase 0-spike (GATE)

Formålet er å verifisere primitivene resten av planen bygger på, og måle boot-tid. **Hvis modul-trikset (sjekk `c_module_trick`) eller js-interop feiler, STOPP og rapporter — resten av planen avhenger av dem.** Enkeltsjekker som feiler (f.eks. `re.split`) er informasjon, ikke stopp — de har fallback i senere tasks.

**Files:**
- Create: `micropython/tests/spike_primitives.py`
- Create: `web_examples/mpy_spike.html`
- Create: `micropython/NOTAT_fase0.md`

**Interfaces:**
- Produces: `micropython/NOTAT_fase0.md` med målt boot-tid og OK/FEIL-liste som Task 2–6 slår opp i.

- [ ] **Step 1: Installer unix-porten av MicroPython**

```bash
brew install micropython
micropython -c "print('hei')"
```
Forventet: `hei`. (Unix-porten har samme VM/dialekt som wasm-porten; stdlib-utvalget avviker litt — wasm-resultatene fra Step 4 er fasit ved avvik.)

- [ ] **Step 2: Skriv primitiv-sjekkene**

Opprett `micropython/tests/spike_primitives.py`:

```python
# spike_primitives.py — fase 0-sjekker for MicroPython-modusen. Kjøres BÅDE
# under unix-micropython (micropython spike_primitives.py) og i wasm-spiken
# (web_examples/mpy_spike.html). Ingen pytest — bare OK/FEIL-linjer.
import sys

def check(name, fn):
    try:
        fn()
        print('OK   ' + name)
    except BaseException as e:
        print('FEIL ' + name + ': ' + repr(e))

def c_compile_eval():
    assert eval(compile('1+1', '<t>', 'eval'), {}) == 2

def c_compile_exec():
    g = {}
    exec(compile('x = 41\nx += 1', '<t>', 'exec'), g)
    assert g['x'] == 42

def c_module_trick():
    # Bærebjelken i _register_module (Task 2): et vanlig objekt i sys.modules
    # må fungere for både `import m` og `from m import navn`.
    class _Mod:
        def __init__(self, name, g):
            self.__name__ = name
            self._g = g
        def __getattr__(self, k):
            try:
                return self._g[k]
            except KeyError:
                raise AttributeError(k)
    g = {'__name__': 'spikemod'}
    exec(compile('x = 42\ndef f():\n    return x', 'spikemod.py', 'exec'), g)
    sys.modules['spikemod'] = _Mod('spikemod', g)
    import spikemod
    assert spikemod.f() == 42
    from spikemod import x
    assert x == 42

def c_stringio():
    import io
    b = io.StringIO()
    b.write('abc')
    assert b.getvalue() == 'abc'

def c_print_exception():
    # _format_exc i runneren (Task 2) bruker denne under MicroPython
    import io
    try:
        1 / 0
    except ZeroDivisionError as e:
        buf = io.StringIO()
        sys.print_exception(e, buf)
        assert 'ZeroDivisionError' in buf.getvalue()

def c_sys_stdout_assign():
    # Forventet FEIL i MicroPython (readonly) — informasjonspunkt som
    # begrunner stdout-via-motoren-designet. OK i CPython.
    import io
    old = sys.stdout
    sys.stdout = io.StringIO()
    sys.stdout = old

def c_binascii_base64():
    import binascii
    assert binascii.a2b_base64('aGVp') == b'hei'

def c_json_floats():
    import json
    v = json.loads('{"a": [1.5, null]}')
    assert v['a'][0] == 1.5 and v['a'][1] is None
    assert '{:g}'.format(v['a'][0]) == '1.5'   # Brython-fella finnes IKKE her

def c_format_thousands():
    # Forventet FEIL i MicroPython ({:,} støttes ikke) — dokumentasjonspunkt
    assert '{:,}'.format(1234) == '1,234'

def c_re_split_class():
    import re
    assert re.split('[_\\-]', 'a_b-c') == ['a', 'b', 'c']

def c_class_features():
    class A:
        def __init__(self):
            self._v = 1
        @property
        def v(self):
            return self._v
        @staticmethod
        def s():
            return 2
    class B(A):
        def __init__(self):
            super().__init__()
    assert B().v == 1 and A.s() == 2

def c_csv_missing():
    # Forventet FEIL i MicroPython (ingen csv-modul) — begrunner _parse_csv_text
    import csv  # noqa

def c_datetime_missing():
    # Forventet FEIL i wasm-porten — begrunner try/except rundt datetime i plotly-porten
    import datetime  # noqa

for _n, _f in sorted(globals().items()):
    if _n.startswith('c_'):
        check(_n, _f)
print('SPIKE FERDIG')
```

- [ ] **Step 3: Kjør under unix-micropython**

```bash
micropython micropython/tests/spike_primitives.py
```
Forventet: `OK` på alt unntatt (trolig) `c_sys_stdout_assign`, `c_format_thousands`, `c_csv_missing`, `c_datetime_missing` — og `SPIKE FERDIG` til slutt. Noter resultatet.

- [ ] **Step 4: Skriv wasm-spike-siden**

Opprett `web_examples/mpy_spike.html`:

```html
<!DOCTYPE html>
<!-- fase 0-spike: boot-tid + primitiver + rå (uportert) pandas_brython under
     MicroPython-wasm. Kjør: python3 -m http.server 8901 fra repo-roten,
     åpne http://localhost:8901/web_examples/mpy_spike.html -->
<html><head><meta charset="utf-8"><title>mpy-spike</title></head>
<body><pre id="out">laster…</pre>
<script type="module">
const out = document.getElementById('out');
const lines = [];
const show = () => { out.textContent = lines.join('\n'); };
const BASE = 'https://cdn.jsdelivr.net/npm/@micropython/micropython-webassembly-pyscript@1.27.0/';
try {
  const t0 = performance.now();
  const { loadMicroPython } = await import(BASE + 'micropython.mjs');
  const mp = await loadMicroPython({
    url: BASE + 'micropython.wasm',
    stdout: (l) => { lines.push(l); show(); },
    linebuffer: true,
  });
  lines.push('BOOT: ' + Math.round(performance.now() - t0) + ' ms (mål: Brython-boot til sml. er ~1500-3000 ms)');

  // js-interop: attributt, kall, Python-callback til JS
  window.__spikeCb = (f) => f(21);
  mp.runPython('import js\nprint("js.Math.floor:", js.Math.floor(1.5))\nprint("callback:", js.__spikeCb(lambda x: x * 2))');

  // primitivene (samme fil som unix-kjøringen)
  mp.runPython(await (await fetch('../micropython/tests/spike_primitives.py')).text());

  // RÅ pandas_brython: registrer via modul-trikset og prøv kjernebruk.
  // Feilene her er fase 0-funnene som styrer porte-jobben i Task 4.
  const psrc = await (await fetch('../brython/pandas_brython.py')).text();
  mp.globals.set('__pandas_src', psrc);
  const t2 = performance.now();
  mp.runPython(`
import sys
class _Mod:
    def __init__(self, name, g):
        self.__name__ = name
        self._g = g
    def __getattr__(self, k):
        try:
            return self._g[k]
        except KeyError:
            raise AttributeError(k)
_g = {'__name__': 'pandas_brython'}
try:
    exec(compile(__pandas_src, 'pandas_brython.py', 'exec'), _g)
    sys.modules['pandas_brython'] = _Mod('pandas_brython', _g)
    import pandas_brython as pd
    df = pd.DataFrame({'by': ['Oslo', 'Bergen', 'Oslo'], 'v': [10, 20, 30]})
    print('RAA PANDAS: DataFrame OK, len =', len(df))
    print('RAA PANDAS: groupby =', dict(df.groupby('by')['v'].mean()))
    print('RAA PANDAS: to_html OK' if '<table' in df.to_html() else 'RAA PANDAS: to_html MANGLER TABLE')
except BaseException as e:
    import io
    buf = io.StringIO()
    sys.print_exception(e, buf)
    print('RAA PANDAS FEILET:')
    print(buf.getvalue())
`);
  lines.push('rå-pandas-forsøk: ' + Math.round(performance.now() - t2) + ' ms');
} catch (e) {
  lines.push('SPIKE-KRASJ: ' + (e && e.message ? e.message : String(e)));
}
show();
</script></body></html>
```

- [ ] **Step 5: Kjør wasm-spiken i nettleser**

```bash
cd /Users/hom/Documents/GitHub/safestat && python3 -m http.server 8901
```
Åpne `http://localhost:8901/web_examples/mpy_spike.html`. Kopier hele `<pre>`-innholdet. Forventet: BOOT godt under 500 ms; js-interop OK; primitivene som i Step 3; rå-pandas enten OK eller en konkret feilliste.

- [ ] **Step 6: Skriv fase 0-notatet og vurder gaten**

Opprett `micropython/NOTAT_fase0.md` med: boot-tid (wasm), full OK/FEIL-liste fra begge kjøringer, rå-pandas-utfallet, og konklusjon «GATE BESTÅTT» / «GATE FEILET fordi …». Gaten er bestått hvis `c_module_trick`, js-interop (inkl. callback), `c_compile_*`, `c_stringio` og `c_print_exception` alle er OK i wasm.

- [ ] **Step 7: Commit og push**

```bash
cd /Users/hom/Documents/GitHub/safestat
git checkout -b micropython-mode master
git add micropython/tests/spike_primitives.py web_examples/mpy_spike.html micropython/NOTAT_fase0.md
git commit -m "spike: fase 0 MicroPython-wasm — primitiver, boot-tid, rå pandas"
git push -u origin micropython-mode
```

---

### Task 2: Runner — `micropython/micropython_runner.py`

**Files:**
- Create: `micropython/micropython_runner.py`
- Test: `micropython/tests/test_micropython_runner.py`

**Interfaces:**
- Consumes: modul-trikset verifisert i Task 1 (`c_module_trick`).
- Produces (kalles fra Task 3 via `mp.globals.get(...)`): `_execute_code(code) -> ''` (all output går via print), `_get_last_error() -> str` (`''`, traceback, eller `'__BRYTHON_PENDING__'`), `_register_module(name, source) -> ''|traceback`, `_alias_module(alias, canonical) -> ''|feiltekst`, `_snapshot()`, `_rollback()`, `_bind_datasets(spec_json) -> ''|traceback`. Brukerfunksjonen `show(*objs)` ligger i brukerglobals.

- [ ] **Step 1: Skriv de failende testene**

Opprett `micropython/tests/test_micropython_runner.py` — speiler `brython/tests/test_brython_runner.py`, men output leses med `capsys` (runneren printer i stedet for å returnere tekst):

```python
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import micropython_runner as mr

ES = '__micro_transform_start_'
EE = '__micro_transform_end__'


def run(capsys, code):
    ret = mr._execute_code(code)
    assert ret == ''          # kontrakt: all output via print, motoren samler
    return capsys.readouterr().out


def test_stdout_and_last_expression(capsys):
    out = run(capsys, 'print("hei")\n1 + 1')
    assert 'hei' in out and '2' in out
    assert mr._get_last_error() == ''


def test_state_persists_between_runs(capsys):
    run(capsys, 'xx = 41')
    out = run(capsys, 'xx + 1')
    assert '42' in out


def test_error_returns_traceback(capsys):
    run(capsys, '1/0')
    assert 'ZeroDivisionError' in mr._get_last_error()


def test_show_string(capsys):
    out = run(capsys, 'show("tekst")')
    assert 'tekst' in out


def test_register_and_alias_module(capsys):
    err = mr._register_module('minmod', 'verdi = 7\ndef dobbel(x):\n    return 2 * x')
    assert err == ''
    err = mr._alias_module('mm', 'minmod')
    assert err == ''
    out = run(capsys, 'import mm\nmm.dobbel(mm.verdi)')
    assert '14' in out


def test_register_module_syntax_error_returns_traceback():
    err = mr._register_module('broken', 'def f(:')
    assert 'SyntaxError' in err
    assert 'broken' not in sys.modules


def test_snapshot_rollback(capsys):
    run(capsys, 'a = 1')
    mr._snapshot()
    run(capsys, 'a = 2\nb = 3')
    mr._rollback()
    out = run(capsys, 'print(a, "b" in dir())')
    assert '1' in out and 'False' in out


def test_bind_datasets_columns(capsys):
    # 'columns'-varianten trenger pandas_mpy, som først finnes i Task 4.
    # Registrer en mini-pandas som _bind_datasets importerer — testen låser
    # KONTRAKTEN (None -> nan, kolonnedict -> frame). VIKTIG: rydd
    # sys.modules før OG etter — pytest deler prosess på tvers av testfiler,
    # og en gjenglemt mini ville skygget den ekte pandas_mpy i senere filer.
    mini = (
        'nan = float("nan")\n'
        'class DataFrame:\n'
        '    def __init__(self, cols):\n'
        '        self.cols = cols\n'
        '    def __len__(self):\n'
        '        return len(next(iter(self.cols.values()), []))\n'
        'def read_csv(f):\n'
        '    rows = [l.split(",") for l in f.getvalue().strip().split(chr(10))]\n'
        '    return DataFrame({h: [r[i] for r in rows[1:]]'
        ' for i, h in enumerate(rows[0])})\n'
    )
    sys.modules.pop('pandas_mpy', None)
    try:
        assert mr._register_module('pandas_mpy', mini) == ''
        spec = {'iris': {'kind': 'csv', 'payload': 'a,b\n1,x\n2,y\n'},
                'tall': {'kind': 'columns', 'payload': {'v': [1, None, 3]}}}
        assert mr._bind_datasets(json.dumps(spec)) == ''
        out = run(capsys, 'print(len(iris), len(tall))')
        assert '2 3' in out
    finally:
        sys.modules.pop('pandas_mpy', None)


def test_pending_signal(capsys):
    run(capsys, 'class _P(BaseException):\n'
                '    __brython_pending__ = True\n'
                'def _kast():\n'
                '    raise _P()')
    run(capsys, '_kast()')
    assert mr._get_last_error() == '__BRYTHON_PENDING__'


def test_indented_last_line_not_evaled_out_of_context(capsys):
    out = run(capsys, 'if True:\n    y = 5\n    y')
    assert mr._get_last_error() == ''
```

- [ ] **Step 2: Kjør testene — forvent modulfeil**

```bash
python3 -m pytest micropython/tests/test_micropython_runner.py -v
```
Forventet: FAIL/ERROR med `ModuleNotFoundError: No module named 'micropython_runner'`.

- [ ] **Step 3: Skriv runneren**

Opprett `micropython/micropython_runner.py`. Basis: kopier `brython/brython_runner.py` og gjør disse endringene (resultatet vises her i sin helhet for de endrede delene — trailing-expression-blokken i `_execute_code` kopieres UENDRET fra Brython-runneren, linjene fra `lines = code.split(chr(10))` til og med `exec(compile(code, ...))`-fallbacken, kun med `'<brython>'` byttet til `'<micropython>'`):

```python
# micropython/micropython_runner.py — persistent kjøremiljø for MicroPython-
# modusen. Port av brython/brython_runner.py (samme grensesnitt og
# embed-marker-protokoll); designspec 2026-07-12-micropython-mode-design.md.
#
# VIKTIGSTE forskjell fra Brython-runneren: stdout fanges IKKE her.
# MicroPython tillater ikke sys.stdout-bytte (fase 0: c_sys_stdout_assign);
# motoren (js/micropython-engine.js) fanger stdout via loadMicroPython({stdout}).
# _execute_code print()-er derfor alt (også trailing expression) og
# returnerer ''. Under CPython (pytest) fanges utskriften med capsys.
import sys, json
from io import StringIO

_EMBED_S = '__micro_transform_start_'
_EMBED_E = '__micro_transform_end__'
_PENDING = '__BRYTHON_PENDING__'   # delt protokollmarkør (samme som Brython)

_shared_vars = {}
_last_error = ''


def _format_exc(e):
    """Traceback-tekst på begge dialekter."""
    if hasattr(sys, 'print_exception'):        # MicroPython
        buf = StringIO()
        sys.print_exception(e, buf)
        return buf.getvalue()
    import traceback                            # CPython (pytest)
    return traceback.format_exc()


def _fmt(obj):
    """Formater ett objekt som output-tekst (embed-markører for figurer/frames)."""
    if obj is None:
        return ''
    if hasattr(obj, 'to_plotly_json_str'):
        return _EMBED_S + 'figure__' + '\n' + obj.to_plotly_json_str() + '\n' + _EMBED_E
    if hasattr(obj, 'to_html'):
        html = obj.to_html()
        if '<table class=' not in html:
            html = html.replace('<table', '<table class="output-table"', 1)
        return _EMBED_S + 'tablehtml__' + '\n' + html + '\n' + _EMBED_E
    if isinstance(obj, str):
        return obj
    return repr(obj)


def _show(*objs):
    for o in objs:
        print(_fmt(o))


_shared_vars['show'] = _show


def _execute_code(code):
    """Kjør koden i de persistente brukerglobals. All output via print
    (motoren samler); returnerer alltid ''."""
    global _last_error
    _last_error = ''
    try:
        # >>> HER: trailing-expression-blokken fra brython_runner.py,
        # uendret bortsett fra '<brython>' -> '<micropython>' — fra
        # `lines = code.split(chr(10))` til og med if not displayed-fallbacken.
        # Den setter `result` og `displayed`. <<<
        shown = _fmt(result) if displayed else ''
        if shown:
            print(shown)
        return ''
    except BaseException as e:
        if getattr(e, '__brython_pending__', False):
            _last_error = _PENDING
            return ''
        if not isinstance(e, Exception):
            raise
        _last_error = _format_exc(e)
        return ''


def _get_last_error():
    return _last_error


class _Mod:
    """MicroPython kan ikke lage types.ModuleType-instanser; et vanlig objekt
    i sys.modules fungerer for både `import m` og `from m import navn`
    (fase 0: c_module_trick). __getattr__ delegerer til modul-globals."""
    def __init__(self, name, g):
        self.__name__ = name
        self._g = g

    def __getattr__(self, k):
        try:
            return self._g[k]
        except KeyError:
            raise AttributeError(k)


def _register_module(name, source):
    """Lazy lib-lasting (motoren kaller): gjør `source` importerbar som `name`.
    Idempotent; '' ved suksess, traceback-tekst ved feil."""
    if name in sys.modules:
        return ''
    g = {'__name__': name}
    try:
        exec(compile(source, name + '.py', 'exec'), g)
    except Exception as e:
        return _format_exc(e)
    sys.modules[name] = _Mod(name, g)
    return ''


def _alias_module(alias, canonical):
    """`import alias` -> allerede registrert `canonical`. Dottet alias krever
    forelder i sys.modules først (samme regel som Brython-runneren)."""
    if canonical not in sys.modules:
        return 'Ukjent modul: ' + canonical
    if '.' in alias:
        parent_name, _, child = alias.rpartition('.')
        if parent_name not in sys.modules:
            return 'Ukjent foreldremodul: ' + parent_name
        setattr(sys.modules[parent_name], child, sys.modules[canonical])
    sys.modules[alias] = sys.modules[canonical]
    return ''


_snap = None


def _snapshot():
    global _snap
    _snap = dict(_shared_vars)


def _rollback():
    # Per-nøkkel med vilje (arv fra Brython-fella; ufarlig og likt begge steder)
    if _snap is None:
        return
    for k in list(_shared_vars.keys()):
        if k not in _snap:
            del _shared_vars[k]
    for k in list(_snap.keys()):
        _shared_vars[k] = _snap[k]


def _bind_datasets(spec_json):
    """Bind datasett fra JS til brukerglobals. spec: {name: {kind, payload}}.
    kind 'csv' -> CSV-tekst; kind 'columns' -> {kolonne: [verdier]}.
    NB: ingen float-str-rundtur her — MicroPythons json gir ekte floats
    (fase 0: c_json_floats); Brython-fella finnes ikke i denne dialekten."""
    try:
        import pandas_mpy as _pd
        spec = json.loads(spec_json) if isinstance(spec_json, str) else spec_json
        for name, d in spec.items():
            if d['kind'] == 'csv':
                _shared_vars[name] = _pd.read_csv(StringIO(d['payload']))
            else:
                cols = {k: [_pd.nan if v is None else v for v in vals]
                        for k, vals in d['payload'].items()}
                _shared_vars[name] = _pd.DataFrame(cols)
        return ''
    except Exception as e:
        return _format_exc(e)
```

Trailing-expression-blokken limes inn fra `brython/brython_runner.py:80-115` (fra `lines = code.split(chr(10))` t.o.m. `if not displayed: exec(...)`), med kommentarblokken over den (linje 46–79) beholdt.

- [ ] **Step 4: Kjør testene**

```bash
python3 -m pytest micropython/tests/test_micropython_runner.py -v
```
Forventet: alle PASS.

- [ ] **Step 5: Kjør runneren under unix-micropython**

Runneren skal også kunne lastes av selve MicroPython. Røyk-test:

```bash
micropython -c "
import sys
sys.path.insert(0, 'micropython')
import micropython_runner as mr
mr._execute_code('print(\"hei\")\n1 + 1')
print('err:', repr(mr._get_last_error()))
assert mr._register_module('m1', 'v = 5') == ''
mr._execute_code('import m1\nprint(m1.v)')
print('err2:', repr(mr._get_last_error()))
"
```
Forventet: `hei`, `2`, `err: ''`, `5`, `err2: ''`.

- [ ] **Step 6: Commit og push**

```bash
git add micropython/micropython_runner.py micropython/tests/test_micropython_runner.py
git commit -m "feat(micropython): runner — port av brython_runner med stdout-via-motor"
git push
```

---

### Task 3: Motor — `js/micropython-engine.js`

**Files:**
- Create: `js/micropython-engine.js`
- Create: `web_examples/mpy_engine_test.html` (manuell browser-røyktest — index.html røres først i Task 7)

**Interfaces:**
- Consumes: runner-funksjonene fra Task 2 via `mp.globals.get('<navn>')` (proxies kallbare fra JS).
- Produces: `window.MicroPythonEngine = { load, run, _scanImports }`; `run(script, {loads})` resolver ALLTID `{text, error}`. Duck-bro-globalen heter `__mpyDuckSync`; capture-hookene `__mpyCaptureStart`/`__mpyCaptureEnd` (brukes av `micropython/dash.py` i Task 6); embed-datatags `mpydata_<navn>`.

- [ ] **Step 1: Skriv motoren**

Opprett `js/micropython-engine.js`:

```javascript
// js/micropython-engine.js — rask Python-motor (MicroPython-wasm) for
// openstat/safestat. Speiler js/brython-engine.js; designspec:
// docs/superpowers/specs/2026-07-12-micropython-mode-design.md
//
// Boot: dynamisk import() av den offisielle wasm-portens ES-modul (pinnet
// 1.27.0), loadMicroPython med stdout-callback — runneren skriver ALT via
// print (MicroPython tillater ikke sys.stdout-bytte), motoren samler linjene
// i __stdoutBuf og bygger {text}. Lazy libs, duck-replay-broen og
// {text, error}-kontrakten er som i Brython-motoren.
(function (global) {
  'use strict';

  var MPY_BASE = 'https://cdn.jsdelivr.net/npm/@micropython/micropython-webassembly-pyscript@1.27.0/';

  // Library registry — samme form som Brython-motorens (js-deps er
  // {url, global}-objekter, ikke strenger).
  var LIB_REGISTRY = {
    // pandas_mpy har (som pandas_brython) modulnivå try-import av plotly (df.plot)
    pandas_mpy:         { aliases: [], deps: ['plotly_express_mpy'], js: [] },
    plotly_express_mpy: { aliases: [], deps: [], js: [] },
    duckdb_mpy:         { aliases: ['duckdb'], deps: ['pandas_mpy'], js: [] },
    dash:               { aliases: [], deps: [], js: [{ url: 'js/dash.js', global: 'Dash' }] }
  };

  function scanImports(code) {
    // Identisk logikk som brython-engine.js scanImports (over-match ufarlig,
    // under-match gir høylytt ModuleNotFoundError).
    var needed = [];
    function add(rawName) {
      var name = rawName.split('.')[0];
      var canonical = LIB_REGISTRY.hasOwnProperty(name) ? name : null;
      if (!canonical) {
        for (var k in LIB_REGISTRY) {
          if (LIB_REGISTRY[k].aliases.indexOf(name) !== -1) { canonical = k; break; }
        }
      }
      if (canonical && needed.indexOf(canonical) === -1) needed.push(canonical);
    }
    var re = /^[ \t]*(?:from[ \t]+([A-Za-z_][A-Za-z0-9_.]*)|import[ \t]+([^#\r\n]+))/gm;
    var m, parts, i, t;
    while ((m = re.exec(code))) {
      if (m[1]) { add(m[1]); continue; }
      parts = m[2].split(',');
      for (i = 0; i < parts.length; i++) {
        t = parts[i].trim().split(/[ \t]/)[0];
        if (/^[A-Za-z_][A-Za-z0-9_.]*$/.test(t)) add(t);
      }
    }
    return needed;
  }

  var __registered = {};
  var __jsLoaded = {};
  var __stdoutBuf = [];
  var __captureMark = 0;

  // dash.py-kroker: MicroPython kan ikke bytte sys.stdout, så callback-
  // utskrift fanges ved å merke/splitte motorens stdout-buffer i stedet.
  global.__mpyCaptureStart = function () { __captureMark = __stdoutBuf.length; };
  global.__mpyCaptureEnd = function () {
    return __stdoutBuf.splice(__captureMark).join('\n');
  };

  function addScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = function () { reject(new Error('Kunne ikke laste ' + src)); };
      document.head.appendChild(s);
    });
  }

  function fetchText(path) {
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error('Kunne ikke hente ' + path + ' (' + r.status + ')');
      return r.text();
    });
  }

  function loadJsDep(dep) {
    if (global[dep.global]) return Promise.resolve();
    if (!__jsLoaded[dep.url]) {
      __jsLoaded[dep.url] = addScript(dep.url).catch(function (e) {
        delete __jsLoaded[dep.url];
        throw e;
      });
    }
    return __jsLoaded[dep.url];
  }

  var __enginePromise = null;

  function load() {
    if (__enginePromise) return __enginePromise;
    __enginePromise = (async function () {
      var esm = await import(MPY_BASE + 'micropython.mjs');
      var mp = await esm.loadMicroPython({
        url: MPY_BASE + 'micropython.wasm',
        stdout: function (line) { __stdoutBuf.push(line); },
        linebuffer: true
      });
      var source = await fetchText('micropython/micropython_runner.py');
      mp.runPython(source);
      return {
        mp: mp,
        _execute_code: mp.globals.get('_execute_code'),
        _get_last_error: mp.globals.get('_get_last_error'),
        _register_module: mp.globals.get('_register_module'),
        _alias_module: mp.globals.get('_alias_module'),
        _snapshot: mp.globals.get('_snapshot'),
        _rollback: mp.globals.get('_rollback'),
        _bind_datasets: mp.globals.get('_bind_datasets')
      };
    })().catch(function (e) { __enginePromise = null; throw e; });
    return __enginePromise;
  }

  async function ensureLibs(mod, names, _visiting) {
    _visiting = _visiting || {};
    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      if (__registered[name]) continue;
      var entry = LIB_REGISTRY[name];
      if (!entry) throw new Error('Ukjent bibliotek i LIB_REGISTRY: ' + name);
      if (_visiting[name]) throw new Error('Sirkulær avhengighet i LIB_REGISTRY: ' + name);
      _visiting[name] = true;
      await ensureLibs(mod, entry.deps, _visiting);
      for (var j = 0; j < entry.js.length; j++) await loadJsDep(entry.js[j]);
      var source = await fetchText('micropython/' + name + '.py');
      var err = mod._register_module(name, source);
      if (err) throw new Error(String(err));
      for (var a = 0; a < entry.aliases.length; a++) {
        err = mod._alias_module(entry.aliases[a], name);
        if (err) throw new Error(String(err));
      }
      __registered[name] = true;
    }
  }

  var PENDING_MARKER = '__BRYTHON_PENDING__';   // delt protokoll med Brython-motoren
  var MAX_DUCK_PASSES = 10;

  // Per-run duckdb-bro — identisk protokoll som Brython-motorens
  // beginDuckBridge (JSON-streng {pending}|{cols}|{error}), eget globalnavn
  // så motorene ikke tråkker i hverandres closures.
  function beginDuckBridge(spec) {
    var cache = {};
    var pending = [];
    var registered = false;
    global.__mpyDuckSync = function (sqlText) {
      if (cache.hasOwnProperty(sqlText)) return cache[sqlText];
      if (pending.indexOf(sqlText) === -1) pending.push(sqlText);
      return '{"pending":true}';
    };
    return {
      hasPending: function () { return pending.length > 0; },
      flush: async function () {
        if (!global.__brythonDuck) {
          throw new Error('duckdb i MicroPython-modus krever DuckDB-hjelperen (__brythonDuck) i index.html');
        }
        if (!registered) {
          for (var name in spec) {
            await global.__brythonDuck.register(name, spec[name].kind, spec[name].payload);
          }
          registered = true;
        }
        var batch = pending;
        pending = [];
        for (var i = 0; i < batch.length; i++) {
          try {
            var cols = await global.__brythonDuck.query(batch[i]);
            cache[batch[i]] = JSON.stringify({ cols: cols });
          } catch (e) {
            cache[batch[i]] = JSON.stringify({ error: (e && e.message) || String(e) });
          }
        }
      }
    };
  }

  // Samme kildeoppsett som Brython-motorens buildDatasetSpec; embed-tags
  // heter mpydata_<navn>.
  async function buildDatasetSpec(loads) {
    var spec = {};
    var i, l;
    for (i = 0; i < (loads || []).length; i++) {
      l = loads[i];
      if (!l.bytes) continue;
      if (l.format === 'csv') {
        spec[l.alias] = { kind: 'csv', payload: new TextDecoder().decode(l.bytes) };
      } else if (l.format === 'json') {
        spec[l.alias] = { kind: 'columns', payload: JSON.parse(new TextDecoder().decode(l.bytes)) };
      } else if (l.format === 'parquet') {
        if (typeof global.__brythonParquetColumns !== 'function') {
          throw new Error('parquet-kilden «' + l.alias + '» støttes ikke: DuckDB-hjelperen mangler');
        }
        spec[l.alias] = { kind: 'columns', payload: await global.__brythonParquetColumns(l.bytes) };
      } else {
        throw new Error('formatet «' + l.format + '» (' + l.alias + ') støttes ikke i MicroPython-modus — bruk python/r');
      }
    }
    var nodes = document.querySelectorAll('script[type="application/json"][id^="mpydata_"]');
    for (i = 0; i < nodes.length; i++) {
      var name = nodes[i].id.slice('mpydata_'.length);
      if (!spec[name]) spec[name] = { kind: 'columns', payload: JSON.parse(nodes[i].textContent) };
    }
    return spec;
  }

  async function run(script, opts) {
    // Kontrakt: run() resolver ALLTID {text, error} — aldri reject (samme
    // begrunnelse som i brython-engine.js run()).
    try {
      var mod = await load();
      var spec = await buildDatasetSpec(opts && opts.loads);
      var needed = scanImports(script);
      if (Object.keys(spec).length && needed.indexOf('pandas_mpy') === -1) {
        needed.push('pandas_mpy');   // _bind_datasets bygger DataFrames
      }
      await ensureLibs(mod, needed);
      var duck = beginDuckBridge(spec);
      mod._snapshot();
      var err = null, pass;
      for (pass = 0; pass < MAX_DUCK_PASSES; pass++) {
        if (pass > 0) mod._rollback();
        __stdoutBuf.length = 0;      // nytt pass = tom buffer (pending-pass forkastes)
        __captureMark = 0;
        if (Object.keys(spec).length) {
          var bindErr = mod._bind_datasets(JSON.stringify(spec));
          if (bindErr) return { text: '', error: String(bindErr) };
        }
        mod._execute_code(script);
        err = mod._get_last_error();
        if (err !== PENDING_MARKER) break;
        if (!duck.hasPending()) {
          return { text: '', error: 'duckdb_mpy: replay uten ventende spørringer (intern feil)' };
        }
        await duck.flush();
      }
      if (err === PENDING_MARKER) {
        return { text: '', error: 'duckdb-spørringene stabiliserer seg ikke etter ' +
                 MAX_DUCK_PASSES + ' pass — bygges SQL-tekstene av ikke-deterministiske ' +
                 'verdier (f.eks. random uten seed)?' };
      }
      var text = __stdoutBuf.join('\n');
      return { text: text, error: err ? String(err) : null };
    } catch (e) {
      return { text: '', error: (e && e.message) || String(e) };
    }
  }

  global.MicroPythonEngine = { load: load, run: run, _scanImports: scanImports };
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 2: Skriv browser-røyktesten**

Opprett `web_examples/mpy_engine_test.html`:

```html
<!DOCTYPE html>
<!-- Røyktest for MicroPythonEngine uten index.html. Kjør:
     python3 -m http.server 8901 fra repo-roten, åpne
     http://localhost:8901/web_examples/mpy_engine_test.html -->
<html><head><meta charset="utf-8"><title>mpy-engine-test</title>
<base href="../"></head>
<body><pre id="out">kjører…</pre>
<script src="js/micropython-engine.js"></script>
<script type="module">
const out = document.getElementById('out');
const results = [];
function rec(name, res) {
  results.push(name + ': ' + (res.error ? 'FEIL — ' + res.error : 'OK — ' + JSON.stringify(res.text).slice(0, 120)));
  out.textContent = results.join('\n');
}
rec('basics', await MicroPythonEngine.run('print("hei")\n1 + 1'));
await MicroPythonEngine.run('zz = 40');
rec('state', await MicroPythonEngine.run('zz + 2'));
rec('feil-traceback', await MicroPythonEngine.run('1/0'));
rec('scanImports', { text: MicroPythonEngine._scanImports('import duckdb\nimport pandas_mpy').join(','), error: null });
</script></body></html>
```

- [ ] **Step 3: Kjør røyktesten i nettleser**

```bash
python3 -m http.server 8901
```
Åpne `http://localhost:8901/web_examples/mpy_engine_test.html`. Forventet: `basics: OK` med «hei» og «2», `state: OK` med «42», `feil-traceback: FEIL — …ZeroDivisionError…`, `scanImports: OK — "duckdb_mpy,pandas_mpy"`. (pandas/plotly-import testes i Task 4/5 når filene finnes.)

- [ ] **Step 4: Commit og push**

```bash
git add js/micropython-engine.js web_examples/mpy_engine_test.html
git commit -m "feat(micropython): motor — wasm-boot, lazy libs, duck-bro, stdout-buffer"
git push
```

---

### Task 4: pandas-port — `micropython/pandas_mpy.py`

**Files:**
- Create: `micropython/pandas_mpy.py` (kopi av `brython/pandas_brython.py` + edits under)
- Test: `micropython/tests/test_pandas_mpy.py` (tilpasset kopi av `brython/tests/test_pandas_brython.py`)
- Create: `micropython/tests/mpy_smoke_pandas.py` (kjøres under unix-micropython)

**Interfaces:**
- Produces: modul `pandas_mpy` med samme API som `pandas_brython` (`DataFrame`, `read_csv`, `nan`, groupby, `to_html`, …). Runnerens `_bind_datasets` (Task 2) importerer `pandas_mpy`.

- [ ] **Step 1: Kopier og gi nytt navn**

```bash
cp brython/pandas_brython.py micropython/pandas_mpy.py
```

- [ ] **Step 2: Tilpass testfila og kjør — forvent delvis grønt**

```bash
sed -e 's/pandas_brython/pandas_mpy/g' \
    brython/tests/test_pandas_brython.py > micropython/tests/test_pandas_mpy.py
python3 -m pytest micropython/tests/test_pandas_mpy.py -v
```
Forventet: det meste PASS allerede (ren kopi under CPython); noter ev. feil.

- [ ] **Step 3: Gjør de tre portene**

I `micropython/pandas_mpy.py`:

**(a) Headerkommentar** (linje 1-ish): oppdater til å nevne MicroPython-modusen og at fila er en divergerende kopi av `pandas_brython.py` per 2026-07-12.

**(b) `import base64` (linje ~77)** — MicroPython mangler base64, har binascii (fase 0: `c_binascii_base64`). Erstatt linjen med:

```python
try:
    import base64
except ImportError:              # MicroPython: binascii dekker b64decode
    import binascii
    class base64:
        @staticmethod
        def b64decode(s):
            return binascii.a2b_base64(s)
```

**(c) csv-avhengigheten (~linje 3590-3660)** — hele try-import-blokken med Brython-QUOTE-lappingen OG `csv.reader`-løkka erstattes. Legg til modulnivå-funksjonen (plasser rett over `read_csv`):

```python
def _parse_csv_text(text, sep=','):
    """Minimal RFC-4180-parser (MicroPython har ingen csv-modul): håndterer
    sitering, doblede anførselstegn og CRLF. Erstatter csv.reader."""
    rows, row, field, in_q = [], [], [], False
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if in_q:
            if c == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                in_q = False
            else:
                field.append(c)
        elif c == '"':
            in_q = True
        elif c == sep:
            row.append(''.join(field))
            field = []
        elif c == '\n':
            row.append(''.join(field))
            field = []
            rows.append(row)
            row = []
        elif c != '\r':
            field.append(c)
        i += 1
    if field or row:
        row.append(''.join(field))
        rows.append(row)
    return rows
```

og skriv om lesestedet: der koden i dag gjør `spamreader = csv.reader(csvfile, delimiter=sep)` og itererer, hent i stedet hele teksten (`csvfile.read()` hvis fil-objekt, ellers strengen direkte) og iterer over `_parse_csv_text(tekst, sep)`. Fjern `import csv`-blokken og QUOTE-lappingen (linje ~3596-3617) helt.

Merk: `from js import window`-blokken (linje 63-75) skal IKKE endres — `import js` finnes i MicroPython, så første gren treffer der (samme gren som Pyodide).

- [ ] **Step 4: Kjør pytest på nytt**

```bash
python3 -m pytest micropython/tests/test_pandas_mpy.py -v
```
Forventet: alle PASS (parseren skal gi samme resultat som csv.reader for testenes filer).

- [ ] **Step 5: Skriv og kjør unix-micropython-røyken**

Opprett `micropython/tests/mpy_smoke_pandas.py`:

```python
# Kjøres under unix-micropython: micropython micropython/tests/mpy_smoke_pandas.py
# Dialekt-røyk for pandas_mpy — feiler høylytt med traceback ved dialektbrudd.
import sys
sys.path.insert(0, 'micropython')
import pandas_mpy as pd

df = pd.DataFrame({'by': ['Oslo', 'Bergen', 'Oslo'], 'v': [10, 20, 30]})
assert len(df) == 3
g = df.groupby('by')['v'].mean()
assert '<table' in df.to_html()
sub = df[df['v'] > 10]
assert len(sub) == 2
df['dobbel'] = df['v'] * 2
assert list(df['dobbel']) == [20, 40, 60]
from io import StringIO
df2 = pd.read_csv(StringIO('a,b\n1,"x,y"\n2,z\n'))
assert len(df2) == 2
print('MPY-PANDAS-RØYK OK')
```

```bash
micropython micropython/tests/mpy_smoke_pandas.py
```
Forventet: `MPY-PANDAS-RØYK OK`. Dialektfeil her (f.eks. en str-metode MicroPython mangler) fikses i `pandas_mpy.py` (IKKE i brython-originalen) og dokumenteres i filhodet; kjør Step 4 + 5 til begge er grønne.

- [ ] **Step 6: Verifiser i nettleser**

Legg til nederst i `web_examples/mpy_engine_test.html`-scriptet:

```javascript
rec('pandas', await MicroPythonEngine.run(
  'import pandas_mpy as pd\ndf = pd.DataFrame({"a": [1, 2, 3]})\ndf'));
```
Kjør som i Task 3 Step 3. Forventet: `pandas: OK` med `tablehtml__`-markør i teksten.

- [ ] **Step 7: Commit og push**

```bash
git add micropython/pandas_mpy.py micropython/tests/test_pandas_mpy.py micropython/tests/mpy_smoke_pandas.py web_examples/mpy_engine_test.html
git commit -m "feat(micropython): pandas_mpy — port med _parse_csv_text og binascii-base64"
git push
```

---

### Task 5: plotly-port — `micropython/plotly_express_mpy.py`

**Files:**
- Create: `micropython/plotly_express_mpy.py` (kopi av `brython/plotly_express_brython.py` + edits)
- Test: `micropython/tests/test_plotly_express_mpy.py`
- Create: `micropython/tests/mpy_smoke_plotly.py`

**Interfaces:**
- Consumes: `pandas_mpy` (Task 4).
- Produces: modul `plotly_express_mpy` med samme API som brython-varianten; figurer har `to_plotly_json_str()` (runnerens `_fmt` bruker den).

- [ ] **Step 1: Kopier, tilpass tester, kjør**

```bash
cp brython/plotly_express_brython.py micropython/plotly_express_mpy.py
sed -e 's/plotly_express_brython/plotly_express_mpy/g' -e 's/pandas_brython/pandas_mpy/g' \
    brython/tests/test_plotly_express_brython.py > micropython/tests/test_plotly_express_mpy.py
python3 -m pytest micropython/tests/test_plotly_express_mpy.py -v
```
Forventet: PASS (ren kopi under CPython). Sjekk også at kopien refererer riktig pandas: `grep -n pandas_brython micropython/plotly_express_mpy.py` — bytt ev. treff til `pandas_mpy`.

- [ ] **Step 2: Gjør de tre portene**

I `micropython/plotly_express_mpy.py`:

**(a) Headerkommentar:** som i Task 4.

**(b) datetime (linje ~129 og ~144-149):** wasm-porten mangler datetime (fase 0: `c_datetime_missing`). I `json_safe`: erstatt `import datetime` med

```python
    try:
        import datetime
    except ImportError:      # MicroPython-wasm: ingen datetime — grenen hoppes over
        datetime = None
```

og pakk isinstance-sjekkene:

```python
    if datetime is not None:
        if isinstance(obj, datetime.datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(obj, datetime.date):
            return obj.strftime('%Y-%m-%d')
        if isinstance(obj, datetime.time):
            return obj.strftime('%H:%M:%S')
```

**(c) re-avhengigheten (linje ~434-436):** eneste re-bruk i fila er `re.split(r'[_\-]', str(column_name))`. Fjern `import re` og erstatt kallet med det dialekt-sikre ekvivalentet:

```python
    words = str(column_name).replace('-', '_').split('_')
```

- [ ] **Step 3: Kjør pytest**

```bash
python3 -m pytest micropython/tests/test_plotly_express_mpy.py -v
```
Forventet: alle PASS.

- [ ] **Step 4: Skriv og kjør unix-micropython-røyken**

Opprett `micropython/tests/mpy_smoke_plotly.py`:

```python
# micropython micropython/tests/mpy_smoke_plotly.py
import sys, json
sys.path.insert(0, 'micropython')
import pandas_mpy as pd
import plotly_express_mpy as pe

df = pd.DataFrame({'x': [1, 2, 3], 'y': [3.5, None, 4.0], 'k': ['a', 'b', 'a']})
for fig in (pe.scatter(df, x='x', y='y'),
            pe.bar(df, x='k', y='x'),
            pe.line(df, x='x', y='y'),
            pe.histogram(df, x='k'),
            pe.pie(df, names='k', values='x')):
    d = json.loads(fig.to_plotly_json_str())
    assert 'data' in d and 'layout' in d
print('MPY-PLOTLY-RØYK OK')
```

```bash
micropython micropython/tests/mpy_smoke_plotly.py
```
Forventet: `MPY-PLOTLY-RØYK OK`. Dialektfeil fikses i mpy-kopien og noteres i filhodet.

- [ ] **Step 5: Verifiser i nettleser**

Legg til i `web_examples/mpy_engine_test.html`:

```javascript
rec('plotly', await MicroPythonEngine.run(
  'import pandas_mpy as pd\nimport plotly_express_mpy as pe\n' +
  'df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})\npe.scatter(df, x="x", y="y")'));
```
Forventet: `plotly: OK` med `figure__`-markør i teksten.

- [ ] **Step 6: Commit og push**

```bash
git add micropython/plotly_express_mpy.py micropython/tests/test_plotly_express_mpy.py micropython/tests/mpy_smoke_plotly.py web_examples/mpy_engine_test.html
git commit -m "feat(micropython): plotly_express_mpy — port uten re/datetime-avhengighet"
git push
```

---

### Task 6: dash- og duckdb-port

**Files:**
- Create: `micropython/dash.py` (kopi av `brython/dash.py` + edits)
- Create: `micropython/duckdb_mpy.py` (kopi av `brython/duckdb_brython.py` + edits)
- Test: `micropython/tests/test_duckdb_mpy.py`

**Interfaces:**
- Consumes: `pandas_mpy` (Task 4); motorens `__mpyDuckSync` / `__mpyCaptureStart` / `__mpyCaptureEnd` (Task 3); `window.Dash` fra `js/dash.js` (lastes av LIB_REGISTRY).
- Produces: moduler `dash` og `duckdb_mpy` (alias `duckdb`); `duckdb_mpy._executor`-kroken for CPython-tester beholdes.

- [ ] **Step 1: Kopier duckdb, tilpass tester, kjør**

```bash
cp brython/duckdb_brython.py micropython/duckdb_mpy.py
sed -e 's/duckdb_brython/duckdb_mpy/g' -e 's/pandas_brython/pandas_mpy/g' \
    brython/tests/test_duckdb_brython.py > micropython/tests/test_duckdb_mpy.py
python3 -m pytest micropython/tests/test_duckdb_mpy.py -v
```
Forventet: PASS (testene bruker `_executor`-kroken, ikke nettleser).

- [ ] **Step 2: Porter duckdb_mpy.py**

I `micropython/duckdb_mpy.py`:

**(a)** `import pandas_brython as _pd` → `import pandas_mpy as _pd` (gjort av sed — verifiser).

**(b)** window-oppslaget og bro-navnet:

```python
try:
    import js as _js                 # MicroPython (og Pyodide)
except ImportError:                  # CPython (pytest)
    _js = None
```

og i `_run_sql`: `if _window is None:` → `if _js is None:`; kall-linjen blir

```python
    d = _json.loads(_js.__mpyDuckSync(q))
```

**(c)** Fjern float-str-rundturen nederst i `_run_sql` (Brython-fella finnes ikke her; fase 0: `c_json_floats`):

```python
    return d['cols']
```

**(d)** Behold `_PendingSQL` med `__brython_pending__ = True` uendret — det er den delte protokollens attributtnavn (se Global Constraints). Oppdater headerkommentaren til å referere `js/micropython-engine.js` og `__mpyDuckSync`.

- [ ] **Step 3: Kjør duckdb-testene på nytt**

```bash
python3 -m pytest micropython/tests/test_duckdb_mpy.py -v
```
Forventet: alle PASS.

- [ ] **Step 4: Porter dash.py**

```bash
cp brython/dash.py micropython/dash.py
```

I `micropython/dash.py`:

**(a)** Linje 3, `from browser import window` →

```python
from js import window                # MicroPython: js-modulen (jsffi)
```

**(b)** Callback-utskriftsfangsten (linje ~319-347) bruker `sys.stdout = buf` — umulig i MicroPython. Erstatt mønsteret

```python
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        ...
            sys.stdout = old
```

med motor-hookene fra Task 3:

```python
        window.__mpyCaptureStart()
        ...
        # der koden i dag leser buf.getvalue() etter å ha satt sys.stdout
        # tilbake, bruk i stedet:
        tekst = window.__mpyCaptureEnd()
```

Les blokken rundt linje 319-347 nøye: `__mpyCaptureEnd()` må kalles i samme finally/etterkant-posisjon som dagens `sys.stdout = old`, og verdien brukes der `buf.getvalue()` brukes i dag. Fjern da også ubrukte `import io`/`import sys` hvis ingenting annet i fila bruker dem.

**(c)** Duck-typet plotly-gjenkjenning (linje ~117): står det `plotly_express_brython` i streng/kommentar, oppdater til `plotly_express_mpy` — sjekk med `grep -n plotly micropython/dash.py`.

- [ ] **Step 5: Unix-micropython-røyk for modul-lasting**

dash.py krever `window` — full test skjer i nettleser (Task 7). Verifiser bare at fila parser og laster under MicroPython med en window-stub:

```bash
micropython -c "
import sys
sys.path.insert(0, 'micropython')
class _W:
    pass
sys.modules['js'] = _W()
sys.modules['js'].window = _W()
import dash
print('MPY-DASH-LASTING OK')
"
```
Forventet: `MPY-DASH-LASTING OK`. (`sys.modules['js']`-stubben skygger jsffi — kun for parse/last-sjekk.)

- [ ] **Step 6: Commit og push**

```bash
git add micropython/dash.py micropython/duckdb_mpy.py micropython/tests/test_duckdb_mpy.py
git commit -m "feat(micropython): dash + duckdb_mpy — capture-hooks og __mpyDuckSync"
git push
```

---

### Task 7: index.html-integrasjon — ⛔ GATE: `dash-v2-runtimes` må være merget først

Sjekk gaten: `git log --oneline origin/master | head -5` skal inneholde dash-v2-runtimes-mergen (spør Hans hvis usikkert). Merge deretter master inn i arbeidsbranchen: `git merge master` (løs ev. konflikter — ingen av branchens filer overlapper dash-v2, så det skal være rent).

**Files:**
- Modify: `index.html` — seks punkter: script-tag (~linje 807), modusknapp (~532), eksempelseksjon (~87-111-området), eksempel-laster-whitelist (~1900), `modeRegistry` (~3691), `RUNTIME_FOR_MODE` (~3754), bootstrap-runtime-grenen (~9927). (Linjenumre er FØR dash-v2-mergen — søk på ankerne som angitt.)

**Interfaces:**
- Consumes: `window.MicroPythonEngine` (Task 3).

- [ ] **Step 1: Script-tag**

Rett under `<script src="js/brython-engine.js"></script>`:

```html
  <script src="js/micropython-engine.js"></script>
```

- [ ] **Step 2: Modusknapp**

I `mode-dropdown-menu`-diven, rett under Brython-knappen:

```html
          <button type="button" data-mode="micropython">MicroPython</button>
```

- [ ] **Step 3: RUNTIME_FOR_MODE**

I `RUNTIME_FOR_MODE`-objektet, legg til:

```javascript
                             micropython: 'micropython',
```

- [ ] **Step 4: modeRegistry-raden**

Rett etter `brython:`-oppføringen i `modeRegistry` (søk `brython: { id: 'brython'`), legg til en rad som er en tilpasset kopi av Brython-raden — samme purgePlots/dash-DOM-håndtering:

```javascript
      micropython: { id: 'micropython', label: 'MicroPython', hlConfig: PY_HL_CFG, handleTab: handlePythonTab,
        onActivate: function () { if (window.MicroPythonEngine) window.MicroPythonEngine.load().catch(function () {}); },
        runSelf: async function (script, ctx) {
          setStatus(ctx.rightStatus, t('Laster MicroPython…'));
          var _dl = await window.DataLoader.resolveAndFetchLoads(script,
            { anthropicKey: getAnthropicKey(), promptKey: mdPromptKey });
          setStatus(ctx.rightStatus, t('Kjører…'));
          // Samme dash v2-forbehold som Brython-raden: js/dash.js skriver DOM
          // direkte til #outputArea under kjøring — tøm FØR, ikke etter.
          purgePlots(outputArea);
          outputArea.innerHTML = '';
          var res = await window.MicroPythonEngine.run(script, { loads: _dl.loads });
          var _omEl = document.querySelector('input[name="outputMode"]:checked');
          var _asHtml = !_omEl || _omEl.value === 'html';
          var _suppress = (typeof suppressEmbedded !== 'undefined' && suppressEmbedded) ? !!suppressEmbedded.checked : false;
          if (outputArea.querySelector('.dash')) {
            appendOutput(res.text || '', _asHtml, _suppress);
          } else {
            renderOutput(res.text || '', _asHtml, _suppress);
          }
          if (res.error) {
            var _pre = document.createElement('pre');
            _pre.className = 'error';
            _pre.textContent = res.error;
            outputArea.appendChild(_pre);
          }
          setStatus(ctx.rightStatus, res.error ? t('Feil') : t('Ferdig'));
        } },
```

NB: hvis dash-v2-mergen har endret Brython-radens `runSelf` (f.eks. nye dash-hooks), speil den NYE Brython-raden — den er fasit, ikke koden over.

- [ ] **Step 5: Bootstrap-grenen**

I den ivrige runtime-lastingen (søk `runtimeForMode(activeEditorMode) === 'brython'`), legg til en gren etter brython-grenen:

```javascript
    } else if (runtimeForMode(activeEditorMode) === 'micropython' && window.MicroPythonEngine) {
      window.MicroPythonEngine.load().then(function () {
        runtimeReadyBootstrap(null);
      }).catch(function (e) {
        setStatus(leftStatus, 'Load failed: ' + (e && e.message ? e.message : String(e)), true);
      });
```

- [ ] **Step 6: Eksempel-laster-whitelisten**

I mode-whitelisten (søk `mode === 'statx' || mode === 'duckdb' || mode === 'brython'`), utvid med `|| mode === 'micropython'`. Sjekk også dropdown-persistens-listen (søk `.indexOf(_wanted)` med `'brython'` i array-literalen) og legg til `'micropython'` der.

- [ ] **Step 7: Browser-røyktest av hele appen**

```bash
python3 -m http.server 8901
```
Åpne `http://localhost:8901/index.html`, velg MicroPython i modusmenyen, kjør:

```python
import pandas_mpy as pd
import plotly_express_mpy as pe
df = pd.DataFrame({"x": [1, 2, 3], "y": [2, 4, 9]})
show(df)
pe.scatter(df, x="x", y="y")
```
Forventet: tabell + plotly-figur i output; statuslinje «Ferdig». Test også en feil (`1/0` → rød traceback) og modusbytte frem og tilbake (editor-innhold bevares per modus).

- [ ] **Step 8: Commit og push**

```bash
git add index.html
git commit -m "feat(micropython): modus-registrering i index.html (6 punkter)"
git push
```

---

### Task 8: Eksempler, dashboard-røyk og sync til openstat

**Files:**
- Create: `examples/mp01_pandas_basics.txt`, `examples/mp02_plotly.txt`, `examples/mp03_dashboard.txt`
- Modify: `index.html` (eksempelseksjon)
- Modify (openstat): kopier `micropython/`, `js/micropython-engine.js`, `examples/mp*.txt` + gjenta Task 7-editsene i openstats `index.html`

**Interfaces:**
- Consumes: alt over.

- [ ] **Step 1: Skriv eksemplene**

`examples/mp01_pandas_basics.txt`:

```python
# MicroPython-modus: rask Python i nettleseren
import pandas_mpy as pd

df = pd.DataFrame({
    "by": ["Oslo", "Bergen", "Oslo", "Bergen", "Tromsø"],
    "år": [2023, 2023, 2024, 2024, 2024],
    "verdi": [10, 20, 30, 25, 15],
})
show(df)
df.groupby("by")["verdi"].mean()
```

`examples/mp02_plotly.txt`:

```python
# Grafer med plotly express (MicroPython)
import pandas_mpy as pd
import plotly_express_mpy as pe

df = pd.DataFrame({
    "x": [1, 2, 3, 4, 5, 6],
    "y": [2, 4, 9, 16, 25, 36],
    "gruppe": ["a", "b", "a", "b", "a", "b"],
})
pe.scatter(df, x="x", y="y", color="gruppe", title="Rask scatter")
```

`examples/mp03_dashboard.txt`: kopier `examples/bry11_dashboard_salg.txt` (dashboard uten eksterne data) og bytt `pandas_brython` → `pandas_mpy`, `plotly_express_brython` → `plotly_express_mpy`:

```bash
sed -e 's/pandas_brython/pandas_mpy/g' -e 's/plotly_express_brython/plotly_express_mpy/g' \
    examples/bry11_dashboard_salg.txt > examples/mp03_dashboard.txt
```

- [ ] **Step 2: Eksempelseksjon i index.html**

Rett etter `data-section-mode="brython"`-seksjonen:

```html
            <div class="examples-section" data-section-mode="micropython">
              <button type="button" data-example="mp01_pandas_basics.txt" data-mode="micropython" data-i18n>pandas_mpy &mdash; basics</button>
              <button type="button" data-example="mp02_plotly.txt" data-mode="micropython" data-i18n>plotly_express_mpy &mdash; grafer</button>
              <button type="button" data-example="mp03_dashboard.txt" data-mode="micropython" data-i18n>Dashboard &mdash; salg</button>
            </div>
```

- [ ] **Step 3: Kjør alle tre eksemplene i nettleser**

Som Task 7 Step 7 — alle tre eksempelknappene skal gi riktig output; mp03 skal bygge et interaktivt dashboard der kontrollene oppdaterer kortene (verifiserer capture-hookene fra Task 6). Kjør også `bry11`-originalen i Brython-modus etterpå — den skal være uendret (ingen regresjon).

- [ ] **Step 4: Publiseringsstøtte (mpydata_-embed)**

Publiserte Brython-dashboards baker inn data som `<script type="application/json" id="brythondata_<navn>">`-tags som motoren leser. Finn skrivesiden:

```bash
grep -rn "brythondata_" index.html js/
```

Speil funnene for micropython-modusen med prefikset `mpydata_` (motoren leser allerede tags med det prefikset — Task 3). Hvis skrivesiden er modus-gated (f.eks. `activeEditorMode === 'brython'`), utvid gaten til også å dekke `'micropython'` med riktig prefiks. Verifiser ved å publisere/eksportere mp03-dashboardet og åpne resultatet: dashboardet skal virke uten `# load`-kilder.

- [ ] **Step 5: Fullfør felle-dokumentasjonen**

Oppdater `micropython/NOTAT_fase0.md` med en «Feller funnet under portingen»-seksjon (alt som ble fikset i Task 4-6-røykene), og legg en énlinjes peker i headerkommentaren til `micropython/pandas_mpy.py`.

- [ ] **Step 6: Merge til master og push (safestat)**

```bash
python3 -m pytest micropython/tests/ -v          # alt grønt
git checkout master && git pull
git merge micropython-mode
git push origin master
```

- [ ] **Step 7: Sync til openstat**

`scripts/sync_check.sh` dekker ikke UI/js — kopier manuelt (samme behandling som brython/):

```bash
cp -r micropython ../openstat/micropython
cp js/micropython-engine.js ../openstat/js/micropython-engine.js
cp examples/mp0*.txt ../openstat/examples/
```

Gjenta deretter Task 7 Step 1-6 og Task 8 Step 2 i `../openstat/index.html` (openstats index.html drifter fritt — IKKE byte-kopier hele fila; det er denne fella som tidligere slettet dash-oppføringer). Kjør browser-røyken (Task 7 Step 7) mot openstat, commit og push openstat.

- [ ] **Step 8: Rapporter**

Si fra til Hans: «pushet og live på …» med begge Pages-URL-ene, boot-tid-tallet fra fase 0, og listen over dialekt-feller som ble funnet.
