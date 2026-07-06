# Remote columnar sources: DuckDB files + column/table pruning — design

Date: 2026-07-06
Status: draft — proposal from exploratory discussion, revised to decouple assembly execution
from analysis dialect (see §3); not yet reviewed with owner
Repos: m2py (primary), microdata-api (remote parity, later), safepy (unaffected — see §6)
Builds on: `2026-07-05-variable-level-assembly-design.md` (`import`/`join`/`create-dataset`),
`2026-06-28-duckdb-mode-design.md` (the DuckDB-WASM worker already running in the app),
`2026-07-05-encrypted-external-sources-design.md` (`connect`/`load` grammar, source registration, protection levels)

## Goal

Two things, currently true, that this proposes to change:

1. **m2py cannot connect to a `.duckdb` database file as a source at all.** `sniffFormat`
   (`js/data-loader.js:47-53`) only recognizes `parquet`/`json`/`html`, defaulting everything
   else to `csv`. A remote `.duckdb` file would silently be misparsed as CSV.
2. **Every source, of any format, is always downloaded in full before anything happens to it.**
   `fetchLoadTarget` (`js/data-loader.js:25-45`) does one whole-body `fetch()` per source. The
   variable-level `import <alias>/<column> into <dataset>` directive (Project A) *declares* that
   only one column is wanted, but the frame behind it has already been fully downloaded and
   materialized by the time `safepy.assembly` (Python, pandas-based) does the column projection
   — in memory, not over the network.

This proposal is to let `connect`/`load`/`import` reach a `.duckdb` file as a first-class
source kind, and to make single-variable (and, for DuckDB files, single-*table*) extraction
from both Parquet and DuckDB sources actually avoid the full download, by pushing the
projection down to the query engine instead of doing it after materialization.

**Key architectural correction (see §3):** dataset *construction* (`connect`/`load`/`import`/
`join`/`create-dataset`) and dataset *analysis* (the script body — stats, restricted verbs,
suppression) are already meant to be separate concerns — the assembly design doc says so
explicitly ("assembly is trusted, outside the facade"). Network-level pruning should therefore
attach to the construction phase itself, via a single DuckDB-backed assembly executor, and
benefit **every** analysis dialect (python/r/duckdb/microdata) equally — not be a side effect of
which editor tab happens to be open. An earlier draft of this note tied the benefit to "duckdb
mode" specifically; that coupling was an implementation shortcut, not a real constraint, and is
corrected here.

**Non-goals (v1):** CSV partial reads (CSV isn't chunked/indexed — there's nothing to prune),
speeding up the analysis phase itself once a dataset is assembled, remote reads against
protected/sensitive sources during assembly (see §6), or unchecked/un-checkpointed DuckDB files
(see §2).

## Why this isn't hypothetical — evidence already in the codebase

The engine capability already exists and is already used, just not for user-registered sources:

```js
// index.html:3090 — schema introspection for the app's own bundled datasets
const r = await conn.query("SELECT * FROM read_parquet('" + base + "static_data/" + t + ".parquet') LIMIT 0");
```

`LIMIT 0` against a *URL* proves duckdb-wasm is doing its own range-request-based remote read
here (footer + schema only) — not a JS `fetch()` of the whole file. The general `connect`/`load`
pipeline simply never routes user sources through this call shape; it always goes through
`fetchLoadTarget` → full buffer → `db.registerFileBuffer` → `read_parquet('<local-buffer-name>')`
(`index.html:3121-3128`). Wiring the general path to do what line 3090 already does is the core
of this proposal.

## 1. `duckdb` as a connectable source kind

Add `.duckdb` recognition alongside csv/parquet/json in the format-detection layer, and a new
source `kind` (mirroring the existing Anvil-registration `kind` values `url`/`media`/
`encrypted_url` in `admin_sources.py`/`owner_sources.py`): `duckdb_url`.

A DuckDB file can contain **multiple tables**, unlike a CSV/Parquet blob which *is* one table.
The existing `load := "load" (alias["/" path] | url) "as" NAME` grammar already has a path
slot after the alias (today used for REST API paths, e.g. `ssb/tables/05839/data`) — for a
duckdb-kind source this slot should mean **table name**:

```
# connect https://example.com/panel.duckdb as db
# load db/patients as p        -- table "patients" inside panel.duckdb
# load db/visits as v          -- table "visits", same file, one ATTACH
```

Both `load` lines attach the same remote file once (cached per-alias connection) and select a
different table from it — one network-level catalog fetch, not two full downloads.

## 2. Requirements for a source to actually support this

Both for DuckDB files and for the existing Parquet path, "remote columnar" only works if:

- **The host serves HTTP range requests** (`Accept-Ranges: bytes`) with CORS headers that expose
  `Content-Range`/`Accept-Ranges` for the in-browser case. Most static hosts, S3, GitHub raw, and
  Netlify already qualify; a host that doesn't silently falls back to a full download today, and
  m2py should surface that fallback to the user rather than hiding it (e.g. a status-bar note
  "kilden støtter ikke delvis nedlasting — laster hele filen").
- **For `.duckdb` files: the file must be checkpointed** (no pending write-ahead-log entries).
  An unflushed WAL forces sequential replay, which defeats the whole point. m2py can't verify
  this client-side before attaching; document it as an owner-facing requirement at registration
  time (see §4) rather than trying to detect it.
- **Parquet remains the safer bet.** Its footer/row-group/column-chunk layout was purpose-built
  for exactly this access pattern; DuckDB's native page/block format supports it but is younger
  and less battle-tested for scattered remote reads. Recommend Parquet as the default advice
  for "single large public dataset," DuckDB files as the answer specifically when a user wants
  **multiple related tables in one file/URL**.

## 3. A single, mode-neutral assembly executor (decoupled from analysis dialect)

Currently `import <alias>/<column> into <dataset>` compiles, via `safepy.assembly`, against
fully-materialized pandas frames (`_pyLoads`/`_asmSpec` in `index.html:8829-8940`) regardless of
editor mode — so the directive *declares* single-column intent, but the executor behind it
always pays for a full download first, no matter what.

The fix is not "give `duckdb` mode a faster path and leave the others as they are." It's to stop
treating the assembly executor as an extension of whichever analysis dialect is active, and give
it one implementation that always runs the same way:

- **Assembly always executes against a DuckDB engine**, regardless of whether the analysis that
  follows is written in python, r, duckdb, or microdata syntax. `create-dataset`/`import`/`join`
  compile to `ATTACH`/`read_parquet('<url>')`/`SELECT <column> FROM ...`/real SQL `JOIN`s against
  the remote source(s) — column and (for DuckDB files) table pruning happen here, unconditionally.
  This replaces `safepy.assembly`'s pandas implementation rather than sitting beside it as a
  duckdb-only fast path.
- **Only after assembly finishes does the result get handed to the active analysis engine** —
  this is the hand-off boundary, and it's the only place mode matters:
  - `duckdb` mode: the assembled result stays exactly where it is — already a DuckDB
    table/view, nothing further to convert.
  - `python` mode (Pyodide): the assembled DuckDB result is Arrow-shaped already (see the
    `__arrowToColumns` precedent at `index.html:3053`); converting Arrow → pandas DataFrame is a
    well-understood, comparatively cheap hand-off, done once, after pruning — not before it.
  - `r` mode (webR): same assembled result, converted through the existing base64-CSV injection
    bridge (or, later, a direct Arrow-R path) — again a one-time hand-off after pruning, not a
    re-fetch.
  - `microdata` mode: unaffected in v1, per the assembly design doc's existing scope (microdata
    DSL stays untouched and separate).
- **Consequence worth calling out explicitly:** the *same script* (`import p/income into panel`)
  now gets identical network-level pruning no matter which analysis dialect follows it — mode
  choice affects how you analyze, not how much data was fetched to build the dataset you're
  analyzing. That symmetry is the whole point of treating construction and analysis as separate
  concerns.
- **Secondary benefit: engines can load lazily.** If a workflow is "acquire + assemble + SQL
  analysis," there's no need to boot Pyodide/pandas at all — a real startup-cost win, since
  Pyodide+pandas is a heavy WASM payload that today loads regardless of whether the analysis
  script ever touches it. Pyodide would only need to load once assembly is done *and* the active
  mode actually requires it.
- **The "structure only" scope boundary matters more now, not less.** The assembly design doc
  already restricts assembly to acquire/select-columns/join — no row filtering, no derived
  columns, no aggregation (those stay in the analysis script body). That restriction was mostly
  about keeping assembly simple; now that assembly is a real query engine instead of a pandas
  concat, it's also what keeps assembly from quietly becoming a second, unsuppressed analysis
  surface (e.g. a `WHERE` clause smuggled into a join could itself be disclosive against a
  protected column). This boundary should be enforced by the executor, not left as a convention.

## 4. An explicit `kind()` option, instead of relying on sniffing

`sniffFormat` today guesses from `Content-Type` and file extension, defaulting silently to CSV
on anything unrecognized (`js/data-loader.js:47-53`). That's fine for opportunistic public-API
loads, but it's the wrong default once a source might be a `.duckdb` file: a URL with no
extension, an API gateway that doesn't set `Content-Type` correctly, or a proxy hop through
`/api/hent` can all make sniffing guess wrong — and guessing wrong for a binary DuckDB file
(vs. treating it as CSV text) fails loudly, but guessing wrong between two binary-ish formats
might not.

Proposal: extend the existing directive option grammar (`key(...)`, `exec(...)`) with a third,
optional `kind(...)`:

```
option := "key(" (literal | "ask") ")"
        | "exec(" ("local" | "remote") ")"
        | "kind(" ("csv" | "parquet" | "duckdb" | "json") ")"
```

```
# connect https://example.com/panel.duckdb as db, kind(duckdb)
# load db/patients as p
```

When `kind()` is present, skip sniffing entirely and trust the declaration (failing fast with a
clear error if the bytes don't match, rather than mis-parsing). This mirrors — and should reuse
— the `format` field a data owner already declares at registration time for Anvil sources
(`fFormat` in `deldata.html`, `admin_sources.py`'s `format` column); `kind()` just gives the same
explicitness to the ad-hoc "bare URL, no registration" path that `connect`/`load` also supports.

## 5. Schema peeking as a first-class, user-visible feature

The `LIMIT 0` trick already used internally for the app's bundled datasets (§ above) is worth
surfacing directly: given a registered or ad-hoc parquet/duckdb source, offer a "peek columns"
action (in the connect/load UI, or an editor affordance) that runs the schema-only query and
lists available variables/tables *before* the user commits to loading anything — genuinely free,
since it's the same near-zero-byte request the network layer would do anyway.

## 6. Interaction with protection levels — this must not become a bypass

Remote columnar pruning is a *transport* optimization; it must not change *who is allowed to see
what*. A registered source still carries a `level` (`public`/`protected`/`sensitive`) independent
of its `kind`/`format`, and moving assembly from pandas to a DuckDB engine (§3) does not change
who gets to run it against what — it only changes the mechanism for cases already allowed today.
Concretely:

- **`public` sources**: remote columnar reads happen client-side, same as today's local analysis
  — no new access-control surface, just less bandwidth.
- **`protected`/`sensitive` sources**: must **not** get a client-side `ATTACH`/`read_parquet(url)`
  shortcut — that would hand raw column bytes straight to the browser, bypassing the STRICT
  facade, suppression, and audit logging entirely. For these, any future push-down needs to
  happen **inside** the server-side safepy STRICT engine (i.e., the server's DuckDB dialect
  reads only the columns a `group_agg`/`crosstab`/etc. call actually needs from its own
  server-side attached copy) — a server-side efficiency gain, never a client-side data-exposure
  path. Worth its own follow-on spec rather than folding it in here.
- If this ever does reach the server, `query_audit` should log *which columns* a run touched, not
  just that the source was accessed — a finer-grained audit trail than exists today.

## 7. Other related ideas surfaced by this exploration

- **Caching.** Repeated schema-peeks or repeated queries against the same remote file could
  reuse an HTTP cache (browsers already cache individual range responses to some degree); an
  explicit ETag/If-Range check before re-attaching would avoid redundant catalog fetches across
  runs in the same session.
- **Arrow Flight / Arrow IPC as an alternative transport.** Range-request-over-HTTP works well
  for a static file host, but if a source is ever served by an actual application/API server
  (rather than a dumb file host), Arrow Flight (or just Arrow IPC streaming) is a more efficient
  and more standard transport for "give me these columns" than emulating range requests against
  a database file. Flag as a future alternative for server-hosted (not GitHub-hosted) sources,
  not something to build now.
- **Surfacing the fallback, not hiding it.** Whatever is implemented, when a host doesn't support
  ranges (or a `.duckdb` file has a pending WAL) and m2py falls back to a full download, the user
  should see that plainly (status line / audit note) rather than the app quietly doing the slow
  thing and the user assuming pruning happened.
- **`kind()` doubles as a schema/registration hint.** Once `kind()` exists for ad-hoc URLs, the
  same value could be pre-filled into `deldata.html`'s `fFormat` field when an owner registers a
  source they already tested via a bare `connect`/`load` script — one fewer manual step, and one
  less chance for the registered `format` to drift from what the file actually is.

## 8. Example scripts: Parquet and DuckDB sources

All proposed syntax — none of this runs today. Each example extends the existing assembly
grammar from `docs/directive-language-examples.md` §10 (`create-dataset`/`import`/`join`) with
`kind()` (§4) and duckdb table-path `load` (§1). Where a path grammar choice is still open
(table vs. column separator), the example picks one option for illustration and is flagged —
see the corresponding open question below.

**a) Parquet — single-variable import, pruned regardless of analysis dialect**

```
# connect https://example.com/patients.parquet as pq
# create-dataset onevar, key(pid)
# import pq/income into onevar
```

Syntactically identical to what already works today. What changes under this proposal is
*execution*: `income` is fetched via a remote-columnar `SELECT income FROM
read_parquet('https://example.com/patients.parquet')`-shaped query instead of a full-file
download — and that holds whether the analysis script that follows is written in `python`, `r`,
or `duckdb` mode (§3), not just the last of those.

**b) DuckDB file — multiple tables, joined into one keyed dataset**

```
# connect https://example.com/panel.duckdb as db, kind(duckdb)
# create-dataset panel, key(pid)
# import db/patients.age, db/patients.sex into panel
# load db/visits as visits
# join visits into panel on pid
```

One `ATTACH` (one catalog fetch) against `panel.duckdb`, then: `age`/`sex` pulled from just the
`patients` table (not the whole file, not even the whole `patients` table if it has other
columns); `visits` loaded as its own dataset in full (no column list given); the two joined on
`pid`. (`db/patients.age` uses a dot to separate table from column — one candidate answer to
the open "path grammar" question below, not a settled decision.)

**c) Mixing a Parquet source and a DuckDB-file source in one assembly**

```
# connect https://example.com/income.parquet as inc, kind(parquet)
# connect https://example.com/panel.duckdb as db, kind(duckdb)
# create-dataset combined, key(pid)
# import inc/income into combined
# import db/demographics.age, db/demographics.sex into combined
```

One keyed dataset built from a single column of a Parquet file and two columns of one table
inside a DuckDB file — neither source downloaded in full. `kind(parquet)` here is a belt-and-
braces declaration (the `.parquet` extension would sniff correctly on its own); shown for
symmetry with (d).

**d) `kind()` where sniffing would guess wrong**

```
# connect https://data.example.org/export?id=42 as db, kind(duckdb)
# load db/results as r
```

The URL has no file extension and the response `Content-Type` may not disambiguate a binary
DuckDB file from anything else — without `kind(duckdb)`, `sniffFormat` would default this to
`csv` (§4) and mis-parse the bytes. This is the case `kind()` exists for.

## 9. Other source kinds considered

Surveyed while scoping this proposal, sorted by whether they change v1 scope, connect to
already-deferred work, or are deliberately excluded.

**Extend now — same pattern as DuckDB/Parquet, low incremental cost:**

- **SQLite files.** More common than a raw `.duckdb` file as "one file, several tables" for a
  data owner to hand over. DuckDB can `ATTACH '<url>' (TYPE sqlite)` the same way it attaches a
  `.duckdb` file. Notably, this exact idea — range-request-based querying of a SQLite file
  hosted as a static object, no full download — already has proven prior art outside this
  ecosystem: **sql.js-httpvfs**, a WASM SQLite build with a virtual filesystem doing precisely
  the trick §1–§3 propose for DuckDB. Worth keeping as a fallback engine for the "one small
  SQLite file" case if DuckDB-wasm's own remote-attach path proves rougher in practice than
  `read_parquet(url)` already is.
- **Arrow IPC / Feather files.** The app already speaks Arrow natively end-to-end
  (`__arrowToColumns`), so an Arrow IPC file is a natural sibling to Parquet: `read_ipc(url)`
  instead of `read_parquet(url)`. Weaker column-pruning guarantees than Parquet's footer-driven
  layout (its per-record-batch structure supports partial reads, but less rigorously), but same
  category and same `kind()` mechanism.
- **Hive-partitioned Parquet directories** (e.g. `.../data/year=2024/*.parquet`). A second,
  orthogonal pruning axis — whole *files* skipped by partition value in the path, on top of
  column pruning inside each file that's actually read. Only useful once a "public dataset" is a
  directory tree rather than one file, and it needs a directory listing/manifest a static host
  like GitHub raw generally can't provide — so this really only pays off if the source lives on
  actual object storage (S3/GCS/Azure Blob) rather than a git repo.

**Connects to work already deferred elsewhere — don't design in isolation:**

- **Native cloud-storage protocols** (`s3://`, `gs://`, `az://`) with owner-supplied
  credentials or signed URLs. `2026-07-05-encrypted-external-sources-design.md` already
  deferred "owner-supplied storage tokens (private GitHub repos)" as future work; the same
  mechanism would also unlock column-pruned remote queries against **private** sources, not just
  public ones, since DuckDB's native object-storage clients use the identical range-request
  pattern this doc proposes for plain HTTP. When that deferred item is picked up, it should be
  scoped together with this proposal rather than separately.
- **MotherDuck** (hosted DuckDB-as-a-service) as an alternative to "owner hosts a bare file
  somewhere." Low priority; noted as an option if a managed alternative to a raw URL is ever
  wanted.

**Explicitly out of scope — naming this so it's a decision, not an omission:**

- **CSV, JSON, Excel/xlsx.** None support partial/columnar reads in any meaningful way — xlsx is
  a zipped bundle of XML sheets, CSV/JSON are flat unindexed text. These stay on the existing
  full-download path; adding them here would be scope creep, not a gap.
- **Zarr / HDF5** (chunked multi-dimensional array formats from scientific/climate computing).
  These genuinely support range-based partial reads, but for array data, not the tabular
  microdata this tool targets. Only worth revisiting if the app's scope ever grows to cover that
  kind of data.

## 10. Alternative `import` syntax: `from <source> import <cols> into <name>` — undecided

Raised in discussion, not adopted or rejected. Current shipped grammar:

```
# import p/income, p/edu into panel
```

Proposed alternative:

```
# from p import income, edu into panel
```

**In favor:** removes the repeated `alias/` prefix for the common case (several columns, one
source) — the current syntax's most-flagged awkwardness. `import` is also the one directive
already named after Python's own statement, so matching Python's `from X import Y` shape
arguably *increases* consistency with the mental model the name invokes, rather than reducing
consistency with the rest of the grammar. It would also cleanly resolve the `<table>.<column>`
open question below: `from db/patients import age, sex into panel` reuses the existing
`alias/table` convention from `load` instead of inventing a dot separator just for `import`.

**Against:**
- The current grammar lets one `import` line span **multiple sources**
  (`import p/income, s/sales into panel` — `parseAssembly`'s `bySrc` grouping in
  `js/data-directives.js` exists specifically for this). `from` would force one source per line.
  In practice every example seen so far (including the ones in §8) already writes one
  source per line anyway, so this may be a non-loss — but it is a capability given up, not just
  a cosmetic change.
- **This is not a green-field choice.** `IMPORT_RE`/`parseAssembly` in `js/data-directives.js`
  and the assertions in `netlify/edge-functions/_lib/data-directives.test.ts` already implement
  and test the current syntax. Adopting `from` means changing shipped, tested parsing code, not
  just this design doc and the examples in `docs/directive-language-examples.md` §10.
- **Structural inconsistency.** `connect`/`load`/`join`/`create-dataset` all put the verb first
  ("VERB target as/into name"); `from p import ... into panel` puts the source *before* the
  verb — a different sentence shape, unique to `import`. Defensible as a deliberate one-off
  given `import`'s Python heritage, but it should be a conscious, recorded exception if adopted,
  not something that quietly diverges from the rest of the language.

No recommendation is recorded here on purpose — genuine pros and cons on both sides, revisit
before `import` ships (or gets its grammar extended for duckdb tables), not after.

## Open design questions (not resolved here)

- Exact `import`/path grammar for a duckdb source's `<table>.<column>` vs. today's single opaque
  `alias/path` slot — needs a decision (dot vs. slash vs. a second option, or the `from`
  alternative in §10) before implementation.
- Whether `kind(duckdb)` implies "may contain multiple tables" automatically, or whether a
  source also needs to declare which table `load <alias> as x` (no path) defaults to.
- Whether schema-peeking should be cached per source for the lifetime of a session, and where
  (client memory only, or worth a lightweight server-side cache for registered sources).
- Whether replacing `safepy.assembly`'s pandas implementation outright (one executor, always
  DuckDB-backed) is feasible in one step, or needs an interim period where both implementations
  exist and are checked against each other for parity before the pandas path is removed.
- Where exactly Pyodide's lazy-load trigger should live (§3) — e.g. does the run orchestration
  need to parse the analysis script body *before* running assembly, just to decide whether
  pandas will be needed afterward, and does that pre-parse cost outweigh the load it's avoiding
  for small scripts.
