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
-->

Se `_lib/data-svar-prompt.ts` — innholdet er inlinet som TS-konstanter fordi
Deno Deploy ikke bundler .md-filer ved kjøretid.
