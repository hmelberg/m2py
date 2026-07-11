# Differensialtester mot ekte numpy — kjøres kun der numpy finnes.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
realnp = pytest.importorskip('numpy')
import numpy_brython as np

DATA = [12.9, 13.5, 12.8, 15.6, 17.2, 19.2, 12.6, 15.3, 14.4, 11.3]


def test_aggregations_diff():
    mine = np.array(DATA)
    ref = realnp.array(DATA)
    assert mine.mean() == pytest.approx(float(ref.mean()), rel=1e-12)
    assert mine.std() == pytest.approx(float(ref.std()), rel=1e-12)          # ddof=0
    assert mine.var(ddof=1) == pytest.approx(float(ref.var(ddof=1)), rel=1e-12)
    assert np.median(DATA) == pytest.approx(float(realnp.median(ref)), rel=1e-12)
    for q in (10, 25, 50, 75, 90, 99):
        assert np.percentile(DATA, q) == pytest.approx(
            float(realnp.percentile(ref, q)), rel=1e-12)

def test_constructors_and_ops_diff():
    assert np.linspace(0, 7, 13).tolist() == pytest.approx(
        realnp.linspace(0, 7, 13).tolist())
    assert np.arange(2, 20, 3).tolist() == realnp.arange(2, 20, 3).tolist()
    a = np.array(DATA)
    r = realnp.array(DATA)
    assert ((a - a.mean()) / a.std()).tolist() == pytest.approx(
        ((r - r.mean()) / r.std()).tolist(), rel=1e-12)

def test_sort_argsort_where_dot_diff():
    assert np.argsort(DATA).tolist() == realnp.argsort(DATA).tolist()
    assert np.sort(DATA).tolist() == pytest.approx(realnp.sort(DATA).tolist())
    c = [v > 14.0 for v in DATA]
    assert np.where(np.array(c), 1, 0).tolist() == \
        realnp.where(realnp.array(c), 1, 0).tolist()
    m = [[1.5, 2.0], [3.0, 4.5]]
    mine = np.dot(m, m).tolist()
    ref = realnp.dot(realnp.array(m), realnp.array(m)).tolist()
    for i in range(len(mine)):
        assert mine[i] == pytest.approx(ref[i], rel=1e-12)
    assert np.unique([3, 1, 2, 1, 3]).tolist() == \
        realnp.unique([3, 1, 2, 1, 3]).tolist()

def test_dot_1d_2d_and_unique_nan_diff():
    assert np.dot([1.5, 2.5], [[1, 2], [3, 4]]).tolist() == pytest.approx(
        realnp.dot([1.5, 2.5], realnp.array([[1, 2], [3, 4]])).tolist())
    mine = np.unique([2.0, float('nan'), 1.0, float('nan')]).tolist()
    ref = realnp.unique([2.0, float('nan'), 1.0, float('nan')]).tolist()
    assert len(mine) == len(ref) == 3
    assert mine[:2] == pytest.approx(ref[:2])

def test_arange_float_diff():
    assert np.arange(0, 1, 0.1).tolist() == pytest.approx(
        realnp.arange(0, 1, 0.1).tolist())
