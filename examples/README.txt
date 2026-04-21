Eksempelskript for Microdata
===========================
Kommentarer i microdata bruker // (ikke #).

Disse .txt-filene kan lastes inn i Microdata script runner (Hamburger-meny → Last inn script, eller dra-fra-eksempler hvis tilgjengelig).

01_beskrivende_statistikk.txt
  Opprett datasett, importer variabler (kjønn, inntekt, kommune), summarize med og uten gini/iqr og if-betingelse.

02_tabeller_og_kategorier.txt
  define-labels, assign-labels, list-labels, tabulate (frekvens, radprosent, top n), aggregate + tabulate med summarize.

03_visualiseringer.txt
  barchart, histogram, boxplot (med over()), scatter, piechart, hexbin. Bruker kodelister for lesbare etiketter.

04_aggregat_og_generate.txt
  generate (nye variabler), sample, aggregate (mean/count by kommune), collapse (aggregering til høyere nivå).

05_regresjon.txt
  ci (konfidensintervall), correlate (med sig), regress (OLS), regress-predict med predicted(pred).

06_avansert_analyse.txt
  normaltest, anova, import-panel, summarize-panel, tabulate-panel, transitions-panel.

Variabler brukt: fd/BEFOLKNING_KJOENN (kjonn), fd/INNTEKT_WLONN (inntekt), fd/BOSATT_KOMMUNE (kommune).
For panel: tidspunkter 2010-01-01, 2011-01-01, 2012-01-01.
