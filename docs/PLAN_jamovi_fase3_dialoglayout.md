# Design: jamovi fase 3 del 1 — dialog-layout fra u.yaml + visuell polish

*Dato: 2026-07-09 · Status: til gjennomsyn · Bakgrunn: Hans 9/7: «Jeg vil gjerne at
dialogene og innholdet skal se bra ut og ha en god struktur. De kan virke litt rotete nå.»*

## Mål

Opsjonspanelene i jamovi-modus skal ha samme struktur som ekte jamovi: to-kolonners
rutenett, gruppeoverskrifter, innrykkede under-opsjoner som deaktiveres når
foreldre-valget er av, og sammenleggbare seksjoner — generert automatisk fra jamovi
sine egne layoutfiler, ikke håndkurert.

## Kilde: u.yaml (verifisert)

jamovi publiserer layout-kildefilene åpent:
`https://raw.githubusercontent.com/jamovi/jmv/master/jamovi/<analyse>.u.yaml`
(+ `jamovi/scatr` for scat). Filene inneholder hele strukturen:

- `VariableSupplier` + `TargetLayoutBox`/`VariablesListBox` — rollebokser m/ maxItemCount
- `LayoutBox` med `cell: {column, row}` — rutenett (typisk to kolonner)
- `Label` med children — gruppeoverskrifter
- `CheckBox` med nøstede children + `enable: (navn)`-uttrykk — under-opsjoner
- `RadioButton` med `optionName`/`optionPart` — List-opsjoner som radiogrupper
- `ComboBox`, `TextBox` (format: number), `CollapseBox` — nedtrekk, tallfelt, seksjoner

Versjonsmerknad: GitHub master kan ligge foran wasm-jmv 2.7.7. Generatoren validerer
derfor hvert opsjonsnavn mot vår vendored `jamovi-full.yaml` og DROPPER ukjente navn
med varsel — layouten kan aldri referere opsjoner motoren ikke har.

## Endringer

### 1. Vendoring
`tools/jmv_yaml/ui/<analyse>.u.yaml` — hentes én gang (curl-skript eller manuelt) for
de 13 fase 1-analysene. Sjekkes inn som resten av YAML-ene.

### 2. Generator (`tools/gen_jmv_specs.py`)
Nytt steg: parse u.yaml → kompakt `layout`-tre per analyse i `jmv_specs.js`:

```
node := { t: 'supplier', targets: [{name, max?}] }
      | { t: 'label',    label, children }
      | { t: 'grid',     cells: [{col, row, children}] }
      | { t: 'check',    name, label?, children? }
      | { t: 'radio',    option, part, label }
      | { t: 'combo',    name } | { t: 'text', name, label?, format }
      | { t: 'collapse', label, children }
enable-uttrykk: kun enkel form '(navn)' tas med som {enable: 'navn'}; annet ignoreres.
Ukjente node-typer (f.eks. ModelBuilder i linReg): barna flates opp der det gir mening,
ellers utelates de — analysen faller da tilbake til dagens flate rendering for de
opsjonene (aldri krasj).
```

Nye pytest-tester: ttestIS-layouten har Tests/Hypothesis-grupper med riktige
radio-parts; descriptives har collapse-seksjoner; alle refererte opsjonsnavn finnes
i options-lista.

### 3. Renderer (`js/modes/jamovi.js`)
`renderJmvLayout(layoutTree, spec, values, onChange)` erstatter dagens
`addSection`/`control`-løype når `spec.layout` finnes; ellers beholdes dagens
fallback (flat liste). Semantikk:

- Rollebokser bygges fra supplier/targets (samme klikk/pil-interaksjon som i dag)
- check-children rendres innrykket; disables (ikke skjules) når parent er false
- `enable: 'navn'`-felter disables når den navngitte opsjonen er falsy
- radio-gruppe skriver `values[option] = part`; grid → CSS grid med to kolonner
- collapse → dagens `jmv-section`-stil
- `JMV_SECTIONS`-kartet pensjoneres (fallbacken beholder generisk seksjonering)

### 4. CSS-polish (`css/modes/jamovi.css`)
Rutenett-spacing, innrykk med tynn venstre guidelinje for under-opsjoner,
disabled-stil (dempet + ikke klikkbar), konsistent label-typografi, mer luft mellom
grupper. Fargespråket beholdes som i dag.

## Verifisering

- pytest for generatoren (som over)
- Én browser-gjennomgang av ttestIS + descriptives + contTables med **2–3 screenshots**
  (dette er visuelt design — Hans skal kunne vurdere resultatet), sammenlignet mot
  ekte jamovi side om side
- Hans gjør endelig visuell vurdering manuelt

## Utenfor scope (senere i fase 3)

Ikoner i menyen, skjult toppmeny, scatr-wasm, ANOVA-familien, Model Builder-UI for
blocks/Terms (linReg beholder dagens syntetiserte blokk).

## Synk

Implementeres i safestat, speiles til openstat (samme filer + regenerert specs).
