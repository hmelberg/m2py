"""Tester for oaxaca-kommandoen (Blinder-Oaxaca-dekomponering).

Kilde for syntaks og opsjoner:
https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer#oaxaca
    oaxaca var-name var-list by var-name [if] [, options]
    options: robust, noconstant, pool

Formlene følger Jann (2008), "The Blinder-Oaxaca decomposition for linear
regression models", Stata Journal 8(4):453-479 — samme som Stata `oaxaca`.
"""
import pathlib
import re

import numpy as np
import pandas as pd
import pytest

import m2py
from m2py import MicroInterpreter, MicroParser, RegressionHandler

sm = pytest.importorskip("statsmodels.api")


# ---------------------------------------------------------------------------
# Testdata: to grupper med ulike gjennomsnitt OG ulike koeffisienter, slik at
# alle tre komponentene (endowments/coefficients/interaction) er ulik null.
# ---------------------------------------------------------------------------

def _sample(n=1200, seed=7):
    rng = np.random.default_rng(seed)
    g = np.repeat([0, 1], n // 2)                     # 0 = gruppe 1, 1 = gruppe 2
    utd = np.where(g == 0, rng.normal(13, 2, n), rng.normal(11, 2, n))
    alder = np.where(g == 0, rng.normal(45, 8, n), rng.normal(41, 8, n))
    lonn = np.where(
        g == 0,
        4.0 + 0.09 * utd + 0.012 * alder,
        3.4 + 0.06 * utd + 0.008 * alder,
    ) + rng.normal(0, 0.30, n)
    return pd.DataFrame({"lonn": lonn, "utd": utd, "alder": alder, "kvinne": g})


def _fit(df, dep="lonn", indep=("utd", "alder"), by="kvinne", **options):
    return RegressionHandler()._oaxaca_fit(df, dep, list(indep), by, dict(options))


def _manual(df, dep="lonn", indep=("utd", "alder"), by="kvinne", const=True):
    """Uavhengig referanseutregning av beta/xbar per gruppe, rett fra statsmodels."""
    indep = list(indep)
    codes = sorted(df[by].dropna().unique())
    out = []
    for code in codes:
        d = df[df[by] == code]
        X = d[indep].astype(float)
        if const:
            X = sm.add_constant(X, has_constant="add")
        model = sm.OLS(d[dep].astype(float), X).fit()
        out.append((model.params.to_numpy(), X.mean().to_numpy(), model))
    return out


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

class TestParseOaxaca:
    def test_splits_dep_indep_and_by(self):
        p = MicroParser().parse_line("oaxaca lonn utd alder by kvinne")
        assert p["command"] == "oaxaca"
        assert p["args"] == {"dep": "lonn", "indep": ["utd", "alder"], "by": "kvinne"}

    def test_keeps_if_condition_and_options(self):
        p = MicroParser().parse_line("oaxaca lonn utd by kvinne if alder > 30, pool robust")
        assert p["args"] == {"dep": "lonn", "indep": ["utd"], "by": "kvinne"}
        assert p["condition"] == "alder > 30"
        assert p["options"] == {"pool": True, "robust": True}

    def test_missing_by_gives_raw_so_dispatcher_reports_syntax_error(self):
        p = MicroParser().parse_line("oaxaca lonn utd alder")
        assert p["args"] == {"raw": "lonn utd alder"}


# ---------------------------------------------------------------------------
# Three-fold (standard)
# ---------------------------------------------------------------------------

class TestThreefold:
    def test_group1_is_the_lower_by_code(self):
        r = _fit(_sample())
        assert (r["g1"], r["g2"]) == (0, 1)

    def test_difference_is_group1_minus_group2_mean(self):
        df = _sample()
        r = _fit(df)
        m0 = df.loc[df.kvinne == 0, "lonn"].mean()
        m1 = df.loc[df.kvinne == 1, "lonn"].mean()
        assert r["mean1"] == pytest.approx(m0)
        assert r["mean2"] == pytest.approx(m1)
        assert r["diff"] == pytest.approx(m0 - m1)

    def test_group_sizes_are_reported(self):
        df = _sample()
        r = _fit(df)
        assert (r["n1"], r["n2"]) == (int((df.kvinne == 0).sum()), int((df.kvinne == 1).sum()))

    def test_components_are_endowments_coefficients_interaction(self):
        r = _fit(_sample())
        assert [t["name"] for t in r["terms"]] == ["endowments", "coefficients", "interaction"]

    def test_components_sum_to_the_difference(self):
        r = _fit(_sample())
        assert sum(t["est"] for t in r["terms"]) == pytest.approx(r["diff"], abs=1e-9)

    def test_endowments_equals_xbar_diff_times_group2_beta(self):
        df = _sample()
        (b1, xb1, _), (b2, xb2, _) = _manual(df)
        r = _fit(df)
        expected = float((xb1 - xb2) @ b2)
        assert r["terms"][0]["est"] == pytest.approx(expected)

    def test_coefficients_equals_group2_xbar_times_beta_diff(self):
        df = _sample()
        (b1, xb1, _), (b2, xb2, _) = _manual(df)
        r = _fit(df)
        assert r["terms"][1]["est"] == pytest.approx(float(xb2 @ (b1 - b2)))

    def test_interaction_equals_xbar_diff_times_beta_diff(self):
        df = _sample()
        (b1, xb1, _), (b2, xb2, _) = _manual(df)
        r = _fit(df)
        assert r["terms"][2]["est"] == pytest.approx(float((xb1 - xb2) @ (b1 - b2)))


# ---------------------------------------------------------------------------
# Two-fold pooled (, pool)
# ---------------------------------------------------------------------------

class TestPooledTwofold:
    def test_components_are_explained_unexplained(self):
        r = _fit(_sample(), pool=True)
        assert [t["name"] for t in r["terms"]] == ["explained", "unexplained"]

    def test_components_sum_to_the_difference(self):
        r = _fit(_sample(), pool=True)
        assert sum(t["est"] for t in r["terms"]) == pytest.approx(r["diff"], abs=1e-9)

    def test_reference_coefficients_come_from_pooled_model_with_group_indicator(self):
        df = _sample()
        X = df[["utd", "alder"]].astype(float).copy()
        X["_grp"] = (df["kvinne"] == 0).astype(float)      # gruppeindikator (Jann 2008)
        X = sm.add_constant(X, has_constant="add")
        star = sm.OLS(df["lonn"].astype(float), X).fit().params
        b_star = np.array([star["const"], star["utd"], star["alder"]])
        (_, xb1, _), (_, xb2, _) = _manual(df)
        r = _fit(df, pool=True)
        assert r["terms"][0]["est"] == pytest.approx(float((xb1 - xb2) @ b_star))

    def test_unexplained_equals_jann_formula(self):
        df = _sample()
        (b1, xb1, _), (b2, xb2, _) = _manual(df)
        r = _fit(df, pool=True)
        b_star = np.asarray(r["beta_star"])
        assert r["terms"][1]["est"] == pytest.approx(
            float(xb1 @ (b1 - b_star) + xb2 @ (b_star - b2)))


# ---------------------------------------------------------------------------
# Standardfeil
# ---------------------------------------------------------------------------

class TestStandardErrors:
    def test_every_component_has_a_positive_finite_se(self):
        r = _fit(_sample())
        ses = [t["se"] for t in r["terms"]] + [r["diff_se"]]
        assert all(np.isfinite(s) and s > 0 for s in ses)

    def test_endowments_se_matches_delta_method(self):
        df = _sample()
        (b1, xb1, m1), (b2, xb2, m2) = _manual(df)
        d = xb1 - xb2
        X1 = sm.add_constant(df.loc[df.kvinne == 0, ["utd", "alder"]].astype(float),
                             has_constant="add")
        X2 = sm.add_constant(df.loc[df.kvinne == 1, ["utd", "alder"]].astype(float),
                             has_constant="add")
        Vx1 = np.cov(X1.to_numpy(), rowvar=False) / len(X1)
        Vx2 = np.cov(X2.to_numpy(), rowvar=False) / len(X2)
        var = d @ m2.cov_params().to_numpy() @ d + b2 @ (Vx1 + Vx2) @ b2
        r = _fit(df)
        assert r["terms"][0]["se"] == pytest.approx(float(np.sqrt(var)))

    def test_robust_changes_standard_errors_not_estimates(self):
        df = _sample()
        plain, rob = _fit(df), _fit(df, robust=True)
        for a, b in zip(plain["terms"], rob["terms"]):
            assert b["est"] == pytest.approx(a["est"])
            assert b["se"] != pytest.approx(a["se"])

    def test_p_values_follow_from_estimate_and_se(self):
        from scipy import stats
        r = _fit(_sample())
        t = r["terms"][1]
        assert t["p"] == pytest.approx(2 * stats.norm.sf(abs(t["est"] / t["se"])))


# ---------------------------------------------------------------------------
# Opsjoner og feilhåndtering
# ---------------------------------------------------------------------------

class TestOptionsAndErrors:
    def test_noconstant_decomposes_the_predicted_difference(self):
        df = _sample()
        r = _fit(df, noconstant=True)
        (b1, xb1, _), (b2, xb2, _) = _manual(df, const=False)
        assert r["pred_diff"] == pytest.approx(float(xb1 @ b1 - xb2 @ b2))
        assert sum(t["est"] for t in r["terms"]) == pytest.approx(r["pred_diff"], abs=1e-9)

    def test_with_constant_predicted_difference_equals_raw_difference(self):
        r = _fit(_sample())
        assert r["pred_diff"] == pytest.approx(r["diff"])

    def test_factor_syntax_expands_to_dummies(self):
        df = _sample()
        df["utdniva"] = pd.cut(df["utd"], 3, labels=[1, 2, 3]).astype(int)
        r = _fit(df, indep=("i.utdniva", "alder"))
        assert r["indep"] == ["utdniva_2", "utdniva_3", "alder"]

    def test_by_variable_with_three_values_is_rejected(self):
        df = _sample()
        df.loc[df.index[:10], "kvinne"] = 2
        with pytest.raises(ValueError, match="nøyaktig to"):
            _fit(df)

    def test_by_variable_with_one_value_is_rejected(self):
        df = _sample()
        df["kvinne"] = 0
        with pytest.raises(ValueError, match="nøyaktig to"):
            _fit(df)

    def test_unknown_variable_is_rejected(self):
        with pytest.raises(ValueError, match="finnes ikke|ikke funnet"):
            _fit(_sample(), indep=("utd", "fantasi"))

    def test_by_variable_may_not_also_be_a_regressor(self):
        with pytest.raises(ValueError, match="by-variabelen"):
            _fit(_sample(), indep=("utd", "kvinne"))


# ---------------------------------------------------------------------------
# Tekst-output
# ---------------------------------------------------------------------------

class TestOutput:
    def _run(self, line, df=None):
        it = MicroInterpreter(metadata_path=None)
        it.datasets["d"] = _sample() if df is None else df
        it.active_name = "d"
        it._execute_instruction(it.parser.parse_line(line))
        return "\n".join(str(m) for m in it.output_log)

    def test_threefold_output_lists_groups_sizes_and_components(self):
        out = self._run("oaxaca lonn utd alder by kvinne")
        assert "Blinder-Oaxaca" in out
        assert "kvinne = 0" in out and "kvinne = 1" in out
        assert re.search(r"^\s*endowments\s+-?\d", out, re.M)
        assert re.search(r"^\s*coefficients\s+-?\d", out, re.M)
        assert re.search(r"^\s*interaction\s+-?\d", out, re.M)

    def test_pool_output_uses_two_fold_labels(self):
        out = self._run("oaxaca lonn utd alder by kvinne, pool")
        assert re.search(r"^\s*explained\s+-?\d", out, re.M)
        assert re.search(r"^\s*unexplained\s+-?\d", out, re.M)
        assert "interaction" not in out

    def test_if_condition_filters_the_sample(self):
        df = _sample()
        out = self._run("oaxaca lonn utd alder by kvinne if alder > 45", df)
        n1 = int(((df.kvinne == 0) & (df.alder > 45)).sum())
        assert f"N = {n1}" in out

    def test_output_is_english_when_the_ui_language_is_english(self):
        old = getattr(m2py, "M2PY_LANG", None)
        m2py.M2PY_LANG = "en"
        try:
            out = self._run("oaxaca lonn utd alder by kvinne")
        finally:
            m2py.M2PY_LANG = old
        assert "Group 1" in out and "mean = " in out
        assert "gjennomsnitt" not in out and "Differanse" not in out

    def test_error_messages_are_english_when_the_ui_language_is_english(self):
        df = _sample()
        df.loc[df.index[:10], "kvinne"] = 2
        old = getattr(m2py, "M2PY_LANG", None)
        m2py.M2PY_LANG = "en"
        try:
            out = self._run("oaxaca lonn utd alder by kvinne", df)
        finally:
            m2py.M2PY_LANG = old
        assert "exactly two values" in out

    def test_syntax_error_names_the_unparsable_arguments(self):
        out = self._run("oaxaca lonn utd alder")
        assert "Kunne ikke tolke argumentene" in out
        assert "lonn utd alder" in out


# ---------------------------------------------------------------------------
# Registrering i kommandotabellene
# ---------------------------------------------------------------------------

def test_oaxaca_is_registered_as_an_if_filtering_command():
    assert "oaxaca" in m2py._COND_FILTER_COMMANDS


# ---------------------------------------------------------------------------
# Avsløringskontroll (T7): hver gruppe er sin egen populasjon
# ---------------------------------------------------------------------------

class TestDisclosureControl:
    def _run(self, df, line="oaxaca lonn utd alder by kvinne"):
        old = getattr(m2py, "M2PY_DISCLOSURE_CONTROL", "0")
        m2py.M2PY_DISCLOSURE_CONTROL = "1"
        try:
            it = MicroInterpreter(metadata_path=None)
            it.datasets["d"] = df
            it.active_name = "d"
            it._execute_instruction(it.parser.parse_line(line))
            return "\n".join(str(m) for m in it.output_log)
        finally:
            m2py.M2PY_DISCLOSURE_CONTROL = old

    def test_a_group_below_the_population_minimum_is_refused(self):
        df = _sample()
        small = df[df.kvinne == 1].head(4)                 # bare 4 kvinner igjen
        out = self._run(pd.concat([df[df.kvinne == 0], small], ignore_index=True))
        assert "FEIL" in out
        assert "Blinder-Oaxaca" not in out

    def test_two_large_groups_pass(self):
        out = self._run(_sample())
        assert "Blinder-Oaxaca" in out


# ---------------------------------------------------------------------------
# Python-eksport: m2py_translate -> m2py_runtime.pandas_ops / polars_ops
# ---------------------------------------------------------------------------

class TestPythonExport:
    def test_translate_emits_an_ops_call_for_pandas(self):
        import m2py_translate as T
        code = T.translate("oaxaca lonn utd alder by kvinne", backend="pandas",
                           source_path=None)
        assert "UNTRANSLATED" not in code
        assert "ops.oaxaca(" in code
        assert "dep='lonn'" in code and "indep=['utd', 'alder']" in code
        assert "by='kvinne'" in code

    def test_translate_passes_the_pool_and_noconstant_options(self):
        import m2py_translate as T
        code = T.translate("oaxaca lonn utd by kvinne, pool noconstant",
                           backend="pandas", source_path=None)
        assert "pool=True" in code and "noconstant=True" in code

    def test_pandas_ops_returns_the_same_estimates_as_the_emulator(self):
        from m2py_runtime import pandas_ops as po
        df = _sample()
        emu = _fit(df)
        out = po.oaxaca(df, "lonn", ["utd", "alder"], "kvinne").set_index("term")
        for t in emu["terms"]:
            assert out.loc[t["name"], "estimate"] == pytest.approx(t["est"])
            assert out.loc[t["name"], "se"] == pytest.approx(t["se"])
        assert out.loc["difference", "estimate"] == pytest.approx(emu["pred_diff"])

    def test_pandas_ops_pool_returns_the_two_fold_terms(self):
        from m2py_runtime import pandas_ops as po
        out = po.oaxaca(_sample(), "lonn", ["utd", "alder"], "kvinne", pool=True)
        assert list(out["term"]) == ["difference", "explained", "unexplained"]

    @pytest.mark.parametrize("opts", [{"pool": True}, {"robust": True},
                                      {"pool": True, "robust": True},
                                      {"noconstant": True}])
    def test_pandas_ops_matches_the_emulator_for_every_option(self, opts):
        from m2py_runtime import pandas_ops as po
        df = _sample()
        emu = _fit(df, **{k: True for k in opts})
        out = po.oaxaca(df, "lonn", ["utd", "alder"], "kvinne", **opts).set_index("term")
        for t in emu["terms"]:
            assert out.loc[t["name"], "estimate"] == pytest.approx(t["est"])
            assert out.loc[t["name"], "se"] == pytest.approx(t["se"])

    def test_polars_backend_gives_the_same_numbers(self):
        pl = pytest.importorskip("polars")
        import m2py_translate as T
        df = _sample()
        code = T.translate("oaxaca lonn utd alder by kvinne", backend="polars",
                           source_path=None)
        assert "UNTRANSLATED" not in code
        ns = {"data": pl.LazyFrame(df), "pl": pl, "datasets": None}
        exec(code, ns)
        got = ns["result_1"].to_pandas().set_index("term")
        emu = _fit(df)
        assert got.loc["endowments", "estimate"] == pytest.approx(emu["terms"][0]["est"])


# ---------------------------------------------------------------------------
# Kommandoen må være synlig i appen (autocomplete + hjelp)
# ---------------------------------------------------------------------------

def _repo_file(name):
    return (pathlib.Path(__file__).resolve().parent.parent / name).read_text(encoding="utf-8")


def test_oaxaca_is_in_the_autocomplete_command_list():
    block = re.search(r"const MICRODATA_COMMANDS = \[(.*?)\];",
                      _repo_file("index.html"), re.S)
    assert block, "fant ikke MICRODATA_COMMANDS i index.html"
    assert "'oaxaca'" in block.group(1)


def test_oaxaca_has_a_help_entry():
    assert '"oaxaca"' in _repo_file("command_help.js")
