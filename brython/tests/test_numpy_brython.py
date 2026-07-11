import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
import numpy_brython as np


def test_array_1d_basics():
    a = np.array([1, 2, 3])
    assert a.ndim == 1 and a.shape == (3,) and a.size == 3
    assert a.tolist() == [1, 2, 3]
    assert len(a) == 3
    assert list(a) == [1, 2, 3]
    assert a[0] == 1 and a[-1] == 3
    assert a[1:].tolist() == [2, 3]

def test_array_2d_basics():
    m = np.array([[1, 2, 3], [4, 5, 6]])
    assert m.ndim == 2 and m.shape == (2, 3) and m.size == 6
    assert m.tolist() == [[1, 2, 3], [4, 5, 6]]
    assert m[1, 2] == 6
    assert m[0].tolist() == [1, 2, 3]
    assert m[:, 1].tolist() == [2, 5]
    assert m[1, :].tolist() == [4, 5, 6]
    assert m.T.tolist() == [[1, 4], [2, 5], [3, 6]]

def test_array_ragged_raises():
    with pytest.raises(ValueError):
        np.array([[1, 2], [3]])

def test_bool_mask_and_fancy_indexing():
    a = np.array([10, 20, 30, 40])
    assert a[[True, False, True, False]].tolist() == [10, 30]
    assert a[[2, 0]].tolist() == [30, 10]

def test_setitem_int_mask_slice():
    a = np.array([1, 2, 3, 4])
    a[0] = 9
    assert a.tolist() == [9, 2, 3, 4]
    a[[False, True, False, True]] = 0
    assert a.tolist() == [9, 0, 3, 0]
    a[1:3] = [7, 8]
    assert a.tolist() == [9, 7, 8, 0]

def test_constructors():
    assert np.arange(4).tolist() == [0, 1, 2, 3]
    assert np.arange(1, 7, 2).tolist() == [1, 3, 5]
    assert np.linspace(0.0, 1.0, 5).tolist() == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert np.linspace(0.0, 1.0, 5).tolist()[-1] == 1.0   # eksakt endepunkt
    assert np.zeros(3).tolist() == [0.0, 0.0, 0.0]
    assert np.ones((2, 2)).tolist() == [[1.0, 1.0], [1.0, 1.0]]
    assert np.full(2, 7.5).tolist() == [7.5, 7.5]

def test_asarray_and_copy_semantics():
    a = np.array([1, 2, 3])
    assert np.asarray(a) is a
    b = np.array(a)
    b[0] = 99
    assert a.tolist() == [1, 2, 3]      # kopi, aldri view

def test_constants():
    assert np.nan != np.nan
    assert abs(np.pi - math.pi) < 1e-15

def test_filled_one_tuple_shape():
    assert np.zeros((3,)).tolist() == [0.0, 0.0, 0.0]
    assert np.full((2,), 5).tolist() == [5, 5]
    with pytest.raises(ValueError, match='støttes'):
        np.ones((2, 2, 2))

def test_arithmetic_scalar_and_array():
    a = np.array([1.0, 2.0, 3.0])
    assert (a + 1).tolist() == [2.0, 3.0, 4.0]
    assert (1 + a).tolist() == [2.0, 3.0, 4.0]
    assert (a * 2).tolist() == [2.0, 4.0, 6.0]
    assert (10 - a).tolist() == [9.0, 8.0, 7.0]
    assert (a / 2).tolist() == [0.5, 1.0, 1.5]
    assert (2 / a).tolist() == [2.0, 1.0, 2.0 / 3.0]
    assert (a ** 2).tolist() == [1.0, 4.0, 9.0]
    assert (-a).tolist() == [-1.0, -2.0, -3.0]

def test_arithmetic_array_array_and_shape_mismatch():
    a = np.array([1.0, 2.0])
    b = np.array([10.0, 20.0])
    assert (a + b).tolist() == [11.0, 22.0]
    assert (a * [3, 4]).tolist() == [3.0, 8.0]
    m = np.array([[1, 2], [3, 4]])
    assert (m + m).tolist() == [[2, 4], [6, 8]]
    with pytest.raises(ValueError):
        a + np.array([1.0, 2.0, 3.0])

def test_comparisons_and_mask_flow():
    a = np.array([1, 5, 3, 8])
    assert (a > 3).tolist() == [False, True, False, True]
    assert (a == 3).tolist() == [False, False, True, False]
    assert a[(a > 3).tolist()].tolist() == [5, 8]
    assert a[a > 3].tolist() == [5, 8]          # maske direkte som ndarray

def test_unary_math():
    assert np.sqrt(np.array([1.0, 4.0, 9.0])).tolist() == [1.0, 2.0, 3.0]
    assert np.sqrt(16) == 4.0                    # skalar inn -> skalar ut
    assert np.abs(np.array([-1, 2, -3])).tolist() == [1, 2, 3]
    assert np.round(np.array([1.234, 5.678]), 1).tolist() == [1.2, 5.7]
    assert np.exp(0) == 1.0
    r = np.log(np.array([1.0, math.e]))
    assert r[0] == pytest.approx(0.0) and r[1] == pytest.approx(1.0)
    assert np.isnan(np.array([1.0, np.nan])).tolist() == [False, True]

def test_bool_of_array_is_guarded():
    assert bool(np.array([1]))
    assert not bool(np.array([0]))
    with pytest.raises(ValueError, match='tvetydig'):
        bool(np.array([1, 2]) == np.array([1, 2]))
    with pytest.raises(ValueError, match='tvetydig'):
        if np.array([1, 2, 3]) > 2:
            pass

def test_aggregation_methods_and_functions():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert a.mean() == 2.5 and np.mean(a) == 2.5
    assert np.mean([1, 2, 3]) == 2.0                 # liste rett inn
    assert a.sum() == 10.0 and np.sum(a) == 10.0
    assert a.min() == 1.0 and np.max(a) == 4.0
    assert a.var() == pytest.approx(1.25)            # ddof=0 (numpy-default!)
    assert a.std() == pytest.approx(math.sqrt(1.25))
    assert a.var(ddof=1) == pytest.approx(5.0 / 3.0)
    assert np.median([3, 1, 2]) == 2
    assert np.median([4, 1, 3, 2]) == 2.5
    m = np.array([[1, 2], [3, 4]])
    assert m.mean() == 2.5 and m.sum() == 10          # aggregering over alt

def test_percentile_linear_interpolation():
    a = [1.0, 2.0, 3.0, 4.0]
    assert np.percentile(a, 50) == 2.5
    assert np.percentile(a, 25) == 1.75
    assert np.percentile(a, 0) == 1.0 and np.percentile(a, 100) == 4.0
    assert np.quantile(a, 0.5) == 2.5
    assert np.percentile(a, [25, 75]).tolist() == [1.75, 3.25]

def test_sort_argsort_argmax_unique_cumsum():
    a = np.array([3, 1, 2, 1])
    assert np.sort(a).tolist() == [1, 1, 2, 3]
    assert np.argsort(a).tolist() == [1, 3, 2, 0]
    assert a.argmax() == 0 and np.argmin(a) == 1
    assert np.unique(a).tolist() == [1, 2, 3]
    assert a.cumsum().tolist() == [3, 4, 6, 7]

def test_where_both_forms():
    c = np.array([True, False, True])
    assert np.where(c, 1, 0).tolist() == [1, 0, 1]
    x = np.array([10, 20, 30])
    y = np.array([-1, -2, -3])
    assert np.where(c, x, y).tolist() == [10, -2, 30]
    idx = np.where(np.array([0, 5, 0, 7]) > 0)
    assert isinstance(idx, tuple) and idx[0].tolist() == [1, 3]

def test_concatenate_and_dot():
    assert np.concatenate([np.array([1, 2]), [3], np.array([4])]).tolist() == [1, 2, 3, 4]
    assert np.dot([1, 2, 3], [4, 5, 6]) == 32
    m = np.array([[1, 2], [3, 4]])
    v = np.array([5, 6])
    assert np.dot(m, v).tolist() == [17, 39]
    assert np.dot(m, m).tolist() == [[7, 10], [15, 22]]
    assert (m @ v).tolist() == [17, 39]
    with pytest.raises(ValueError):
        np.dot([1, 2], [1, 2, 3])

def test_astype_and_round_method():
    a = np.array([1.7, 2.2])
    assert a.astype(int).tolist() == [1, 2]
    assert a.round().tolist() == [2.0, 2.0]

def test_dot_1d_2d_and_unique_nan():
    # 1D·2D: radvektor mot matrise
    assert np.dot([1, 2], [[1, 2, 3], [4, 5, 6]]).tolist() == [9, 12, 15]
    # nan dedupliseres og legges sist (som numpy equal_nan=True)
    u = np.unique([2.0, np.nan, 1.0, np.nan, 2.0]).tolist()
    assert u[0] == 1.0 and u[1] == 2.0
    assert len(u) == 3 and u[2] != u[2]

def test_random_seed_reproducible():
    np.random.seed(42)
    a = np.random.normal(0, 1, 5)
    np.random.seed(42)
    b = np.random.normal(0, 1, 5)
    assert a.tolist() == b.tolist()
    assert len(a) == 5

def test_random_shapes_and_scalar():
    np.random.seed(1)
    s = np.random.normal()
    assert isinstance(s, float)
    m = np.random.uniform(0, 1, (2, 3))
    assert m.shape == (2, 3)
    assert all(0.0 <= v <= 1.0 for v in m._flat())

def test_randint_range_exclusive():
    np.random.seed(2)
    vals = np.random.randint(0, 10, 200).tolist()
    assert all(0 <= v <= 9 for v in vals)
    assert 9 in vals and 0 in vals               # med 200 trekk

def test_choice_and_shuffle():
    np.random.seed(3)
    pool = [10, 20, 30, 40]
    one = np.random.choice(pool)
    assert one in pool
    tre = np.random.choice(pool, 3, replace=False)
    assert len(set(tre.tolist())) == 3
    x = [1, 2, 3, 4, 5]
    np.random.shuffle(x)
    assert sorted(x) == [1, 2, 3, 4, 5]

def test_default_rng():
    rng = np.default_rng(7)
    a = rng.normal(0, 1, 4)
    b = np.default_rng(7).normal(0, 1, 4)
    assert a.tolist() == b.tolist()
    ints = np.default_rng(7).integers(0, 5, 100).tolist()
    assert all(0 <= v <= 4 for v in ints)

def test_random_statistical_sanity():
    np.random.seed(1234)
    xs = np.random.normal(10.0, 2.0, 4000)
    assert xs.mean() == pytest.approx(10.0, abs=0.15)
    assert xs.std() == pytest.approx(2.0, abs=0.15)

def test_integration_matplotlib_scipy_statsmodels():
    import matplotlib_brython as plt
    import scipy_stats_brython as st
    import statsmodels_brython as smb
    np.random.seed(11)
    x = np.linspace(0.0, 10.0, 20)
    y = x * 2.0 + 1.0 + np.random.normal(0.0, 0.1, 20)
    # matplotlib: ndarray rett inn i plot
    plt.figure()
    plt.plot(x, y)
    trace = plt.gcf().data[0]
    assert trace['x'] == pytest.approx(x.tolist())
    # scipy: ndarray rett inn i ttest
    res = st.ttest_ind(np.array([1.0, 2.0, 3.0, 4.0]),
                       np.array([1.1, 2.1, 2.9, 4.2]))
    assert res.pvalue > 0.5
    # statsmodels: dict med ndarray-kolonner
    ols = smb.ols('y ~ x', {'y': y, 'x': x}).fit()
    assert ols.params['x'] == pytest.approx(2.0, abs=0.05)
    assert ols.rsquared > 0.99

def test_setitem_guards():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(ValueError, match='feil lengde'):
        a[1:3] = [7, 8, 9]
    with pytest.raises(IndexError, match='feil lengde'):
        a[[True, False]] = 0
    with pytest.raises(ValueError, match='1D'):
        a[0] = [7, 8]
    m = np.array([[1, 2], [3, 4]])
    with pytest.raises(ValueError, match='maske'):
        m[[True, False]] = 0
    m[0] = [9, 9]
    assert m.tolist() == [[9, 9], [3, 4]]
    with pytest.raises(ValueError):
        m[0] = [9]

def test_arange_float_step_no_drift():
    assert len(np.arange(0, 1, 0.1)) == 10
    assert np.arange(0, 1, 0.1).tolist()[0] == 0.0

def test_percentile_range_and_2d_sort_guards():
    with pytest.raises(ValueError, match='0, 100'):
        np.percentile([1, 2, 3], -10)
    with pytest.raises(ValueError, match='1D'):
        np.sort(np.array([[3, 1], [2, 0]]))

def test_pandas_integration_ndarray():
    import pandas_brython as pd
    df = pd.DataFrame({'x': [1.0, 2.0, 3.0]})
    df['c'] = np.array([10.0, 20.0, 30.0])
    assert list(df['c'].values) == [10.0, 20.0, 30.0]       # IKKE kringkastet
    s = pd.Series(np.array([1.0, 2.0]))
    assert list(s.values) == [1.0, 2.0]
    df2 = pd.DataFrame({'a': np.array([1, 2]), 'b': [3, 4]})
    assert df2['a'].values[1] == 2
