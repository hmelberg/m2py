"""Regresjonstester for stille feil funnet i kodegjennomgang (juni 2026).

Hver test dokumenterer forventet atferd der koden tidligere ga
plausible men gale resultater uten feilmelding.
"""
import inspect

import numpy as np
import pandas as pd
import pytest

import m2py
import protect
from m2py import LabelManager, MicroInterpreter, StatsEngine


# ---------------------------------------------------------------------------
# tabulate ..., top / bottom uten tall skal vise 10 (ikke 1) kategorier
# Parseren lagrer opsjoner uten argument som True; int(True) == 1 ga topp-1.
# ---------------------------------------------------------------------------

def _freq_df(n_cats=15):
    """15 kategorier med synkende frekvens: k0 x 16, k1 x 15, ..."""
    vals = []
    for i in range(n_cats):
        vals.extend([f"k{i:02d}"] * (n_cats + 1 - i))
    return pd.DataFrame({"grp": vals, "kjonn": (["m", "f"] * len(vals))[: len(vals)]})


def _data_rows(obj):
    """Antall rader utenom Total/_chi2."""
    return [i for i in obj.index if i not in ("Total", "_chi2")]


class TestTabulateBareTopBottom:
    def test_oneway_bare_top_defaults_to_10(self):
        tb = StatsEngine().execute("tabulate", _freq_df(), ["grp"], {"top": True})
        assert len(_data_rows(tb)) == 10

    def test_oneway_bare_bottom_defaults_to_10(self):
        tb = StatsEngine().execute("tabulate", _freq_df(), ["grp"], {"bottom": True})
        assert len(_data_rows(tb)) == 10

    def test_twoway_bare_top_defaults_to_10(self):
        tb = StatsEngine().execute(
            "tabulate", _freq_df(), ["grp", "kjonn"], {"top": True}
        )
        assert len(_data_rows(tb)) == 10

    def test_twoway_bare_bottom_defaults_to_10(self):
        tb = StatsEngine().execute(
            "tabulate", _freq_df(), ["grp", "kjonn"], {"bottom": True}
        )
        assert len(_data_rows(tb)) == 10

    def test_explicit_top_n_still_works(self):
        tb = StatsEngine().execute("tabulate", _freq_df(), ["grp"], {"top": "3"})
        assert len(_data_rows(tb)) == 3


# ---------------------------------------------------------------------------
# != på kodekolonner med ledende nuller skal speile ==-logikken.
# Før: kandidatlisten ble bygget men ikke brukt, så
# "drop if kommune != '0301'" droppet ALT, inkludert Oslo-radene.
# ---------------------------------------------------------------------------

class TestNotEqualOnZeroPaddedCodes:
    @pytest.fixture
    def interp(self):
        it = MicroInterpreter(metadata_path=None)
        it.label_manager.define_labels("komm_cl", [(301, "Oslo"), (1103, "Stavanger")])
        it.label_manager.assign_labels("kommune", "komm_cl")
        return it

    # object = pandas 2.x (Pyodide i dag); str = pandas 3.x (fremtidig oppgradering)
    @pytest.fixture(params=[object, "str"])
    def df(self, request):
        return pd.DataFrame(
            {"kommune": pd.Series(["0301", "0301", "1103"], dtype=request.param)}
        )

    def test_eq_matches_zero_padded_codes(self, interp, df):
        mask = interp._eval_condition_mask(df, "kommune == '0301'")
        assert mask.tolist() == [True, True, False]

    def test_neq_is_complement_of_eq(self, interp, df):
        mask = interp._eval_condition_mask(df, "kommune != '0301'")
        assert mask.tolist() == [False, False, True]

    def test_neq_without_codelist_unchanged(self):
        # Vanlige strengkolonner uten kodeliste skal oppføre seg som før
        it = MicroInterpreter(metadata_path=None)
        df = pd.DataFrame({"fylke": ["a", "b", "a"]})
        mask = it._eval_condition_mask(df, "fylke != 'a'")
        assert mask.tolist() == [False, True, False]


# ---------------------------------------------------------------------------
# p%-regelen: celler med 1-2 bidragsytere er maksimalt avslørende og skal
# undertrykkes — før ble de hoppet over (continue). sum_rest == 0 betyr at
# nest største bidragsyter kan beregne den største eksakt -> undertrykk.
# ---------------------------------------------------------------------------

class TestPPercentRule:
    def test_single_contributor_cell_is_suppressed(self):
        s = pd.Series({"B": 500.0, "C": 800.0})
        res = protect.suppress(
            s, p_percent=0.1,
            contributions={"B": [500], "C": [400, 250, 150]},
        )
        assert np.isnan(res["B"])
        assert res["C"] == 800.0

    def test_two_contributor_cell_is_suppressed(self):
        s = pd.Series({"A": 1000.0, "C": 800.0})
        res = protect.suppress(
            s, p_percent=0.1,
            contributions={"A": [900, 100], "C": [400, 250, 150]},
        )
        assert np.isnan(res["A"])
        assert res["C"] == 800.0

    def test_zero_remainder_cell_is_suppressed(self):
        # x1 > 0 men resten summerer til 0: nr. 2 kan utlede nr. 1 eksakt
        s = pd.Series({"D": 500.0})
        res = protect.suppress(s, p_percent=0.1, contributions={"D": [300, 200, 0]})
        assert np.isnan(res["D"])

    def test_safe_cell_is_kept(self):
        s = pd.Series({"C": 800.0})
        res = protect.suppress(
            s, p_percent=0.1, contributions={"C": [400, 250, 150]}
        )
        assert res["C"] == 800.0

    def test_cell_without_contribution_data_is_kept(self):
        # Ingen bidragsdata for cellen -> ingenting å vurdere, behold
        s = pd.Series({"E": 42.0})
        res = protect.suppress(s, p_percent=0.1, contributions={})
        assert res["E"] == 42.0

    def test_all_zero_contributions_kept(self):
        # x1 == 0: alle bidrag er null, ingenting å avsløre
        s = pd.Series({"F": 0.0})
        res = protect.suppress(s, p_percent=0.1, contributions={"F": [0, 0, 0]})
        assert res["F"] == 0.0


# ---------------------------------------------------------------------------
# Død LabelManager-klasse: m2py.py hadde to definisjoner der den første
# (avvikende API) skygget søk/redigering men aldri ble brukt.
# ---------------------------------------------------------------------------

class TestSingleLabelManager:
    def test_only_one_labelmanager_definition(self):
        src = inspect.getsource(m2py)
        assert src.count("\nclass LabelManager") == 1

    def test_live_api_drop_labels_varargs(self):
        # Eksekutøren kaller drop_labels(*names) — sikre at API-et består
        lm = LabelManager()
        lm.define_labels("cl", [(1, "a"), (2, "b")])
        lm.assign_labels("x", "cl")
        lm.drop_labels("cl")
        assert "cl" not in lm.codelists
        assert "x" not in lm.var_to_codelist
