<!-- KILDE for data-svar-edge-funksjonen (Web-modus: generelle dataspørsmål
mot åpne kilder). TS-konstantene i _lib/data-svar-prompt.ts er render-målet;
denne fila er kildedokument + endringslogg (samme mønster som kode-svar.md).

Design: docs/superpowers/specs/2026-07-03-web-data-svar-design.md.

Blokkstruktur: INTRO (tre faser: tolk → finn → generer; søkehåndverk),
DELIVERY (connect/load-direktiver, proxy, POST-innpakking, kildesitering),
SCIENCE (rå→justert, identifikasjon, heterogenitet, ærlighet — utvidet fra
INFERENCE_STRATEGY_PYR i kode-svar.ts), INLINE (datatilfangst-stigen:
probet → transkribert-fra-web_fetch → modellkunnskap; aldri utfall fra
nivå 3), MULTI (merge til ÉN analysedataframe, join-nøkler, radtall
før/etter), MODE_PY/R/DUCK (miljø + svarformat), + registerblokk
(renderRegistryBlock, byte-stabil). Hosted tools: web_search + web_fetch.

Prompt-utviklingsloop (spec §7): endringer kjøres mot evalsettet
(docs/eval/data-svar-evalsett.md) før deploy; feilmønstre fra evals og
reparasjonsrunder blir nye promptregler eller register-quirks.

ENDRINGSLOGG
- 2026-07-03: v1 — blokkene opprettet per spec.
- 2026-07-03: v1.1 — Evalsett-kjøring #1 (11 spørsmål, docs/eval/data-svar-evalsett.md):
  5/11 PASS, 6/11 FAIL. Klart gjentakende mønster i 5 av 6 feil (Q3/Q5/Q7/Q8/Q9):
  modellen skriver ad-hoc nettverkskode (read.csv/pd.read_csv/requests/pyfetch mot
  samme URL) i stedet for å bruke en allerede innlastet `# load`-variabel, og/eller
  merker en kilde «probe-verifisert» uten at probe faktisk returnerte ok=true for
  akkurat den URL-en. DELIVERY-blokken fikk to nye KRAV-punkter som adresserer
  begge: (1) `navn` fra `# load` er ferdig data — aldri hent på nytt; (2)
  «probe-verifisert» krever eksakt URL-treff i probe-loggen, ellers si ærlig fra at
  ingen kilde ble funnet. Samtidig: registerets `ssb`-oppføring fikk `cors: false`
  og en rettet `sporrings_url_mal` (v2, ikke v2-beta, for selve datauttrekket) —
  v2-beta/.../data feilet reproduserbart i to uavhengige spørsmål (Q3, Q4), mens
  søk og /metadata fortsatt virker fint på v2-beta. Q11 feilet separat med
  AbortError (90s non-streaming-turngrense nådd under et 11-verktøykall-forløp) —
  logget som infra-observasjon, ikke en promptfeil. `data-svar-prompt.test.ts`
  grønn etter endringen (115/115 i hele `_lib/`-suiten).
- 2026-07-03: v1.2 — Final-review fiksrunde: DELIVERY-eksempelet motsa det
  rettede `ssb`-registeret (viste fortsatt `v2-beta/.../data` og en direkte
  `ssb/…`-load uten proxy). Eksempelet er nå justert til å stemme eksakt med
  `data/data-sources.json`s `ssb`-oppføring: `# connect ssb` (register-id,
  som `fred`) + `# load /api/hent?url=<url-enkodet v2 data-URL…> as ledighet`
  (proxy obligatorisk, `cors:false`; datauttrekk MÅ bruke `/v2/`, ikke
  `/v2-beta/`). OWID- og fred-eksempellinjene er uendret. Samtidig:
  `_lib/anthropic.ts`s `AGENTIC_TIMEOUT_MS` hevet 90s → 180s (Q11 i evalsettet
  traff denne grensen med `AbortError` under et langt multi-probe-forløp;
  streaming av siste runde er den riktige langsiktige fiksen, se kommentar i
  fila). Q3/Q5/Q11 kjørt på nytt mot evalsettet — se
  `docs/eval/data-svar-evalsett.md` for resultatene. `data-svar-prompt.test.ts`
  og hele `_lib/`-suiten grønn etter endringen.
-->

Se `_lib/data-svar-prompt.ts` — innholdet er inlinet som TS-konstanter fordi
Deno Deploy ikke bundler .md-filer ved kjøretid.
