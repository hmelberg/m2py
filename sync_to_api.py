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
    runtime = source_root / "m2py_runtime"
    if runtime.is_dir():
        for p in sorted(runtime.glob("*.py")):
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
