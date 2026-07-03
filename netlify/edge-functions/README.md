# Edge Functions — lokal testing

AI-endepunkter (se `netlify.toml` for path-mapping):

- `dm-vurder` → `/api/dm-vurder` — personvern-/dataminimerings-vurdering av et script
- `kode-svar` → `/api/kode-svar` — AI-assistent som genererer/forklarer microdata-kode
- `kode-svar-v2` → `/api/kode-svar-v2` — eksperimentell 2-stegs variant: en
  «variabel-velger»-modell (env `PICKER_MODEL`, standard rask Haiku) plukker
  relevante variabler som vises med full kodeliste i generasjons-prompten;
  klienten kjører én auto-rettingsrunde mot lokal Pyodide-validering. v1
  (`kode-svar`) er urørt, og v2 degraderer til v1-lik oppførsel hvis velgeren feiler.
- `tolk-resultat` → `/api/tolk-resultat` — tolker output fra en kjøring
- `data-svar` → `/api/data-svar` — Web-modus (kun admin): agentisk tool-loop
  (search_catalog/table_metadata/probe + web_search) som finner åpne data og
  genererer python/r/duckdb-script med connect/load-direktiver. SSE-events:
  progress/text/sources/continue/done/error. Fortsettelsesprotokoll: Netlify
  har CPU-tak per invokasjon, så serveren kjører én API-tur per POST og
  avslutter med `{type:"continue", state, probed}` når den ikke er ferdig;
  klienten re-POSTer samme body pluss `resume:{state, probed}` til svaret
  kommer. Prompt-kilde: `prompts/data-svar.md`;
  register: `data/data-sources.json`; evalsett: `docs/eval/data-svar-evalsett.md`.
- `hent` → `/api/hent?url=…[&body=…]` — SSRF-herdet GET-proxy (kun admin).
  Injiserer API-nøkler server-side for register-kilder (host-matchet);
  `body` GET-innpakker POST-json (PxWeb v1 o.l.).

## Forutsetninger

1. Installer Netlify CLI: `npm install -g netlify-cli`
2. Sett env-vars: `cp .env.example .env`, fyll inn `ANTHROPIC_API_KEY` og
   `M2PY_ACCESS_TOKEN` (delt token for lokal/admin-tilgang). Samme variabler må
   settes i Netlify-konsollen før prod-deploy.
   - `FRED_API_KEY` (valgfri) — server-side nøkkel `hent`/`data-svar` injiserer
     for FRED-kilder i registeret (host-matchet, aldri sendt til klienten).
   - `DATA_SVAR_MODEL` (valgfri) — override av modellen `data-svar` bruker
     (standard: samme som `ANTHROPIC_MODEL`/`claude-sonnet-4-6`).

## Start lokal dev-server

```
netlify dev
```

Server starter typisk på `http://localhost:8888`.

## Auth

Alle tre endepunktene krever `Authorization: Bearer <token>` (felles
`_lib/auth.ts`-gate: token-sjekk → metode → body-grense → rate-limit → Anvil-
validering, med konstant-tid-sammenligning og positiv-cache). Bruk det delte
`M2PY_ACCESS_TOKEN` lokalt, eller et gyldig brukertoken fra Anvil.

## Test dm-vurder med curl

```bash
curl -N -X POST http://localhost:8888/api/dm-vurder \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $M2PY_ACCESS_TOKEN" \
  -d '{
    "script": "// personvern: formål: Studere inntektsforskjeller\nimport all from BEFOLKNING\nkeep if alder >= 18\nsummarize INNTEKT, by(kommune)"
  }'
```

Forventet output: en strøm av `data: {"type":"text","text":"..."}`-linjer,
deretter en `data: {"type":"done","inputTokens":...,"outputTokens":...}`-linje.
Innholdet er norsk markdown (Klassifisering, Samlet vurdering, Observasjoner).

## Feil-scenarioer

- Mangler/ugyldig token → 401
- Feil metode (ikke POST) → 405
- For stor body (`content-length` over grensen) → 413
- For mange kall fra samme IP → 429 (med `Retry-After`)

## Struktur

- `dm-vurder.ts`, `kode-svar.ts`, `tolk-resultat.ts` — endepunktene
- `_lib/auth.ts` — felles request-gate (auth + rate-limit + body-guard)
- `_lib/rate-limit.ts` — per-IP token-bucket (Netlify Blobs; failer åpent)
- `_lib/anthropic.ts` — Anthropic streaming-klient (timeout + 429/529-retry)
- `_lib/parse-script-context.ts` — personvern-kommentarer + språk-deteksjon
- `prompts/` — kildefiler for prompt-tekstene (duplisert som TypeScript-
  konstanter i endepunkt-filene siden Deno Deploy ikke bundler .md i runtime;
  oppdater begge stedene ved endring)

## Tester

```
deno check *.ts _lib/*.ts
deno test --allow-all _lib/
```
(kjøres også i CI via `.github/workflows/edge-tests.yml`)
