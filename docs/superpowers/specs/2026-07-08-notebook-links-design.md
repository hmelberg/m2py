# Notebook links — URL-driven startup, autorun, and prose rendering

**Date:** 2026-07-08
**Applies to:** SafeStat (source of truth) → ported to OpenStat
**Status:** design, pending implementation plan

## Summary

Turn a shared URL into a self-contained "notebook": a link can load a script
from GitHub straight into the editor, or run it and show only the output;
scripts can carry rendered prose (markdown) inline; and the hostname the app is
served on picks the starting mode and repositions the welcome message. Four
parts, one spec:

1. **Fragment loader** — `#user.repo.path.file.ext` (or a raw URL) fetches a
   script from GitHub and opens it in the editor.
2. **Output-only autorun** — an `#output.…` link runs the script and shows only
   the output, with a "show code" escape hatch. Autorun trust differs per app.
3. **Prose rendering** — top-level bare strings (Python) and `#'` roxygen lines
   (R) render as markdown, always on, interleaved with output.
4. **Hostname-driven startup mode & repositioned welcome** — the subdomain/host
   (`py.`, `r.`, `duck.`, or `micro`/`microdata.run`) selects the initial editor
   mode; the bare domain defaults to **python**; the welcome message reframes the
   product per mode (code-first, not microdata-first).

Most of this is wiring over machinery that already exists (see *Reuse map*).

## Reuse map (what already exists)

| Capability | Existing anchor |
|---|---|
| Fragment entry point | `openFromFragment()` — `js/github-storage.js:125` (matches `#s=`) |
| Load-and-run | `setEditor(text, lang)` + `document.getElementById('btnRun').click()` |
| Language from extension | `langFromPath()` in `js/github-storage.js` |
| Output-only (hide input) | `window.mdSetInputHidden(true)` / `applyInputForMode` — `index.html:3755-3757` (jamovi already runs output-only) |
| Markdown embed → render | emit `_log_embed('markdown', …)` (`m2py.py:9676`, marker `MICRO_EMBED_START`, `m2py.py:6529`); front-end parses `EMBED_START` (`index.html:2816`) and renders `embedType === 'markdown'` (`index.html:6027-6033`) |
| Autorun confirmation gate | `confirmAutoRun()` / `getAutorunPref()` — `js/ai-chat.js:1262-1266` (the S2 gate) |
| Run-in-progress guard | `scriptRunInProgress` (`index.html:4027`) |

New code is limited to two small, pure, independently testable units: a
**fragment router/resolver** and a **prose segmenter**.

---

## Part 1 — Fragment grammar & routing

### Grammar

`openFromFragment()` gains a classifier over `location.hash`:

| Fragment | Meaning |
|---|---|
| `#s=<packed>` | existing inline share (unchanged) |
| `#<user>.<repo>.<seg>.<…>.<file>.<ext>` | dotted shorthand → open in editor |
| `#output.<user>.<repo>.<…>.<file>.<ext>` | dotted shorthand → autorun, output-only |
| `#url=<raw URL>` | raw-URL fallback → open in editor |
| `#output=<raw URL>` | raw-URL fallback → autorun, output-only |

### Dotted resolver

`user.repo.a.b.file.ext` →
`https://raw.githubusercontent.com/user/repo/<branch>/a/b/file.ext`

- First token = `user`, second = `repo`.
- Remaining tokens: all dots become `/`, except the final dot which separates
  the file extension. So `hans.demo.analyses.income.py` →
  `.../hans/demo/main/analyses/income.py`.
- **Branch:** not encoded. Fetch `main`; on HTTP 404 retry `master`. (A repo on
  another branch, or a file/folder whose name contains a dot, must use the
  raw-URL form — the shorthand cannot express those.)
- Must have at least `user`, `repo`, and one path segment with an extension;
  otherwise it is not treated as a dotted fragment (falls through, e.g. so a
  bare `#section` anchor is ignored).

### Raw-URL fallback

`#url=` / `#output=` take a full URL (any CORS-capable raw host: GitHub raw,
gist raw, Dropbox `dl.dropboxusercontent.com`). This is the general escape hatch
for branches, dotted names, and non-GitHub hosts. Reuses the existing
`fetchUrl()` fetch/CORS-error handling.

### Fragment lifecycle

- Unlike `#s=` (a one-shot import that is stripped via `history.replaceState`),
  the new fragments are **kept** in the URL so the link stays shareable and
  reload re-runs it.
- On load, the fragment router runs before the placeholder boot auto-run
  (`index.html:2806`) and **supersedes** it: if a fragment is present, the
  placeholder auto-run does not fire. All runs respect `scriptRunInProgress`.
- `langFromPath(ext)` sets the editor mode from the extension (`.py`→python,
  `.r`/`.R`→r, `.txt`/microdata→microdata, etc.).

---

## Part 2 — Output-only & autorun (per app)

### Output-only presentation

For `#output…` links: after the script is set, call
`window.mdSetInputHidden(true)` (the same path jamovi uses) to hide the editor
and show only `#outputArea`. Add a small **"‹ show code / edit"** affordance
that calls `mdSetInputHidden(false)` to reveal the editor (so a reader can
inspect or fork the script). This does not re-hide automatically. Output-only
also **suppresses the welcome message** entirely (see Part 4).

### Autorun trust — differs per app (decision)

- **OpenStat** (public, no login, BYOK): autorun directly — fetch → setEditor →
  run. **Safety valve:** if `localStorage` already holds a secret (a connected
  GitHub PAT `m2py_github_profiles`/`m2py_github_pat`, or a BYOK Anthropic key
  `md_anthropic_key`), fall back to the confirmation gate even in OpenStat, so a
  visitor who has entered credentials is not silently exposed. A fresh visitor
  with no secrets gets zero-friction autorun.
- **SafeStat** (login, PAT, protected sources): always route autorun through the
  existing S2 gate (`confirmAutoRun()`), which shows the source and requires one
  click. `md_ai_autorun=1` opt-out applies as it already does.

Rationale: autorun executes code main-thread with `import js` access to
`localStorage`. The gate makes execution a conscious, sourced click; the
OpenStat safety valve narrows the zero-click path to the genuinely low-risk
case (no stored secrets). This mirrors the S2 fix already shipped.

---

## Part 3 — Prose rendering (always on)

Prose renders as markdown in **any** python/R run (editor or autorun) — a script
reads the same however it is launched. Reuses the markdown embed pipeline, so
prose interleaves with output in source order.

### Python — top-level bare strings via AST transform

Before execution, parse the script with `ast`. For each **top-level**
`ast.Expr` whose `.value` is an `ast.Constant` of type `str` (covers
triple-quoted and adjacent-literal-folded strings; **excludes** strings assigned
to variables and docstrings inside functions/classes), replace the node with a
call to an injected emitter:

```
Expr(Constant("## Heading\n\ntext"))  →  Expr(Call(__md_emit__, [Constant(...)]))
```

Then `ast.fix_missing_locations`, compile, and exec **once** in the normal
namespace. `__md_emit__(s)` writes the markdown embed markers
(`__micro_transform_start_markdown__ … __micro_transform_end__`) to stdout, which
the existing renderer turns into rendered markdown. Executing the whole
transformed module once (rather than manual chunking) preserves execution order,
output order, and variable persistence for free.

- Out of scope for v1: f-strings as prose (a bare f-string is `JoinedStr`, not
  `Constant`) — noted as a future extension.
- Guard: strings are scanned/escaped so a payload cannot inject a spurious embed
  marker.

### R — `#'` roxygen lines

Line scan before execution: contiguous runs of lines whose first non-space chars
are `#'` are collected, the `#'` prefix stripped, joined, and emitted as one
markdown block at that position (via the same embed markers, printed with
`cat`); all other lines run as R. Line-based, no parser needed.

### Microdata mode

Unchanged — keeps its existing `textblock/endblock` markdown feature
(`m2py.py:8040`). The bare-string / roxygen rules apply only to python and R.

### Behavior-change note

Always-on means an existing Python script with a module-level docstring at the
top will now render it as a heading instead of silently discarding it. This is
intended (it is the feature). Implementation includes a quick audit of the
shipped `web_examples/` and `manual_scripts/` for stray top-level bare strings
that would render unexpectedly.

---

## Part 4 — Hostname-driven startup mode & repositioned welcome

### Startup mode from hostname

At boot, before the fragment router, resolve a **default editor mode** from
`location.hostname`:

1. First hostname label matched exactly against a map:
   `py → python`, `r → r`, `duck → duckdb` (extensible: `statx`, `jamovi`).
2. Else if the hostname contains the substring `micro`
   (covers `micro.safestat.app` and `microdata.run`) → `microdata`.
3. Else (bare `openstat.app` / `safestat.app`, localhost, Netlify previews) →
   `python` (**the default flips from today's microdata**).

Exact first-label matching (not substring) for `py`/`r`/`duck` avoids false hits
like `spy.` → `py`. All modes remain available in the mode menu regardless of
host; the hostname only sets the *initial* mode.

### Precedence

- **No fragment:** hostname decides the initial mode.
- **Fragment present:** the file extension in the fragment decides the mode
  (`langFromPath`), overriding the hostname — you cannot run a `.r` file in
  python mode. The hostname still selects the welcome framing.

### DNS note (ops, not code)

The code reads whatever hostname it is served on. Creating the actual subdomains
(`py.openstat.app`, `r.safestat.app`, …) is a Netlify domain + DNS task outside
this spec. Until they exist, the bare-domain default (python) applies.

### Repositioned welcome — `f(framing, app)`

The welcome message is chosen by **framing** (microdata vs general) and **app**
(OpenStat vs SafeStat). Output-only (`#output…`) shows **no welcome** at all.
One global dismissal key (unchanged `*_welcome_dismissed`); the variant is
selected at show time.

- **microdata framing** (hostname contains `micro`), either app — keep the
  existing microdata-practice copy (adjusted only to name the app):
  > *Øv på å kjøre analyser i microdata.no-stil. Inneholder ikke ekte tall; et
  > hobbyprosjekt, ikke laget av microdata.no.*
  > EN: *Practise running analyses in the microdata.no style. No real figures; a
  > hobby project, not made by microdata.no.*

- **OpenStat, general framing** (python/r/duck/bare host):
  > *OpenStat er en motor for å stille spørsmål som kan besvares med kode og
  > statistikk — og for å se og endre koden som gir svaret. Skriv i Python, R,
  > DuckDB eller microdata-stil; kjør i nettleseren.*
  > EN: *OpenStat is an engine for asking questions that can be answered with
  > code and statistics — and for seeing and revising the code behind the
  > answer. Write in Python, R, DuckDB or microdata style; run in the browser.*

- **SafeStat, general framing** — OpenStat general **plus** the sensitive-data
  angle:
  > *SafeStat gjør det samme, og kan i tillegg dele og gi tilgang til sensitive
  > data: bare analyser som bruker et begrenset sett kommandoer slipper gjennom,
  > slik at resultatene viser aggregater — aldri opplysninger om enkeltpersoner.*
  > EN: *SafeStat does the same, and can additionally distribute and grant access
  > to sensitive data: only analyses using a restricted set of commands are
  > permitted, so results show aggregates — never information about individuals.*

Copy above is a draft for refinement; all strings go through the i18n catalog
(`js/i18n/en.js`) as elsewhere.

---

## Architecture & components

| Unit | Responsibility | Location |
|---|---|---|
| `fragment-router` | classify `location.hash`; dotted↔raw resolve; `main`→`master`; hand off to open vs autorun-output | extend `js/github-storage.js` (or a sibling `js/notebook-links.js`) |
| output-only presenter | `mdSetInputHidden(true)` + "show code" affordance; per-app autorun (OpenStat direct/safety-valve, SafeStat S2 gate) | `index.html` + `js/ai-chat.js` gate reuse |
| `prose-segmenter` (Python) | AST transform of top-level bare-string `Expr` → `__md_emit__` call; inject emitter | Python run path (the `runPythonAsync` that executes editor content) |
| `prose-segmenter` (R) | `#'` block scan → `cat`-emitted markdown embed | R run path (webR hybrid runner) |
| `startup-mode` resolver | `location.hostname` → default mode (`py`/`r`/`duck` exact label, `micro` substring, else python); pick welcome framing | boot path in `index.html`, runs before the fragment router |

Interfaces stay narrow: the router takes a hash string and returns a
`{action, url, mode}` decision (pure, testable without the DOM); the Python
segmenter takes source and returns transformed source (pure, testable without
Pyodide); the R segmenter takes source and returns transformed source.

## Testing

- **Router/resolver (unit):** dotted→URL; raw-URL passthrough; `main`→`master`
  fallback on 404; missing extension / too-few tokens rejected; `#output`
  vs open; gist and Dropbox raw URLs; `#s=` still handled.
- **Python segmenter (unit):** bare triple-quoted → markdown; single-quoted bare
  string → markdown; assigned string NOT rendered; function/class docstring NOT
  rendered; interleaving order across code+prose; variables persist across
  prose; marker-injection payload neutralized.
- **R segmenter (unit):** contiguous `#'` block → one markdown block; `#'`
  interleaved with code; ordinary `#` comments untouched.
- **Startup-mode resolver (unit):** `py.openstat.app`→python, `r.…`→r,
  `duck.…`→duckdb, `microdata.run`/`micro.safestat.app`→microdata,
  `spy.openstat.app`→python (no false `py` hit), bare host→python, localhost→
  python; fragment file-extension overrides host mode but host still picks
  welcome framing.
- **Welcome variant (unit):** framing×app → correct copy; output-only →
  no welcome; dismissal respected across variants.
- **E2E per app:** open-link loads into editor with correct mode; output-link
  runs and hides input and shows no welcome; "show code" reveals editor;
  SafeStat shows the gate, OpenStat runs directly (and OpenStat falls back to the
  gate when a secret is present); `micro` host boots microdata with the
  microdata welcome, bare host boots python with the general welcome.

## Rollout

Build in **SafeStat** first (engine is source of truth), then port to
**OpenStat** with the per-app autorun switch — the same SafeStat→OpenStat flow
used for the code-review fixes. Prose-segmenter engine code (if any lands in
`m2py.py`/run helpers shared via the sync) propagates through `sync_to_api.py`.

## Out of scope (v1)

- f-strings / dynamic interpolation as prose.
- Non-GitHub dotted shorthands (raw-URL form covers other hosts).
- Auto-hiding the editor again after "show code".
- A visual notebook editor; this is link + rendering only.
