"""
commands.py — pure pattern-matching extractors for microdata commands.

Each extractor takes an AST value node and a Ctx and returns a list of
microdata command strings (possibly empty) or None if the pattern does not match.

Col-assign extractors additionally take the target column name as the first argument.

None   = pattern not matched (try next extractor)
[]     = matched but nothing to emit (no-op, silently skip)
[...]  = matched, emit these lines
"""
import ast
from dataclasses import dataclass, field
from typing import Optional

from .chain import (
    decompose, MethodStep, AttrStep, SubscriptStep,
    str_const, str_list as chain_str_list, is_df_root,
)
from .expr import ExprTranslator


# ── context ───────────────────────────────────────────────────────────────────

@dataclass
class Ctx:
    df_name: str
    tr: ExprTranslator
    known_functions: dict = field(default_factory=dict)


# ── registry ──────────────────────────────────────────────────────────────────

class Registry:
    """
    Holds three lists of pure extractors, one per assignment context.

    Extractors are called in registration order; the first non-None result wins.
    Return None to skip, [] to match-and-skip, [...] to match-and-emit.
    """

    def __init__(self):
        self._df: list = []    # (value, ctx) → list[str] | None
        self._col: list = []   # (col, value, ctx) → list[str] | None
        self._expr: list = []  # (value, ctx) → list[str] | None

    def df(self, fn):
        """Decorator: register a df= extractor."""
        self._df.append(fn)
        return fn

    def col(self, fn):
        """Decorator: register a col= extractor."""
        self._col.append(fn)
        return fn

    def expr(self, fn):
        """Decorator: register an expr-stmt extractor."""
        self._expr.append(fn)
        return fn

    def match_df(self, value, ctx: Ctx) -> Optional[list]:
        for fn in self._df:
            result = fn(value, ctx)
            if result is not None:
                return result
        return None

    def match_col(self, col: str, value, ctx: Ctx) -> Optional[list]:
        for fn in self._col:
            result = fn(col, value, ctx)
            if result is not None:
                return result
        return None

    def match_expr(self, value, ctx: Ctx) -> Optional[list]:
        for fn in self._expr:
            result = fn(value, ctx)
            if result is not None:
                return result
        return None


REGISTRY = Registry()


# ── internal helpers ──────────────────────────────────────────────────────────

def _is_call(node, method: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
    )


def _str_list(node) -> Optional[list]:
    """List of string literals from a Constant, List, or Tuple node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.List, ast.Tuple)):
        result = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                result.append(elt.value)
            else:
                return None
        return result
    return None


def _col_name(node, df_name: str, tr: ExprTranslator) -> Optional[str]:
    """Return a column name from df['col'], df.col, or any translatable expression."""
    if node is None:
        return None
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name) and node.value.id == df_name:
            s = node.slice
            if isinstance(s, ast.Constant) and isinstance(s.value, str):
                return s.value
    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == df_name:
            return node.attr
    return tr.translate(node)


def _kwarg_str(kwargs: dict, key: str) -> Optional[str]:
    node = kwargs.get(key)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None



@REGISTRY.df
def _drop_cols(value, ctx: Ctx) -> Optional[list]:
    """df.drop(columns=[...]) / df.drop([...], axis=1) → drop col1 col2"""
    if not _is_call(value, "drop"):
        return None
    kwargs = {kw.arg: kw.value for kw in value.keywords}
    cols_node = kwargs.get("columns")
    if cols_node is None:
        axis_node = kwargs.get("axis") or (value.args[1] if len(value.args) > 1 else None)
        if axis_node and isinstance(axis_node, ast.Constant) and axis_node.value == 1:
            cols_node = value.args[0] if value.args else None
    if cols_node is None:
        return None
    cols = _str_list(cols_node)
    if cols is None:
        return None
    return ["drop " + " ".join(cols)]


@REGISTRY.df
def _sort_values(value, ctx: Ctx) -> Optional[list]:
    """df.sort_values(...) → comment (no microdata equivalent)."""
    if not _is_call(value, "sort_values"):
        return None
    return ["// UNTRANSLATED: sort_values — no direct microdata equivalent"]


@REGISTRY.df
def _no_op_reassignment(value, ctx: Ctx) -> Optional[list]:
    """df.copy() / df.reset_index() / df = df → silently skip.

    Only matches when the method is called *directly* on df (one step),
    so that df.groupby(...).mean().reset_index() is NOT consumed here.
    """
    _NO_OP_NAMES = frozenset({"copy", "reset_index", "set_index", "rename_axis"})
    if isinstance(value, ast.Name) and value.id == ctx.df_name:
        return []
    root, steps = decompose(value)
    if (is_df_root(root, ctx.df_name)
            and len(steps) == 1
            and isinstance(steps[0], MethodStep)
            and steps[0].name in _NO_OP_NAMES):
        return []
    return None


@REGISTRY.df
def _df_fillna(value, ctx: Ctx) -> Optional[list]:
    """df = df.fillna(val) → replace col = val if sysmiss(col) for each known col.
    When no columns are known, emit a generic replace comment."""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) != 1:
        return None
    step = steps[0]
    if not (isinstance(step, MethodStep) and step.name == "fillna"):
        return None
    fill_node = step.args[0] if step.args else step.kwargs.get("value")
    if fill_node is None:
        return None
    fill = ctx.tr.translate(fill_node)
    if fill is None:
        return None
    # We don't know column names at translation time — emit a comment placeholder
    return [f"# replace [each col] = {fill} if sysmiss([each col])  (df.fillna)"]


# ── col= extractors ───────────────────────────────────────────────────────────

@REGISTRY.col
def _clone_variables(col: str, value, ctx: Ctx) -> Optional[list]:
    """df['new'] = df['old'] / df.old → clone-variables old -> new"""
    src = None
    if isinstance(value, ast.Subscript):
        if isinstance(value.value, ast.Name) and value.value.id == ctx.df_name:
            s = value.slice
            if isinstance(s, ast.Constant) and isinstance(s.value, str):
                src = s.value
    elif isinstance(value, ast.Attribute):
        if isinstance(value.value, ast.Name) and value.value.id == ctx.df_name:
            src = value.attr
    if src is None:
        return None
    if src == col:
        return []  # self-copy — no-op
    return [f"clone-variables {src} -> {col}"]


@REGISTRY.col
def _destring(col: str, value, ctx: Ctx) -> Optional[list]:
    """pd.to_numeric(df['col']) / df['col'].astype(float/int) → destring col"""
    root, steps = decompose(value)
    if (isinstance(root, ast.Name) and root.id == "pd"
            and len(steps) == 1 and isinstance(steps[0], MethodStep)
            and steps[0].name == "to_numeric"):
        return [f"destring {col}"]
    if steps and isinstance(steps[-1], MethodStep) and steps[-1].name == "astype":
        astype = steps[-1]
        if astype.args:
            arg = astype.args[0]
            if isinstance(arg, ast.Name):
                if arg.id in ("float", "int"):
                    return [f"destring {col}"]
                if arg.id == "str":
                    return [f"generate {col} = string({col})"]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if any(t in arg.value.lower() for t in ("float", "int")):
                    return [f"destring {col}"]
                if arg.value.lower() in ("str", "string", "object"):
                    return [f"generate {col} = string({col})"]
    return None


# ── expr-stmt extractors ──────────────────────────────────────────────────────

_COL_STAT_METHODS = frozenset([
    "mean", "std", "var", "median", "min", "max", "sum", "count",
    "nunique", "describe", "sem", "skew", "kurt", "kurtosis",
])

# Panel variants must fire BEFORE _col_stat / _describe / _value_counts so that
# the groupby step is detected before the method-on-column pattern matches.

@REGISTRY.expr
def _summarize_panel(value, ctx: Ctx) -> Optional[list]:
    """df.groupby('year')['col'].describe() → summarize-panel col, by(year)"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) < 2:
        return None
    if not (isinstance(steps[-1], MethodStep) and steps[-1].name == "describe"):
        return None
    gb_idx = next((i for i, s in enumerate(steps)
                   if isinstance(s, MethodStep) and s.name == "groupby"), -1)
    if gb_idx < 0:
        return None
    gb_step = steps[gb_idx]
    if not gb_step.args:
        return None
    by_vars = chain_str_list(gb_step.args[0])
    if by_vars is None:
        return None
    cols = []
    for s in steps[gb_idx + 1 : -1]:
        if isinstance(s, SubscriptStep):
            c = chain_str_list(s.key) or ([str_const(s.key)] if str_const(s.key) else [])
            cols.extend(c)
    by_str = " ".join(_sub_pdc(by_vars, ctx))
    col_str = (" " + " ".join(cols)) if cols else ""
    return [f"summarize-panel{col_str}, by({by_str})"]


@REGISTRY.expr
def _tabulate_panel(value, ctx: Ctx) -> Optional[list]:
    """df.groupby('year')['edu'].value_counts() → tabulate-panel edu, by(year)"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) < 3:
        return None
    if not (isinstance(steps[-1], MethodStep) and steps[-1].name == "value_counts"):
        return None
    gb_idx = next((i for i, s in enumerate(steps)
                   if isinstance(s, MethodStep) and s.name == "groupby"), -1)
    if gb_idx < 0:
        return None
    gb_step = steps[gb_idx]
    if not gb_step.args:
        return None
    by_vars = chain_str_list(gb_step.args[0])
    if by_vars is None:
        return None
    cols = []
    for s in steps[gb_idx + 1 : -1]:
        if isinstance(s, SubscriptStep):
            c = chain_str_list(s.key) or ([str_const(s.key)] if str_const(s.key) else [])
            cols.extend(c)
    if not cols:
        return None
    by_str = " ".join(_sub_pdc(by_vars, ctx))
    vc_step = steps[-1]
    vc_kw = vc_step.kwargs
    opts = []
    norm = vc_kw.get("normalize")
    if isinstance(norm, ast.Constant) and norm.value is True:
        opts.append("cellpct")
    dn = vc_kw.get("dropna")
    if isinstance(dn, ast.Constant) and dn.value is False:
        opts.append("missing")
    sort = vc_kw.get("sort")
    if isinstance(sort, ast.Constant) and sort.value is True:
        opts.append("rowsort()")
    opt_str = _build_opts(*opts)
    return [f"tabulate-panel {' '.join(cols)}, by({by_str}){opt_str}"]


def _strip_outer_parens(s: str) -> str:
    """Strip surrounding parens only when they genuinely wrap the whole expression.

    '(a == 1)'          → 'a == 1'
    '(a == 1) & (b > 2)'  → unchanged  (outer parens belong to sub-expressions)
    '((a) & (b))'       → '(a) & (b)'
    """
    if not (s.startswith("(") and s.endswith(")")):
        return s
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and i < len(s) - 1:
            return s   # first ( closed before the end → not a simple wrapper
    return s[1:-1]


def _translate_filter(key, tr) -> Optional[str]:
    """Translate a boolean mask AST node to a microdata condition string.

    Handles simple conditions, compound & / | expressions, and ~ (NOT).
    """
    # ~expr → !(inner)
    if isinstance(key, ast.UnaryOp) and isinstance(key.op, (ast.Invert, ast.Not)):
        inner = tr.translate(key.operand)
        if inner:
            inner = _strip_outer_parens(inner)
            return f"!({inner})"
        return None
    raw = tr.translate(key)
    if raw is None:
        return None
    return _strip_outer_parens(raw)


_GROUPBY_STAT_MAP = {
    "mean":    None,        # default in summarize()
    "min":     None,        # shown by summarize() automatically
    "max":     None,        # shown by summarize() automatically
    "sum":     "sum",
    "std":     "std",
    "median":  "p50",
    "count":   "__freq__",  # → frequency table, no summarize()
    "size":    "__freq__",
    "nunique": "__freq__",
}


_POST_PROC_METHODS = frozenset({"head", "tail", "sort_values", "sort_index",
                                 "nlargest", "nsmallest"})


def _peel_post_proc(remaining: list) -> tuple:
    """Strip trailing post-processing steps and return (trimmed, opts_list).

    Recognises head/tail/nlargest/nsmallest → top(n)/bottom(n)
    and sort_values/sort_index → rowsort().
    opts_list entries are inserted in call order (outermost last).
    """
    opts: list = []
    end = len(remaining)
    while end > 0 and isinstance(remaining[end - 1], MethodStep) \
            and remaining[end - 1].name in _POST_PROC_METHODS:
        step = remaining[end - 1]
        n_node = step.args[0] if step.args else None
        n = int(n_node.value) if isinstance(n_node, ast.Constant) else (5 if step.name in ("head","tail") else 10)
        if step.name == "head":
            opts.insert(0, f"top({n})")
        elif step.name == "tail":
            opts.insert(0, f"bottom({n})")
        elif step.name == "nlargest":
            opts.insert(0, f"top({n})")
        elif step.name == "nsmallest":
            opts.insert(0, f"bottom({n})")
        elif step.name in ("sort_values", "sort_index"):
            opts.insert(0, "rowsort()")
        end -= 1
    return remaining[:end], opts


def _sub_pdc(by_vars: list, ctx: Ctx) -> list:
    """Substitute the panel time column name with panel@date in a by-variable list."""
    pdc = ctx.tr.panel_date_col if ctx.tr else None
    if not pdc:
        return by_vars
    return ["panel@date" if v == pdc else v for v in by_vars]


def _build_opts(*parts, extra=()) -> str:
    """Build ', opt1 opt2 ...' string from non-empty parts + extra."""
    all_parts = [p for p in parts if p] + list(extra)
    return (", " + " ".join(all_parts)) if all_parts else ""


def _extract_val_cols(core: list) -> Optional[list]:
    """Extract column name(s) from an optional SubscriptStep/AttrStep before the agg."""
    if len(core) == 0:
        return None
    if len(core) == 1:
        s = core[0]
        if isinstance(s, SubscriptStep):
            cols = chain_str_list(s.key)
            if cols is None:
                c = str_const(s.key)
                cols = [c] if c else None
            return cols
        if isinstance(s, AttrStep):
            return [s.name]
    return None  # unexpected shape → caller returns None


@REGISTRY.expr
def _groupby_tabulate(value, ctx: Ctx) -> Optional[list]:
    """df[filter].groupby(by, dropna=False)[col].stat().head/tail/sort()
    → tabulate by [if cond][, summarize(col) [stat] [top/bottom/rowsort] [missing]]
    """
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or not steps:
        return None

    i, cond_str = 0, None

    if isinstance(steps[0], SubscriptStep):
        key = steps[0].key
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return None
        if isinstance(key, (ast.List, ast.Tuple)):
            return None
        cond_str = _translate_filter(key, ctx.tr)
        if cond_str is None:
            return None
        i = 1

    if i >= len(steps) or not (isinstance(steps[i], MethodStep) and steps[i].name == "groupby"):
        return None
    gb_step = steps[i]
    i += 1

    if not gb_step.args:
        return None
    by_vars = chain_str_list(gb_step.args[0])
    if by_vars is None:
        s = str_const(gb_step.args[0])
        by_vars = [s] if s else None
    if not by_vars:
        return None

    extra_opts: list = []
    dn = gb_step.kwargs.get("dropna")
    if isinstance(dn, ast.Constant) and dn.value is False:
        extra_opts.append("missing")

    remaining, post = _peel_post_proc(list(steps[i:]))
    extra_opts = post + extra_opts  # post before missing

    if not remaining or not isinstance(remaining[-1], MethodStep):
        return None
    agg_name = remaining[-1].name
    if agg_name not in _GROUPBY_STAT_MAP:
        return None
    stat_opt = _GROUPBY_STAT_MAP[agg_name]

    val_cols = _extract_val_cols(remaining[:-1])
    if val_cols is None and len(remaining) > 1:
        return None  # unexpected chain shape

    by_str = " ".join(_sub_pdc(by_vars, ctx))
    if_str = f" if {cond_str}" if cond_str else ""

    if stat_opt == "__freq__" or val_cols is None:
        return [f"tabulate {by_str}{if_str}{_build_opts(extra=extra_opts)}"]

    return [
        f"tabulate {by_str}{if_str}{_build_opts(f'summarize({c})', stat_opt or '', extra=extra_opts)}"
        for c in val_cols
    ]


# ── groupby .agg() / .aggregate() → tabulate ─────────────────────────────────

_AGG_FUNC_STAT = {
    "mean":    None,        # default summarize()
    "min":     None,        # shown by summarize() automatically
    "max":     None,        # shown by summarize() automatically
    "sum":     "sum",
    "std":     "std",
    "median":  "p50",
    "count":   "__freq__",
    "size":    "__freq__",
    "nunique": "__freq__",
}
_AGG_NO_EQUIV = frozenset({"min", "max", "var", "first", "last", "sem",
                            "skew", "kurt", "kurtosis"})
# Stats with no microdata display equivalent whatsoever (not shown by tabulate summarize)
_DISPLAY_NO_EQUIV = frozenset({"var", "first", "last", "sem",
                                "skew", "kurt", "kurtosis", "nunique"})
# Stats that are frequency/count only (tabulate without summarize)
_COUNT_STATS = frozenset({"count", "size"})


def _parse_agg_arg(args: list, val_cols: Optional[list]) -> Optional[list]:
    """Parse agg(func) positional arg into [(col, func_str), ...] or None.

    Handles: string, list-of-strings, dict {col: func_or_list}.
    Named aggregation (kwargs only) returns None.
    """
    if not args:
        return None
    func_node = args[0]

    # agg('mean') / agg('sum') etc.
    if isinstance(func_node, ast.Constant) and isinstance(func_node.value, str):
        func = func_node.value
        return [(c, func) for c in val_cols] if val_cols else [(None, func)]

    # agg(['mean', 'sum', ...])
    if isinstance(func_node, (ast.List, ast.Tuple)):
        funcs = []
        for elt in func_node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                funcs.append(elt.value)
            elif isinstance(elt, ast.Attribute):        # np.sum → 'sum'
                funcs.append(elt.attr)
            else:
                return None
        if not funcs:
            return None
        return [(c, f) for c in (val_cols or [None]) for f in funcs]

    # agg({'col': func_or_list, ...})
    if isinstance(func_node, ast.Dict):
        pairs = []
        for k, v in zip(func_node.keys, func_node.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                return None
            col = k.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                pairs.append((col, v.value))
            elif isinstance(v, (ast.List, ast.Tuple)):
                for elt in v.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        pairs.append((col, elt.value))
                    else:
                        return None
            else:
                return None
        return pairs or None

    return None


def _parse_named_agg_display(kwargs: dict) -> Optional[list]:
    """Parse named-agg kwargs: agg(out=('src_col', 'stat'), ...) → [(src_col, stat)].
    Output names are ignored — only source column and stat matter for display."""
    pairs = []
    for _out_name, val in kwargs.items():
        if not isinstance(val, ast.Tuple) or len(val.elts) != 2:
            return None
        col_node, stat_node = val.elts
        if not (isinstance(col_node, ast.Constant) and isinstance(col_node.value, str)):
            return None
        if isinstance(stat_node, ast.Constant) and isinstance(stat_node.value, str):
            pairs.append((col_node.value, stat_node.value))
        elif isinstance(stat_node, ast.Attribute) and isinstance(stat_node.value, ast.Name):
            pairs.append((col_node.value, stat_node.attr))  # np.mean → 'mean'
        elif isinstance(stat_node, ast.Name):
            pairs.append((col_node.value, stat_node.id))
        else:
            return None
    return pairs or None


@REGISTRY.expr
def _groupby_agg(value, ctx: Ctx) -> Optional[list]:
    """df[filter].groupby(by)[col_sel].agg(func/dict/named-kwargs)
    → one tabulate per unique source column.

    Output column names (from named aggregation) are ignored; tabulate uses
    the source column name. Stats shown by tabulate summarize() automatically
    (mean, min, max, std, N) need no special option — just summarize(col).
    Returns None only when no pair can produce any output.
    """
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or not steps:
        return None

    i, cond_str = 0, None

    if isinstance(steps[0], SubscriptStep):
        key = steps[0].key
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            return None
        if isinstance(key, (ast.List, ast.Tuple)):
            return None
        cond_str = _translate_filter(key, ctx.tr)
        if cond_str is None:
            return None
        i = 1

    if i >= len(steps) or not (isinstance(steps[i], MethodStep) and steps[i].name == "groupby"):
        return None
    gb_step = steps[i]
    i += 1

    if not gb_step.args:
        return None
    by_vars = chain_str_list(gb_step.args[0])
    if by_vars is None:
        s = str_const(gb_step.args[0])
        by_vars = [s] if s else None
    if not by_vars:
        return None

    extra_opts: list = []
    dn = gb_step.kwargs.get("dropna")
    if isinstance(dn, ast.Constant) and dn.value is False:
        extra_opts.append("missing")

    remaining, post = _peel_post_proc(list(steps[i:]))
    extra_opts = post + extra_opts

    if not remaining or not isinstance(remaining[-1], MethodStep):
        return None
    agg_step = remaining[-1]
    if agg_step.name not in ("agg", "aggregate"):
        return None

    val_cols = _extract_val_cols(remaining[:-1])
    if val_cols is None and len(remaining) > 1:
        return None

    # Parse (src_col, stat) pairs — positional args first, then named kwargs
    pairs = _parse_agg_arg(agg_step.args, val_cols)
    if pairs is None and agg_step.kwargs:
        pairs = _parse_named_agg_display(agg_step.kwargs)
    if pairs is None:
        return None

    by_str = " ".join(_sub_pdc(by_vars, ctx))
    if_str = f" if {cond_str}" if cond_str else ""

    # Build one tabulate per unique source column.
    # tabulate summarize(col) always shows N, mean, std, min, max — so a single
    # line covers many stats at once. Count/size → plain tabulate (N shown there too).
    note_lines: list = []
    # col → ordered list of unique micro_stat values (None = default: mean/min/max/std)
    col_stats: dict = {}   # ordered by first appearance
    has_count = False

    for col, func in pairs:
        if func in _DISPLAY_NO_EQUIV:
            note_lines.append(
                f"// NOTE: agg('{func}') on '{col or '?'}': "
                f"no microdata display equivalent"
            )
        elif func in _COUNT_STATS:
            has_count = True   # N shown automatically in any summarize line
        else:
            micro_stat = _AGG_FUNC_STAT.get(func)
            lst = col_stats.setdefault(col, [])
            if micro_stat not in lst:
                lst.append(micro_stat)

    tabulate_lines = []
    for col, stats in col_stats.items():
        # Combine all specific stats (non-None) into one summarize() line.
        # mean is summarize's default; other stats are added as explicit options.
        specific = [s for s in stats if s is not None]
        stat_opts = " ".join(specific)   # e.g. "std p50" or "" for mean-only
        tabulate_lines.append(
            f"tabulate {by_str}{if_str}"
            f"{_build_opts(f'summarize({col})', stat_opts, extra=extra_opts)}"
        )
    # Only count stats requested and no summarize col → emit plain tabulate
    if has_count and not col_stats:
        tabulate_lines.append(f"tabulate {by_str}{if_str}{_build_opts(extra=extra_opts)}")

    result = note_lines + tabulate_lines
    return result or None


@REGISTRY.expr
def _col_stat(value, ctx: Ctx) -> Optional[list]:
    """df['col'].mean() etc. → summarize col"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) < 2:
        return None
    # Skip groupby chains — handled by _groupby_tabulate
    if any(isinstance(s, MethodStep) and s.name == "groupby" for s in steps):
        return None
    stat_step = steps[-1]
    col_step = steps[-2]
    if not (isinstance(stat_step, MethodStep) and stat_step.name in _COL_STAT_METHODS):
        return None
    if isinstance(col_step, SubscriptStep):
        col = str_const(col_step.key)
    elif isinstance(col_step, AttrStep):
        col = col_step.name
    else:
        col = None
    if col is None:
        return None
    return [f"summarize {col}"]


@REGISTRY.expr
def _col_hist(value, ctx: Ctx) -> Optional[list]:
    """df['col'].hist() → histogram col  (df['col'].plot() is handled by _df_plot)"""
    if not _is_call(value, "hist"):
        return None
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) < 2:
        return None
    col_step = steps[-2]
    # skip df.plot.hist() — handled by _df_plot
    if isinstance(col_step, AttrStep) and col_step.name == "plot":
        return None
    if isinstance(col_step, SubscriptStep):
        col = str_const(col_step.key)
    elif isinstance(col_step, AttrStep):
        col = col_step.name
    else:
        col = None
    if col is None:
        return None
    return [f"histogram {col}"]


@REGISTRY.expr
def _describe(value, ctx: Ctx) -> Optional[list]:
    """df.describe() / df[['a','b']].describe() → summarize [cols]"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or not steps:
        return None
    if not (isinstance(steps[-1], MethodStep) and steps[-1].name == "describe"):
        return None
    if len(steps) == 1:
        return ["summarize"]
    if len(steps) == 2 and isinstance(steps[0], SubscriptStep):
        cols = _str_list(steps[0].key)
        if cols:
            return ["summarize " + " ".join(cols)]
    return None


@REGISTRY.expr
def _correlate(value, ctx: Ctx) -> Optional[list]:
    """df[['a','b']].corr() / df['a'].corr(df['b']) → correlate a b"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or not steps:
        return None
    corr = steps[-1]
    if not (isinstance(corr, MethodStep) and corr.name == "corr"):
        return None
    if len(steps) == 2 and isinstance(steps[0], SubscriptStep):
        # df[['a', 'b']].corr()
        cols = _str_list(steps[0].key)
        if cols and len(cols) >= 2:
            return ["correlate " + " ".join(cols)]
        # df['a'].corr(df['b'])
        a = str_const(steps[0].key)
        if a and corr.args:
            b = _col_name(corr.args[0], ctx.df_name, ctx.tr)
            if b:
                return [f"correlate {a} {b}"]
    return None


@REGISTRY.expr
def _crosstab(value, ctx: Ctx) -> Optional[list]:
    """pd.crosstab(df['a'], df['b'], normalize=..., values=..., aggfunc=...) → tabulate a b [opts]"""
    root, steps = decompose(value)
    if not (isinstance(root, ast.Name) and root.id == "pd"):
        return None
    if not (len(steps) == 1 and isinstance(steps[0], MethodStep)
            and steps[0].name == "crosstab"):
        return None
    ct = steps[0]
    args = ct.args
    if len(args) < 2:
        return None
    a = _col_name(args[0], ctx.df_name, ctx.tr)
    b = _col_name(args[1], ctx.df_name, ctx.tr)
    if not (a and b):
        return None

    kw = ct.kwargs
    opts = []

    # normalize= → pct option
    norm = kw.get("normalize")
    if norm is not None:
        if isinstance(norm, ast.Constant):
            if norm.value in (True, "all"):
                opts.append("cellpct")
            elif norm.value == "index":
                opts.append("rowpct")
            elif norm.value == "columns":
                opts.append("colpct")
        elif isinstance(norm, ast.Name) and norm.id == "True":
            opts.append("cellpct")

    # values= + aggfunc= → summarize(col) [stat]
    val_node = kw.get("values")
    agg_node = kw.get("aggfunc")
    if val_node is not None:
        val_col = _col_name(val_node, ctx.df_name, ctx.tr)
        if val_col:
            stat = None
            if isinstance(agg_node, ast.Constant) and isinstance(agg_node.value, str):
                stat = _AGG_FUNC_STAT.get(agg_node.value)
            summ = f"summarize({val_col})" + (f" {stat}" if stat else "")
            opts.append(summ)

    opt_str = _build_opts(*opts)
    return [f"tabulate {a} {b}{opt_str}"]


def _str_list_from_node(node) -> Optional[list]:
    """Extract list of string column names from an AST node.
    Handles bare string 'col', list ['col1','col2'], or Name node.
    """
    if node is None:
        return None
    s = str_const(node)
    if s is not None:
        return [s]
    ls = chain_str_list(node)
    if ls is not None:
        return ls
    return None


@REGISTRY.expr
def _pivot_table(value, ctx: Ctx) -> Optional[list]:
    """pd.pivot_table(df, values, index, columns, aggfunc) / df.pivot_table(...)
    → tabulate index_vars col_vars, summarize(val) [stat] [missing]

    Handles:
      - single/list values and index/columns
      - aggfunc as string, list, or dict {col: func_or_list}
      - dropna=False → missing
      - margins=True → ignored (default in microdata)
    """
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if not (isinstance(func, ast.Attribute) and func.attr == "pivot_table"):
        return None
    if not isinstance(func.value, ast.Name):
        return None
    caller = func.value.id
    if caller not in ("pd", ctx.df_name):
        return None

    kw = {k.arg: k.value for k in value.keywords}

    index_vars = _str_list_from_node(kw.get("index"))
    col_vars   = _str_list_from_node(kw.get("columns"))

    if not index_vars and not col_vars:
        return None

    by_vars = (index_vars or []) + (col_vars or [])
    by_str  = " ".join(by_vars)

    val_cols     = _str_list_from_node(kw.get("values"))
    aggfunc_node = kw.get("aggfunc")

    extra_opts: list = []
    dn = kw.get("dropna")
    if isinstance(dn, ast.Constant) and dn.value is False:
        extra_opts.append("missing")

    def _lines_for(col: Optional[str], fn: Optional[str]) -> Optional[str]:
        """Build one tabulate line for (col, aggfunc_string)."""
        if fn in _AGG_NO_EQUIV:
            return None
        stat = _AGG_FUNC_STAT.get(fn) if fn else None
        if fn and fn not in _AGG_FUNC_STAT and fn not in _AGG_NO_EQUIV:
            return None  # unknown function — skip
        if stat == "__freq__":
            # count/size → plain tabulate (freq is already the default display)
            return f"tabulate {by_str}{_build_opts(*extra_opts)}"
        if col:
            return f"tabulate {by_str}{_build_opts(f'summarize({col})', stat, *extra_opts)}"
        return f"tabulate {by_str}{_build_opts(*extra_opts)}"

    lines = []

    if val_cols is None:
        # No values kwarg — plain frequency table
        line = _lines_for(None, None)
        if line:
            lines.append(line)
    elif isinstance(aggfunc_node, ast.Dict):
        # aggfunc={'D': 'mean', 'E': ['min','max']}
        for k_node, v_node in zip(aggfunc_node.keys, aggfunc_node.values):
            col = str_const(k_node) if k_node else None
            if col is None:
                continue
            fns = _str_list_from_node(v_node) or [None]
            for fn in fns:
                line = _lines_for(col, fn)
                if line:
                    lines.append(line)
    else:
        # aggfunc is a string (or default 'mean')
        fn = None
        if isinstance(aggfunc_node, ast.Constant) and isinstance(aggfunc_node.value, str):
            fn = aggfunc_node.value
        for col in val_cols:
            line = _lines_for(col, fn)
            if line:
                lines.append(line)

    return lines if lines else None


@REGISTRY.expr
def _value_counts(value, ctx: Ctx) -> Optional[list]:
    """df['col'].value_counts(...) / df[cols].value_counts() / df.value_counts(cols) → tabulate"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) < 1:
        return None
    # skip groupby forms — handled by _tabulate_panel
    if any(isinstance(s, MethodStep) and s.name == "groupby" for s in steps):
        return None
    # peel trailing head/tail/sort before looking for value_counts
    remaining, post_opts = _peel_post_proc(list(steps))
    if not remaining:
        return None
    vc_step = remaining[-1]
    if not (isinstance(vc_step, MethodStep) and vc_step.name == "value_counts"):
        return None

    kw = vc_step.kwargs
    opts = []
    # normalize=True → cellpct
    norm = kw.get("normalize")
    if isinstance(norm, ast.Constant) and norm.value is True:
        opts.append("cellpct")
    # dropna=False → missing
    dn = kw.get("dropna")
    if isinstance(dn, ast.Constant) and dn.value is False:
        opts.append("missing")
    # sort=True (default) → rowsort(); only add if explicitly True
    sort = kw.get("sort")
    if isinstance(sort, ast.Constant) and sort.value is True:
        opts.append("rowsort()")

    opt_str = _build_opts(*opts, extra=post_opts)

    # Form 1: df.value_counts(['col1', 'col2']) — positional arg with col list
    if len(remaining) == 1:
        if vc_step.args:
            cols_list = chain_str_list(vc_step.args[0])
            if cols_list is None:
                s = str_const(vc_step.args[0])
                cols_list = [s] if s else None
            if cols_list:
                return [f"tabulate {' '.join(cols_list)}{opt_str}"]
        return None

    # Form 2: df['col'].value_counts() or df[['a','b']].value_counts()
    col_step = remaining[-2]
    if isinstance(col_step, SubscriptStep):
        col_spec = _subscript_cols(col_step)
    elif isinstance(col_step, AttrStep):
        col_spec = col_step.name
    else:
        col_spec = None
    if col_spec:
        return [f"tabulate {col_spec}{opt_str}"]
    return None


@REGISTRY.expr
def _series_hist(value, ctx: Ctx) -> Optional[list]:
    """df['col'].hist() → histogram col  (explicit series-hist pattern)"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) < 2:
        return None
    if not (isinstance(steps[-1], MethodStep) and steps[-1].name == "hist"):
        return None
    col_step = steps[-2]
    col = str_const(col_step.key) if isinstance(col_step, SubscriptStep) else None
    if col:
        return [f"histogram {col}"]
    return None


@REGISTRY.expr
def _normaltest(value, ctx: Ctx) -> Optional[list]:
    """scipy.stats.normaltest(df['col']) → normaltest col"""
    root, steps = decompose(value)
    if not (steps and isinstance(steps[-1], MethodStep)
            and steps[-1].name == "normaltest"):
        return None
    args = steps[-1].args
    if not args:
        return None
    col = _col_name(args[0], ctx.df_name, ctx.tr)
    if col:
        return [f"normaltest {col}"]
    return None


_PLT_SKIP = frozenset({
    "show", "savefig", "figure", "subplot", "tight_layout",
    "title", "xlabel", "ylabel", "legend", "grid", "xlim", "ylim",
})


@REGISTRY.expr
def _matplotlib(value, ctx: Ctx) -> Optional[list]:
    """plt.hist(...) / plt.boxplot(...) / plt.show() / etc."""
    root, steps = decompose(value)
    if not (isinstance(root, ast.Name) and root.id in ("plt", "matplotlib")):
        return None
    if not (len(steps) == 1 and isinstance(steps[0], MethodStep)):
        return None
    step = steps[0]
    method = step.name
    if method == "hist":
        col = _col_name(step.args[0] if step.args else None, ctx.df_name, ctx.tr)
        return [f"histogram {col}" if col else "// UNTRANSLATED: plt.hist()"]
    if method in ("boxplot", "boxplots"):
        col = _col_name(step.args[0] if step.args else None, ctx.df_name, ctx.tr)
        return [f"boxplot {col}" if col else "// UNTRANSLATED: plt.boxplot()"]
    if method == "pie":
        col = _col_name(step.args[0] if step.args else None, ctx.df_name, ctx.tr)
        return [f"piechart {col}" if col else "// UNTRANSLATED: plt.pie()"]
    if method in _PLT_SKIP:
        return []  # skip display/styling calls
    return None


_PLOT_NO_EQUIV = frozenset({"line", "area", "kde", "density"})


def _kwarg_cols(kw: dict, key: str) -> Optional[str]:
    """Extract a column spec from a kwarg: string → 'col', list → 'col1 col2'."""
    node = kw.get(key)
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        parts = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                parts.append(elt.value)
            else:
                return None
        return " ".join(parts) if parts else None
    return None


def _subscript_cols(step: SubscriptStep) -> Optional[str]:
    """Extract column spec from a SubscriptStep: single string or list of strings."""
    single = str_const(step.key)
    if single is not None:
        return single
    multi = chain_str_list(step.key)
    if multi:
        return " ".join(multi)
    return None


def _plot_kind_to_microdata(kind: str, kw: dict, col: Optional[str]) -> Optional[str]:
    """Map a resolved plot kind + kwargs to a microdata command string.

    col  — pre-selected column spec (from df[['a','b']].plot.*); overrides y/column.
    Returns a command string, or None if no microdata equivalent.
    """
    if kind in _PLOT_NO_EQUIV:
        return None

    y   = col or _kwarg_cols(kw, "y") or _kwarg_cols(kw, "column")
    x   = _kwarg_str(kw, "x")
    by  = _kwarg_str(kw, "by") or _kwarg_str(kw, "color")

    if kind in ("bar", "barh"):
        opts = ([f"over({x})"] if x else []) + ([f"by({by})"] if by else [])
        opt_str = ", " + " ".join(opts) if opts else ""
        return f"barchart (mean) {y}{opt_str}" if y else "// barchart: no y column"

    if kind == "hist":
        opts = ([f"by({by})"] if by else [])
        opt_str = ", " + " ".join(opts) if opts else ""
        return f"histogram {y}{opt_str}" if y else "// histogram: no column"

    if kind in ("box", "boxplot"):
        opts = ([f"over({x})"] if x else []) + ([f"by({by})"] if by else [])
        opt_str = ", " + " ".join(opts) if opts else ""
        return f"boxplot {y}{opt_str}" if y else "// boxplot: no column"

    if kind == "pie":
        return f"piechart {y}" if y else "// piechart: no column"

    if kind in ("scatter", "hexbin"):
        if x and y:
            return f"hexbin {x} {y}"
        return "// hexbin: need both x and y"

    return None


@REGISTRY.expr
def _df_plot(value, ctx: Ctx) -> Optional[list]:
    """df.plot.KIND(...) / df.plot(kind=...) / df.boxplot(...) / df.hist(...)"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name):
        return None
    if not steps or not isinstance(steps[-1], MethodStep):
        return None
    method = steps[-1].name
    kw = steps[-1].kwargs

    # ── df.boxplot(column='y', by='g') ───────────────────────────────────────
    if method == "boxplot" and len(steps) == 1:
        col = _kwarg_cols(kw, "column")
        by  = _kwarg_str(kw, "by")
        opt_str = f", over({by})" if by else ""
        return [f"boxplot {col}{opt_str}" if col else "// boxplot: no column specified"]

    # ── df.hist(column='col' or ['a','b']) ────────────────────────────────────
    if method == "hist" and len(steps) == 1:
        col = _kwarg_cols(kw, "column")
        return [f"histogram {col}" if col else "// histogram: no column"]

    # ── df.plot.KIND(...) ─────────────────────────────────────────────────────
    if (len(steps) == 2
            and isinstance(steps[0], AttrStep) and steps[0].name == "plot"):
        cmd = _plot_kind_to_microdata(method, kw, col=None)
        if cmd is None:
            return [f"// UNTRANSLATED: df.plot.{method}() — no microdata equivalent"]
        return [cmd]

    # ── df.plot(kind='xxx', ...) ──────────────────────────────────────────────
    if method == "plot" and len(steps) == 1:
        kind = _kwarg_str(kw, "kind") or "line"
        kw2  = {k: v for k, v in kw.items() if k != "kind"}
        cmd  = _plot_kind_to_microdata(kind, kw2, col=None)
        if cmd is None:
            return [f"// UNTRANSLATED: df.plot(kind='{kind}') — no microdata equivalent"]
        return [cmd]

    # ── df['col'].plot.KIND(...) / df[['a','b']].plot.KIND(...) ──────────────
    if (len(steps) == 3
            and isinstance(steps[0], SubscriptStep)
            and isinstance(steps[1], AttrStep) and steps[1].name == "plot"):
        col = _subscript_cols(steps[0])
        cmd = _plot_kind_to_microdata(method, kw, col=col)
        if cmd is None:
            return [f"// UNTRANSLATED: df[...].plot.{method}() — no microdata equivalent"]
        return [cmd]

    # ── df['col'].plot() / df[['a','b']].plot() ───────────────────────────────
    if (len(steps) == 2
            and isinstance(steps[0], SubscriptStep)
            and method == "plot"):
        col = _subscript_cols(steps[0])
        # Default plot() → histogram
        by  = _kwarg_str(kw, "by") or _kwarg_str(kw, "color")
        opt_str = f", by({by})" if by else ""
        return [f"histogram {col}{opt_str}" if col else "// histogram: no column"]

    return None


# ── anova ─────────────────────────────────────────────────────────────────────

def _group_col_from_eq(cond, df_name: str) -> Optional[str]:
    """Extract grouping column from df['g'] == v comparison."""
    if not isinstance(cond, ast.Compare) or len(cond.ops) != 1:
        return None
    if not isinstance(cond.ops[0], ast.Eq):
        return None
    left = cond.left
    if isinstance(left, ast.Subscript):
        if isinstance(left.value, ast.Name) and left.value.id == df_name:
            return str_const(left.slice)
    return None


@REGISTRY.expr
def _anova_f_oneway(value, ctx: Ctx) -> Optional[list]:
    """scipy.stats.f_oneway(df[df['g']==1]['y'], ...) → anova y g"""
    root, steps = decompose(value)
    if not (steps and isinstance(steps[-1], MethodStep)
            and steps[-1].name == "f_oneway"):
        return None
    args = steps[-1].args
    if len(args) < 2:
        return None

    dep_vars: set = set()
    group_vars: set = set()
    for arg in args:
        arg_root, arg_steps = decompose(arg)
        if not (is_df_root(arg_root, ctx.df_name) and len(arg_steps) >= 2):
            return None
        last = arg_steps[-1]
        if not isinstance(last, SubscriptStep):
            return None
        dep = str_const(last.key)
        if dep is None:
            return None
        dep_vars.add(dep)
        filt = arg_steps[-2]
        if not isinstance(filt, SubscriptStep):
            return None
        group = _group_col_from_eq(filt.key, ctx.df_name)
        if group is None:
            return None
        group_vars.add(group)

    if len(dep_vars) != 1 or len(group_vars) != 1:
        return None
    return [f"anova {dep_vars.pop()} {group_vars.pop()}"]


# ── fillna inplace ────────────────────────────────────────────────────────────

@REGISTRY.expr
def _fillna_inplace(value, ctx: Ctx) -> Optional[list]:
    """df['col'].fillna(val, inplace=True) → replace col = val if sysmiss(col)"""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or len(steps) < 2:
        return None
    step = steps[-1]
    if not (isinstance(step, MethodStep) and step.name == "fillna"):
        return None
    # require inplace=True
    ip = step.kwargs.get("inplace")
    if not (isinstance(ip, ast.Constant) and ip.value is True):
        return None
    fill_node = step.args[0] if step.args else step.kwargs.get("value")
    if fill_node is None:
        return None
    fill = ctx.tr.translate(fill_node)
    if fill is None:
        return None
    col_step = steps[-2]
    if isinstance(col_step, SubscriptStep):
        col = str_const(col_step.key)
    elif isinstance(col_step, AttrStep):
        col = col_step.name
    else:
        col = None
    if col:
        return [f"replace {col} = {fill} if sysmiss({col})"]
    return None


# ── rolling / cumulative — no microdata equivalent ────────────────────────────

_ROLLING_METHODS = frozenset({
    "rolling", "expanding", "ewm",
    "cumsum", "cumprod", "cummax", "cummin",
    "shift", "diff", "pct_change",
})


@REGISTRY.expr
def _no_equiv_rolling(value, ctx: Ctx) -> Optional[list]:
    """Flag rolling/cumulative/lag patterns with a comment — no microdata equivalent."""
    root, steps = decompose(value)
    if not is_df_root(root, ctx.df_name) or not steps:
        return None
    # find the first no-equiv method anywhere in the chain
    for step in steps:
        if isinstance(step, MethodStep) and step.name in _ROLLING_METHODS:
            return [f"# NOTE: {step.name}() has no direct microdata equivalent"]
    return None


# ── tabulate chi2 ─────────────────────────────────────────────────────────────

@REGISTRY.expr
def _chi2_crosstab(value, ctx: Ctx) -> Optional[list]:
    """chi2_contingency(pd.crosstab(df['a'], df['b'])) → tabulate a b, chi2"""
    # chi2_contingency may be a bare call (Name) or method call (stats.chi2_contingency)
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if isinstance(func, ast.Name):
        if func.id != "chi2_contingency":
            return None
        crosstab_args = value.args
    elif isinstance(func, ast.Attribute):
        if func.attr != "chi2_contingency":
            return None
        crosstab_args = value.args
    else:
        return None
    if not crosstab_args:
        return None
    ct_root, ct_steps = decompose(crosstab_args[0])
    if not (isinstance(ct_root, ast.Name) and ct_root.id == "pd"):
        return None
    if not (len(ct_steps) == 1 and isinstance(ct_steps[0], MethodStep)
            and ct_steps[0].name == "crosstab"):
        return None
    ct_args = ct_steps[0].args
    if len(ct_args) < 2:
        return None
    a = _col_name(ct_args[0], ctx.df_name, ctx.tr)
    b = _col_name(ct_args[1], ctx.df_name, ctx.tr)
    if a and b:
        return [f"tabulate {a} {b}, chi2"]
    return None
