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


# ---------------------------------------------------------------------------
# 6b. D1 (kodegjennomgang 2026-07-07): tabulate-panel og transitions-panel
# gikk helt utenom T5 — en tabell tabulate blokkerer ble vist med råceller
# på 1-2 via panelvariantene (transitions-panel til og med som rad-
# normaliserte overgangssannsynligheter fra celler på størrelse 1).
# ---------------------------------------------------------------------------

class TestPanelTablesDisclosure:
    def _tiny_panel_df(self):
        # 6 grupper à 2 enheter, 2 tidspunkter => alle råceller har frekvens < 5
        rows = []
        for tid in (2019, 2020):
            for g in range(6):
                for i in range(2):
                    rows.append({"unit_id": g * 2 + i + 1, "tid": tid, "grp": g})
        return pd.DataFrame(rows)

    def test_tabulate_blocks_small_cells_sanity(self, dc_on):
        # Sanity: samme data blokkeres av vanlig tabulate (T5).
        it = _interp(self._tiny_panel_df())
        out = _run(it, "tabulate grp")
        assert "FEIL" in out and "celler" in out

    def test_tabulate_panel_blocked_like_tabulate(self, dc_on):
        it = _interp(self._tiny_panel_df())
        out = _run(it, "tabulate-panel grp")
        assert "FEIL" in out and "celler" in out

    def test_transitions_panel_blocked(self, dc_on):
        it = _interp(self._tiny_panel_df())
        out = _run(it, "transitions-panel grp")
        assert "FEIL" in out and "celler" in out

    def test_panel_tables_allowed_when_dc_off(self, dc_off):
        it = _interp(self._tiny_panel_df())
        out = _run(it, "tabulate-panel grp")
        out += _run(it, "transitions-panel grp")
        assert "FEIL" not in out


# ---------------------------------------------------------------------------
# 7. destring force: uten force skal ikke-numeriske verdier gi FEIL (hele
# operasjonen avbrytes, jf. manualen). Med force → missing. Tidligere var
# begge grener errors='coerce', så force var død og verdier ble stille NaN.
# ---------------------------------------------------------------------------

class TestDestringForce:
    def test_non_numeric_without_force_errors(self):
        it = _interp(pd.DataFrame({"x": ["1", "2", "abc", "4"]}))
        out = _run(it, "destring x")
        assert "FEIL" in out
        # Operasjonen skal ikke ha konvertert kolonnen
        assert it.datasets[it.active_name]["x"].tolist() == ["1", "2", "abc", "4"]

    def test_non_numeric_with_force_becomes_missing(self):
        it = _interp(pd.DataFrame({"x": ["1", "2", "abc", "4"]}))
        out = _run(it, "destring x, force")
        assert "FEIL" not in out
        col = it.datasets[it.active_name]["x"]
        assert col[0] == 1 and col[1] == 2 and col[3] == 4
        assert pd.isna(col[2])

    def test_clean_numeric_without_force_converts(self):
        it = _interp(pd.DataFrame({"x": ["1", "2", "3"]}))
        out = _run(it, "destring x")
        assert "FEIL" not in out
        assert it.datasets[it.active_name]["x"].tolist() == [1, 2, 3]

    def test_missing_values_are_not_treated_as_non_numeric(self):
        # Ekte missing (NaN) skal ikke utløse force-feilen.
        it = _interp(pd.DataFrame({"x": ["1", None, "3"]}))
        out = _run(it, "destring x")
        assert "FEIL" not in out
        col = it.datasets[it.active_name]["x"]
        assert col[0] == 1 and col[2] == 3 and pd.isna(col[1])


# ---------------------------------------------------------------------------
# 8. Toppnivå-feilmelding skal inkludere unntakstypen (ikke bare str(e)),
# slik at kryptiske feil (f.eks. KeyError) blir lettere å diagnostisere.
# ---------------------------------------------------------------------------

class TestCommandErrorMessage:
    def test_error_includes_exception_type(self):
        it = _interp(pd.DataFrame({"x": [1.0] * 12}))
        out = _run(it, "regress y q")
        assert "FEIL PÅ KOMMANDO 'regress'" in out
        assert "ValueError" in out


# ---------------------------------------------------------------------------
# 9. Nøstede for...end-blokker: microdata bruker `;` mellom nivåer i ÉN for.
# Et nøstet for...end ble tidligere stille feilkjørt (ytre body ble kuttet
# ved indre `end`). Nå skal det gi en tydelig FEIL.
# ---------------------------------------------------------------------------

class TestNestedForRejected:
    def test_nested_for_end_errors_clearly(self):
        it = _interp(pd.DataFrame({"x": [1.0] * 12}))
        it.run_script(
            "for i in 1:2\nfor j in 3:4\nsummarize x\nend\nend"
        )
        out = "\n".join(str(m) for m in it.output_log)
        assert "FEIL" in out
        assert "nøst" in out.lower() or "nest" in out.lower()
        # Skal avvises rent: nøyaktig én feil, og kroppen kjøres ikke
        assert out.lower().count("feil") == 1
        assert "Gj.snitt" not in out  # summarize skal ikke ha kjørt

    def test_single_level_for_still_works(self):
        it = _interp(pd.DataFrame({"x": [1.0] * 12}))
        it.run_script("for i in 1:2\nsummarize x\nend")
        out = "\n".join(str(m) for m in it.output_log)
        assert "FEIL" not in out

    def test_multilevel_semicolon_for_still_works(self):
        # microdata-idiomet for nøsting: `;` mellom nivåer
        it = _interp(pd.DataFrame({"x": [1.0] * 12}))
        it.run_script("for i in 1:2; j in 3:4\nsummarize x\nend")
        out = "\n".join(str(m) for m in it.output_log)
        assert "FEIL" not in out


# ---------------------------------------------------------------------------
# 10. configure seed/alpha/cache var skrive-bare: verdiene ble lagret men
# aldri lest. Loggen ("Satt seed = 42") villedet til å tro de virket. Nå
# skal loggen være ærlig om at innstillingen ikke påvirker beregninger ennå.
# ---------------------------------------------------------------------------

class TestConfigureHonest:
    def test_seed_states_no_effect_yet(self):
        it = _interp(pd.DataFrame({"x": [1.0]}))
        out = _run(it, "configure seed 42")
        assert "42" in out and "ikke" in out.lower()

    def test_alpha_states_no_effect_yet(self):
        it = _interp(pd.DataFrame({"x": [1.0]}))
        out = _run(it, "configure alpha 0.1")
        assert "0.1" in out and "ikke" in out.lower()

    def test_cache_states_no_effect_yet(self):
        it = _interp(pd.DataFrame({"x": [1.0]}))
        out = _run(it, "configure nocache")
        assert "ikke" in out.lower()


# ---------------------------------------------------------------------------
# 11. destring ignore(): anførselstegn rundt tegnlisten er streng-skilletegn,
# ikke tegn som skal fjernes. ignore(',') skal bare fjerne komma — en apostrof
# i dataene er ikke-numerisk og skal utløse force-feilen, ikke fjernes stille.
# ---------------------------------------------------------------------------

class TestDestringIgnoreQuoting:
    def test_ignore_quotes_are_delimiters_not_ignored_chars(self):
        it = _interp(pd.DataFrame({"v": ["1'0", "2"]}))
        out = _run(it, "destring v, ignore(',')")
        assert "FEIL" in out  # apostrofen er ikke-numerisk og ikke i ignore-settet

    def test_ignore_quoted_and_unquoted_equivalent(self):
        a = _interp(pd.DataFrame({"v": ["1.000", "2.500"]}))
        _run(a, "destring v, ignore('.')")
        b = _interp(pd.DataFrame({"v": ["1.000", "2.500"]}))
        _run(b, "destring v, ignore(.)")
        assert a.datasets["testdata"]["v"].tolist() == b.datasets["testdata"]["v"].tolist() == [1000, 2500]


# ---------------------------------------------------------------------------
# 12. Konfigurerbare avsløringsterskler (Innstillinger): T1/T5/T6/T7 skal
# kunne settes via M2PY_DEFAULTS. Standardene er uendret (1000/5/10/10).
# ---------------------------------------------------------------------------

class TestConfigurableThresholds:
    def test_defaults_unchanged(self):
        assert m2py._dc_threshold("dc_min_population") == 1000
        assert m2py._dc_threshold("dc_tabulate_low_cell") == 5
        assert m2py._dc_threshold("dc_min_affected") == 10
        assert m2py._dc_threshold("dc_min_summarize") == 10

    # T7 — minste populasjon for deskriptiv statistikk
    def test_t7_default_blocks(self, dc_on):
        it = _interp(pd.DataFrame({"x": list(map(float, range(8)))}))
        assert "FEIL" in _run(it, "summarize x")

    def test_t7_lowered_allows(self, dc_on, monkeypatch):
        monkeypatch.setitem(m2py.M2PY_DEFAULTS, "dc_min_summarize", 5)
        it = _interp(pd.DataFrame({"x": list(map(float, range(8)))}))
        assert "FEIL" not in _run(it, "summarize x")

    # T1 — minste populasjon etter keep/drop
    def test_t1_default_blocks(self, dc_on):
        it = _interp(pd.DataFrame({"g": [1] * 500 + [0] * 1000}))
        assert "FEIL" in _run(it, "keep if g == 1")

    def test_t1_lowered_allows(self, dc_on, monkeypatch):
        monkeypatch.setitem(m2py.M2PY_DEFAULTS, "dc_min_population", 100)
        it = _interp(pd.DataFrame({"g": [1] * 500 + [0] * 1000}))
        assert "FEIL" not in _run(it, "keep if g == 1")

    # T6 — minste antall påvirkede rader
    def test_t6_default_blocks(self, dc_on):
        it = _interp(pd.DataFrame({"x": [1] * 5 + [2] * 2000}))
        assert "FEIL" in _run(it, "recode x (1 = 9)")

    def test_t6_lowered_allows(self, dc_on, monkeypatch):
        monkeypatch.setitem(m2py.M2PY_DEFAULTS, "dc_min_affected", 2)
        it = _interp(pd.DataFrame({"x": [1] * 5 + [2] * 2000}))
        assert "FEIL" not in _run(it, "recode x (1 = 9)")

    # T5 — minste cellefrekvens i tabeller
    def _tiny3(self):
        grp = [g for g in range(6) for _ in range(3)]  # 6 celler à 3 rader
        return pd.DataFrame({"grp": grp})

    def test_t5_default_blocks(self, dc_on):
        assert "FEIL" in _run(_interp(self._tiny3()), "tabulate grp")

    def test_t5_lowered_allows(self, dc_on, monkeypatch):
        monkeypatch.setitem(m2py.M2PY_DEFAULTS, "dc_tabulate_low_cell", 2)
        assert "FEIL" not in _run(_interp(self._tiny3()), "tabulate grp")


# ---------------------------------------------------------------------------
# 9. D2 (kodegjennomgang 2026-07-07): figurkommandoer gikk utenom
# avsløringskontrollen. piechart, diskret histogram og sankey viste de samme
# råtellingene som tabulate ville blokkert (T5); barchart med (min)/(max)/
# (mean) viste eksakte, uwinsoriserte gruppe-ekstremer (T2).
# ---------------------------------------------------------------------------

class TestGraphDisclosure:
    def _tiny_cells_df(self):
        # 6 kategorier à 2 rader => alle celler har frekvens < 5 (100 % små)
        grp = [g for g in range(6) for _ in range(2)]
        return pd.DataFrame({"grp": grp, "grp2": [0, 1] * 6})

    def test_piechart_blocked_small_cells(self, dc_on):
        out = _run(_interp(self._tiny_cells_df()), "piechart grp")
        assert "FEIL" in out and "celler" in out

    def test_discrete_histogram_blocked_small_cells(self, dc_on):
        out = _run(_interp(self._tiny_cells_df()), "histogram grp, discrete")
        assert "FEIL" in out and "celler" in out

    def test_sankey_blocked_small_links(self, dc_on):
        out = _run(_interp(self._tiny_cells_df()), "sankey grp grp2")
        assert "FEIL" in out and "celler" in out

    def test_graphs_allowed_when_dc_off(self, dc_off):
        it = _interp(self._tiny_cells_df())
        out = _run(it, "piechart grp")
        out += _run(it, "histogram grp, discrete")
        out += _run(it, "sankey grp grp2")
        assert "FEIL" not in out

    def test_piechart_allowed_with_big_cells(self, dc_on):
        grp = [g for g in range(3) for _ in range(20)]
        out = _run(_interp(pd.DataFrame({"grp": grp})), "piechart grp")
        assert "FEIL" not in out


class TestBarchartWinsorization:
    """barchart (min)/(max)/(mean) skal bruke samme T2-winsorisering som
    histogram/boxplot/scatter — ellers viser (min)-søylen den eksakte
    laveste enkeltverdien i hver gruppe."""

    def _df(self):
        # Én ekstrem enkeltverdi (0.0) i gruppe 1 — resten ligger rundt 1000+
        lonn = [0.0] + [1000.0 + i for i in range(99)] + [2000.0 + i for i in range(100)]
        g = [1] * 100 + [2] * 100
        return pd.DataFrame({"lonn": lonn, "g": g})

    def test_barchart_min_over_group_is_winsorized(self, dc_on):
        df = self._df()
        fig = m2py.PlotHandler().execute(
            "barchart", df, {"stat": "min", "vars": ["lonn"]}, {"over": "g"}
        )
        w = m2py._winsorize_series(df["lonn"])
        expected = w.groupby(df["g"]).min()
        y = [float(v) for v in fig.data[0].y]
        assert 0.0 not in y
        assert y == pytest.approx([expected.loc[1], expected.loc[2]])

    def test_barchart_min_exact_when_dc_off(self, dc_off):
        df = self._df()
        fig = m2py.PlotHandler().execute(
            "barchart", df, {"stat": "min", "vars": ["lonn"]}, {"over": "g"}
        )
        y = [float(v) for v in fig.data[0].y]
        assert 0.0 in y

    def test_barchart_mean_single_var_is_winsorized(self, dc_on):
        df = self._df()
        fig = m2py.PlotHandler().execute(
            "barchart", df, {"stat": "mean", "vars": ["lonn"]}, {}
        )
        w = m2py._winsorize_series(df["lonn"])
        y = [float(v) for v in fig.data[0].y]
        assert y[0] == pytest.approx(w.mean())
        assert y[0] != pytest.approx(df["lonn"].mean())


# ---------------------------------------------------------------------------
# 10. D3 (kodegjennomgang 2026-07-07): tabulate ..., summarize(var) —
# volumtabellen hoppet over T2-winsorisering og T8-avrunding som vanlig
# summarize bruker: rå gruppegjennomsnitt og persentiler i full presisjon.
# ---------------------------------------------------------------------------

class TestVolumeTableWinsorizeAndRound:
    def _df(self):
        # 2 grupper à 25 (alle celler >= 5, T5 passerer); én ekstrem outlier
        grp = [0] * 25 + [1] * 25
        inntekt = (
            [100.0 + i for i in range(24)] + [1e9]
            + [200.0 + i for i in range(25)]
        )
        return pd.DataFrame({"grp": grp, "inntekt": inntekt})

    def test_volume_mean_uses_winsorized_column(self, dc_on):
        from m2py import StatsEngine
        df = self._df()
        tb = StatsEngine().execute("tabulate", df, ["grp"], {"summarize": "inntekt"})
        w = m2py._winsorize_series(df["inntekt"])
        expected = w[df["grp"] == 0].mean()
        raw = df.loc[df["grp"] == 0, "inntekt"].mean()
        assert float(tb.loc[0]) == pytest.approx(expected)
        assert float(tb.loc[0]) != pytest.approx(raw)

    def test_volume_crosstab_mean_uses_winsorized_column(self, dc_on):
        from m2py import StatsEngine
        df = self._df()
        df["kjonn"] = ([0] * 13 + [1] * 12) * 2
        tb = StatsEngine().execute(
            "tabulate", df, ["grp", "kjonn"], {"summarize": "inntekt"}
        )
        w = m2py._winsorize_series(df["inntekt"])
        expected = w[(df["grp"] == 0) & (df["kjonn"] == 1)].mean()
        assert float(tb.loc[0, 1]) == pytest.approx(expected)

    def test_volume_p50_rounded_to_3_sig_digits(self, dc_on):
        from m2py import StatsEngine
        grp = [0] * 25 + [1] * 25
        inntekt = [123456.789 + i for i in range(50)]
        df = pd.DataFrame({"grp": grp, "inntekt": inntekt})
        tb = StatsEngine().execute(
            "tabulate", df, ["grp"], {"summarize": "inntekt", "p50": True}
        )
        raw_p50 = df.loc[df["grp"] == 0, "inntekt"].quantile(0.5)
        assert float(tb.loc[0]) == m2py._round_to_sig_digits(raw_p50)
        assert float(tb.loc[0]) != pytest.approx(raw_p50)

    def test_volume_table_unchanged_when_dc_off(self, dc_off):
        from m2py import StatsEngine
        df = self._df()
        tb = StatsEngine().execute("tabulate", df, ["grp"], {"summarize": "inntekt"})
        raw = df.loc[df["grp"] == 0, "inntekt"].mean()
        assert float(tb.loc[0]) == pytest.approx(raw)


# ---------------------------------------------------------------------------
# 11. D4 (kodegjennomgang 2026-07-07): gruppert summarize svakere enn vanlig
# summarize — T7 sjekket bare total-N (gruppe på 2 fikk mean/min/max),
# summarize-panel winsoriserte ikke, og gini ble beregnet på rå kolonne
# mens gjennomsnittet var winsorisert.
# ---------------------------------------------------------------------------

class TestGroupedSummarizeT7:
    def test_summarize_by_small_group_refused(self, dc_on):
        # Total (103) passerer T7, men gruppe 1 har bare 3 enheter.
        df = pd.DataFrame({
            "g": [1] * 3 + [2] * 100,
            "x": [float(i) for i in range(103)],
        })
        out = _run(_interp(df), "summarize x, by(g)")
        assert "FEIL" in out

    def test_summarize_by_big_groups_allowed(self, dc_on):
        df = pd.DataFrame({
            "g": [1] * 50 + [2] * 50,
            "x": [float(i) for i in range(100)],
        })
        out = _run(_interp(df), "summarize x, by(g)")
        assert "FEIL" not in out

    def test_summarize_panel_small_tid_group_refused(self, dc_on):
        df = pd.DataFrame({
            "unit_id": list(range(100)) + [1, 2, 3],
            "tid": [2019] * 100 + [2020] * 3,
            "x": [float(i) for i in range(103)],
        })
        out = _run(_interp(df), "summarize-panel x")
        assert "FEIL" in out

    def test_small_groups_allowed_when_dc_off(self, dc_off):
        df = pd.DataFrame({
            "g": [1] * 3 + [2] * 100,
            "x": [float(i) for i in range(103)],
        })
        out = _run(_interp(df), "summarize x, by(g)")
        assert "FEIL" not in out


class TestSummarizePanelWinsorize:
    def _df(self):
        x = [100.0 + i for i in range(24)] + [1e9] + [200.0 + i for i in range(25)]
        return pd.DataFrame({
            "unit_id": list(range(25)) * 2,
            "tid": [2019] * 25 + [2020] * 25,
            "x": x,
        })

    def test_panel_mean_uses_winsorized_column(self, dc_on):
        from m2py import StatsEngine
        df = self._df()
        res = StatsEngine().execute("summarize-panel", df, ["x"], {})
        w = m2py._winsorize_series(df["x"])
        expected = w[df["tid"] == 2019].mean()
        raw = df.loc[df["tid"] == 2019, "x"].mean()
        assert float(res.loc[2019, ("x", "mean")]) == pytest.approx(expected)
        assert float(res.loc[2019, ("x", "mean")]) != pytest.approx(raw)

    def test_panel_mean_raw_when_dc_off(self, dc_off):
        from m2py import StatsEngine
        df = self._df()
        res = StatsEngine().execute("summarize-panel", df, ["x"], {})
        raw = df.loc[df["tid"] == 2019, "x"].mean()
        assert float(res.loc[2019, ("x", "mean")]) == pytest.approx(raw)


class TestGiniOnWinsorizedColumn:
    """gini skal beregnes på samme winsoriserte kolonne som mean/std (T2) —
    ellers avslører den rå kolonne-informasjon som resten av tabellen skjuler."""

    def _df(self):
        x = [100.0 + i for i in range(49)] + [1e9]
        return pd.DataFrame({"g": [1] * 25 + [2] * 25, "x": x})

    def test_plain_summarize_gini_winsorized(self, dc_on):
        from m2py import StatsEngine
        df = self._df()
        res = StatsEngine().execute("summarize", df, ["x"], {"gini": True})
        w = m2py._winsorize_series(df["x"])
        assert float(res.loc["x", "Gini"]) == pytest.approx(m2py.calculate_gini(w))
        assert float(res.loc["x", "Gini"]) != pytest.approx(m2py.calculate_gini(df["x"]))

    def test_grouped_summarize_gini_winsorized(self, dc_on):
        from m2py import StatsEngine
        df = self._df()
        res = StatsEngine().execute("summarize", df, ["x"], {"gini": True, "by": "g"})
        w = m2py._winsorize_series(df["x"])
        expected = m2py.calculate_gini(w[df["g"] == 2])
        raw = m2py.calculate_gini(df.loc[df["g"] == 2, "x"])
        assert float(res.loc[2, ("x", "gini")]) == pytest.approx(expected)
        assert float(res.loc[2, ("x", "gini")]) != pytest.approx(raw)

    def test_plain_summarize_gini_raw_when_dc_off(self, dc_off):
        from m2py import StatsEngine
        df = self._df()
        res = StatsEngine().execute("summarize", df, ["x"], {"gini": True})
        assert float(res.loc["x", "Gini"]) == pytest.approx(m2py.calculate_gini(df["x"]))


# ---------------------------------------------------------------------------
# 13. D5 (kodegjennomgang 2026-07-07): regresjon/overlevelse hadde ikke noe
# populasjonsminimum — `regress`/`logit`/`cox`/`kaplan-meier` kjørte på
# subsett summarize ville T7-nektet. Samme T7-sjekk (totalt N; for
# kaplan-meier by() også per gruppe) skal gjelde. DC av: uendret.
# ---------------------------------------------------------------------------

class TestModelPopulationMinimum:
    def _reg_df(self, n=8):
        rng = np.random.default_rng(1)
        x = rng.normal(size=n)
        return pd.DataFrame({"y": 2 * x + rng.normal(size=n), "x": x})

    def _surv_df(self, n=8, groups=None):
        rng = np.random.default_rng(2)
        df = pd.DataFrame({
            "dead": rng.integers(0, 2, size=n),
            "tid": rng.uniform(1, 10, size=n),
        })
        if groups is not None:
            df["g"] = groups
        return df

    def test_regress_blocked_below_t7(self, dc_on):
        it = _interp(self._reg_df(8))
        out = _run(it, "regress y x")
        assert "FEIL" in out and "minst 10" in out

    def test_regress_allowed_at_t7(self, dc_on):
        it = _interp(self._reg_df(30))
        out = _run(it, "regress y x")
        assert "FEIL" not in out

    def test_regress_if_subset_blocked(self, dc_on):
        df = self._reg_df(30)
        df["grp"] = [1] * 5 + [0] * 25
        it = _interp(df)
        out = _run(it, "regress y x if grp == 1")
        assert "FEIL" in out and "minst 10" in out

    def test_logit_blocked_below_t7(self, dc_on):
        df = self._reg_df(8)
        df["y"] = (df["y"] > 0).astype(float)
        it = _interp(df)
        out = _run(it, "logit y x")
        assert "FEIL" in out and "minst 10" in out

    def test_coefplot_blocked_below_t7(self, dc_on):
        it = _interp(self._reg_df(8))
        out = _run(it, "coefplot y x")
        assert "FEIL" in out and "minst 10" in out

    def test_cox_blocked_below_t7(self, dc_on):
        it = _interp(self._surv_df(8))
        out = _run(it, "cox dead tid")
        assert "FEIL" in out and "minst 10" in out

    def test_kaplan_meier_blocked_below_t7(self, dc_on):
        it = _interp(self._surv_df(8))
        out = _run(it, "kaplan-meier dead tid")
        assert "FEIL" in out and "minst 10" in out

    def test_kaplan_meier_by_group_blocked_per_group(self, dc_on):
        # Totalt N=33 passerer, men én gruppe har 3 — per-gruppe-sjekk skal slå til
        groups = [1] * 30 + [2] * 3
        it = _interp(self._surv_df(33, groups=groups))
        out = _run(it, "kaplan-meier dead tid, by(g)")
        assert "FEIL" in out and "Gruppen" in out and "minst 10" in out

    def test_kaplan_meier_by_group_allowed_when_all_big(self, dc_on):
        groups = [1] * 15 + [2] * 15
        it = _interp(self._surv_df(30, groups=groups))
        out = _run(it, "kaplan-meier dead tid, by(g)")
        assert "FEIL" not in out

    def test_dc_off_unchanged(self, dc_off):
        it = _interp(self._reg_df(8))
        out = _run(it, "regress y x")
        assert "FEIL" not in out
        it2 = _interp(self._surv_df(8))
        out2 = _run(it2, "kaplan-meier dead tid")
        assert "FEIL" not in out2


# ---------------------------------------------------------------------------
# 14. S4 (kodegjennomgang 2026-07-07): variabelnavn interpoleres i
# data-var1/data-var2-attributtene i tablehtml-embeds og konsumeres via
# innerHTML — de skal HTML-escapes (inkl. anførselstegn).
# ---------------------------------------------------------------------------

class TestTablehtmlAttributeEscaping:
    def test_data_var_attributes_are_escaped(self):
        name = 'a"b'
        it = _interp(pd.DataFrame({name: ["x"] * 6 + ["y"] * 6}))
        _run(it, f"tabulate {name}")
        embeds = [str(m) for m in it.output_log if "data-var1" in str(m)]
        assert embeds, "forventet tablehtml-embed med data-var1"
        html = embeds[0]
        assert 'data-var1="a&quot;b"' in html
        assert 'data-var1="a"b"' not in html
