import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
import scipy_stats_brython as st

# ── spesialfunksjoner: eksakte identiteter (scipy-frie) ────────────────────

def test_gammainc_p_exponential_identity():
    # P(1, x) = 1 - e^-x  (eksakt)
    for x in (0.1, 0.5, 1.0, 2.0, 5.0, 10.0):
        assert abs(st._gammainc_p(1.0, x) - (1.0 - math.exp(-x))) < 1e-12

def test_gammainc_p_bounds_and_monotone():
    assert st._gammainc_p(2.5, 0.0) == 0.0
    vals = [st._gammainc_p(2.5, x) for x in (0.5, 1.0, 2.0, 4.0, 8.0, 20.0)]
    assert all(b > a for a, b in zip(vals, vals[1:]))
    assert vals[-1] > 0.9999

def test_betainc_uniform_identity():
    # I_x(1, 1) = x  (eksakt)
    for x in (0.0, 0.1, 0.25, 0.5, 0.9, 1.0):
        assert abs(st._betainc(1.0, 1.0, x) - x) < 1e-12

def test_betainc_symmetry():
    # I_x(a, b) = 1 - I_(1-x)(b, a)
    assert abs(st._betainc(2.5, 4.0, 0.3) - (1.0 - st._betainc(4.0, 2.5, 0.7))) < 1e-12

def test_norm_ppf_std_known_values():
    assert abs(st._norm_ppf_std(0.5)) < 1e-12
    assert abs(st._norm_ppf_std(0.975) - 1.959963984540054) < 1e-9
    assert abs(st._norm_ppf_std(0.025) + 1.959963984540054) < 1e-9
    # roundtrip mot erfc-basert cdf
    for p in (0.001, 0.1, 0.3, 0.7, 0.99, 0.9999):
        x = st._norm_ppf_std(p)
        assert abs(0.5 * math.erfc(-x / math.sqrt(2.0)) - p) < 1e-12

def test_invert_cdf_recovers_known_function():
    # invertér F(x) = 1 - e^-x på [0, ∞)
    cdf = lambda x: 1.0 - math.exp(-x)
    for p in (0.1, 0.5, 0.9, 0.999):
        assert abs(st._invert_cdf(cdf, p, 0.0, 1.0) - (-math.log(1.0 - p))) < 1e-9

def test_tolist_duck_typing():
    class FakeSeries:
        def tolist(self):
            return [1, 2]
    assert st._tolist(FakeSeries()) == [1, 2]
    assert st._tolist(range(3)) == [0, 1, 2]
    assert st._tolist((4, 5)) == [4, 5]

# ── fordelinger: eksakte identiteter og rundturer (scipy-frie) ──────────────

def test_norm_cdf_ppf_pdf():
    assert abs(st.norm.cdf(0.0) - 0.5) < 1e-15
    assert abs(st.norm.cdf(1.959963984540054) - 0.975) < 1e-12
    assert abs(st.norm.ppf(0.975) - 1.959963984540054) < 1e-9
    assert abs(st.norm.pdf(0.0) - 1.0 / math.sqrt(2.0 * math.pi)) < 1e-15
    # loc/scale: standardisering
    assert abs(st.norm.cdf(120.0, loc=100.0, scale=10.0) - st.norm.cdf(2.0)) < 1e-15
    assert abs(st.norm.sf(1.0) - (1.0 - st.norm.cdf(1.0))) < 1e-15

def test_t_cauchy_identity_and_symmetry():
    # t med df=1 er Cauchy: cdf(x) = 1/2 + arctan(x)/pi  (eksakt)
    for x in (-3.0, -1.0, 0.0, 0.5, 2.0):
        assert abs(st.t.cdf(x, 1) - (0.5 + math.atan(x) / math.pi)) < 1e-12
    assert abs(st.t.cdf(-1.7, 7) + st.t.cdf(1.7, 7) - 1.0) < 1e-12
    assert abs(st.t.ppf(0.975, 1000) - 1.96) < 1e-2

def test_chi2_exponential_identity():
    # chi2 med df=2 er eksponentiell(1/2): cdf(x) = 1 - e^(-x/2)  (eksakt)
    for x in (0.5, 1.0, 3.0, 8.0):
        assert abs(st.chi2.cdf(x, 2) - (1.0 - math.exp(-x / 2.0))) < 1e-12
    assert st.chi2.cdf(0.0, 4) == 0.0

def test_f_symmetry_identity():
    # X ~ F(d, d)  =>  1/X ~ F(d, d), så cdf(1, d, d) = 0.5  (eksakt)
    for d in (2, 5, 10):
        assert abs(st.f.cdf(1.0, d, d) - 0.5) < 1e-12

def test_ppf_cdf_roundtrips():
    for p in (0.01, 0.1, 0.5, 0.9, 0.99):
        assert abs(st.t.cdf(st.t.ppf(p, 7), 7) - p) < 1e-9
        assert abs(st.chi2.cdf(st.chi2.ppf(p, 5), 5) - p) < 1e-9
        assert abs(st.f.cdf(st.f.ppf(p, 4, 9), 4, 9) - p) < 1e-9

# ── t-tester og korrelasjon ─────────────────────────────────────────────────

def test_ttest_1samp_symmetric_data():
    res = st.ttest_1samp([-1.0, 0.0, 1.0], 0.0)
    assert abs(res.statistic) < 1e-12
    assert abs(res.pvalue - 1.0) < 1e-12
    stat, p = res                       # tuple-utpakking som i scipy
    assert stat == res.statistic and p == res.pvalue
    assert res[0] == stat and res[1] == p

def test_ttest_ind_identical_groups():
    res = st.ttest_ind([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert abs(res.statistic) < 1e-12 and abs(res.pvalue - 1.0) < 1e-12

def test_ttest_rel_zero_diff_no_crash():
    # identiske par gir 0/0 — nan aksepteres, poenget er ingen krasj
    res = st.ttest_rel([5.0, 6.0, 7.0], [5.0, 6.0, 7.0])
    assert res.statistic != res.statistic     # nan
    assert res.pvalue != res.pvalue           # nan

def test_pearsonr_perfect_and_zero():
    r = st.pearsonr([1, 2, 3, 4], [2, 4, 6, 8])
    assert abs(r.statistic - 1.0) < 1e-12
    r2 = st.pearsonr([1, 2, 3, 4], [1, -1, 1, -1])
    assert abs(r2.statistic) < 0.5      # nær null, ikke eksakt

def test_pearsonr_n2_pvalue_is_one():
    res = st.pearsonr([1, 2], [3, 5])
    assert abs(res.statistic - 1.0) < 1e-12
    assert res.pvalue == 1.0

def test_ttest_degenerate_n1_returns_nan():
    r1 = st.ttest_1samp([5.0], 3.0)
    assert r1.statistic != r1.statistic and r1.pvalue != r1.pvalue
    r2 = st.ttest_ind([5.0], [1.0, 2.0])
    assert r2.statistic != r2.statistic
    r3 = st.ttest_ind([5.0], [1.0])
    assert r3.statistic != r3.statistic

# ── chi2_contingency og mannwhitneyu ───────────────────────────────────────

def test_chi2_contingency_independent_table():
    # perfekt uavhengighet: forventet == observert => stat 0, p 1
    res = st.chi2_contingency([[10, 20], [20, 40]], correction=False)
    assert abs(res.statistic) < 1e-12
    assert abs(res.pvalue - 1.0) < 1e-12
    assert res.dof == 1
    stat, p, dof, exp = res             # 4-tuple-utpakking som i scipy
    assert exp[0][0] == pytest.approx(10.0)

def test_chi2_contingency_yates_reduces_statistic():
    raw = st.chi2_contingency([[12, 5], [6, 14]], correction=False)
    yates = st.chi2_contingency([[12, 5], [6, 14]], correction=True)
    assert yates.statistic < raw.statistic

def test_mannwhitneyu_identical_groups():
    res = st.mannwhitneyu([1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6])
    assert res.pvalue > 0.9

def test_mannwhitneyu_empty_input_returns_nan():
    res = st.mannwhitneyu([], [1.0, 2.0])
    assert res.statistic != res.statistic and res.pvalue != res.pvalue


def test_ttest_ind_welch_constant_groups_nan():
    res = st.ttest_ind([5.0, 5.0, 5.0], [3.0, 3.0, 3.0], equal_var=False)
    assert res.statistic != res.statistic and res.pvalue != res.pvalue


def test_chi2_contingency_zero_expected_raises():
    with pytest.raises(ValueError):
        st.chi2_contingency([[0, 0], [1, 2]])


def test_chi2_contingency_ragged_raises():
    with pytest.raises(ValueError):
        st.chi2_contingency([[1, 2, 3], [4, 5]])
    with pytest.raises(ValueError):
        st.chi2_contingency([[1, 2], []])
