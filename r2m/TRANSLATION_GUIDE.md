# R → microdata.no Translation Guide

This guide explains what R code the translator can convert to microdata.no scripts, what it converts it to, and where the limits are.

---

## General rules and advice

### What translates well
The translator works best on **data manipulation pipelines** — filtering rows, creating variables, recoding values, collapsing to group-level summaries — and on **statistical models and plots** that have a direct microdata equivalent. Straightforward dplyr chains and base-R model calls are the sweet spot.

### What does not translate
- **Algorithmic R code** — loops (other than trivial `for` loops), recursive functions, `apply`/`lapply`/`sapply`, custom function definitions, and general-purpose programming logic have no microdata equivalent.
- **Data I/O** — `read_csv`, `read.csv`, `readRDS`, `write.csv`, `saveRDS` and similar functions are skipped silently. In microdata, data is imported with `import`/`require`, not loaded from files.
- **Results inspection** — `head()`, `tail()`, `str()`, `View()`, `print()`, and `nrow()` are silently dropped. They have no output command in microdata scripts.
- **Package management** — `library()`, `require()`, `install.packages()`, and `source()` are silently dropped.
- **Post-estimation** — `summary(model)`, `coef()`, `confint()`, `predict(model, newdata=)`, and `residuals()` called on a fitted model object are not translated. Fit the model instead.

### How to write R for best translation results
1. **Use a single data frame called `df`** (or tell the translator the name). Column references like `df$income` and `df[["income"]]` are reliably detected. Bare column names inside dplyr pipes (`mutate(x = ...)`) also work.
2. **Use dplyr pipes** (`|>` or `%>%`) for data manipulation. The translator understands chained verbs.
3. **Use standard function names** — both base R (`lm`, `glm`, `t.test`) and common package idioms (`lme4::lmer`, `plm::plm`, `rdrobust::rdrobust`, `MASS::glm.nb`) are recognised. Namespace prefixes (`package::function`) are stripped automatically.
4. **Keep expressions simple** — arithmetic, comparisons, and function calls inside `mutate` or `generate` translate well. Complex nested expressions may produce a `// Cannot translate` comment instead.
5. **Scalar constants become `let` bindings** — assign a number or string to a plain variable and it becomes a microdata binding (`YEAR <- 2020` → `let YEAR = 2020`).
6. **Untranslatable lines produce comments** — every line that cannot be converted emits a `//` comment in the output so you can see exactly what needs manual work.

---

## What translates — detailed reference

### Data manipulation (dplyr verbs)

| R | microdata | Notes |
|---|-----------|-------|
| `filter(cond)` | `keep if cond` | All comparison and boolean operators supported |
| `filter(!cond)` | `drop if cond` | Negated condition flips to `drop` |
| `mutate(y = expr)` | `generate y = expr` | See expression support below |
| `mutate(x = as.numeric(x))` | `destring x` | In-place type conversion only |
| `mutate(x = coalesce(x, val))` | `replace x = val if sysmiss(x)` | |
| `mutate(y = coalesce(x, val))` | `generate y = x` + `replace y = val if sysmiss(y)` | |
| `mutate(x = factor(x, levels, labels))` | `define-labels` + `assign-labels` | Requires both `levels=` and `labels=` |
| `mutate(x = ifelse(cond, t, f))` | `generate x = f` + `replace x = t if cond` | |
| `mutate(x = case_when(...))` | `generate x = .` + multiple `replace x = v if cond` | |
| `mutate(x = recode(x, old=new, ...))` | `recode x (old=new) ...` | |
| `select(a, b, c)` | `keep a b c` | |
| `select(-a, -b)` | `drop a b` | |
| `rename(new = old)` | `rename old new` | |
| `drop_na(x, y)` | `drop if sysmiss(x) | sysmiss(y)` | |
| `drop_na()` (no args) | comment only | All-column NA drop has no equivalent |
| `distinct()` | comment only | No deduplication command in microdata |
| `arrange(...)` | comment only | No sort command in microdata |
| `slice_head(n=k)` | comment only | No row-index command in microdata |

#### group_by + summarise → collapse

A `group_by() |> summarise()` chain collapses the dataset to one row per group — all aggregations are emitted as a **single** `collapse` command:

```r
df |> group_by(sex) |> summarise(mean_inc = mean(income), n = n())
# → collapse (mean) income -> mean_inc (count) n -> n, by(sex)
```

Supported aggregation statistics: `mean`, `sum`, `sd`, `median`, `min`, `max`, `n()` → `count`, `IQR` → `iqr`.

#### group_by + mutate → aggregate

A `group_by() |> mutate()` with aggregation functions adds group-level values as new columns while **keeping the full dataset** — emitted as a single `aggregate` command:

```r
df |> group_by(sector) |> mutate(sector_mean = mean(income))
# → aggregate (mean) income -> sector_mean, by(sector)
```

### Joins

Microdata's `merge` syntax is: `merge var-list into dataset [on variable]`

The **source** dataset (the one whose variables you are copying) must be **active** when `merge` runs. The **target** dataset (the one being enriched) must already exist (created with `create-dataset`, `clone`, or `clone-units`).

The translator emits `use <source>` first to make the source active, followed by the `merge` command with a placeholder for the variable list (since the variable names in the right-hand dataset are not known at translation time).

| R | microdata output | Notes |
|---|-----------------|-------|
| `left_join(df2, by="id")` | `use df2` + `merge <vars_from_df2> into df on id` | Replace placeholder with actual var names |
| `right_join(df2, by="id")` | `use df` + `merge <vars_from_df> into df2 on id` | Source/target swapped |
| `inner_join(df2, by="id")` | same as left_join + warning | microdata merge does not drop unmatched rows automatically |
| `full_join(df2, by="id")` | same as left_join + warning | rows in source not in target are not added |
| `anti_join` / `semi_join` | comment only | No direct equivalent |

The `on` option takes a **single** linking variable. If `by = c("id1", "id2")` is used, only the first key is passed to `on` and a warning is emitted.

If the key variable is the unit identifier of the target dataset, `on` can be omitted — microdata will use the identifier automatically.

### Reshape

| R | microdata | Notes |
|---|-----------|-------|
| `pivot_longer(cols=c(x1,x2), names_to="year", values_to="val")` | `reshape-to-panel x1 x2, year(year) value(val)` | |
| `pivot_wider(names_from=year, values_from=val)` | `reshape-from-panel val, year(year)` | |

### Sampling and counts

| R | microdata |
|---|-----------|
| `sample_n(1000)` | `sample 1000` |
| `sample_frac(0.1)` | `sample 10` |
| `count(x, y)` / `table(df$x, df$y)` | `tabulate x y` |

### Dataset operations

| R | microdata |
|---|-----------|
| `df2 <- df` | `clone-dataset df2` |
| `df2 <- df[cond, ]` | `clone-dataset df2` + `use df2` + `keep if cond` |
| `YEAR <- 2020` | `let YEAR = 2020` |
| `label <- "text"` | `let label = 'text'` |

---

### Expressions inside generate / replace / keep if

The following R expressions translate inside `mutate`, `filter`, `generate`, `replace`, and `keep if`:

#### Arithmetic and logic
| R | microdata |
|---|-----------|
| `+`, `-`, `*`, `/` | same |
| `x^2` | `x**2` |
| `x %% y` | `x % y` |
| `x %/% y` | `x // y` |
| `==`, `!=`, `<`, `<=`, `>`, `>=` | same |
| `&` / `&&`, `\|` / `\|\|` | `&`, `\|` |
| `!expr` | `!(expr)` |
| `x %in% c(1,2,3)` | `inlist(x, 1, 2, 3)` |
| `between(x, lo, hi)` | `inrange(x, lo, hi)` |
| `is.na(x)` | `sysmiss(x)` |
| `!is.na(x)` | `(!sysmiss(x))` |
| `TRUE` / `FALSE` | `1` / `0` |
| `NA` / `NaN` / `Inf` | `.` (sysmiss) |

#### Math functions
| R | microdata |
|---|-----------|
| `log(x)` | `ln(x)` |
| `log10(x)` | `log10(x)` |
| `log(x, base=10)` | `log10(x)` |
| `exp(x)` | `exp(x)` |
| `sqrt(x)` | `sqrt(x)` |
| `abs(x)` | `abs(x)` |
| `ceiling(x)` | `ceil(x)` |
| `floor(x)` | `floor(x)` |
| `round(x, d)` | `round(x, d)` |
| `trunc(x)` / `as.integer(x)` | `int(x)` |
| `cos`, `sin`, `tan`, `acos`, `asin`, `atan` | same |
| `pi` | `pi()` |
| `choose(n, k)` | `comb(n, k)` |
| `lfactorial(x)` | `lnfactorial(x)` |
| `qlogis(x)` | `logit(x)` (transform, not regression) |

#### String functions
| R | microdata |
|---|-----------|
| `toupper(x)` / `str_to_upper(x)` | `upper(x)` |
| `tolower(x)` / `str_to_lower(x)` | `lower(x)` |
| `nchar(x)` / `str_length(x)` | `length(x)` |
| `trimws(x)` / `str_trim(x)` | `trim(x)` |
| `trimws(x, "left")` | `ltrim(x)` |
| `trimws(x, "right")` | `rtrim(x)` |
| `substr(x, start, stop)` / `str_sub(x, start, end)` | `substr(x, start, length)` |
| `startsWith(x, p)` / `str_starts(x, p)` | `startswith(x, p)` |
| `endsWith(x, p)` / `str_ends(x, p)` | `endswith(x, p)` |
| `as.character(x)` | `string(x)` |
| `paste0(a, b, c)` | `rowconcat(a, b, c)` |
| `paste(a, b, sep=s)` | `rowconcat(a, s, b)` |

#### Date functions
| R | microdata |
|---|-----------|
| `year(x)`, `month(x)`, `day(x)` | same |
| `week(x)`, `quarter(x)` | same |
| `wday(x)` | `dow(x)` |
| `yday(x)` | `doy(x)` |
| `lubridate::semester(x)` | `halfyear(x)` |
| `make_date(y, m, d)` / `ISOdate(y, m, d)` | `date(y, m, d)` |
| `format(d, "%Y-%m-%d")` | `isoformatdate(d)` |

#### Row-wise functions (across multiple columns)
| R | microdata |
|---|-----------|
| `pmax(x, y, ...)` | `rowmax(x, y, ...)` |
| `pmin(x, y, ...)` | `rowmin(x, y, ...)` |
| `rowMeans(cbind(x, y, ...))` | `rowmean(x, y, ...)` |
| `rowSums(cbind(x, y, ...))` | `rowtotal(x, y, ...)` |
| `rowMeans(df[, c("x","y")])` | `rowmean(x, y)` |

#### Ranking / quantiles
| R | microdata |
|---|-----------|
| `ntile(x, n)` / `dplyr::ntile(x, n)` | `quantile(x, n)` |

#### Probability distributions

All functions accept `lower.tail = FALSE` (selects upper-tail variant) and `ncp=` (selects non-central variant where available).

| R | microdata (lower tail) | microdata (upper tail) |
|---|------------------------|------------------------|
| `pnorm(x)` | `normal(x)` | *(no upper-tail equivalent)* |
| `dnorm(x)` | `normalden(x)` | |
| `pt(x, df)` | `t(x, df)` | `ttail(x, df)` |
| `dt(x, df)` | `tden(x, df)` | |
| `qt(x, df)` | `invt(x, df)` | `invttail(x, df)` |
| `pchisq(x, df)` | `chi2(x, df)` | `chi2tail(x, df)` |
| `dchisq(x, df)` | `chi2den(x, df)` | |
| `qchisq(x, df)` | `invchi2(x, df)` | `invchi2tail(x, df)` |
| `pf(x, df1, df2)` | `F(x, df1, df2)` | `Ftail(x, df1, df2)` |
| `stats::df(x, df1, df2)` | `Fden(x, df1, df2)` | *(bare `df()` not mapped — collision with data frame name)* |
| `qf(x, df1, df2)` | `invF(x, df1, df2)` | `invFtail(x, df1, df2)` |
| `pbeta(x, a, b)` | `ibeta(x, a, b)` | `ibetatail(x, a, b)` |
| `dbeta(x, a, b)` | `betaden(x, a, b)` | |
| `qbeta(x, a, b)` | `invibeta(x, a, b)` | `invibetatail(x, a, b)` |
| `pbinom(x, n, p)` | `binomial(x, n, p)` | |
| `dbinom(x, n, p)` | `binomialp(x, n, p)` | |

---

### Statistical analysis commands

| R | microdata |
|---|-----------|
| `summary(df)` | `summarize` |
| `cor(df[, cols])` | `correlate col1 col2 ...` |
| `cor(df$x, df$y)` | `correlate x y` |
| `t.test(df$x)` | `ci x` |
| `t.test(df$x, df$y)` | `ci x y` |
| `t.test(y ~ group, data=df)` | `ci y, by(group)` |
| `aov(y ~ x + z, data=df)` | `anova y x z` |
| `chisq.test(table(df$x, df$y))` | `tabulate x y, chi2` |
| `shapiro.test(df$x)` | `normaltest x` |

### Regression models

| R | microdata |
|---|-----------|
| `lm(y ~ x + z, data=df)` | `regress y x z` |
| `glm(y ~ x, family=binomial(), data=df)` | `logit y x` |
| `glm(y ~ x, family=binomial(link="probit"), data=df)` | `probit y x` |
| `glm(y ~ x, family=poisson(), data=df)` | `poisson y x` |
| `MASS::glm.nb(y ~ x, data=df)` | `negative-binomial y x` |
| `nnet::multinom(y ~ x, data=df)` | `mlogit y x` |
| `ivreg::ivreg(y ~ x \| z, data=df)` | `ivregress y x, iv(z)` |
| `plm::plm(y ~ x, data=df, model="within")` | `regress-panel y x, fe` |
| `plm::plm(y ~ x, data=df, model="random")` | `regress-panel y x, re` |
| `lme4::lmer(y ~ x + (1\|group), data=df)` | `regress-mml y x by group` |
| `rdrobust::rdrobust(y, x)` | `rdd y x` |
| `rdrobust::rdrobust(y, x, c=val)` | `rdd y x, cutoff(val)` |
| `oaxaca::oaxaca(y ~ x \| group, data=df)` | `oaxaca y x by group` |

**Formula terms supported:** plain variables, `x:z` interactions (generates a temp variable), `I(expr)` (generates a temp variable), `*` expansion (generates main effects and interaction). Intercept markers (`-1`, `0`) are dropped.

**Formula terms not supported:** `poly(x, n)`, `splines::ns(x, df)`, `offset(x)` — these produce `// Cannot translate` comments.

### Survival analysis

| R | microdata |
|---|-----------|
| `survfit(Surv(time, event) ~ group, data=df)` | `kaplan-meier time event, by(group)` |
| `survfit(Surv(time, event) ~ 1, data=df)` | `kaplan-meier time event` |
| `survival::coxph(Surv(time, event) ~ x + z, data=df)` | `cox time event x z` |

### Plots

#### Base R
| R | microdata |
|---|-----------|
| `hist(df$x)` | `histogram x` |
| `boxplot(df$x)` | `boxplot x` |
| `boxplot(y ~ group, data=df)` | `boxplot y, by(group)` |
| `pie(table(df$x))` | `piechart x` |
| `table(df$x, df$y)` | `tabulate x y` |
| `summary(df)` | `summarize` |

#### ggplot2 chains (`ggplot(...) + geom_*() + ...`)
| geom | microdata | Notes |
|------|-----------|-------|
| `geom_histogram` | `histogram x` | `bins=` → `bin()`, `binwidth=` → `width()` |
| `geom_density` / `geom_freqpoly` | `histogram x` | |
| `geom_bar` | `barchart (count) x` | `fill=` → `over()`, `position="stack"` → `stack` |
| `geom_col` | `barchart (mean) y, over(x)` | Pre-summarised bar chart |
| `geom_bar + coord_polar("y")` | `piechart fill_var` | Pie chart idiom |
| `geom_boxplot` / `geom_violin` | `boxplot y, over(x)` | |
| `geom_point` / `geom_jitter` | `hexbin x y` | microdata has no scatter; hexbin is closest |
| `geom_hex` / `geom_bin2d` | `hexbin x y` | |
| `geom_line` / `geom_smooth` | comment only | No line chart in microdata |
| `facet_wrap(~var)` | `, by(var)` option | Added to any chart command |
| `coord_flip()` | `horizontal` option | Added to bar/boxplot |

---

## What does not translate (and why)

### No microdata equivalent
| R pattern | Why not translatable |
|-----------|----------------------|
| `arrange(df, x)` | No sort command in microdata |
| `distinct(df)` | No deduplication command |
| `slice_head(n=k)` / `head(df, k)` | No row-index access |
| `na.omit(df)` (all columns) | Would require listing all columns |
| `cumsum` / `cummax` / `lag` / `lead` | No window/time-series functions |
| `pnorm(x, lower.tail=FALSE)` | No upper-tail normal CDF in microdata |
| `left_join` with mismatched key names (`by = c("a" = "b")`) | microdata `merge ... on` requires the same key name in both datasets |
| `anti_join` / `semi_join` | No filtering join |
| Weighted regression (`weights=`) | No weight option on `regress` |
| `geom_line` / time series plots | No line chart command |

### Patterns that partially translate
| R pattern | What happens |
|-----------|--------------|
| `select(starts_with("x"))` | Comment — only literal column names supported |
| `mutate(across(cols, fn))` | Comment — `across()` not supported |
| `n_distinct(x)` in summarise | Comment — no equivalent statistic |
| `first()` / `last()` in summarise | Comment — no first/last aggregation |
| `var(x)` in summarise | Comment — no variance stat (use `sd` then square) |
| `full_join` / `inner_join` | Translated with a warning — microdata merge does not add unmatched rows from the source or automatically drop unmatched target rows |
| `lme4::lmer` with slope random effects `(x\|group)` | Group extracted, slope term silently dropped |
| Bare `df()` (F-distribution density) | Not mapped — `df` collides with data frame variable name; use `stats::df()` |

### Silently dropped (no output)
`library()`, `require()`, `source()`, `options()`, `setwd()`, `install.packages()`, `print()`, `cat()`, `message()`

---

## Mixed R and microdata blocks

You can freely mix R and native microdata syntax in the same script using section markers:

```
## microdata
create-dataset mydata
require no.ssb.fdb:9 as ds
import ds/INNTEKT_WLONN 2020-01-01 as income

## r
df <- df |>
  filter(income > 0) |>
  mutate(log_income = log(income))

lm(log_income ~ age + edu + sex, data = df)

## microdata
tabulate sex edu
histogram log_income
```

Lines inside a `## microdata` block are passed through unchanged. Lines inside a `## r` block (or any block before the first marker) are translated.
