# Edge Functions — lokal testing

## Forutsetninger

1. Installer Netlify CLI:
   ```
   npm install -g netlify-cli
   ```

2. Sett API-nøkkel og andre env-vars:
   ```
   cp .env.example .env
   # Rediger .env og fyll inn ANTHROPIC_API_KEY
   ```

   Tilsvarende variabler må også settes i Netlify-konsollen før prod-deploy.

## Start lokal dev-server

```
netlify dev
```

Server starter typisk på `http://localhost:8888`.

## Test dm-quick med curl

```bash
curl -N -X POST http://localhost:8888/api/dm-quick \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8888" \
  -d '{
    "script": "// personvern: formål: Studere inntektsforskjeller\nimport all from BEFOLKNING\nkeep if alder >= 18\nsummarize INNTEKT, by(kommune)"
  }'
```

Forventet output: en strøm av `data: {"type":"text","text":"..."}`-linjer,
deretter en `data: {"type":"done","inputTokens":...,"outputTokens":...}`-linje.

Innholdet skal være norsk markdown med seksjonene Klassifisering,
Samlet vurdering, og evt. Observasjoner.

## Test feil-scenarioer

Avvist origin (403):
```bash
curl -X POST http://localhost:8888/api/dm-quick \
  -H "Content-Type: application/json" \
  -d '{"script":"test"}' \
  -w "\n%{http_code}\n"
```

For stor body (413):
```bash
python3 -c "print('x' * 60000)" > /tmp/big.txt
curl -X POST http://localhost:8888/api/dm-quick \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:8888" \
  -d "{\"script\":\"$(cat /tmp/big.txt)\"}" \
  -w "\n%{http_code}\n"
```

(NB: origin-sjekk og body-grense legges til i Tasks 11–12.)

## Edge Function-struktur

- `dm-quick.ts` — kjapp vurdering, streamer til klient
- `_lib/parse-script-context.ts` — parser for personvern-kommentarer + språk-deteksjon
- `_lib/anthropic.ts` — tynn Anthropic streaming-klient
- `prompts/` — kildefiler for prompt-tekstene (innholdet er duplisert som
  TypeScript-konstanter i `dm-quick.ts` siden Deno Deploy ikke bundler .md
  filer automatisk; oppdater begge stedene ved endring)
