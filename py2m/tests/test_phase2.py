"""py2m Phase 2 — high-value idiom coverage.

Each idiom below was UNTRANSLATED before Phase 2. TDD: these assert the
desired translation; implement until green. (Outputs verified against the
microdata.no manuals in /tmp/mdoc.txt and /tmp/mfunc.txt.)
"""
from py2m import transform


def tr(src, **kw):
    return transform(src, **kw).script()


def warns(src, **kw):
    return transform(src, **kw).warnings


# ---------------------------------------------------------------------------
# df.assign(...) → one generate per keyword
# ---------------------------------------------------------------------------

class TestAssign:
    def test_single_kwarg(self):
        assert tr("df = df.assign(x = df['a'] + 1)") == "generate x = (a + 1)"

    def test_multiple_kwargs(self):
        assert tr("df = df.assign(x = df['a'] + 1, y = df['b'] * 2)") == \
            "generate x = (a + 1)\ngenerate y = (b * 2)"

    def test_assign_with_function(self):
        assert tr("df = df.assign(l = np.log(df['income']))") == "generate l = ln(income)"


# ---------------------------------------------------------------------------
# Series.where / Series.mask → generate + replace (like np.where)
# ---------------------------------------------------------------------------

class TestWhereMask:
    def test_where_keeps_value_where_true(self):
        # s.where(cond, other): keep s where cond True, else other
        assert tr("df['x'] = df['a'].where(df['a'] > 0, 0)") == \
            "generate x = 0\nreplace x = a if a > 0"

    def test_mask_replaces_where_true(self):
        # s.mask(cond, other): other where cond True, else s
        assert tr("df['x'] = df['a'].mask(df['a'] < 0, 0)") == \
            "generate x = a\nreplace x = 0 if a < 0"


# ---------------------------------------------------------------------------
# Expression-level coverage
# ---------------------------------------------------------------------------

class TestExpressionCoverage:
    def test_str_cat_to_rowconcat(self):
        assert tr("df['full'] = df['first'].str.cat(df['last'])") == \
            "generate full = rowconcat(first, last)"

    def test_str_cat_with_sep(self):
        assert tr("df['full'] = df['first'].str.cat(df['last'], sep=' ')") == \
            "generate full = rowconcat(first, ' ', last)"

    def test_qcut_to_quantile(self):
        assert tr("df['q'] = pd.qcut(df['income'], 4, labels=False)") == \
            "generate q = quantile(income, 4)"

    def test_strftime_iso_to_isoformatdate(self):
        assert tr("df['s'] = df['d'].dt.strftime('%Y-%m-%d')") == \
            "generate s = isoformatdate(d)"

    def test_date_subtraction_days(self):
        # microdata dates are integer days, so d2 - d1 IS the day difference
        assert tr("df['days'] = (df['d2'] - df['d1']).dt.days") == \
            "generate days = (d2 - d1)"


# ---------------------------------------------------------------------------
# Approximations stay loud (non-ISO strftime can't map)
# ---------------------------------------------------------------------------

class TestQueryBooleanOps:
    def test_query_with_ampersand(self):
        # pandas query() & is low-precedence logical AND, unlike Python's &
        assert tr("df = df.query('a > 2 & b < 9')") == "keep if (a > 2) & (b < 9)"

    def test_query_with_pipe(self):
        assert tr("df = df.query('a > 2 | b < 9')") == "keep if (a > 2) | (b < 9)"


class TestCloneDatasetTwoArg:
    def test_collapse_emits_two_arg_clone(self):
        # microdata clone-dataset takes <source> <target>
        out = tr("summary = df.groupby('g').agg(m=('x','mean')).reset_index()")
        assert out.startswith("clone-dataset df summary")


class TestStillLoud:
    def test_non_iso_strftime_is_untranslated(self):
        out = tr("df['s'] = df['d'].dt.strftime('%d.%m.%Y')")
        assert "UNTRANSLATED" in out
