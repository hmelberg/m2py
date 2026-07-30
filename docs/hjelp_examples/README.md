# Hjelpesidenes eksempler

Resultatblokkene i `hjelp.html` er **generert**, ikke skrevet for hånd.

    .venv/bin/python docs/hjelp_examples/run_examples.py

skriver én fil per eksempel til `output/`. Innholdet limes inn i
`<pre class="result">` i hjelp.html, og `tests/test_hjelp.py` sammenligner de to.

Endrer du et eksempel: rediger `EXAMPLES` i `run_examples.py`, kjør skriptet,
lim inn på nytt, kjør testene. Frøet (`default_rng(42)`) er låst — endrer du
det, endres hvert resultattall på hjelpesidene.

Eksempler som ikke kan kjøres her — ask-svar, jamovi-dialoger, federerte
spørringer, hybrid-skript som krever en ekte SSB-registerkobling — merkes i
HTML-en med `class="result illustration"` og ordet «illustrasjon» synlig for
leseren. De skal aldri se ut som kjørt output.

## Tre harnesser, ett kommando

`run_examples.py` sin `main()` kjører alle tre:

1. **`EXAMPLES`** — safepy (STRICT-dialektene Python/R/SQL), pakket ut fra
   `vendor/safepy.zip`.
2. **`MICRODATA_EXAMPLES`** — m2py sin `MicroInterpreter` kjørt headless
   (samme mønster som `tests/test_if_condition.py`): et manuelt datasett,
   `_execute_instruction(parser.parse_line(...))`, `output_log` lest ut som
   tekst. Brukes i `#microdata`-seksjonen.
3. **`run_examples_js.mjs`** (Node) — ren klientlogikk uten Python-motstykke:
   delelenke-komprimering (`felles-lagre`), steg-for-steg-blokksplitting
   (`felles-forklar`) og widget-linje-parsing (`felles-widgets`). Funksjonene
   trekkes ut ORDRETT fra `js/github-storage.js`, `index.html` og
   `widgets/forklar-widgets.js` mellom bokstavelige markører og kjøres i en
   vm-sandkasse — de limes ikke inn for hånd. Endrer kildefilene navn eller
   rekkefølge på disse funksjonene, feiler skriptet høyt i stedet for å
   stille fryse en utdatert kopi. Krever `node` i PATH.
