"""Phase 1 correctness bug-fix tests for py2m.

Each test asserts the CORRECT desired behavior for a bug found in the code
review. Theme: every approximation/skip must be LOUD (a warning + an
UNTRANSLATED comment), never silent.
"""
from py2m import transform


def tr(src, **kw):
    return transform(src, **kw).script()


def warns(src, **kw):
    return transform(src, **kw).warnings


# ── Bug 1: range(n) with a non-literal arg must not crash ──────────────────────

class TestRangeNonLiteral:
    def test_range_non_literal_does_not_crash(self):
        # Must not raise; should degrade to UNTRANSLATED + warning.
        r = transform("for i in range(n):\n    df['x'] = df['x'] + 1\n")
        out = r.script()
        assert "UNTRANSLATED" in out
        assert r.warnings  # at least one warning

    def test_range_empty(self):
        # range(0) yields no values — must not emit a bogus 'for' line.
        r = transform("for i in range(0):\n    df['x'] = df['x'] + 1\n")
        out = r.script()
        # No emitted 'for' command line (only the UNTRANSLATED echo of source).
        cmd_lines = [l for l in out.splitlines() if not l.startswith("//")]
        assert not any(l.startswith("for ") for l in cmd_lines)
        assert "UNTRANSLATED" in out or r.warnings

    def test_range_literal_still_works(self):
        # Regression guard: literal range still compiles.
        assert tr("for i in range(1, 4):\n    df['x'] = df['x'] + 1\n") == (
            "for i in 1 : 3\ngenerate x = (x + 1)\nend"
        )


# ── Bug 2: a*b in regression formula = full-factorial, I(x*z) not corrupted ────

class TestFormulaStar:
    def test_ols_star_expands_to_main_plus_interaction(self):
        out = tr(
            "import statsmodels.formula.api as smf\n"
            "m = smf.ols('y ~ age*sex', data=df).fit()\n"
        )
        # age*sex → age + sex + age:sex ; the interaction is a generated term.
        assert "regress-panel-diff" not in out
        assert "regress y" in out
        assert "age" in out and "sex" in out
        # interaction generated as a product
        assert "age * sex" in out or "age*sex" in out

    def test_I_product_not_corrupted(self):
        out = tr(
            "import statsmodels.formula.api as smf\n"
            "m = smf.ols('y ~ I(x*z)', data=df).fit()\n"
        )
        assert "regress-panel-diff" not in out
        assert "I()" not in out  # the old corruption
        assert "x * z" in out  # the product is preserved as a generated term


# ── Bug 3: print(...) arguments are translated, not discarded ───────────────────

class TestPrintArgs:
    def test_print_mean_behaves_like_bare_expr(self):
        printed = tr("print(df['x'].mean())")
        bare = tr("df['x'].mean()")
        assert printed == bare
        assert printed.strip() != ""

    def test_print_string_literal_skipped(self):
        assert tr('print("hello")') == ""


# ── Bug 4: if/else does not emit body unconditionally and keeps the else ───────

class TestIfElse:
    def test_if_body_not_emitted_as_command(self):
        out = tr("if x:\n    df = df[df['a'] > 0]\nelse:\n    df = df[df['a'] < 0]\n")
        # The 'keep if a > 0' must NOT be emitted as if always true.
        assert "keep if a > 0" not in out
        assert "UNTRANSLATED" in out

    def test_if_warns(self):
        w = warns("if x:\n    df = df[df['a'] > 0]\n")
        assert w


# ── Bug 5: open-ended .str[2:] slice is not silently dropped ────────────────────

class TestStrSliceOpen:
    def test_open_ended_slice_untranslated(self):
        r = transform("df['y'] = df['x'].str[2:]")
        out = r.script()
        assert out != "generate y = x"  # not silently losing the slice
        assert "UNTRANSLATED" in out

    def test_closed_slice_still_works(self):
        assert tr("df['y'] = df['x'].str[2:5]") == "generate y = substr(x, 3, 3)"


# ── Bug 6: lossy stat substitutions are loud (var/first/last) ───────────────────

class TestStatAlias:
    def test_var_not_silently_sd(self):
        r = transform("df = df.groupby('g').agg({'x':'var'}).reset_index()")
        out = r.script()
        # must not silently produce a (sd) collapse
        assert "collapse (sd)" not in out
        assert "UNTRANSLATED" in out or r.warnings

    def test_first_not_silently_min(self):
        r = transform("df = df.groupby('g').agg({'x':'first'}).reset_index()")
        out = r.script()
        assert "collapse (min)" not in out
        assert "UNTRANSLATED" in out or r.warnings

    def test_std_still_works(self):
        assert tr("df = df.groupby('g').agg({'x':'std'}).reset_index()") == (
            "collapse (sd) x -> x, by(g)"
        )


# ── Bug 7: pd.cut with np.inf bins is recognised ────────────────────────────────

class TestPdCutInf:
    def test_inf_upper_bin(self):
        out = tr("df['b'] = pd.cut(df['age'], bins=[0,30,np.inf], labels=[1,2])")
        assert "UNTRANSLATED" not in out
        assert "generate b = ." in out
        # last bin should be open-ended: age > 30 (no upper bound)
        assert "replace b = 2 if age > 30" in out
        assert "inf" not in out

    def test_normal_cut_still_works(self):
        assert tr("df['b'] = pd.cut(df['age'], bins=[0,30,60], labels=[1,2])") == (
            "generate b = .\n"
            "replace b = 1 if age > 0 & age <= 30\n"
            "replace b = 2 if age > 30 & age <= 60"
        )


# ── Bug 8: string literals with embedded quotes are not emitted malformed ──────

class TestStringEscape:
    def test_quote_in_string_not_malformed(self):
        r = transform("df['x'] = \"O'Brien\"")
        out = r.script()
        # The old output was the malformed:  generate x = 'O'Brien'
        assert out != "generate x = 'O'Brien'"

    def test_plain_string_still_works(self):
        assert tr("df['x'] = 'hello'") == "generate x = 'hello'"


# ── Bug 9: df-wide fillna emits explicit UNTRANSLATED, not a fake comment ───────

class TestDfFillna:
    def test_df_fillna_loud(self):
        out = tr("df = df.fillna(0)")
        assert not out.startswith("# replace")
        assert "UNTRANSLATED" in out


# ── Bug 10: in-place secondary-df filter does not self-clone ────────────────────

class TestSelfClone:
    def test_no_self_clone_on_in_place_filter(self):
        out = tr("df2 = df[df['x'] > 0]\ndf2 = df2[df2['y'] > 0]")
        # second statement is an in-place filter on the already-active df2:
        # only one clone-dataset expected (from the first statement).
        assert out.count("clone-dataset") == 1
        assert "clone-dataset df df2" in out
        assert "keep if y > 0" in out
