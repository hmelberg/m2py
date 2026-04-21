"""
Py2MTransformer: walks a Python AST and emits microdata.no script lines.

Usage:
    from py2m import transform
    result = transform(python_source, df_name='df')
    print(result.script())
    for w in result.warnings:
        print("WARNING:", w)
"""
import ast
import re
from dataclasses import dataclass, field
from typing import Optional

from .expr import ExprTranslator
from .formula import parse_formula
from .expander import (
    try_np_where, try_map, try_pd_cut, try_fillna, try_clip,
    try_apply_simple_func, try_str_method_assign,
    try_groupby_transform, try_groupby_collapse,
    extract_groupby_transform_info,
    _is_df_col,
)
from .chain import decompose, MethodStep, AttrStep, SubscriptStep, str_const, str_list, is_df_root
from .commands import REGISTRY, Ctx, _AGG_FUNC_STAT


@dataclass
class TranslationResult:
    microdata_lines: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def script(self) -> str:
        return "\n".join(self.microdata_lines)


# ── regression command map ────────────────────────────────────────────────────

_SMF_CMD = {
    "ols": "regress",
    "logit": "logit",
    "probit": "probit",
    "mnlogit": "mlogit",
    "poisson": "poisson",
    "negativebinomial": "negative-binomial",
    "glm": None,  # too general
    "mixedlm": "regress-mml",
}

# linearmodels panel classes → (microdata command, default option)
_PANEL_CLASSES: dict = {
    "PanelOLS":    ("regress-panel", "fe"),
    "RandomEffects": ("regress-panel", "re"),
    "BetweenOLS":  ("regress-panel", "be"),
    "PooledOLS":   ("regress", None),
}

# linearmodels IV classes → method keyword
_IV_CLASSES: dict = {
    "IV2SLS": "2sls",
    "IVLIML": "liml",
    "IVGMM":  "gmm",
}

# plotly express functions → microdata chart commands
_PX_COMMANDS = {
    "histogram": "histogram",
    "box": "boxplot",
    "violin": "boxplot",      # approximate
    "bar": "barchart",
    "pie": "piechart",
    "scatter": "hexbin",      # approximate
    "strip": None,
    "line": None,
    "area": None,
    "scatter_matrix": None,
    "sunburst": None,
    "treemap": None,
    "choropleth": None,
    "density_heatmap": "hexbin",
    "density_contour": None,
    "ecdf": None,
    "sankey": "sankey",
}


# ── main class ────────────────────────────────────────────────────────────────

class Py2MTransformer:
    def __init__(self, df_name: str = "df", dataset_name: str = None):
        self.df_name = df_name
        self._dataset_name = dataset_name  # microdata name of the active dataset, if known
        self._lines: list[str] = []
        self._warnings: list[str] = []
        self._translator = ExprTranslator(df_name)
        self._models: dict = {}   # var_name → {cmd, depvar, predictors, options}
        self._lifelines: dict = {}  # var_name → kind (kaplan-meier, cox, weibull)
        self._known_labels: dict = {}  # var_name → {k: label_str} value-label sets
        self._known_functions: dict = {}  # func_name → ast.FunctionDef
        self._pending_transforms: dict = {}  # var_name → {src_col, stat, by_str}
        self._pending_collapses: dict = {}   # var_name → list of collapse command strings
        self._tmp_count = 0
        self._src_lines: list[str] = []
        # Multi-dataset tracking
        self._current_df: str = df_name   # name of the currently active microdata dataset
        self._known_dfs: set = {df_name}  # all dataset names seen so far
        # Panel tracking: Python column name that corresponds to panel@date after reshape
        self._panel_date_col: Optional[str] = None

    # ── public ───────────────────────────────────────────────────────────────

    def transform(self, source: str) -> TranslationResult:
        self._src_lines = source.splitlines()
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return TranslationResult(
                microdata_lines=[f"// Parse error: {e}"],
                warnings=[str(e)],
            )
        self._collect_function_defs(tree)
        for node in tree.body:
            self._visit(node)
        return TranslationResult(
            microdata_lines=self._lines,
            warnings=self._warnings,
        )

    # ── internals ────────────────────────────────────────────────────────────

    def _emit(self, line: str):
        self._lines.append(line)

    def _warn(self, msg: str, lineno: int = None):
        loc = f" (line {lineno})" if lineno else ""
        self._warnings.append(f"{msg}{loc}")

    def _comment(self, text: str):
        self._lines.append(f"// {text}")

    def _set_panel_date_col(self, col: Optional[str]):
        """Record that a Python column name maps to panel@date and update the translator."""
        self._panel_date_col = col
        self._translator.panel_date_col = col

    def _untranslated(self, node):
        """Emit original Python source line as a comment."""
        lineno = getattr(node, "lineno", None)
        if lineno and lineno <= len(self._src_lines):
            self._comment(f"UNTRANSLATED: {self._src_lines[lineno - 1].strip()}")
        else:
            self._comment("UNTRANSLATED")

    # Methods that display individual rows — not allowed in microdata
    _DF_DISPLAY_METHODS = frozenset({
        "head", "tail", "sample", "iloc", "loc",
        "to_string", "to_csv", "to_excel", "to_json", "to_html",
        "iterrows", "itertuples", "values", "to_numpy", "to_records",
    })

    def _is_df_display_attempt(self, node) -> bool:
        """Return True if the expression is a bare dataframe or a display call on one."""
        root, steps = decompose(node)
        if not (isinstance(root, ast.Name) and
                root.id in (self._known_dfs | {self.df_name})):
            return False
        # bare `df` or `df[cond]` with no method steps → display attempt
        if not steps:
            return True
        # Method call on df: df.head(), df.tail(), df.to_csv(), etc.
        if (isinstance(steps[-1], MethodStep) and
                steps[-1].name in self._DF_DISPLAY_METHODS):
            return True
        # Subscript with no following method (df[cond], df[['a','b']]) — already caught
        # by the non-call branch, but guard here too
        if all(isinstance(s, (SubscriptStep, AttrStep)) for s in steps):
            return True
        return False

    def _emit_privacy_note(self):
        """Emit a Norwegian note that microdata does not allow individual-level display."""
        self._comment(
            "OBS: Microdata tillater ikke visning av individnivådata av personvernhensyn. "
            "Bruk aggregeringskommandoer (tabulate, summarize, regress osv.) for å analysere dataene."
        )

    def _tmp(self, label: str = "") -> str:
        self._tmp_count += 1
        return f"_py2m_{label}{self._tmp_count}" if label else f"_py2m_tmp{self._tmp_count}"

    def _ctx(self) -> Ctx:
        return Ctx(self.df_name, self._translator, self._known_functions)

    # ── multi-dataset helpers ─────────────────────────────────────────────────

    def _ensure_active(self, name: str) -> None:
        """Emit 'use NAME' only when NAME is not the currently active dataset."""
        if self._current_df != name:
            self._emit(f"use {name}")
            self._current_df = name

    def _clone_and_switch(self, src: str, new_name: str) -> None:
        """Ensure src is active, clone it as new_name, then switch into it."""
        self._ensure_active(src)
        self._emit(f"clone-dataset {new_name}")
        self._known_dfs.add(new_name)
        self._emit(f"use {new_name}")
        self._current_df = new_name

    def _try_reshape(self, target: str, value, lineno: int) -> bool:
        """
        Handle reshape operations:
          pd.wide_to_long(df, stubnames, i, j)  → reshape-to-panel stub1 stub2
          df.pivot(...)                           → reshape-from-panel
          df.pivot_table(...)                     → reshape-from-panel
          df.melt(..., value_name=stub, var_name=j) → reshape-to-panel stub  (with note)
        If target differs from the source df, clone first.
        """
        if not isinstance(value, ast.Call):
            return False

        func = value.func
        kws = {k.arg: k.value for k in value.keywords}
        pargs = value.args

        # ── pd.wide_to_long(df, stubnames, i, j) ─────────────────────────────
        if (isinstance(func, ast.Attribute) and func.attr == "wide_to_long"
                and isinstance(func.value, ast.Name) and func.value.id == "pd"):
            stubs_node = pargs[1] if len(pargs) > 1 else kws.get("stubnames")
            stubs = str_list(stubs_node) if stubs_node is not None else None
            if not stubs:
                return False
            j_node = pargs[3] if len(pargs) > 3 else kws.get("j")
            j_name = str_const(j_node)
            src_node = pargs[0] if pargs else None
            src_name = src_node.id if isinstance(src_node, ast.Name) else self.df_name
            if target != src_name:
                self._clone_and_switch(src_name, target)
            else:
                self._ensure_active(src_name)
            self._emit(f"reshape-to-panel {' '.join(stubs)}")
            self._set_panel_date_col(j_name)
            return True

        # ── df.pivot(...) / df.pivot_table(...) / df.melt(...) ──────────────
        # Source may be any known dataframe, not just self.df_name.
        root, steps = decompose(value)
        src_name = root.id if isinstance(root, ast.Name) else None
        if not (src_name and src_name in self._known_dfs and steps
                and isinstance(steps[-1], MethodStep)):
            return False
        method = steps[-1].name

        if method in ("pivot", "pivot_table"):
            if target != src_name:
                self._clone_and_switch(src_name, target)
            else:
                self._ensure_active(src_name)
            self._emit("reshape-from-panel")
            self._set_panel_date_col(None)
            return True

        if method == "melt":
            step = steps[-1]
            val_name_node = step.kwargs.get("value_name")
            var_name_node = step.kwargs.get("var_name")
            stub = str_const(val_name_node)
            j_name = str_const(var_name_node)
            if stub is None:
                return False
            if target != src_name:
                self._clone_and_switch(src_name, target)
            else:
                self._ensure_active(src_name)
            self._comment(
                f"NOTE: melt to long format — '{stub}' treated as panel variable prefix"
            )
            self._emit(f"reshape-to-panel {stub}")
            self._set_panel_date_col(j_name)
            return True

        return False

    def _try_clone_dataset(self, new_name: str, value, lineno: int) -> bool:
        """
        Recognise: new_df = src_df[cond] / .query() / .dropna() / .groupby().agg()
        and emit:  clone-dataset new_df + use new_df + filter/collapse command.
        Returns True if the pattern was recognised.
        """
        root, steps = decompose(value)
        if not (isinstance(root, ast.Name) and root.id in self._known_dfs):
            return False
        src = root.id
        if not steps:
            return False

        src_tr = ExprTranslator(src)

        # ── groupby collapse: src_df.groupby(...).agg(...) ───────────────────
        lines = try_groupby_collapse(value, src, src_tr)
        if lines is not None:
            self._clone_and_switch(src, new_name)
            for ln in lines:
                self._emit(ln)
            return True

        step = steps[0]

        # ── src_df[...] subscript patterns ───────────────────────────────────
        if isinstance(step, SubscriptStep):
            s = step.key
            # df[['col1', 'col2']] → keep cols
            if isinstance(s, (ast.List, ast.Tuple)):
                cols = _extract_str_list(s)
                if cols:
                    self._clone_and_switch(src, new_name)
                    self._emit("keep " + " ".join(cols))
                    return True
            # df[~mask] → drop if
            if isinstance(s, ast.UnaryOp) and isinstance(s.op, (ast.Invert, ast.Not)):
                old_tr = self._translator
                self._translator = src_tr
                inner = self._mask_to_condition(s.operand)
                self._translator = old_tr
                if inner:
                    self._clone_and_switch(src, new_name)
                    self._emit(f"drop if {inner}")
                    return True
            # df[cond] → keep if
            old_tr = self._translator
            self._translator = src_tr
            cond = self._mask_to_condition(s)
            self._translator = old_tr
            if cond:
                self._clone_and_switch(src, new_name)
                self._emit(f"keep if {cond}")
                return True

        # ── .query('expr') ───────────────────────────────────────────────────
        if isinstance(step, MethodStep) and step.name == "query":
            if step.args and isinstance(step.args[0], ast.Constant):
                expr_str = src_tr.translate(step.args[0].value)
                if expr_str:
                    self._clone_and_switch(src, new_name)
                    self._emit(f"keep if {expr_str}")
                    return True

        # ── .dropna(subset=[...]) → drop if sysmiss(...) ────────────────────
        if isinstance(step, MethodStep) and step.name == "dropna":
            if isinstance(value, ast.Call):
                kwargs = {kw.arg: kw.value for kw in value.keywords}
                args = value.args
                subset_node = args[0] if args else kwargs.get("subset")
                if subset_node is not None:
                    cols = _extract_str_list(subset_node)
                    if cols:
                        parts = [f"sysmiss({c})" for c in cols]
                        how_node = kwargs.get("how")
                        how = how_node.value if (how_node and isinstance(how_node, ast.Constant)) else "any"
                        if how == "all":
                            cond = " & ".join(f"({p})" for p in parts) if len(parts) > 1 else parts[0]
                        else:
                            cond = " | ".join(f"({p})" for p in parts) if len(parts) > 1 else parts[0]
                        self._clone_and_switch(src, new_name)
                        self._emit(f"drop if {cond}")
                        return True

        return False

    def _groupby_display_clone(self, collapse_lines: list) -> None:
        """
        Display a grouped summary without modifying the active dataset:
          clone-dataset _tmp → use _tmp → collapse → use df → delete-dataset _tmp
        Used for standalone groupby expressions (not assigned to any variable).
        """
        tmp = self._tmp("disp")
        self._ensure_active(self.df_name)
        self._emit(f"clone-dataset {tmp}")
        self._emit(f"use {tmp}")
        for ln in collapse_lines:
            self._emit(ln)
        self._emit(f"use {self.df_name}")
        self._emit(f"delete-dataset {tmp}")
        self._current_df = self.df_name  # restored

    def _collect_function_defs(self, tree):
        """Pre-scan for function definitions (needed for .apply() support)."""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self._known_functions[node.name] = node

    # ── dispatcher ───────────────────────────────────────────────────────────

    def _visit(self, node):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return  # skip imports
        if isinstance(node, ast.FunctionDef):
            return  # stored in _known_functions, not emitted
        if isinstance(node, ast.Assign):
            self._handle_assign(node)
        elif isinstance(node, ast.AugAssign):
            self._handle_aug_assign(node)
        elif isinstance(node, ast.Expr):
            self._handle_expr_stmt(node)
        elif isinstance(node, ast.For):
            self._handle_for(node)
        elif isinstance(node, ast.If):
            self._handle_if(node)
        elif isinstance(node, (ast.Pass, ast.Break, ast.Continue)):
            pass
        elif isinstance(node, ast.Raise):
            pass
        elif isinstance(node, ast.Return):
            pass
        else:
            self._untranslated(node)

    # ── assignment ───────────────────────────────────────────────────────────

    def _handle_assign(self, node: ast.Assign):
        if len(node.targets) != 1:
            self._untranslated(node)
            return

        target = node.targets[0]
        value = node.value
        lineno = node.lineno

        # ── df = ... (whole dataframe reassignment) ──────────────────────────
        if isinstance(target, ast.Name) and target.id == self.df_name:
            self._ensure_active(self.df_name)
            if _is_pd_dataframe_call(value):
                self._emit(f"create-dataset {self.df_name}")
                return
            if self._try_reshape(target.id, value, lineno):
                return
            if self._try_df_filter(value, lineno):
                return
            if self._try_df_rename(value, lineno):
                return
            # Pure patterns: drop cols, sort comment, no-op, etc.
            df_lines = REGISTRY.match_df(value, self._ctx())
            if df_lines is not None:
                for l in df_lines:
                    self._emit(l)
                return
            if self._try_df_dropna(value, lineno):
                return
            if self._try_df_sample(value, lineno):
                return
            # df = df.groupby(...).agg(...).reset_index()
            lines = try_groupby_collapse(value, self.df_name, self._translator)
            if lines:
                for l in lines:
                    self._emit(l)
                return
            # df = pd.merge(...) / df = df.merge(...)
            if self._try_merge(value, lineno):
                return
            # df = df.join(df2)
            if self._try_join(value, lineno):
                return
            self._untranslated(node)
            self._warn("Unrecognised df-level reassignment", lineno)
            return

        # ── model = smf.ols(...).fit() ───────────────────────────────────────
        if isinstance(target, ast.Name) and _is_statsmodels_fit(value):
            if self._handle_regression_assign(target.id, value, lineno):
                return

        # ── model = PanelOLS.from_formula(...).fit() ─────────────────────────
        if isinstance(target, ast.Name) and _is_panel_fit(value):
            if self._handle_panel_regression(target.id, value, lineno):
                return

        # ── model = IV2SLS.from_formula(...).fit() ───────────────────────────
        if isinstance(target, ast.Name) and _is_iv_fit(value):
            if self._handle_iv_regression(target.id, value, lineno):
                return

        # ── lifelines fitter = KaplanMeierFitter() etc. ──────────────────────
        if isinstance(target, ast.Name) and _is_lifelines_constructor(value):
            kind = _lifelines_kind(value)
            if kind:
                self._lifelines[target.id] = kind
                return

        # ── fitter.fit(...) ──────────────────────────────────────────────────
        if isinstance(target, ast.Name) and _is_lifelines_fit(value, self._lifelines):
            if self._handle_lifelines_fit(target.id, value, lineno):
                return

        # ── df['col'] = ... ──────────────────────────────────────────────────
        col = _is_df_col(target, self.df_name)
        if col:
            self._ensure_active(self.df_name)
            if self._handle_col_assign(col, value, lineno):
                return
            self._untranslated(node)
            self._warn(f"Could not translate assignment to df['{col}']", lineno)
            return

        # ── secondary_df['col'] = ... (multi-dataset) ────────────────────────
        if isinstance(target, (ast.Subscript, ast.Attribute)):
            for sec_df in list(self._known_dfs - {self.df_name}):
                sec_col = _is_df_col(target, sec_df)
                if sec_col is not None:
                    self._ensure_active(sec_df)
                    old_name, old_tr = self.df_name, self._translator
                    self.df_name = sec_df
                    self._translator = ExprTranslator(sec_df)
                    success = self._handle_col_assign(sec_col, value, lineno)
                    self.df_name = old_name
                    self._translator = old_tr
                    if not success:
                        self._untranslated(node)
                        self._warn(f"Could not translate assignment to {sec_df}['{sec_col}']", lineno)
                    return

        # ── df.loc[cond, 'col'] = val ────────────────────────────────────────
        if self._handle_loc_assign(target, value, lineno):
            return

        # ── var = smf.ols(...) (without .fit()) — store smf step for later ─────
        if isinstance(target, ast.Name) and _is_statsmodels_model(value):
            _, steps = decompose(value)
            self._models[target.id] = {"smf_step": steps[0]}
            return

        # ── result = var.fit() ───────────────────────────────────────────────
        if isinstance(target, ast.Name) and _is_method_call(value, "fit"):
            model_obj = value.func.value
            if isinstance(model_obj, ast.Name) and model_obj.id in self._models:
                stored = self._models[model_obj.id]
                if "smf_step" in stored:
                    _, fit_steps = decompose(value)
                    fit_step = fit_steps[-1] if fit_steps else None
                    if fit_step and isinstance(fit_step, MethodStep):
                        info = {"smf_step": stored["smf_step"], "fit_step": fit_step}
                        if self._handle_regression_assign(target.id, info, lineno):
                            return

        # ── var = df.groupby(...)[col].transform(stat) — defer to df['x'] = var ─
        if isinstance(target, ast.Name):
            info = extract_groupby_transform_info(value, self.df_name, self._translator)
            if info:
                self._pending_transforms[target.id] = info
                return

        # ── reshape: pd.wide_to_long / df.pivot / df.melt ────────────────────
        if isinstance(target, ast.Name):
            if self._try_reshape(target.id, value, lineno):
                return

        # ── new_df = src_df[cond / .query() / .dropna() / .groupby().agg()] ─
        # Emit clone-dataset + use + operation immediately (multi-dataset path).
        if isinstance(target, ast.Name) and target.id != self.df_name:
            if self._try_clone_dataset(target.id, value, lineno):
                return

        # ── var = df.groupby(...).agg(...) — store for to_microdata(var, 'name') ─
        if isinstance(target, ast.Name):
            lines = try_groupby_collapse(value, self.df_name, self._translator)
            if lines:
                var_name = target.id
                self._pending_collapses[var_name] = lines
                self._comment(
                    f"NOTE: '{var_name}' is a groupby summary. "
                    f"Use to_microdata({var_name}, 'name') to create a named dataset, "
                    f"or use {self.df_name} = {self.df_name}.groupby(...).agg(...) "
                    f"to collapse in place."
                )
                return

        # ── var = {k: 'label', ...} — value-label set definition ──────────────
        if isinstance(target, ast.Name):
            if self._try_define_labels(target.id, value, lineno):
                return

        # ── let: simple scalar binding ───────────────────────────────────────
        if isinstance(target, ast.Name):
            if self._try_let_binding(target.id, value, lineno):
                return

        # ── NAME = pd.DataFrame(index=SRC.index) / NAME = SRC[[]] → clone-units ─
        if isinstance(target, ast.Name):
            src = _clone_units_source(value)
            if src is not None:
                self._emit(f"clone-units {src} {target.id}")
                return

        # ── NAME = pd.DataFrame(...) → create-dataset ────────────────────────
        if isinstance(target, ast.Name) and _is_pd_dataframe_call(value):
            self._emit(f"create-dataset {target.id}")
            return

        # ── var = df[cond] / df.sort_values() etc. (unrecognised view) ──────────
        # _try_clone_dataset above handles [cond], .query(), .dropna(), .groupby().agg().
        # Only unrecognised methods reach here.
        if isinstance(target, ast.Name) and self._is_df_view_expression(value):
            var = target.id
            self._warn(
                f"'{var}' looks like a filtered/reshaped copy of {self.df_name} "
                f"but the specific pattern could not be translated.",
                lineno,
            )
            self._comment(
                f"WARNING: '{var}' — untranslated view of {self.df_name}"
            )
            return

        self._untranslated(node)

    def _handle_aug_assign(self, node: ast.AugAssign):
        """df['col'] += expr  →  replace col = col + expr (or generate if new)."""
        col = _is_df_col(node.target, self.df_name)
        if col is None:
            self._untranslated(node)
            return
        self._ensure_active(self.df_name)
        val = self._translator.translate(node.value)
        if val is None:
            self._untranslated(node)
            return
        op_map = {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
            ast.Pow: "**",
        }
        op = op_map.get(type(node.op))
        if op is None:
            self._untranslated(node)
            return
        self._emit(f"replace {col} = ({col} {op} {val})")

    # ── df['col'] = <various patterns> ───────────────────────────────────────

    def _handle_col_assign(self, col: str, value, lineno: int) -> bool:
        tr = self._translator

        # df['col'] = pending_transform_var (two-step groupby transform)
        if isinstance(value, ast.Name) and value.id in self._pending_transforms:
            info = self._pending_transforms.pop(value.id)
            self._emit(
                f"aggregate ({info['stat']}) {info['src_col']} -> {col}, by({info['by_str']})"
            )
            return True

        # df['pred'] = model.predict()
        if self._try_model_predict(col, value, lineno):
            return True

        # df['resid'] = model.resid  or  model.fittedvalues
        if self._try_model_attr(col, value, lineno):
            return True

        # df['col'] = df['col'].cat.rename_categories(labels)
        if self._try_assign_labels(col, value, lineno):
            return True

        # df['col'] = pd.to_numeric(df['col']) / .astype(float/int)
        col_lines = REGISTRY.match_col(col, value, self._ctx())
        if col_lines is not None:
            for l in col_lines:
                self._emit(l)
            return True

        # df['col'] = df.groupby(...)['y'].transform('stat')
        lines = try_groupby_transform(col, value, self.df_name, tr)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = np.where(...)
        lines = try_np_where(col, value, tr)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = df['col2'].map({...})
        lines = try_map(col, value, self.df_name, tr)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = pd.cut(...)
        lines = try_pd_cut(col, value, self.df_name, tr)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = df['col2'].fillna(val)
        lines = try_fillna(col, value, self.df_name, tr)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = df['col2'].clip(lower=, upper=)
        lines = try_clip(col, value, self.df_name, tr)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = df['col2'].str.method()
        lines = try_str_method_assign(col, value, self.df_name, tr)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = df['col2'].apply(simple_func)
        lines = try_apply_simple_func(col, value, self.df_name, tr, self._known_functions)
        if lines:
            for l in lines:
                self._emit(l)
            return True

        # df['col'] = simple expression → generate
        expr = tr.translate(value)
        if expr is not None:
            self._emit(f"generate {col} = {expr}")
            return True

        # Last resort: try to extract a clip/fillna inside a function call
        # e.g. np.log(df['x'].clip(lower=1)) → generate tmp = clip; generate col = ln(tmp)
        if self._try_nested_expansion(col, value, lineno):
            return True

        return False

    def _try_nested_expansion(self, col: str, value, lineno: int) -> bool:
        """np.func(df['x'].clip(...)) → generate tmp = clip(...); generate col = func(tmp)."""
        root, steps = decompose(value)
        if not (isinstance(root, ast.Name) and root.id in ("np", "math")):
            return False
        if not (len(steps) == 1 and isinstance(steps[0], MethodStep) and steps[0].args):
            return False
        step = steps[0]
        inner_arg = step.args[0]
        tmp = self._tmp("inner")
        lines = (
            try_clip(tmp, inner_arg, self.df_name, self._translator)
            or try_fillna(tmp, inner_arg, self.df_name, self._translator)
        )
        if not lines:
            return False
        for l in lines:
            self._emit(l)
        from .expr import _NP_FUNC, _MATH_FUNC
        func_map = _NP_FUNC if root.id == "np" else _MATH_FUNC
        mf = func_map.get(step.name)
        if mf:
            self._emit(f"generate {col} = {mf}({tmp})")
            self._emit(f"drop {tmp}")
            return True
        return False

    # ── df = df[...] filters ──────────────────────────────────────────────────

    def _try_df_filter(self, value, lineno: int) -> bool:
        root, steps = decompose(value)
        if not is_df_root(root, self.df_name) or not steps:
            return False
        step = steps[0]
        tr = self._translator

        # df.query("expr")
        if isinstance(step, MethodStep) and step.name == "query":
            if step.args and isinstance(step.args[0], ast.Constant):
                expr = tr.translate(step.args[0].value)
                if expr:
                    self._emit(f"keep if {expr}")
                    return True
            self._warn("Could not translate df.query() expression", lineno)
            return True

        # df.dropna() handled separately by _try_df_dropna
        if isinstance(step, MethodStep) and step.name == "dropna":
            return False

        if not isinstance(step, SubscriptStep):
            return False
        s = step.key

        # df[['col1', 'col2']] — column selection
        if isinstance(s, (ast.List, ast.Tuple)):
            cols = _extract_str_list(s)
            if cols:
                self._emit("keep " + " ".join(cols))
                return True

        # df[~mask] or df[not mask] → drop if
        if isinstance(s, ast.UnaryOp) and isinstance(s.op, (ast.Invert, ast.Not)):
            inner = self._mask_to_condition(s.operand)
            if inner:
                self._emit(f"drop if {inner}")
                return True

        cond = self._mask_to_condition(s)
        if cond:
            self._emit(f"keep if {cond}")
            return True

        return False

    def _mask_to_condition(self, mask_node) -> Optional[str]:
        """Convert a boolean mask expression to a microdata condition string."""
        tr = self._translator
        # Try direct translation
        result = tr.translate(mask_node)
        if result:
            return result
        # If it's a Name (boolean column), it should translate as-is
        return None

    def _try_df_dropna(self, value, lineno: int) -> bool:
        if not _is_method_call(value, "dropna"):
            return False
        tr = self._translator
        kwargs = {kw.arg: kw.value for kw in value.keywords}
        args = value.args

        subset_node = args[0] if args else kwargs.get("subset")
        if subset_node is not None:
            cols = _extract_str_list(subset_node)
            if cols:
                parts = [f"sysmiss({c})" for c in cols]
                how = "any"
                how_node = kwargs.get("how")
                if how_node and isinstance(how_node, ast.Constant):
                    how = how_node.value
                if how == "all":
                    cond = " & ".join(f"({p})" for p in parts) if len(parts) > 1 else parts[0]
                else:
                    cond = " | ".join(f"({p})" for p in parts) if len(parts) > 1 else parts[0]
                self._emit(f"drop if {cond}")
                return True
        # dropna() with no subset — warn
        self._warn("df.dropna() without subset: cannot determine which columns to check", lineno)
        self._comment("UNTRANSLATED: df.dropna() — specify subset=[...] for translation")
        return True

    def _try_df_rename(self, value, lineno: int) -> bool:
        if not _is_method_call(value, "rename"):
            return False
        kwargs = {kw.arg: kw.value for kw in value.keywords}
        cols_node = kwargs.get("columns")
        if cols_node is None and value.args:
            return False
        if cols_node is None:
            return False
        if not isinstance(cols_node, ast.Dict):
            return False
        for k, v in zip(cols_node.keys, cols_node.values):
            if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                self._emit(f"rename {k.value} {v.value}")
            else:
                self._warn("Non-literal rename keys/values", lineno)
        return True

    def _try_df_sample(self, value, lineno: int) -> bool:
        if not _is_method_call(value, "sample"):
            return False
        kwargs = {kw.arg: kw.value for kw in value.keywords}
        args = value.args

        n_node = args[0] if args else kwargs.get("n")
        frac_node = kwargs.get("frac")
        seed_node = kwargs.get("random_state") or kwargs.get("seed")

        seed = 12345  # default seed
        if seed_node and isinstance(seed_node, ast.Constant):
            seed = int(seed_node.value)

        if frac_node and isinstance(frac_node, ast.Constant):
            frac = float(frac_node.value)
            self._emit(f"sample {frac} {seed}")
            return True
        if n_node and isinstance(n_node, ast.Constant):
            n = int(n_node.value)
            self._emit(f"sample {n} {seed}")
            return True
        self._warn("df.sample(): could not determine n/frac", lineno)
        return True

    _VIEW_METHODS = frozenset({
        "dropna", "fillna", "sort_values", "sort_index", "query",
        "drop", "filter", "head", "tail", "sample", "rename", "assign", "pipe",
    })

    def _is_df_view_expression(self, value) -> bool:
        """True when value is a filtered/reshaped view of df (not an in-place mutation)."""
        root, steps = decompose(value)
        if not is_df_root(root, self.df_name) or not steps:
            return False
        step = steps[0]
        return (
            isinstance(step, SubscriptStep)
            or (isinstance(step, MethodStep) and step.name in self._VIEW_METHODS)
        )

    # ── merge / join helpers ──────────────────────────────────────────────────

    def _extract_merge_cols(self, node, on_cols: list):
        """
        From the 'other' argument of merge/join, return (dataset_name, col_list_or_None).
        col_list is the non-key columns to transfer; None means unknown (bare name, no selection).
        """
        # df2[['key', 'col1', 'col2']] or df2[['col1', 'col2']]
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            name = node.value.id
            cols = _extract_str_list(node.slice)
            if cols is None:
                s = node.slice
                if isinstance(s, ast.Constant) and isinstance(s.value, str):
                    cols = [s.value]
            if cols is not None:
                non_key = [c for c in cols if c not in on_cols]
                return name, (non_key if non_key else None)
            return name, None
        # df2 (bare name)
        if isinstance(node, ast.Name):
            return node.id, None
        return None, None

    def _emit_merge(self, provider: str, receiver: str, cols, on_cols: list,
                    how: str, lineno: int):
        """Emit use + merge command; handles unknown col list."""
        self._ensure_active(provider)
        how_opt = " outer" if how == "outer" else ""
        on_str  = (" on " + " ".join(on_cols)) if on_cols else ""
        if cols:
            self._emit(f"merge {' '.join(cols)} into {receiver}{on_str}{how_opt}")
        else:
            self._comment(
                f"NOTE: specify which columns of '{provider}' to merge — "
                f"e.g. merge col1 col2 into {receiver}{on_str}"
            )

    def _try_merge(self, value, lineno: int) -> bool:
        """
        df = df.merge(df2, on='key')
        df = pd.merge(df, df2, on='key')

        The provider (df2) must be active and provides variables;
        the receiver (df) is the target dataset that gets the new columns.
        """
        root, steps = decompose(value)
        if not (steps and isinstance(steps[-1], MethodStep) and steps[-1].name == "merge"):
            return False
        merge_step = steps[-1]

        # pd.merge(left, right, ...)
        if isinstance(root, ast.Name) and root.id == "pd":
            if len(merge_step.args) < 2:
                return False
            left_node  = merge_step.args[0]
            right_node = merge_step.args[1]
            on_node    = (merge_step.args[2] if len(merge_step.args) > 2
                          else merge_step.kwargs.get("on"))
            how_node   = merge_step.kwargs.get("how")
            lo_node    = merge_step.kwargs.get("left_on")
            ro_node    = merge_step.kwargs.get("right_on")
        # df.merge(other, ...)
        elif is_df_root(root, self.df_name) and len(steps) == 1:
            if not merge_step.args:
                return False
            left_node  = root
            right_node = merge_step.args[0]
            on_node    = (merge_step.args[1] if len(merge_step.args) > 1
                          else merge_step.kwargs.get("on"))
            how_node   = merge_step.kwargs.get("how")
            lo_node    = merge_step.kwargs.get("left_on")
            ro_node    = merge_step.kwargs.get("right_on")
        else:
            return False

        # left_on / right_on (different key names on each side) — too complex
        if lo_node or ro_node:
            self._warn(
                "merge with left_on/right_on: rename the key column first, "
                "then use a simple on= key",
                lineno,
            )
            self._comment("UNTRANSLATED: merge with different left/right key names")
            return True

        # Join keys
        on_cols: list = []
        if on_node:
            if isinstance(on_node, ast.Constant):
                on_cols = [on_node.value]
            elif isinstance(on_node, (ast.List, ast.Tuple)):
                on_cols = _extract_str_list(on_node) or []

        # how=
        how = "left"
        if how_node and isinstance(how_node, ast.Constant):
            how = how_node.value

        if how == "inner":
            self._warn(
                "merge how='inner': no direct microdata equivalent — "
                "using left merge; add 'drop if sysmiss(col)' to approximate.",
                lineno,
            )
            self._comment("NOTE: inner join approximated — add drop if sysmiss(...) after")

        # how='right' swaps which side provides columns
        if how == "right":
            left_node, right_node = right_node, left_node

        # receiver = left (base dataset), provider = right (supplies new columns)
        if isinstance(left_node, ast.Name):
            receiver_name = left_node.id
        elif isinstance(left_node, ast.Subscript) and isinstance(left_node.value, ast.Name):
            receiver_name = left_node.value.id
        else:
            receiver_name = self.df_name
        provider_name, merge_cols = self._extract_merge_cols(right_node, on_cols)

        if provider_name is None:
            self._warn("merge(): could not determine the right-hand dataset name", lineno)
            return False

        self._known_dfs.add(provider_name)
        self._emit_merge(provider_name, receiver_name, merge_cols, on_cols, how, lineno)
        return True

    def _try_join(self, value, lineno: int) -> bool:
        """
        df.join(df2)               → use df2; merge <cols> into df
        df.join(df2, on='key')     → use df2; merge <cols> into df on key
        df.join(df2, how='outer')  → ... outer
        """
        root, steps = decompose(value)
        if not (is_df_root(root, self.df_name) and steps
                and isinstance(steps[-1], MethodStep)
                and steps[-1].name == "join"):
            return False
        join_step = steps[-1]
        if not join_step.args:
            return False

        other_node = join_step.args[0]
        on_node    = join_step.kwargs.get("on")
        how_node   = join_step.kwargs.get("how")

        on_cols: list = []
        if on_node and isinstance(on_node, ast.Constant):
            on_cols = [on_node.value]

        how = "left"
        if how_node and isinstance(how_node, ast.Constant):
            how = how_node.value

        provider_name, merge_cols = self._extract_merge_cols(other_node, on_cols)
        if provider_name is None:
            return False

        self._known_dfs.add(provider_name)
        self._emit_merge(provider_name, self.df_name, merge_cols, on_cols, how, lineno)
        return True

    # ── df.loc[cond, 'col'] = val ─────────────────────────────────────────────

    def _handle_loc_assign(self, target, value, lineno: int) -> bool:
        if not isinstance(target, ast.Subscript):
            return False
        obj = target.value
        if not (isinstance(obj, ast.Attribute) and obj.attr == "loc"):
            return False
        if not (isinstance(obj.value, ast.Name) and obj.value.id == self.df_name):
            return False

        self._ensure_active(self.df_name)
        s = target.slice
        if not isinstance(s, ast.Tuple) or len(s.elts) != 2:
            return False

        cond_node, col_node = s.elts
        cond = self._mask_to_condition(cond_node)
        col = None
        if isinstance(col_node, ast.Constant) and isinstance(col_node.value, str):
            col = col_node.value
        if cond is None or col is None:
            return False

        val = self._translator.translate(value)
        if val is None:
            return False
        self._emit(f"replace {col} = {val} if {cond}")
        return True

# ── let-binding (scalar variable assignment) ──────────────────────────────

    def _try_define_labels(self, var: str, value, lineno: int) -> bool:
        """var = {k: 'label', ...} → define-labels var k1 "v1" k2 "v2" ..."""
        if not isinstance(value, ast.Dict) or not value.keys:
            return False
        pairs = []
        for k_node, v_node in zip(value.keys, value.values):
            if not isinstance(k_node, ast.Constant):
                return False
            if not (isinstance(v_node, ast.Constant) and isinstance(v_node.value, str)):
                return False
            pairs.append((k_node.value, v_node.value))
        if not pairs:
            return False
        self._known_labels[var] = dict(pairs)
        parts = " ".join(f'{k} "{v}"' for k, v in pairs)
        self._emit(f"define-labels {var} {parts}")
        return True

    def _try_assign_labels(self, col: str, value, lineno: int) -> bool:
        """df['col'] = df['col'].cat.rename_categories({k:v} or label_var) → assign-labels"""
        root, steps = decompose(value)
        if not is_df_root(root, self.df_name):
            return False
        # Pattern: df['col'].cat.rename_categories(arg)
        if not (len(steps) >= 3
                and isinstance(steps[-1], MethodStep)
                and steps[-1].name == "rename_categories"
                and isinstance(steps[-2], AttrStep) and steps[-2].name == "cat"
                and isinstance(steps[-3], SubscriptStep)):
            return False
        args = steps[-1].args
        label_arg = args[0] if args else None
        if label_arg is None:
            return False
        # Case 1: known label variable
        if isinstance(label_arg, ast.Name) and label_arg.id in self._known_labels:
            self._emit(f"assign-labels {col} {label_arg.id}")
            return True
        # Case 2: inline dict with string values → auto define-labels
        if isinstance(label_arg, ast.Dict) and label_arg.keys:
            pairs = []
            for k_node, v_node in zip(label_arg.keys, label_arg.values):
                if not (isinstance(k_node, ast.Constant)
                        and isinstance(v_node, ast.Constant)
                        and isinstance(v_node.value, str)):
                    return False
                pairs.append((k_node.value, v_node.value))
            label_name = self._tmp("labels")
            self._known_labels[label_name] = dict(pairs)
            parts = " ".join(f'{k} "{v}"' for k, v in pairs)
            self._emit(f"define-labels {label_name} {parts}")
            self._emit(f"assign-labels {col} {label_name}")
            return True
        return False

    def _try_let_binding(self, var: str, value, lineno: int) -> bool:
        """var = literal or simple expression  →  let var = expr."""
        if isinstance(value, ast.Constant):
            v = value.value
            if isinstance(v, (int, float)):
                self._emit(f"let {var} = {repr(v)}")
                return True
            if isinstance(v, str):
                self._emit(f"let {var} = '{v}'")
                return True
        # Try translating as a microdata-compatible expression
        # (useful for date_fmt(2022) etc.)
        expr = self._translator.translate(value)
        if expr:
            self._emit(f"let {var} = {expr}")
            return True
        return False

    # ── regression ───────────────────────────────────────────────────────────

    def _handle_regression_assign(self, var: str, fit_chain, lineno: int) -> bool:
        info = _parse_statsmodels_fit(fit_chain)
        if info is None:
            return False

        cmd, formula, cov_type, cluster_var, extra_opts = info

        # ── Difference-in-differences: smf.ols('y ~ a*b + controls', ...) ────
        if cmd == "regress":
            star_m = re.search(r'\b([A-Za-z_]\w*)\s*\*\s*([A-Za-z_]\w*)\b', formula)
            if star_m:
                a, b = star_m.group(1), star_m.group(2)
                dep = formula.split("~")[0].strip()
                rhs = formula.split("~", 1)[1] if "~" in formula else ""
                rhs_c = re.sub(
                    r'\b' + re.escape(a) + r'\s*\*\s*' + re.escape(b) + r'\b', '', rhs)
                rhs_c = re.sub(
                    r'\b(?:' + re.escape(a) + r'|' + re.escape(b) + r')\b', '', rhs_c)
                controls = [v.strip() for v in rhs_c.split("+")
                            if v.strip() and v.strip() not in ("", "0", "1", "-1")]
                ctrl_str = (" " + " ".join(controls)) if controls else ""
                self._emit(f"regress-panel-diff {dep} {a} {b}{ctrl_str}")
                self._models[var] = {
                    "cmd": "regress-panel-diff", "depvar": dep,
                    "predictors": [a, b] + controls,
                }
                return True

        parsed = parse_formula(formula, self.df_name)

        if parsed.warnings:
            for w in parsed.warnings:
                self._warn(w, lineno)

        # Emit pre-commands (generate for interaction/transform terms)
        for pre in parsed.pre_commands:
            self._emit(pre)

        predictors = [t.var_name for t in parsed.terms]
        dep = parsed.depvar
        pred_str = " ".join(predictors)

        opts = []
        if parsed.no_constant:
            opts.append("noconstant")
        if cov_type in ("HC0", "HC1", "HC2", "HC3", "HAC"):
            opts.append("robust")
        elif cov_type == "cluster" and cluster_var:
            opts.append(f"cluster({cluster_var})")
        if extra_opts:
            opts.extend(extra_opts)

        opt_str = ", " + " ".join(opts) if opts else ""
        self._emit(f"{cmd} {dep} {pred_str}{opt_str}")

        # Store for downstream predict()
        self._models[var] = {
            "cmd": cmd,
            "depvar": dep,
            "predictors": predictors,
        }
        return True

    def _handle_panel_regression(self, var: str, node, lineno: int) -> bool:
        """PanelOLS/RandomEffects/BetweenOLS/PooledOLS .from_formula(...).fit()."""
        root, steps = decompose(node)
        cls_name = root.id
        cmd, default_opt = _PANEL_CLASSES[cls_name]

        from_formula_step = steps[0]
        if not from_formula_step.args:
            return False
        formula_node = from_formula_step.args[0]
        if not (isinstance(formula_node, ast.Constant) and isinstance(formula_node.value, str)):
            return False
        formula = formula_node.value

        # Strip EntityEffects / TimeEffects markers from formula
        entity_effects = bool(re.search(r'\bEntityEffects\b', formula))
        time_effects   = bool(re.search(r'\bTimeEffects\b',   formula))
        formula_clean  = re.sub(r'\s*\+\s*EntityEffects\b', '', formula)
        formula_clean  = re.sub(r'\s*\+\s*TimeEffects\b',   '', formula_clean).strip()

        parsed = parse_formula(formula_clean, self.df_name)
        for w in parsed.warnings:
            self._warn(w, lineno)
        for pre in parsed.pre_commands:
            self._emit(pre)

        predictors = [t.var_name for t in parsed.terms]
        dep        = parsed.depvar
        pred_str   = " ".join(predictors)

        opts = [default_opt] if default_opt else []
        if not default_opt and entity_effects:
            opts.append("fe")
        if time_effects:
            opts.append("te")

        fit_step = steps[-1]
        cov_node = fit_step.kwargs.get("cov_type")
        if cov_node and isinstance(cov_node, ast.Constant):
            ct = cov_node.value.lower()
            if "robust" in ct or ct in ("hc0", "hc1", "hc2", "hc3"):
                opts.append("robust")

        opt_str = ", " + " ".join(opts) if opts else ""
        self._emit(f"{cmd} {dep} {pred_str}{opt_str}")
        self._models[var] = {"cmd": cmd, "depvar": dep, "predictors": predictors}
        return True

    def _handle_iv_regression(self, var: str, node, lineno: int) -> bool:
        """IV2SLS/IVLIML/IVGMM .from_formula('y ~ x + [endog ~ instr]', df).fit()."""
        root, steps = decompose(node)
        method_name = _IV_CLASSES[root.id]

        from_formula_step = steps[0]
        if not from_formula_step.args:
            return False
        formula_node = from_formula_step.args[0]
        if not (isinstance(formula_node, ast.Constant) and isinstance(formula_node.value, str)):
            return False
        formula = formula_node.value

        iv_info = _parse_iv_formula(formula)
        if iv_info is None:
            self._comment(
                f"UNTRANSLATED: {root.id}.from_formula — "
                "use 'y ~ x + [endogenous ~ instruments]' syntax"
            )
            return True

        dep        = iv_info["dep"]
        exog       = iv_info["exog"]
        endog      = iv_info["endog"]
        instruments = iv_info["instruments"]

        exog_str  = (" " + " ".join(exog)) if exog else ""
        endog_str = " ".join(endog)
        instr_str = " ".join(instruments)

        self._emit(f"ivregress {method_name} {dep}{exog_str} ({endog_str} = {instr_str})")
        self._models[var] = {"cmd": "ivregress", "depvar": dep, "predictors": exog + endog}
        return True

    def _try_model_predict(self, col: str, value, lineno: int) -> bool:
        root, steps = decompose(value)
        if not (isinstance(root, ast.Name) and root.id in self._models):
            return False
        if not (len(steps) == 1 and isinstance(steps[0], MethodStep)
                and steps[0].name == "predict"):
            return False
        info = self._models[root.id]
        if "cmd" not in info:
            return False
        cmd = info["cmd"]
        dep, preds = info["depvar"], " ".join(info["predictors"])
        self._emit(f"{_predict_command(cmd)} {dep} {preds}, predicted({col})")
        return True

    def _try_model_attr(self, col: str, value, lineno: int) -> bool:
        """df['resid'] = model.resid / model.fittedvalues etc."""
        root, steps = decompose(value)
        if not (isinstance(root, ast.Name) and root.id in self._models):
            return False
        if not (len(steps) == 1 and isinstance(steps[0], AttrStep)):
            return False
        info = self._models[root.id]
        if "cmd" not in info:
            return False
        attr = steps[0].name
        cmd = info["cmd"]
        dep, preds = info["depvar"], " ".join(info["predictors"])
        predict_cmd = _predict_command(cmd)
        if attr in ("resid", "resids", "residuals", "resid_pearson", "resid_deviance"):
            self._emit(f"{predict_cmd} {dep} {preds}, residuals({col})")
            return True
        if attr in ("fittedvalues", "predict", "mu"):
            self._emit(f"{predict_cmd} {dep} {preds}, predicted({col})")
            return True
        return False

    # ── lifelines survival ────────────────────────────────────────────────────

    def _handle_lifelines_fit(self, var: str, value, lineno: int) -> bool:
        """fitter.fit(duration_col=..., event_col=...) → kaplan-meier/cox/weibull."""
        root, steps = decompose(value)
        kind = self._lifelines.get(var)
        if kind is None and isinstance(root, ast.Name):
            kind = self._lifelines.get(root.id)
        if kind is None:
            return False

        fit_step = next((s for s in reversed(steps)
                         if isinstance(s, MethodStep) and s.name == "fit"), None)
        if fit_step is None:
            return False
        args = fit_step.args
        kwargs = fit_step.kwargs

        if kind == "kaplan-meier":
            dur_node = args[0] if args else kwargs.get("durations")
            ev_node = kwargs.get("event_observed") or (args[1] if len(args) > 1 else None)
            dur = _extract_col_name(dur_node, self.df_name, self._translator)
            ev = _extract_col_name(ev_node, self.df_name, self._translator)
            if dur and ev:
                self._emit(f"kaplan-meier {ev} {dur}")
                return True
            if dur:
                self._emit(f"kaplan-meier {dur}")
                return True

        if kind in ("cox", "weibull"):
            dur_col = _kwarg_str(kwargs, "duration_col")
            ev_col = _kwarg_str(kwargs, "event_col")
            formula_str = _kwarg_str(kwargs, "formula")
            predictors = []
            if formula_str:
                pf = parse_formula(f"_y ~ {formula_str}", self.df_name)
                for pre in pf.pre_commands:
                    self._emit(pre)
                predictors = [t.var_name for t in pf.terms]
            if dur_col and ev_col:
                pred_str = " ".join(predictors)
                self._emit(f"{kind} {ev_col} {dur_col}{' ' + pred_str if pred_str else ''}")
                return True

        return False

    # ── expression statements ─────────────────────────────────────────────────

    def _handle_expr_stmt(self, node: ast.Expr):
        value = node.value
        lineno = node.lineno

        if not isinstance(value, ast.Call):
            # Bare dataframe view (e.g. `df`, `df[cond]`, `df[['a','b']]`):
            # microdata does not allow individual-level data to be displayed.
            if self._is_df_display_attempt(value):
                self._emit_privacy_note()
            return  # other bare non-call expressions — skip

        # print(...) — skip
        if isinstance(value.func, ast.Name) and value.func.id == "print":
            return

        # use_dataset('name') → use name (explicit dataset switch hint)
        if isinstance(value.func, ast.Name) and value.func.id == "use_dataset":
            if value.args and isinstance(value.args[0], ast.Constant):
                name = str(value.args[0].value)
                self._ensure_active(name)
                self._known_dfs.add(name)
            return

        # df.groupby(...)[col].transform(stat) as standalone display expression.
        # In Python/Jupyter this shows a per-row Series without modifying df.
        # Use tabulate for stats it can express; clone+collapse+delete for the rest.
        info = extract_groupby_transform_info(value, self.df_name, self._translator)
        if info is not None:
            stat    = info["stat"]
            col     = info["src_col"]
            by_str  = info["by_str"]
            micro_stat = _AGG_FUNC_STAT.get(stat)
            if micro_stat == "__freq__":
                self._emit(f"tabulate {by_str}")
            elif stat in _AGG_FUNC_STAT:
                stat_str = f" {micro_stat}" if micro_stat else ""
                self._emit(f"tabulate {by_str}, summarize({col}){stat_str}")
            else:
                # No tabulate equivalent — clone, collapse, restore, delete
                self._groupby_display_clone(
                    [f"collapse ({stat}) {col} -> {col}, by({by_str})"]
                )
            return

        # Pure patterns: col stats, histograms, describe, correlate, crosstab,
        # value_counts, normaltest, matplotlib, df.plot, etc.
        expr_lines = REGISTRY.match_expr(value, self._ctx())
        if expr_lines is not None:
            for l in expr_lines:
                self._emit(l)
            return

        # df.groupby(...).agg(...) with stats that have no microdata display equivalent.
        # There is no way to show this result in microdata — emit a guidance comment.
        lines = try_groupby_collapse(value, self.df_name, self._translator)
        if lines is not None:
            self._comment(
                "UNTRANSLATED: standalone grouped aggregation with no display equivalent. "
                "Assign to a variable to keep the result: "
                "summary = df.groupby(...).agg(...)"
            )
            self._warn(
                "Standalone grouped aggregation cannot be displayed in microdata",
                lineno,
            )
            return

        # model.summary(), result.summary() — skip (microdata auto-displays)
        if _is_method_call(value, "summary"):
            return
        if _is_method_call(value, "plot_survival_function"):
            return
        # Any object's .show() or .savefig() not caught by the registry
        if _is_method_call(value, "show"):
            return
        if _is_method_call(value, "savefig"):
            return

        # model.conf_int() → ci depvar predictors
        # model.params.plot() → coefplot
        _cr, _cs = decompose(value)
        if isinstance(_cr, ast.Name) and _cr.id in self._models:
            _mi = self._models[_cr.id]
            if "depvar" in _mi:
                if _is_method_call(value, "conf_int"):
                    all_vars = [_mi["depvar"]] + _mi.get("predictors", [])
                    self._emit("ci " + " ".join(all_vars))
                    return
                if ("cmd" in _mi and _cs
                        and isinstance(_cs[-1], MethodStep) and _cs[-1].name == "plot"):
                    self._emit("coefplot")
                    return

        # px.xxx(...) — impure: has warnings for approximate/missing commands
        if self._try_plotly_express(value, lineno):
            return

        # smf.ols(...).fit() as standalone (result discarded)
        if _is_statsmodels_fit(value):
            tmp = self._tmp("model")
            self._handle_regression_assign(tmp, value, lineno)
            return

        # PanelOLS.from_formula(...).fit() as standalone
        if _is_panel_fit(value):
            tmp = self._tmp("panel")
            self._handle_panel_regression(tmp, value, lineno)
            return

        # IV2SLS.from_formula(...).fit() as standalone
        if _is_iv_fit(value):
            tmp = self._tmp("iv")
            self._handle_iv_regression(tmp, value, lineno)
            return

        # lifelines fitter.fit(...)
        if _is_lifelines_fit(value, self._lifelines):
            self._handle_lifelines_fit("_anon", value, lineno)
            return

        # to_microdata(var) or to_microdata(var, 'dataset_name')
        if self._try_to_microdata(value, lineno):
            return

        # df.head(), df.tail(), df.sample() etc. — display of individual rows not allowed
        if self._is_df_display_attempt(value):
            self._emit_privacy_note()
            return

        self._untranslated(node)

    def _try_to_microdata(self, node, lineno: int) -> bool:
        """
        to_microdata(summary_df)               → clone-dataset summary_df + collapse
        to_microdata(summary_df, 'my_dataset') → clone-dataset my_dataset + collapse

        Collapses the pending DataFrame (created by groupby.agg) into a new microdata
        dataset.  The original dataset remains active — switch back with 'use <name>'
        if needed.

        Rule: always call to_microdata() immediately after the groupby.agg() assignment.
        """
        if not isinstance(node, ast.Call):
            return False
        if not (isinstance(node.func, ast.Name) and node.func.id == "to_microdata"):
            return False
        if not node.args:
            return False

        var_node = node.args[0]
        if not isinstance(var_node, ast.Name):
            return False
        var = var_node.id

        # Dataset name: second positional arg or keyword 'name=', default = var name
        name = var
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            name = str(node.args[1].value)
        else:
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    name = str(kw.value.value)

        if var in self._pending_collapses:
            lines = self._pending_collapses.pop(var)
            self._emit(f"clone-dataset {name}")
            for ln in lines:
                self._emit(ln)
            # Switch back to original dataset after the clone
            if self._dataset_name:
                self._emit(f"use {self._dataset_name}")
            else:
                self._comment(
                    "NOTE: active dataset is now '{name}' — "
                    "add 'use <original_dataset_name>' to switch back if needed"
                )
            return True

        # var is not a pending collapse — emit a comment and continue
        self._warn(
            f"to_microdata({var}): '{var}' is not a recognised groupby summary — "
            "ensure it comes from df.groupby(...).agg(...).reset_index()",
            lineno,
        )
        return True

    def _try_plotly_express(self, value, lineno: int) -> bool:
        root, steps = decompose(value)
        if not (isinstance(root, ast.Name) and root.id == "px"):
            return False
        if not (len(steps) == 1 and isinstance(steps[0], MethodStep)):
            return False
        step = steps[0]
        method = step.name
        if method not in _PX_COMMANDS:
            return False

        micro_cmd = _PX_COMMANDS[method]
        if micro_cmd is None:
            self._warn(f"px.{method}(): no microdata equivalent", lineno)
            self._comment(f"UNTRANSLATED: px.{method}()")
            return True

        if method in ("scatter", "density_heatmap"):
            self._warn(f"px.{method}(): translated to hexbin (approximate)", lineno)
        if method == "violin":
            self._warn("px.violin(): translated to boxplot (approximate)", lineno)

        kw = step.kwargs
        x_col     = _kwarg_str(kw, "x")
        y_col     = _kwarg_str(kw, "y")
        color_col = _kwarg_str(kw, "color")
        nbins     = _kwarg_str(kw, "nbins")

        if method == "histogram":
            col = x_col or y_col
            opts = ([f"by({color_col})"] if color_col else []) + ([f"bin({nbins})"] if nbins else [])
            opt_str = ", " + " ".join(opts) if opts else ""
            self._emit(f"histogram {col}{opt_str}" if col else "// histogram: missing x")

        elif method in ("box", "violin"):
            var = y_col or x_col
            opts = ([f"over({x_col})"] if x_col and x_col != var else []) + \
                   ([f"by({color_col})"] if color_col else [])
            opt_str = ", " + " ".join(opts) if opts else ""
            self._emit(f"boxplot {var}{opt_str}" if var else "// boxplot: missing y")

        elif method == "bar":
            var = y_col
            opts = ([f"over({x_col})"] if x_col else []) + ([f"by({color_col})"] if color_col else [])
            opt_str = ", " + " ".join(opts) if opts else ""
            self._emit(f"barchart (mean) {var}{opt_str}" if var else "// barchart: missing y")

        elif method == "pie":
            names_col = _kwarg_str(kw, "names")
            self._emit(f"piechart {names_col}" if names_col
                       else "// UNTRANSLATED: px.pie() — no 'names' argument")

        elif method in ("scatter", "density_heatmap"):
            if x_col and y_col:
                self._emit(f"hexbin {x_col} {y_col}")
            else:
                self._comment("UNTRANSLATED: px.scatter() — need x and y")

        elif method == "sankey":
            source_col = _kwarg_str(kw, "source")
            target_col = _kwarg_str(kw, "target")
            value_col  = _kwarg_str(kw, "value")
            if source_col and target_col and value_col:
                self._emit(f"sankey {source_col} {target_col} {value_col}")
            elif source_col and target_col:
                self._emit(f"sankey {source_col} {target_col}")
            else:
                self._comment("UNTRANSLATED: px.sankey() — need source, target, value arguments")

        return True

    # ── for loops ─────────────────────────────────────────────────────────────

    def _handle_for(self, node: ast.For):
        var = node.target.id if isinstance(node.target, ast.Name) else None
        if var is None:
            self._untranslated(node)
            return

        extracted = _extract_for_values(node.iter)
        if extracted is None:
            self._untranslated(node)
            self._warn("for loop: could not extract iteration values (must be range() or literal list)", node.lineno)
            return
        values, is_range = extracted

        # microdata for syntax: range() sources use compact 'a : b', literal lists use space-separated
        if is_range and all(isinstance(v, int) for v in values) and len(values) >= 2:
            sorted_vals = sorted(values)
            if sorted_vals == list(range(sorted_vals[0], sorted_vals[-1] + 1)):
                self._emit(f"for {var} in {sorted_vals[0]} : {sorted_vals[-1]}")
            else:
                self._emit(f"for {var} in {' '.join(str(v) for v in values)}")
        else:
            self._emit(f"for {var} in {' '.join(str(v) for v in values)}")

        for child in node.body:
            self._visit(child)

        self._emit("end")

    # ── if statements ─────────────────────────────────────────────────────────

    def _handle_if(self, node: ast.If):
        """Simple if/else at module level — limited support."""
        # Just emit the body with a warning
        self._comment("UNTRANSLATED: if statement (translate body manually or use 'keep if')")
        for child in node.body:
            self._visit(child)


# ── module-level helpers ──────────────────────────────────────────────────────

def _is_method_call(node, method: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
    )


def _is_statsmodels_model(node) -> bool:
    """smf.ols(...) — model construction, not yet .fit()."""
    root, steps = decompose(node)
    return (
        isinstance(root, ast.Name) and root.id in ("smf", "sm")
        and len(steps) == 1
        and isinstance(steps[0], MethodStep)
        and steps[0].name in _SMF_CMD
    )


def _is_statsmodels_fit(node) -> bool:
    """smf.ols(...).fit(...) — the full chain."""
    root, steps = decompose(node)
    return (
        isinstance(root, ast.Name) and root.id in ("smf", "sm")
        and len(steps) >= 2
        and isinstance(steps[0], MethodStep) and steps[0].name in _SMF_CMD
        and isinstance(steps[-1], MethodStep) and steps[-1].name == "fit"
    )


def _is_panel_fit(node) -> bool:
    """PanelOLS/RandomEffects/BetweenOLS/PooledOLS.from_formula(...).fit()."""
    root, steps = decompose(node)
    return (
        isinstance(root, ast.Name) and root.id in _PANEL_CLASSES
        and len(steps) >= 2
        and isinstance(steps[0], MethodStep) and steps[0].name == "from_formula"
        and isinstance(steps[-1], MethodStep) and steps[-1].name == "fit"
    )


def _is_iv_fit(node) -> bool:
    """IV2SLS/IVLIML/IVGMM.from_formula(...).fit()."""
    root, steps = decompose(node)
    return (
        isinstance(root, ast.Name) and root.id in _IV_CLASSES
        and len(steps) >= 2
        and isinstance(steps[0], MethodStep) and steps[0].name == "from_formula"
        and isinstance(steps[-1], MethodStep) and steps[-1].name == "fit"
    )


def _parse_iv_formula(formula: str) -> Optional[dict]:
    """
    Parse IV formula like 'y ~ x1 + x2 + [endog1 ~ z1 + z2]'.
    Returns {'dep': str, 'exog': list, 'endog': list, 'instruments': list} or None.
    """
    m = re.search(r'\[([^\]~]+)~([^\]]+)\]', formula)
    if not m:
        return None
    endog       = [v.strip() for v in m.group(1).split('+') if v.strip()]
    instruments = [v.strip() for v in m.group(2).split('+') if v.strip()]
    formula_clean = formula.replace(m.group(0), '').strip().rstrip('+').strip()
    if '~' not in formula_clean:
        return None
    dep_part, exog_part = formula_clean.split('~', 1)
    dep  = dep_part.strip()
    exog = [v.strip() for v in exog_part.split('+')
            if v.strip() and v.strip() not in ('0', '1', '-1')]
    return {'dep': dep, 'exog': exog, 'endog': endog, 'instruments': instruments}


def _parse_statsmodels_fit(node) -> Optional[tuple]:
    """
    Extract (cmd, formula, cov_type, cluster_var, extra_opts) from:
      smf.ols('formula', data=df).fit(cov_type='HC3')

    Also accepts the two-step form where node is an already-reconstructed
    dict {'smf_step': MethodStep, 'fit_step': MethodStep}.
    """
    # Accept a pre-parsed dict from the two-step assignment path
    if isinstance(node, dict):
        smf_step = node["smf_step"]
        fit_step = node["fit_step"]
    else:
        root, steps = decompose(node)
        if not (isinstance(root, ast.Name) and root.id in ("smf", "sm")):
            return None
        if len(steps) < 2:
            return None
        smf_step = steps[0]
        fit_step = steps[-1]
        if not (isinstance(smf_step, MethodStep) and smf_step.name in _SMF_CMD):
            return None
        if not (isinstance(fit_step, MethodStep) and fit_step.name == "fit"):
            return None

    cmd = _SMF_CMD.get(smf_step.name)
    if cmd is None:
        return None

    if not smf_step.args:
        return None
    formula_node = smf_step.args[0]
    if not (isinstance(formula_node, ast.Constant) and isinstance(formula_node.value, str)):
        return None
    formula = formula_node.value

    fit_kwargs = fit_step.kwargs
    cov_type = None
    cluster_var = None
    ct_node = fit_kwargs.get("cov_type")
    if ct_node and isinstance(ct_node, ast.Constant):
        cov_type = ct_node.value
    ckwds = fit_kwargs.get("cov_kwds")
    if ckwds and isinstance(ckwds, ast.Dict):
        for k, v in zip(ckwds.keys, ckwds.values):
            if isinstance(k, ast.Constant) and k.value == "groups":
                cluster_var = _is_df_col(v, "df") or (v.id if isinstance(v, ast.Name) else None)

    extra_opts = []
    if smf_step.name == "mixedlm":
        groups_node = smf_step.kwargs.get("groups")
        if groups_node is None and len(smf_step.args) > 2:
            groups_node = smf_step.args[2]
        if groups_node is not None:
            group_col = _is_df_col(groups_node, "df") or (
                groups_node.id if isinstance(groups_node, ast.Name) else None
            )
            if group_col:
                extra_opts.append(f"by({group_col})")

    return cmd, formula, cov_type, cluster_var, extra_opts


def _predict_command(cmd: str) -> str:
    _MAP = {
        "regress": "regress-predict",
        "logit": "logit-predict",
        "probit": "probit-predict",
        "mlogit": "mlogit-predict",
        "poisson": "poisson-predict",
        "negative-binomial": "negative-binomial-predict",
    }
    return _MAP.get(cmd, cmd + "-predict")


def _is_lifelines_constructor(node) -> bool:
    _FITTERS = {"KaplanMeierFitter", "CoxPHFitter", "WeibullAFTFitter", "WeibullFitter"}
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FITTERS
    )


def _lifelines_kind(node) -> Optional[str]:
    _MAP = {
        "KaplanMeierFitter": "kaplan-meier",
        "CoxPHFitter": "cox",
        "WeibullAFTFitter": "weibull",
        "WeibullFitter": "weibull",
    }
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return _MAP.get(node.func.id)
    return None


def _is_lifelines_fit(node, lifelines_vars: dict) -> bool:
    root, steps = decompose(node)
    return (
        isinstance(root, ast.Name) and root.id in lifelines_vars
        and steps and isinstance(steps[-1], MethodStep) and steps[-1].name == "fit"
    )


def _lifelines_kind_from_fit(node, lifelines_vars: dict) -> Optional[str]:
    root, _ = decompose(node)
    if isinstance(root, ast.Name):
        return lifelines_vars.get(root.id)
    return None


def _kwarg_str(kwargs: dict, key: str) -> Optional[str]:
    node = kwargs.get(key)
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_col_name(node, df_name: str, translator: ExprTranslator) -> Optional[str]:
    if node is None:
        return None
    col = _is_df_col(node, df_name)
    if col:
        return col
    return translator.translate(node)


def _extract_str_list(node) -> Optional[list]:
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



def _is_pd_dataframe_call(node) -> bool:
    """True when node is pd.DataFrame(...)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "DataFrame"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pd"
    )


def _clone_units_source(node) -> Optional[str]:
    """Return source dataset name if node is a clone-units pattern, else None.

    Recognised patterns:
      pd.DataFrame(index=SRC.index)  →  source is SRC
      SRC[[]]                         →  source is SRC (empty column list)
    """
    if _is_pd_dataframe_call(node):
        kw = {kw.arg: kw.value for kw in node.keywords}
        index_node = kw.get("index")
        if (index_node is not None
                and isinstance(index_node, ast.Attribute)
                and index_node.attr == "index"
                and isinstance(index_node.value, ast.Name)):
            return index_node.value.id
    if (isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)):
        s = node.slice
        if isinstance(s, (ast.List, ast.Tuple)) and not s.elts:
            return node.value.id
    return None


def _extract_for_values(iter_node) -> Optional[tuple]:
    """range(n) / range(a,b) / range(a,b,c) / [1,2,3] → (values, is_range).
    is_range=True means the source was range() and compact 'a : b' notation is preferred."""
    if isinstance(iter_node, (ast.List, ast.Tuple)):
        result = []
        for elt in iter_node.elts:
            if isinstance(elt, ast.Constant):
                result.append(elt.value)
            else:
                return None
        return result, False
    if isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Name):
        if iter_node.func.id == "range":
            args = [ast.literal_eval(a) for a in iter_node.args]
            if len(args) == 1:
                return list(range(args[0])), True
            if len(args) == 2:
                return list(range(args[0], args[1])), True
            if len(args) == 3:
                return list(range(args[0], args[1], args[2])), True
    return None
