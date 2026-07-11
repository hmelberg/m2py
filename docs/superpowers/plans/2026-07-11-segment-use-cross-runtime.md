# Segment-scoped `# use` — eksplisitt datasync mellom runtimes i hybridscript

> Godkjent design 2026-07-11 (samtale med Hans). Utføres inline samme økt, safestat først.

**Mål:** `# use <navn> [from python|r|duckdb]` virker på BLOKKNIVÅ i hybridscript, så en `#r`-blokk kan bruke en ramme laget i en `#py`-blokk i samme script (og omvendt). Kopisemantikk (parquet-snapshot ved blokkgrensen). Kortform uten `from` er lov: kilden utledes som runtime-familien til nærmeste FOREGÅENDE segment med annen runtime enn blokken selv (feil hvis ingen).

**Vedtak fra Hans:** (1) kortform tillates; (2) safestat+openstat KUTTER implisitt micro→R-kopiering i R-modus — eksplisitt `use` kreves; microdata-repoen beholder implisitt (mer microdata-vennlig).

**Runtime-familier:** microdata/pyodide → `python` (deler heap, trenger aldri use seg imellom); `duckdb`; `r`.

## Tasks

1. **Parser (`js/data-directives.js` + tester):** `USE_RE` får valgfri `from`-del; `parseUse` beholder dagens kontrakt (from kan nå være null). Ny `parseSegmentUses(segments)` → per segment `{uses:[{name,from}], text:<uten use-linjer>, errors}` med inferens-regelen over. Node-tester for kortform, eksplisitt, inferens, tvetydighet-feil, stripping.
2. **Python-familie-løkka (`index.html` ~10290):** før hvert segment kjøres: materialiser segmentets uses — `from r`: nanoparquet-eksport fra webR → bytes → pyodide FS → `pd.read_parquet` bundet i `_g` + `e.datasets`; `from duckdb`: `__duckUseBytes` → samme binding; `from python` i python-familie-segment: feil («du er allerede i python»). Nye `kind === 'r'`-segmenter håndteres JS-side: uses inn i webR (python-kilde: to_parquet-glue → `parquetInjectionRCode`; duckdb: `__duckUseBytes`), kjør via `captureR`, render med `buildROutputNodes` — erstatter dagens STILLE ignorering.
3. **Run-start-use erstattes:** den globale use-håndteringen i python|duckdb-lastblokka fjernes — segmentnivå dekker den (én-blokks script: første blokkgrense = kjøringsstart, bakoverkompatibelt). Native SQL-vei fortsetter å avstå ved uses (Pyodide-fallback tar dem).
4. **R-modus (`runHybridR`):** (a) ukjente/`pyodide`-segmenter → tydelig feil («#py-blokker støttes i python-modus — bruk # use … from r der»); (b) implisitt kopier-alt-eksporten etter micro-fasen ERSTATTES av injeksjon av kun navngitte uses (samme parquet+labels-vei); run-start use-from-python/duckdb-logikken flyttes inn i samme segmentbehandling.
5. **Eksempler:** r03–r08 får `# use <navn>` i `#r`-blokken (safestat+openstat; microdata-repoens beholdes urørt). Sjekk r31/rex.
6. **Hjelp:** hybrid-seksjonen dokumenterer blokknivå-use + at micro→R nå er eksplisitt (safestat/openstat).
7. **Port:** openstat = som safestat. microdata = task 1+2+3 (parity for #r-i-python-modus og kortform), MEN beholder implisitt micro→R i R-modus og urørte r-eksempler.
8. **Deploy-disiplin:** sw.js CACHE-bump (data-directives.js endres). Verifisering: node-tester; headless: `#py → #r use df`-script i python-modus; r03-eksempelet med use i R-modus; feilmelding uten use; native SQL uendret.
