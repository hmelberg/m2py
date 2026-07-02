# tests/test_sync_to_api.py
from pathlib import Path
import sync_to_api as s


def _make_src(root: Path):
    (root / "m2py.py").write_text("emulator v1\n")
    (root / "functions.py").write_text("functions\n")
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
    rels = {rel for _, rel, _ in manifest}
    assert {"m2py.py", "functions.py", "m2py_translate.py", "m2py_remote.py",
            "m2py_protection.py", "protect.py",
            "m2py_runtime/__init__.py", "m2py_runtime/pandas_ops.py"} == rels


def test_build_manifest_includes_safepy_package(tmp_path):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    sp = tmp_path / "safepy" / "safepy"; sp.mkdir(parents=True)
    (sp / "__init__.py").write_text("safepy init\n")
    (sp / "api.py").write_text("api\n")
    ad = sp / "adapters"; ad.mkdir()
    (ad / "__init__.py").write_text("adapters init\n")
    manifest = s.build_manifest(src, prot, sp)
    rels = {rel for _, rel, _ in manifest}
    assert {"safepy/__init__.py", "safepy/api.py",
            "safepy/adapters/__init__.py"} <= rels
    # safepy files carry the safepy provenance header, m2py files the m2py one
    headers = {rel: h for _, rel, h in manifest}
    assert "the safepy repo" in headers["safepy/api.py"]
    assert "the m2py repo" in headers["m2py.py"]


def test_compute_status_detects_match_drift_missing(tmp_path):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    # match: dest contains header + source content
    (dest / "m2py.py").write_text(s.GENERATED_HEADER + "emulator v1\n")
    # drift: different translator content
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


def test_build_manifest_without_runtime_dir(tmp_path):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    # NOTE: no m2py_runtime dir, and the fixed source files need not exist for
    # build_manifest (it only assembles paths, does not read them).
    manifest = s.build_manifest(src, prot)
    rels = {rel for _, rel, _ in manifest}
    assert "protect.py" in rels
    assert not any(rel.startswith("m2py_runtime/") for rel in rels)
    # no safepy_root given -> no safepy entries
    assert not any(rel.startswith("safepy/") for rel in rels)


def test_report_only_main_writes_nothing(tmp_path, capsys):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    (dest / "m2py.py").write_text("SERVER-EDITED emulator\n")  # drift on m2py.py

    rc = s.main(["--source", str(src), "--protect", str(prot), "--dest", str(dest)])
    out = capsys.readouterr().out

    assert rc == 0
    # report-only: nothing copied — protect.py still absent at dest
    assert not (dest / "protect.py").exists()
    assert not (dest / "m2py_translate.py").exists()
    # clobber-safety warning shown for drifted m2py.py
    assert "WARNING" in out and "m2py.py" in out
    assert "Report-only" in out
    # the drifted m2py.py must NOT be overwritten in report-only mode (clobber-safety)
    assert (dest / "m2py.py").read_text() == "SERVER-EDITED emulator\n"


def test_main_returns_2_on_missing_source(tmp_path, capsys):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()  # protect.py absent -> missing_source
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    rc = s.main(["--source", str(src), "--protect", str(prot), "--dest", str(dest)])
    assert rc == 2


def test_apply_copies_drift_and_missing_only(tmp_path, capsys):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    # match: dest already has header + source
    (dest / "m2py.py").write_text(s.GENERATED_HEADER + "emulator v1\n")
    (dest / "m2py_translate.py").write_text("OLD\n")        # drift

    rc = s.main(["--apply", "--source", str(src), "--protect", str(prot), "--dest", str(dest)])
    out = capsys.readouterr().out
    assert rc == 0

    # drifted file now has header + source content
    assert (dest / "m2py_translate.py").read_text() == s.GENERATED_HEADER + "translator\n"
    # missing files were created with header prepended
    assert (dest / "protect.py").read_text() == s.GENERATED_HEADER + "protect\n"
    assert (dest / "m2py_remote.py").exists()
    assert (dest / "m2py_protection.py").exists()
    assert (dest / "m2py_runtime" / "pandas_ops.py").read_text() == s.GENERATED_HEADER + "ops\n"
    # after apply, a fresh status shows all match
    manifest = s.build_manifest(src, prot)
    statuses = s.compute_status(manifest, dest)
    assert all(st["status"] == "match" for st in statuses)
    assert "Applied: copied" in out


def test_apply_writes_generated_header(tmp_path, capsys):
    """Every synced file must begin with GENERATED_HEADER."""
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()

    s.main(["--apply", "--source", str(src), "--protect", str(prot), "--dest", str(dest)])

    assert (dest / "protect.py").read_text().startswith(s.GENERATED_HEADER)
    assert (dest / "m2py.py").read_text().startswith(s.GENERATED_HEADER)
    assert (dest / "functions.py").read_text().startswith(s.GENERATED_HEADER)
