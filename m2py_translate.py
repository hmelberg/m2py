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

# verbs the translator understands (data shaping / stats / merge — not import)
SUPPORTED = {
    "generate", "replace", "recode", "keep", "drop", "rename", "destring",
    "collapse", "aggregate", "merge", "summarize",
}


def _merge_parts(args):
    """merge IR args=[name, 'on', key] -> (name, key, how)."""
    name, key = args[0], None
    if "on" in args:
        i = args.index("on")
        if i + 1 < len(args):
            key = args[i + 1]
    return name, key


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
    if cmd == "summarize":
        vars_ = list(args) if args else None
        return f"{var} = ops.summarize({var}, vars={vars_!r}, by={opts.get('by')!r})"
    if cmd == "merge":
        name, key = _merge_parts(args)
        rhs = (f'pl.scan_parquet("{name}.parquet")' if backend == "polars"
               else f'pd.read_parquet("{name}.parquet")')
        load = f"_{name} = datasets[{name!r}] if datasets else {rhs}"
        return f"{load}\n{var} = ops.merge({var}, _{name}, on={key!r})"
    return None


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
    for line in script.splitlines():
        if not line.strip():
            continue
        instr = parser.parse_line(line)
        if not instr or instr["command"] in ("textblock", "endblock", "end"):
            continue
        if instr["command"] not in SUPPORTED:
            body.append(f"# UNTRANSLATED ({instr['command']}): {line.strip()}")
            continue
        if backend == "polars":
            try:
                _check_polars_expr(instr)
            except UnsupportedExpr as e:
                body.append(f"# UNTRANSLATED (expr: {e}): {line.strip()}")
                continue
        emitted = _emit(instr, backend)
        body.append(emitted if emitted else f"# UNTRANSLATED: {line.strip()}")

    return "\n".join(header + [""] + body + [""] + footer) + "\n"


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
        try:
            _check_polars_expr(instr)
        except UnsupportedExpr:
            out.append(line.strip())
    return out
