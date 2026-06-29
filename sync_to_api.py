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
