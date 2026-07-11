# Enhetstester for cluster/decomposition-seksjonen (KMeans, PCA) i
# sklearn_brython. Ren Python — trenger ikke ekte sklearn/numpy.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest
import sklearn_brython as skl
import numpy_brython as np
import pandas_brython as pd


# Deterministisk fixture: tre velseparerte klynger som eksplisitte tallister.
BLOBS = [
    [0.0, 0.0], [0.2, 0.1], [-0.1, 0.2], [0.1, -0.2],
    [10.0, 10.0], [10.2, 9.9], [9.8, 10.1], [10.1, 10.2],
    [-10.0, 10.0], [-9.8, 10.2], [-10.2, 9.9], [-10.1, 10.1],
]
FASIT_PARTISJON = {frozenset(range(0, 4)), frozenset(range(4, 8)),
                   frozenset(range(8, 12))}

# Klassisk PCA-eksempel (Lindsay Smith-tutorialen) — to korrelerte kolonner.
XPCA = [
    [2.5, 2.4], [0.5, 0.7], [2.2, 2.9], [1.9, 2.2], [3.1, 3.0],
    [2.3, 2.7], [2.0, 1.6], [1.0, 1.1], [1.5, 1.6], [1.1, 0.9],
]


def _partisjon(labels):
    """Grupper indekser etter label — sammenlikner klyngeINNHOLD, ikke
    label-tallene (labelnummerering er vilkårlig)."""
    grupper = {}
    for i, lab in enumerate(labels):
        if lab not in grupper:
            grupper[lab] = []
        grupper[lab].append(i)
    return {frozenset(g) for g in grupper.values()}


# ── KMeans ──────────────────────────────────────────────────────────────────

def test_kmeans_finner_tre_klynger():
    km = skl.KMeans(n_clusters=3, random_state=0).fit(BLOBS)
    assert _partisjon(km.labels_.tolist()) == FASIT_PARTISJON
    assert isinstance(km.inertia_, float)
    assert 0.0 < km.inertia_ < 1.0          # tette klynger → liten inertia
    assert isinstance(km.n_iter_, int) and km.n_iter_ >= 1
    sentre = km.cluster_centers_.tolist()
    assert len(sentre) == 3 and len(sentre[0]) == 2
    # sentrene skal ligge nær (0,0), (10,10) og (-10,10) i en eller annen orden
    grov = sorted((round(c[0]), round(c[1])) for c in sentre)
    assert grov == [(-10, 10), (0, 0), (10, 10)]


def test_kmeans_fit_predict_lik_labels():
    km = skl.KMeans(n_clusters=3, random_state=1)
    fp = km.fit_predict(BLOBS)
    assert fp.tolist() == km.labels_.tolist()


def test_kmeans_predict_nye_punkter():
    km = skl.KMeans(n_clusters=3, random_state=0).fit(BLOBS)
    nye = km.predict([[0.05, 0.05], [9.9, 9.95], [-10.05, 10.05]])
    labels = km.labels_.tolist()
    # nytt punkt nær hver klynge skal få samme label som klyngens medlemmer
    assert nye.tolist() == [labels[0], labels[4], labels[8]]


def test_kmeans_samme_random_state_identisk():
    a = skl.KMeans(n_clusters=3, random_state=42).fit(BLOBS)
    b = skl.KMeans(n_clusters=3, random_state=42).fit(BLOBS)
    assert a.labels_.tolist() == b.labels_.tolist()
    assert a.cluster_centers_.tolist() == b.cluster_centers_.tolist()
    assert a.inertia_ == b.inertia_


def test_kmeans_init_random():
    km = skl.KMeans(n_clusters=3, init='random', random_state=0).fit(BLOBS)
    assert _partisjon(km.labels_.tolist()) == FASIT_PARTISJON


def test_kmeans_dataframe_og_ndarray_input():
    df = pd.DataFrame({'x': [r[0] for r in BLOBS],
                       'y': [r[1] for r in BLOBS]})
    arr = np.array(BLOBS)
    for X in (df, arr):
        km = skl.KMeans(n_clusters=3, random_state=0).fit(X)
        assert _partisjon(km.labels_.tolist()) == FASIT_PARTISJON


def test_kmeans_identiske_punkter_krasjer_ikke():
    # degenerert input skal ikke gi rå ZeroDivisionError (Brython-felle 4)
    km = skl.KMeans(n_clusters=2, random_state=0).fit([[1.0, 1.0]] * 5)
    assert km.inertia_ == 0.0
    assert len(km.labels_.tolist()) == 5


def test_kmeans_for_mange_klynger():
    with pytest.raises(ValueError, match='n_clusters'):
        skl.KMeans(n_clusters=13).fit(BLOBS)      # 13 > 12 rader


def test_kmeans_ukjent_init():
    with pytest.raises(ValueError, match='init'):
        skl.KMeans(n_clusters=2, init='fancy').fit(BLOBS)


def test_kmeans_predict_foer_fit():
    with pytest.raises(ValueError, match='fit'):
        skl.KMeans(n_clusters=2).predict(BLOBS)


# ── PCA ─────────────────────────────────────────────────────────────────────

def test_pca_rekonstruksjon():
    p = skl.PCA()
    Xt = p.fit_transform(XPCA)
    Xr = p.inverse_transform(Xt).tolist()
    for rad, fasit in zip(Xr, XPCA):
        for v, f in zip(rad, fasit):
            assert v == pytest.approx(f, abs=1e-8)
    # fit_transform skal være lik fit + transform
    Xt2 = skl.PCA().fit(XPCA).transform(XPCA)
    for r1, r2 in zip(Xt.tolist(), Xt2.tolist()):
        for v1, v2 in zip(r1, r2):
            assert v1 == pytest.approx(v2, abs=1e-12)


def test_pca_forklart_varians():
    p = skl.PCA().fit(XPCA)
    assert p.n_components_ == 2
    ratio = p.explained_variance_ratio_.tolist()
    assert sum(ratio) <= 1.0 + 1e-9
    assert sum(ratio) == pytest.approx(1.0, abs=1e-9)   # alle komponenter med
    assert ratio == sorted(ratio, reverse=True)          # synkende
    ev = p.explained_variance_.tolist()
    assert ev == sorted(ev, reverse=True)
    assert all(v >= 0.0 for v in ev)
    # kjent fasit for dette datasettet: første komponent forklarer ~96 %
    assert ratio[0] > 0.9


def test_pca_n_components_1():
    p = skl.PCA(n_components=1).fit(XPCA)
    Xt = p.transform(XPCA).tolist()
    assert len(Xt) == 10 and len(Xt[0]) == 1
    assert p.n_components_ == 1
    assert len(p.explained_variance_ratio_.tolist()) == 1
    assert p.explained_variance_ratio_.tolist()[0] <= 1.0 + 1e-9


def test_pca_fortegnskonvensjon():
    # svd_flip-stil: største |element| i hver komponent skal være positivt.
    # Fortegn er en konvensjon, ikke matematikk.
    p = skl.PCA().fit(XPCA)
    for komp in p.components_.tolist():
        assert max(komp, key=abs) > 0


def test_pca_dataframe_og_ndarray_input():
    fasit = skl.PCA().fit(XPCA).components_.tolist()
    df = pd.DataFrame({'x': [r[0] for r in XPCA],
                       'y': [r[1] for r in XPCA]})
    arr = np.array(XPCA)
    for X in (df, arr):
        komp = skl.PCA().fit(X).components_.tolist()
        for r1, r2 in zip(komp, fasit):
            for v1, v2 in zip(r1, r2):
                assert v1 == pytest.approx(v2, abs=1e-12)


def test_pca_for_mange_komponenter():
    with pytest.raises(ValueError, match='n_components'):
        skl.PCA(n_components=3).fit(XPCA)         # bare 2 kolonner


def test_pca_en_rad():
    # degenerert input: ddof=1 ville delt på null → norsk ValueError i stedet
    with pytest.raises(ValueError, match='rader'):
        skl.PCA().fit([[1.0, 2.0]])


def test_pca_konstant_data():
    # null varians → norsk ValueError, aldri rå ZeroDivisionError
    with pytest.raises(ValueError, match='variasjon'):
        skl.PCA().fit([[1.0, 2.0]] * 4)


def test_pca_transform_foer_fit():
    with pytest.raises(ValueError, match='fit'):
        skl.PCA().transform(XPCA)
