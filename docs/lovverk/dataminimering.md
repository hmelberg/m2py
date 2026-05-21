# Prinsippet om dataminimering

**Kilde:** Helsedirektoratet, Normen, Faktaark 57
https://www.helsedirektoratet.no/normen/personvernprinsippene-faktaark-57/om-prinsippene-og-deres-funksjon/prinsippet-om-dataminimering

**Lovgrunnlag:**
- Personvernforordningen (GDPR) art. 5(1)(c)
- Helseregisterloven § 6

## Prinsippets formulering

> "Personopplysningene som behandles skal være adekvate, relevante og begrenset
> til det som er nødvendig for å oppnå de formålene som er fastsatt ved
> innsamling."

Helseregisterloven § 6 utdyper at "Graden av personidentifikasjon" ikke skal
overskride det nødvendige for formålet.

## Konkrete krav

For hver behandling må det vurderes:

- Om formålet kan nås med færre opplysninger.
- Om registrerte må være identifiserbar gjennom hele prosessen, eller om data
  kan pseudonymiseres / anonymiseres / aggregeres på et tidligere tidspunkt.

## Viktig nyanse

> "Personvernforordningen gir ingen endelig svar på hvilke personopplysninger
> som er nødvendig å behandle"

Vurderingen avhenger sterkt av formålet. Helsehjelp krever typisk flere
opplysninger enn personal­administrasjon. Familiehistorikk kan være nødvendig
for pasientutredning, men ikke ved ansettelsesvurdering.

## Vesentlig unntak

> "Prinsippet om dataminimering skal ikke tolkes så strengt at det kan gå ut
> over forsvarlig helsehjelp"

Pasientsikkerhet prioriteres. (Mindre relevant for forskningsscript, men
illustrerer at prinsippet skal kalibreres mot formålet.)

## Anvendelse på forskningsscript

I praksis for et microdata.no-script betyr dette at:

- Variabler som importeres men ikke brukes, bør fjernes.
- Granulariteten på hver variabel bør være den groveste som tjener formålet
  (kapittelnivå-ICD framfor full kode, måned/år framfor dato, aldersgruppe
  framfor eksakt alder, fylke framfor kommune der det holder).
- Populasjonen bør avgrenses så tidlig som mulig.
- Aggregering / pseudonymisering bør skje så tidlig i prosessen som mulig.
- Hver kobling mellom registre bør være begrunnet i formålet.

Disse vurderingene må alltid kalibreres mot det konkrete forsknings­formålet —
endelig avgjørelse ligger hos forsker og dataansvarlig.
