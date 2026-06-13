"""Regresjonstester for stille-feil-sveipen (kodegjennomgang juni 2026):

1. Ukjente kommandoer / uparserbare argumenter skal gi FEIL, ikke stille no-op.
2. recode: regler skal IKKE kaskadere ("Verdier som allerede er omkodet
   påvirkes ikke av påfølgende regler" — manualen), min/max evalueres på
   originalverdiene, nonmissing/* støttes, if respekteres, prefix() lager
   nye variabler.
3. merge (gammel syntaks): eksplisitt on()-nøkkel som mangler skal gi FEIL,
   ikke stille bytte nøkkel; ukjent datasett skal gi forståelig FEIL.
4. robust/cluster: feil ved beregning av standardfeil skal gi FEIL, ikke
   stille falle tilbake til vanlige standardfeil.
5. ivregress: standardfeil skal bruke korrekte 2SLS-residualer (faktisk
   endogen variabel), ikke naive trinn-2-residualer.
"""
import re

import numpy as np
import pandas as pd
import pytest

import m2py
from m2py import MicroInterpreter


def _interp(df=None, name="testdata"):
    it = MicroInterpreter(metadata_path=None)
    if df is not None:
        it.datasets[name] = df
        it.active_name = name
    return it


def _run(it, *lines):
    for line in lines:
        it._execute_instruction(it.parser.parse_line(line))
    return "\n".join(str(m) for m in it.output_log)


@pytest.fixture
def dc_off(monkeypatch):
    monkeypatch.setattr(m2py, "M2PY_DISCLOSURE_CONTROL", "0", raising=False)


@pytest.fixture
def dc_on(monkeypatch):
    monkeypatch.setattr(m2py, "M2PY_DISCLOSURE_CONTROL", "1", raising=False)


# ---------------------------------------------------------------------------
# 1. Ukjent kommando / ugyldige argumenter
# ---------------------------------------------------------------------------

class TestNoSilentNoOp:
    def test_typo_command_logs_error(self):
        it = _interp(pd.DataFrame({"x": [1.0, 2.0]}))
        out = _run(it, "sumarize x")
        assert "FEIL" in out and "sumarize" in out

    def test_unparseable_args_logs_error(self):
        # sample krever count|fraction OG seed — 'sample 0.5' parser til raw
        it = _interp(pd.DataFrame({"x": [1.0, 2.0]}))
        out = _run(it, "sample 0.5")
        assert "FEIL" in out and "sample" in out

    def test_malformed_define_labels_logs_error(self):
        # Ujevnt antall verdi/etikett-tokens (manglende anførselstegn)
        it = _interp(pd.DataFrame({"x": [1.0]}))
        out = _run(it, "define-labels yrke 1 Ufaglært arbeider")
        assert "FEIL" in out and "define-labels" in out

    def test_valid_command_does_not_error(self):
        it = _interp(pd.DataFrame({"x": np.random.default_rng(0).normal(size=50)}))
        out = _run(it, "summarize x")
        assert "FEIL" not in out


# ---------------------------------------------------------------------------
# 2. recode
# ---------------------------------------------------------------------------

class TestRecodeSemantics:
    def test_rules_do_not_cascade(self, dc_off):
        # Manualen: "Verdier som allerede er omkodet påvirkes ikke av
        # påfølgende regler." Gammel oppførsel: 1-5 -> 2, deretter 2/3 -> 9
        # traff de nye 2-erne og ga 9.
        it = _interp(pd.DataFrame({"x": [1, 2, 3, 10]}))
        _run(it, "recode x (1/5 = 2) (2/3 = 9)")
        assert it.datasets["testdata"]["x"].tolist() == [2, 2, 2, 10]

    def test_star_rule_blocks_later_rules(self, dc_off):
        # Manualen: "Regler som følger etter en med venstreside lik * får
        # dermed ingen virkning."
        it = _interp(pd.DataFrame({"x": [1, 2, 3]}))
        _run(it, "recode x (* = 9) (1 = 5)")
        assert it.datasets["testdata"]["x"].tolist() == [9, 9, 9]

    def test_nonmissing_and_missing_rules(self, dc_off):
        it = _interp(pd.DataFrame({"x": [1.0, np.nan, 5.0]}))
        _run(it, "recode x (1 = 0) (nonmissing = 7) (missing = 99)")
        assert it.datasets["testdata"]["x"].tolist() == [0, 99, 7]

    def test_min_max_evaluated_on_original_values(self, dc_off):
        # min/max skal ikke se verdier som tidligere regler har skrevet
        it = _interp(pd.DataFrame({"x": [1, 2, 3]}))
        _run(it, "recode x (min = 99) (max = 0)")
        assert it.datasets["testdata"]["x"].tolist() == [99, 2, 0]

    def test_recode_honors_if_condition(self, dc_off):
        it = _interp(pd.DataFrame({"x": [1, 1, 2], "g": [1, 2, 2]}))
        _run(it, "recode x (1 = 9) if g == 2")
        assert it.datasets["testdata"]["x"].tolist() == [1, 9, 2]

    def test_prefix_option_creates_new_variable(self, dc_off):
        it = _interp(pd.DataFrame({"x": [1, 2, 3]}))
        _run(it, "recode x (1/2 = 0), prefix('ny_')")
        df = it.datasets["testdata"]
        assert df["x"].tolist() == [1, 2, 3]  # original urørt
        assert df["ny_x"].tolist() == [0, 0, 3]


# ---------------------------------------------------------------------------
# 3. merge (gammel syntaks)
# ---------------------------------------------------------------------------

class TestMergeKeyValidation:
    def _two_datasets(self):
        it = _interp(pd.DataFrame({"unit_id": [1, 2, 3], "x": [10, 20, 30]}), "a")
        it.datasets["b"] = pd.DataFrame({"unit_id": [1, 2, 3], "y": [7, 8, 9]})
        return it

    def test_missing_explicit_on_key_errors(self):
        # Gammel oppførsel: on(pid) finnes ikke -> stille bytte til unit_id
        it = self._two_datasets()
        out = _run(it, "merge b, on(pid)")
        assert "FEIL" in out and "pid" in out
        assert "y" not in it.datasets["a"].columns  # ingen merge utført

    def test_unknown_dataset_errors_clearly(self):
        it = self._two_datasets()
        out = _run(it, "merge finnesikke")
        assert "FEIL" in out and "finnesikke" in out
        assert "KOMMANDO" not in out  # ikke via den generiske exception-loggen

    def test_valid_merge_reports_key(self):
        it = self._two_datasets()
        out = _run(it, "merge b, on(unit_id)")
        assert "y" in it.datasets["a"].columns
        assert "unit_id" in out  # nøkkelen som ble brukt skal logges


# ---------------------------------------------------------------------------
# 4. robust / cluster standardfeil
# ---------------------------------------------------------------------------

def _reg_df(n=200, seed=3):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    g = rng.integers(1, 6, n)
    y = 2 * x + rng.normal(0, 1, n)
    return pd.DataFrame({"y": y, "x": x, "g": g})


class TestRobustClusterErrors:
    def test_cluster_with_unknown_variable_errors(self):
        it = _interp(_reg_df())
        out = _run(it, "regress y x, cluster(finnesikke)")
        assert "FEIL" in out and "finnesikke" in out

    def test_cluster_with_valid_variable_works(self):
        it = _interp(_reg_df())
        out = _run(it, "regress y x, cluster(g)")
        assert "FEIL" not in out and "cluster" in out

    def test_robust_works(self):
        it = _interp(_reg_df())
        out = _run(it, "regress y x, robust")
        assert "FEIL" not in out and "HC1" in out


# ---------------------------------------------------------------------------
# 5. ivregress: korrekte 2SLS-standardfeil
# ---------------------------------------------------------------------------

class TestTwoStageLeastSquaresSE:
    def test_reported_se_uses_actual_endog_residuals(self):
        n = 3000
        rng = np.random.default_rng(7)
        z = rng.normal(0, 1, n)
        u = rng.normal(0, 1, n)  # utelatt konfunder -> endogenitet
        xe = z + u + rng.normal(0, 0.3, n)
        y = 2 * xe + 3 * u + rng.normal(0, 0.5, n)

        it = _interp(pd.DataFrame({"y": y, "xe": xe, "z": z}))
        out = _run(it, "ivregress y (xe = z)")

        m = re.search(r"^xe\s+(-?[\d.]+)\s+([\d.]+)", out, re.M)
        assert m, f"fant ikke xe-raden i output:\n{out}"
        se_reported = float(m.group(2))

        # Manuell 2SLS med korrekte residualer (faktisk xe, ikke predikert)
        Z = np.column_stack([np.ones(n), z])
        xhat = Z @ np.linalg.lstsq(Z, xe, rcond=None)[0]
        X2 = np.column_stack([np.ones(n), xhat])
        b = np.linalg.lstsq(X2, y, rcond=None)[0]
        resid = y - np.column_stack([np.ones(n), xe]) @ b
        sigma2 = resid @ resid / (n - 2)
        cov = sigma2 * np.linalg.inv(X2.T @ X2)
        se_expected = float(np.sqrt(cov[1, 1]))

        # Naiv SE (trinn-2-residualer) er ~66 % større i dette oppsettet,
        # så 3 % toleranse skiller skarpt mellom riktig og galt.
        assert se_reported == pytest.approx(se_expected, rel=0.03)


# ---------------------------------------------------------------------------
# 6. tabulate ..., summarize(): volumtabeller skal også avsløringskontrolleres
# ---------------------------------------------------------------------------

class TestTabulateSummarizeDisclosure:
    """En gjennomsnitts-/sum-tabell over celler med 1–2 observasjoner avslører
    nær-individuelle verdier. Frekvenstabeller stoppes av T5; volumtabellen
    (summarize(...)) gikk tidligere utenom kontrollen og ble vist."""

    def _tiny_cells_df(self):
        # 6 grupper à 2 rader => alle 6 celler har frekvens < 5 (100 % små)
        grp = [g for g in range(6) for _ in range(2)]
        inntekt = [100000 + 1000 * i for i in range(12)]
        return pd.DataFrame({"grp": grp, "inntekt": [float(x) for x in inntekt]})

    def test_default_disclosure_control_is_off(self):
        # Standarden er AV: uten bryter/direktiv blokkeres ikke små tabeller.
        assert m2py._is_disclosure_control() is False
        it = _interp(self._tiny_cells_df())
        out = _run(it, "tabulate grp, summarize(inntekt) mean")
        assert "FEIL" not in out

    def test_directive_can_turn_disclosure_on(self):
        # // m2py: disclosure-control=on slår kontrollen på for scriptet.
        it = _interp(self._tiny_cells_df())
        it.run_script("// m2py: disclosure-control=on\ntabulate grp, summarize(inntekt) mean")
        out = "\n".join(str(m) for m in it.output_log)
        assert "FEIL" in out and "celler" in out

    def test_frequency_table_blocked(self, dc_on):
        # Når kontrollen er på stoppes frekvenstabellen (T5).
        it = _interp(self._tiny_cells_df())
        out = _run(it, "tabulate grp")
        assert "FEIL" in out and "celler" in out

    def test_summarize_volume_table_blocked(self, dc_on):
        it = _interp(self._tiny_cells_df())
        out = _run(it, "tabulate grp, summarize(inntekt) mean")
        assert "FEIL" in out and "celler" in out

    def test_summarize_volume_table_allowed_when_dc_off(self, dc_off):
        it = _interp(self._tiny_cells_df())
        out = _run(it, "tabulate grp, summarize(inntekt) mean")
        assert "FEIL" not in out

    def test_summarize_crosstab_blocked(self, dc_on):
        # To-veis volumtabell med små celler skal også stoppes.
        df = self._tiny_cells_df()
        df["kjonn"] = [0, 1] * 6
        it = _interp(df)
        out = _run(it, "tabulate grp kjonn, summarize(inntekt) mean")
        assert "FEIL" in out and "celler" in out
