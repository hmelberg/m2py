# Enhetstester for sklearn_brython kjerneseksjonen (train_test_split,
# StandardScaler, KNeighborsClassifier, metrikker) — håndregnede fasiter.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import sklearn_brython as skl

import pytest
import numpy_brython as np
import pandas_brython as pd


# ── train_test_split: størrelser ────────────────────────────────────────────

def test_split_default_er_kvart():
    tr, te = skl.train_test_split(list(range(10)), random_state=0)
    assert len(tr) == 7 and len(te) == 3     # ceil(10*0.25) = 3

def test_split_float_andel_ceil():
    tr, te = skl.train_test_split(list(range(11)), test_size=0.2,
                                  random_state=0)
    assert len(tr) == 8 and len(te) == 3     # ceil(11*0.2) = 3

def test_split_heltall_antall():
    tr, te = skl.train_test_split(list(range(10)), test_size=3,
                                  random_state=0)
    assert len(tr) == 7 and len(te) == 3

def test_split_train_size_floor():
    tr, te = skl.train_test_split(list(range(10)), train_size=0.65,
                                  random_state=0)
    assert len(tr) == 6 and len(te) == 4     # floor(10*0.65) = 6

def test_split_disjunkt_og_uttoemmende():
    data = list(range(13))
    tr, te = skl.train_test_split(data, test_size=0.3, random_state=42)
    assert set(tr) & set(te) == set()
    assert sorted(tr + te) == data

def test_split_determinisme_samme_seed():
    a = skl.train_test_split(list(range(20)), random_state=7)
    b = skl.train_test_split(list(range(20)), random_state=7)
    assert a == b

def test_split_shuffle_false_bevarer_rekkefoelge():
    tr, te = skl.train_test_split(list(range(8)), test_size=0.25,
                                  shuffle=False)
    assert tr == [0, 1, 2, 3, 4, 5] and te == [6, 7]

def test_split_rader_holder_foelge():
    # X-rad i og y-verdi i skal havne samme sted
    X = [[i, i * 10] for i in range(12)]
    y = list(range(12))
    X_tr, X_te, y_tr, y_te = skl.train_test_split(X, y, random_state=3)
    for rad, mal in zip(X_tr, y_tr):
        assert rad == [mal, mal * 10]
    for rad, mal in zip(X_te, y_te):
        assert rad == [mal, mal * 10]


# ── train_test_split: containertyper ────────────────────────────────────────

def test_split_dataframe_inn_dataframe_ut():
    df = pd.DataFrame({'x': [1, 2, 3, 4, 5, 6, 7, 8],
                       'y': [8, 7, 6, 5, 4, 3, 2, 1]})
    tr, te = skl.train_test_split(df, test_size=0.25, random_state=1)
    assert isinstance(tr, pd.DataFrame) and isinstance(te, pd.DataFrame)
    assert tr.shape == (6, 2) and te.shape == (2, 2)
    assert tuple(tr.columns) == ('x', 'y')
    # radene er intakte (x + y == 9 i alle rader)
    for rad in tr.values + te.values:
        assert rad[0] + rad[1] == 9

def test_split_ndarray_inn_ndarray_ut():
    arr = np.array([[i, i + 1] for i in range(10)])
    tr, te = skl.train_test_split(arr, test_size=0.2, random_state=1)
    assert isinstance(tr, np.ndarray) and isinstance(te, np.ndarray)
    assert tr.shape == (8, 2) and te.shape == (2, 2)

def test_split_liste_inn_liste_ut():
    tr, te = skl.train_test_split([1, 2, 3, 4], test_size=0.25,
                                  random_state=1)
    assert isinstance(tr, list) and isinstance(te, list)


# ── train_test_split: norske feil ───────────────────────────────────────────

def test_split_stratify_ikke_stottet():
    with pytest.raises(NotImplementedError, match='stratify'):
        skl.train_test_split([1, 2, 3, 4], stratify=[0, 0, 1, 1])

def test_split_ingen_arrays():
    with pytest.raises(ValueError, match='minst ett array'):
        skl.train_test_split()

def test_split_ulik_lengde():
    with pytest.raises(ValueError, match='ulikt antall rader'):
        skl.train_test_split([1, 2, 3], [1, 2])

def test_split_ugyldig_andel():
    with pytest.raises(ValueError, match='mellom 0 og 1'):
        skl.train_test_split([1, 2, 3, 4], test_size=1.5)

def test_split_for_stort_heltall():
    with pytest.raises(ValueError, match='ugyldig splitt'):
        skl.train_test_split([1, 2, 3], test_size=5)


# ── StandardScaler ──────────────────────────────────────────────────────────

def test_scaler_haandregnet():
    X = [[1.0, 10.0], [3.0, 10.0], [5.0, 10.0]]
    sc = skl.StandardScaler().fit(X)
    assert sc.mean_ == [3.0, 10.0]
    assert sc.var_ == pytest.approx([8.0 / 3.0, 0.0])   # ddof=0
    # konstant kolonne: var 0 -> scale 1.0 (som sklearn)
    assert sc.scale_[0] == pytest.approx((8.0 / 3.0) ** 0.5)
    assert sc.scale_[1] == 1.0
    Z = sc.transform(X).tolist()
    assert [rad[1] for rad in Z] == [0.0, 0.0, 0.0]
    assert Z[1][0] == 0.0                               # midtpunktet

def test_scaler_rundtur():
    X = [[1.5, -2.0], [4.0, 0.5], [-3.0, 7.25], [0.0, 1.0]]
    sc = skl.StandardScaler()
    Z = sc.fit_transform(X)
    tilbake = sc.inverse_transform(Z).tolist()
    for rad_inn, rad_ut in zip(X, tilbake):
        assert rad_ut == pytest.approx(rad_inn, abs=1e-12)

def test_scaler_fit_transform_lik_fit_pluss_transform():
    X = [[1.0, 2.0], [3.0, 4.0], [5.0, 7.0]]
    a = skl.StandardScaler().fit_transform(X).tolist()
    sc = skl.StandardScaler().fit(X)
    b = sc.transform(X).tolist()
    assert a == b

def test_scaler_ikke_tilpasset():
    with pytest.raises(ValueError, match='ikke tilpasset'):
        skl.StandardScaler().transform([[1.0]])


# ── KNeighborsClassifier ────────────────────────────────────────────────────

def test_knn_k1_naermeste_vinner():
    X = [[0.0], [10.0], [20.0]]
    y = ['lav', 'midt', 'hoy']
    knn = skl.KNeighborsClassifier(n_neighbors=1).fit(X, y)
    assert knn.predict([[1.0], [11.0], [19.0]]).tolist() == \
        ['lav', 'midt', 'hoy']

def test_knn_k_lik_n_flertall():
    # k = n: hele treningssettet stemmer -> flertallsklassen (likhetsfritt)
    X = [[0.0], [1.0], [2.0], [3.0], [4.0]]
    y = ['a', 'a', 'a', 'b', 'b']
    knn = skl.KNeighborsClassifier(n_neighbors=5).fit(X, y)
    assert knn.predict([[100.0]]).tolist() == ['a']

def test_knn_stemmelikhet_foerst_i_sortert():
    # 2-2-likhet: sklearn 1.9.0 velger klassen først i sortert classes_
    # (verifisert empirisk) — 'a' slår 'c'
    X = [[0.0], [1.0], [3.0], [4.0]]
    y = ['c', 'c', 'a', 'a']
    knn = skl.KNeighborsClassifier(n_neighbors=4).fit(X, y)
    assert knn.predict([[2.0]]).tolist() == ['a']

def test_knn_score():
    X = [[0.0], [1.0], [10.0], [11.0]]
    y = [0, 0, 1, 1]
    knn = skl.KNeighborsClassifier(n_neighbors=1).fit(X, y)
    assert knn.score([[0.5], [10.5], [0.4]], [0, 1, 1]) == \
        pytest.approx(2.0 / 3.0)

def test_knn_k_storre_enn_n():
    with pytest.raises(ValueError, match='antall treningsrader'):
        skl.KNeighborsClassifier(n_neighbors=4).fit([[1.0], [2.0]], [0, 1])


# ── metrikker (håndregnede fasiter) ─────────────────────────────────────────

def test_accuracy_haandregnet():
    assert skl.accuracy_score([1, 0, 1, 1], [1, 1, 1, 0]) == 0.5
    assert skl.accuracy_score(['a', 'b'], ['a', 'b']) == 1.0

def test_confusion_matrix_haandregnet():
    m = skl.confusion_matrix(['b', 'a', 'b'], ['a', 'a', 'b'])
    # labels sortert ['a', 'b']; rader = sanne klasser
    assert m.tolist() == [[1, 0], [1, 1]]
    assert m.shape == (2, 2)

def test_confusion_matrix_union_av_labels():
    m = skl.confusion_matrix([0, 0], [1, 2])   # y_pred har nye klasser
    assert m.tolist() == [[0, 1, 1], [0, 0, 0], [0, 0, 0]]

def test_mse_haandregnet():
    assert skl.mean_squared_error([1, 2, 3], [2, 2, 4]) == \
        pytest.approx(2.0 / 3.0)

def test_r2_haandregnet():
    assert skl.r2_score([1, 2, 3], [1, 2, 3]) == 1.0
    # snitt-prediksjon: SS_res == SS_tot -> 0.0
    assert skl.r2_score([1, 2, 3], [2, 2, 2]) == 0.0

def test_r2_konstant_y_true_som_sklearn():
    # sklearn: 0.0 (med warning) ved konstant y_true og imperfekt prediksjon,
    # 1.0 ved perfekt — aldri rå ZeroDivisionError
    assert skl.r2_score([3, 3, 3], [3, 3, 4]) == 0.0
    assert skl.r2_score([3, 3, 3], [3, 3, 3]) == 1.0

def test_metrikker_ulik_lengde():
    for fn in (skl.accuracy_score, skl.confusion_matrix,
               skl.mean_squared_error, skl.r2_score):
        with pytest.raises(ValueError, match='ulik lengde'):
            fn([1, 2, 3], [1, 2])
