"""Ytelses- og minnetester for Pyodide-kritiske kodestier (kodegjennomgang
juni 2026), pluss karakteriseringstester som låser semantikken før/etter
vektorisering:

1. reshape-to-panel: vektorisert (var iterrows med O(rader × tider × kolonner
   × stubber) indre løkker — hang nettleserfanen på store datasett).
2. Mockdata-RNG: _norway_*-funksjonene memoiseres — én md5+Generator per
   person totalt, ikke per importert variabel. Verdiene er bit-identiske.
3. cox: skal ikke forurense forskerens datasett med dummy-kolonner.
4. weibull: modellen har ingen kovariater, så alle radenes prediksjonskurver
   er identiske — prediker for én rad, ikke alle (100 × N-allokering).
5. boxplot: kopier bare kolonnene som trengs, ikke hele datasettet.
"""
import hashlib
import time

import numpy as np
import pandas as pd
import pytest

import m2py
from m2py import MicroInterpreter


def _interp(df, name="testdata"):
    it = MicroInterpreter(metadata_path=None)
    it.datasets[name] = df
    it.active_name = name
    return it


def _run(it, line):
    it._execute_instruction(it.parser.parse_line(line))
    return "\n".join(str(m) for m in it.output_log)


# ---------------------------------------------------------------------------
# 1. reshape-to-panel
# ---------------------------------------------------------------------------

def _wide_df(n=4):
    return pd.DataFrame({
        "unit_id": np.arange(1, n + 1),
        "kjonn": [1, 2, 1, 2][:n],
        "lonn2014": [100.0, 200.0, 300.0, 400.0][:n],
        "lonn2017": [110.0, 210.0, 310.0, 410.0][:n],
        "siv2014": [1, 2, 3, 4][:n],
        "siv2017": [5, 6, 7, 8][:n],
    })


class TestReshapeToPanelSemantics:
    """Karakterisering — skal holde både før og etter vektorisering."""

    def test_basic_long_format(self):
        it = _interp(_wide_df())
        _run(it, "reshape-to-panel lonn siv")
        res = it.datasets["testdata"]
        assert list(res.columns) == ["unit_id", "tid", "panel@date", "lonn", "siv", "kjonn"]
        assert len(res) == 8  # 4 enheter x 2 tider

    def test_row_order_unit_major_time_ascending(self):
        it = _interp(_wide_df())
        _run(it, "reshape-to-panel lonn siv")
        res = it.datasets["testdata"]
        assert [int(u) for u in res["unit_id"]] == [1, 1, 2, 2, 3, 3, 4, 4]
        assert list(res["tid"]) == ["2014", "2017"] * 4

    def test_values_and_fixed_columns(self):
        it = _interp(_wide_df())
        _run(it, "reshape-to-panel lonn siv")
        res = it.datasets["testdata"]
        r = res[(res["unit_id"] == 2) & (res["tid"] == "2017")].iloc[0]
        assert r["lonn"] == 210.0
        assert int(r["siv"]) == 6
        assert int(r["kjonn"]) == 2  # fast opplysning repeteres
        assert r["panel@date"] == "2017"

    def test_missing_time_combo_gives_nan(self):
        # annen-prefikset finnes bare for 2014 -> NaN for 2017
        df = _wide_df()
        df["annen2014"] = [9.0, 8.0, 7.0, 6.0]
        it = _interp(df)
        _run(it, "reshape-to-panel lonn annen")
        res = it.datasets["testdata"]
        r17 = res[res["tid"] == "2017"]
        assert r17["annen"].isna().all()
        r14 = res[(res["unit_id"] == 1) & (res["tid"] == "2014")].iloc[0]
        assert r14["annen"] == 9.0


class TestReshapeToPanelPerformance:
    def test_50k_rows_under_half_second(self):
        n = 50_000
        rng = np.random.default_rng(0)
        df = pd.DataFrame({
            "unit_id": np.arange(n),
            "kjonn": rng.integers(1, 3, n),
            "lonn2014": rng.normal(5e5, 5e4, n),
            "lonn2017": rng.normal(5e5, 5e4, n),
            "lonn2020": rng.normal(5e5, 5e4, n),
            "siv2014": rng.integers(1, 5, n),
            "siv2017": rng.integers(1, 5, n),
            "siv2020": rng.integers(1, 5, n),
        })
        it = _interp(df)
        t0 = time.perf_counter()
        _run(it, "reshape-to-panel lonn siv")
        elapsed = time.perf_counter() - t0
        res = it.datasets["testdata"]
        assert res.shape == (150_000, 6)
        assert elapsed < 0.5, f"reshape-to-panel tok {elapsed:.2f}s for 50k rader"


# ---------------------------------------------------------------------------
# 2. Mockdata-RNG-memoisering
# ---------------------------------------------------------------------------

class TestMockdataRngMemoization:
    def test_latent_z_matches_md5_formula(self):
        # Verdiene skal være bit-identiske med den opprinnelige formelen
        for uid in (1, 42, 99999):
            h = hashlib.md5(f"norway_latent_v1:{uid}".encode()).digest()
            u1 = max(1e-12, min(1 - 1e-12, int.from_bytes(h[:4], "big") / 2**32))
            u2 = max(1e-12, min(1 - 1e-12, int.from_bytes(h[4:8], "big") / 2**32))
            expected = float(np.sqrt(-2 * np.log(u1)) * np.cos(2 * np.pi * u2))
            assert m2py._norway_latent_z(uid) == expected

    def test_deterministic_per_uid(self):
        assert m2py._norway_synth_kjonn_from_uid(7) == m2py._norway_synth_kjonn_from_uid(7)
        assert m2py._norway_demo_birth_year_from_uid(7) == m2py._norway_demo_birth_year_from_uid(7)

    def test_functions_are_memoized(self):
        # Gjentatte kall (typisk: hver nye import av en variabel) skal være
        # cache-oppslag, ikke nye md5+Generator-konstruksjoner per rad.
        uids = range(1000, 2000)
        for f in (
            m2py._norway_latent_z,
            m2py._norway_synth_kjonn_from_uid,
            m2py._norway_demo_birth_year_from_uid,
            m2py._norway_synth_age_from_uid,
        ):
            assert hasattr(f, "cache_info"), f"{f.__name__} er ikke memoisert"
            for u in uids:
                f(u)
            before = f.cache_info().hits
            for u in uids:
                f(u)
            assert f.cache_info().hits >= before + len(uids)


# ---------------------------------------------------------------------------
# 3-5. Overlevelse og plott: minne
# ---------------------------------------------------------------------------

def _surv_df(n=300, seed=5):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "event": rng.integers(0, 2, n),
        "tid": rng.integers(1, 120, n).astype(float),
        "region": rng.integers(1, 4, n),
        "ekstra": rng.normal(0, 1, n),
    })


class TestSurvivalMemory:
    def test_cox_does_not_mutate_dataset(self):
        df = _surv_df()
        it = _interp(df)
        cols_before = list(df.columns)
        out = _run(it, "cox event tid i.region")
        assert "FEIL" not in out
        assert list(it.datasets["testdata"].columns) == cols_before

    def test_weibull_predicts_single_curve_not_per_row(self, monkeypatch):
        import lifelines

        calls = {}
        orig = lifelines.WeibullAFTFitter.predict_survival_function

        def spy(self, X, *a, **k):
            calls["n_rows"] = len(X)
            return orig(self, X, *a, **k)

        monkeypatch.setattr(lifelines.WeibullAFTFitter, "predict_survival_function", spy)
        it = _interp(_surv_df())
        out = _run(it, "weibull event tid")
        assert "FEIL" not in out
        assert calls.get("n_rows") == 1


class TestBoxplotMemory:
    def test_boxplot_copies_only_needed_columns(self, monkeypatch):
        import plotly.express as px

        calls = {}
        orig = px.box

        def spy(data, *a, **k):
            calls["n_cols"] = data.shape[1]
            return orig(data, *a, **k)

        monkeypatch.setattr(px, "box", spy)
        df = _surv_df()
        it = _interp(df)
        _run(it, "boxplot ekstra, over(region)")
        assert calls.get("n_cols") == 2  # over_var + var, ikke hele datasettet
