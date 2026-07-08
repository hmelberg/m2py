# scripts/gen_hospital.py
"""Generate a synthetic hospital-admissions dataset. All data is fake.
Deterministic under a fixed seed. Same person (id) may have several admissions."""
import numpy as np, pandas as pd

_ICD = [
    ("I21", "Acute myocardial infarction", "Cardiology"),
    ("J18", "Pneumonia", "Pulmonology"),
    ("E11", "Type 2 diabetes mellitus", "Endocrinology"),
    ("K35", "Acute appendicitis", "Surgery"),
    ("S72", "Fracture of femur", "Orthopedics"),
    ("N39", "Urinary tract infection", "Urology"),
    ("C50", "Malignant neoplasm of breast", "Oncology"),
    ("F32", "Depressive episode", "Psychiatry"),
]
_CITIES = ["Oslo", "Bergen", "Trondheim", "Stavanger", "Tromsø"]
_FIRST = ["Anna","Bjørn","Kari","Ole","Ingrid","Lars","Mette","Nils","Sofie","Erik"]
_LAST = ["Hansen","Olsen","Larsen","Andersen","Berg","Nilsen","Haugen","Dahl","Lie","Moen"]


def build(seed=42):
    rng = np.random.default_rng(seed)
    n_persons = 900
    persons = []
    for pid in range(1, n_persons + 1):
        g = rng.choice(["F", "M"])
        name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        city = rng.choice(_CITIES)
        birth = np.datetime64("1940-01-01") + int(rng.integers(0, 60 * 365)) * np.timedelta64(1, "D")
        persons.append((pid, name, g, city, birth))

    rows = []
    for pid, name, g, city, birth in persons:
        n_adm = int(rng.integers(1, 6))  # 1..5 admissions
        for _ in range(n_adm):
            icd, text, dept = _ICD[int(rng.integers(0, len(_ICD)))]
            admit = np.datetime64("2015-01-01") + int(rng.integers(0, 9 * 365)) * np.timedelta64(1, "D")
            los = int(rng.integers(1, 21))
            discharge = admit + los * np.timedelta64(1, "D")
            rows.append({
                "id": pid, "name": name, "gender": g, "city": city,
                "birth_date": np.datetime_as_string(birth, unit="D"),
                "icd10": icd, "diagnosis_text": text,
                "admit_date": np.datetime_as_string(admit, unit="D"),
                "discharge_date": np.datetime_as_string(discharge, unit="D"),
                "department": dept,
                "admission_type": rng.choice(["emergency", "elective"]),
            })
    df = pd.DataFrame(rows)
    return df.sort_values(["id", "admit_date"]).reset_index(drop=True)


if __name__ == "__main__":
    build().to_csv("data/hospital_admissions.csv", index=False)
    print("wrote data/hospital_admissions.csv")
