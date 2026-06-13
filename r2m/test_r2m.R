# test_r2m.R — regression tests for the r2m translator
# Run with: source("test_r2m.R")

source("r2m/expr.R")
source("r2m/expanders.R")
source("r2m/commands.R")
source("r2m/translator.R")

PASS <- 0L; FAIL <- 0L

expect <- function(label, r_code, expected_lines) {
  result <- translate(r_code)
  actual <- trimws(result$script)
  exp    <- paste(trimws(expected_lines), collapse = "\n")
  if (identical(actual, exp)) {
    cat("  PASS:", label, "\n")
    PASS <<- PASS + 1L
  } else {
    cat("  FAIL:", label, "\n")
    cat("    expected:\n"); cat(paste0("      ", strsplit(exp,    "\n")[[1]]), sep = "\n"); cat("\n")
    cat("    actual:\n");   cat(paste0("      ", strsplit(actual, "\n")[[1]]), sep = "\n"); cat("\n")
    FAIL <<- FAIL + 1L
  }
}

cat("── expr.R ──────────────────────────────────────────────────\n")

expr_check <- function(label, r_expr_str, expected) {
  node   <- parse(text = r_expr_str, keep.source = FALSE)[[1]]
  actual <- translate_expr(node, "df")
  if (identical(actual, expected)) {
    cat("  PASS:", label, "\n"); PASS <<- PASS + 1L
  } else {
    cat("  FAIL:", label, "\n")
    cat("    expected:", deparse(expected), "\n")
    cat("    actual:  ", deparse(actual),   "\n")
    FAIL <<- FAIL + 1L
  }
}

expr_check("log(x)",            "log(income)",           "ln(income)")
expr_check("log10(x)",          "log10(income)",         "log10(income)")
expr_check("sqrt(x)",           "sqrt(x)",               "sqrt(x)")
expr_check("abs(x)",            "abs(x)",                "abs(x)")
expr_check("ceiling(x)",        "ceiling(x)",            "ceil(x)")
expr_check("floor(x)",          "floor(x)",              "floor(x)")
expr_check("round(x,2)",        "round(x, 2)",           "round(x, 2)")
expr_check("is.na",             "is.na(x)",              "sysmiss(x)")
expr_check("!is.na",            "!is.na(x)",             "(!sysmiss(x))")
expr_check("toupper",           "toupper(name)",         "upper(name)")
expr_check("tolower",           "tolower(name)",         "lower(name)")
expr_check("nchar",             "nchar(name)",           "length(name)")
expr_check("trimws",            "trimws(name)",          "trim(name)")
expr_check("df$col",            "df$income",             "income")
expr_check("df[[col]]",         "df[['income']]",        "income")
expr_check("arithmetic",        "age * 2 + 1",           "((age * 2) + 1)")
expr_check("comparison",        "age >= 18",             "age >= 18")
expr_check("boolean &",         "age > 18 & income > 0", "(age > 18) & (income > 0)")
expr_check("boolean |",         "a == 1 | b == 2",       "(a == 1) | (b == 2)")
expr_check("not",               "!flag",                 "!(flag)")
expr_check("%in%",              "sex %in% c(1, 2)",      "inlist(sex, 1, 2)")
expr_check("pnorm",             "pnorm(z)",              "normal(z)")
expr_check("year()",            "year(date_col)",        "year(date_col)")
expr_check("TRUE literal",      "TRUE",                  "1")
expr_check("FALSE literal",     "FALSE",                 "0")
expr_check("string literal",    "'Oslo'",                "'Oslo'")
expr_check("NA → missing",      "NA_real_",              ".")
expr_check("NA base → missing", "NA",                    ".")

# trimws with which argument
expr_check("trimws left",    "trimws(name, 'left')",   "ltrim(name)")
expr_check("trimws right",   "trimws(name, 'right')",  "rtrim(name)")
expr_check("trimws both",    "trimws(name)",            "trim(name)")

# combinatorics & math
expr_check("choose",         "choose(10, 3)",           "comb(10, 3)")
expr_check("lfactorial",     "lfactorial(x)",           "lnfactorial(x)")
expr_check("qlogis",         "qlogis(p)",               "logit(p)")

# row-wise functions
expr_check("pmax",           "pmax(a, b, c)",           "rowmax(a, b, c)")
expr_check("pmin",           "pmin(a, b)",              "rowmin(a, b)")
expr_check("paste0",         "paste0(first, last)",     "rowconcat(first, last)")
expr_check("paste sep",      "paste(first, last, sep='-')",
                             "rowconcat(first, '-', last)")

# date construction / formatting
expr_check("make_date",      "lubridate::make_date(yr, mo, dy)", "date(yr, mo, dy)")
expr_check("format iso",     "format(d, '%Y-%m-%d')",  "isoformatdate(d)")
expr_check("semester",       "lubridate::semester(d)", "halfyear(d)")

# distributions: t
expr_check("dt",             "dt(x, 5)",                "tden(x, 5)")
expr_check("pt upper",       "pt(x, 5, lower.tail=FALSE)", "ttail(x, 5)")
expr_check("qt",             "qt(p, 5)",                "invt(p, 5)")
expr_check("qt upper",       "qt(p, 5, lower.tail=FALSE)", "invttail(p, 5)")

# distributions: chi-squared
expr_check("dchisq",         "dchisq(x, 3)",            "chi2den(x, 3)")
expr_check("pchisq upper",   "pchisq(x, 3, lower.tail=FALSE)", "chi2tail(x, 3)")
expr_check("qchisq",         "qchisq(p, 3)",            "invchi2(p, 3)")
expr_check("qchisq upper",   "qchisq(p, 3, lower.tail=FALSE)", "invchi2tail(p, 3)")
expr_check("pchisq ncp",     "pchisq(x, 3, ncp=2)",    "nchi2(x, 3, 2)")

# distributions: F
expr_check("pf lower",       "pf(x, 2, 10)",            "F(x, 2, 10)")
expr_check("pf upper",       "pf(x, 2, 10, lower.tail=FALSE)", "Ftail(x, 2, 10)")
expr_check("qf",             "qf(p, 2, 10)",            "invF(p, 2, 10)")
expr_check("stats::df",      "stats::df(x, 2, 10)",     "Fden(x, 2, 10)")

# distributions: beta
expr_check("dbeta",          "dbeta(x, 2, 5)",          "betaden(x, 2, 5)")
expr_check("pbeta",          "pbeta(x, 2, 5)",          "ibeta(x, 2, 5)")
expr_check("pbeta upper",    "pbeta(x, 2, 5, lower.tail=FALSE)", "ibetatail(x, 2, 5)")
expr_check("qbeta",          "qbeta(p, 2, 5)",          "invibeta(p, 2, 5)")
expr_check("qbeta upper",    "qbeta(p, 2, 5, lower.tail=FALSE)", "invibetatail(p, 2, 5)")

# distributions: binomial
expr_check("pbinom",         "pbinom(3, 10, 0.5)",      "binomial(3, 10, 0.5)")
expr_check("dbinom",         "dbinom(3, 10, 0.5)",      "binomialp(3, 10, 0.5)")

cat("\n── translator.R — column assignment ────────────────────────\n")

expect("df$col <- expr",
  "df$income_log <- log(df$income)",
  "generate income_log = ln(income)")

expect("df$col <- ifelse",
  "df$adult <- ifelse(df$age >= 18, 1, 0)",
  c("generate adult = 0", "replace adult = 1 if age >= 18"))

expect("df$col <- case_when (first-match priority)",
  "df$grp <- case_when(df$age < 30 ~ 1, df$age < 60 ~ 2, TRUE ~ 3)",
  # dplyr case_when is first-match-wins. Sequential `replace` overwrites, so
  # non-default branches must be emitted in REVERSE order for the first listed
  # condition to win (a row with age 25 must get 1, not 2).
  c("generate grp = .", "replace grp = 2 if age < 60",
    "replace grp = 1 if age < 30", "replace grp = 3 if sysmiss(grp)"))

cat("\n── translator.R — native pipe (desugared |>) ────────────────\n")

expect("filter via native pipe",
  "df <- df |> filter(age >= 18)",
  "keep if age >= 18")

expect("mutate via native pipe",
  "df <- df |> mutate(log_inc = log(income))",
  "generate log_inc = ln(income)")

# transmute keeps only the new columns (unlike mutate, which keeps all)
expect("transmute drops other columns",
  "df <- df |> transmute(double_age = age * 2)",
  c("generate double_age = (age * 2)", "keep double_age"))

expect("filter + mutate chain",
  "df <- df |> filter(age >= 18, income > 0) |> mutate(log_inc = log(income))",
  c("keep if (age >= 18) & (income > 0)", "generate log_inc = ln(income)"))

expect("select",
  "df <- df |> select(income, age, sex)",
  "keep income age sex")

cat("\n── base-R idioms ────────────────────────────────────────────\n")

expect("base transform → generate",
  "df <- transform(df, z = age + 1)",
  "generate z = (age + 1)")

expect("base subset → keep if (with clone for new name)",
  "df2 <- subset(df, age > 18)",
  c("clone-dataset df df2", "use df2", "keep if age > 18"))

expect("base aggregate → collapse",
  "agg <- aggregate(income ~ sector, data = df, FUN = mean)",
  c("clone-dataset df agg", "use agg",
    "collapse (mean) income -> income, by(sector)"))

# base merge → join (same shape as left_join)
res_bmerge <- translate('df3 <- merge(df, df2, by = "id")')
if (grepl("clone-dataset df df3", res_bmerge$script) &&
    grepl("merge <vars_from_df2> into df3 on id", res_bmerge$script)) {
  cat("  PASS: base merge → join\n"); PASS <- PASS + 1L
} else {
  cat("  FAIL: base merge → join\n"); cat(res_bmerge$script, "\n"); FAIL <- FAIL + 1L
}

cat("\n── across / case_match / na_if / str_c ──────────────────────\n")

expect("case_match in mutate",
  'df <- df |> mutate(region = case_match(code, 1 ~ "North", 2 ~ "South", .default = "Other"))',
  c("generate region = .",
    "replace region = 'North' if code == 1",
    "replace region = 'South' if code == 2",
    "replace region = 'Other' if sysmiss(region)"))

expect("across with lambda in mutate",
  "df <- df |> mutate(across(c(a, b), ~ .x * 2))",
  c("generate a = (a * 2)", "generate b = (b * 2)"))

expect("across with bare function in summarise",
  "stats <- df |> group_by(sex) |> summarise(across(c(income, age), mean))",
  c("clone-dataset df stats", "use stats",
    "collapse (mean) income -> income (mean) age -> age, by(sex)"))

expect("na_if in mutate",
  "df <- df |> mutate(grade = na_if(grade, -1))",
  c("generate grade = grade", "replace grade = . if grade == (-1)"))

expect("str_c → rowconcat",
  "df$full <- str_c(first, last)",
  "generate full = rowconcat(first, last)")

expect("select negative",
  "df <- df |> select(-edu_raw)",
  "drop edu_raw")

expect("rename",
  "df <- df |> rename(income_nok = income)",
  "rename income income_nok")

expect("drop_na",
  "df <- df |> drop_na(income, age)",
  "drop if (sysmiss(income)) | (sysmiss(age))")

expect("clone when target != source",
  "df2 <- df |> filter(age >= 18)",
  c("clone-dataset df df2", "use df2", "keep if age >= 18"))

cat("\n── translator.R — group_by chains ──────────────────────────\n")

expect("group_by + summarise",
  "df |> group_by(sex) |> summarise(mean_inc = mean(income), n = n())",
  "collapse (mean) income -> mean_inc (count) n -> n, by(sex)")

expect("group_by + summarise assigned",
  "stats <- df |> group_by(sex) |> summarise(mean_inc = mean(income))",
  c("clone-dataset df stats", "use stats",
    "collapse (mean) income -> mean_inc, by(sex)"))

expect("group_by + mutate (aggregate)",
  "df <- df |> group_by(sex) |> mutate(mean_inc = mean(income))",
  "aggregate (mean) income -> mean_inc, by(sex)")

cat("\n── translator.R — regression ────────────────────────────────\n")

expect("lm",
  "lm(income ~ age + edu + sex, data = df)",
  "regress income age edu sex")

expect("lm with interaction",
  "lm(income ~ age + sex + age:sex, data = df)",
  c("generate _r2m_age_sex = age * sex",
    "regress income age sex _r2m_age_sex"))

expect("glm binomial",
  "glm(employed ~ age + edu, family = binomial(), data = df)",
  "logit employed age edu")

expect("glm poisson",
  "glm(n_jobs ~ age + edu, family = poisson(), data = df)",
  "poisson n_jobs age edu")

cat("\n── translator.R — standalone calls ──────────────────────────\n")

expect("table",
  "table(df$sex, df$edu_grp)",
  "tabulate sex edu_grp")

expect("hist",
  "hist(df$income)",
  "histogram income")

expect("boxplot with group",
  "boxplot(df$income ~ df$sex)",
  "boxplot income, by(sex)")

expect("summary",
  "summary(df)",
  "summarize")

cat("\n── translator.R — magrittr pipe ─────────────────────────────\n")

expect("magrittr filter",
  "df <- df %>% filter(age >= 18)",
  "keep if age >= 18")

expect("magrittr chain",
  "df <- df %>% filter(age >= 18) %>% mutate(x = log(income))",
  c("keep if age >= 18", "generate x = ln(income)"))

cat("\n── translator.R — ggplot2 ───────────────────────────────────\n")

expect("ggplot histogram",
  "ggplot(df, aes(x = income)) + geom_histogram()",
  "histogram income")

expect("ggplot histogram bins",
  "ggplot(df, aes(x = income)) + geom_histogram(bins = 20)",
  "histogram income, bin(20)")

expect("ggplot histogram facet",
  "ggplot(df, aes(x = income)) + geom_histogram() + facet_wrap(~sex)",
  "histogram income, by(sex)")

expect("ggplot geom_bar count",
  "ggplot(df, aes(x = region)) + geom_bar()",
  "barchart (count) region")

expect("ggplot geom_bar fill",
  "ggplot(df, aes(x = region, fill = sex)) + geom_bar()",
  "barchart (count) region, over(sex)")

expect("ggplot geom_bar stacked",
  "ggplot(df, aes(x = region, fill = sex)) + geom_bar(position = \"stack\")",
  "barchart (count) region, over(sex) stack")

expect("ggplot geom_col",
  "ggplot(df, aes(x = sector, y = mean_inc)) + geom_col()",
  "barchart (mean) mean_inc, over(sector)")

expect("ggplot geom_boxplot",
  "ggplot(df, aes(x = sex, y = income)) + geom_boxplot()",
  "boxplot income, over(sex)")

expect("ggplot geom_point scatter",
  "ggplot(df, aes(x = age, y = income)) + geom_point()",
  "hexbin age income")

expect("ggplot assigned to var",
  "p <- ggplot(df, aes(x = income)) + geom_histogram()",
  "histogram income")

cat("\n── translator.R — ## microdata blocks ───────────────────────\n")

expect("passthrough block",
  "## microdata\ncreate-dataset mydata\nrequire w income age\n## r\ndf <- df |> filter(age >= 18)",
  c("create-dataset mydata", "require w income age", "keep if age >= 18"))

cat("\n── translator.R — base R bracket filter ─────────────────────\n")

expect("base R filter assigned to new df",
  "df2 <- df[df$age >= 18, ]",
  c("clone-dataset df df2", "use df2", "keep if age >= 18"))

cat("\n── full examples (smoke tests) ──────────────────────────────\n")

# basic example — just check no errors and key lines present
r_basic <- '
df <- df |>
  filter(age >= 18, income > 0) |>
  mutate(log_income = log(income), high_edu = ifelse(edu >= 16, 1, 0)) |>
  select(income, log_income, age, high_edu, edu, sex)
df <- df |> drop_na(income, age)
summary(df)
hist(df$income)
'
res_basic <- translate(r_basic)
if (grepl("keep if", res_basic$script) &&
    grepl("generate log_income = ln", res_basic$script) &&
    grepl("generate high_edu = 0", res_basic$script) &&
    grepl("keep income", res_basic$script) &&
    grepl("drop if", res_basic$script) &&
    grepl("summarize", res_basic$script) &&
    grepl("histogram income", res_basic$script)) {
  cat("  PASS: basic example\n"); PASS <- PASS + 1L
} else {
  cat("  FAIL: basic example\n")
  cat(res_basic$script, "\n"); FAIL <- FAIL + 1L
}

# recode example — check case_when and ifelse
r_recode <- '
df <- df |>
  mutate(
    region_name = case_when(region == 1 ~ "North", region == 2 ~ "South", TRUE ~ "Other"),
    sex_label   = ifelse(sex == 1, "Male", "Female")
  )
table(df$region_name, df$sex_label)
'
res_recode <- translate(r_recode)
if (grepl("generate region_name = \\.", res_recode$script) &&
    grepl("replace region_name = 'North' if region == 1", res_recode$script) &&
    grepl("generate sex_label = 'Female'", res_recode$script) &&
    grepl("tabulate region_name sex_label", res_recode$script)) {
  cat("  PASS: recode/case_when example\n"); PASS <- PASS + 1L
} else {
  cat("  FAIL: recode/case_when example\n")
  cat(res_recode$script, "\n"); FAIL <- FAIL + 1L
}

# groupby collapse
r_grp <- '
stats <- df |>
  group_by(sector, sex) |>
  summarise(mean_inc = mean(income), n = n())
'
res_grp <- translate(r_grp)
if (grepl("clone-dataset df stats", res_grp$script) &&
    grepl("collapse \\(mean\\) income -> mean_inc \\(count\\) n -> n, by\\(sector sex\\)", res_grp$script)) {
  cat("  PASS: group_by + summarise example\n"); PASS <- PASS + 1L
} else {
  cat("  FAIL: group_by + summarise example\n")
  cat(res_grp$script, "\n"); FAIL <- FAIL + 1L
}

cat("\n── statistical tests ────────────────────────────────────────\n")

expect("cor two vars",
  "cor(df$income, df$age)",
  "correlate income age")

expect("cor matrix",
  "cor(df[, c('income', 'age', 'edu')])",
  "correlate income age edu")

expect("aov",
  "aov(income ~ edu + sex, data = df)",
  "anova income edu sex")

expect("t.test one sample",
  "t.test(df$income)",
  "ci income")

expect("t.test two sample",
  "t.test(df$income, df$income2)",
  "ci income income2")

expect("t.test formula",
  "t.test(income ~ sex, data = df)",
  "ci income, by(sex)")

cat("\n── advanced regression ──────────────────────────────────────\n")

expect("glm probit",
  "glm(employed ~ age + edu, family = binomial(link = 'probit'), data = df)",
  "probit employed age edu")

expect("glm.nb",
  "MASS::glm.nb(n_jobs ~ age + edu, data = df)",
  "negative-binomial n_jobs age edu")

expect("multinom",
  "nnet::multinom(edu_grp ~ age + sex, data = df)",
  "mlogit edu_grp age sex")

expect("ivreg",
  "ivreg::ivreg(income ~ edu | instrument, data = df)",
  "ivregress income edu, iv(instrument)")

cat("\n── survival analysis ────────────────────────────────────────\n")

# microdata order is `cox hendelse-var tid-var` = event first, time second
# (m2py reads args[0]=event, args[1]=duration). R's Surv(time, event) is the
# reverse, so the handler must swap.
expect("coxph",
  "survival::coxph(Surv(time, event) ~ age + sex, data = df)",
  "cox event time age sex")

expect("survfit",
  "survfit(Surv(time, event) ~ sex, data = df)",
  "kaplan-meier event time, by(sex)")

expect("survfit no group",
  "survfit(Surv(time, event) ~ 1, data = df)",
  "kaplan-meier event time")

expect("survreg weibull",
  "survival::survreg(Surv(time, event) ~ age + sex, dist = 'weibull', data = df)",
  "weibull event time age sex")

expect("survreg weibull no covariates",
  "survreg(Surv(time, event) ~ 1, dist = 'weibull', data = df)",
  "weibull event time")

cat("\n── factor labels ────────────────────────────────────────────\n")

expect("factor in-place",
  "df$sex <- factor(df$sex, levels = c(1, 2), labels = c('Male', 'Female'))",
  c("define-labels sex_lbl 1='Male' 2='Female'",
    "assign-labels sex sex_lbl"))

expect("factor new col in mutate",
  "df <- df |> mutate(sex_label = factor(sex, levels = c(1, 2), labels = c('M', 'F')))",
  c("generate sex_label = sex",
    "define-labels sex_label_lbl 1='M' 2='F'",
    "assign-labels sex_label sex_label_lbl"))

cat("\n── destring ─────────────────────────────────────────────────\n")

expect("destring col assign",
  "df$income <- as.numeric(df$income)",
  "destring income")

expect("destring in mutate",
  "df <- df |> mutate(income = as.numeric(income))",
  "destring income")

cat("\n── pie chart ────────────────────────────────────────────────\n")

expect("base pie",
  "pie(table(df$edu_group))",
  "piechart edu_group")

expect("ggplot pie",
  "ggplot(df, aes(x = '', fill = edu_group)) + geom_bar() + coord_polar('y')",
  "piechart edu_group")

cat("\n── joins ────────────────────────────────────────────────────\n")

expect("left_join in pipe",
  "df <- df |> left_join(df2, by = 'id')",
  c("use df2",
    "merge <vars_from_df2> into df on id",
    "// Replace <vars_from_df2> with the variable names to bring in from df2"))

expect("left_join assigned",
  "df3 <- df |> left_join(df2, by = 'id')",
  c("clone-dataset df df3", "use df3",
    "use df2",
    "merge <vars_from_df2> into df3 on id",
    "// Replace <vars_from_df2> with the variable names to bring in from df2"))

cat("\n── reshape ──────────────────────────────────────────────────\n")

expect("pivot_longer",
  "df <- df |> pivot_longer(cols = c(inc2020, inc2021, inc2022), names_to = 'year', values_to = 'income')",
  "reshape-to-panel inc2020 inc2021 inc2022, year(year) value(income)")

expect("pivot_wider",
  "df <- df |> pivot_wider(names_from = year, values_from = income)",
  "reshape-from-panel income, year(year)")

cat("\n── sampling & count ─────────────────────────────────────────\n")

# microdata `sample` requires a seed (sample count|fraction seed). A preceding
# set.seed() supplies it; without one a default seed is emitted with a warning.
expect("sample_n with set.seed",
  paste("set.seed(42)", "df <- df |> sample_n(1000)", sep = "\n"),
  "sample 1000 42")

expect("sample_frac emits fraction not percent",
  paste("set.seed(42)", "df <- df |> sample_frac(0.1)", sep = "\n"),
  "sample 0.1 42")

expect("slice_sample n with set.seed",
  paste("set.seed(7)", "df <- df |> slice_sample(n = 100)", sep = "\n"),
  "sample 100 7")

expect("slice_sample prop emits fraction",
  paste("set.seed(7)", "df <- df |> slice_sample(prop = 0.25)", sep = "\n"),
  "sample 0.25 7")

# no set.seed -> default seed + warning (m2py rejects a seedless sample)
res_noseed <- translate("df <- df |> sample_n(1000)")
if (grepl("sample 1000 1", res_noseed$script) &&
    any(grepl("set.seed", c(res_noseed$script, res_noseed$warnings)))) {
  cat("  PASS: sample without set.seed gets default seed + warning\n"); PASS <- PASS + 1L
} else {
  cat("  FAIL: sample without set.seed gets default seed + warning\n")
  cat("    script:", res_noseed$script, "\n")
  cat("    warnings:", paste(res_noseed$warnings, collapse=" | "), "\n"); FAIL <- FAIL + 1L
}

expect("count",
  "df |> count(sex, edu)",
  "tabulate sex edu")

cat("\n── rowMeans / rowSums ───────────────────────────────────────\n")

expr_check("rowMeans cbind",
  "rowMeans(cbind(inc2020, inc2021, inc2022))",
  "rowmean(inc2020, inc2021, inc2022)")

expr_check("rowSums cbind",
  "rowSums(cbind(inc2020, inc2021, inc2022))",
  "rowtotal(inc2020, inc2021, inc2022)")

expr_check("rowMeans bracket",
  'rowMeans(df[, c("inc2020", "inc2021")])',
  "rowmean(inc2020, inc2021)")

cat("\n── let bindings ─────────────────────────────────────────────\n")

expect("scalar numeric let",
  "YEAR <- 2020",
  "let YEAR = 2020")

expect("scalar string let",
  "label <- 'Høy inntekt'",
  "let label = 'Høy inntekt'")

cat("\n── coalesce ─────────────────────────────────────────────────\n")

expect("coalesce in-place",
  "df$income <- coalesce(df$income, 0)",
  "replace income = 0 if sysmiss(income)")

expect("coalesce new col",
  "df$y <- coalesce(df$x, 0)",
  c("generate y = x",
    "replace y = 0 if sysmiss(y)"))

expect("coalesce in mutate",
  "df <- df |> mutate(income = coalesce(income, 0))",
  "replace income = 0 if sysmiss(income)")

expect("coalesce col fallback",
  "df <- df |> mutate(wage_fill = coalesce(wage1, wage2))",
  c("generate wage_fill = wage1",
    "replace wage_fill = wage2 if sysmiss(wage_fill)"))

cat("\n── normaltest ───────────────────────────────────────────────\n")

expect("shapiro.test",
  "shapiro.test(df$income)",
  "normaltest income")

cat("\n── chisq.test ───────────────────────────────────────────────\n")

expect("chisq.test table",
  "chisq.test(table(df$sex, df$edu))",
  "tabulate sex edu, chi2")

expect("chisq.test two cols",
  "chisq.test(df$sex, df$edu)",
  "tabulate sex edu, chi2")

expect("rowMeans in mutate",
  "df <- df |> mutate(mean_wage = rowMeans(cbind(wage1, wage2, wage3)))",
  "generate mean_wage = rowmean(wage1, wage2, wage3)")

expect("rowSums in mutate",
  "df <- df |> mutate(total_wage = rowSums(cbind(wage1, wage2, wage3)))",
  "generate total_wage = rowtotal(wage1, wage2, wage3)")

cat("\n── rdd ──────────────────────────────────────────────────────\n")

expect("rdrobust basic",
  "rdrobust::rdrobust(df$vote, df$margin)",
  "rdd vote margin")

expect("rdrobust with cutoff",
  "rdrobust::rdrobust(df$vote, df$margin, c = 500000)",
  "rdd vote margin, cutoff(500000)")

cat("\n── regress-panel (plm) ──────────────────────────────────────\n")

expect("plm fixed effects",
  "plm::plm(income ~ edu + age, data = df, model = 'within')",
  "regress-panel income edu age, fe")

expect("plm random effects",
  "plm::plm(income ~ edu + age, data = df, model = 'random')",
  "regress-panel income edu age, re")

expect("plm default (no model arg)",
  "plm::plm(income ~ edu + age, data = df)",
  "regress-panel income edu age, fe")

cat("\n── regress-mml (lmer) ───────────────────────────────────────\n")

expect("lmer two-level",
  "lme4::lmer(income ~ edu + age + (1 | region), data = df)",
  "regress-mml income edu age by region")

cat("\n── oaxaca ───────────────────────────────────────────────────\n")

expect("oaxaca pipe formula",
  "oaxaca::oaxaca(income ~ edu + age | female, data = df)",
  "oaxaca income edu age by female")

expect("oaxaca by= argument",
  "oaxaca::oaxaca(income ~ edu + age, data = df, by = 'female')",
  "oaxaca income edu age by female")

cat("\n── dataset switching (use NAME) ─────────────────────────────\n")

expect("standalone call with data= different from default",
  "lm(income ~ age, data = df2)",
  c("use df2", "regress income age"))

expect("standalone call uses current_df after pipe switch",
  paste("df2 <- df |> filter(age >= 18)",
        "shapiro.test(df2$income)",
        sep = "\n"),
  c("clone-dataset df df2", "use df2", "keep if age >= 18", "normaltest income"))

expect("assigned model call with data= emits use",
  "fit <- lm(income ~ edu + age, data = df_adults)",
  c("use df_adults", "regress income edu age"))

expect("no spurious use when data= matches current active dataset",
  paste("df <- df |> filter(age >= 18)",
        "lm(income ~ age, data = df)",
        sep = "\n"),
  c("keep if age >= 18", "regress income age"))

cat("\n── namespaced calls (pkg::fun) ──────────────────────────────\n")

expect("survival::coxph emits cox",
  "fit <- survival::coxph(Surv(time, event) ~ age + sex, data = df)",
  "cox event time age sex")

expect("plm::plm emits regress-panel",
  "fit <- plm::plm(income ~ edu + age, data = df, model = 'within')",
  "regress-panel income edu age, fe")

expect("namespaced expr function (stats::sd in mutate)",
  "df$z <- dplyr::if_else(df$age > 40, 1, 0)",
  c("generate z = 0", "replace z = 1 if age > 40"))

cat("\n── graceful degradation (one bad line must not abort) ────────\n")

# A statement that errors inside a handler must degrade to a warning, not
# crash the whole translation — the good lines before/after must still emit.
res_deg <- tryCatch(
  translate(paste("df$a <- df$x + 1",
                  "fit <- lm()",          # malformed: throws inside handler
                  "df$b <- df$y * 2",
                  sep = "\n")),
  error = function(e) list(script = paste("ABORTED:", conditionMessage(e)), warnings = character(0)))
deg_ok <- grepl("generate a = (x + 1)", res_deg$script, fixed = TRUE) &&
          grepl("generate b = (y * 2)", res_deg$script, fixed = TRUE) &&
          any(grepl("SKIPPED", c(res_deg$script, res_deg$warnings)))
if (deg_ok) { cat("  PASS: one bad statement degrades to a warning\n"); PASS <- PASS + 1L
} else { cat("  FAIL: one bad statement degrades to a warning\n")
  cat("    script:\n"); cat(res_deg$script, "\n")
  cat("    warnings:", paste(res_deg$warnings, collapse=" | "), "\n"); FAIL <- FAIL + 1L }

cat("\n── loader completeness (regression guard) ───────────────────\n")
# Every r2m/*.R source must be loaded by BOTH the standalone runner and the
# main app. (A new file missing from a loader silently breaks translation —
# e.g. expanders.R was added but index.html's loader was not updated.)
r_files <- basename(list.files("r2m", pattern = "\\.R$"))
for (loader in c("r2m_runner.html", "../index.html")) {
  if (!file.exists(loader)) next
  html    <- paste(readLines(loader, warn = FALSE), collapse = "\n")
  missing <- r_files[!vapply(r_files, function(f) grepl(f, html, fixed = TRUE), logical(1))]
  if (length(missing) == 0) {
    cat("  PASS:", loader, "loads all r2m/*.R\n"); PASS <- PASS + 1L
  } else {
    cat("  FAIL:", loader, "is missing:", paste(missing, collapse = ", "), "\n")
    FAIL <- FAIL + 1L
  }
}

cat(sprintf("\n══ Results: %d passed, %d failed ══\n", PASS, FAIL))

# Non-zero exit on failure so CI (and `Rscript test_r2m.R`) fails loudly.
if (FAIL > 0) quit(status = 1)
