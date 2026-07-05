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


# ---------------------------------------------------------------------------
# Enslig `.` → np.nan: omskrivingen var blind for strenger, så et
# strenglitteral som '.' ble til litteralen 'np.nan'.
# ---------------------------------------------------------------------------

class TestLoneDotQuoteAware:
    def test_dot_string_literal_preserved(self):
        # '.' er en gyldig strengverdi, ikke missing
        assert m2py._micro_expr_fixup("kode = '.'") == "kode = '.'"

    def test_dot_inside_double_quotes_preserved(self):
        assert m2py._micro_expr_fixup('kode = ". "') == 'kode = ". "'

    def test_bare_dot_still_becomes_nan(self):
        # Utenfor strenger skal `.` fortsatt bli np.nan (tildeling)
        assert m2py._micro_expr_fixup("x = .") == "x = np.nan"

    def test_dot_in_string_with_bare_dot_outside(self):
        # Blandet: strengen bevares, det frie punktet konverteres
        assert m2py._micro_expr_fixup("x = . if s == 'a'") == "x = np.nan if s == 'a'"


# ---------------------------------------------------------------------------
# for-each-ekspansjon brukte rå substring-replace: en iterator som `i` manglet
# ord som `import` (→ `1mport`) og `summarize` (→ `summar1ze`).
# ---------------------------------------------------------------------------

class TestForEachWordBoundary:
    def _expand(self, text):
        return m2py.MicroParser().preprocess_script(text)

    def test_iterator_does_not_mangle_keywords(self):
        out = self._expand("for-each i in 1 {\nimport INNTEKT\nsummarize i\n}")
        assert "1mport" not in out and "summar1ze" not in out
        assert "import INNTEKT" in out
        assert "summarize 1" in out

    def test_iterator_replaces_bare_token_each_item(self):
        out = self._expand("for-each v in a b {\nsummarize v\n}")
        assert "summarize a" in out and "summarize b" in out


# ---------------------------------------------------------------------------
# Rank-swap byttet på feil akse: rad-indeks ble forvekslet med rang-posisjon,
# så naerhetsgarantien (swap_range_pct) holdt ikke når data ikke var sortert.
# ---------------------------------------------------------------------------

class TestRankSwapProximity:
    def test_rank_swap_is_local_in_value_rank(self):
        rng = np.random.default_rng(42)
        vals = np.arange(1000, dtype=float)
        rng.shuffle(vals)  # rad-rekkefølge != verdi-rekkefølge
        df = pd.DataFrame({"x": vals})
        out = protect.swap(df, "x", method="rank", level="row",
                           share=0.1, swap_range_pct=0.02, random_state=0)
        rank = pd.Series(df["x"].values).rank(method="first").values
        val_to_rank = {v: r for v, r in zip(df["x"].values, rank)}
        newrank = np.array([val_to_rank[v] for v in out["x"].values])
        drank = np.abs(newrank - rank)
        changed = out["x"].values != df["x"].values
        window = int(1000 * 0.02)
        assert changed.sum() > 0
        # Hver byttet verdi skal flyttes bare noen få vinduer i rang, ikke
        # over hele fordelingen.
        assert drank[changed].max() <= 4 * window


# ---------------------------------------------------------------------------
# plot-jitter brukte en useeded RNG, i motsetning til alle andre verb, så
# resultatet var ikke reproduserbart med random_state.
# ---------------------------------------------------------------------------

class TestPlotJitterSeeded:
    def test_jitter_is_reproducible_with_seed(self):
        x = np.arange(50.0)
        y = np.arange(50.0)
        r1 = protect.suppress((x, y), jitter=(1.0, 1.0), random_state=0)
        r2 = protect.suppress((x, y), jitter=(1.0, 1.0), random_state=0)
        assert np.allclose(r1[0], r2[0]) and np.allclose(r1[1], r2[1])


# ---------------------------------------------------------------------------
# k-anonymisering returnerte stille data som IKKE var k-anonyme når
# iterasjonene tok slutt. Nå verifiseres målet og funksjonen feiler tydelig.
# ---------------------------------------------------------------------------

class TestKAnonymizeVerifiesTarget:
    def test_raises_when_target_not_reached(self):
        df = pd.DataFrame({"a": list(range(20)), "b": list(range(20))})
        with pytest.raises(ValueError, match="[kK]"):
            protect.profile(df, "k_anonymize", quasi_ids=["a", "b"],
                            k=5, max_iterations=1)

    def test_succeeds_when_reachable(self):
        df = pd.DataFrame({"a": [1, 1, 1, 2, 2, 2, 3, 4]})
        out, log = protect.profile(df, "k_anonymize", quasi_ids=["a"], k=2)
        assert protect.risk(out, quasi_ids=["a"]).k_min >= 2


# ---------------------------------------------------------------------------
# RiskReport.t_max (t-closeness) ble skrevet ut men aldri beregnet (alltid
# None). Nå beregnes den som maks total-variasjonsavstand per gruppe.
# ---------------------------------------------------------------------------

class TestTClosenessComputed:
    def test_t_max_computed_when_sensitive_given(self):
        df = pd.DataFrame({
            "q": [0, 0, 0, 1, 1, 1],
            "s": ["A", "A", "A", "A", "B", "B"],
        })
        rep = protect.risk(df, quasi_ids=["q"], sensitive=["s"])
        assert rep.t_max is not None
        assert rep.t_max > 0.3

    def test_t_max_none_without_sensitive(self):
        df = pd.DataFrame({"q": [0, 0, 1, 1]})
        rep = protect.risk(df, quasi_ids=["q"])
        assert rep.t_max is None


# ---------------------------------------------------------------------------
# Deterministiske verb (coarsen/year/month) godtok share<1 men ignorerte den
# stille. Delvis anvendelse ville gitt inkonsistente data — avvis tydelig.
# ---------------------------------------------------------------------------

class TestDeterministicVerbsRejectPartialShare:
    def test_coarsen_rejects_partial_share(self):
        df = pd.DataFrame({"x": [1.0, 2, 3, 4]})
        with pytest.raises(ValueError, match="share"):
            protect.coarsen(df, "x", to=10, share=0.5)

    def test_year_rejects_partial_share(self):
        df = pd.DataFrame({"d": pd.to_datetime(["2001-05-01", "2002-06-01"])})
        with pytest.raises(ValueError, match="share"):
            protect.year(df, "d", share=0.5)

    def test_month_rejects_partial_share(self):
        df = pd.DataFrame({"d": pd.to_datetime(["2001-05-01", "2002-06-01"])})
        with pytest.raises(ValueError, match="share"):
            protect.month(df, "d", share=0.5)

    def test_default_share_is_accepted(self):
        df = pd.DataFrame({"x": [1.0, 2, 3, 4]})
        out = protect.coarsen(df, "x", to=10)  # share=1.0 default
        assert list(out["x"]) == [0.0, 0.0, 0.0, 0.0]


def test_sync_datasets_keeps_dataset_named_df():
    """Web-load binder datasett med alias 'df' (make_active=False): synken må
    ikke klobre navnet med None når ingen dataset er aktivt."""
    import pandas as pd
    from m2py import MicroInterpreter
    e = MicroInterpreter()
    frame = pd.DataFrame({"x": [1, 2, 3]})
    e.datasets["df"] = frame
    e.active_name = None
    g = {}
    e.sync_datasets_to_globals(g)
    assert g["df"] is frame
    assert g["active_df"] is None
    # og med et annet navn er 'df' fortsatt None som før
    e2 = MicroInterpreter()
    e2.datasets["helse"] = frame
    e2.active_name = None
    g2 = {}
    e2.sync_datasets_to_globals(g2)
    assert g2["df"] is None and g2["helse"] is frame
