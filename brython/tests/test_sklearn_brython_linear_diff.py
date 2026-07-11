# Diff-tester: sklearn_brython.linear_model mot EKTE scikit-learn (1.9.0).
# Hoppes over der sklearn ikke er installert.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import sklearn_brython as skl

import random
import pytest

sklearn = pytest.importorskip('sklearn')
from sklearn.linear_model import LinearRegression as SkLinReg
from sklearn.linear_model import LogisticRegression as SkLogReg


# ── fixtures ────────────────────────────────────────────────────────────────

def _fixture_lin_flerkolonne():
    """40 rader, 3 kolonner, støy — blandede fortegn i både X og y."""
    rng = random.Random(7)
    X = [[rng.uniform(-5.0, 5.0), rng.uniform(-3.0, 3.0), rng.uniform(0.0, 10.0)]
         for _ in range(40)]
    y = [2.5 * a - 1.7 * b + 0.3 * c - 4.0 + rng.gauss(0.0, 1.0)
         for a, b, c in X]
    return X, y


def _fixture_lin_negativ():
    """25 rader, 2 kolonner — første kolonne helt negativ, negativ y-trend."""
    rng = random.Random(11)
    X = [[rng.uniform(-10.0, -1.0), rng.uniform(-2.0, 2.0)] for _ in range(25)]
    y = [-0.9 * a + 3.3 * b - 12.0 + rng.gauss(0.0, 0.5) for a, b in X]
    return X, y


def _fixture_logit():
    """80 rader, 2 kolonner. Støy (sd 1.2) rundt signalet gjør at klassene
    OVERLAPPER — bevisst ikke perfekt separerbare (lærdom fra statsmodels-
    stadiet: separerbare data gir divergerende koeffisienter)."""
    rng = random.Random(3)
    X, y = [], []
    for _ in range(80):
        a = rng.uniform(-2.0, 2.0)
        b = rng.uniform(-2.0, 2.0)
        z = 0.8 * a - 0.6 * b + rng.gauss(0.0, 1.2)
        X.append([a, b])
        y.append(1 if z > 0.0 else 0)
    return X, y


def test_logit_fixture_er_ikke_perfekt_separerbar():
    X, y = _fixture_logit()
    assert 0 < sum(y) < len(y)                       # begge klasser til stede
    # nesten uregularisert modell: ved perfekt separasjon ville accuracy -> 1.0
    ekte = SkLogReg(C=1e6, solver='lbfgs', max_iter=5000).fit(X, y)
    assert ekte.score(X, y) < 1.0


# ── LinearRegression ────────────────────────────────────────────────────────

@pytest.mark.parametrize('fixture', [_fixture_lin_flerkolonne,
                                     _fixture_lin_negativ])
def test_linreg_diff(fixture):
    X, y = fixture()
    mitt = skl.LinearRegression().fit(X, y)
    ekte = SkLinReg().fit(X, y)
    assert mitt.coef_.tolist() == pytest.approx(list(ekte.coef_), abs=1e-8)
    assert mitt.intercept_ == pytest.approx(float(ekte.intercept_), abs=1e-8)
    Xny = X[:7]
    assert (mitt.predict(Xny).tolist()
            == pytest.approx(list(ekte.predict(Xny)), abs=1e-8))
    assert mitt.score(X, y) == pytest.approx(ekte.score(X, y), abs=1e-8)


def test_linreg_diff_uten_intercept():
    X, y = _fixture_lin_negativ()
    mitt = skl.LinearRegression(fit_intercept=False).fit(X, y)
    ekte = SkLinReg(fit_intercept=False).fit(X, y)
    assert mitt.coef_.tolist() == pytest.approx(list(ekte.coef_), abs=1e-8)
    assert mitt.intercept_ == 0.0 and float(ekte.intercept_) == 0.0
    assert (mitt.predict(X).tolist()
            == pytest.approx(list(ekte.predict(X)), abs=1e-8))


# ── LogisticRegression ──────────────────────────────────────────────────────

@pytest.mark.parametrize('C', [1.0, 10.0])
def test_logreg_diff(C):
    X, y = _fixture_logit()
    mitt = skl.LogisticRegression(C=C).fit(X, y)
    ekte = SkLogReg(C=C, solver='lbfgs', max_iter=5000, tol=1e-10).fit(X, y)
    assert mitt.classes_.tolist() == list(ekte.classes_)
    assert mitt.coef_.shape == ekte.coef_.shape == (1, 2)
    assert mitt.intercept_.shape == (1,)
    assert (mitt.coef_.tolist()[0]
            == pytest.approx(list(ekte.coef_[0]), abs=1e-3))
    assert (mitt.intercept_.tolist()[0]
            == pytest.approx(float(ekte.intercept_[0]), abs=1e-3))
    assert mitt.predict(X).tolist() == [int(v) for v in ekte.predict(X)]
    for mrad, erad in zip(mitt.predict_proba(X).tolist(),
                          ekte.predict_proba(X).tolist()):
        assert mrad == pytest.approx(erad, abs=1e-4)


def test_logreg_diff_score_er_accuracy():
    X, y = _fixture_logit()
    mitt = skl.LogisticRegression(C=1.0).fit(X, y)
    ekte = SkLogReg(C=1.0, solver='lbfgs', max_iter=5000, tol=1e-10).fit(X, y)
    assert mitt.score(X, y) == pytest.approx(ekte.score(X, y), abs=1e-12)
