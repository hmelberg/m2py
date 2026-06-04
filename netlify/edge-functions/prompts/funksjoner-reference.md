<!-- Offisiell funksjonsreferanse for microdata.no.
Kilde: https://microdata.no/manual/kommandoer_og_funksjoner/funksjoner
Hentet: 2026-05-28.

Brukes som kilde for FN_GLOSS-glosene i kode-svar.ts. Selve funksjonslista i
prompten genereres fortsatt fra functions.py (kanoniske navn + signaturer);
denne fila er fasiten for beskrivelsene. Oppdater ved endringer på microdata.no. -->

# microdata.no — funksjoner

## Datobehandling
- `date(årstall, måned, dag)` — Datoverdi fra årstall, måned og dag. Datoer før 1970-01-01 gir negative resultater.
- `isoformatdate(dato)` — Konverterer fra datoverdi til formatet YYYY-MM-DD.
- `day(dato)` — Dag i måneden fra datoverdi (1–31).
- `month(dato)` — Månedsverdi fra datoverdi (1–12).
- `week(dato)` — Ukenummer fra datoverdi (1–53).
- `year(dato)` — Årstall fra datoverdi.
- `halfyear(dato)` — Halvårstall fra datoverdi (1–2).
- `quarter(dato)` — Kvartalstall fra datoverdi (1–4).
- `dow(dato)` — Dag i uken (1=mandag, 2=tirsdag, …, 7=søndag).
- `doy(dato)` — Dag i året (1–366).

## Sannsynlighetsberegning
- `binomial(variabel, n, p)` — Sannsynligheten for floor(n) eller færre suksesser i floor(variabel) forsøk.
- `binomialp(variabel, n, p)` — Sannsynligheten for floor(n) suksesser i floor(variabel) forsøk.
- `binomialtail(variabel, n, p)` — Sannsynligheten for floor(n) eller flere suksesser.
- `normal(x)` — Den kumulative standardiserte normalfordelingen.
- `normalden(variabel, μ?, σ?)` — Normalfordelingen med forventning μ og standardavvik σ.
- `F(variabel, v1, v2, λ)` — Kumulativ F-fordeling med v1 og v2 frihetsgrader.
- `Fden(variabel, v1, v2)` — Sannsynlighetstetthet til F-fordelingen.
- `Ftail(variabel, v1, v2, λ)` — Omvendt kumulativ F-fordeling.
- `invF(variabel, v1, v2)` — Invers kumulativ F-fordeling.
- `invFtail(variabel, v1, v2)` — Invers omvendt kumulativ F-fordeling.
- `invnFtail(variabel, v1, v2, λ)` — Invers omvendt kumulativ ikke-sentrert F-fordeling.
- `nF(variabel, v1, v2, λ)` — Kumulativ ikke-sentrert F-fordeling.
- `nFden(variabel, v1, v2, λ)` — Tetthet av ikke-sentrert F-fordeling.
- `nFtail(variabel, v1, v2, λ)` — Omvendt kumulativ ikke-sentrert F-fordeling.
- `chi2(variabel, v)` — Kumulativ kjikvadratfordeling med v frihetsgrader.
- `chi2den(variabel, v)` — Tetthet til kjikvadratfordelingen.
- `chi2tail(variabel, v)` — Omvendt kumulativ kjikvadratfordeling.
- `invchi2(variabel, v)` — Invers kumulativ kjikvadratfordeling.
- `invchi2tail(variabel, v)` — Invers omvendt kumulativ kjikvadratfordeling.
- `nchi2(variabel, v, λ)` — Kumulativ ikke-sentrert kjikvadratfordeling.
- `nchi2den(variabel, v, λ)` — Tetthet til ikke-sentrert kjikvadratfordeling.
- `nchi2tail(variabel, v, λ)` — Omvendt kumulativ ikke-sentrert kjikvadratfordeling.
- `betaden(variabel, α, β)` — Tetthet til beta-fordelingen.
- `ibeta(variabel, α, β)` — Kumulativ beta-fordeling (regularisert ufullstendig betafunksjon).
- `ibetatail(variabel, α, β)` — Omvendt kumulativ beta-fordeling.
- `invibeta(variabel, α, β)` — Invers kumulativ beta-fordeling.
- `invibetatail(variabel, α, β)` — Invers omvendt kumulativ beta-fordeling.
- `t(variabel, v)` — Kumulativ Students t-fordeling.
- `tden(variabel, v)` — Students t-fordeling (tetthet).
- `ttail(variabel, v)` — Omvendt kumulativ Students t-fordeling.
- `invt(variabel, v)` — Invers kumulativ Students t-fordeling.
- `invttail(variabel, v)` — Invers omvendt kumulativ Students t-fordeling.
- `invnttail(variabel, v, λ)` — Invers omvendt kumulativ ikke-sentrert t-fordeling.
- `nt(variabel, v, λ)` — Kumulativ ikke-sentrert Students t-fordeling.
- `ntden(variabel, v)` — Ikke-sentrert Students t-fordeling (tetthet).
- `nttail(variabel, v, λ)` — Omvendt kumulativ ikke-sentrert t-fordeling.

## Matematikk
- `acos(x)` — Radianverdien av arc-cosinus.
- `asin(x)` — Radianverdien av arc-sinus.
- `atan(x)` — Radianverdien av arc-tangens.
- `cos(x)` / `sin(x)` / `tan(x)` — Trigonometriske funksjoner.
- `comb(x, y)` — Kombinatorisk verdi x!/{y!(x−y)!}.
- `sqrt(x)` — Kvadratrot.
- `exp(x)` — Eksponentialfunksjonen e^x.
- `ln(x)` — Naturlig logaritme.
- `log10(x)` — Base 10-logaritme.
- `lnfactorial(x)` — Naturlig logaritme av x-fakultet, ln(x!).
- `logit(x)` — Logaritmen av oddsratioen, ln(x/(1−x)).
- `abs(x)` — Absoluttverdi.
- `ceil(x)` — Heltallsavrunding oppover.
- `floor(x)` — Heltallsavrunding nedover (samme som int()).
- `int(x)` — Heltallsverdien av x (dropper desimaler; samme som floor()).
- `round(x, y?)` — Avrunder til nærmeste heltall (uten y); y bestemmer avrundingsnivå.
- `quantile(x, y)` — Verdi basert på rangeringen av en kontinuerlig verdi over valgt inndeling.
- `pi()` — π.

## Behandle flere variabler (rad-vis)
- `rowmax(variabel, [...])` — Maksimumsverdien blant variablene.
- `rowmin(variabel, [...])` — Minimumsverdien blant variablene.
- `rowmean(variabel, [...])` — Gjennomsnittet blant variablene.
- `rowmedian(variabel, [...])` — Medianverdien blant variablene.
- `rowtotal(variabel, [...])` — Totalsummen av variablene.
- `rowstd(variabel, [...])` — Standardavviket for variablene.
- `rowconcat(variabel, [...])` — Sammenslåing av tekstverdiene.
- `rowmissing(variabel, [...])` — Antall missing-verdier blant variablene.
- `rowvalid(variabel, [...])` — Antall gyldige (ikke-missing) verdier blant variablene.

## Strengbehandling
- `length(verdi)` — Antall tegn i tekstverdien.
- `string(verdi)` — Konverterer verdien til alfanumerisk format.
- `lower(variabel)` / `upper(variabel)` — Små/store bokstaver (ASCII).
- `startswith(variabel, streng)` — 1 hvis verdien starter med tegnsekvensen.
- `endswith(variabel, streng)` — 1 hvis verdien slutter med tegnsekvensen.
- `substr(variabel, posisjon, lengde)` — Deltekst gitt ved startposisjon og lengde.
- `ltrim(variabel)` / `rtrim(variabel)` / `trim(variabel)` — Fjerner tomrom fra start / slutt / begge.

## Logikk
- `inlist(variabel, [...])` — 1 (true) dersom første variabel finnes blant de resterende.
- `inrange(variabel, min, max)` — 1 (true) dersom variabelen er ≥ min og ≤ max.
- `sysmiss(variabel)` — 1 (true) dersom variabelen er missing.

## Etiketter
- `label_to_code(variabel, etikett)` — Koden til etiketten fra variabelens kodeliste.
- `inlabels(variabel, etikett, [...])` — Filtrerer verdier basert på én eller flere etiketter i kodelisten.
- `labelcontains(variabel, etikett)` — Filtrerer verdier basert på etiketter som inneholder argumentet.

## Bindinger
- `date_fmt(årstall, måned?, dag?)` — Konverterer årstall til formatet yyyy-mm-dd (valgfri måned/dag).
- `to_int(tallformatert streng)` — Konverterer en tallformatert streng til et tall.
- `to_str(tall eller symbol)` — Konverterer et tall eller symbol til en streng.
- `to_symbol(streng)` — Konverterer en streng til et symbol (gitt at den er et gyldig navn).
- `bind(binding)` — Returnerer bindingen i argumentet. Nyttig for å referere til eksisterende bindinger.
