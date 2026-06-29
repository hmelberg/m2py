# SafeStat Remote Compute — v1 Part 2: Sync Script — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `sync_to_api.py` — a locally-testable tool that copies the canonical engine files from the m2py repo (and the sibling `protect` repo) into the `microdata-api` Anvil app's `server_code/`, with an md5 drift report, report-only by default.

**Architecture:** Pure-Python file-sync tool with parameterized functions (`build_manifest`, `compute_status`, `apply_sync`, `format_report`) plus a thin `main()` CLI. All logic is testable against temporary directories; the CLI defaults point at the real sibling repos but run report-only unless `--apply` is passed. This is the prerequisite that puts the translator, `protect`, and the Part-1 core onto the server so the later Anvil `/run_extended` endpoint can import them. It also fulfills the original "sync files to microdata-api" goal and answers "is the server up to date?".

**Tech Stack:** Python 3.13 (PATH python — pandas 2.3.3 env where the suite is clean at 531/1), stdlib only (`hashlib`, `shutil`, `pathlib`, `argparse`), pytest.

## Global Constraints

- **Report-only by default.** Running the tool with no flags must NOT write or delete anything — it only prints a drift report. Copying happens only with `--apply`. (spec: Sync — "First run is a report-only diff, not a copy.")
- **Never delete; only overwrite manifest files.** The tool copies source→dest for drifted/missing files; it must never remove a file at the destination. (spec: Sync — "must never silently wipe a server-only adaptation.")
- **Clobber-safety surfacing.** When the server's `m2py.py` shows `drift`, the report must visibly warn that the destination may carry Anvil-local edits and to verify before `--apply`. (spec: Sync — clobber-safety on `m2py.py`.)
- **Canonical file set (the manifest):** `m2py.py`, `m2py_translate.py`, `m2py_remote.py`, `m2py_protection.py` (from the m2py repo root), `protect.py` (from the sibling `protect` repo root), and every `*.py` under `m2py_runtime/`. (spec: Sync + v1 scope; the Part-1 files `m2py_remote.py`/`m2py_protection.py` are included.)
- **The destination is `microdata-api/server_code/` (sibling of the m2py repo).** The tool must not touch any other path. (verified: `/Users/hom/Documents/GitHub/microdata-api/server_code/`.)
- **Do not edit any existing repo file.** This plan creates only `sync_to_api.py` and its test. The full m2py suite must stay green (baseline 531 passed, 1 xfailed on the PATH python). (spec: Verification.)
- Real-world starting state (informational, for the Task 4 dry-run): on the real server `m2py.py` exists and is **drifted**; `m2py_translate.py`, `m2py_runtime/`, `protect.py`, `m2py_remote.py`, `m2py_protection.py` are **missing_dest**. (verified earlier this session.)

---

## File Structure

- **Create `sync_to_api.py`** (m2py repo root) — the sync tool. One responsibility: compute and optionally apply file sync from canonical sources to the Anvil `server_code/`. All core logic in parameterized module functions so the CLI is a thin shell.
- **Create `tests/test_sync_to_api.py`** — unit tests driving the functions against `tmp_path` directories (never the real repos).

---

### Task 1: Manifest + status detection

**Files:**
- Create: `sync_to_api.py`
- Test: `tests/test_sync_to_api.py`

**Interfaces:**
- Produces:
  - `build_manifest(source_root: Path, protect_root: Path) -> list[tuple[Path, str]]` — list of `(abs_source_path, dest_relpath)`. Fixed files plus every `*.py` under `source_root/"m2py_runtime"` mapped to `"m2py_runtime/<name>"`.
  - `compute_status(manifest, dest_root: Path) -> list[dict]` — one dict per entry: `{"name": str, "source": Path, "dest": Path, "source_md5": str|None, "dest_md5": str|None, "status": str}` where `status` ∈ `{"match","drift","missing_dest","missing_source"}`.
  - `_md5(path: Path) -> str` (md5 hex of file bytes).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/hom/Documents/GitHub/m2py && python -m pytest tests/test_sync_to_api.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sync_to_api'`.

- [ ] **Step 3: Write minimal implementation**

```python
# sync_to_api.py
"""Sync canonical engine files from the m2py repo (and the sibling protect repo)
into the microdata-api Anvil app's server_code/, with an md5 drift report.

Report-only by default; pass --apply to copy. Never deletes; only overwrites
files named in the manifest. Run before pushing microdata-api so Anvil deploys
current engine code.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                       # m2py repo root
PROTECT_ROOT = HERE.parent / "protect"
DEST_ROOT = HERE.parent / "microdata-api" / "server_code"


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def build_manifest(source_root: Path, protect_root: Path):
    """Return [(abs_source_path, dest_relpath), ...]."""
    entries = [
        (source_root / "m2py.py", "m2py.py"),
        (source_root / "m2py_translate.py", "m2py_translate.py"),
        (source_root / "m2py_remote.py", "m2py_remote.py"),
        (source_root / "m2py_protection.py", "m2py_protection.py"),
        (protect_root / "protect.py", "protect.py"),
    ]
    for p in sorted((source_root / "m2py_runtime").glob("*.py")):
        entries.append((p, f"m2py_runtime/{p.name}"))
    return entries


def compute_status(manifest, dest_root: Path):
    out = []
    for src, rel in manifest:
        dest = dest_root / rel
        s_md5 = _md5(src) if src.exists() else None
        d_md5 = _md5(dest) if dest.exists() else None
        if s_md5 is None:
            status = "missing_source"
        elif d_md5 is None:
            status = "missing_dest"
        elif s_md5 == d_md5:
            status = "match"
        else:
            status = "drift"
        out.append({"name": rel, "source": src, "dest": dest,
                    "source_md5": s_md5, "dest_md5": d_md5, "status": status})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sync_to_api.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add sync_to_api.py tests/test_sync_to_api.py
git commit -m "feat(sync): manifest + md5 status detection for server sync"
```

---

### Task 2: Report formatting + report-only `main` (no writes)

**Files:**
- Modify: `sync_to_api.py`
- Test: `tests/test_sync_to_api.py`

**Interfaces:**
- Consumes: `build_manifest`, `compute_status` from Task 1.
- Produces:
  - `format_report(statuses) -> str` — one line per entry with a status mark; includes a visible clobber-safety WARNING line when `m2py.py` status is `drift`.
  - `main(argv=None) -> int` — parses `--apply/--source/--protect/--dest`, prints the report; with no `--apply` it makes NO filesystem changes and returns `0` (or `2` if any `missing_source`).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sync_to_api.py
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


def test_main_returns_2_on_missing_source(tmp_path, capsys):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()  # protect.py absent -> missing_source
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    rc = s.main(["--source", str(src), "--protect", str(prot), "--dest", str(dest)])
    assert rc == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sync_to_api.py -q`
Expected: FAIL — `AttributeError: module 'sync_to_api' has no attribute 'main'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to sync_to_api.py
_MARK = {"match": "=", "drift": "~", "missing_dest": "+", "missing_source": "!"}


def format_report(statuses) -> str:
    lines = ["Sync status (source -> server_code):"]
    for st in statuses:
        lines.append(f"  [{_MARK[st['status']]}] {st['name']:34} {st['status']}")
    drifted_m2py = any(st["name"] == "m2py.py" and st["status"] == "drift"
                       for st in statuses)
    if drifted_m2py:
        lines.append("")
        lines.append("  WARNING: server_code/m2py.py differs from source. The server "
                     "copy may carry Anvil-local edits — verify it is import-clean "
                     "before --apply (it would be overwritten).")
    return "\n".join(lines)


def apply_sync(statuses):
    """Copy source -> dest for drift/missing_dest entries. Never deletes."""
    copied = []
    for st in statuses:
        if st["status"] in ("drift", "missing_dest"):
            st["dest"].parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(st["source"], st["dest"])
            copied.append(st["name"])
    return copied


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sync engine files into microdata-api/server_code.")
    ap.add_argument("--apply", action="store_true",
                    help="copy drift/missing files (default: report only)")
    ap.add_argument("--source", default=str(HERE))
    ap.add_argument("--protect", default=str(PROTECT_ROOT))
    ap.add_argument("--dest", default=str(DEST_ROOT))
    args = ap.parse_args(argv)

    manifest = build_manifest(Path(args.source), Path(args.protect))
    statuses = compute_status(manifest, Path(args.dest))
    print(format_report(statuses))

    if any(st["status"] == "missing_source" for st in statuses):
        print("\nERROR: one or more source files are missing — aborting.", file=sys.stderr)
        return 2

    pending = [st for st in statuses if st["status"] in ("drift", "missing_dest")]
    if args.apply:
        copied = apply_sync(statuses)
        print(f"\nApplied: copied {len(copied)} file(s): {', '.join(copied) or '(none)'}")
    else:
        print(f"\nReport-only. {len(pending)} file(s) would change. "
              f"Re-run with --apply to copy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sync_to_api.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add sync_to_api.py tests/test_sync_to_api.py
git commit -m "feat(sync): report-only default + clobber-safety warning"
```

---

### Task 3: `--apply` copies drift/missing and leaves matches untouched

**Files:**
- Modify: `tests/test_sync_to_api.py` (the `apply_sync`/`--apply` code already landed in Task 2; this task proves it).
- Test: `tests/test_sync_to_api.py`

**Interfaces:**
- Consumes: `main(["--apply", ...])` and `apply_sync` from Task 2.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_sync_to_api.py
def test_apply_copies_drift_and_missing_only(tmp_path, capsys):
    src = tmp_path / "m2py"; src.mkdir()
    prot = tmp_path / "protect"; prot.mkdir()
    (prot / "protect.py").write_text("protect\n")
    _make_src(src)
    dest = tmp_path / "server_code"; dest.mkdir()
    (dest / "m2py.py").write_text("emulator v1\n")          # match (identical)
    (dest / "m2py_translate.py").write_text("OLD\n")        # drift
    # protect.py + remote + protection + runtime/* are missing_dest

    rc = s.main(["--apply", "--source", str(src), "--protect", str(prot), "--dest", str(dest)])
    out = capsys.readouterr().out
    assert rc == 0

    # drifted file now matches source
    assert (dest / "m2py_translate.py").read_text() == "translator\n"
    # missing files were created, including nested runtime dir
    assert (dest / "protect.py").read_text() == "protect\n"
    assert (dest / "m2py_remote.py").exists()
    assert (dest / "m2py_protection.py").exists()
    assert (dest / "m2py_runtime" / "pandas_ops.py").read_text() == "ops\n"
    # after apply, a fresh status shows all match
    manifest = s.build_manifest(src, prot)
    statuses = s.compute_status(manifest, dest)
    assert all(st["status"] == "match" for st in statuses)
    assert "Applied: copied" in out
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_sync_to_api.py::test_apply_copies_drift_and_missing_only -v`
Expected: PASS (the implementation landed in Task 2). If it FAILS, fix `apply_sync`/`main` until it passes — the test is the contract. Do not weaken the test.

- [ ] **Step 3: (only if the test failed) fix the implementation**

If Step 2 passed, skip. Otherwise correct `apply_sync`/`main` in `sync_to_api.py` so drift+missing_dest are copied (with parent `mkdir`), matches are left untouched, and a post-apply status is all `match`.

- [ ] **Step 4: Run the full test file**

Run: `python -m pytest tests/test_sync_to_api.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_sync_to_api.py sync_to_api.py
git commit -m "test(sync): --apply copies drift/missing, leaves matches; nested dir created"
```

---

### Task 4: Real report-only dry-run + suite-green gate

**Files:**
- None (verification only).

**Interfaces:**
- Consumes: the finished `sync_to_api.py` CLI against the real sibling repos.

- [ ] **Step 1: Real report-only dry-run (NO writes)**

Run: `cd /Users/hom/Documents/GitHub/m2py && python sync_to_api.py`
Expected: a status report against the real `../microdata-api/server_code`. Based on the known starting state it should show `m2py.py` as `drift` (with the WARNING line) and `m2py_translate.py`, `m2py_remote.py`, `m2py_protection.py`, `protect.py`, and every `m2py_runtime/*.py` as `missing_dest`, ending with "Report-only. N file(s) would change." **Confirm it wrote nothing**:

Run: `cd /Users/hom/Documents/GitHub/microdata-api && git status --short server_code/`
Expected: no new/changed files from the dry-run (the report-only invocation must not have created anything).

- [ ] **Step 2: Full suite green (no regression)**

Run: `cd /Users/hom/Documents/GitHub/m2py && python -m pytest -q 2>&1 | tail -3`
Expected: `531 passed` plus the new `sync_to_api` tests (6), `1 xfailed` — i.e. `537 passed, 1 xfailed`. No previously-passing test fails.

- [ ] **Step 3: Confirm only the two new files were added across this plan**

Run: `git -C /Users/hom/Documents/GitHub/m2py diff --name-only HEAD~3 | sort`
Expected: only `sync_to_api.py` and `tests/test_sync_to_api.py`.

---

## Self-Review

**Spec coverage (Sync section of the design):**
- "checked-in manifest of canonical files" → `build_manifest` (Task 1). ✓
- manifest covers `m2py.py`, `m2py_translate.py`, `m2py_runtime/`, `protect.py`, plus the Part-1 `m2py_remote.py`/`m2py_protection.py` → `build_manifest` entries (Task 1). ✓
- "md5 drift report" → `compute_status` + `format_report` (Tasks 1–2). ✓
- "report-only first run, not a copy" → report-only default in `main` (Task 2, proven by `test_report_only_main_writes_nothing`). ✓
- "never silently wipe a server-only adaptation" → never deletes; clobber-safety WARNING on `m2py.py` drift (Task 2). ✓
- "Run before each Anvil push" → CLI defaults to the real `server_code`; `--apply` performs the copy (Tasks 2–3). ✓
- Deferred and correctly ABSENT: the actual git-commit/push of `microdata-api` (a manual step the user does after `--apply`); the Anvil endpoint itself (Part 3).

**Placeholder scan:** none — every step has runnable code/commands.

**Type consistency:** `compute_status` returns dicts with the `status`/`source`/`dest`/`name` keys that `format_report`, `apply_sync`, and `main` all read; `build_manifest` returns `(Path, str)` tuples consumed by `compute_status`. ✓

---

## Next plan (after this is green)

- **Part 3 — Anvil `/run_extended` endpoint + minimal registry + async** (deploy-and-verify-live, no local pytest): `m2py_shim.run_extended` wraps `run_remote` (resolve source → `read_source` → build `datasets` → `run_remote`); `@http_endpoint("/run_extended")` launches a background task; poll via existing `/task_status`; minimal `Source` Data Table + `resolve_source` seeded with one public source. Prerequisite satisfied by THIS plan: run `python sync_to_api.py --apply`, then commit + push `microdata-api` so Anvil deploys the synced engine.
