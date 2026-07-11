# Persistent Brython execution environment for openstat/safestat.
# Pattern from code2web's brython_shared_module.py; output uses the app's
# stdout embed-marker protocol so buildOutputNodes() renders it unchanged.
import sys, json, traceback
from io import StringIO

_EMBED_S = '__micro_transform_start_'
_EMBED_E = '__micro_transform_end__'

_shared_vars = {}
_last_error = ''

def _fmt(obj):
    """Format one object as output text (embed markers for figures/frames)."""
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
    """User-facing show(): print each object in its rendered form."""
    for o in objs:
        print(_fmt(o))

_shared_vars['show'] = _show

def _execute_code(code):
    """Run code in the persistent globals; return output text ('' on error)."""
    global _last_error
    _last_error = ''
    buf = StringIO()
    old = sys.stdout
    sys.stdout = buf
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
                    tail_code = compile(tail_src, '<brython>', 'eval')
                except SyntaxError:
                    continue
                head_src = chr(10).join(lines[:i]) or 'pass'
                try:
                    head_code = compile(head_src, '<brython>', 'exec')
                except SyntaxError:
                    continue
                exec(head_code, _shared_vars)
                result = eval(tail_code, _shared_vars)
                displayed = True
                break
        if not displayed:
            exec(compile(code, '<brython>', 'exec'), _shared_vars)
        out = buf.getvalue()
        shown = _fmt(result)
        if shown:
            out = out + ('' if not out or out.endswith(chr(10)) else chr(10)) + shown
        return out
    except Exception:
        _last_error = traceback.format_exc()
        return buf.getvalue()
    finally:
        sys.stdout = old

def _get_last_error():
    return _last_error

def _register_module(name, source):
    """Lazy lib-loading (engine calls this): make `source` importable as
    module `name`. Idempotent; returns '' on success, traceback on failure."""
    import types
    if name in sys.modules:
        return ''
    mod = types.ModuleType(name)
    try:
        exec(compile(source, name + '.py', 'exec'), mod.__dict__)
    except Exception:
        return traceback.format_exc()
    sys.modules[name] = mod
    return ''

def _alias_module(alias, canonical):
    """Make `import alias` resolve to already-registered module `canonical`.
    Dotted alias ('matplotlib.pyplot'): foreldremodulen må allerede ligge i
    sys.modules (registrer den plain aliasen først); barnet settes som
    attributt på forelderen så `import a.b as x` binder riktig."""
    if canonical not in sys.modules:
        return 'Ukjent modul: ' + canonical
    if '.' in alias:
        parent_name, _, child = alias.rpartition('.')
        if parent_name not in sys.modules:
            return 'Ukjent foreldremodul: ' + parent_name
        setattr(sys.modules[parent_name], child, sys.modules[canonical])
    sys.modules[alias] = sys.modules[canonical]
    return ''

def _bind_datasets(spec_json):
    """Bind datasets from JS into user globals. spec: {name: {kind, payload}}.
    kind 'csv' → payload is CSV text; kind 'columns' → payload is {col: [values]}."""
    try:
        import pandas_brython as _pd
        spec = json.loads(spec_json) if isinstance(spec_json, str) else spec_json
        for name, d in spec.items():
            if d['kind'] == 'csv':
                _shared_vars[name] = _pd.read_csv(StringIO(d['payload']))
            else:
                # JSON null (from JS) arrives as None; pandas_brython's
                # isna()/dropna() only recognize its own nan sentinel.
                cols = {k: [_pd.nan if v is None else v for v in vals]
                        for k, vals in d['payload'].items()}
                _shared_vars[name] = _pd.DataFrame(cols)
        return ''
    except Exception:
        return traceback.format_exc()
