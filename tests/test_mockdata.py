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
