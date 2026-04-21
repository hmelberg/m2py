# Analyse: `summarize inntekt if kjonn == 1` gir tomt/feil resultat

## Observasjon

- `tabulate kjonn` viser **Mann 501, Kvinne 499** (labels brukes, data finnes).
- `summarize inntekt, gini iqr` gir forventet tall.
- `summarize inntekt if kjonn == 1, gini` gir **count 0** og alle "-" (tomt subset).

Altså: **if-betingelsen** `kjonn == 1` matcher ingen rader, så filtrert datasett blir tomt før summarize.

---

## Hvorfor kan `kjonn == 1` matche ingen rader?

### 1. Type-mismatch: kolonnen er streng, ikke tall

I koden:

- **Filtrering**: `df_target = df_target.query(cond).copy()` med `cond = "kjonn == 1"`.
- **Pandas `query()`**: Uttrykket evalueres med vanlige Python-regler. Da er `"1" == 1` **False** (streng vs. int).

Hvis kolonnen `kjonn` i DataFrame faktisk har **dtype object** (strenger `"1"` og `"2"`), vil:

- `kjonn == 1` (int) gi False for alle rader → filtrert df blir tom.

Generering i `MockDataEngine.generate()`:

- For variabler med `distribution` og ikke-alfanumerisk type bygges typisk:  
  `data[var_name] = [int(c) if isinstance(c, str) and c.isdigit() else c for c in raw]`.
- Det *forutsetter* at vi ikke senere overskriver kolonnen med strenger (f.eks. labels). Tabulate bruker labels kun ved *visning* (apply_labels_to_series på resultatet), ikke ved å erstatte verdier i selve datasettet.

Mulige årsaker til at kolonnen likevel blir streng:

- **Merge**: Ved `pd.merge(..., on='unit_id')` kan dtyper endres hvis den andre tabellen har andre typer eller NaN-kombinasjoner, slik at pandas faller tilbake til object.
- **Andre steder**: Noe annet som skriver til `df['kjonn']` med strenger (f.eks. label-tekst) vil føre til samme effekt.

Uansett: hvis `kjonn` i praksis er streng, forklarer det at `query("kjonn == 1")` gir 0 rader.

### 2. Alfanumerisk vs. numerisk i microdata.no

I ekte microdata:

- En variabel kan være **definert** som alfanumerisk (koder som strenger, f.eks. `"1"`, `"2"`) eller numerisk (1, 2).
- **Verdier i data** kan derfor være enten koder (tall eller strenger) eller label-tekst (f.eks. "Mann", "Kvinne") avhengig av datakilde og innlasting.
- **If-betingelser** bør derfor kunne skrives både som:
  - `kjonn == 1` (numerisk kode), og
  - `kjonn == "Mann"` (label), og kanskje også `kjonn == "1"` (streng-kode).

I vår app:

- Vi genererer BEFOLKNING_KJOENN som **int** (1, 2) i generate-logikken.
- Hvis kolonnen av en eller annen grunn ender som **object/streng**, vil kun sammenligning mot **samme type** fungere, f.eks. `kjonn == "1"` eller `kjonn == "Mann"` (hvis vi noen gang lagrer labels i kolonnen). Da vil `kjonn == 1` alltid gi tomt resultat.

Så problemet kan oppsummeres som: **enten** lagret datatype (streng vs. int), **eller** at vi ikke støtter både kode- og label-sammenligning i betingelsen.

### 3. Parsing av linjen (bekreftet ok)

For `summarize inntekt if kjonn == 1, gini`:

- Komma håndteres først: `line = "summarize inntekt if kjonn == 1"`, options får `gini`.
- Deretter splittes på `" if "`: `line = "summarize inntekt"`, `condition = "kjonn == 1"`.
- Kommando blir `summarize`, remainder `inntekt`, dvs. args og condition er som forventet.

Altså: **parsing er korrekt**; problemet ligger i evaluering av `cond` mot data (type eller innhold).

---

## Konklusjon og anbefaling (uten kodeendring)

1. **Sannsynlig årsak**: Kolonnen `kjonn` har i praksis **dtype object** (streng), så `query("kjonn == 1")` matcher ingen rader. Det bør sjekkes ved å logge eller inspisere `df['kjonn'].dtype` og noen verdier rett før `query(cond)` for denne kommandoen.

2. **Generelt (microdata.no-liknende oppførsel)**:
   - **Numeriske variabler**: `if kjonn == 1` bør bruke tall i data; kolonnen bør være int (eller minst sammenligning som 1.0 hvis float).
   - **Alfanumeriske variabler**: Både kode og label bør kunne brukes i betingelser, f.eks. `if kommune == "0301"` eller `if kommune == "Oslo"` (hvis vi har label-oppslag). Det krever at betingelses-evaluering enten:
     - normaliserer til kode før sammenligning, eller
     - tillater både `var == 1` og `var == "Mann"` (ved å slå opp label→kode der det er aktuelt).

3. **Neste steg (ved feilsøking)**:
   - Verifisere dtype og noen verdier for `kjonn` i det aktive datasettet rett før `df_target.query(cond)`.
   - Hvis kolonnen er streng: enten sikre at vi aldri lagrer kjonn som streng (f.eks. unngå object etter merge), eller utvide condition-evaluering slik at både `kjonn == 1` og `kjonn == "1"` (og evt. `kjonn == "Mann"`) håndteres.

Denne analysen er begrenset til å forklare og diskutere; ingen endringer er gjort i kodebasen.
