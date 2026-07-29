# The m2py directive language — examples

Directives are plain comments at the start of a line, understood by
`js/data-directives.js` before any script actually runs. The comment marker
can be `#`, `--`, or `//` (whichever the active mode uses) — the parser
treats them identically.

## Grammar

```
directive   := connect | load | require | create-dataset | import | join

connect     := "connect" target ["as" alias] ["," option]*
load        := "load" (alias["/" path] | url) "as" NAME ["," option]*
require     := "require" target "as" NAME              # legacy alias for load
option      := "key(" (literal | "ask") ")"
             | "exec(" ("local" | "remote") ")"
             | "kind(" ("csv" | "parquet" | "duckdb" | "sqlite" | "json") ")"

target      := registry-id | url | anvil-name
```

`kind(...)` names the source's format explicitly instead of letting the
loader sniff it from the URL/content-type — mainly needed for `duckdb`/
`sqlite`, which can't be reliably sniffed from a URL alone. A `kind()` on
`load` overrides one given on the `connect` it resolves through.

`target` resolves in this order:
1. **Registry id** — an entry in `data/data-sources.json` (`ssb`, `eurostat`, `worldbank`, `oecd`, `who`, ...) → public web API, fetched with that entry's `base_url`/proxy rules.
2. **URL** (`http(s)://...`) → fetched directly. If the bytes turn out to be a `safepy-enc-v1` encrypted envelope, a key is required.
3. **Bare name that isn't a known registry id** → treated as a **registered Anvil source** (`GET /_/api/source_access?id=<name>`); the source's registered `level`/`local_mode` then decides whether it downloads locally, requires a key, or is remote-only.

---

## 1. Public registry source — no options needed

```
# connect https://data.ssb.no/api/pxwebapi/v2-beta/tables as ssb
# load ssb/05839/data?outputFormat=csv as ledighet
```
`ssb` is connected as an alias for a base URL; `load` appends a path to it and binds the result into the script under the name `ledighet`.

Using the short registry id instead of the full URL works the same way:
```
# connect ssb
# load ssb/tables/05839/data?outputFormat=csv as ledighet
```

## 2. Plain public URL, no `connect` needed at all

```
// load https://ourworldindata.org/grapher/co2-emissions.csv as co2
```
A bare URL can be `load`ed directly — no `connect` line required, no alias indirection.

## 3. Legacy `require` (URL-only alias for `load`)

```
# require https://x.example/gammel-data.csv as gammel
```
`require` behaves exactly like `load` for URLs. Named (non-URL) sources still use `require` for backward compatibility but are treated specially and NOT rewritten by the client — they route straight to the server.

## 4. FRED — a registry source that needs the CORS proxy + an API key

```
# connect fred
# load fred/series/observations?series_id=UNRATE&file_type=json as us
```
Because the FRED registry entry declares `cors:false` and an `auth` block, the fetch is silently routed through `/api/hent` (the same-origin proxy) instead of a direct browser fetch — the script itself doesn't change.

## 5. Registered protected source — key supplied interactively

```
# connect helse2025 as h, key(ask)
# load h as df
```
`helse2025` isn't a public registry id, so it resolves as an Anvil-registered source. `key(ask)` means: don't hard-code a secret in the script — pop a password modal at run time, held in memory only for that session (never written to localStorage, never logged).

## 6. Registered source with a literal key and forced remote execution

```
# connect kilde2 as k, key(qL7xK2mN9pR4sT6v), exec(remote)
# load k as df
```
`exec(remote)` forces the whole script for this source onto the server, even if the source's policy would otherwise allow local analysis. (The reverse, `exec(local)`, is refused by the client if the source's registered level is non-public — protected/sensitive sources can never be forced local.)

## 7. Directly loading an encrypted file by URL

```
# load https://raw.githubusercontent.com/owner/repo/data.enc.json as df, key(abcDEF123)
```
No `connect`/registration needed if the owner just hands you a URL and a key: the loader sniffs the `safepy-enc-v1` envelope, verifies its fingerprint, and decrypts client-side with WebCrypto using the supplied key.

## 8. Key precedence — `load`-level key overrides `connect`-level key

```
# connect helse2025 as h, key(K1)
# load h as df, key(K2)
```
`df` is decrypted with `K2`. A key on `connect` is just the default for everything loaded through that alias; a key on the individual `load` line wins.

## 9. Mixing several sources of different kinds in one script

```
# connect ssb as s
# connect helse2025 as h, key(ask)
# load s/tables as offentlig
# load h as beskyttet
# load https://ourworldindata.org/grapher/life-expectancy.csv as owid
```
`offentlig` comes from the public SSB registry, `beskyttet` from a key-gated Anvil source, and `owid` from a plain public URL — each resolved independently by the same script.

## 10. Variable-level assembly — `create-dataset` / `import` / `join`

A separate, richer directive set lets you assemble one analysis dataset out of *columns* pulled from multiple registered sources, rather than loading each source as a whole frame:

```
# connect people as p
# connect sales_src as s
# create-dataset panel, key(pid)
# import p/income, p/edu into panel
# import p/region into panel
# load s as sales
# join sales into panel on pid
```
This declares a dataset called `panel`, keyed on `pid`; pulls the `income` and `edu` columns from source `p` (plus `region` in a second `import` line); separately loads all of `sales_src` as `sales`; then joins `sales` into `panel` on the `pid` key. `import`/`join` default to a `left` join — an explicit join type can be appended:

```
# import p/x into panel inner
# join sales into panel on pid outer
```

## 11. Comment-marker flexibility (same directive, three syntaxes)

These three lines are parsed identically — only the comment marker differs, matching whichever language mode the script segment is in:
```
# connect https://data.ssb.no/api/pxwebapi/v2-beta/tables as ssb
-- connect https://data.ssb.no/api/pxwebapi/v2-beta/tables as ssb
// connect https://data.ssb.no/api/pxwebapi/v2-beta/tables as ssb
```

## 12. Homomorphically-encrypted (HE) tier

HE sources (`format="he"`, Paillier-encrypted) use the **same** `connect`/`load`/`require` directives as any other registered source — there is no separate directive syntax. What's different is the *editor mode/dialect* the script runs under, and what happens on resolution: the ciphertext is useless without the authority key, so an HE source is **always executed remotely** through the HE facade, never fetched or decrypted into the browser.

Referencing a registered HE source is written exactly like a protected source (§5 above):
```
# connect helse_he as h, key(ask)
# load h as df
```
The difference is invisible in the directive text — it's the registered source's `format` field, checked at `/source_access` resolution time, that routes it into the HE facade instead of a normal remote run.

The legacy `require` form works the same way:
```
# require helse_he as h
```
There is no separate "Kryptert" editor mode anymore (2026-07-08): HE is a security *level* derived from the sources, shown in the bottom-bar level badge (purple "Kryptert") in whatever language mode you are in. When the script references an HE source, the run is sent to the server with `dialect: 'he'`; the server never decrypts the data, and only the HE facade verbs (`group_agg`, `value_counts`, `crosstab`, `ols`) are available against it. In the DSL modes (SafeStat/Microdata) the client pre-flights this verb whitelist and refuses the run with a line-numbered error before anything is sent; the server enforces it regardless. An example HE script:
```
# require helse_he as data
group_agg data, mean(inntekt) by(kjonn)
```

**`exec(local)` is always refused on an HE source** — there's no plaintext to run against locally:
```
# connect helse_he as h, exec(local)
# load h as df
```
→ rejected with the same "cannot run locally" error protected/sensitive sources get, except here it's unconditional (HE has no local mode at all, unlike `protected`/`sensitive` which can allow `local_mode="open"`/`"strict"`).

**You cannot mix an HE (or any named) source with a plain URL source in one remote run yet:**
```
# require helse_he as h
# load https://ourworldindata.org/grapher/co2.csv as co2
```
→ refused: "Server-kjøring kan ikke kombinere navngitte kilder og URL-kilder (ennå)" (server execution can't yet combine named sources and URL sources — use only named sources).

## 13. DuckDB/SQLite sources — table and column addressing (dot-grammar)

A `duckdb`/`sqlite` file holds several tables in one file, so `load`/`import`
address a *table* the same way they'd otherwise address a whole source, and a
*column* by appending `.column` to the table:

```
# connect https://x.example/panel.duckdb as db, kind(duckdb)
# load db/visits as visits
```
`db/visits` means "table `visits` inside the `db` connection" — not a URL
path segment. Loading the whole table materializes it as an ordinary frame
named `visits`, exactly like loading any other source.

Column-level assembly (§10) uses the same dot-grammar, with the table named
before the dot and the column after it:
```
# create-dataset panel, key(pid)
# import db/patients.age, db/patients.sex into panel
```
This imports just the `age` and `sex` columns from the `patients` table —
network-level column pushdown means the rest of that table (and any other
tables in the same file) is never fetched.

A `duckdb`/`sqlite` `load`/`import` **without** a table name is refused —
there's no "whole file" to load, only tables inside it:
```
# load db as x
```
→ rejected: `«x»: duckdb/sqlite-kilder krever en tabell — «load db/<tabell> as x»`
(duckdb/sqlite sources require a table — write `load db/<table> as x`).

Table-addressed sources can mix freely with plain (non-table) sources in the
same assembly:
```
# connect https://x.example/income.parquet as inc, kind(parquet)
# connect https://x.example/panel.duckdb as db, kind(duckdb)
# create-dataset combined, key(pid)
# import inc/income into combined
# import db/demographics.age, db/demographics.sex into combined
```

## 14. Federated sources — `federert(...)` (phase 0, pull)

Three regions, same table, analyzed as one dataset. The automatic `__member`
column shows which region each row came from.

```
# connect demo-federert as helse
# load helse as personer
print(len(personer))
print(personer["__member"].value_counts())
```

Custom, inline (members are full URLs or registry ids; a path after the alias
is appended to every member — same relative layout at each holder):

```
# connect federert(https://a.no/data, https://b.no/data) as h
# load h/person.parquet as df
```

Member schemas must agree (column names; order is free) or the run is refused
with a message naming the drifting member. Members with `level: sensitive` are
refused in pull-federation — they require node members (phase 1). See
`docs/superpowers/specs/2026-07-29-federated-sources-design.md`.

---

**Source:** grammar and resolution order from
`docs/superpowers/specs/2026-07-05-encrypted-external-sources-design.md` §1;
duckdb/sqlite dot-grammar and pushdown from
`docs/superpowers/specs/2026-07-06-remote-columnar-sources-design.md`;
parsing implemented in `js/data-directives.js`; fetch/decrypt implemented in
`js/data-loader.js`; every example above (except #9, a composite) mirrors a
case asserted in `netlify/edge-functions/_lib/data-directives.test.ts`.
