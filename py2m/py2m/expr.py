"""
ExprTranslator: converts Python AST expression nodes to microdata.no expression strings.

df['col'] / df.col        → col
np.log(x)                 → ln(x)
pd.isna(x)                → sysmiss(x)
+, -, *, /, **            → same
==, !=, <, <=, >, >=      → same
and / or / not            → & / | / !
inlist(), inrange(), etc. → pass-through (microdata functions)

Returns None for untranslatable expressions.
"""
import ast
from typing import Optional

# numpy attr → microdata function name (None = no equivalent)
_NP_FUNC: dict[str, Optional[str]] = {
    "log": "ln", "log10": "log10", "log2": None,
    "exp": "exp", "sqrt": "sqrt",
    "abs": "abs", "absolute": "abs",
    "ceil": "ceil", "floor": "floor", "trunc": "int",
    "arccos": "acos", "arcsin": "asin", "arctan": "atan",
    "cos": "cos", "sin": "sin", "tan": "tan",
    "round": "round", "around": "round",
    "sign": None, "clip": None,
}

_MATH_FUNC: dict[str, Optional[str]] = {
    "log": "ln", "log10": "log10", "log2": None,
    "exp": "exp", "sqrt": "sqrt",
    "fabs": "abs", "ceil": "ceil", "floor": "floor", "trunc": "int",
    "cos": "cos", "sin": "sin", "tan": "tan",
    "acos": "acos", "asin": "asin", "atan": "atan",
    "comb": "comb",
    "lgamma": "lnfactorial",
}

# Functions that are microdata-native and pass through directly
_MICRODATA_FUNCS: set[str] = {
    # math
    "ln", "log10", "sqrt", "exp", "abs", "ceil", "floor", "int", "round", "pi",
    "cos", "sin", "tan", "acos", "asin", "atan",
    "comb", "lnfactorial", "logit",
    # date
    "date", "year", "month", "day", "week", "halfyear", "quarter",
    "dow", "doy", "isoformatdate", "date_fmt",
    # probability
    "normal", "normalden",
    "chi2", "chi2den", "chi2tail", "invchi2", "invchi2tail",
    "t", "tden", "ttail", "invt", "invttail",
    "F", "Fden", "Ftail", "invF", "invFtail",
    "binomial", "binomialp", "binomialtail",
    "betaden", "ibeta", "ibetatail", "invibeta", "invibetatail",
    # nF / nchi2 / nt families
    "nF", "nFden", "nFtail", "nchi2", "nchi2den", "nchi2tail",
    "nt", "ntden", "nttail", "invnttail",
    # string
    "length", "string", "lower", "upper", "substr",
    "trim", "ltrim", "rtrim", "startswith", "endswith",
    # logic
    "inlist", "inrange", "sysmiss",
    # row aggregates
    "rowmax", "rowmin", "rowmean", "rowmedian", "rowtotal",
    "rowstd", "rowmissing", "rowvalid", "rowconcat",
    # other
    "quantile", "to_int", "to_str",
}

# scipy.stats distribution method → microdata function
# Handles both direct imports (norm.cdf) and stats.norm.cdf form.
# Positional args are passed through as-is (loc/scale kwargs are ignored).
_SCIPY_DIST_MAP: dict[tuple, str] = {
    # Normal
    ("norm",  "cdf"):  "normal",
    ("norm",  "pdf"):  "normalden",
    # Chi-squared
    ("chi2",  "cdf"):  "chi2",
    ("chi2",  "sf"):   "chi2tail",
    ("chi2",  "ppf"):  "invchi2",
    ("chi2",  "isf"):  "invchi2tail",
    # Student's t
    ("t",     "cdf"):  "t",
    ("t",     "sf"):   "ttail",
    ("t",     "ppf"):  "invt",
    ("t",     "isf"):  "invttail",
    # F-distribution
    ("f",     "cdf"):  "F",
    ("f",     "sf"):   "Ftail",
    ("f",     "ppf"):  "invF",
    ("f",     "isf"):  "invFtail",
    # Binomial
    ("binom", "cdf"):  "binomial",
    ("binom", "pmf"):  "binomialp",
    ("binom", "sf"):   "binomialtail",
    # Beta
    ("beta",  "cdf"):  "ibeta",
    ("beta",  "sf"):   "ibetatail",
    ("beta",  "ppf"):  "invibeta",
    ("beta",  "isf"):  "invibetatail",
    # Noncentral families
    ("ncx2",  "cdf"):  "nchi2",
    ("ncx2",  "sf"):   "nchi2tail",
    ("ncf",   "cdf"):  "nF",
    ("ncf",   "sf"):   "nFtail",
    ("nct",   "cdf"):  "nt",
    ("nct",   "sf"):   "nttail",
}

# pandas .str method → microdata function
_STR_METHODS: dict[str, str] = {
    "lower": "lower",
    "upper": "upper",
    "strip": "trim",
    "lstrip": "ltrim",
    "rstrip": "rtrim",
    "startswith": "startswith",
    "endswith": "endswith",
    "len": "length",
}


class ExprTranslator:
    """Translates a Python AST expression node to a microdata expression string."""

    def __init__(self, df_name: str = "df", panel_date_col: str = None):
        self.df_name = df_name
        self.panel_date_col = panel_date_col  # Python column name that maps to panel@date

    def translate(self, node) -> Optional[str]:
        """Return microdata expression string, or None if untranslatable."""
        if node is None:
            return None
        if isinstance(node, str):
            try:
                return self.translate(ast.parse(node, mode="eval").body)
            except SyntaxError:
                return None
        fn = getattr(self, f"_t_{type(node).__name__}", None)
        return fn(node) if fn else None

    # ── leaf nodes ──────────────────────────────────────────────────────────

    def _t_Constant(self, node) -> Optional[str]:
        v = node.value
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return f"'{v}'"
        return None

    def _t_Name(self, node) -> Optional[str]:
        n = node.id
        if n == self.df_name:
            return None
        if self.panel_date_col and n == self.panel_date_col:
            return "panel@date"
        if n in ("True", "False"):
            return "1" if n == "True" else "0"
        if n in ("None", "nan", "inf", "NaN"):
            return None
        return n  # column name or let-binding

    # .dt component → microdata date function
    _DT_FUNC: dict = {
        "year": "year", "month": "month", "day": "day",
        "quarter": "quarter", "week": "week",
        "dayofweek": "dow", "weekday": "dow",
        "dayofyear": "doy",
    }

    def _t_Attribute(self, node) -> Optional[str]:
        # df['col'].dt.year  /  df.col.dt.month  etc.
        if isinstance(node.value, ast.Attribute) and node.value.attr == "dt":
            func = self._DT_FUNC.get(node.attr)
            if func is not None:
                col = self.translate(node.value.value)
                if col is not None:
                    return f"{func}({col})"
            return None  # unsupported .dt component — don't fall through

        # df.colname
        if isinstance(node.value, ast.Name):
            if node.value.id == self.df_name:
                return node.attr
            if node.value.id == "np" and node.attr == "pi":
                return "pi()"
            if node.value.id == "math" and node.attr == "pi":
                return "pi()"
        return None

    def _t_Subscript(self, node) -> Optional[str]:
        # df['colname']
        if isinstance(node.value, ast.Name) and node.value.id == self.df_name:
            s = node.slice
            if isinstance(s, ast.Constant) and isinstance(s.value, str):
                col = s.value
                # Substitute the panel time column with its microdata name
                if self.panel_date_col and col == self.panel_date_col:
                    return "panel@date"
                return col
            if isinstance(s, ast.Name):
                return s.id
        return None

    # ── operators ───────────────────────────────────────────────────────────

    def _t_BinOp(self, node) -> Optional[str]:
        left = self.translate(node.left)
        right = self.translate(node.right)
        if left is None or right is None:
            return None
        op_map = {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
            ast.Pow: "**", ast.Mod: "%", ast.FloorDiv: "//",
            ast.BitAnd: "&", ast.BitOr: "|",  # pandas boolean mask operators
        }
        op = op_map.get(type(node.op))
        if op is None:
            return None
        # For boolean & | wrap each side in parens for unambiguous precedence
        if op in ("&", "|"):
            return f"({left}) {op} ({right})"
        return f"({left} {op} {right})"

    def _t_UnaryOp(self, node) -> Optional[str]:
        operand = self.translate(node.operand)
        if operand is None:
            return None
        if isinstance(node.op, ast.USub):
            return f"(-{operand})"
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, (ast.Not, ast.Invert)):
            return f"!({operand})"
        return None

    def _t_Compare(self, node) -> Optional[str]:
        if len(node.ops) != 1:
            return None  # chained comparisons unsupported
        left = self.translate(node.left)
        right = self.translate(node.comparators[0])
        if left is None or right is None:
            return None
        op_map = {
            ast.Eq: "==", ast.NotEq: "!=",
            ast.Lt: "<", ast.LtE: "<=",
            ast.Gt: ">", ast.GtE: ">=",
        }
        op = op_map.get(type(node.ops[0]))
        if op is None:
            return None
        return f"{left} {op} {right}"

    def _t_BoolOp(self, node) -> Optional[str]:
        op = "&" if isinstance(node.op, ast.And) else "|"
        parts = [self.translate(v) for v in node.values]
        if any(p is None for p in parts):
            return None
        return f" {op} ".join(f"({p})" for p in parts)

    # ── function calls ───────────────────────────────────────────────────────

    def _t_Call(self, node) -> Optional[str]:
        func = node.func
        args = node.args

        # ── method calls on non-Name values ──────────────────────────────────
        if isinstance(func, ast.Attribute) and not isinstance(func.value, ast.Name):
            kws = {k.arg: k.value for k in node.keywords}

            # df[cols].stat(axis=1) → rowXxx(col1, col2, ...)
            _ROW_AGG_MAP = {
                "max": "rowmax", "min": "rowmin", "mean": "rowmean",
                "sum": "rowtotal", "std": "rowstd", "median": "rowmedian",
            }
            axis = kws.get("axis")
            if isinstance(axis, ast.Constant) and axis.value == 1:
                if func.attr in _ROW_AGG_MAP:
                    cols = self._extract_df_cols(func.value)
                    if cols:
                        return f"{_ROW_AGG_MAP[func.attr]}({', '.join(cols)})"
                # df[cols].isna().sum(axis=1) → rowmissing(...)
                # df[cols].notna().sum(axis=1) → rowvalid(...)
                if (func.attr == "sum"
                        and isinstance(func.value, ast.Call)
                        and isinstance(func.value.func, ast.Attribute)):
                    inner = func.value.func
                    if inner.attr in ("isna", "isnull"):
                        cols = self._extract_df_cols(inner.value)
                        if cols:
                            return f"rowmissing({', '.join(cols)})"
                    if inner.attr in ("notna", "notnull"):
                        cols = self._extract_df_cols(inner.value)
                        if cols:
                            return f"rowvalid({', '.join(cols)})"

            # col.isna() / col.isnull() / col.notna() / col.notnull() — method form
            if func.attr in ("isna", "isnull"):
                col = self.translate(func.value)
                if col is not None:
                    return f"sysmiss({col})"
            if func.attr in ("notna", "notnull"):
                col = self.translate(func.value)
                if col is not None:
                    return f"(!sysmiss({col}))"

            # col.mean() / col.sum() etc. used as scalar expressions
            _COL_STAT_TO_FUNC = {
                "mean": "mean", "sum": "sum", "min": "min", "max": "max",
                "median": "median", "count": "count",
            }
            if func.attr in _COL_STAT_TO_FUNC:
                col = self.translate(func.value)
                if col is not None:
                    return f"{_COL_STAT_TO_FUNC[func.attr]}({col})"

            # col.isin([a, b, c]) → inlist(col, a, b, c)
            if func.attr == "isin":
                col = self.translate(func.value)
                if col is not None and args:
                    vals_node = args[0]
                    if isinstance(vals_node, (ast.List, ast.Tuple)):
                        vals = [self.translate(v) for v in vals_node.elts]
                        if all(v is not None for v in vals):
                            return f"inlist({col}, {', '.join(vals)})"

            # col.between(low, high) → inrange(col, low, high)
            if func.attr == "between":
                col = self.translate(func.value)
                if col is not None and len(args) >= 2:
                    low = self.translate(args[0])
                    high = self.translate(args[1])
                    if low is not None and high is not None:
                        return f"inrange({col}, {low}, {high})"

            # col.abs() → abs(col)
            if func.attr == "abs" and not args:
                col = self.translate(func.value)
                if col is not None:
                    return f"abs({col})"

            # col.round(n) → round(col, n)
            if func.attr == "round":
                col = self.translate(func.value)
                if col is not None:
                    if args:
                        n = self.translate(args[0])
                        if n is not None:
                            return f"round({col}, {n})"
                    return f"round({col})"

            # col.str.replace(old, new) → subinstr(col, old, new, .)
            if (func.attr == "replace"
                    and isinstance(func.value, ast.Attribute)
                    and func.value.attr == "str"):
                col = self.translate(func.value.value)
                if col is not None and len(args) >= 2:
                    old = self.translate(args[0])
                    new_ = self.translate(args[1])
                    if old is not None and new_ is not None:
                        return f"subinstr({col}, {old}, {new_}, .)"

            # col.str.contains(sub) → no microdata equivalent (returns None → UNTRANSLATED)

            # stats.dist.method(x, ...) → microdata distribution function
            # e.g. stats.norm.cdf(x) / st.chi2.sf(x, df)
            if (isinstance(func.value, ast.Attribute)
                    and isinstance(func.value.value, ast.Name)
                    and func.value.value.id in ("stats", "st")):
                mf = _SCIPY_DIST_MAP.get((func.value.attr, func.attr))
                if mf is not None:
                    return self._emit_call(mf, args)

        # ── module.func(args) — np.log(x), math.sqrt(x), pd.isna(x) ─────────
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            mod, attr = func.value.id, func.attr

            if mod == "np":
                mf = _NP_FUNC.get(attr)
                if mf is None:
                    return None
                return self._emit_call(mf, args)

            if mod == "math":
                mf = _MATH_FUNC.get(attr)
                if mf is None:
                    return None
                return self._emit_call(mf, args)

            if mod == "pd":
                if attr in ("isna", "isnull"):
                    return self._emit_call("sysmiss", args)
                if attr in ("notna", "notnull"):
                    a = self.translate(args[0]) if args else None
                    return f"(!sysmiss({a}))" if a else None

            # scipy.special.logit(x)
            if mod == "special" and attr == "logit":
                return self._emit_call("logit", args)

            # Direct scipy.stats import: norm.cdf(x), chi2.sf(x, df), t.cdf(x, df) …
            mf = _SCIPY_DIST_MAP.get((mod, attr))
            if mf is not None:
                return self._emit_call(mf, args)

        # df.col.str.lower() etc. — handled by expander, not here

        # direct function call
        if isinstance(func, ast.Name):
            name = func.id
            if name in _MICRODATA_FUNCS:
                return self._emit_call(name, args)
            if name == "abs":
                return self._emit_call("abs", args)
            if name == "int":
                a = self.translate(args[0]) if args else None
                return f"int({a})" if a else None
            if name == "float":
                return self.translate(args[0]) if args else None
            if name == "str":
                a = self.translate(args[0]) if args else None
                return f"string({a})" if a else None

        return None

    def _extract_df_cols(self, node) -> Optional[list]:
        """Extract column-name list from df[['a','b','c']] AST node, or None."""
        if not isinstance(node, ast.Subscript):
            return None
        if not (isinstance(node.value, ast.Name) and node.value.id == self.df_name):
            return None
        s = node.slice
        if isinstance(s, ast.List):
            cols = []
            for elt in s.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    cols.append(elt.value)
                else:
                    return None
            return cols if cols else None
        return None

    def _emit_call(self, name: str, args: list) -> Optional[str]:
        translated = [self.translate(a) for a in args]
        if any(t is None for t in translated):
            return None
        return f"{name}({', '.join(translated)})"

    # ── str accessor ─────────────────────────────────────────────────────────

    def translate_str_chain(self, node) -> Optional[str]:
        """
        Translate any df['col'].str.<ops> chain to a microdata expression.

        Uses the chain decomposer, so arbitrary chaining and subscripts work:
          df['col'].str.lower()
          df['col'].str.lower().str.strip()
          df['col'].str.startswith('x')
          df['col'].str[0:3]          ← subscript form
        """
        from .chain import decompose, AttrStep, MethodStep, SubscriptStep

        root, steps = decompose(node)

        # Find first AttrStep('str')
        str_idx = next(
            (i for i, s in enumerate(steps) if isinstance(s, AttrStep) and s.name == "str"),
            -1,
        )
        if str_idx < 0:
            return None

        # Translate the column expression from root + steps before .str
        col_expr = self._steps_to_col(root, steps[:str_idx])
        if col_expr is None:
            return None

        # Walk through remaining steps, applying str operations in order
        i = str_idx + 1
        while i < len(steps):
            step = steps[i]
            if isinstance(step, AttrStep) and step.name == "str":
                i += 1  # repeated .str accessor between chained methods — skip
            elif isinstance(step, MethodStep):
                col_expr = self._apply_str_method(col_expr, step.name, step.args)
                if col_expr is None:
                    return None
                i += 1
            elif isinstance(step, SubscriptStep):
                col_expr = self._apply_str_subscript(col_expr, step.key)
                if col_expr is None:
                    return None
                i += 1
            else:
                return None

        return col_expr

    def _steps_to_col(self, root, steps) -> Optional[str]:
        """
        Translate (root, pre-str steps) to a column name string.
        Handles:  df['col'] → 'col',  df.col → 'col'
        """
        from .chain import SubscriptStep, AttrStep, str_const
        if not isinstance(root, ast.Name):
            return None
        if root.id == self.df_name:
            if len(steps) == 1:
                s = steps[0]
                if isinstance(s, SubscriptStep):
                    return str_const(s.key)
                if isinstance(s, AttrStep):
                    return s.name
            return None
        # A standalone variable name used as a string column
        if not steps:
            return root.id
        return None

    def _apply_str_method(self, col_expr: str, method: str, args: list) -> Optional[str]:
        if method == "lower":
            return f"lower({col_expr})"
        if method == "upper":
            return f"upper({col_expr})"
        if method in ("strip",):
            return f"trim({col_expr})"
        if method == "lstrip":
            return f"ltrim({col_expr})"
        if method == "rstrip":
            return f"rtrim({col_expr})"
        if method == "len":
            return f"length({col_expr})"
        if method == "startswith":
            if args:
                v = self.translate(args[0])
                if v:
                    return f"startswith({col_expr}, {v})"
        if method == "endswith":
            if args:
                v = self.translate(args[0])
                if v:
                    return f"endswith({col_expr}, {v})"
        if method == "slice":
            start = self.translate(args[0]) if args else "0"
            stop = self.translate(args[1]) if len(args) > 1 else None
            if start is not None and stop is not None:
                try:
                    return f"substr({col_expr}, {int(start) + 1}, {int(stop) - int(start)})"
                except (ValueError, TypeError):
                    pass
        # .str.replace / .str.contains — no microdata equivalent
        return None

    def _apply_str_subscript(self, col_expr: str, key) -> Optional[str]:
        """df['col'].str[i:j] → substr(col, i+1, j-i)."""
        if isinstance(key, ast.Slice):
            try:
                lo = int(ast.literal_eval(key.lower)) if key.lower else 0
                hi = int(ast.literal_eval(key.upper)) if key.upper else None
                if hi is not None:
                    return f"substr({col_expr}, {lo + 1}, {hi - lo})"
                return col_expr  # str[i:] with no upper bound — return as-is
            except (ValueError, TypeError):
                pass
        return None
