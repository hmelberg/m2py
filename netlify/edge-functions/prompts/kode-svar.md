<!-- KILDE for kode-svar-edge-funksjonen (rask, enkelt-svar kode-AI).
Reglene her er en kondensert kopi av kjernen i
microdata-api/server_code/prompts.py (SYSTEM_PROMPT, GRAMMAR_CHEATSHEET,
DATABANK_CHEATSHEET, DATASET_STRUCTURE, MERGE_CHEATSHEET, PSEUDONYM_RULES,
TYPE_RULES, DATE_QUIRKS, PRIVACY_RULES, NPR_CANONICAL_IMPORTS).

Forskjell fra Anvil-løpet: dette er ETT enkelt kall — ingen retrieval, ingen
tool-use (`lookup_variable`), ingen validerings-/reparasjons-loop på serveren.
Variabel-katalogen og kommando-referansen hentes ved kald start fra de samme
statiske filene nettstedet serverer (variable_metadata.json, command_help.js)
og legges inn i den cachede system-prefiksen. Klienten validerer svaret
lokalt i Pyodide (m2py) og viser et ⚠-merke ved feil.

SYNK MED prompts.py (begge veier). Følgende innhold er FELLES og bør holdes
synkront med microdata-api/server_code/prompts.py: grammatikk (inkl.
`import-event`/`import-panel`), Stata-avvik, type-/kode-regler (fnutter,
destring), funksjonsreferanse, familie-/relasjons-idiom, pseudonym-regler,
dato- og personvern-regler. Per 2026-05-28 er disse portet til prompts.py.

Bevisst FORSKJELLIG (ikke port til Anvil): den anriket variabel-katalogen
(full beskrivelse/labels inline), den inlinede kommune-kodelista, og at all
kunnskap er front-lastet. Grunnen: Anvil har `lookup_variable`-tool +
validerings-/reparasjons-loop, så der holdes katalogen kompakt og detaljer
hentes on-demand. Dette løpet har hverken tool eller repair, så det må
front-laste alt. -->

Se `dm-vurder.ts` / `kode-svar.ts` — reglene er inlinet som TS-konstanter fordi
Deno Deploy ikke bundler .md-filer ved kjøretid. Denne filen er kilde-dokument.
