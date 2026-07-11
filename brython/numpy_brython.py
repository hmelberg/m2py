# numpy_brython — numpy-subsett i ren Python for Brython-modus.
# Importeres som `import numpy as np` (alias i LIB_REGISTRY).
#
# 1D/2D-arrays over rene Python-lister, KOPI-semantikk (aldri views).
# Bevisst utelatt: full broadcasting (kun skalar<->array og lik form),
# dtyper, reshape utover .T, linalg utover dot/@. `import numpy.random`
# som MODUL støttes ikke — bruk np.random-attributtet.
#
# NB to feller i denne fila:
#  1) Modulfunksjonene sum/min/max/abs/round SKYGGER innebygde — all intern
#     kode bruker _sum/_min/_max/_abs/_round (bundet under).
#  2) Brython-fellene (se test_brython_scoping_trap.py): metodekropper må
#     aldri referere en global med metodens navn — underscore-regelen over
#     oppfyller dette.
import math
import random as _pyrandom

_sum, _min, _max, _abs, _round = sum, min, max, abs, round

nan = float('nan')
pi = math.pi
e = math.e


class ndarray:
    """1D/2D-array. _d er flat liste (1D) eller liste av rader (2D)."""

    def __init__(self, data):
        if isinstance(data, ndarray):
            data = data.tolist()
        data = list(data)
        if data and isinstance(data[0], (list, tuple, ndarray)):
            rows = [list(r.tolist() if isinstance(r, ndarray) else r)
                    for r in data]
            w = len(rows[0])
            for r in rows:
                if len(r) != w:
                    raise ValueError('array: radene har ulik lengde')
            self._d = rows
            self.ndim = 2
            self.shape = (len(rows), w)
        else:
            self._d = list(data)
            self.ndim = 1
            self.shape = (len(self._d),)

    @property
    def size(self):
        return self.shape[0] * (self.shape[1] if self.ndim == 2 else 1)

    @property
    def T(self):
        if self.ndim == 1:
            return ndarray(self._d)
        return ndarray([[self._d[r][c] for r in range(self.shape[0])]
                        for c in range(self.shape[1])])

    def tolist(self):
        if self.ndim == 1:
            return list(self._d)
        return [list(r) for r in self._d]

    def _flat(self):
        if self.ndim == 1:
            return list(self._d)
        return [v for row in self._d for v in row]

    def __len__(self):
        return self.shape[0]

    def __iter__(self):
        if self.ndim == 1:
            return iter(list(self._d))
        return iter([ndarray(r) for r in self._d])

    def __getitem__(self, key):
        if isinstance(key, tuple):
            if self.ndim != 2 or len(key) != 2:
                raise IndexError('tuppel-indeks krever 2D-array')
            i, j = key
            if isinstance(i, int) and isinstance(j, int):
                return self._d[i][j]
            if isinstance(i, int):
                return ndarray(self._d[i][j])
            if isinstance(j, int):
                return ndarray([row[j] for row in self._d[i]])
            return ndarray([row[j] for row in self._d[i]])
        if isinstance(key, ndarray):
            key = key.tolist()
        if isinstance(key, list):
            if key and isinstance(key[0], bool):
                if len(key) != len(self._d):
                    raise IndexError('boolsk maske har feil lengde')
                return ndarray([v for v, k in zip(self._d, key) if k])
            return ndarray([self._d[i] for i in key])
        if isinstance(key, slice):
            return ndarray(self._d[key])
        out = self._d[key]
        return ndarray(out) if isinstance(out, list) else out

    def __setitem__(self, key, value):
        if isinstance(key, ndarray):
            key = key.tolist()
        if isinstance(value, ndarray):
            value = value.tolist()
        if isinstance(key, list) and key and isinstance(key[0], bool):
            if self.ndim != 1:
                raise ValueError('maske-tilordning støttes kun for 1D-arrays')
            if len(key) != len(self._d):
                raise IndexError('boolsk maske har feil lengde')
            if not isinstance(value, (int, float)):
                raise ValueError('maske-tilordning støtter kun skalar verdi')
            for i, k in enumerate(key):
                if k:
                    self._d[i] = value
        elif isinstance(key, slice):
            n = len(range(*key.indices(len(self._d))))
            if isinstance(value, (list, tuple)):
                if len(value) != n:
                    raise ValueError('tilordning med feil lengde: %d verdier '
                                     'til %d posisjoner' % (len(value), n))
                self._d[key] = list(value)
            else:
                self._d[key] = [value] * n
        else:
            if self.ndim == 1:
                if isinstance(value, (list, tuple)):
                    raise ValueError('kan ikke legge en liste inn i et '
                                     '1D-array')
                self._d[key] = value
            elif self.ndim == 2 and isinstance(key, int):
                if (not isinstance(value, (list, tuple))
                        or len(value) != self.shape[1]):
                    raise ValueError('rad-tilordning krever liste med '
                                     'lengde %d' % self.shape[1])
                self._d[key] = list(value)
            else:
                self._d[key] = value

    def _binop(self, other, fn):
        if isinstance(other, (list, tuple)):
            other = ndarray(other)
        if isinstance(other, ndarray):
            if other.shape != self.shape:
                raise ValueError('array-former passer ikke: %r mot %r'
                                 % (self.shape, other.shape))
            if self.ndim == 1:
                return ndarray([fn(a, b) for a, b in zip(self._d, other._d)])
            return ndarray([[fn(a, b) for a, b in zip(r1, r2)]
                            for r1, r2 in zip(self._d, other._d)])
        if self.ndim == 1:
            return ndarray([fn(a, other) for a in self._d])
        return ndarray([[fn(a, other) for a in r] for r in self._d])

    def __add__(self, o): return self._binop(o, lambda a, b: a + b)
    def __radd__(self, o): return self._binop(o, lambda a, b: b + a)
    def __sub__(self, o): return self._binop(o, lambda a, b: a - b)
    def __rsub__(self, o): return self._binop(o, lambda a, b: b - a)
    def __mul__(self, o): return self._binop(o, lambda a, b: a * b)
    def __rmul__(self, o): return self._binop(o, lambda a, b: b * a)
    def __truediv__(self, o): return self._binop(o, lambda a, b: a / b)
    def __rtruediv__(self, o): return self._binop(o, lambda a, b: b / a)
    def __pow__(self, o): return self._binop(o, lambda a, b: a ** b)
    def __neg__(self): return self._binop(0, lambda a, b: -a)
    def __abs__(self): return self._binop(0, lambda a, b: _abs(a))

    def __lt__(self, o): return self._binop(o, lambda a, b: a < b)
    def __le__(self, o): return self._binop(o, lambda a, b: a <= b)
    def __gt__(self, o): return self._binop(o, lambda a, b: a > b)
    def __ge__(self, o): return self._binop(o, lambda a, b: a >= b)
    def __eq__(self, o): return self._binop(o, lambda a, b: a == b)
    def __ne__(self, o): return self._binop(o, lambda a, b: a != b)

    __hash__ = None                     # elementvis __eq__ -> uhashbar (som numpy)

    def __bool__(self):
        if self.size == 1:
            return bool(self._flat()[0])
        raise ValueError('sannhetsverdien til et array med flere elementer '
                         'er tvetydig — bruk .any()-logikk eller sammenlikn '
                         'med .tolist()')

    def __matmul__(self, o):
        return dot(self, o)             # dot defineres i Task 3 — oppslag ved kall

    # NB: metodene bruker KUN _sum/_min/_max (skygge-/Brython-fellene)
    def mean(self):
        flat = self._flat()
        return _sum(flat) / len(flat)

    def sum(self):
        return _sum(self._flat())

    def min(self):
        return _min(self._flat())

    def max(self):
        return _max(self._flat())

    def var(self, ddof=0):
        flat = self._flat()
        n = len(flat) - ddof
        if n <= 0:
            return nan
        m = _sum(flat) / len(flat)
        return _sum((v - m) ** 2 for v in flat) / n

    def std(self, ddof=0):
        v = self.var(ddof)
        return math.sqrt(v) if v == v else nan

    def argmax(self):
        flat = self._flat()
        return flat.index(_max(flat))

    def argmin(self):
        flat = self._flat()
        return flat.index(_min(flat))

    def cumsum(self):
        out = []
        acc = 0
        for v in self._flat():
            acc += v
            out.append(acc)
        return ndarray(out)

    def round(self, decimals=0):
        return _unary(self, lambda v: _round(v, decimals))

    def astype(self, typ):
        return _unary(self, typ)

    def __repr__(self):
        return 'array(%r)' % (self.tolist(),)


def array(data):
    return ndarray(data)


def asarray(a):
    if isinstance(a, ndarray):
        return a
    if isinstance(a, (list, tuple)):
        return ndarray(a)
    if hasattr(a, 'tolist'):
        return ndarray(a.tolist())
    return ndarray([a])


def arange(start, stop=None, step=1):
    if stop is None:
        start, stop = 0, start
    if step == 0:
        raise ValueError('arange: step kan ikke være 0')
    n = int(math.ceil((stop - start) / step))
    if n < 0:
        n = 0
    return ndarray([start + i * step for i in range(n)])


def linspace(start, stop, num=50):
    if num < 1:
        raise ValueError('linspace: num må være minst 1')
    if num == 1:
        return ndarray([float(start)])
    step = (stop - start) / (num - 1)
    vals = [start + step * i for i in range(num - 1)]
    vals.append(float(stop))                       # eksakt endepunkt som numpy
    return ndarray(vals)


def _filled(shape, value):
    if isinstance(shape, tuple):
        if len(shape) == 1:
            return ndarray([value] * shape[0])
        if len(shape) == 2:
            r, c = shape
            return ndarray([[value] * c for _ in range(r)])
        raise ValueError('kun 1D- og 2D-former støttes: %r' % (shape,))
    return ndarray([value] * shape)


def zeros(shape):
    return _filled(shape, 0.0)


def ones(shape):
    return _filled(shape, 1.0)


def full(shape, value):
    return _filled(shape, value)


def _unary(a, fn):
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        return fn(a)
    arr = asarray(a)
    if arr.ndim == 1:
        return ndarray([fn(v) for v in arr._d])
    return ndarray([[fn(v) for v in r] for r in arr._d])


def sqrt(a):
    return _unary(a, math.sqrt)


def log(a):
    return _unary(a, math.log)


def exp(a):
    return _unary(a, math.exp)


def abs(a):                             # skygger builtin — intern kode bruker _abs
    return _unary(a, _abs)


def round(a, decimals=0):               # skygger builtin — intern kode bruker _round
    return _unary(a, lambda v: _round(v, decimals))


def isnan(a):
    return _unary(a, lambda v: isinstance(v, float) and v != v)


def mean(a):
    return asarray(a).mean()


def median(a):
    flat = sorted(asarray(a)._flat())
    n = len(flat)
    mid = n // 2
    if n % 2:
        return flat[mid]
    return (flat[mid - 1] + flat[mid]) / 2.0


def std(a, ddof=0):
    return asarray(a).std(ddof)


def var(a, ddof=0):
    return asarray(a).var(ddof)


def sum(a):                             # skygger builtin — intern kode bruker _sum
    return asarray(a).sum()


def min(a):                             # skygger builtin — intern kode bruker _min
    return asarray(a).min()


def max(a):                             # skygger builtin — intern kode bruker _max
    return asarray(a).max()


def percentile(a, q):
    if isinstance(q, (list, tuple)):
        return ndarray([percentile(a, x) for x in q])
    if not 0.0 <= q <= 100.0:
        raise ValueError('percentile: q må ligge i [0, 100]')
    flat = sorted(asarray(a)._flat())
    if not flat:
        raise ValueError('percentile: tomt array')
    pos = (len(flat) - 1) * q / 100.0
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(flat[lo])
    frac = pos - lo
    return flat[lo] * (1.0 - frac) + flat[hi] * frac


def quantile(a, q):
    if isinstance(q, (list, tuple)):
        return ndarray([percentile(a, x * 100.0) for x in q])
    return percentile(a, q * 100.0)


def cumsum(a):
    return asarray(a).cumsum()


def unique(a):
    seen = []
    has_nan = False
    for v in asarray(a)._flat():
        if isinstance(v, float) and v != v:
            has_nan = True              # numpy dedupliserer nan (equal_nan=True)
            continue
        if v not in seen:
            seen.append(v)
    out = sorted(seen)
    if has_nan:
        out.append(nan)                 # numpy legger nan sist
    return ndarray(out)


def sort(a):
    arr = asarray(a)
    if arr.ndim != 1:
        raise ValueError('sort støtter kun 1D-arrays')
    return ndarray(sorted(arr._flat()))


def argsort(a):
    arr = asarray(a)
    if arr.ndim != 1:
        raise ValueError('argsort støtter kun 1D-arrays')
    flat = arr._flat()
    return ndarray(sorted(range(len(flat)), key=lambda i: flat[i]))


def argmax(a):
    return asarray(a).argmax()


def argmin(a):
    return asarray(a).argmin()


def where(cond, x=None, y=None):
    c = asarray(cond)
    if x is None and y is None:
        if c.ndim != 1:
            raise ValueError('where(cond) uten verdier støtter kun 1D')
        return (ndarray([i for i, v in enumerate(c._d) if v]),)
    if (x is None) != (y is None):
        raise ValueError('where: oppgi enten bare cond, eller cond, x OG y')

    def _pick(src, i, j=None):
        if isinstance(src, ndarray):
            return src._d[i] if j is None else src._d[i][j]
        return src

    xa = asarray(x) if isinstance(x, (list, tuple, ndarray)) else x
    ya = asarray(y) if isinstance(y, (list, tuple, ndarray)) else y
    for arr in (xa, ya):
        if isinstance(arr, ndarray) and arr.shape != c.shape:
            raise ValueError('where: x/y må ha samme form som cond')
    if c.ndim == 1:
        return ndarray([_pick(xa, i) if v else _pick(ya, i)
                        for i, v in enumerate(c._d)])
    return ndarray([[_pick(xa, i, j) if v else _pick(ya, i, j)
                     for j, v in enumerate(row)]
                    for i, row in enumerate(c._d)])


def concatenate(arrays):
    out = []
    for a in arrays:
        arr = asarray(a)
        if arr.ndim != 1:
            raise ValueError('concatenate: kun 1D-arrays støttes')
        out.extend(arr._d)
    return ndarray(out)


def dot(a, b):
    A, B = asarray(a), asarray(b)
    if A.ndim == 1 and B.ndim == 1:
        if A.shape != B.shape:
            raise ValueError('dot: lengdene passer ikke')
        return _sum(x * y for x, y in zip(A._d, B._d))
    if A.ndim == 1:
        A = ndarray([A._d])                      # radvektor
        return dot(A, B)[0]
    if B.ndim == 1:
        if A.shape[1] != B.shape[0]:
            raise ValueError('dot: formene passer ikke: %r mot %r'
                             % (A.shape, B.shape))
        return ndarray([_sum(x * y for x, y in zip(row, B._d))
                        for row in A._d])
    if A.shape[1] != B.shape[0]:
        raise ValueError('dot: formene passer ikke: %r mot %r'
                         % (A.shape, B.shape))
    Bt = B.T
    return ndarray([[_sum(x * y for x, y in zip(row, col))
                     for col in Bt._d] for row in A._d])


# ── np.random ───────────────────────────────────────────────────────────────
# Samme seed -> samme tall på tvers av kjøringer og CPython/Brython, men
# IKKE de samme tallene som ekte numpy (Mersenne-strømmene brukes ulikt).

class _Generator:
    """default_rng-stil generator."""

    def __init__(self, seed=None):
        self._rng = _pyrandom.Random(seed)

    def _sized(self, size, gen):
        if size is None:
            return gen()
        if isinstance(size, tuple):
            r, c = size
            return ndarray([[gen() for _ in range(c)] for _ in range(r)])
        return ndarray([gen() for _ in range(size)])

    def normal(self, loc=0.0, scale=1.0, size=None):
        return self._sized(size, lambda: self._rng.gauss(loc, scale))

    def uniform(self, low=0.0, high=1.0, size=None):
        return self._sized(size, lambda: self._rng.uniform(low, high))

    def integers(self, low, high=None, size=None):
        if high is None:
            low, high = 0, low
        return self._sized(size, lambda: self._rng.randrange(low, high))

    def choice(self, a, size=None, replace=True):
        pool = (list(range(a)) if isinstance(a, int)
                else asarray(a)._flat())
        if size is None:
            return self._rng.choice(pool)
        if not replace:
            return ndarray(self._rng.sample(pool, size))
        return ndarray([self._rng.choice(pool) for _ in range(size)])

    def shuffle(self, x):
        if isinstance(x, ndarray):
            self._rng.shuffle(x._d)
        else:
            self._rng.shuffle(x)


class _RandomState(_Generator):
    """np.random.* (legacy-API: seed/randint/rand/randn)."""

    def seed(self, n=None):
        self._rng = _pyrandom.Random(n)

    def randint(self, low, high=None, size=None):
        return self.integers(low, high, size)

    def rand(self, n=None):
        return self.uniform(0.0, 1.0, n)

    def randn(self, n=None):
        return self.normal(0.0, 1.0, n)


random = _RandomState()


def default_rng(seed=None):
    return _Generator(seed)
