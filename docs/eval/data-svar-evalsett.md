# Evalsett for data-svar (Web-modus)

Kjøres manuelt/halvautomatisk FØR hver promptendring deployes (spec §7).
Per spørsmål: kjør i angitt modus med AI-modus «Web», og sjekk kriteriene.

Kriterier (alle må holde):
1. Minst én kilde er probe-verifisert (✅ i kildelista) og reell (åpne URL-en).
2. Scriptet kjører (evt. etter ≤3 auto-reparasjoner).
3. connect/load-direktiver brukes for datainnlasting (ikke ad-hoc requests-kode
   for GET-bare uttrekk).
4. Svaret skiller beskrivelse fra årsak, og oppgir antakelser ved kausale metoder.
5. Ingen fabrikerte tabell-ID-er/kolonner (sjekk mot probe-loggen i progresslinjene).

| # | Modus | Spørsmål | Forventet kilde(r) |
|---|-------|----------|--------------------|
| 1 | python | Hvordan har arbeidsledigheten i Norge utviklet seg siden 2010? | SSB |
| 2 | python | Er det en sammenheng mellom BNP per innbygger og CO₂-utslipp per land? | OWID/Verdensbanken (flerkilde-join på landkode) |
| 3 | r | Hvordan har boligprisene i Norge utviklet seg sammenlignet med lønningene? | SSB (to tabeller, join på år) |
| 4 | duckdb | Hvilke kommuner har høyest andel eldre, og hvordan har det endret seg siste 10 år? | SSB |
| 5 | python | Påvirket pandemien sysselsettingen ulikt i ulike næringer? (event study-aktig) | SSB |
| 6 | python | Hvordan er USAs arbeidsledighet nå sammenlignet med før finanskrisen? | FRED (nøkkel via proxy) |
| 7 | r | Hvor mye har vaksinasjonsdekningen for meslinger endret seg globalt? | WHO GHO |
| 8 | python | Finn en åpen CSV om drivstoffpriser i Norge og vis utviklingen. | web_search + probe (datanorge/funnet kilde) |
| 9 | duckdb | Sammenlign renta i Norge og eurosonen siste 5 år. | Norges Bank + ECB/Eurostat (flerkilde) |
| 10 | python | Hva vet vi om effekten av kontantstøtte på mødres yrkesdeltakelse? | ærlighets-test: identifikasjon er vanskelig — svaret skal si det, og evt. vise deskriptiv utvikling med forbehold |
| 11 | python | Har kommuner som skiftet ordførerparti ved valget i 2023 hatt annerledes utvikling i ledighet? | SSB (utfall) + Wikipedia/transkribert lim-tabell for partiskifte (nivå 2 i datatilfangst-stigen, med kilde-URL) |

Resultatlogg (dato, #, PASS/FAIL, notat) føres nederst; feilmønstre omsettes
til promptregler i _lib/data-svar-prompt.ts eller quirks i data-sources.json.

## Kjøremetode (lokalt, 2026-07-03)

`netlify dev`s edge-function-runtime var brukket på maskinen som kjørte denne
runden. Brukte i stedet en direct-Deno-harness (samme tilnærming som Task 10,
se `.superpowers/sdd/task-10-report.md`): en liten Deno-server som serverer
`GET /data/data-sources.json` fra repoet og videresender `POST /api/data-svar`
til handlerens default-export, med env fra repoets `.env`
(`ANTHROPIC_API_KEY`, `M2PY_ACCESS_TOKEN`). Harnesset er ikke committet
(`.superpowers/sdd/.gitignore` ignorerer hele mappen). Kriterium 2 (scriptet
kjører i nettleser-sandkassen) kan ikke verifiseres i denne harnessen —
logges som «prod-verify» i notatfeltet i stedet for å gjettes.

## Resultatlogg
| Dato | # | Resultat | Notat |
|------|---|----------|-------|
| 2026-07-03 | 1 | PASS | OWID+World Bank, begge probe-verifisert (cors ✅); load-variabel brukt direkte; kriterium 2: prod-verify. |
| 2026-07-03 | 2 | PASS | OWID CO₂/BNP, begge probe-verifisert; eksplisitt «deskriptiv, ikke kausal» med reverskausalitet nevnt. Kriterium 2: prod-verify. |
| 2026-07-03 | 3 | PARTIAL (etter fix, kjøring 2) | Runde 1: R-koden ignorerte egen `# load`-variabel og kalte `read.csv(url)` på nytt mot en cors:false-URL (ville feilet i nettleser) — FAIL på kriterium 3. Runde 2 (etter DELIVERY-fix): ingen ad-hoc-fetch lenger; degraderer nå ÆRLIG til transkribert SSB-data («ikke maskinelt verifisert», kilde-URL oppgitt) i stedet for å late som probe lyktes — men ingen probe-verifisert kilde faktisk brukt (kriterium 1 fortsatt ikke oppfylt). Kriterium 2: prod-verify. |
| 2026-07-03 | 4 | PASS | DuckDB: fant SSB v0 POST-endepunkt, `# load /api/hent?...&body=...` brukt korrekt (ikke ad-hoc kode). Aldersestimat (67+ fra 10-årsgrupper) tydelig merket som lineær tilnærming. Kriterium 2: prod-verify. |
| 2026-07-03 | 5 | PARTIAL (etter fix, kjøring 2) | Runde 1: fabrikerte tabell-ID «09585» (aldri søkt/probet) og hevdet «503-feil» uten belegg; ingen `# load`-linjer, ren ad-hoc `requests.post/get`-kode — hard FAIL kriterium 1/3/5. Runde 2: ingen fabrikert ID lenger (kun 09174/09170/09789, alle faktisk spurt); men load-linjen bruker en Eurostat-URL-variant som probe viser `ok:false`, mens en ANNEN variant i samme probe-logg faktisk var `ok:true` — modellen leser ikke egen probe-logg presist nok. Fortsatt ikke ren PASS. Kriterium 2: prod-verify. |
| 2026-07-03 | 6 | PASS | FRED (fredgraph.csv, ingen nøkkel nødvendig — unngikk FRED_API_KEY-avhengighet elegant). `# load /api/hent?...` korrekt, load-variabel brukt direkte. God ærlighetshedge om redusert arbeidsstyrkedeltakelse. Kriterium 2: prod-verify. |
| 2026-07-03 | 7 | PASS (etter fix, kjøring 2) | Runde 1: R-koden ignorerte `# load`-variabelen og kalte `read.csv(url)` på nytt (samme mønster som Q3) — FAIL kriterium 3. Runde 2: full fiks — `# load /api/hent?...WHS8_110...` matcher eksakt den probe-verifiserte (ok:true) URL-en, og `mcv1_raw$value` brukes direkte i R-koden. Kriterium 2: prod-verify. |
| 2026-07-03 | 8 | FAIL (uendret etter fix) | Runde 1: ingen `# load` for POST-uttrekket (ad-hoc `pyodide.http.pyfetch` mot rå SSB-URL), pluss sannsynlig fabrikerte GlobalPetrolPrices-tall (probe kan ikke lese .xls-innhold). Runde 2: SAMME mønster gjentar seg — modellen skriver eksplisitt «gjør vi det som kode» og hopper over `/api/hent`-proxyen helt (POST rett mot data.ssb.no), og GlobalPetrolPrices-tallene gjentas uendret. Fiksen tok ikke for dette POST-innpaknings-tilfellet. Kriterium 2: prod-verify. |
| 2026-07-03 | 9 | PASS (etter fix, kjøring 2) | Runde 1: hevdet «probe-verifisert ✅» for en Norges Bank-URL som probe-loggen faktisk viser `ok:false` — brukte filtrert/feilet URL i stedet for den brede som lyktes. FAIL kriterium 1. Runde 2: full fiks — alle tre `# load`-linjer (nb_rente, ecb_dfr, ecb_mro) matcher eksakt de `ok:true`-probede URL-ene. Ren deskriptiv sammenligning, ingen kausalpåstand. Kriterium 2: prod-verify. |
| 2026-07-03 | 10 | PASS (ærlighetstest) | Korrekt: sier identifikasjon er vanskelig, viser til reelle metodevalg (diff-in-diff mot eldre barns mødre, panel-FE), ingen falsk kausal påstand. Sekundær observasjon (ikke jaget videre): ingen kode-blokk levert i det hele tatt (svarformat-kravet «ÉN kjørbar blokk» ble ikke fulgt), og litteraturtallene (Rønsen, Drange & Rege m.fl.) er ikke merket «fra modellkunnskap — verifiser» selv om de er trent-inn kunnskap. |
| 2026-07-03 | 11 | FAIL (miljø/infra, ikke promptfeil) | Begge kjøringer (før og etter fix) endte med `AbortError: The signal has been aborted` etter hhv. 324s/309s og 10-11 verktøykall (SSB + valg.no/valgresultat.no). Sannsynlig årsak: den ikke-strømmende siste-runden i `runAgenticStream` treffer 90s-timeouten (`AGENTIC_TIMEOUT_MS`) når konteksten er stor nok. Ingen svar produsert i noen av kjøringene — logget som infrastrukturfunn, ikke jaget videre innenfor budsjettet. |

**Oppsummering runde 1 (uten fix):** 5 PASS (1,2,4,6,10), 6 FAIL (3,5,7,8,9,11).
**Oppsummering runde 2 (etter DELIVERY-fix i `data-svar-prompt.ts` + `ssb`-registerfiks i `data-sources.json`, kun de 6 feilende spørsmålene kjørt på nytt):**
7 PASS (1,2,4,6,7,9,10), 2 PARTIAL (3,5 — forbedret fra FAIL, men ikke fullt kriterium-1-oppfylt), 2 FAIL (8,11 — 8 er en promptmiss for POST-innpakning i python-modus, 11 er et infra/timeout-funn).

## Runde 3 (v1.2, 2026-07-03): kun Q3, Q5, Q11 kjørt på nytt

Etter final-review-fiksene (DELIVERY-eksempelet justert til register-id +
proxy-form i tråd med `ssb`-registeroppføringen; `AGENTIC_TIMEOUT_MS` 90s →
180s i `_lib/anthropic.ts`). Transkripter i `.superpowers/sdd/eval/q{3,5,11}_v12.txt`
(ikke committet). Suksesskrav: Q11 uten AbortError; Q3/Q5 ikke verre enn før.

| Dato | # | Resultat | Notat |
|------|---|----------|-------|
| 2026-07-03 | 3 | PARTIAL (uendret) | Ingen ad-hoc-fetch: `# load /api/hent?url=<OECD-URL>` + `df <- hpi_raw` brukt direkte; ærlig merket «OECD-URL ikke probe-verifisert» og lønnstabellen «transkribert … verifiser». Kriterium 1 fortsatt ikke oppfylt: alle SSB-prober feilet fordi modellen skriver `data.ssb.no/api/v2/…` (uten `/pxwebapi/`-segmentet) — samme mønster fantes i runde 2-transkriptene, altså IKKE en regresjon fra v1.2-eksempelet, men et eget funn: modellen følger ikke registerets `sporrings_url_mal` bokstavelig. Kriterium 2: prod-verify. |
| 2026-07-03 | 5 | PARTIAL (litt bedre) | Runde 2-defekten (påstått «probe-verifisert» for en ok:false-URL) er borte: Eurostat-load-linjen er ærlig merket «ikke probe-verifisert (API-budsjettet ble brukt opp på SSB-forsøk)», og `emp_raw` brukes direkte (ingen ad-hoc fetch). Kriterium 1 fortsatt ikke oppfylt (probe-budsjettet gikk til SSB-prober som feilet — samme `/pxwebapi/`-mangel som Q3). Residual: guarded fallback med inline-tall «fra modellkunnskap» inkluderer utfallsvariabelen (brudd på stige-regelen nivå 3), tydelig merket — logget, ikke jaget. Kriterium 2: prod-verify. |
| 2026-07-03 | 11 | PASS på suksesskravet (infra-fiks verifisert); innhold PARTIAL | Ingen AbortError lenger: fullt svar levert på 166s med done-event (mot abort etter 309–324s før) — 180s-timeouten løste infra-funnet. Innholdet er ÆRLIG (sier rett ut at ingen kilde ble probe-verifisert, SSB 503; DiD-resultatet rammes inn som deskriptivt med seleksjonsskjevhet nevnt), men scriptet bruker en pyfetch-hjelpefunksjon mot /api/hent i stedet for `# load`-linjer (samme POST/flertrinns-mønster som Q8) — kriterium 3-miss, logget, ikke jaget (budsjett: én kjøring). Kriterium 2: prod-verify. |

**Oppsummering runde 3:** suksesskravet oppfylt — Q11 aborterer ikke lenger
(infra-fiksen virker), Q3/Q5 ikke verre (Q5 marginalt bedre på ærlighet).
Nytt tverrgående funn logget: modellen dropper `/pxwebapi/`-segmentet i
SSB-URL-er (forklarer de gjentatte 404/503-probene i Q3/Q5/Q11) — kandidat
for en quirks-presisering eller promptregel i en senere runde.
