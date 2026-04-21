"""
Statsmodels formula parser and term expander.

Parses 'y ~ x1 + x2 + x1:x2 + I(x**2) - 1' into structured terms.
For interaction and transform terms, emits 'generate _py2m_<name> = expr'
commands before the regression command.
"""
import re
import ast
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FormulaTerm:
    kind: str         # 'simple' | 'interaction' | 'transform' | 'categorical'
    var_name: str     # predictor name to use in microdata regression command
    generate_expr: Optional[str] = None  # microdata expr for a generate command
    original: str = ""
    warning: Optional[str] = None


@dataclass
class ParsedFormula:
    depvar: str
    terms: list = field(default_factory=list)
    no_constant: bool = False
    warnings: list = field(default_factory=list)
    # pre-commands to emit before the regression (generate for derived terms)
    pre_commands: list = field(default_factory=list)


def parse_formula(formula: str, df_name: str = "df") -> ParsedFormula:
    """Parse a statsmodels formula string into a ParsedFormula."""
    formula = formula.strip()
    if "~" not in formula:
        return ParsedFormula(depvar=formula, warnings=["No ~ found in formula"])

    lhs, rhs = formula.split("~", 1)
    depvar = lhs.strip()
    rhs = rhs.strip()

    no_constant = False
    # -1 at end = no intercept
    if re.search(r"\s*-\s*1\s*$", rhs):
        no_constant = True
        rhs = re.sub(r"\s*-\s*1\s*$", "", rhs).strip()
    # + 0 = no intercept
    if re.search(r"\+\s*0\b", rhs):
        no_constant = True
        rhs = re.sub(r"\+\s*0\b", "", rhs).strip()

    result = ParsedFormula(depvar=depvar, no_constant=no_constant)
    counter = [0]

    # Expand a*b → a + b + a:b
    rhs = _expand_star_terms(rhs)

    raw_terms = _split_top_level(rhs, "+")

    for raw in raw_terms:
        raw = raw.strip()
        if not raw or raw in ("0", "1"):
            continue
        term = _parse_one_term(raw, counter, df_name)
        if term:
            result.terms.append(term)
            if term.warning:
                result.warnings.append(term.warning)
            if term.generate_expr and term.kind != "categorical":
                result.pre_commands.append(
                    f"generate {term.var_name} = {term.generate_expr}"
                )

    return result


def _expand_star_terms(rhs: str) -> str:
    """Replace a*b with a + b + a:b (statsmodels full-factorial expansion)."""
    # Only handle simple var*var (no nested parens)
    def replacer(m):
        a, b = m.group(1).strip(), m.group(2).strip()
        if re.match(r"^\w+$", a) and re.match(r"^\w+$", b):
            return f"{a} + {b} + {a}:{b}"
        return m.group(0)
    return re.sub(r"(\w+)\s*\*\s*(\w+)", replacer, rhs)


def _parse_one_term(term: str, counter: list, df_name: str) -> Optional[FormulaTerm]:
    term = term.strip()
    if not term:
        return None

    # C(var) — categorical: needs runtime category values
    m = re.match(r"^C\((.+)\)$", term)
    if m:
        var = m.group(1).strip()
        return FormulaTerm(
            kind="categorical",
            var_name=var,
            original=term,
            warning=(
                f"C({var}): categorical dummies require known category values at runtime. "
                f"Pre-encode with pd.get_dummies(df, columns=['{var}'], drop_first=True) "
                f"and list the resulting columns explicitly in your formula."
            ),
        )

    # I(expr) — arbitrary transform
    m = re.match(r"^I\((.+)\)$", term)
    if m:
        inner = m.group(1).strip()
        counter[0] += 1
        tmp = f"_py2m_t{counter[0]}"
        expr = _formula_expr_to_microdata(inner, df_name)
        if expr:
            return FormulaTerm(
                kind="transform",
                var_name=tmp,
                generate_expr=expr,
                original=term,
            )
        return FormulaTerm(
            kind="transform",
            var_name=tmp,
            original=term,
            warning=f"I({inner}): could not translate expression to microdata",
        )

    # var1:var2 — interaction
    if ":" in term:
        parts = [p.strip() for p in term.split(":")]
        if all(re.match(r"^\w+$", p) for p in parts):
            tmp = "_py2m_" + "_".join(parts)
            expr = " * ".join(parts)
            return FormulaTerm(
                kind="interaction",
                var_name=tmp,
                generate_expr=expr,
                original=term,
            )
        # Interaction with non-simple terms — warn
        counter[0] += 1
        tmp = f"_py2m_t{counter[0]}"
        return FormulaTerm(
            kind="interaction",
            var_name=tmp,
            original=term,
            warning=f"Interaction '{term}': complex interaction terms not directly supported",
        )

    # np.func(var) or other Python expression (no parens → must be simple or I())
    # If it contains parens, try to translate as arbitrary expr
    if "(" in term or "**" in term or "/" in term:
        counter[0] += 1
        tmp = f"_py2m_t{counter[0]}"
        expr = _formula_expr_to_microdata(term, df_name)
        if expr:
            return FormulaTerm(
                kind="transform",
                var_name=tmp,
                generate_expr=expr,
                original=term,
            )
        return FormulaTerm(
            kind="transform",
            var_name=tmp,
            original=term,
            warning=f"Formula term '{term}': could not translate",
        )

    # Simple variable name
    if re.match(r"^\w+$", term):
        return FormulaTerm(kind="simple", var_name=term, original=term)

    return None


def _formula_expr_to_microdata(expr: str, df_name: str) -> Optional[str]:
    """
    Convert a Python expression string (as found inside I() or interaction)
    to a microdata expression.  Bare names are treated as column references.
    """
    from .expr import ExprTranslator

    # In formula context bare names are columns — subclass to reflect that
    class _FormulaTranslator(ExprTranslator):
        def _t_Name(self, node):
            n = node.id
            if n in ("True", "False"):
                return "1" if n == "True" else "0"
            if n in ("None", "nan", "inf", "NaN"):
                return None
            return n  # always treat as column/binding

    try:
        tree = ast.parse(expr, mode="eval")
        return _FormulaTranslator(df_name=df_name).translate(tree.body)
    except SyntaxError:
        return None


def _split_top_level(s: str, sep: str) -> list:
    """Split string on sep at parenthesis depth 0."""
    parts, depth, buf = [], 0, []
    for c in s:
        if c == "(":
            depth += 1
            buf.append(c)
        elif c == ")":
            depth -= 1
            buf.append(c)
        elif c == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(c)
    if buf:
        parts.append("".join(buf))
    return parts
