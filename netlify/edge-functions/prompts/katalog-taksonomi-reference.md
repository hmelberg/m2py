<!-- Katalog-taksonomi for microdata.no, levert av bruker 2026-05-28.
Bakgrunnsinfo om databanker, emner, datatyper, enhetstyper og temporalitet.
Brukes for å begrunne reglene i kode-svar.ts (særlig temporalitet→import og
enhetstype→struktur). Selve katalogen genereres fra variable_metadata.json.

Merk: emne/topic-taggene finnes IKKE i variable_metadata.json, så de kan ikke
vises per variabel i prompten — denne fila er kun orientering. -->

# microdata.no — katalog-taksonomi

## Databanker
- `no.ssb.fdb` — versjon **53**, 729 variabler (all SSB-registerdata).
- `no.fhi.npr` — Norsk pasientregister (egen databank i VÅR versjon, i tillegg
  til SSB FDB).

## Datatype (av 729)
- Numerisk (heltall): 360
- Alfanumerisk: 273
- Numerisk (desimaltall): 94
- Instant: 2

## Enhetstype (hva en rad representerer)
- Person: 496
- Kommune: 112  (geografiske nøkkel-/kodevariabler)
- Jobb: 53  (arbeidsforhold; person-ref `ARBEIDSFORHOLD_PERSON`)
- Kjøretøy: 25  (person-ref `KJORETOY_KJORETOYID_FNR`)
- Kurs: 16  (person-ref `NUDB_KURS_FNR`)
- Trafikkulykke: 11  /  Person i trafikkulykke: 10  (`TRAFULYK_PERS_*`)
- Målepunkt: 6  (Elhub; person-ref `ELHUB_PERS_MALEPUNKTID_FNR`)

Enhetstype ≠ Person ⇒ entitetsdata i eget datasett; koble til person via
collapse + merge på nøkkelvariabel (se nokkelvariabler-reference.md).

## Temporalitet (av 729) — bestemmer import-kommando
- Akkumulert: 281 — `import` med ÉN dato (akkumulert fram til datoen)
- Tverrsnitt: 246 — `import` med ÉN dato (verdi ved tidspunktet)
- Fast: 135 — `import` uten dato (uendret over tid)
- Forløp: 67 — `import-event db/VAR <fra> to <til>` (hendelsesdata → paneldatasett)

(Det finnes INGEN "Event"-temporalitet. Panel-analyse — `summarize-panel`,
`tabulate-panel`, `transitions-panel`, `regress-panel` — krever paneldatasett
bygd med `import-panel`, `import-event` eller `reshape-to-panel`.)

## Nøkkelvariabel-kategorier (antall)
Familie (1), Foretak (2), Husholdning (2), Kommune (21), Person (13),
Søsken (1), Trafikkulykke (1), Virksomhet (2). Detaljer: nokkelvariabler-reference.md.

## Emner (antall variabler) — kun orientering (ikke per-variabel i katalogen)
A-ordningen (62), Arbeid og lønn (148), Arbeidsledighet (16), Arbeidsmarked (62),
Arbeidsmiljø/sykefravær/arbeidskonflikter (4), Arbeidssøker (12), Avfall (2),
Avfall frå hushalda (2), Barn/Familie og husholdninger (39), Barne- og familievern (6),
Barnevern (6), Befolkning (72), Boforhold (21), Bostøtte (13), Eiendomsskatt (4),
Ekteskap og skilsmisser (1), Elhub (6), Energi og industri (6), Familie (9),
Familie og husholdninger (1), Fødte og døde (4), Grunnskole (35), Husholdning (45),
Høyere utdanning (33), Inntekt (63), Inntekt og forbruk (111), Inntekt og formue (10),
Innvandrere (18), Introduksjonsprogrammet (11), KOSTRA (112), Karakter (19),
Kjøretøy (25), Kommunale finanser (109), Kommuneregnskap (105), Kriminalitet (10),
Kriminalitet og rettsvesen (10), Landtransport (46), Levekår (21), Lånekassen (9),
Lønn (62), Motorvogn (25), Natur og miljø (2), Offentlig sektor (109), Populasjon (1),
Samboere (1), Skatt for personer (52), Sosiale forhold og kriminalitet (95),
Sosialhjelp (8), Standpunktkarakter (19), Statistikkbanken (112), Svalbard (1),
Sykefravær (3), Sysselsetting (126), Tilknytning til arbeid/utdanning/velferd (40),
Trafikkulykke (21), Transport og reiseliv (46), Trygd og stønad (58), Utdanning (95),
Utdanningsnivå (20), Valg (6), Videregående utdanning (28),
Virksomheter og foretak (13), Virksomheter/foretak/regnskap (13),
Økonomisk sosialhjelp (1).
