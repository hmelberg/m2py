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

import re

import m2py
from m2py_runtime.exprcompile import compile_expr, UnsupportedExpr

# prediction verbs (transform: fit a model and add predicted/residual columns).
# poisson-predict is NOT a real microdata command (the emulator rejects it).
PREDICT = {
    "regress-predict": "regress_predict", "logit-predict": "logit_predict",
    "probit-predict": "probit_predict", "mlogit-predict": "mlogit_predict",
    "negative-binomial-predict": "negative_binomial_predict",
}
# binary/multinomial predicts: `predicted` is Xβ, `probabilities` is P(Y=…)
PREDICT_BINARY = {"logit-predict", "probit-predict", "mlogit-predict"}
# TRANSFORM verbs reassign the working frame (df / lf -> new frame).
TRANSFORM = {
    "generate", "replace", "recode", "keep", "drop", "rename", "destring",
    "collapse", "aggregate", "merge", "reshape-to-panel", "reshape-from-panel",
    "ivregress-predict", "regress-panel-predict",
} | set(PREDICT)
# ANALYSIS verbs compute a side result and PRINT it; the working frame is
# unchanged (matching the emulator, where summarize/tabulate/regress don't alter
# the active dataset).
# regression family -> op name (analysis verbs returning a coefficient table)
REGRESSION = {
    "regress": "regress", "logit": "logit", "probit": "probit",
    "poisson": "poisson", "negative-binomial": "negative_binomial",
}
# survival verbs -> op name (analysis verbs, lifelines)
SURVIVAL = {"cox": "cox", "kaplan-meier": "kaplan_meier", "weibull": "weibull"}
# panel & IV regression (analysis verbs, linearmodels/statsmodels)
PANEL_IV = {"regress-panel", "regress-panel-diff", "ivregress"}
ANALYSIS = ({"summarize", "tabulate", "correlate", "mlogit", "rdd",
             "normaltest", "ci", "anova", "hausman",
             "summarize-panel", "tabulate-panel"}
            | set(REGRESSION) | set(SURVIVAL) | PANEL_IV)
# PLOT verbs build a plotly Figure (terminal, like analysis). Offline they are
# written to an HTML file; in-memory (tests) the figure object is left in scope.
PLOT = {"histogram", "barchart", "scatter", "boxplot",
        "piechart", "hexbin", "sankey", "coefplot"}

# dataset/session verbs — handled by the translate loop (they switch the active
# dataset / create variables), not by the per-frame emitters.
SESSION = {"create-dataset", "use", "clone-dataset", "delete-dataset",
           "rename-dataset"}
# label verbs are display-only in the emulator (the data keeps its codes), so
# they are no-ops on the offline data — recorded as comments, not flagged.
LABELS = {"define-labels", "assign-labels", "drop-labels", "list-labels"}

SUPPORTED = TRANSFORM | ANALYSIS | PLOT | SESSION | LABELS

# Options each verb actually honours. Any option on a line that is NOT listed
# here makes the line UNTRANSLATED — so an unrecognised flag (e.g. a tabulate
# formatting option) is surfaced, never silently dropped. Keep these in sync
# with what _emit / _emit_analysis and the runtime ops implement.
HANDLED_OPTIONS = {
    "generate": set(), "replace": set(), "recode": set(), "rename": set(),
    "keep": set(), "drop": set(),
    "destring": {"force"},                 # always coerces == force semantics
    "reshape-to-panel": set(),
    "reshape-from-panel": set(),
    "collapse": {"by"}, "aggregate": {"by"},
    "merge": {"on", "outer_join"},
    "summarize": {"by", "gini", "iqr"},
    # two-way is via args, not an option; freq just shows counts (always on)
    "tabulate": {"by", "missing", "freq", "chi2", "top", "bottom",
                 "cellpct", "rowpct", "colpct", "cell", "row", "col"},
    "correlate": {"pairwise", "covariance"},   # sig/obs (text/extra cols) deferred
    "normaltest": set(),
    "ci": {"level"},
    "summarize-panel": {"gini", "iqr"},
    # tabulate-panel: tid is the columns; summarize()-volume variant deferred
    "tabulate-panel": {"missing", "rowpct", "colpct", "row", "col"},
    "anova": set(),
    "hausman": set(),
    # regression family: noconstant only; or/irr/robust/exposure/level deferred
    "regress": {"noconstant"},
    "logit": {"noconstant"},
    "probit": {"noconstant"},
    "poisson": {"noconstant"},
    "negative-binomial": {"noconstant"},
    # panel: effect selectors; robust/level/cluster deferred
    "regress-panel": {"fe", "re", "random", "be", "pooled"},
    # IV: only 2SLS implemented; liml/gmm/robust/level deferred
    "ivregress": {"tsls", "2sls"},
    "ivregress-predict": {"predicted", "residuals", "tsls", "2sls"},
    "regress-panel-diff": {"pooled"},
    "regress-panel-predict": {"fe", "re", "random", "be", "pooled",
                              "predicted", "residuals", "effects"},
    "mlogit": {"noconstant"},
    # rdd: local-polynomial OLS (sharp + fuzzy); cluster/robust/derivate deferred
    "rdd": {"cutoff", "polynomial", "fuzzy"},
    # survival: by/level/hazard variants deferred
    "cox": set(),
    "kaplan-meier": set(),
    "weibull": set(),
    # plots
    "histogram": {"bin", "nbins", "discrete", "percent", "density", "freq", "normal"},
    # statistic via parenthesised (stat), not a flag
    "barchart": {"over", "horizontal", "stack"},
    "scatter": {"by", "color"},
    "boxplot": {"over"},
    "piechart": set(),                  # (percent) via parenthesised stat
    "hexbin": {"bin", "nbins"},
    "sankey": set(),
    "coefplot": {"standardize", "noconstant"},
    # predict variants (transform): name the predicted/residual columns
    # (binary outcomes also accept `probabilities`; regress `cooksd` deferred)
    **{v: ({"predicted", "residuals", "probabilities", "noconstant"}
           if v in PREDICT_BINARY else {"predicted", "residuals", "noconstant"})
       for v in PREDICT},
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


def _expr_polars_ok(expr):
    """An expression is fine for the polars backend if exprcompile maps it
    natively OR every function it calls is a known microdata function / numpy —
    in which case the polars op's pandas-eval fallback handles it. Only genuinely
    unknown function names make it untranslatable."""
    import ast
    try:
        compile_expr(expr)
        return True
    except UnsupportedExpr:
        pass
    known = set(m2py.get_microdata_functions()) | {
        "int", "min", "max", "abs", "round", "len", "str", "float", "where", "np"}
    try:
        tree = ast.parse(m2py._micro_expr_fixup(expr), mode="eval")
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                    and f.value.id == "np":
                continue                          # numpy fn -> fallback handles it
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
            if name and name not in known:
                return False
    return True


def _check_polars_expr(instr):
    """Raise UnsupportedExpr if the polars backend can neither compile nor fall
    back on this line's expression/condition (i.e. an unknown function)."""
    cmd, args, cond = instr["command"], instr["args"], instr["condition"]
    if cmd in ("generate", "replace"):
        if not isinstance(args, dict) or "expression" not in args:
            raise UnsupportedExpr(f"unexpected {cmd} args shape")
        if not _expr_polars_ok(args["expression"]):
            raise UnsupportedExpr("unknown function in expression")
    if cond and not _expr_polars_ok(cond):
        raise UnsupportedExpr("unknown function in condition")


def _sanitize(name):
    """A valid Python identifier suffix for a dataset name."""
    s = re.sub(r"\W", "_", str(name))
    return s if s and not s[0].isdigit() else "d_" + s


def _dsvar(backend, name):
    """Variable holding the working frame for a named dataset."""
    return f"{'lf' if backend == 'polars' else 'df'}_{_sanitize(name)}"


def _load_dataset(backend, name, source_path):
    """Emit the line that materialises dataset ``name`` into its variable: from
    ``<name>.parquet`` (file mode) or the in-memory ``datasets`` dict."""
    var = _dsvar(backend, name)
    if backend == "polars":
        src = (f'pl.scan_parquet("{name}.parquet")' if source_path is not None
               else f"datasets[{name!r}]")
    else:
        src = (f'pd.read_parquet("{name}.parquet")' if source_path is not None
               else f"datasets[{name!r}].copy()")
    return f"{var} = {src}"


def _emit(instr, backend, frame=None, known=()):
    cmd, args, opts, cond = (
        instr["command"], instr["args"], instr["options"], instr["condition"])
    var = frame or ("lf" if backend == "polars" else "df")

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
    if cmd == "reshape-to-panel":
        prefixes = args.get("prefixes") if isinstance(args, dict) else None
        if not prefixes:
            return None
        return f"{var} = ops.reshape_to_panel({var}, prefixes={prefixes!r})"
    if cmd == "reshape-from-panel":
        return f"{var} = ops.reshape_from_panel({var})"
    if cmd == "regress-panel-predict":
        if not isinstance(args, (list, tuple)) or len(args) < 2:
            return None
        dep, indep = args[0], list(args[1:])
        effect = next((e for e in ("re", "be", "pooled") if opts.get(e)), "fe")
        if opts.get("random"):
            effect = "re"
        pred = opts.get("predicted")
        pred = "predicted" if pred in (None, True) else pred
        res = opts.get("residuals")
        res = "residuals" if res is True else res
        eff = opts.get("effects")
        eff = "effects" if eff is True else eff
        return (f"{var} = ops.regress_panel_predict({var}, dep={dep!r}, indep={indep!r}, "
                f"effect={effect!r}, predicted={pred!r}, residuals={res!r}, effects={eff!r})")
    if cmd == "ivregress-predict":
        if not isinstance(args, dict) or not args.get("dep") or not args.get("endog"):
            return None
        res = opts.get("residuals")
        res = "residuals" if res is True else res
        pred = opts.get("predicted")
        pred = "predicted" if pred in (None, True) else pred
        return (f"{var} = ops.ivregress_predict({var}, dep={args['dep']!r}, "
                f"exog={args.get('exog', [])!r}, endog={args['endog']!r}, "
                f"instruments={args.get('instruments', [])!r}, "
                f"predicted={pred!r}, residuals={res!r})")
    if cmd in PREDICT:
        if not isinstance(args, (list, tuple)) or len(args) < 2:
            return None
        dep, indep = args[0], list(args[1:])
        res = opts.get("residuals")
        res = "residuals" if res is True else res          # name, or None
        if cmd in PREDICT_BINARY:
            pred = opts.get("predicted")                   # Xβ only if requested
            pred = "predicted" if pred is True else pred
            prob = opts.get("probabilities")
            prob = "probabilities" if prob is True else prob
            return (f"{var} = ops.{PREDICT[cmd]}({var}, dep={dep!r}, indep={indep!r}, "
                    f"predicted={pred!r}, probabilities={prob!r}, residuals={res!r}, "
                    f"noconstant={bool(opts.get('noconstant'))!r})")
        pred = opts.get("predicted")                       # default 'predicted'
        pred = "predicted" if pred in (None, True) else pred
        return (f"{var} = ops.{PREDICT[cmd]}({var}, dep={dep!r}, indep={indep!r}, "
                f"predicted={pred!r}, residuals={res!r}, "
                f"noconstant={bool(opts.get('noconstant'))!r})")
    if cmd == "merge":
        name, key, how, sel = _merge_parts(args, opts)
        if not name or not key:
            return None
        lines = []
        if name in known:                           # already a dataset variable
            other = _dsvar(backend, name)
        else:
            other = f"_{name}"
            rhs = (f'pl.scan_parquet("{name}.parquet")' if backend == "polars"
                   else f'pd.read_parquet("{name}.parquet")')
            lines.append(f"{other} = datasets[{name!r}] if datasets else {rhs}")
        if sel:                                     # into-form: bring only these cols (+ key)
            cols = [key] + [v for v in sel if v != key]
            lines.append(f"{other} = {other}.select({cols!r})" if backend == "polars"
                         else f"{other} = {other}[{cols!r}]")
        lines.append(f"{var} = ops.merge({var}, {other}, on={key!r}, how={how!r})")
        return "\n".join(lines)
    return None


def _frame_expr(base, cond):
    """The frame an analysis/plot reads: the working frame ``base``, or a
    row-filtered view of it when the verb carries an ``if`` condition (applied via
    the tested ``keep`` op, without mutating the working frame)."""
    if cond:
        return f"ops.keep({base}, vars=None, cond={cond!r})"
    return base


def _emit_analysis(instr, backend, idx, frame=None):
    """Emit an analysis step: compute a result from the (unchanged) working frame
    and store/print it. Returns the code line, or None if unhandled."""
    cmd, args, opts = instr["command"], instr["args"], instr["options"]
    base = frame or ("lf" if backend == "polars" else "df")
    var = _frame_expr(base, instr["condition"])
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
        call = (f"ops.correlate({var}, vars={vars_!r}, "
                f"pairwise={bool(opts.get('pairwise'))!r}, "
                f"covariance={bool(opts.get('covariance'))!r})")
    elif cmd == "summarize-panel":
        call = (f"ops.summarize_panel({var}, vars={vars_!r}, "
                f"gini={bool(opts.get('gini'))!r}, iqr={bool(opts.get('iqr'))!r})")
    elif cmd == "tabulate-panel":
        if not vars_:
            return None
        cell = bool(opts.get("rowpct") or opts.get("row"))
        col = bool(opts.get("colpct") or opts.get("col"))
        call = (f"ops.tabulate_panel({var}, var1={vars_[0]!r}, "
                f"missing={bool(opts.get('missing'))!r}, "
                f"rowpct={cell!r}, colpct={col!r})")
    elif cmd == "normaltest":
        call = f"ops.normaltest({var}, vars={vars_!r})"
    elif cmd == "ci":
        try:
            level = int(opts.get("level", 95))
        except (ValueError, TypeError):
            level = 95
        call = f"ops.ci({var}, vars={vars_!r}, level={level!r})"
    elif cmd == "anova":
        if not vars_ or len(vars_) < 2:
            return None
        call = f"ops.anova({var}, dep={vars_[0]!r}, factors={vars_[1:]!r})"
    elif cmd == "hausman":
        if not vars_ or len(vars_) < 2:
            return None
        call = f"ops.hausman({var}, dep={vars_[0]!r}, indep={vars_[1:]!r})"
    elif cmd in REGRESSION:
        if not vars_ or len(vars_) < 2:
            return None
        call = (f"ops.{REGRESSION[cmd]}({var}, dep={vars_[0]!r}, "
                f"indep={vars_[1:]!r}, noconstant={bool(opts.get('noconstant'))!r})")
    elif cmd in SURVIVAL:
        if not vars_ or len(vars_) < 2:
            return None
        event, duration, covars = vars_[0], vars_[1], vars_[2:]
        if cmd == "cox":
            call = f"ops.cox({var}, event={event!r}, duration={duration!r}, covars={covars!r})"
        else:
            call = f"ops.{SURVIVAL[cmd]}({var}, event={event!r}, duration={duration!r})"
    elif cmd == "regress-panel":
        if not vars_ or len(vars_) < 2:
            return None
        effect = next((e for e in ("re", "be", "pooled") if opts.get(e)), "fe")
        if opts.get("random"):
            effect = "re"
        call = (f"ops.regress_panel({var}, dep={vars_[0]!r}, indep={vars_[1:]!r}, "
                f"effect={effect!r})")
    elif cmd == "regress-panel-diff":
        if not vars_ or len(vars_) < 3:
            return None
        call = (f"ops.regress_panel_diff({var}, dep={vars_[0]!r}, group={vars_[1]!r}, "
                f"treated={vars_[2]!r}, covars={vars_[3:]!r})")
    elif cmd == "ivregress":
        if not isinstance(args, dict) or not args.get("dep") or not args.get("endog"):
            return None
        call = (f"ops.ivregress({var}, dep={args['dep']!r}, exog={args.get('exog', [])!r}, "
                f"endog={args['endog']!r}, instruments={args.get('instruments', [])!r})")
    elif cmd == "mlogit":
        if not vars_ or len(vars_) < 2:
            return None
        call = f"ops.mlogit({var}, dep={vars_[0]!r}, indep={vars_[1:]!r})"
    elif cmd == "rdd":
        if not isinstance(args, dict) or not args.get("dep") or not args.get("runvar"):
            return None
        try:
            cutoff = float(opts.get("cutoff", 0))
        except (ValueError, TypeError):
            cutoff = 0.0
        try:
            poly = int(opts.get("polynomial", 1))
        except (ValueError, TypeError):
            poly = 1
        fuzzy = opts.get("fuzzy")
        fuzzy = None if fuzzy in (None, True) else fuzzy
        call = (f"ops.rdd({var}, dep={args['dep']!r}, runvar={args['runvar']!r}, "
                f"exog={args.get('exog', [])!r}, cutoff={cutoff!r}, "
                f"polynomial={poly!r}, fuzzy={fuzzy!r})")
    else:
        return None
    return f"{res} = {call}\nprint({res})"


def _emit_plot(instr, backend, idx, write, frame=None):
    """Emit a plot step: build a plotly Figure from the (unchanged) working frame
    into ``fig_<idx>``; write it to an HTML file in file mode."""
    cmd, args, opts = instr["command"], instr["args"], instr["options"]
    base = frame or ("lf" if backend == "polars" else "df")
    var = _frame_expr(base, instr["condition"])
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
        call = (f"ops.histogram({var}, vars={vars_!r}, bins={bins}, "
                f"discrete={bool(opts.get('discrete'))!r}, "
                f"percent={bool(opts.get('percent'))!r}, "
                f"density={bool(opts.get('density'))!r}, "
                f"normal={bool(opts.get('normal'))!r})")
    elif cmd == "barchart":
        # statistic comes from the parenthesised (stat) form -> args['stat'];
        # bare `, mean`-style flags are NOT honoured by the emulator, so they
        # remain unhandled options and the line is flagged.
        stat = args.get("stat", "count")
        call = (f"ops.barchart({var}, vars={vars_!r}, stat={stat!r}, "
                f"over={opts.get('over')!r}, "
                f"horizontal={bool(opts.get('horizontal'))!r}, "
                f"stack={bool(opts.get('stack'))!r})")
    elif cmd == "scatter":
        if len(vars_) < 2:
            return None
        by = opts.get("by") or opts.get("color")
        call = f"ops.scatter({var}, vars={vars_!r}, by={by!r})"
    elif cmd == "boxplot":
        call = f"ops.boxplot({var}, vars={vars_!r}, over={opts.get('over')!r})"
    elif cmd == "piechart":
        stat = args.get("stat", "count")     # (percent) via parenthesised stat
        call = f"ops.piechart({var}, vars={vars_!r}, stat={stat!r})"
    elif cmd == "hexbin":
        if len(vars_) < 2:
            return None
        raw = opts.get("bin") or opts.get("nbins")
        try:
            bins = int(raw) if raw else 30
        except (ValueError, TypeError):
            bins = 30
        call = f"ops.hexbin({var}, vars={vars_!r}, bins={bins})"
    elif cmd == "sankey":
        if len(vars_) < 2:
            return None
        call = f"ops.sankey({var}, vars={vars_!r})"
    elif cmd == "coefplot":
        reg_cmd = args.get("reg_cmd", "regress") if isinstance(args, dict) else "regress"
        if reg_cmd not in ("regress", "logit", "probit", "poisson") or len(vars_) < 2:
            return None                      # e.g. `coefplot y x1` -> reg_cmd='y'
        call = (f"ops.coefplot({var}, reg_cmd={reg_cmd!r}, dep={vars_[0]!r}, "
                f"indep={vars_[1:]!r}, standardize={bool(opts.get('standardize'))!r}, "
                f"noconstant={bool(opts.get('noconstant'))!r})")
    else:
        return None
    line = f"{fig} = {call}"
    if write:
        line += f'\n{fig}.write_html("plot_{idx}.html")'
    return line


def _expand_loops(script):
    """Unroll ``for ... end`` loops and apply ``let`` bindings at translate time,
    producing a flat script. microdata loops are statically unrollable (no nested
    for-blocks; semicolon `;` separates nested levels, space zips). Binding
    substitution (`$name`/`${expr}`/`++`) reuses the emulator's own
    ``_substitute_bindings`` for exact fidelity."""
    it = m2py.MicroInterpreter(metadata_path=None)   # used only for substitution
    parser = it.parser
    lines = script.splitlines()
    out = []

    def process(seq):
        i = 0
        while i < len(seq):
            sub = it._substitute_bindings(seq[i])
            instr = parser.parse_line(sub)
            if not instr:
                out.append(sub)
                i += 1
                continue
            cmd = instr["command"]
            if cmd == "let" and isinstance(instr["args"], dict):
                name, expr = instr["args"].get("name"), instr["args"].get("expression")
                try:
                    val = eval(expr, {"__builtins__": {}}, it._binding_eval_env())
                except Exception:
                    val = expr
                if name:
                    it.bindings[name] = val
                i += 1
                continue
            if cmd == "for" and isinstance(instr["args"], dict) and "levels" in instr["args"]:
                body, j = [], i + 1
                while j < len(lines):
                    bj = parser.parse_line(lines[j].strip())
                    if bj and bj["command"] == "end":
                        break
                    body.append(lines[j])
                    j += 1
                levels = instr["args"]["levels"]

                def step(idx):
                    if idx >= len(levels):
                        process(body)
                        return
                    lvl = levels[idx]
                    vals = lvl["values"]
                    n = len(vals[0]) if vals else 0
                    for k in range(n):
                        for vn, vl in zip(lvl["vars"], vals):
                            it.bindings[vn] = vl[k]
                        step(idx + 1)

                step(0)
                i = j + 1                       # skip the matching 'end'
                continue
            out.append(sub)
            i += 1

    process(lines)
    return "\n".join(out)


def translate(script, backend="pandas", source_path="df"):
    """Return a runnable Python program (string) for ``script``.

    ``source_path`` names the input parquet stem ("df" -> df.parquet). Pass
    ``None`` to operate on an in-memory ``df`` (pandas) / ``data`` (polars)
    provided by the caller's namespace — used by the test harness. ``datasets``
    (a dict) may also be provided for merge inputs.
    """
    parser = m2py.MicroParser()
    script = _expand_loops(script)               # unroll for-loops, apply let bindings

    if backend == "polars":
        header = ["import polars as pl",
                  "from m2py_runtime import polars_ops as ops",
                  "datasets = globals().get('datasets')"]
        implicit = (f'lf = pl.scan_parquet("{source_path}.parquet")' if source_path is not None
                    else "lf = data if isinstance(data, pl.LazyFrame) else pl.LazyFrame(data)")
    else:
        header = ["import pandas as pd",
                  "from m2py_runtime import pandas_ops as ops",
                  "datasets = globals().get('datasets')"]
        implicit = (f'df = pd.read_parquet("{source_path}.parquet")'
                    if source_path is not None else None)

    default_frame = "lf" if backend == "polars" else "df"
    body = []
    idx = 0
    active = None          # None = the implicit single working frame (df/lf)
    known = set()          # dataset names that already have an emitted variable
    used_implicit = False  # did any command actually read the implicit frame?

    def cur():
        nonlocal used_implicit
        if active:
            return _dsvar(backend, active)
        used_implicit = True
        return default_frame

    for line in script.splitlines():
        if not line.strip():
            continue
        instr = parser.parse_line(line)
        if not instr or instr["command"] in ("textblock", "endblock", "end"):
            continue
        cmd, a = instr["command"], instr["args"]

        # ---- labels: display-only in the emulator, so a no-op on the data ----
        if cmd in LABELS:
            body.append(f"# {cmd} (display-only; data keeps codes): {line.strip()}")
            continue

        # ---- dataset/session management (switch active / create variables) ----
        if cmd in SESSION:
            if cmd == "create-dataset" and a:
                known.add(a[0]); active = a[0]
                body.append(_load_dataset(backend, a[0], source_path))
            elif cmd == "use" and a:
                if a[0] not in known:
                    known.add(a[0])
                    body.append(_load_dataset(backend, a[0], source_path))
                active = a[0]
            elif cmd == "clone-dataset" and len(a) >= 2:
                sv, dv = _dsvar(backend, a[0]), _dsvar(backend, a[1])
                body.append(f"{dv} = {sv}" if backend == "polars" else f"{dv} = {sv}.copy()")
                known.add(a[1])
            elif cmd == "rename-dataset" and len(a) >= 2:
                body.append(f"{_dsvar(backend, a[1])} = {_dsvar(backend, a[0])}")
                known.discard(a[0]); known.add(a[1])
                if active == a[0]:
                    active = a[1]
            elif cmd == "delete-dataset" and a:
                body.append(f"del {_dsvar(backend, a[0])}")
                known.discard(a[0])
                if active == a[0]:
                    active = None
            else:
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
        frame = cur()
        if cmd in ANALYSIS:
            idx += 1
            emitted = _emit_analysis(instr, backend, idx, frame)
        elif cmd in PLOT:
            idx += 1
            emitted = _emit_plot(instr, backend, idx, write=source_path is not None, frame=frame)
        else:
            emitted = _emit(instr, backend, frame, known)
        body.append(emitted if emitted else f"# UNTRANSLATED: {line.strip()}")

    # footer: materialise the final active frame into `df` (+ write in file mode)
    final = cur()
    if backend == "polars":
        footer = [f'df = {final}.collect(engine="streaming")']
        if source_path is not None:
            footer.append('df.write_parquet("result.parquet")')
    else:
        footer = ([] if final == "df" else [f"df = {final}"])
        if source_path is not None:
            footer.append('df.to_parquet("result.parquet")')

    # only set up the implicit df/lf if the script actually reads it (a pure
    # multi-dataset script never does, so we don't require a default source)
    if used_implicit and implicit:
        header.append(implicit)
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
    for line in _expand_loops(script).splitlines():
        if not line.strip():
            continue
        instr = parser.parse_line(line)
        if not instr or instr["command"] in ("textblock", "endblock", "end"):
            continue
        cmd = instr["command"]
        if cmd not in SUPPORTED:
            out.append(line.strip())
            continue
        if cmd in SESSION or cmd in LABELS:    # always translate (no-op/state)
            continue
        if _unhandled_options(instr):
            out.append(line.strip())
            continue
        try:
            _check_polars_expr(instr)
        except UnsupportedExpr:
            out.append(line.strip())
            continue
        # also flag verbs that parse/options-check but can't actually emit
        # (e.g. coefplot without a reg-command, scatter with one variable)
        if cmd in ANALYSIS:
            emitted = _emit_analysis(instr, "polars", 1)
        elif cmd in PLOT:
            emitted = _emit_plot(instr, "polars", 1, False)
        else:
            emitted = _emit(instr, "polars")
        if not emitted:
            out.append(line.strip())
    return out
