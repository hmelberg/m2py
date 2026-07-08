# Startup example + English example library

**Date:** 2026-07-08
**Applies to:** SafeStat (source of truth) → ported to OpenStat (except the encrypted safe-mode example, which is SafeStat-only)
**Status:** design, pending implementation plan
**Builds on:** the notebook-links feature (fragment loader, `_nbFrag` guard, per-mode startup) merged 2026-07-08.

## Summary

Replace the microdata startup placeholder with a **per-mode startup example** that
loads a CSV from GitHub and produces a table + barplot, and add an **English,
code-first example library** covering external CSV loading, live public-API
loading, column selection, and (SafeStat only) analysis of an **encrypted
sensitive dataset in safe mode**. Sample datasets are committed to each repo and
loaded via their GitHub raw URLs.

## Decisions (from brainstorming)

- **Startup = per-mode.** The active boot mode's editor is seeded with that
  mode's example. Bare domain boots Python (post notebook-links), so most
  visitors see the Python startup; R mode → R example; microdata → keep the
  current Norwegian microdata script (not our focus).
- **Load source = GitHub raw URL** of committed data files (relative paths are
  rejected by the loader — `js/data-directives.js:27` only accepts `http(s)://`).
  URLs are per-repo (`hmelberg/openstat` vs `hmelberg/safestat`).
- **External demos = both** a committed CSV (GitHub raw) and a live public API
  (World Bank — CORS-open, no proxy needed).
- **Language = English** for all non-microdata examples; existing Norwegian
  Python/R/SQL example labels + comments are translated to English. Microdata
  examples stay Norwegian.
- **Show both load methods**: examples comment that `# load <url> as name` and a
  plain `pd.read_csv("<url>")` / `read.csv("<url>")` are both valid.

## Verified feasibility

- `# load <url> as iris` runs `pd.read_csv(url)` → `to_microdata(df, name="iris")`
  in the web-loader preamble (`index.html:7062-7079`); datasets are synced to
  globals by name, so `iris` is a pandas DataFrame in Python mode and a
  data.frame in R mode. Confirmed by reading the preamble.
- **Plan must verify first:** a *key-less* CSV load (`# load url as iris`, no
  `keys(...)`) materializes cleanly through `to_microdata` in both Python and R.
  If `to_microdata` requires a key, the fallback is a direct
  `pd.read_csv(url)` / `read.csv(url)` in the example (still valid, per the
  "both methods" decision).

---

## Part 1 — Per-mode startup example

### Mechanism

Replace the single `_PLACEHOLDER` (`index.html:3990`) with a `STARTUP_EXAMPLES`
map keyed by mode:

```
STARTUP_EXAMPLES = { python: <py script>, r: <r script>, microdata: <current placeholder>, duckdb: <optional sql> }
```

At boot, seed the active mode's editor: `if (!scriptInput.value.trim() && !_nbFrag)
scriptInput.value = STARTUP_EXAMPLES[activeEditorMode] || STARTUP_EXAMPLES.python`.

- `_nbFrag` is the synchronous notebook-fragment guard already added by the
  notebook-links fix (`index.html:9279`): a `#…` link still supersedes the
  startup example.
- Scope: seed the **active mode only** at boot (YAGNI — the dropdown covers the
  other modes). Mode-switching behavior is unchanged.

### Python startup script (English)

```python
# OpenStat — a quick example. Edit it freely, or pick another under "Examples".
# Two ways to load data: the `# load` directive (below), or plain pandas.
# load https://raw.githubusercontent.com/hmelberg/openstat/main/data/iris.csv as iris
# (equivalent: iris = pd.read_csv("https://raw.githubusercontent.com/hmelberg/openstat/main/data/iris.csv"))

# A table — mean measurements per species:
iris.groupby("species").mean(numeric_only=True).round(2)

# A barplot — how many flowers of each species:
import matplotlib.pyplot as plt
iris["species"].value_counts().plot.bar()
plt.title("Iris — count per species"); plt.ylabel("count"); plt.show()
```

### R startup script (English)

```r
# OpenStat — a quick example. Edit it freely, or pick another under "Examples".
# Two ways to load data: the `# load` directive (below), or plain read.csv().
# load https://raw.githubusercontent.com/hmelberg/openstat/main/data/iris.csv as iris
# (equivalent: iris <- read.csv("https://raw.githubusercontent.com/hmelberg/openstat/main/data/iris.csv"))

# A table — mean measurements per species:
aggregate(. ~ species, data = iris, FUN = mean)

# A barplot — how many flowers of each species:
barplot(table(iris$species), main = "Iris — count per species", ylab = "count")
```

(SafeStat uses its own repo URL `hmelberg/safestat`. The microdata startup script
is unchanged.)

---

## Part 2 — Committed datasets

Commit to `data/` in each repo (small, classic, each has a categorical column
good for a barplot):

- `data/iris.csv` — 150 rows; columns `sepal_length,sepal_width,petal_length,petal_width,species`.
- `data/penguins.csv` — Palmer penguins; columns incl. `species,island,bill_length_mm,bill_depth_mm,flipper_length_mm,body_mass_g,sex,year`. Used by the column-selection example.
- **SafeStat only:** `data/hospital_admissions.enc.json` — the encrypted synthetic
  hospital dataset (Part 4).

All loaded via `https://raw.githubusercontent.com/hmelberg/<repo>/main/data/<file>`.

---

## Part 3 — English example library (dropdown)

Examples live in `examples/` and are registered as inline dropdown buttons with
`data-example` + `data-mode` (existing pattern, `index.html:29-55`). The dropdown
already filters by mode.

### Translate existing (non-microdata) examples to English
The current Python/R/SQL example **labels** (in the dropdown markup) and the
**comments** inside their `examples/*.txt` files are translated to English.
Microdata examples (`data-mode="microdata"`) are left in Norwegian.

### New examples (English), per mode

For each of Python and R, add:

1. **CSV from GitHub** (`ex_csv_iris`) — the startup script above, also available
   from the menu. Shows `# load` + the `pd.read_csv`/`read.csv` equivalent, a
   table, and a barplot.
2. **Select specific columns → focused dataset** (`ex_columns`) — load the wider
   penguins CSV, keep only chosen columns, and analyze that subset (the
   external-data analogue of microdata's "import specific variables"):
   ```python
   # load https://raw.githubusercontent.com/hmelberg/openstat/main/data/penguins.csv as penguins
   # Keep only the columns we need — a focused dataset:
   flippers = penguins[["species", "flipper_length_mm"]].dropna()
   flippers.groupby("species")["flipper_length_mm"].mean().round(1)
   flippers.groupby("species")["flipper_length_mm"].mean().plot.bar(title="Mean flipper length by species")
   import matplotlib.pyplot as plt; plt.ylabel("mm"); plt.show()
   ```
   (R equivalent with `subset`/`[ , cols]` + `aggregate` + `barplot`.)
3. **Live public API** (`ex_api_worldbank`) — load from the World Bank registry
   source (CORS-open) and barplot a simple indicator for a few countries:
   ```python
   # load worldbank/country/NOR;SWE;DNK;FIN/indicator/SP.DYN.LE00.IN?format=json&per_page=100 as life
   # (life expectancy at birth; World Bank returns [meta, rows] JSON — the loader flattens it)
   latest = life.sort_values("date").groupby("country").last(numeric_only=False)
   latest["value"].plot.bar(title="Life expectancy — latest year"); ...
   ```
   The exact registry query string is finalized in the plan against
   `data/data-sources.json`'s World Bank template; if the JSON shape needs
   massaging the example does it in a couple of lines. If the registry load
   proves awkward, fall back to a direct `pd.read_json(<worldbank url>)`.

Dropdown labels (English), e.g. "Load a CSV from GitHub", "Select columns → focused
dataset", "Live data — World Bank API".

---

## Part 4 — Encrypted safe-mode example (SafeStat only, Python + R)

Demonstrates SafeStat's differentiator: analyzing a **sensitive encrypted
dataset** so that **only aggregates are released** — individual records never
surface.

### Synthetic dataset

Generate a synthetic hospital-admissions CSV (a committed generator script under
`scripts/` or `manual_scripts/`, deterministic seed) with columns:

`id, name, gender, city, birth_date, icd10, diagnosis_text, admit_date,
discharge_date, department, admission_type` — **multiple admissions per `id`**
(same person can appear more than once), ~a few thousand rows. All fake
(names/ids synthetic). `icd10` from a small set with matching `diagnosis_text`
(short disease text).

### Encryption

Encrypt the CSV to a `safepy-enc-v1` AES artifact `data/hospital_admissions.enc.json`
using the project's own tooling — either `safepy`'s `encfile` (Python, runnable
in the venv) or a small Node WebCrypto harness matching `js/enc-crypto.js`.
**Plan must verify** the artifact decrypts with `js/enc-crypto.js` (the two are
implementations of the same spec — interop is the acceptance test). Commit only
the encrypted artifact. Publish a **demo key** in the example (acceptable: the
data is synthetic and the example must actually run; clearly labeled "demo key,
synthetic data").

### Example script (SafeStat only, one Python + one R)

```python
# SafeStat — analyze a SENSITIVE, ENCRYPTED dataset in safe mode.
# The file is encrypted; it is decrypted locally with the key, and safe mode
# only releases AGGREGATES — individual admissions never appear in the output.
# load https://raw.githubusercontent.com/hmelberg/safestat/main/data/hospital_admissions.enc.json as adm, key("DEMO-…"), exec(local)

# Admissions per ICD-10 chapter (first letter of the code):
adm["chapter"] = adm["icd10"].str[0]
adm["chapter"].value_counts().sort_index()

# City × gender crosstab of admissions:
import pandas as pd
pd.crosstab(adm["city"], adm["gender"])

# Mean length of stay (days) by department — an aggregate, no row-level data:
los = (pd.to_datetime(adm["discharge_date"]) - pd.to_datetime(adm["admit_date"])).dt.days
los.groupby(adm["department"]).mean().round(1).plot.bar(title="Mean length of stay by dept (days)")
import matplotlib.pyplot as plt; plt.ylabel("days"); plt.show()
```

R equivalent (`read` via the same `# load … key(…) exec(local)` directive; safe
aggregates with `table`/`aggregate`/`barplot`).

- **Safe-mode enforcement — important honesty note.** An ad-hoc URL load
  (`# load <enc url> as adm, key(...)`) can *decrypt and analyze*, but the
  directive grammar offers only `exec(local|remote)` — there is no `exec(strict)`.
  SafeStat's **enforced** safe mode (the strict facade that actively blocks
  row-level output) is triggered by a source **registered** as
  `level: protected`/`sensitive` with strict `local_mode` (via `deldata.html` +
  the Anvil backend) — which needs login and is therefore **not self-contained**
  in a shareable example. So this example delivers the **workflow**
  (encrypted file → key → aggregate-only analysis) with the aggregate-only-ness
  by **convention** (the script writes only aggregates), and a prominent comment
  explains that in a real deployment the source is *registered as protected* so
  the facade *enforces* it. This is the honest, runnable form. (An `exec(strict)`
  directive that forces the local strict facade on an ad-hoc encrypted load
  would make the enforcement real and self-contained — noted as a possible small
  engine addition; see Open question for the user.)
- Registered in the dropdown with `data-mode="python"` / `"r"` and English labels
  ("Encrypted data — safe-mode analysis (Python/R)"). **Not ported to OpenStat.**

## Resolved decision — safemodus delivery

**Chosen: option 1 (workflow-by-convention), 2026-07-08.** The encrypted example
is self-contained and runnable: it loads the encrypted file with a demo key and
performs aggregate-only analysis, with a prominent comment explaining that in a
real deployment the source is *registered as protected* so the strict facade
*enforces* aggregate-only output. **No engine change** in this plan. (Deferred,
may revisit: an `exec(strict)` directive to make ad-hoc enforcement real without
login — explicitly out of scope for now.)

---

## Architecture & components

| Unit | Responsibility | Location |
|---|---|---|
| `STARTUP_EXAMPLES` map + boot seeding | per-mode startup content, fragment-gated | `index.html` (replaces `_PLACEHOLDER`) |
| committed datasets | iris/penguins (+ encrypted hospital, SafeStat) | `data/*.csv`, `data/*.enc.json` |
| example scripts | English CSV/API/columns/encrypted examples | `examples/*.txt` |
| dropdown registration | `data-example` + `data-mode` buttons, English labels | `index.html` examples dropdown |
| hospital generator + encryptor | build + encrypt the synthetic dataset (one-time, committed output) | `scripts/` (SafeStat) |

## Testing

- `node --check` on the index.html startup-map + dropdown edits.
- Headless: confirm `# load <raw csv> as iris` parses via `DataDirectives.parse`
  and the World Bank registry query resolves; confirm the encrypted artifact
  round-trips (encrypt → `js/enc-crypto.js` decrypt).
- Example scripts are content — full verification is a browser run (deferred,
  with a checklist), like the notebook-links QA.

## Rollout

Build in **SafeStat**, port to **OpenStat** — porting swaps the GitHub-raw repo
URLs (`safestat`→`openstat`) and **omits Part 4** (the encrypted safe-mode
example and its dataset). iris/penguins datasets and the CSV/API/columns examples
port to both.

## Out of scope

- Seeding every mode's buffer at boot (only the active mode is seeded).
- HE (homomorphic) encryption for the safe-mode example (AES + safe local
  execution is the chosen path; HE is Python-only and more limited).
- Rewriting the microdata example library (stays Norwegian, unchanged).
