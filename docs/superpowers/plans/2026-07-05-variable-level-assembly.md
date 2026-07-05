# Variable-level Assembly Language (Project A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dialect modes (python/r/duckdb) a common assembly language — `create-dataset key(k)` / `import src/col into ds` / `join ds2 into ds on k` / `load src as ds` — that compiles to a mode-neutral spec run by one shared executor, producing named frames identically in the browser (open + strict) and on the server (protected/remote).

**Architecture:** A pure-pandas executor `safepy/assembly.py` (vendored to both surfaces by the existing sync) turns an AssemblySpec + a `resolver(source_alias)->DataFrame` into named DataFrames. `js/data-directives.js` parses the new verbs into the spec; `js/data-loader.js` fetches the referenced *sources* (reusing grant/decrypt/remote routing) and returns the spec; the run handler runs the executor in a Pyodide preamble (local) and `safepy_shim` runs it before `safepy.run` (remote). Assembly is trusted code, outside the safepy facade.

**Tech Stack:** pandas (Pyodide + server), WebCrypto/existing loader, Deno tests (JS), pytest (Python), Playwright (browser).

**Spec:** `docs/superpowers/specs/2026-07-05-variable-level-assembly-design.md`.

## Global Constraints

- Repos: safepy (executor, source of truth), m2py (parser/loader/UI), microdata-api (remote shim). All on `dev`, pushed after each version; the executor reaches both surfaces via `python m2py/sync_to_api.py --apply` (Anvil + `vendor/safepy.zip`).
- **Common verbs only for dialect modes** (python/r/duckdb). Microdata mode is untouched; an assembly directive there errors with a clear message.
- **Source vs dataset distinction is load-bearing:** *sources* = connect aliases (fetched whole); *datasets* = named results the executor builds; only datasets are user-visible.
- Assembly is **structure only** — select columns, equi-join on a single key, whole-table load. No filter/derive/aggregate (those stay in the analysis script).
- Default join = **left onto the accumulator**, overridable `inner`/`outer`/`left`. Single key per dataset (v1).
- **All-or-nothing routing:** if any referenced source routes remote, the whole run (assembly + analysis) goes remote; else local. Mirrors existing behavior.
- Assembly runs as **trusted code**, never through the safepy STRICT facade.
- Backward compatibility: a bare `# load <url> as df` (no other assembly) must keep working exactly as today (it becomes a trivial single-source dataset).
- Norwegian user-facing errors. No new JS deps. Browser modules keep the `(function(global){…})(…)` pattern.
- Test commands: `python -m pytest tests/ -x -q` per repo; `cd m2py/netlify/edge-functions && deno test --allow-read --allow-env _lib/<f>.test.ts`.

## AssemblySpec (the IR every layer speaks)

```json
{
  "sources": ["p", "s"],
  "datasets": [
    {"name": "sales", "load": "s"},
    {"name": "panel", "key": "pid", "steps": [
      {"op": "import", "source": "p", "columns": ["income", "edu"], "how": "left"},
      {"op": "import", "source": "p", "columns": ["region"], "how": "left"},
      {"op": "join", "from": "sales", "on": "pid", "how": "left"}
    ]}
  ]
}
```
- `sources` = connect aliases to fetch whole (import sources + load targets; NOT join `from`, which is a dataset).
- `load` datasets = the whole source. `steps` datasets = assembled in written order.
- `join.from` references an already-built dataset name.

## File Structure

| File | Repo | Responsibility |
|---|---|---|
| `safepy/assembly.py` (new) | safepy | Pure executor: validate + build named DataFrames from a spec |
| `tests/test_assembly.py` (new) | safepy | Executor unit tests |
| `js/data-directives.js` (modify) | m2py | Parse create-dataset/import/join → spec; keep parse/resolve |
| `netlify/edge-functions/_lib/data-directives.test.ts` (modify) | m2py | Parser tests |
| `js/data-loader.js` (modify) | m2py | Fetch spec sources; return `{sources, remote, spec}` |
| `netlify/edge-functions/_lib/data-loader.test.ts` (modify) | m2py | Loader tests |
| `index.html` (modify) | m2py | Assembly preamble (local); route python/r/duckdb |
| `server_code/safepy_shim.py` (modify) | microdata-api | Run executor before safepy.run; accept spec |
| `server_code/api_endpoints.py` (modify) | microdata-api | Pass `assembly` through /run_extended → bg task |
| `tests/test_assembly_shim.py` (new) | microdata-api | Remote assembly tests |
| `examples/py31_assembly.txt`, `r31_assembly.txt`, `sql31_assembly.txt` (new) | m2py | Documented examples |

---

## Task 1: `safepy/assembly.py` — the shared executor (safepy)

**Files:**
- Create: `safepy/safepy/assembly.py`
- Test: `safepy/tests/test_assembly.py`

**Interfaces:**
- Produces (used by loader-preamble and shim):
  - `referenced_sources(spec: dict) -> list[str]` — connect aliases to fetch.
  - `build_datasets(spec: dict, resolver) -> tuple[dict, list[str]]` — `resolver(alias)->DataFrame`; returns `(datasets_by_name, notes)`. `notes` are Norwegian row-multiplication strings. Raises `AssemblyError` (subclass of ValueError) with a Norwegian message on any structural problem.
  - `AssemblyError` exception class.

- [ ] **Step 1: Write the failing tests**

`safepy/tests/test_assembly.py`:

```python
"""Pure executor for the variable-level assembly language (Project A).
resolver(alias) -> DataFrame; build_datasets -> {name: DataFrame}. No Anvil,
no Pyodide, no safepy engine — plain pandas."""
import pandas as pd
import pytest

from safepy import assembly


def _resolver(frames):
    def r(alias):
        if alias not in frames:
            raise assembly.AssemblyError(f"ukjent kilde «{alias}»")
        return frames[alias]
    return r


PEOPLE = pd.DataFrame({"pid": [1, 2, 3], "income": [10, 20, 30],
                       "edu": ["a", "b", "c"], "region": ["N", "S", "N"]})
SALES = pd.DataFrame({"pid": [1, 2, 2], "amount": [5, 6, 7]})


def test_referenced_sources():
    spec = {"sources": ["p", "s"], "datasets": []}
    assert assembly.referenced_sources(spec) == ["p", "s"]


def test_load_whole_source():
    spec = {"sources": ["p"], "datasets": [{"name": "d", "load": "p"}]}
    out, _ = assembly.build_datasets(spec, _resolver({"p": PEOPLE}))
    assert list(out["d"].columns) == ["pid", "income", "edu", "region"]
    assert len(out["d"]) == 3


def test_import_selects_columns_plus_key():
    spec = {"sources": ["p"], "datasets": [
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income"], "how": "left"}]}]}
    out, _ = assembly.build_datasets(spec, _resolver({"p": PEOPLE}))
    assert sorted(out["panel"].columns) == ["income", "pid"]      # key + selected
    assert len(out["panel"]) == 3


def test_second_import_merges_on_key():
    spec = {"sources": ["p"], "datasets": [
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income"], "how": "left"},
            {"op": "import", "source": "p", "columns": ["region"], "how": "left"}]}]}
    out, _ = assembly.build_datasets(spec, _resolver({"p": PEOPLE}))
    assert sorted(out["panel"].columns) == ["income", "pid", "region"]
    assert len(out["panel"]) == 3


def test_join_dataset_left_default():
    spec = {"sources": ["p", "s"], "datasets": [
        {"name": "sales", "load": "s"},
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income"], "how": "left"},
            {"op": "join", "from": "sales", "on": "pid", "how": "left"}]}]}
    out, notes = assembly.build_datasets(spec, _resolver({"p": PEOPLE, "s": SALES}))
    # left join panel(3 rows) with sales(pid 1,2,2) -> pid1 x1, pid2 x2, pid3 x1 = 4
    assert len(out["panel"]) == 4
    assert any("rader" in n for n in notes)         # row-multiplication note


def test_inner_join_override():
    spec = {"sources": ["p", "s"], "datasets": [
        {"name": "sales", "load": "s"},
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income"], "how": "left"},
            {"op": "join", "from": "sales", "on": "pid", "how": "inner"}]}]}
    out, _ = assembly.build_datasets(spec, _resolver({"p": PEOPLE, "s": SALES}))
    assert set(out["panel"]["pid"]) == {1, 2}       # pid 3 dropped (inner)


def test_unknown_dataset_in_join():
    spec = {"sources": ["p"], "datasets": [
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income"], "how": "left"},
            {"op": "join", "from": "nope", "on": "pid", "how": "left"}]}]}
    with pytest.raises(assembly.AssemblyError, match="ukjent datasett «nope»"):
        assembly.build_datasets(spec, _resolver({"p": PEOPLE}))


def test_missing_column():
    spec = {"sources": ["p"], "datasets": [
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["salary"], "how": "left"}]}]}
    with pytest.raises(assembly.AssemblyError, match="kolonnen «salary»"):
        assembly.build_datasets(spec, _resolver({"p": PEOPLE}))


def test_missing_key_in_source():
    nokey = pd.DataFrame({"x": [1], "income": [9]})
    spec = {"sources": ["p"], "datasets": [
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income"], "how": "left"}]}]}
    with pytest.raises(assembly.AssemblyError, match="nøkkelkolonnen «pid»"):
        assembly.build_datasets(spec, _resolver({"p": nokey}))


def test_key_dtype_mismatch_note_or_error():
    s2 = pd.DataFrame({"pid": ["1", "2"], "amount": [5, 6]})   # str keys
    spec = {"sources": ["p", "s"], "datasets": [
        {"name": "sales", "load": "s"},
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income"], "how": "left"},
            {"op": "join", "from": "sales", "on": "pid", "how": "left"}]}]}
    with pytest.raises(assembly.AssemblyError, match="ulik type"):
        assembly.build_datasets(spec, _resolver({"p": PEOPLE, "s": s2}))
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/test_assembly.py -x -q`
Expected: collection error — `cannot import name 'assembly'`

- [ ] **Step 3: Implement `safepy/safepy/assembly.py`**

```python
# safepy/assembly.py
"""Variable-level assembly executor (Project A, spec
m2py/docs/superpowers/specs/2026-07-05-variable-level-assembly-design.md).

Pure pandas: turns a mode-neutral AssemblySpec + a resolver(source_alias)->
DataFrame into named DataFrames. Trusted code (never the safepy facade); the
same file runs in the browser (Pyodide) and on the server (shim), vendored to
both by m2py/sync_to_api.py, so local and remote assembly cannot diverge.

Assembly is structure only: whole-table load, column select, single-key
equi-join (left default). Rows/derivation/aggregation are the analysis
script's job.
"""
from __future__ import annotations


class AssemblyError(ValueError):
    """Structural problem in an assembly spec (Norwegian message)."""


_VALID_HOW = {"left", "inner", "outer"}


def referenced_sources(spec: dict) -> list[str]:
    return list(spec.get("sources") or [])


def _check_key(df, key, where):
    if key not in df.columns:
        raise AssemblyError(f"{where} mangler nøkkelkolonnen «{key}»")


def build_datasets(spec: dict, resolver):
    """spec + resolver(alias)->DataFrame -> ({name: DataFrame}, [notes])."""
    datasets: dict = {}
    notes: list = []

    for ds in spec.get("datasets") or []:
        name = ds["name"]
        if "load" in ds:
            datasets[name] = resolver(ds["load"])
            continue

        key = ds.get("key")
        if not key:
            raise AssemblyError(f"datasettet «{name}» mangler key(...)")
        acc = None                                   # accumulator, built by steps

        for step in ds.get("steps") or []:
            how = step.get("how", "left")
            if how not in _VALID_HOW:
                raise AssemblyError(f"ukjent join-type «{how}»")

            if step["op"] == "import":
                src = resolver(step["source"])
                _check_key(src, key, f"kilden «{step['source']}»")
                missing = [c for c in step["columns"] if c not in src.columns]
                if missing:
                    raise AssemblyError(
                        f"kolonnen «{missing[0]}» finnes ikke i kilden "
                        f"«{step['source']}» (har: {', '.join(map(str, src.columns))})")
                piece = src[[key] + list(step["columns"])].copy()
                if acc is None:
                    acc = piece                       # first import establishes rows
                else:
                    _merge_check(acc, piece, key, name, step["source"])
                    before = len(acc)
                    acc = acc.merge(piece, on=key, how=how)
                    _note_multiplication(notes, name, before, len(acc))

            elif step["op"] == "join":
                on = step["on"]
                other = datasets.get(step["from"])
                if other is None:
                    raise AssemblyError(f"ukjent datasett «{step['from']}» "
                                        f"(join into «{name}» — feil rekkefølge?)")
                if acc is None:
                    raise AssemblyError(f"«{name}» er tomt — importer variabler "
                                        f"før join")
                _check_key(acc, on, f"«{name}»")
                _check_key(other, on, f"«{step['from']}»")
                _merge_check(acc, other, on, name, step["from"])
                before = len(acc)
                acc = acc.merge(other, on=on, how=how)
                _note_multiplication(notes, name, before, len(acc))
            else:
                raise AssemblyError(f"ukjent monterings-operasjon «{step['op']}»")

        datasets[name] = acc if acc is not None else _empty()
    return datasets, notes


def _merge_check(a, b, key, name, other_name):
    if a[key].dtype != b[key].dtype:
        raise AssemblyError(
            f"nøkkelen «{key}» har ulik type i «{name}» og «{other_name}»")


def _note_multiplication(notes, name, before, after):
    if after != before:
        notes.append(f"{name}: {before} → {after} rader etter join")


def _empty():
    import pandas as pd
    return pd.DataFrame()
```

- [ ] **Step 4: Run tests + full safepy suite**

Run: `cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/test_assembly.py tests/ -x -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/safepy
git add safepy/assembly.py tests/test_assembly.py
git commit -m "feat(assembly): pure executor for variable-level assembly (Project A)"
```

---

## Task 2: Parser — `data-directives.js` emits the AssemblySpec (m2py)

**Files:**
- Modify: `m2py/js/data-directives.js`
- Test: `m2py/netlify/edge-functions/_lib/data-directives.test.ts`

**Interfaces:**
- Consumes: existing `parse()` (connects/loads).
- Produces: `DataDirectives.parseAssembly(script) -> {spec, errors}` where `spec = {sources: [...], datasets: [...]}` per the IR. `create-dataset <name>, key(<k>)` → a keyed dataset; `import <a>/<c>[, <a>/<c>...] into <name> [how]` → import step; `join <name> into <target> on <col> [how]` → join step; `load <src> as <name>` (bare source, no `/`) → `{name, load: src}`. `sources` = unique import-sources ∪ load-targets. Directives resolve source aliases through the existing connect list (a `load h as x` / `import h/c` where `h` is a connect alias or a URL). Errors: unknown alias, import into a dataset with no create-dataset, duplicate dataset name.

- [ ] **Step 1: Extend the Deno test (failing)**

Append to `data-directives.test.ts`:

```typescript
Deno.test("parseAssembly: create-dataset + import + join + load", () => {
  const script = [
    "# connect people as p",
    "# connect sales_src as s",
    "# create-dataset panel, key(pid)",
    "# import p/income, p/edu into panel",
    "# import p/region into panel",
    "# load s as sales",
    "# join sales into panel on pid",
  ].join("\n");
  const { spec, errors } = DD.parseAssembly(script);
  assertEquals(errors, []);
  assertEquals(spec.sources.sort(), ["p", "s"]);
  const panel = spec.datasets.find((d: {name: string}) => d.name === "panel");
  assertEquals(panel.key, "pid");
  assertEquals(panel.steps.length, 3);
  assertEquals(panel.steps[0], {op: "import", source: "p", columns: ["income", "edu"], how: "left"});
  assertEquals(panel.steps[2], {op: "join", from: "sales", on: "pid", how: "left"});
  const sales = spec.datasets.find((d: {name: string}) => d.name === "sales");
  assertEquals(sales.load, "s");
});

Deno.test("parseAssembly: how override", () => {
  const { spec } = DD.parseAssembly(
    "# connect p as p\n# create-dataset d, key(id)\n# import p/x into d inner");
  assertEquals(spec.datasets[0].steps[0].how, "inner");
});

Deno.test("parseAssembly: import into missing dataset errors", () => {
  const { errors } = DD.parseAssembly("# connect p as p\n# import p/x into ghost");
  if (!errors.some((e: string) => e.includes("ghost"))) throw new Error("ventet feil for ukjent datasett");
});

Deno.test("parseAssembly: bare load still works (backward compat)", () => {
  const { spec } = DD.parseAssembly("# load https://x.example/d.csv as df");
  assertEquals(spec.datasets[0], {name: "df", load: "df"});
  assertEquals(spec.sources, ["df"]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/data-directives.test.ts`
Expected: new tests FAIL (`parseAssembly` undefined)

- [ ] **Step 3: Implement `parseAssembly` in `data-directives.js`**

Add these regexes near the existing ones (top of the IIFE):

```javascript
  var CREATE_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*create-dataset[ \t]+([A-Za-z_]\w*)[ \t]*,[ \t]*key\(\s*([A-Za-z_]\w*)\s*\)[ \t]*$/gim;
  var IMPORT_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*import[ \t]+(\S+(?:[ \t]*,[ \t]*\S+)*)[ \t]+into[ \t]+([A-Za-z_]\w*)(?:[ \t]+(left|inner|outer))?[ \t]*$/gim;
  var JOIN_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*join[ \t]+([A-Za-z_]\w*)[ \t]+into[ \t]+([A-Za-z_]\w*)[ \t]+on[ \t]+([A-Za-z_]\w*)(?:[ \t]+(left|inner|outer))?[ \t]*$/gim;
  var LOADAS_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*load[ \t]+([A-Za-z_]\w*)[ \t]+as[ \t]+([A-Za-z_]\w*)[ \t]*$/gim;
```

Add the function (and export it):

```javascript
  // Project A: parse create-dataset/import/join/load into a mode-neutral spec.
  function parseAssembly(script) {
    var errors = [], datasets = [], byName = {}, sources = {}, m;
    // connect aliases (for source validation)
    var conns = {};
    parse(script).connects.forEach(function (c) { conns[c.alias] = true; });

    CREATE_RE.lastIndex = 0;
    while ((m = CREATE_RE.exec(script)) !== null) {
      if (byName[m[1]]) { errors.push('datasettet «' + m[1] + '» er allerede opprettet'); continue; }
      var d = { name: m[1], key: m[2], steps: [] };
      datasets.push(d); byName[m[1]] = d;
    }
    LOADAS_RE.lastIndex = 0;
    while ((m = LOADAS_RE.exec(script)) !== null) {
      var srcL = m[1], nameL = m[2];
      if (byName[nameL]) { errors.push('datasettet «' + nameL + '» er allerede opprettet'); continue; }
      var dl = { name: nameL, load: srcL };
      datasets.push(dl); byName[nameL] = dl; sources[srcL] = true;
    }
    IMPORT_RE.lastIndex = 0;
    while ((m = IMPORT_RE.exec(script)) !== null) {
      var target = m[2];
      var d2 = byName[target];
      if (!d2 || d2.load) { errors.push('ukjent datasett «' + target + '» (mangler create-dataset?)'); continue; }
      var bySrc = {};
      m[1].split(',').forEach(function (ref) {
        var parts = ref.trim().split('/');
        if (parts.length !== 2) { errors.push('import krever <kilde>/<kolonne>: ' + ref.trim()); return; }
        var src = parts[0].trim(), col = parts[1].trim();
        sources[src] = true;
        (bySrc[src] = bySrc[src] || []).push(col);
      });
      Object.keys(bySrc).forEach(function (src) {
        d2.steps.push({ op: 'import', source: src, columns: bySrc[src], how: (m[3] || 'left') });
      });
    }
    JOIN_RE.lastIndex = 0;
    while ((m = JOIN_RE.exec(script)) !== null) {
      var tgt = m[2], d3 = byName[tgt];
      if (!d3 || d3.load) { errors.push('ukjent datasett «' + tgt + '» (mangler create-dataset?)'); continue; }
      if (!byName[m[1]]) { errors.push('ukjent datasett «' + m[1] + '» i join'); continue; }
      d3.steps.push({ op: 'join', from: m[1], on: m[3], how: (m[4] || 'left') });
    }
    return { spec: { sources: Object.keys(sources), datasets: datasets }, errors: errors };
  }
```

Change the export line to include it:
```javascript
  global.DataDirectives = { parse: parse, resolve: resolve, scrubKeys: scrubKeys, parseAssembly: parseAssembly };
```

NOTE the ordering: the IMPORT regex runs after CREATE and LOADAS so imports find their datasets. Since `import` groups columns per source into one step, `import p/income, p/edu` → one step with `columns: ["income","edu"]` (test asserts this). Verify the multi-column single-source grouping matches the test.

- [ ] **Step 4: Run tests**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read _lib/data-directives.test.ts`
Expected: all pass (old + 4 new). If a pre-existing `load ssb/path as x` (registry path) test now also matches LOADAS_RE — it won't, because LOADAS_RE requires a bare `[A-Za-z_]\w*` source with no `/`; registry paths contain `/` and are handled by the existing LOAD_RE, untouched.

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/data-directives.js netlify/edge-functions/_lib/data-directives.test.ts
git commit -m "feat(directives): parseAssembly — create-dataset/import/join/load -> AssemblySpec"
```

---

## Task 3: Loader — fetch spec sources, return `{sources, remote, spec}` (m2py)

**Files:**
- Modify: `m2py/js/data-loader.js`
- Test: `m2py/netlify/edge-functions/_lib/data-loader.test.ts`

**Interfaces:**
- Consumes: `DataDirectives.parseAssembly` (Task 2), existing `resolve`/fetch/decrypt/grant machinery.
- Produces: `DataLoader.resolveAndAssemble(script, deps) -> Promise<{sources: [{alias, bytes, format, strict?, level?}], remote: [{alias, sourceId, key?}], spec}>`. It fetches each spec source once (a spec source is a connect alias → resolved like a whole-table `load <alias> as <alias>`), reusing all grant/decrypt/authorize logic. If any source routes remote, it goes in `remote` (and the caller runs the whole thing server-side with the spec). `resolveAndFetchLoads` stays for non-assembly callers (R currently; unchanged).

- [ ] **Step 1: Failing Deno test**

Append to `data-loader.test.ts`:

```typescript
Deno.test("resolveAndAssemble: fetches spec sources + returns spec", async () => {
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    const body = url.includes("people") ? "pid,income\n1,10\n2,20" : "pid,amount\n1,5";
    return Promise.resolve(new Response(body, { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const script = [
    "# connect https://x.example/people.csv as p",
    "# connect https://x.example/sales.csv as s",
    "# create-dataset panel, key(pid)",
    "# import p/income into panel",
    "# load s as sales",
    "# join sales into panel on pid",
  ].join("\n");
  const out = await DL.resolveAndAssemble(script, { fetchImpl, registry: [] });
  assertEquals(out.remote, []);
  assertEquals(out.sources.map((x: {alias: string}) => x.alias).sort(), ["p", "s"]);
  assertEquals(out.spec.datasets.find((d: {name: string}) => d.name === "panel").key, "pid");
  const p = out.sources.find((x: {alias: string}) => x.alias === "p");
  assertEquals(new TextDecoder().decode(p.bytes), "pid,income\n1,10\n2,20");
});

Deno.test("resolveAndAssemble: a remote source routes the whole run remote", async () => {
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(
      new Response(JSON.stringify({ remote_only: true, default_exec: "remote" }),
        { status: 200, headers: { "content-type": "application/json" } }));
    return Promise.resolve(new Response("pid,x\n1,2", { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const script = [
    "# connect helse2025 as h",
    "# create-dataset panel, key(pid)",
    "# import h/x into panel",
  ].join("\n");
  const out = await DL.resolveAndAssemble(script, { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.remote, [{ alias: "h", sourceId: "helse2025", key: undefined }]);
  assertEquals(out.sources, []);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read --allow-env _lib/data-loader.test.ts`
Expected: new tests FAIL (`resolveAndAssemble` undefined)

- [ ] **Step 3: Implement `resolveAndAssemble` in `data-loader.js`**

Reuse the internals of `resolveAndFetchLoads`. The key move: build a synthetic "loads" list where each spec source becomes a whole-table load (`# load <alias> as <alias>`), run it through the SAME resolve/fetch/grant/decrypt path, then return `{sources, remote, spec}`.

```javascript
  // Project A: fetch the SOURCES a spec needs (each connect alias as a whole
  // table), honoring grants/decrypt/remote routing exactly like load does, and
  // return the spec so the runtime can assemble. Same fetch layer as
  // resolveAndFetchLoads — only the shape of the request changes.
  async function resolveAndAssemble(script, deps) {
    deps = deps || {};
    var DD = global.DataDirectives;
    if (!DD) return { sources: [], remote: [], spec: { sources: [], datasets: [] } };
    var parsed = DD.parseAssembly(script);
    if (parsed.errors.length) throw new Error('Monteringsfeil: ' + parsed.errors.join('; '));
    var spec = parsed.spec;
    if (!spec.sources.length) return { sources: [], remote: [], spec: spec };

    // Synthesize a "load <alias> as <alias>" per source and run the existing pipeline.
    var srcScript = spec.sources.map(function (a) { return '# load ' + a + ' as ' + a; }).join('\n')
      + '\n' + script;   // include original so connect lines + options resolve
    var loaded = await resolveAndFetchLoads(srcScript, deps);
    return { sources: loaded.loads, remote: loaded.remote, spec: spec };
  }

  global.DataLoader = { resolveAndFetchLoads: resolveAndFetchLoads, resolveAndAssemble: resolveAndAssemble, _sniffFormat: sniffFormat };
```

Implementation note: verify `resolveAndFetchLoads` de-duplicates a source referenced by both the synthesized `load a as a` and any original `load a as a` — since a spec `load s as sales` already synthesizes `load s as s` AND the original `load s as sales`, both fetch source `s`. That double-fetch of the same URL is harmless but wasteful; if the existing pipeline errors on a duplicate alias, strip original bare `load` lines from `script` before appending (they're represented in `spec.datasets`), keeping only `connect` lines. Prefer: pass just the `connect` lines + synthesized source-loads:
```javascript
    var connectLines = script.split(/\r?\n/).filter(function (ln) { return /^[ \t]*(?:#|--|\/\/)[ \t]*connect\b/.test(ln); }).join('\n');
    var srcScript = connectLines + '\n' + spec.sources.map(function (a) { return '# load ' + a + ' as ' + a; }).join('\n');
```
Use this second form (connects + synthesized loads only) so each source is fetched exactly once.

- [ ] **Step 4: Run tests**

Run: `cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read --allow-env _lib/data-loader.test.ts`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add js/data-loader.js netlify/edge-functions/_lib/data-loader.test.ts
git commit -m "feat(loader): resolveAndAssemble — fetch spec sources + carry spec, reuse grant/decrypt path"
```

---

## Task 4: Local execution (python mode) + assembly preamble (m2py)

**Files:**
- Modify: `m2py/index.html`
- Run: `python sync_to_api.py --web` (bundle `assembly.py` into `vendor/safepy.zip`)

**Interfaces:**
- Consumes: `resolveAndAssemble` (Task 3), `safepy.assembly` (Task 1, via the zip), existing `loadPyodideAndM2py`, `ensureSafepyLoaded` (loads the zip; already used by strict), `to_microdata`/`sync_datasets_to_globals` for binding.
- Produces: `buildAssemblyPreamble(sources, spec) -> pythonString` that reads each source's FS file into a frame, runs `assembly.build_datasets`, binds each dataset by name (and prints notes), used before the analysis script.

- [ ] **Step 1: Add `buildAssemblyPreamble`** (near `buildWebDataLoaderPreamble`, `index.html:6725`):

```javascript
    // Project A: build named datasets from an AssemblySpec via the shared
    // safepy.assembly executor (same code as the server), then bind them for
    // the analysis script. Sources are the fetched whole tables on the FS.
    function buildAssemblyPreamble(loads, spec) {
      if (!spec || !spec.datasets || !spec.datasets.length) return '';
      return `
# ── Project A: montér datasett fra kilder (delt executor safepy.assembly) ──
import json as _json, pandas as _pd
from safepy import assembly as _asm
_asm_src = {}
for _al in json.loads(${JSON.stringify(JSON.stringify(loads.map(function (l) { return { alias: l.alias, format: l.format, path: l.path }; })))}):
    _asm_src[_al["alias"]] = (_pd.read_parquet(_al["path"]) if _al["format"] == "parquet" else _pd.read_csv(_al["path"]))
_asm_spec = json.loads(${JSON.stringify(JSON.stringify(spec))})
_asm_ds, _asm_notes = _asm.build_datasets(_asm_spec, lambda a: _asm_src[a])
for _n, _df in _asm_ds.items():
    to_microdata(_df, name=_n, make_active=False)
for _note in _asm_notes:
    print(_note)
`;
    }
```

- [ ] **Step 2: Route python mode through assembly when the script has assembly verbs**

In the run handler (python/duckdb block, around `index.html:8750-8790`), detect assembly and branch. Read the current `_dl = await window.DataLoader.resolveAndFetchLoads(...)` block; when the script contains `create-dataset`/`import ... into`/`join ... into` OR any `# load <bare> as`, use `resolveAndAssemble` instead and the assembly preamble:

```javascript
        var _hasAssembly = /^[ \t]*(?:#|--|\/\/)[ \t]*(create-dataset|import|join)\b/im.test(effectiveScript)
          || /^[ \t]*(?:#|--|\/\/)[ \t]*load[ \t]+[A-Za-z_]\w*[ \t]+as\b/im.test(effectiveScript);
```

When `_hasAssembly` and mode is python: call `resolveAndAssemble`; if `_asm.remote.length`, route the whole run remote with the spec (Task 6 handles the body — for now pass `assembly: _asm.spec` to `runSafeStatRemote`); else fetch sources to FS (same FS-write mapping as `_pyLoads`, keyed by source alias), and inject `buildAssemblyPreamble(_pyLoads, _asm.spec)` into `setupCode` right after `buildWebDataLoaderPreamble(...)`. Ensure `ensureSafepyLoaded(py)` runs first (assembly.py lives in the zip). The strict/grant handling for sources is already inside `resolveAndAssemble` (it reuses the same path).

Precise wiring (adapt to the actual block):
```javascript
        if (_hasAssembly && activeEditorMode === 'python') {
          var _asm = await window.DataLoader.resolveAndAssemble(effectiveScript, {
            authToken: getAuthToken(), anthropicKey: getAnthropicKey(), apiBase: getMdApiBase(),
            promptKey: mdPromptKey, authorizeStrict: function (ids) { return mdAuthorizeStrictRun(ids, effectiveScript); } });
          if (_asm.remote.length) {
            var _rS = _asm.remote.map(function (r) { return { alias: r.alias, source_id: r.sourceId }; });
            var _rK = {}; for (var _i = 0; _i < _asm.remote.length; _i++) { var _r = _asm.remote[_i];
              if (_r.key === 'ask') _rK[_r.sourceId] = await mdPromptKey(_r.alias); else if (_r.key) _rK[_r.sourceId] = _r.key; }
            var _stripped = effectiveScript.replace(/^[ \t]*(?:#|--|\/\/)[ \t]*(?:connect|load|import|join|create-dataset)\b[^\n]*\n?/gim, '');
            await runSafeStatRemote(_stripped, _ctx, _rS, t('ikke-offentlig kilde'), 'python', _rK, _asm.spec);
            return;
          }
          await ensureSafepyLoaded(py);
          py.FS.mkdirTree('/home/pyodide/_webdata');
          var _asmLoads = _asm.sources.map(function (l) {
            var _p = '/home/pyodide/_webdata/' + l.alias + '.' + l.format;
            py.FS.writeFile(_p, l.bytes);
            return { alias: l.alias, format: l.format, path: _p };
          });
          // strip assembly + connect directives from the code the interpreter sees
          effectiveScript = effectiveScript.replace(/^[ \t]*(?:#|--|\/\/)[ \t]*(?:connect|load|import|join|create-dataset)\b[^\n]*\n?/gim, '');
          window.__assemblyPreamble = buildAssemblyPreamble(_asmLoads, _asm.spec);
        } else {
          window.__assemblyPreamble = '';
        }
```
Then in `setupCode` (around `index.html:8842`), append `+ (window.__assemblyPreamble || '')` after `buildWebDataLoaderPreamble(_pyLoads)`.

(Keep the existing non-assembly `_pyLoads` path for scripts without assembly verbs — the `else` leaves `_pyLoads` behavior untouched.)

- [ ] **Step 3: Bundle assembly.py + verify in the browser**

```bash
cd /Users/hom/Documents/GitHub/m2py && python sync_to_api.py --web   # zip now includes safepy/assembly.py
python -m http.server 8123 &
```
Playwright: python mode, run the §1 example over two public CSVs (host small CSVs via data: URLs or the seaborn penguins split). Expected: `panel` renders a groupby, a row-count note prints if the join multiplies. Then a bare `# load <url> as df` script still works (backward-compat).

- [ ] **Step 4: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add index.html vendor/safepy.zip
git commit -m "feat(assembly): local execution — assembly preamble runs safepy.assembly in Pyodide (python mode)"
```

---

## Task 5: Local execution — R + DuckDB modes (m2py)

**Files:**
- Modify: `m2py/index.html`

**Interfaces:**
- Consumes: Task 4's `buildAssemblyPreamble`, the existing R/duckdb bridges that expose pandas frames.

- [ ] **Step 1: R mode** — in `runHybridR` (`index.html:7406`), where `_dlR` is built, add the same assembly branch: if `_hasAssembly`, use `resolveAndAssemble`, write sources to the Pyodide FS (R strict already uses Pyodide for strict), run `buildAssemblyPreamble` in Pyodide to build the datasets as pandas frames, then bridge them into webR (the existing micro→R sync path — frames become R data.frames). If any source is remote → error like the strict-R case (remote R via connect not supported; use require). Verify with an R example over two CSVs.

- [ ] **Step 2: DuckDB mode** — assembly datasets are pandas frames; the duckdb bridge already registers pandas frames as views (`duckdb_bridge.py`). Route duckdb mode through the same assembly branch (build datasets in Pyodide, register as duckdb views), so `-- create-dataset / -- import` work and the SQL body queries the assembled `panel`. The duckdb-native SQL power path (raw JOINs) is unchanged and needs no assembly directives. Verify with a duckdb example.

- [ ] **Step 3: Commit**

```bash
cd /Users/hom/Documents/GitHub/m2py
git add index.html
git commit -m "feat(assembly): local execution in R + DuckDB modes over assembled frames"
```

---

## Task 6: Remote execution — shim runs the executor (microdata-api)

**Files:**
- Run: `python m2py/sync_to_api.py --apply` (vendor `assembly.py` server-side)
- Modify: `microdata-api/server_code/safepy_shim.py`, `server_code/api_endpoints.py`
- Test: `microdata-api/tests/test_assembly_shim.py`

**Interfaces:**
- Consumes: `safepy.assembly` (vendored), existing `resolve_source`/`load_dataframe`.
- Produces: `safepy_shim.run_extended(script, sources_req, dialect, on_progress, source_keys, assembly=None)` — when `assembly` (a spec) is given, resolve each source to a frame as today, then `assembly.build_datasets(spec, resolver)` where `resolver(alias)` maps the source alias to its resolved frame, and run `safepy.run` against the ASSEMBLED datasets instead of the raw source frames. `/run_extended` passes `body.get("assembly")` through to `bg_run_extended` → `run_extended`.

- [ ] **Step 1: Vendor sync + failing test**

```bash
python /Users/hom/Documents/GitHub/m2py/sync_to_api.py --apply    # copies safepy/assembly.py into server_code/safepy/
```

`microdata-api/tests/test_assembly_shim.py`:

```python
"""Remote assembly: the shim builds datasets from the spec (trusted, outside
the facade), then safepy analyses the assembled frames. No Anvil."""
import os
import pandas as pd
from cryptography.fernet import Fernet

os.environ.setdefault("MEDIA_AT_REST_KEY", Fernet.generate_key().decode())

import source_registry
import safepy_shim

PEOPLE = pd.DataFrame({"pid": list(range(60)),
                       "region": ["A" if i % 2 else "B" for i in range(60)],
                       "income": [30000 + i * 100 for i in range(60)]})


def _patch(monkeypatch, frames):
    monkeypatch.setattr(source_registry, "resolve_source",
                        lambda sid: {"source_id": sid, "kind": "url", "location": "x",
                                     "format": "csv", "level": "protected", "status": "active"})
    monkeypatch.setattr(source_registry, "load_dataframe",
                        lambda src: frames[src["source_id"]])


def test_remote_assembly_then_analysis(monkeypatch):
    _patch(monkeypatch, {"people": PEOPLE})
    spec = {"sources": ["p"], "datasets": [
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["income", "region"], "how": "left"}]}]}
    out = safepy_shim.run_extended(
        "panel.groupby('region')['income'].mean()",
        [{"alias": "p", "source_id": "people"}], dialect="pandas", assembly=spec)
    assert out["err"] is None
    assert out["results"] and "output-table" in out["results"][0]


def test_remote_assembly_missing_column_errors(monkeypatch):
    _patch(monkeypatch, {"people": PEOPLE})
    spec = {"sources": ["p"], "datasets": [
        {"name": "panel", "key": "pid", "steps": [
            {"op": "import", "source": "p", "columns": ["salary"], "how": "left"}]}]}
    out = safepy_shim.run_extended(
        "panel.sum()", [{"alias": "p", "source_id": "people"}],
        dialect="pandas", assembly=spec)
    assert out["err"] and "salary" in out["err"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/test_assembly_shim.py -x -q`
Expected: FAIL (unexpected `assembly` kwarg)

- [ ] **Step 3: Implement in `safepy_shim.py`**

Add `assembly=None` to `run_extended`'s signature. After the source-frame loop builds `frames` (alias→DataFrame) and before `safepy.run`, insert:

```python
    if assembly:
        try:
            from safepy import assembly as _asm
            built, _notes = _asm.build_datasets(assembly, lambda a: frames[a])
        except Exception as exc:      # AssemblyError or missing alias
            return _error_shape(script, str(exc))
        frames = built                # analysis runs against assembled datasets
```

(Place it after the HE/level resolution; assembled frames replace the raw source frames. Encrypted/HE sources: v1 assembly requires plaintext frames — if `n_he`, return `_error_shape(script, "montering støtter ikke krypterte (HE) kilder ennå")`. Add that guard.)

`api_endpoints.py` — in `http_run_extended`, read `assembly = body.get("assembly")` (validate: `None` or dict), pass it into `launch_background_task("bg_run_extended", …, source_keys, assembly)`; add `assembly=None` to `bg_run_extended` and forward `assembly=assembly` into `safepy_shim.run_extended`.

- [ ] **Step 4: Client sends the spec** — in `runSafeStatRemote` (`index.html:8003`), add a trailing `assembly` param and `if (assembly) body.assembly = assembly;`. (Task 4 already passes `_asm.spec` at the call site.)

- [ ] **Step 5: Tests + full suite + commit**

```bash
cd /Users/hom/Documents/GitHub/microdata-api
python -m pytest tests/ -x -q
git add server_code/ tests/test_assembly_shim.py
git commit -m "feat(assembly): remote execution — shim assembles datasets before safepy.run"
cd /Users/hom/Documents/GitHub/m2py && git add index.html && git commit -m "feat(assembly): send AssemblySpec to /run_extended for remote assembly"
```

---

## Task 7: Examples, E2E, docs, push

**Files:**
- Create: `m2py/examples/py31_assembly.txt`, `r31_assembly.txt`, `sql31_assembly.txt`

- [ ] **Step 1: Examples** — the §1 python example; an R equivalent; a duckdb example (common verbs + a raw-SQL power-path variant). Each self-contained over public CSVs.

- [ ] **Step 2: Full suites (three repos)**

```bash
cd /Users/hom/Documents/GitHub/safepy && python -m pytest tests/ -x -q
cd /Users/hom/Documents/GitHub/microdata-api && python -m pytest tests/ -x -q
cd /Users/hom/Documents/GitHub/m2py/netlify/edge-functions && deno test --allow-read --allow-env _lib/
```

- [ ] **Step 3: Playwright E2E** — python/r/duckdb assembly over public sources (local); a strict-source assembly (decrypt-at-run → assemble → strict analysis); a stubbed remote-assembly run (grant remote_only → spec sent → suppressed result). Confirm the row-multiplication note surfaces on a non-unique-key join.

- [ ] **Step 4: Parity check** — a fixture AssemblySpec + fixed CSVs assembled by the local preamble and by the shim yield the same frame (the executor is one vendored file; this guards the wiring).

- [ ] **Step 5: Memory + push**

Update the `roadmap-access-verbs` memory (Project A shipped; note what's built vs the §8 deferred items). Push all three repos to `dev`.

```bash
cd /Users/hom/Documents/GitHub/safepy && git push origin dev
cd /Users/hom/Documents/GitHub/microdata-api && git push origin dev
cd /Users/hom/Documents/GitHub/m2py && git add examples && git commit -m "docs(examples): variable-level assembly (py/r/duckdb)" && git push origin dev
```

## Self-Review Notes

- Spec coverage: §1 grammar → Task 2; §2 IR → Tasks 1-2; §3 execution (local+remote, one executor) → Tasks 1,4,5,6; §4 whole-then-select → Task 1 (`src[[key]+cols]`); §5 access-control fit → Tasks 3,6 (routing + HE guard); §6 errors → Task 1 (executor) + Task 2 (parser); §7 testing → per-task + Task 7; §8 deferred → not built (correct).
- Invariant checks: assembly runs as trusted code (Task 1/6, never through safepy facade); all-or-nothing remote routing (Task 3); backward-compat bare `load` (Tasks 2-4); microdata mode untouched (assembly verbs only parsed in dialect modes — the run handler branches only for python/r/duckdb).
- Type consistency: AssemblySpec shape identical across `parseAssembly` (JS), `resolveAndAssemble`, `buildAssemblyPreamble`, `safepy_shim.run_extended`, and `assembly.build_datasets`; `build_datasets` returns `(dict, notes)` everywhere; source alias → frame resolver signature identical local/remote.
