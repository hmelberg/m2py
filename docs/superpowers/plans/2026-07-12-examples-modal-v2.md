# Eksempler-modal v2 — Implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erstatt eksempel-dropdownen med ÉN modal som er scoped til aktiv modus, drevet av `examples/<modus>/`-foldere; fold `web_examples/` inn i `examples/microdata/`; migrer alle modiers eksempler til folderstrukturen.

**Architecture:** Datalaget fra v1 står (generator, `examples/manifest.json`, `js/examples-menu.js`). Alle eksempelfiler flyttes til `examples/<modus>/`. «Eksempler»-knappen åpner den eksisterende to-panels-modalen (`initWebExamples`), nå generalisert til å vise gruppert data fra `ExamplesMenu.groupForMode(manifest, aktivModus)`. Modalen tilpasser seg: flat modus → én liste; kategorisert → to paneler; begge scrollbare.

**Tech Stack:** Python 3 stdlib (`pathlib`, `re`, `json`, `html`), pytest, ES5 browser-JS, Node `node:test`.

**Utgangspunkt:** grenen `examples-manifest` (safestat `b554745`, openstat `521468e`). v1 Task 1–3 + generator står; micropython alt migrert til `examples/micropython/`; v1s dropdown-render (i `index.html`) FJERNES av denne planen.

## Global Constraints

- **To repoer:** safestat leder; synk til openstat (Task V2-5). Delt kode (generator, `examples-menu.js`, modal-JS) byte-identisk; `examples/`-innhold og `manifest.json` per repo.
- **Modus-scoped:** modalen viser KUN aktiv modus' eksempler (fra `examples/<modus>/`). Aldri eksempler fra andre modi.
- **Ett system:** ingen egen «Flere eksempler»-knapp; ingen dropdown. Klikk «Eksempler» → modal.
- **Lat henting:** `examples/manifest.json` hentes med `{cache:'no-store'}` ved første modal-åpning, aldri på boot-stien.
- **Adaptiv + scrollbar:** flat modus (ingen kategorier) → én liste, intet tomt kategori-panel. Kategorisert → to paneler. Begge paneler scrollbare (eksisterende `.web-examples-pane{overflow-y:auto}` + `.web-examples-body{max-height:60vh}`).
- **Bevar kuraterte labels:** de ~80 labelene som i dag bare finnes i `index.html`-knappene MÅ skrives inn i filene som `# label:` under migreringen. web-eksemplenes `// Example:`-labels bevares via generator-utvidelse (Task V2-1) — ikke rør de filenes innhold.
- **Label-kilde (prioritert):** `# label:`/`-- label:`/`// label:`/`// Example:` → `#options.title` → filnavn.
- **ES5 browser-JS** (`var`/`function`); ingen bundling.
- **Modus-hvitelist (generator):** `microdata, python, r, statx, jamovi, duckdb, brython, micropython, safestat`.

---

### Task V2-1: Generator godtar `// Example:`-markør

**Files:**
- Modify: `examples/generate_manifest.py`
- Test: `tests/test_examples_manifest.py`

**Interfaces:**
- Produces: `label_for` godtar nå en `Example:`-markør (`#`/`--`/`//`-prefiks) på samme prioritetsnivå som `label:` (før `#options.title`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_examples_manifest.py`:

```python
def test_label_from_example_marker(tmp_path):
    p = tmp_path / "01_x.txt"
    p.write_text("// ===\n// Example: Opprette datasett\n// Source: http://x\n",
                 encoding="utf-8")
    assert gm.label_for(p) == "Opprette datasett"


def test_label_line_beats_example_marker(tmp_path):
    p = tmp_path / "01_x.txt"
    p.write_text("// Example: Fra Example\n# label: Fra label\n", encoding="utf-8")
    assert gm.label_for(p) == "Fra label"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/safestat && python -m pytest tests/test_examples_manifest.py -k "example_marker or beats_example" -v`
Expected: FAIL (`test_label_from_example_marker` returns filename-derived `"X"` instead of `"Opprette datasett"`).

- [ ] **Step 3: Implement**

In `examples/generate_manifest.py`, add an EXAMPLE regex near the existing `LABEL_RE`:

```python
EXAMPLE_RE = re.compile(r"^\s*(?:#|--|//)\s*Example:\s*(.+?)\s*$")
```

In `label_for`, in the FIRST pass (the one that currently checks `LABEL_RE`), also accept `EXAMPLE_RE` at the same tier. Concretely, the first pass becomes: for each of the first 5 lines, if `LABEL_RE` OR `EXAMPLE_RE` matches, return its group(1). Keep the second pass (`TITLE_RE`) and the filename fallback unchanged. `# label:` still wins over `// Example:` only when the label line appears first; to guarantee label-line priority regardless of order, check ALL lines for `LABEL_RE` first, then ALL lines for `EXAMPLE_RE`, then `TITLE_RE` (three ordered passes over the collected `lines`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/hom/Documents/GitHub/safestat && python -m pytest tests/test_examples_manifest.py -v`
Expected: PASS (all prior + 2 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add examples/generate_manifest.py tests/test_examples_manifest.py
git commit -m "feat: generator reads // Example: label marker (for web_examples fold-in)"
```

---

### Task V2-2: Migrer alle modiers eksempler til `examples/<modus>/` + fold web_examples

**Files:**
- Move: all flat `examples/*.txt` → `examples/<mode>/<file>.txt` (per their `data-mode` in index.html); add `# label:` line to each from the index.html button text.
- Move: `web_examples/<NN_kategori>/*.txt` → `examples/microdata/<NN_kategori>/*.txt` (labels come from their existing `// Example:` lines — do NOT edit content).
- Regenerate: `examples/manifest.json`.
- Scratch: a one-off migration script in the session scratchpad (NOT committed).

**Interfaces:**
- Consumes: `examples/generate_manifest.py` (with V2-1).
- Produces: `examples/manifest.json` with every mode populated; each mode's entries carry the curated labels.

- [ ] **Step 1: Write a one-off migration script (scratchpad, not committed)**

Create `/private/tmp/claude-501/-Users-hom-Documents-GitHub/9a73ebd5-168d-44d8-9606-75379bb75618/scratchpad/migrate_examples.py`:

```python
import html, re, subprocess, sys
from pathlib import Path

REPO = Path(sys.argv[1])            # repo root
idx = (REPO / "index.html").read_text(encoding="utf-8")

# 1) Parse example buttons: data-example, data-mode, inner text (label).
BTN = re.compile(
    r'<button[^>]*data-example="([^"]+)"[^>]*data-mode="([^"]+)"[^>]*>(.*?)</button>',
    re.S)
moved = 0
for m in BTN.finditer(idx):
    fileattr, mode, label = m.group(1), m.group(2), m.group(3)
    label = html.unescape(re.sub(r"<[^>]+>", "", label)).strip()
    if "/" in fileattr:             # already migrated (e.g. micropython/01_...)
        continue
    src = REPO / "examples" / fileattr
    if not src.exists():
        print("SKIP missing:", src); continue
    dst = REPO / "examples" / mode / fileattr
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(REPO), "mv", str(src), str(dst)], check=True)
    text = dst.read_text(encoding="utf-8")
    dst.write_text("# label: " + label + "\n" + text, encoding="utf-8")
    moved += 1
print("moved+labeled:", moved)

# 2) Fold web_examples category folders into examples/microdata/ (keep // Example:).
web = REPO / "web_examples"
folded = 0
if web.exists():
    for cat in sorted(p for p in web.iterdir() if p.is_dir()
                      and re.match(r"^\d+_", p.name)):
        dst = REPO / "examples" / "microdata" / cat.name
        subprocess.run(["git", "-C", str(REPO), "mv", str(cat), str(dst)], check=True)
        folded += 1
print("folded web categories:", folded)
```

- [ ] **Step 2: Run the migration for safestat**

Run: `python /private/tmp/claude-501/-Users-hom-Documents-GitHub/9a73ebd5-168d-44d8-9606-75379bb75618/scratchpad/migrate_examples.py /Users/hom/Documents/GitHub/safestat`
Expected: prints `moved+labeled: N` (N ≈ 70, the non-micropython flat files) and `folded web categories: 12`. Investigate any `SKIP missing` lines (a button pointing at a non-existent file — note it, it becomes a dead button to drop in V2-3).

- [ ] **Step 3: Regenerate the manifest**

Run: `cd /Users/hom/Documents/GitHub/safestat && python examples/generate_manifest.py`
Expected: `Skrev manifest.json (M modi, T eksempler).` with M = number of modes that have files (≈ 8) and T ≈ 160.

- [ ] **Step 4: Verify counts and a spot-check**

Run:
```bash
cd /Users/hom/Documents/GitHub/safestat
python -c "import json; m=json.load(open('examples/manifest.json')); \
print('modes', sorted(m)); \
print('per-mode', {k: len(v) for k,v in m.items()}); \
print('microdata categories', sorted({e['group'] for e in m['microdata'] if e['group']})); \
assert any(e['group'] for e in m['microdata']), 'microdata should have categories'; \
assert all(e['label'] for mode in m.values() for e in mode), 'every entry has a label'"
```
Expected: micropython 4 (flat), microdata has both flat entries (group=None) and ~12 categories, other modes populated, every entry has a non-empty label.

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add examples/ 
git commit -m "feat: migrate all modes' examples into examples/<mode>/ + fold web_examples into microdata"
```
(The scratchpad migration script is outside the repo and is not committed.)

---

### Task V2-3: Generaliser modalen; «Eksempler» åpner den modus-scoped

**Files:**
- Modify: `index.html` — the examples-menu init region (`menuExamplesBtn` handler ~1889; the v1 dropdown render funcs `renderExamplesFromManifest`/`ensureExamplesRendered`/`global_ExamplesMenu`; the delegated click listener; the `initWebExamples` modal ~1936; the `.examples-section` markup ~31–121; the `menuWebExamples` button ~122).

**Interfaces:**
- Consumes: `ExamplesMenu.groupForMode(manifest, mode)` (v1), `loadExampleFile(file, title, mode)` (v1), the modal DOM (`#webExamplesOverlay`, `#webExCategories`, `#webExScripts`, `#webExLoadBtn`, `#webExCancelBtn`), `activeEditorMode`.
- Produces: a mode-scoped example modal opened from «Eksempler».

- [ ] **Step 1: Read the current modal + menu code**

Read `index.html` around lines 749–759 (modal HTML), 1882–1934 (menu handlers + delegated click + v1 render), and 1936–~2040 (`initWebExamples`). You will adapt `initWebExamples` rather than rewrite it.

- [ ] **Step 2: Add a lazy manifest loader (once)**

In the examples-menu scope, add a memoized loader (reuse v1's if still present; otherwise add):

```javascript
      var __examplesManifest = null, __examplesManifestP = null;
      function loadExamplesManifest() {
        if (__examplesManifest) return Promise.resolve(__examplesManifest);
        if (!__examplesManifestP) {
          var base = window.location.href.replace(/[^/]+$/, '');
          __examplesManifestP = fetch(base + 'examples/manifest.json', { cache: 'no-store' })
            .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
            .then(function (m) { __examplesManifest = m; return m; })
            .catch(function (e) { __examplesManifestP = null; throw e; });
        }
        return __examplesManifestP;
      }
```

- [ ] **Step 3: Generalise the modal to render a grouped list for a mode**

Adapt `initWebExamples` (rename its opener to `openExamplesModal(mode)` and expose it in the menu scope). Replace its `web_examples/manifest.json` fetch + `manifest.categories` rendering with rendering from `ExamplesMenu.groupForMode`. Required behavior:

- `openExamplesModal(mode)`:
  1. `loadExamplesManifest()` then compute `groups = ExamplesMenu.groupForMode(manifest, mode)`.
  2. If `groups.length === 0`: show `.empty-hint` ("Ingen eksempler for denne modusen ennå") in the scripts pane, hide the categories pane, open the overlay.
  3. If the ONLY group is the null group (flat mode): hide the categories pane (`webExCategories.style.display = 'none'`), render ALL its examples as buttons in the scripts pane.
  4. If there are named categories: show the categories pane (`display = ''`), render one button per group (label = `group.group`); clicking a category renders that group's examples in the scripts pane (category click only navigates — it does NOT load). If a null group also exists, list it first under a heading like "Ukategorisert". Auto-select the first category so the scripts pane isn't empty on open.
  5. **Single-click to load:** clicking a SCRIPT button calls `loadExampleFile(ex.file, ex.label, mode)` immediately (v1 helper — loads the file, switches mode) and closes the modal (`overlay.classList.remove('open')`). No select-then-confirm step. Remove the old `loadSelected` `web_examples/`-path fetch and the selection/`selected`/`loadBtn.disabled` bookkeeping.
  6. On fetch failure: show `.empty-hint` ("Kunne ikke laste eksempler — last siden på nytt") in the scripts pane.
- **Footer:** remove the «Last inn» button (`#webExLoadBtn`) — single-click loads, so it's redundant. Keep «Avbryt» (`#webExCancelBtn`) to close the modal.
- Panes stay scrollable (existing CSS `.web-examples-pane{overflow-y:auto}`, `.web-examples-body{max-height:60vh}`) — no CSS change needed for scrolling.

- [ ] **Step 4: Wire «Eksempler» to open the modal; remove the dropdown**

- In the `menuExamplesBtn` click handler (~1889): replace the dropdown-toggle body with `openExamplesModal(activeEditorMode); hamburgerDropdown.classList.remove('open');` (close the hamburger; do NOT toggle `examplesDropdown`).
- Delete: v1's `renderExamplesFromManifest`, `ensureExamplesRendered`, `global_ExamplesMenu`, `updateExamplesVisibility`, and the delegated click listener on `examplesDropdown` (the modal now owns clicks). Keep `loadExampleFile`.
- Delete the `.examples-dropdown#examplesDropdown` block (the `.examples-section` divs, lines ~30–121) and the `menuWebExamples` button (~122) and its click handler.
- If any `SKIP missing` dead buttons were noted in V2-2, they are already removed by deleting the `.examples-section` markup — no separate action.

- [ ] **Step 5: Syntax check + tests**

Run:
```bash
cd /Users/hom/Documents/GitHub/safestat
# extract the main inline <script> and node --check it (as prior tasks did)
node --test tests/js/examples-menu.test.js
```
Expected: `node --check` on the extracted inline script passes; `examples-menu` tests 3/3 green.

Do NOT run a browser (deferred to Hans, Task V2-6).

- [ ] **Step 6: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add index.html
git commit -m "feat: examples menu opens a mode-scoped modal (remove dropdown + web-examples button)"
```

---

### Task V2-4: Rydd bort `web_examples/` + død dropdown-CSS + README

**Files:**
- Delete: `web_examples/generate_manifest.py`, `web_examples/manifest.json`, and the now-empty `web_examples/` scaffolding (any leftover non-category files like `mpy_engine_test.html` — check before deleting; leave non-example assets if still referenced).
- Modify: `app.css` — remove dead `.examples-dropdown*` / `.examples-section` rules if no longer referenced.
- Modify: `README.md` — update the `## Examples` section to say the menu opens a mode-scoped modal and that examples live in `examples/<mode>/`.

- [ ] **Step 1: Confirm web_examples has no remaining referenced assets**

Run: `cd /Users/hom/Documents/GitHub/safestat && grep -rn "web_examples" index.html app.css js/ | grep -v "generate_manifest"`
Expected: no references remain (the modal no longer reads `web_examples/`). If any remain, resolve them before deleting.

- [ ] **Step 2: Remove web_examples generator/manifest and dead CSS**

```bash
cd /Users/hom/Documents/GitHub/safestat
git rm web_examples/generate_manifest.py web_examples/manifest.json
# remove any now-empty category dirs already moved by V2-2 (git mv emptied them)
```
Then remove dead CSS rules in `app.css` for `.examples-dropdown` and `.examples-section` IF `grep -n "examples-dropdown\|examples-section" index.html` returns nothing (the markup is gone). Keep `.web-examples-*` rules (the modal still uses them).

- [ ] **Step 3: Update README**

Replace the `## Examples` body so it reads: examples live in `examples/<mode>/` (optional `NN_category/` subfolders → categories in the modal); add/remove a file, run `python examples/generate_manifest.py`; the «Eksempler» button opens a mode-scoped modal built from `examples/manifest.json`.

- [ ] **Step 4: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add -A
git commit -m "chore: retire web_examples/, drop dead dropdown CSS, update README"
```

---

### Task V2-5: Synk til openstat

**Files:**
- Mirror in `/Users/hom/Documents/GitHub/openstat/` (branch `examples-manifest`): `examples/generate_manifest.py`, `tests/test_examples_manifest.py` (byte-identical from safestat); run the same migration script against openstat; the same `index.html` modal edits; retire openstat's `web_examples/`; README.

**Interfaces:**
- Consumes: all artifacts from V2-1..V2-4.

- [ ] **Step 1: Copy identical code files**

```bash
cd /Users/hom/Documents/GitHub
cp safestat/examples/generate_manifest.py openstat/examples/generate_manifest.py
cp safestat/tests/test_examples_manifest.py openstat/tests/test_examples_manifest.py
```

- [ ] **Step 2: Run the migration + regenerate in openstat**

```bash
cd /Users/hom/Documents/GitHub/openstat
python /private/tmp/claude-501/-Users-hom-Documents-GitHub/9a73ebd5-168d-44d8-9606-75379bb75618/scratchpad/migrate_examples.py /Users/hom/Documents/GitHub/openstat
python examples/generate_manifest.py
python -m pytest tests/test_examples_manifest.py -q
```
Expected: migration + manifest succeed; tests green. NOTE: openstat has fewer modes (openstat = safestat minus features), so `moved+labeled` and mode count will be smaller — that is correct, not an error.

- [ ] **Step 3: Apply the same index.html modal edits to openstat**

Read the safestat modal change as reference: `git -C /Users/hom/Documents/GitHub/safestat show <V2-3 SHA> -- index.html`. Apply the same edits to `openstat/index.html`, locating anchors by surrounding code (openstat line numbers differ). If an anchor block differs materially from safestat's pre-edit state, STOP and report NEEDS_CONTEXT.

- [ ] **Step 4: Retire openstat web_examples + README + verify**

Repeat V2-4 in openstat. Then `node --check` the extracted inline script and `node --test tests/js/examples-menu.test.js`.

- [ ] **Step 5: Commit (do NOT merge/push to main)**

```bash
cd /Users/hom/Documents/GitHub/openstat
git add -A
git commit -m "feat: mode-scoped examples modal (sync from safestat)"
```

---

### Task V2-6: Manuell browser-verifisering (Hans)

Not a coding task — hand back to Hans with a checklist (controller runs the server):

- [ ] Each mode: open «Eksempler» → modal shows ONLY that mode's examples.
- [ ] micropython → flat list (no category pane), 4 examples, loads on click.
- [ ] microdata → category pane (~12 categories) + scripts, both scroll with many; loads on click.
- [ ] A mode with many flat examples (e.g. brython, 25) → scripts pane scrolls.
- [ ] No «Flere eksempler»-button remains; no cross-mode examples anywhere.
- [ ] Fallback: block/rename `examples/manifest.json`, reopen → modal shows the "kunne ikke laste"-hint, app otherwise fine.

---

## Self-Review

**Spec-dekning (v2):**
- Én modus-scoped modal → V2-3. ✓
- Fold web_examples → microdata → V2-2 Step 1(#2)/2. ✓
- Alle modi migrert → V2-2. ✓
- Generator leser `// Example:` → V2-1. ✓
- Adaptiv (flat/kategorisert) + scrollbar → V2-3 Step 3 (+ eksisterende CSS). ✓
- Fjern dropdown + «Flere eksempler»-knapp → V2-3 Step 4. ✓
- Bevar kuraterte labels → V2-2 Step 1(#1) skriver `# label:` fra knappetekst. ✓
- Lat henting, no-store, boot urørt → V2-3 Step 2. ✓
- Rydd web_examples + død CSS → V2-4. ✓
- To repoer, safestat leder → V2-5. ✓
- Grasiøs degradering → V2-3 Step 3(#6). ✓

**Plassholder-skann:** V2-3 Step 3 gir algoritme + eksakte integrasjonspunkter for å tilpasse eksisterende `initWebExamples` (ikke verbatim kode, fordi det er tilpasning av en stor eksisterende komponent implementeren leser i sin helhet); alle andre steg har konkrete kommandoer/kode. Ingen TBD/TODO.

**Type-konsistens:** `groupForMode` → `[{group, examples:[{file,label}]}]` konsumeres av modalen (V2-3) og `loadExampleFile(file,label,mode)` (v1) kalles med de feltene. Generatorens `label_for`-utvidelse (V2-1) er additiv. Migreringsskriptet skriver `# label:` som `label_for` leser. ✓
