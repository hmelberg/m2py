# Differensialtester mot ekte statsmodels 0.14.6 — kun der det finnes.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
smf = pytest.importorskip('statsmodels.formula.api')
pd = pytest.importorskip('pandas')
import statsmodels_brython as smb

RAW = {
    'y':      [12.9, 13.5, 12.8, 15.6, 17.2, 19.2, 12.6, 15.3, 14.4, 11.3, 16.1, 18.3],
    'alder':  [34.0, 41.0, 29.0, 52.0, 38.0, 45.0, 31.0, 47.0, 36.0, 27.0, 50.0, 44.0],
    'region': ['N', 'S', 'N', 'S', 'O', 'O', 'N', 'S', 'O', 'N', 'S', 'O'],
}

def _both(formula):
    mine = smb.ols(formula, RAW).fit()
    ref = smf.ols(formula, pd.DataFrame(RAW)).fit()
    return mine, ref

def test_ols_diff_numeric_and_categorical():
    mine, ref = _both('y ~ alder + region')
    for name in ref.params.index:
        assert mine.params[name] == pytest.approx(ref.params[name], rel=1e-6)
        assert mine.bse[name] == pytest.approx(ref.bse[name], rel=1e-6)
        assert mine.tvalues[name] == pytest.approx(ref.tvalues[name], rel=1e-6)
        assert mine.pvalues[name] == pytest.approx(ref.pvalues[name], rel=1e-6)
    assert mine.rsquared == pytest.approx(ref.rsquared, rel=1e-8)
    assert mine.rsquared_adj == pytest.approx(ref.rsquared_adj, rel=1e-8)
    assert mine.fvalue == pytest.approx(ref.fvalue, rel=1e-6)
    assert mine.f_pvalue == pytest.approx(ref.f_pvalue, rel=1e-6)
    assert mine.nobs == ref.nobs
    assert mine.df_resid == ref.df_resid and mine.df_model == ref.df_model

def test_ols_diff_c_notation_and_no_intercept():
    mine, ref = _both('y ~ C(region) + alder')
    for name in ref.params.index:
        assert mine.params[name] == pytest.approx(ref.params[name], rel=1e-6)
    mine0, ref0 = _both('y ~ alder - 1')
    assert mine0.params['alder'] == pytest.approx(ref0.params['alder'], rel=1e-6)
    assert mine0.bse['alder'] == pytest.approx(ref0.bse['alder'], rel=1e-6)

def test_predict_and_conf_int_diff():
    mine = smb.ols('y ~ alder + region', RAW).fit()
    ref = smf.ols('y ~ alder + region', pd.DataFrame(RAW)).fit()
    nydata = {'alder': [30.0, 48.0], 'region': ['N', 'S']}
    mp = mine.predict(nydata)
    rp = ref.predict(pd.DataFrame(nydata))
    for a, b in zip(mp, list(rp)):
        assert a == pytest.approx(float(b), rel=1e-6)
    rci = ref.conf_int()
    mci = mine.conf_int()
    for name in ref.params.index:
        assert mci[name][0] == pytest.approx(float(rci.loc[name][0]), rel=1e-6)
        assert mci[name][1] == pytest.approx(float(rci.loc[name][1]), rel=1e-6)

LOGIT_RAW = {
    'kjopt': [0.0, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0,
              1.0, 1.0, 0.0, 0.0],
    'pris':  [9.5, 5.7, 3.2, 6.1, 7.8, 2.5, 3.9, 4.6, 4.4, 9.0, 2.8, 3.6,
              6.9, 3.5, 7.2, 4.8],
    'by':    ['O', 'B', 'O', 'B', 'O', 'B', 'O', 'B', 'O', 'B', 'O', 'B',
              'O', 'B', 'O', 'B'],
}

def test_logit_diff():
    mine = smb.logit('kjopt ~ pris + by', LOGIT_RAW).fit()
    ref = smf.logit('kjopt ~ pris + by', pd.DataFrame(LOGIT_RAW)).fit(disp=0)
    for name in ref.params.index:
        assert mine.params[name] == pytest.approx(ref.params[name], rel=1e-5)
        assert mine.bse[name] == pytest.approx(ref.bse[name], rel=1e-5)
        assert mine.pvalues[name] == pytest.approx(ref.pvalues[name], rel=1e-5)
    assert mine.llf == pytest.approx(ref.llf, rel=1e-8)
    assert mine.prsquared == pytest.approx(ref.prsquared, rel=1e-6)
    mp = mine.predict({'pris': [4.0, 8.0], 'by': ['O', 'B']})
    rp = ref.predict(pd.DataFrame({'pris': [4.0, 8.0], 'by': ['O', 'B']}))
    for a, b in zip(mp, list(rp)):
        assert a == pytest.approx(float(b), rel=1e-5)

def test_ols_diff_no_intercept_categorical_rsquared():
    # full-rang-dummyer spenner konstanten -> statsmodels bruker sentrert TSS
    for formula in ('y ~ region - 1', 'y ~ region + alder - 1'):
        mine = smb.ols(formula, RAW).fit()
        ref = smf.ols(formula, pd.DataFrame(RAW)).fit()
        assert mine.rsquared == pytest.approx(ref.rsquared, rel=1e-8)
        assert mine.rsquared_adj == pytest.approx(ref.rsquared_adj, rel=1e-8)
        assert mine.fvalue == pytest.approx(ref.fvalue, rel=1e-6)
        assert mine.f_pvalue == pytest.approx(ref.f_pvalue, rel=1e-6)
        assert mine.df_model == ref.df_model

def test_missing_drop_diff():
    raw_missing = {'y': [12.9, 13.5, None, 15.6, 17.2, 19.2, None, 15.3, 14.4, 11.3],
                   'alder': [34.0, None, 29.0, 52.0, 38.0, 45.0, 31.0, 47.0, 36.0, 27.0],
                   'region': ['N', 'S', 'N', 'S', 'O', 'O', 'N', 'S', 'O', 'N']}
    mine = smb.ols('y ~ alder + region', raw_missing).fit()
    ref = smf.ols('y ~ alder + region',
                  pd.DataFrame(raw_missing).astype({'y': float, 'alder': float})).fit()
    assert mine.nobs == int(ref.nobs)
    for name in ref.params.index:
        assert mine.params[name] == pytest.approx(ref.params[name], rel=1e-6)
        assert mine.pvalues[name] == pytest.approx(ref.pvalues[name], rel=1e-6)
    assert mine.rsquared == pytest.approx(ref.rsquared, rel=1e-8)
