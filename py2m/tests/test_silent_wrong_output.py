"""Regression tests for py2m (Python -> microdata.no) silent-wrong-output bugs
found in the 2026-07-07 review (docs/REVIEW_2026-07-07.md, "Translators"
section). Each case is a verified repro: before the fix the translator either
emitted M code that computes something DIFFERENT from the Python source, or
silently dropped part of the source. The guiding principle: when a construct
can't be translated faithfully, degrade loudly (an UNTRANSLATED/NOTE comment)
rather than emit something that looks plausible but is wrong.
"""
from py2m import transform


def tr(src, **kw):
    """Translate Python source and return the emitted microdata script."""
    return transform(src, **kw).script()


def warns(src, **kw):
    return transform(src, **kw).warnings


# ---------------------------------------------------------------------------
# 1. commands.py:236 — .astype(int/float) assignment discarding the source
# ---------------------------------------------------------------------------

class TestAstypeDiscardsSourceExpression:
    def test_comparison_cast_to_int_translates_the_condition(self):
        out = tr("df['pos'] = (df['x'] > 0).astype(int)")
        assert out == "generate pos = x > 0"

    def test_comparison_cast_to_float_translates_the_condition(self):
        out = tr("df['pos'] = (df['x'] > 0).astype(float)")
        assert out == "generate pos = x > 0"

    def test_boolop_comparison_cast_to_int_translates_the_condition(self):
        out = tr("df['flag'] = ((df['x'] > 0) & (df['y'] < 5)).astype(int)")
        assert "generate flag = (x > 0) & (y < 5)" == out

    def test_plain_column_cast_still_destrings_in_place(self):
        # Not a derived expression -- an actual dtype conversion of an
        # existing column. Must keep working exactly as before.
        assert tr("df['x'] = df['x'].astype(int)") == "destring x"

    def test_arithmetic_expression_cast_to_int_degrades_loudly(self):
        # Truncation semantics of .astype(int) on a non-boolean expression
        # can't be reproduced by a plain `generate` -- must not silently
        # emit a value that differs from pandas' truncation.
        out = tr("df['z'] = (df['x'] / df['y']).astype(int)")
        assert out.startswith("// UNTRANSLATED")
        assert "z" in out


# ---------------------------------------------------------------------------
# 2. expander.py:673,757 — filter before .groupby() dropped
# ---------------------------------------------------------------------------

class TestGroupbyFilterPrefixNotDropped:
    def test_transform_with_filter_emits_keep_if(self):
        out = tr("df['m'] = df[df['x'] > 0].groupby('g')['y'].transform('mean')")
        lines = out.splitlines()
        assert any(l.startswith("keep if x > 0") for l in lines)
        assert "aggregate (mean) y -> m, by(g)" in lines

    def test_transform_without_filter_is_unaffected(self):
        out = tr("df['m'] = df.groupby('g')['y'].transform('mean')")
        assert out == "aggregate (mean) y -> m, by(g)"

    def test_collapse_with_filter_emits_keep_if(self):
        out = tr("summary = df[df['x'] > 0].groupby('g').agg(m=('y','mean')).reset_index()")
        assert "keep if x > 0" in out
        assert "collapse (mean) y -> m, by(g)" in out


# ---------------------------------------------------------------------------
# 3. expr.py:238/267 — comparisons in arithmetic losing parens
# ---------------------------------------------------------------------------

class TestComparisonParensInArithmetic:
    def test_comparisons_multiplied_and_added_keep_precedence(self):
        out = tr("df['z'] = (df['a']==1)*2 + (df['b']==2)*3")
        # Must NOT read as "a == (1*2) + ..." -- each comparison has to stay
        # a single, parenthesised unit.
        assert "a == 1 * 2" not in out
        assert "(a == 1)" in out and "(b == 2)" in out

    def test_top_level_conditions_stay_unparenthesised(self):
        # Regression guard: the fix must not add parens to the common case
        # (keep if / replace if), only to comparisons nested in arithmetic.
        assert tr("df = df[df['age'] > 18]") == "keep if age > 18"


# ---------------------------------------------------------------------------
# 4. expander.py:306 — pd.cut(labels=False) 1-based vs pandas 0-based
# ---------------------------------------------------------------------------

class TestPdCutLabelsFalseIsZeroBased:
    def test_labels_false_emits_zero_based_codes(self):
        out = tr("df['b'] = pd.cut(df['age'], bins=[0, 30, 60], labels=False)")
        assert "replace b = 0 if age > 0 & age <= 30" in out
        assert "replace b = 1 if age > 30 & age <= 60" in out
        assert "= 2 if" not in out

    def test_no_labels_arg_is_unaffected_one_based(self):
        # Not the bug being fixed here -- just locking in current behaviour.
        out = tr("df['b'] = pd.cut(df['age'], bins=[0, 30, 60])")
        assert "replace b = 1 if age > 0 & age <= 30" in out
        assert "replace b = 2 if age > 30 & age <= 60" in out


# ---------------------------------------------------------------------------
# 5. transformer.py:1004 — inner-merge-as-left-join, positional how misread
# ---------------------------------------------------------------------------

class TestMergeHowAndOnParsing:
    def test_default_merge_warns_inner_approximated(self):
        # pandas' own default how= is 'inner', not 'left'.
        out = tr("df = df.merge(df2, on='key')")
        assert "NOTE: inner join approximated" in out
        w = warns("df = df.merge(df2, on='key')")
        assert any("inner" in m for m in w)

    def test_explicit_left_how_no_inner_caveat(self):
        out = tr("df = df.merge(df2, on='key', how='left')")
        assert "NOTE: inner join approximated" not in out

    def test_positional_how_on_df_merge_is_read_correctly(self):
        # DataFrame.merge(right, how=, on=, ...): 'left' is `how`, not `on`.
        out = tr("df = df.merge(df2[['key', 'wage']], 'left', 'key')")
        assert "merge wage into df on key" in out
        assert "NOTE: inner join approximated" not in out

    def test_positional_how_on_pd_merge_is_read_correctly(self):
        # pandas.merge(left, right, how=, on=, ...): 'left' is `how`, not `on`.
        out = tr("df = pd.merge(df, df2[['key', 'wage']], 'left', 'key')")
        assert "merge wage into df on key" in out
        assert "NOTE: inner join approximated" not in out

    def test_positional_how_inner_still_warns(self):
        out = tr("df = pd.merge(df, df2[['key', 'wage']], 'inner', 'key')")
        assert "NOTE: inner join approximated" in out
        assert "merge wage into df on key" in out


# ---------------------------------------------------------------------------
# 6a. same-column .map({}) keeps unmapped values, pandas gives NaN
# ---------------------------------------------------------------------------

class TestSameColumnMapCaveat:
    def test_same_column_map_flags_unmapped_value_difference(self):
        out = tr("df['a'] = df['a'].map({1: 'x', 2: 'y'})")
        assert "recode a (1='x') (2='y')" in out
        assert "NOTE" in out and "missing" in out


# ---------------------------------------------------------------------------
# 6b. df[cond].head(10) silently dropped the .head()
# ---------------------------------------------------------------------------

class TestFilterThenHeadDegradesLoudly:
    def test_df_reassign_filter_then_head_is_untranslated(self):
        out = tr("df = df[df['x'] > 0].head(10)")
        assert out.startswith("// UNTRANSLATED")
        assert "keep if" not in out

    def test_new_dataset_filter_then_head_is_untranslated(self):
        out = tr("new_df = df[df['x'] > 0].head(10)")
        assert "keep if" not in out

    def test_plain_filter_reassign_is_unaffected(self):
        assert tr("df = df[df['x'] > 0]") == "keep if x > 0"


# ---------------------------------------------------------------------------
# 6c. &/| rewritten inside string literals in .query()
# ---------------------------------------------------------------------------

class TestQueryStringLiteralsNotRewritten:
    def test_ampersand_inside_string_literal_untouched(self):
        out = tr('''df = df.query("name == 'A & B' & age > 3")''')
        assert "A & B" in out
        assert "A and B" not in out

    def test_pipe_inside_double_quoted_string_literal_untouched(self):
        out = tr('''df = df.query('name == "A | B" | age > 3')''')
        assert "A | B" in out
        assert "A or B" not in out
