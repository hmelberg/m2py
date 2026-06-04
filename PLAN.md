# Plan: dele, åpne og lagre scripts — «tre verb»-løsningen

Status: planlagt, ikke implementert. Gjelder `index.html` (script-editoren).

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
