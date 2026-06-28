"""Translate a microdata script into a runnable Python program.

The microdata ``MicroParser`` turns each line into an instruction dict (the IR);
this module walks that IR and emits thin calls to the runtime ops:

    backend="pandas" -> m2py_runtime.pandas_ops on an eager pd.DataFrame
    backend="polars" -> m2py_runtime.polars_ops on a lazy pl.LazyFrame
                        (collected with the streaming engine at the end)

The emitted program is standalone (given the runtime package on PYTHONPATH) and
is the artifact you can run offline — e.g. send the string to a worker / API and
execute it natively where polars' streaming engine and real files exist.

Unsupported verbs (or, for polars, expressions the compiler can't map) are
emitted as ``# UNTRANSLATED:`` comments — never silently-wrong code. Call
:func:`unsupported` to list them for a script without generating.
"""

import m2py
from m2py_runtime.exprcompile import compile_expr, UnsupportedExpr

# TRANSFORM verbs reassign the working frame (df / lf -> new frame).
TRANSFORM = {
    "generate", "replace", "recode", "keep", "drop", "rename", "destring",
    "collapse", "aggregate", "merge",
}
# ANALYSIS verbs compute a side result and PRINT it; the working frame is
# unchanged (matching the emulator, where summarize/tabulate/regress don't alter
# the active dataset).
ANALYSIS = {"summarize", "tabulate", "correlate", "regress"}
# PLOT verbs build a plotly Figure (terminal, like analysis). Offline they are
# written to an HTML file; in-memory (tests) the figure object is left in scope.
PLOT = {"histogram", "barchart", "scatter", "boxplot"}

SUPPORTED = TRANSFORM | ANALYSIS | PLOT

# Options each verb actually honours. Any option on a line that is NOT listed
# here makes the line UNTRANSLATED — so an unrecognised flag (e.g. a tabulate
# formatting option) is surfaced, never silently dropped. Keep these in sync
# with what _emit / _emit_analysis and the runtime ops implement.
HANDLED_OPTIONS = {
    "generate": set(), "replace": set(), "recode": set(), "rename": set(),
    "keep": set(), "drop": set(),
    "destring": {"force"},                 # always coerces == force semantics
    "collapse": {"by"}, "aggregate": {"by"},
    "merge": {"on", "outer_join"},
    "summarize": {"by", "gini", "iqr"},
    # two-way is via args, not an option; freq just shows counts (always on)
    "tabulate": {"by", "missing", "freq", "chi2", "top", "bottom",
                 "cellpct", "rowpct", "colpct", "cell", "row", "col"},
    "correlate": set(),
    "regress": set(),
    # plots: v1 supports the core forms; grouped/stat/styling options deferred
    "histogram": {"bin", "nbins"},      # microdata's option is bin(); 'bins' is flagged
    "barchart": set(),
    "scatter": set(),
    "boxplot": set(),
}


def _unhandled_options(instr):
    """Return option names present on this instruction that the translator does
    not honour (so the caller can mark the line UNTRANSLATED)."""
    cmd = instr["command"]
    opts = instr.get("options") or {}
    return sorted(set(opts) - HANDLED_OPTIONS.get(cmd, set()))


def _merge_parts(args, opts):
    """Resolve a merge instruction to (name, key, how, select).

    Handles the list forms ``merge X on K`` / ``merge X, on(K)`` and the
    into-form ``merge a b into X on K``. ``how`` follows the emulator: outer when
    the ``outer_join`` option is set, else left. ``select`` is the column subset
    to bring from the right frame (into-form), or None for all columns.
    """
    how = "outer" if opts.get("outer_join") else "left"
    if isinstance(args, dict):                      # merge a b into X on K
        return args.get("into"), args.get("on") or opts.get("on"), how, args.get("vars")
    name = args[0]
    key = opts.get("on")
    if "on" in args:
        i = args.index("on")
        if i + 1 < len(args):
            key = args[i + 1]
    return name, key, how, None


def _check_polars_expr(instr):
    """Raise UnsupportedExpr if the polars backend can't compile this line's
    expression/condition (so the caller can mark it UNTRANSLATED)."""
    cmd, args, cond = instr["command"], instr["args"], instr["condition"]
    if cmd in ("generate", "replace"):
        if not isinstance(args, dict) or "expression" not in args:
            raise UnsupportedExpr(f"unexpected {cmd} args shape")
        compile_expr(args["expression"])
    if cond:
        compile_expr(cond, condition=True)


def _emit(instr, backend):
    cmd, args, opts, cond = (
        instr["command"], instr["args"], instr["options"], instr["condition"])
    var = "lf" if backend == "polars" else "df"

    if cmd in ("generate", "replace"):
        if not isinstance(args, dict) or "expression" not in args:
            return None
        return (f"{var} = ops.{cmd}({var}, target={args['target']!r}, "
                f"expression={args['expression']!r}, cond={cond!r})")
    if cmd == "rename":
        return f"{var} = ops.rename({var}, old={args['old']!r}, new={args['new']!r})"
    if cmd == "destring":
        return f"{var} = ops.destring({var}, vars={args['vars']!r})"
    if cmd == "recode":
        return (f"{var} = ops.recode({var}, vars={args['vars']!r}, "
                f"rules={args['rules']!r}, prefix={args.get('prefix')!r})")
    if cmd in ("keep", "drop"):
        vars_ = args.get("vars") or None
        return f"{var} = ops.{cmd}({var}, vars={vars_!r}, cond={cond!r})"
    if cmd in ("collapse", "aggregate"):
        return (f"{var} = ops.{cmd}({var}, targets={args['targets']!r}, "
                f"by={opts.get('by')!r})")
    if cmd == "merge":
        name, key, how, sel = _merge_parts(args, opts)
        if not name or not key:
            return None
        rhs = (f'pl.scan_parquet("{name}.parquet")' if backend == "polars"
               else f'pd.read_parquet("{name}.parquet")')
        lines = [f"_{name} = datasets[{name!r}] if datasets else {rhs}"]
        if sel:                                     # into-form: bring only these cols (+ key)
            cols = [key] + [v for v in sel if v != key]
            if backend == "polars":
                lines.append(f"_{name} = _{name}.select({cols!r})")
            else:
                lines.append(f"_{name} = _{name}[{cols!r}]")
        lines.append(f"{var} = ops.merge({var}, _{name}, on={key!r}, how={how!r})")
        return "\n".join(lines)
    return None


def _frame_expr(backend, cond):
    """The frame an analysis/plot reads: the working frame, or a row-filtered
    view of it when the verb carries an ``if`` condition. Uses the tested ``keep``
    op so the condition is applied without mutating the working frame."""
    base = "lf" if backend == "polars" else "df"
    if cond:
        return f"ops.keep({base}, vars=None, cond={cond!r})"
    return base


def _emit_analysis(instr, backend, idx):
    """Emit an analysis step: compute a result from the (unchanged) working frame
    and store/print it. Returns the code line, or None if unhandled."""
    cmd, args, opts = instr["command"], instr["args"], instr["options"]
    var = _frame_expr(backend, instr["condition"])
    res = f"result_{idx}"
    vars_ = list(args) if args else None

    if cmd == "summarize":
        call = (f"ops.summarize({var}, vars={vars_!r}, by={opts.get('by')!r}, "
                f"gini={bool(opts.get('gini'))!r}, iqr={bool(opts.get('iqr'))!r})")
    elif cmd == "tabulate":
        cell = bool(opts.get("cellpct") or opts.get("cell"))
        row = bool(opts.get("rowpct") or opts.get("row"))
        col = bool(opts.get("colpct") or opts.get("col"))
        call = (f"ops.tabulate({var}, vars={vars_!r}, by={opts.get('by')!r}, "
                f"missing={bool(opts.get('missing'))!r}, "
                f"cellpct={cell!r}, rowpct={row!r}, colpct={col!r}, "
                f"chi2={bool(opts.get('chi2'))!r}, "
                f"top={opts.get('top')!r}, bottom={opts.get('bottom')!r})")
    elif cmd == "correlate":
        call = f"ops.correlate({var}, vars={vars_!r})"
    elif cmd == "regress":
        if not vars_:
            return None
        call = f"ops.regress({var}, dep={vars_[0]!r}, indep={vars_[1:]!r})"
    else:
        return None
    return f"{res} = {call}\nprint({res})"


def _emit_plot(instr, backend, idx, write):
    """Emit a plot step: build a plotly Figure from the (unchanged) working frame
    into ``fig_<idx>``; write it to an HTML file in file mode."""
    cmd, args, opts = instr["command"], instr["args"], instr["options"]
    var = _frame_expr(backend, instr["condition"])
    vars_ = args.get("vars") if isinstance(args, dict) else None
    if not vars_:
        return None
    fig = f"fig_{idx}"
    if cmd == "histogram":
        raw = opts.get("bin") or opts.get("nbins")  # microdata option is bin()
        try:
            bins = int(raw) if raw else 30
        except (ValueError, TypeError):
            bins = 30
        call = f"ops.histogram({var}, vars={vars_!r}, bins={bins})"
    elif cmd == "barchart":
        call = f"ops.barchart({var}, vars={vars_!r})"
    elif cmd == "scatter":
        if len(vars_) < 2:
            return None
        call = f"ops.scatter({var}, vars={vars_!r})"
    elif cmd == "boxplot":
        call = f"ops.boxplot({var}, vars={vars_!r})"
    else:
        return None
    line = f"{fig} = {call}"
    if write:
        line += f'\n{fig}.write_html("plot_{idx}.html")'
    return line


def translate(script, backend="pandas", source_path="df"):
    """Return a runnable Python program (string) for ``script``.

    ``source_path`` names the input parquet stem ("df" -> df.parquet). Pass
    ``None`` to operate on an in-memory ``df`` (pandas) / ``data`` (polars)
    provided by the caller's namespace — used by the test harness. ``datasets``
    (a dict) may also be provided for merge inputs.
    """
    parser = m2py.MicroParser()

    if backend == "polars":
        header = ["import polars as pl",
                  "from m2py_runtime import polars_ops as ops",
                  "datasets = globals().get('datasets')"]
        if source_path is not None:
            header.append(f'lf = pl.scan_parquet("{source_path}.parquet")')
        else:
            header.append("lf = data if isinstance(data, pl.LazyFrame) else pl.LazyFrame(data)")
        footer = ['df = lf.collect(engine="streaming")']
        if source_path is not None:
            footer.append('df.write_parquet("result.parquet")')
    else:
        header = ["import pandas as pd",
                  "from m2py_runtime import pandas_ops as ops",
                  "datasets = globals().get('datasets')"]
        if source_path is not None:
            header.append(f'df = pd.read_parquet("{source_path}.parquet")')
        footer = ['df.to_parquet("result.parquet")'] if source_path is not None else []

    body = []
    idx = 0
    for line in script.splitlines():
        if not line.strip():
            continue
        instr = parser.parse_line(line)
        if not instr or instr["command"] in ("textblock", "endblock", "end"):
            continue
        cmd = instr["command"]
        if cmd not in SUPPORTED:
            body.append(f"# UNTRANSLATED ({cmd}): {line.strip()}")
            continue
        bad = _unhandled_options(instr)
        if bad:
            body.append(f"# UNTRANSLATED (unhandled option: {', '.join(bad)}): {line.strip()}")
            continue
        if backend == "polars":
            try:
                _check_polars_expr(instr)
            except UnsupportedExpr as e:
                body.append(f"# UNTRANSLATED (expr: {e}): {line.strip()}")
                continue
        if cmd in ANALYSIS:
            idx += 1
            emitted = _emit_analysis(instr, backend, idx)
        elif cmd in PLOT:
            idx += 1
            emitted = _emit_plot(instr, backend, idx, write=source_path is not None)
        else:
            emitted = _emit(instr, backend)
        body.append(emitted if emitted else f"# UNTRANSLATED: {line.strip()}")

    return "\n".join(header + [""] + body + [""] + footer) + "\n"


def run(script, datasets, backend="polars", active=None):
    """Translate ``script`` and execute it locally, returning the resulting
    DataFrame (pandas for backend="pandas", polars for "polars").

    ``datasets`` is a dict of name -> pandas.DataFrame; ``active`` names the
    working dataset (defaults to the first). This mirrors what an offline worker
    / Anvil endpoint does: receive the microdata script as a string, translate
    it, and execute the generated code. Convenience for local testing.
    """
    if active is None:
        active = next(iter(datasets))
    code = translate(script, backend=backend, source_path=None)
    if backend == "polars":
        import polars as pl
        ns = {"data": pl.LazyFrame(datasets[active]), "pl": pl,
              "datasets": {k: pl.LazyFrame(v) for k, v in datasets.items()}}
        exec(code, ns)
        return ns["df"]
    import pandas as pd
    ns = {"df": datasets[active].copy(), "pd": pd, "datasets": dict(datasets)}
    exec(code, ns)
    return ns["df"]


def unsupported(script):
    """Return the list of script lines that would be emitted UNTRANSLATED for
    the polars backend (verb unknown or expression uncompilable)."""
    out = []
    parser = m2py.MicroParser()
    for line in script.splitlines():
        if not line.strip():
            continue
        instr = parser.parse_line(line)
        if not instr or instr["command"] in ("textblock", "endblock", "end"):
            continue
        if instr["command"] not in SUPPORTED:
            out.append(line.strip())
            continue
        if _unhandled_options(instr):
            out.append(line.strip())
            continue
        try:
            _check_polars_expr(instr)
        except UnsupportedExpr:
            out.append(line.strip())
    return out
