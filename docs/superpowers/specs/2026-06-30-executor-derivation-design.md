# Executor derivation — sensitivity ⊕ size → local / remote

> **Status:** approved design (brainstorming output, 2026-06-30). Refines the
> **Executor axis** of `docs/superpowers/specs/2026-06-29-safestat-remote-compute-slice-design.md`
> (which built the remote *path*; this adds the *derivation* layer on top — no
> existing behavior is reversed).

## Core principle

The executor (local vs remote) is **derived from the source, not toggled**. Two
independent drivers, **most-restrictive wins**:

- **Sensitivity:** a **non-public** source → **forced remote** (security — the
  data must not reach the client).
- **Size / feasibility:** a **too-large** source → **remote** (capability — the
  browser can't run it), *even when public*.

**Remote execution always requires login** (+ a "may run remote" permission) —
it consumes Anvil compute, so it's gated regardless of the data. **Local
execution is free** (no login) and is only possible when the data can actually
reach the client (public **and** small enough).

This means "remote" is one seam with different backends: *sensitive-remote* runs
the protect/suppress path; *large-public-remote* runs the DuckDB/streaming path
(the Backend axis, deferred). Both go through `/run_extended`.

## Source-declared executor policy

Each registered source carries (in addition to its existing fields):

- `public` — **derived from the existing `level`** (`public` == `level == "public"`);
  not a new stored field. `protected`/`sensitive` ⇒ non-public.
- `default_exec: 'local' | 'remote' | 'strict_remote'` (NEW field) — meaningful only for
  **public** sources (non-public is always remote):
  - `local` — small public → runs **local** by default.
  - `remote` — large public → runs **remote** by default, but the user **may**
    `exec(local)` (allowed — it's public).
  - `strict_remote` — very large public → runs **remote**; `exec(local)` is
    **refused** (data must not be pulled to the browser even though public).

`default_exec` is **declared at registration**. An optional size threshold that
auto-sets `remote`/`strict_remote` is a deferred refinement (declared, not
measured, for now).

## Resolution (per source reference)

| Source's declared default | `exec(local)` | `exec(remote)` | no override |
|---|---|---|---|
| public → `local` | local | remote *(login)* | **local** |
| public → `remote` | local *(allowed)* | remote | **remote** *(login)* |
| public → `strict_remote` | **refused** | remote | **remote** *(login)* |
| **non-public** | **never honored** | remote | **remote** *(login)* |

**Across multiple sources in one script: most-restrictive wins** — if any source
resolves to remote, the whole script runs remote (you cannot split a script's
data between client and server).

## `exec()` override — bounded

A `require` line may carry an `exec()` option (the existing generic `, name(arg)`
option slot — **no parser grammar change**): `require X as a, exec(remote)` /
`exec(local)`.

- `exec(remote)` — always allowed to *request* (tightening is safe); gated by
  login + permission.
- `exec(local)` — honored only if the source is **public AND not
  `strict_remote`**; otherwise **refused** with a clear message.

The rule in one line: **you can always tighten to remote; you can loosen to
local only when the data is public and not strict.**

## The `/source_info` lookup (the carrier)

`GET /_/api/source_info?id=<source_id>` (public, no auth) →

- public source → `{ "public": true, "default_exec": "local"|"remote"|"strict_remote", "location": "<url>" }`
  (client may fetch `location` and run local).
- non-public → `{ "public": false, "default_exec": "remote" }` — **`location`
  omitted** (never leak where protected data lives).

One endpoint feeds the whole client decision. (Later: a `variables` array for
tab-autocomplete — returned for public sources, and for non-public only to an
authenticated, permitted user.)

## Auth — remote requires login

Any remote run requires a valid token. `/run_extended` validates it
(reuse `auth.authenticate_or_fail`); for **non-public** sources auth is
mandatory. The server **re-resolves each source's level from the registry and
never trusts the request** — and enforces the `exec()` bounds server-side too
(`exec(local)` on a non-public/`strict_remote` source is refused at the server,
not only the client). v1 "may run remote" permission = **any logged-in user**; a
per-user flag is deferred. The client already holds a token in
`window.mdAuth.token` and the app has a login flow — the client attaches the
token and, on `401`, tells the user to log in.

## Client data flow (`runSafeStatScript`)

1. For each `require <X> as <alias>[, exec(opt)]`:
   - `X` is a URL → `{kind:'url', location:X, public:true, default_exec:'local'}`.
   - `X` is a name → `await sourceInfo(X)` (the `/source_info` lookup).
2. Apply the `exec()` override (bounded per the table) → per-source executor.
3. Combine **most-restrictive** → the script's executor.
4. Dispatch:
   - **local** → the existing Pyodide path (fetch URL refs / public-name
     `location`, run in browser).
   - **remote** → `/run_extended` (attach token; `401` → prompt login), poll
     `/run_extended_status`, render.

The manual `mål:` toggle is demoted to a **developer override** (or removed) —
the executor is now derived. A small **non-blocking indicator** shows where it
ran and why ("remote · data stays on the server", "local").

## Test fixtures (replace the single public seed)

| Source id | Level | `default_exec` | Exercises |
|---|---|---|---|
| `hospital` | **non-public** (`protected`) | remote (forced) | login gate + **suppression** (`tabulate tilstand_1_1` → small diagnosis cells suppressed) + compute-to-data |
| `demo_public` *(new, small CSV at a URL)* | public | `local` | local default + `exec(remote)` opt-in |

**Honest caveat:** `hospital`'s bytes sit at a *public* GitHub URL but we declare
it non-public — so it tests the **execution path** (forced-remote, login,
suppress), not data *residency*. A truly protected source would be Anvil-stored
or behind a credentialed URL (the upload/credentialed-URL layer, deferred).

## Scope — basic build now

**Build:**
1. **Registry:** relabel `hospital` → `protected` (non-public); add `demo_public`
   (small public CSV at a URL); add `public`/`default_exec` fields.
2. **`/source_info`** endpoint (public) returning `{public, default_exec, location?}`.
3. **Client derivation** in `runSafeStatScript`: parse `require <X> as <alias>[, exec(...)]`,
   derive per the table, most-restrictive-wins, dispatch local/remote. Demote the
   manual toggle; add the where-it-ran indicator.
4. **Auth gate:** `/run_extended` requires a valid token; client attaches
   `window.mdAuth.token`, handles `401`. Server re-resolves level + enforces
   `exec()` bounds.
5. **Suppression** activates automatically (`hospital` now `protected` →
   `resolve_policy` → `post_suppress`). No new code — already wired in Part 1.

**Deferred (designed here, not built):** `strict_remote` *enforcement* + size
**measurement**/threshold, autocomplete `variables` metadata, encrypted / key
sources, upload + credentialed-URL **residency**, granular per-user remote
permission, `HEAD`-probing a URL's size.

## Guardrails

- Server never trusts a level or `exec` from the request — `/source_info` and
  `/run_extended` both resolve from the registry and enforce `exec()` bounds
  server-side.
- Most-restrictive-wins across sources.
- Builds on the translator/executor seam; no emulator fork; additive only.
