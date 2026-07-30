# Brukerdokumentasjon: fire spesialiserte hjelpesider

**Dato:** 2026-07-30
**Omfang:** `hjelp.html` + `hjelp.en.html` i safestat, openstat, askstat, microdata (8 filer)
**Kanonisk plassering:** denne spec-en bor i safestat; de tre andre repoene peker hit.

## Problemet

Alle fire hjelpesidene er nær-identiske kloner av samme dokument. De forteller
i praksis samme historie fire ganger, og hver app sitt faktiske særpreg er
enten fraværende eller klemt inn i et avsnitt på slutten.

Målt tilstand 2026-07-30:

| Fil | `<title>` | `<h1>` | Feil |
|---|---|---|---|
| `openstat/hjelp.html` | OpenStat – Dokumentasjon | OpenStat | Har «Microdata-kommandoer» som tredje seksjon — modusen ble fjernet 2026-07-24 |
| `safestat/hjelp.html` | Microdata Script Runner | Microdata Script Runner | Feil navn. Strict-seksjonen er ~15 linjer for tre dialekter |
| `microdata/hjelp.html` | Microdata Script Runner | Microdata Script Runner | Feil navn (skal være Microdata) |
| `askstat/hjelp.html` | OpenStat – Dokumentasjon | OpenStat | Feil navn. **Ingen** seksjon om ask, ruter, kataloger eller BYOK |

`nav-logo` sier «Script Runner» i alle fire. Alle fire har 16–18 `<h2>` som
overlapper nesten fullstendig, og bare 9 tabeller i hele dokumentet.

## Målet

Fire hjelpesider som hver leder med det appen faktisk er spesialisert på, med
korte innledninger og oversiktstabeller først, tematiske dybdeseksjoner under,
og kjørte eksempler som viser faktisk output.

Ikke i omfang denne runden: `docs/README.md` (utviklerdokumentasjon, utdatert i
alle fire), README-ene generelt. Unntak: `askstat/README.md` er en byte-kopi av
openstat sin og heter «OpenStat» — navn og førsteavsnitt rettes som en
bagatell.

## Identitet per repo

Rettes i `<title>`, `<h1>`, `nav-logo` og ledesetning, i både norsk og engelsk
versjon.

| Repo | `<title>` (no / en) | `<h1>` | `nav-logo` | Ledesetning (no) |
|---|---|---|---|---|
| openstat | OpenStat – Dokumentasjon / Documentation | OpenStat | OpenStat | Sju analysemotorer i nettleseren, samme datasett |
| safestat | SafeStat – Dokumentasjon / Documentation | SafeStat | SafeStat | Analyser beskyttede data uten at dataene forlater det trygge |
| microdata | Microdata – Dokumentasjon / Documentation | Microdata | Microdata | Emulator av microdata.no — skriv og kjør microdata-kode |
| askstat | AskStat – Dokumentasjon / Documentation | AskStat | AskStat | Spør på norsk, få kode og svar fra offentlig statistikk |

## Spesialisering

Verifisert mot `modeRegistry` i `index.html` og `LABEL_MODE`/`hostnameMode` i
`js/notebook-links.js`, 2026-07-30:

| Repo | Moduser i registeret | Default | Særpreg ingen søsken har |
|---|---|---|---|
| openstat | python, r, duckdb, brython, micropython, javascript, jamovi | `brython` | Sju motorer side om side; datadirektiver; API-kataloger. Ingen microdata, ingen statx |
| safestat | + microdata, safestat (remote) | `python` | Innlogging; beskyttede/krypterte kilder; restriktivt språk; federerte kilder; nøkkellager |
| microdata | microdata, python, r, statx, duckdb, brython | `microdata` (låst) | `hostnameMode()` og `urlHasMicro()` returnerer konstanter; py2m/r2m; avsløringskontroll |
| askstat | som openstat | `brython`, men ask-visning er default vis (`?view=editor` gir editoren) | Spørsmål → rute → kode → svar; SSB/PxWeb/SDMX/APD/DBnomics-oppdagelse; BYOK forbi adminGate |

Hva hver side **leder** med, og hva den korter ned:

| Repo | Leder med | Kortes ned til henvisning |
|---|---|---|
| openstat | Motorvalget: samme datasett, sju språk | Microdata-kommandoer (skal helt ut), avsløringskontroll |
| safestat | Tillitsmodellen: hvor koden kjører, hva som slipper ut | Motorsammenlikning |
| microdata | Emulatortroskapen: språket kommando for kommando | Andre moduser (kort modusmeny-notis) |
| askstat | Spørsmålsløkka: spørsmål → rute → kode → svar | Editor-detaljer |

## Struktur

Samme fire-lags skjelett i alle fire. Bare lag 1 er repo-spesifikt.

- **Lag 0 — Kom i gang.** Hero med ledesetning, en «30 sekunder»-boks med
  det korteste mulige første resultatet, og en «Denne siden dekker»-tabell.
- **Lag 1 — Kjernen.** Repo-spesifikk, leder dokumentet. Se dybdeseksjoner
  nedenfor.
- **Lag 2 — Felles verktøy.** Editor og snarveier, datasett-panel,
  lagre/dele/hente, Kjør skrittvis, AI-assistent, eksempler.

**Modusoversikten hører ikke til lag 2.** Modusene skiller seg per repo —
safestat har microdata og safestat (remote), microdata har statx, openstat og
askstat har javascript — så en byte-identisk fellesseksjon er umulig. Hver side
har sin egen modustabell, generert fra sitt eget `modeRegistry`. For openstat er
denne tabellen selve lag 1 («Motorvalget», utvidet med oppstartstid og
bibliotektilgang); for de tre andre er den en kort tabell i lag 2 med lenke
videre.
- **Lag 3 — Referanse.** Tabellene: kommandoer, direktiver, snarveier,
  Tab-autocomplete.

### Dybdeseksjoner per repo (lag 1)

| Repo | Seksjoner | Nye tabeller |
|---|---|---|
| openstat | Motorvalget · Datadirektiver · API-kataloger · Hybridskript · `pretty_output` | Motormatrise (7 motorer × oppstartstid, bibliotektilgang, når du velger den) · direktivsyntaks · katalog-`kind` |
| safestat | Tillitsmodellen · Beskyttede kilder · Restricted Python · Restricted R · Restricted SQL · Federerte kilder · Nøkkellager | Profil (OPEN/STRICT) × dialekt · tillatt/ikke tillatt per dialekt · hva fasaden frigir · federeringsverb |
| microdata | microdata-språket kommando for kommando · Avsløringskontroll-reglene · Avvik fra microdata.no · py2m/r2m | Kommandoreferanse · sensureringsregler (terskel → effekt) · avviksliste |
| askstat | Spørsmålsløkka · De fire rutene · Katalogene · Proveniens i generert kode · BYOK · Fra svar til editor | Rutetabell (`beregning`, `data`, `oppslag`, `språk`) · katalogtabell |

**Restricted Python og Restricted R får hver sin fulle seksjon**, ikke ett
felles avsnitt. Hver seksjon dekker: hva du kan skrive, hva som ikke finnes,
hva fasaden frigir, og kjørte eksempler — inkludert minst ett som blir
**avvist**, med den faktiske feilmeldingen.

Kilde for strict-innholdet: `vendor/safepy.zip`, `js/strict-worker.js`, og
`# options.profile = strict`-oppførselen. Bekreftet 2026-07-30: to profiler
(OPEN, STRICT), tre dialekter (python, r, duckdb).

## Layout og navigasjon

Bygger på CSS-en som finnes: 220 px sticky sidemeny, `prefers-color-scheme`
dark mode, klassene `doc-table`, `callout`, `card`, `badge`. Ingen ny
avhengighet, ingen byggesteg — sidene skal fortsatt være selvstendige filer
som virker offline.

| Grep | Hva det løser |
|---|---|
| Scrollspy i sidemenyen | Du ser hvor du er i et langt dokument |
| Filterfelt øverst i nav | Skriv «groupby» → nav-lenkene filtreres. Ren klientside, ingen indeks |
| Oversiktstabell først i hver hovedseksjon | Kort innledning og kart før detaljene |
| Todelt eksempelblokk: kode ‖ resultat | Side om side over 900 px, stablet under |
| Kopier-knapp på kodeblokker | Eksempler blir brukbare, ikke bare lesbare |
| Modus-badge på hvert eksempel (`py` `r` `sql` `micro`) | Du ser språket umiddelbart |
| Beholder eksisterende CSS-variabler | Ingen visuell brist mot resten av appen |

Scrollspy, filter og kopier-knapp implementeres som én liten inline
`<script>`-blokk nederst i hver fil, identisk på tvers av de fire (og dermed
dekket av synk-sjekken).

## Eksempler med faktiske resultater

Hvert eksempel kjøres før output limes inn.

| Type | Kjøres slik |
|---|---|
| Python, R, DuckDB, microdata-motoren | Lokalt: `.venv/bin/python`, `pytest`, `Rscript` |
| Brython, MicroPython, JavaScript | Mot `netlify dev` på localhost |
| Ask-svar, jamovi-dialoger, federerte spørringer | Mot `netlify dev` på localhost |

Skulle et eksempel vise seg umulig å kjøre, merkes resultatblokken **i teksten**
som illustrasjon. Ingen oppdiktede tall som utgir seg for å være kjørt.

Verifiseringsfellen fra `project_openstat_verify_felle` gjelder: Chrome cacher
`js/` over HTTP, og `netlify dev` cacher edge-TS-moduler. Hard-reload med
ignoreCache, og restart av `netlify dev` med en 400-smoke før evaluering.

## Synk-disiplin

Åtte filer skal ikke drive fra hverandre. Dagens tilstand er beviset på at de
gjør det: askstat sin hjelpeside het «OpenStat» uten at noe fanget det.

- **safestat er kanonisk** for lag 2 og 3, i tråd med at safestat leder UI.
- Fellesseksjonene holdes **byte-identiske** på tvers av de fire, slik at
  `diff` avslører drift. Repo-spesifikke ord (appnavn, ledesetning) bor bare i
  identitetsblokken og i lag 1 — aldri inne i en fellesseksjon.
- Lag 0 er **ikke** felles: hero, ledesetning, «30 sekunder»-boksen og «Denne
  siden dekker»-tabellen er repo-spesifikke per definisjon. Lag 0 har samme
  *form* i alle fire, men ikke samme innhold, og er unntatt synk-sjekken.
- Modustabellen er repo-spesifikk (se over) og er også unntatt synk-sjekken.
- Nytt skript `scripts/hjelp_sync_check.sh` sammenligner fellesseksjonene på
  tvers av søskenrepoene og gir exit 1 ved avvik. Seksjonsgrensene markeres med
  HTML-kommentarer: `<!-- SYNC:START felles-editor -->` … `<!-- SYNC:END -->`.

## Rekkefølge

1. **safestat** — kanonisk for fellesdelen, og har mest nytt innhold (strict × 3)
2. **openstat** — arver fellesdelen, får motormatrisen, mister microdata-seksjonen
3. **askstat** — arver fellesdelen, får hele ask-laget som er fraværende i dag
4. **microdata** — sist; avviker mest, minst gjenbruk

Norsk skrives ferdig per repo, engelsk oversettes umiddelbart etterpå i samme
runde, slik at de to ikke kommer i utakt.

## Ferdig når

- Alle åtte filer har riktig `<title>`, `<h1>`, `nav-logo` og ledesetning
- Hver side leder med sitt eget særpreg, med oversiktstabell før detaljer
- `openstat/hjelp.html` nevner ikke microdata-modus som eksisterende
- `askstat/hjelp.html` dokumenterer spørsmålsløkka, de fire rutene, katalogene,
  proveniens og BYOK
- `safestat/hjelp.html` har egne fulle seksjoner for Restricted Python og
  Restricted R, hver med et avvist eksempel og faktisk feilmelding
- Hvert kodeeksempel er kjørt, eller merket som illustrasjon i teksten
- `scripts/hjelp_sync_check.sh` går grønt i alle fire repoer
- Scrollspy, nav-filter og kopier-knapp virker; sidene virker offline
- `askstat/README.md` heter AskStat
