import pandas as pd, os
D = os.path.join(os.path.dirname(__file__), "..", "data")

def test_iris_schema():
    df = pd.read_csv(os.path.join(D, "iris.csv"))
    assert list(df.columns) == ["sepal_length", "sepal_width", "petal_length", "petal_width", "species"]
    assert len(df) == 150
    assert set(df["species"].unique()) == {"setosa", "versicolor", "virginica"}

def test_penguins_schema():
    df = pd.read_csv(os.path.join(D, "penguins.csv"))
    for c in ["species", "island", "bill_length_mm", "flipper_length_mm", "body_mass_g", "sex"]:
        assert c in df.columns, c
    assert len(df) >= 300
    assert "Adelie" in set(df["species"].unique())
