# Extended mode — architecture & guardrails

**Status:** standing design note (the guardrail for building "Extended" mode)
**Related:** `docs/superpowers/specs/2026-06-28-manifest-and-require-design.md`
(the editor-delivery decision, staged A→B, and "microdata is a source kind").

## Purpose

"Extended" mode lets the editor analyze data from arbitrary sources (a CSV at a
URL, a parquet file, a manifest-described registry) instead of only the SSB
microdata catalog. The two modes **share a lot of code now and diverge over
time**, and the divergence (especially how `import`/`require` are interpreted)
must land almost entirely in Extended without touching traditional microdata
mode. This note records *how* to build it so that property holds by construction,
not by vigilance.

## The key fact: two engines, one-directional dependency

- **Microdata mode** runs on the **emulator** (`MicroInterpreter` in `m2py.py`)
  — SSB catalog + deterministic mock data.
- **The offline / Extended path** runs on the **translator**
  (`m2py_translate` + `m2py_runtime`) — real data via `read_source`, emitted as
  runnable pandas/polars.

The dependency runs **one way**: the translator depends on the emulator (parser,
oracle semantics, a few helpers); the emulator never calls the translator.
Therefore **anything built into the translator's interpretation of
`import`/`require`/loading cannot reach microdata mode** — it is a code path the
emulator never executes. Most of the isolation you want is already structural.

### Cardinal rule: never fork the emulator

Do **not** copy `m2py.py` into an `m2py_extended.py`. Forking duplicates the ~95%
that is shared and forces every bug-fix to be chased across both copies. There is
**one emulator** (the microdata engine), **one translator** (the Extended
engine), and a small shared layer between them. Build Extended as a *consumer of
the translator*, not as a fork of the emulator.

## The only shared *mutable* surfaces — and the rule for each

Almost everything is naturally isolated by the engine split. Exactly three things
are shared and mutable. Each has one rule:

1. **The parser / IR (`MicroParser`)** — both engines parse the same text.
   **Rule: changes must be additive and behavior-preserving for existing
   scripts.** New optional syntax (`keys()`, URL sources, `version()`, `auth()`)
   is fine because it does not change how today's lines parse. The URL `//`-guard
   is the model — it preserved every existing parse result. Anything that would
   change an existing parse result is a red flag.

2. **The runtime ops (`m2py_runtime`)** — the emulator only touches these in one
   spot (the lazy `keys` import in merge). **Rule: add new ops or new optional
   parameters; never change an existing op's behavior.** `merge_into` becoming
   list-aware while keeping the scalar path identical is the model.

3. **Reused helpers in `m2py.py`** (`_py_eval_expr`, `DataTransformHandler`, the
   parser, `resolve_merge_key`). **Rule: the translator may *call* them but must
   not *change* them.** If Extended needs different behavior, wrap or add — do not
   edit the shared helper.

Any change to one of these three surfaces is rare and must be reviewed against the
**full test suite** as the regression guard (the characterization-test method:
refactor behind a seam, suite stays green, prove behavior is unchanged).

## Parsing vs interpreting (the subtlest seam)

The parser is the surface most likely to be *felt* as shared, because new Extended
behavior — especially for `import` — often seems to need new syntax. Keep two
layers distinct:

- **Parsing** (text → IR): shared. Changing it can affect both engines.
- **Interpreting** (IR → behavior): the emulator does one thing with the IR, the
  translator another. Separate.

The real question for any Extended change is **"new *syntax*, or just new
*interpretation*?"** — and most import changes are the latter. Three routes reach
new behavior **without touching `MicroParser`**:

1. **Reinterpret existing syntax.** `import src/INNTEKT as lonn` already parses;
   Extended makes `src` a file/URL source and the import a column-pull/join
   instead of catalog+mock. Same IR, different meaning → translator-only.
2. **Use the generic option slot.** `MicroParser` already captures `, name(arg)`
   generically (this is how `keys()`, `version()`, `auth()` parse), so a new knob
   like `import s/x as y, join(left)` → `options={'join':'left'}` needs **no
   grammar change** — the translator just reads the option.
3. **Post-parse in the translator.** Pull Extended-only constructs out of the raw
   line / IR in the translator, leaving `MicroParser` untouched.

When a grammar change in `MicroParser` *is* genuinely needed, the protective rule
is **not** "don't touch the parser." It is:

> **Don't change how any *existing* script parses.**

An additive change (a new optional token/form) is safe for two compounding
reasons: (1) existing microdata scripts parse identically — the new field is
simply absent for them (verified by the suite); and (2) the new syntax only
appears in Extended scripts, which run on the **translator, never the emulator**,
so the emulator never even sees that IR. So the blast radius is "did an existing
line's parse result change?", not "did the parser file change?".

**Anti-pattern to avoid:** making the *same text* parse differently per mode
(mode-dependent tokenization). That genuinely couples the engines. Keep **one
superset grammar** — the IR carries every field, each engine interprets what it
needs. If two behaviors need different syntax, give them *different syntax*.

| Kind of import change | Parser? | Affects emulator? |
|---|---|---|
| Reinterpret existing syntax (file source, column-pull) | no | no |
| New option via the generic `, opt(arg)` slot | no | no |
| Extended-only construct, post-parsed in the translator | no | no |
| Genuinely new grammar, **additive** | yes (additive) | no — existing scripts parse identically; new syntax only runs in Extended |
| Change to how *existing* syntax parses | yes | **yes — red flag, don't** |

Only the last row is dangerous, and it is the one thing rule 1 forbids.

## In-engine divergence: dispatch by source kind, never branch on mode

Inside the translator, **do not write `if extended:`** anywhere. Put the
divergence behind a small policy interface keyed on the **bound source's kind** —
the concrete form of the "microdata is a source kind" decision.

```python
class SourceKind:                 # the seam
    def emit_load(self, name): ...                       # how to materialise the dataset
    def emit_import(self, active, var, alias, opts): ...  # what `import` does
    def key_for(self, name): ...                          # where keys come from
    def metadata(self, name): ...                         # labels / types

class CatalogKind(SourceKind):    # microdata semantics: catalog, mock, labels, time-align
    ...

class FileKind(SourceKind):       # manifest / read_source / column-pull / explicit keys
    ...
```

The translator's walk asks the bound source's kind how to handle each
`require`/`import`/load; it never knows or cares about "mode."

Consequences:

- **New Extended `import` behavior** (read from a URL, column-pull, join on key)
  lives entirely in `FileKind.emit_import`. `CatalogKind` is the faithful
  microdata version and is never touched — so "changes mainly affect Extended" is
  enforced by *where the code physically lives*, not by discipline alone.
- **It scales to the planned convergence (staged A→B)** with no restructuring:
  - *Step A (now):* the whole script is `FileKind` (Extended mode) or
    `CatalogKind` (microdata mode).
  - *Step B (later):* dispatch *per source* — a script mixing an SSB catalog
    source and a URL CSV picks the kind per `require`. Same interface.

`CatalogKind` is the default; `manifest=None` / no Extended mode selects it, so the
untouched path is always the baseline.

## Execution targets (a second axis, orthogonal to mode)

*Where* and *how* a script runs — local Pyodide, send-to-server-API,
encrypted-local-with-API-unscramble, remote-data-remote-execution — is a
**different axis from semantics**, and must not become its own mode. Splitting on
it would create a cross-product (Extended-local, Extended-remote,
microdata-remote, …) and duplicate the identical translation. Whenever
"mode × mechanism" starts multiplying, the mechanism is a *strategy*, not a mode.

**Translate once, run via an Executor.** The translator produces one portable
artifact (the pandas/polars script + the source bindings); an executor runs it,
behind a common interface:

```python
class Executor:
    def run(self, artifact, sources) -> Result: ...
```

| Scenario | Executor |
|---|---|
| Local Pyodide, public data | `LocalPyodideExecutor` |
| Send script to server, get result back | `RemoteApiExecutor` (compute-to-data) |
| Encrypted local data, unscramble result via API | `EncryptedLocalExecutor` |
| External data, code runs there | `RemoteApiExecutor` |

The security mechanisms (encryption, unscramble-API, no-data-egress) are
properties of the executor and the source — layered on, **not new languages**.

**The target is derived, not toggled.** The manifest's `sensitivity`/location
(the security spectrum in the manifest spec) implies the executor: a public URL →
local; a registered sensitive source → remote-API (data never leaves the server);
an encrypted blob → encrypted-local. So *the same source property that picks the
source-kind policy (semantics) also picks the executor (where it runs)* — both
fall out of "what kind of source is this," and neither needs a manual mode switch
in the common case.

**Most-restrictive source wins.** For a script mixing sources of different
sensitivity (a public CSV + a sensitive registry), the executor is the most
restrictive any source demands: if anything is compute-to-data, the whole script
runs remotely — you cannot pull sensitive data local. This makes the target a
derived, *enforced* property, not a user preference.

**Backend** (pandas / polars / DuckDB push-down) is a third, related runtime knob
the executor selects (browser → pandas; large server-side data → DuckDB/polars
streaming). It too is orthogonal to mode.

So the three axes compose independently:

| Axis | What it decides | Selector |
|---|---|---|
| **Mode** | semantics (microdata vs Extended) | source kind (`CatalogKind`/`FileKind`) |
| **Executor** | where it runs + trust envelope | source sensitivity/location (most-restrictive wins) |
| **Backend** | runtime engine | executor (size/locality) |

"Translate once, run anywhere, under the envelope the source demands" is the
property that keeps this from exploding into modes.

## Front-end: reuse the existing mode-plugin system

The editor already has a lazy mode-plugin system (`registerMode` + the `window.M2PY`
contract, from the jamovi refactor; `js/modes/<id>.js` loaded on demand). Extended
mode is **another mode module** — `js/modes/extended.js` that lazy-loads,
self-registers, and routes its run to `translate(manifest=…)` + execute. The
microdata-mode plugin is untouched. The UI cost is "one more mode module," not new
infrastructure.

## Guardrails checklist (apply to every Extended change)

1. Build Extended **on** the translator; **never fork** the emulator.
2. Shared surfaces (parser, ops, helpers): **additive and behavior-preserving
   only**, guarded by the green suite.
3. All semantic divergence goes in a **`FileKind` / Extended policy** object;
   **zero `if extended:`** in shared code.
4. **Default is microdata** (`CatalogKind` / `manifest=None`) — the untouched path
   is the baseline.
5. Every Extended feature is a method on the policy or a new op. **If you are
   editing the emulator's logic in `m2py.py`, stop** — it is almost certainly the
   wrong place.

## Why this is efficient

The engine split isolates ~90% of the divergence for free (the emulator never runs
translator code). A small source-kind policy isolates the rest into one class. The
three additive-only rules plus the test suite protect the shared seams. Net: heavy
sharing now, safe divergence later, and microdata mode never feels an Extended
change.
