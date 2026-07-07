"""Phase 3 — mock-data correctness & consistency.

Generated values must be deterministic per person and INDEPENDENT of how the
variable is imported. Previously the per-variable RNG seed was derived from the
output column name (the alias), so `import X as y` gave a person different
values than `import X` — and the dynamic generator diverged from the static
build, which seeds on the canonical short_name.
"""
import numpy as np
import pandas as pd
import pytest

import m2py
from m2py import MicroInterpreter


def _interp():
    return MicroInterpreter(metadata_path=None)


def _run(it, *lines):
    for line in lines:
        it._execute_instruction(it.parser.parse_line(line))
    return it


def _values_by_person(it, valcol):
    df = it.datasets[it.active_name]
    key = "PERSONID_1" if "PERSONID_1" in df.columns else "unit_id"
    return df.set_index(key)[valcol]


class TestAliasSeedConsistency:
    def test_alias_does_not_change_money_values(self):
        a = _run(_interp(), "create-dataset d", "import db/INNTEKT_WYRKINNT 2019-01-01")
        b = _run(_interp(), "create-dataset d",
                 "import db/INNTEKT_WYRKINNT 2019-01-01 as inntekt")
        va = _values_by_person(a, "INNTEKT_WYRKINNT")
        vb = _values_by_person(b, "inntekt").reindex(va.index)
        # Series.equals treats NaN == NaN as equal and requires matching dtype.
        assert va.equals(vb)

    def test_same_variable_different_dates_vary(self):
        # The alias-independence fix must NOT collapse time variation: the same
        # variable imported at two dates must still change for some persons
        # (otherwise transition/sankey diagrams degenerate).
        it = _run(_interp(), "create-dataset d",
                  "import db/SIVSTANDFDT_SIVSTAND 2010-01-01 as s10",
                  "import db/SIVSTANDFDT_SIVSTAND 2015-01-01 as s15")
        df = it.datasets[it.active_name]
        assert (df["s10"] != df["s15"]).any()


class TestNprConsistency:
    """NPR (helseregister) episodes must be internally consistent: diagnoses
    must respect the person's actual gender, and discharge can't precede
    admission regardless of import order."""

    def _npr(self, *cmds):
        return _run(MicroInterpreter(metadata_path=None), "create-dataset d", *cmds)

    def test_childbirth_diagnosis_only_for_females(self):
        # O80 (delivery) must never land on a person whose actual gender is male.
        it = self._npr("import ndb/HOVEDTILSTAND1")
        df = it.datasets[it.active_name]
        o80 = df[df["HOVEDTILSTAND1"] == "O80"]
        assert len(o80) > 0  # sanity: the demo produces some deliveries
        sexes = [m2py._norway_synth_kjonn_from_uid(int(u)) for u in o80["unit_id"]]
        assert all(s == 2 for s in sexes), "childbirth assigned to a male person"

    def test_discharge_not_before_admission_inndato_first(self):
        it = self._npr("import ndb/INNDATO", "import ndb/UTDATO")
        df = it.datasets[it.active_name]
        assert (df["UTDATO"] >= df["INNDATO"]).all()

    def test_discharge_not_before_admission_utdato_first(self):
        # Reverse import order must still hold (implicit INNDATO must match).
        it = self._npr("import ndb/UTDATO", "import ndb/INNDATO")
        df = it.datasets[it.active_name]
        assert (df["UTDATO"] >= df["INNDATO"]).all()


class TestSilentMetadataFallback:
    """A failed external-metadata load must surface a visible warning, not
    silently substitute demo distributions/labels."""

    def test_external_metadata_failure_warns(self):
        it = MicroInterpreter(metadata_path=None)
        eng = it.data_engine
        eng.catalog["MYVAR"] = {"external_metadata": "definitely/missing_xyz.json",
                                "data_type": "string"}
        eng._catalog_by_short["MYVAR"] = eng.catalog["MYVAR"]
        _run(it, "create-dataset d", "import db/MYVAR")
        text = "\n".join(str(m) for m in it.output_log)
        assert "ADVARSEL" in text and "MYVAR" in text

    def test_normal_demo_import_has_no_spurious_warning(self):
        it = _run(_interp(), "create-dataset d", "import db/INNTEKT_WYRKINNT 2019-01-01")
        text = "\n".join(str(m) for m in it.output_log)
        assert "ADVARSEL" not in text


class TestPanelCodes:
    """import-panel must preserve zero-padded/alphanumeric label codes and not
    crash on non-numeric ones (it used to int() every code)."""

    def _panel(self):
        it = MicroInterpreter(metadata_path=None)
        eng = it.data_engine
        eng.catalog["NPRNIVA"] = {"labels": {"I": "Innlagt", "U": "Ute", "R": "Rehab"},
                                  "data_type": "string", "microdata_datatype": "Alfanumerisk"}
        eng.catalog["KOMM"] = {"labels": {"0301": "Oslo", "1103": "Stavanger", "5001": "Trondheim"},
                               "data_type": "string", "microdata_datatype": "Alfanumerisk"}
        return _run(it, "create-dataset d",
                    "import-panel db/NPRNIVA db/KOMM 2018-01-01 2019-01-01")

    def test_no_crash_on_alphanumeric_codes(self):
        it = self._panel()
        text = "\n".join(str(m) for m in it.output_log)
        assert "FEIL" not in text
        df = it.datasets[it.active_name]
        assert set(df["NPRNIVA"].unique()) <= {"I", "U", "R"}

    def test_zero_padded_codes_preserved(self):
        it = self._panel()
        df = it.datasets[it.active_name]
        # '0301' must stay the 4-char string, not become int 301
        assert all(isinstance(v, str) and len(v) == 4 for v in df["KOMM"].unique())


class TestStaticSourceLimit:
    """The static (DuckDB/Parquet) source must bound the population by
    `WHERE unit_id <= n`, not `LIMIT n` — parquet row order is unguaranteed, so
    LIMIT could select a person set inconsistent with the entity tables (which
    already filter `ref_col <= n`), leaving dangling unit_ids."""

    def _src(self):
        import static_source
        return static_source.StaticDataSource({"INNTEKT_X": {}}, {})

    def test_person_population_bounded_by_where_not_limit(self):
        descs = self._src().plan([{"var": "db/INNTEKT_X", "date1": None}], limit=5)
        assert len(descs) == 1
        d = descs[0]
        assert d.get("kind") == "person"
        assert not d.get("limit"), "person scan must not use LIMIT"
        assert d.get("where") and "unit_id <= 5" in d["where"]

    def test_person_sql_uses_where(self):
        sqls = self._src().plan_sql(
            "import db/INNTEKT_X", base_url="https://x/", limit=5)
        sql = sqls[0]["sql"]
        assert "unit_id <= 5" in sql and "LIMIT" not in sql.upper()


class TestValidImportDateGrid:
    """The yearly import-date grid must not enumerate dates outside the
    variable's [valid_from, valid_to] window (a discontinued variable must not
    offer dates after valid_to)."""

    def test_export_grid_respects_valid_to(self):
        import mockdata_export as mx
        ds = mx.valid_import_dates("2010-06-01", "2018-03-31", "Tverrsnitt")
        assert all("2010-06-01" <= d <= "2018-03-31" for d in ds)
        assert "2018-06-01" not in ds      # past valid_to -> excluded
        assert "2017-06-01" in ds          # valid years still present

    def test_export_akkumulert_window_bounds(self):
        import mockdata_export as mx
        ds = mx.valid_import_dates("2010-06-01", "2018-03-31", "Akkumulert")
        assert all("2010-06-01" <= d <= "2018-03-31" for d in ds)
        assert "2010-03-31" not in ds      # period-end before valid_from
        assert "2018-06-01" not in ds      # period-start past valid_to

    def test_m2py_grid_respects_valid_to(self):
        import m2py
        meta = {"temporalitet": "Tverrsnitt",
                "description": "Gyldighetsperiode: 2010-06-01 – 2018-03-31"}
        ds = m2py._valid_import_dates_for(meta)
        assert ds is not None
        assert all("2010-06-01" <= d <= "2018-03-31" for d in ds)
        assert "2018-06-01" not in ds


class TestStaticDynamicPanelDeath:
    """In the dynamic static-build panel, a dead person must have no record
    after death — income, wealth AND municipality all missing (the register
    returns nothing post-death; carrying last year's value makes dead people
    'live' and 'own')."""

    def test_dead_persons_have_no_wealth_or_municipality(self):
        import json
        import mockdata_export as mx
        catalog = json.load(open("variable_metadata.json"))["variables"]
        engine = mx.make_engine(800, catalog)
        tables = mx.build_all(engine, years=[2018, 2019, 2020],
                              dynamic_person_year=True, dead_fraction=0.3,
                              entities=[], include_npr=False,
                              include_trafikkulykke=False)
        py = tables["person_year"]
        dead = py[py["livsstatus"] == "dod"]
        assert len(dead) > 0
        assert dead["SKATT_NETTOFORMUE"].isna().all()
        assert dead["BOSATT_KOMMUNE"].isna().all()
        # sanity: the living still have values
        assert py[py["livsstatus"] == "sysselsatt"]["SKATT_NETTOFORMUE"].notna().any()


class TestLiveDeathDates:
    """H3 (kodegjennomgang 2026-07-07): den generiske date:yyyymmdd-
    generatoren ga ALLE personer en uniform dødsdato 1990-2025 uavhengig av
    fødsel — 100 % døde, ~15 % døde før de ble født, og «levende = missing
    DOEDS_DATO» valgte ingen. Live-generatoren må gi missing for flertallet
    og aldri dødsdato før fødselsdato eller fram i tid."""

    # Trenger ekte metadata: data_type 'date:yyyymmdd' står i variable_metadata.json
    def _meta_interp(self):
        from pathlib import Path
        meta = Path(__file__).resolve().parent.parent / "variable_metadata.json"
        return MicroInterpreter(metadata_path=meta)

    def _import_both(self, *extra):
        return _run(self._meta_interp(), "create-dataset d",
                    "import db/BEFOLKNING_FOEDSELS_AAR_MND as fdato",
                    "import db/BEFOLKNING_DOEDS_DATO as dod", *extra)

    def test_most_persons_alive(self):
        it = self._import_both()
        df = it.datasets[it.active_name]
        share_dead = df["dod"].notna().mean()
        assert 0.005 <= share_dead <= 0.35, (
            f"forventet et realistisk mindretall døde, fikk {share_dead:.1%}"
        )

    def test_death_never_before_birth(self):
        it = self._import_both()
        df = it.datasets[it.active_name]
        dead = df[df["dod"].notna()]
        assert len(dead) > 0
        death_yyyymm = (dead["dod"] // 100).astype(int)
        assert (death_yyyymm >= dead["fdato"]).all(), (
            "dødsdato før fødselsdato i live-generert data"
        )

    def test_no_future_death_dates(self):
        it = self._import_both()
        df = it.datasets[it.active_name]
        dead = df[df["dod"].notna()]
        assert (dead["dod"] // 10000 <= m2py._DEMO_REF_YEAR).all()

    def test_death_respects_import_reference_date(self):
        # Import per 2010-01-01: ingen dødsdatoer etter referanseåret
        it = _run(self._meta_interp(), "create-dataset d",
                  "import db/BEFOLKNING_DOEDS_DATO 2010-01-01 as dod")
        df = it.datasets[it.active_name]
        dead = df[df["dod"].notna()]
        assert len(dead) > 0
        assert (dead["dod"] // 10000 <= 2010).all()

    def test_survival_prep_chain_with_missing_deaths(self):
        # Manualeksempelet (overlevelsesanalyse) gjør
        # string() -> substr() -> destring på dødsdato. Med realistisk
        # mest-missing dødsdato må string(missing) forbli missing (ikke
        # bli strengen 'nan' som velter destring), og sysmiss må fortsatt
        # skille døde fra levende.
        it = self._import_both()
        dead_before = it.datasets[it.active_name]["dod"].notna()
        _run(it,
             "replace dod = string(dod)",
             "generate yyyy = substr(dod,1,4)",
             "destring yyyy")
        out = "\n".join(str(m) for m in it.output_log)
        assert "FEIL" not in out
        df = it.datasets[it.active_name]
        assert df["yyyy"].notna().equals(dead_before)
        assert (df.loc[dead_before, "yyyy"] >= 1900).all()

    def test_other_yyyymmdd_variables_unchanged(self):
        # Generisk yyyymmdd-generator for ikke-dødsvariabler er som før:
        # alle rader får en dato (f.eks. BEFOLKNING_FORSTDATO).
        it = _run(self._meta_interp(), "create-dataset d",
                  "import db/BEFOLKNING_FORSTDATO as forst")
        df = it.datasets[it.active_name]
        assert df["forst"].notna().all()


class TestLatentStructureNaNHandling:
    """apply_latent_structure rank-matches a column's values onto a latent
    score. `np.sort` puts NaN last, so naively doing
    `new[order] = np.sort(vals)` hands every NaN to the highest-score
    persons and every real value to the lowest-score ones — e.g. real AFP
    (early-retirement pension) amounts landing on children while the actual
    pensioners (highest age-score) get NaN. Missingness must stay exactly
    where it was; only non-null values may be reordered."""

    def _engine(self):
        import mockdata_export as mx
        catalog = {
            "AFP_TEST": {
                "data_type": "int",
                "short_title": "AFP test",
                "description": "afp pensjon",
            }
        }
        return mx.make_engine(30, catalog)

    def test_nan_positions_survive_reordering(self):
        import mockdata_export as mx
        engine = self._engine()
        n = 30
        uids = np.arange(1, n + 1, dtype=np.int64)
        # Children (uid 1-15, born 2018) never receive AFP -> NaN.
        # Adults (uid 16-30, born 1950) have real AFP amounts.
        birth = np.where(uids <= 15, 2018 * 100 + 1, 1950 * 100 + 1)
        afp = np.where(uids <= 15, np.nan, uids.astype(float) * 1000.0)
        df = pd.DataFrame({
            "unit_id": uids,
            "BEFOLKNING_FOEDSELS_AAR_MND": birth,
            "AFP_TEST": afp,
        })
        nan_mask_before = pd.isna(df["AFP_TEST"]).to_numpy()
        assert nan_mask_before.sum() == 15  # sanity: missingness correlates with age

        out = mx.apply_latent_structure(df, engine, ref_year=2020)

        nan_mask_after = pd.isna(out["AFP_TEST"]).to_numpy()
        assert np.array_equal(nan_mask_before, nan_mask_after), (
            "NaN positions must be unchanged by rank-matching"
        )
        # The old bug handed every real value to the (NaN-score) children.
        assert out.loc[out["unit_id"] <= 15, "AFP_TEST"].isna().all(), (
            "children must not receive AFP values just because NaNs sort last"
        )
        # Values are conserved — a permutation of the originals, not lost or duplicated.
        before_vals = np.sort(df.loc[~nan_mask_before, "AFP_TEST"].to_numpy())
        after_vals = np.sort(out.loc[~nan_mask_after, "AFP_TEST"].to_numpy())
        assert np.allclose(before_vals, after_vals)


class TestTrafikkulykkeMortalityScoping:
    """build_trafikkulykke must not involve persons who are dead or not yet
    born in the accident's year — previously involvements were sampled from
    the full person universe with no death check, and ages for the
    not-yet-born were clamped to 0 instead of excluding them."""

    def _engine(self):
        import mockdata_export as mx
        return mx.make_engine(5, {})  # empty catalog -> no extra TRAFULYK_* vars generated

    def _person_df(self):
        return pd.DataFrame({
            "unit_id": [1, 2, 3, 4, 5],
            "BEFOLKNING_KJOENN": ["1", "2", "1", "2", "1"],
            "BEFOLKNING_FOEDSELS_AAR_MND": [197001, 194001, 202101, 198001, 199001],
            # uid 2 died in 2005 (before the 2020 accident); uid 3 is not
            # born until 2021 (after the 2020 accident); the rest are alive.
            "BEFOLKNING_DOEDS_DATO": [np.nan, 20050101, np.nan, np.nan, np.nan],
        })

    def test_dead_and_unborn_excluded_from_involvements(self):
        import mockdata_export as mx
        engine = self._engine()
        person_df = self._person_df()

        tables = mx.build_trafikkulykke(engine, person_df, years=[2020], accident_rate=1.0)
        acc_df = tables["trafikkulykke"]
        bridge_df = tables["person_i_trafikkulykke"]

        assert (acc_df["TRAFULYK_AARMND"] // 100 == 2020).all()  # sanity: single accident year
        involved = set(bridge_df["TRAFULYK_PERS_FNR"].tolist())
        assert 2 not in involved, "person dead before the accident year must not be involved"
        assert 3 not in involved, "person not yet born in the accident year must not be involved"
        assert involved <= {1, 4, 5}
        # declared per-accident count must match actual rows sampled for it
        assert acc_df["TRAFULYK_ANTALL_PERS"].sum() == len(bridge_df)
        # ages must be non-negative (no not-yet-born clamped to age 0)
        assert (bridge_df["TRAFULYK_PERS_ALDER"] >= 0).all()


class TestSynthEducationChildGuard:
    """synth_education must never hand a child a NUS2000 attainment level.
    Birth years > 2005 fell into the fallback "9999" cohort bucket
    (0.15/0.55/0.30), which still gave 10-year-olds a 30% chance of "high"
    (tertiary) education. Persons younger than 18 at the reference year must
    get "low" deterministically."""

    def test_children_always_low(self):
        import mockdata_core as mc
        # Sample many unit_ids (varying the seed) at several child ages;
        # every single one must resolve to "low", not just "usually".
        for age in (0, 5, 10, 17):
            for uid in range(1, 51):
                assert mc.synth_education(uid, age=age, as_of_year=2025) == "low"

    def test_adults_are_not_all_low(self):
        import mockdata_core as mc
        # Sanity: the guard must not blanket-clamp adults too.
        levels = {mc.synth_education(uid, age=30, as_of_year=2025) for uid in range(1, 51)}
        assert levels != {"low"}

    def test_vectorised_matches_scalar(self):
        import numpy as np
        import mockdata_core as mc
        uids = np.arange(1, 21)
        ages = np.full(20, 8)
        vec = mc.synth_education_vec(uids, ages=ages, as_of_year=2025)
        assert all(v == "low" for v in vec)


class TestMultiRecordDeterministicDates:
    """_generate_variable_values (used by multi-record entities: jobb/kjøretøy/
    kurs) drifted from generate(): it produced RANDOM birth years instead of the
    deterministic per-person ones, so a person's age differed between their
    person record and their entity records."""

    def test_birthdate_is_deterministic_per_person(self):
        eng = MicroInterpreter(metadata_path=None).data_engine
        uids = np.arange(1, 201, dtype=np.int64)
        meta = {"data_type": "date:yyyymm"}
        vals = eng._generate_variable_values(
            "BEFOLKNING_FOEDSELS_AAR_MND", "BEFOLKNING_FOEDSELS_AAR_MND",
            meta, len(uids), np.random.default_rng(0), uids=uids)
        years = [int(v) // 100 for v in vals]
        expected = [m2py._norway_demo_birth_year_from_uid(int(u)) for u in uids]
        assert years == expected
