// Hjelpetekster for microdata-kommandoer. Lastes av microdata_runner.html.
window.MICRODATA_COMMAND_HELP = {
  // Analyse
  "anova": {
    "syntax": "anova var-name var-list [if] [, options]",
    "description": "Analyse av varians/kovarians (ANOVA/ANCOVA) for én kontinuerlig avhengig variabel og én eller flere faktorvariabler. Første variabel er kontinuerlig, de neste er faktorer.",
    "description_en": "Analysis of variance/covariance (ANOVA/ANCOVA) for one continuous dependent variable and one or more factor variables. The first variable is continuous, the following ones are factors.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#anova"
  },
  "ci": {
    "syntax": "ci var-list [, options]",
    "description": "Vis konfidensintervaller og standardfeil for hver variabel i listen. Standard konfidensnivå er 95 %, kan endres med level().",
    "description_en": "Display confidence intervals and standard errors for each variable in the list. The default confidence level is 95%, which can be changed with level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#ci"
  },
  "correlate": {
    "syntax": "correlate var-list [if] [, options]",
    "description": "Vis korrelasjonsmatrise (eventuelt kovarians) for variabler. Støtter opsjoner som covariance, pairwise, obs og sig.",
    "description_en": "Display a correlation matrix (optionally covariance) for variables. Supports options such as covariance, pairwise, obs and sig.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#correlate"
  },
  "normaltest": {
    "syntax": "normaltest var-list [if]",
    "description": "Kjører flere normalitetstester (skewness, kurtosis, Jarque-Bera, Shapiro-Wilk) for valgte variabler eller hele datasettet.",
    "description_en": "Runs several normality tests (skewness, kurtosis, Jarque-Bera, Shapiro-Wilk) for selected variables or the entire dataset.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#normaltest"
  },
  "transitions-panel": {
    "syntax": "transitions-panel var-name var-list [if]",
    "description": "Vis toveis overgangssannsynligheter mellom kategorier over tid for panelvariabler (overgangstabeller).",
    "description_en": "Display two-way transition probabilities between categories over time for panel variables (transition tables).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#transitions-panel"
  },

  // Regresjon
  "regress": {
    "syntax": "regress var-name var-list [if] [, options]",
    "description": "Ordinær lineær regresjon (OLS). Første variabel er avhengig, resten uavhengige. Faktorsyntaks: i.var (dummyer), c.var (kontinuerlig), a#b (interaksjon), a##b (full kryssing). Opsjoner: robust, cluster(), level(), noconstant, control(), standardize, ov/vif/het_bp (diagnostikk), margins().",
    "description_en": "Ordinary linear regression (OLS). The first variable is the dependent variable, the rest are independent. Factor syntax: i.var (dummies), c.var (continuous), a#b (interaction), a##b (full crossing). Options: robust, cluster(), level(), noconstant, control(), standardize, ov/vif/het_bp (diagnostics), margins().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#regress"
  },
  "regress-predict": {
    "syntax": "regress-predict var-name var-list [if] [, options]",
    "description": "Som regress, men genererer nye variabler: predikerte verdier (predicted()), residualer (residuals()) og/eller Cooks distance (cooksd()).",
    "description_en": "Like regress, but generates new variables: predicted values (predicted()), residuals (residuals()) and/or Cook's distance (cooksd()).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#regress-predict"
  },
  "regress-panel": {
    "syntax": "regress-panel var-name var-list [if] [, options]",
    "description": "Lineær regresjon for paneldata (krever paneldatasett bygd med import-panel/import-event/reshape-to-panel). Modelltype: fe (fixed effects, standard), re (random), be (between), pooled. Opsjoner: robust, cluster(), level(), noconstant.",
    "description_en": "Linear regression for panel data (requires a panel dataset built with import-panel/import-event/reshape-to-panel). Model type: fe (fixed effects, default), re (random), be (between), pooled. Options: robust, cluster(), level(), noconstant.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#regress-panel"
  },
  "regress-panel-diff": {
    "syntax": "regress-panel-diff var-name group-var treated-var var-list [if] [, options]",
    "description": "Diff-in-diff-regresjon. group-var = 1 for behandlingsgruppe / 0 kontroll; treated-var = 1 fra og med behandlingstidspunkt / 0 før. ATET er koeffisienten til interaksjonsleddet (group#treated). Opsjoner: robust, cluster(), level().",
    "description_en": "Difference-in-differences regression. group-var = 1 for the treatment group / 0 for control; treated-var = 1 from the treatment time onwards / 0 before. ATET is the coefficient of the interaction term (group#treated). Options: robust, cluster(), level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#regress-panel-diff"
  },
  "regress-panel-predict": {
    "syntax": "regress-panel-predict var-name var-list [if] [, options]",
    "description": "Som regress-panel, men genererer predikerte verdier (predicted()), residualer (residuals()) og/eller enhetseffekter (effects()). Modelltype fe/re/be/pooled.",
    "description_en": "Like regress-panel, but generates predicted values (predicted()), residuals (residuals()) and/or unit effects (effects()). Model type fe/re/be/pooled.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#regress-panel-predict"
  },
  "regress-mml": {
    "syntax": "regress-mml response-var var-list by group-var-1 [group-var-2] [if] [, options]",
    "description": "Lineær flernivåanalyse (mixed model) med inntil tre nivåer. Gruppevariabler angis etter by-leddet (høyeste nivå først). Standardestimering REML. Opsjoner: control(), noconstant, level().",
    "description_en": "Linear multilevel analysis (mixed model) with up to three levels. Group variables are specified after the by clause (highest level first). Default estimation is REML. Options: control(), noconstant, level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#regress-mml"
  },
  "regress-mml-predict": {
    "syntax": "regress-mml-predict response-var var-list by group-var-1 [group-var-2] [if] [, options]",
    "description": "Henter predikerte verdier (predicted()) og residualer (residuals()) fra en regress-mml-modell. Modelluttrykket må være identisk med regress-mml.",
    "description_en": "Retrieves predicted values (predicted()) and residuals (residuals()) from a regress-mml model. The model expression must be identical to regress-mml.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#regress-mml-predict"
  },
  "hausman": {
    "syntax": "hausman var-name var-list [if] [, options]",
    "description": "Hausman spesifikasjonstest som sammenligner en regress-panel med fixed effects mot en med random effects. P-verdi < 0.05 ⇒ bruk FE, ellers RE. Variabler og opsjoner som i regress-panel.",
    "description_en": "Hausman specification test comparing a regress-panel with fixed effects against one with random effects. P-value < 0.05 ⇒ use FE, otherwise RE. Variables and options as in regress-panel.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#hausman"
  },
  "ivregress": {
    "syntax": "ivregress var-name var-list [( var-list = var-list )] var-list [if] [, options]",
    "description": "Lineær regresjon med instrumentvariabler. Endogen(e) variabler og instrumenter angis i parentes: (endog = instrumenter). Estimator: tsls (standard), liml, gmm. Opsjoner: firststage, endog, overid, robust, cluster(), level(), noconstant.",
    "description_en": "Linear regression with instrumental variables. Endogenous variable(s) and instruments are specified in parentheses: (endog = instruments). Estimator: tsls (default), liml, gmm. Options: firststage, endog, overid, robust, cluster(), level(), noconstant.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#ivregress"
  },
  "ivregress-predict": {
    "syntax": "ivregress-predict var-name var-list [( var-list = var-list )] var-list [if] [, options]",
    "description": "Som ivregress, men genererer predikerte verdier (predicted()) og/eller residualer (residuals()).",
    "description_en": "Like ivregress, but generates predicted values (predicted()) and/or residuals (residuals()).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#ivregress-predict"
  },
  "logit": {
    "syntax": "logit var-name var-list [if] [, options]",
    "description": "Logistisk regresjon; avhengig variabel må være binær (0/1). Opsjoner: or (oddsratio), mfx()/mfx_at() (marginaleffekter), margins(), robust, cluster(), control(), level().",
    "description_en": "Logistic regression; the dependent variable must be binary (0/1). Options: or (odds ratio), mfx()/mfx_at() (marginal effects), margins(), robust, cluster(), control(), level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#logit"
  },
  "logit-predict": {
    "syntax": "logit-predict var-name var-list [if] [, options]",
    "description": "Som logit, men genererer sannsynligheter (probabilities()), lineære prediksjoner (predicted()) og/eller residualer (residuals()).",
    "description_en": "Like logit, but generates probabilities (probabilities()), linear predictions (predicted()) and/or residuals (residuals()).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#logit-predict"
  },
  "probit": {
    "syntax": "probit var-name var-list [if] [, options]",
    "description": "Probit-regresjon; avhengig variabel må være binær. Opsjoner: mfx()/mfx_at(), margins(), robust, cluster(), control(), level().",
    "description_en": "Probit regression; the dependent variable must be binary. Options: mfx()/mfx_at(), margins(), robust, cluster(), control(), level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#probit"
  },
  "probit-predict": {
    "syntax": "probit-predict var-name var-list [if] [, options]",
    "description": "Som probit, men genererer sannsynligheter (probabilities()) og/eller predikerte verdier (predicted()).",
    "description_en": "Like probit, but generates probabilities (probabilities()) and/or predicted values (predicted()).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#probit-predict"
  },
  "mlogit": {
    "syntax": "mlogit var-name var-list [if] [, options]",
    "description": "Multinomisk logit-regresjon; avhengig variabel må ha flere enn to kategorier. Støtter faktorvariabler og interaksjoner. Opsjoner: mfx()/mfx_at(), robust, cluster(), control(), level().",
    "description_en": "Multinomial logit regression; the dependent variable must have more than two categories. Supports factor variables and interactions. Options: mfx()/mfx_at(), robust, cluster(), control(), level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#mlogit"
  },
  "mlogit-predict": {
    "syntax": "mlogit-predict var-name var-list [if] [, options]",
    "description": "Som mlogit, men genererer sannsynligheter (probabilities()) og/eller predikerte verdier (predicted()) per kategori av avhengig variabel.",
    "description_en": "Like mlogit, but generates probabilities (probabilities()) and/or predicted values (predicted()) per category of the dependent variable.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#mlogit-predict"
  },
  "poisson": {
    "syntax": "poisson var-name var-list [if] [, options]",
    "description": "Poisson telleregresjon; avhengig variabel er en tellevariabel (ikke-negative heltall). Velg poisson når forventning ≈ varians, ellers negative-binomial. Opsjoner: irr (rate-ratio), exposure(), robust, cluster(), control(), level().",
    "description_en": "Poisson count regression; the dependent variable is a count variable (non-negative integers). Choose poisson when the mean ≈ the variance, otherwise negative-binomial. Options: irr (rate ratio), exposure(), robust, cluster(), control(), level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#poisson"
  },
  "poisson-predict": {
    "syntax": "poisson-predict var-name var-list [if] [, options]",
    "description": "Som poisson, men genererer predikerte verdier (predicted()) og/eller residualer (residuals()).",
    "description_en": "Like poisson, but generates predicted values (predicted()) and/or residuals (residuals()).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#poisson-predict"
  },
  "negative-binomial": {
    "syntax": "negative-binomial var-name var-list [if] [, options]",
    "description": "Negativ binomial telleregresjon; generalisering av poisson for overdispergerte tellinger (varians > forventning). Estimerer dispersjonsparameteren alpha. Opsjoner: irr, exposure(), robust, cluster(), control(), level().",
    "description_en": "Negative binomial count regression; a generalization of poisson for overdispersed counts (variance > mean). Estimates the dispersion parameter alpha. Options: irr, exposure(), robust, cluster(), control(), level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#negative-binomial"
  },
  "negative-binomial-predict": {
    "syntax": "negative-binomial-predict var-name var-list [if] [, options]",
    "description": "Som negative-binomial, men genererer predikerte verdier (predicted()) og/eller residualer (residuals()).",
    "description_en": "Like negative-binomial, but generates predicted values (predicted()) and/or residuals (residuals()).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#negative-binomial-predict"
  },
  "oaxaca": {
    "syntax": "oaxaca var-name var-list by var-name [if] [, options]",
    "description": "Blinder-Oaxaca-dekomponering av forskjellen i gjennomsnittlig avhengig variabel mellom to grupper (angitt med by) i forklart og uforklart komponent. Opsjoner: pool (pooled two-fold), robust, noconstant.",
    "description_en": "Blinder-Oaxaca decomposition of the difference in the mean of the dependent variable between two groups (specified with by) into an explained and an unexplained component. Options: pool (pooled two-fold), robust, noconstant.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#oaxaca"
  },
  "rdd": {
    "syntax": "rdd var-name runvar var-list [if] [, options]",
    "description": "Regression Discontinuity Design (RDD): estimerer effekten av en behandling som tildeles etter en terskel i en kontinuerlig running-variabel. Første variabel er avhengig, andre er running-variabel (terskel), øvrige er kovariater. Opsjoner: cutoff() (standard 0), polynomial() (standard 1), fuzzy(treatment-dummy) for fuzzy RDD, derivate(), cluster(), level().",
    "description_en": "Regression Discontinuity Design (RDD): estimates the effect of a treatment assigned according to a threshold in a continuous running variable. The first variable is the dependent variable, the second is the running variable (threshold), the rest are covariates. Options: cutoff() (default 0), polynomial() (default 1), fuzzy(treatment-dummy) for fuzzy RDD, derivate(), cluster(), level().",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#rdd"
  },
  "coefplot": {
    "syntax": "coefplot reg-cmd var-name var-list",
    "description": "Visualiser koeffisientestimater (med konfidensintervall) fra en regresjon. Angi regresjonskommandoen først, deretter modelluttrykket, f.eks. coefplot regress depvar var1 var2. Støtter regress/logit/probit/poisson.",
    "description_en": "Visualize coefficient estimates (with confidence intervals) from a regression. Specify the regression command first, then the model expression, e.g. coefplot regress depvar var1 var2. Supports regress/logit/probit/poisson.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#coefplot"
  },

  // Overlevelsesanalyse
  "cox": {
    "syntax": "cox event-var duration-var [var-list] [if] [, options]",
    "description": "Cox proporsjonal hasard-regresjon for forløps-/overlevelsesdata. Første variabel er hendelse (0/1), andre er varighet/tid; øvrige er kovariater (i.var støttes). Opsjon hazard viser hazard ratios; level() setter konfidensnivå.",
    "description_en": "Cox proportional hazards regression for event history/survival data. The first variable is the event (0/1), the second is duration/time; the rest are covariates (i.var is supported). The hazard option displays hazard ratios; level() sets the confidence level.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#cox"
  },
  "kaplan-meier": {
    "syntax": "kaplan-meier event-var duration-var [if]",
    "description": "Kaplan-Meier-estimat av overlevelsesfunksjonen. Første variabel er hendelse (0/1), andre er varighet/tid.",
    "description_en": "Kaplan-Meier estimate of the survival function. The first variable is the event (0/1), the second is duration/time.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#kaplan-meier"
  },
  "weibull": {
    "syntax": "weibull event-var duration-var [if]",
    "description": "Weibull parametrisk overlevelsesmodell. Første variabel er hendelse (0/1), andre er varighet/tid.",
    "description_en": "Weibull parametric survival model. The first variable is the event (0/1), the second is duration/time.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#weibull"
  },

  // Bindinger
  "let": {
    "syntax": "let name = expression",
    "description": "Definer en binding (konstant) i klienten, uavhengig av datasettet. Brukes typisk til datoer, årstall eller andre gjenbrukbare verdier.",
    "description_en": "Define a binding (constant) in the client, independent of the dataset. Typically used for dates, years or other reusable values.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#let"
  },
  "for": {
    "syntax": "for i [, j] in values | n : m [, ...] [; g in ..]",
    "description": "Start en løkke over verdier eller intervaller (n:m, inklusiv). Kommandoene mellom for og end kjører for hver kombinasjon av iteratorverdier. Eksempler: `for år in 1998 : 2009`, `for forelder in mor, far`, `for år, v in 0:2, første andre tredje`. NB: bruk ikke parentes rundt verdiene og ikke ellipsis `...` — disse er ikke gyldig i microdata.no.",
    "description_en": "Start a loop over values or intervals (n:m, inclusive). The commands between for and end run for each combination of iterator values. Examples: `for year in 1998 : 2009`, `for parent in mother, father`, `for year, v in 0:2, first second third`. NB: do not use parentheses around the values and do not use ellipsis `...` — these are not valid in microdata.no.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#for"
  },
  "end": {
    "syntax": "end",
    "description": "Avslutt en for-løkke eller textblock-seksjon og kjør kroppen for resterende iterasjoner (for-løkker).",
    "description_en": "End a for loop or textblock section and run the body for the remaining iterations (for loops).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#end"
  },

  // Datasett
  "require": {
    "syntax": "require datastore as local-alias",
    "description": "Opprett kobling fra versjonert datakilde til et lokalt alias som brukes ved import (f.eks. no.ssb.fdb:9 as fdb).",
    "description_en": "Create a link from a versioned data source to a local alias used when importing (e.g. no.ssb.fdb:9 as fdb).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#require"
  },
  "create-dataset": {
    "syntax": "create-dataset new-dataset",
    "description": "Opprett et nytt tomt datasett og sett det aktivt.",
    "description_en": "Create a new empty dataset and make it active.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#create-dataset"
  },
  "delete-dataset": {
    "syntax": "delete-dataset dataset",
    "description": "Slett hele datasettet og alle variabler i det.",
    "description_en": "Delete the entire dataset and all variables in it.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#delete-dataset"
  },
  "use": {
    "syntax": "use dataset",
    "description": "Aktiver et eksisterende datasett når du har flere datasett i samme økt.",
    "description_en": "Activate an existing dataset when you have several datasets in the same session.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#use"
  },
  "clone-dataset": {
    "syntax": "clone-dataset dataset new-dataset",
    "description": "Lag en full kopi av et datasett med nytt navn.",
    "description_en": "Make a full copy of a dataset with a new name.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clone-dataset"
  },
  "clone-units": {
    "syntax": "clone-units dataset new-dataset",
    "description": "Lag nytt datasett som inneholder samme enheter (populasjon) som et eksisterende datasett, uten variabler.",
    "description_en": "Create a new dataset containing the same units (population) as an existing dataset, without variables.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clone-units"
  },
  "rename-dataset": {
    "syntax": "rename-dataset dataset new-dataset",
    "description": "Gi nytt navn til et eksisterende datasett.",
    "description_en": "Give an existing dataset a new name.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#rename-dataset"
  },
  "reshape-from-panel": {
    "syntax": "reshape-from-panel",
    "description": "Gjør om panel-/long-format til wide-format der opplysninger ligger horisontalt (én rad per enhet).",
    "description_en": "Convert panel/long format to wide format where information is stored horizontally (one row per unit).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#reshape-from-panel"
  },
  "reshape-to-panel": {
    "syntax": "reshape-to-panel variable-prefixes",
    "description": "Gjør om wide-datasett til panel-/long-format basert på prefiks for variabelnavn (tidspunkt i suffiks).",
    "description_en": "Convert a wide dataset to panel/long format based on variable name prefixes (time point in the suffix).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#reshape-to-panel"
  },

  // Tilrettelegging
  "import": {
    "syntax": "import register-var [time] [as name] [, options]",
    "description": "Importer tverrsnittsvariabel fra register (eventuelt ved et gitt tidspunkt) inn i aktivt datasett. Kan bruke outer_join for full join.",
    "description_en": "Import a cross-sectional variable from a register (optionally at a given time point) into the active dataset. Can use outer_join for a full join.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#import"
  },
  "import-event": {
    "syntax": "import-event register-var time to time [as name] [, options]",
    "description": "Importer hendelses-/forløpsvariabel for gitt tidsintervall til et paneldatasett.",
    "description_en": "Import an event/history variable for a given time interval into a panel dataset.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#import-event"
  },
  "import-panel": {
    "syntax": "import-panel register-var register-var-list time [time ...]",
    "description": "Importer variabler på flere tidspunkter i long/panel-format (flere rader per enhet).",
    "description_en": "Import variables at multiple time points in long/panel format (multiple rows per unit).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#import-panel"
  },
  "generate": {
    "syntax": "generate name = expression [if]",
    "description": "Lag ny variabel definert ved et uttrykk. Støtter aritmetikk og funksjoner, med valgfri if-betingelse. Med `if`: rader som ikke matcher får automatisk missing-verdi. Tildeling med `.` er OK (`generate x = .` gir alle missing). Sammenligning med `.` er IKKE gyldig — bruk `sysmiss(x)`.",
    "description_en": "Create a new variable defined by an expression. Supports arithmetic and functions, with an optional if condition. With `if`: rows that do not match automatically get a missing value. Assignment with `.` is OK (`generate x = .` sets all values to missing). Comparison with `.` is NOT valid — use `sysmiss(x)`.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#generate"
  },
  "rename": {
    "syntax": "rename old-name new-name",
    "description": "Gi nytt navn til en eksisterende variabel i datasettet.",
    "description_en": "Give an existing variable in the dataset a new name.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#rename"
  },
  "clone-variables": {
    "syntax": "clone-variables var-name [-> new-name] [...] [, options]",
    "description": "Lag kopier av én eller flere variabler, med mulighet for prefiks og/eller suffiks.",
    "description_en": "Make copies of one or more variables, with the option of adding a prefix and/or suffix.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clone-variables"
  },
  "drop": {
    "syntax": "drop (var-list | if)",
    "description": "Fjern variabler eller observasjoner fra datasettet basert på variabelliste eller if-betingelse.",
    "description_en": "Remove variables or observations from the dataset based on a variable list or an if condition.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#drop"
  },
  "keep": {
    "syntax": "keep (var-list | if)",
    "description": "Behold kun spesifiserte variabler eller observasjoner som oppfyller en betingelse, slett resten. I sammensatte betingelser med & eller |: bruk parenteser rundt sammenligninger, f.eks. keep if (regstat == '1') & inrange(alder,16,66).",
    "description_en": "Keep only the specified variables or the observations that satisfy a condition, deleting the rest. In compound conditions with & or |: use parentheses around comparisons, e.g. keep if (regstat == '1') & inrange(alder,16,66).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#keep"
  },
  "aggregate": {
    "syntax": "aggregate (stat) var-name -> new-name [...] [, by(var)]",
    "description": "Beregn aggregerte statistikker (mean, sum, count, osv.) gruppert på by()-variabel, og legg resultatene inn som nye variabler i samme datasett.",
    "description_en": "Compute aggregate statistics (mean, sum, count, etc.) grouped by the by() variable, and add the results as new variables in the same dataset.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#aggregate"
  },
  "collapse": {
    "syntax": "collapse (statistic) var-name [-> new-name] [...] [, by(var)]",
    "description": "Aggreger datasettet til et høyere nivå. Etterpå består datasettet kun av aggregerte variabler og by-variabelen. Støttede statistikker: count, sum, mean, sd, median, min, max, p25, p75, gini, iqr, percent. NB: kun ÉN by-variabel — for sammensatte nøkler, lag composite først med `generate k = string(a) ++ \"_\" ++ string(b)`. `first`/`last` er ikke støttet i microdata.no.",
    "description_en": "Aggregate the dataset to a higher level. Afterwards the dataset consists only of the aggregated variables and the by variable. Supported statistics: count, sum, mean, sd, median, min, max, p25, p75, gini, iqr, percent. NB: only ONE by variable — for composite keys, create a composite first with `generate k = string(a) ++ \"_\" ++ string(b)`. `first`/`last` are not supported in microdata.no.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#collapse"
  },
  "merge": {
    "syntax": "merge var-list into dataset [on variable]",
    "description": "Koble variabler fra ett datasett inn i et annet på samme eller lavere enhetsnivå, gjerne via en koblingsvariabel. NB: kun ÉN nøkkel-variabel i `on` — for sammensatte nøkler, lag composite først med `generate k = string(a) ++ \"_\" ++ string(b)`.",
    "description_en": "Merge variables from one dataset into another at the same or a lower unit level, typically via a linking variable. NB: only ONE key variable in `on` — for composite keys, create a composite first with `generate k = string(a) ++ \"_\" ++ string(b)`.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#merge"
  },
  "recode": {
    "syntax": "recode var-list (rule) [(rule)...] [if] [, options]",
    "description": "Omkode verdier i én eller flere variabler etter et sett med regler. Verdier uten regler forblir uendret. Støtter intervaller, missing/nonmissing og *.",
    "description_en": "Recode values in one or more variables according to a set of rules. Values without rules remain unchanged. Supports intervals, missing/nonmissing and *.",
    "options": [
      "prefix() – Lag nye variabler med prefiks",
      "generate() – Lag nye variabler med angitt navn"
    ],
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#recode"
  },
  "replace": {
    "syntax": "replace var-name = expression [if]",
    "description": "Erstatt verdier i en eksisterende variabel for enheter som oppfyller en betingelse. Tildeling til `.` er OK (`replace x = .`). Sammenligning med `.` (f.eks. `if y == .`) er IKKE gyldig — bruk `sysmiss(y)`.",
    "description_en": "Replace values in an existing variable for units that satisfy a condition. Assignment to `.` is OK (`replace x = .`). Comparison with `.` (e.g. `if y == .`) is NOT valid — use `sysmiss(y)`.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#replace"
  },
  "destring": {
    "syntax": "destring var-list [, options]",
    "description": "Konverter alfanumeriske variabler til numerisk format. Støtter prefix(), ignore(), force og dpcomma.",
    "description_en": "Convert alphanumeric variables to numeric format. Supports prefix(), ignore(), force and dpcomma.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#destring"
  },
  "assign-labels": {
    "syntax": "assign-labels var-name codelist-name",
    "description": "Koble en eksisterende kodeliste til en variabel slik at labels vises i output.",
    "description_en": "Attach an existing code list to a variable so that labels are shown in output.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#assign-labels"
  },
  "define-labels": {
    "syntax": "define-labels codelist-name value label [value label ...]",
    "description": "Definer en ny kodeliste med verdier og labels som kan brukes på kategoriske variabler.",
    "description_en": "Define a new code list with values and labels that can be used on categorical variables.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#define-labels"
  },
  "drop-labels": {
    "syntax": "drop-labels codelist-name [codelist-name ...]",
    "description": "Slett én eller flere kodelister som ikke lenger skal brukes.",
    "description_en": "Delete one or more code lists that are no longer needed.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#drop-labels"
  },
  "list-labels": {
    "syntax": "list-labels (codelist-name | register-var [time])",
    "description": "Vis innholdet i en kodeliste, enten definert i skriptet eller knyttet til en registervariabel.",
    "description_en": "Display the contents of a code list, either one defined in the script or one attached to a register variable.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#list-labels"
  },
  "sample": {
    "syntax": "sample count|fraction seed",
    "description": "Ta et tilfeldig utvalg av observasjoner (fast antall eller andel) basert på gitt seed-verdi.",
    "description_en": "Draw a random sample of observations (fixed count or fraction) based on a given seed value.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#sample"
  },

  // Grafikk
  "barchart": {
    "syntax": "barchart (statistic) var-list [if] [, options]",
    "description": "Lag søylediagram som viser count/percent eller andre statistikker (mean, min, max, median, sum, sd) for variabler.",
    "description_en": "Create a bar chart showing count/percent or other statistics (mean, min, max, median, sum, sd) for variables.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#barchart"
  },
  "boxplot": {
    "syntax": "boxplot var-list [if] [, options]",
    "description": "Lag boksplott for én eller flere variabler, eventuelt gruppert etter over()-variabler.",
    "description_en": "Create a box plot for one or more variables, optionally grouped by over() variables.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#boxplot"
  },
  "hexbin": {
    "syntax": "hexbin var-name var-list [if] [, options]",
    "description": "Vis todimensjonal fordeling i hexbin-diagram (tetthet i sekskanter) for to variabler.",
    "description_en": "Display a two-dimensional distribution in a hexbin plot (density in hexagons) for two variables.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#hexbin"
  },
  "histogram": {
    "syntax": "histogram var-name [if] [, options]",
    "description": "Lag histogram for en kontinuerlig (eller diskret) variabel. Støtter density, freq, percent, bin(), width(), normal, discrete.",
    "description_en": "Create a histogram for a continuous (or discrete) variable. Supports density, freq, percent, bin(), width(), normal, discrete.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#histogram"
  },
  "piechart": {
    "syntax": "piechart var-name [if]",
    "description": "Lag kakediagram for en kategorisk variabel.",
    "description_en": "Create a pie chart for a categorical variable.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#piechart"
  },
  "sankey": {
    "syntax": "sankey var-list [if]",
    "description": "Lag Sankey-diagram som viser strømninger mellom kategorier (f.eks. over tid).",
    "description_en": "Create a Sankey diagram showing flows between categories (e.g. over time).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#sankey"
  },

  // Statistikk
  "summarize": {
    "syntax": "summarize var-list [if] [, options]",
    "description": "Vis univariat nøkkelstatistikk (antall, mean, sd, min, max osv.) for numeriske variabler.",
    "description_en": "Display univariate summary statistics (count, mean, sd, min, max, etc.) for numeric variables.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#summarize"
  },
  "summarize-panel": {
    "syntax": "summarize-panel var-list [if] [, options]",
    "description": "Som summarize, men fordelt etter måletidspunkter for paneldata importert med import-panel.",
    "description_en": "Like summarize, but broken down by measurement time points for panel data imported with import-panel.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#summarize-panel"
  },
  "tabulate": {
    "syntax": "tabulate var-list [if] [, options]",
    "description": "Lag én- eller flerdimensjonal frekvens- eller volumtabell for kategoriske variabler, med støtte for ulike prosent- og summarize()-statistikker.",
    "description_en": "Create a one- or multi-dimensional frequency or volume table for categorical variables, with support for various percentage and summarize() statistics.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#tabulate"
  },
  "tabulate-panel": {
    "syntax": "tabulate-panel var-list [if] [, options]",
    "description": "Frekvens- eller volumtabell for panelvariabler over tid (tidsdimensjon i kolonner).",
    "description_en": "Frequency or volume table for panel variables over time (time dimension in the columns).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#tabulate-panel"
  },

  // Støtte
  "clear": {
    "syntax": "clear",
    "description": "Fjern all historikk og alle datasett/variabler i kommandolinjeområdet (kan ikke angres).",
    "description_en": "Remove all history and all datasets/variables in the command line area (cannot be undone).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#clear"
  },
  "help": {
    "syntax": "help [command-name]",
    "description": "Vis hjelpetekst for en kommando, eller list alle kommandoer hvis ingen navn oppgis.",
    "description_en": "Display help text for a command, or list all commands if no name is given.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#help"
  },
  "help-function": {
    "syntax": "help-function [function-name]",
    "description": "Vis hjelpetekst for en funksjon, eller list alle funksjoner hvis ingen navn oppgis.",
    "description_en": "Display help text for a function, or list all functions if no name is given.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#help-function"
  },
  "history": {
    "syntax": "history",
    "description": "List alle kommandoer i gjeldende kommandolinjeøkt uten resultater (nyttig for oversikt/kopiering).",
    "description_en": "List all commands in the current command line session without results (useful for overview/copying).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#history"
  },
  "textblock": {
    "syntax": "textblock ... endblock",
    "description": "Skriv en lengre kommentartekst (markdown) som ikke eksekveres, men vises i output.",
    "description_en": "Write a longer comment text (markdown) that is not executed but is shown in the output.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#textblock"
  },
  "variables": {
    "syntax": "variables [register-var-list]",
    "description": "List opp registervariabler med metadata, enten alle eller et utvalg spesifisert ved navn.",
    "description_en": "List register variables with metadata, either all of them or a selection specified by name.",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#variables"
  },
  "configure": {
    "syntax": "configure [konfigurasjon, ...]",
    "description": "Aktiver spesielle konfigurasjoner for skriptet (f.eks. alpha eller nocache).",
    "description_en": "Enable special configurations for the script (e.g. alpha or nocache).",
    "source": "https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#configure"
  }
};

window.MICRODATA_FUNCTION_HELP = {
  // Datobehandling
  "date": {
    "syntax": "date(year, month, day)",
    "description": "Datoverdi som antall dager siden 1970-01-01. Brukes til å lage datoer fra år, måned og dag.",
    "description_en": "Date value as the number of days since 1970-01-01. Used to create dates from year, month and day."
  },
  "isoformatdate": {
    "syntax": "isoformatdate(date_value)",
    "description": "Konverterer en datoverdi (antall dager siden 1970-01-01) til streng på formatet YYYY-MM-DD.",
    "description_en": "Converts a date value (number of days since 1970-01-01) to a string in the format YYYY-MM-DD."
  },
  "day": {
    "syntax": "day(date_value)",
    "description": "Gir dag i måneden (1–31) fra en datoverdi.",
    "description_en": "Returns the day of the month (1–31) from a date value."
  },
  "month": {
    "syntax": "month(date_value)",
    "description": "Gir månedsnummer (1–12) fra en datoverdi.",
    "description_en": "Returns the month number (1–12) from a date value."
  },
  "week": {
    "syntax": "week(date_value)",
    "description": "Gir ukenummer (1–53) fra en datoverdi.",
    "description_en": "Returns the week number (1–53) from a date value."
  },
  "year": {
    "syntax": "year(date_value)",
    "description": "Gir årstall fra en datoverdi.",
    "description_en": "Returns the year from a date value."
  },
  "halfyear": {
    "syntax": "halfyear(date_value)",
    "description": "Gir halvår (1 eller 2) fra en datoverdi.",
    "description_en": "Returns the half-year (1 or 2) from a date value."
  },
  "quarter": {
    "syntax": "quarter(date_value)",
    "description": "Gir kvartal (1–4) fra en datoverdi.",
    "description_en": "Returns the quarter (1–4) from a date value."
  },
  "dow": {
    "syntax": "dow(date_value)",
    "description": "Gir ukedag (1–7, der 1 = mandag) fra en datoverdi.",
    "description_en": "Returns the day of the week (1–7, where 1 = Monday) from a date value."
  },
  "doy": {
    "syntax": "doy(date_value)",
    "description": "Gir dag i året (1–366) fra en datoverdi.",
    "description_en": "Returns the day of the year (1–366) from a date value."
  },

  // Sannsynlighet / fordelinger (utvalg)
  "normal": {
    "syntax": "normal(x)",
    "description": "Kumulativ standard normalfordeling ved x (P(X ≤ x)).",
    "description_en": "Cumulative standard normal distribution at x (P(X ≤ x))."
  },
  "normalden": {
    "syntax": "normalden(x, mu = 0, sigma = 1)",
    "description": "Tetthet (pdf) for normalfordeling med forventning mu og standardavvik sigma.",
    "description_en": "Density (pdf) of the normal distribution with mean mu and standard deviation sigma."
  },
  "chi2": {
    "syntax": "chi2(x, v)",
    "description": "Kumulativ kjikvadrat-fordeling med v frihetsgrader ved x.",
    "description_en": "Cumulative chi-squared distribution with v degrees of freedom at x."
  },
  "chi2den": {
    "syntax": "chi2den(x, v)",
    "description": "Tetthet (pdf) for kjikvadrat-fordeling med v frihetsgrader.",
    "description_en": "Density (pdf) of the chi-squared distribution with v degrees of freedom."
  },
  "chi2tail": {
    "syntax": "chi2tail(x, v)",
    "description": "Haletest (1 - CDF) for kjikvadrat-fordeling med v frihetsgrader.",
    "description_en": "Upper-tail probability (1 - CDF) for the chi-squared distribution with v degrees of freedom."
  },
  "t": {
    "syntax": "t(x, v)",
    "description": "Kumulativ t-fordeling ved x med v frihetsgrader.",
    "description_en": "Cumulative t distribution at x with v degrees of freedom."
  },
  "tden": {
    "syntax": "tden(x, v)",
    "description": "Tetthet (pdf) for t-fordeling med v frihetsgrader.",
    "description_en": "Density (pdf) of the t distribution with v degrees of freedom."
  },
  "ttail": {
    "syntax": "ttail(x, v)",
    "description": "Haletest (1 - CDF) for t-fordeling med v frihetsgrader.",
    "description_en": "Upper-tail probability (1 - CDF) for the t distribution with v degrees of freedom."
  },
  "F": {
    "syntax": "F(x, v1, v2, lambda = 0)",
    "description": "Kumulativ F-fordeling ved x med v1 og v2 frihetsgrader (ev. ikke-sentrert med lambda).",
    "description_en": "Cumulative F distribution at x with v1 and v2 degrees of freedom (optionally non-central with lambda)."
  },
  "Fden": {
    "syntax": "Fden(x, v1, v2)",
    "description": "Tetthet (pdf) for F-fordeling med v1 og v2 frihetsgrader.",
    "description_en": "Density (pdf) of the F distribution with v1 and v2 degrees of freedom."
  },
  "Ftail": {
    "syntax": "Ftail(x, v1, v2, lambda = 0)",
    "description": "Haletest (1 - CDF) for F-fordeling.",
    "description_en": "Upper-tail probability (1 - CDF) for the F distribution."
  },
  "binomial": {
    "syntax": "binomial(x, n, p)",
    "description": "Sannsynlighet for ≤ n suksesser i x forsøk med suksess-sannsynlighet p (kumulativ binomial).",
    "description_en": "Probability of ≤ n successes in x trials with success probability p (cumulative binomial)."
  },
  "binomialp": {
    "syntax": "binomialp(x, n, p)",
    "description": "Sannsynlighet for eksakt n suksesser i x forsøk med suksess-sannsynlighet p.",
    "description_en": "Probability of exactly n successes in x trials with success probability p."
  },
  "binomialtail": {
    "syntax": "binomialtail(x, n, p)",
    "description": "Sannsynlighet for ≥ n suksesser i x forsøk med suksess-sannsynlighet p.",
    "description_en": "Probability of ≥ n successes in x trials with success probability p."
  },

  // Matematikk
  "acos": {
    "syntax": "acos(x)",
    "description": "Arc-cosinus (i radianer) av x, der x ∈ [-1, 1].",
    "description_en": "Arc cosine (in radians) of x, where x ∈ [-1, 1]."
  },
  "asin": {
    "syntax": "asin(x)",
    "description": "Arc-sinus (i radianer) av x, der x ∈ [-1, 1].",
    "description_en": "Arc sine (in radians) of x, where x ∈ [-1, 1]."
  },
  "atan": {
    "syntax": "atan(x)",
    "description": "Arc-tangens (i radianer) av x.",
    "description_en": "Arc tangent (in radians) of x."
  },
  "cos": {
    "syntax": "cos(x)",
    "description": "Cosinus til x (radianer).",
    "description_en": "Cosine of x (radians)."
  },
  "sin": {
    "syntax": "sin(x)",
    "description": "Sinus til x (radianer).",
    "description_en": "Sine of x (radians)."
  },
  "tan": {
    "syntax": "tan(x)",
    "description": "Tangens til x (radianer).",
    "description_en": "Tangent of x (radians)."
  },
  "sqrt": {
    "syntax": "sqrt(x)",
    "description": "Kvadratroten av x (x ≥ 0).",
    "description_en": "The square root of x (x ≥ 0)."
  },
  "exp": {
    "syntax": "exp(x)",
    "description": "Eksponentialfunksjonen e^x.",
    "description_en": "The exponential function e^x."
  },
  "ln": {
    "syntax": "ln(x)",
    "description": "Naturlig logaritme av x.",
    "description_en": "Natural logarithm of x."
  },
  "log10": {
    "syntax": "log10(x)",
    "description": "Logaritme base 10 av x.",
    "description_en": "Base-10 logarithm of x."
  },
  "logit": {
    "syntax": "logit(x)",
    "description": "Log-odds: ln(x / (1 - x)) for x i (0, 1).",
    "description_en": "Log-odds: ln(x / (1 - x)) for x in (0, 1)."
  },
  "abs": {
    "syntax": "abs(x)",
    "description": "Absoluttverdien av x.",
    "description_en": "The absolute value of x."
  },
  "ceil": {
    "syntax": "ceil(x)",
    "description": "Runder x opp til nærmeste heltall.",
    "description_en": "Rounds x up to the nearest integer."
  },
  "floor": {
    "syntax": "floor(x)",
    "description": "Runder x ned til nærmeste heltall.",
    "description_en": "Rounds x down to the nearest integer."
  },
  "int": {
    "syntax": "int(x)",
    "description": "Dropper desimaler (heltallsdelen av x).",
    "description_en": "Drops the decimals (the integer part of x)."
  },
  "quantile": {
    "syntax": "quantile(x, n)",
    "description": "Gir kvantilgruppe (0..n-1) for verdier i x ved inndeling i n like store grupper (2–100).",
    "description_en": "Returns the quantile group (0..n-1) for the values of x when dividing into n equally sized groups (2–100)."
  },
  "round": {
    "syntax": "round(x, y = 1)",
    "description": "Avrunder x til nærmeste multiplum av y (standard y = 1 for nærmeste heltall).",
    "description_en": "Rounds x to the nearest multiple of y (default y = 1 for the nearest integer)."
  },
  "pi": {
    "syntax": "pi()",
    "description": "Matematisk konstant π.",
    "description_en": "The mathematical constant π."
  },
  "comb": {
    "syntax": "comb(x, y)",
    "description": "Kombinasjoner: x! / (y! * (x - y)!).",
    "description_en": "Combinations: x! / (y! * (x - y)!)."
  },

  // Behandle flere variabler (rad-funksjoner)
  "rowmax": {
    "syntax": "rowmax(var1, var2, ...)",
    "description": "Maksimumsverdien over oppgitte variabler på hver rad.",
    "description_en": "The maximum value across the specified variables on each row."
  },
  "rowmin": {
    "syntax": "rowmin(var1, var2, ...)",
    "description": "Minimumsverdien over oppgitte variabler på hver rad.",
    "description_en": "The minimum value across the specified variables on each row."
  },
  "rowmean": {
    "syntax": "rowmean(var1, var2, ...)",
    "description": "Gjennomsnittet av oppgitte variabler på hver rad.",
    "description_en": "The mean of the specified variables on each row."
  },
  "rowmedian": {
    "syntax": "rowmedian(var1, var2, ...)",
    "description": "Medianen av oppgitte variabler på hver rad.",
    "description_en": "The median of the specified variables on each row."
  },
  "rowtotal": {
    "syntax": "rowtotal(var1, var2, ...)",
    "description": "Summen av oppgitte variabler på hver rad.",
    "description_en": "The sum of the specified variables on each row."
  },
  "rowstd": {
    "syntax": "rowstd(var1, var2, ...)",
    "description": "Standardavviket for oppgitte variabler på hver rad.",
    "description_en": "The standard deviation of the specified variables on each row."
  },
  "rowmissing": {
    "syntax": "rowmissing(var1, var2, ...)",
    "description": "Antall missing-verdier blant oppgitte variabler på hver rad.",
    "description_en": "The number of missing values among the specified variables on each row."
  },
  "rowvalid": {
    "syntax": "rowvalid(var1, var2, ...)",
    "description": "Antall gyldige (ikke-missing) verdier blant oppgitte variabler på hver rad.",
    "description_en": "The number of valid (non-missing) values among the specified variables on each row."
  },
  "rowconcat": {
    "syntax": "rowconcat(var1, var2, ...)",
    "description": "Slår sammen tekstverdier fra flere variabler til én streng per rad.",
    "description_en": "Concatenates text values from several variables into one string per row."
  },

  // Strengbehandling
  "length": {
    "syntax": "length(str)",
    "description": "Antall tegn i en streng eller alfanumerisk variabel.",
    "description_en": "The number of characters in a string or alphanumeric variable."
  },
  "string": {
    "syntax": "string(x)",
    "description": "Konverterer tall eller annen verdi til streng.",
    "description_en": "Converts a number or other value to a string."
  },
  "lower": {
    "syntax": "lower(str)",
    "description": "Konverterer tekst til små bokstaver (ASCII).",
    "description_en": "Converts text to lower case (ASCII)."
  },
  "upper": {
    "syntax": "upper(str)",
    "description": "Konverterer tekst til store bokstaver (ASCII).",
    "description_en": "Converts text to upper case (ASCII)."
  },
  "substr": {
    "syntax": "substr(str, pos, length)",
    "description": "Delstreng fra str, fra posisjon pos med angitt lengde (negativ pos fra slutten).",
    "description_en": "Substring of str, from position pos with the given length (negative pos counts from the end)."
  },
  "ltrim": {
    "syntax": "ltrim(str)",
    "description": "Fjerner whitespace fra starten av strengen.",
    "description_en": "Removes whitespace from the start of the string."
  },
  "rtrim": {
    "syntax": "rtrim(str)",
    "description": "Fjerner whitespace fra slutten av strengen.",
    "description_en": "Removes whitespace from the end of the string."
  },
  "trim": {
    "syntax": "trim(str)",
    "description": "Fjerner whitespace både i starten og slutten av strengen.",
    "description_en": "Removes whitespace from both the start and the end of the string."
  },
  "startswith": {
    "syntax": "startswith(str, prefix)",
    "description": "Returnerer 1 (true) hvis str starter med prefix.",
    "description_en": "Returns 1 (true) if str starts with prefix."
  },
  "endswith": {
    "syntax": "endswith(str, suffix)",
    "description": "Returnerer 1 (true) hvis str slutter med suffix.",
    "description_en": "Returns 1 (true) if str ends with suffix."
  },

  // Logikk
  "inlist": {
    "syntax": "inlist(x, v1, v2, ...)",
    "description": "Returnerer 1 hvis x er lik én av verdiene v1, v2, ...; ellers 0.",
    "description_en": "Returns 1 if x equals one of the values v1, v2, ...; otherwise 0."
  },
  "inrange": {
    "syntax": "inrange(x, lo, hi)",
    "description": "Returnerer 1 hvis lo ≤ x ≤ hi; ellers 0.",
    "description_en": "Returns 1 if lo ≤ x ≤ hi; otherwise 0."
  },
  "sysmiss": {
    "syntax": "sysmiss(x)",
    "description": "Returnerer 1 hvis x er system-missing (ingen observasjon i datasettet).",
    "description_en": "Returns 1 if x is system-missing (no observation in the dataset)."
  },

  // Etiketter
  "label_to_code": {
    "syntax": "label_to_code(var, label)",
    "description": "Returnerer koden som har gitt etikett i variabelens kodeliste.",
    "description_en": "Returns the code that has the given label in the variable's code list."
  },
  "inlabels": {
    "syntax": "inlabels(var, label1, label2, ...)",
    "description": "Filter: 1 hvis variabelens etikett er blant oppgitte etiketter; ellers 0.",
    "description_en": "Filter: 1 if the variable's label is among the specified labels; otherwise 0."
  },
  "labelcontains": {
    "syntax": "labelcontains(var, substring)",
    "description": "Filter: 1 hvis variabelens etikett inneholder substring; ellers 0.",
    "description_en": "Filter: 1 if the variable's label contains substring; otherwise 0."
  },

  // Bindinger (inne i let/++/import-dato)
  "date_fmt": {
    "syntax": "date_fmt(year, month = 1, day = 1)",
    "description": "Returnerer streng på formatet YYYY-MM-DD (ofte brukt i let/++, import-dato).",
    "description_en": "Returns a string in the format YYYY-MM-DD (often used in let/++ and import dates)."
  },
  "to_int": {
    "syntax": "to_int(str)",
    "description": "Konverterer en tallformatert streng til heltall.",
    "description_en": "Converts a numeric-formatted string to an integer."
  },
  "to_str": {
    "syntax": "to_str(x)",
    "description": "Konverterer et tall eller symbol til streng.",
    "description_en": "Converts a number or symbol to a string."
  },
  "to_symbol": {
    "syntax": "to_symbol(str)",
    "description": "Konverterer en streng til symbol hvis den er et gyldig navn.",
    "description_en": "Converts a string to a symbol if it is a valid name."
  },
  "bind": {
    "syntax": "bind(name)",
    "description": "Returnerer bindingen med gitt navn (brukes innenfor let/++ for å referere til eksisterende bindinger).",
    "description_en": "Returns the binding with the given name (used within let/++ to refer to existing bindings)."
  }
};
