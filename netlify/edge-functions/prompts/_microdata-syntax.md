<!-- KOPI: microdata-syntaks-reglene her er en kopi av kjernen i
microdata-api/server_code/prompts.py (GRAMMAR_CHEATSHEET, PRIVACY_RULES,
PSEUDONYM_RULES, TYPE_RULES m.fl.). Hold synkront. -->

MICRODATA.NO-SYNTAKS — REGLER FOR REVIDERT SCRIPT

Hvis du foreslår endringer i microdata-DSL-del av scriptet, må endringene
være gyldig prod-syntaks:

GENERELLE REGLER
- `import all from <register>` eller `import variables (V1, V2) from <register>`
- `keep if <expr>` / `drop if <expr>` — populasjons-filter
- `generate <var> = <expr>` — ny variabel
- `replace <var> = <expr> if <cond>` — endre verdi
- `summarize <var> [if <cond>]` — beskrivende statistikk
- `tabulate <var> [<var2>]` — frekvenstabell
- `collapse (mean|sum|sd|count|median|min|max|p25|p75) <var>, by(<key>)` — aggregering
- `merge <var-list> into <dataset> [on <key>]` — kobling

STRICT EMULATION (avvist i prod)
- `collapse (first|last)` er IKKE støttet
- Multi-key `by(k1 k2)` eller `on(k1 k2)` er IKKE støttet — bruk composite key
- For-løkke-ellipsis (`for y in 1998, ..., 2009`) er IKKE støttet — bruk range `1998:2009`
- Parens rundt iterator-listen er IKKE støttet
- `for y in 1998 : 2009` (range) eller `for y in 1998, 1999, 2000` (komma) er OK

PSEUDONYM-REGLER
- Variabler med _FNR-suffiks (eller markert is_pseudonym i metadata) er
  pseudonymer.
- Pseudonymer kan KUN brukes som nøkkel i `collapse(by)` eller `merge(on)`.
- Aldri i `generate`, `replace`, sammenligninger, `string()`, `sysmiss()`.

TYPE-REGLER
- Alfanumeriske (string) variabler kan IKKE brukes i numeriske operasjoner:
  `mean`, `sum`, `min`, `max`, `sd`, `median`, persentiler — verken i
  `collapse` eller `summarize`.
- Bruk `tabulate` eller `count` for strenger.

MISSING VALUES
- `generate x = .` (tildeling til missing) er OK.
- `if x == .` (sammenligning) er IKKE støttet — bruk `if sysmiss(x)`.

REGISTERVARIABLER
- Bruk eksisterende variabelnavn fra registrene — ikke oppfinn nye.
- For grovere geografi: BEFOLKNING_KOMMUNENR (finest) → BEFOLKNING_FYLKE → BEFOLKNING_LANDSDEL.
- For fødselsdato: BEFOLKNING_FOEDEAAR (år) → BEFOLKNING_FOEDSELS_AAR_MND (år+mnd) → BEFOLKNING_FOEDEDATO (full).
