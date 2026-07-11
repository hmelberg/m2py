# Enhetstester for sklearn_brython.linear_model-seksjonen (ren CPython,
# fake-frie). Diff mot ekte sklearn ligger i test_sklearn_brython_linear_diff.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import sklearn_brython as skl

import pytest
import numpy_brython as npb
import pandas_brython as pdb


# Eksakt lineært datasett: y = 1 + 2·x1 + 3·x2 (kolonnene er ikke kollineære)
X_LISTE = [[1.0, 2.0], [2.0, 1.0], [3.0, 4.0], [4.0, 3.0], [5.0, 7.0], [6.0, 5.0]]
Y_LIN = [1.0 + 2.0 * r[0] + 3.0 * r[1] for r in X_LISTE]

# Overlappende binært datasett (én forklaringsvariabel, labels som strenger).
# 'ja' dominerer for høye x, 'nei' for lave — men med to bevisste avvik
# (x=0.5 er 'nei', x=-0.5 er 'ja') så klassene overlapper.
X_LOG = [[-2.0], [-1.5], [-1.0], [-0.5], [0.5], [1.0], [1.5], [2.0], [-0.8], [0.8]]
Y_LOG = ['nei', 'nei', 'nei', 'ja', 'nei', 'ja', 'ja', 'ja', 'nei', 'ja']


# ── LinearRegression ────────────────────────────────────────────────────────

def test_linreg_fit_predict_score():
    m = skl.LinearRegression().fit(X_LISTE, Y_LIN)
    assert m.fit(X_LISTE, Y_LIN) is m                    # fit returnerer self
    assert m.coef_.tolist() == pytest.approx([2.0, 3.0], abs=1e-9)
    assert m.intercept_ == pytest.approx(1.0, abs=1e-9)
    pred = m.predict([[10.0, 20.0], [0.0, 0.0]])
    assert pred.tolist() == pytest.approx([81.0, 1.0], abs=1e-9)
    assert m.score(X_LISTE, Y_LIN) == pytest.approx(1.0, abs=1e-12)


def test_linreg_uten_intercept():
    X = [[1.0], [2.0], [3.0], [4.0]]
    y = [2.0, 4.0, 6.0, 8.0]                             # y = 2x eksakt
    m = skl.LinearRegression(fit_intercept=False).fit(X, y)
    assert m.coef_.tolist() == pytest.approx([2.0], abs=1e-12)
    assert m.intercept_ == 0.0
    assert m.predict([[5.0]]).tolist() == pytest.approx([10.0], abs=1e-12)


def test_linreg_1d_input_blir_en_kolonne():
    m = skl.LinearRegression().fit([1.0, 2.0, 3.0, 4.0], [3.0, 5.0, 7.0, 9.0])
    assert m.coef_.tolist() == pytest.approx([2.0], abs=1e-12)
    assert m.intercept_ == pytest.approx(1.0, abs=1e-9)


def test_linreg_dataframe_og_ndarray_gir_samme_som_liste():
    df = pdb.DataFrame({'a': [r[0] for r in X_LISTE],
                        'b': [r[1] for r in X_LISTE]})
    nd = npb.array(X_LISTE)
    m1 = skl.LinearRegression().fit(X_LISTE, Y_LIN)
    m2 = skl.LinearRegression().fit(df, Y_LIN)
    m3 = skl.LinearRegression().fit(nd, npb.array(Y_LIN))
    assert m2.coef_.tolist() == pytest.approx(m1.coef_.tolist(), abs=1e-12)
    assert m3.coef_.tolist() == pytest.approx(m1.coef_.tolist(), abs=1e-12)
    assert m2.intercept_ == pytest.approx(m1.intercept_, abs=1e-12)
    assert m3.intercept_ == pytest.approx(m1.intercept_, abs=1e-12)
    assert (m2.predict(df).tolist()
            == pytest.approx(m1.predict(X_LISTE).tolist(), abs=1e-12))


def test_linreg_predict_returnerer_numpy_brython_array():
    m = skl.LinearRegression().fit(X_LISTE, Y_LIN)
    pred = m.predict(X_LISTE)
    assert isinstance(pred, npb.ndarray)
    maske = pred > 20.0                                  # boolsk maske virker
    assert len(pred[maske].tolist()) == sum(1 for v in Y_LIN if v > 20.0)


def test_linreg_ikke_tilpasset_gir_norsk_valueerror():
    with pytest.raises(ValueError, match='ikke tilpasset'):
        skl.LinearRegression().predict([[1.0]])
    with pytest.raises(ValueError, match='ikke tilpasset'):
        skl.LinearRegression().score([[1.0]], [1.0])


def test_linreg_singulaer_gir_norsk_valueerror():
    X = [[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]]             # kolonne 2 = 2·kolonne 1
    with pytest.raises(ValueError, match='singul'):
        skl.LinearRegression().fit(X, [1.0, 2.0, 3.0])


def test_linreg_ulik_lengde_gir_norsk_valueerror():
    with pytest.raises(ValueError, match='ulikt antall rader'):
        skl.LinearRegression().fit(X_LISTE, Y_LIN[:-1])


def test_linreg_konstant_y_gir_ikke_zerodivision():
    X = [[1.0], [2.0], [3.0]]
    m = skl.LinearRegression().fit(X, [5.0, 5.0, 5.0])
    assert m.score(X, [5.0, 5.0, 5.0]) == 1.0            # som sklearn.r2_score


# ── LogisticRegression ──────────────────────────────────────────────────────

def test_logreg_fit_predict_proba_score():
    m = skl.LogisticRegression().fit(X_LOG, Y_LOG)
    assert m.classes_.tolist() == ['ja', 'nei']          # sorterte unike labels
    assert m.coef_.shape == (1, 1)
    assert m.intercept_.shape == (1,)
    pred = m.predict(X_LOG)
    assert set(pred.tolist()) <= {'ja', 'nei'}           # originale labels
    proba = m.predict_proba(X_LOG)
    assert proba.shape == (len(X_LOG), 2)
    for rad in proba.tolist():
        assert rad[0] + rad[1] == pytest.approx(1.0, abs=1e-12)
        assert 0.0 <= rad[0] <= 1.0
    # kolonnene følger classes_-rekkefølgen: høy x -> 'ja' (kolonne 0)
    p_hoy = m.predict_proba([[2.0]]).tolist()[0]
    p_lav = m.predict_proba([[-2.0]]).tolist()[0]
    assert p_hoy[0] > 0.5 and p_lav[1] > 0.5
    # de to avvikerne kan ikke treffes av en monoton modell -> 8/10
    assert m.score(X_LOG, Y_LOG) == pytest.approx(0.8)


def test_logreg_dataframe_og_ndarray_gir_samme_som_liste():
    df = pdb.DataFrame({'x': [r[0] for r in X_LOG]})
    nd = npb.array(X_LOG)
    m1 = skl.LogisticRegression().fit(X_LOG, Y_LOG)
    m2 = skl.LogisticRegression().fit(df, Y_LOG)
    m3 = skl.LogisticRegression().fit(nd, Y_LOG)
    assert m2.coef_.tolist()[0] == pytest.approx(m1.coef_.tolist()[0], abs=1e-10)
    assert m3.coef_.tolist()[0] == pytest.approx(m1.coef_.tolist()[0], abs=1e-10)
    assert (m2.intercept_.tolist()
            == pytest.approx(m1.intercept_.tolist(), abs=1e-10))
    assert m2.predict(df).tolist() == m1.predict(X_LOG).tolist()


def test_logreg_flere_enn_to_klasser_gir_norsk_valueerror():
    with pytest.raises(ValueError, match='kun binær klassifisering'):
        skl.LogisticRegression().fit([[1.0], [2.0], [3.0]], ['a', 'b', 'c'])


def test_logreg_en_klasse_gir_norsk_valueerror():
    with pytest.raises(ValueError, match='bare én klasse'):
        skl.LogisticRegression().fit([[1.0], [2.0]], ['a', 'a'])


def test_logreg_ikke_tilpasset_gir_norsk_valueerror():
    with pytest.raises(ValueError, match='ikke tilpasset'):
        skl.LogisticRegression().predict([[1.0]])
    with pytest.raises(ValueError, match='ikke tilpasset'):
        skl.LogisticRegression().predict_proba([[1.0]])
