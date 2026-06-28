# Manifest, `require`, and key model — design

**Status:** approved design (2026-06-28), pre-implementation
**Builds on:** `docs/superpowers/specs/2026-06-28-offline-script-codegen-design.md`
(implicit-key merge resolution, `KeyTracker`, `merge_into`, `m2py_translate`),
the `#duckdb` hybrid mode, and the microdata emulator catalog.

## Goal

Generalize the offline code-generation path from "microdata scripts over a
known catalog" into a **secure compute-to-data platform**: users submit a script,
it runs server-side against data they never see or download, and only vetted
*results* return. The same language and translator serve a spectrum of sources —
from a fully public CSV on the web (zero ceremony, anonymous) to a
sensitive registered registry (login, access control, disclosure control).
microdata.no becomes *one configured catalog* on that spectrum, not a special
case in the code.

This spec covers the **source-binding / key-declaration / import** layer that
makes that possible. Two layers are deliberately deferred to named follow-on
specs: the DuckDB compute push-down, and the disclosure/output-control layer.

## Core principle: opt-in security along a sensitivity spectrum

One mechanism; the security parts switch on only when a source needs them.

| Source | Login | Key | Auth | Disclosure layer |
|---|---|---|---|---|
| Public URL / file | no | only to `merge` | none | none |
| Registered, non-sensitive | optional (usage tracking) | from manifest | maybe | none |
| Registered, sensitive | **required** | from manifest | data-owner secret | **yes** |

Public users pay no tax. Sensitive data triggers identity + authorization +
output control. The **script itself is always identity-free and secret-free** —
the same script run by two users authorizes differently based on the session,
not the text.

## The manifest (generalized catalog)

A **manifest** declares, per logical dataset: where it lives, its format, its
key(s), its version, its auth requirement, and its sensitivity. It is the
source-agnostic replacement for the microdata catalog — and microdata's catalog
is just one built-in manifest.

The manifest has two halves with different exposure:

- **Schema (non-sensitive):** dataset names, formats, key column(s) + entity
  type, available versions, sensitivity flag. This is the only part the
  **browser/translator** receives, served by a registry endpoint the session is
  bound to. It carries no rows, no physical locations-with-credentials, no
  secrets. The translator uses it to bake merge keys at translate time
  (`KeyTracker` consumes it).
- **Run-time half (sensitive):** physical location, secret handle, access
  grants. Resolved only on the execution side (Anvil) at run time. Never crosses
  the browser or the API boundary.

A source may also *be* a manifest: `require something.json as NAME` binds a
self-describing manifest that carries its own per-table keys/schema (the rich
form), versus a raw file plus an inline `keys()` (the simple form).

## The `require` grammar

```
require <source> [as NAME] [version(N)] [keys(<keyspec>)] [auth(<type>, <handle>) | secret(<handle>)]

<source>  ::= name                # resolved via the registry/manifest
            | name.ext            # explicit file; format from extension
            | url                 # explicit web file; format from extension
<keyspec> ::= col [unit(<entity>)] [, col2 [unit(<entity>)] ...]   # composite allowed
```

Every clause after `<source>` is optional — a public CSV needs only the source.

### Source forms and format inference

| Form | Example | Resolution |
|---|---|---|
| bare `name` | `require persons as p` | registry supplies location, format, key, version, auth |
| `name.ext` | `require persons.parquet as p` | explicit file; format from extension |
| `url` | `require https://h/persons.parquet as p` | explicit web file; format from extension |

Format by extension: `.csv`→csv, `.parquet`→parquet, `.duckdb`/`.db`→duckdb,
`.sqlite`→sql, `.json`→**manifest** (self-describing, carries its own keys). A
bare name with no registry entry is the only error case.

### Version

Versions are **immutable** (a published version never changes; updates create a
new version). `version(N)` is optional; omitted = **latest at submit time**.
Because published versions never change, "latest" is stable, and an explicit
`version(N)` pins exact reproducibility. The `:N` colon (`fdb:43`) stays as sugar
for registry names; `version()` is the uniform form (URLs make `:` ambiguous).

For external URLs the system does not manage versions — the URL itself encodes
the version (a commit-pinned URL is immutable; a branch URL is the author's
choice). `version()` is simply omitted there.

**Every run records the resolved version number** (audit log / echoed into
results) so even a default-latest run is reconstructable.

### Keys

- **Explicit always wins and is always valid.** `on()`/`by()`/inline `keys()`
  override anything the manifest says.
- **The manifest supplies defaults** so keys are declared *once per source*, not
  per statement — removing the `on(pid)`-every-time tedium.
- **Composite keys allowed:** `keys(a, b)` and explicit `on(a b)`. microdata's
  single-key restriction is a property of *its* catalog (it may declare itself
  single-key and reject multi-key), not a global rule.
- **Optional `unit(<entity>)` marker** flags a key as an individual identifier
  (e.g. `keys(PERSONID_1 unit(person))`) for the disclosure layer. Omitted = a
  plain join key; the disclosure layer's default policy applies (conservative for
  sensitive sources).
- **Keyless sources are valid.** Most verbs (filter, `generate`,
  `collapse by(col)`, `summarize`) operate within one table and need no entity
  key. A key is required *only to combine sources* (see Import). A synthetic
  `__rowid` is offered as an explicit opt-in for **positional** alignment only —
  it does not enable entity joins between files that share no real key, and is
  never a silent default.

### Auth / credentials (never in the script)

The script is a shared artifact (sent over the API, logged, possibly re-shared),
so **credentials are never literals in it** — the grammar accepts only *handles*
into a server-side secret store, resolved at run time. A raw password where a
handle is expected is a hard error.

- **Registered source (preferred):** the data owner registers location + format
  + key + version + auth type + secret handle once; the script just names the
  source (`require persons as p`) and carries none of it. The owner's credential
  lets the sandbox read the protected source; the submitter gets neither the
  credential nor the rows — only results.
- **Ad-hoc source (escape hatch):** `auth(type, handle)` or `secret(handle)`
  names a secret in the *submitter's* store, resolved at run time:
  `require https://host/d.parquet as d, secret(host_token)`.
- **Public source:** no `auth`/`secret`, no login — fully anonymous.

The auth *type* (basic / api_key / bearer / cloud-keys / connection-string) is
manifest metadata; the script is auth-agnostic. The platform logs *which secret
handles* a run used (never the values).

## Import semantics

`import` separates into two things:

1. **Source binding** = `require` (where the data lives + its key), above.
2. **Column pull** = `import NAME/VAR as alias` (which columns to bring in).

The rule for when a column pull becomes a merge:

- **Same bound source, multiple variables** → pure column selection (same rows,
  no join, **no key needed**).
- **Different source into an existing dataset** → an implicit **merge on the
  declared key(s)** (or explicit `on()`); flagged `# TODO: verify join key` if no
  key resolves. This is the precise point "combine needs a key" triggers.

Non-`import` data creation is **first-class**: a dataset may be built by a
DuckDB/SQL block or a direct file bind, and declare its key via a `keys()` option
on `create-dataset` (or a small `set-key` statement) that populates the same key
registry `require` does. `require keys()`, `create-dataset … keys()`, and the
JSON manifest are three front-ends to one underlying key model.

## Access layer

**DuckDB is the read substrate.** Every source form (csv/parquet/duckdb/sql/url)
registers as a DuckDB relation; the generated code reads through DuckDB and pulls
per-dataset into pandas/polars for the stats verbs. This unifies "many formats,"
"multiple files," and "larger-than-memory" behind one interface and reuses the
existing `#duckdb` work.

SQL **push-down** (running collapse/merge/filter inside DuckDB and materializing
only results — better for >RAM and for the security boundary) is a **named
follow-on**, not v1.

## Results boundary

The API returns **analysis side-outputs** — summaries, tables, coefficients,
figures — subject to the (deferred) disclosure layer. **Row-level / individual
extracts are never streamed back**; an extract is written as a **new registered
dataset** (its own manifest entry, key, owner) that a subsequent authorized
script can read. This preserves compute-to-data: you can build extracts (the
original large-data aim), but they stay inside the platform boundary.

## Identity & authorization

- **Public sources:** no login; anonymous.
- **Sensitive sources:** login required. The source's manifest entry declares its
  sensitivity/clearance; at run time the platform checks the logged-in user (from
  the **user database** — identity, grants, the user's own secret handles, audit
  trail) against that clearance. Authorization is a run-time decision keyed on the
  session, not the script text — the same script authorizes differently per user.

The user-DB / IAM implementation is a named follow-on; this spec only fixes the
language-level hooks: source sensitivity/clearance in the manifest, and the rule
that identity lives in the session, never in the script.

## Audit / reproducibility record

Each run records: resolved source versions, secret handles used (not values),
the script (hash or text), the manifest schema snapshot, and a timestamp — so a
run is reconstructable and auditable.

## How key resolution flows (translate time vs run time)

- **Translate time (browser):** `KeyTracker` consumes the *schema* half of the
  manifest (served by the registry endpoint) to bake explicit `left_on`/`right_on`
  into each merge — exactly as it already does from the microdata catalog, but
  sourced from the manifest. No data, locations, or secrets are needed here.
- **Run time (Anvil):** the run-time half resolves physical location + secret +
  access grants; DuckDB reads the source; the baked keys drive the joins; outputs
  pass through the disclosure layer before return.

## Worked examples across the spectrum

```
# Public CSV — anonymous, no key, no version, no auth
require https://raw.githubusercontent.com/u/r/main/income.csv as inc
import inc/wage as wage
summarize wage

# Two public files, explicit key to combine
require data/persons.parquet as p, keys(id)
require data/income.csv      as i, keys(id)
import i/wage as wage into p          # cross-source -> merge on id
collapse (mean) wage, by(region)

# Sensitive registered source — login enforced, keys+auth from registry
require persons as p                  # registry: s3://…, parquet, key PERSONID_1
                                      #   unit(person), auth aws:owner_creds, sensitive
import income/wage as wage into p     # implicit merge on PERSONID_1
regress wage alder utd                # returns a coef table (disclosure layer applies)

# Ad-hoc credentialed URL — secret by handle, never literal
require https://api.host/extract.parquet as x, secret(host_token)
import x/value as v
```

## Out of scope (named follow-ons)

- **Disclosure / output-control layer** — small-cell suppression, the
  "forbidden-on-a-key" rules (the `unit()` marker is reserved now, enforced
  there), result vetting before return.
- **DuckDB compute push-down** — running shaping/aggregation inside DuckDB.
- **IAM / user-database implementation** — identities, grants, secret store,
  audit storage. This spec fixes only the language-level hooks.

## File / component impact (when built)

- Registry endpoint + schema response format (new).
- `require`/`import` IR already parsed by `MicroParser`; extend the translator to
  consume the manifest schema in `KeyTracker` (generalize its current
  import-path source), add `version()`/`keys(... unit())`/`auth()`/`secret()`
  handling, and the DuckDB source adapters.
- `create-dataset … keys()` / `set-key` to declare keys for non-import datasets.
- Run-time loader on Anvil: manifest run-time-half resolution, secret injection,
  DuckDB registration, audit record.
