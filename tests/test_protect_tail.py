"""Regression tests for the remaining medium/low findings in the
2026-07-07 protect.py review (docs/REVIEW_2026-07-07.md, section 2):
P3, P5, P6, P7, S4, S6, S7, S9, S10, S11, A1, A2, A3, A4, A5.

P1/P2/P4/S1/S2/S3/S5/S8 were already fixed before this pass and are
covered by tests/test_regressions.py — not duplicated here.
"""
import numpy as np
import pandas as pd
import pytest

import protect


# ============================================================================
# P3 — microaggregation: trailing remainder merged into last full group
# ============================================================================


class TestMicroaggregationRemainderMerged:
    def test_trailing_remainder_merged_into_last_group(self):
        # 7 ascending values, k=3 -> full groups [1,2,3],[4,5,6] and a
        # trailing remainder of 1 holding the LARGEST value (100). That
        # remainder must be folded into the last full group, not replaced
        # by its own (unchanged) mean.
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 100.0]})
        out = protect.noise(df, "x", method="group_mean", scale=3)
        assert 100.0 not in out["x"].values
        assert out["x"].iloc[0:3].nunique() == 1
        assert out["x"].iloc[0] == pytest.approx((1 + 2 + 3) / 3)
        # last (merged) group covers rows 3..6 inclusive
        assert out["x"].iloc[3:7].nunique() == 1
        assert out["x"].iloc[-1] == pytest.approx((4 + 5 + 6 + 100) / 4)

    def test_exact_multiple_of_k_is_unaffected(self):
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
        out = protect.noise(df, "x", method="group_mean", scale=3)
        assert out["x"].iloc[0:3].nunique() == 1
        assert out["x"].iloc[3:6].nunique() == 1
        assert out["x"].iloc[0] == pytest.approx(2.0)
        assert out["x"].iloc[3] == pytest.approx(5.0)

    def test_fewer_rows_than_k_still_forms_one_group(self):
        df = pd.DataFrame({"x": [1.0, 2.0]})
        out = protect.noise(df, "x", method="group_mean", scale=5)
        assert out["x"].nunique() == 1
        assert out["x"].iloc[0] == pytest.approx(1.5)


# ============================================================================
# P5 — insert() decoy IDs blend into the real ID format
# ============================================================================


class TestInsertDecoyIdsBlendIn:
    def _numeric_panel(self, n_units=20):
        pid = [f"PT{i:04d}" for i in range(n_units)]
        return pd.DataFrame({"pid": pid, "x": range(n_units)})

    def test_row_level_ids_continue_numeric_range_not_decoy_prefixed(self):
        df = self._numeric_panel()
        out = protect.insert(df, n=5, unit_id="pid", random_state=0)
        new_ids = set(out["pid"].iloc[len(df):])
        assert len(new_ids) == 5
        assert new_ids.isdisjoint(set(df["pid"]))
        assert not any(str(v).startswith("DECOY") for v in new_ids)
        assert all(v.startswith("PT") and int(v[2:]) >= len(df) for v in new_ids)

    def test_unit_level_new_pids_not_decoy_prefixed(self):
        df = pd.DataFrame({
            "pid": [f"PT{i:04d}" for i in range(20) for _ in range(2)],
            "visit": list(range(2)) * 20,
        })
        out = protect.insert(df, n=3, level="unit", unit_id="pid", random_state=0)
        new_pids = set(out["pid"]) - set(df["pid"])
        assert len(new_pids) == 3
        assert not any(str(v).startswith("DECOY") for v in new_pids)

    def test_insert_warns_with_decoy_count_not_which_rows(self):
        df = self._numeric_panel()
        with pytest.warns(UserWarning, match="added 5 decoy"):
            protect.insert(df, n=5, unit_id="pid", random_state=0)

    def test_alpha_ids_fallback_still_not_decoy_prefixed(self):
        df = pd.DataFrame({"pid": list("ABCDEFGHIJ"), "x": range(10)})
        out = protect.insert(df, n=2, unit_id="pid", random_state=0)
        new_ids = set(out["pid"]) - set(df["pid"])
        assert len(new_ids) == 2
        assert new_ids.isdisjoint(set(df["pid"]))
        assert not any(str(v).startswith("DECOY") for v in new_ids)


# ============================================================================
# P6 — HIPAA Safe Harbor ZIP rule: honest population-vs-heuristic labeling
# ============================================================================


class TestSafeHarborZipHonestLogging:
    def _panel(self):
        zips = ["00301"] * 3 + ["00501"] * 30 + [f"9000{i}" for i in range(17)]
        return pd.DataFrame({
            "pid": [f"P{i}" for i in range(len(zips))],
            "zip": zips,
            "dob": pd.Timestamp("1990-01-01"),
        })

    def test_default_is_labeled_heuristic_not_hipaa_compliance(self):
        df = self._panel()
        out, log = protect.profile(df, "safe_harbor", zip_col="zip")
        text = log.to_text()
        assert "HEURISTIC" in text
        assert "NOT the HIPAA population rule" in text

    def test_population_mapping_applies_the_true_rule(self):
        df = self._panel()
        zip_population = {"003": 25_000, "005": 5_000, "900": 1}
        out, log = protect.profile(
            df, "safe_harbor", zip_col="zip", zip_population=zip_population,
        )
        text = log.to_text()
        assert "164.514" in text
        assert (out.loc[df["zip"].str.startswith("003"), "zip"] == "003").all()
        assert (out.loc[df["zip"].str.startswith("005"), "zip"] == "***").all()
        assert (out.loc[df["zip"].str.startswith("9000"), "zip"] == "***").all()


# ============================================================================
# P7 — jitter 'auto' scale is SD-based (meaningful), not 1%-of-range (cosmetic)
# ============================================================================


class TestJitterAutoScaleIsSdBased:
    def test_resolve_jitter_scale_is_005_times_sd(self):
        s = pd.Series(np.arange(100, dtype=float))
        scale = protect._resolve_jitter_scale(s, "auto", is_date=False)
        assert scale == pytest.approx(0.05 * s.std())

    def test_jitter_auto_bounded_by_sd_scale(self):
        df = pd.DataFrame({"x": np.arange(100, dtype=float)})
        sd = df["x"].std()
        out = protect.jitter(df, "x", random_state=7)
        diffs = (out["x"] - df["x"]).abs()
        assert diffs.max() <= 0.05 * sd + 1e-9
        assert diffs.max() > 0

    def test_jitter_auto_warns_stating_method_and_magnitude(self):
        df = pd.DataFrame({"x": np.arange(50, dtype=float)})
        with pytest.warns(UserWarning, match="magnitude"):
            protect.jitter(df, "x", random_state=3)


# ============================================================================
# S4 — l-diversity/t-closeness use the same unit-level denominator as k
# ============================================================================


class TestRiskLDiversityUnitLevelConsistent:
    def _df(self):
        # Each unit's rows vary in the sensitive column across visits, but
        # the quasi-id (sex) is unit-invariant.
        return pd.DataFrame({
            "pid": ["A", "A", "A", "B", "B", "B"],
            "sex": ["M", "M", "M", "F", "F", "F"],
            "icd": ["I10", "E11", "J45", "I10", "E11", "J45"],
        })

    def test_unit_level_l_diversity_uses_one_row_per_unit(self):
        df = self._df()
        report = protect.risk(df, quasi_ids=["sex"], sensitive=["icd"], unit_id="pid")
        # k-anonymity denominator: 2 units, each its own class of size 1.
        assert report.k_min == 1
        assert report.distinct_combos == 2
        # l-diversity must use the SAME 1-row-per-unit population: each
        # unit contributes exactly one (first) icd value, so within-class
        # diversity is minimal (l=1), not inflated by counting all 3
        # visits' worth of distinct icd codes per unit.
        assert report.l_min == pytest.approx(1.0)
        assert report.l_median == pytest.approx(1.0)

    def test_row_level_l_diversity_unaffected_when_no_unit_id(self):
        df = self._df()
        report = protect.risk(df, quasi_ids=["sex"], sensitive=["icd"])
        # Without unit_id, l-diversity is computed on raw rows: each sex
        # class spans all 3 visits with 3 distinct icd codes -> l=3.
        assert report.l_min == pytest.approx(3.0)


# ============================================================================
# S6 — bin(labels="range") produces documented "lo-hi" labels; NaN stays NaN
# ============================================================================


class TestBinRangeLabelsAndNaN:
    def test_range_labels_are_lo_hi_not_pandas_interval_repr(self):
        df = pd.DataFrame({"x": [0, 5, 10, 15, 20, 25]})
        out = protect.bin(df, "x", bins=[0, 10, 20, 30], method="manual", labels="range")
        labels = set(out["x"].unique())
        assert labels == {"0-10", "10-20", "20-30"}
        assert not any("(" in l or "]" in l for l in labels)

    def test_missing_value_stays_missing_not_the_string_nan(self):
        df = pd.DataFrame({"x": [1.0, 5.0, np.nan, 15.0]})
        out = protect.bin(df, "x", bins=[0, 10, 20], method="manual", labels="range")
        assert out["x"].isna().sum() == 1
        assert pd.isna(out.loc[2, "x"])
        assert out.loc[0, "x"] == "0-10"
        assert out.loc[3, "x"] == "10-20"

    def test_min_count_merge_path_still_uses_lo_hi_labels(self):
        rng = np.random.default_rng(0)
        df = pd.DataFrame({"x": rng.uniform(0, 100, 200)})
        out = protect.bin(df, "x", bins=20, method="quantile", min_count=20, labels="range")
        for lbl in out["x"].dropna().unique():
            assert "-" in lbl
            assert "(" not in lbl and "]" not in lbl


# ============================================================================
# S7 — year/month/diff propagate NaT per row instead of corrupting/crashing
# ============================================================================


class TestDateVerbsPropagateMissingPerRow:
    def _df(self):
        return pd.DataFrame({
            "d": pd.to_datetime(["2020-05-15", None, "2021-08-20"]),
            "pid": ["A", "B", "C"],
        })

    def test_year_plain_int_with_one_nat(self):
        out = protect.year(self._df(), "d")
        assert out["d"].iloc[0] == 2020
        assert pd.isna(out["d"].iloc[1])
        assert out["d"].iloc[2] == 2021

    def test_year_as_date_with_one_nat(self):
        out = protect.year(self._df(), "d", as_date=True)
        assert out["d"].iloc[0] == pd.Timestamp("2020-01-01")
        assert pd.isna(out["d"].iloc[1])
        assert out["d"].iloc[2] == pd.Timestamp("2021-01-01")

    def test_year_bin_with_one_nat(self):
        out = protect.year(self._df(), "d", bin=5)
        assert out["d"].iloc[0] == "2020-2024"
        assert pd.isna(out["d"].iloc[1])
        assert out["d"].iloc[2] == "2020-2024"

    def test_month_string_with_one_nat_other_rows_stay_clean(self):
        out = protect.month(self._df(), "d")
        assert out["d"].iloc[0] == "2020-05"
        assert pd.isna(out["d"].iloc[1])
        assert out["d"].iloc[2] == "2021-08"
        # Regression guard: valid rows must not be corrupted into the
        # '2020.0-5.0' form that appeared once ANY row was NaT.
        assert "." not in out["d"].iloc[0]
        assert "." not in out["d"].iloc[2]

    def test_month_bin_with_one_nat(self):
        out = protect.month(self._df(), "d", bin=3)
        assert pd.isna(out["d"].iloc[1])
        assert "." not in out["d"].iloc[0]
        assert "." not in out["d"].iloc[2]

    def test_diff_does_not_crash_on_nat(self):
        out = protect.diff(self._df(), "d", ref="min")
        assert out["d"].iloc[0] == 0
        assert pd.isna(out["d"].iloc[1])
        assert out["d"].iloc[2] > 0

    def test_diff_keep_order_not_falsely_triggered_by_nat(self):
        df = pd.DataFrame({
            "pid": ["A", "A", "A"],
            "d": pd.to_datetime(["2020-01-01", None, "2020-03-01"]),
        })
        out = protect.diff(df, "d", ref="first_per_unit", unit_id="pid")
        assert out["d"].iloc[0] == 0
        assert pd.isna(out["d"].iloc[1])
        assert out["d"].iloc[2] == 60


# ============================================================================
# S9 — shorten() keeps NaN as NaN (no premature astype(str))
# ============================================================================


class TestShortenPreservesNaN:
    def test_nan_stays_nan_not_truncated_to_n(self):
        df = pd.DataFrame({"icd": ["I10.9", None, "E11.2"]})
        out = protect.shorten(df, "icd", sep=".")
        assert pd.isna(out["icd"].iloc[1])
        assert out["icd"].iloc[0] == "I10"
        assert out["icd"].iloc[2] == "E11"

    def test_nan_stays_nan_through_min_count_cascade(self):
        df = pd.DataFrame({"icd": ["A1", "A1", "A2", None, None, None]})
        out = protect.shorten(df, "icd", keep=2, min_count=3)
        assert out["icd"].isna().sum() == 3


# ============================================================================
# S10 — collapse() keeps NaN as NaN (does not recode to other_label)
# ============================================================================


class TestCollapsePreservesNaN:
    def test_rare_below_keeps_nan_as_nan(self):
        df = pd.DataFrame({"c": ["X"] * 10 + ["Y"] + [None] * 3})
        out = protect.collapse(df, "c", rare_below=5)
        assert out["c"].isna().sum() == 3
        assert (out["c"] == "Other").sum() == 1
        assert (out["c"] == "X").sum() == 10

    def test_keep_top_keeps_nan_as_nan(self):
        df = pd.DataFrame({"c": ["X"] * 5 + ["Y"] * 3 + ["Z"] * 2 + [None] * 4})
        out = protect.collapse(df, "c", keep_top=1)
        assert out["c"].isna().sum() == 4

    def test_health_research_profile_knock_on_nan_stays_own_risk_class(self):
        df = pd.DataFrame({
            "pid": [f"P{i}" for i in range(12)],
            "icd": ["I10"] * 10 + [None, None],
        })
        out, log = protect.profile(
            df, "health_research", unit_id="pid", sensitive_cols=["icd"], k=5,
        )
        assert out["icd"].isna().sum() == 2
        report = protect.risk(out, quasi_ids=["icd"], unit_id="pid")
        # NaN forms its own equivalence class of size 2 (< k) — correctly
        # flagged as risky, not silently merged into "Other".
        assert report.k_min <= 2


# ============================================================================
# S11 — noise() clip only touches rows actually selected by `share`
# ============================================================================


class TestNoiseClipOnlyPerturbedRows:
    def test_share_zero_leaves_extreme_values_unclipped(self):
        df = pd.DataFrame({"x": [1000.0, -1000.0] + [5.0] * 8})
        out = protect.noise(df, "x", scale=1.0, share=0.0, clip=(0, 100), random_state=0)
        assert out["x"].iloc[0] == 1000.0
        assert out["x"].iloc[1] == -1000.0

    def test_partial_share_clips_only_selected_rows(self):
        df = pd.DataFrame({"x": [1000.0] * 20})
        out = protect.noise(df, "x", scale=0.01, share=0.3, clip=(0, 10), random_state=0)
        changed = out["x"] != df["x"]
        assert changed.sum() > 0
        # Rows NOT selected for perturbation must be untouched by clip.
        assert (out.loc[~changed, "x"] == 1000.0).all()
        # Rows that WERE perturbed get clipped down (1000 -> way above 10).
        assert (out.loc[changed, "x"] <= 10).all()


# ============================================================================
# A1 — uniform inert-parameter policy (share/unit_id) across verbs
# ============================================================================


class TestInertParameterPolicy:
    def test_winsorize_rejects_nondefault_share(self):
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
        with pytest.raises(ValueError, match="share"):
            protect.winsorize(df, "x", share=0.5)

    def test_winsorize_warns_on_unit_id(self):
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "pid": ["A", "B", "C"]})
        with pytest.warns(UserWarning, match="unit_id"):
            protect.winsorize(df, "x", unit_id="pid")

    def test_bin_rejects_nondefault_share(self):
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0]})
        with pytest.raises(ValueError, match="share"):
            protect.bin(df, "x", bins=2, share=0.5)

    def test_bin_warns_on_unit_id(self):
        df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0], "pid": ["A", "B", "C", "D"]})
        with pytest.warns(UserWarning, match="unit_id"):
            protect.bin(df, "x", bins=2, unit_id="pid")

    def test_swap_shuffle_rejects_nondefault_share(self):
        df = pd.DataFrame({"x": [1, 2, 3, 4, 5]})
        with pytest.raises(ValueError, match="share"):
            protect.swap(df, "x", method="shuffle", share=0.9, random_state=0)

    def test_swap_shuffle_accepts_its_own_default_share(self):
        df = pd.DataFrame({"x": [1, 2, 3, 4, 5]})
        out = protect.swap(df, "x", method="shuffle", random_state=0)
        assert sorted(out["x"]) == sorted(df["x"])

    def test_swap_pram_rejects_nondefault_share(self):
        df = pd.DataFrame({"x": ["a", "b", "a", "b"]})
        transition = {"a": {"a": 0.5, "b": 0.5}, "b": {"a": 0.5, "b": 0.5}}
        with pytest.raises(ValueError, match="share"):
            protect.swap(df, "x", method="pram", share=1.0,
                         transition=transition, random_state=0)


# ============================================================================
# A2 — risk() accepts quasi-IDs positionally (fixes scrub-risk(VAR1, VAR2))
# ============================================================================


class TestRiskAcceptsPositionalColumns:
    def test_positional_columns_used_as_quasi_ids(self):
        df = pd.DataFrame({"sex": ["M", "F", "M", "F"], "zip": ["1", "1", "2", "2"]})
        report = protect.risk(df, ["sex", "zip"])
        assert report.distinct_combos == 4

    def test_positional_and_keyword_quasi_ids_conflict_raises(self):
        df = pd.DataFrame({"sex": ["M", "F"]})
        with pytest.raises(ValueError, match="quasi_ids"):
            protect.risk(df, ["sex"], quasi_ids=["sex"])

    def test_missing_quasi_ids_raises_clear_error(self):
        df = pd.DataFrame({"sex": ["M", "F"]})
        with pytest.raises(ValueError, match="quasi"):
            protect.risk(df)


# ============================================================================
# A3 — differing share defaults (noise/jitter=1.0, swap=0.05, insert=0.01)
#      are documented in each verb's docstring
# ============================================================================


class TestShareDefaultsDocumented:
    @pytest.mark.parametrize("fn,expected_default", [
        (protect.noise, "1.0"),
        (protect.jitter, "1.0"),
        (protect.swap, "0.05"),
        (protect.insert, "0.01"),
    ])
    def test_docstring_mentions_share_default(self, fn, expected_default):
        doc = fn.__doc__ or ""
        assert "share" in doc
        assert expected_default in doc


# ============================================================================
# A4 — profile('health_research') wires up quasi_ids instead of ignoring it
# ============================================================================


class TestHealthResearchProfileWiresQuasiIds:
    def test_quasi_ids_generalized_to_reach_target_k(self):
        df = pd.DataFrame({
            "pid": [f"P{i:02d}" for i in range(20)],
            "zip": [f"Z{i:02d}" for i in range(20)],  # all unique -> k=1
        })
        out, log = protect.profile(
            df, "health_research", unit_id="pid", quasi_ids=["zip"], k=5,
        )
        report = protect.risk(out, quasi_ids=["zip"], unit_id="pid")
        assert report.k_min >= 5
        assert len(log) > 0


# ============================================================================
# A5 — discarded pseudonymize keys get a loud note in the log
# ============================================================================


class TestPseudonymizeKeyDiscardNoted:
    def test_protect_recipe_logs_key_discarded_note(self):
        df = pd.DataFrame({"pid": ["A", "B", "C"], "x": [1, 2, 3]})
        out, log = protect.protect(
            df, recipe={"pid": {"pseudonymize": {"method": "random", "random_state": 1}}},
        )
        assert isinstance(out, pd.DataFrame)
        assert isinstance(log, protect.TransformLog)
        text = log.to_text()
        assert "not recoverable" in text.lower() or "discarded" in text.lower()
        assert "irreversible" in text.lower() or "no other way" in text.lower()

    def test_safe_harbor_profile_logs_key_discarded_note(self):
        df = pd.DataFrame({"pid": ["A", "B", "C"], "dob": pd.Timestamp("1990-01-01")})
        out, log = protect.profile(df, "safe_harbor", id_cols=["pid"])
        text = log.to_text()
        assert "discard" in text.lower() or "irreversible" in text.lower()
