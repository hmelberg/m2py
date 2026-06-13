# r2m Improvement Plan — R→microdata.no Translator

> Status (updated 2026-06-13): Phases 0–4 implemented; test suite at 171 tests
> (was crashing mid-run), CI added. Remaining: Phase 3 `md_*` helpers and the
> `predict()`→`regress-predict` model registry are deferred; the import family
> is parked (write it directly in microdata). Original analysis below.

Scope: `r2m/r2m/{expr.R, commands.R, translator.R}` (~1950 lines), `r2m/test_r2m.R` (607 lines), `r2m/r2m_runner.html` (703 lines), against the manuals. File paths below are relative to `r2m/`.

---

## 1. Coverage matrix (commands)

Legend: **Full** = emits correct command from ≥1 idiom; **Partial** = emits with placeholders/missing options; **Missing** = no path emits it.

### Analysis
| command | status | emitter | R idiom mapped / should map |
|---|---|---|---|
| `anova` | Full | `commands.R:845` handle_aov | `aov(y~x, data=)` |
| `ci` | Partial | `commands.R:856` handle_t_test | `t.test`; `level()` dropped |
| `correlate` | Full | `commands.R:826` handle_cor | `cor(...)` |
| `normaltest` | Full | `commands.R:790` handle_normaltest | `shapiro.test` |
| `transitions-panel` | Missing | absent | no natural verb; helper only |

### Bindings / loops
| `let` | Partial | `translator.R:248` scalar branch | `YEAR <- 2020`; only scalar literals, not `x <- a+b` |
| `for`/`end` | Missing | absent | `for (i in 1:5) {...}` → `for i in 1:5 … end`. High value for repeated imports |

### Datasett
| `require` | Missing | absent (`library/require` dropped at `translator.R:123`) | mandatory before import; helper `md_require()` |
| `create-dataset` | Missing | absent | helper `md_create_dataset()` |
| `delete-dataset` | Missing | absent | `rm(df)` → `delete-dataset` |
| `use` | Full (internal) | `translator.R:46` `.ensure_active` | auto on switch |
| `clone-dataset` | Full | `translator.R:242,304,399` | `df2 <- df`; `df2 <- df[...]`; pipe-to-new |
| `clone-units` | Missing | absent | helper `md_clone_units()` |
| `rename-dataset` | Missing | absent | `df2 <- df; rm(df)`, or helper |
| `reshape-to-panel` | Full | `commands.R:1166` handle_pivot_longer | `pivot_longer` |
| `reshape-from-panel` | Full | `commands.R:1187` handle_pivot_wider | `pivot_wider` |

### Tilrettelegging
| `import` | Missing | absent | **largest gap**; no R analogue; helper `md_import()` |
| `import-event` | Missing | absent | helper `md_import_event()` |
| `import-panel` | Missing | absent | helper `md_import_panel()` |
| `generate` | Full | `translator.R:226`, `commands.R:223` | `df$x <- expr`, `mutate(x=...)` |
| `rename` | Full | `commands.R:346` handle_rename | `rename(new=old)` |
| `clone-variables` | Missing | absent | `df$y <- df$x` currently → `generate y = x`; copy-with-prefix needs helper |
| `drop` (vars) | Full | `commands.R:337` | `select(-x)` |
| `drop if` | Full | `commands.R:416` handle_drop_na | `drop_na`; general via `## microdata` |
| `keep` (vars) | Full | `commands.R:339` | `select(x,y)` |
| `keep if` | Full | `commands.R:131` handle_filter | `filter`, `df[cond,]` |
| `aggregate` | Full | `commands.R:231` group path | `group_by + mutate(mean(x))` |
| `collapse` | Full | `commands.R:400` handle_summarise | `group_by + summarise` |
| `merge` | Partial | `commands.R:1082` `.handle_join_base` | `*_join` → emits placeholder + warning; var-list unknown at translate time |
| `recode` | Full | `commands.R:279` / `translator.R:486` | `dplyr::recode`; not base intervals / `case_match` |
| `replace` | Full | `translator.R:248` (ifelse/case_when) | as part of ifelse/case_when |
| `destring` | Full | `commands.R:203`, `translator.R:221` | `as.numeric(x)` |
| `assign/define-labels` | Full | `commands.R:85` `.expand_factor_labels` | `factor(x, levels=, labels=)` |
| `drop/list-labels` | Missing | absent | helper or `## microdata` |
| `sample` | Partial (buggy) | `commands.R:1209,1216` | `sample_n`/`sample_frac`; **emits no seed, converts fraction to percent** — contradicts manual `sample count\|fraction seed` |

### Grafikk
| `barchart` | Full | `commands.R:671` ggplot, `:768` base (comment) | `geom_bar/col` |
| `boxplot` | Full | `commands.R:711,756` | `geom_boxplot`, `boxplot(y~g)` |
| `coefplot` | Missing | absent | wraps regression; helper / `## microdata` |
| `hexbin` | Full (overloaded) | `commands.R:725` | `geom_point/hex`; scatter→hexbin is lossy |
| `histogram` | Full | `commands.R:654,749` | `freq/density/percent` not mapped |
| `piechart` | Full | `commands.R:771,678` | base `pie`, ggplot coord_polar |
| `sankey` | Missing | absent | no R idiom; helper only |

### Modellering & tester
| `regress` | Full | `commands.R:439` handle_lm | `lm` |
| `logit` | Full | `commands.R:450` handle_glm | `glm(family=binomial)` |
| `probit` | Full | `commands.R:475` | `glm(binomial(link="probit"))` |
| `poisson` | Full | `commands.R:460` | `glm(family=poisson)` |
| `mlogit` | Full | `commands.R:901` handle_multinom | `nnet::multinom` |
| `negative-binomial` | Full | `commands.R:889` handle_glm_nb | `MASS::glm.nb` |
| `ivregress` | Full | `commands.R:912` handle_ivreg | `ivreg::ivreg(y~x|z)` |
| `oaxaca` | Full | `commands.R:1049` handle_oaxaca | `oaxaca::oaxaca(y~x|g)` |
| `rdd` | Full | `commands.R:982` handle_rdrobust | `rdrobust::rdrobust(y,x,c=)` |
| `regress-mml` | Full | `commands.R:1015` handle_lmer | `lme4::lmer(y~x+(1|g))` |
| `regress-panel` | Full | `commands.R:1001` handle_plm | `plm::plm(model=)` |
| `regress-panel-diff` | Missing | absent | DiD; `lm(y~group*time)` / `fixest::feols`; helper or detect interaction |
| `hausman` | Missing | absent | `plm::phtest(fe, re)`; helper |
| all `-predict` | Missing | absent | `predict(fit)`/`augment()` → `regress-predict … predicted()`; helper or detect |
| `summarize` | Full | `commands.R:787` handle_summary | `summary(df)`; no var-list/options |
| `summarize-panel` | Missing | absent | — |
| `tabulate` | Full | `commands.R:742,1228,799` | `table()`, `count()`, `chisq.test()` |
| `test` | Missing | absent | `car::linearHypothesis` → `test`; helper |

### Forløp (survival)
| `cox` | Full | `commands.R:967` handle_coxph | `survival::coxph(Surv()~x)` |
| `kaplan-meier` | Full | `commands.R:954` handle_survfit | `survfit(Surv()~g)` |
| `weibull` | Missing | absent | `survival::survreg(Surv()~x, dist="weibull")` — easy add, parallels coxph |

**Summary:** ~28 Full, ~6 Partial, ~22 Missing. Biggest gap: the **import family** (`import`, `import-event`, `import-panel`, `require`, `create-dataset`) — foundational, currently unreachable.

---

## 2. Tidyverse vs base coverage

dplyr dispatch: `DPLYR_DISPATCH` (`commands.R:1240`); verb list `DPLYR_VERBS` (`translator.R:325`).

**Handled:** `filter`, `mutate`/`transmute` (transmute incorrectly aliased to mutate — doesn't drop columns, `commands.R:1242`), `select`, `rename`, `summarise`, `group_by`+summarise→collapse, `group_by`+mutate→aggregate, `count`, `drop_na`, all `*_join` (partial), `pivot_longer/wider`, `sample_n/frac`, `slice_head/max/min` (comment), `arrange`/`distinct` (comment — correct, microdata auto-sorts), `if_else` (aliased with ifelse).

**Not handled:** `slice`/`slice_tail`/`slice_sample` (in `DPLYR_VERBS` but absent from dispatch → "Untranslated"); **`across()`** (high-frequency; should expand to one generate/replace per column); **`case_match()`** (modern recode replacement; maps to `recode`); `pull`/`bind_rows`/`bind_cols`; `relocate`/`rename_with`; tidyr `separate`/`unite` (unite→rowconcat, separate→substr).

**stringr:** handled `str_trim/starts/ends/length/to_upper/to_lower/sub` (`expr.R:246-302`); not `str_detect`, `str_replace`, `str_c`(→rowconcat), `str_pad`, `str_extract`.

**lubridate:** handled `year/month/day/week/quarter`, `wday`→dow, `yday`→doy, `make_date`, `semester`→halfyear (`expr.R:305`); not `ymd/dmy/as_date` (parsing), `floor_date`, `today/now`, `hour/minute`, date arithmetic.

**base-R:** handled `df$x<-`, `df[["x"]]<-`, `df2<-df[cond,]`, `ifelse`, and all standalone stats/plots (`table/hist/boxplot/pie/barplot/summary/cor/t.test/chisq.test/aov/shapiro.test`, `STANDALONE_DISPATCH` `commands.R:1276`). **Not handled:** `subset()` (→keep if), base `merge()` (→join), `aggregate(y~g)` (→collapse), `transform()` (→generate), `tapply`/`by`/`ave`, `within()`.

**Highest-value gaps:** `across()`, `case_match()`, base `subset()`, base `merge()`, base `aggregate()`/`transform()`, `slice_sample`→`sample`.

---

## 3. Function coverage (`expr.R`)

`translate_expr` (`expr.R:68`); `MICRODATA_FUNCS` (`expr.R:27`) passes ~80 native funcs through.

**Mapped (verified):** `log`→ln/log10, exp/sqrt/abs/ceiling→ceil/floor/round/trunc→int, `as.character`→string, trig, `toupper/tolower`→upper/lower, `nchar`→length, `trimws`→trim*, `startsWith/endsWith`→startswith/endswith, `substr`→substr (stop→length), `%in%`→inlist, `between`→inrange, `is.na`→sysmiss, `pmax/pmin`→rowmax/min, `paste/paste0`→rowconcat, `rowMeans/rowSums`→rowmean/total, `ntile`→quantile, `choose`→comb, `qlogis`→logit, full distribution family, `make_date`→date, `format(%Y-%m-%d)`→isoformatdate, `semester`→halfyear, date accessors.

**Pass-through but no R source feeds them:** `rowmedian`, `rowstd`, `rowmissing`, `rowvalid`, `halfyear`, `to_int/to_str`.

**Unmapped R + microdata target to add:** `median`/`sd` rowwise→rowmedian/rowstd; `na_if`→`replace … if`; `weekdays()/months()`→dow/month; `as.Date`→date/isoformatdate; `grepl(fixed=)` anchored→startswith/labelcontains. **Label functions** `label_to_code/inlabels/labelcontains` have no R idiom → helper only.

Coverage is strong on math/stats/string/date scalars; weakest on label functions and row-wise reducers.

---

## 4. Architecture & extension cost

**Dispatch flow:** `translate()` (`translator.R:9`) → `.split_blocks` (67) separates `## microdata`/`## r` → `.translate_r_block` (97) loops statements through `.translate_stmt` (112), which branches: assignment (117), pipe (120), silenced libs (123), ggplot (128), standalone via `dispatch_standalone` (`commands.R:1311`), dplyr via `.unroll_dplyr` (147), else Untranslated. Pipes → `.run_pipe_steps` (394) → `dispatch_dplyr` (`commands.R:1270`) per verb.

**Extension points:** new expr function → clause in `translate_expr` or append to `MICRODATA_FUNCS` (`expr.R:27`); new dplyr verb → `handle_*` + register in `DPLYR_DISPATCH` (`commands.R:1240`) AND `DPLYR_VERBS` (`translator.R:325`) — *two places, easy to forget* (`slice_sample` already drifted); new standalone call → `handle_*` + `STANDALONE_DISPATCH` (`commands.R:1276`).

**Duplicated-expander problem:** `.expand_ifelse/.expand_case_when/.expand_recode` exist twice — `commands.R:239-292` and `translator.R:442-502` (translator copies win by load order). The `case_when` priority bug must be fixed in the *right* copy. **Cheap fix:** new `r2m/r2m/expanders.R` with the single canonical copy; delete duplicates; source order `expr.R → expanders.R → commands.R → translator.R` (~120 lines removed, ~1 hour).

**Per-statement error recovery (structural fix):** `.translate_r_block` (`translator.R:106`) has no guard, so one bad statement aborts everything. Wrap each iteration in `tryCatch` that appends a `// SKIPPED (translator error): ...` warning. This neutralizes the `::` crash as fatal. **Root-fix the `::` crash too:** `.translate_stmt:115` does `as.character(expr[[1]])`, which returns `c("::","pkg","fun")` for `pkg::fun(...)`, so `if (fn %in% …)` at :117 errors under R 4.2+ (breaks the runner's own `plm::`/`survival::` examples, `r2m_runner.html:518,629`). Add `.callee_name(expr)` returning the bare name, used at `translator.R:115,184,255`.

---

## 5. Ad-hoc `md_*` helper functions (R-side escape hatch)

Small R functions that run as valid R AND are recognized 1:1. Recognition: a `MD_HELPER_DISPATCH` table checked early in `.translate_stmt` (after silenced-libs, `translator.R:123`) and `.translate_df_assign` (before standalone, `translator.R:279`), passing `lhs_name` so `x <- md_import(...)` uses `x` as the `as` name. Ship matching runnable stubs in `md_helpers.R`.

| helper (R) | emits |
|---|---|
| `md_require("no.ssb.fdb:9", as="ds")` | `require no.ssb.fdb:9 as ds` |
| `md_create_dataset("mydata")` | `create-dataset mydata` |
| `x <- md_import("fd/INNTEKT_WLONN", date="2011-11-12", as="rehab2011")` | `import fd/INNTEKT_WLONN 2011-11-12 as rehab2011` |
| `md_import_event("fd/F_REHAB", from="2011-11-12", to="2012-11-12", as="r")` | `import-event fd/F_REHAB 2011-11-12 to 2012-11-12 as r` |
| `md_import_panel(c("ds/KJONN","ds/WLONN"), times=c("2001-01-01","2002-02-02"))` | `import-panel ds/KJONN ds/WLONN 2001-01-01 2002-02-02` |
| `md_sample(n=10000, seed=342343)` / `md_sample(frac=0.2, seed=422323)` | `sample 10000 342343` / `sample 0.2 422323` (**fixes seedless bug**) |
| `md_recode(var, "1/7"=0, "8/max"=99, prefix="new_")` | `recode var (1/7 = 0) (8/max = 99), prefix('new_')` |
| `md_tabulate(kjonn, siv, options="chi2")` | `tabulate kjonn siv, chi2` |
| `md_transitions(sivstand)` | `transitions-panel sivstand` |
| `md_weibull(time, event, age, sex)` | `weibull time event age sex` |
| `md_predict("regress", income, edu, predicted="pred", residuals="res")` | `regress-predict income edu, predicted(pred) residuals(res)` |
| `md_hausman()` / `md_test("edu = 0")` | `hausman` / `test edu = 0` |
| `md("clone-units set1 set2")` | `clone-units set1 set2` (raw passthrough escape hatch) |

Converts the import family + sample-with-seed + transitions + weibull + predict + hausman + test from Missing/buggy to Full at low cost.

---

## 6. Sequenced implementation plan

**Phase 0 — Stop the bleeding + green tests + CI (RECOMMENDED FIRST PR, ~1 day).**
1. Root-fix the `::` crash: `.callee_name(expr)` at `translator.R:115,184,255` (verifies runner's `plm::`/`survival::` examples).
2. Per-statement `tryCatch` in `.translate_r_block` (`translator.R:106`).
3. Fix known bugs: `case_when` first-match priority (`translator.R:459`); verify `mutate(x=NA)`; `pmax/pmin/paste0` all-unnamed empty-call guard (`expr.R:445-469`, use `names(args) %||% rep("",length(args))`).
4. Add `.github/workflows/r2m-tests.yml` running `Rscript r2m/test_r2m.R`, assert `0 failed`.
Acceptance: `test_r2m.R` prints `N passed, 0 failed`.

**Phase 1 — Consolidate duplicated code (~0.5 day).** New `r2m/r2m/expanders.R`; delete duplicate `.expand_*` from `commands.R:239-316` and `translator.R:442-502`; fix `transmute` aliasing (`commands.R:1242`); align `DPLYR_VERBS` with `DPLYR_DISPATCH`.

**Phase 2 — High-value idiom coverage (~2-3 days).** `across()`; `case_match()`→recode; base `subset()`→keep if, base `merge()`→join, base `aggregate()`/`transform()`→collapse/generate; `slice_sample`→sample (+ seed fix); `survreg(dist="weibull")`→weibull; `predict()`/`augment`→regress-predict; expr shims `na_if`, `str_c`→rowconcat, `as.Date`/`ymd`→date/isoformatdate, base `weekdays/months`.

**Phase 3 — `md_*` helpers (~2 days).** `MD_HELPER_DISPATCH` + `handle_md_*`, runnable `md_helpers.R` stubs, recognition wired into statement + assignment paths, tests per helper, Import example in `r2m_runner.html` EXAMPLES (`:379`).

**Phase 4 — UX / docs (~1 day).** Surface skipped-statement warnings in the runner output pane; document the helper escape hatch + import workflow + this coverage table in `TRANSLATION_GUIDE.md`; `## microdata` cheat-sheet for unmapped commands (`coefplot`, `drop-labels`, `sankey`).

**Implementer index:** `::` crash `translator.R:115,184,255`; no per-statement guard `translator.R:106`; duplicated expanders `commands.R:239-316` vs `translator.R:442-502`; `case_when` bug `translator.R:459`; `pmax/paste` bug `expr.R:445-469`; verb-table drift `commands.R:1240` vs `translator.R:325`; `sample` bug `commands.R:1209-1224`; helper insertion points `translator.R:123,279`; CI target `test_r2m.R` (existing `.github/workflows/` holds only Claude bots).
