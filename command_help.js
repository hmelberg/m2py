// Hjelpetekster for microdata-kommandoer. Lastes av microdata_runner.html.
window.MICRODATA_COMMAND_HELP = {
  // Analyse
  "anova": {
    "syntax": "anova var-name var-list [if] [, options]",
    "description": "Analyse av varians/kovarians (ANOVA/ANCOVA) for én kontinuerlig avhengig variabel og én eller flere faktorvariabler. Første variabel er kontinuerlig, de neste er faktorer.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#anova"
  },
  "ci": {
    "syntax": "ci var-list [, options]",
    "description": "Vis konfidensintervaller og standardfeil for hver variabel i listen. Standard konfidensnivå er 95 %, kan endres med level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#ci"
  },
  "correlate": {
    "syntax": "correlate var-list [if] [, options]",
    "description": "Vis korrelasjonsmatrise (eventuelt kovarians) for variabler. Støtter opsjoner som covariance, pairwise, obs og sig.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#correlate"
  },
  "normaltest": {
    "syntax": "normaltest var-list [if]",
    "description": "Kjører flere normalitetstester (skewness, kurtosis, Jarque-Bera, Shapiro-Wilk) for valgte variabler eller hele datasettet.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#normaltest"
  },
  "transitions-panel": {
    "syntax": "transitions-panel var-name var-list [if]",
    "description": "Vis toveis overgangssannsynligheter mellom kategorier over tid for panelvariabler (overgangstabeller).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#transitions-panel"
  },

  // Bindinger
  "let": {
    "syntax": "let name = expression",
    "description": "Definer en binding (konstant) i klienten, uavhengig av datasettet. Brukes typisk til datoer, årstall eller andre gjenbrukbare verdier.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#let"
  },
  "for": {
    "syntax": "for i [, j] in (values | n : m) [, ...] [; g in ..]",
    "description": "Start en løkke over verdier eller intervaller. Kommandoene mellom for og end kjører for hver kombinasjon av iteratorverdier.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#for"
  },
  "end": {
    "syntax": "end",
    "description": "Avslutt en for-løkke eller textblock-seksjon og kjør kroppen for resterende iterasjoner (for-løkker).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#end"
  },

  // Datasett
  "require": {
    "syntax": "require datastore as local-alias",
    "description": "Opprett kobling fra versjonert datakilde til et lokalt alias som brukes ved import (f.eks. no.ssb.fdb:9 as fdb).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#require"
  },
  "create-dataset": {
    "syntax": "create-dataset new-dataset",
    "description": "Opprett et nytt tomt datasett og sett det aktivt.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#create-dataset"
  },
  "delete-dataset": {
    "syntax": "delete-dataset dataset",
    "description": "Slett hele datasettet og alle variabler i det.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#delete-dataset"
  },
  "use": {
    "syntax": "use dataset",
    "description": "Aktiver et eksisterende datasett når du har flere datasett i samme økt.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#use"
  },
  "clone-dataset": {
    "syntax": "clone-dataset dataset new-dataset",
    "description": "Lag en full kopi av et datasett med nytt navn.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clone-dataset"
  },
  "clone-units": {
    "syntax": "clone-units dataset new-dataset",
    "description": "Lag nytt datasett som inneholder samme enheter (populasjon) som et eksisterende datasett, uten variabler.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clone-units"
  },
  "rename-dataset": {
    "syntax": "rename-dataset dataset new-dataset",
    "description": "Gi nytt navn til et eksisterende datasett.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#rename-dataset"
  },
  "reshape-from-panel": {
    "syntax": "reshape-from-panel",
    "description": "Gjør om panel-/long-format til wide-format der opplysninger ligger horisontalt (én rad per enhet).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#reshape-from-panel"
  },
  "reshape-to-panel": {
    "syntax": "reshape-to-panel variable-prefixes",
    "description": "Gjør om wide-datasett til panel-/long-format basert på prefiks for variabelnavn (tidspunkt i suffiks).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#reshape-to-panel"
  },

  // Tilrettelegging
  "import": {
    "syntax": "import register-var [time] [as name] [, options]",
    "description": "Importer tverrsnittsvariabel fra register (eventuelt ved et gitt tidspunkt) inn i aktivt datasett. Kan bruke outer_join for full join.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#import"
  },
  "import-event": {
    "syntax": "import-event register-var time to time [as name] [, options]",
    "description": "Importer hendelses-/forløpsvariabel for gitt tidsintervall til et paneldatasett.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#import-event"
  },
  "import-panel": {
    "syntax": "import-panel register-var register-var-list time [time ...]",
    "description": "Importer variabler på flere tidspunkter i long/panel-format (flere rader per enhet).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#import-panel"
  },
  "generate": {
    "syntax": "generate name = expression [if]",
    "description": "Lag ny variabel definert ved et uttrykk. Støtter aritmetikk og funksjoner, med valgfri if-betingelse.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#generate"
  },
  "rename": {
    "syntax": "rename old-name new-name",
    "description": "Gi nytt navn til en eksisterende variabel i datasettet.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#rename"
  },
  "clone-variables": {
    "syntax": "clone-variables var-name [-> new-name] [...] [, options]",
    "description": "Lag kopier av én eller flere variabler, med mulighet for prefiks og/eller suffiks.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clone-variables"
  },
  "drop": {
    "syntax": "drop (var-list | if)",
    "description": "Fjern variabler eller observasjoner fra datasettet basert på variabelliste eller if-betingelse.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#drop"
  },
  "keep": {
    "syntax": "keep (var-list | if)",
    "description": "Behold kun spesifiserte variabler eller observasjoner som oppfyller en betingelse, slett resten. I sammensatte betingelser med & eller |: bruk parenteser rundt sammenligninger, f.eks. keep if (regstat == '1') & inrange(alder,16,66).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#keep"
  },
  "aggregate": {
    "syntax": "aggregate (stat) var-name -> new-name [...] [, by(var)]",
    "description": "Beregn aggregerte statistikker (mean, sum, count, osv.) gruppert på by()-variabel, og legg resultatene inn som nye variabler i samme datasett.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#aggregate"
  },
  "collapse": {
    "syntax": "collapse (statistic) var-name [-> new-name] [...] [, by(var)]",
    "description": "Aggreger datasettet til et høyere nivå. Etterpå består datasettet kun av aggregerte variabler og by-variabelen.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#collapse"
  },
  "merge": {
    "syntax": "merge var-list into dataset [on variable]",
    "description": "Koble variabler fra ett datasett inn i et annet på samme eller lavere enhetsnivå, gjerne via en koblingsvariabel.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#merge"
  },
  "recode": {
    "syntax": "recode var-list (rule) [(rule)...] [if] [, options]",
    "description": "Omkode verdier i én eller flere variabler etter et sett med regler. Verdier uten regler forblir uendret. Støtter intervaller, missing/nonmissing og *.",
    "options": [
      "prefix() – Lag nye variabler med prefiks",
      "generate() – Lag nye variabler med angitt navn"
    ],
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#recode"
  },
  "replace": {
    "syntax": "replace var-name = expression [if]",
    "description": "Erstatt verdier i en eksisterende variabel for enheter som oppfyller en betingelse.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#replace"
  },
  "destring": {
    "syntax": "destring var-list [, options]",
    "description": "Konverter alfanumeriske variabler til numerisk format. Støtter prefix(), ignore(), force og dpcomma.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#destring"
  },
  "assign-labels": {
    "syntax": "assign-labels var-name codelist-name",
    "description": "Koble en eksisterende kodeliste til en variabel slik at labels vises i output.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#assign-labels"
  },
  "define-labels": {
    "syntax": "define-labels codelist-name value label [value label ...]",
    "description": "Definer en ny kodeliste med verdier og labels som kan brukes på kategoriske variabler.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#define-labels"
  },
  "drop-labels": {
    "syntax": "drop-labels codelist-name [codelist-name ...]",
    "description": "Slett én eller flere kodelister som ikke lenger skal brukes.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#drop-labels"
  },
  "list-labels": {
    "syntax": "list-labels (codelist-name | register-var [time])",
    "description": "Vis innholdet i en kodeliste, enten definert i skriptet eller knyttet til en registervariabel.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#list-labels"
  },
  "sample": {
    "syntax": "sample count|fraction seed",
    "description": "Ta et tilfeldig utvalg av observasjoner (fast antall eller andel) basert på gitt seed-verdi.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#sample"
  },

  // Grafikk
  "barchart": {
    "syntax": "barchart (statistic) var-list [if] [, options]",
    "description": "Lag søylediagram som viser count/percent eller andre statistikker (mean, min, max, median, sum, sd) for variabler.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#barchart"
  },
  "boxplot": {
    "syntax": "boxplot var-list [if] [, options]",
    "description": "Lag boksplott for én eller flere variabler, eventuelt gruppert etter over()-variabler.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#boxplot"
  },
  "hexbin": {
    "syntax": "hexbin var-name var-list [if] [, options]",
    "description": "Vis todimensjonal fordeling i hexbin-diagram (tetthet i sekskanter) for to variabler.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#hexbin"
  },
  "histogram": {
    "syntax": "histogram var-name [if] [, options]",
    "description": "Lag histogram for en kontinuerlig (eller diskret) variabel. Støtter density, freq, percent, bin(), width(), normal, discrete.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#histogram"
  },
  "piechart": {
    "syntax": "piechart var-name [if]",
    "description": "Lag kakediagram for en kategorisk variabel.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#piechart"
  },
  "sankey": {
    "syntax": "sankey var-list [if]",
    "description": "Lag Sankey-diagram som viser strømninger mellom kategorier (f.eks. over tid).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#sankey"
  },

  // Statistikk
  "summarize": {
    "syntax": "summarize var-list [if] [, options]",
    "description": "Vis univariat nøkkelstatistikk (antall, mean, sd, min, max osv.) for numeriske variabler.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#summarize"
  },
  "summarize-panel": {
    "syntax": "summarize-panel var-list [if] [, options]",
    "description": "Som summarize, men fordelt etter måletidspunkter for paneldata importert med import-panel.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#summarize-panel"
  },
  "tabulate": {
    "syntax": "tabulate var-list [if] [, options]",
    "description": "Lag én- eller flerdimensjonal frekvens- eller volumtabell for kategoriske variabler, med støtte for ulike prosent- og summarize()-statistikker.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#tabulate"
  },
  "tabulate-panel": {
    "syntax": "tabulate-panel var-list [if] [, options]",
    "description": "Frekvens- eller volumtabell for panelvariabler over tid (tidsdimensjon i kolonner).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#tabulate-panel"
  },

  // Støtte
  "clear": {
    "syntax": "clear",
    "description": "Fjern all historikk og alle datasett/variabler i kommandolinjeområdet (kan ikke angres).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clear"
  },
  "help": {
    "syntax": "help [command-name]",
    "description": "Vis hjelpetekst for en kommando, eller list alle kommandoer hvis ingen navn oppgis.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#help"
  },
  "help-function": {
    "syntax": "help-function [function-name]",
    "description": "Vis hjelpetekst for en funksjon, eller list alle funksjoner hvis ingen navn oppgis.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#help-function"
  },
  "history": {
    "syntax": "history",
    "description": "List alle kommandoer i gjeldende kommandolinjeøkt uten resultater (nyttig for oversikt/kopiering).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#history"
  },
  "textblock": {
    "syntax": "textblock ... endblock",
    "description": "Skriv en lengre kommentartekst (markdown) som ikke eksekveres, men vises i output.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#textblock"
  },
  "variables": {
    "syntax": "variables [register-var-list]",
    "description": "List opp registervariabler med metadata, enten alle eller et utvalg spesifisert ved navn.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#variables"
  },
  "configure": {
    "syntax": "configure [konfigurasjon, ...]",
    "description": "Aktiver spesielle konfigurasjoner for skriptet (f.eks. alpha eller nocache).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#configure"
  }
};

window.MICRODATA_FUNCTION_HELP = {
  // Datobehandling
  "date": {
    "syntax": "date(year, month, day)",
    "description": "Datoverdi som antall dager siden 1970-01-01. Brukes til å lage datoer fra år, måned og dag."
  },
  "isoformatdate": {
    "syntax": "isoformatdate(date_value)",
    "description": "Konverterer en datoverdi (antall dager siden 1970-01-01) til streng på formatet YYYY-MM-DD."
  },
  "day": {
    "syntax": "day(date_value)",
    "description": "Gir dag i måneden (1–31) fra en datoverdi."
  },
  "month": {
    "syntax": "month(date_value)",
    "description": "Gir månedsnummer (1–12) fra en datoverdi."
  },
  "week": {
    "syntax": "week(date_value)",
    "description": "Gir ukenummer (1–53) fra en datoverdi."
  },
  "year": {
    "syntax": "year(date_value)",
    "description": "Gir årstall fra en datoverdi."
  },
  "halfyear": {
    "syntax": "halfyear(date_value)",
    "description": "Gir halvår (1 eller 2) fra en datoverdi."
  },
  "quarter": {
    "syntax": "quarter(date_value)",
    "description": "Gir kvartal (1–4) fra en datoverdi."
  },
  "dow": {
    "syntax": "dow(date_value)",
    "description": "Gir ukedag (1–7, der 1 = mandag) fra en datoverdi."
  },
  "doy": {
    "syntax": "doy(date_value)",
    "description": "Gir dag i året (1–366) fra en datoverdi."
  },

  // Sannsynlighet / fordelinger (utvalg)
  "normal": {
    "syntax": "normal(x)",
    "description": "Kumulativ standard normalfordeling ved x (P(X ≤ x))."
  },
  "normalden": {
    "syntax": "normalden(x, mu = 0, sigma = 1)",
    "description": "Tetthet (pdf) for normalfordeling med forventning mu og standardavvik sigma."
  },
  "chi2": {
    "syntax": "chi2(x, v)",
    "description": "Kumulativ kjikvadrat-fordeling med v frihetsgrader ved x."
  },
  "chi2den": {
    "syntax": "chi2den(x, v)",
    "description": "Tetthet (pdf) for kjikvadrat-fordeling med v frihetsgrader."
  },
  "chi2tail": {
    "syntax": "chi2tail(x, v)",
    "description": "Haletest (1 - CDF) for kjikvadrat-fordeling med v frihetsgrader."
  },
  "t": {
    "syntax": "t(x, v)",
    "description": "Kumulativ t-fordeling ved x med v frihetsgrader."
  },
  "tden": {
    "syntax": "tden(x, v)",
    "description": "Tetthet (pdf) for t-fordeling med v frihetsgrader."
  },
  "ttail": {
    "syntax": "ttail(x, v)",
    "description": "Haletest (1 - CDF) for t-fordeling med v frihetsgrader."
  },
  "F": {
    "syntax": "F(x, v1, v2, lambda = 0)",
    "description": "Kumulativ F-fordeling ved x med v1 og v2 frihetsgrader (ev. ikke-sentrert med lambda)."
  },
  "Fden": {
    "syntax": "Fden(x, v1, v2)",
    "description": "Tetthet (pdf) for F-fordeling med v1 og v2 frihetsgrader."
  },
  "Ftail": {
    "syntax": "Ftail(x, v1, v2, lambda = 0)",
    "description": "Haletest (1 - CDF) for F-fordeling."
  },
  "binomial": {
    "syntax": "binomial(x, n, p)",
    "description": "Sannsynlighet for ≤ n suksesser i x forsøk med suksess-sannsynlighet p (kumulativ binomial)."
  },
  "binomialp": {
    "syntax": "binomialp(x, n, p)",
    "description": "Sannsynlighet for eksakt n suksesser i x forsøk med suksess-sannsynlighet p."
  },
  "binomialtail": {
    "syntax": "binomialtail(x, n, p)",
    "description": "Sannsynlighet for ≥ n suksesser i x forsøk med suksess-sannsynlighet p."
  },

  // Matematikk
  "acos": {
    "syntax": "acos(x)",
    "description": "Arc-cosinus (i radianer) av x, der x ∈ [-1, 1]."
  },
  "asin": {
    "syntax": "asin(x)",
    "description": "Arc-sinus (i radianer) av x, der x ∈ [-1, 1]."
  },
  "atan": {
    "syntax": "atan(x)",
    "description": "Arc-tangens (i radianer) av x."
  },
  "cos": {
    "syntax": "cos(x)",
    "description": "Cosinus til x (radianer)."
  },
  "sin": {
    "syntax": "sin(x)",
    "description": "Sinus til x (radianer)."
  },
  "tan": {
    "syntax": "tan(x)",
    "description": "Tangens til x (radianer)."
  },
  "sqrt": {
    "syntax": "sqrt(x)",
    "description": "Kvadratroten av x (x ≥ 0)."
  },
  "exp": {
    "syntax": "exp(x)",
    "description": "Eksponentialfunksjonen e^x."
  },
  "ln": {
    "syntax": "ln(x)",
    "description": "Naturlig logaritme av x."
  },
  "log10": {
    "syntax": "log10(x)",
    "description": "Logaritme base 10 av x."
  },
  "logit": {
    "syntax": "logit(x)",
    "description": "Log-odds: ln(x / (1 - x)) for x i (0, 1)."
  },
  "abs": {
    "syntax": "abs(x)",
    "description": "Absoluttverdien av x."
  },
  "ceil": {
    "syntax": "ceil(x)",
    "description": "Runder x opp til nærmeste heltall."
  },
  "floor": {
    "syntax": "floor(x)",
    "description": "Runder x ned til nærmeste heltall."
  },
  "int": {
    "syntax": "int(x)",
    "description": "Dropper desimaler (heltallsdelen av x)."
  },
  "quantile": {
    "syntax": "quantile(x, n)",
    "description": "Gir kvantilgruppe (0..n-1) for verdier i x ved inndeling i n like store grupper (2–100)."
  },
  "round": {
    "syntax": "round(x, y = 1)",
    "description": "Avrunder x til nærmeste multiplum av y (standard y = 1 for nærmeste heltall)."
  },
  "pi": {
    "syntax": "pi()",
    "description": "Matematisk konstant π."
  },
  "comb": {
    "syntax": "comb(x, y)",
    "description": "Kombinasjoner: x! / (y! * (x - y)!)."
  },

  // Behandle flere variabler (rad-funksjoner)
  "rowmax": {
    "syntax": "rowmax(var1, var2, ...)",
    "description": "Maksimumsverdien over oppgitte variabler på hver rad."
  },
  "rowmin": {
    "syntax": "rowmin(var1, var2, ...)",
    "description": "Minimumsverdien over oppgitte variabler på hver rad."
  },
  "rowmean": {
    "syntax": "rowmean(var1, var2, ...)",
    "description": "Gjennomsnittet av oppgitte variabler på hver rad."
  },
  "rowmedian": {
    "syntax": "rowmedian(var1, var2, ...)",
    "description": "Medianen av oppgitte variabler på hver rad."
  },
  "rowtotal": {
    "syntax": "rowtotal(var1, var2, ...)",
    "description": "Summen av oppgitte variabler på hver rad."
  },
  "rowstd": {
    "syntax": "rowstd(var1, var2, ...)",
    "description": "Standardavviket for oppgitte variabler på hver rad."
  },
  "rowmissing": {
    "syntax": "rowmissing(var1, var2, ...)",
    "description": "Antall missing-verdier blant oppgitte variabler på hver rad."
  },
  "rowvalid": {
    "syntax": "rowvalid(var1, var2, ...)",
    "description": "Antall gyldige (ikke-missing) verdier blant oppgitte variabler på hver rad."
  },
  "rowconcat": {
    "syntax": "rowconcat(var1, var2, ...)",
    "description": "Slår sammen tekstverdier fra flere variabler til én streng per rad."
  },

  // Strengbehandling
  "length": {
    "syntax": "length(str)",
    "description": "Antall tegn i en streng eller alfanumerisk variabel."
  },
  "string": {
    "syntax": "string(x)",
    "description": "Konverterer tall eller annen verdi til streng."
  },
  "lower": {
    "syntax": "lower(str)",
    "description": "Konverterer tekst til små bokstaver (ASCII)."
  },
  "upper": {
    "syntax": "upper(str)",
    "description": "Konverterer tekst til store bokstaver (ASCII)."
  },
  "substr": {
    "syntax": "substr(str, pos, length)",
    "description": "Delstreng fra str, fra posisjon pos med angitt lengde (negativ pos fra slutten)."
  },
  "ltrim": {
    "syntax": "ltrim(str)",
    "description": "Fjerner whitespace fra starten av strengen."
  },
  "rtrim": {
    "syntax": "rtrim(str)",
    "description": "Fjerner whitespace fra slutten av strengen."
  },
  "trim": {
    "syntax": "trim(str)",
    "description": "Fjerner whitespace både i starten og slutten av strengen."
  },
  "startswith": {
    "syntax": "startswith(str, prefix)",
    "description": "Returnerer 1 (true) hvis str starter med prefix."
  },
  "endswith": {
    "syntax": "endswith(str, suffix)",
    "description": "Returnerer 1 (true) hvis str slutter med suffix."
  },

  // Logikk
  "inlist": {
    "syntax": "inlist(x, v1, v2, ...)",
    "description": "Returnerer 1 hvis x er lik én av verdiene v1, v2, ...; ellers 0."
  },
  "inrange": {
    "syntax": "inrange(x, lo, hi)",
    "description": "Returnerer 1 hvis lo ≤ x ≤ hi; ellers 0."
  },
  "sysmiss": {
    "syntax": "sysmiss(x)",
    "description": "Returnerer 1 hvis x er system-missing (ingen observasjon i datasettet)."
  },

  // Etiketter
  "label_to_code": {
    "syntax": "label_to_code(var, label)",
    "description": "Returnerer koden som har gitt etikett i variabelens kodeliste."
  },
  "inlabels": {
    "syntax": "inlabels(var, label1, label2, ...)",
    "description": "Filter: 1 hvis variabelens etikett er blant oppgitte etiketter; ellers 0."
  },
  "labelcontains": {
    "syntax": "labelcontains(var, substring)",
    "description": "Filter: 1 hvis variabelens etikett inneholder substring; ellers 0."
  },

  // Bindinger (inne i let/++/import-dato)
  "date_fmt": {
    "syntax": "date_fmt(year, month = 1, day = 1)",
    "description": "Returnerer streng på formatet YYYY-MM-DD (ofte brukt i let/++, import-dato)."
  },
  "to_int": {
    "syntax": "to_int(str)",
    "description": "Konverterer en tallformatert streng til heltall."
  },
  "to_str": {
    "syntax": "to_str(x)",
    "description": "Konverterer et tall eller symbol til streng."
  },
  "to_symbol": {
    "syntax": "to_symbol(str)",
    "description": "Konverterer en streng til symbol hvis den er et gyldig navn."
  },
  "bind": {
    "syntax": "bind(name)",
    "description": "Returnerer bindingen med gitt navn (brukes innenfor let/++ for å referere til eksisterende bindinger)."
  }
};
