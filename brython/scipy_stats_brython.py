# scipy_stats_brython — scipy.stats-subsett i ren Python for Brython-modus.
# Importeres som `from scipy import stats` / `import scipy.stats` (aliaser i
# LIB_REGISTRY) eller direkte som scipy_stats_brython.
#
# Kun SKALARE argumenter til fordelingsmetodene (ingen array-broadcasting) —
# undervisningsskala. Numerikk: math.lgamma/erf/erfc (finnes i Brython 3.12,
# spike-verifisert 2026-07-11) + ufullstendig gamma/beta (NR-stil serie +
# modifisert Lentz-kjedebrøk), Acklams invers-normal med én Halley-korreksjon,
# og halveringsinversjon for t/chi2/f sin ppf.
#
# NB Brython-feller (se test_brython_scoping_trap.py): ingen metode refererer
# en global med metodens navn; ingen setdefault med ikke-streng-nøkler.
import math


def _tolist(v):
    """list-ifiser: lister, tupler, range og pandas_brython-Series (duck)."""
    if hasattr(v, 'tolist'):
        return list(v.tolist())
    if hasattr(v, 'values') and not isinstance(v, dict):
        vals = v.values
        return list(vals() if callable(vals) else vals)
    return list(v)


# ── spesialfunksjoner ───────────────────────────────────────────────────────

def _gammainc_p(a, x):
    """Regularisert nedre ufullstendig gamma P(a, x) (NR gammp).
    Nøyaktig til df ~10 000 (chi2); ved ekstreme parametre kan serien
    stoppe før full konvergens."""
    if a <= 0.0 or x < 0.0:
        raise ValueError('gammainc: krever a > 0 og x >= 0')
    if x == 0.0:
        return 0.0
    if x < a + 1.0:
        # serieutvikling
        ap = a
        s = 1.0 / a
        d = s
        for _ in range(500):
            ap += 1.0
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-15:
                break
        return s * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # kjedebrøk for Q(a, x) (modifisert Lentz); P = 1 - Q
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    q = math.exp(-x + a * math.log(x) - math.lgamma(a)) * h
    return 1.0 - q


def _betacf(a, b, x):
    """Kjedebrøken i ufullstendig beta (NR betacf, modifisert Lentz)."""
    tiny = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def _betainc(a, b, x):
    """Regularisert ufullstendig beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_bt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(ln_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _norm_ppf_std(p):
    """Standard-normal invers-CDF: Acklams approksimasjon + én
    Halley-korreksjon (relativ feil ~1e-15)."""
    if p <= 0.0 or p >= 1.0:
        if p == 0.0:
            return float('-inf')
        if p == 1.0:
            return float('inf')
        raise ValueError('ppf: p må ligge i [0, 1]')
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00)
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        x = ((((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
             / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0))
    elif p <= 1.0 - plow:
        q = p - 0.5
        r = q * q
        x = ((((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
             / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0))
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        x = -((((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
              / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0))
    # Halley-korreksjon mot erfc-basert CDF
    e = 0.5 * math.erfc(-x / math.sqrt(2.0)) - p
    u = e * math.sqrt(2.0 * math.pi) * math.exp(x * x / 2.0)
    return x - u / (1.0 + x * u / 2.0)


def _invert_cdf(cdf, p, lo, hi):
    """Numerisk inversjon av en monotont stigende CDF ved halvering.
    hi utvides til cdf(hi) >= p. Nøyaktig for p opp til ~1-1e-9; lengre
    ute i halen degraderer presisjonen (dobbel-presisjon nær 1)."""
    if p <= 0.0 or p >= 1.0:
        if p == 0.0:
            return lo
        if p == 1.0:
            return float('inf')
        raise ValueError('ppf: p må ligge i [0, 1]')
    while cdf(hi) < p:
        hi *= 2.0
        if hi > 1e300:
            break
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if cdf(mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13 * max(1.0, abs(hi)):
            break
    return 0.5 * (lo + hi)


# ── fordelinger (skalar inn/ut; instanser som i scipy) ──────────────────────

_SQRT2 = math.sqrt(2.0)
_SQRT2PI = math.sqrt(2.0 * math.pi)


class _Norm:
    def pdf(self, x, loc=0.0, scale=1.0):
        z = (x - loc) / scale
        return math.exp(-0.5 * z * z) / (scale * _SQRT2PI)

    def cdf(self, x, loc=0.0, scale=1.0):
        z = (x - loc) / scale
        return 0.5 * math.erfc(-z / _SQRT2)

    def sf(self, x, loc=0.0, scale=1.0):
        z = (x - loc) / scale
        return 0.5 * math.erfc(z / _SQRT2)

    def ppf(self, p, loc=0.0, scale=1.0):
        return loc + scale * _norm_ppf_std(p)


class _T:
    def pdf(self, x, df):
        return math.exp(math.lgamma((df + 1.0) / 2.0) - math.lgamma(df / 2.0)
                        - 0.5 * math.log(df * math.pi)
                        - ((df + 1.0) / 2.0) * math.log(1.0 + x * x / df))

    def cdf(self, x, df):
        if x == 0.0:
            return 0.5
        ib = _betainc(df / 2.0, 0.5, df / (df + x * x))
        return 1.0 - 0.5 * ib if x > 0.0 else 0.5 * ib

    def sf(self, x, df):
        return self.cdf(-x, df)          # symmetri

    def ppf(self, p, df):
        if p == 0.5:
            return 0.0
        if p < 0.5:
            return -self.ppf(1.0 - p, df)
        return _invert_cdf(lambda x: self.cdf(x, df), p, 0.0, 10.0)


class _Chi2:
    def pdf(self, x, df):
        if x <= 0.0:
            return 0.0
        return math.exp((df / 2.0 - 1.0) * math.log(x) - x / 2.0
                        - math.lgamma(df / 2.0) - (df / 2.0) * math.log(2.0))

    def cdf(self, x, df):
        if x <= 0.0:
            return 0.0
        return _gammainc_p(df / 2.0, x / 2.0)

    def sf(self, x, df):
        return 1.0 - self.cdf(x, df)

    def ppf(self, p, df):
        return _invert_cdf(lambda x: self.cdf(x, df), p, 0.0, df + 10.0)


class _F:
    def pdf(self, x, dfn, dfd):
        if x <= 0.0:
            return 0.0
        ln_b = (math.lgamma(dfn / 2.0) + math.lgamma(dfd / 2.0)
                - math.lgamma((dfn + dfd) / 2.0))
        return math.exp(0.5 * (dfn * math.log(dfn * x) + dfd * math.log(dfd)
                               - (dfn + dfd) * math.log(dfn * x + dfd))
                        - math.log(x) - ln_b)

    def cdf(self, x, dfn, dfd):
        if x <= 0.0:
            return 0.0
        return _betainc(dfn / 2.0, dfd / 2.0, dfn * x / (dfn * x + dfd))

    def sf(self, x, dfn, dfd):
        return 1.0 - self.cdf(x, dfn, dfd)

    def ppf(self, p, dfn, dfd):
        return _invert_cdf(lambda x: self.cdf(x, dfn, dfd), p, 0.0, 10.0)


norm = _Norm()
t = _T()
chi2 = _Chi2()
f = _F()


# ── hypotesetester ──────────────────────────────────────────────────────────

class TestResult:
    """(statistic, pvalue) — oppfører seg som scipy sitt resultatobjekt:
    attributter + utpakking/indeksering som 2-tuple."""

    def __init__(self, statistic, pvalue):
        self.statistic = statistic
        self.pvalue = pvalue

    def __iter__(self):
        return iter((self.statistic, self.pvalue))

    def __getitem__(self, i):
        return (self.statistic, self.pvalue)[i]

    def __len__(self):
        return 2

    def __repr__(self):
        return 'TestResult(statistic=%r, pvalue=%r)' % (self.statistic, self.pvalue)


def _mean(v):
    return sum(v) / len(v)


def _var(v, ddof=1):
    n = len(v)
    if n - ddof <= 0:
        return float('nan')     # degenerert utvalg — scipy gir nan, ikke krasj
    m = _mean(v)
    return sum((x - m) ** 2 for x in v) / (n - ddof)


def ttest_1samp(a, popmean):
    a = _tolist(a)
    n = len(a)
    se = math.sqrt(_var(a) / n)
    stat = (_mean(a) - popmean) / se if se > 0.0 else float('nan')
    p = 2.0 * t.sf(abs(stat), n - 1) if stat == stat else float('nan')
    return TestResult(stat, p)


def ttest_ind(a, b, equal_var=True):
    a, b = _tolist(a), _tolist(b)
    na, nb = len(a), len(b)
    va, vb = _var(a), _var(b)
    if va != va or vb != vb or (equal_var and na + nb - 2 <= 0):
        return TestResult(float('nan'), float('nan'))
    if equal_var:
        sp = ((na - 1) * va + (nb - 1) * vb) / (na + nb - 2)
        se = math.sqrt(sp * (1.0 / na + 1.0 / nb))
        dof = na + nb - 2
    else:                                # Welch
        se = math.sqrt(va / na + vb / nb)
        if se == 0.0:
            return TestResult(float('nan'), float('nan'))
        dof = ((va / na + vb / nb) ** 2
               / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)))
    stat = (_mean(a) - _mean(b)) / se if se > 0.0 else float('nan')
    p = 2.0 * t.sf(abs(stat), dof) if stat == stat else float('nan')
    return TestResult(stat, p)


def ttest_rel(a, b):
    a, b = _tolist(a), _tolist(b)
    if len(a) != len(b):
        raise ValueError('ttest_rel: like lange utvalg kreves')
    return ttest_1samp([x - y for x, y in zip(a, b)], 0.0)


def pearsonr(x, y):
    x, y = _tolist(x), _tolist(y)
    if len(x) != len(y):
        raise ValueError('pearsonr: like lange utvalg kreves')
    n = len(x)
    mx, my = _mean(x), _mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x)
                    * sum((b - my) ** 2 for b in y))
    r = num / den if den > 0.0 else float('nan')
    r = max(-1.0, min(1.0, r)) if r == r else r
    if n <= 2:
        # scipy: p er udefinert ved dof=0 og settes til 1.0
        p = 1.0 if r == r else float('nan')
    elif r != r or abs(r) == 1.0:
        p = 0.0 if r == r else float('nan')
    else:
        stat = r * math.sqrt((n - 2) / (1.0 - r * r))
        p = 2.0 * t.sf(abs(stat), n - 2)
    return TestResult(r, p)


class Chi2ContingencyResult:
    """Som scipy: attributter + utpakking som (statistic, pvalue, dof,
    expected_freq)."""

    def __init__(self, statistic, pvalue, dof, expected_freq):
        self.statistic = statistic
        self.pvalue = pvalue
        self.dof = dof
        self.expected_freq = expected_freq

    def __iter__(self):
        return iter((self.statistic, self.pvalue, self.dof, self.expected_freq))

    def __getitem__(self, i):
        return (self.statistic, self.pvalue, self.dof, self.expected_freq)[i]

    def __repr__(self):
        return ('Chi2ContingencyResult(statistic=%r, pvalue=%r, dof=%r)'
                % (self.statistic, self.pvalue, self.dof))


def chi2_contingency(observed, correction=True):
    """Kjikvadrat-test for uavhengighet i en krysstabell.
    observed: liste av rader (eller DataFrame — duck-typet på .values).
    correction=True gir Yates-korreksjon for 2x2-tabeller (som scipy)."""
    if hasattr(observed, 'values') and not isinstance(observed, dict):
        vals = observed.values
        observed = vals() if callable(vals) else vals
    rows = [_tolist(r) for r in observed]
    if not rows or not rows[0] or any(len(r) != len(rows[0]) for r in rows):
        raise ValueError('chi2_contingency: tabellen må være rektangulær og ikke tom')
    rsums = [sum(r) for r in rows]
    csums = [sum(c) for c in zip(*rows)]
    total = float(sum(rsums))
    if total <= 0.0:
        raise ValueError('chi2_contingency: tom tabell')
    expected = [[rs * cs / total for cs in csums] for rs in rsums]
    for re_ in expected:
        for e in re_:
            if e == 0.0:
                raise ValueError('chi2_contingency: forventet frekvens er 0 — '
                                 'fjern tomme rader/kolonner fra tabellen')
    dof = (len(rows) - 1) * (len(csums) - 1)
    use_yates = correction and len(rows) == 2 and len(csums) == 2
    stat = 0.0
    for ro, re_ in zip(rows, expected):
        for o, e in zip(ro, re_):
            d = abs(o - e)
            if use_yates:
                d = max(0.0, d - 0.5)
            stat += d * d / e
    p = chi2.sf(stat, dof) if dof > 0 else 1.0
    return Chi2ContingencyResult(stat, p, dof, expected)


def mannwhitneyu(x, y, alternative='two-sided'):
    """Mann-Whitney U (asymptotisk normaltilnærming med midtrang for
    uavgjorte, tie-korrigert varians og kontinuitetskorreksjon — som scipy
    med method='asymptotic'). Statistikken er U1 (for x)."""
    x, y = _tolist(x), _tolist(y)
    nx, ny = len(x), len(y)
    merged = [(v, 0) for v in x] + [(v, 1) for v in y]
    merged.sort(key=lambda pair: pair[0])
    ranks = [0.0] * len(merged)
    tie_term = 0.0
    i = 0
    while i < len(merged):
        j = i
        while j + 1 < len(merged) and merged[j + 1][0] == merged[i][0]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[k] = avg
        cnt = j - i + 1
        if cnt > 1:
            tie_term += cnt ** 3 - cnt
        i = j + 1
    rx = sum(r for r, (v, g) in zip(ranks, merged) if g == 0)
    u1 = rx - nx * (nx + 1) / 2.0
    n = nx + ny
    if nx == 0 or ny == 0:
        return TestResult(float('nan'), float('nan'))   # tomt utvalg — som øvrige degenererte tilfeller
    mu = nx * ny / 2.0
    sigma2 = nx * ny / 12.0 * ((n + 1) - tie_term / (n * (n - 1.0)))
    sigma = math.sqrt(sigma2)
    if sigma == 0.0:
        return TestResult(u1, float('nan'))
    if alternative == 'two-sided':
        z = (abs(u1 - mu) - 0.5) / sigma
        p = min(1.0, 2.0 * norm.sf(z))
    elif alternative == 'greater':
        z = (u1 - mu - 0.5) / sigma
        p = norm.sf(z)
    elif alternative == 'less':
        z = (u1 - mu + 0.5) / sigma
        p = norm.cdf(z)
    else:
        raise ValueError("mannwhitneyu: alternative må være "
                         "'two-sided', 'less' eller 'greater'")
    return TestResult(u1, p)
