# Sample 1 — Full analyse, godt minimert

Forventet vurdering: god / akseptabel.

```
// personvern: formål: Inntektsforskjeller mellom kjønn for kohorten 1970
import variables KJOENN, INNTEKT from BEFOLKNING
keep if BEFOLKNING_FOEDEAAR == 1970
collapse (mean) INNTEKT, by(KJOENN)
```
