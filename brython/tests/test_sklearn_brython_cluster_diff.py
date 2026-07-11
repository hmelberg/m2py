# Diff-tester for cluster/decomposition-seksjonen mot EKTE scikit-learn
# (1.9.0). Hoppes over der sklearn ikke er installert (f.eks. i Brython).
#
# Fortegn på PCA-komponenter er en KONVENSJON, ikke matematikk: både vi og
# sklearn kan velge ±v for samme egenvektor. Testene FORTEGNS-JUSTERER derfor
# per komponent (multipliserer med sign av prikkproduktet mot sklearns
# komponent) før sammenlikning.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest

sklearn = pytest.importorskip('sklearn')
import numpy as np                       # ekte numpy (følger med sklearn)
from sklearn.cluster import KMeans as SkKMeans
from sklearn.decomposition import PCA as SkPCA

import sklearn_brython as skl


def _partisjon(labels):
    """Grupper indekser etter label. KMeans-labelnummerering er vilkårlig, så
    vi sammenlikner PARTISJONENE (mengden av klyngeinnhold), ikke tallene."""
    grupper = {}
    for i, lab in enumerate(labels):
        if lab not in grupper:
            grupper[lab] = []
        grupper[lab].append(i)
    return {frozenset(g) for g in grupper.values()}


def _blobs():
    """Tre velseparerte klynger, deterministisk (seedet ekte numpy)."""
    rng = np.random.RandomState(0)
    sentre = np.array([[0.0, 0.0], [8.0, 8.0], [-8.0, 8.0]])
    return np.vstack([sentre[i] + 0.5 * rng.randn(20, 2) for i in range(3)])


def _pca_data():
    """Korrelerte data: 2 latente faktorer i 4 kolonner + litt støy."""
    rng = np.random.RandomState(42)
    Z = rng.randn(40, 2)
    W = np.array([[1.0, 0.5, 0.2, -0.3],
                  [0.0, 1.2, -0.7, 0.4]])
    return Z @ W + 0.05 * rng.randn(40, 4)


# ── KMeans ──────────────────────────────────────────────────────────────────

def test_kmeans_samme_partisjon_som_sklearn():
    X = _blobs()
    vaar = skl.KMeans(n_clusters=3, n_init=10, random_state=0).fit(X.tolist())
    ekte = SkKMeans(n_clusters=3, n_init=10, random_state=0).fit(X)
    assert _partisjon(vaar.labels_.tolist()) == _partisjon(ekte.labels_.tolist())


def test_kmeans_inertia_som_sklearn():
    X = _blobs()
    vaar = skl.KMeans(n_clusters=3, n_init=10, random_state=0).fit(X.tolist())
    ekte = SkKMeans(n_clusters=3, n_init=10, random_state=0).fit(X)
    assert vaar.inertia_ == pytest.approx(float(ekte.inertia_), rel=1e-6)


def test_kmeans_predict_konsistent_med_sklearn():
    X = _blobs()
    vaar = skl.KMeans(n_clusters=3, n_init=10, random_state=0).fit(X.tolist())
    ekte = SkKMeans(n_clusters=3, n_init=10, random_state=0).fit(X)
    # bygg permutasjonsmappingen vår-label → sklearn-label fra treningsdataene
    # (veldefinert fordi partisjonene er like, jf. testen over)
    vl = vaar.labels_.tolist()
    el = ekte.labels_.tolist()
    mapping = {}
    for v, e in zip(vl, el):
        assert mapping.get(v, e) == e   # konsistent mapping
        mapping[v] = e
    nye = [[0.2, -0.1], [7.5, 8.3], [-8.2, 7.9], [4.0, 4.0]]
    vaar_pred = vaar.predict(nye).tolist()
    ekte_pred = ekte.predict(np.array(nye)).tolist()
    assert [mapping[v] for v in vaar_pred] == ekte_pred


# ── PCA ─────────────────────────────────────────────────────────────────────

def _fortegn(vaare_komponenter, ekte_komponenter):
    """Fortegnsvektor per komponent: sign av prikkproduktet mot sklearns
    komponent. Fortegn er konvensjon (±v er samme egenvektor)."""
    tegn = np.sign(np.sum(vaare_komponenter * ekte_komponenter, axis=1))
    tegn[tegn == 0] = 1.0
    return tegn


def test_pca_components_som_sklearn():
    X = _pca_data()
    vaar = skl.PCA(n_components=3).fit(X.tolist())
    ekte = SkPCA(n_components=3).fit(X)
    vc = np.array(vaar.components_.tolist())
    ec = ekte.components_
    vc = vc * _fortegn(vc, ec)[:, None]   # fortegns-justert
    assert float(np.max(np.abs(vc - ec))) < 1e-6


def test_pca_forklart_varians_som_sklearn():
    X = _pca_data()
    vaar = skl.PCA(n_components=3).fit(X.tolist())
    ekte = SkPCA(n_components=3).fit(X)
    dv = np.abs(np.array(vaar.explained_variance_.tolist())
                - ekte.explained_variance_)
    dr = np.abs(np.array(vaar.explained_variance_ratio_.tolist())
                - ekte.explained_variance_ratio_)
    assert float(np.max(dv)) < 1e-8
    assert float(np.max(dr)) < 1e-8


def test_pca_transform_som_sklearn():
    X = _pca_data()
    vaar = skl.PCA(n_components=3).fit(X.tolist())
    ekte = SkPCA(n_components=3).fit(X)
    tegn = _fortegn(np.array(vaar.components_.tolist()), ekte.components_)
    vt = np.array(vaar.transform(X.tolist()).tolist()) * tegn[None, :]
    et = ekte.transform(X)
    assert float(np.max(np.abs(vt - et))) < 1e-6


def test_pca_alle_komponenter_som_sklearn():
    # n_components=None → min(n, p) komponenter, ratio summerer til 1
    X = _pca_data()
    vaar = skl.PCA().fit(X.tolist())
    ekte = SkPCA().fit(X)
    assert vaar.n_components_ == ekte.n_components_
    dr = np.abs(np.array(vaar.explained_variance_ratio_.tolist())
                - ekte.explained_variance_ratio_)
    assert float(np.max(dr)) < 1e-8
