# Microdata Script Runner — docs

Dette er et hobbyprosjekt og er ikke laget av microdata.no selv. Siden inneholder ikke ekte tall, og det gis ingen garantier for at analysene er korrekt implementert.

## Avsløringskontroll og streng emulering

m2py forsøker som standard å oppføre seg som microdata.no — både med tanke på syntaks (avviser konstruksjoner som ikke kjører i prod) og sensurering av output (min populasjon 1000, små celler skjules, winsorisering, 3-sifret persentil-presisjon m.m.). Dette styres av ett valg "Avsløringskontroll" i hamburger-menyen (default PÅ).

For å overstyre per script, legg inn et direktiv øverst:

```
// m2py: disclosure-control=off
```

Direktivet er en vanlig kommentar som microdata.no ignorerer, så samme script kan kjøres begge steder. Se [`hjelp.html`](../hjelp.html) for full beskrivelse av reglene.

## Innhold

- **ANALYSIS_summarize_if_condition.md** — Analyse av hvorfor `summarize ... if kjonn == 1` gir tomt resultat (type-mismatch mellom streng og int).
- **PLAN_remove_fd_prefix.md** — Plan for å fjerne `fd/`-prefiks fra variabel-metadata i `variable_metadata.json` (ikke implementert).
