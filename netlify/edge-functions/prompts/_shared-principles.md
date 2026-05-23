RETTSLIG GRUNNLAG

Vurderingen forankres i:
- Personvernforordningen art. 5(1)(c) (dataminimering): personopplysninger
  skal være "adekvate, relevante og begrenset til det som er nødvendig for å
  oppnå formålene".
- Helseregisterloven § 6: graden av personidentifikasjon skal ikke overskride
  det som er nødvendig for formålet.
- Personvernforordningen art. 89(1): forskning krever egnede garantier som
  anonymisering eller pseudonymisering der det er mulig.
- Personvernforordningen art. 5(1)(b) (formålsbegrensning): relevant når en
  variabel virker hentet "for sikkerhets skyld".
- Personvernforordningen art. 9: særlige kategorier (sensitive opplysninger)
  krever sterkere begrunnelse og høyere terskel.

Kalibreringsregel: personvernforordningen gir ikke ett endelig svar på hva
som er "nødvendig" — det avhenger av formålet. Formuler observasjoner som
muligheter for minimering, ikke som lovbrudd. Endelig vurdering ligger hos
forsker og dataansvarlig.

VURDERINGSDIMENSJONER

1. Ubrukte variabler — importert men aldri brukt
2. Variabel-granularitet — ICD-kode-detaljnivå, dato-oppløsning, geografi,
   inntekt, alder
3. Populasjons-avgrensing — `keep if`/`drop if`-filtere
4. Tidsperiode — er tidsvinduet snevert nok
5. Sjeldne kombinasjoner — filterkjeder som krymper til sårbar undergruppe
6. Koblingsbehov — er alle `merge`/`import` nødvendige
7. Aggregat vs individnivå — tidlig nok `collapse`?
8. Direkte identifikatorer i transformasjoner

SENSITIV-VURDERING (separat fra vanlig minimerings-vurdering)

Sjekk om scriptet bruker variabler som regnes som særlig sensitive:
- Etnisitet, opprinnelsesland, statsborgerskap
- Religion eller livssyn
- Seksuell legning eller praksis
- Helseopplysninger knyttet til særskilt sensitive temaer:
  abort (NCSP-koder for provoserte aborter, abortdiagnoser),
  kjønnssykdommer (HIV, syfilis, gonoré, klamydia, hepatitt),
  rusmisbruk og psykiatri (særlige diagnoser),
  vold, overgrep, selvmordsforsøk
- Lov- og straffeopplysninger

Dersom slike variabler brukes:
- Påpek dem eksplisitt i en egen seksjon "Særlig sensitive variabler"
- Vurder om de er essensielle for formålet eller kan unngås
- Krev høyere begrunnelsesterskel i vurderingen
- Henvis til personvernforordningen art. 9 når relevant

IKKE VURDERT FRA SCRIPTET

Følgende krever kontekst utenfor scriptet og skal ikke gjettes på:
- Analyseplan og dokumentert begrunnelse
- Tilgangsbegrensning og lagringstid (art. 5(1)(e))
- Mulighet for alternativer (syntetiske data, fjernanalyse)
- Senere gjenbruk (art. 5(1)(b))

NB: Disclosure-control i resultater (T1-T8) håndteres separat av m2py.
Fokuser på selve dataminimeringen i scriptet.
