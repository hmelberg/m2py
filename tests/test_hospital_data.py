# tests/test_hospital_data.py
import importlib.util, os, pandas as pd
_p = os.path.join(os.path.dirname(__file__), "..", "scripts", "gen_hospital.py")
_spec = importlib.util.spec_from_file_location("gen_hospital", _p)
gen = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(gen)

def test_schema_and_invariants():
    df = gen.build(seed=42)
    assert list(df.columns) == ["id","name","gender","city","birth_date","icd10",
        "diagnosis_text","admit_date","discharge_date","department","admission_type"]
    assert len(df) >= 2000
    # multiple admissions per person exist
    assert df["id"].duplicated().any()
    assert df["id"].nunique() < len(df)
    ad = pd.to_datetime(df["admit_date"]); dis = pd.to_datetime(df["discharge_date"]); bir = pd.to_datetime(df["birth_date"])
    assert (dis >= ad).all()          # discharge on/after admit
    assert (ad.dt.year - bir.dt.year >= 0).all()   # born before admitted
    assert set(df["gender"].unique()) <= {"F", "M"}
    # icd10 <-> diagnosis_text is a consistent 1:1 mapping
    assert (df.groupby("icd10")["diagnosis_text"].nunique() == 1).all()

def test_deterministic():
    import pandas.testing as pt
    pt.assert_frame_equal(gen.build(seed=42), gen.build(seed=42))
