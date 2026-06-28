"""Golden / characterization tests for py2m (Python -> microdata.no).

Phase 0: lock in the current behavior of the commands that already translate
correctly, so later phases (bug fixes, new coverage) can change the engine with
a safety net. Each test asserts the exact emitted script for one idiom.

Run:  python -m pytest py2m/tests/   (from the repo root)
  or: python -m pytest tests/        (from the py2m/ directory)
"""
from py2m import transform


def tr(src, **kw):
    """Translate Python source and return the emitted microdata script."""
    return transform(src, **kw).script()


def warns(src, **kw):
    return transform(src, **kw).warnings


# ---------------------------------------------------------------------------
# Variable manipulation
# ---------------------------------------------------------------------------

class TestGenerateReplace:
    def test_generate_arithmetic(self):
        assert tr("df['x'] = df['a'] + 1") == "generate x = (a + 1)"

    def test_generate_np_log(self):
        assert tr("df['log_x'] = np.log(df['x'])") == "generate log_x = ln(x)"

    def test_replace_loc_assignment(self):
        assert tr("df.loc[df['a'] > 5, 'x'] = 1") == "replace x = 1 if a > 5"

    def test_np_where_two_branches(self):
        assert tr("df['x'] = np.where(df['a'] > 5, 1, 0)") == \
            "generate x = 0\nreplace x = 1 if a > 5"

    def test_fillna_scalar(self):
        assert tr("df['x'] = df['income'].fillna(0)") == \
            "generate x = income\nreplace x = 0 if sysmiss(x)"


# ---------------------------------------------------------------------------
# Row selection / columns
# ---------------------------------------------------------------------------

class TestRowsAndColumns:
    def test_keep_if_boolean_mask(self):
        assert tr("df = df[df['age'] > 18]") == "keep if age > 18"

    def test_keep_columns(self):
        assert tr("df = df[['a','b']]") == "keep a b"

    def test_drop_columns(self):
        assert tr("df = df.drop(columns=['a'])") == "drop a"

    def test_query_to_keep_if(self):
        assert tr("df = df.query('age > 18')") == "keep if age > 18"

    def test_dropna_subset_to_drop_if(self):
        assert tr("df = df.dropna(subset=['income'])") == "drop if sysmiss(income)"

    def test_rename_columns(self):
        assert tr("df = df.rename(columns={'a':'b'})") == "rename a b"

    def test_destring(self):
        assert tr("df['x'] = pd.to_numeric(df['x'])") == "destring x"

    def test_astype_str_new_column_refs_source(self):
        # df['c'] = df['a'].astype(str) must read the SOURCE column 'a',
        # not the (not-yet-existing) target column 'c'.
        assert tr("df['c'] = df['a'].astype(str)") == "generate c = string(a)"

    def test_astype_str_quoted_new_column_refs_source(self):
        assert tr("df['c'] = df['a'].astype('str')") == "generate c = string(a)"

    def test_astype_str_same_column(self):
        # In-place string cast still works.
        assert tr("df['a'] = df['a'].astype(str)") == "generate a = string(a)"


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class TestAggregation:
    def test_groupby_transform_to_aggregate(self):
        assert tr("df['m'] = df.groupby('g')['x'].transform('mean')") == \
            "aggregate (mean) x -> m, by(g)"

    def test_groupby_agg_to_collapse(self):
        assert tr("summary = df.groupby('g').agg(m=('x','mean')).reset_index()") == \
            "clone-dataset df summary\nuse summary\ncollapse (mean) x -> m, by(g)"


# ---------------------------------------------------------------------------
# Tables / descriptive / sampling
# ---------------------------------------------------------------------------

class TestTablesAndStats:
    def test_value_counts_to_tabulate(self):
        assert tr("df['x'].value_counts()") == "tabulate x"

    def test_crosstab_to_tabulate(self):
        assert tr("pd.crosstab(df['a'], df['b'])") == "tabulate a b"

    def test_describe_to_summarize(self):
        assert tr("df['x'].describe()") == "summarize x"

    def test_corr_to_correlate(self):
        assert tr("df[['a','b']].corr()") == "correlate a b"

    def test_sample_with_seed(self):
        assert tr("df = df.sample(n=1000, random_state=42)") == "sample 1000 42"


# ---------------------------------------------------------------------------
# Regression + predict
# ---------------------------------------------------------------------------

class TestRegression:
    def test_ols_to_regress(self):
        assert tr("model = smf.ols('y ~ x + z', data=df).fit()") == "regress y x z"

    def test_logit(self):
        assert tr("model = smf.logit('y ~ x', data=df).fit()") == "logit y x"

    def test_predict_and_resid_with_model_context(self):
        src = ("model = smf.ols('y ~ x', data=df).fit()\n"
               "df['predicted'] = model.predict()\n"
               "df['residuals'] = model.resid")
        assert tr(src) == (
            "regress y x\n"
            "regress-predict y x, predicted(predicted)\n"
            "regress-predict y x, residuals(residuals)"
        )


# ---------------------------------------------------------------------------
# Expression-level function mapping (inside generate)
# ---------------------------------------------------------------------------

class TestExpressionFunctions:
    def test_np_sqrt(self):
        assert tr("df['x'] = np.sqrt(df['a'])") == "generate x = sqrt(a)"

    def test_abs_method(self):
        assert tr("df['x'] = df['a'].abs()") == "generate x = abs(a)"

    def test_str_len(self):
        assert tr("df['x'] = df['name'].str.len()") == "generate x = length(name)"

    def test_str_upper(self):
        assert tr("df['x'] = df['name'].str.upper()") == "generate x = upper(name)"

    def test_isin_to_inlist(self):
        assert tr("df['x'] = df['kommune'].isin([301, 1103])") == \
            "generate x = inlist(kommune, 301, 1103)"

    def test_between_to_inrange(self):
        assert tr("df['x'] = df['age'].between(18, 67)") == \
            "generate x = inrange(age, 18, 67)"

    def test_isna_to_sysmiss(self):
        assert tr("df['x'] = df['income'].isna()") == "generate x = sysmiss(income)"

    def test_dt_year(self):
        assert tr("df['x'] = df['d'].dt.year") == "generate x = year(d)"

    def test_rowwise_max(self):
        assert tr("df['x'] = df[['a','b','c']].max(axis=1)") == \
            "generate x = rowmax(a, b, c)"

    def test_round_with_digits(self):
        assert tr("df['x'] = df['a'].round(2)") == "generate x = round(a, 2)"


# ---------------------------------------------------------------------------
# Clean translations should not emit warnings (guards against silent noise)
# ---------------------------------------------------------------------------

class TestNoSpuriousWarnings:
    def test_simple_generate_has_no_warnings(self):
        assert warns("df['x'] = df['a'] + 1") == []

    def test_groupby_collapse_has_no_warnings(self):
        assert warns("summary = df.groupby('g').agg(m=('x','mean')).reset_index()") == []
