<!-- Source of truth for SCRUB_REFERENCE / SCRUB_REVISION_INSTRUCTION i dm-vurder.ts.
     Hold synkront med protect-pakkens dokumenterte defaults (protect/protect.py).
     Injiseres betinget når scriptet bruker scrub, eller når brukeren ber revidert
     script om å foreslå scrub (bruk_scrub). -->

SCRUB-KOMMANDOER (innebygd dataminimering, protect-pakken)

Scriptet kan bruke scrub-<verb>(variabel[, …][, key=value …]) i microdata, eller
scrub.<verb>(df, "kol", …) i Python/R. Dette ER de-identifisering på input-siden —
vurder dem aktivt og tolk argumentene for å bedømme STYRKEN, ikke bare at det finnes.
Ved bart kall (uten argumenter) gjelder defaultene under.

Virker bart (fornuftige defaults):
- jitter (scale=auto ≈ 1% av spennvidde; dato: 1 dag; share=1.0) — liten støy; verdien er fortsatt til stede
- noise (scale=auto ≈ 5% av SD; method=gaussian; share=1.0) — sterkere støy enn jitter
- winsorize (limits=(0.01,0.99); method=percentile) — kapper 1./99. persentil
- bin (bins=10; method=quantile) — 10 kvantil-intervaller
- year (bin=ingen) / month (bin=ingen) — trunkér dato til år / måned
- diff (ref=first_per_unit; unit=days) — dato → varighet (fjerner faktisk dato)
- shorten (keep=3; side=left) — beholder de første 3 tegnene av en kode (ICD/ZIP/NACE)
- pseudonymize (method=random) — bytter ID-er → PSEUDONYMT (fortsatt personopplysning, art. 4(5)/fortale 26), IKKE anonymt

Krever et argument — bart kall er ufullstendig (og feiler):
- collapse (rare_below=K | keep_top=N | keep_prop=p | mapping=…) — slår sammen sjeldne kategorier; høyere rare_below = sterkere
- coarsen (to=…) — snap til grovere oppløsning
- risk (quasi_ids=…) — k-anonymitet/l-diversitet/unikhets-rapport (endrer ikke data)

Spesielt:
- swap (method=rank; level=row; share=0.05) — NB: bytter bare 5% av radene som default ⇒ svakt med mindre share økes
- scrub-auto — type-bevisste defaults (dato→year, numerisk→jitter, kategorisk→collapse)

Universelle argumenter (alle verb):
- unit_id — transformasjonen trekkes én gang per enhet (microdata: default datasettets person-nøkkel) ⇒ konsistent per person
- share (1.0, unntatt swap=0.05) — andel enheter/rader som perturberes; share<1.0 ⇒ resten er URØRT (svakere)
- random_state — seed for reproduserbarhet

Bruk i vurderingen:
1. Gi kreditt for det scrubben faktisk beskytter — ikke gjenta som et problem.
2. Bedøm styrken ut fra de (oppgitte eller default) parametrene (svak: rare_below=2, share=0.1, keep=5; sterkere: rare_below=10, share=1.0).
3. Er verbet riktig for variabeltypen? En sensitiv variabel som bare jittres ⇒ verdien er fortsatt til stede.
4. Pseudonymisering er ikke anonymisering.

---

BRUK AV SCRUB I REVIDERT SCRIPT (kun når bruk_scrub er på)

Du KAN foreslå scrub-kommandoer for å minimere/de-identifisere der det er
forholdsmessig. Bruk riktig form for språket: microdata scrub-<verb>(variabel, …);
Python/R scrub.<verb>(df, "kol", …). Velg verb etter variabeltype og sett parametre
som gir reell beskyttelse (f.eks. collapse(rare_below=10) for sjeldne kategorier,
winsorize/jitter/noise for tall, year/coarsen for datoer). Ikke perturbér nøkler/ID-er
som trengs til kobling, og ikke bruk scrub der det ødelegger den analytiske intensjonen.
Forklar kort hvorfor i en // personvern:-kommentar (eller # personvern: for Python/R)
over hver scrub-linje.
