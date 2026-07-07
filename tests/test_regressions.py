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
# B3 (kodegjennomgang 2026-07-07): label-tekst-betingelser mot null-paddede
# koder. Kodelistenøkkelen '0301' ble konvertert til int 301 og oppslaget
# prøvde bare '301' som strengkandidat — `keep if bosted == 'Oslo'` beholdt
# 0 rader når dataene holder '0301'-strenger.
# ---------------------------------------------------------------------------

class TestLabelConditionMatchesZeroPaddedCodes:
    @pytest.fixture
    def interp(self):
        it = MicroInterpreter(metadata_path=None)
        lm = it.label_manager
        # Null-paddede strengnøkler slik variable_metadata.json leverer dem
        lm.catalog["KOMM"] = {"labels": {"0301": "Oslo", "1103": "Stavanger"}}
        lm._catalog_by_short["KOMM"] = lm.catalog["KOMM"]
        lm.register_var_alias("bosted", "db/KOMM")
        return it

    @pytest.fixture
    def df(self):
        return pd.DataFrame({"bosted": ["0301", "0301", "1103"]})

    def test_label_eq_matches_padded_codes(self, interp, df):
        mask = interp._eval_condition_mask(df, "bosted == 'Oslo'")
        assert mask.tolist() == [True, True, False]

    def test_label_eq_matches_unpadded_codes(self, interp, df):
        # Ikke-paddet kode ('1103') skal fortsatt matche via int-nøkkelen
        mask = interp._eval_condition_mask(df, "bosted == 'Stavanger'")
        assert mask.tolist() == [False, False, True]

    def test_label_neq_is_complement(self, interp, df):
        mask = interp._eval_condition_mask(df, "bosted != 'Oslo'")
        assert mask.tolist() == [False, False, True]

    def test_keep_if_label_keeps_rows(self, interp, df):
        interp.datasets["d"] = df
        interp.active_name = "d"
        interp._execute_instruction(interp.parser.parse_line("keep if bosted == 'Oslo'"))
        assert interp.datasets["d"]["bosted"].tolist() == ["0301", "0301"]

    def test_int_coded_column_with_padded_labels(self, interp):
        # Numerisk kolonne (301) med padded kodeliste skal også matche label
        df = pd.DataFrame({"bosted": [301, 301, 1103]})
        mask = interp._eval_condition_mask(df, "bosted == 'Oslo'")
        assert mask.tolist() == [True, True, False]


# ---------------------------------------------------------------------------
# B5 (kodegjennomgang 2026-07-07): recode konverterte HELE kolonnen via
# pd.to_numeric + str(int(x))-rundtur — verdier som ingen regel matchet ble
# korruptert: '0301' → '301', 'XXXX' → missing, '01.110' → '1'.
# ---------------------------------------------------------------------------

class TestRecodePassThrough:
    def _interp(self, df):
        it = MicroInterpreter(metadata_path=None)
        it.datasets["d"] = df
        it.active_name = "d"
        return it

    def test_unmatched_string_values_pass_through_byte_identical(self):
        it = self._interp(pd.DataFrame(
            {"bosted": ["0301", "4601", "5001", "XXXX", "01.110", None]}
        ))
        it._execute_instruction(it.parser.parse_line("recode bosted (4601 = 1)"))
        vals = it.datasets["d"]["bosted"].tolist()
        assert vals[0] == "0301"      # ikke '301'
        assert vals[1] == "1"         # matchet regel → omkodet
        assert vals[2] == "5001"      # urørt
        assert vals[3] == "XXXX"      # ikke NaN
        assert vals[4] == "01.110"    # ikke '1'
        assert pd.isna(vals[5])       # ekte missing forblir missing

    def test_missing_rule_does_not_hit_non_numeric_strings(self):
        # 'XXXX' er IKKE missing — (missing = 9) skal ikke treffe den
        it = self._interp(pd.DataFrame({"x": ["1", "XXXX", None]}))
        it._execute_instruction(it.parser.parse_line("recode x (missing = 9)"))
        vals = it.datasets["d"]["x"].tolist()
        assert vals[0] == "1"
        assert vals[1] == "XXXX"
        assert vals[2] == "9"

    def test_matched_string_values_stay_strings(self):
        # Eksisterende garanti: omkodede verdier på strengkolonner blir
        # strenger (parstatus == '1' skal virke etter recode)
        it = self._interp(pd.DataFrame({"x": ["1", "2", "3"]}))
        it._execute_instruction(it.parser.parse_line("recode x (2/3 = 2)"))
        assert it.datasets["d"]["x"].tolist() == ["1", "2", "2"]

    def test_numeric_recode_unchanged(self):
        it = self._interp(pd.DataFrame({"x": [1.0, 2.0, 7.0, np.nan]}))
        it._execute_instruction(it.parser.parse_line("recode x (1/5 = 2)"))
        vals = it.datasets["d"]["x"].tolist()
        assert vals[0] == 2 and vals[1] == 2 and vals[2] == 7
        assert pd.isna(vals[3])


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


# ---------------------------------------------------------------------------
# REVIEW_2026-07-07 §2 (SDC verbs, protect.py) — silent no-ops and mislabels
# found by execution-verified code review.
# ---------------------------------------------------------------------------

class TestSwapSmallDataGuaranteesPairs:
    """P1: n_swap = int(round(n * share)) rounded to 0 pairs for default
    share=0.05 on small data — swap silently changed nothing while still
    being reported as applied."""

    def test_row_swap_changes_something_on_small_data(self):
        df = pd.DataFrame({"x": np.arange(20.0)})
        out = protect.swap(df, "x", method="random", level="row", random_state=0)
        assert not out["x"].equals(df["x"])

    def test_unit_swap_changes_something_on_small_data(self):
        # 10 units x 2 rows; default share=0.05 previously rounded to 0 pairs.
        df = pd.DataFrame({
            "id": np.repeat(np.arange(10), 2),
            "x": np.arange(20.0),
        })
        out = protect.swap(df, "x", method="random", level="unit",
                            unit_id="id", random_state=0)
        assert not out["x"].equals(df["x"])

    def test_share_zero_is_still_a_true_no_op(self):
        # share=0 is a deliberate request for no perturbation, not a bug.
        df = pd.DataFrame({"x": np.arange(20.0)})
        out = protect.swap(df, "x", method="random", level="row", share=0.0,
                            random_state=0)
        assert out["x"].equals(df["x"])


class TestNoiseGroupMeanRejectsFractionalScale:
    """P2: k = int(scale) silently truncated fractional scale (e.g. the
    natural-looking scale=0.05) to k=0, then k<2 returned the column
    unchanged while noise() still reported success."""

    def test_fractional_scale_raises(self):
        df = pd.DataFrame({"x": np.arange(20.0)})
        with pytest.raises(ValueError, match="group_mean"):
            protect.noise(df, "x", method="group_mean", scale=0.05)

    def test_scale_one_raises(self):
        df = pd.DataFrame({"x": np.arange(20.0)})
        with pytest.raises(ValueError, match="integer"):
            protect.noise(df, "x", method="group_mean", scale=1)

    def test_integer_scale_still_works(self):
        df = pd.DataFrame({"x": np.arange(20.0)})
        out = protect.noise(df, "x", method="group_mean", scale=4)
        assert not out["x"].equals(df["x"])


class TestRiskCountsMissingQuasiIds:
    """P4: groupby(dropna=True) made a unique record with a NaN quasi-ID
    invisible to risk() — overstating safety (k_min/units_at_risk missed
    the riskiest record)."""

    def test_nan_quasi_id_forms_its_own_equivalence_class(self):
        df = pd.DataFrame({"q": [1, 1, 1, 2, 2, np.nan]})
        rep = protect.risk(df, quasi_ids=["q"])
        assert rep.distinct_combos == 3  # {1, 2, NaN}
        assert rep.units_at_risk >= 1

    def test_k_min_reflects_the_nan_singleton(self):
        df = pd.DataFrame({"q": [1, 1, 1, 2, 2, np.nan]})
        rep = protect.risk(df, quasi_ids=["q"])
        assert rep.k_min == 1


class TestGroupedVerbsPreserveNanGroupRows:
    """S1: winsorize(by=), collapse(by=), and noise(method='group_mean',
    by=) all did groupby(dropna=True) then assigned the grouped result back
    to the full column — rows whose `by` value was NaN came back as NaN
    even though they were never touched by any group computation."""

    def test_winsorize_by_nan_group_keeps_original_value(self):
        df = pd.DataFrame({
            "g": ["a", "a", "a", "b", "b", np.nan],
            "x": [1.0, 2.0, 300.0, 10.0, 20.0, 999.0],
        })
        out = protect.winsorize(df, "x", by="g", limits=(0.0, 0.5))
        assert out.loc[5, "x"] == 999.0

    def test_collapse_by_nan_group_keeps_original_value(self):
        df = pd.DataFrame({
            "g": ["a", "a", "b", "b", np.nan],
            "x": ["rare1", "common", "rare2", "common", "rareX"],
        })
        out = protect.collapse(df, "x", by="g", rare_below=2)
        assert out.loc[4, "x"] == "rareX"

    def test_noise_group_mean_by_nan_group_keeps_original_value(self):
        df = pd.DataFrame({
            "g": ["a", "a", "a", "a", np.nan],
            "x": [1.0, 2.0, 3.0, 4.0, 999.0],
        })
        out = protect.noise(df, "x", method="group_mean", scale=2, by="g")
        assert out.loc[4, "x"] == 999.0


class TestRiskKBelow5CountsRecords:
    """S3: k_below_5 counted equivalence CLASSES with size<5 but is
    rendered in describe() as 'records with k<5' — undercounting by
    roughly a factor of k."""

    def test_k_below_5_is_a_record_count_not_a_class_count(self):
        # classes: {1: k=1, 2: k=1, 3: k=3} -> 3 classes with k<5,
        # but 1 + 1 + 3 = 5 records fall in them.
        df = pd.DataFrame({"q": [1, 2, 3, 3, 3]})
        rep = protect.risk(df, quasi_ids=["q"])
        assert rep.k_below_5 == 5


class TestSuppressRangesBelowLowest:
    """S5: values below the lowest range were mislabeled '>{max}' (the
    fall-through label) instead of '<{min}'."""

    def test_value_below_lowest_range_labeled_lt_min(self):
        s = pd.Series({"a": 0.0, "b": 3.0, "c": 8.0})
        out = protect.suppress(s, ranges=[(1, 5), (6, 10)])
        assert out["a"] == "<1"
        assert out["b"] == "1-5"
        assert out["c"] == "6-10"

    def test_value_above_highest_range_still_labeled_gt_max(self):
        s = pd.Series({"a": 99.0})
        out = protect.suppress(s, ranges=[(1, 5), (6, 10)])
        assert out["a"] == ">10"


class TestRiskEmptyDataFrame:
    """S8: int(eq_classes.min()) on an empty groupby raised a bare,
    confusing ValueError from a NaN-cast; give a clear one instead."""

    def test_empty_dataframe_raises_clear_error(self):
        df = pd.DataFrame({"q": pd.Series([], dtype=float)})
        with pytest.raises(ValueError, match="empty"):
            protect.risk(df, quasi_ids=["q"])


class TestSwapUnitExchangesFullSequence:
    """S2: swap(level='unit') took the FIRST row's value from each unit and
    broadcast it to every row of the other unit, annihilating within-unit
    variation instead of exchanging the two units' full record sequences."""

    def test_unit_values_are_exchanged_not_broadcast(self):
        df = pd.DataFrame({
            "id": [1, 1, 1, 2, 2, 2],
            "x": [100.0, 200.0, 300.0, 10.0, 20.0, 30.0],
        })
        out = protect.swap(df, "x", method="random", level="unit",
                            unit_id="id", share=1.0, random_state=0)
        got1 = sorted(out.loc[out["id"] == 1, "x"].tolist())
        got2 = sorted(out.loc[out["id"] == 2, "x"].tolist())
        # Whole sequences trade places -- not all rows collapsed onto one
        # broadcast value (the old bug would give got1 == got2 == [10]*3).
        assert got1 == [10.0, 20.0, 30.0]
        assert got2 == [100.0, 200.0, 300.0]

    def test_units_with_different_row_counts_are_not_paired(self):
        # A 3-row unit and a 2-row unit can't be exchanged without
        # truncating/padding, so they must be left unswapped -- which here
        # means nothing at all can change, and that must raise loudly
        # rather than silently reporting success.
        df = pd.DataFrame({
            "id": [1, 1, 1, 2, 2],
            "x": [1.0, 2.0, 3.0, 10.0, 20.0],
        })
        with pytest.raises(ValueError, match="no values were changed"):
            protect.swap(df, "x", method="random", level="unit",
                         unit_id="id", share=1.0, random_state=0)


class TestPerturbationNoOpRaises:
    """Cross-cutting: perturbation verbs must detect a 0-values-changed
    outcome and fail loudly rather than silently reporting success."""

    def test_noise_zero_scale_raises(self):
        df = pd.DataFrame({"x": np.arange(20.0)})
        with pytest.raises(ValueError, match="no values were changed"):
            protect.noise(df, "x", method="gaussian", scale=0.0, random_state=0)

    def test_swap_constant_column_raises(self):
        # Swapping identical values leaves the column bit-for-bit unchanged.
        df = pd.DataFrame({"x": [7.0] * 20})
        with pytest.raises(ValueError, match="no values were changed"):
            protect.swap(df, "x", method="random", level="row", random_state=0)


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


# ---------------------------------------------------------------------------
# B4 (kodegjennomgang 2026-07-07): `++`-strengkonkatenasjon i generate var
# ødelagt — `_process_pp_in_line` evaluerte kjeden på parse-tid med bare
# bindinger i scope, så kolonneuttrykk ble limt til ugyldig Python
# (`string(a)_string(b)` → SyntaxError). Linjen under er NØYAKTIG den
# workarounden feilmeldingene for collapse by()/merge on anbefaler.
# ---------------------------------------------------------------------------

class TestPlusPlusStringConcatInGenerate:
    def _interp(self, df):
        it = MicroInterpreter(metadata_path=None)
        it.datasets["d"] = df
        it.active_name = "d"
        return it

    def _run(self, it, *lines):
        # ++-prosessering skjer i MicroInterpreter._substitute_bindings, som
        # bare kjøres via run_script — ikke via parse_line direkte.
        it.run_script("\n".join(lines))
        return "\n".join(str(m) for m in it.output_log)

    def test_recommended_composite_key_line_works(self):
        it = self._interp(pd.DataFrame({"a": [1, 2], "b": [10, 20], "x": [1.0, 2.0]}))
        out = self._run(it, 'generate composite = string(a) ++ "_" ++ string(b)')
        assert "FEIL" not in out, out
        assert list(it.datasets["d"]["composite"]) == ["1_10", "2_20"]

    def test_composite_key_then_collapse_by_works(self):
        it = self._interp(pd.DataFrame({"a": [1, 1, 2], "b": [10, 10, 20], "x": [1.0, 3.0, 5.0]}))
        out = self._run(
            it,
            'generate composite = string(a) ++ "_" ++ string(b)',
            "collapse (mean) x, by(composite)",
        )
        assert "FEIL" not in out, out
        res = it.datasets["d"]
        assert sorted(res["composite"]) == ["1_10", "2_20"]
        assert sorted(res["x"]) == [2.0, 5.0]

    def test_single_quotes_variant_works(self):
        it = self._interp(pd.DataFrame({"a": [7], "b": [8]}))
        out = self._run(it, "generate composite = string(a) ++ '_' ++ string(b)")
        assert "FEIL" not in out, out
        assert list(it.datasets["d"]["composite"]) == ["7_8"]

    def test_binding_name_gluing_still_works(self):
        # Rene symbol-ledd skal fortsatt limes til navn (bindings-bruk):
        # `let år = 2020` + `generate kopi = siv_ ++ $år` refererer kolonnen
        # siv_2020 — ikke verdikonkat av en kolonne `siv_`.
        it = self._interp(pd.DataFrame({"siv_2020": [1.0, 2.0]}))
        out = self._run(
            it,
            "let år = 2020",
            "generate kopi = siv_ ++ $år",
        )
        assert "FEIL" not in out, out
        assert list(it.datasets["d"]["kopi"]) == [1.0, 2.0]

    def test_multi_token_chain_still_glues_names(self):
        # `barchart (mean) lønn++$år dagpenger++$år` (web_examples) — ++ limer
        # navn selv når leddet har prefiks-tokens. Skal IKKE tolkes som
        # verdikonkatenasjon selv om prefikset inneholder parenteser.
        it = MicroInterpreter(metadata_path=None)
        it.bindings["år"] = 2018
        line = it._substitute_bindings("barchart (mean) lønn++$år dagpenger++$år")
        assert line == "barchart (mean) lønn2018 dagpenger2018"

    def test_create_dataset_chain_still_glues(self):
        it = MicroInterpreter(metadata_path=None)
        it.bindings["år"] = 2018
        assert it._substitute_bindings("create-dataset nav++$år") == "create-dataset nav2018"


# ---------------------------------------------------------------------------
# B7 (kodegjennomgang 2026-07-07): collapse (percent) returnerte ~100 for
# hver gruppe (andel ikke-missing INNEN gruppen). Riktig semantikk er
# gruppens andel av totalen — prosentene skal summere til 100 over gruppene.
# ---------------------------------------------------------------------------

class TestCollapsePercentIsShareOfTotal:
    def test_percent_sums_to_100_across_groups(self):
        df = pd.DataFrame({"g": [1] * 3 + [2] * 7, "x": [1.0] * 10})
        res = StatsEngine().execute(
            "collapse", df,
            {"targets": [{"stat": "percent", "src": "x", "target": "pct"}]},
            {"by": "g"},
        )
        assert sorted(res["pct"]) == [pytest.approx(30.0), pytest.approx(70.0)]
        assert res["pct"].sum() == pytest.approx(100.0)

    def test_percent_counts_nonmissing_share(self):
        # Missing teller ikke: 3 av 10 ikke-missing i gruppe 1 => 30 %
        df = pd.DataFrame({
            "g": [1] * 3 + [2] * 8,
            "x": [1.0] * 3 + [2.0] * 7 + [np.nan],
        })
        res = StatsEngine().execute(
            "collapse", df,
            {"targets": [{"stat": "percent", "src": "x", "target": "pct"}]},
            {"by": "g"},
        )
        assert sorted(res["pct"]) == [pytest.approx(30.0), pytest.approx(70.0)]

    def test_percent_global_collapse_is_100(self):
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
        res = StatsEngine().execute(
            "collapse", df,
            {"targets": [{"stat": "percent", "src": "x", "target": "pct"}]},
            {},
        )
        assert float(res["pct"].iloc[0]) == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# B9 (kodegjennomgang 2026-07-07): rowconcat bakte inn literal 'nan' for
# missing (astype(str) FØR fillna). Missing skal bli tom streng.
# ---------------------------------------------------------------------------

class TestRowconcatMissingBecomesEmpty:
    def test_nan_becomes_empty_string(self):
        import functions
        a = pd.Series(["a", None, "c"])
        b = pd.Series([1.0, 2.0, np.nan])
        out = functions.rowconcat(a, "-", b)
        assert out.tolist() == ["a-1.0", "-2.0", "c-"]
        assert not out.str.contains("nan").any()

    def test_all_present_unchanged(self):
        import functions
        out = functions.rowconcat(pd.Series(["x", "y"]), "_", pd.Series(["1", "2"]))
        assert out.tolist() == ["x_1", "y_2"]


# ---------------------------------------------------------------------------
# B10 (kodegjennomgang 2026-07-07): _elementwise var død kode med invertert
# None-guard — skal være fjernet, ikke reparert.
# ---------------------------------------------------------------------------

def test_elementwise_helper_removed():
    import functions
    assert not hasattr(functions, "_elementwise")


# ---------------------------------------------------------------------------
# B11 (kodegjennomgang 2026-07-07): dupliserte collapse-mål —
# `collapse (mean) x (sd) x, by(g)` lot siste statistikk stille overskrive
# den første. Skal feile høyt (microdata.no-dokumentasjonen definerer ingen
# auto-suffiks-atferd).
# ---------------------------------------------------------------------------

class TestCollapseDuplicateTargetsErrorLoudly:
    def _df(self):
        return pd.DataFrame({"g": [1, 1, 2, 2], "x": [1.0, 3.0, 5.0, 7.0]})

    def test_duplicate_unnamed_targets_raise(self):
        with pytest.raises(ValueError, match="målnavnet"):
            StatsEngine().execute(
                "collapse", self._df(),
                {"targets": [
                    {"stat": "mean", "src": "x", "target": None},
                    {"stat": "sd", "src": "x", "target": None},
                ]},
                {"by": "g"},
            )

    def test_duplicate_explicit_targets_raise(self):
        with pytest.raises(ValueError, match="målnavnet"):
            StatsEngine().execute(
                "collapse", self._df(),
                {"targets": [
                    {"stat": "mean", "src": "x", "target": "s"},
                    {"stat": "sd", "src": "x", "target": "s"},
                ]},
                {"by": "g"},
            )

    def test_script_level_error_is_logged(self):
        it = MicroInterpreter(metadata_path=None)
        it.datasets["d"] = self._df()
        it.active_name = "d"
        it.run_script("collapse (mean) x (sd) x, by(g)")
        out = "\n".join(str(m) for m in it.output_log)
        assert "FEIL" in out and "målnavnet" in out

    def test_renamed_targets_still_work(self):
        res = StatsEngine().execute(
            "collapse", self._df(),
            {"targets": [
                {"stat": "mean", "src": "x", "target": None},
                {"stat": "sd", "src": "x", "target": "x_sd"},
            ]},
            {"by": "g"},
        )
        assert list(res.columns) == ["g", "x", "x_sd"]
        assert sorted(res["x"]) == [pytest.approx(2.0), pytest.approx(6.0)]


# ---------------------------------------------------------------------------
# B12 (kodegjennomgang 2026-07-07): de døde '<n> if <cond>'-regex-grenene i
# generate/replace er fjernet (parse_line splitter alltid ' if ' ut som egen
# betingelse). Verifiser at oppførselen via parseren er uendret.
# ---------------------------------------------------------------------------

class TestGenerateReplaceIfStillWork:
    def _interp(self):
        it = MicroInterpreter(metadata_path=None)
        it.datasets["d"] = pd.DataFrame({"y": [1, 2, 1, 3], "x": [0.0, 0.0, 0.0, 0.0]})
        it.active_name = "d"
        return it

    def test_generate_value_if_condition(self):
        it = self._interp()
        it.run_script("generate z = 1 if y == 1")
        z = it.datasets["d"]["z"]
        assert z.tolist()[0] == 1.0 and z.tolist()[2] == 1.0
        assert pd.isna(z.tolist()[1]) and pd.isna(z.tolist()[3])

    def test_replace_value_if_condition(self):
        it = self._interp()
        it.run_script("replace x = 9 if y == 1")
        assert it.datasets["d"]["x"].tolist() == [9.0, 0.0, 9.0, 0.0]

    def test_dead_branch_removed_from_source(self):
        src = inspect.getsource(m2py)
        assert r"^(\d+)\s+if\s+(.+)$" not in src
