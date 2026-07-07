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

    # Uten manifest-info (n_persons/person-rader) finnes ingen død-bestand å
    # ta hensyn til — grensen skal da være den enkle unit_id <= n.
    _NO_DEAD_MANIFEST = {"n_persons": 100, "tables": {"person": {"rows": 100}}}

    def _src(self):
        import static_source
        return static_source.StaticDataSource(
            {"INNTEKT_X": {}}, {}, manifest=self._NO_DEAD_MANIFEST)

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


class TestStaticSourceLimitIncludesDeceased:
    """The deceased stock is minted with unit_id > n_living
    (mockdata_export.build_deceased_stock), so the old `unit_id <= n` limit
    silently excluded ALL historical dead — 'import everyone, filter to alive'
    became a no-op exactly when a population limit was set. A limit of n must
    take a proportional share of living AND dead ids."""

    _MANIFEST = {"n_persons": 100, "tables": {"person": {"rows": 160}}}

    def _src(self, manifest=None):
        import static_source
        return static_source.StaticDataSource(
            {"INNTEKT_X": {}, "JOBB_X": {"enhetstype": "Jobb"}}, {},
            manifest=manifest or self._MANIFEST)

    def test_small_limit_takes_share_of_both_strata(self):
        # 100 levende + 60 døde; limit 40 -> 25 levende (1..25) + 15 døde (101..115)
        descs = self._src().plan([{"var": "db/INNTEKT_X", "date1": None}], limit=40)
        w = descs[0]["where"]
        assert "unit_id <= 25" in w
        assert "unit_id > 100" in w and "unit_id <= 115" in w

    def test_entity_filter_uses_living_share(self):
        # Entitetsrader refererer levende personer — filteret må bruke den
        # levende andelen (25), ikke hele limit (40), ellers refererer
        # entitetsrader personer utenfor universet.
        descs = self._src().plan([{"var": "db/JOBB_X", "date1": None}], limit=40)
        w = descs[0]["where"]
        assert "ARBEIDSFORHOLD_PERSON <= 25" in w

    def test_repo_manifest_is_autoloaded(self):
        import static_source
        src = static_source.StaticDataSource({"INNTEKT_X": {}}, {})
        # static_data/manifest.json ligger ved siden av modulen og skal
        # plukkes opp automatisk for lokal kjøring (CLI/tester).
        assert src.manifest and int(src.manifest["n_persons"]) > 0

    def test_limit_covers_dead_ids_against_real_manifest(self):
        import static_source
        src = static_source.StaticDataSource({"INNTEKT_X": {}}, {})
        n_living, n_total = src._population_counts()
        assert n_living and n_total > n_living  # bygget har død-bestand
        descs = src.plan([{"var": "db/INNTEKT_X", "date1": None}], limit=50)
        w = descs[0]["where"]
        assert f"unit_id > {n_living}" in w, w

    def test_limit_at_or_above_total_keeps_simple_bound(self):
        descs = self._src().plan([{"var": "db/INNTEKT_X", "date1": None}], limit=160)
        assert descs[0]["where"] == "unit_id <= 160"


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


class TestLiveKommuneMatchesStatic:
    """H1 (kodegjennomgang 2026-07-07): live person-generering av kodede
    kategoriske med null-paddede strengkoder (BOSATT_KOMMUNE, data_type int)
    ga float64 (301.0) mens den statiske parquet-en har '0301'-strenger
    (normalize_for_microdata) og entitetsgenereringen strengifiserer. Live
    skal gi nøyaktig de samme strengkodene — og betingelser på '0301', 301
    og labelteksten skal alle treffe."""

    @pytest.fixture(scope="class")
    def kommune_it(self):
        it = MicroInterpreter(metadata_path="variable_metadata.json")
        it.run_script("create-dataset d\n"
                      "import db/BOSATT_KOMMUNE 2015-01-01 as kommune")
        return it

    def test_live_dtype_and_value_space_match_static(self, kommune_it):
        col = kommune_it.datasets[kommune_it.active_name]["kommune"]
        static_col = pd.read_parquet(
            "static_data/person_year.parquet",
            columns=["year", "BOSATT_KOMMUNE"],
        ).query("year == 2015")["BOSATT_KOMMUNE"]
        # Samme dtype-familie som statisk (strengkoder, ikke float)
        assert col.dtype == static_col.dtype == object
        assert all(isinstance(v, str) for v in col.dropna())
        # Verdiene er gyldige kommunekoder fra samme kodebok som statisk bygg
        codes = set(pd.read_parquet("static_data/kommune.parquet")["kommune_nr"].astype(str))
        assert set(col.dropna()) <= codes
        # Era-riktig: '0301' (Oslo før/etter reformen) finnes i 2015-rommet
        assert "0301" in set(col)

    def test_condition_mask_matches_string_int_and_label(self, kommune_it):
        df = kommune_it.datasets[kommune_it.active_name]
        masks = {
            cond: kommune_it._eval_condition_mask(df, cond)
            for cond in ("kommune == '0301'", "kommune == 301", "kommune == 'Oslo'")
        }
        counts = {c: int(m.sum()) for c, m in masks.items()}
        assert all(n > 0 for n in counts.values()), counts
        # Alle tre formene skal treffe nøyaktig samme rader
        assert len(set(counts.values())) == 1, counts

    def test_keep_if_int_code_works_end_to_end(self, kommune_it):
        it = MicroInterpreter(metadata_path="variable_metadata.json")
        it.run_script("create-dataset d\n"
                      "import db/BOSATT_KOMMUNE 2015-01-01 as kommune\n"
                      "keep if kommune == 301")
        df = it.datasets[it.active_name]
        assert len(df) > 0
        assert set(df["kommune"]) == {"0301"}


class TestStaticRouteTimeVaryingCore:
    """static_source.route() konsulterte bare person_year når temporalitet var
    akkumulert/tverrsnitt OG dato var gitt — BOSATT_KOMMUNE har temporalitet
    None, så person_year-radene (bygget via CORE_TIMEVARYING) ble aldri
    servert og statiske kommune-importer falt stille tilbake til generering.
    Variabler som faktisk er materialisert i person_year skal rutes dit når
    dato er gitt."""

    def _src(self):
        import json
        import duckdb
        import static_source
        catalog = json.load(open("variable_metadata.json"))["variables"]
        con = duckdb.connect()
        table_columns = {}
        for t in ("person", "person_year"):
            cols = [r[0] for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('static_data/{t}.parquet')"
            ).fetchall()]
            table_columns[t] = set(cols)
        con.close()
        return static_source.StaticDataSource(catalog, table_columns)

    def test_kommune_routes_to_person_year_with_date(self):
        d = self._src().route("BOSATT_KOMMUNE", "2015-01-01")
        assert d is not None
        assert d["table"] == "person_year"
        assert d["where"] == "year=2015"
        assert d["key"] == "person_year|BOSATT_KOMMUNE|2015"

    def test_kommune_without_date_falls_back(self):
        # Uten dato finnes ingen person_year-rute, og BOSATT_KOMMUNE er ikke
        # materialisert i person-tabellen — korrekt svar er fallback (None).
        d = self._src().route("BOSATT_KOMMUNE", None)
        assert d is None

    def test_era_correct_codes_served_per_year(self):
        import duckdb
        src = self._src()
        con = duckdb.connect()
        codes = {}
        for year in (2015, 2021):
            plan = src.plan_sql(f"import db/BOSATT_KOMMUNE {year}-01-01", base_url="./")
            assert plan and "person_year" in plan[0]["sql"]
            rows = con.execute(plan[0]["sql"]).fetchall()
            codes[year] = {r[1] for r in rows if r[1] is not None}
        con.close()
        # Gamle Østfold/Akershus-koder (010x) finnes i 2015, ikke i 2021;
        # Agder-koder (42xx) finnes i 2021, ikke i 2015.
        assert "0104" in codes[2015]
        assert "0104" not in codes[2021]
        assert any(str(c).startswith("42") for c in codes[2021])
        assert not any(str(c).startswith("42") for c in codes[2015])

    def test_generate_serves_cached_person_year_rows(self):
        import duckdb
        src = self._src()
        d = src.route("BOSATT_KOMMUNE", "2015-01-01")
        con = duckdb.connect()
        df = con.execute(
            "SELECT unit_id, BOSATT_KOMMUNE FROM "
            "read_parquet('static_data/person_year.parquet') WHERE year=2015"
        ).df()
        con.close()
        src.set_cache({d["key"]: {c: df[c].tolist() for c in df.columns}})
        out = src.generate("import", {"var": "db/BOSATT_KOMMUNE",
                                      "date1": "2015-01-01",
                                      "alias": "kommune"}, pd.DataFrame())
        assert out is not None
        assert list(out.columns) == ["unit_id", "kommune"]
        assert "0104" in set(out["kommune"].dropna())


class TestDriverStatsMatchAgeDraw:
    """M1 (kodegjennomgang 2026-07-07): _DRIVER_STATS['age'] var (44, 14) mens
    den faktiske syntetiske persondistribusjonen trekker N(42, 23) — monotone
    aldersverb ga ~+44 % per ekte SD når vokabularet lovte +25 %."""

    def test_driver_stats_match_synthetic_draw(self):
        import mockdata_realism as mr
        assert mr._DRIVER_STATS["age"] == (42.0, 23.0)

    def test_one_true_sd_is_one_step(self):
        import mockdata_realism as mr
        steps = mr._driver_steps_monotone("age", np.array([42.0 + 23.0, 42.0, 42.0 - 23.0]))
        assert steps.tolist() == [1.0, 0.0, -1.0]


class TestPiecewiseTrendOpenWindow:
    """L2 (kodegjennomgang 2026-07-07): liste-trend uten "from" integrerte fra
    år -1e9 -> exp(inf). Åpen nedre grense skal forankres et dokumentert
    maks-spenn under vinduets slutt."""

    def test_open_from_window_is_finite(self):
        import math
        import mockdata_realism as mr
        spec = {"trend": [
            {"to": 2019, "annual_change": "+2%"},
            {"from": 2020, "to": 2030, "annual_change": "+1%"},
        ]}
        v = mr.apply_trend_to_log_mean(0.0, spec, 2022)
        assert math.isfinite(v) and math.isfinite(math.exp(v))
        expected = (math.log(1.02) * mr._TREND_OPEN_SPAN_YEARS
                    + math.log(1.01) * 2)
        assert v == pytest.approx(expected)

    def test_fully_open_window_is_finite(self):
        import math
        import mockdata_realism as mr
        spec = {"trend": [{"annual_change": "+3%"}]}
        v = mr.apply_trend_to_log_mean(0.0, spec, 2020)
        assert math.isfinite(v) and math.isfinite(math.exp(v))
        assert v == pytest.approx(math.log(1.03) * mr._TREND_OPEN_SPAN_YEARS)

    def test_closed_windows_unchanged(self):
        import math
        import mockdata_realism as mr
        spec = {"trend": [{"from": 2010, "to": 2019, "annual_change": "+2%"}]}
        v = mr.apply_trend_to_log_mean(0.0, spec, 2015)
        assert v == pytest.approx(math.log(1.02) * 5)
