# py2m Improvement Plan — Concrete, Sequenced, File-Cited

> Status (updated 2026-06-13): Phases 0–2 implemented + UX/docs polish; 65 tests
> (was zero), CI added, TRANSLATION_GUIDE.md written, runner highlights
> untranslated lines. Remaining: Phase 3 `md` helper module (import family,
> parked — write it directly in microdata) and the Phase 4 architecture refactor
> (declarative Pattern table — deferred; not a big-structural-change priority).
> Original analysis below.

py2m (`py2m/py2m/`) is an AST-pattern translator: `transformer.py` (1979 ln, dispatch + stateful handlers), `commands.py` (1344 ln, pure pattern→string extractors in a `Registry`), `expander.py` (854 ln, one-Python-construct→many-commands), `expr.py` (568 ln, expression-level AST→microdata), `formula.py` (220 ln, R-formula parsing), `chain.py` (163 ln, method-chain flattener). There is a stale `functions.py` at the package root and `tests/` contains only `__init__.py` (zero tests).

Architecture is sound (chain decomposer + registry of pure extractors). The gaps are **breadth** (whole command families have no entry point) and **silence** (matched-but-wrong and matched-but-empty results emit nothing).

---

## 1. Coverage matrix — commands

Legend: **full** = idiomatic Python reliably emits it; **partial** = emitted only via a narrow/fragile path or with known corruption; **missing** = no code path emits it.

### Data-source / dataset lifecycle
| microdata cmd | status | py2m site | natural Python idiom that *should* map |
|---|---|---|---|
| `require ds as alias` | missing | absent | `import` skipped (`transformer.py:396`). Helper `md.require(...)`. |
| `import reg-var [time] as name` | missing | absent | **largest gap** — no session starts without it. Helper `md.import_var(...)`. |
| `import-event ... to ...` | missing | absent | `md.import_event(...)`. |
| `import-panel v1 v2 t1 t2 t3` | missing | absent | `md.import_panel(...)`. |
| `create-dataset` | full | `transformer.py:434,596` | `df = pd.DataFrame()`. |
| `clone-dataset` | partial | `transformer.py:206,1575`; `_clone_and_switch` 203 | only as side-effect of filter/collapse-to-new-var. |
| `clone-units` | partial | `transformer.py:591` via `_clone_units_source` 1936 | `X = pd.DataFrame(index=SRC.index)` — obscure. |
| `delete-dataset` | partial | `transformer.py:384` | only internal temp cleanup; no `del df2`. |
| `use dataset` | full | `_ensure_active` 197 | implicit on cross-df ops. |
| `rename-dataset` | missing | absent | helper or `df2 = df1; del df1`. |
| `reshape-to-panel` | partial | `transformer.py:242,279` | `pd.wide_to_long`, `df.melt`. |
| `reshape-from-panel` | partial | `transformer.py:260` | `df.pivot`/`df.pivot_table` — collides with analytic `_pivot_table` (`commands.py:865`). |

### Variable manipulation
| microdata cmd | status | py2m site | natural idiom |
|---|---|---|---|
| `generate name = expr` | full | `transformer.py:728` | `df['x'] = expr`. |
| `replace ... [if]` | full | `transformer.py:1099`, expander np.where/map/cut/clip | `df.loc[mask,col]=v`, `np.where`, `.map`. |
| `rename old new` | partial | `transformer.py:863` | `df.rename(columns={...})` literal keys only. |
| `clone-variables a -> b` | full | `commands.py:220` | `df['b']=df['a']`. |
| `drop` / `drop if` | full | `commands.py:152`; `transformer.py:803` | `df.drop(columns=)`, `df[~mask]`. |
| `keep` / `keep if` | full | `transformer.py:796,808` | `df[['a','b']]`, `df[mask]`, `.query()`. |
| `aggregate (stat) v -> n, by()` | full | `expander.py:584` | `groupby().transform()`. |
| `collapse (stat) v -> n, by()` | full | `expander.py:707,722` | `groupby().agg()`. |
| `merge v into ds [on]` | partial | `transformer.py:1034` | `df.merge`/`pd.merge`; `left_on/right_on`/`inner` only warned (1009). |
| `recode v (rule)` | partial | `expander.py:160,244` | only same-column `.map` and `pd.cut`. No interval/`min`/`max`/`nonmissing`/`*`/label rules. |
| `destring` | full | `commands.py:230` | `pd.to_numeric`, `.astype(int)`. `ignore()`/`force` absent. |
| `assign/define-labels` | partial | `transformer.py:1119,1140` | dict literal + `.cat.rename_categories`. |
| `drop/list-labels` | missing | absent | helper only. |
| `sample count/frac seed` | full | `transformer.py:884,888` | `df.sample(n=, random_state=)`. |

### Statistics & tests
| microdata cmd | status | py2m site | natural idiom |
|---|---|---|---|
| `summarize` | partial | `commands.py:733,768` | `.describe()`, `col.mean()`. |
| `summarize-by` | partial | conflated with `tabulate, summarize(col)` at `commands.py:504` | `groupby().mean()` becomes `tabulate`, never `summarize-by`. |
| `summarize-panel` | partial | `commands.py:283` | `groupby(timecol).describe()`. |
| `tabulate` / `tabulate-panel` | full | `commands.py:325,501,846,1004` | `value_counts`, `crosstab`, `pivot_table`, `groupby().agg()`. |
| `tabulate ..., chi2` | partial | `commands.py:1343` | `chi2_contingency(crosstab(...))`. |
| `correlate` | full | `commands.py:789,795` | `.corr()`. `covariance`/`sig`/`pairwise` absent. |
| `ci [, level()]` | partial | `transformer.py:1496` | only `model.conf_int()`; no raw-variable `ci`, no `level()`. |
| `normaltest` | full | `commands.py:1035` | `stats.normaltest`. |
| `anova` | partial | `commands.py:1252` | `stats.f_oneway` only; interaction terms `a#b`/`a##b` and `smf.ols(...).anova` not mapped. |
| `test` | missing | absent | `model.f_test`/`wald_test`/`t_test`. |
| `transitions-panel v base` | missing | absent | `pd.crosstab(df['v_t0'], df['v_t1'])`, or helper. |

### Regression family
| microdata cmd | status | py2m site | idiom |
|---|---|---|---|
| `regress` | partial | `transformer.py:1232` via `_SMF_CMD` 41 | `smf.ols(...).fit()`. **`a*b` unconditionally hijacked to `regress-panel-diff`** (1188). |
| `logit`/`probit`/`poisson`/`negative-binomial`/`mlogit` | partial | `_SMF_CMD` 41, emitted 1232 | `smf.logit/...`. Reachable, untested. |
| `regress-mml` | partial | `_SMF_CMD["mixedlm"]` 48 | `smf.mixedlm`. `by group2` unsupported. |
| `regress-panel [fe/re/be]` | partial | `_PANEL_CLASSES` 52 | linearmodels `PanelOLS`/`RandomEffects`/`BetweenOLS`. |
| `regress-panel-diff` | partial | `transformer.py:1200` | fires on *any* `a*b`, corrupting plain interactions. |
| `ivregress 2sls/liml/gmm` | partial | `transformer.py:1320` | linearmodels `IV2SLS.from_formula(...)`. |
| `hausman` | missing | absent | linearmodels Hausman, or `md.hausman(fe, re)`. |
| `oaxaca v vars by g` | missing | absent | helper-only `md.oaxaca(...)`. |
| `rdd dep run vars` | missing | absent | `rdrobust`, or `md.rdd(...)`. |
| `coefplot` | partial | `transformer.py:1500` | `model.params.plot()`. Cannot specify type/vars. |
| `*-predict` (all) | partial | `transformer.py:1336,1357` | `df['p']=model.predict()`, `model.resid`. |

### Charts
| microdata cmd | status | py2m site | idiom |
|---|---|---|---|
| `histogram` | full | `commands.py:756,1122`; `transformer.py:1628` | `.hist()`, `.plot.hist`, `px.histogram`. |
| `barchart` | partial | `commands.py:1117`; `transformer.py:1641` | `.plot.bar`, `px.bar`. `(count)/(percent)`, `stack`, `horizontal` not derived. |
| `boxplot` | full | `commands.py:1127,1156`; `transformer.py:1635` | `.boxplot`, `px.box`. |
| `piechart` | full | `commands.py:1130`; `transformer.py:1645` | `.plot.pie`, `px.pie`. |
| `hexbin` | partial | `commands.py:1134`; `transformer.py:1650` | `.plot.scatter`→hexbin (approx), `px.density_heatmap`. |
| `sankey` | partial | `transformer.py:1659` | maps to `px.sankey` (wrong API; real is `go.Sankey`). |

**Summary:** of ~70 commands, ~18 full, ~30 partial, ~12 missing (`require`, `import`, `import-event`, `import-panel`, `rename-dataset`, `drop-labels`, `list-labels`, `test`, `transitions-panel`, `hausman`, `oaxaca`, `rdd`). The import/datastore family being absent is the largest single gap.

---

## 2. Coverage matrix — functions (`expr.py`)

Reachable today via `_MICRODATA_FUNCS` (expr.py:40), `_NP_FUNC` (18), `_MATH_FUNC` (29), `_STR_METHODS` (111), `_DT_FUNC` (167), `_SCIPY_DIST_MAP` (73), plus `_t_Call` (266) and the str-chain walker (454).

**Reachable:** all math; dates `year/month/day/week/quarter/dow/doy`; strings `length/lower/upper/trim*/startswith/endswith/substr/string`; row aggs `rowmax/min/mean/median/total/std/missing/valid`; predicates `inlist` (`.isin`), `inrange` (`.between`), `sysmiss` (`isna`); distributions via scipy.

**Unmapped microdata functions + natural Python source to wire up:**
| microdata fn | Python equivalent |
|---|---|
| `halfyear(d)` | `(month-1)//6+1` or `md.halfyear`. |
| `isoformatdate(d)` | `s.dt.strftime('%Y-%m-%d')`. |
| `date(y,m,d)` | `pd.Timestamp(y,m,d)` (name mapped, no constructor source). |
| `rowconcat(...)` | `df[cols].astype(str).agg(''.join, axis=1)` / `.str.cat` (listed but unreachable). |
| `quantile(x,n)` | `pd.qcut(s, n, labels=False)`. |
| `distance(...)` | helper-only. |
| `label_to_code/inlabels/labelcontains` | helper-only (no pandas analog). |
| `normalden(x,μ,σ)` | `stats.norm.pdf(x, loc, scale)` — loc/scale currently dropped (expr.py:72). |

Also unmapped numpy/pandas: `np.sign`, `np.log2` (None at expr.py:19), `s.str.contains/match/extract`, `s.str.pad/zfill/cat`, `s.where`/`s.mask`.

---

## 3. Top idiom gaps (15 most common)

| # | idiom | status (cite) | fix sketch |
|---|---|---|---|
| 1 | `df.assign(x=..., y=...)` | not handled — `_VIEW_METHODS` warning (transformer.py:895) | each kwarg → `generate`. **High value, low effort.** |
| 2 | `df.query("a>1 & b==2")` | handled (transformer.py:775; multi-df 341) | add `@var` and `in`. |
| 3 | `df.loc[mask,'col']=val` | handled (transformer.py:1074) | add RHS-is-column and tuple targets. |
| 4 | `df.groupby(g).agg(out=('y','mean'))` | output name dropped for display (commands.py:582); named-stat no-display → silent NOTE (682) | make NOTE a warning. |
| 5 | `value_counts(normalize=True)` | handled (commands.py:971) | default `sort=True` lost (979) — treat absent as True. |
| 6 | `pd.crosstab(a,b,normalize='index')` | handled (commands.py:821) | OK. |
| 7 | `pd.pivot_table(...)` | handled (commands.py:865) **but collides** with reshape `df.pivot_table` (transformer.py:255) | disambiguate analytic vs reshape. |
| 8 | `df.sort_values('x')` | dropped → fake `// UNTRANSLATED` (commands.py:160) | clean comment; `rowsort()` when post-processing tabulate. |
| 9 | `df.drop_duplicates()` | not handled | explicit NOTE: no microdata equiv. |
| 10 | `df.rename(columns={...})` | literals only (transformer.py:863) | variable-name keys → warn. |
| 11 | `.astype('category')`/`.astype(str)` | partial (commands.py:238) | str→`string()`; category→labels/warn. |
| 12 | `df.fillna(0)` (df-wide) | placeholder `[each col]` comment (commands.py:199) | expand per-column or warn loudly. |
| 13 | datetime ops `.dt.year`, `(d2-d1).dt.days` | partial (expr.py:167) | date subtraction → invalid output; add day-diff guidance. |
| 14 | chains beyond chain.py (`assign().query()`, `groupby().agg().sort().head()`) | partial — `_peel_post_proc` (commands.py:383) handles trailing only | extend extractors to consume `assign`/`pipe`. |
| 15 | `df['x']=df['a'].where(cond, other)` | unmapped | `.where/.mask` → np.where-style expansion. |

Cross-cutting silent/crashing bugs (confirmed in code): `range(n)` crash (`_extract_for_values` 1972); if/else unconditional + else dropped (`_handle_if` 1699); `print` discarded (1422); `.str[2:]` silent (expr.py:565); `var→sd/first→min/last→max` silent (expander.py:836-840); self-clone on in-place secondary filter; `pd.cut` inf mismatch (expander.py:254).

---

## 4. Architecture & extension cost

**Adding a command today** uses three mechanisms:
1. **Pure pattern→string:** `@REGISTRY.df/.col/.expr` in `commands.py` (registry 85, decorators 48-61, dispatch 63-82). Clean path.
2. **Multi-line expansion:** a `try_*` in `expander.py`, called in a hand-ordered waterfall in `_handle_col_assign` (transformer.py:639-736).
3. **Stateful/cross-statement:** a branch in the giant `if/elif` ladder in `_handle_assign` (421-614) / `_handle_expr_stmt` (1410-1539) + a `_is_*` predicate (1709-1957) + a lookup dict (`_SMF_CMD` 41, `_PANEL_CLASSES` 52, `_PX_COMMANDS` 67).

Registry additions are cheap; stateful additions mean editing the 200-line ladder — where collisions (DiD hijack, pivot_table double-match) and ordering bugs live.

**Small refactor — declarative pattern→template table.** Most extractors are "recognize chain shape X with kwargs Y → fill template Z." A lightweight `Pattern(root, chain, emit, options)` spec driving the `_handle_col_assign` waterfall and the px/plot maps converts the ordering ladder into data, kills the collision class, and makes "add a command" = "add a row." Keep model/dataset handlers imperative (they need state).

**Make failures loud.** The registry's `[]` (match-and-emit-nothing) is indistinguishable from a real no-op, and several extractors return `[]`/placeholder for cases they can't translate (commands.py:199 `[each col]`; 160 fake sort; expander.py silent aliasing). Fixes: a `warnings` channel on `Ctx` (commands.py:26) threaded into `TranslationResult.warnings`; every approximation (`var→sd`, inner→left, violin→boxplot, scatter→hexbin) emits a `// WARNING:` + warning; replace command-looking placeholders with explicit `// UNTRANSLATED`; add `--strict` to cli.py (nonzero exit on any warning).

---

## 5. Ad-hoc `md` helper module (Python side)

A real importable `md.py` whose functions **run as plain pandas** AND are recognized 1:1 by the translator. Recognition: generalize the existing bare-name special-cases (`use_dataset` transformer.py:1426, `to_microdata` 1554) into a `_MD_HELPERS` table + a single `_try_md_helper(value)` checked early in `_handle_assign` and `_handle_expr_stmt`. The translator pattern-matches the call; it never executes it.

| signature | emits |
|---|---|
| `md.require("no.ssb.fdb:9", as_="ds")` | `require no.ssb.fdb:9 as ds` |
| `df = md.import_var("fd/INNTEKT_WLONN", time="2011-11-12", as_="inntekt")` | `import fd/INNTEKT_WLONN 2011-11-12 as inntekt` |
| `df = md.import_event("fd/F_REHAB", "2011-11-12", "2012-11-12", as_="r")` | `import-event fd/F_REHAB 2011-11-12 to 2012-11-12 as r` |
| `df = md.import_panel(["ds/KJONN","ds/WLONN"], ["2001-01-01","2002-01-01"])` | `import-panel ds/KJONN ds/WLONN 2001-01-01 2002-01-01` |
| `md.recode(df,"v1",{(1,7):0,"nonmissing":1,"missing":(99,"vet ikke")})` | `recode v1 (1/7 = 0) (nonmissing = 1) (missing = 99 "vet ikke" missing)` |
| `md.labels_define("kjonn",{1:"Mann"})` / `md.labels(df,"v",...)` | `define-labels kjonn 1 "Mann"` + `assign-labels v kjonn` |
| `df = md.sample(df, 10000, seed=342343)` | `sample 10000 342343` |
| `md.clone_units(src="person", new="hendelse")` | `clone-units person hendelse` |
| `md.transitions(df,"sivstand",base="sivstand_2010")` | `transitions-panel sivstand sivstand_2010` |
| `md.oaxaca(df,"lonn",["x1","x2"],by="kjonn")` | `oaxaca lonn x1 x2 by kjonn` |
| `md.rdd(df,"vote",run="margin",controls=["i.fylke"],cutoff=600000,cluster="fylke")` | `rdd vote margin i.fylke, cutoff(600000) cluster(fylke)` |
| `md.test(model,["x1=x2","x3"])` / `md.ci(df,["inntekt2004"],level=90)` | `test x1 x2 x3` / `ci inntekt2004, level(90)` |

This single deliverable makes the entire missing column reachable without fragile pandas heuristics, while keeping scripts runnable.

---

## 6. Sequenced implementation plan

**Phase 0 — Test harness first (½ day, RECOMMENDED FIRST PR).** Create `tests/test_translate.py` with a `tr(src)->str` helper + golden-string assertions, one per currently-working command (~40 baseline tests, green). Add `--strict` to cli.py. Small, zero-risk, makes every later change verifiable.

**Phase 1 — Quick correctness fixes (1-2 days).** Each with a regression test: `range(n)` crash (transformer.py:1972); DiD hijack gate (1188); `I(x*z)` protection (formula.py); if/else (1699); `print` (1422); `.str[2:]` (expr.py:565); stat aliasing (expander.py:836); `pd.cut` inf (254); df-wide `fillna` (commands.py:199); string escaping (expr.py:151).

**Phase 2 — High-value idiom coverage (2-3 days).** `df.assign`→generate; `.where/.mask`; raw-variable `ci`+`level()`; `summarize-by` split from tabulate; pivot_table disambiguation; date subtraction/`strftime`/`isoformatdate`/`halfyear`/`rowconcat`/`quantile`(qcut); make every approximation loud.

**Phase 3 — `md` helper module (2-3 days).** Ship `md.py` (12 signatures) + `_try_md_helper` dispatch reusing existing arg extractors. Delivers all ~12 missing commands; document in README/runner.

**Phase 4 — Architecture refactor (2-3 days).** Declarative `Pattern` table; migrate the `_handle_col_assign` waterfall + px/plot maps; add `warnings` channel + `Matched` sentinel; eliminate ambiguous `[]`.

**Phase 5 — Tests/CI/UX (1-2 days).** Full golden suite under `--strict`; GitHub Actions; delete stale root `functions.py`; surface warnings inline in `py2m_runner.html` + `md.*` examples.

**Recommended first PR: Phase 0** — test harness + `--strict`, converting every later fix from "trust me" to "verified."

**Implementer index:** dispatch ladder `transformer.py:421-614` (assign), `1410-1539` (expr-stmt); registry `commands.py:35-85`; expansion waterfall `transformer.py:639-736`; expression tables `expr.py:18-120`; formula/DiD `transformer.py:1186-1207` + `formula.py`; silent-output sites to harden `commands.py:160,199,682`, `expander.py:836-840`.
