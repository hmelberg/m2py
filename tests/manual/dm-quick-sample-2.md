# Sample 2 — Full analyse, overdetaljert

Forventet vurdering: forbedringspotensial. AI bør foreslå:
- Bytt full fødselsdato til år (BEFOLKNING_FOEDEDATO → BEFOLKNING_FOEDEAAR)
- Vurder fylke i stedet for kommune
- Fjern ubrukte variabler fra "import all"

```
import all from BEFOLKNING
import all from NUDB
keep if BEFOLKNING_FOEDEDATO >= 19700101
collapse (mean) INNTEKT, by(BEFOLKNING_KOMMUNENR)
```
