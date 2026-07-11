# sklearn_brython.py — sklearn-subsett for Brython-modus (openstat/safestat).
# Ren Python over lister; predict/transform returnerer numpy_brython-arrays så
# boolske masker og .tolist() virker som i ekte sklearn ved undervisningsskala.
# Diff-testet mot scikit-learn 1.9.0 (brython/tests/test_sklearn_brython_*).
#
# Monteres fra seksjonsfiler (_skl_helpers + _skl_part_linear + _skl_part_cluster
# + _skl_part_core + namespaces) — én fil i repoet, sklearn_brython.py.
import random as _random
import numpy_brython as _np


def _as_matrix(X):
    """Koersér X (DataFrame/ndarray/liste-av-lister/1D-liste) til liste-av-
    lister med floats. 1D-input blir én kolonne (n,1)."""
    v = getattr(X, 'values', None)
    if v is not None and not callable(v):
        X = v                      # pandas_brython DataFrame/Series .values
    if hasattr(X, 'tolist'):
        X = X.tolist()             # numpy_brython ndarray
    X = list(X)
    if not X:
        raise ValueError('sklearn_brython: tomt datasett')
    forste = X[0]
    if hasattr(forste, 'tolist'):
        X = [r.tolist() for r in X]
        forste = X[0]
    if not isinstance(forste, (list, tuple)):
        return [[float(x)] for x in X]
    ut = []
    for r in X:
        rad = [float(x) for x in r]
        if len(rad) != len(X[0]):
            raise ValueError('sklearn_brython: radene i X har ulik lengde')
        ut.append(rad)
    return ut


def _as_vector(y):
    """Koersér y (Series/ndarray/liste) til en flat liste (verdier urørte)."""
    v = getattr(y, 'values', None)
    if v is not None and not callable(v):
        y = v
    if hasattr(y, 'tolist'):
        y = y.tolist()
    y = list(y)
    if not y:
        raise ValueError('sklearn_brython: tom målvektor')
    return y


def _check_len(X, y):
    if len(X) != len(y):
        raise ValueError('sklearn_brython: X og y har ulikt antall rader '
                         '(%d != %d)' % (len(X), len(y)))


def _check_fitted(est, attr):
    if getattr(est, attr, None) is None:
        raise ValueError('sklearn_brython: %s er ikke tilpasset ennå — kall '
                         'fit() først' % est.__class__.__name__)


def _solve(A, b):
    """Løs A x = b (Gauss-Jordan med partiell pivotering). A: n×n, b: n."""
    n = len(A)
    M = [list(A[i]) + [float(b[i])] for i in range(n)]
    for col in range(n):
        p = col
        for r in range(col + 1, n):
            if abs(M[r][col]) > abs(M[p][col]):
                p = r
        if M[p][col] == 0:
            raise ValueError('sklearn_brython: singulær matrise — kolonnene '
                             'er lineært avhengige (fjern duplikat/konstant kolonne)')
        M[col], M[p] = M[p], M[col]
        piv = M[col][col]
        M[col] = [x / piv for x in M[col]]
        for r in range(n):
            if r != col and M[r][col] != 0:
                f = M[r][col]
                M[r] = [a - f * c for a, c in zip(M[r], M[col])]
    return [M[i][n] for i in range(n)]
# ── linear_model ────────────────────────────────────────────────────────────
# LinearRegression via normalligninger, LogisticRegression (kun binær) via
# Newton–Raphson med sklearns L2-parametrisering: objektivet er
# 0.5·w'w + C·Σ log(1 + exp(−ỹᵢ·zᵢ)) der C er INVERS regulariseringsstyrke
# og intercept IKKE straffes (verifisert empirisk mot scikit-learn 1.9.0 i
# brython/tests/test_sklearn_brython_linear_diff.py).
#
# Delta mot ekte sklearn:
#   * Singulær X (lineært avhengige kolonner) gir norsk ValueError fra _solve;
#     ekte sklearn gir minimum-norm-løsning via lstsq/SVD.
#   * LogisticRegression støtter kun to klasser (ingen multinomial/OvR).
#
# NB Brython-feller: ingen metode deler navn med en modulnivå-funksjon her
# (_sigmoid brukes kun fra metoder som heter noe annet); ingen setdefault;
# ingen skygging av builtins på modulnivå.


def _sigmoid(z):
    """Numerisk stabil logistisk funksjon — kan aldri gi overflow."""
    if z >= 0.0:
        return 1.0 / (1.0 + _np.exp(-z))
    e = _np.exp(z)
    return e / (1.0 + e)


def _design(M, fit_intercept):
    """Designmatrise: intercept-kolonne (1.0) først når fit_intercept."""
    if fit_intercept:
        return [[1.0] + list(r) for r in M]
    return [list(r) for r in M]


def _xtx_xty(D, yv, p):
    """X'X (symmetrisk, bygges som øvre trekant) og X'y som rene lister."""
    XtX = [[0.0] * p for _ in range(p)]
    Xty = [0.0] * p
    for i in range(len(D)):
        ri = D[i]
        yi = yv[i]
        for a in range(p):
            ra = ri[a]
            Xty[a] += ra * yi
            for b in range(a, p):
                XtX[a][b] += ra * ri[b]
    for a in range(p):
        for b in range(a + 1, p):
            XtX[b][a] = XtX[a][b]
    return XtX, Xty


class LinearRegression:
    """Minste kvadraters lineær regresjon via normalligninger (X'X)β = X'y.

    Attributter etter fit: coef_ (1D-array uten intercept), intercept_ (float,
    0.0 når fit_intercept=False)."""

    def __init__(self, fit_intercept=True):
        self.fit_intercept = fit_intercept
        self.coef_ = None
        self.intercept_ = None

    def fit(self, X, y):
        M = _as_matrix(X)
        yv = [float(v) for v in _as_vector(y)]
        _check_len(M, yv)
        D = _design(M, self.fit_intercept)
        p = len(D[0])
        XtX, Xty = _xtx_xty(D, yv, p)
        beta = _solve(XtX, Xty)          # singulær X -> norsk ValueError
        if self.fit_intercept:
            self.intercept_ = float(beta[0])
            self.coef_ = _np.array([float(v) for v in beta[1:]])
        else:
            self.intercept_ = 0.0
            self.coef_ = _np.array([float(v) for v in beta])
        return self

    def predict(self, X):
        _check_fitted(self, 'coef_')
        M = _as_matrix(X)
        w = self.coef_.tolist()
        if len(M[0]) != len(w):
            raise ValueError('sklearn_brython: X har %d kolonner, men modellen '
                             'er tilpasset med %d' % (len(M[0]), len(w)))
        b = self.intercept_
        return _np.array([b + sum(wj * xj for wj, xj in zip(w, r)) for r in M])

    def score(self, X, y):
        """R² — samme definisjon som sklearn: 1 − SS_res/SS_tot."""
        _check_fitted(self, 'coef_')
        yv = [float(v) for v in _as_vector(y)]
        yh = self.predict(X).tolist()
        _check_len(yh, yv)
        gj = sum(yv) / len(yv)
        ss_tot = sum((v - gj) ** 2 for v in yv)
        ss_res = sum((v - h) ** 2 for v, h in zip(yv, yh))
        if ss_tot == 0.0:
            # konstant y: som sklearn.r2_score — aldri rå ZeroDivisionError
            return 1.0 if ss_res == 0.0 else 0.0
        return 1.0 - ss_res / ss_tot


class LogisticRegression:
    """Binær logistisk regresjon med L2-regularisering (Newton–Raphson).

    Samme parametrisering som sklearn (lbfgs): min 0.5·w'w + C·Σ log-loss,
    C = invers regulariseringsstyrke, intercept straffes ikke.

    Attributter etter fit: classes_ (sorterte unike labels), coef_ (form
    (1, p)), intercept_ (form (1,)) — som sklearn."""

    def __init__(self, C=1.0, max_iter=100, tol=1e-6, fit_intercept=True):
        self.C = C
        self.max_iter = max_iter
        self.tol = tol
        self.fit_intercept = fit_intercept
        self.classes_ = None
        self.coef_ = None
        self.intercept_ = None

    def fit(self, X, y):
        M = _as_matrix(X)
        labels = _as_vector(y)
        _check_len(M, labels)
        klasser = sorted(set(labels))
        if len(klasser) > 2:
            raise ValueError('sklearn_brython: LogisticRegression — kun binær '
                             'klassifisering støttes (fant %d klasser)'
                             % len(klasser))
        if len(klasser) < 2:
            raise ValueError('sklearn_brython: y inneholder bare én klasse — '
                             'logistisk regresjon trenger to')
        y01 = [1.0 if lab == klasser[1] else 0.0 for lab in labels]
        D = _design(M, self.fit_intercept)
        n = len(D)
        p = len(D[0])
        straff = [1.0] * p
        if self.fit_intercept:
            straff[0] = 0.0                  # intercept straffes ikke
        C = float(self.C)
        beta = [0.0] * p
        for _ in range(int(self.max_iter)):
            # gradient og Hessian for 0.5·w'w + C·Σ log(1+exp(−ỹz))
            g = [straff[a] * beta[a] for a in range(p)]
            H = [[0.0] * p for _ in range(p)]
            for a in range(p):
                H[a][a] = straff[a]
            for i in range(n):
                r = D[i]
                z = sum(bj * xj for bj, xj in zip(beta, r))
                pi = _sigmoid(z)
                dg = C * (pi - y01[i])
                vekt = C * pi * (1.0 - pi)
                for a in range(p):
                    g[a] += dg * r[a]
                    ra = vekt * r[a]
                    for b in range(a, p):
                        H[a][b] += ra * r[b]
            for a in range(p):
                for b in range(a + 1, p):
                    H[b][a] = H[a][b]
            steg = _solve(H, g)
            beta = [bj - sj for bj, sj in zip(beta, steg)]
            if max(abs(sj) for sj in steg) < self.tol:
                break
        if self.fit_intercept:
            self.intercept_ = _np.array([float(beta[0])])
            self.coef_ = _np.array([[float(v) for v in beta[1:]]])
        else:
            self.intercept_ = _np.array([0.0])
            self.coef_ = _np.array([[float(v) for v in beta]])
        self.classes_ = _np.array(klasser)
        return self

    def predict_proba(self, X):
        """(n, 2)-array med P(klasse) i classes_-rekkefølge."""
        _check_fitted(self, 'coef_')
        M = _as_matrix(X)
        w = self.coef_.tolist()[0]
        if len(M[0]) != len(w):
            raise ValueError('sklearn_brython: X har %d kolonner, men modellen '
                             'er tilpasset med %d' % (len(M[0]), len(w)))
        b = float(self.intercept_.tolist()[0])
        ut = []
        for r in M:
            p1 = _sigmoid(b + sum(wj * xj for wj, xj in zip(w, r)))
            ut.append([1.0 - p1, p1])
        return _np.array(ut)

    def predict(self, X):
        """Originale klasselabels; z > 0 gir classes_[1] (som sklearn)."""
        proba = self.predict_proba(X).tolist()
        kl = self.classes_.tolist()
        return _np.array([kl[1] if pr[1] > 0.5 else kl[0] for pr in proba])

    def score(self, X, y):
        """Accuracy — andel riktig klassifiserte."""
        labels = _as_vector(y)
        pred = self.predict(X).tolist()
        _check_len(pred, labels)
        riktige = sum(1 for a, b in zip(pred, labels) if a == b)
        return riktige / len(labels)
# ── cluster/decomposition-seksjon (KMeans, PCA) ─────────────────────────────
# Monteres etter _skl_helpers — bruker _as_matrix, _check_fitted, _np og
# _random derfra (samme modul etter montering, derfor ingen imports her).
#
# NB Brython-feller (se test_brython_scoping_trap.py): ingen metode refererer
# en global med metodens navn (interne hjelpere heter _km_* / _pca_*);
# ingen setdefault; degenerert input gir norsk ValueError, aldri rå
# ZeroDivisionError.


def _km_dist2(a, b):
    """Kvadrert euklidsk avstand mellom to punktlister av lik lengde."""
    s = 0.0
    for i in range(len(a)):
        d = a[i] - b[i]
        s += d * d
    return s


def _km_naermeste(x, sentre):
    """(indeks, kvadrert avstand) til nærmeste senter."""
    best = 0
    bd = _km_dist2(x, sentre[0])
    for c in range(1, len(sentre)):
        d = _km_dist2(x, sentre[c])
        if d < bd:
            bd = d
            best = c
    return best, bd


def _km_vektet_valg(rng, vekter):
    """Trekk indeks proporsjonalt med vekter. Sum 0 (alle punkter identiske
    med sentrene) → uniformt valg, så vi aldri deler på null."""
    total = 0.0
    for w in vekter:
        total += w
    if total <= 0.0:
        return rng.randrange(len(vekter))
    r = rng.random() * total
    akk = 0.0
    for i in range(len(vekter)):
        akk += vekter[i]
        if akk >= r:
            return i
    return len(vekter) - 1


def _km_plusspluss(rng, X, k):
    """k-means++-seeding (Arthur & Vassilvitskii): første senter uniformt,
    deretter proporsjonalt med kvadrert avstand til nærmeste valgte senter."""
    sentre = [list(X[rng.randrange(len(X))])]
    d2 = [_km_dist2(x, sentre[0]) for x in X]
    while len(sentre) < k:
        i = _km_vektet_valg(rng, d2)
        c = list(X[i])
        sentre.append(c)
        for j in range(len(X)):
            d = _km_dist2(X[j], c)
            if d < d2[j]:
                d2[j] = d
    return sentre


def _km_lloyd(X, sentre, max_iter, tol_abs):
    """Lloyd-iterasjon. Tomme klynger re-seedes med punktet lengst fra sitt
    senter (standard praksis). Returnerer (sentre, labels, inertia, n_iter)."""
    n = len(X)
    k = len(sentre)
    p = len(X[0])
    labels = [0] * n
    n_iter = 0
    for it in range(max_iter):
        n_iter = it + 1
        # tilordning
        for i in range(n):
            labels[i], _ = _km_naermeste(X[i], sentre)
        # kolonnesummer per klynge
        antall = [0] * k
        summer = [[0.0] * p for _ in range(k)]
        for i in range(n):
            c = labels[i]
            antall[c] += 1
            rad = summer[c]
            x = X[i]
            for j in range(p):
                rad[j] += x[j]
        # tomme klynger → re-seed med punktet lengst fra sitt senter
        tomme = [c for c in range(k) if antall[c] == 0]
        if tomme:
            avst = [_km_dist2(X[i], sentre[labels[i]]) for i in range(n)]
            brukt = set()
            for c in tomme:
                fjernest = -1.0
                fi = 0
                for i in range(n):
                    if i in brukt:
                        continue
                    if avst[i] > fjernest:
                        fjernest = avst[i]
                        fi = i
                brukt.add(fi)
                gammel = labels[fi]
                antall[gammel] -= 1
                for j in range(p):
                    summer[gammel][j] -= X[fi][j]
                labels[fi] = c
                antall[c] = 1
                summer[c] = list(X[fi])
        # nye sentre + samlet forflytning
        flytt = 0.0
        nye = []
        for c in range(k):
            if antall[c] == 0:      # kan skje hvis re-seed tømte en singleton
                nc = list(sentre[c])
            else:
                nc = [summer[c][j] / antall[c] for j in range(p)]
            flytt += _km_dist2(nc, sentre[c])
            nye.append(nc)
        sentre = nye
        if flytt <= tol_abs:
            break
    # slutt-tilordning og inertia mot de endelige sentrene
    inertia = 0.0
    for i in range(n):
        labels[i], bd = _km_naermeste(X[i], sentre)
        inertia += bd
    return sentre, labels, inertia, n_iter


class KMeans:
    """K-gjennomsnitt-klynging (Lloyds algoritme, k-means++-seeding, beste av
    n_init omstarter målt på inertia). Ren Python — undervisningsskala."""

    def __init__(self, n_clusters=8, *, init='k-means++', n_init=10,
                 max_iter=300, tol=1e-4, random_state=None):
        self.n_clusters = n_clusters
        self.init = init
        self.n_init = n_init
        self.max_iter = max_iter
        self.tol = tol
        self.random_state = random_state
        self.cluster_centers_ = None
        self.labels_ = None
        self.inertia_ = None
        self.n_iter_ = None

    def fit(self, X):
        M = _as_matrix(X)
        n = len(M)
        p = len(M[0])
        k = int(self.n_clusters)
        if k < 1:
            raise ValueError('sklearn_brython: n_clusters må være minst 1 '
                             '(fikk %d)' % k)
        if k > n:
            raise ValueError('sklearn_brython: n_clusters=%d er større enn '
                             'antall rader (%d)' % (k, n))
        if self.init not in ('k-means++', 'random'):
            raise ValueError("sklearn_brython: ukjent init %r — bruk "
                             "'k-means++' eller 'random'" % (self.init,))
        rng = _random.Random(self.random_state)
        # sklearn-stil toleranse: tol * gjennomsnittlig kolonnevarians.
        # Identiske punkter gir 0 → konvergens i første iterasjon, ingen
        # divisjon på null noe sted.
        snittvar = 0.0
        for j in range(p):
            m = 0.0
            for i in range(n):
                m += M[i][j]
            m /= n
            s = 0.0
            for i in range(n):
                d = M[i][j] - m
                s += d * d
            snittvar += s / n
        snittvar /= p
        tol_abs = float(self.tol) * snittvar

        beste = None
        for _omstart in range(max(1, int(self.n_init))):
            if self.init == 'k-means++':
                start = _km_plusspluss(rng, M, k)
            else:
                start = [list(M[i]) for i in rng.sample(range(n), k)]
            resultat = _km_lloyd(M, start, int(self.max_iter), tol_abs)
            if beste is None or resultat[2] < beste[2]:
                beste = resultat
        sentre, labels, inertia, n_iter = beste
        self.cluster_centers_ = _np.array(sentre)
        self.labels_ = _np.array([int(l) for l in labels])
        self.inertia_ = float(inertia)
        self.n_iter_ = int(n_iter)
        return self

    def predict(self, X):
        _check_fitted(self, 'cluster_centers_')
        M = _as_matrix(X)
        sentre = self.cluster_centers_.tolist()
        if len(M[0]) != len(sentre[0]):
            raise ValueError('sklearn_brython: X har %d kolonner, modellen '
                             'ble tilpasset med %d'
                             % (len(M[0]), len(sentre[0])))
        return _np.array([_km_naermeste(x, sentre)[0] for x in M])

    def fit_predict(self, X):
        self.fit(X)
        return self.labels_


def _pca_jacobi(A):
    """Egendekomponering av symmetrisk matrise med syklisk Jacobi-rotasjon
    (NR-stil). Returnerer (egenverdier, V) der kolonne j i V er egenvektoren
    til egenverdi j. Konvergens på Frobenius-normen av off-diagonalen."""
    n = len(A)
    a = [list(rad) for rad in A]
    V = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    if n == 1:
        return [a[0][0]], V
    fro = 0.0
    for i in range(n):
        for j in range(n):
            fro += a[i][j] * a[i][j]
    fro = fro ** 0.5
    if fro == 0.0:                      # nullmatrise — alt er egenvektor
        return [0.0] * n, V
    terskel = 1e-14 * fro
    for _feie in range(100):
        off = 0.0
        for i in range(n - 1):
            for j in range(i + 1, n):
                off += a[i][j] * a[i][j]
        if (2.0 * off) ** 0.5 <= terskel:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if apq == 0.0:
                    continue
                # rotasjonsvinkel: minste rot av t^2 + 2*theta*t - 1 = 0
                theta = (a[q][q] - a[p][p]) / (2.0 * apq)
                if theta >= 0.0:
                    t = 1.0 / (theta + (theta * theta + 1.0) ** 0.5)
                else:
                    t = -1.0 / (-theta + (theta * theta + 1.0) ** 0.5)
                c = 1.0 / (t * t + 1.0) ** 0.5
                s = t * c
                a[p][p] = a[p][p] - t * apq
                a[q][q] = a[q][q] + t * apq
                a[p][q] = 0.0
                a[q][p] = 0.0
                for kk in range(n):
                    if kk != p and kk != q:
                        akp = a[kk][p]
                        akq = a[kk][q]
                        a[kk][p] = c * akp - s * akq
                        a[kk][q] = s * akp + c * akq
                        a[p][kk] = a[kk][p]
                        a[q][kk] = a[kk][q]
                for kk in range(n):
                    vkp = V[kk][p]
                    vkq = V[kk][q]
                    V[kk][p] = c * vkp - s * vkq
                    V[kk][q] = s * vkp + c * vkq
    return [a[i][i] for i in range(n)], V


class PCA:
    """Prinsipalkomponentanalyse via egendekomponering av kovariansmatrisen
    (ddof=1, som sklearn). Fortegn per komponent følger sklearns
    svd_flip-konvensjon: elementet med størst absoluttverdi gjøres positivt.
    Fortegnet er en KONVENSJON, ikke matematikk — diff-tester justerer det."""

    def __init__(self, n_components=None):
        self.n_components = n_components
        self.mean_ = None
        self.components_ = None
        self.explained_variance_ = None
        self.explained_variance_ratio_ = None
        self.n_components_ = None

    def fit(self, X):
        M = _as_matrix(X)
        n = len(M)
        p = len(M[0])
        if n < 2:
            raise ValueError('sklearn_brython: PCA krever minst 2 rader '
                             '(fikk %d) — kovarians med ddof=1' % n)
        k = self.n_components
        if k is None:
            k = min(n, p)
        k = int(k)
        if k < 1:
            raise ValueError('sklearn_brython: n_components må være minst 1 '
                             '(fikk %d)' % k)
        if k > p:
            raise ValueError('sklearn_brython: n_components=%d er større enn '
                             'antall kolonner (%d)' % (k, p))
        # sentrer
        snitt = [0.0] * p
        for i in range(n):
            for j in range(p):
                snitt[j] += M[i][j]
        for j in range(p):
            snitt[j] /= n
        Xc = [[M[i][j] - snitt[j] for j in range(p)] for i in range(n)]
        # kovariansmatrise (ddof=1, som sklearn)
        C = [[0.0] * p for _ in range(p)]
        for a in range(p):
            for b in range(a, p):
                s = 0.0
                for i in range(n):
                    s += Xc[i][a] * Xc[i][b]
                s /= (n - 1)
                C[a][b] = s
                C[b][a] = s
        totalvar = 0.0
        for j in range(p):
            totalvar += C[j][j]
        if totalvar <= 0.0:
            raise ValueError('sklearn_brython: PCA krever variasjon i '
                             'dataene — alle radene er like')
        egenverdier, V = _pca_jacobi(C)
        rekkefolge = sorted(range(p), key=lambda j: egenverdier[j],
                            reverse=True)
        komponenter = []
        varians = []
        for idx in rekkefolge[:k]:
            v = [V[r][idx] for r in range(p)]
            # svd_flip-stil fortegn: største |element| gjøres positivt
            mi = 0
            stor = 0.0
            for j in range(p):
                aj = v[j] if v[j] >= 0 else -v[j]
                if aj > stor:
                    stor = aj
                    mi = j
            if v[mi] < 0:
                v = [-x for x in v]
            komponenter.append(v)
            ev = egenverdier[idx]
            varians.append(ev if ev > 0.0 else 0.0)  # klipp numerisk støy
        self.mean_ = _np.array(snitt)
        self.components_ = _np.array(komponenter)
        self.explained_variance_ = _np.array(varians)
        self.explained_variance_ratio_ = _np.array(
            [ev / totalvar for ev in varians])
        self.n_components_ = k
        return self

    def transform(self, X):
        _check_fitted(self, 'components_')
        M = _as_matrix(X)
        snitt = self.mean_.tolist()
        komponenter = self.components_.tolist()
        p = len(snitt)
        if len(M[0]) != p:
            raise ValueError('sklearn_brython: X har %d kolonner, PCA ble '
                             'tilpasset med %d' % (len(M[0]), p))
        ut = []
        for rad in M:
            c = [rad[j] - snitt[j] for j in range(p)]
            ut.append([sum(c[j] * komp[j] for j in range(p))
                       for komp in komponenter])
        return _np.array(ut)

    def fit_transform(self, X):
        self.fit(X)
        return self.transform(X)

    def inverse_transform(self, X):
        _check_fitted(self, 'components_')
        M = _as_matrix(X)
        snitt = self.mean_.tolist()
        komponenter = self.components_.tolist()
        k = len(komponenter)
        p = len(snitt)
        if len(M[0]) != k:
            raise ValueError('sklearn_brython: X har %d kolonner, forventet '
                             '%d komponenter' % (len(M[0]), k))
        ut = []
        for rad in M:
            ut.append([snitt[j] + sum(rad[c] * komponenter[c][j]
                                      for c in range(k))
                       for j in range(p)])
        return _np.array(ut)
# ── kjerne: model_selection / preprocessing / neighbors / metrics ──────────
# Seksjonsfil for sklearn_brython — monteres etter _skl_helpers, så _np,
# _random, _as_matrix, _as_vector, _check_len, _check_fitted er tilgjengelige
# på modulnivå. INGEN imports her.
#
# NB Brython-feller (se test_brython_scoping_trap.py): ingen metode heter likt
# som en modulnivåfunksjon den refererer (score/transform kolliderer ikke med
# noe modulnivånavn; accuracy_score kalles via aliaset _accuracy nederst);
# ingen setdefault med ikke-streng-nøkler (tellerne bruker `if k not in d`).


def _rows_in(a):
    """Antall rader i et array-aktig objekt (DataFrame/Series/ndarray/liste)."""
    try:
        return len(a)
    except TypeError:
        return len(list(a))


def _take_rows(a, idx):
    """Radsubsett som BEVARER containertypen:
    pandas_brython DataFrame/Series -> samme type (via .iloc),
    numpy_brython ndarray -> ndarray, liste/tuppel -> liste."""
    iloc = getattr(a, 'iloc', None)
    if iloc is not None:
        return iloc[list(idx)]           # pandas_brython: DataFrame/Series ut
    if hasattr(a, 'tolist'):
        rows = a.tolist()                # numpy_brython ndarray
        return _np.array([rows[i] for i in idx])
    seq = list(a)
    return [seq[i] for i in idx]


def _split_sizes(n, test_size, train_size):
    """Størrelsessemantikk som sklearn: float-andel -> n_test = ceil(n*andel),
    n_train = floor(n*andel); heltall = antall rader; default test_size=0.25
    når begge er None; den som mangler blir resten."""
    if test_size is None and train_size is None:
        test_size = 0.25
    n_test = None
    n_train = None
    if test_size is not None:
        if isinstance(test_size, float):
            if not 0.0 < test_size < 1.0:
                raise ValueError('sklearn_brython: test_size som andel må '
                                 'ligge mellom 0 og 1 (fikk %r)' % test_size)
            t = n * test_size
            n_test = int(t)              # ceil uten math-import
            if n_test < t:
                n_test += 1
        else:
            n_test = int(test_size)
    if train_size is not None:
        if isinstance(train_size, float):
            if not 0.0 < train_size < 1.0:
                raise ValueError('sklearn_brython: train_size som andel må '
                                 'ligge mellom 0 og 1 (fikk %r)' % train_size)
            n_train = int(n * train_size)  # floor, som sklearn
        else:
            n_train = int(train_size)
    if n_test is None:
        n_test = n - n_train
    if n_train is None:
        n_train = n - n_test
    if n_train < 1 or n_test < 1 or n_train + n_test > n:
        raise ValueError('sklearn_brython: ugyldig splitt — train=%d og '
                         'test=%d går ikke opp i n=%d rader'
                         % (n_train, n_test, n))
    return n_train, n_test


def train_test_split(*arrays, test_size=None, train_size=None,
                     random_state=None, shuffle=True, stratify=None):
    """Del arrays i train/test. Returrekkefølge som sklearn:
    a_train, a_test, b_train, b_test, ...

    Egen RNG (_random.Random(random_state)): samme seed gir samme splitt på
    tvers av kjøringer HER, men IKKE samme permutasjon som ekte sklearn
    (sklearn bruker numpy sin RNG) — bare størrelsene matcher eksakt."""
    if stratify is not None:
        raise NotImplementedError('sklearn_brython: stratify støttes ikke '
                                  'ennå — bruk stratify=None')
    if not arrays:
        raise ValueError('sklearn_brython: train_test_split trenger minst '
                         'ett array')
    n = _rows_in(arrays[0])
    for a in arrays[1:]:
        if _rows_in(a) != n:
            raise ValueError('sklearn_brython: arrayene har ulikt antall '
                             'rader (%d != %d)' % (n, _rows_in(a)))
    n_train, n_test = _split_sizes(n, test_size, train_size)
    idx = list(range(n))
    if shuffle:
        rng = _random.Random(random_state)
        rng.shuffle(idx)
        test_idx = idx[:n_test]
        train_idx = idx[n_test:n_test + n_train]
    else:
        train_idx = idx[:n_train]
        test_idx = idx[n_train:n_train + n_test]
    ut = []
    for a in arrays:
        ut.append(_take_rows(a, train_idx))
        ut.append(_take_rows(a, test_idx))
    return ut


# ── preprocessing ───────────────────────────────────────────────────────────

class StandardScaler:
    """Standardiser kolonner: (x - mean_) / scale_. mean_/var_ med ddof=0;
    scale_ = sqrt(var_), men konstant kolonne (var 0) får scale 1.0 som
    sklearn, så transform gir 0 i stedet for deling på null."""

    def __init__(self, with_mean=True, with_std=True):
        self.with_mean = with_mean
        self.with_std = with_std
        self.mean_ = None
        self.var_ = None
        self.scale_ = None
        self.n_features_in_ = None

    def fit(self, X, y=None):
        M = _as_matrix(X)
        n = len(M)
        p = len(M[0])
        self.n_features_in_ = p
        self.mean_ = [sum(rad[j] for rad in M) / n for j in range(p)]
        self.var_ = [sum((rad[j] - self.mean_[j]) ** 2 for rad in M) / n
                     for j in range(p)]
        if self.with_std:
            self.scale_ = [v ** 0.5 if v > 0.0 else 1.0 for v in self.var_]
        else:
            self.scale_ = None           # som sklearn ved with_std=False
        return self

    def transform(self, X):
        _check_fitted(self, 'n_features_in_')
        M = _as_matrix(X)
        if M and len(M[0]) != self.n_features_in_:
            raise ValueError('sklearn_brython: X har %d kolonner, men '
                             'skaleren ble tilpasset med %d'
                             % (len(M[0]), self.n_features_in_))
        m = self.mean_ if self.with_mean else [0.0] * self.n_features_in_
        s = self.scale_ if self.with_std else [1.0] * self.n_features_in_
        return _np.array([[(rad[j] - m[j]) / s[j]
                           for j in range(self.n_features_in_)] for rad in M])

    def fit_transform(self, X, y=None):
        self.fit(X)
        return self.transform(X)

    def inverse_transform(self, X):
        _check_fitted(self, 'n_features_in_')
        M = _as_matrix(X)
        m = self.mean_ if self.with_mean else [0.0] * self.n_features_in_
        s = self.scale_ if self.with_std else [1.0] * self.n_features_in_
        return _np.array([[rad[j] * s[j] + m[j]
                           for j in range(self.n_features_in_)] for rad in M])


# ── neighbors ───────────────────────────────────────────────────────────────

class KNeighborsClassifier:
    """k nærmeste naboer (euklidsk avstand, uniform flertallsvotering).
    Ved stemmelikhet vinner klassen som kommer først i sortert classes_ —
    verifisert empirisk mot sklearn 1.9.0 (sklearn tar mode over
    label-indekser i sortert classes_, og argmax tar første ved likhet).
    Ved AVSTANDS-likhet på k-grensen er sklearn (argpartition) udefinert,
    så diff-testene bruker likhetsfrie fixtures."""

    def __init__(self, n_neighbors=5):
        self.n_neighbors = n_neighbors
        self.classes_ = None
        self.n_features_in_ = None
        self._X = None
        self._y = None

    def fit(self, X, y):
        M = _as_matrix(X)
        yv = _as_vector(y)
        _check_len(M, yv)
        if self.n_neighbors < 1:
            raise ValueError('sklearn_brython: n_neighbors må være minst 1 '
                             '(fikk %r)' % self.n_neighbors)
        if self.n_neighbors > len(M):
            raise ValueError('sklearn_brython: n_neighbors=%d er større enn '
                             'antall treningsrader (%d) — velg mindre k'
                             % (self.n_neighbors, len(M)))
        self._X = M
        self._y = yv
        self.classes_ = sorted(set(yv))
        self.n_features_in_ = len(M[0])
        return self

    def predict(self, X):
        _check_fitted(self, 'classes_')
        M = _as_matrix(X)
        if M and len(M[0]) != self.n_features_in_:
            raise ValueError('sklearn_brython: X har %d kolonner, men '
                             'modellen ble tilpasset med %d'
                             % (len(M[0]), self.n_features_in_))
        k = self.n_neighbors
        preds = []
        for q in M:
            d2 = [sum((a - b) ** 2 for a, b in zip(rad, q))
                  for rad in self._X]
            naermeste = sorted(range(len(d2)), key=lambda i: (d2[i], i))[:k]
            teller = {}
            for i in naermeste:
                lab = self._y[i]
                if lab not in teller:    # ikke setdefault (Brython-felle)
                    teller[lab] = 0
                teller[lab] += 1
            best = None
            best_n = -1
            for c in self.classes_:      # sortert -> først-i-sortert vinner
                n_c = teller[c] if c in teller else 0
                if n_c > best_n:
                    best = c
                    best_n = n_c
            preds.append(best)
        return _np.array(preds)

    def score(self, X, y):
        preds = self.predict(X).tolist()
        return _accuracy(_as_vector(y), preds)


# ── metrics ─────────────────────────────────────────────────────────────────

def _metric_par(y_true, y_pred):
    """Koersér og lengdesjekk et (y_true, y_pred)-par med norsk feilmelding."""
    yt = _as_vector(y_true)
    yp = _as_vector(y_pred)
    if len(yt) != len(yp):
        raise ValueError('sklearn_brython: y_true og y_pred har ulik lengde '
                         '(%d != %d)' % (len(yt), len(yp)))
    return yt, yp


def accuracy_score(y_true, y_pred):
    """Andel riktige: sum(y_true == y_pred) / n."""
    yt, yp = _metric_par(y_true, y_pred)
    return sum(1 for a, b in zip(yt, yp) if a == b) / len(yt)


def confusion_matrix(y_true, y_pred):
    """Forvirringsmatrise som _np 2D-array. Labels = sortert union av
    y_true og y_pred; rader = sanne klasser, kolonner = predikerte."""
    yt, yp = _metric_par(y_true, y_pred)
    labels = sorted(set(yt) | set(yp))
    pos = {}
    for i, lab in enumerate(labels):
        pos[lab] = i
    m = [[0] * len(labels) for _ in labels]
    for a, b in zip(yt, yp):
        m[pos[a]][pos[b]] += 1
    return _np.array(m)


def mean_squared_error(y_true, y_pred):
    """Gjennomsnittlig kvadrert avvik."""
    yt, yp = _metric_par(y_true, y_pred)
    return sum((float(a) - float(b)) ** 2 for a, b in zip(yt, yp)) / len(yt)


def r2_score(y_true, y_pred):
    """R² = 1 - SS_res/SS_tot. Konstant y_true (SS_tot = 0) gir ALDRI rå
    ZeroDivisionError: som sklearn returneres 1.0 ved perfekt prediksjon
    og ellers 0.0 (sklearn gir samme tall med en warning)."""
    yt, yp = _metric_par(y_true, y_pred)
    yt = [float(v) for v in yt]
    yp = [float(v) for v in yp]
    snitt = sum(yt) / len(yt)
    ss_res = sum((a - b) ** 2 for a, b in zip(yt, yp))
    ss_tot = sum((a - snitt) ** 2 for a in yt)
    if ss_tot == 0.0:
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


# Underscore-alias så metoder trygt kan kalle metrikken uten navnekollisjon
# (Brython-felle 1) — KNeighborsClassifier.score bruker denne.
_accuracy = accuracy_score


# ── Namespace-objekter: `from sklearn import cluster` osv. i CPython-tester.
# I nettleseren overskriver _alias_module attributtene med selve modulen
# (flat — samme navn), så begge veier virker.
class _NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


model_selection = _NS(train_test_split=train_test_split)
preprocessing = _NS(StandardScaler=StandardScaler)
linear_model = _NS(LinearRegression=LinearRegression,
                   LogisticRegression=LogisticRegression)
cluster = _NS(KMeans=KMeans)
decomposition = _NS(PCA=PCA)
neighbors = _NS(KNeighborsClassifier=KNeighborsClassifier)
metrics = _NS(accuracy_score=accuracy_score, confusion_matrix=confusion_matrix,
              mean_squared_error=mean_squared_error, r2_score=r2_score)
