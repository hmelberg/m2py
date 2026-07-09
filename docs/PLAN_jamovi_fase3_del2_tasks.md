# jamovi fase 3 del 2 — implementeringsplan: toppmeny, ikoner, finpolish, flere analyser

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** jamovi-modus får skjult app-toppmeny (mer jamovi-følelse), ikoner i analysemenyen, visuell finpolish av opsjonspanelet, og flere analyser i menyen (de som er billige nå som u.yaml-layout genereres automatisk). scatr-wasm er eksplisitt UTSATT (Hans 9/7).

**Architecture:** Tre uavhengige forbedringer i js/modes/jamovi.js + css + index.html, pluss en utvidelse av PHASE1-listen i generatoren der hver kandidat røyk-testes i webR før den beholdes. Designbeslutninger: toppmenyen skjules i jamovi- og jamovilight-modus med en «Vis toppmenyen»-bryter i jamovi-hamburgeren; ikoner gjenbrukes fra v1-settet (jamovi_v1.js har SVG-ene) mappet til jmv-navn.

**Tech Stack:** som del 1. Verifisering: lean browser-sjekk; screenshots KUN for ikon/polish-tasken (visuelt).

## Global Constraints

- Motor- og layout-kontraktene fra del 1 er uendret (values-form, renderJmvLayout-nodeformat, buildJmvCall, stale-guard).
- Fredet: jamovi_v1-/jamovi_light-filene (men jamovi_light-MODUSEN skal også få skjult toppmeny — styres fra index.html, ikke fra de fredede filene).
- Alle nye analyser må: (a) finnes i wasm-jmv 2.7.7, (b) kjøre uten feil i webR på et testdatasett, (c) få u.yaml-layout eller akseptabel fallback. Kandidater som feiler (b) DROPPES fra PHASE1 igjen og noteres.
- Kodestil: var/IIFE/T(...); generator-stil som før. Branch: `jamovi-fase3-del2` fra master.

---

### Task 1: Skjult toppmeny i jamovi-modus

**Files:**
- Modify: `index.html` (modusbytte-logikk + CSS-offsets)
- Modify: `app.css` eller inline `<style>` i index.html (der `.topbar`-reglene bor — undersøk)
- Modify: `js/modes/jamovi.js` (hamburger-menypunkt)

**Interfaces:**
- Produces: body-klassen `topbar-hidden` styrer alt; `switchEditorMode` setter/fjerner den for modusene `jamovi` og `jamovilight`; localStorage-nøkkel `m2py_topbar_visible` = '1' overstyrer (bruker har valgt å vise).

- [ ] **Step 1: Kartlegg layout-avhengighetene.** `header.topbar` er `position:fixed` (44px) og innholdet under er offset deretter (se kommentaren rundt index.html:3978 og tilhørende CSS). Grep etter `topbar`-høyde/offset-regler i app.css/index.html og noter ALLE stedene som antar 44px (mode-gui-bar-posisjonering, editor/output-paneler, evt. scroll-beregninger i JS).
- [ ] **Step 2: Implementér.** `body.topbar-hidden .topbar { display:none; }` + juster hver offset fra Step 1 til 0 under `body.topbar-hidden` (CSS-variabel `--topbar-h: 44px` → `0px` er ryddigst hvis reglene lar seg samle). I `switchEditorMode` (index.html): sett/fjern klassen når målmodus er jamovi/jamovilight, MED localStorage-overstyring:
```js
var wantHidden = (target === 'jamovi' || target === 'jamovilight')
  && localStorage.getItem('m2py_topbar_visible') !== '1';
document.body.classList.toggle('topbar-hidden', wantHidden);
```
  Kall også `M.updateModeGuiBar()` etterpå hvis bar-posisjonen avhenger av toppmenyen.
- [ ] **Step 3: Bryter i jamovi-hamburgeren** (js/modes/jamovi.js, app-menyen med «Åpne eksempeldatasett…»): nytt punkt `T('Vis/skjul toppmenyen')` som toggler localStorage-nøkkelen og klassen umiddelbart. (jamovi_light er fredet — den får bare default-oppførselen fra Step 2, ingen egen bryter.)
- [ ] **Step 4: Verifiser (lean, ingen screenshots).** Bytt til jamovi → toppmeny borte, ingen hvit stripe/feil-offset (sjekk at jamovi-tabbaren ligger helt øverst og at output ikke hopper); Data-fanen og dialogene fungerer; bytt til python → toppmeny tilbake; jamovilight → borte; hamburger-bryteren viser/skjuler og huskes over modusbytte og reload. Konsoll ren.
- [ ] **Step 5: Commit** — "jamovi fase 3: toppmenyen skjules i jamovi-modusene (bryter i hamburgeren)"

---

### Task 2: Ikoner i analysemenyen + visuell finpolish

**Files:**
- Modify: `js/modes/jamovi.js` (ikon-kart + menygenerering)
- Modify: `css/modes/jamovi.css`

- [ ] **Step 1: Ikon-kart.** Lag `JMV_AN_ICONS = { descriptives: '<svg …>', ttestIS: …, … }` for alle analyser i PHASE1 (inkl. Task 3-tilskuddene — bruk et fornuftig default-ikon for navn uten eget). Gjenbruk SVG-ene fra `js/modes/jamovi_v1.js` sitt gamle `JAMOVI_ICONS`-objekt (descriptives, frequencies→propTestN, ttest_ind→ttestIS, ttest_paired→ttestPS, ttest_one→ttestOneS, anova_oneway→anovaOneW+anova, kruskal→anovaNP, correlation→corrMatrix, lin_reg→linReg, log_reg→logRegBin, contingency→contTables, gof→propTestN-alternativ) — KOPIER strengene, ikke referer til den fredede filen. scat: gjenbruk correlation-punktsvermen. Menygenereringen prepender ikonet i hvert `data-an`-knappeinnhold (samme mønster som v1: `svg + <span>`).
- [ ] **Step 2: Finpolish (sammenlign med ekte jamovi der du kan):**
  - Rolleboksene: fast min-høyde per maxItemCount (én-variabels bokser skal være lave), tydeligere «slipp her»-tomtilstand
  - Konsistent vertikal rytme: samme margin mellom grupper i og utenfor grid; seksjonskropper med litt mer luft
  - `.jmv-optgroup-label` nærmere jamovi (12px, #333, ikke fet kursiv-look)
  - Panelbredde: 440px → vurder 480px hvis gridene kniper
  - Variabellisten: zebra-striping av annenhver rad fjernes hvis den finnes; hover beholdes
- [ ] **Step 3: Verifiser med 2 screenshots** (ttestIS + descriptives, til `.superpowers/sdd/fase3del2-screens/`) — dette er visuelt og skal vurderes av Hans. Konsoll ren; `node --check`.
- [ ] **Step 4: Commit** — "jamovi fase 3: ikoner i analysemenyen + visuell finpolish av panelet"

---

### Task 3: Flere analyser i menyen

**Files:**
- Modify: `tools/gen_jmv_specs.py` (PHASE1 + u.yaml-henting for nye)
- Create: `tools/jmv_yaml/ui/<nye>.u.yaml`
- Modify: `tests/test_gen_jmv_specs.py`
- Regenerate: `js/modes/jmv_specs.js`

**Kandidater** (alle finnes i jmv 2.7.7; u.yaml hentes fra jamovi/jmv master):
`ancova`, `corrPart`, `logRegMulti`, `logRegOrd`, `contTablesPaired` (McNemar), `reliability`, `pca`, `efa`

- [ ] **Step 1:** Hent u.yaml for kandidatene (`curl` som i del 1, lowercase filnavn). Legg dem i PHASE1. Kjør generatoren — noter drift-varsler; sjekk at hver får layout (eller akseptabel fallback).
- [ ] **Step 2:** Utvid testene: kandidatene er med, har opsjoner og (der layout finnes) gyldige navn — gjenbruk eksisterende parametriserte sjekker (PHASE1-løkkene fanger dem automatisk; legg til én strukturtest for `ancova` med supplier dep/factors/covs).
- [ ] **Step 3: Røyk-test HVER kandidat i webR** (browser, lean): åpne analysen fra menyen på et passende datasett (clinicaltrial for ancova/reliabilitet-aktige; parenthood for corrPart/pca/efa; agpp for contTablesPaired; iris-lignende for logRegMulti — bruk lsj-eksemplene og `# requires`-frie standardløp). Kriterium: analysen kjører og gir tabeller uten R-feil med bare roller fylt. Kandidater som feiler (f.eks. manglende wasm-avhengighet à la websocket-saken): FJERN fra PHASE1, regenerer, og noter i rapporten hva som feilet og hvorfor (loadNamespace-spor hvis raskt tilgjengelig).
- [ ] **Step 4:** `pytest` grønn; commit — "jamovi fase 3: N nye analyser i menyen (ancova, corrPart, …)"

---

### Task 4: Synk openstat + roadmap

- [ ] Kopiér endrede filer til openstat (branch `jamovi-fase3-del2` fra main): js/modes/jamovi.js, js/modes/jmv_specs.js, css/modes/jamovi.css, tools/gen_jmv_specs.py, tools/jmv_yaml/ui/, tests/test_gen_jmv_specs.py + gjør Task 1-index.html/css-endringene for hånd i openstat (finn tilsvarende steder). md5-verifisér de kopierte filene; pytest + node --check i openstat.
- [ ] Huk av toppmeny- og ikon-punktene i docs/ROADMAP.md (begge repoer); oppdater «Flere analyser»-listen med hva som kom inn/falt ut.
- [ ] Commit begge repoer. IKKE push — Hans vurderer (særlig ikoner/polish og toppmeny-følelsen) først.

## Self-review-notater

- Task 1 og 2 er uavhengige; Task 3 avhenger kun av generatoren (del 1); Task 4 sist.
- jamovi_light-fredningen respekteres: toppmeny-skjuling styres i index.html (switchEditorMode), ikke i de fredede filene; bryteren finnes kun i nye jamovi-modusens hamburger.
- Ingen placeholder-steg: ikon-kilden er konkret (v1-fila), CSS-punktene er konkrete, kandidatlisten eksplisitt med drop-regel.
