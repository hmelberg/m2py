# Variable-level assembly language (Project A) — design

Date: 2026-07-05
Status: approved in dialogue (owner, 2026-07-05)
Repos: m2py (parser + local execution + UI), microdata-api (remote execution in the shim), safepy (unchanged — assembly is trusted, outside the facade)
Builds on: `2026-07-05-encrypted-external-sources-design.md` (connect/load, grants, sources) and `2026-07-05-browser-strict-execution-design.md` (local strict runs, remote shim).

## Goal

Give the **dialect modes** (python/r/duckdb) a concise, intuitive language for
*assembling* analysis datasets from connected sources — selecting variables
(columns), combining datasets (joins), and building named datasets keyed on a
join column — that works identically whether the data is analysed locally in
the browser or remotely on the server.

This answers the original design questions: distinguishing "load a table" from
"import a variable", and specifying the id to match on. The mature **microdata
mode** DSL is intentionally left untouched and separate.

## Principle: common core + mode-native power paths

Two layers, and we do **not** force everything to the lowest common denominator:

1. **Mode-neutral common language** — `connect` / `load` / `import` / `join` /
   `create-dataset` — parses and behaves identically in python, r, and duckdb
   modes. This is the intuitive, portable layer.
2. **Mode-native power paths** — in **duckdb mode**, raw SQL (JOIN, WHERE,
   computed columns) is already a rich assembly language; a duckdb source in
   duckdb mode may use it directly. The common verbs also work in duckdb mode
   (compiling to the same assembled frames). CSV-in-python stays with the
   common verbs; duckdb can go further. Future sources may add their own
   options without changing the common core.

**Scope boundary:** assembly is *structure only* — acquire, select columns,
join. Row filtering, derivation, and statistics stay in the analysis script
body. (`# keep-if`, derived columns, aggregation are explicitly out of v1.)

## Decisions (with rationale)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Common language for dialect modes only; **microdata mode untouched**. | The microdata DSL is mature and well-tested; the aim is a good language for the *other* modes, inspired by it but expanded (it lacks dataset-level import). |
| D2 | Directives compile to a mode-neutral **AssemblySpec**, executed by **trusted runtime code** (loader locally, shim remotely) to produce named pandas frames *before* the analysis script. | One mechanism, full local/remote parity; assembly ops are fixed-safe so they need not pass through the untrusted-script safepy facade. |
| D3 | Assembly runs **where the data routes** — browser for open + strict sources, server shim for protected/remote. | Reuses the grant-driven routing already built; protected rows never come to the browser. |
| D4 | Explicit **`create-dataset <name>, key(<col>)`** declares the join key up front. | The owner's original instinct (key in create-dataset, not connect); reads top-down like building a table. |
| D5 | **Single key** per dataset in v1; **left-join onto the accumulator** by default, overridable `inner`/`outer`/`left`. | Matches microdata's proven single-key model; left-onto-accumulator is predictable when building a panel incrementally. Composite keys deferred. |
| D6 | Column extraction v1 = **load-whole-source-then-select**. | Correct for csv/parquet/encrypted; pushdown is an optimization (deferred), and duckdb mode's SQL already gets pushdown natively. |
| D7 | Assembly produces **pandas frames** (the interchange), exposed to R/duckdb by the existing mode bridges. | Reuses the established "pandas frames as lingua franca" pattern (micro→py, web-load→py). |

## 1. Grammar (common layer)

Comment directives, same comment markers as connect/load (`#`, `--`, `//`):

```
directive   := connect | load | create-dataset | import | join

connect     := "connect" <source> "as" <alias>                       # existing
load        := "load" <alias> "as" <name>                            # whole table → dataset
create-ds   := "create-dataset" <name> "," "key(" <col> ")"          # empty dataset, one join key
import      := "import" <colref> ("," <colref>)* "into" <name> [how]  # column(s) → dataset
join        := "join" <name-or-alias> "into" <name> "on" <col> [how]  # combine datasets

colref      := <alias> "/" <column>
how         := "inner" | "outer" | "left"                            # default: left
```

Semantics:
- **`load h as sales`** — the whole source `h` becomes the named dataset `sales`.
- **`create-dataset panel, key(pid)`** — an empty dataset `panel` whose join
  key is `pid`. Every subsequent `import ... into panel` merges on `pid`.
- **`import h/income, h/edu into panel`** — pull columns `income`, `edu` (plus
  the key `pid`) from source `h` and left-join them onto `panel` on `pid`. The
  first import into an empty `panel` establishes its rows.
- **`join sales into panel on pid`** — left-join the already-loaded dataset
  `sales` into `panel` on the shared column `pid`.
- `how` (`inner`/`outer`/`left`) overrides the default left-join per statement.

The analysis script (any dialect) then sees the assembled named datasets as
variables — e.g. `panel.groupby('region')['income'].mean()`.

### Example (python mode)

```python
#py
# connect people as p
# connect sales_src as s

# create-dataset panel, key(pid)
# import p/income, p/edu into panel
# import p/region into panel
# load s as sales
# join sales into panel on pid

panel.groupby('region')['income'].mean()
```

### Example (duckdb mode — common verbs OR native SQL)

```sql
#duckdb
-- connect people as p
-- create-dataset panel, key(pid)
-- import p/income, p/region into panel
SELECT region, avg(income) FROM panel GROUP BY region
```
```sql
#duckdb
-- Power path: raw SQL assembly (duckdb-native), richer than the common verbs
-- connect people as p
-- connect sales_src as s
SELECT p.region, avg(s.amount)
FROM p JOIN s ON p.pid = s.pid
GROUP BY p.region
```

## 2. AssemblySpec (mode-neutral IR)

The directive parser emits one spec per run:

```json
{
  "datasets": [
    {
      "name": "panel",
      "key": "pid",
      "steps": [
        {"op": "import", "source": "p", "columns": ["income", "edu"], "how": "left"},
        {"op": "import", "source": "p", "columns": ["region"], "how": "left"},
        {"op": "join",   "from": "sales", "on": "pid", "how": "left"}
      ]
    },
    {"name": "sales", "load": "s"}
  ]
}
```

- `load` datasets are whole-table; `steps` datasets are assembled.
- Steps run in written order (left-to-right accumulation).
- `source`/`from` reference connect aliases or already-named datasets.

## 3. Execution — one spec, two runtimes

A single pure executor turns an AssemblySpec + a resolver into named frames.
`resolve(alias_or_name) -> DataFrame` differs by runtime; the merge logic is shared.

- **Local (browser)** — for open + strict sources (rows are in the browser).
  The loader (`js/data-loader.js` + Pyodide preamble) fetches each source,
  runs the spec in pandas, and binds the named frames. For strict runs the
  spec executes inside the strict run (decrypt-at-run frames feed the
  assembly), before `safepy.run` sees the assembled frames. R/duckdb modes
  read the frames via the existing bridges.
- **Remote (protected/sensitive)** — the spec travels to the server alongside
  `sources`. The shim (`safepy_shim`) resolves each source to a frame
  (applying the per-source input `pre_recipe`), runs the **same** executor
  (trusted pandas code), and hands the assembled named frames to `safepy.run`
  for the untrusted analysis script. Assembly is not user code and does not
  pass through the STRICT facade.

The executor is implemented once as pure Python in the **safepy repo**
(`safepy/assembly.py`) so the existing sync already carries it to both
surfaces: `sync_to_api.py --apply` vendors it into
`microdata-api/server_code/safepy/`, and `--web` bundles it into
`vendor/safepy.zip` for Pyodide. It is pure pandas (no safepy-engine
dependency; it lives in the package only for vendoring convenience). Local and
remote therefore run byte-identical assembly code.

## 4. Column extraction (v1)

`import h/income` loads the whole source `h` once (cached across imports from
the same source in one run) and selects `income` + the key. Correct for
csv/parquet/encrypted. Deferred: parquet/duckdb column pushdown for large
files; duckdb mode's SQL path already reads only referenced columns.

## 5. Access-control interaction

Assembly changes nothing about grants, keys, or suppression:
- Where a source may be analysed (open/strict/remote) is decided by its grant
  exactly as today; assembly runs in that same place.
- Input-side protection (`pre_recipe`, e.g. `microdata_no` profile) applies to
  each source frame **before** assembly; result-side suppression applies to the
  analysis output **after**.

**Threat-model note (documented, not solved in v1):** joining protected sources
on a key can raise re-identification risk (linkage). v1 relies on the existing
per-source input recipe + output suppression; a linkage-aware policy (e.g.
flagging joins that shrink effective cell sizes) is deferred.

## 6. Error handling

| Situation | Behavior |
|---|---|
| `import`/`join` into a `<name>` with no `create-dataset` and no prior `load` | "ukjent datasett «panel» — mangler create-dataset?" |
| Column not in the source | "kolonnen «income» finnes ikke i kilden «p» (har: …)" |
| Key column missing in a source being imported | "kilden «p» mangler nøkkelkolonnen «pid»" |
| Key dtype mismatch across frames | "nøkkelen «pid» har ulik type i «panel» og «sales»" |
| Join would multiply rows (many-to-many on the key) | run proceeds; a note reports the row-count change ("panel: 1000 → 4200 rader etter join") |
| Unknown connect alias | existing connect/load error |
| Assembly directive in microdata mode | "monterings-språket gjelder python/r/duckdb — microdata-modus bruker sitt eget DSL" |

The row-multiplication **note** (not error) surfaces the most common silent
mistake (a non-unique key) without blocking legitimate one-to-many joins.

## 7. Testing

- **Spec parser** (Deno, `data-directives`): directives → AssemblySpec; error
  cases (missing create-dataset, bad colref).
- **Executor** (pytest, `assembly.py`): import-select, left/inner/outer joins,
  first-import-establishes-rows, row-multiplication note, all error rows above
  — pure, no Anvil/Pyodide.
- **Local execution** (Playwright): the python example assembles `panel` and
  renders the groupby; an r-mode and a duckdb-mode example over the same spec.
- **Remote execution** (pytest, `safepy_shim`): the spec + two sources
  assemble server-side, then a suppressed analysis returns.
- **Parity fixture**: the same AssemblySpec + same inputs yields a byte-identical
  assembled frame from the local and remote executor (the executor is one
  vendored file, so this guards the wiring, not the logic).

## 8. Deferred

- **Composite keys** (`key(pid, year)`) — panels; single key in v1. This also
  covers microdata-style *panel* import: joining on `(pid, year)` is the same
  mechanism, no separate verb.
- **Temporal / as-of `import`** (microdata `import-event` analogue) — an
  optional date modifier such as `import p/income at 2020-06-30` or
  `during 2020-01-01 to 2020-12-31`, performing an as-of / interval join
  ("the value valid on date D") against interval-structured sources
  (`valid_from`/`valid_to`). Data-model-dependent: it only activates when a
  source is *registered as* interval-structured (which columns are the
  date/interval — metadata generic files don't self-describe), and temporal
  joins carry their own correctness concerns (overlaps, gaps, point-in-time).
  Out of v1 deliberately: the common verbs stay columns + equi-joins, and
  **duckdb mode's SQL power path already expresses as-of joins, date windows,
  and interval logic today** — so the capability exists now, just in the
  mode-native path rather than the common core. Build the common-verb version
  when a concrete event-structured dataset needs it. (Plain date-window
  *filtering* on long-format rows is not this item — that is row filtering,
  which stays in the analysis script body.)
- **Column pushdown** (parquet/duckdb) for large-file `import`.
- **Assembly-time filter / derive / aggregate** — stays in the analysis script
  in v1 (`keep-if`, computed columns, collapse).
- **Assembly for microdata mode** — microdata keeps its own DSL.
- **Linkage-aware suppression policy** for joins of protected sources.
- **`use <name>` active-dataset switching** — v1 uses explicit `into <name>` on
  every statement (no implicit active dataset), which is clearer for the
  non-microdata audience.
- **Runtime-conditional / interleaved dataset creation** — a dataset whose
  *definition* depends on a runtime result of earlier analysis. Assembly is a
  static preamble (parsed and executed before any analysis), so this is out of
  scope — and deliberately so for the safe modes, where the full set of
  protected data a run touches must be known up front to authorize and log it.
  Multiple datasets analysed in sequence ARE supported (directives are
  order-free and all materialized before the script); only *data-dependent*
  definitions are excluded. True conditional loading, if ever needed, is a
  separate re-run-with-a-new-spec feature, not part of Project A.
