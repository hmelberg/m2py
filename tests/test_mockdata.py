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
