"""
Expansion patterns: Python constructs that map to multiple microdata commands.

Each function returns a list of microdata command strings, or None if the
pattern doesn't match.
"""
import ast
from typing import Optional

from .expr import ExprTranslator
from .chain import (
    decompose, find_method, find_attr, strip_suffix,
    str_const, str_list, is_df_root,
    MethodStep, SubscriptStep, AttrStep,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_np_where(node) -> bool:
    """Check if node is a call to np.where(...)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "where"
        and isinstance(func.value, ast.Name)
        and func.value.id == "np"
    )


def _is_df_col(node, df_name: str) -> Optional[str]:
    """Return column name if node is df['col'] or df.col, else None."""
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name) and node.value.id == df_name:
            s = node.slice
            if isinstance(s, ast.Constant) and isinstance(s.value, str):
                return s.value
            if isinstance(s, ast.Name):
                return s.id
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == df_name:
            return node.attr
    return None


def _default_init(values) -> str:
    """Choose a sensible missing value for generate based on the mapped values.
    values are already-translated microdata strings (e.g. '1', "'hello'").
    A value is a string literal if it starts with a quote character.
    """
    if not values:
        return "."
    str_vals = [v for v in values if isinstance(v, str) and v.startswith("'")]
    return "''" if str_vals else "."


# ── np.where → generate + replace if ────────────────────────────────────────

def _collect_np_where_cases(node, translator: ExprTranslator) -> Optional[dict]:
    """
    Recursively unpack nested np.where calls.
    Returns {'default': str, 'cases': [(cond_str, val_str), ...]}
    where cases are ordered from outermost to innermost (highest priority last).
    """
    if not _is_np_where(node):
        return None
    args = node.args
    if len(args) < 3:
        return None
    cond_str = translator.translate(args[0])
    true_str = translator.translate(args[1])
    if cond_str is None or true_str is None:
        return None

    false_node = args[2]
    if _is_np_where(false_node):
        nested = _collect_np_where_cases(false_node, translator)
        if nested is None:
            return None
        # Prepend this (outermost) case
        nested["cases"].insert(0, (cond_str, true_str))
        return nested
    else:
        default_str = translator.translate(false_node)
        if default_str is None:
            return None
        return {"default": default_str, "cases": [(cond_str, true_str)]}


def try_np_where(target: str, value_node, translator: ExprTranslator) -> Optional[list]:
    """
    df['target'] = np.where(cond, v_true, v_false)
    → generate target = v_false
      replace target = v_true if cond
    """
    if not _is_np_where(value_node):
        return None
    expansion = _collect_np_where_cases(value_node, translator)
    if expansion is None:
        return None

    lines = [f"generate {target} = {expansion['default']}"]
    # Apply conditions from innermost to outermost so outermost wins
    for cond, val in reversed(expansion["cases"]):
        lines.append(f"replace {target} = {val} if {cond}")
    return lines


# ── .map({k: v}) → generate + replace if ────────────────────────────────────

def _is_df_col_map(node, df_name: str):
    """
    Detect df['col'].map({...}).
    Returns (col_name, dict_node) or None.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "map"):
        return None
    col = _is_df_col(func.value, df_name)
    if col is None:
        return None
    if not node.args:
        return None
    dict_node = node.args[0]
    if not isinstance(dict_node, ast.Dict):
        return None
    return col, dict_node


def try_map(target: str, value_node, df_name: str, translator: ExprTranslator) -> Optional[list]:
    """
    df['target'] = df['col'].map({k1: v1, k2: v2})
    → generate target = .
      replace target = v1 if col == k1
      replace target = v2 if col == k2
    """
    result = _is_df_col_map(value_node, df_name)
    if result is None:
        return None
    col, dict_node = result

    pairs = []
    for key_node, val_node in zip(dict_node.keys, dict_node.values):
        k = translator.translate(key_node)
        v = translator.translate(val_node)
        if k is None or v is None:
            return None
        pairs.append((k, v))

    # Same-column mapping → recode syntax
    if target == col:
        val_to_keys: dict = {}
        for k, v in pairs:
            val_to_keys.setdefault(v, []).append(k)
        parts = " ".join(f"({' '.join(ks)}={v})" for v, ks in val_to_keys.items())
        return [f"recode {col} {parts}"]

    # Different-column mapping → generate + replace if
    init = _default_init([v for _, v in pairs])
    lines = [f"generate {target} = {init}"]
    for k, v in pairs:
        lines.append(f"replace {target} = {v} if {col} == {k}")
    return lines


# ── pd.cut → generate + replace if ──────────────────────────────────────────

def _is_pd_cut(node) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "cut"
        and isinstance(func.value, ast.Name)
        and func.value.id == "pd"
    )


def try_pd_cut(target: str, value_node, df_name: str, translator: ExprTranslator) -> Optional[list]:
    """
    df['target'] = pd.cut(df['col'], bins=[b0,b1,b2], labels=[l1,l2], right=True)
    → generate target = .
      replace target = l1 if col > b0 & col <= b1
      replace target = l2 if col > b1 & col <= b2
    """
    if not _is_pd_cut(value_node):
        return None

    # Extract positional args and keyword args
    args = value_node.args
    kwargs = {kw.arg: kw.value for kw in value_node.keywords}

    if not args:
        return None
    col_node = args[0]
    col = _is_df_col(col_node, df_name)
    if col is None:
        col = translator.translate(col_node)
    if col is None:
        return None

    bins_node = args[1] if len(args) > 1 else kwargs.get("bins")
    labels_node = args[2] if len(args) > 2 else kwargs.get("labels")
    right_node = kwargs.get("right")

    # Determine right (default True)
    right = True
    if right_node is not None:
        if isinstance(right_node, ast.Constant):
            right = bool(right_node.value)

    # Parse bins list
    if bins_node is None or not isinstance(bins_node, (ast.List, ast.Tuple)):
        return None
    bins = []
    for b in bins_node.elts:
        t = translator.translate(b)
        if t is None:
            return None
        bins.append(t)

    # Parse labels list (optional; if absent use 1-based integers)
    labels = []
    if labels_node is not None and isinstance(labels_node, (ast.List, ast.Tuple)):
        for lbl in labels_node.elts:
            t = translator.translate(lbl)
            if t is None:
                return None
            labels.append(t)
    else:
        labels = [str(i + 1) for i in range(len(bins) - 1)]

    if len(labels) != len(bins) - 1:
        return None

    # Same-column binning → recode range syntax
    if target == col:
        parts = [f"({bins[i]}/{bins[i + 1]}={labels[i]})" for i in range(len(labels))]
        return [f"recode {col} {' '.join(parts)}"]

    # Build generate + replace sequence
    init = _default_init(labels)
    lines = [f"generate {target} = {init}"]

    for i, lbl in enumerate(labels):
        lo = bins[i]
        hi = bins[i + 1]
        # Handle np.inf / np.nan as sentinel
        lo_str = lo.replace("inf", "").strip() if "inf" in lo else lo
        hi_str = hi.replace("inf", "").strip() if "inf" in hi else hi

        if right:
            if "inf" in lo or lo in ("-inf", "(-inf)", "(-1*inf)"):
                cond = f"{col} <= {hi_str}"
            elif "inf" in hi or hi in ("inf", "(inf)"):
                cond = f"{col} > {lo_str}"
            else:
                cond = f"{col} > {lo_str} & {col} <= {hi_str}"
        else:
            if "inf" in lo or lo in ("-inf", "(-inf)"):
                cond = f"{col} < {hi_str}"
            elif "inf" in hi or hi in ("inf",):
                cond = f"{col} >= {lo_str}"
            else:
                cond = f"{col} >= {lo_str} & {col} < {hi_str}"

        lines.append(f"replace {target} = {lbl} if {cond}")

    return lines


# ── .fillna() → replace if sysmiss ──────────────────────────────────────────

def _is_df_col_fillna(node, df_name: str):
    """
    Detect df['col'].fillna(value).
    Returns (col_name, fill_node) or None.
    """
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "fillna"):
        return None
    col = _is_df_col(func.value, df_name)
    if col is None:
        return None
    if not node.args and not node.keywords:
        return None
    fill_node = node.args[0] if node.args else next(
        (kw.value for kw in node.keywords if kw.arg == "value"), None
    )
    if fill_node is None:
        return None
    return col, fill_node


def try_fillna(target: str, value_node, df_name: str, translator: ExprTranslator) -> Optional[list]:
    """
    df['target'] = df['col'].fillna(val)
    If target == col:  replace col = val if sysmiss(col)
    Otherwise:         generate target = col
                       replace target = val if sysmiss(target)
    """
    result = _is_df_col_fillna(value_node, df_name)
    if result is None:
        return None
    col, fill_node = result
    fill = translator.translate(fill_node)
    if fill is None:
        return None

    if target == col:
        return [f"replace {col} = {fill} if sysmiss({col})"]
    else:
        return [
            f"generate {target} = {col}",
            f"replace {target} = {fill} if sysmiss({target})",
        ]


# ── .clip() → generate + replace ────────────────────────────────────────────

def try_clip(target: str, value_node, df_name: str, translator: ExprTranslator) -> Optional[list]:
    """
    df['target'] = df['col'].clip(lower=lo, upper=hi)
    → generate target = col
      replace target = lo if col < lo
      replace target = hi if col > hi
    """
    if not isinstance(value_node, ast.Call):
        return None
    func = value_node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "clip"):
        return None
    col = _is_df_col(func.value, df_name)
    if col is None:
        return None

    kwargs = {kw.arg: kw.value for kw in value_node.keywords}
    args = value_node.args

    lo_node = args[0] if len(args) > 0 else kwargs.get("lower")
    hi_node = args[1] if len(args) > 1 else kwargs.get("upper")

    lo = translator.translate(lo_node) if lo_node else None
    hi = translator.translate(hi_node) if hi_node else None

    if lo is None and hi is None:
        return None

    lines = [f"generate {target} = {col}"]
    if lo is not None:
        lines.append(f"replace {target} = {lo} if {col} < {lo}")
    if hi is not None:
        lines.append(f"replace {target} = {hi} if {col} > {hi}")
    return lines


# ── simple .apply() with if/elif/else function body ──────────────────────────

def _make_lambda_translator(param: str, col: str, base: ExprTranslator) -> ExprTranslator:
    """Return a translator that maps `param` → col and delegates everything else."""
    class _LambdaTranslator(ExprTranslator):
        def _t_Name(self, node):
            if node.id == param:
                return col
            return super()._t_Name(node)
    return _LambdaTranslator(df_name=base.df_name)


def _try_apply_lambda(
    target: str,
    col: str,
    lambda_node,
    translator: ExprTranslator,
) -> Optional[list]:
    """
    Translate df['col'].apply(lambda x: body).

    Simple expression body → generate target = <expr>
    Ternary body (a if cond else b) → generate target = b; replace target = a if cond
    """
    if len(lambda_node.args.args) != 1:
        return None  # only single-parameter lambdas
    param = lambda_node.args.args[0].arg
    lt = _make_lambda_translator(param, col, translator)
    body = lambda_node.body

    if isinstance(body, ast.IfExp):
        # lambda x: val_true if cond else val_false
        cond  = lt.translate(body.test)
        v_true  = lt.translate(body.body)
        v_false = lt.translate(body.orelse)
        if cond is None or v_true is None or v_false is None:
            return None
        return [
            f"generate {target} = {v_false}",
            f"replace {target} = {v_true} if {cond}",
        ]

    expr = lt.translate(body)
    if expr is not None:
        return [f"generate {target} = {expr}"]
    return None


def try_apply_simple_func(
    target: str,
    value_node,
    df_name: str,
    translator: ExprTranslator,
    known_functions: dict,
) -> Optional[list]:
    """
    df['target'] = df['col'].apply(func_or_lambda)

    Handles three cases:
    1. Module/builtin function (np.log, abs, etc.): synthesise func(df['col'])
       and delegate to the expression translator.
    2. Lambda expression: inline substitution of the parameter.
    3. User-defined function (known_functions): if/elif/else branch mapping.
    """
    if not isinstance(value_node, ast.Call):
        return None
    func = value_node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "apply"):
        return None
    col_node = func.value
    col = _is_df_col(col_node, df_name)
    if col is None:
        return None
    if not value_node.args:
        return None
    func_ref = value_node.args[0]

    # ── Case 1: module/builtin function reference (np.log, abs, int, …) ──────
    if isinstance(func_ref, (ast.Name, ast.Attribute)):
        # Synthesise func_ref(df['col']) and translate via existing rules
        synthetic = ast.Call(func=func_ref, args=[col_node], keywords=[])
        ast.fix_missing_locations(synthetic)
        expr = translator.translate(synthetic)
        if expr is not None:
            return [f"generate {target} = {expr}"]
        # Not a known translatable function — fall through to user-defined check

    # ── Case 2: lambda ────────────────────────────────────────────────────────
    if isinstance(func_ref, ast.Lambda):
        return _try_apply_lambda(target, col, func_ref, translator)

    # ── Case 3: user-defined function with if/elif/else body ──────────────────
    if not isinstance(func_ref, ast.Name):
        return None
    func_name = func_ref.id
    func_def = known_functions.get(func_name)
    if func_def is None:
        return None

    cases = _extract_if_elif_else(func_def, col, translator)
    if cases is None:
        return None

    default, branches = cases
    init = _default_init([v for _, v in branches] + ([default] if default else []))
    if default is None:
        default = init

    lines = [f"generate {target} = {default}"]
    # Apply from last branch to first so earlier (higher priority) branches win
    for cond, val in reversed(branches):
        lines.append(f"replace {target} = {val} if {cond}")
    return lines


def _extract_if_elif_else(
    func_def: ast.FunctionDef,
    arg_col: str,
    translator: ExprTranslator,
) -> Optional[tuple]:
    """
    Parse a simple function body like:
        def f(x):
            if x < 18:   return 1
            elif x < 65: return 2
            else:        return 3

    Returns (default_val, [(cond_str, val_str), ...]) or None.
    The function argument name is substituted with arg_col in conditions.
    """
    if len(func_def.args.args) != 1:
        return None  # only single-arg functions

    arg_name = func_def.args.args[0].arg

    # Build a translator that treats the function arg as the column
    class _ArgTranslator(ExprTranslator):
        def _t_Name(self, node):
            if node.id == arg_name:
                return arg_col
            return super()._t_Name(node)

    atrans = _ArgTranslator(df_name=translator.df_name)

    body = func_def.body
    if len(body) != 1 or not isinstance(body[0], ast.If):
        return None

    branches = []
    default = None

    def _walk_if(node):
        nonlocal default
        if not isinstance(node, ast.If):
            if isinstance(node, ast.Return):
                v = atrans.translate(node.value)
                default = v
            return True

        cond_str = atrans.translate(node.test)
        if cond_str is None:
            return False

        if len(node.body) != 1 or not isinstance(node.body[0], ast.Return):
            return False
        val_str = atrans.translate(node.body[0].value)
        if val_str is None:
            return False
        branches.append((cond_str, val_str))

        if not node.orelse:
            return True
        if len(node.orelse) == 1:
            child = node.orelse[0]
            if isinstance(child, ast.If):
                return _walk_if(child)
            elif isinstance(child, ast.Return):
                v = atrans.translate(child.value)
                if v is None:
                    return False
                default = v
                return True
        return False

    if not _walk_if(body[0]):
        return None

    return default, branches


# ── .str accessor on assignment ──────────────────────────────────────────────

def try_str_method_assign(
    target: str, value_node, df_name: str, translator: ExprTranslator
) -> Optional[list]:
    """
    df['target'] = df['col'].str.lower()          → generate target = lower(col)
    df['target'] = df['col'].str.lower().str.strip() → generate target = trim(lower(col))
    df['target'] = df['col'].str[0:3]             → generate target = substr(col, 1, 3)
    """
    expr = translator.translate_str_chain(value_node)
    if expr:
        return [f"generate {target} = {expr}"]
    return None


# ── groupby transform → aggregate ────────────────────────────────────────────

def try_groupby_transform(
    target: str, value_node, df_name: str, translator: ExprTranslator
) -> Optional[list]:
    """
    df['target'] = df.groupby('g')['y'].transform('mean')
    df['target'] = df.groupby(['g1','g2'])['y'].transform('mean')
    Also handles prefix steps: df[cond].groupby(g)['y'].transform('mean')
    → aggregate (mean) y -> target, by(g)
    """
    info = _match_groupby_transform(value_node, df_name)
    if info is None:
        return None
    return [f"aggregate ({info['stat']}) {info['src_col']} -> {target}, by({info['by_str']})"]


def _match_groupby_transform(node, df_name: str) -> Optional[dict]:
    """
    Recognise df[...].groupby(g)[col].transform(stat) via the chain decomposer.
    Returns {'src_col', 'stat', 'by_str'} or None.
    """
    root, steps = decompose(node)
    if not is_df_root(root, df_name):
        return None

    gb_idx = find_method(steps, "groupby")
    if gb_idx < 0:
        return None

    # Steps from groupby onward must be: groupby(g), subscript(col), transform(stat)
    tail = steps[gb_idx:]
    if len(tail) < 3:
        return None
    gb_step, sub_step, tr_step = tail[0], tail[1], tail[2]

    if not isinstance(gb_step, MethodStep) or not gb_step.args:
        return None
    if not isinstance(tr_step, MethodStep) or tr_step.name != "transform":
        return None

    by_vars = str_list(gb_step.args[0])
    if by_vars is None:
        return None

    # Column: df.groupby(g)['col'] (SubscriptStep) or df.groupby(g).col (AttrStep)
    if isinstance(sub_step, SubscriptStep):
        src_col = str_const(sub_step.key)
    elif isinstance(sub_step, AttrStep):
        src_col = sub_step.name
    else:
        src_col = None
    if src_col is None:
        return None

    if not tr_step.args:
        return None

    # Stat: string 'mean', np.mean attribute, or bare name mean/sum/…
    stat_arg = tr_step.args[0]
    stat_str = str_const(stat_arg)
    if stat_str is None:
        # np.mean / np.sum etc.
        _NP_STAT = {
            "mean": "mean", "sum": "sum", "std": "std", "median": "median",
            "min": "min", "max": "max", "average": "mean",
        }
        if (isinstance(stat_arg, ast.Attribute)
                and isinstance(stat_arg.value, ast.Name)
                and stat_arg.value.id in ("np", "numpy")):
            stat_str = _NP_STAT.get(stat_arg.attr)
        elif isinstance(stat_arg, ast.Name):
            stat_str = _NP_STAT.get(stat_arg.id)
    if stat_str is None:
        return None
    stat = _stat_alias(stat_str)
    if stat is None:
        return None

    return {"src_col": src_col, "stat": stat, "by_str": " ".join(by_vars)}


# ── groupby collapse → collapse ───────────────────────────────────────────────

_COLLAPSE_STATS = frozenset({
    "mean", "sum", "count", "std", "median", "min", "max",
    "sem", "var", "first", "last",
})


def try_groupby_collapse(
    value_node, df_name: str, translator: ExprTranslator
) -> Optional[list]:
    """
    Recognise any of:
      df.groupby(g).agg({'y': 'mean'}).reset_index()
      df.groupby(g).agg(out=('y', 'mean')).reset_index()
      df.groupby(g)['y'].mean().reset_index()
      df[cond].groupby(g)['y'].mean()          ← prefix filter now works
    → collapse (mean) y -> y, by(g)
    """
    root, steps = decompose(value_node)
    if not is_df_root(root, df_name):
        return None

    # Strip trailing housekeeping methods
    steps = strip_suffix(steps, "reset_index", "rename_axis")
    if not steps:
        return None

    gb_idx = find_method(steps, "groupby")
    if gb_idx < 0:
        return None

    gb_step = steps[gb_idx]
    if not isinstance(gb_step, MethodStep) or not gb_step.args:
        return None
    by_vars = str_list(gb_step.args[0])
    if by_vars is None:
        return None
    by_str = " ".join(by_vars)

    tail = steps[gb_idx + 1:]
    if not tail:
        return None

    # Pattern A: groupby(g).agg({...}) or groupby(g).agg(out=('col', 'stat'))
    if len(tail) == 1 and isinstance(tail[0], MethodStep) and tail[0].name == "agg":
        agg_step = tail[0]
        specs = None
        if agg_step.args:
            specs = _parse_agg_arg(agg_step.args[0], translator)
        if specs is None and agg_step.kwargs:
            specs = _parse_named_agg_kwargs(agg_step.kwargs)
        if specs is None:
            return None
        parts = " ".join(f"({stat}) {src} -> {tgt}" for src, stat, tgt in specs)
        return [f"collapse {parts}, by({by_str})"]

    # Pattern B: groupby(g)[col].stat_method()
    if (
        len(tail) >= 2
        and isinstance(tail[0], SubscriptStep)
        and isinstance(tail[1], MethodStep)
        and tail[1].name in _COLLAPSE_STATS
    ):
        src_col = str_const(tail[0].key)
        if src_col is None:
            return None
        stat = _stat_alias(tail[1].name)
        if stat is None:
            return None
        return [f"collapse ({stat}) {src_col} -> {src_col}, by({by_str})"]

    return None


def _parse_agg_arg(agg_arg, translator: ExprTranslator) -> Optional[list]:
    """
    Parse the positional argument to .agg({...}).
    Returns list of (src_col, stat, target_col) tuples.
    """
    if not isinstance(agg_arg, ast.Dict):
        return None

    specs = []
    for key_node, val_node in zip(agg_arg.keys, agg_arg.values):
        if not isinstance(key_node, ast.Constant):
            return None
        col = key_node.value
        if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
            stat = _stat_alias(val_node.value)
            if stat is None:
                return None
            specs.append((col, stat, col))
        elif isinstance(val_node, ast.List):
            # {'col': ['mean', 'count']} → multiple specs
            for s_node in val_node.elts:
                if not isinstance(s_node, ast.Constant):
                    return None
                stat = _stat_alias(s_node.value)
                if stat is None:
                    return None
                tgt = f"{col}_{s_node.value}"
                specs.append((col, stat, tgt))
        else:
            return None

    return specs if specs else None


def _parse_named_agg_keywords(keywords) -> Optional[list]:
    """
    Parse .agg(out_col=('src_col', 'stat'), ...) from a list of AST keyword nodes.
    Returns list of (src_col, stat, target_col) tuples, or None.
    """
    specs = []
    for kw in keywords:
        if kw.arg is None:   # **kwargs spread — bail out
            return None
        tgt = kw.arg
        val = kw.value
        if not isinstance(val, ast.Tuple) or len(val.elts) < 2:
            return None
        col_node, stat_node = val.elts[0], val.elts[1]
        if not (isinstance(col_node, ast.Constant) and isinstance(col_node.value, str)):
            return None
        if not (isinstance(stat_node, ast.Constant) and isinstance(stat_node.value, str)):
            return None
        stat = _stat_alias(stat_node.value)
        if stat is None:
            return None
        specs.append((col_node.value, stat, tgt))
    return specs if specs else None


def _parse_named_agg_kwargs(kwargs: dict) -> Optional[list]:
    """
    Like _parse_named_agg_keywords but takes the {str: ast_node} dict produced
    by the chain decomposer (MethodStep.kwargs).
    """
    specs = []
    for tgt, val in kwargs.items():
        if not isinstance(val, ast.Tuple) or len(val.elts) < 2:
            return None
        col_node, stat_node = val.elts[0], val.elts[1]
        if not (isinstance(col_node, ast.Constant) and isinstance(col_node.value, str)):
            return None
        if not (isinstance(stat_node, ast.Constant) and isinstance(stat_node.value, str)):
            return None
        stat = _stat_alias(stat_node.value)
        if stat is None:
            return None
        specs.append((col_node.value, stat, tgt))
    return specs if specs else None


def _extract_by_vars(groupby_call, translator: ExprTranslator) -> Optional[list]:
    """Extract the list of groupby variable names from df.groupby(...)."""
    if not groupby_call.args:
        return None
    by_node = groupby_call.args[0]
    if isinstance(by_node, ast.Constant) and isinstance(by_node.value, str):
        return [by_node.value]
    if isinstance(by_node, (ast.List, ast.Tuple)):
        result = []
        for elt in by_node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                result.append(elt.value)
            else:
                return None
        return result if result else None
    return None


def _stat_alias(name: str) -> Optional[str]:
    """Map pandas aggregation name to microdata stat keyword."""
    _MAP = {
        "mean": "mean", "average": "mean",
        "sum": "sum",
        "count": "count", "size": "count",
        "std": "sd", "std": "sd",
        "var": "sd",   # approximate: use sd
        "median": "median",
        "min": "min",
        "max": "max",
        "sem": "semean",
        "iqr": "iqr",
        "gini": "gini",
        "first": "min",  # approximate
        "last": "max",   # approximate
    }
    return _MAP.get(name.lower())


def extract_groupby_transform_info(
    value_node, df_name: str, translator: ExprTranslator
) -> Optional[dict]:
    """
    Extract info from df.groupby(g)[col].transform(stat) without needing a target.
    Returns {'src_col', 'stat', 'by_str'} or None.

    Delegates to _match_groupby_transform (chain-based).
    """
    return _match_groupby_transform(value_node, df_name)
