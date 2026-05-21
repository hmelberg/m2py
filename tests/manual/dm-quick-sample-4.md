# Sample 4 — Mixed (microdata + Python)

Forventet vurdering: språk detekteres som "mixed". AI vurderer microdata-delen for minimering og noterer Python-delen som etterbehandling.

```
import all from BEFOLKNING
collapse (mean) INNTEKT, by(KJOENN)
# Python-side analyse
import pandas as pd
df = pd.read_csv("result.csv")
df.plot()
```
