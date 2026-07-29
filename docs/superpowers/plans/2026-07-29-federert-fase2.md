# Federert fase 2 (safestat-node + federert logit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any data holder can run `pip install ./node && safestat-node --config node.json` to host a federated node (token auth, vendored engine), and federated scripts gain `logit` via iterative Newton rounds — exact pooled MLE, still aggregates-only per round.

**Architecture:** Logit can't be pooled from one-shot statistics (the sufficient stats depend on β), so the coordinator drives Newton-Raphson: each round it fans the script out with the current β (`fed_round: {beta}`), each node computes gradient Xᵀ(y−p), Hessian XᵀWX and log-likelihood at that β (SDC-gated like regress), the combine layer sums them and takes a Newton step; 4–10 rounds converge to the same MLE statsmodels finds on pooled data. A stateful `FederatedDriver` in `m2py_runtime/federate.py` holds round state inside Pyodide between the browser's fan-outs, so JS stays a dumb loop. The node package (`node/` dir: `pyproject.toml` + `safestat_node/`) wraps the phase-1 dev-node server with config-file/token support and a vendored engine copied in by `scripts/build_node_package.py`; it replaces `scripts/dev_federert_node.py`.

**Tech Stack:** numpy Newton-Raphson, statsmodels (equality oracle), stdlib http.server + argparse/json (no server framework), pip/venv, Pyodide-persistent driver state.

**Spec:** `docs/superpowers/specs/2026-07-29-federated-sources-design.md` §6. Scope: `safestat-node` + logistic regression. **Deferred with reasons:** trusted-hub combine (needs a hub-deployment decision Hans must make; combine interface already accommodates it), overlap handling (spec: only on real need), percentiles (no exact combine).

## Global Constraints

- v1 restriction: at most ONE `logit` statement per federated script (thread-local carries one β); more → Norwegian refusal.
- Logit round payloads pass the SAME SDC gate as regress sufficient stats: refused when node `n < min_n` or any at-risk count `< min_n`.
- Node package has NO new runtime deps beyond the engine's (pandas, numpy, statsmodels, pyarrow, scipy); server stays stdlib http.server.
- Norwegian user-facing messages with «…»; ES5 JS; existing module styles.
- Tests: `python3 -m pytest tests/ -q`, `node --test tests/js/*.test.js`. Commit per task; no pushes.
- statsmodels `Logit` reports z-based (normal) p-values — `logit_final` must match (erfc, not t-dist).

---

### Task 1: `pandas_ops` — `_design` helper, `set_fed_round`, federated `logit`

**Files:**
- Modify: `m2py_runtime/pandas_ops.py` (`_fit_model` at ~line 912, `logit` at ~line 1041, flag block at ~line 44)
- Test: `tests/test_federate_stats.py` (extend)

**Interfaces:**
- Produces: `_design(df, dep, indep, noconstant=False)` → `(X, Y)` (numeric-coerced, listwise-dropna, add_constant unless noconstant — EXACTLY `_fit_model`'s preamble, which now calls it). `set_fed_round(beta_or_None)` / `get_fed_round()` (thread-local like `set_federated`). Under `get_federated()`, `logit(df, dep, indep, noconstant=False)`:
  - fed_round None → returns a 1-row placeholder DataFrame (`{"info": ["federert logit — kombineres via iterative runder"]}`) with `attrs["fedstats"] = {"model": "logit", "terms": [str], "n": int, "at_risk": [int]}` (NO local fit — separation-safe on small nodes);
  - fed_round β → same placeholder with `attrs["fedstats"] = {"model": "logit_round", "terms", "grad": [float], "hess": [[float]], "loglik": float, "n", "at_risk"}` computed at β (p=sigmoid(Xβ), grad=Xᵀ(y−p), hess=XᵀWX, W=p(1−p)).
  - Regress's existing fedstats dict stays keyless (`"model"` absent ⇒ regress).

- [ ] **Step 1: Failing tests** — append to `tests/test_federate_stats.py`:

```python
def _logit_df(n=40, seed=5):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    p = 1 / (1 + np.exp(-(0.5 + 1.5 * x)))
    return pd.DataFrame({"y": (rng.random(n) < p).astype(float), "x": x})


def test_logit_federated_init_emits_terms_no_fit():
    ops.set_federated(True)
    out = ops.logit(_logit_df(), "y", ["x"])
    fs = out.attrs["fedstats"]
    assert fs["model"] == "logit" and fs["terms"] == ["const", "x"]
    assert fs["n"] == 40 and "grad" not in fs


def test_logit_federated_round_computes_grad_hess_at_beta():
    df = _logit_df()
    ops.set_federated(True)
    ops.set_fed_round([0.0, 0.0])
    try:
        fs = ops.logit(df, "y", ["x"]).attrs["fedstats"]
    finally:
        ops.set_fed_round(None)
    assert fs["model"] == "logit_round"
    X = np.column_stack([np.ones(40), df["x"].to_numpy()])
    y = df["y"].to_numpy()
    p = np.full(40, 0.5)                      # sigmoid(0)
    assert np.allclose(fs["grad"], X.T @ (y - p))
    assert np.allclose(fs["hess"], (X * (p * (1 - p))[:, None]).T @ X)
```

- [ ] **Step 2:** Run `python3 -m pytest tests/test_federate_stats.py -q` → the two new tests FAIL (`set_fed_round` missing / fedstats absent).

- [ ] **Step 3: Implement.** In the flag block after `get_federated()` add:

```python
def set_fed_round(beta):
    """Fase 2: koordinatorens gjeldende logit-β for denne runden (én logit
    per federert skript i v1). None = init-runde (bare terms/n frigis)."""
    _release_ctx.fed_round_beta = list(beta) if beta is not None else None


def get_fed_round():
    return getattr(_release_ctx, "fed_round_beta", None)
```

Factor `_fit_model`'s preamble into `_design` (and call it from `_fit_model`):

```python
def _design(df, dep, indep, noconstant=False):
    """Designmatrisen slik _fit_model bygger den (numerisk koersjon, listwise
    dropna, konstant med mindre noconstant) — UTEN å tilpasse en modell."""
    import statsmodels.api as sm
    d = df[[dep] + list(indep)].apply(pd.to_numeric, errors="coerce").dropna().astype(float)
    X = d[list(indep)].copy()
    if not noconstant:
        X = sm.add_constant(X, has_constant="add")
    return X, d[dep]
```

(`_fit_model` keeps its `standardize` branch inline between the coercion and add_constant — restructure so the shared, non-standardized path goes through `_design` and `_fit_model` applies standardization before add_constant only when asked; the existing test suite guards equivalence.)

Replace `logit`:

```python
def logit(df, dep, indep, noconstant=False):
    """Logistic-regression coefficient table."""
    if get_federated():
        X, Y = _design(df, dep, indep, noconstant)
        Xa = np.asarray(X, dtype=float)
        Ya = np.asarray(Y, dtype=float)
        base = {"terms": [str(c) for c in X.columns], "n": int(len(Ya)),
                "at_risk": [int(v) for v in (Xa != 0).sum(axis=0)]}
        beta = get_fed_round()
        if beta is None:
            fs = dict(base, model="logit")
        else:
            eta = Xa @ np.asarray(beta, dtype=float)
            p = 1.0 / (1.0 + np.exp(-eta))
            w = p * (1.0 - p)
            fs = dict(base, model="logit_round",
                      grad=(Xa.T @ (Ya - p)).tolist(),
                      hess=((Xa * w[:, None]).T @ Xa).tolist(),
                      loglik=float(np.sum(Ya * eta - np.log1p(np.exp(eta)))))
        out = pd.DataFrame({"info": ["federert logit — kombineres via iterative runder"]})
        out.attrs["fedstats"] = fs
        return out
    return _coef_table(_fit_model(df, "logit", dep, indep, noconstant))
```

- [ ] **Step 4:** `python3 -m pytest tests/test_federate_stats.py -q` → pass; `python3 -m pytest tests/ -q` → all pass (guards the `_design` factoring).

- [ ] **Step 5: Commit** `feat(federert): logit emits per-round gradient/Hessian behind fed_round`.

---

### Task 2: `extract_stats` handles logit payloads

**Files:**
- Modify: `m2py_runtime/federate.py` (`extract_stats`'s fedstats branch)
- Test: `tests/test_federate_stats.py` (extend)

**Interfaces:**
- Produces: fedstats with `model == "logit"` → `{"kind": "logit_init", ...base}`; `model == "logit_round"` → `{"kind": "logit_round", ...}`; missing model key → `{"kind": "regress", ...}` (unchanged). Same min_n gate for all three (n and at_risk).

- [ ] **Step 1: Failing tests:**

```python
def test_extract_logit_init_and_round_kinds():
    ops.set_federated(True)
    ns = {"result_1": ops.logit(_logit_df(), "y", ["x"])}
    assert federate.extract_stats(ns, None)[0]["kind"] == "logit_init"
    ops.set_fed_round([0.0, 0.0])
    try:
        ns = {"result_1": ops.logit(_logit_df(), "y", ["x"])}
    finally:
        ops.set_fed_round(None)
    s = federate.extract_stats(ns, None)[0]
    assert s["kind"] == "logit_round" and "hess" in s


def test_extract_logit_below_threshold_refused():
    ops.set_federated(True)
    ns = {"result_1": ops.logit(_logit_df(n=4), "y", ["x"])}
    assert federate.extract_stats(ns, SPEC)[0]["kind"] == "refused"
```

- [ ] **Step 2:** Run → FAIL (kind comes back "regress"/passes gate wrongly).

- [ ] **Step 3: Implement** — replace the fedstats branch in `extract_stats`:

```python
        if isinstance(r, pd.DataFrame) and "fedstats" in r.attrs:
            fs = r.attrs["fedstats"]
            kind = {"logit": "logit_init", "logit_round": "logit_round"}.get(
                fs.get("model"), "regress")
            min_n = (spec or {}).get("min_n")
            if min_n and (fs["n"] < min_n or any(a < min_n for a in fs["at_risk"])):
                stats.append({"kind": "refused", "reason":
                              "Personvern: for få enheter hos denne noden til å "
                              f"frigi regresjonsstatistikk (krever minst {min_n})."})
            else:
                stats.append({k: v for k, v in dict(fs, kind=kind).items()
                              if k != "model"})
            continue
```

- [ ] **Step 4:** `python3 -m pytest tests/test_federate_stats.py -q` → pass; full suite green.

- [ ] **Step 5: Commit** `feat(federert): extract logit init/round payloads with SDC gate`.

---

### Task 3: `FederatedDriver` — Newton loop state + render; combine refusal for stray logit kinds

**Files:**
- Modify: `m2py_runtime/federate.py`
- Test: `tests/test_federate_combine.py` (extend)

**Interfaces:**
- Consumes: Task 2 payload kinds; existing `combine_stats`/`combine_and_render`.
- Produces:
  - `combine_stats` maps `logit_init`/`logit_round` positions to `{"kind": "refused", "reason": "logit krever iterative runder — kjøres via den federerte driveren"}` (plain combine must never silently mishandle them).
  - `class FederatedDriver(per_node, members=None, overlap=None)`:
    - `.logit_spec()` → `None` or `{"index": int, "terms": [str], "beta": [0.0]*p}`; raises `ValueError` (Norwegian) if >1 logit position or terms differ across nodes.
    - `.step(per_node_round)` → `{"beta": [float], "converged": bool, "max_delta": float}` — sums grad/hess across nodes at position `index`, Newton-updates internal β (singular Hessian → `{"error": "..."}`), max 25 steps tracked internally, convergence at `max|Δβ| < 1e-8`.
    - `.render()` → same dict shape as `combine_and_render`, where the logit position renders the final `[term, coef, se, t, p]` frame (se from inv(H) at final β, z-stats, normal p) — or a refusal if never converged.

- [ ] **Step 1: Failing test** — the full driver loop against pooled statsmodels, simulating fan-out with `run_remote_from_sources`:

```python
def test_federated_logit_driver_matches_pooled(tmp_path):
    from m2py_remote import run_remote_from_sources
    rng = np.random.default_rng(11)
    x = rng.normal(size=120)
    p = 1 / (1 + np.exp(-(0.4 + 1.2 * x)))
    df = pd.DataFrame({"y": (rng.random(120) < p).astype(int), "x": x})
    parts = {"nord": df.iloc[:50], "vest": df.iloc[50:]}
    paths = {}
    for name, part in parts.items():
        pth = tmp_path / f"{name}.csv"
        part.to_csv(pth, index=False)
        paths[name] = str(pth)
    script = "create-dataset demo\nlogit y x"

    def fan_out(fed_round):
        out = []
        for name, pth in paths.items():
            res = run_remote_from_sources(
                script, [{"alias": "demo", "location": pth, "level": "public"}],
                federated=True, fed_round=fed_round)
            assert res["err"] is None, res["err"]
            out.append({"member": name, "stats": res["stats"]})
        return out

    drv = federate.FederatedDriver(fan_out(None))
    spec = drv.logit_spec()
    assert spec is not None and spec["terms"] == ["const", "x"]
    beta = spec["beta"]
    for _ in range(25):
        st = drv.step(fan_out({"beta": beta}))
        beta = st["beta"]
        if st["converged"]:
            break
    assert st["converged"]
    res = drv.render()
    frame = None
    import io
    got = pd.read_html(io.StringIO(res["results"][1 + spec["index"]]))[0]
    import statsmodels.api as sm
    X = sm.add_constant(df[["x"]])
    want = sm.Logit(df["y"], X).fit(disp=0)
    assert np.allclose(got["coef"].to_numpy(), want.params.to_numpy(), atol=1e-5)
    assert np.allclose(got["se"].to_numpy(), want.bse.to_numpy(), atol=1e-5)


def test_combine_stats_refuses_stray_logit():
    nodes = [{"member": "a", "stats": [{"kind": "logit_init", "terms": ["const"],
                                        "n": 10, "at_risk": [10]}]}]
    out = federate.combine_stats(nodes)
    assert out[0]["kind"] == "refused" and "iterative" in out[0]["reason"]
```

(This test also depends on Task 4's `fed_round` kwarg — implement Tasks 3+4 together before running it; the `combine_stats` test runs standalone.)

- [ ] **Step 2:** Run `python3 -m pytest tests/test_federate_combine.py -q` → new tests FAIL.

- [ ] **Step 3: Implement** in `m2py_runtime/federate.py`. In `combine_stats`'s dispatch add before the `else`:

```python
        elif kind in ("logit_init", "logit_round"):
            out.append({"kind": "refused", "reason":
                        "logit krever iterative runder — kjøres via den "
                        "federerte driveren"})
```

Append the driver:

```python
class FederatedDriver:
    """Koordinatortilstand for iterative verb (v1: én logit). Lever i Pyodide
    mellom fan-outs — JS er bare løkka. Runde 0-payload gis i konstruktøren;
    step() mater hver påfølgende runde; render() gir sluttresultatet der
    logit-posisjonen er byttet ut med den konvergerte tabellen."""

    MAX_ROUNDS = 25
    TOL = 1e-8

    def __init__(self, per_node, members=None, overlap=None):
        self._round0 = per_node
        self._members = members
        self._overlap = overlap
        self._logit = None
        idxs = [i for i, s in enumerate(per_node[0]["stats"])
                if s["kind"] == "logit_init"] if per_node else []
        if len(idxs) > 1:
            raise ValueError("én logit per federert skript (ennå) — "
                             "skriptet har " + str(len(idxs)))
        if idxs:
            i = idxs[0]
            column = [node["stats"][i] for node in self._round0]
            if any(s["kind"] != "logit_init" for s in column):
                self._logit = {"index": i, "error":
                               "medlemmene returnerte ulike resultattyper for logit-setningen"}
            elif any(s["terms"] != column[0]["terms"] for s in column):
                self._logit = {"index": i, "error":
                               "medlemmene har ulike logit-termer — samme "
                               "modellspesifikasjon kreves hos alle"}
            else:
                self._logit = {"index": i, "terms": column[0]["terms"],
                               "beta": [0.0] * len(column[0]["terms"]),
                               "hess": None, "rounds": 0, "converged": False,
                               "error": None, "n": sum(s["n"] for s in column)}

    def logit_spec(self):
        if not self._logit or self._logit.get("error"):
            return None
        return {"index": self._logit["index"], "terms": self._logit["terms"],
                "beta": list(self._logit["beta"])}

    def step(self, per_node_round):
        import numpy as np
        L = self._logit
        i = L["index"]
        column = [node["stats"][i] for node in per_node_round]
        bad = next((s for s in column if s["kind"] != "logit_round"), None)
        if bad is not None:
            L["error"] = bad.get("reason", "uventet rundesvar fra et medlem")
            return {"error": L["error"]}
        grad = sum(np.asarray(s["grad"], dtype=float) for s in column)
        hess = sum(np.asarray(s["hess"], dtype=float) for s in column)
        try:
            delta = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            L["error"] = "kombinert Hessian er singulær — modellen kan ikke poolgjøres"
            return {"error": L["error"]}
        L["beta"] = (np.asarray(L["beta"]) + delta).tolist()
        L["hess"] = hess
        L["rounds"] += 1
        md = float(np.max(np.abs(delta)))
        L["converged"] = md < self.TOL
        if L["rounds"] >= self.MAX_ROUNDS and not L["converged"]:
            L["error"] = ("logit konvergerte ikke innen " + str(self.MAX_ROUNDS)
                          + " runder")
        return {"beta": list(L["beta"]), "converged": L["converged"],
                "max_delta": md}

    def _logit_frame(self):
        import numpy as np
        import pandas as pd
        L = self._logit
        hinv = np.linalg.inv(L["hess"])
        se = np.sqrt(np.maximum(np.diag(hinv), 0.0))
        beta = np.asarray(L["beta"])
        with np.errstate(divide="ignore", invalid="ignore"):
            z = beta / se
        pvals = [math.erfc(abs(v) / math.sqrt(2)) for v in z]
        return pd.DataFrame({"term": L["terms"], "coef": beta, "se": se,
                             "t": z, "p": pvals})

    def render(self):
        res = combine_and_render(self._round0, members=self._members,
                                 overlap=self._overlap)
        L = self._logit
        if L:
            pos = 1 + L["index"]   # results[0] er fed-noten
            if L.get("error"):
                res["results"][pos] = "<pre class=\"error\">" + L["error"] + "</pre>"
            elif L["converged"]:
                res["results"][pos] = _render_frame(self._logit_frame())
            else:
                res["results"][pos] = ("<pre class=\"error\">logit ble aldri "
                                       "kjørt ferdig (ingen runder)</pre>")
        return res
```

- [ ] **Step 4:** After Task 4, run `python3 -m pytest tests/test_federate_combine.py -q` → all pass.

- [ ] **Step 5: Commit** (with Task 4) `feat(federert): Newton driver for federated logit`.

---

### Task 4: `run_remote` / node server pass `fed_round` through

**Files:**
- Modify: `m2py_remote.py` (both signatures), `node/safestat_node/server.py` once Task 5 exists — until then the old `scripts/dev_federert_node.py` gets the same two-line change so it keeps working for local tests.
- Test: covered by Task 3's driver test (uses the kwarg).

**Interfaces:**
- Produces: `run_remote(..., federated=False, fed_round=None)` and `run_remote_from_sources(..., federated=False, fed_round=None)`; when `fed_round` is a dict, `pandas_ops.set_fed_round(fed_round.get("beta"))` wraps the exec (cleared in `finally`). Node servers forward `req.get("fed_round")`.

- [ ] **Step 1: Implement** — in `run_remote`, extend the flag block:

```python
    _ops.set_federated(federated)
    _ops.set_fed_round((fed_round or {}).get("beta") if federated else None)
```

and in `finally`: `_ops.set_fed_round(None)`. Both signatures gain `fed_round=None`; `run_remote_from_sources` forwards it. In the node server's `do_POST`, the run call becomes:

```python
                              "result": run_remote_from_sources(
                                  req["script"], sources,
                                  federated=bool(req.get("federated")),
                                  fed_round=req.get("fed_round"))}
```

- [ ] **Step 2:** `python3 -m pytest tests/test_federate_combine.py tests/test_run_remote_from_sources.py -q` → all pass (driver test now green). Full suite green.

- [ ] **Step 3: Commit** together with Task 3.

---

### Task 5: `safestat-node` package (config, token auth, vendored engine)

**Files:**
- Create: `node/pyproject.toml`, `node/safestat_node/__init__.py`, `node/safestat_node/__main__.py`, `node/safestat_node/server.py`, `scripts/build_node_package.py`
- Delete: `scripts/dev_federert_node.py` (replaced; no users to migrate)
- Test: `tests/test_safestat_node.py` (new)

**Interfaces:**
- Produces: `safestat-node --config node.json` or `safestat-node --port 9301 --source id=path [--level L] [--token T]`; config JSON `{"port": int, "level": str, "token": str|absent, "sources": {id: path}}` (CLI flags win over config). With a token configured, every request (except OPTIONS) must carry `Authorization: Bearer <token>` → else 401. `server.create_server(config) -> ThreadingHTTPServer` (bindable to port 0 for tests); `server.main()` is the console entry point. Engine imports resolve from `safestat_node/_engine/` when present (pip install), else from the repo root (checkout). `scripts/build_node_package.py` copies the engine set into `_engine/`.

- [ ] **Step 1: Failing tests** — `tests/test_safestat_node.py`:

```python
"""safestat-node-serveren (fase 2): config, token-auth, run_extended."""
import json
import pathlib
import sys
import threading
import urllib.request
import urllib.error

import pandas as pd
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "node"))
from safestat_node import server as node_server


@pytest.fixture
def running_node(tmp_path):
    src = tmp_path / "demo.csv"
    pd.DataFrame({"grp": [1] * 6 + [2] * 7}).to_csv(src, index=False)
    cfg = {"port": 0, "level": "public", "token": "hemmelig",
           "sources": {"demo": str(src)}}
    srv = node_server.create_server(cfg)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d" % srv.server_address[1]
    srv.shutdown()


def _post(url, body, token=None):
    req = urllib.request.Request(url + "/_/api/run_extended",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    return urllib.request.urlopen(req)


def test_token_required(running_node):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(running_node, {"script": "", "sources": []})
    assert exc.value.code == 401


def test_run_extended_with_token(running_node):
    body = {"script": "create-dataset demo\ntabulate grp",
            "sources": [{"alias": "demo", "source_id": "demo"}],
            "federated": True}
    sub = json.loads(_post(running_node, body, token="hemmelig").read())
    req = urllib.request.Request(
        running_node + "/_/api/run_extended_status?task_id=" + sub["task_id"],
        headers={"Authorization": "Bearer hemmelig"})
    st = json.loads(urllib.request.urlopen(req).read())
    assert st["status"] == "completed"
    assert st["result"]["stats"][0]["kind"] == "tabulate"
```

- [ ] **Step 2:** Run `python3 -m pytest tests/test_safestat_node.py -q` → FAIL (`No module named 'safestat_node'`).

- [ ] **Step 3: Implement.** `node/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "safestat-node"
version = "0.1.0"
description = "Selvbetjent federert SafeStat-node: kjør m2py-skript mot lokale data, frigi kun SDC-gatede aggregater"
requires-python = ">=3.11"
dependencies = ["pandas", "numpy", "statsmodels", "pyarrow", "scipy"]

[project.scripts]
safestat-node = "safestat_node.server:main"

[tool.setuptools]
packages = ["safestat_node"]

[tool.setuptools.package-data]
safestat_node = ["_engine/*.py", "_engine/m2py_runtime/*.py"]
```

`node/safestat_node/__init__.py`: empty. `node/safestat_node/__main__.py`:

```python
from .server import main

main()
```

`node/safestat_node/server.py` — the phase-1 dev node, upgraded (engine path shim, config file, token, fed_round):

```python
"""safestat-node: selvbetjent federert node (fase 2, spec 2026-07-29 §6).

Same run_extended protocol as the Anvil server and the browser fan-out
expects: synchronous run at submit, one-shot status poll, permissive CORS.
Auth: optional bearer token (config/CLI) — required on everything but
OPTIONS when set. Engine: vendored copy under _engine/ (pip install), else
the repo root (checkout).

  safestat-node --config node.json
  safestat-node --port 9301 --source person=data/person.parquet --token X
"""
import argparse
import json
import pathlib
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ENGINE = pathlib.Path(__file__).resolve().parent / "_engine"
_REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ENGINE if (_ENGINE / "m2py_remote.py").exists() else _REPO))
from m2py_remote import run_remote_from_sources  # noqa: E402


def _make_handler(cfg, tasks):
    token = cfg.get("token")
    sources = cfg.get("sources", {})
    level = cfg.get("level", "public")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, Authorization")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self):
            if not token:
                return True
            return self.headers.get("Authorization") == "Bearer " + token

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers",
                             "Content-Type, Authorization")
            self.end_headers()

        def do_POST(self):
            if not self._authed():
                return self._send(401, {"error": "ugyldig eller manglende token"})
            if not self.path.startswith("/_/api/run_extended"):
                return self._send(404, {"error": "ukjent endepunkt"})
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            run_sources = []
            for s in req.get("sources", []):
                loc = sources.get(s.get("source_id"))
                if not loc:
                    return self._send(200, {"error": "ukjent kilde «%s» på denne noden"
                                            % s.get("source_id")})
                run_sources.append({"alias": s["alias"], "location": loc,
                                    "level": level})
            task_id = uuid.uuid4().hex
            try:
                tasks[task_id] = {"status": "completed",
                                  "result": run_remote_from_sources(
                                      req["script"], run_sources,
                                      federated=bool(req.get("federated")),
                                      fed_round=req.get("fed_round"))}
            except Exception as exc:
                tasks[task_id] = {"status": "failed", "error": repr(exc)}
            self._send(200, {"task_id": task_id})

        def do_GET(self):
            if not self._authed():
                return self._send(401, {"error": "ugyldig eller manglende token"})
            if not self.path.startswith("/_/api/run_extended_status"):
                return self._send(404, {"error": "ukjent endepunkt"})
            task_id = self.path.split("task_id=", 1)[-1].split("&")[0]
            self._send(200, tasks.get(task_id, {"status": "failed",
                                                "error": "ukjent task_id"}))

        def log_message(self, fmt, *args):
            print("[safestat-node:%s] %s"
                  % (self.server.server_address[1], fmt % args))

    return Handler


def create_server(cfg):
    tasks = {}
    return ThreadingHTTPServer(("127.0.0.1", int(cfg.get("port", 9301))),
                               _make_handler(cfg, tasks))


def main():
    ap = argparse.ArgumentParser(prog="safestat-node")
    ap.add_argument("--config")
    ap.add_argument("--port", type=int)
    ap.add_argument("--source", action="append", metavar="ID=PATH")
    ap.add_argument("--level", choices=["public", "protected", "sensitive"])
    ap.add_argument("--token")
    args = ap.parse_args()
    cfg = {}
    if args.config:
        cfg = json.loads(pathlib.Path(args.config).read_text())
    if args.port:
        cfg["port"] = args.port
    if args.level:
        cfg["level"] = args.level
    if args.token:
        cfg["token"] = args.token
    if args.source:
        cfg.setdefault("sources", {}).update(
            dict(pair.split("=", 1) for pair in args.source))
    if not cfg.get("sources"):
        ap.error("ingen kilder — bruk --source id=sti eller --config")
    srv = create_server(cfg)
    print("safestat-node på :%d (%s, %s%s)"
          % (srv.server_address[1], ", ".join(cfg["sources"]),
             cfg.get("level", "public"),
             ", token-beskyttet" if cfg.get("token") else ""))
    srv.serve_forever()


if __name__ == "__main__":
    main()
```

`scripts/build_node_package.py`:

```python
"""Vendorer motoren inn i node/safestat_node/_engine/ før pip-bygging.
Kjør på nytt etter enhver motorendring (samme disiplin som sync_to_api.py)."""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ROOT / "node" / "safestat_node" / "_engine"
FILES = ["m2py.py", "m2py_remote.py", "m2py_translate.py", "m2py_protection.py",
         "protect.py", "functions.py", "mockdata_core.py"]

if ENGINE.exists():
    shutil.rmtree(ENGINE)
(ENGINE / "m2py_runtime").mkdir(parents=True)
for f in FILES:
    shutil.copy2(ROOT / f, ENGINE / f)
for p in sorted((ROOT / "m2py_runtime").glob("*.py")):
    shutil.copy2(p, ENGINE / "m2py_runtime" / p.name)
print("vendored:", len(FILES) + len(list((ENGINE / 'm2py_runtime').glob('*.py'))), "filer")
```

Delete `scripts/dev_federert_node.py`. If the vendored set is missing an import at runtime, the Task 6 venv smoke reveals it — extend `FILES` there, not speculatively.

- [ ] **Step 4:** `python3 -m pytest tests/test_safestat_node.py -q` → 2 passed. Full pytest suite green.

- [ ] **Step 5: Commit** `feat(federert): safestat-node package with config and bearer-token auth`.

---

### Task 6: venv install E2E + browser token support

**Files:**
- Modify: `index.html` (`maybeRunFederatedMicrodata`: members with `"auth": "bearer"` prompt for a token via `mdPromptKey` and send it as the node's headers)
- Verification: throwaway venv in the scratchpad dir.

- [ ] **Step 1: Vendor + install + CLI smoke**

```bash
python3 scripts/build_node_package.py
python3 -m venv --system-site-packages "$SCRATCH/venv"
"$SCRATCH/venv/bin/pip" install --no-deps ./node -q
echo '{"port": 9301, "level": "public", "token": "t1", "sources": {"person": "'$PWD'/static_data/federert/nord/person.parquet"}}' > "$SCRATCH/node.json"
"$SCRATCH/venv/bin/safestat-node" --config "$SCRATCH/node.json" &
sleep 1
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:9301/_/api/run_extended -d '{}'        # 401
curl -s -X POST localhost:9301/_/api/run_extended -H 'Authorization: Bearer t1' -H 'Content-Type: application/json' \
  -d '{"script":"create-dataset person\ntabulate BEFOLKNING_KJOENN","sources":[{"alias":"person","source_id":"person"}],"federated":true}'
```

Expected: `401`, then a task_id; status poll (with token) → completed tabulate. Kill the node. If imports fail inside the venv, add the missing module to `FILES` in `build_node_package.py`, re-run vendor+install, retry.

- [ ] **Step 2: Browser token wiring** — in `maybeRunFederatedMicrodata`, the `nodes` mapping becomes:

```js
      var nodeMembers = entry.members.filter(function (mm) { return mm.tier === 'node'; });
      var nodes = [];
      for (var ni = 0; ni < nodeMembers.length; ni++) {
        var mm = nodeMembers[ni];
        var hdrs = undefined;
        if (mm.auth === 'bearer') {
          var tok = await mdPromptKey('token for «' + mm.id + '»');
          if (!tok) { outputArea.innerHTML = '<pre class="error">' + t('federert medlem «{id}» krever token', { id: mm.id }) + '</pre>'; return true; }
          hdrs = { 'Authorization': 'Bearer ' + tok };
        }
        nodes.push({ id: mm.id, api: mm.api, headers: hdrs,
                     body: { script: cleanScript, sources: [{ alias: alias, source_id: mm.source }],
                             backend: 'pandas', federated: true } });
      }
```

(`runNodes` already forwards `node.headers` on submit and poll — phase 1.)

- [ ] **Step 3:** `node --test tests/js/*.test.js` green; commit `feat(federert): venv-verified node install and bearer-token browser support`.

---

### Task 7: Browser logit driver loop

**Files:**
- Modify: `index.html` (`maybeRunFederatedMicrodata`'s combine block becomes a driver session)
- Test: browser E2E in Task 8 (the driver math itself is pytest-covered in Task 3).

**Interfaces:**
- Consumes: `FederatedDriver` (Task 3) via Pyodide (state persists between `py.runPython` calls), `Federate.runNodes` (existing), `fed_round` body field (Task 4).

- [ ] **Step 1: Implement** — replace the block from `var py = await loadPyodideAndM2py();` through `renderSafeStatResult(...)` with:

```js
        var py = await loadPyodideAndM2py();
        py.globals.set('__fed_payload', JSON.stringify({ per_node: payload, overlap: entry.overlap || null }));
        var specJson = py.runPython(
          'import json\n' +
          'from m2py_runtime.federate import FederatedDriver\n' +
          '_p = json.loads(__fed_payload)\n' +
          '__fed_driver = FederatedDriver(_p["per_node"], overlap=_p["overlap"])\n' +
          'json.dumps(__fed_driver.logit_spec())');
        var spec = JSON.parse(specJson);
        if (spec) {
          var beta = spec.beta;
          for (var round = 0; round < 25; round++) {
            outputArea.innerHTML = '<div style="padding:8px;opacity:.6">' + t('Federert logit: runde {r}…', { r: round + 1 }) + '</div>';
            var roundNodes = nodes.map(function (nd) {
              return { id: nd.id, api: nd.api, headers: nd.headers,
                       body: Object.assign({}, nd.body, { fed_round: { beta: beta } }) };
            });
            var roundResults = await window.Federate.runNodes(roundNodes, {});
            var roundPayload = roundResults.map(function (r) { return { member: r.id, stats: (r.result && r.result.stats) || [] }; });
            py.globals.set('__fed_round', JSON.stringify(roundPayload));
            var stJson = py.runPython('json.dumps(__fed_driver.step(json.loads(__fed_round)))');
            var st = JSON.parse(stJson);
            if (st.error) break;
            beta = st.beta;
            if (st.converged) break;
          }
        }
        var resJson = py.runPython('json.dumps(__fed_driver.render())');
        renderSafeStatResult(JSON.parse(resJson), script, ctx, t('federert ({n} noder)', { n: nodes.length }));
```

Note `render()` returns DataFrames rendered to HTML inside Python — JSON-safe already.

- [ ] **Step 2:** `node --test tests/js/*.test.js` + full pytest green (no logic moved, only wiring). Commit `feat(federert): browser Newton-round driver for federated logit`.

---

### Task 8: E2E smoke + docs + status + merge

- [ ] **Step 1:** Two package nodes (no tokens, so the browser flow stays unprompted): `PYTHONPATH=node python3 -m safestat_node --port 9301 --source person=static_data/federert/nord/person.parquet` and 9302 with vest; app on 8127. In microdata mode run:

```
require demo-federert-node as person
create-dataset person
generate kvinne = BEFOLKNING_KJOENN == 2
logit kvinne BEFOLKNING_INNALDER
```

(First verify that exact script works through `run_remote_from_sources` in a REPL, and that `generate`'s comparison syntax is right — adjust the smoke script to whatever the DSL accepts, e.g. `generate kvinne = (BEFOLKNING_KJOENN == 2)`.) Expected: converged coef table; verify coef against pooled statsmodels on the concatenated parquet in a one-liner.

- [ ] **Step 2:** Negative: rerun with node 9302 down → error naming «vest».

- [ ] **Step 3:** Docs: `docs/directive-language-examples.md` §14 node paragraph gains logit + the `safestat-node` install line (`pip install ./node`, `safestat-node --config node.json`, token support). Spec §6/status: safestat-node + logit implemented; trusted-hub + overlap still deferred. Tick this plan + execution log. Update `node/README`? No — pyproject description suffices (YAGNI).

- [ ] **Step 4:** Suites green → merge `federert-fase2` to master, delete branch. No push.

---

## Self-review notes

- Spec §6 coverage: safestat-node (T5–T6), logistic via iterative rounds (T1–T4, T7–T8); trusted-hub + overlap explicitly deferred with reasons (header).
- Type consistency: `fedstats["model"]` values "logit"/"logit_round" (T1) ↔ extract kinds "logit_init"/"logit_round" (T2) ↔ driver consumption (T3); `fed_round: {beta}` shape identical in T3-test/T4/T7; config dict keys identical in T5 code/tests/T6 smoke.
- The engine vendoring list is intentionally minimal-with-arbiter (venv smoke) rather than speculative-complete — noted in T5/T6.
