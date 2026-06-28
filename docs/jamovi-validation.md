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
