# tests/test_sync_to_api.py
from pathlib import Path
import sync_to_api as s


def _make_src(root: Path):
    (root / "m2py.py").write_text("emulator v1\n")
    (root / "m2py_translate.py").write_text("translator\n")
    (root / "m2py_remote.py").write_text("remote\n")
    (root / "m2py_protection.py").write_text("protection\n")
    rt = root / "m2py_runtime"
    rt.mkdir()
    (rt / "__init__.py").write_text("rt init\n")
    (rt / "pandas_ops.py").write_text("ops\n")


def test_build_manifest_lists_fixed_files_and_runtime(tmp_path):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    manifest = s.build_manifest(src, prot)
    rels = {rel for _, rel in manifest}
    assert {"m2py.py", "m2py_translate.py", "m2py_remote.py",
            "m2py_protection.py", "protect.py",
            "m2py_runtime/__init__.py", "m2py_runtime/pandas_ops.py"} == rels


def test_compute_status_detects_match_drift_missing(tmp_path):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    # match: identical m2py.py
    (dest / "m2py.py").write_text("emulator v1\n")
    # drift: different translator
    (dest / "m2py_translate.py").write_text("OLD translator\n")
    # everything else absent -> missing_dest
    manifest = s.build_manifest(src, prot)
    statuses = {d["name"]: d["status"] for d in s.compute_status(manifest, dest)}
    assert statuses["m2py.py"] == "match"
    assert statuses["m2py_translate.py"] == "drift"
    assert statuses["protect.py"] == "missing_dest"
    assert statuses["m2py_runtime/pandas_ops.py"] == "missing_dest"


def test_compute_status_flags_missing_source(tmp_path):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    # protect.py deliberately absent at source
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    manifest = s.build_manifest(src, prot)
    statuses = {d["name"]: d["status"] for d in s.compute_status(manifest, dest)}
    assert statuses["protect.py"] == "missing_source"
