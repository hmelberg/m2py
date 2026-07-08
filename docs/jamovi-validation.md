# jamovi mode — result validation against *Learning Statistics with jamovi*

The jamovi mode generates standard R, runs it via webR on the active dataset, and
renders jamovi-style tables. To validate correctness, the bundled book datasets
(`examples/lsj/`, from the *Learning Statistics with jamovi* data package) were
analysed in the app and compared against the numbers published in the book.

Load a dataset via the jamovi **☰ menu → Åpne eksempeldatasett…**, then run the
analysis from the **Analyser** ribbon.

| Dataset | Analysis | App result | Book (published jamovi) | Match |
|---|---|---|---|---|
| harpo | Independent t-test (grade by tutor), Student's | t = 2.12, df = 31, p = .043, Cohen's d = 0.74 | t(31) = 2.115, p = .043, d = 0.74 | ✓ |
| harpo | Independent t-test, Welch's | t = 2.03, df = 23.02, p = .054, mean diff = 5.48 | t = 2.034, df = 23.0, p = .054 | ✓ |
| clinicaltrial | One-way ANOVA (mood.gain by drug) + η² | F(2,15) = 18.61, p < .001, η² = .713 | F(2,15) = 18.6, p < .001, η² = .71 | ✓ |
| parenthood | Linear regression (dan.grump ~ dan.sleep) | R² = .816, intercept = 125.96, slope = −8.94 | R² = .816, 125.96, −8.94 | ✓ |
| parenthood | Correlation (dan.sleep, dan.grump) | r = −0.903 | r = −.903 | ✓ |

All checks reproduce the book's published values. The bundled datasets also let the
app double as a teaching companion to the book.

Datasets bundled under `examples/lsj/` (27 CSVs). A curated subset is offered in the
example picker (`JAMOVI_EXAMPLES` in `js/modes/jamovi.js`); the rest are available by
filename.

## 2026-07-09 — jmv-motoren, fase 1 (jmv 2.7.7 i webR v0.6.0, R 4.6)

jamovi-modus 2.0 kjører de ekte jmv-analysefunksjonene (`jmv::ttestIS`,
`jmv::anovaOneW`, `jmv::corrMatrix`, `jmv::linReg`, `jmv::contTables`, `jmv::propTestN`,
`jmv::descriptives`, `scatr::scatr`) via webR, med et spec-drevet opsjonspanel og en
generisk resultatrenderer (se `docs/superpowers/specs/2026-06-27-jamovi-mode-design.md`
og `docs/superpowers/plans/2026-06-27-jamovi-mode.md`). Nedenfor er sjekklisten for
manuell validering mot jamovi-skrivebordsappen — hver rad krysses av etter side-om-side-
sammenligning.

### Sjekkliste

| Datasett | Analyse | Opsjoner | Status |
|---|---|---|---|
| harpo | Independent Samples T-Test | Welch's + effect size + descriptives | til manuell kontroll |
| chico | Paired Samples T-Test | Wilcoxon rank | til manuell kontroll |
| zeppo | One Sample T-Test | — | til manuell kontroll |
| clinicaltrial | One-Way ANOVA | Tukey post hoc + Levene | til manuell kontroll |
| parenthood | Correlation Matrix + Linear Regression | CI + std. estimate | til manuell kontroll |
| parenthood | Scatter Plot (scat) | grupper/regresjonslinje | til manuell kontroll |
| agpp | Contingency Tables | Expected + Cramér's V | til manuell kontroll |
| cards | Proportion Test (N Outcomes) | — | til manuell kontroll |
| (valgfritt datasett) | Descriptives | splitBy + hist + violin + freq | til manuell kontroll |

### Kjente begrensninger i fase 1

- Pareto Plot fjernet (finnes ikke i wasm-scatr 1.0.1; fase 2 når nyere scatr bygges
  som wasm)
- Bayes factor-opsjoner (bf/bfPrior i t-tester) kan feile: BayesFactor→hypergeo→deSolve
  mangler wasm-binær — utestet
- contTables virker via fabrikkert websocket-stub (`.jmv_install_stubs` i
  `js/modes/jmv_helpers.R`)
- «Terms»-opsjoner (anova modelTerms, linReg blocks) bruker jmv sine R-defaults; ingen
  UI ennå
- Første lasting av jmv-motoren: ~170 MB (engangs; caches av service worker `m2py-v7`)

### Hvordan teste

Bytt til jamovi-modus, hamburger → «Åpne eksempeldatasett…», velg datasett, åpne
analysen fra menyen, tilordne variabler — resultatet oppdateres live; sammenlign
tall/kolonner mot samme analyse i jamovi-appen (`/Applications/jamovi.app`).
