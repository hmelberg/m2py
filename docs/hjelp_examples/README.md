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
