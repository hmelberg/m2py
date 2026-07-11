# statsmodels_brython — statsmodels-formel-API (OLS + Logit) i ren Python.
# Importeres som `import statsmodels.formula.api as smf` (aliaser i
# LIB_REGISTRY) eller direkte som statsmodels_brython.
#
# Formler: 'y ~ x1 + x2 + C(kat)' med '- 1'/'+ 0' for uten konstantledd.
# Strengkolonner behandles automatisk som kategoriske (som statsmodels);
# navngiving følger patsy: 'region[T.S]' / 'C(region)[T.S]', sorterte
# nivåer, første nivå droppes (treatment-koding). params/bse/tvalues/
# pvalues er dict-er nøklet på disse navnene.
#
# NB Brython-feller (AST-vakter i test_brython_scoping_trap.py): ingen
# metode refererer global med metodens navn; setdefault kun streng-nøkler.
import html
import math
import scipy_stats_brython as _stats


def _col(data, name):
    """Hent en kolonne som liste — duck-typet (dict-of-lists eller
    pandas_brython DataFrame/Series)."""
    try:
        ser = data[name]
    except Exception:
        raise ValueError('ukjent kolonne i formelen: ' + name)
    if hasattr(ser, 'tolist'):
        return list(ser.tolist())
    if hasattr(ser, 'values') and not isinstance(ser, (list, tuple)):
        vals = ser.values
        return list(vals() if callable(vals) else vals)
    return list(ser)


def _parse_formula(formula):
    """'y ~ x1 + C(kat) - 1' -> ('y', ['x1', 'C(kat)'], False)."""
    left, sep, right = formula.partition('~')
    yname = left.strip()
    if not sep or not yname or not right.strip():
        raise ValueError("formelen må ha formen 'y ~ x1 + x2'")
    rhs = right.replace(' ', '')
    intercept = True
    terms = []
    for tok in rhs.replace('-1', '+&NOINT&').split('+'):
        if not tok:
            continue
        if tok in ('&NOINT&', '0'):
            intercept = False
        elif tok != '1':
            terms.append(tok)
    return yname, terms, intercept


def _is_categorical(values):
    return any(isinstance(v, str) for v in values)


def _levels_sorted(values):
    seen = []
    for v in values:
        if v not in seen:
            seen.append(v)
    try:
        return sorted(seen)
    except TypeError:                      # blandede typer — fall tilbake til str
        return sorted(seen, key=str)


def _term_spec(term, data):
    """Én formelterm -> spec-oppføring ('num', col) | ('cat', col, levels, prefix)."""
    if term.startswith('C(') and term.endswith(')'):
        col = term[2:-1].strip()
        levels = _levels_sorted(_col(data, col))
        return ('cat', col, levels, 'C(%s)' % col)
    vals = _col(data, term)
    if _is_categorical(vals):
        return ('cat', term, _levels_sorted(vals), term)
    return ('num', term)


def _design_from_spec(spec, intercept, data, n=None):
    """Bygg (names, X) fra en spec — brukes både ved fit og predict.
    n = antall rader; utledes fra første term når den ikke oppgis
    (ren-intercept-spec uten n gir ValueError). Ukjent kategorinivå i nye
    data gir ValueError (som statsmodels)."""
    if n is None:
        if not spec:
            raise ValueError('kan ikke bygge designmatrise uten termer og uten n')
        n = len(_col(data, _spec_col(spec[0])))
    names = ['Intercept'] if intercept else []
    columns = [[1.0] * n] if intercept else []
    reduced_rank = intercept
    for entry in spec:
        if entry[0] == 'num':
            vals = _col(data, entry[1])
            names.append(entry[1])
            columns.append([float(v) for v in vals])
        else:
            _, col, levels, prefix = entry
            vals = _col(data, col)
            for v in vals:
                if v not in levels:
                    raise ValueError('ukjent kategorinivå %r i kolonnen %s'
                                     % (v, col))
            if not reduced_rank:
                # patsy: uten konstantledd får FØRSTE kategoriske term full
                # rang — alle nivåer, navn uten 'T.'
                for lev in levels:
                    names.append('%s[%s]' % (prefix, lev))
                    columns.append([1.0 if v == lev else 0.0 for v in vals])
                reduced_rank = True
            else:
                for lev in levels[1:]:
                    names.append('%s[T.%s]' % (prefix, lev))
                    columns.append([1.0 if v == lev else 0.0 for v in vals])
    for c in columns:
        if len(c) != n:
            raise ValueError('kolonnene i formelen har ulik lengde')
    X = [[c[i] for c in columns] for i in range(n)]
    return names, X


def _spec_col(entry):
    return entry[1]


def _data_nrows(data):
    """Antall rader i et data-objekt (DataFrame duck via len, ellers
    lengden på første kolonne i en dict)."""
    if isinstance(data, dict):
        if not data:
            raise ValueError('kan ikke bestemme antall rader i nye data')
        return len(next(iter(data.values())))
    try:
        return len(data)
    except Exception:
        raise ValueError('kan ikke bestemme antall rader i nye data')


def _build_design(formula, data):
    """Formel + data -> (y, names, X, spec)."""
    yname, terms, intercept = _parse_formula(formula)
    y = [float(v) for v in _col(data, yname)]
    spec = [_term_spec(t, data) for t in terms]
    names, X = _design_from_spec(spec, intercept, data, n=len(y))
    if not names:
        raise ValueError('formelen har ingen forklaringsvariabler')
    return y, names, X, spec


# ── lineær algebra ──────────────────────────────────────────────────────────

def _solve(A, B):
    """Løs A·X = B (A n×n, B n×m) med Gauss-Jordan og delvis pivotering.
    Muterer ikke input. Norsk feil ved singulær matrise."""
    n = len(A)
    M = [list(Arow) + list(Brow) for Arow, Brow in zip(A, B)]
    width = len(M[0])
    for colidx in range(n):
        piv = max(range(colidx, n), key=lambda r: abs(M[r][colidx]))
        if abs(M[piv][colidx]) < 1e-12:
            raise ValueError('designmatrisen er singulær — perfekt '
                             'kolineære kolonner i formelen?')
        M[colidx], M[piv] = M[piv], M[colidx]
        pv = M[colidx][colidx]
        M[colidx] = [v / pv for v in M[colidx]]
        for r in range(n):
            if r != colidx and M[r][colidx] != 0.0:
                factor = M[r][colidx]
                Mc = M[colidx]
                M[r] = [a - factor * b for a, b in zip(M[r], Mc)]
    return [row[n:width] for row in M]


def _xtx_xty(X, y):
    k = len(X[0])
    xtx = [[sum(row[i] * row[j] for row in X) for j in range(k)]
           for i in range(k)]
    xty = [[sum(row[i] * yv for row, yv in zip(X, y))] for i in range(k)]
    return xtx, xty


# ── OLS ─────────────────────────────────────────────────────────────────────

class OLSResults:
    def __init__(self, names, beta, cov, y, X, intercept, spec, has_const):
        self._names = names
        self._spec = spec
        self._intercept = intercept
        self._cov = cov
        n = len(y)
        k = len(names)
        self.nobs = n
        self.df_resid = n - k
        self.df_model = k - 1 if has_const else k
        self.params = {nm: b for nm, b in zip(names, beta)}
        self.fittedvalues = [sum(b * xv for b, xv in zip(beta, row))
                             for row in X]
        self.resid = [yv - fv for yv, fv in zip(y, self.fittedvalues)]
        ssr = sum(r * r for r in self.resid)
        ymean = sum(y) / n
        sst = (sum((v - ymean) ** 2 for v in y) if has_const
               else sum(v * v for v in y))
        self.rsquared = 1.0 - ssr / sst if sst > 0.0 else float('nan')
        self.rsquared_adj = (1.0 - (1.0 - self.rsquared) * (n - (1 if has_const else 0))
                             / self.df_resid) if self.df_resid > 0 else float('nan')
        self.bse = {}
        self.tvalues = {}
        self.pvalues = {}
        for i, nm in enumerate(names):
            se = math.sqrt(cov[i][i]) if cov[i][i] > 0.0 else float('nan')
            self.bse[nm] = se
            tv = self.params[nm] / se if se and se > 0.0 else float('nan')
            self.tvalues[nm] = tv
            self.pvalues[nm] = (2.0 * _stats.t.sf(abs(tv), self.df_resid)
                                if tv == tv and self.df_resid > 0 else float('nan'))
        if self.df_model > 0 and self.df_resid > 0 and ssr > 0.0 and sst > ssr:
            self.fvalue = ((sst - ssr) / self.df_model) / (ssr / self.df_resid)
            self.f_pvalue = _stats.f.sf(self.fvalue, self.df_model, self.df_resid)
        else:
            self.fvalue = float('nan')
            self.f_pvalue = float('nan')

    def predict(self, data=None):
        if data is None:
            return list(self.fittedvalues)
        names, X = _design_from_spec(self._spec, self._intercept, data,
                                     n=None if self._spec else _data_nrows(data))
        beta = [self.params[nm] for nm in names]
        return [sum(b * xv for b, xv in zip(beta, row)) for row in X]

    def conf_int(self, alpha=0.05):
        q = _stats.t.ppf(1.0 - alpha / 2.0, self.df_resid)
        out = {}
        for nm in self._names:
            b, se = self.params[nm], self.bse[nm]
            out[nm] = ([b - q * se, b + q * se] if se == se
                       else [float('nan'), float('nan')])
        return out

    def summary(self):
        stats_rows = [
            ('Observasjoner', '%d' % self.nobs),
            ('R²', '%.4f' % self.rsquared),
            ('Justert R²', '%.4f' % self.rsquared_adj),
            ('F-statistikk', '%.4g (p=%.4g)' % (self.fvalue, self.f_pvalue)),
        ]
        return Summary('OLS-regresjon', stats_rows, self._names, self.params,
                       self.bse, self.tvalues, self.pvalues, self.conf_int())


class Summary:
    """summary()-objekt: to_html() rendres av appens tabell-embed;
    str() gir tekst-fallback."""

    def __init__(self, title, stats_rows, names, params, bse, tvalues,
                 pvalues, ci, stat_label='t'):
        self._title = title
        self._stats_rows = stats_rows
        self._names = names
        self._params = params
        self._bse = bse
        self._tvalues = tvalues
        self._pvalues = pvalues
        self._ci = ci
        self._stat_label = stat_label

    def to_html(self):
        parts = ['<table class="output-table" data-summary="1">']
        parts.append('<caption>%s</caption>' % html.escape(str(self._title)))
        parts.append('<thead><tr><th></th><th>koef</th><th>std.feil</th>'
                     '<th>%s</th><th>P&gt;|%s|</th><th>[0.025</th>'
                     '<th>0.975]</th></tr></thead><tbody>'
                     % (self._stat_label, self._stat_label))
        for nm in self._names:
            lo, hi = self._ci[nm]
            parts.append(
                '<tr><th>%s</th><td>%.4f</td><td>%.4f</td><td>%.3f</td>'
                '<td>%.4f</td><td>%.3f</td><td>%.3f</td></tr>'
                % (html.escape(str(nm)), self._params[nm], self._bse[nm],
                   self._tvalues[nm], self._pvalues[nm], lo, hi))
        parts.append('</tbody></table>')
        rows = ''.join('<tr><th>%s</th><td>%s</td></tr>'
                       % (html.escape(str(k)), html.escape(str(v)))
                       for k, v in self._stats_rows)
        parts.append('<table class="output-table"><tbody>%s</tbody></table>'
                     % rows)
        return ''.join(parts)

    def __str__(self):
        lines = [self._title]
        for k, v in self._stats_rows:
            lines.append('%s: %s' % (k, v))
        lines.append('%-24s %10s %10s %8s %8s' % ('', 'koef', 'std.feil',
                                                  self._stat_label, 'p'))
        for nm in self._names:
            lines.append('%-24s %10.4f %10.4f %8.3f %8.4f'
                         % (nm, self._params[nm], self._bse[nm],
                            self._tvalues[nm], self._pvalues[nm]))
        return '\n'.join(lines)

    def __repr__(self):
        return self.__str__()


class OLSModel:
    def __init__(self, formula, data):
        self._formula = formula
        self._data = data

    def fit(self, **kwargs):
        for key in kwargs:
            if key not in ('disp', 'maxiter'):
                raise ValueError("fit: argumentet '%s' støttes ikke i "
                                 'Brython-utgaven' % key)
        y, names, X, spec = _build_design(self._formula, self._data)
        n, k = len(X), len(names)
        if n <= k:
            raise ValueError('ols: for få observasjoner (%d) til %d '
                             'koeffisienter' % (n, k))
        xtx, xty = _xtx_xty(X, y)
        beta = [row[0] for row in _solve(xtx, xty)]
        fitted = [sum(b * xv for b, xv in zip(beta, row)) for row in X]
        ssr = sum((yv - fv) ** 2 for yv, fv in zip(y, fitted))
        sigma2 = ssr / (n - k)
        identity = [[1.0 if i == j else 0.0 for j in range(k)] for i in range(k)]
        xtx_inv = _solve(xtx, identity)
        cov = [[sigma2 * xtx_inv[i][j] for j in range(k)] for i in range(k)]
        _, _, intercept = _parse_formula(self._formula)
        has_const = intercept or any(e[0] == 'cat' for e in spec)
        return OLSResults(names, beta, cov, y, X, intercept, spec, has_const)


def ols(formula, data):
    return OLSModel(formula, data)


# ── Logit ───────────────────────────────────────────────────────────────────

def _logit_newton(X, y, max_iter=50, tol=1e-8):
    """Newton–Raphson for logistisk regresjon. Returnerer (beta, cov,
    llf, converged). mu klippes mot [1e-10, 1-1e-10] for stabilitet."""
    n = len(X)
    k = len(X[0])
    beta = [0.0] * k
    converged = False
    cov = None
    for _ in range(max_iter):
        eta = [sum(b * xv for b, xv in zip(beta, row)) for row in X]
        mu = [1.0 / (1.0 + math.exp(-min(35.0, max(-35.0, e)))) for e in eta]
        mu = [min(1.0 - 1e-10, max(1e-10, m)) for m in mu]
        grad = [[sum(row[i] * (yv - m) for row, yv, m in zip(X, y, mu))]
                for i in range(k)]
        W = [m * (1.0 - m) for m in mu]
        H = [[sum(row[i] * row[j] * w for row, w in zip(X, W))
              for j in range(k)] for i in range(k)]
        delta = [row[0] for row in _solve(H, grad)]
        beta = [b + d for b, d in zip(beta, delta)]
        if max(abs(d) for d in delta) < tol:
            converged = True
            identity = [[1.0 if i == j else 0.0 for j in range(k)]
                        for i in range(k)]
            cov = _solve(H, identity)
            break
    if cov is None:
        identity = [[1.0 if i == j else 0.0 for j in range(k)]
                    for i in range(k)]
        cov = _solve(H, identity)
    eta = [sum(b * xv for b, xv in zip(beta, row)) for row in X]
    mu = [1.0 / (1.0 + math.exp(-min(35.0, max(-35.0, e)))) for e in eta]
    mu = [min(1.0 - 1e-10, max(1e-10, m)) for m in mu]
    llf = sum(yv * math.log(m) + (1.0 - yv) * math.log(1.0 - m)
              for yv, m in zip(y, mu))
    return beta, cov, llf, converged


class LogitResults:
    def __init__(self, names, beta, cov, y, X, intercept, spec, llf,
                 converged):
        self._names = names
        self._spec = spec
        self._intercept = intercept
        self.nobs = len(y)
        self.converged = converged
        self.llf = llf
        self.params = {nm: b for nm, b in zip(names, beta)}
        self.bse = {}
        self.tvalues = {}
        self.pvalues = {}
        for i, nm in enumerate(names):
            se = math.sqrt(cov[i][i]) if cov[i][i] > 0.0 else float('nan')
            self.bse[nm] = se
            z = self.params[nm] / se if se and se > 0.0 else float('nan')
            self.tvalues[nm] = z
            self.pvalues[nm] = (2.0 * _stats.norm.sf(abs(z))
                                if z == z else float('nan'))
        # null-modell (kun intercept) for McFaddens pseudo-R²
        ybar = sum(y) / len(y)
        ybar = min(1.0 - 1e-10, max(1e-10, ybar))
        self.llnull = sum(yv * math.log(ybar) + (1.0 - yv) * math.log(1.0 - ybar)
                          for yv in y)
        self.prsquared = (1.0 - self.llf / self.llnull
                          if self.llnull != 0.0 else float('nan'))
        self.fittedvalues = [
            1.0 / (1.0 + math.exp(-min(35.0, max(-35.0,
                sum(b * xv for b, xv in zip(beta, row))))))
            for row in X]

    def predict(self, data=None):
        if data is None:
            return list(self.fittedvalues)
        names, X = _design_from_spec(self._spec, self._intercept, data,
                                     n=None if self._spec else _data_nrows(data))
        beta = [self.params[nm] for nm in names]
        return [1.0 / (1.0 + math.exp(-min(35.0, max(-35.0,
                    sum(b * xv for b, xv in zip(beta, row))))))
                for row in X]

    def conf_int(self, alpha=0.05):
        q = _stats.norm.ppf(1.0 - alpha / 2.0)
        out = {}
        for nm in self._names:
            b, se = self.params[nm], self.bse[nm]
            out[nm] = ([b - q * se, b + q * se] if se == se
                       else [float('nan'), float('nan')])
        return out

    def summary(self):
        stats_rows = [
            ('Observasjoner', '%d' % self.nobs),
            ('Log-likelihood', '%.4f' % self.llf),
            ('Pseudo-R² (McFadden)', '%.4f' % self.prsquared),
            ('Konvergert', 'ja' if self.converged else 'NEI'),
        ]
        return Summary('Logistisk regresjon', stats_rows, self._names,
                       self.params, self.bse, self.tvalues, self.pvalues,
                       self.conf_int(), stat_label='z')


class LogitModel:
    def __init__(self, formula, data):
        self._formula = formula
        self._data = data

    def fit(self, **kwargs):                       # disp o.l. aksepteres og ignoreres
        for key in kwargs:
            if key not in ('disp', 'maxiter'):
                raise ValueError("fit: argumentet '%s' støttes ikke i "
                                 'Brython-utgaven' % key)
        y, names, X, spec = _build_design(self._formula, self._data)
        if len(X) <= len(names):
            raise ValueError('logit: for få observasjoner (%d) til %d '
                             'koeffisienter' % (len(X), len(names)))
        for v in y:
            if v not in (0.0, 1.0):
                raise ValueError('logit: y må være binær (0/1), fant %r' % v)
        beta, cov, llf, converged = _logit_newton(X, y)
        _, _, intercept = _parse_formula(self._formula)
        return LogitResults(names, beta, cov, y, X, intercept, spec, llf,
                            converged)


def logit(formula, data):
    return LogitModel(formula, data)
