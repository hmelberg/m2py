import json
from pathlib import Path

import pytest

import importlib.util

_SPEC = importlib.util.spec_from_file_location(
    "generate_manifest",
    Path(__file__).resolve().parent.parent / "examples" / "generate_manifest.py",
)
gm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gm)


def test_pretty():
    assert gm.pretty("pandas_basics") == "Pandas basics"
    assert gm.pretty("") == ""


def test_folder_label():
    assert gm.folder_label("01_grunnleggende") == "01 — Grunnleggende"
    assert gm.folder_label("annet") == "Annet"


def test_label_from_label_line(tmp_path):
    p = tmp_path / "01_foo.txt"
    p.write_text("#options.mode = micropython\n# label: Min fine tittel\nimport x\n",
                 encoding="utf-8")
    assert gm.label_for(p) == "Min fine tittel"


def test_label_from_options_title(tmp_path):
    p = tmp_path / "01_foo.txt"
    p.write_text('#options.title = "Salgs-dashboard"\nimport x\n', encoding="utf-8")
    assert gm.label_for(p) == "Salgs-dashboard"


def test_label_fallback_to_filename(tmp_path):
    p = tmp_path / "03_csv_url.txt"
    p.write_text("import x\n", encoding="utf-8")
    assert gm.label_for(p) == "Csv url"


def test_label_priority_label_over_title(tmp_path):
    """Label line should take priority over #options.title regardless of line order."""
    p = tmp_path / "example.txt"
    p.write_text('#options.title = "FraTittel"\n# label: FraLabel\n', encoding="utf-8")
    assert gm.label_for(p) == "FraLabel"


def test_build_manifest_flat_and_categorised(tmp_path):
    root = tmp_path / "examples"
    mp = root / "micropython"
    mp.mkdir(parents=True)
    (mp / "01_a.txt").write_text("# label: Eksempel A\n", encoding="utf-8")
    (mp / "02_b.txt").write_text("# label: Eksempel B\n", encoding="utf-8")
    cat = mp / "10_avansert"
    cat.mkdir()
    (cat / "01_c.txt").write_text("# label: Eksempel C\n", encoding="utf-8")
    # flat file in root and a _private dir must be ignored
    (root / "loose.txt").write_text("x\n", encoding="utf-8")
    (root / "__pycache__").mkdir()

    m = gm.build_manifest(root)

    assert list(m.keys()) == ["micropython"]
    assert m["micropython"] == [
        {"file": "micropython/01_a.txt", "label": "Eksempel A", "group": None},
        {"file": "micropython/02_b.txt", "label": "Eksempel B", "group": None},
        {"file": "micropython/10_avansert/01_c.txt", "label": "Eksempel C",
         "group": "10 — Avansert"},
    ]


def test_build_manifest_skips_unknown_mode_folders(tmp_path):
    """Only folders whose name is a known mode key should be included; a stray
    data folder like examples/lsj/ must not pollute the manifest."""
    root = tmp_path / "examples"
    mp = root / "micropython"
    mp.mkdir(parents=True)
    (mp / "01_a.txt").write_text("# label: Eksempel A\n", encoding="utf-8")

    unknown = root / "lsj"
    unknown.mkdir()
    (unknown / "01_x.txt").write_text("# label: Ukjent\n", encoding="utf-8")

    m = gm.build_manifest(root)

    assert list(m.keys()) == ["micropython"]


def test_label_from_example_marker(tmp_path):
    p = tmp_path / "01_x.txt"
    p.write_text("// ===\n// Example: Opprette datasett\n// Source: http://x\n",
                 encoding="utf-8")
    assert gm.label_for(p) == "Opprette datasett"


def test_label_line_beats_example_marker(tmp_path):
    p = tmp_path / "01_x.txt"
    p.write_text("// Example: Fra Example\n# label: Fra label\n", encoding="utf-8")
    assert gm.label_for(p) == "Fra label"
