# Lazy microdata-assets (safestat) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Samme lazy-lasting som openstat (plan `openstat/docs/superpowers/plans/2026-07-23-lazy-microdata-assets.md`, merget 2026-07-23): `variable_metadata.json` (640 KB), `mockdata_realism.py` og `static_source.py` hentes først når microdata-språket er i spill — restricted python/r/duckdb-brukere betaler ikke for microdata de ikke bruker.

**Architecture:** Som openstat: memoiserte `ensureMicrodataCatalog()` / `ensureMockdataModules(py)` / `ensureMicrodataAssets(py)` med gates på kjørestedene. **Tre safestat-forskjeller:**
1. **Microdata er førsteklasses/valgbar** (først i modusmenyen, init-default). Boot som lander i microdata/statx UTEN switch (lagret modus === init `'microdata'`) fyrer ikke `onActivate` — derfor eksplisitt prefetch etter `restoreEditorMode()` i tillegg til onActivate.
2. **Katalogen er rutingkritisk:** `maybeRunRemoteMicrodata()` (server-vs-lokal, ~9631) og forklar-vernet for serverkilder (~10529) returnerer stille «lokal» uten katalog. Gaten må derfor awaites FØR rutingbeslutningen i microdata-modus — prefetch alene er ikke nok.
3. **Ingen fallback-opprydding** (openstats Task 4 droppes): `|| modeRegistry.microdata` m.fl. er konsistente med at microdata er førsteklasses her.

`m2py.py` endres ikke (byte-identisk med openstat, verifisert med cmp). `mockdata_core.py` MÅ bli i kjernebooten (toppnivå-import i `m2py.py:1668` — openstat-avviket). `sw.js` trenger ingen endring (SWR-runtime-cache, ikke precache).

**Tech Stack:** Vanilla JS i `index.html`, Pyodide, node:test, pytest, browserverifisering via `python3 -m http.server`.

## Global Constraints

- Delte motorfiler (m2py.py, functions.py, m2py_translate.py, m2py_runtime/, mockdata_*.py, protect.py) røres ikke.
- Microdata-/statx-brukeres opplevelse skal være uendret: katalog prefetches ved modusaktivering OG boot-landing, og alle ruting-/kjørestier awaiter ensure før de leser `microdataCatalog`.
- safestat-modusen (`runSafeStatScript`, translator/remote) bruker ikke katalogen — ingen gate der.
- Linjenumre er fra 2026-07-23 — finn stedene via kodeankrene.

---

### Task 1: `ensureMicrodataCatalog()` + prefetch (onActivate + boot-landing)

**Files:** Modify `index.html` (~2905 IIFE; ~3668 microdata-entry; ~3698 statx-entry; etter `restoreEditorMode()`-IIFE ~4330)

- [ ] Erstatt `fetchAutocompleteData`-IIFE-en (~2905, uten `?v=` her i safestat) med samme `ensureMicrodataCatalog()` som openstat (med `?v=` cache-buster, konsistent med bootens `_cb`).
- [ ] `modeRegistry.microdata` (~3668): legg til `onActivate: function () { ensureMicrodataCatalog(); }`.
- [ ] `modeRegistry.statx` (~3698): prepend `ensureMicrodataCatalog();` i eksisterende onActivate.
- [ ] Etter `restoreEditorMode()`-IIFE-ens avsluttende `})();`: boot-landing-prefetch:

```js
    // Lazy katalog: boot som LANDER i microdata/statx uten switch (lagret
    // modus === init-verdien) fyrer ikke onActivate — prefetch eksplisitt så
    // autocomplete/variabelbrowser/serverruting har katalogen som før.
    if (activeEditorMode === 'microdata' || activeEditorMode === 'statx') ensureMicrodataCatalog();
```

- [ ] Verifiser: fersk side i python-modus → ingen `variable_metadata.json`-fetch; med `localStorage md_editor_mode='microdata'` → katalogen hentes ved boot.
- [ ] Commit.

### Task 2: Slank kjernebooten + `ensureMockdataModules(py)`

**Files:** Modify `index.html` (`_loadPyodideAndM2pyImpl` ~8937–9080; nye funksjoner etter den)

- [ ] Fetch-listen (~8940): fjern `variable_metadata.json`, `mockdata_realism.py`, `static_source.py`; behold `mockdata_core.py` (flytt til destrukturering `[m2pyResp, funcResp, coreResp, protectResp, notebookProseResp]`, legg `!coreResp.ok` i feilsjekken). Fjern metaResp→microdataCatalog-blokken (~8953–8959).
- [ ] Registreringsblokkene: behold mockdata_core-registrering FØR m2py (omskriv eksisterende blokk til kun core); slett realism- og static_source-registreringene.
- [ ] Etter `_loadPyodideAndM2pyImpl`: legg til `ensureMockdataModules(py)` (fetch+register realism + static_source, med egne `import sys, importlib.util`) og `ensureMicrodataAssets(py)` — identisk med openstat.
- [ ] Verifiser boot i python-modus (ingen realism/static_source/katalog-fetch; `print(1+1)` OK).
- [ ] Commit.

### Task 3: Gates på kjørestedene

**Files:** Modify `index.html` (hovedkjøring ~10124 og ~10295; statx ~8836; r-hybrid ~8612; forklar ~10529 og ~10819)

- [ ] **Ruting (kritisk):** før `if (activeEditorMode === 'microdata' && await maybeRunRemoteMicrodata(effectiveScript, _ctx)) return;` (~10124), sett inn:

```js
        // Lazy katalog: rutingen server-vs-lokal (maybeRunRemoteMicrodata) og
        // resten av microdata-stien LESER katalogen — den må være lastet FØR
        // beslutningen, ellers ruter serverkilde-scripts stille til lokal.
        if (activeEditorMode === 'microdata') {
          try { await ensureMicrodataCatalog(); }
          catch (e) { console.warn('microdata-katalog (ruting):', e); }
        }
```

- [ ] **Hovedpipeline:** flytt `catalogJson`/`catalogArg` (~10295–10298) NED til etter segment-use-blokken (`segments = _segUse.segments;`-avsnittet), med samme gate som openstat (`activeEditorMode === 'microdata' || segments.some(kind === 'microdata')` → `await ensureMicrodataAssets(py)`).
- [ ] **statx** (`runStatxScript` ~8836): `await ensureMicrodataAssets(py)` ubetinget etter `loadPyodideAndM2py()`.
- [ ] **r-hybrid** (~8612, inne i `if (microdataSegs.length > 0)`): `await ensureMicrodataAssets(py)` etter `if (!py) py = await loadPyodideAndM2py();`.
- [ ] **forklar-vernet** (~10529): før `if (activeEditorMode === 'microdata' && microdataCatalog && …)`-blokken i btnForklar-handleren (async), sett inn `if (activeEditorMode === 'microdata') { try { await ensureMicrodataCatalog(); } catch (e) {} }`.
- [ ] **forklar-init** (~10819): inne i `if (activeEditorMode !== 'r')`, før catalogJson: gate på `microdata || statx` → `await ensureMicrodataAssets(py)` (som openstat).
- [ ] Verifiser i browser (matrise under) + `node --test "tests/js/*.test.js"` + pytest.
- [ ] Commit.

### Task 4: Sluttverifisering

| # | Handling | Forventet |
|---|----------|-----------|
| 1 | Fersk side, python-modus, `print(1+1)` | Ingen katalog/realism/static_source-fetch; OK |
| 2 | Bytt til Microdata i menyen | Katalog hentes ved aktivering |
| 3 | Kjør require/import/tabulate i microdata-modus | realism+static_source hentes ved kjøring; ekte etiketter |
| 4 | Reload (lagret modus=microdata) | Katalog hentes ved boot-landing (uten switch) |
| 5 | statx med `// micro`-segment + summarize | OK |
| 6 | python-script med `# micro`-segment | Segment-gate henter assets; OK |
| 7 | duckdb `SELECT 1` | Ingen microdata-fetches |

- [ ] Kjør matrisen + begge testsuiter; diff skal kun omfatte `index.html` + denne planen.
- [ ] Commit (kun ved fikser).
