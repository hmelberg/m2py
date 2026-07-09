# jamovi fase 3 del 3 — implementeringsplan: Model Builder, refLevels, Friedman, Log-Linear

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modell-kontroll i dialogene (hovedeffekter/interaksjoner for anova/ancova/regresjonene, post hoc-ledd, referansenivåer per faktor) + de to siste enkle analysene (Friedman, Log-Linear). scatr-wasm og øvrige utsatte punkter røres IKKE.

**Architecture:** Tre byggeklosser i js/modes/jamovi.js: (1) `values`-utvidelse + `buildJmvCall`-utvidelse for term-lister og refLevels; (2) en «Modell»-seksjon (term-bygger) og refLevels-rader i panelet, injisert for analyser som har opsjonene (u.yaml-layouten dekker dem ikke — de droppes som ukjente typer i generatoren, med vilje); (3) asynkron nivå-henting fra Pyodide for refLevels. Pluss PHASE1-utvidelse for anovaRMNP/logLinear.

**Fakta (verifisert i vendored YAML):** `modelTerms`/`postHoc` er type Terms (anova, ancova); `blocks` er Array-of-Terms og `refLevels` er Array-of-Group{var,ref} (linReg, logRegBin, logRegMulti, logRegOrd, logLinear). Ingen rene Level-opsjoner finnes i utvalget.

## Global Constraints

- Kontrakter fra del 1/2 uendret (layout-nodeformat, stale-guard, live-oppdatering, rolleboks-interaksjon).
- DEFAULT-OPPFØRSEL BEVARES: når brukeren ikke rører modellbyggeren, skal R-kallet være som i dag (blocks syntetiseres av covs+factors for regresjonene; anova/ancova får jmv sin fulle faktorielle default; refLevels utelates). Eksplisitte verdier sendes KUN etter brukerinteraksjon.
- R-kallformater (jmv R-grensesnitt):
  - `modelTerms = list(c('a'), c('b'), c('a','b'))` — alltid c(...)-vektorer
  - `blocks = list(list(c('x1'), c('x2'), c('x1','x2')))` — fase 1-syntesen oppgraderes til samme form (én blokk)
  - `postHoc = list(c('a'), c('a','b'))`
  - `refLevels = list(list(var='drug', ref='placebo'), ...)`
- `values`-former: `modelTerms`/`postHoc`: `null` (auto) ELLER array av array-av-navn; `blocks`: `null` ELLER array med ÉN blokk (array av ledd); `refLevels`: `null` ELLER array av `{var, ref}`.
- Fredet: jamovi_v1-/jamovi_light-filene. Branch `jamovi-fase3-del3` fra master. Kodestil som før.

---

### Task 1: Motor + Modell-seksjon (term-bygger)

**Files:** Modify `js/modes/jamovi.js`, `css/modes/jamovi.css`

**Interfaces:**
- Produces: `buildJmvCall` håndterer de fire opsjonene per formatene over; `renderModelSection(spec, values, body, onChange)` — kalles av openJmvAnalysis etter renderJmvLayout når spec har `modelTerms` eller `blocks` i options.

- [ ] **Step 1: buildJmvCall.** Ny gren FØR den generiske løkka: opsjonene `modelTerms`, `postHoc`, `blocks`, `refLevels` hoppes over i den generiske løkka og håndteres eksplisitt:
```js
      function rTermVec(t) { return 'c(' + t.map(rQuote).join(', ') + ')'; }
      // modelTerms/postHoc: values er null (auto) eller [[navn,...],...]
      if (hasOpt('modelTerms') && values.modelTerms && values.modelTerms.length)
        args.push('modelTerms = list(' + values.modelTerms.map(rTermVec).join(', ') + ')');
      if (hasOpt('postHoc') && values.postHoc && values.postHoc.length)
        args.push('postHoc = list(' + values.postHoc.map(rTermVec).join(', ') + ')');
      if (hasOpt('refLevels') && values.refLevels && values.refLevels.length)
        args.push('refLevels = list(' + values.refLevels.map(function (r) {
          return 'list(var = ' + rQuote(r.var) + ', ref = ' + rQuote(r.ref) + ')';
        }).join(', ') + ')');
```
  `blocks`: erstatt fase 1-syntesen — hvis `values.blocks` er satt: `blocks = list(list(<ledd som c(...)>))` fra values.blocks[0]; ellers dagens auto-syntese (covs+factors som enkeltledd, i c(...)-form).
- [ ] **Step 2: Modell-seksjon.** `renderModelSection`: en `jmv-section` («Model», åpen) med:
  - Term-liste (`values.modelTerms` for anova/ancova, `values.blocks[0]` for regresjonene/logLinear): rader med leddnavn (`a` eller `a ✻ b` — jamovi bruker ✻) og ✕ for fjerning.
  - Auto-tilstand (`values.<x> === null`): grå tekst «Automatisk: alle hovedeffekter» + knapp «Tilpass modell» som materialiserer hovedeffektene (fra tilordnede covs/factors — HVILKE roller: les spec.options for rolle-navnene: anova/ancova: factors(+covs for ancova); regresjonene: covs+factors; logLinear: factors(+counts er ikke ledd)) inn i term-lista og aktiverer redigering.
  - Redigering: kilde-liste av tilordnede modell-variabler med flervalg (klikk = toggle valgt), knapper «→ Legg til» (hvert valgt navn som eget hovedledd) og «→ Interaksjon» (alle valgte som ETT interaksjonsledd; krever ≥2). Duplikatledd ignoreres (sammenlign sortert).
  - «Tilbakestill (automatisk)»-knapp → values tilbake til null.
  - postHoc (kun anova/ancova): under term-lista, en kompakt flervalgsliste av gjeldende ledd med tittel «Post Hoc-ledd» → values.postHoc (null hvis tom).
  - Endringer i rolleboksene (covs/factors) mens modellen er tilpasset: fjernede variabler lukes ut av leddene (ledd som mister alle komponenter fjernes); nye variabler legges IKKE til automatisk (jamovi-likt). Koble via eksisterende scheduleRun-sti — openJmvAnalysis kaller `refreshModelSection()` fra rolle-endringshandleren.
- [ ] **Step 3: openJmvAnalysis-integrasjon** — etter layout-rendring: `if (hasOpt('modelTerms') || hasOpt('blocks')) renderModelSection(...)`. CSS: gjenbruk section-/rolleboks-stil; term-rader som `.jmv-term-row` (flex, ✕ til høyre), kilde-liste maks-høyde 140px.
- [ ] **Step 4: Verifiser (lean).** clinicaltrial → ANCOVA: dep=mood.gain, factors=drug, covs=(en numerisk hvis finnes; ellers therapy som factor#2): «Tilpass modell» → legg interaksjon drug✻therapy → syntakslinjen viser `modelTerms = list(c('drug'), c('therapy'), c('drug', 'therapy'))` og tabellen får interaksjonsrad; fjern ledd → oppdateres; «Tilbakestill» → auto som før. parenthood → linReg: dep=dan.grump, covs=dan.sleep+baby.sleep, interaksjon → `blocks = list(list(c('dan.sleep'), c('baby.sleep'), c('dan.sleep', 'baby.sleep')))` og koeffisient-tabellen viser interaksjonen. postHoc: ANCOVA med postHoc på drug → Post Hoc-tabell dukker opp. `node --check`. Konsoll ren.
- [ ] **Step 5: Commit** — "jamovi fase 3: Modell-bygger (hovedeffekter/interaksjoner, blocks, post hoc-ledd)"

---

### Task 2: refLevels (referansenivåer med nivåer fra data)

**Files:** Modify `js/modes/jamovi.js`, `css/modes/jamovi.css`

**Interfaces:**
- Produces: «Reference Levels»-seksjon for analyser med refLevels-opsjon; `fetchLevels(varName): Promise<string[]>` (Pyodide, unike ikke-NA verdier som strenger, maks 50, sortert).

- [ ] **Step 1: fetchLevels** — gjenbruk mønsteret fra eksisterende engine-kall (py.globals.set + runPythonAsync): `sorted(set(str(v) for v in e.datasets[e.active_name][col].dropna().unique()))[:50]`, JSON tilbake. Cache per (datasett, kolonne) i et enkelt objekt som tømmes ved datasettbytte (hekt på jamoviSwitchDataset/jamoviLoadExample — samme sted som paneelinvalideringen fra del 1).
- [ ] **Step 2: Seksjon.** For spec med refLevels: en `jmv-section` («Reference Levels», kollapset) som viser én rad per tilordnet faktor-variabel (nominal i factors-rollen): variabelnavn + `<select>` med nivåene (async fylt; «(auto: første nivå)» som førstevalg = null-verdi). Bruker velger → `values.refLevels` oppdateres (kun rader der brukeren har valgt eksplisitt tas med; tom liste → null). Rolle-endringer re-bygger radene (samme hook som Task 1 Step 2 siste punkt).
- [ ] **Step 3: Verifiser (lean).** clinicaltrial → logRegBin-lignende er dårlig (binært utfall trengs) — bruk agpp: logRegBin dep=response (hvis binær; inspiser først), ellers lag syntetisk via ttestIS-datasett: harpo → logRegBin dep=tutor, covs=grade: Reference Levels viser tutor-rad med Anastasia/Bernadette; velg Bernadette → syntaks viser `refLevels = list(list(var = 'tutor', ref = 'Bernadette'))` og koeffisient-fortegnet snur. `node --check`. Konsoll ren.
- [ ] **Step 4: Commit** — "jamovi fase 3: referansenivå-velger (refLevels) med nivåer fra data"

---

### Task 3: Friedman (anovaRMNP) + Log-Linear (logLinear)

**Files:** Modify `tools/gen_jmv_specs.py` (PHASE1), Create `tools/jmv_yaml/ui/anovarmnp.u.yaml` + `loglinear.u.yaml`, Modify `tests/test_gen_jmv_specs.py`, Regenerate `js/modes/jmv_specs.js`

- [ ] Hent u.yaml (jamovi/jmv master, lowercase); legg begge i PHASE1; generator + tester (PHASE1-løkkene tar dem; legg til navnene i listene). Merk: logLinear har blocks/refLevels → får Modell-/RefLevels-seksjonene fra Task 1/2 automatisk (verifiser at hasOpt-logikken slår til).
- [ ] Røyk i browser: anovaRMNP med chico (measures = grade_test1+grade_test2) → Friedman-tabell; logLinear med agpp (factors = to kategoriske) → koeffisient-tabell. Feiler noe på manglende wasm-pakke: samme dropp-/stub-regel som del 2 (dokumentér).
- [ ] pytest grønn; commit — "jamovi fase 3: Friedman og Log-Linear i menyen (23 analyser)"

---

### Task 4: Synk openstat + roadmap

- [ ] Kopiér endrede filer (js/modes/jamovi.js, jmv_specs.js, jmv_helpers.R hvis endret, css/modes/jamovi.css, tools/gen_jmv_specs.py, tools/jmv_yaml/ui/, tests/test_gen_jmv_specs.py) til openstat på branch `jamovi-fase3-del3` fra main; md5 + pytest + node --check der.
- [ ] docs/ROADMAP.md begge repoer: huk av Level-typen (notér at den ble refLevels), Model Builder, og oppdater analyse-listene (gjenstår: RM ANOVA, MANCOVA, CFA).
- [ ] Commit begge. IKKE push — Hans vurderer.

## Self-review-notater

- values-formene og R-formatene er definert én gang (Global Constraints) og refereres fra Task 1/2 — ingen drift.
- Default-bevaring er eksplisitt krav (Task 1 Step 1: kun etter brukerinteraksjon) — dagens fase 1-syntese for blocks beholdes som fallback, oppgradert til c(...)-form (ren normalisering, samme semantikk i R).
- Friedman/logLinear gjenbruker alt fra del 2; logLinear er avhengig av Task 1/2 for full nytte men kjører også uten (auto-modell).
