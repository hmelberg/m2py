# Python → microdata.no Translation Guide

py2m translates Python (pandas / numpy / statsmodels / plotly express) into a
microdata.no script. It is AST-based: it recognises common idioms and maps them
to microdata commands. Anything it can't map is emitted as a loud
`// UNTRANSLATED` line plus a warning — never silently dropped.

All mappings below are covered by the test suite (`py2m/tests/`).

## General rules

**Translates well:** column assignment, row filtering, group aggregation,
frequency/cross tables, descriptive stats, sampling, OLS/logit/probit/poisson
regression and predictions, and a wide set of element-wise expressions.

**Does not translate** (emitted as `// UNTRANSLATED` + warning): control flow
(`if/else`, `for` over non-literals), positional row selection, deduplication,
sorting, and any pandas idiom with no microdata equivalent.

**Write Python for best results:** operate on a single DataFrame (default name
`df`); use explicit column names (`df['income']`, not computed names); keep one
operation per statement where possible.

## Mixed Python and microdata blocks

Import data in microdata, analyse in Python:

```
## microdata
create-dataset folk
require w income age gender

## python
df['log_income'] = np.log(df['income'].clip(lower=1))
df = df[df['age'] > 18]
smf.ols('log_income ~ age + gender', data=df).fit()
```

Lines in a `## microdata` block pass through unchanged; `## python` blocks are translated.

---

## Variable manipulation

| Python | microdata |
|--------|-----------|
| `df['x'] = df['a'] + 1` | `generate x = (a + 1)` |
| `df['x'] = np.log(df['a'])` | `generate x = ln(a)` |
| `df.loc[df['a'] > 5, 'x'] = 1` | `replace x = 1 if a > 5` |
| `df['x'] = np.where(df['a'] > 5, 1, 0)` | `generate x = 0` + `replace x = 1 if a > 5` |
| `df['x'] = df['a'].where(cond, other)` | `generate x = other` + `replace x = a if cond` |
| `df['x'] = df['a'].mask(cond, other)` | `generate x = a` + `replace x = other if cond` |
| `df['x'] = df['income'].fillna(0)` | `generate x = income` + `replace x = 0 if sysmiss(x)` |
| `df = df.assign(x=…, y=…)` | one `generate` per keyword |
| `df['x'] = pd.cut(df['age'], bins=[0,30,np.inf], labels=[1,2])` | `generate x = .` + `replace x = … if …` (handles `np.inf`) |
| `df['x'] = df['c'].map({1:'a', 2:'b'})` | `generate x = <missing>` + `replace x = … if c == …` |
| `df['x'] = pd.qcut(df['income'], 4, labels=False)` | `generate x = quantile(income, 4)` |

## Rows and columns

| Python | microdata |
|--------|-----------|
| `df = df[df['age'] > 18]` | `keep if age > 18` |
| `df = df.query('age > 18')` | `keep if age > 18` |
| `df = df[['a','b']]` | `keep a b` |
| `df = df.drop(columns=['a'])` | `drop a` |
| `df = df.dropna(subset=['income'])` | `drop if sysmiss(income)` |
| `df = df.rename(columns={'a':'b'})` | `rename a b` (literal keys only) |
| `df['x'] = pd.to_numeric(df['x'])` | `destring x` |
| `df = df.sample(n=1000, random_state=42)` | `sample 1000 42` |

## Aggregation

| Python | microdata |
|--------|-----------|
| `df['m'] = df.groupby('g')['x'].transform('mean')` | `aggregate (mean) x -> m, by(g)` |
| `s = df.groupby('g').agg(m=('x','mean')).reset_index()` | `clone-dataset s` + `use s` + `collapse (mean) x -> m, by(g)` |
| `df.groupby('g')['x'].mean()` | `tabulate g, summarize(x)` |

Supported statistics: `mean`, `sum`, `min`, `max`, `median`, `count`, `sd`, `sem`, `iqr`. Lossy ones (`var`, `first`, `last`) are **not** substituted — they emit `// UNTRANSLATED` so results aren't silently wrong.

## Tables, descriptives, regression

| Python | microdata |
|--------|-----------|
| `df['x'].value_counts()` | `tabulate x` |
| `df['x'].value_counts(normalize=True)` | `tabulate x, cellpct` |
| `pd.crosstab(df['a'], df['b'])` | `tabulate a b` |
| `pd.crosstab(df['a'], df['b'], normalize='index')` | `tabulate a b, rowpct` |
| `df['x'].describe()` | `summarize x` |
| `df[['a','b']].corr()` | `correlate a b` |
| `smf.ols('y ~ x + z', data=df).fit()` | `regress y x z` |
| `smf.logit('y ~ x', data=df).fit()` | `logit y x` |
| `smf.probit / smf.poisson / smf.mnlogit` | `probit / poisson / mlogit` |
| `model.predict()` / `model.resid` (after a model) | `regress-predict …, predicted(…)` / `residuals(…)` |

**Formulas:** `x:z` interactions and `a*b` (main effects + interaction) generate
temp variables; `I(expr)` is supported. `a*b` is **not** interpreted as
difference-in-differences.

## Expression functions

| Python | microdata |
|--------|-----------|
| `np.sqrt`, `np.exp`, `np.log`→`ln`, `np.abs`, `.abs()`, `.round(n)` | same / `ln` / `abs` / `round` |
| `df['name'].str.len()` / `.upper()` / `.lower()` / `.strip()` | `length` / `upper` / `lower` / `trim` |
| `df['a'].str.cat(df['b'], sep=' ')` | `rowconcat(a, ' ', b)` |
| `df['k'].isin([1, 2])` | `inlist(k, 1, 2)` |
| `df['age'].between(18, 67)` | `inrange(age, 18, 67)` |
| `df['income'].isna()` | `sysmiss(income)` |
| `df['d'].dt.year` / `.month` / `.quarter` / … | `year(d)` / `month(d)` / `quarter(d)` |
| `df['d'].dt.strftime('%Y-%m-%d')` | `isoformatdate(d)` (ISO format only) |
| `(df['d2'] - df['d1']).dt.days` | `(d2 - d1)` (microdata dates are integer days) |
| `df[['a','b','c']].max(axis=1)` | `rowmax(a, b, c)` (also min/mean/sum/std/median) |
| scipy `stats.norm.cdf(x)` etc. | distribution functions |

---

## What does not translate (emitted loudly)

| Python pattern | Why |
|----------------|-----|
| `if / else`, `for i in range(n)` (non-literal) | no control flow in microdata |
| `df.sort_values(...)` / `df.drop_duplicates()` | no sort / dedup command |
| `df.head(k)` / `.iloc[...]` | no positional row access |
| `df['x'].str[2:]` (open-ended) / `.str.contains(...)` | no equivalent string op |
| `var` / `first` / `last` aggregation | different statistic — not substituted |
| `df.fillna(0)` over all columns | apply per column instead |
| string literals containing `'` | microdata has no string-quote escape |
| `pd.pivot_table(...)` (analytic, assigned) | not yet mapped |

Each of these becomes a `// UNTRANSLATED` comment (and usually a warning), so a
partially-translatable script still produces the commands it can and flags the
rest for manual conversion.
