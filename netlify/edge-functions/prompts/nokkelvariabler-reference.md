<!-- Nøkkelvariabler (linking keys) i microdata.no.
Kilde: microdata.no variabelkatalog (kategori "nøkkelvariabler"), levert av bruker 2026-05-28.
Brukes som kilde for RELATIONS_LINKS-blokken i kode-svar.ts. Selve katalogen i
prompten genereres fra variable_metadata.json; denne fila forklarer ROLLEN til
disse variablene (kobling), som den flate katalogen ikke viser. Oppdater ved
endringer på microdata.no.

Alle er Numerisk (heltall) pseudonymer/ID-er MED MINDRE annet er nevnt (kommune-
variablene er Alfanumeriske kommunekoder). Pseudonymer brukes KUN som nøkkel i
collapse(by) / merge(on) — aldri i analyse. -->

# microdata.no — nøkkelvariabler (koblingsnøkler)

Egne variabler som kobler informasjon (a) mellom personer (familie),
(b) fra hendelses-/entitetsregistre til person, og (c) til geografi/enhet.
Kategorier (antall): Familie (1), Foretak (2), Husholdning (2), Kommune (21),
Person (13), Søsken (1), Trafikkulykke (1), Virksomhet (2).

## Person ↔ person (familie-pekere)
Hver peker ligger på personens egen rad og er pseudonymet til slektningen
(= slektningens egen PERSONID_1). Koble ved å merge `on <peker-alias>`.
- `BEFOLKNING_FAR_FNR` — far (Fast)
- `BEFOLKNING_MOR_FNR` — mor (Fast)
- `BEFOLKNING_FARFAR_FNR` — farfar (Fast)
- `BEFOLKNING_FARMOR_FNR` — farmor (Fast)
- `BEFOLKNING_MORFAR_FNR` — morfar (Fast)
- `BEFOLKNING_MORMOR_FNR` — mormor (Fast)
- `BEFOLKNING_EKT_FNR` — ektefelle (Tverrsnitt, 1975–2025)
- `BEFOLKNING_SAMB_FNR` — samboer (Tverrsnitt, 1987–2025)
- `BEFOLKNING_SOESKEN_FNR` — søsken (Fast) [kategori: Søsken]

## Gruppere personer (familie / husholdning)
Felles gruppe-id for personer som hører sammen. Collapse/merge `by`/`on` denne.
- `BEFOLKNING_REGSTAT_FAMNR` — familienummer (Tverrsnitt, 2005–2025) [Familie]
- `BEFOLKNING_HUSHNR` — husholdningsnummer bohusholdning (Tverrsnitt, 2005–2025)
- `INNTEKT_HUSHNR` — husholdningsnummer (Tverrsnitt, 2004–2024)

## Entitet/hendelse → person (fler-rad-per-person)
Registre der én person kan ha mange rader. Person-ref-kolonnen kobler raden til
personen; collapse `by(person-ref)` for å aggregere til person-nivå.
- Jobb (A-ordningen) → `ARBEIDSFORHOLD_PERSON` (enhetstype Jobb, Fast)
- Kjøretøy → `KJORETOY_KJORETOYID_FNR` (enhetstype Kjøretøy, Tverrsnitt 1998–2024)
- Kurs → `NUDB_KURS_FNR` (enhetstype Kurs, Fast)
- Elhub målepunkt → `ELHUB_PERS_MALEPUNKTID_FNR` (enhetstype Målepunkt, 2020–2026)
- Foretak (personens hovedarbeidsforhold) → `REGSYS_FRTK_ID_SSB` (2015–2025),
  `REGSYS_ORGFOR` (2000–2014) [Foretak]
- Virksomhet (personens hovedarbeidsforhold) → `REGSYS_VIRK_ID_SSB` (2015–2025),
  `REGSYS_ORGBED` (2000–2014) [Virksomhet]

## Trafikkulykke
Eget register; hver rad er en person involvert i en ulykke (enhetstype "Person i
trafikkulykke", Fast).
- `TRAFULYK_PERS_FNR` — kobler raden til personen
- `TRAFULYK_PERS_TRAFULYK` — ulykke-id (samme verdi = samme ulykke; bruk for å
  finne personer involvert i samme ulykke)

## Kommune (geografi) — 21 variabler
Alfanumeriske kommunekoder (strenger — ingen numeriske operasjoner). Brukes som
`by()`-nøkkel for regional statistikk, eller for å koble til kommune-nivå data.
Bosted (vanligst): `BEFOLKNING_KOMMNR_FAKTISK` (faktisk adresse, 2014–2025),
`BEFOLKNING_KOMMNR_FORMELL` (folkeregisteret, 1989–2026). Fylke = `substr(komm, 1, 2)`.
Øvrige (register-spesifikke):
- `ARBLONN_ARB_ARBKOMM` — arbeidsstedskommune (A-ordningen, enhetstype Jobb)
- `ARBLONN_PERS_KOMMNR` — bostedskommune (A-ordningen)
- `ARBSTATUS_ARB_KOMM_NR` — arbeidsstedskommune, hovedarbeidsforhold
- `ARBSTATUS_PERS_KOMM_NR` — bostedskommune
- `REGSYS_ARB_ARBKOMM` — arbeidsstedskommune, hovedarbeidsforhold (2015–2025)
- `REGSYS_ARBKOMM` — arbeidsstedskommune (2000–2014)
- `BARNEVERN_KOMM` — kommune oppgavegiver (barnevern)
- `BEFOLKNING_FOEDEKOMMNR` — fødekommune (Fast)
- `BEFOLKNING_SVALBARD_KOMMNR` — bosted Svalbard
- `BOSATTEFDT_BOSTED` — bostedskommune (Forløp, 1991–2024)
- `ELHUB_PERS_MALEPUNKT_ADR_KOMMUNE` — kommune målepunkt
- `INTRO_AVSL_OPPFOLG_KOMMNR` — avslutningskommune (introduksjonsprogram)
- `INTRO_FORST_BOSETTING_KOMMNR` — første bosettingskommune
- `INTRO_OPPFOLG_KOMMNR` — oppfølgingskommune
- `NUDB_KOMM_16` — bostedskommune ved fylte 16 år (Fast)
- `NUDB_KURS_SKOLEKOM` — skolekommune (enhetstype Kurs, Forløp)
- `SOSHJELP_KOMMUNE` — utbetalingskommune (sosialhjelp)
- `TRAFULYK_KOMMUNE` — ulykkeskommune (enhetstype Trafikkulykke)
- `VALG_MANNTALL_KOMMNR` — manntallsført kommune (valg)
