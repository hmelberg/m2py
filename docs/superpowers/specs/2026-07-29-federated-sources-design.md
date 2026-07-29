# Federated data sources — design

**Date:** 2026-07-29
**Status:** Approved. Phase 0 implemented 2026-07-29 (plan `docs/superpowers/plans/2026-07-29-federert-fase0.md`); phases 1–2 not started.
**Scope decision:** Horizontal partitioning first; browser-as-coordinator; three trust tiers; phases 0 → 1 → 2.

## 1. Problem

SafeStat analyzes one dataset at a time. In practice the same table often lives split
across several data holders (regions, hospitals, registries): same variables,
different people. We want the analyst to write a script **as if the data were one
source**, while behind the scenes the analysis runs against many sources — and, for
sensitive data, without raw rows ever leaving any holder.

"Federated" covers two fundamentally different models, and the design supports both
as *tiers of the same source definition* rather than as separate features:

- **Model A — pull-and-pool (data travels).** Fetch from N sub-sources, auto-union,
  analyze locally. Simple, works in every mode, but the analysis environment sees
  the pooled raw data.
- **Model B — compute-to-data (the script travels).** Each holder's node runs the
  translated script locally, applies statistical disclosure control (SDC), and
  returns only aggregates; a coordinator combines them. Raw data never leaves the
  source. This is the DataSHIELD model, and the restricted microdata language makes
  it tractable: a finite verb set means every verb either has a known combine rule
  or is refused.

### Why not an existing library

- **Dask / Spark / R future**: distributed compute over a *trusted* cluster — they
  assume free data movement between workers, the opposite of federation. None run
  in Pyodide/webR.
- **DataSHIELD (R)**: the right prior art — whitelisted functions, per-node
  disclosure checks, aggregate-only returns. Not embeddable (needs Opal servers),
  but its design is adopted here. SafeStat's m2py verb set + `m2py_protection` is
  already structurally a DataSHIELD server.
- **vantage6 / Flower / PySyft**: heavy, server-centric, ML-oriented.

**Decision: build a thin federation layer on existing SafeStat seams.**

## 2. Existing seams this builds on

| Seam | File | Role in federation |
| --- | --- | --- |
| Multi-source remote run | `m2py_remote.py` (`run_remote_from_sources`) | Already runs one script over a list of `{alias, location, level}` sources on one server. Federation = fanning this out across N servers. |
| Policy merge | `m2py_protection.py` (`resolve_policy`) | Most-restrictive-source-wins across `public < protected < sensitive`; extended to member tiers. |
| Result-side SDC | `m2py_protection.py` (`PandasProtect.suppress`) | Per-node suppression before any aggregate is released. |
| Directive DSL | `js/data-directives.js` (`# connect`, `# load`) | Where a federated alias is declared and expanded. |
| Registry | `data/data-sources.json`, `m2py_runtime/manifest.py` | Where a federated source definition lives. |
| Per-source keys | `source_keys` via `/local_run_authorize`, `key(ask)`, server-injected env keys | Reused per member; no new key machinery. |
| Strict worker | `js/strict-worker.js` | Basis of the encrypted-static middle tier: plaintext exists only inside the Pyodide module worker. |
| Remote run protocol | `/_/api/run_extended[_status]` (`index.html`, `runSafeStatRemote`) | Reused unchanged as the per-node protocol in Phase 1. |

## 3. Source definition

A federated source is a compound entry in the registry (and, equivalently, in a
`Manifest`), declaring per member what that holder offers:

```json
{
  "id": "helse",
  "kind": "federated",
  "partition": "horizontal",
  "entity": "person_id",
  "overlap": "possible",
  "members": [
    { "id": "helse-nord", "tier": "node",      "url": "https://nord.example/api",  "level": "sensitive" },
    { "id": "helse-vest", "tier": "encrypted", "url": "https://vest.example/pasienter.enc", "level": "protected" },
    { "id": "helse-sor",  "tier": "static",    "url": "https://sor.example/pasienter.parquet", "level": "public" }
  ]
}
```

Directive syntax — the alias behaves as one source from then on:

```
# connect federert(helse-nord, helse-vest, helse-sor) as helse
import helse/pasienter
```

or `# connect helse as h` when the compound entry is already in the registry.
Member credentials use the existing mechanisms per member (`key(ask)` per encrypted
member; per-run `source_keys` for node members; env-injected keys via the proxy).

### Trust tiers (per member)

| Tier | Holder installs | What travels | Sufficient for level |
| --- | --- | --- | --- |
| `static` | nothing (any static host) | raw data | `public` |
| `encrypted` | nothing (upload one AES-GCM envelope) | ciphertext; plaintext only inside the strict worker | `protected` |
| `node` | small service (`safestat-node`, Phase 2; Anvil app today) | aggregates only | `sensitive` |

**Enforcement rule:** `resolve_policy` refuses the run if any member's `level`
demands a higher tier than the member provides (e.g. sensitive data behind a plain
static URL → hard error naming the member). A single federated source may mix
tiers; the coordinator pulls the static/encrypted members and dispatches script to
the node members, provided every member's own policy is satisfied.

The **encrypted middle tier** is deliberately first-class: it costs the holder
nothing to operate, and SafeStat is unusually suited to it — the strict worker
already guarantees plaintext never touches the JS heap, the Pyodide FS, or disk,
and the analyst only sees SDC-protected output. It is weaker than a node (the
ciphertext travels; a leaked key exposes the file) but far stronger than plain pull.

### Horizontal-first; overlap future-proofing

Scope is **horizontal partitioning** (same schema, different people). At connect
time the coordinator checks member schemas and warns/refuses on drift.

Patients appearing in more than one member (rare, per scope decision) are a
*semantics* problem, not an architecture problem — entity counts silently become
episode counts. Insurance is limited to the two fields already in the format:

- `overlap: "possible"` ⇒ entity-count results get an automatic footnote
  ("members may overlap; counts are episode-level"), and cross-node
  distinct-entity counts refuse with a clear message.
- Future options (node-side hashed-ID sketches, privacy-preserving record linkage)
  slot in behind these fields without format changes. Not designed further now.

Vertical partitioning (same people, different variables; requires linkage) is an
explicit **non-goal**.

## 4. Phase 0 — pull-federation (all modes, tiers static/encrypted)

**What:** `federert(...)` alias expands, in `DataDirectives.resolve()`, into N load
items plus an automatic union step in the `AssemblySpec` (a `union` counterpart to
the existing create-dataset/import/join compilation in `js/assembly-duckdb.js`).
A provenance column (`__member`) is added so per-member breakdowns stay possible.

- Works in every mode; in sql/duckdb mode, duckdb-wasm unions parquet over HTTP
  range requests natively, so only touched byte ranges transfer.
- Encrypted members go through the existing `maybeDecrypt` / strict-worker path.
- Tier/level enforcement applies from day one: pulling a `sensitive` member is
  refused even in Phase 0.

**Touches:** `js/data-directives.js`, `js/data-loader.js`, `js/assembly-duckdb.js`,
registry schema in `data/data-sources.json`. No server changes.

## 5. Phase 1 — true federation (microdata mode, node members)

**Coordinator: the browser.** The static app fans the run out to N nodes directly
and combines client-side. No central party ever sees raw data or unprotected
aggregates from more than its own node — a stronger trust story than a hub, and no
new server tier. (A hub variant exists only as a possible Phase 2 policy option;
see §6.)

**Per-node protocol: `run_extended`, unchanged.** Each node receives
`{script (translated), sources (its own members only), backend, source_keys}` and
returns SDC-protected aggregates plus the metadata the combine layer needs
(per-cell `n`, sums, sufficient statistics — see below). The node is
`m2py_remote.run_remote_from_sources` as it exists today; the additions are
(a) returning combineable statistics rather than only rendered results, and
(b) a `federated: true` flag so the node knows to emit them.

**Combine layer (new, client-side JS module `js/federate.js`):** per-verb rules,
mirroring the DataSHIELD design. Verbs outside the table refuse with a clear
message; coverage grows verb-by-verb.

| Verb class | Combine | How |
| --- | --- | --- |
| count, sum, freq/tabulate | exact | sum per-node cells |
| mean, summarize | exact | pool (sum, n) per group |
| variance, correlation, linear regression | exact | pool sufficient statistics (XᵀX, Xᵀy, n) |
| logistic regression | later | iterative (one fan-out per round); not in v1 |
| median, percentiles | refused in v1 | no exact combine; iterative bisection is a later option |
| raw-row verbs (list, scatter, …) | forbidden | already blocked on non-public data (`_RAW_PLOT_VERBS`) |

**SDC placement — per-node suppress, then combine (default).** Each node applies
`PandasProtect.suppress` before anything leaves it. This can over-suppress sparse
tables (a cell with n=3 in each of four nodes is n=12 combined but suppressed
everywhere); accepted as the safe default. Combine-then-suppress requires a
coordinator all nodes trust and is deferred to the Phase 2 hub option — the combine
layer's interface is written so the hub can implement it without redesign.

**Sufficient statistics are themselves outputs** and pass the same SDC gate: a node
refuses to emit XᵀX/Xᵀy when its local n is below the policy threshold, exactly as
it would refuse a small cell.

**Run flow:**

1. Analyst writes an m2py script against the federated alias; directive lines are
   stripped from the script as today.
2. `maybeRunRemoteMicrodata` detects a federated source with node members →
   `m2py_translate.translate()` output is POSTed to each node's `run_extended`
   in parallel; per-node status polled as today.
3. `js/federate.js` combines returned statistics per verb, renders one result, and
   annotates it (member list, per-member n where releasable, overlap footnote if
   `overlap: "possible"`).

**Error handling:** a member that is down/unauthorized fails the run by default
(partial results silently presented as the whole would be a correctness trap); a
future `allow_partial` flag on the source definition may relax this, always with a
prominent "k of N members" annotation. Schema drift between members is caught at
connect time. Mixed-tier runs execute pull for static/encrypted members and
node-dispatch for node members, then feed both into the same combine layer (a
pulled member is combined as a locally-computed "node" result).

## 6. Phase 2 — someday

- **`safestat-node`**: a pip-installable service (FastAPI + `m2py_remote` +
  `m2py_protection` + policy file) so any holder can run a node without Anvil.
  `m2py_remote.py` is pure CPython (~180 lines + engine files), so this is
  packaging, not new engine work.
- **Trusted-hub combine mode**: opt-in coordinator that receives exact (unrounded,
  unsuppressed) aggregates from consenting nodes and applies SDC once on the
  combined result — better utility on sparse tables. Same combine interface as the
  browser layer.
- **Overlap handling**: hashed-ID distinct-count sketches or record linkage, behind
  the `entity`/`overlap` fields. Only if a real need appears.
- **Logistic regression / percentiles** via iterative rounds.

## 7. Testing

- **Phase 0:** unit tests for `federert(...)` expansion in `data-directives`
  (existing test conventions in `tests/`); an example federated source over 2–3
  static parquet files split from the existing synthetic `static_data` tables —
  assert that federated results equal the same analysis on the unsplit table
  (byte-equal for counts/means).
- **Phase 1:** pytest-side, split a synthetic table into N parts and run
  `run_remote_from_sources` per part + combine in Python, asserting exact equality
  with the pooled run for every supported verb (the combine rules are exact, so
  equality is exact up to float tolerance for regression). SDC tests: per-node
  small cells suppressed even when combined n is large (documented behavior);
  sufficient-stats refusal below threshold. Browser-side, smoke test against 2–3
  "virtual nodes" (the existing Anvil server registered under multiple source
  aliases) before any real multi-server setup exists.

## 8. Non-goals

- Vertical partitioning / record linkage.
- Adopting Dask, Spark, DataSHIELD, vantage6, Flower, or PySyft.
- Federating the open (non-restricted) Python/R languages beyond Model A pull —
  arbitrary code has no general combine rule; true federation stays exclusive to
  the restricted verb set by design.
- Differential privacy; the SDC model remains threshold/rounding-based as today.
