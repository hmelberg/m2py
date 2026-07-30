# Fire spesialiserte hjelpesider — implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erstatte fire nær-identiske hjelpesider med fire spesialiserte, der hver leder med det appen faktisk er, med kjørte eksempler og en synk-sjekk som hindrer at de driver fra hverandre igjen.

**Architecture:** Fire-lags skjelett i alle åtte filer (`hjelp.html` + `hjelp.en.html` × 4 repoer). Lag 0 (hero) og lag 1 (kjernen) er repo-spesifikke; lag 2 (verktøy) og lag 3 (referanse) holdes byte-identiske mellom repoene, avgrenset av `<!-- SYNC:START navn -->`-markører og håndhevet av `scripts/hjelp_sync_check.sh`. Alle kodeeksempler produseres av et kjørbart skript som skriver output til fil, og en pytest sammenligner det som står i HTML-en mot den faktiske outputen.

**Tech Stack:** Rå HTML + CSS + vanilla JS (ingen byggesteg, sidene skal virke offline). pytest med `html.parser` fra stdlib for strukturtester. `safepy` fra `vendor/safepy.zip` for strict-eksempler. `netlify dev` for nettleseravhengige eksempler.

**Spec:** `docs/superpowers/specs/2026-07-30-hjelpesider-design.md`

## Global Constraints

- **Ingen nye avhengigheter.** `bs4` er ikke installert og skal ikke installeres — bruk `html.parser` fra stdlib. Ingen byggesteg, ingen CDN-referanser; sidene skal virke offline.
- **Behold eksisterende CSS-variabler og klasser:** `--accent`, `--accent-light`, `--text`, `--text-muted`, `--bg`, `--bg-card`, `--bg-code`, `--border`, `--radius`, `--shadow`, `--tag-micro`, `--tag-py`, `--tag-r`, og klassene `doc-table`, `callout`, `callout tip`, `card`, `card-grid`, `card-title`, `card-body`, `badge`, `badge-py`, `badge-r`, `badge-micro`, `page`, `nav-logo`, `nav-section`, `doc-header`, `lead`.
- **Dark mode via `@media (prefers-color-scheme: dark)`** må fortsette å virke i alle åtte filer.
- **Sidemenyen er 220 px, `position: sticky`.** Ikke endre bredden.
- **Identitet per repo** — eksakte strenger, ingen avvik:

  | Repo | `<title>` no | `<title>` en | `<h1>` | `nav-logo` |
  |---|---|---|---|---|
  | openstat | `OpenStat – Dokumentasjon` | `OpenStat – Documentation` | `OpenStat` | `OpenStat` |
  | safestat | `SafeStat – Dokumentasjon` | `SafeStat – Documentation` | `SafeStat` | `SafeStat` |
  | microdata | `Microdata – Dokumentasjon` | `Microdata – Documentation` | `Microdata` | `Microdata` |
  | askstat | `AskStat – Dokumentasjon` | `AskStat – Documentation` | `AskStat` | `AskStat` |

- **Ledesetninger** (`<p class="lead">`), norsk:
  - openstat: `Sju analysemotorer i nettleseren, samme datasett.`
  - safestat: `Analyser beskyttede data uten at dataene forlater det trygge.`
  - microdata: `Emulator av microdata.no — skriv og kjør microdata-kode.`
  - askstat: `Spør på norsk, få kode og svar fra offentlig statistikk.`
- **Strengen `Microdata Script Runner` skal ikke finnes i noen av de åtte filene** når planen er ferdig.
- **Ingen oppdiktede resultattall.** Hvert `<pre class="result">` er enten generert av `docs/hjelp_examples/run_examples.py`, eller bærer klassen `result illustration` og teksten «illustrasjon» synlig for leseren.
- **Slett den gamle scrollspyen i hvert repo.** Alle fire `hjelp.html` har fra før et `<script>` nederst som toggler klassen `active` basert på `scrollY >= offsetTop - 60`, og linje ~67 styler `nav a.active` med samme aksentfarge som den nye `nav a.nav-active`. Lar du den stå, kjører to scrollspyer med ulik terskel samtidig og fremhever ofte **to** navlenker. Blokken ligger utenfor SYNC-markørene, så den blir ikke ryddet av å kopiere fellesdelen — hvert repo må slette den selv. `tests/test_hjelp.py` har en test som håndhever det.
- **Ikke bryt linjer inne i en `<pre class="result">`.** Teksten sammenlignes ordrett mot harnessens outputfil, så en linjedeling for lesbarhetens skyld gjør at testen feiler. `.example-result pre` har `overflow-x: auto` — lange linjer ruller, og det er meningen.
- **Resultatverdiene i denne planen er målt 2026-07-30** mot `vendor/safepy.zip` slik den var da. Avviker en outputfil fra planen, er **filen** som har rett — planens verdier er en hjelp, ikke en autoritet.
- **Rekkefølge er bindende:** safestat (Task 1–10) → openstat (11–12) → askstat (13–14) → microdata (15–16) → sluttverifisering (17). Fellesseksjonene kopieres *fra safestat*, aldri omvendt.
- **Python-kommando per repo.** Bare safestat har `.venv`. De tre søsknene bruker systemets `python3`, som har pandas, numpy og pytest (verifisert 2026-07-30):

  | Repo | Kommando |
  |---|---|
  | safestat | `.venv/bin/python` |
  | openstat, askstat, microdata | `python3` |

  Står det `.venv/bin/python` i en task som gjelder et søskenrepo, er det en feil i planen — bruk `python3`.
- **De fire repoene må ligge side om side** i samme foreldermappe. `scripts/hjelp_sync_check.sh` slår opp søsknene relativt til sin egen plassering (`$HERE/..`, overstyrbart med `HJELP_SYNC_ROOT`), og taskene bruker stier som `../openstat`. Et git-worktree som flytter et repo ut av `~/Documents/GitHub/` brekker begge.

---

## Filstruktur

**Nye filer (bor i safestat, kopieres til søsknene der det er angitt):**

| Fil | Ansvar | Kopieres til søsken |
|---|---|---|
| `docs/hjelp_examples/run_examples.py` | Kjører alle strict-eksempler mot safepy, skriver `output/*.txt` | Nei — safestat-spesifikk |
| `docs/hjelp_examples/output/*.txt` | Generert, sjekket inn. Én fil per eksempel-id | Nei |
| `tests/test_hjelp.py` | Strukturtester: identitet, seksjons-id-er, forbudte strenger, resultat-samsvar | Ja, med repo-spesifikke forventninger |
| `scripts/hjelp_sync_check.sh` | Differ SYNC-blokker mot søskenrepoene, exit 1 ved avvik | Ja |

**Endrede filer:**

| Fil | Endring |
|---|---|
| `hjelp.html`, `hjelp.en.html` (× 4 repoer) | Full omskriving til fire-lags struktur |
| `askstat/README.md` | Navn og førsteavsnitt: OpenStat → AskStat |

**SYNC-blokknavn** (identiske i alle fire repoer, definerer hva synk-sjekken dekker):

`felles-css`, `felles-js`, `felles-editor`, `felles-sidebar`, `felles-lagre`, `felles-forklar`, `felles-widgets`, `felles-ai`, `felles-eksempler`, `felles-referanse-snarveier`, `felles-referanse-tab`

Lag 0, modustabellen og lag 1 er **ikke** i SYNC-blokker og er dermed unntatt sjekken.

---

## Task 1: Eksempel-harness for strict-eksempler

**Files:**
- Create: `docs/hjelp_examples/run_examples.py`
- Create: `docs/hjelp_examples/README.md`
- Test: `tests/test_hjelp_examples.py`

**Interfaces:**
- Produces: `docs/hjelp_examples/output/<id>.txt` for hver `id` i `EXAMPLES`. Senere tasks limer innholdet i disse filene inn i `<pre class="result">`-blokker og `tests/test_hjelp.py` sammenligner.
- Produces: `EXAMPLES: list[dict]` med nøklene `id: str`, `dialect: str`, `code: str`, `expect_ok: bool`.
- Produces: `run_one(example: dict, df) -> str` — returnerer den ferdige tekstblokken som skal limes inn.
- Produces: `build_frame() -> pandas.DataFrame` — deterministisk demoramme, `np.random.default_rng(42)`, n=5000, kolonnene `kjonn` (1/2), `alder` (20–69), `lonn` (float).

Datarammen må være deterministisk, ellers endrer resultattallene seg hver kjøring og synk-sjekken bråker uten grunn.

- [ ] **Step 1: Skriv den feilende testen**

Opprett `tests/test_hjelp_examples.py`:

```python
"""Eksempel-harness for hjelpesidene: resultatblokkene skal være genererte,
ikke skrevet for hånd. Testen låser at harnessen er deterministisk — samme
kode inn gir samme tekst ut, hver gang."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = REPO / "docs" / "hjelp_examples" / "run_examples.py"
OUTDIR = REPO / "docs" / "hjelp_examples" / "output"


def test_harness_er_deterministisk():
    """To kjøringer på rad gir identisk output for hvert eksempel."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    df1 = run_examples.build_frame()
    df2 = run_examples.build_frame()
    for ex in run_examples.EXAMPLES:
        a = run_examples.run_one(ex, df1)
        b = run_examples.run_one(ex, df2)
        assert a == b, f"{ex['id']} er ikke deterministisk"


def test_avvist_eksempel_gir_ekte_feilmelding():
    """Et eksempel merket expect_ok=False skal produsere safepy sin faktiske
    feilmelding — ikke en tom blokk og ikke en oppdiktet tekst."""
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    df = run_examples.build_frame()
    ex = next(e for e in run_examples.EXAMPLES if e["id"] == "strict-py-avvist-head")
    out = run_examples.run_one(ex, df)
    assert "'head' is not allowed" in out
    assert "reveal individual rows" in out


def test_harness_skriver_alle_outputfiler():
    """Kjør harnessen og se at hver EXAMPLES-id fikk sin fil."""
    subprocess.run([sys.executable, str(HARNESS)], cwd=REPO, check=True)
    sys.path.insert(0, str(HARNESS.parent))
    import run_examples

    for ex in run_examples.EXAMPLES:
        f = OUTDIR / f"{ex['id']}.txt"
        assert f.exists(), f"mangler output for {ex['id']}"
        assert f.read_text(encoding="utf-8").strip(), f"tom output for {ex['id']}"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp_examples.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'run_examples'`

- [ ] **Step 3: Skriv harnessen**

Opprett `docs/hjelp_examples/run_examples.py`:

```python
#!/usr/bin/env python3
"""Kjører hjelpesidenes strict-eksempler og skriver resultatet til output/.

Hjelpesidene skal vise faktiske resultater, ikke plausible. Dette skriptet er
kilden: hvert eksempel kjøres mot safepy, og teksten det skriver limes rett inn
i <pre class="result"> i hjelp.html. tests/test_hjelp.py sammenligner de to, så
et eksempel som slutter å stemme blir fanget.

Kjør:  .venv/bin/python docs/hjelp_examples/run_examples.py
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from tempfile import mkdtemp

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUTDIR = HERE / "output"


def _load_safepy():
    """safepy bor i vendor/safepy.zip — pakk ut til en temp-mappe og importer."""
    dest = mkdtemp(prefix="safepy-hjelp-")
    with zipfile.ZipFile(REPO / "vendor" / "safepy.zip") as z:
        z.extractall(dest)
    sys.path.insert(0, dest)
    import safepy
    return safepy


def build_frame():
    """Deterministisk demoramme. Frøet er låst — endrer du det, endres hvert
    resultattall i hjelpesidene."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 5000
    return pd.DataFrame({
        "kjonn": rng.choice([1, 2], n),
        "alder": rng.integers(20, 70, n),
        "lonn": rng.normal(520000, 130000, n).round(0),
    })


EXAMPLES = [
    {
        "id": "strict-py-gruppegjennomsnitt",
        "dialect": "pandas",
        "expect_ok": True,
        "code": 'df.groupby("kjonn")["lonn"].mean()',
    },
    {
        "id": "strict-py-avvist-head",
        "dialect": "pandas",
        "expect_ok": False,
        "code": "df.head()",
    },
    {
        "id": "strict-py-avvist-posisjon",
        "dialect": "pandas",
        "expect_ok": False,
        "code": 'df["lonn"][0]',
    },
    {
        "id": "strict-py-avvist-import",
        "dialect": "pandas",
        "expect_ok": False,
        "code": 'import os\ndf.groupby("kjonn")["lonn"].mean()',
    },
    {
        "id": "strict-r-summarise",
        "dialect": "r",
        "expect_ok": True,
        "code": "df |> group_by(kjonn) |> summarise(m = mean(lonn), n = n())",
    },
    {
        "id": "strict-r-avvist-head",
        "dialect": "r",
        "expect_ok": False,
        "code": "head(df)",
    },
    {
        "id": "strict-sql-gruppe",
        "dialect": "duckdb",
        "expect_ok": True,
        # ORDER BY kjonn er IKKE kosmetikk: uten den svinger DuckDB sin
        # radrekkefølge tilfeldig mellom kjøringer i samme prosess (målt ~35/65
        # over 20 kall, 2026-07-30), og både harness-testen og hjelpesidenes
        # resultatsammenligning blir flaky. ORDER BY på et aggregat er lovlig i
        # strict SQL — verifisert.
        "code": ("SELECT kjonn, avg(lonn) AS m, count(*) AS n "
                 "FROM df GROUP BY kjonn ORDER BY kjonn"),
    },
]


def _format_payload(payload) -> str:
    """Gjør safepy sin payload til noe en leser forstår."""
    if not isinstance(payload, dict):
        return str(payload)
    t = payload.get("type")
    if t == "series":
        lines = [f"{payload.get('index_name', '')}  {payload.get('name', '')}"]
        for k, v in zip(payload["index"], payload["values"]):
            lines.append(f"{k}  {v:,.0f}".replace(",", " "))
        return "\n".join(lines)
    if t == "frame":
        cols = payload["columns"]
        lines = ["  ".join([""] + list(cols))]
        for idx, row in zip(payload["index"], payload["data"]):
            cells = [f"{v:,.0f}".replace(",", " ") if isinstance(v, float) else str(v)
                     for v in row]
            lines.append("  ".join([str(idx)] + cells))
        return "\n".join(lines)
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def run_one(example: dict, df) -> str:
    """Kjør ett eksempel og returner tekstblokken som skal limes inn."""
    safepy = _load_safepy()
    r = safepy.run(example["code"], {"df": df}, "protected",
                   profile="strict", dialect=example["dialect"])
    if r.ok != example["expect_ok"]:
        raise AssertionError(
            f"{example['id']}: forventet ok={example['expect_ok']}, fikk ok={r.ok} "
            f"({r.error!r})")
    if r.ok:
        return _format_payload(r.payload)
    err = r.error
    msg = err.get("message") if isinstance(err, dict) else str(err)
    kind = err.get("kind") if isinstance(err, dict) else "error"
    return f"Avvist ({kind}): {msg}"


def main() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df = build_frame()
    for ex in EXAMPLES:
        text = run_one(ex, df)
        (OUTDIR / f"{ex['id']}.txt").write_text(text + "\n", encoding="utf-8")
        print(f"  {ex['id']}: {len(text)} tegn")
    print(f"Skrev {len(EXAMPLES)} eksempler til {OUTDIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Skriv README for mappa**

Opprett `docs/hjelp_examples/README.md`:

```markdown
# Hjelpesidenes eksempler

Resultatblokkene i `hjelp.html` er **generert**, ikke skrevet for hånd.

    .venv/bin/python docs/hjelp_examples/run_examples.py

skriver én fil per eksempel til `output/`. Innholdet limes inn i
`<pre class="result">` i hjelp.html, og `tests/test_hjelp.py` sammenligner de to.

Endrer du et eksempel: rediger `EXAMPLES` i `run_examples.py`, kjør skriptet,
lim inn på nytt, kjør testene. Frøet (`default_rng(42)`) er låst — endrer du
det, endres hvert resultattall på hjelpesidene.

Eksempler som ikke kan kjøres her — ask-svar, jamovi-dialoger, federerte
spørringer — merkes i HTML-en med `class="result illustration"` og ordet
«illustrasjon» synlig for leseren. De skal aldri se ut som kjørt output.
```

- [ ] **Step 5: Kjør harnessen og testene**

Run:
```bash
.venv/bin/python docs/hjelp_examples/run_examples.py
.venv/bin/python -m pytest tests/test_hjelp_examples.py -v
```
Expected: harnessen skriver 7 filer; alle tre tester PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/hjelp_examples/ tests/test_hjelp_examples.py
git commit -m "docs(hjelp): eksempel-harness som genererer faktiske resultater

Hjelpesidene skal vise ekte output. Harnessen kjører hvert strict-eksempel
mot safepy og skriver resultatet til fil, så HTML-en kan sammenlignes mot
noe som faktisk er kjørt."
```

---

## Task 2: Fellesskikt for layout — scrollspy, nav-filter, kopier-knapp, todelt eksempelblokk

**Files:**
- Modify: `hjelp.html` (CSS-blokken i `<head>`, og en ny `<script>` før `</body>`)
- Test: `tests/js/test_hjelp_ui.mjs`

**Interfaces:**
- Consumes: ingenting fra Task 1.
- Produces: CSS-klassene `example`, `example-code`, `example-result`, `result`, `result illustration`, `copy-btn`, `nav-filter`, `nav-link-hidden`, `nav-active`, `overview` — brukt av hver senere task som skriver innhold.
- Produces: globalt `window.HjelpUI = { initScrollspy, initNavFilter, initCopyButtons }`, hver kallbar uten argumenter og idempotent.
- Produces: `HjelpUI.matchNav(query: string, labels: string[]) -> number[]` — ren funksjon, returnerer indeksene som skal vises. Node-testet.

Den rene funksjonen `matchNav` skilles ut nettopp for å kunne node-testes uten DOM, i tråd med mønsteret i `js/cells.js`.

- [ ] **Step 1: Skriv den feilende testen**

Opprett `tests/js/test_hjelp_ui.mjs`:

```javascript
/* Nav-filteret i hjelpesidene: ren funksjon, node-testet uten DOM.
   Mønsteret følger js/cells.js — ren halvdel testbar, DOM-halvdel ikke. */
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// Hent ut matchNav fra hjelp.html sin inline script-blokk. Vi mater blokken et
// falskt window-objekt; IIFE-en henger API-et på det, og `document` er guardet
// bort, så ingen DOM trengs.
const html = readFileSync(new URL('../../hjelp.html', import.meta.url), 'utf8');
const m = html.match(/\/\* SYNC:START felles-js \*\/([\s\S]*?)\/\* SYNC:END \*\//);
assert.ok(m, 'fant ikke felles-js-blokken i hjelp.html');
const fakeWindow = {};
new Function('window', m[1])(fakeWindow);
assert.ok(fakeWindow.HjelpUI, 'blokken hengte ikke HjelpUI på window');
const { matchNav } = fakeWindow.HjelpUI;

test('tom query viser alt', () => {
  assert.deepEqual(matchNav('', ['Editor', 'Moduser', 'Strict']), [0, 1, 2]);
});

test('filtrerer på delstreng, uavhengig av store bokstaver', () => {
  assert.deepEqual(matchNav('mod', ['Editor', 'Moduser', 'Strict']), [1]);
  assert.deepEqual(matchNav('MOD', ['Editor', 'Moduser', 'Strict']), [1]);
});

test('ingen treff gir tom liste', () => {
  assert.deepEqual(matchNav('zzz', ['Editor', 'Moduser']), []);
});

test('trimmer whitespace', () => {
  assert.deepEqual(matchNav('  strict  ', ['Editor', 'Strict']), [1]);
});

test('flere treff beholder rekkefølgen', () => {
  assert.deepEqual(matchNav('e', ['Editor', 'Moduser', 'Referanse']), [0, 1, 2]);
});
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `node --test tests/js/test_hjelp_ui.mjs`
Expected: FAIL — `fant ikke felles-js-blokken i hjelp.html`

- [ ] **Step 3: Legg til CSS-blokken**

I `hjelp.html`, inne i `<style>`, rett før den avsluttende `</style>`, legg til:

```css
/* SYNC:START felles-css */
/* ── Oversiktstabell først i hver hovedseksjon ── */
.overview { margin: 0 0 28px; }
.overview .doc-table { margin: 0; }
.overview-hint {
  font-size: 13px; color: var(--text-muted); margin: 6px 0 0;
}

/* ── Todelt eksempelblokk: kode ‖ resultat ── */
.example {
  display: grid; grid-template-columns: 1fr 1fr; gap: 1px;
  background: var(--border); border: 1px solid var(--border);
  border-radius: var(--radius); overflow: hidden; margin: 18px 0;
}
.example > * { background: var(--bg-card); }
.example-code, .example-result { padding: 14px 16px; min-width: 0; }
.example-code pre, .example-result pre {
  margin: 0; overflow-x: auto; font-size: 13px; line-height: 1.6;
}
.example-label {
  display: block; font-size: 11px; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--text-muted); margin-bottom: 8px;
}
.result { color: var(--text); }
.result.illustration { color: var(--text-muted); font-style: italic; }
.illustration-tag {
  display: inline-block; font-size: 11px; font-style: normal;
  padding: 1px 6px; border-radius: 4px; margin-left: 6px;
  background: var(--bg-code); color: var(--text-muted);
}
@media (max-width: 900px) {
  .example { grid-template-columns: 1fr; }
}

/* ── Kopier-knapp ── */
.example-code { position: relative; }
.copy-btn {
  position: absolute; top: 10px; right: 10px;
  font-size: 11px; padding: 3px 8px; cursor: pointer;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg-card); color: var(--text-muted);
}
.copy-btn:hover { color: var(--accent); border-color: var(--accent); }

/* ── Nav: filter + scrollspy ── */
.nav-filter {
  width: calc(100% - 36px); margin: 0 18px 14px; padding: 6px 9px;
  font-size: 13px; font-family: inherit;
  border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg); color: var(--text);
}
.nav-filter:focus { outline: none; border-color: var(--accent); }
.nav-link-hidden { display: none !important; }
nav a.nav-active {
  color: var(--accent); background: var(--accent-light);
  border-left: 2px solid var(--accent);
}
/* SYNC:END */
```

- [ ] **Step 4: Legg til JS-blokken**

I `hjelp.html`, rett før `</body>`, legg til:

```html
<script>
/* SYNC:START felles-js */
(function hjelpUI(w) {
  'use strict';

  // Ren funksjon — node-testet i tests/js/test_hjelp_ui.mjs.
  // Returnerer indeksene i `labels` som matcher `query`.
  function matchNav(query, labels) {
    var q = String(query || '').trim().toLowerCase();
    var out = [];
    for (var i = 0; i < labels.length; i++) {
      if (!q || String(labels[i]).toLowerCase().indexOf(q) >= 0) out.push(i);
    }
    return out;
  }

  function navLinks() {
    return Array.prototype.slice.call(document.querySelectorAll('nav a[href^="#"]'));
  }

  function initNavFilter() {
    var input = document.querySelector('.nav-filter');
    if (!input || input.dataset.wired) return;
    input.dataset.wired = '1';
    var links = navLinks();
    var labels = links.map(function (a) { return a.textContent; });
    input.addEventListener('input', function () {
      var keep = matchNav(input.value, labels);
      var show = Object.create(null);
      keep.forEach(function (i) { show[i] = true; });
      links.forEach(function (a, i) {
        a.classList.toggle('nav-link-hidden', !show[i]);
      });
      // Skjul en seksjonsoverskrift som ikke har synlige lenker under seg.
      Array.prototype.forEach.call(
        document.querySelectorAll('nav .nav-section'),
        function (h) {
          var any = false, el = h.nextElementSibling;
          while (el && !el.classList.contains('nav-section')) {
            if (el.tagName === 'A' && !el.classList.contains('nav-link-hidden')) any = true;
            el = el.nextElementSibling;
          }
          h.classList.toggle('nav-link-hidden', !any);
        });
    });
  }

  function initScrollspy() {
    var links = navLinks();
    if (!links.length || document.body.dataset.spyWired) return;
    document.body.dataset.spyWired = '1';
    var byId = Object.create(null);
    links.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var targets = Object.keys(byId)
      .map(function (id) { return document.getElementById(id); })
      .filter(Boolean);
    if (!targets.length || !w.IntersectionObserver) return;
    var seen = Object.create(null);
    var obs = new w.IntersectionObserver(function (entries) {
      entries.forEach(function (e) { seen[e.target.id] = e.isIntersecting; });
      var active = targets.filter(function (t) { return seen[t.id]; })[0];
      links.forEach(function (a) { a.classList.remove('nav-active'); });
      if (active && byId[active.id]) byId[active.id].classList.add('nav-active');
    }, { rootMargin: '-80px 0px -70% 0px' });
    targets.forEach(function (t) { obs.observe(t); });
  }

  function initCopyButtons() {
    Array.prototype.forEach.call(
      document.querySelectorAll('.example-code'),
      function (box) {
        if (box.querySelector('.copy-btn')) return;
        var pre = box.querySelector('pre');
        if (!pre) return;
        var btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.type = 'button';
        btn.textContent = 'Kopier';
        btn.addEventListener('click', function () {
          var text = pre.textContent;
          var done = function () {
            btn.textContent = 'Kopiert';
            w.setTimeout(function () { btn.textContent = 'Kopier'; }, 1400);
          };
          if (w.navigator && w.navigator.clipboard) {
            w.navigator.clipboard.writeText(text).then(done, function () {});
          }
        });
        box.appendChild(btn);
      });
  }

  w.HjelpUI = {
    matchNav: matchNav,
    initNavFilter: initNavFilter,
    initScrollspy: initScrollspy,
    initCopyButtons: initCopyButtons,
  };

  if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
      initNavFilter(); initScrollspy(); initCopyButtons();
    });
  }
})(typeof window !== 'undefined' ? window : this);
/* SYNC:END */
</script>
```

- [ ] **Step 5: Legg filterfeltet i nav**

I `hjelp.html`, rett etter `<div class="nav-logo">…</div>` og «In English»-lenken, legg til:

```html
<input class="nav-filter" type="search" placeholder="Filtrer…" aria-label="Filtrer innholdsfortegnelsen">
```

- [ ] **Step 6: Kjør testen for å se at den passerer**

Run: `node --test tests/js/test_hjelp_ui.mjs`
Expected: 5 tester PASS.

- [ ] **Step 7: Commit**

```bash
git add hjelp.html tests/js/test_hjelp_ui.mjs
git commit -m "feat(hjelp): scrollspy, nav-filter, kopier-knapp, todelt eksempelblokk

Fellesskiktet for layout, avgrenset av SYNC-markører så det kan holdes
identisk på tvers av de fire repoene. matchNav er skilt ut som ren
funksjon og node-testet, etter mønsteret i js/cells.js."
```

---

## Task 3: Synk-sjekk for fellesseksjonene

**Files:**
- Create: `scripts/hjelp_sync_check.sh`
- Test: `tests/test_hjelp_sync.py`

**Interfaces:**
- Consumes: SYNC-markørene fra Task 2 (`/* SYNC:START felles-css */`, `<!-- SYNC:START felles-editor -->` osv.).
- Produces: `scripts/hjelp_sync_check.sh` — exit 0 når alle SYNC-blokker er identiske på tvers av de søskenrepoene som finnes lokalt, exit 1 ellers, med en diff på stderr. Hopper over søsken som ikke er sjekket ut, med en melding — den skal ikke feile fordi et repo mangler.
- Produces: `extract_block(text: str, name: str) -> str | None` i testen — brukes også av Task 17.

Markørene finnes i to former fordi CSS/JS krever `/* */` og HTML krever `<!-- -->`. Skriptet må håndtere begge.

- [ ] **Step 1: Skriv den feilende testen**

Opprett `tests/test_hjelp_sync.py`:

```python
"""Synk-sjekk for hjelpesidenes fellesseksjoner.

De fire repoene har hver sin hjelp.html. Fellesseksjonene skal være
byte-identiske; dagens tilstand er beviset på at de ellers driver fra
hverandre (askstat sin het «OpenStat» i to måneder)."""
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "hjelp_sync_check.sh"

BLOCK_NAMES = [
    "felles-css", "felles-js", "felles-editor", "felles-sidebar",
    "felles-lagre", "felles-forklar", "felles-widgets", "felles-ai",
    "felles-eksempler", "felles-referanse-snarveier", "felles-referanse-tab",
]


def extract_block(text: str, name: str):
    """Hent én SYNC-blokk. Godtar både /* */ og <!-- --> som markør."""
    pat = (r"(?:/\*|<!--)\s*SYNC:START\s+" + re.escape(name)
           + r"\s*(?:\*/|-->)(.*?)(?:/\*|<!--)\s*SYNC:END\s*(?:\*/|-->)")
    m = re.search(pat, text, re.DOTALL)
    return m.group(1) if m else None


def test_skriptet_finnes_og_er_kjorbart():
    assert SCRIPT.exists(), "scripts/hjelp_sync_check.sh mangler"
    assert SCRIPT.stat().st_mode & 0o111, "skriptet er ikke kjørbart"


def test_alle_blokker_finnes_i_egen_hjelp():
    """Hver navngitt blokk skal faktisk finnes i safestat sin hjelp.html."""
    text = (REPO / "hjelp.html").read_text(encoding="utf-8")
    mangler = [n for n in BLOCK_NAMES if extract_block(text, n) is None]
    assert not mangler, f"mangler SYNC-blokker: {mangler}"


def test_skriptet_gir_exit_0_naar_alt_stemmer():
    r = subprocess.run(["sh", str(SCRIPT)], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"exit {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_skriptet_gir_exit_1_ved_avvik(tmp_path):
    """Bygg et falskt søskenrepo med en sabotert blokk og se at skriptet
    faktisk går til exit 1. Uten denne kunne skriptet returnert 0 alltid og
    synk-disiplinen vært en illusjon."""
    text = (REPO / "hjelp.html").read_text(encoding="utf-8")
    blokk = extract_block(text, "felles-css")
    assert blokk is not None, "felles-css mangler i hjelp.html"

    falsk = tmp_path / "faksesosken"
    falsk.mkdir()
    saboterte = text.replace(blokk, blokk + "\n.sabotasje { color: red; }", 1)
    assert saboterte != text, "sabotasjen endret ingenting"
    (falsk / "hjelp.html").write_text(saboterte, encoding="utf-8")
    (falsk / "hjelp.en.html").write_text(
        (REPO / "hjelp.en.html").read_text(encoding="utf-8"), encoding="utf-8")

    r = subprocess.run(
        ["sh", str(SCRIPT)], cwd=REPO, capture_output=True, text=True,
        env={**os.environ,
             "HJELP_SYNC_ROOT": str(tmp_path),
             "HJELP_SYNC_SIBLINGS": "faksesosken"})
    assert r.returncode == 1, (
        f"skriptet godtok et avvik (exit {r.returncode})\n{r.stdout}\n{r.stderr}")
    assert "felles-css" in r.stderr, "feilmeldingen navngir ikke blokken"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp_sync.py -v`
Expected: FAIL — `scripts/hjelp_sync_check.sh mangler`

- [ ] **Step 3: Skriv synk-skriptet**

Opprett `scripts/hjelp_sync_check.sh`:

```sh
#!/bin/sh
# Diff hjelpesidenes fellesseksjoner mot søskenrepoene.
#
# Lag 2 (verktøy) og lag 3 (referanse) skal være byte-identiske i safestat,
# openstat, askstat og microdata. Lag 0 (hero), modustabellen og lag 1
# (kjernen) er repo-spesifikke og med vilje utenfor sjekken.
#
# Exit 1 ved avvik. Søsken som ikke er sjekket ut lokalt hoppes over.
#
# HJELP_SYNC_ROOT og HJELP_SYNC_SIBLINGS kan overstyres — testen bruker det for
# å bygge et falskt søsken med en sabotert blokk og bekrefte at exit 1 faktisk
# inntreffer. Uten overstyring er standarden søskenrepoene ved siden av dette.
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT="${HJELP_SYNC_ROOT:-$HERE/..}"
SIBLINGS="${HJELP_SYNC_SIBLINGS:-openstat askstat microdata}"
BLOCKS="felles-css felles-js felles-editor felles-sidebar felles-lagre
        felles-forklar felles-widgets felles-ai felles-eksempler
        felles-referanse-snarveier felles-referanse-tab"
FILES="hjelp.html hjelp.en.html"

fail=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Hent én SYNC-blokk ut av en fil. Godtar /* */ og <!-- -->.
extract() {
  awk -v name="$2" '
    $0 ~ ("SYNC:START[ \t]+" name "([ \t]*\\*/|[ \t]*-->)") { on=1; next }
    on && /SYNC:END/ { on=0 }
    on { print }
  ' "$1"
}

for f in $FILES; do
  [ -f "$HERE/$f" ] || { echo "hopper over $f (finnes ikke her)"; continue; }
  for sib in $SIBLINGS; do
    sibfile="$ROOT/$sib/$f"
    if [ ! -f "$sibfile" ]; then
      echo "hopper over $sib/$f (ikke sjekket ut)"
      continue
    fi
    for b in $BLOCKS; do
      extract "$HERE/$f" "$b" > "$tmp/a"
      extract "$sibfile" "$b" > "$tmp/b"
      if [ ! -s "$tmp/a" ]; then
        echo "AVVIK: blokk '$b' mangler i safestat/$f" >&2
        fail=1
        continue
      fi
      if [ ! -s "$tmp/b" ]; then
        echo "AVVIK: blokk '$b' mangler i $sib/$f" >&2
        fail=1
        continue
      fi
      if ! diff -q "$tmp/a" "$tmp/b" >/dev/null; then
        echo "AVVIK i $f, blokk '$b': safestat vs $sib" >&2
        diff -u "$tmp/a" "$tmp/b" | head -40 >&2
        fail=1
      fi
    done
  done
done

if [ "$fail" -ne 0 ]; then
  echo "" >&2
  echo "Fellesseksjonene har drevet fra hverandre. safestat er kanonisk —" >&2
  echo "kopier derfra til søskenet, ikke omvendt." >&2
  exit 1
fi

echo "hjelp_sync_check: fellesseksjonene stemmer"
```

- [ ] **Step 4: Gjør skriptet kjørbart**

Run: `chmod +x scripts/hjelp_sync_check.sh`

- [ ] **Step 5: Kjør testen**

Run:
```bash
sh scripts/hjelp_sync_check.sh
.venv/bin/python -m pytest tests/test_hjelp_sync.py -v
```
Expected: skriptet hopper over søsknene (de har ikke SYNC-blokker ennå) og melder «fellesseksjonene stemmer» for de blokkene som finnes; alle fire tester PASS.

Merk: `test_alle_blokker_finnes_i_egen_hjelp` vil feile på blokkene som ennå ikke er skrevet (`felles-editor` og utover kommer i Task 9). Kommenter ut de blokknavnene i `BLOCK_NAMES` som ennå ikke finnes, med en `# Task 9`-kommentar, og fjern kommentaren i Task 9.

- [ ] **Step 6: Commit**

```bash
git add scripts/hjelp_sync_check.sh tests/test_hjelp_sync.py
git commit -m "feat(hjelp): synk-sjekk for fellesseksjonene

Exit 1 når en SYNC-blokk har drevet fra søskenrepoene. Lag 0, modustabellen
og lag 1 er bevisst utenfor sjekken — de er repo-spesifikke."
```

---

## Task 4: safestat — identitet og lag 0

**Files:**
- Modify: `hjelp.html:1-230` (`<title>`, `nav-logo`, `doc-header`, ny lag 0-seksjon)
- Test: `tests/test_hjelp.py`

**Interfaces:**
- Consumes: CSS-klassen `overview` fra Task 2.
- Produces: `tests/test_hjelp.py` med `IDENTITY: dict[str, dict]` og `read(repo, fil) -> str` — utvides av Task 11, 13, 15 med sine repoer.
- Produces: seksjons-id-ene `intro` og `hurtigstart` i safestat/hjelp.html.

- [ ] **Step 1: Skriv den feilende testen**

Opprett `tests/test_hjelp.py`:

```python
"""Strukturtester for hjelpesidene.

Identitet, påkrevde seksjoner og forbudte strenger. Testen finnes fordi
askstat sin hjelpeside het «OpenStat» i to måneder uten at noe fanget det."""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

IDENTITY = {
    "safestat": {
        "title_no": "SafeStat – Dokumentasjon",
        "title_en": "SafeStat – Documentation",
        "h1": "SafeStat",
        "nav_logo": "SafeStat",
        "lead_no": "Analyser beskyttede data uten at dataene forlater det trygge.",
    },
}

FORBUDT_OVERALT = ["Microdata Script Runner"]


def read(fil: str) -> str:
    return (REPO / fil).read_text(encoding="utf-8")


class _Grab(HTMLParser):
    """Plukker ut title, første h1, nav-logo, lead og alle section-id-er.
    Bruker stdlib — bs4 er ikke installert og skal ikke installeres."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.h1 = None
        self.nav_logo = None
        self.lead = None
        self.section_ids = []
        self._want = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._want = "title"
        elif tag == "h1" and self.h1 is None:
            self._want = "h1"
        elif tag == "div" and a.get("class") == "nav-logo":
            self._want = "nav_logo"
        elif tag == "p" and a.get("class") == "lead":
            self._want = "lead"
        elif tag == "section" and a.get("id"):
            self.section_ids.append(a["id"])

    def handle_data(self, data):
        if self._want and data.strip():
            setattr(self, self._want, data.strip())
            self._want = None

    def handle_endtag(self, tag):
        self._want = None


def grab(fil: str) -> _Grab:
    p = _Grab()
    p.feed(read(fil))
    return p


@pytest.mark.parametrize("fil", ["hjelp.html", "hjelp.en.html"])
def test_ingen_forbudte_strenger(fil):
    text = read(fil)
    for s in FORBUDT_OVERALT:
        assert s not in text, f"{fil} inneholder fortsatt «{s}»"


def test_identitet_norsk():
    ident = IDENTITY["safestat"]
    g = grab("hjelp.html")
    assert g.title == ident["title_no"]
    assert g.h1 == ident["h1"]
    assert g.nav_logo == ident["nav_logo"]
    assert g.lead == ident["lead_no"]


def test_identitet_engelsk():
    ident = IDENTITY["safestat"]
    g = grab("hjelp.en.html")
    assert g.title == ident["title_en"]
    assert g.h1 == ident["h1"]
    assert g.nav_logo == ident["nav_logo"]


def test_lag0_seksjoner_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("intro", "hurtigstart"):
        assert s in ids, f"mangler seksjon #{s}"


def test_navfilter_finnes():
    assert 'class="nav-filter"' in read("hjelp.html")


def test_denne_siden_dekker_tabell():
    """Lag 0 skal ha en oversiktstabell, ikke bare prosa."""
    text = read("hjelp.html")
    m = re.search(r'<section id="intro".*?</section>', text, re.DOTALL)
    assert m, "fant ikke intro-seksjonen"
    assert 'class="overview"' in m.group(0), "intro mangler oversiktstabell"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -v`
Expected: FAIL — `hjelp.html inneholder fortsatt «Microdata Script Runner»`

- [ ] **Step 3: Rett identiteten**

I `hjelp.html`:
- `<title>Microdata Script Runner – Dokumentasjon</title>` → `<title>SafeStat – Dokumentasjon</title>`
- `<div class="nav-logo">Script Runner</div>` → `<div class="nav-logo">SafeStat</div>`
- `<h1>Microdata Script Runner</h1>` → `<h1>SafeStat</h1>`
- `<p class="lead">…</p>` → `<p class="lead">Analyser beskyttede data uten at dataene forlater det trygge.</p>`

I `hjelp.en.html`, samme, med `SafeStat – Documentation` og leadet
`Analyse protected data without the data leaving safe ground.`

- [ ] **Step 4: Skriv lag 0**

Erstatt `<section id="intro">` (linje ~212–227) med:

```html
<section id="intro">
  <h2>Hva er dette?</h2>
  <p>SafeStat er en analysearbeidsbenk i nettleseren for data som ikke tåler å bli sett. Du skriver vanlig Python, R eller SQL; SafeStat sørger for at bare <strong>undertrykte aggregater</strong> slipper ut — aldri en enkeltrad, aldri et ekstremverdi.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Del</th><th>Hva du finner der</th></tr></thead>
      <tbody>
        <tr><td><a href="#tillit">Tillitsmodellen</a></td><td>Hvor koden kjører, hva som slipper ut, hvem som ser hva</td></tr>
        <tr><td><a href="#kilder">Beskyttede kilder</a></td><td>Krypterte og passordbeskyttede datasett, nøkkellageret</td></tr>
        <tr><td><a href="#strict-py">Restricted Python</a></td><td>Hva du kan skrive, hva som ikke finnes, og hvorfor</td></tr>
        <tr><td><a href="#strict-r">Restricted R</a></td><td>Samme frigivelseskjerne, R-syntaks</td></tr>
        <tr><td><a href="#federert">Federerte kilder</a></td><td>Analyser flere noder uten å samle dataene</td></tr>
        <tr><td><a href="#modes">Moduser</a></td><td>De ni språkene, og når du velger hvilket</td></tr>
        <tr><td><a href="#tab-full">Referanse</a></td><td>Snarveier, direktiver, Tab-autocomplete</td></tr>
      </tbody>
    </table>
    <p class="overview-hint">Filtrer innholdsfortegnelsen til venstre for å hoppe rett til et emne.</p>
  </div>

  <div class="callout">
    <strong>NB:</strong> Dette er et hobbyprosjekt og er ikke laget av microdata.no. Demodataene inneholder ikke ekte tall, og det gis ingen garantier for at analysene er korrekt implementert.
  </div>
</section>

<section id="hurtigstart">
  <h2>30 sekunder</h2>
  <p>Velg <strong>python</strong> i modusmenyen, lim inn dette, og trykk <kbd>Ctrl</kbd>+<kbd>Enter</kbd>:</p>

  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge badge-py">py</span></span>
      <pre><code># options.profile = strict
df.groupby("kjonn")["lonn"].mean()</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">kjonn  mean(lonn)
1  520 790
2  518 450</pre>
    </div>
  </div>

  <p>Du fikk et gruppegjennomsnitt. Prøv nå <code>df.head()</code> i stedet — det finnes ikke, og <a href="#strict-py">Restricted Python</a> forklarer hvorfor.</p>
</section>
```

Resultatblokken over er den faktiske outputen fra harnessen, målt
2026-07-30. Kjør likevel `.venv/bin/python docs/hjelp_examples/run_examples.py`
og sammenlign mot `output/strict-py-gruppegjennomsnitt.txt` — avviker de,
er det filen som har rett, og `test_strict_py_resultatblokker_stemmer_med_harness`
i Task 6 vil fange det.

- [ ] **Step 5: Kjør testene**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -v`
Expected: alle PASS.

- [ ] **Step 6: Commit**

```bash
git add hjelp.html hjelp.en.html tests/test_hjelp.py
git commit -m "docs(hjelp): safestat får riktig navn og et lag 0 som orienterer

Siden het «Microdata Script Runner». Nå: SafeStat, med ledesetning, en
oversiktstabell over hva siden dekker, og et hurtigstart-eksempel med
faktisk kjørt output."
```

---

## Task 5: safestat — tillitsmodellen og beskyttede kilder

**Files:**
- Modify: `hjelp.html` (ny `<section id="tillit">` og `<section id="kilder">`, plassert rett etter `#hurtigstart`)
- Modify: `hjelp.en.html` (samme, engelsk)
- Test: `tests/test_hjelp.py` (utvid)

**Interfaces:**
- Consumes: `overview`-klassen (Task 2), `IDENTITY`/`grab` (Task 4).
- Produces: seksjons-id-ene `tillit` og `kilder`.

- [ ] **Step 1: Utvid testen**

Legg til i `tests/test_hjelp.py`:

```python
def test_tillit_og_kilder_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("tillit", "kilder"):
        assert s in ids, f"mangler seksjon #{s}"


def test_tillit_har_oversiktstabell():
    text = read("hjelp.html")
    m = re.search(r'<section id="tillit".*?</section>', text, re.DOTALL)
    assert m, "fant ikke tillit-seksjonen"
    blokk = m.group(0)
    assert 'class="doc-table"' in blokk, "tillit mangler tabell"
    # De tre nivåene skal navngis eksplisitt.
    for niva in ("public", "protected", "sensitive"):
        assert niva in blokk, f"tillit nevner ikke nivået «{niva}»"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py::test_tillit_og_kilder_finnes -v`
Expected: FAIL — `mangler seksjon #tillit`

- [ ] **Step 3: Skriv seksjonene**

**Advarsel om kilden.** En tidligere versjon av denne planen hentet
nivåtabellen fra docstringen øverst i `safepy/policy.py`. Den docstringen er
feil på to punkter, verifisert 2026-07-30:

- Den omtaler et felt `sandbox_allowed` og påstår «we encode the boundary as
  a value, not a comment». Feltet **finnes ikke** på `Policy` — det opptrer
  bare to steder i hele safepy, begge i den samme docstringen.
- Den sier «protected and sensitive get the STRICT capability executor», mens
  koden på linje 138 gjør `Profile.OPEN` for både `public` og `protected`.

Det som faktisk gjelder for en SafeStat-bruker: appen sender
`profile='strict'` eksplisitt ved hver strict-kjøring (`index.html:9532`), og
`api.py:130` lar et eksplisitt argument overstyre den utledede profilen. Så
protected *blir* STRICT i SafeStat — men fordi appen overstyrer, ikke fordi
nivået bestemmer det. Det finnes heller ingen «oversett til artefakt»-sti
noe sted i koden, og `index.html:2233` behandler `protected` og `sensitive`
likt. Eneste reelle særbehandling av `sensitive` er at pull-federering
nekter det (`js/data-directives.js:119`).

**Skriv det som er sant om appen, ikke det docstringen påstår.** Sett inn
rett etter `#hurtigstart`:

```html
<section id="tillit">
  <h2>Tillitsmodellen</h2>
  <p>Alt henger på ett spørsmål: <em>hvor kjører koden din, og hva får forlate det stedet?</em> Svaret bestemmes av datakildens beskyttelsesnivå — ikke av hva du selv velger.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Nivå</th><th>Hvor koden kjører</th><th>Profil i SafeStat</th><th>Begrensning</th></tr></thead>
      <tbody>
        <tr><td><code>public</code></td><td>I nettleseren din</td><td>OPEN, med mindre du ber om strict</td><td>Ingen</td></tr>
        <tr><td><code>protected</code></td><td>Bak fasaden — lokalt hvis eieren har åpnet for det, ellers bare eksternt</td><td>STRICT, alltid</td><td>Krever innlogging; kjøringen logges</td></tr>
        <tr><td><code>sensitive</code></td><td>Samme som protected</td><td>STRICT, alltid</td><td>Som protected, og kan <strong>ikke</strong> brukes med pull-federering — krever node-medlem</td></tr>
      </tbody>
    </table>
    <p class="overview-hint">Blander du flere kilder, vinner det <strong>mest restriktive</strong> nivået.</p>
  </div>

  <h3>To profiler</h3>
  <table class="doc-table">
    <thead><tr><th>Profil</th><th>Hva som er i navnerommet</th><th>Forsvaret</th></tr></thead>
    <tbody>
      <tr><td><strong>OPEN</strong></td><td>Ekte pandas og den rå datarammen</td><td>Oppregning: en portvokter på syntaksnoder, en nektliste på metoder, og en proveniensjekk på vei ut. «Sannsynligvis trygt» — hele pandas er angrepsflate.</td></tr>
      <tr><td><strong>STRICT</strong></td><td>Bare <code>SafeFrame</code>-fasaden og de trygge verbene. Ingen pandas, ingen rå dataramme.</td><td>Konstruksjon: de avslørende mulighetene <em>finnes ikke</em>. Angrepsflaten er den korte, lukkede metodelista.</td></tr>
    </tbody>
  </table>

  <div class="callout tip">
    <strong>Skru på selv:</strong> <code># options.profile = strict</code> øverst i skriptet, i python-, r- eller duckdb-modus. Beskyttede kilder tvinger strict uansett hva du skriver.
  </div>
</section>

<section id="kilder">
  <h2>Beskyttede kilder</h2>
  <p>En beskyttet kilde er kryptert på disk og låses opp med en nøkkel du oppgir. Nøkkelen brukes til å dekryptere, aldri til å sende data ut.</p>
  <table class="doc-table">
    <thead><tr><th>Kilde</th><th>Låses opp med</th><th>Hvor nøkkelen bor</th></tr></thead>
    <tbody>
      <tr><td>Passordbeskyttet fil</td><td>Passord i dialogen</td><td>Bare i minnet, forsvinner ved reload</td></tr>
      <tr><td>Kryptert datasett (<code>.enc</code>)</td><td>Nøkkel fra nøkkellageret</td><td>Nøkkellageret i <strong>nettleseren din</strong> — synkes til kontoen hvis du er innlogget</td></tr>
      <tr><td>Federert node</td><td>Node-token</td><td>På noden — data forlater den aldri</td></tr>
    </tbody>
  </table>
  <p>Nøkkellageret er beskrevet under <a href="#federert">Federerte kilder</a>, siden de to hører sammen i praksis.</p>
</section>
```

Oppdater `<nav>` med lenker til `#tillit` og `#kilder` under en ny
`<div class="nav-section">Tillit</div>`.

- [ ] **Step 4: Skriv den engelske versjonen**

Samme struktur i `hjelp.en.html`, oversatt. `<code>`-innhold,
profilnavn (OPEN/STRICT) og nivånavn (public/protected/sensitive) er
identiske i begge språk.

- [ ] **Step 5: Kjør testene**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -v`
Expected: alle PASS.

- [ ] **Step 6: Commit**

```bash
git add hjelp.html hjelp.en.html tests/test_hjelp.py
git commit -m "docs(hjelp): tillitsmodellen og beskyttede kilder

safestat leder nå med det den faktisk er: hvor koden kjører og hva som
slipper ut. Nivå- og profiltabellene er verifisert mot safepy/policy.py."
```

---

## Task 6: safestat — Restricted Python

**Files:**
- Modify: `hjelp.html` (ny `<section id="strict-py">`)
- Modify: `hjelp.en.html`
- Test: `tests/test_hjelp.py` (utvid)

**Interfaces:**
- Consumes: outputfilene `strict-py-gruppegjennomsnitt.txt`, `strict-py-avvist-head.txt`, `strict-py-avvist-posisjon.txt`, `strict-py-avvist-import.txt` fra Task 1.
- Produces: seksjons-id `strict-py`.

Metodelistene under er hentet fra `safepy/safeframe.py` og
`safepy/ast_gate.py` 2026-07-30. Ikke skriv dem på nytt fra hukommelsen —
kjør uttrekket i Step 3 hvis de må oppfriskes.

- [ ] **Step 1: Utvid testen**

```python
def test_strict_py_har_avvist_eksempel_med_ekte_feilmelding():
    """Seksjonen skal vise et eksempel som blir avvist, med safepy sin
    faktiske feilmelding — ikke en omskrevet variant."""
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-py".*?</section>', text, re.DOTALL)
    assert m, "fant ikke strict-py-seksjonen"
    blokk = m.group(0)
    assert "'head' is not allowed" in blokk
    assert "reveal individual rows" in blokk


def test_strict_py_resultatblokker_stemmer_med_harness():
    """Hver <pre class="result"> i strict-py skal finnes ordrett i en
    outputfil fra harnessen. Fanger resultater som er redigert for hånd."""
    outdir = REPO / "docs" / "hjelp_examples" / "output"
    kjort = [f.read_text(encoding="utf-8").strip() for f in outdir.glob("*.txt")]
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-py".*?</section>', text, re.DOTALL)
    assert m
    blokker = re.findall(r'<pre class="result">(.*?)</pre>', m.group(0), re.DOTALL)
    assert blokker, "strict-py har ingen resultatblokker"
    import html as _html
    for b in blokker:
        ren = _html.unescape(b).strip()
        assert any(ren == k for k in kjort), (
            f"resultatblokk finnes ikke i harness-output:\n{ren[:200]}")
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -k strict_py -v`
Expected: FAIL — `fant ikke strict-py-seksjonen`

- [ ] **Step 3: Frisk opp metodelistene hvis nødvendig**

```bash
T=$(mktemp -d) && unzip -q -o vendor/safepy.zip -d "$T" && \
.venv/bin/python -c "
import sys; sys.path.insert(0, '$T')
from safepy import safeframe
from safepy.ast_gate import _DENIED_METHODS, _SAFE_BUILTINS, _IMPORT_WHITELIST
print('SafeFrame:', sorted(m for m in dir(safeframe.SafeFrame) if not m.startswith('_')))
print()
print('SafeColumn:', sorted(m for m in dir(safeframe.SafeColumn) if not m.startswith('_')))
print()
print('SafeGroupBy:', sorted(m for m in dir(safeframe.SafeGroupBy) if not m.startswith('_')))
print()
print('nektet:', sorted(_DENIED_METHODS))
print('byggefunksjoner:', sorted(_SAFE_BUILTINS))
print('import tillatt:', sorted(_IMPORT_WHITELIST))
"
```

- [ ] **Step 4: Skriv seksjonen**

```html
<section id="strict-py">
  <h2>Restricted Python</h2>
  <p>Du skriver pandas. Men i STRICT-profilen er <code>df</code> ikke en <code>DataFrame</code> — den er en <code>SafeFrame</code>, en fasade med et bevisst kort metodeutvalg. Alt som kunne vise deg en enkeltrad er ikke forbudt; det <em>finnes ikke</em>.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Du vil</th><th>Skriv</th><th>Virker</th></tr></thead>
      <tbody>
        <tr><td>Se på dataene</td><td><code>df.head()</code></td><td>Nei — bruk <code>df.describe()</code> eller <code>df.count()</code></td></tr>
        <tr><td>Gruppegjennomsnitt</td><td><code>df.groupby("kjonn")["lonn"].mean()</code></td><td>Ja</td></tr>
        <tr><td>Filtrere</td><td><code>df[df["alder"] &gt;= 40]</code></td><td>Ja — masken er lovlig, resultatet er fortsatt privat</td></tr>
        <tr><td>Én rad</td><td><code>df["lonn"][0]</code></td><td>Nei — posisjonsindeksering er stengt</td></tr>
        <tr><td>Regresjon</td><td><code>df.ols("lonn ~ alder + kjonn")</code></td><td>Ja</td></tr>
        <tr><td>Eget uttrykk</td><td><code>df.apply(lambda r: …)</code></td><td>Nei — vilkårlig kode er den egentlige risikoen</td></tr>
      </tbody>
    </table>
  </div>

  <h3>Det som virker</h3>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge badge-py">py</span></span>
      <pre><code>df.groupby("kjonn")["lonn"].mean()</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">kjonn  mean(lonn)
1  520 790
2  518 450</pre>
    </div>
  </div>

  <h3>Tre måter å bli avvist</h3>
  <p>Portvokteren leser koden din før den kjører. Meldingene navngir <em>kode</em> — en metode, en modul, en linje — men aldri en dataverdi, siden feiltekst ellers ville vært en lekkasjekanal.</p>

  <div class="example">
    <div class="example-code">
      <span class="example-label">Rå rader <span class="badge badge-py">py</span></span>
      <pre><code>df.head()</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">Avvist (attribute): 'head' is not allowed: it can reveal individual rows or run arbitrary code</pre>
    </div>
  </div>

  <div class="example">
    <div class="example-code">
      <span class="example-label">Posisjonsindeks <span class="badge badge-py">py</span></span>
      <pre><code>df["lonn"][0]</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">Avvist (subscript): positional indexing (df[&lt;int&gt;]) is not allowed; select by column name or boolean mask</pre>
    </div>
  </div>

  <div class="example">
    <div class="example-code">
      <span class="example-label">Import utenfor lista <span class="badge badge-py">py</span></span>
      <pre><code>import os
df.groupby("kjonn")["lonn"].mean()</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">Avvist (import): module 'os' is not available in safepy</pre>
    </div>
  </div>

  <h3>Hele metodeutvalget</h3>
  <p>Dette er alt <code>SafeFrame</code> kan. Lista er kort med vilje — den er hele angrepsflaten.</p>
  <table class="doc-table">
    <thead><tr><th>Gruppe</th><th>Metoder</th></tr></thead>
    <tbody>
      <tr><td>Form og utvalg</td><td><code>assign</code> <code>astype</code> <code>drop</code> <code>drop_duplicates</code> <code>dropna</code> <code>fillna</code> <code>filter</code> <code>rename</code> <code>replace</code> <code>round</code> <code>select_dtypes</code> <code>sort_values</code> <code>where</code> <code>clip</code> <code>merge</code></td></tr>
      <tr><td>Omforming</td><td><code>explode</code> <code>melt</code> <code>pivot</code> <code>pivot_table</code> <code>stack</code> <code>unstack</code> <code>crosstab</code></td></tr>
      <tr><td>Aggregater</td><td><code>count</code> <code>mean</code> <code>median</code> <code>std</code> <code>sum</code> <code>var</code> <code>nunique</code> <code>describe</code> <code>value_counts</code> <code>corr</code> <code>cov</code> <code>groupby</code> <code>summarise</code> / <code>summarize</code></td></tr>
      <tr><td>Tester</td><td><code>anova</code> <code>chisq</code> <code>corr_test</code> <code>ttest</code> <code>mannwhitney</code> <code>logrank</code></td></tr>
      <tr><td>Modeller</td><td><code>ols</code> <code>logit</code> <code>poisson</code> <code>feols</code> <code>iv</code> <code>cox</code> <code>propensity</code> <code>ate</code> <code>refute_ate</code> <code>synthetic_control</code></td></tr>
      <tr><td>Overlevelse</td><td><code>kaplan_meier</code> <code>rmst</code> <code>weibull_aft</code> <code>lognormal_aft</code> <code>loglogistic_aft</code></td></tr>
    </tbody>
  </table>

  <h3>Kolonner</h3>
  <p>En kolonne (<code>SafeColumn</code>) har i tillegg <code>abs</code> <code>between</code> <code>cummax</code> <code>cummin</code> <code>cumprod</code> <code>cumsum</code> <code>diff</code> <code>dt</code> <code>ffill</code> <code>bfill</code> <code>interpolate</code> <code>isin</code> <code>isna</code> <code>notna</code> <code>kurt</code> <code>map</code> <code>mask</code> <code>max</code> <code>min</code> <code>pct_change</code> <code>quantile</code> <code>sem</code> <code>shift</code> <code>skew</code> <code>str</code> — og <code>plot</code> / <code>hist</code> / <code>boxplot</code>, der histogrammet omdirigeres til en undertrykt frekvenstabell.</p>
  <p>En gruppering (<code>SafeGroupBy</code>) har <code>count</code> <code>mean</code> <code>median</code> <code>size</code> <code>std</code> <code>sum</code> <code>var</code>.</p>

  <h3>Hva som aldri er lov</h3>
  <table class="doc-table">
    <thead><tr><th>Kategori</th><th>Eksempler</th><th>Hvorfor</th></tr></thead>
    <tbody>
      <tr><td>Rå rader ut</td><td><code>head</code> <code>tail</code> <code>sample</code> <code>iloc</code> <code>loc</code> <code>at</code> <code>iat</code> <code>values</code> <code>iterrows</code> <code>to_csv</code> <code>to_dict</code> <code>to_numpy</code></td><td>Viser enkeltindivider direkte</td></tr>
      <tr><td>Radidentifiserende reduksjon</td><td><code>idxmax</code> <code>idxmin</code> <code>argmax</code> <code>nlargest</code> <code>nsmallest</code> <code>first</code> <code>last</code> <code>mode</code></td><td>Returnerer én bestemt rad</td></tr>
      <tr><td>Rangering</td><td><code>rank</code></td><td>Rangering pluss filter pluss sum er en differanseangrep-primitiv. Krever et spørrebudsjett som ennå ikke finnes.</td></tr>
      <tr><td>Vilkårlig kode</td><td><code>apply</code> <code>applymap</code> <code>pipe</code> <code>query</code> <code>eval</code> <code>rolling</code></td><td>Tar en funksjon; den kan gjøre hva som helst</td></tr>
      <tr><td>Sandkasseflukt</td><td><code>eval</code> <code>exec</code> <code>open</code> <code>getattr</code> <code>globals</code> <code>__import__</code></td><td>Ut av sandkassen</td></tr>
      <tr><td>Syntaks</td><td>lambda, comprehensions, <code>def</code>, <code>for</code>, <code>while</code>, <code>try</code>, f-strenger, <code>df[1:5]</code></td><td>Portvokteren godtar bare tilordninger og uttrykk. Ny syntaks kan ikke snike seg inn.</td></tr>
      <tr><td>Navn</td><td>alt som starter med <code>_</code></td><td>Private attributter er en omvei rundt fasaden</td></tr>
    </tbody>
  </table>

  <p>Bare <code>len</code> <code>round</code> <code>abs</code> <code>int</code> <code>float</code> <code>str</code> <code>bool</code> kan kalles på navn. Bare <code>lifelines</code> <code>numpy</code> <code>pandas</code> <code>pyfixest</code> <code>polars</code> kan importeres, og de løses opp til trygge fasader — aldri de virkelige modulene.</p>

  <div class="callout">
    <strong>Omforminger er lov.</strong> <code>pivot</code>, <code>stack</code>, <code>melt</code> og <code>explode</code> beholder hele populasjonen og returnerer et privat objekt som bare kan forlate systemet som et undertrykt aggregat. De er trygge ved konstruksjon, ikke ved tillatelse.
  </div>
</section>
```

Erstatt hver `INNHOLD FRA …`-plassholder med filens faktiske innhold,
HTML-escapet.

- [ ] **Step 5: Skriv den engelske versjonen**

Samme i `hjelp.en.html`. Metodenavn, feilmeldinger og resultatblokker er
identiske i begge språk — bare prosaen oversettes.

- [ ] **Step 6: Kjør testene**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -v`
Expected: alle PASS.

- [ ] **Step 7: Commit**

```bash
git add hjelp.html hjelp.en.html tests/test_hjelp.py
git commit -m "docs(hjelp): Restricted Python får en egen full seksjon

Var ett avsnitt for tre dialekter. Nå: hele metodeutvalget, hva som aldri
er lov og hvorfor, og tre avviste eksempler med safepy sine faktiske
feilmeldinger. Resultatblokkene er generert, og en test sammenligner dem
mot harness-output."
```

---

## Task 7: safestat — Restricted R og Restricted SQL

**Files:**
- Modify: `hjelp.html` (nye `<section id="strict-r">` og `<section id="strict-sql">`)
- Modify: `hjelp.en.html`
- Test: `tests/test_hjelp.py` (utvid)

**Interfaces:**
- Consumes: `strict-r-summarise.txt`, `strict-r-avvist-head.txt`, `strict-sql-gruppe.txt` fra Task 1.
- Produces: seksjons-id-ene `strict-r` og `strict-sql`.

- [ ] **Step 1: Utvid testen**

```python
def test_strict_r_har_avvist_eksempel():
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-r".*?</section>', text, re.DOTALL)
    assert m, "fant ikke strict-r-seksjonen"
    assert "base-R function 'head' is not supported" in m.group(0)


def test_strict_r_og_sql_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("strict-r", "strict-sql"):
        assert s in ids, f"mangler seksjon #{s}"


def test_r_dialekten_er_beskrevet_som_oversatt():
    """R-koden oversettes, den kjøres aldri direkte. Leseren må få vite det,
    ellers forventer de at hele R er tilgjengelig."""
    text = read("hjelp.html")
    m = re.search(r'<section id="strict-r".*?</section>', text, re.DOTALL)
    assert m
    blokk = m.group(0).lower()
    assert "oversett" in blokk, "strict-r sier ikke at koden oversettes"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -k strict_r -v`
Expected: FAIL — `fant ikke strict-r-seksjonen`

- [ ] **Step 3: Skriv seksjonene**

```html
<section id="strict-r">
  <h2>Restricted R</h2>
  <p>R-koden din <strong>oversettes</strong> — den kjøres aldri direkte. SafeStat leser uttrykket, bygger det om til den samme frigivelseskjernen som Restricted Python bruker, og kjører det der. Derfor er det ikke hele R du har tilgang til, men en dialekt: tidyverse-formen for det som kan uttrykkes trygt.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Du vil</th><th>Skriv</th><th>Virker</th></tr></thead>
      <tbody>
        <tr><td>Gruppere og oppsummere</td><td><code>df |&gt; group_by(kjonn) |&gt; summarise(m = mean(lonn))</code></td><td>Ja</td></tr>
        <tr><td>Filtrere</td><td><code>df |&gt; filter(alder &gt;= 40)</code></td><td>Ja</td></tr>
        <tr><td>Ny kolonne</td><td><code>df |&gt; mutate(logl = log(lonn))</code></td><td>Ja</td></tr>
        <tr><td>Se på dataene</td><td><code>head(df)</code></td><td>Nei</td></tr>
        <tr><td>Regresjon</td><td><code>lm(lonn ~ alder + kjonn, data = df)</code></td><td>Ja</td></tr>
        <tr><td>Egen funksjon</td><td><code>sapply(df, function(x) …)</code></td><td>Nei — vilkårlig kode</td></tr>
      </tbody>
    </table>
    <p class="overview-hint">Røroperatoren <code>|&gt;</code> og <code>%&gt;%</code> forstås begge.</p>
  </div>

  <h3>Det som virker</h3>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge badge-r">r</span></span>
      <pre><code>df |&gt; group_by(kjonn) |&gt; summarise(m = mean(lonn), n = n())</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">  m  n
1  520 790  2 530
2  518 450  2 470</pre>
    </div>
  </div>

  <h3>Det som ikke finnes</h3>
  <p>Base-R-funksjoner som viser rader er ikke en del av dialekten. Meldingen sier hvilken funksjon det gjelder, ikke hva som var i dataene.</p>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge badge-r">r</span></span>
      <pre><code>head(df)</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">Avvist (DisclosureError): base-R function 'head' is not supported in safepy's R dialect</pre>
    </div>
  </div>

  <div class="callout">
    <strong>Samme kjerne, samme regler.</strong> Alt i <a href="#strict-py">Restricted Python</a> sin «Hva som aldri er lov» gjelder her også — bare uttrykt i R. Rangering, radidentifiserende reduksjoner og vilkårlige funksjoner er stengt av samme grunn.
  </div>
</section>

<section id="strict-sql">
  <h2>Restricted SQL</h2>
  <p>SQL er den tredje dialekten inn i den samme kjernen. <code>SELECT</code> med <code>GROUP BY</code> virker; alt som ville returnert rader gjør ikke.</p>

  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge">sql</span></span>
      <pre><code>SELECT kjonn, avg(lonn) AS m, count(*) AS n
FROM df GROUP BY kjonn ORDER BY kjonn</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">  m  n
1  520 790  2 530
2  518 450  2 470</pre>
    </div>
  </div>

  <table class="doc-table">
    <thead><tr><th>Konstruksjon</th><th>Virker</th></tr></thead>
    <tbody>
      <tr><td><code>SELECT … GROUP BY</code> med aggregatfunksjoner</td><td>Ja</td></tr>
      <tr><td><code>WHERE</code>-filtre</td><td>Ja</td></tr>
      <tr><td><code>JOIN</code> mellom kilder på samme nivå</td><td>Ja</td></tr>
      <tr><td><code>ORDER BY</code> på et aggregat</td><td>Ja — og verdt å bruke: uten den er radrekkefølgen tilfeldig</td></tr>
      <tr><td><code>SELECT *</code> uten aggregering</td><td>Nei — det er rader</td></tr>
      <tr><td><code>LIMIT</code> som utvalgsmekanisme</td><td>Nei</td></tr>
      <tr><td><code>ORDER BY</code> etterfulgt av radhenting</td><td>Nei</td></tr>
    </tbody>
  </table>
</section>
```

- [ ] **Step 4: Skriv den engelske versjonen**

Samme i `hjelp.en.html`.

- [ ] **Step 5: Fjern xfail-markøren på lenketesten**

Task 4 la inn `test_ingen_hengende_interne_lenker` merket
`@pytest.mark.xfail(strict=True, reason="Tasks 5-7 legger til #tillit,
#kilder, #strict-py, #strict-r")`. Denne tasken lander den siste av de fire
id-ene (`#strict-r`), så markøren skal bort nå.

Fordi den er `strict=True`, blir testen rapportert som **FEIL** når den
begynner å passere med markøren på — det er hele poenget, og det er
signalet ditt. Fjern dekoratøren og `pytest`-importen hvis den ikke brukes
til noe annet.

- [ ] **Step 6: Kjør testene**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -v`
Expected: alle PASS, ingen xfail, ingen xpass.

- [ ] **Step 7: Commit**

```bash
git add hjelp.html hjelp.en.html tests/test_hjelp.py
git commit -m "docs(hjelp): Restricted R og Restricted SQL får egne seksjoner

R-koden oversettes og kjøres aldri direkte — det står nå eksplisitt, med
kjørte eksempler for både det som virker og det som avvises."
```

---

## Task 8: safestat — federerte kilder og nøkkellager

**Files:**
- Modify: `hjelp.html` (skriv om `<section id="federert">`, ny `<section id="nokler">`)
- Modify: `hjelp.en.html`
- Test: `tests/test_hjelp.py` (utvid)

**Interfaces:**
- Consumes: `overview`-klassen, `illustration`-klassen fra Task 2.
- Produces: seksjons-id-ene `federert` og `nokler`.

Federerte eksempler krever flere noder og kan ikke kjøres av harnessen fra
Task 1. De merkes derfor `class="result illustration"` med ordet
«illustrasjon» synlig — se den globale regelen.

- [ ] **Step 1: Utvid testen**

```python
def test_ikke_kjorte_resultater_er_merket():
    """Et resultat som ikke kommer fra harnessen skal bære klassen
    'illustration' OG ordet «illustrasjon» synlig for leseren. Ellers ser
    oppdiktede tall ut som kjørt output."""
    text = read("hjelp.html")
    for blokk in re.findall(r'<pre class="result illustration">(.*?)</pre>',
                            text, re.DOTALL):
        pass  # innholdet er fritt; kravet gjelder merkingen rundt
    for m in re.finditer(r'<section id="(federert|nokler)".*?</section>',
                         text, re.DOTALL):
        seksjon = m.group(0)
        for res in re.findall(r'<pre class="result([^"]*)">', seksjon):
            assert "illustration" in res, (
                f"resultatblokk i #{m.group(1)} er ikke merket som illustrasjon")
        if 'class="result illustration"' in seksjon:
            assert "illustrasjon" in seksjon.lower(), (
                f"#{m.group(1)} mangler synlig «illustrasjon»-merking")


def test_federert_og_nokler_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("federert", "nokler"):
        assert s in ids, f"mangler seksjon #{s}"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -k "federert or nokler or merket" -v`
Expected: FAIL — `mangler seksjon #nokler`

- [ ] **Step 3: Verifiser federeringsverbene**

```bash
.venv/bin/python -m pytest tests/test_federate_combine.py tests/test_federate_stats.py -v 2>&1 | tail -20
grep -noE "(tabulate|summarize|regress|logit)" docs/superpowers/specs/2026-07-29-federated-sources-design.md | head
```

Bruk bare verb som faktisk er implementert. Spec-en for federerte kilder
oppgir `tabulate`, `summarize`, `regress` og `logit` som eksakte; `overlap`
og trusted-hub er bevisst ikke bygget og skal beskrives som fraværende, ikke
utelates.

- [ ] **Step 4: Skriv seksjonene**

```html
<section id="federert">
  <h2>Federerte kilder</h2>
  <p>Noen ganger kan ikke dataene flyttes — de ligger hos flere eiere som hver har lov til å se sitt eget, men ingen har lov til å se alt. Federering løser det ved å sende <em>spørsmålet</em> til hver node og bare hente tilbake aggregatene.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Verb</th><th>Hva noden regner ut</th><th>Eksakt på tvers av noder</th></tr></thead>
      <tbody>
        <tr><td><code>tabulate</code></td><td>Frekvenser per celle</td><td>Ja — cellene summeres</td></tr>
        <tr><td><code>summarize</code></td><td>Sum, antall, kvadratsum</td><td>Ja — gjennomsnitt og varians rekonstrueres</td></tr>
        <tr><td><code>regress</code></td><td>Kryssproduktmatriser</td><td>Ja — normalligningene løses sentralt</td></tr>
        <tr><td><code>logit</code></td><td>Gradienter per iterasjon</td><td>Ja — iterasjonene koordineres</td></tr>
      </tbody>
    </table>
    <p class="overview-hint">«Eksakt» betyr at svaret er identisk med det du ville fått om alle dataene lå i én tabell.</p>
  </div>

  <h3>Slik ser det ut</h3>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge badge-py">py</span></span>
      <pre><code># options.profile = strict
# data: node_oslo, node_bergen
fed.summarize("lonn", by="kjonn")</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat <span class="illustration-tag">illustrasjon</span></span>
      <pre class="result illustration">kjonn  n      mean(lonn)
1      12 430  521 400
2      11 980  518 100

2 noder svarte. Ingen rader forlot noen node.</pre>
    </div>
  </div>
  <p>Blokken over er en <strong>illustrasjon</strong>: federering krever flere kjørende noder, så den kan ikke genereres av eksempel-harnessen slik de andre resultatene på denne siden kan.</p>

  <h3>Det som ikke finnes ennå</h3>
  <table class="doc-table">
    <thead><tr><th>Mangler</th><th>Konsekvens</th></tr></thead>
    <tbody>
      <tr><td>Trusted hub</td><td>Ingen mellomledd som kan se delresultater. Alt koordineres av klienten din.</td></tr>
      <tr><td><code>overlap</code></td><td>Du kan ikke spørre om hvor mange individer som finnes i to noder samtidig.</td></tr>
    </tbody>
  </table>
</section>

<section id="nokler">
  <h2>Nøkkellager</h2>
  <p>Krypterte datasett trenger en nøkkel. Nøkkellageret holder dine, knyttet til kontoen din, slik at du ikke må lime inn den samme nøkkelen hver gang.</p>
  <table class="doc-table">
    <thead><tr><th>Handling</th><th>Hvor det skjer</th><th>Hva serveren ser</th></tr></thead>
    <tbody>
      <tr><td>Legge inn en nøkkel</td><td>Nettleseren krypterer før sending</td><td>Bare den krypterte formen</td></tr>
      <tr><td>Låse opp et datasett</td><td>Nettleseren, etter å ha hentet nøkkelen</td><td>Ingenting av innholdet</td></tr>
      <tr><td>Synkronisere mellom enheter</td><td>Via kontoen din</td><td>Bare den krypterte formen</td></tr>
    </tbody>
  </table>
  <div class="callout">
    <strong>Mister du hovedpassordet, er nøklene borte.</strong> Serveren kan ikke gjenopprette dem — det er hele poenget med at den aldri ser dem i klartekst.
  </div>
</section>
```

- [ ] **Step 5: Skriv den engelske versjonen**

Samme i `hjelp.en.html`. I engelsk versjon er den synlige merkingen ordet
`illustration`; juster testen i Task 17 tilsvarende.

- [ ] **Step 6: Kjør testene**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -v`
Expected: alle PASS.

- [ ] **Step 7: Commit**

```bash
git add hjelp.html hjelp.en.html tests/test_hjelp.py
git commit -m "docs(hjelp): federerte kilder og nøkkellager

Med en verbtabell som sier hvilke som er eksakte, og en eksplisitt liste
over det som ikke finnes ennå (trusted hub, overlap). Federerte resultater
er merket som illustrasjon — de kan ikke kjøres av harnessen."
```

---

## Task 9: safestat — lag 2 og lag 3 i SYNC-blokker

**Files:**
- Modify: `hjelp.html` (pakk inn og skriv om seksjonene `editor`, `sidebar`, `lagre-dele`, `forklar`, `widgets`, `ai`, `tab-full`; ny `eksempler`; modustabell i `modes`)
- Modify: `hjelp.en.html`
- Modify: `tests/test_hjelp_sync.py` (fjern `# Task 9`-kommentarene)
- Test: `tests/test_hjelp.py` (utvid)

**Interfaces:**
- Consumes: SYNC-markørformen fra Task 3.
- Produces: SYNC-blokkene `felles-editor`, `felles-sidebar`, `felles-lagre`, `felles-forklar`, `felles-widgets`, `felles-ai`, `felles-eksempler`, `felles-referanse-snarveier`, `felles-referanse-tab` — kopieres ordrett av Task 11, 13, 15.

Innholdet i disse blokkene må være **repo-nøytralt**: ingen appnavn, ingen
henvisning til microdata-modus eller strict, ingen ledesetning. Alt
repo-spesifikt hører i lag 0, modustabellen eller lag 1.

- [ ] **Step 1: Utvid testen**

Legg til i `tests/test_hjelp.py`:

```python
SYNC_BLOKKER = [
    "felles-css", "felles-js", "felles-editor", "felles-sidebar",
    "felles-lagre", "felles-forklar", "felles-widgets", "felles-ai",
    "felles-eksempler", "felles-referanse-snarveier", "felles-referanse-tab",
]

APPNAVN = ["SafeStat", "OpenStat", "AskStat", "Microdata"]


def _block(text, name):
    pat = (r"(?:/\*|<!--)\s*SYNC:START\s+" + re.escape(name)
           + r"\s*(?:\*/|-->)(.*?)(?:/\*|<!--)\s*SYNC:END\s*(?:\*/|-->)")
    m = re.search(pat, text, re.DOTALL)
    return m.group(1) if m else None


@pytest.mark.parametrize("navn", SYNC_BLOKKER)
def test_sync_blokk_finnes(navn):
    assert _block(read("hjelp.html"), navn) is not None, f"mangler {navn}"


@pytest.mark.parametrize("navn", SYNC_BLOKKER)
def test_sync_blokk_er_repo_noytral(navn):
    """En fellesblokk skal ikke nevne et appnavn — da kan den ikke deles."""
    blokk = _block(read("hjelp.html"), navn)
    assert blokk is not None
    for navn_app in APPNAVN:
        assert navn_app not in blokk, (
            f"{navn} nevner «{navn_app}»; flytt det til lag 0 eller lag 1")


def test_modustabell_finnes_og_er_utenfor_sync():
    """Modustabellen er repo-spesifikk og skal IKKE ligge i en SYNC-blokk."""
    text = read("hjelp.html")
    m = re.search(r'<section id="modes".*?</section>', text, re.DOTALL)
    assert m, "fant ikke modes-seksjonen"
    blokk = m.group(0)
    assert 'class="doc-table"' in blokk, "modes mangler tabell"
    assert "SYNC:START" not in blokk, "modustabellen skal ikke være i en SYNC-blokk"
    # safestat har microdata og safestat (remote) i tillegg til de sju vanlige.
    for modus in ("microdata", "Python", "R", "DuckDB", "Brython",
                  "MicroPython", "SafeStat"):
        assert modus in blokk, f"modustabellen mangler «{modus}»"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `.venv/bin/python -m pytest tests/test_hjelp.py -k "sync_blokk or modustabell" -v`
Expected: FAIL — `mangler felles-editor`

- [ ] **Step 3: Skriv modustabellen (utenfor SYNC)**

Erstatt `<section id="modes">` sitt innhold med en tabell bygget fra
`modeRegistry` i `index.html`. Hent den faktiske lista først:

```bash
ln=$(grep -noE "modeRegistry\s*=\s*\{" index.html | head -1 | cut -d: -f1)
awk -v s="$ln" 'NR>=s && NR<=s+400' index.html | grep -E "^\s{6}[a-z]+:\s*\{"
```

```html
<section id="modes">
  <h2>Moduser</h2>
  <p>Samme editor, samme datasett — ni språk. Modusen bestemmer hvilken motor som kjører koden, og hvilke knapper som vises.</p>
  <table class="doc-table">
    <thead><tr><th>Modus</th><th>Motor</th><th>Bruk den når</th></tr></thead>
    <tbody>
      <tr><td><strong>Python</strong></td><td>Pyodide</td><td>Du vil ha pandas, statsmodels og hele det vanlige økosystemet</td></tr>
      <tr><td><strong>R</strong></td><td>WebR</td><td>Du tenker i tidyverse, eller trenger en R-pakke</td></tr>
      <tr><td><strong>SQL – DuckDB</strong></td><td>DuckDB</td><td>Spørsmålet er en spørring, ikke et skript</td></tr>
      <tr><td><strong>Brython</strong></td><td>Brython</td><td>Du vil starte raskt og holder deg til Python-kjernen</td></tr>
      <tr><td><strong>MicroPython</strong></td><td>MicroPython</td><td>Du vil starte nesten umiddelbart</td></tr>
      <tr><td><strong>microdata</strong></td><td>m2py</td><td>Du skriver microdata.no-kommandoer</td></tr>
      <tr><td><strong>SafeStat</strong></td><td>Fjernkjøring</td><td>Dataene er beskyttet og kan ikke lastes ned</td></tr>
    </tbody>
  </table>
  <p>Restriktiv kjøring gjelder Python, R og SQL — se <a href="#strict-py">Restricted Python</a>.</p>
</section>
```

Rett tabellen mot den faktiske `modeRegistry`-lista fra kommandoen over
før du limer inn. Nevner tabellen en modus som ikke finnes i registeret,
eller mangler en som gjør det, er tabellen feil.

- [ ] **Step 4: Pakk lag 2 i SYNC-blokker**

For hver av seksjonene `editor`, `sidebar`, `lagre-dele`, `forklar`,
`widgets`, `ai` — sett `<!-- SYNC:START felles-<navn> -->` rett før
`<section …>` og `<!-- SYNC:END -->` rett etter `</section>`. Blokknavnene
er `felles-editor`, `felles-sidebar`, `felles-lagre`, `felles-forklar`,
`felles-widgets`, `felles-ai`.

Gå gjennom teksten i hver og fjern alt repo-spesifikt:
- Erstatt «Script Runner», «SafeStat», «m2py» med «appen» eller en nøytral omskriving
- Flytt setninger om microdata-kommandoer eller strict ut av blokken og inn i lag 1
- La tastatursnarveier, panelbeskrivelser og lagringsflyt stå — de er faktisk felles

- [ ] **Step 5: Legg til eksempler-seksjonen**

Ny seksjon, i SYNC-blokk `felles-eksempler`, plassert etter `#ai`:

```html
<!-- SYNC:START felles-eksempler -->
<section id="eksempler">
  <h2>Eksempler</h2>
  <p>Knappen <strong>Eksempler</strong> åpner en liste som er filtrert på modusen du står i. Listen bygges av appen selv, så den viser alltid det som faktisk finnes.</p>
  <table class="doc-table">
    <thead><tr><th>Du vil</th><th>Gjør</th></tr></thead>
    <tbody>
      <tr><td>Se hva som er mulig i denne modusen</td><td>Trykk <strong>Eksempler</strong></td></tr>
      <tr><td>Starte fra et eksempel</td><td>Velg det — det erstatter innholdet i editoren</td></tr>
      <tr><td>Beholde det du har skrevet</td><td>Lagre først; eksempelet overskriver editoren</td></tr>
    </tbody>
  </table>
</section>
<!-- SYNC:END -->
```

- [ ] **Step 6: Del referansen i to SYNC-blokker**

Pakk snarveistabellen i `felles-referanse-snarveier` og
`<section id="tab-full">` i `felles-referanse-tab`. Er snarveiene i dag
en del av `#editor`, flytt tabellen ned i referansedelen og la `#editor`
beholde prosaen — referansetabeller hører i lag 3.

- [ ] **Step 7: Gjenta i hjelp.en.html — og ta igjen etterslepet**

Samme blokker, samme navn, engelsk tekst. Blokkene er identiske *innad i
et språk* — `hjelp.html` sammenlignes mot søsknenes `hjelp.html`, og
`hjelp.en.html` mot deres `hjelp.en.html`.

**Den engelske fila ligger tre tasks etter, og det er her den innhentes.**
Task 2 la layoutlaget bare i den norske; Task 4 ga den engelske ny identitet,
men lot brødteksten stå. Resultatet er en side som heter «SafeStat» i tittelen
og forteller om «Script Runner ... microdata.no» i første avsnitt. Denne
steppen lukker hele etterslepet:

1. **`felles-css` og `felles-js`** — port begge SYNC-blokkene fra
   `hjelp.html` til `hjelp.en.html`, ordrett. Uten dem har den engelske siden
   verken scrollspy, navfilter, kopier-knapp eller styling for `.overview` og
   `.example` — og synk-sjekken i streng modus vil felle den.
2. **Lag 0** — oversett `#intro` og `#hurtigstart` fra Task 4, inkludert
   oversiktstabellen og hurtigstart-eksempelet. Resultatblokken er
   byte-identisk med den norske (tall er tall).
3. **Lag 1** — oversett seksjonene fra Task 5–8 (`#tillit`, `#kilder`,
   `#strict-py`, `#strict-r`, `#strict-sql`, `#federert`, `#nokler`).
   Metodenavn, feilmeldinger, profilnavn (OPEN/STRICT), nivånavn
   (public/protected/sensitive) og resultatblokker er identiske i begge
   språk — bare prosaen oversettes.
4. **Fjern gammel norsk-avledet prosa** som ikke lenger stemmer, særlig
   avsnitt som beskriver appen som en microdata.no-kjører.

Verifiser til slutt at `grep -c "Script Runner" hjelp.en.html` gir 0, og at
`test_identitet_engelsk` fortsatt passerer.

- [ ] **Step 8: Fjern Task 9-kommentarene i synk-testen**

I `tests/test_hjelp_sync.py`, avkommenter blokknavnene i `BLOCK_NAMES`
som ble satt på vent i Task 3.

**Og redd `test_streng_modus_avviser_manglende_enkeltblokk` fra å bli tom.**
Den bygger i dag sitt testtilfelle ved å velge et blokknavn safestat *ikke*
har. Når du fyller inn alle elleve, finnes ikke et slikt navn lenger, og
testen selv-skipper — den mister altså dekning nøyaktig når blokkene den
skal vokte endelig eksisterer. Bygg den om: lag det manglende tilfellet ved
å *fjerne* en blokk fra en kopi av `hjelp.html`, og fjerne den samme fra det
falske søskenet, i stedet for å lete etter en som allerede mangler. Kjør
`.venv/bin/python -m pytest tests/test_hjelp_sync.py -v` og bekreft at den
kjører — ikke skipper.

- [ ] **Step 9: Kjør alt**

Run:
```bash
.venv/bin/python -m pytest tests/test_hjelp.py tests/test_hjelp_sync.py -v
node --test tests/js/test_hjelp_ui.mjs
sh scripts/hjelp_sync_check.sh
```
Expected: pytest og node PASS. Synk-skriptet melder avvik mot søsknene —
det er forventet nå og rettes i Task 11, 13, 15.

- [ ] **Step 10: Commit**

```bash
git add hjelp.html hjelp.en.html tests/test_hjelp.py tests/test_hjelp_sync.py
git commit -m "docs(hjelp): lag 2 og 3 pakket i SYNC-blokker, modustabell fra registeret

Fellesseksjonene er nå repo-nøytrale og avgrenset, klare til å kopieres.
Modustabellen er bevisst utenfor — den er bygget fra modeRegistry og
skiller seg per repo. En test håndhever at ingen fellesblokk nevner et
appnavn."
```

---

## Task 10: safestat — sluttsjekk i nettleseren

**Files:**
- Modify: `hjelp.html`, `hjelp.en.html` (rettelser funnet under sjekken)

**Interfaces:**
- Consumes: alt fra Task 1–9.
- Produces: ingen nye grensesnitt.

Ingen test her; dette er den manuelle kontrollen som fanger det tester
ikke ser — at siden faktisk er lesbar og at scrollspy, filter og
kopier-knapp virker.

- [ ] **Step 1: Start en lokal server**

```bash
netlify dev
```

Verifiseringsfellen gjelder: Chrome cacher `js/` over HTTP, og
`netlify dev` cacher edge-TS-moduler. Bruk hard-reload med ignoreCache.

- [ ] **Step 2: Gå gjennom sjekklista**

Åpne `http://localhost:8888/hjelp.html` og verifiser:

- [ ] Tittel i fanen sier «SafeStat – Dokumentasjon»
- [ ] Sidemenyen uthever seksjonen du er i når du ruller
- [ ] Filterfeltet skjuler lenker som ikke matcher, og skjuler tomme gruppeoverskrifter
- [ ] Kopier-knappen dukker opp på kodeblokker og sier «Kopiert» etter klikk
- [ ] Eksempelblokkene står side om side; krymp vinduet under 900 px og se at de stables
- [ ] Ingen horisontal rulling på body i noen bredde
- [ ] Dark mode: bytt systemtema og se at kontrasten holder i tabeller, `callout` og eksempelblokker
- [ ] Alle interne lenker i «Denne siden dekker» treffer en seksjon som finnes
- [ ] **Offline:** slå av nettverket i DevTools (Network → Offline), hard-reload,
      og se at siden fortsatt rendrer fullstendig — scrollspy, filter og
      kopier-knapp inkludert. Ingen forespørsel skal gå til en ekstern vert —
      sjekk at ingen ressurs lastes utenfra:
      `grep -noE '(src|href)="https?://[^"]*|url\(https?://[^)]*' hjelp.html hjelp.en.html`
      skal bare treffe `href` på vanlige prosalenker (som microdata.no), aldri
      en `<script src>`, `<link href>` eller `url(...)`.
- [ ] Samme runde på `hjelp.en.html`

- [ ] **Step 3: Rett det som ble funnet, og commit**

```bash
git add hjelp.html hjelp.en.html
git commit -m "fix(hjelp): rettelser fra nettlesergjennomgang av safestat"
```

---

## Task 11: openstat — fellesdel, motormatrise, og microdata ut

**Files:**
- Modify: `../openstat/hjelp.html`, `../openstat/hjelp.en.html`
- Create: `../openstat/tests/test_hjelp.py`, `../openstat/scripts/hjelp_sync_check.sh`
- Create: `../openstat/tests/js/test_hjelp_ui.mjs`

**Interfaces:**
- Consumes: SYNC-blokkene fra Task 9 (kopieres ordrett fra safestat).
- Produces: openstat sin lag 0 og lag 1. Ingenting senere avhenger av dette.

openstat sin hjelpeside har i dag «Microdata-kommandoer» som tredje
seksjon. Modusen ble fjernet fra openstat 2026-07-24 — seksjonen skal ut,
ikke skrives om.

- [ ] **Step 1: Skriv den feilende testen**

Opprett `../openstat/tests/test_hjelp.py` som en kopi av safestat sin, med
disse endringene i `IDENTITY` og to nye tester:

```python
IDENTITY = {
    "openstat": {
        "title_no": "OpenStat – Dokumentasjon",
        "title_en": "OpenStat – Documentation",
        "h1": "OpenStat",
        "nav_logo": "OpenStat",
        "lead_no": "Sju analysemotorer i nettleseren, samme datasett.",
    },
}

FORBUDT_OVERALT = ["Microdata Script Runner"]


def test_ingen_microdata_modus_seksjon():
    """microdata-modus ble fjernet fra openstat 2026-07-24. Hjelpesiden skal
    ikke lenger dokumentere den som eksisterende."""
    ids = grab("hjelp.html").section_ids
    assert "microdata" not in ids, "openstat dokumenterer fortsatt microdata-modus"
    text = read("hjelp.html")
    assert "Microdata-kommandoer" not in text


def test_motormatrise_dekker_alle_moduser_i_registeret():
    """Modustabellen skal navngi hver modus i modeRegistry — ikke flere,
    ikke færre."""
    text = read("hjelp.html")
    m = re.search(r'<section id="modes".*?</section>', text, re.DOTALL)
    assert m, "fant ikke modes-seksjonen"
    blokk = m.group(0)
    for modus in ("Python", "R", "DuckDB", "Brython", "MicroPython",
                  "JavaScript", "jamovi"):
        assert modus in blokk, f"motormatrisen mangler «{modus}»"
    assert "Statx" not in blokk, "Statx ble fjernet fra openstat 2026-07-24"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `cd ../openstat && python3 -m pytest tests/test_hjelp.py -v`
Expected: FAIL — `openstat dokumenterer fortsatt microdata-modus`

- [ ] **Step 3: Kopier fellesdelen fra safestat**

For hver SYNC-blokk: hent blokken fra `../safestat/hjelp.html` og sett den
inn på tilsvarende plass i `openstat/hjelp.html`, med markørene. Samme for
`hjelp.en.html`. Kopier også:

```bash
cp ../safestat/scripts/hjelp_sync_check.sh scripts/
cp ../safestat/tests/js/test_hjelp_ui.mjs tests/js/
chmod +x scripts/hjelp_sync_check.sh
```

I `scripts/hjelp_sync_check.sh`, endre `SIBLINGS` til
`safestat askstat microdata`.

- [ ] **Step 4: Fjern microdata-seksjonen**

Slett `<section id="microdata">` … `</section>` (i dag rundt linje 240) og
tilsvarende nav-lenke. Sjekk om andre seksjoner viser til den:

```bash
grep -n "#microdata\|Microdata-kommandoer\|microdata-modus" hjelp.html hjelp.en.html
```

Rett hver treff — enten fjern setningen, eller vis til søskenrepoet
`microdata` der modusen faktisk finnes.

- [ ] **Step 5: Mål oppstartstidene**

Motormatrisen skal oppgi faktiske tall, ikke anslag. Start
`netlify dev`, åpne appen, og mål tiden fra modusbytte til første kjørte
resultat per motor. Noter tallene og bruk dem i tabellen. Får du ikke målt
en motor, la kolonnen stå tom for den framfor å gjette.

- [ ] **Step 6: Skriv lag 0 og motormatrisen**

```html
<section id="intro">
  <h2>Hva er dette?</h2>
  <p>OpenStat er sju analysemotorer i samme nettleserfane. Du velger språk etter hva oppgaven trenger — ikke etter hva som er installert, for ingenting er installert.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Del</th><th>Hva du finner der</th></tr></thead>
      <tbody>
        <tr><td><a href="#modes">Motorvalget</a></td><td>De sju motorene, oppstartstid, og når du velger hvilken</td></tr>
        <tr><td><a href="#direktiver">Datadirektiver</a></td><td>Hente og montere data med én linje</td></tr>
        <tr><td><a href="#api">API-kataloger</a></td><td>SSB, Eurostat, OECD og de andre kildene</td></tr>
        <tr><td><a href="#hybrid">Hybridskript</a></td><td>Flere språk i samme skript</td></tr>
        <tr><td><a href="#tab-full">Referanse</a></td><td>Snarveier, direktiver, Tab-autocomplete</td></tr>
      </tbody>
    </table>
  </div>
</section>

<section id="hurtigstart">
  <h2>30 sekunder</h2>
  <p>Appen starter i Brython — den raskeste veien til et resultat. Lim inn og trykk <kbd>Ctrl</kbd>+<kbd>Enter</kbd>:</p>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge badge-py">py</span></span>
      <pre><code>print(sum(range(1, 101)))</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result">5050</pre>
    </div>
  </div>
  <p>Bytt til <strong>Python</strong> i modusmenyen om du trenger pandas. <a href="#modes">Motorvalget</a> forklarer avveiningen.</p>
</section>
```

Modustabellen (utenfor SYNC), med målte tall fra Step 5:

```html
<section id="modes">
  <h2>Motorvalget</h2>
  <p>Alle sju kjører i nettleseren din. Forskjellen er hvor lang tid de bruker på å starte, og hvor mye de har med seg.</p>
  <table class="doc-table">
    <thead><tr><th>Motor</th><th>Oppstart</th><th>Har med seg</th><th>Velg den når</th></tr></thead>
    <tbody>
      <tr><td><strong>MicroPython</strong></td><td>~18 ms</td><td>Python-kjernen, ingen tredjepartsbibliotek</td><td>Du vil ha svar umiddelbart og trenger ikke pandas</td></tr>
      <tr><td><strong>Brython</strong></td><td>MÅLT VERDI</td><td>Python-kjernen, et utvalg lette bibliotek</td><td>Standardvalget — rask start, nok bibliotek</td></tr>
      <tr><td><strong>JavaScript</strong></td><td>MÅLT VERDI</td><td>Alt nettleseren har</td><td>Du vil manipulere siden, eller kjenner JS best</td></tr>
      <tr><td><strong>SQL – DuckDB</strong></td><td>MÅLT VERDI</td><td>DuckDB med Parquet- og CSV-lesing</td><td>Spørsmålet er en spørring, ikke et skript</td></tr>
      <tr><td><strong>Python</strong></td><td>MÅLT VERDI</td><td>pandas, numpy, statsmodels, scipy, matplotlib, seaborn, sklearn</td><td>Du trenger det virkelige økosystemet</td></tr>
      <tr><td><strong>R</strong></td><td>MÅLT VERDI</td><td>Ekte R via WebR, ikke oversatt</td><td>Du tenker i R, eller trenger en R-pakke</td></tr>
      <tr><td><strong>jamovi</strong></td><td>MÅLT VERDI</td><td>Dialogbasert analyse på ekte jmv</td><td>Du vil klikke deg fram, ikke skrive kode</td></tr>
    </tbody>
  </table>
  <p class="overview-hint">Tallene er målt i Chrome på en laptop, fra modusbytte til første resultat. De varierer med maskin og nettverk.</p>
</section>
```

- [ ] **Step 7: Rett identiteten og skriv engelsk versjon**

`<title>`, `<h1>`, `nav-logo` og lead er allerede riktige i openstat
(«OpenStat»), men kontroller `nav-logo` — den sa «Script Runner»:

```bash
grep -n 'class="nav-logo"' hjelp.html hjelp.en.html
```

- [ ] **Step 8: Kjør alt**

Run:
```bash
python3 -m pytest tests/test_hjelp.py -v
node --test tests/js/test_hjelp_ui.mjs
sh scripts/hjelp_sync_check.sh
```
Expected: pytest og node PASS. Synk-skriptet skal nå melde at safestat og
openstat stemmer, og hoppe over eller klage på askstat/microdata — de er
ikke gjort ennå.

- [ ] **Step 9: Commit**

```bash
git add hjelp.html hjelp.en.html tests/ scripts/hjelp_sync_check.sh
git commit -m "docs(hjelp): openstat leder med motorvalget, microdata-seksjonen ut

Siden dokumenterte fortsatt microdata-modus, som ble fjernet 24. juli.
Erstattet med en motormatrise over de sju som faktisk finnes, med målte
oppstartstider. Fellesseksjonene er kopiert fra safestat."
```

---

## Task 12: openstat — sluttsjekk i nettleseren

**Files:**
- Modify: `../openstat/hjelp.html`, `../openstat/hjelp.en.html`

- [ ] **Step 1: Kjør sjekklista fra Task 10**

Samme åtte punkter, men tittelen skal si «OpenStat – Dokumentasjon», og
kontroller i tillegg:

- [ ] Ingen lenke peker på `#microdata`
- [ ] Motormatrisen har et tall eller en tom celle i hver rad — ingen «MÅLT VERDI» igjen

Run: `grep -n "MÅLT VERDI" hjelp.html hjelp.en.html` → ingen treff.

- [ ] **Step 2: Rett og commit**

```bash
git add hjelp.html hjelp.en.html
git commit -m "fix(hjelp): rettelser fra nettlesergjennomgang av openstat"
```

---

## Task 13: askstat — fellesdel og hele ask-laget

**Files:**
- Modify: `../askstat/hjelp.html`, `../askstat/hjelp.en.html`, `../askstat/README.md`
- Create: `../askstat/tests/test_hjelp.py`, `../askstat/scripts/hjelp_sync_check.sh`, `../askstat/tests/js/test_hjelp_ui.mjs`

**Interfaces:**
- Consumes: SYNC-blokkene fra Task 9.
- Produces: askstat sin lag 0 og lag 1.

askstat sin hjelpeside heter i dag «OpenStat» og nevner ikke ask med et
ord. Dette er den største mangelen i hele planen.

- [ ] **Step 1: Skriv den feilende testen**

Opprett `../askstat/tests/test_hjelp.py`, som safestat sin, med:

```python
IDENTITY = {
    "askstat": {
        "title_no": "AskStat – Dokumentasjon",
        "title_en": "AskStat – Documentation",
        "h1": "AskStat",
        "nav_logo": "AskStat",
        "lead_no": "Spør på norsk, få kode og svar fra offentlig statistikk.",
    },
}

FORBUDT_OVERALT = ["Microdata Script Runner", "OpenStat"]

ASK_RUTER = ["beregning", "data", "oppslag", "språk"]


def test_ask_seksjonene_finnes():
    """Det askstat faktisk er, må være dokumentert."""
    ids = grab("hjelp.html").section_ids
    for s in ("ask", "ruter", "kataloger", "proveniens", "byok"):
        assert s in ids, f"mangler seksjon #{s}"


def test_alle_fire_ruter_er_navngitt():
    """Rutene er en lukket liste i js/ask-view.js — alle fire skal beskrives."""
    text = read("hjelp.html")
    m = re.search(r'<section id="ruter".*?</section>', text, re.DOTALL)
    assert m, "fant ikke ruter-seksjonen"
    for rute in ASK_RUTER:
        assert rute in m.group(0), f"ruter-tabellen mangler «{rute}»"


def test_readme_heter_askstat():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert readme.lstrip().startswith("# AskStat"), "README heter fortsatt noe annet"
    assert "OpenStat — browser statistics workbench" not in readme
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `cd ../askstat && python3 -m pytest tests/test_hjelp.py -v`
Expected: FAIL — `hjelp.html inneholder fortsatt «OpenStat»`

- [ ] **Step 3: Kopier fellesdelen fra safestat**

Som Task 11 Step 3. `SIBLINGS` settes til `safestat openstat microdata`.

- [ ] **Step 4: Verifiser rutene og katalogene mot koden**

```bash
grep -n "ASK_ROUTES" js/ask-view.js
grep -rhoE "\b(ssb|eurostat|oecd|worldbank|dbnomics|sdmx|fhi|dst|statfin|apd|pxweb)\b" \
  netlify/edge-functions/_lib/*.ts netlify/edge-functions/*.ts | sort | uniq -c | sort -rn
grep -n "COMMENT_PREFIX\|buildAskProvenance" js/ask-view.js
```

Bruk bare kilder som faktisk er referert. Er en katalog nevnt bare én gang
i én fil, kontroller at den er koblet inn før du dokumenterer den.

- [ ] **Step 5: Skriv lag 0 og ask-laget**

```html
<section id="intro">
  <h2>Hva er dette?</h2>
  <p>AskStat tar et spørsmål på norsk og gir deg to ting: et svar, og koden som kom fram til det. Koden er poenget — du kan lese den, endre den og kjøre den på nytt.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Del</th><th>Hva du finner der</th></tr></thead>
      <tbody>
        <tr><td><a href="#ask">Spørsmålsløkka</a></td><td>De fire stegene fra spørsmål til svar</td></tr>
        <tr><td><a href="#ruter">De fire rutene</a></td><td>Hvordan spørsmålet ditt blir klassifisert, og hva det betyr</td></tr>
        <tr><td><a href="#kataloger">Katalogene</a></td><td>Hvilke datakilder som søkes i</td></tr>
        <tr><td><a href="#proveniens">Proveniens</a></td><td>Hvorfor den genererte koden starter med kommentarer</td></tr>
        <tr><td><a href="#byok">Egen nøkkel</a></td><td>Din API-nøkkel, og hva som skjer med den</td></tr>
        <tr><td><a href="#modes">Moduser</a></td><td>Editoren bak ask-visningen — sju språk</td></tr>
      </tbody>
    </table>
  </div>
</section>

<section id="hurtigstart">
  <h2>30 sekunder</h2>
  <p>Skriv et spørsmål i feltet og trykk <kbd>Enter</kbd>:</p>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Spørsmål</span>
      <pre><code>hvor mange bor i Bergen?</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Svar <span class="illustration-tag">illustrasjon</span></span>
      <pre class="result illustration">Bergen hadde 291 189 innbyggere (SSB tabell 07459, 2024).

  ── ask ── generated by askstat
  Question: hvor mange bor i Bergen?
  Route: oppslag</pre>
    </div>
  </div>
  <p>Blokken over er en <strong>illustrasjon</strong> — et ask-svar avhenger av kilden og av modellen, så det kan ikke låses til en fast tekst slik de kjørbare eksemplene kan. Tallet du får, kommer med sin egen kildehenvisning.</p>
</section>

<section id="ask">
  <h2>Spørsmålsløkka</h2>
  <p>Fire steg, og du ser hvert av dem.</p>
  <table class="doc-table">
    <thead><tr><th>Steg</th><th>Hva som skjer</th><th>Hva du ser</th></tr></thead>
    <tbody>
      <tr><td>1. Ruting</td><td>Spørsmålet klassifiseres i én av fire ruter</td><td>Ruten, og en tolkning av hva spørsmålet betyr operasjonelt</td></tr>
      <tr><td>2. Oppdagelse</td><td>Katalogene søkes for et datasett som kan svare</td><td>Kilden som ble valgt</td></tr>
      <tr><td>3. Kode</td><td>Et skript genereres, med proveniens øverst</td><td>Koden, i python-, r- eller sql-modus</td></tr>
      <tr><td>4. Svar</td><td>Koden kjøres og resultatet tolkes</td><td>Svaret, og resultatet det bygger på</td></tr>
    </tbody>
  </table>
  <div class="callout tip">
    <strong>Fra svar til editor:</strong> trykk <strong>Åpne i editor</strong>, eller legg til <code>?view=editor</code> i adressen. Da får du hele arbeidsbenken med koden lastet inn.
  </div>
</section>

<section id="ruter">
  <h2>De fire rutene</h2>
  <p>Ruten bestemmer hva AskStat gjør med spørsmålet. Er den usikker, faller den tilbake på <code>data</code>.</p>
  <table class="doc-table">
    <thead><tr><th>Rute</th><th>Spørsmålet handler om</th><th>Eksempel</th></tr></thead>
    <tbody>
      <tr><td><code>oppslag</code></td><td>Ett tall som finnes i en tabell</td><td>«hvor mange bor i Bergen?»</td></tr>
      <tr><td><code>data</code></td><td>Å finne og hente et datasett</td><td>«vis befolkning per kommune»</td></tr>
      <tr><td><code>beregning</code></td><td>Noe som må regnes ut fra data</td><td>«hvilken kommune vokste mest fra 2015?»</td></tr>
      <tr><td><code>språk</code></td><td>Kode eller syntaks, ikke data</td><td>«hvordan grupperer jeg i pandas?»</td></tr>
    </tbody>
  </table>
</section>

<section id="kataloger">
  <h2>Katalogene</h2>
  <p>Oppdagelsen søker i flere kataloger samtidig. Tabellen under er de som er koblet inn.</p>
  <table class="doc-table">
    <thead><tr><th>Katalog</th><th>Dekker</th></tr></thead>
    <tbody>
      <tr><td><strong>SSB</strong></td><td>Norsk offisiell statistikk, PxWeb-tabeller</td></tr>
      <tr><td><strong>PxWeb</strong></td><td>Nordiske statistikkbyråer med samme grensesnitt</td></tr>
      <tr><td><strong>SDMX</strong></td><td>Eurostat, OECD og andre som snakker SDMX</td></tr>
      <tr><td><strong>APD</strong></td><td>Aggregert datasettkatalog</td></tr>
      <tr><td><strong>DBnomics</strong></td><td>Økonomiske tidsserier fra mange kilder</td></tr>
      <tr><td><strong>World Bank</strong></td><td>Globale indikatorer</td></tr>
      <tr><td><strong>FHI</strong></td><td>Norske helsedata</td></tr>
      <tr><td><strong>StatFin</strong></td><td>Finsk statistikk</td></tr>
      <tr><td><strong>DST</strong></td><td>Dansk statistikk</td></tr>
    </tbody>
  </table>
  <p class="overview-hint">Rett denne tabellen mot uttrekket i Step 4 — dokumenter bare kataloger som faktisk er koblet inn.</p>
</section>

<section id="proveniens">
  <h2>Proveniens i generert kode</h2>
  <p>Hvert generert skript starter med kommentarer som sier hvor det kom fra. De er vanlige kommentarer, så de påvirker ikke kjøringen — men de gjør at koden kan leses om et halvt år.</p>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Generert kode <span class="badge badge-py">py</span></span>
      <pre><code># ══ ask ══ generated by askstat
# Question: hvor mange bor i Bergen?
# Route: oppslag
# Interpretation: befolkning, Bergen kommune, siste år

df = ost_read_csv("...")
df[df["kommune"] == "Bergen"]["befolkning"]</code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Hva blokken gir deg</span>
      <pre class="result">Spørsmålet du stilte, ordrett.
Ruten som ble valgt.
Tolkningen — hva spørsmålet ble forstått som.

Kommentartegnet følger modusen:
  python, r  →  #
  duckdb     →  --</pre>
    </div>
  </div>
</section>

<section id="byok">
  <h2>Egen nøkkel</h2>
  <p>AskStat trenger en API-nøkkel til språkmodellen. Du oppgir din egen i innstillingene.</p>
  <table class="doc-table">
    <thead><tr><th>Spørsmål</th><th>Svar</th></tr></thead>
    <tbody>
      <tr><td>Hvor lagres nøkkelen?</td><td>Bare i nettleserens <code>localStorage</code></td></tr>
      <tr><td>Ser serveren den?</td><td>Den videresendes til modellen, men lagres ikke</td></tr>
      <tr><td>Lagres spørsmålene mine?</td><td>Nei</td></tr>
      <tr><td>Hva om jeg ikke har nøkkel?</td><td>Ask-visningen trenger en. Editoren virker uten.</td></tr>
    </tbody>
  </table>
  <p>Se <a href="personvern.html">personvernerklæringen</a> for hele bildet.</p>
</section>
```

- [ ] **Step 6: Rett README**

I `README.md`, erstatt de to første avsnittene:

```markdown
# AskStat — spør om offentlig statistikk på norsk

> Søsterprosjekter: [OpenStat](https://github.com/hmelberg/openstat) — den
> generelle arbeidsbenken uten ask-laget — [SafeStat](https://github.com/hmelberg/safestat)
> — full build med innlogging, beskyttede kilder og fjernkjøring — og
> [Microdata](https://github.com/hmelberg/microdata) — microdata.no-emulatoren.
> AskStat er forket fra openstat 2026-07-28 med full historikk.

AskStat tar et spørsmål på norsk, ruter det, finner et datasett i katalogene
(SSB, PxWeb, SDMX, APD, DBnomics og flere), genererer kode med proveniens, og
kjører den. Ask-visningen er default; `?view=editor` gir hele arbeidsbenken.
```

Gå gjennom resten av README og rett hver gjenstående «OpenStat»:

```bash
grep -n "OpenStat" README.md
```

- [ ] **Step 7: Skriv den engelske versjonen**

Samme seksjoner i `hjelp.en.html`. Rutenavnene (`beregning`, `data`,
`oppslag`, `språk`) er identifikatorer i koden og oversettes **ikke** —
forklar dem på engelsk, men behold navnene.

- [ ] **Step 8: Kjør alt**

Run:
```bash
python3 -m pytest tests/test_hjelp.py -v
node --test tests/js/test_hjelp_ui.mjs
sh scripts/hjelp_sync_check.sh
```
Expected: pytest og node PASS. Synk-skriptet stemmer mot safestat og
openstat; microdata gjenstår.

- [ ] **Step 9: Commit**

```bash
git add hjelp.html hjelp.en.html README.md tests/ scripts/hjelp_sync_check.sh
git commit -m "docs(hjelp): askstat får sitt eget navn og hele ask-laget

Hjelpesiden het «OpenStat» og nevnte ikke ask med et ord. Nå:
spørsmålsløkka, de fire rutene, katalogene, proveniens og BYOK. README
het også OpenStat — rettet."
```

---

## Task 14: askstat — sluttsjekk i nettleseren

**Files:**
- Modify: `../askstat/hjelp.html`, `../askstat/hjelp.en.html`

- [ ] **Step 1: Kjør sjekklista fra Task 10**

Tittelen skal si «AskStat – Dokumentasjon». I tillegg:

- [ ] Ordet «OpenStat» finnes ikke i noen av de to filene:
      `grep -n "OpenStat" hjelp.html hjelp.en.html` → ingen treff
- [ ] Still et faktisk spørsmål i ask-visningen og se at løkka oppfører seg
      som dokumentert: rute vises, kode genereres med proveniens, svar kommer
- [ ] Trykk «Åpne i editor» og se at koden følger med

- [ ] **Step 2: Rett og commit**

```bash
git add hjelp.html hjelp.en.html
git commit -m "fix(hjelp): rettelser fra nettlesergjennomgang av askstat"
```

---

## Task 15: microdata — fellesdel og emulatorinnholdet

**Files:**
- Modify: `../microdata/hjelp.html`, `../microdata/hjelp.en.html`
- Create: `../microdata/tests/test_hjelp.py`, `../microdata/scripts/hjelp_sync_check.sh`, `../microdata/tests/js/test_hjelp_ui.mjs`

**Interfaces:**
- Consumes: SYNC-blokkene fra Task 9.
- Produces: microdata sin lag 0 og lag 1.

microdata er den eneste av de fire der `statx` fortsatt står i
`modeRegistry` — den skal dokumenteres her, i motsetning til i openstat.

- [ ] **Step 1: Skriv den feilende testen**

Opprett `../microdata/tests/test_hjelp.py`, som safestat sin, med:

```python
IDENTITY = {
    "microdata": {
        "title_no": "Microdata – Dokumentasjon",
        "title_en": "Microdata – Documentation",
        "h1": "Microdata",
        "nav_logo": "Microdata",
        "lead_no": "Emulator av microdata.no — skriv og kjør microdata-kode.",
    },
}

FORBUDT_OVERALT = ["Microdata Script Runner"]


def test_emulator_seksjonene_finnes():
    ids = grab("hjelp.html").section_ids
    for s in ("kommandoer", "avsloring", "avvik", "oversettere"):
        assert s in ids, f"mangler seksjon #{s}"


def _tabellrader(blokk: str) -> int:
    """Antall rader i <tbody> — en tom tabell er ikke dokumentasjon."""
    m = re.search(r"<tbody>(.*?)</tbody>", blokk, re.DOTALL)
    return len(re.findall(r"<tr>", m.group(1))) if m else 0


def test_avvik_seksjonen_er_konkret():
    """«Avvik fra microdata.no» skal liste faktiske avvik i en tabell — en
    vag ansvarsfraskrivelse hjelper ingen."""
    text = read("hjelp.html")
    m = re.search(r'<section id="avvik".*?</section>', text, re.DOTALL)
    assert m, "fant ikke avvik-seksjonen"
    blokk = m.group(0)
    assert 'class="doc-table"' in blokk, "avvik mangler tabell"
    assert _tabellrader(blokk) >= 2, (
        "avvikstabellen er tom eller har bare én rad — skjelettet er ikke fylt ut")


@pytest.mark.parametrize("seksjon", ["kommandoer", "avsloring", "oversettere"])
def test_emulatortabellene_er_fylt_ut(seksjon):
    """Skjelettene i planen har tomme <tbody>. Testen hindrer at de blir
    stående slik."""
    text = read("hjelp.html")
    m = re.search(rf'<section id="{seksjon}".*?</section>', text, re.DOTALL)
    assert m, f"fant ikke {seksjon}-seksjonen"
    assert _tabellrader(m.group(0)) >= 2, (
        f"#{seksjon} har en tom eller nesten tom tabell")


def test_ingen_html_kommentar_plassholdere():
    """Skjelettenes <!-- … --> skal være erstattet med innhold."""
    for fil in ("hjelp.html", "hjelp.en.html"):
        text = read(fil)
        rester = re.findall(r"<!--\s*(?:Én rad per|Et kort skript|Output kopiert|"
                            r"Faktiske terskler|Ett faktisk avvik|fra py2m|fra r2m|"
                            r"kjørt gjennom|faktisk oversetteroutput)[^>]*-->", text)
        assert not rester, f"{fil} har igjen plassholdere: {rester[:3]}"


def test_statx_er_dokumentert():
    """statx finnes fortsatt i microdata sitt modeRegistry, i motsetning til
    openstat der den ble fjernet."""
    text = read("hjelp.html")
    m = re.search(r'<section id="modes".*?</section>', text, re.DOTALL)
    assert m
    assert "Statx" in m.group(0), "modustabellen mangler Statx"
```

- [ ] **Step 2: Kjør testen for å se at den feiler**

Run: `cd ../microdata && python3 -m pytest tests/test_hjelp.py -v`
Expected: FAIL — `hjelp.html inneholder fortsatt «Microdata Script Runner»`

- [ ] **Step 3: Kopier fellesdelen fra safestat**

Som Task 11 Step 3. `SIBLINGS` settes til `safestat openstat askstat`.

- [ ] **Step 4: Hent avsløringskontroll-reglene fra motoren**

Reglene skal ikke skrives fra hukommelsen. Hent dem:

```bash
grep -noE "(min_pop|MIN_POP|1000|winsor|percentile|suppress)[A-Za-z_]*" m2py.py | head -30
python3 -m pytest tests/ -k "protect or disclosure or profile" -v 2>&1 | tail -20
```

Bygg tabellen «terskel → effekt» fra det du finner, og oppgi de faktiske
tallene.

- [ ] **Step 5: Skriv lag 0 og emulatorinnholdet**

```html
<section id="intro">
  <h2>Hva er dette?</h2>
  <p>En emulator av <a href="https://microdata.no">microdata.no</a>. Du skriver microdata-kommandoer, de oversettes til Python og kjøres i nettleseren mot syntetiske registerdata. Målet er at et skript som virker her, virker der.</p>

  <div class="overview">
    <table class="doc-table">
      <thead><tr><th>Del</th><th>Hva du finner der</th></tr></thead>
      <tbody>
        <tr><td><a href="#kommandoer">Kommandoene</a></td><td>Språket, kommando for kommando</td></tr>
        <tr><td><a href="#avsloring">Avsløringskontroll</a></td><td>Reglene som sensurerer output, og hvordan du skrur dem av</td></tr>
        <tr><td><a href="#avvik">Avvik fra microdata.no</a></td><td>Der emulatoren ikke er tro mot originalen</td></tr>
        <tr><td><a href="#oversettere">py2m og r2m</a></td><td>Python og R inn, microdata ut</td></tr>
        <tr><td><a href="#tab-full">Referanse</a></td><td>Snarveier, autocomplete</td></tr>
      </tbody>
    </table>
  </div>

  <div class="callout">
    <strong>NB:</strong> Dette er et hobbyprosjekt og er ikke laget av microdata.no. Dataene er syntetiske — ingen tall her er ekte.
  </div>
</section>
```

Skriv deretter de fire seksjonene. Skjelettene under fastsetter struktur og
kolonner; innholdet fylles fra uttrekkene, ikke fra hukommelsen.

```html
<section id="kommandoer">
  <h2>Kommandoene</h2>
  <p>microdata-språket er lite med vilje. Hver kommando gjør én ting, og rekkefølgen er den du ville skrevet på papir: hent data, lag variabler, oppsummer.</p>
  <table class="doc-table">
    <thead><tr><th>Kommando</th><th>Gjør</th><th>Eksempel</th></tr></thead>
    <tbody>
      <!-- Én rad per kommando som faktisk finnes i m2py.py. Eksempelkolonnen
           skal være en kjørbar linje, ikke en skisse. -->
    </tbody>
  </table>

  <h3>Et helt skript</h3>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Kode <span class="badge badge-micro">micro</span></span>
      <pre><code><!-- Et kort skript som faktisk er kjørt i appen --></code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">Resultat</span>
      <pre class="result"><!-- Output kopiert fra appen, ordrett --></pre>
    </div>
  </div>
</section>

<section id="avsloring">
  <h2>Avsløringskontroll</h2>
  <p>Emulatoren sensurerer output på samme måte som microdata.no gjør, fordi et skript som gir tall her og blir avvist der ikke er til hjelp. Kontrollen er på som standard.</p>
  <table class="doc-table">
    <thead><tr><th>Regel</th><th>Terskel</th><th>Effekt når den slår inn</th></tr></thead>
    <tbody>
      <!-- Faktiske terskler fra uttrekket i Step 4. Oppgi tall, ikke «lav». -->
    </tbody>
  </table>

  <h3>Skru den av</h3>
  <p>Legg direktivet øverst i skriptet:</p>
  <pre><code>// m2py: disclosure-control=off</code></pre>
  <p>Direktivet er en vanlig kommentar, så microdata.no ignorerer det. Samme skript kan kjøres begge steder.</p>
  <div class="callout">
    <strong>Hva du mister:</strong> med kontrollen av er tallene ikke lenger sammenlignbare med det du ville fått i produksjon. Skru den av for å forstå dataene, ikke for å rapportere dem.
  </div>
</section>

<section id="avvik">
  <h2>Avvik fra microdata.no</h2>
  <p>Emulatoren er ikke perfekt. Dette er de kjente forskjellene — ikke en ansvarsfraskrivelse, men en liste.</p>
  <table class="doc-table">
    <thead><tr><th>Område</th><th>Her</th><th>På microdata.no</th></tr></thead>
    <tbody>
      <!-- Ett faktisk avvik per rad. Finner du ingen, er det et tegn på at
           lista ikke er undersøkt — sjekk tests/ og docs/eval/. -->
    </tbody>
  </table>
  <p class="overview-hint">Oppdager du et avvik som ikke står her, er det verdt å melde.</p>
</section>

<section id="oversettere">
  <h2>py2m og r2m</h2>
  <p>Skriver du heller Python eller R, kan du la det oversettes til microdata-kommandoer. Oversettelsen er ikke fullstendig; den dekker de mønstrene som har en naturlig microdata-form.</p>
  <table class="doc-table">
    <thead><tr><th>Fra</th><th>Til</th><th>Dekker</th></tr></thead>
    <tbody>
      <tr><td>Python (pandas)</td><td>microdata</td><td><!-- fra py2m/ --></td></tr>
      <tr><td>R (tidyverse)</td><td>microdata</td><td><!-- fra r2m/ --></td></tr>
    </tbody>
  </table>
  <div class="example">
    <div class="example-code">
      <span class="example-label">Python inn <span class="badge badge-py">py</span></span>
      <pre><code><!-- kjørt gjennom oversetteren --></code></pre>
    </div>
    <div class="example-result">
      <span class="example-label">microdata ut</span>
      <pre class="result"><!-- faktisk oversetteroutput --></pre>
    </div>
  </div>
</section>
```

For hver microdata-kommando du dokumenterer: kontroller at den faktisk er
implementert. Dokumenter ikke en kommando som ikke finnes i motoren.

```bash
grep -noE "^\s*(def )?(visit_|handle_)?(create|generate|replace|summarize|tabulate|regress|import|require|define|keep|drop|collapse|merge|sort|list)" m2py.py | head -40
```

Hent oversetterdekningen fra testene, som er den eneste pålitelige kilden til
hva som faktisk oversettes:

```bash
python3 -m pytest py2m/tests/ -q 2>&1 | tail -5
Rscript r2m/test_r2m.R 2>&1 | tail -10
```

- [ ] **Step 6: Skriv den engelske versjonen**

Samme i `hjelp.en.html`. microdata-kommandonavnene er identifikatorer og
oversettes ikke.

- [ ] **Step 7: Kjør alt**

Run:
```bash
python3 -m pytest tests/test_hjelp.py -v
node --test tests/js/test_hjelp_ui.mjs
sh scripts/hjelp_sync_check.sh
```
Expected: alle PASS, og synk-skriptet melder nå at fellesseksjonene stemmer
mot alle tre søsken.

- [ ] **Step 8: Commit**

```bash
git add hjelp.html hjelp.en.html tests/ scripts/hjelp_sync_check.sh
git commit -m "docs(hjelp): microdata leder med emulatortroskapen

Riktig navn, kommandoreferanse, avsløringskontroll-reglene med faktiske
terskler, en konkret avviksliste, og oversetterne. Statx er dokumentert
her — den finnes fortsatt i dette repoets modeRegistry."
```

---

## Task 16: microdata — sluttsjekk i nettleseren

**Files:**
- Modify: `../microdata/hjelp.html`, `../microdata/hjelp.en.html`

- [ ] **Step 1: Kjør sjekklista fra Task 10**

Tittelen skal si «Microdata – Dokumentasjon». I tillegg:

- [ ] Kjør minst tre av de dokumenterte microdata-kommandoene i appen og se
      at de oppfører seg som beskrevet
- [ ] Skru avsløringskontroll av med direktivet og se at det virker som
      dokumentert

- [ ] **Step 2: Rett og commit**

```bash
git add hjelp.html hjelp.en.html
git commit -m "fix(hjelp): rettelser fra nettlesergjennomgang av microdata"
```

---

## Task 17: Sluttverifisering på tvers av alle fire

**Files:**
- Modify: den filen som viser seg å avvike

**Interfaces:**
- Consumes: alt.
- Produces: ingenting.

- [ ] **Step 1: Kjør synk-sjekken i STRICT-modus fra alle fire repoer**

`HJELP_SYNC_STRICT=1` gjør enhver «hopper over» til en feil. Under utrullingen
(Task 3–15) er skriptet lempelig, fordi blokkene ikke finnes overalt ennå. Her,
ved porten, skal ingenting hoppes over — en stille kopieringsfeil i Task 11, 13
eller 15 ville ellers rapportert som suksess.

```bash
for r in safestat openstat askstat microdata; do
  echo "── $r ──"
  (cd ~/Documents/GitHub/$r && HJELP_SYNC_STRICT=1 sh scripts/hjelp_sync_check.sh)
  echo "exit=$?"
done
```
Expected: fire ganger «fellesseksjonene stemmer», exit 0 hver gang, og **ingen**
«hopper over»-linjer. Får du en slik linje, mangler en fil sine SYNC-blokker og
kopieringen har feilet stille.

- [ ] **Step 2: Kjør alle hjelpe-tester i alle fire repoer**

```bash
for r in safestat openstat askstat microdata; do
  echo "── $r ──"
  (cd ~/Documents/GitHub/$r && python3 -m pytest tests/test_hjelp.py tests/test_hjelp_sync.py -q \
     && node --test tests/js/test_hjelp_ui.mjs)
done
```
Expected: alle PASS. `tests/test_hjelp_examples.py` finnes bare i safestat.

- [ ] **Step 3: Verifiser at ingen fil har feil identitet**

```bash
cd ~/Documents/GitHub
for r in openstat safestat microdata askstat; do
  for f in hjelp.html hjelp.en.html; do
    printf "%-10s %-14s %s | %s\n" "$r" "$f" \
      "$(grep -oE '<title>[^<]*' $r/$f | sed 's/<title>//')" \
      "$(grep -oE '<h1[^>]*>[^<]*' $r/$f | head -1 | sed -E 's/<h1[^>]*>//')"
  done
done
grep -rln "Microdata Script Runner" */hjelp.html */hjelp.en.html
```
Expected: tabellen stemmer med Global Constraints; `grep` gir ingen treff.

- [ ] **Step 4: Verifiser at ingen resultatblokk er udokumentert oppdiktet**

```bash
cd ~/Documents/GitHub
for r in openstat safestat microdata askstat; do
  echo "── $r ──"
  grep -c '<pre class="result">' $r/hjelp.html || true
  grep -c '<pre class="result illustration">' $r/hjelp.html || true
done
```

For hver `<pre class="result">` uten `illustration`: bekreft at teksten
finnes i `safestat/docs/hjelp_examples/output/`, eller at den er trivielt
verifiserbar (som `5050`). Er den ingen av de to, merk den som illustrasjon
eller erstatt den med kjørt output.

- [ ] **Step 5: Kjør de fulle testsuitene, for å se at ingenting er brukket**

```bash
for r in safestat openstat askstat microdata; do
  echo "── $r ──"
  (cd ~/Documents/GitHub/$r && python3 -m pytest tests/ -q 2>&1 | tail -5)
done
```
Expected: samme resultat som før planen startet. Nye feil er regresjoner og
må rettes.

- [ ] **Step 6: Commit eventuelle rettelser**

```bash
git add -A && git commit -m "fix(hjelp): sluttverifisering på tvers av de fire repoene"
```

- [ ] **Step 7: Oppdater minnet**

Skriv en memory-fil om hjelpeside-arkitekturen — SYNC-markørene, at
safestat er kanonisk, at eksempler genereres av harnessen — og legg en
linje i `MEMORY.md`. Dette er ikke-åpenbar prosjektkunnskap som ikke kan
leses av koden.

---

## Åpne spørsmål for kontrolløren

- **Push.** Push i openstat er kontrollørens beslutning, ikke en subagents. Ingen task pusher. Etter Task 17: bestem per repo.
- **CI.** `scripts/hjelp_sync_check.sh` kan kobles inn i `.github/workflows/`, men er ikke det i noen task. Verdt det hvis synk-disiplinen skal holde over tid.
- **`docs/README.md`** er utdatert og identisk i alle fire. Utenfor omfanget her; egen runde.
