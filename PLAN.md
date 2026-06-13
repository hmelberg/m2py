# Plan: dele, åpne og lagre scripts — «tre verb»-løsningen

Status: **implementert** i `index.html` (script-editoren) — deling via
`#s=`-fragment («Del (kopier lenke)»), «Åpne fra URL», og GitHub-fillager
(Innstillinger/Åpne/Lagre i hamburgermenyen). Dette dokumentet er den
opprinnelige designen; behold som referanse.

## Mål og prinsipper

Gi brukeren tre tydelige handlinger for å flytte scripts inn og ut av appen,
**uten** at vi (operatøren) påtar oss noe lagrings-, personvern- eller
moderering-ansvar.

- **Alt er klient-side.** Ingen Anvil-/backend-endringer. Ingen database.
- **Ingen innlogging kreves** for noen av funksjonene. (GitHub-PAT er
  brukerens egen, lagres lokalt.)
- Hver funksjon svarer til ett distinkt verb — delemåtene konkurrerer ikke,
  og «GitHub» dukker bare opp ett sted (det valgfrie avanserte sporet).

## De tre verbene

### 1. Del — fragment-lenke
«Kopier en lenke som inneholder hele scriptet.»

- Bygg et objekt `{v:1, name, lang, script}`, `JSON.stringify` → gzip → base64url
  → legg i URL-fragmentet: `https://micro.fhi.dev/#s=<...>`.
- Fragmentet sendes aldri til server → vi lagrer ingenting, ser ingenting.
- Read-only, frosset øyeblikksbilde. Konto ikke nødvendig.
- **UI:** nytt menyvalg «Del (kopier lenke)» i `hamburgerDropdown`. Kopier til
  utklippstavle + vis «Lenke kopiert».
- **Åpning:** ved sidelast, hvis `location.hash` matcher `#s=...`, dekomprimer
  og fyll `scriptInput` + `scriptName` + sett editor-modus (`editorModeLabel`).
  Rens deretter hash med `history.replaceState`.
- **Grense:** ~8 000 tegn i URL. Lengre scripts: vis melding om at scriptet er
  for stort for delelenke (bruk fil-nedlasting eller GitHub i stedet).
- **Komprimering:** innebygd `CompressionStream('gzip')` /
  `DecompressionStream('gzip')` — intet bibliotek.

### 2. Åpne fra URL
«Lim inn en rå lenke til et script og hent det inn.»

- `fetch(url)` → legg teksten i `scriptInput`.
- Virker direkte med CORS: **GitHub raw**, **gist (raw)**, **Dropbox**
  (`dl.dropboxusercontent.com`). Andre kilder kan feile på CORS — da vis
  hjelpsom feilmelding («URL-en tillater ikke direkte henting; bruk en GitHub
  raw- eller gist-lenke»).
- **Husk siste URL-er** i localStorage (`m2py_recent_urls`, maks ~10) for rask
  gjenåpning uten å skrive hele URL-en.
- **Reload-knapp:** hent samme URL på nytt og legg i editoren.
- **UI:** nytt menyvalg «Åpne fra URL…» som åpner en liten modal med
  URL-input + liste over siste URL-er + Reload.
- *(Merk: appen har allerede «Web-eksempler» som laster fra `web_examples/` via
  `manifest.json` — dette er en separat, generell URL-åpner.)*

### 3. Koble til GitHub (avansert, valgfritt)
«Lagre og hent scripts i ditt eget GitHub-repo.» For de avanserte brukerne.

- **Oppsett-modal:** fine-grained PAT, `owner/repo`, branch (default `main`),
  evt. mappe/sti. Lagres i localStorage (`m2py_github_pat`, `m2py_github_repo`,
  `m2py_github_branch`). Vis tydelig: «Tokenet lagres lokalt i nettleseren din.»
- **Lagre (skriv):** `PUT /repos/{owner}/{repo}/contents/{path}` med
  base64-innhold + filas nåværende `sha` (hent eksisterende fil først for å få
  sha; utelat sha ved ny fil).
- **Hent (les):** `GET /repos/{owner}/{repo}/contents/{path}` — list mappe →
  velg fil → last inn i `scriptInput`.
- **Offentlig/privat** = brukerens egen repo-innstilling. Ikke et app-valg.
- **Deling for disse brukerne** = del repoets rå-URL → mottaker bruker verb 2.
  (Ingen egen «del som gist»-knapp — bevisst utelatt.)
- **PAT-oppretting (hjelpetekst i modalen):** Settings → Developer settings →
  Fine-grained tokens → repo-tilgang: kun det ene repoet → Repository
  permissions → Contents: Read and write. Org-repos kan kreve admin-godkjenning.

## Felles tekniske kroker (eksisterende kode)

| Hva | Element / funksjon |
|---|---|
| Editor (tekst) | `scriptInput` (textarea) |
| Scriptnavn | `scriptName` (input) |
| Språk/modus | `editorModeLabel` (Microdata / Python / R) |
| Meny | `hamburgerDropdown`; lukk med `dropdown.classList.remove('open')` |
| Linjenummer/sync | `window.updateLineNumbers()` etter å ha satt `scriptInput.value` |
| Eksisterende mønstre | `menuSave` (last ned), `menuLoad` (lokal fil), Web-eksempler-modal |

## Implementeringsrekkefølge

1. **Del (fragment)** — minst arbeid, umiddelbar nytte, null avhengigheter.
2. **Åpne fra URL** (+ siste-URL-er + reload).
3. **Koble til GitHub (PAT)** — størst, for avanserte brukere.

## Utenfor omfang / utsatt

- Anvil «Mine filer» (scripts-tabell + CRUD) og Anvil share-id-deling.
- Offentlig/privat-galleri på vår side (vil unngå moderering-ansvar).
- Admin-kuratert eksempelbibliotek utover dagens Web-eksempler.
- «Del som gist»-knapp, GDrive-lasting, poll-for-endring, glidende
  token-fornyelse, `/fetch`-proxy.
- Zero-knowledge passordkryptering, full GitHub/GDrive OAuth, webhooks.

## Implementeringsnotater

- **Template literal-backtick:** hver `` ` `` inne i en JS-template-literal må
  escapes som `` \` `` (har tidligere brutt Netlify-bygget). Relevant når vi
  bygger lenker/meldinger med template-literals.
- **CORS:** verb 2 og 3 avhenger av at målet sender CORS-headere. GitHub
  (raw + API) og Dropbox gjør det; vilkårlige URL-er kanskje ikke — håndter
  feil med klar melding heller enn stille feil.
- **PAT er en hemmelighet:** i localStorage er den lesbar for alt JS på
  domenet. Akseptabelt for intern bruk, men kommuniser det.

---

# Utvidelse: GitHub som filbasert lager (planlagt)

Forbedrer verb 3 fra «skriv inn én filsti» til et ekte lager: skill **oppsett**
(engangs) fra **bruk** (daglig), og gi en **filvelger** ved åpning.

## Menystruktur — GitHub-undermeny (valgt)

Speiler det eksisterende «Eksempler»-undermenymønsteret
(`menuExamplesBtn` → `examplesDropdown`).

```
Hamburgermeny
─────────────
Nytt script
Last ned kode            ← omdøpt fra «Lagre script» (nedlasting av .txt)
Last inn fil… (lokal)    ← dagens «Last inn script»
Del (kopier lenke)
Åpne fra URL…
GitHub ▸
   Innstillinger…        ← oppsett: PAT + repo + branch (+ test)
   Åpne fil…             ← filvelger
   Lagre                 ← skriv til gjeldende fil
   Lagre som…            ← ny sti
   Oppdater              ← hent gjeldende fil på nytt
```

## Fase 1 — Oppsett (engangs)

- Egen «Innstillinger»-dialog: PAT, repo (`eier/navn`), branch. **Ingen filsti.**
- Lagres lokalt (eksisterende nøkler `m2py_github_pat/repo/branch`).
- Valider med ett testkall `GET /repos/{repo}` → vis «✓ Tilkoblet» eller feil.
- Er ikke oppsett gjort, sender de andre GitHub-valgene brukeren hit først.

## Fase 2 — Bruk (daglig)

- **Åpne fil…** — ett kall `GET /repos/{repo}/git/trees/{branch}?recursive=1`
  lister alle filer i repoet. Vis i en liste med filter-felt, begrenset til
  tekst/script (`.txt`, `.py`, `.r`, `.md`). Klikk → hent via Contents-API →
  inn i editoren → sett som **gjeldende fil**.
- **Lagre** — `PUT …/contents/{gjeldende sti}` (henter `sha` først). Uten
  gjeldende fil ⇒ oppfør deg som «Lagre som».
- **Lagre som…** — skriv/velg ny sti (eksisterende mapper foreslås fra treet),
  lagre, sett som gjeldende fil.
- **Oppdater** — hent gjeldende fil på nytt (med bekreftelse; forkaster lokale
  endringer).

## Tilstand

- `m2py_github_current = { repo, branch, path }` i localStorage; settes ved
  Åpne / Lagre som / vellykket Lagre.
- **Gjeldende fil vises synlig** (ved scriptnavnet), så «Lagre» aldri er
  tvetydig.

## Implementeringsrekkefølge

1. Del oppsett fra filsti; innfør `current`-tilstand + indikator for gjeldende fil.
2. GitHub-undermeny i hamburgeren + omdøp «Last ned kode».
3. Filvelger (tre-henting + liste + filter).
4. Koble Lagre / Lagre som / Oppdater til `current`.

## Kanttilfeller / notater

- **Sha-konflikt ved Lagre** (filen endret på GitHub etter at vi leste den):
  `PUT` gir 409 → vis melding og tilby «Oppdater».
- **Tre-trunkering** for svært store repos (uaktuelt for scriptbruk).
- Tomt repo / ukjent branch → klare feilmeldinger.
- «Åpne fra URL» og «Del (lenke)» er uendret.

## Holdt utenfor (foreløpig)

- Mappe-*browser* med klikk-navigering (rekursivt tre + filter dekker behovet).
- «Del» som egen GitHub-knapp (for offentlig repo = bare kopier rå-lenken).

---

# Planlagt: kontekstuelt kilde-ikon ved filnavnet (ikke bygget ennå)

Ikonet ved filnavnet skal vise kildens *primærhandling*:

- **GitHub-fil (lese/skrive)** → 💾 **Lagre** (floppy), med amber farge ved
  ulagrede endringer. Klikk = lagre tilbake.
- **URL-fil (kun lese)** → ⟳ **Hent på nytt** (re-fetch). Klikk = hent URL-en
  på nytt (bekreft; forkaster lokale endringer). Ingen lagring mulig.
- **Nytt script / lokal fil / delelenke** → ingen kilde → intet ikon.

«Hent på nytt» **fjernes fra GitHub-undermenyen** og blir kun URL-ikonet.
GitHub-re-fetch skjer ev. via «Åpne fil» / «Nylige» (anbefalt variant —
unngår ordlyd-forvirringen). GitHub-menyen står igjen med: Innstillinger,
Åpne fil, Lagre, Lagre som.

## Implementeringssteg

1. Generaliser `m2py_github_current` → `currentSource` med `kind`
   (`github` | `url`); migrer gammel verdi.
2. Bygg om indikatoren til å vise floppy vs. refresh etter `kind`.
3. `fetchUrl` / recent-URL: sett kilde = `url` (i stedet for å nullstille).
   Fragment / lokal / nytt: kilde = ingen.
4. Koble refresh-ikonet → hent gjeldende URL på nytt (gjenbruk `fetchUrl`,
   med bekreftelse).
5. Fjern `ghMenuRefresh` fra GitHub-menyen (knapp + wiring + ikon-map + hjelp).
6. Behold ulagret/lagret-farge kun for GitHub (floppy); URL = nøytralt
   refresh-ikon.
7. Verifiser + oppdater hjelp.

## Avveiing

Mister ettklikks «pull/forkast» for GitHub; fortsatt mulig via «Åpne fil» /
«Nylige». Akseptert i anbefalt variant.
