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
        # Statement-aware trailing-expression detection (no `ast` — must run
        # under Brython 3.12 too). REPL semantics: if the code's final
        # top-level statement is itself an expression, display its value.
        # A top-level statement always starts at column 0 (no leading
        # space/tab). But column-0 is only *necessary*, not *sufficient*,
        # evidence of "this is where the final top-level statement begins":
        # - Black-style wrapping puts a lone closing ')' at column 0
        #   (`pe.scatter(\n    df, ...\n)`), so the LAST column-0 line can be
        #   a continuation fragment, not the statement start.
        # - Unindented continuations (`sum(nums,\n0)`) put a fragment like
        #   '0)' at column 0 too.
        # - A bare multi-line triple-quoted string's last physical line
        #   ('b"""') is not valid source on its own.
        # So: collect column-0 candidate line indices from the END upward
        # (capped, to bound pathological inputs) and try each one as a
        # prospective statement start, taking tail = lines[i:] joined. The
        # first candidate whose tail compiles in 'eval' mode AND whose head
        # (lines[:i], or 'pass' if empty) compiles in 'exec' mode wins: exec
        # the head, eval+display the tail. If the head fails to compile for
        # that candidate, keep scanning upward rather than giving up. If no
        # candidate ever produces a compilable (head, tail) pair, fall back
        # to plain-exec of the whole code with no display — identical to
        # today's behavior. This still keeps indented-last-line-inside-a-
        # block safe: the only column-0 candidate is the block header,
        # whose tail (header + body) cannot compile as 'eval' (a for/if/def
        # is not a valid expression), so it plain-execs instead of evaling
        # the inner line out of context.
        #
        # Two bounds guard against pathological inputs while staying correct
        # for editor-sized scripts: the scan cap (1000) bounds how many
        # column-0 lines get probed — compiling ~1000 small string slices is
        # negligible cost, and real scripts don't run deeper than that. But
        # a single trailing expression can still legitimately spill more
        # than 1000 unindented lines (e.g. a long literal list, one item per
        # line); if the cap is hit before line 0 is reached, line 0 itself
        # is appended as a final fallback candidate (whole code as tail,
        # head='pass'), so a single-statement script is always found
        # regardless of length.
        lines = code.split(chr(10))
        while lines and lines[-1].strip() == '':
            lines.pop()
        result = None
        displayed = False
        if lines:
            candidates = []
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i]
                if line and line[:1] not in (' ', chr(9)):
                    candidates.append(i)
                    if len(candidates) >= 1000:
                        break
            if 0 not in candidates:
                candidates.append(0)
            for i in candidates:
                tail_src = chr(10).join(lines[i:])
                tail_stripped = tail_src.strip()
                if not tail_stripped or tail_stripped.startswith('#'):
                    continue
                try:
                    tail_code = compile(tail_src, '<micropython>', 'eval')
                except SyntaxError:
                    continue
                head_src = chr(10).join(lines[:i]) or 'pass'
                try:
                    head_code = compile(head_src, '<micropython>', 'exec')
                except SyntaxError:
                    continue
                exec(head_code, _shared_vars)
                result = eval(tail_code, _shared_vars)
                displayed = True
                break
        if not displayed:
            exec(compile(code, '<micropython>', 'exec'), _shared_vars)
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
