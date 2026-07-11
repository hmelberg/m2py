# Differensialtester mot ekte scipy — kjøres kun der scipy finnes (dev-maskin).
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
scipy_stats = pytest.importorskip('scipy.stats')
import scipy_stats_brython as st

XS = (-3.0, -1.5, -0.4, 0.0, 0.7, 1.96, 3.2)
PS = (0.005, 0.05, 0.25, 0.5, 0.8, 0.975, 0.999)

def test_norm_diff():
    for x in XS:
        assert st.norm.pdf(x) == pytest.approx(scipy_stats.norm.pdf(x), abs=1e-9)
        assert st.norm.cdf(x) == pytest.approx(scipy_stats.norm.cdf(x), abs=1e-9)
        assert st.norm.sf(x) == pytest.approx(scipy_stats.norm.sf(x), abs=1e-9)
    for p in PS:
        assert st.norm.ppf(p) == pytest.approx(scipy_stats.norm.ppf(p), abs=1e-9)

def test_t_diff():
    for df in (1, 3, 10, 30):
        for x in XS:
            assert st.t.pdf(x, df) == pytest.approx(scipy_stats.t.pdf(x, df), abs=1e-9)
            assert st.t.cdf(x, df) == pytest.approx(scipy_stats.t.cdf(x, df), abs=1e-9)
        for p in PS:
            assert st.t.ppf(p, df) == pytest.approx(scipy_stats.t.ppf(p, df), abs=1e-7)

def test_chi2_diff():
    for df in (1, 2, 5, 20):
        for x in (0.1, 0.8, 2.0, 5.0, 15.0, 40.0):
            assert st.chi2.pdf(x, df) == pytest.approx(scipy_stats.chi2.pdf(x, df), abs=1e-9)
            assert st.chi2.cdf(x, df) == pytest.approx(scipy_stats.chi2.cdf(x, df), abs=1e-9)
        for p in PS:
            assert st.chi2.ppf(p, df) == pytest.approx(scipy_stats.chi2.ppf(p, df), rel=1e-7)

def test_f_diff():
    for dfn, dfd in ((1, 10), (3, 7), (5, 2), (10, 10)):
        for x in (0.2, 0.9, 1.5, 3.0, 8.0):
            assert st.f.pdf(x, dfn, dfd) == pytest.approx(scipy_stats.f.pdf(x, dfn, dfd), abs=1e-9)
            assert st.f.cdf(x, dfn, dfd) == pytest.approx(scipy_stats.f.cdf(x, dfn, dfd), abs=1e-9)
        for p in PS:
            assert st.f.ppf(p, dfn, dfd) == pytest.approx(scipy_stats.f.ppf(p, dfn, dfd), rel=1e-6)

A = [12.9, 13.5, 12.8, 15.6, 17.2, 19.2, 12.6, 15.3, 14.4, 11.3]
B = [12.7, 13.6, 12.0, 15.2, 16.8, 20.0, 12.0, 15.9, 16.0, 11.1]
C = [14.2, 12.1, 13.8, 16.1, 15.5, 18.0, 13.1]

def test_ttest_1samp_diff():
    mine = st.ttest_1samp(A, 14.0)
    ref = scipy_stats.ttest_1samp(A, 14.0)
    assert mine.statistic == pytest.approx(ref.statistic, rel=1e-8)
    assert mine.pvalue == pytest.approx(ref.pvalue, rel=1e-8)

def test_ttest_ind_pooled_and_welch_diff():
    for ev in (True, False):
        mine = st.ttest_ind(A, C, equal_var=ev)
        ref = scipy_stats.ttest_ind(A, C, equal_var=ev)
        assert mine.statistic == pytest.approx(ref.statistic, rel=1e-8)
        assert mine.pvalue == pytest.approx(ref.pvalue, rel=1e-8)

def test_ttest_rel_diff():
    mine = st.ttest_rel(A, B)
    ref = scipy_stats.ttest_rel(A, B)
    assert mine.statistic == pytest.approx(ref.statistic, rel=1e-8)
    assert mine.pvalue == pytest.approx(ref.pvalue, rel=1e-8)

def test_pearsonr_diff():
    mine = st.pearsonr(A, B)
    ref = scipy_stats.pearsonr(A, B)
    assert mine.statistic == pytest.approx(ref.statistic, rel=1e-8)
    assert mine.pvalue == pytest.approx(ref.pvalue, rel=1e-8)

def test_pearsonr_n2_diff():
    mine = st.pearsonr([1.0, 2.0], [3.0, 5.0])
    ref = scipy_stats.pearsonr([1.0, 2.0], [3.0, 5.0])
    assert mine.statistic == pytest.approx(float(ref.statistic))
    assert mine.pvalue == pytest.approx(float(ref.pvalue))

TABLE = [[23, 11, 8], [14, 19, 12]]

def test_chi2_contingency_diff():
    for corr in (True, False):
        mine = st.chi2_contingency(TABLE, correction=corr)
        ref = scipy_stats.chi2_contingency(TABLE, correction=corr)
        assert mine.statistic == pytest.approx(ref.statistic, rel=1e-8)
        assert mine.pvalue == pytest.approx(ref.pvalue, rel=1e-8)
        assert mine.dof == ref.dof
        for i, row in enumerate(mine.expected_freq):
            for j, v in enumerate(row):
                assert v == pytest.approx(float(ref.expected_freq[i][j]), rel=1e-10)

def test_chi2_contingency_2x2_yates_diff():
    mine = st.chi2_contingency([[12, 5], [6, 14]])           # correction=True default
    ref = scipy_stats.chi2_contingency([[12, 5], [6, 14]])
    assert mine.statistic == pytest.approx(ref.statistic, rel=1e-8)
    assert mine.pvalue == pytest.approx(ref.pvalue, rel=1e-8)

def test_mannwhitneyu_diff_asymptotic():
    x = [3.1, 4.5, 2.8, 5.9, 4.4, 3.3, 5.1, 2.9]
    y = [4.9, 5.5, 6.1, 4.2, 6.8, 5.0, 5.7]
    for alt in ('two-sided', 'less', 'greater'):
        mine = st.mannwhitneyu(x, y, alternative=alt)
        ref = scipy_stats.mannwhitneyu(x, y, alternative=alt, method='asymptotic')
        assert mine.statistic == pytest.approx(float(ref.statistic), rel=1e-10)
        assert mine.pvalue == pytest.approx(float(ref.pvalue), rel=1e-6)

def test_mannwhitneyu_ties_diff():
    x = [1, 2, 2, 3, 3, 3, 4]
    y = [2, 3, 3, 4, 4, 5, 5, 6]
    mine = st.mannwhitneyu(x, y)
    ref = scipy_stats.mannwhitneyu(x, y, method='asymptotic')
    assert mine.statistic == pytest.approx(float(ref.statistic), rel=1e-10)
    assert mine.pvalue == pytest.approx(float(ref.pvalue), rel=1e-6)
