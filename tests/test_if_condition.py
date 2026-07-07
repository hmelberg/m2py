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


def _make_strcode_interp():
    """Datasett der kjonn er STRENG-kodet ('1'/'2') slik metadata-importer gir,
    mens brukeren sammenligner med tall — den kjente dtype-fellen."""
    it = MicroInterpreter(metadata_path=None)
    n = 100
    kjonn = ["1"] * 60 + ["2"] * 40
    alder = list(range(20, 70)) * 2  # 20..69 to ganger
    lonn = [float(1000 + i) for i in range(n)]
    it.datasets["testdata"] = pd.DataFrame(
        {"kjonn": kjonn, "alder": alder, "lonn": lonn}
    )
    it.active_name = "testdata"
    return it


class TestCompoundConditionsDtypeAware:
    """B1 (kodegjennomgang 2026-07-07): sammensatte betingelser (&/|) falt
    tilbake til rå Python-eval uten dtype-tilpasning — `kjonn == 1` mot
    strengkolonnen '1' ga stille 0 rader, mens den enkle betingelsen virket."""

    def _expected_and(self, it):
        df = it.datasets["testdata"]
        return int(((df.kjonn == "1") & (df.alder > 30)).sum())

    def test_mask_compound_and_matches_string_codes(self):
        it = _make_strcode_interp()
        df = it.datasets["testdata"]
        mask = it._eval_condition_mask(df, "kjonn == 1 & alder > 30")
        assert mask is not None
        expected = self._expected_and(it)
        assert expected > 0
        assert int(mask.sum()) == expected

    def test_mask_compound_with_parentheses(self):
        it = _make_strcode_interp()
        df = it.datasets["testdata"]
        mask = it._eval_condition_mask(df, "(kjonn == 1) & (alder > 30)")
        assert mask is not None
        assert int(mask.sum()) == self._expected_and(it)

    def test_mask_compound_or(self):
        it = _make_strcode_interp()
        df = it.datasets["testdata"]
        mask = it._eval_condition_mask(df, "kjonn == 2 | alder > 65")
        assert mask is not None
        expected = int(((df.kjonn == "2") | (df.alder > 65)).sum())
        assert int(mask.sum()) == expected

    def test_mask_or_and_precedence(self):
        # Stata/Python: & binder sterkere enn |
        it = _make_strcode_interp()
        df = it.datasets["testdata"]
        mask = it._eval_condition_mask(df, "kjonn == 2 | kjonn == 1 & alder > 30")
        assert mask is not None
        expected = int(((df.kjonn == "2") | ((df.kjonn == "1") & (df.alder > 30))).sum())
        assert int(mask.sum()) == expected

    def test_summarize_compound_if_filters_rows(self):
        # Sluttbrukerscenarioet fra kodegjennomgangen:
        # `summarize lonn if kjonn == 1 & alder > 30` returnerte 0 rader.
        it = _make_strcode_interp()
        expected = self._expected_and(it)
        captured = {}
        orig = it.stats_engine.execute

        def spy(cmd, df, args, opts):
            captured["n"] = len(df)
            return orig(cmd, df, args, opts)

        it.stats_engine.execute = spy
        _run(it, "summarize lonn if kjonn == 1 & alder > 30")
        assert captured.get("n") == expected

    def test_unparseable_compound_still_falls_back(self):
        # Betingelser vi ikke kan dekomponere trygt skal fortsatt gi et
        # resultat via fallback (numeriske kolonner virker der).
        it = _make_strcode_interp()
        captured = {}
        orig = it.stats_engine.execute

        def spy(cmd, df, args, opts):
            captured["n"] = len(df)
            return orig(cmd, df, args, opts)

        it.stats_engine.execute = spy
        _run(it, "summarize lonn if alder*1 > 30 & alder != 35")
        df = it.datasets["testdata"]
        expected = int(((df.alder > 30) & (df.alder != 35)).sum())
        assert captured.get("n") == expected


class TestGenerateIfDtypeAware:
    """B2 (kodegjennomgang 2026-07-07): `generate ... if <cond>` brukte rå
    _py_eval_cond uten dtype-tilpasning — `generate mann = 1 if kjonn == 1`
    ga en kolonne med bare missing, mens replace med samme betingelse virket."""

    def test_generate_if_matches_string_codes(self):
        it = _make_strcode_interp()
        _run(it, "generate mann = 1 if kjonn == 1")
        df = it.datasets["testdata"]
        assert "mann" in df.columns
        assert (df.loc[df.kjonn == "1", "mann"] == 1).all()
        assert df.loc[df.kjonn == "2", "mann"].isna().all()

    def test_generate_if_compound_condition(self):
        it = _make_strcode_interp()
        _run(it, "generate ung_mann = 1 if kjonn == 1 & alder < 30")
        df = it.datasets["testdata"]
        sel = (df.kjonn == "1") & (df.alder < 30)
        assert sel.any()
        assert (df.loc[sel, "ung_mann"] == 1).all()
        assert df.loc[~sel, "ung_mann"].isna().all()

    def test_generate_if_numeric_column_unchanged(self):
        # Allerede fungerende tilfelle (numerisk kolonne) må være uendret.
        it = _make_interp()
        _run(it, "generate g1 = 1 if g == 1")
        df = it.datasets["testdata"]
        assert (df.loc[df.g == 1, "g1"] == 1).all()
        assert df.loc[df.g == 2, "g1"].isna().all()


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


# ---------------------------------------------------------------------------
# B6 (kodegjennomgang 2026-07-07): 'if'-betingelser med komma ble revet i
# stykker av opsjonssplitteren — linja ble delt på FØRSTE komma (inne i
# inrange/inlist-parentesen) før if-splitten. Varianten
# `summarize x, gini if cond` mistet betingelsen stille og rapporterte
# statistikk for hele populasjonen.
# ---------------------------------------------------------------------------

class TestIfConditionsWithCommas:
    def test_parse_inrange_condition_kept_intact(self):
        it = _make_interp()
        instr = it.parser.parse_line("summarize x if inrange(tid, 30, 40)")
        assert instr["condition"] == "inrange(tid, 30, 40)"
        assert instr["options"] == {}

    def test_parse_condition_before_options(self):
        it = _make_interp()
        instr = it.parser.parse_line("summarize x if inrange(tid, 30, 40), gini")
        assert instr["condition"] == "inrange(tid, 30, 40)"
        assert "gini" in instr["options"]

    def test_summarize_inrange_runs_and_filters(self):
        it = _make_interp()
        out = _run(it, "summarize tid if inrange(tid, 30, 40)")
        assert "FEIL" not in out, out
        n_expected = int(
            ((it.datasets["testdata"]["tid"] >= 30)
             & (it.datasets["testdata"]["tid"] <= 40)).sum()
        )
        assert re.search(rf"(?<![\d.]){n_expected}(?![\d.])", out), out

    def test_tabulate_inlist_condition_runs(self):
        it = _make_interp()
        out = _run(it, "tabulate g if inlist(g, 1, 2)")
        assert "FEIL" not in out, out

    def test_option_then_if_applies_condition(self):
        # `summarize x, gini if g == 1` — betingelsen står ETTER opsjons-
        # kommaet. Før: stille full-populasjonsstatistikk. Nå: betingelsen
        # brukes (Antall = 1200, ikke 2000).
        it = _make_interp()
        instr = it.parser.parse_line("summarize x, gini if g == 1")
        assert instr["condition"] == "g == 1"
        assert "gini" in instr["options"]
        out = _run(it, "summarize x, gini if g == 1")
        assert "FEIL" not in out, out
        assert re.search(r"(?<![\d.])1200(?![\d.])", out), out
        assert not re.search(r"(?<![\d.])2000(?![\d.])", out), out
