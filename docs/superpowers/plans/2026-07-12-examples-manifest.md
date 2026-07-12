# Manifest-drevne eksempler — Implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bygg eksempel-menyen fra et generert `examples/manifest.json` i stedet for hardkodede knapper i `index.html`, med kategorier via undermapper. Pilot på micropython.

**Architecture:** En Python-generator skanner `examples/<modus>/`-mapper (ett valgfritt undernivå = kategori) og skriver `examples/manifest.json`. En liten JS-modul (`js/examples-menu.js`) grupperer manifestet per modus (ren, testbar funksjon). `index.html` henter manifestet *lat* ved første åpning av Eksempler-menyen, bygger knappene, og bruker delegert klikk-håndtering. Speiler det eksisterende `web_examples/`-mønsteret.

**Tech Stack:** Python 3 (stdlib: `pathlib`, `re`, `json`), pytest (Python-tester), Node `node:test`/`node:assert` (JS-tester), vanlig ES5-JS i nettleseren.

## Global Constraints

- **To repoer:** safestat leder (bygg + valider her), synk til openstat etterpå (Task 6). Generator-skriptet og `js/examples-menu.js` er byte-identiske i begge; `examples/`-mappene og `manifest.json` skiller seg per repo.
- **Ingen bakoverkompat:** ingen brukere ennå — erstatt/flytt fritt, ingen migrasjonslag.
- **Ingen oppstartskostnad:** manifestet hentes KUN ved første åpning av menyen, aldri på boot-stien.
- **Ren JS i nettleseren:** ES5-stil (`var`, `function`), matcher `js/data-directives.js`/`js/i18n.js`. Ingen bundling.
- **Cache:** hent `examples/manifest.json` med `{cache: 'no-store'}` så nye eksempler alltid vises uten versjons-bump.
- **Label-kilde (prioritert):** `# label:`/`-- label:`/`// label:`-linje i de første 5 linjene → `#options.title = "..."` → avledet fra filnavn (strip `NN_`, `_`→mellomrom, kapitaliser).
- **Fil-baner i manifestet er relative til `examples/`** (f.eks. `micropython/01_pandas_basics.txt`), fordi klikk-handleren gjør `fetch(base + 'examples/' + file)`.
- **Pilot-omfang:** kun micropython migreres. Øvrige modi beholder sine hardkodede knapper til senere.

---

### Task 1: Generator `examples/generate_manifest.py` + tester

**Files:**
- Create: `examples/generate_manifest.py`
- Test: `tests/test_examples_manifest.py`

**Interfaces:**
- Produces:
  - `pretty(raw: str) -> str` — `"pandas_basics"` → `"Pandas basics"`.
  - `folder_label(name: str) -> str` — `"01_grunnleggende"` → `"01 — Grunnleggende"`; ellers `pretty(name)`.
  - `label_for(path: pathlib.Path) -> str` — leser label-linje / `#options.title` / faller tilbake til `pretty(stem uten NN_)`.
  - `build_manifest(root: pathlib.Path) -> dict` — `{ "<modus>": [ {"file": "<modus>/…txt", "label": str, "group": str|None}, … ] }`. Skanner kun undermapper av `root`; ignorerer flate filer i `root`, samt mapper som starter med `.`/`_` eller heter `tests`. Ett valgfritt undernivå: filer i `root/<modus>/<NN_kategori>/` får `group = folder_label("<NN_kategori>")`. Filer rett i `root/<modus>/` får `group = None`. Sortert: `group=None`-filer først (etter filnavn), deretter kategorier etter mappenavn, filer innen kategori etter filnavn.
  - `main() -> None` — skriver `<repo>/examples/manifest.json` med `build_manifest`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_examples_manifest.py`:

```python
import json
from pathlib import Path

import pytest

import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "generate_manifest",
    Path(__file__).resolve().parent.parent / "examples" / "generate_manifest.py",
)
gm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gm)


def test_pretty():
    assert gm.pretty("pandas_basics") == "Pandas basics"
    assert gm.pretty("") == ""


def test_folder_label():
    assert gm.folder_label("01_grunnleggende") == "01 — Grunnleggende"
    assert gm.folder_label("annet") == "Annet"


def test_label_from_label_line(tmp_path):
    p = tmp_path / "01_foo.txt"
    p.write_text("#options.mode = micropython\n# label: Min fine tittel\nimport x\n",
                 encoding="utf-8")
    assert gm.label_for(p) == "Min fine tittel"


def test_label_from_options_title(tmp_path):
    p = tmp_path / "01_foo.txt"
    p.write_text('#options.title = "Salgs-dashboard"\nimport x\n', encoding="utf-8")
    assert gm.label_for(p) == "Salgs-dashboard"


def test_label_fallback_to_filename(tmp_path):
    p = tmp_path / "03_csv_url.txt"
    p.write_text("import x\n", encoding="utf-8")
    assert gm.label_for(p) == "Csv url"


def test_build_manifest_flat_and_categorised(tmp_path):
    root = tmp_path / "examples"
    mp = root / "micropython"
    mp.mkdir(parents=True)
    (mp / "01_a.txt").write_text("# label: Eksempel A\n", encoding="utf-8")
    (mp / "02_b.txt").write_text("# label: Eksempel B\n", encoding="utf-8")
    cat = mp / "10_avansert"
    cat.mkdir()
    (cat / "01_c.txt").write_text("# label: Eksempel C\n", encoding="utf-8")
    # flat file in root and a _private dir must be ignored
    (root / "loose.txt").write_text("x\n", encoding="utf-8")
    (root / "__pycache__").mkdir()

    m = gm.build_manifest(root)

    assert list(m.keys()) == ["micropython"]
    assert m["micropython"] == [
        {"file": "micropython/01_a.txt", "label": "Eksempel A", "group": None},
        {"file": "micropython/02_b.txt", "label": "Eksempel B", "group": None},
        {"file": "micropython/10_avansert/01_c.txt", "label": "Eksempel C",
         "group": "10 — Avansert"},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/safestat && python -m pytest tests/test_examples_manifest.py -v`
Expected: FAIL — `FileNotFoundError`/`ModuleNotFoundError` for `examples/generate_manifest.py` (does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `examples/generate_manifest.py`:

```python
"""Regenerer examples/manifest.json fra mappestrukturen.

Én mappe per modus under examples/ (mappenavnet ER modus-nøkkelen). Ett
valgfritt undernivå (NN_kategori) blir en kategori-underoverskrift i menyen.
Labelen leses fra en `# label:`-linje (eller `-- label:` / `// label:`),
ellers `#options.title`, ellers avledet fra filnavnet.

Kjør fra repo-roten:
    python examples/generate_manifest.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # .../examples
NUM_RE = re.compile(r"^(\d+)_(.+)$")
LABEL_RE = re.compile(r"^\s*(?:#|--|//)\s*label:\s*(.+?)\s*$")
TITLE_RE = re.compile(r"""^\s*#options\.title\s*=\s*["'](.+?)["']\s*$""")
SKIP_DIRS = {"tests"}


def pretty(raw: str) -> str:
    words = raw.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else raw


def folder_label(name: str) -> str:
    m = NUM_RE.match(name)
    if not m:
        return pretty(name)
    return f"{m.group(1)} — {pretty(m.group(2))}"


def label_for(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as f:
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                m = LABEL_RE.match(line)
                if m:
                    return m.group(1)
                m = TITLE_RE.match(line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    stem = path.stem
    m = NUM_RE.match(stem)
    return pretty(m.group(2) if m else stem)


def _scripts_in(folder: Path, mode: str, group: str | None) -> list[dict]:
    out = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix == ".txt":
            rel = p.relative_to(ROOT).as_posix()
            out.append({"file": rel, "label": label_for(p), "group": group})
    return out


def build_manifest(root: Path = ROOT) -> dict:
    manifest: dict[str, list] = {}
    for mode_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        name = mode_dir.name
        if name.startswith(".") or name.startswith("_") or name in SKIP_DIRS:
            continue
        entries = _scripts_in(mode_dir, name, None)
        for sub in sorted(p for p in mode_dir.iterdir() if p.is_dir()):
            if sub.name.startswith(".") or sub.name.startswith("_"):
                continue
            entries.extend(_scripts_in(sub, name, folder_label(sub.name)))
        if entries:
            manifest[name] = entries
    return manifest


def main() -> None:
    manifest = build_manifest()
    out = ROOT / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    total = sum(len(v) for v in manifest.values())
    print(f"Skrev {out.name} ({len(manifest)} modi, {total} eksempler).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/hom/Documents/GitHub/safestat && python -m pytest tests/test_examples_manifest.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add examples/generate_manifest.py tests/test_examples_manifest.py
git commit -m "feat: examples manifest generator (folder scan, label extraction)"
```

---

### Task 2: Migrer micropython-eksemplene + generer manifest

**Files:**
- Move: `examples/mp01_pandas_basics.txt` → `examples/micropython/01_pandas_basics.txt`
- Move: `examples/mp02_plotly.txt` → `examples/micropython/02_plotly.txt`
- Move: `examples/mp03_dashboard.txt` → `examples/micropython/03_dashboard.txt`
- Move: `examples/mp04_csv_url.txt` → `examples/micropython/04_csv_url.txt`
- Create: `examples/manifest.json` (generert)

**Interfaces:**
- Consumes: `examples/generate_manifest.py` fra Task 1.
- Produces: `examples/manifest.json` med nøkkelen `"micropython"` og 4 oppføringer med baner `micropython/0X_*.txt`.

- [ ] **Step 1: Flytt filene med git mv**

```bash
cd /Users/hom/Documents/GitHub/safestat
mkdir -p examples/micropython
git mv examples/mp01_pandas_basics.txt examples/micropython/01_pandas_basics.txt
git mv examples/mp02_plotly.txt        examples/micropython/02_plotly.txt
git mv examples/mp03_dashboard.txt     examples/micropython/03_dashboard.txt
git mv examples/mp04_csv_url.txt       examples/micropython/04_csv_url.txt
```

- [ ] **Step 2: Legg til `# label:`-linje øverst i hver fil (bevar dagens kuraterte labels)**

Add as the FIRST line of each file (bruk Edit-verktøyet; behold resten av innholdet uendret):

- `examples/micropython/01_pandas_basics.txt`: `# label: pandas_mpy — basics`
- `examples/micropython/02_plotly.txt`: `# label: plotly_express_mpy — grafer`
- `examples/micropython/03_dashboard.txt`: `# label: Dashboard — salg`
- `examples/micropython/04_csv_url.txt`: `# label: Les en CSV fra en URL`

(Filer som starter med `#options.mode = micropython` beholder den linja; sett `# label:`-linja rett over eller under — label_for leser de første 5 linjene.)

- [ ] **Step 3: Generer manifestet**

Run: `cd /Users/hom/Documents/GitHub/safestat && python examples/generate_manifest.py`
Expected output: `Skrev manifest.json (1 modi, 4 eksempler).`

- [ ] **Step 4: Verifiser manifest-innholdet**

Run: `cd /Users/hom/Documents/GitHub/safestat && python -c "import json; m=json.load(open('examples/manifest.json')); assert list(m)==['micropython']; assert [e['file'] for e in m['micropython']]==['micropython/01_pandas_basics.txt','micropython/02_plotly.txt','micropython/03_dashboard.txt','micropython/04_csv_url.txt']; assert m['micropython'][0]['label']=='pandas_mpy — basics'; assert all(e['group'] is None for e in m['micropython']); print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add examples/micropython examples/manifest.json
git rm --cached examples/mp01_pandas_basics.txt examples/mp02_plotly.txt examples/mp03_dashboard.txt examples/mp04_csv_url.txt 2>/dev/null || true
git commit -m "feat: migrate micropython examples into examples/micropython/ + manifest"
```

---

### Task 3: JS-modul `js/examples-menu.js` (gruppering) + tester

**Files:**
- Create: `js/examples-menu.js`
- Test: `tests/js/examples-menu.test.js`

**Interfaces:**
- Produces: `globalThis.ExamplesMenu.groupForMode(manifest, mode) -> Array<{group: string|null, examples: Array<{file, label}>}>`. Filtrerer manifestet til `mode`, samler oppføringer i grupper i rekkefølgen de først dukker opp (`group === null` beholdes som egen ledende gruppe). Returnerer `[]` for ukjent/tom modus.

- [ ] **Step 1: Write the failing test**

Create `tests/js/examples-menu.test.js`:

```javascript
// tests/js/examples-menu.test.js — ren grupperingslogikk for eksempel-menyen.
const test = require('node:test');
const assert = require('node:assert');
require('../../js/examples-menu.js');
const EM = globalThis.ExamplesMenu;

const MANIFEST = {
  micropython: [
    { file: 'micropython/01_a.txt', label: 'A', group: null },
    { file: 'micropython/02_b.txt', label: 'B', group: null },
    { file: 'micropython/10_avansert/01_c.txt', label: 'C', group: '10 — Avansert' },
  ],
};

test('groupForMode: unknown mode gives empty array', () => {
  assert.deepEqual(EM.groupForMode(MANIFEST, 'r'), []);
  assert.deepEqual(EM.groupForMode({}, 'micropython'), []);
});

test('groupForMode: flat + categorised in first-appearance order', () => {
  assert.deepEqual(EM.groupForMode(MANIFEST, 'micropython'), [
    { group: null, examples: [
      { file: 'micropython/01_a.txt', label: 'A' },
      { file: 'micropython/02_b.txt', label: 'B' },
    ] },
    { group: '10 — Avansert', examples: [
      { file: 'micropython/10_avansert/01_c.txt', label: 'C' },
    ] },
  ]);
});

test('groupForMode: missing group treated as null', () => {
  const m = { micropython: [{ file: 'micropython/01_a.txt', label: 'A' }] };
  assert.deepEqual(EM.groupForMode(m, 'micropython'),
    [{ group: null, examples: [{ file: 'micropython/01_a.txt', label: 'A' }] }]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/safestat && node --test tests/js/examples-menu.test.js`
Expected: FAIL — `Cannot find module '../../js/examples-menu.js'`.

- [ ] **Step 3: Write minimal implementation**

Create `js/examples-menu.js`:

```javascript
// js/examples-menu.js — ren, testbar grupperingslogikk for eksempel-menyen.
// DOM-render bor i index.html; denne modulen kjenner ingen DOM.
(function (global) {
  'use strict';

  function groupForMode(manifest, mode) {
    var list = (manifest && manifest[mode]) || [];
    var groups = [];
    var byKey = {};
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      var g = (e.group === undefined) ? null : e.group;
      var key = (g === null) ? ' null' : g;
      if (!byKey[key]) {
        byKey[key] = { group: g, examples: [] };
        groups.push(byKey[key]);
      }
      byKey[key].examples.push({ file: e.file, label: e.label });
    }
    return groups;
  }

  global.ExamplesMenu = { groupForMode: groupForMode };
})(typeof globalThis !== 'undefined' ? globalThis : this);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/hom/Documents/GitHub/safestat && node --test tests/js/examples-menu.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add js/examples-menu.js tests/js/examples-menu.test.js
git commit -m "feat: examples-menu grouping module + tests"
```

---

### Task 4: Wire `index.html` — lat henting, render, delegert klikk

**Files:**
- Modify: `index.html` — legg til script-include (etter `js/notebook-links.js`, ~linje 825); erstatt per-knapp-klikk (linje 1899–1933) med delegering + render; oppdater de 4 statiske micropython-knappene (linje 114–117) til nye baner.

**Interfaces:**
- Consumes: `globalThis.ExamplesMenu.groupForMode` (Task 3), `examples/manifest.json` (Task 2), `window.applyTranslations(root)` (js/i18n.js), eksisterende `switchEditorMode`, `editorContent`, `activeEditorMode`, `scriptInput`, `scriptName`, `updateExamplesVisibility`, `dropdown`, `examplesDropdown`.

- [ ] **Step 1: Legg til script-include for js/examples-menu.js**

Modify `index.html` — legg til linja rett etter `<script src="js/notebook-links.js"></script>` (~linje 825):

```html
  <script src="js/examples-menu.js"></script>
```

- [ ] **Step 2: Oppdater de 4 statiske micropython-knappene til nye baner (sikkerhetsnett)**

Modify `index.html` linje 114–117 — endre KUN `data-example`-verdiene til de nye banene (behold labels/attributter):

```html
              <button type="button" data-example="micropython/01_pandas_basics.txt" data-mode="micropython" data-i18n>pandas_mpy &mdash; basics</button>
              <button type="button" data-example="micropython/02_plotly.txt" data-mode="micropython" data-i18n>plotly_express_mpy &mdash; grafer</button>
              <button type="button" data-example="micropython/03_dashboard.txt" data-mode="micropython" data-i18n>Dashboard &mdash; salg</button>
              <button type="button" data-example="micropython/04_csv_url.txt" data-mode="micropython" data-i18n>Les en CSV fra en URL</button>
```

- [ ] **Step 3: Erstatt per-knapp-klikkhandleren med delegering + render**

Modify `index.html` — erstatt HELE blokken `document.querySelectorAll('.examples-dropdown button[data-example]').forEach(function(btn) { … });` (linje 1899–1933) med følgende. Det (a) trekker klikk-kroppen ut i `loadExampleFile`, (b) delegerer klikk på `examplesDropdown`, (c) legger til lat manifest-henting og render:

```javascript
      function loadExampleFile(file, title, mode) {
        var base = window.location.href.replace(/[^/]+$/, '');
        fetch(base + 'examples/' + file).then(function(r) {
          if (!r.ok) throw new Error(r.status);
          return r.text();
        }).then(function(text) {
          if (mode && (mode === 'microdata' || mode === 'python' || mode === 'r' || mode === 'statx' || mode === 'duckdb' || mode === 'brython' || mode === 'micropython')
              && typeof switchEditorMode === 'function'
              && typeof activeEditorMode !== 'undefined') {
            if (typeof editorContent !== 'undefined') editorContent[mode] = text;
            if (mode !== activeEditorMode) switchEditorMode(mode);
          }
          scriptInput.value = text;
          scriptName.value = title;
          if (window.mdClearOutput) window.mdClearOutput();
          if (window.mdGithubClearCurrent) window.mdGithubClearCurrent();
          if (window.updateLineNumbers) window.updateLineNumbers();
          if (examplesDropdown) examplesDropdown.classList.remove('open');
          dropdown.classList.remove('open');
          scriptInput.focus();
          scriptInput.selectionStart = scriptInput.selectionEnd = 0;
        }).catch(function(err) {
          if (window.location.protocol === 'file:') {
            alert(t('Filen er åpnet direkte i nettleseren (file://). Start en lokal webserver og åpne via http://localhost for å laste eksempler.\n\nEks: åpne terminal i m2py-mappen og kjør:\npython -m http.server 8000\n\nÅpne deretter http://localhost:8000/microdata_runner.html'));
          } else {
            alert(t('Kunne ikke laste eksempel: {file}\nFeil: {msg}\n\nSjekk at examples-mappen ligger i samme mappe som microdata_runner.html og at serveren har tilgang til den.', { file: file, msg: err && err.message ? err.message : String(err) }));
          }
        });
      }

      // Delegert klikk: virker for både statiske og dynamisk bygde knapper.
      if (examplesDropdown) {
        examplesDropdown.addEventListener('click', function(e) {
          var btn = e.target && e.target.closest ? e.target.closest('button[data-example]') : null;
          if (!btn || !examplesDropdown.contains(btn)) return;
          loadExampleFile(btn.getAttribute('data-example'),
                          btn.textContent.trim(),
                          btn.getAttribute('data-mode'));
        });
      }

      // Lat henting av examples/manifest.json ved FØRSTE åpning av menyen.
      // Bygger seksjonene for modi som finnes i manifestet; modi som mangler
      // beholder sine statiske knapper (inkrementell migrering). no-store så
      // nye eksempler alltid vises.
      var __examplesRendered = false;
      function renderExamplesFromManifest(manifest) {
        if (!examplesDropdown || !global_ExamplesMenu()) return;
        Object.keys(manifest).forEach(function(mode) {
          var sec = examplesDropdown.querySelector(
            '.examples-section[data-section-mode="' + mode + '"]');
          if (!sec) return;
          sec.innerHTML = '';
          global_ExamplesMenu().groupForMode(manifest, mode).forEach(function(grp) {
            if (grp.group) {
              var h = document.createElement('div');
              h.className = 'examples-dropdown-title';
              h.textContent = grp.group;
              sec.appendChild(h);
            }
            grp.examples.forEach(function(ex) {
              var b = document.createElement('button');
              b.type = 'button';
              b.setAttribute('data-example', ex.file);
              b.setAttribute('data-mode', mode);
              b.setAttribute('data-i18n', '');
              b.textContent = ex.label;
              sec.appendChild(b);
            });
          });
          if (window.applyTranslations) window.applyTranslations(sec);
        });
      }
      function global_ExamplesMenu() {
        return (typeof ExamplesMenu !== 'undefined') ? ExamplesMenu
             : (typeof globalThis !== 'undefined' ? globalThis.ExamplesMenu : null);
      }
      function ensureExamplesRendered() {
        if (__examplesRendered) return;
        var base = window.location.href.replace(/[^/]+$/, '');
        fetch(base + 'examples/manifest.json', { cache: 'no-store' })
          .then(function(r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function(manifest) {
            __examplesRendered = true;      // kun ved suksess → tillat retry ved feil
            renderExamplesFromManifest(manifest);
            updateExamplesVisibility();     // hold synlighet i takt med aktiv modus
          })
          .catch(function(err) {
            console.warn('examples manifest load failed (statiske knapper beholdes):', err);
          });
      }
```

- [ ] **Step 4: Kall `ensureExamplesRendered()` når menyen åpnes**

Modify `index.html` — i `menuExamplesBtn`-klikkhandleren (linje 1889–1897), legg til kallet rett etter `e.stopPropagation();`:

```javascript
      document.getElementById('menuExamplesBtn').addEventListener('click', function(e) {
        e.stopPropagation();
        ensureExamplesRendered();
        if (examplesDropdown) {
          updateExamplesVisibility();
          examplesDropdown.classList.toggle('open');
        }
        themeDropdown.classList.remove('open');
        exportDropdown.classList.remove('open');
      });
```

- [ ] **Step 5: Manuell verifisering i nettleser**

```bash
cd /Users/hom/Documents/GitHub/safestat && python -m http.server 8000
```
Åpne `http://localhost:8000/index.html` (eller `microdata_runner.html` hvis det er inngangen). Utfør:
1. Bytt til MicroPython-modus. Åpne Eksempler-menyen. Forventet: de 4 micropython-eksemplene vises (bygd fra manifestet).
2. Klikk «Les en CSV fra en URL». Forventet: scriptet lastes i editoren, modus blir micropython, tittel-feltet viser labelen.
3. I DevTools → Network: bekreft ett kall til `examples/manifest.json` ved første menyåpning, og INGEN slikt kall ved sидeinnlasting før menyen åpnes.
4. Fallback: i DevTools blokker `manifest.json` (eller døp den midlertidig om), last på nytt, åpne menyen. Forventet: de 4 statiske knappene vises fortsatt (med nye baner) og virker; en `console.warn` logges.

- [ ] **Step 6: Kjør JS- og Python-testene på nytt (ingen regresjon)**

Run: `cd /Users/hom/Documents/GitHub/safestat && node --test tests/js/examples-menu.test.js && python -m pytest tests/test_examples_manifest.py -q`
Expected: alle grønne.

- [ ] **Step 7: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add index.html
git commit -m "feat: render examples menu from manifest (lazy fetch, delegated clicks)"
```

---

### Task 5: Wire generering inn i synk-arbeidsflyten (dokumentér)

**Files:**
- Modify: `examples/generate_manifest.py` (kun toppkommentar hvis nødvendig) — ingen kodeendring; dette er et dokumentasjons-/prosess-steg.
- Modify: `README.md` (eller nærmeste utvikler-notat) — legg til én linje.

- [ ] **Step 1: Dokumentér regenerering**

Add to `README.md` under et passende «Utvikling»/«Eksempler»-avsnitt (eller opprett et kort avsnitt hvis ingen finnes):

```markdown
### Eksempler
Eksempler ligger i `examples/<modus>/` (ett valgfritt undernivå = kategori).
Legg til/fjern en `.txt`-fil og kjør deretter:

    python examples/generate_manifest.py

for å oppdatere `examples/manifest.json`. `index.html` bygger Eksempler-menyen
fra den fila (henter den ved første åpning). Label leses fra en `# label:`-linje
i fila (ellers `#options.title`, ellers filnavnet).
```

- [ ] **Step 2: Commit**

```bash
cd /Users/hom/Documents/GitHub/safestat
git add README.md
git commit -m "docs: how to add examples (regenerate manifest)"
```

---

### Task 6: Synk til openstat + push begge

**Files:**
- Mirror i `/Users/hom/Documents/GitHub/openstat/`: `examples/generate_manifest.py`, `js/examples-menu.js`, `tests/test_examples_manifest.py`, `tests/js/examples-menu.test.js`, flyttede `examples/micropython/*.txt`, generert `examples/manifest.json`, `index.html`-endringene, README-linja.

**Interfaces:**
- Consumes: alle artefaktene fra Task 1–5 (byte-identisk kode; repo-spesifikke `examples/`-filer).

- [ ] **Step 1: Kopier de identiske kodefilene til openstat**

```bash
cd /Users/hom/Documents/GitHub
cp safestat/examples/generate_manifest.py openstat/examples/generate_manifest.py
cp safestat/js/examples-menu.js           openstat/js/examples-menu.js
cp safestat/tests/test_examples_manifest.py openstat/tests/test_examples_manifest.py
mkdir -p openstat/tests/js
cp safestat/tests/js/examples-menu.test.js  openstat/tests/js/examples-menu.test.js
```

- [ ] **Step 2: Flytt openstat sine micropython-eksempler + legg til labels**

```bash
cd /Users/hom/Documents/GitHub/openstat
mkdir -p examples/micropython
git mv examples/mp01_pandas_basics.txt examples/micropython/01_pandas_basics.txt
git mv examples/mp02_plotly.txt        examples/micropython/02_plotly.txt
git mv examples/mp03_dashboard.txt     examples/micropython/03_dashboard.txt
git mv examples/mp04_csv_url.txt       examples/micropython/04_csv_url.txt
```
Legg til samme `# label:`-linjer som i Task 2 Step 2 (openstat har de samme 4 filene).

- [ ] **Step 3: Generer manifest og kjør testene i openstat**

Run:
```bash
cd /Users/hom/Documents/GitHub/openstat
python examples/generate_manifest.py
python -m pytest tests/test_examples_manifest.py -q
node --test tests/js/examples-menu.test.js
```
Expected: `Skrev manifest.json (1 modi, 4 eksempler).` og grønne tester.

- [ ] **Step 4: Gjør de samme index.html-endringene i openstat**

Gjenta Task 4 Step 1–4 i `openstat/index.html`. NB: linjenumrene skiller seg fra safestat — finn ankrene med:
```bash
cd /Users/hom/Documents/GitHub/openstat
grep -n 'js/notebook-links.js\|data-mode="micropython"\|button\[data-example\]\|menuExamplesBtn' index.html
```
Bruk samme kodeblokker som i Task 4 (identiske). Verifiser manuelt (Task 4 Step 5) mot `http://localhost:8001`.

- [ ] **Step 5: README-linje i openstat**

Legg til samme avsnitt som Task 5 Step 1 i `openstat/README.md`.

- [ ] **Step 6: Commit og push begge repoer**

```bash
cd /Users/hom/Documents/GitHub/safestat && git push
cd /Users/hom/Documents/GitHub/openstat && git add -A && \
  git commit -m "feat: manifest-driven examples menu (sync from safestat)" && git push
```
Bekreft live: `https://hmelberg.github.io/safestat/` og `https://hmelberg.github.io/openstat/`.

---

## Self-Review

**Spec-dekning:**
- Mappe per modus + ett undernivå → Task 1 (`build_manifest`), Task 2 (micropython-mappe). ✓
- Generator + label-kilde-prioritering → Task 1. ✓
- Kategorier vist til bruker (underoverskrifter) → Task 1 (`group`), Task 3 (`groupForMode`), Task 4 Step 3 (`examples-dropdown-title`-render). ✓
- Lat henting, ingen oppstartskostnad → Task 4 Step 4 (`ensureExamplesRendered` kun ved menyåpning). ✓
- Delegert klikk → Task 4 Step 3. ✓
- Grasiøs degradering (statiske knapper beholdes ved feil) → Task 4 Step 2 (oppdaterte baner) + Step 3 (`.catch` beholder statiske). ✓
- i18n-pass over dynamiske knapper → Task 4 Step 3 (`applyTranslations`). ✓
- Regenerering i arbeidsflyt → Task 5. ✓
- To repoer, safestat leder → Task 6. ✓
- Bevar kuraterte labels → Task 2 Step 2. ✓

**Plassholder-skann:** ingen TBD/TODO; all kode er konkret. ✓

**Type-konsistens:** `build_manifest` gir `{mode: [{file,label,group}]}`; `groupForMode` konsumerer nøyaktig det og gir `[{group, examples:[{file,label}]}]`; render leser `grp.group`/`grp.examples`/`ex.file`/`ex.label`/`mode`. `label_for`/`folder_label`/`pretty` konsistente på tvers av Task 1-test og -impl. ✓
