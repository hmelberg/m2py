"""Regresjonstester: 'if'-betingelser skal filtrere for alle kommandoer som
ifølge microdata.no-manualen støtter [if].

Manualen (https://microdata.no/manual/kommandoer_og_funksjoner/kommandoer)
dokumenterer [if] for bl.a. alle regresjons-, figur- og overlevelseskommandoer.
Før denne fiksen ble betingelsen stille ignorert for disse — kommandoen kjørte
på HELE datasettet uten advarsel.
"""
import re

import numpy as np
import pandas as pd
import pytest

import m2py
from m2py import MicroInterpreter


N_TOTAL = 2000
N_GROUP1 = 1200


def _make_interp():
    it = MicroInterpreter(metadata_path=None)
    rng = np.random.default_rng(42)
    g = np.array([1] * N_GROUP1 + [2] * (N_TOTAL - N_GROUP1))
    x = rng.normal(10, 2, N_TOTAL)
    # Klar forskjell mellom gruppene: stigning +2 i gruppe 1, -2 i gruppe 2
    y = np.where(g == 1, 2 * x, -2 * x) + rng.normal(0, 0.5, N_TOTAL)
    event = (rng.random(N_TOTAL) < 0.5).astype(int)
    tid = rng.integers(1, 120, N_TOTAL)
    it.datasets["testdata"] = pd.DataFrame(
        {"y": y, "x": x, "g": g, "event": event, "tid": tid}
    )
    it.active_name = "testdata"
    return it


def _run(it, line):
    it._execute_instruction(it.parser.parse_line(line))
    return "\n".join(str(m) for m in it.output_log)


class TestRegressionCommandsHonorIf:
    def test_regress_if_filters_observations(self):
        it = _make_interp()
        out = _run(it, "regress y x if g == 1")
        m = re.search(r"No\. Observations:\s*(\d+)", out)
        assert m, f"fant ikke nobs i output:\n{out}"
        assert int(m.group(1)) == N_GROUP1

    def test_regress_if_changes_estimate(self):
        it = _make_interp()
        out = _run(it, "regress y x if g == 1")
        # Stigningstallet for gruppe 1 er ~2.0; samlet (begge grupper) er det ~0.4
        m = re.search(r"^x\s+(-?\d+\.\d+)", out, re.M)
        assert m, f"fant ikke koeffisient i output:\n{out}"
        assert float(m.group(1)) > 1.5

    def test_regress_predict_if_only_predicts_subset(self):
        # Prediksjoner skrives tilbake indeks-justert: rader utenfor
        # if-utvalget skal få NaN, ikke prediksjoner fra feil modell.
        it = _make_interp()
        _run(it, "regress-predict y x if g == 1")
        df = it.datasets["testdata"]
        assert "predicted" in df.columns
        assert df.loc[df.g == 1, "predicted"].notna().all()
        assert df.loc[df.g == 2, "predicted"].isna().all()

    def test_documented_if_commands_are_in_filter_set(self):
        # Kommandoer dokumentert med [if] i microdata.no-manualen
        # (av dem emulatoren faktisk implementerer)
        documented = {
            "anova", "correlate", "normaltest", "transitions-panel",
            "summarize", "summarize-panel", "tabulate", "tabulate-panel",
            "barchart", "boxplot", "coefplot", "hexbin", "histogram",
            "piechart", "sankey",
            "hausman", "ivregress", "ivregress-predict",
            "logit", "logit-predict", "mlogit", "mlogit-predict",
            "negative-binomial", "negative-binomial-predict",
            "poisson", "poisson-predict", "probit", "probit-predict",
            "rdd", "regress", "regress-panel", "regress-panel-diff",
            "regress-panel-predict", "regress-predict",
            "cox", "kaplan-meier", "weibull",
        }
        missing = documented - m2py._COND_FILTER_COMMANDS
        assert not missing, f"mangler i filtersettet: {sorted(missing)}"


class TestPlotCommandsHonorIf:
    @pytest.mark.parametrize("line", [
        "histogram x if g == 1",
        "piechart g if g == 1",
        "boxplot x if g == 1",
    ])
    def test_plot_handler_receives_filtered_df(self, line):
        it = _make_interp()
        captured = {}
        orig = it.plot_handler.execute

        def spy(cmd, df, args, opts):
            captured["n"] = len(df)
            return orig(cmd, df, args, opts)

        it.plot_handler.execute = spy
        _run(it, line)
        assert captured.get("n") == N_GROUP1


class TestSurvivalCommandsHonorIf:
    def test_survival_handler_receives_filtered_df(self):
        it = _make_interp()
        captured = {}
        orig = it.survival_handler.execute

        def spy(cmd, df, args, opts):
            captured["n"] = len(df)
            return orig(cmd, df, args, opts)

        it.survival_handler.execute = spy
        _run(it, "kaplan-meier event tid if g == 1")
        assert captured.get("n") == N_GROUP1


class TestUnsupportedIfWarns:
    def test_aggregate_with_if_logs_warning(self):
        # aggregate er IKKE dokumentert med [if] i manualen — betingelsen
        # ignoreres, men det skal sies høyt i stedet for stille.
        it = _make_interp()
        out = _run(it, "aggregate (mean) x -> snitt if g == 1, by(g)")
        assert "ADVARSEL" in out and "'if'" in out

    def test_supported_command_does_not_warn(self):
        it = _make_interp()
        out = _run(it, "summarize x if g == 1")
        assert "ADVARSEL" not in out
