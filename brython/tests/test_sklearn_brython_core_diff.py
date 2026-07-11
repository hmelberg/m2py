# Diff-tester: sklearn_brython kjerneseksjonen mot EKTE scikit-learn (1.9.0).
# Kjøres kun der sklearn er installert (CPython-utvikling, ikke Brython).
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import sklearn_brython as skl

import random
import pytest

sklearn = pytest.importorskip('sklearn')
from sklearn.model_selection import train_test_split as sk_split
from sklearn.preprocessing import StandardScaler as SkScaler
from sklearn.neighbors import KNeighborsClassifier as SkKNN
from sklearn.metrics import (accuracy_score as sk_acc,
                             confusion_matrix as sk_cm,
                             mean_squared_error as sk_mse,
                             r2_score as sk_r2)


# ── fixtures ────────────────────────────────────────────────────────────────

def _tilfeldig_matrise(n, p, seed):
    rng = random.Random(seed)
    return [[rng.uniform(-10, 10) for _ in range(p)] for _ in range(n)]

X_LITEN = [[1.0, -2.0], [4.0, 0.5], [-3.0, 7.25], [0.0, 1.0], [2.5, 2.5]]

Y_PAR = [                                   # (y_true, y_pred)-fixtures
    ([1, 0, 1, 1, 0], [1, 1, 1, 0, 0]),
    (['a', 'b', 'c', 'a'], ['a', 'c', 'c', 'b']),
    ([0, 0, 0, 0], [0, 0, 0, 0]),
]

REG_PAR = [
    ([1.0, 2.0, 3.0, 4.0], [1.1, 1.9, 3.2, 3.7]),
    ([-2.0, 0.5, 7.25], [-2.0, 0.5, 7.25]),
    ([10.0, 12.0, 9.5, 11.0], [11.0, 11.0, 11.0, 11.0]),
]


# ── StandardScaler: eksakt (tol 1e-12) ──────────────────────────────────────

@pytest.mark.parametrize('X', [X_LITEN, _tilfeldig_matrise(30, 4, seed=1)])
def test_scaler_mean_scale_transform_eksakt(X):
    var = skl.StandardScaler().fit(X)
    ekte = SkScaler().fit(X)
    assert var.mean_ == pytest.approx(list(ekte.mean_), abs=1e-12)
    assert var.scale_ == pytest.approx(list(ekte.scale_), abs=1e-12)
    Z_var = var.transform(X).tolist()
    Z_ekte = ekte.transform(X).tolist()
    for rv, re in zip(Z_var, Z_ekte):
        assert rv == pytest.approx(re, abs=1e-12)

def test_scaler_konstant_kolonne_som_sklearn():
    X = [[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]]
    var = skl.StandardScaler().fit(X)
    ekte = SkScaler().fit(X)
    assert var.scale_ == pytest.approx(list(ekte.scale_), abs=1e-12)  # 1.0
    assert var.transform(X).tolist()[0][1] == ekte.transform(X)[0][1] == 0.0


# ── metrikker: eksakt på flere fixtures ─────────────────────────────────────

@pytest.mark.parametrize('yt,yp', Y_PAR)
def test_accuracy_eksakt(yt, yp):
    assert skl.accuracy_score(yt, yp) == sk_acc(yt, yp)

@pytest.mark.parametrize('yt,yp', Y_PAR)
def test_confusion_matrix_eksakt(yt, yp):
    assert skl.confusion_matrix(yt, yp).tolist() == sk_cm(yt, yp).tolist()

@pytest.mark.parametrize('yt,yp', REG_PAR)
def test_mse_eksakt(yt, yp):
    assert skl.mean_squared_error(yt, yp) == \
        pytest.approx(sk_mse(yt, yp), abs=1e-12)

@pytest.mark.parametrize('yt,yp', REG_PAR)
def test_r2_eksakt(yt, yp):
    assert skl.r2_score(yt, yp) == pytest.approx(sk_r2(yt, yp), abs=1e-12)


# ── KNN: identisk predict på likhetsfrie fixtures ───────────────────────────
# Kontinuerlige tilfeldige floats -> ingen avstandslikhet på k-grensen
# (der er sklearns argpartition udefinert). Ren stemmelikhet brytes likt
# hos begge (først i sortert classes_, empirisk verifisert), så den er ufarlig.

@pytest.mark.parametrize('k', [1, 3, 5])
def test_knn_predict_identisk(k):
    rng = random.Random(99)
    X_tr = [[rng.uniform(-5, 5), rng.uniform(-5, 5)] for _ in range(40)]
    y_tr = [rng.choice(['rod', 'gronn', 'bla']) for _ in range(40)]
    X_te = [[rng.uniform(-5, 5), rng.uniform(-5, 5)] for _ in range(25)]
    var = skl.KNeighborsClassifier(n_neighbors=k).fit(X_tr, y_tr)
    ekte = SkKNN(n_neighbors=k).fit(X_tr, y_tr)
    assert var.predict(X_te).tolist() == list(ekte.predict(X_te))

def test_knn_score_som_accuracy():
    X_tr = _tilfeldig_matrise(20, 2, seed=5)
    rng = random.Random(6)
    y_tr = [rng.choice([0, 1]) for _ in range(20)]
    X_te = _tilfeldig_matrise(10, 2, seed=7)
    y_te = [rng.choice([0, 1]) for _ in range(10)]
    var = skl.KNeighborsClassifier(n_neighbors=3).fit(X_tr, y_tr)
    ekte = SkKNN(n_neighbors=3).fit(X_tr, y_tr)
    assert var.score(X_te, y_te) == pytest.approx(ekte.score(X_te, y_te))


# ── train_test_split: n_train/n_test matcher sklearns tall ──────────────────

@pytest.mark.parametrize('n', [10, 11, 7])
@pytest.mark.parametrize('test_size', [None, 0.2, 0.5, 3])  # None = 0.25
def test_split_stoerrelser_som_sklearn(n, test_size):
    data = list(range(n))
    var_tr, var_te = skl.train_test_split(data, test_size=test_size,
                                          random_state=0)
    ekte_tr, ekte_te = sk_split(data, test_size=test_size, random_state=0)
    assert len(var_tr) == len(ekte_tr)
    assert len(var_te) == len(ekte_te)
