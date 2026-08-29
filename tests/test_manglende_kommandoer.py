"""Kommandoer fra microdata.no-manualen som manglet i m2py (funnet 2026-08-30
ved å kjøre hele manuallista mot emulatoren):

  poisson-predict       sto i _COND_FILTER_COMMANDS, men hadde ingen handler
  regress-mml           flernivåanalyse (MML), fantes ikke
  regress-mml-predict   prediksjoner fra samme modell, fantes ikke

Manual: https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer
"""
import numpy as np
import pandas as pd
import pytest

import m2py
from m2py import MicroInterpreter, MicroParser, RegressionHandler

sm = pytest.importorskip("statsmodels.api")


def _run(df, line):
    it = MicroInterpreter(metadata_path=None)
    it.datasets["d"] = df.copy()
    it.active_name = "d"
    it._execute_instruction(it.parser.parse_line(line))
    return "\n".join(str(m) for m in it.output_log), it.datasets["d"]


# ---------------------------------------------------------------------------
# poisson-predict
# ---------------------------------------------------------------------------

def _count_data(n=400, seed=5):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    alder = rng.normal(45, 8, n)
    return pd.DataFrame({
        "sykedager": rng.poisson(np.exp(0.8 + 0.4 * x)),
        "lonn": x, "alder": alder,
        "manedsverk": rng.uniform(0.5, 1.5, n),
    })


class TestPoissonPredict:
    def test_lager_predicted_som_standard(self):
        out, d = _run(_count_data(), "poisson-predict sykedager lonn")
        assert "Ukjent kommando" not in out
        assert "predicted" in d.columns

    def test_predicted_er_forventningen_ikke_lineaerprediksjonen(self):
        df = _count_data()
        _, d = _run(df, "poisson-predict sykedager lonn")
        model = sm.GLM(df["sykedager"], sm.add_constant(df[["lonn"]]),
                       family=sm.families.Poisson()).fit()
        assert np.allclose(d["predicted"], model.predict())
        assert (d["predicted"] > 0).all()          # exp(Xb), aldri negativ

    def test_egendefinert_navn_paa_predicted(self):
        _, d = _run(_count_data(), "poisson-predict sykedager lonn, predicted(pred)")
        assert "pred" in d.columns and "predicted" not in d.columns

    def test_residuals_er_observert_minus_predikert(self):
        df = _count_data()
        _, d = _run(df, "poisson-predict sykedager lonn, predicted(pred) residuals(res)")
        assert np.allclose(d["res"], d["sykedager"] - d["pred"])

    def test_residuals_alene_gir_ogsaa_predicted(self):
        """Samme konvensjon som negative-binomial-predict og regress-predict:
        predicted er standardvalget og lages selv om bare residuals er bedt om.
        (logit-predict avviker bevisst — der er predicted ikke standard.)"""
        _, d = _run(_count_data(), "poisson-predict sykedager lonn, residuals(res)")
        assert "res" in d.columns and "predicted" in d.columns

    def test_noconstant_dropper_konstantleddet(self):
        out, _ = _run(_count_data(), "poisson-predict sykedager lonn, noconstant")
        assert "lonn" in out and "Poisson" in out      # modellen kjørte faktisk
        assert "const" not in out

    def test_exposure_endrer_prediksjonene(self):
        df = _count_data()
        _, a = _run(df, "poisson-predict sykedager lonn, predicted(p)")
        _, b = _run(df, "poisson-predict sykedager lonn, predicted(p) exposure(manedsverk)")
        assert not np.allclose(a["p"], b["p"])

    def test_ukjent_exposure_variabel_feiler_hoeyt(self):
        out, d = _run(_count_data(), "poisson-predict sykedager lonn, exposure(finnesikke)")
        assert "finnesikke" in out and "FEIL" in out
        assert "predicted" not in d.columns

    def test_if_filtrerer(self):
        df = _count_data()
        out, d = _run(df, "poisson-predict sykedager lonn if alder > 45")
        assert d["predicted"].notna().sum() == int((df.alder > 45).sum())


# ---------------------------------------------------------------------------
# regress-mml — flernivåanalyse (MixedLM, REML)
# ---------------------------------------------------------------------------

def _multilevel_data(n_region=6, n_fylke=4, n_per=40, seed=1):
    rng = np.random.default_rng(seed)
    rows = []
    u = rng.normal(0, 1.0, n_region)
    for r in range(n_region):
        v = rng.normal(0, 0.6, n_fylke)
        for f in range(n_fylke):
            for _ in range(n_per):
                mann = int(rng.random() < 0.5)
                rows.append((r + 1, r * n_fylke + f + 1, mann,
                             2 + 0.5 * mann + u[r] + v[f] + rng.normal(0, 0.8)))
    return pd.DataFrame(rows, columns=["region", "fylke", "mann", "lonn"])


class TestParseRegressMml:
    def test_tonivaa(self):
        p = MicroParser().parse_line("regress-mml lonn mann gift by region")
        assert p["args"] == {"dep": "lonn", "indep": ["mann", "gift"], "groups": ["region"]}

    def test_trenivaa_hoeyeste_nivaa_foerst(self):
        p = MicroParser().parse_line("regress-mml lonn mann by region fylke")
        assert p["args"]["groups"] == ["region", "fylke"]

    def test_uten_by_gir_syntaksfeil(self):
        p = MicroParser().parse_line("regress-mml lonn mann")
        assert p["args"] == {"raw": "lonn mann"}

    def test_opsjoner_og_if_overlever(self):
        p = MicroParser().parse_line("regress-mml lonn mann by region if mann == 1, level(90)")
        assert p["args"]["groups"] == ["region"]
        assert p["condition"] == "mann == 1"
        assert p["options"] == {"level": "90"}


class TestRegressMml:
    def test_tonivaa_gir_samme_estimater_som_mixedlm(self):
        df = _multilevel_data()
        out, _ = _run(df, "regress-mml lonn mann by region")
        X = sm.add_constant(df[["mann"]].astype(float))
        ref = sm.MixedLM(df["lonn"].astype(float), X, groups=df["region"]).fit(reml=True)
        assert "Ukjent kommando" not in out
        for name, val in zip(["const", "mann"], ref.params[:2]):
            assert f"{val:.3f}"[:5] in out or f"{val:.4f}"[:6] in out

    def test_gruppevariabelen_navngir_variansleddet(self):
        out, _ = _run(_multilevel_data(), "regress-mml lonn mann by region")
        assert "region" in out

    def test_trenivaa_har_variansledd_for_begge_nivaaer(self):
        out, _ = _run(_multilevel_data(), "regress-mml lonn mann by region fylke")
        assert "region" in out and "fylke" in out

    def test_trenivaa_er_ikke_samme_modell_som_tonivaa(self):
        df = _multilevel_data()
        to, _ = _run(df, "regress-mml lonn mann by region")
        tre, _ = _run(df, "regress-mml lonn mann by region fylke")
        assert to != tre

    def test_faktorsyntaks_virker(self):
        df = _multilevel_data()
        df["utdniva"] = (df.index % 3) + 1
        out, _ = _run(df, "regress-mml lonn mann i.utdniva by region")
        assert "utdniva_2" in out and "utdniva_3" in out

    def test_flere_enn_to_gruppevariabler_avvises(self):
        out, _ = _run(_multilevel_data(), "regress-mml lonn mann by region fylke kommune")
        assert "FEIL" in out and "høyst to" in out

    def test_control_avvises_hoeyt_i_stedet_for_aa_ignoreres_stille(self):
        out, _ = _run(_multilevel_data(), "regress-mml lonn mann by region, control(fylke)")
        assert "FEIL" in out and "control" in out

    def test_trenivaa_matcher_patsy_referansen(self):
        """VCSpec bygges for hånd (patsy er ikke garantert i Pyodide) — den må gi
        nøyaktig samme modell som formel-API-et."""
        pytest.importorskip("patsy")
        df = _multilevel_data()
        ref = sm.MixedLM.from_formula(
            "lonn ~ mann", groups="region", re_formula="1",
            vc_formula={"fylke": "0+C(fylke)"}, data=df).fit(reml=True)
        got = RegressionHandler()._mml_fit(
            df, "lonn", ["mann"], ["region", "fylke"], {})
        assert np.allclose(got["model"].params.to_numpy(), ref.params.to_numpy(), atol=1e-6)

    def test_ukjent_gruppevariabel_feiler_hoeyt(self):
        out, _ = _run(_multilevel_data(), "regress-mml lonn mann by finnesikke")
        assert "finnesikke" in out and "FEIL" in out

    def test_level_endrer_konfidensintervallet(self):
        df = _multilevel_data()
        a, _ = _run(df, "regress-mml lonn mann by region")
        b, _ = _run(df, "regress-mml lonn mann by region, level(90)")
        assert a != b

    def test_if_filtrerer(self):
        df = _multilevel_data()
        out, _ = _run(df, "regress-mml lonn mann by region if region <= 3")
        assert "Ukjent kommando" not in out and "FEIL" not in out


class TestRegressMmlPredict:
    def test_lager_predicted_som_standard(self):
        _, d = _run(_multilevel_data(), "regress-mml-predict lonn mann by region")
        assert "predicted" in d.columns

    def test_egendefinerte_navn(self):
        _, d = _run(_multilevel_data(),
                    "regress-mml-predict lonn mann by region, predicted(p) residuals(res)")
        assert "p" in d.columns and "res" in d.columns

    def test_residualer_er_observert_minus_predikert(self):
        df = _multilevel_data()
        _, d = _run(df, "regress-mml-predict lonn mann by region, predicted(p) residuals(res)")
        assert np.allclose(d["res"], d["lonn"] - d["p"])

    def test_prediksjonen_bruker_gruppeeffektene(self):
        """Med tilfeldige gruppeavskjæringer skal prediksjonen ligge nærmere
        observert verdi enn en ren OLS-prediksjon uten gruppeeffekt."""
        df = _multilevel_data()
        _, d = _run(df, "regress-mml-predict lonn mann by region, predicted(p)")
        X = sm.add_constant(df[["mann"]].astype(float))
        ols = sm.OLS(df["lonn"].astype(float), X).fit().predict()
        assert np.abs(d["p"] - df["lonn"]).mean() < np.abs(ols - df["lonn"]).mean()

    def test_trenivaa_predikerer_ogsaa(self):
        _, d = _run(_multilevel_data(), "regress-mml-predict lonn mann by region fylke")
        assert "predicted" in d.columns and d["predicted"].notna().all()


# ---------------------------------------------------------------------------
# Registrering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", ["poisson-predict", "regress-mml", "regress-mml-predict"])
def test_kommandoen_filtrerer_paa_if(cmd):
    assert cmd in m2py._COND_FILTER_COMMANDS


# ---------------------------------------------------------------------------
# Python-eksport (m2py_translate -> m2py_runtime.pandas_ops / polars_ops)
# ---------------------------------------------------------------------------

class TestPythonEksport:
    def _pandas(self, script, df):
        import m2py_translate as T
        code = T.translate(script, backend="pandas", source_path=None)
        assert "UNTRANSLATED" not in code, code
        ns = {"df": df.copy(), "pd": pd, "datasets": None}
        exec(code, ns)
        return ns

    def test_poisson_predict_oversettes(self):
        ns = self._pandas("poisson-predict sykedager lonn, predicted(p) residuals(res)",
                          _count_data())
        assert {"p", "res"} <= set(ns["df"].columns)

    def test_poisson_predict_gir_samme_tall_som_emulatoren(self):
        df = _count_data()
        _, emu = _run(df, "poisson-predict sykedager lonn, predicted(p)")
        ns = self._pandas("poisson-predict sykedager lonn, predicted(p)", df)
        assert np.allclose(ns["df"]["p"], emu["p"])

    def test_regress_mml_oversettes_og_gir_samme_koeffisienter(self):
        df = _multilevel_data()
        ns = self._pandas("regress-mml lonn mann by region", df)
        res = ns["result_1"]
        ref = RegressionHandler()._mml_fit(df, "lonn", ["mann"], ["region"], {})
        got = dict(zip(res["term"], res["coef"]))
        for term, val in zip(ref["model"].params.index, ref["model"].params.to_numpy()):
            if term in got:
                assert got[term] == pytest.approx(float(val))

    def test_regress_mml_trenivaa_oversettes(self):
        ns = self._pandas("regress-mml lonn mann by region fylke", _multilevel_data())
        assert "fylke" in " ".join(str(t) for t in ns["result_1"]["term"])

    def test_regress_mml_predict_legger_til_kolonner(self):
        ns = self._pandas("regress-mml-predict lonn mann by region, predicted(p)",
                          _multilevel_data())
        assert "p" in ns["df"].columns and ns["df"]["p"].notna().all()

    def test_polars_gir_samme_tall(self):
        pl = pytest.importorskip("polars")
        import m2py_translate as T
        df = _multilevel_data()
        code = T.translate("regress-mml lonn mann by region", backend="polars", source_path=None)
        assert "UNTRANSLATED" not in code, code
        ns = {"data": pl.LazyFrame(df), "pl": pl, "datasets": None}
        exec(code, ns)
        got = ns["result_1"].to_pandas()
        ref = RegressionHandler()._mml_fit(df, "lonn", ["mann"], ["region"], {})
        assert got.loc[got["term"] == "mann", "coef"].iloc[0] == pytest.approx(
            float(ref["model"].params["mann"]))


def test_translate_paastanden_om_at_poisson_predict_ikke_finnes_er_borte():
    """m2py_translate bar kommentaren «poisson-predict is NOT a real microdata
    command (the emulator rejects it)» — den var feil: kommandoen står i
    manualen, og emulatoren avviste den bare fordi den manglet en handler."""
    import pathlib
    src = pathlib.Path(__file__).resolve().parent.parent / "m2py_translate.py"
    assert "NOT a real microdata command" not in src.read_text()


# ---------------------------------------------------------------------------
# Registrering i appen + engelsk meldingskatalog
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", ["poisson-predict", "regress-mml", "regress-mml-predict"])
def test_kommandoen_er_i_autocomplete_lista(cmd):
    import pathlib
    import re as _re
    src = (pathlib.Path(__file__).resolve().parent.parent / "index.html").read_text(encoding="utf-8")
    block = _re.search(r"const MICRODATA_COMMANDS = \[(.*?)\];", src, _re.S)
    assert block, "fant ikke MICRODATA_COMMANDS i index.html"
    assert f"'{cmd}'" in block.group(1)


class TestEngelskeMeldinger:
    def _en(self, df, line):
        old = getattr(m2py, "M2PY_LANG", None)
        m2py.M2PY_LANG = "en"
        try:
            return _run(df, line)[0]
        finally:
            m2py.M2PY_LANG = old

    def test_mml_overskriften_oversettes(self):
        out = self._en(_multilevel_data(), "regress-mml lonn mann by region")
        assert "Multilevel" in out and "levels" in out
        assert "Flernivåmodell" not in out and "grupper" not in out

    def test_mml_feilmelding_om_tre_gruppevariabler_oversettes(self):
        out = self._en(_multilevel_data(), "regress-mml lonn mann by a b c")
        assert "at most two" in out

    def test_mml_control_feilmelding_oversettes(self):
        out = self._en(_multilevel_data(), "regress-mml lonn mann by region, control(fylke)")
        assert "does not support control()" in out
