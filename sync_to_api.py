"""Sync canonical engine files from the m2py repo (and the sibling protect repo)
into the microdata-api Anvil app's server_code/, with an md5 drift report.

Each synced file is written with a GENERATED_HEADER prepended so the destination
carries provenance and md5 comparisons detect raw-source drift correctly.

Report-only by default; pass --apply to copy. Never deletes; only overwrites
files named in the manifest. Run before pushing microdata-api so Anvil deploys
current engine code.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                       # m2py repo root
PROTECT_ROOT = HERE.parent / "protect"
SAFEPY_ROOT = HERE.parent / "safepy" / "safepy"              # the package dir, not repo root
DEST_ROOT = HERE.parent / "microdata-api" / "server_code"
WEB_ZIP = HERE / "vendor" / "safepy.zip"


def _generated_header(repo: str) -> str:
    return (
        "# ============================================================================\n"
        "# GENERATED COPY — DO NOT EDIT HERE.\n"
        f"# Source of truth: the {repo} repo. This file is produced by sync_to_api.py.\n"
        f"# Edit the engine in the {repo} repo and re-run that script; direct edits here\n"
        "# are overwritten on the next sync.\n"
        "# ============================================================================\n"
    )


GENERATED_HEADER = _generated_header("m2py")
GENERATED_HEADER_BYTES = GENERATED_HEADER.encode("utf-8")


def _desired_bytes(src: Path, header: str = GENERATED_HEADER) -> bytes:
    """The exact bytes a synced copy must contain: the header followed by source."""
    return header.encode("utf-8") + src.read_bytes()


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def build_manifest(source_root: Path, protect_root: Path,
                   safepy_root: Path | None = None):
    """Return [(abs_source_path, dest_relpath, header), ...]."""
    h_m2py = _generated_header("m2py")
    h_protect = _generated_header("protect")
    h_safepy = _generated_header("safepy")
    entries = [
        (source_root / "m2py.py", "m2py.py", h_m2py),
        (source_root / "functions.py", "functions.py", h_m2py),
        (source_root / "m2py_translate.py", "m2py_translate.py", h_m2py),
        (source_root / "m2py_remote.py", "m2py_remote.py", h_m2py),
        (source_root / "m2py_protection.py", "m2py_protection.py", h_m2py),
        # protect.py keeps the m2py header it has always carried: changing it
        # would show as drift on every deployment that predates per-repo headers.
        (protect_root / "protect.py", "protect.py", h_m2py),
    ]
    runtime = source_root / "m2py_runtime"
    if runtime.is_dir():
        for p in sorted(runtime.glob("*.py")):
            entries.append((p, f"m2py_runtime/{p.name}", h_m2py))
    if safepy_root is not None and safepy_root.is_dir():
        for p in sorted(safepy_root.glob("*.py")):
            entries.append((p, f"safepy/{p.name}", h_safepy))
        adapters = safepy_root / "adapters"
        if adapters.is_dir():
            for p in sorted(adapters.glob("*.py")):
                entries.append((p, f"safepy/adapters/{p.name}", h_safepy))
    return entries


def compute_status(manifest, dest_root: Path):
    out = []
    for src, rel, header in manifest:
        dest = dest_root / rel
        s_md5 = hashlib.md5(_desired_bytes(src, header)).hexdigest() if src.exists() else None
        d_md5 = _md5(dest) if dest.exists() else None
        if s_md5 is None:
            status = "missing_source"
        elif d_md5 is None:
            status = "missing_dest"
        elif s_md5 == d_md5:
            status = "match"
        else:
            status = "drift"
        out.append({"name": rel, "source": src, "dest": dest, "header": header,
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
    """Write header+source -> dest for drift/missing_dest entries. Never deletes."""
    copied = []
    for st in statuses:
        if st["status"] in ("drift", "missing_dest"):
            st["dest"].parent.mkdir(parents=True, exist_ok=True)
            st["dest"].write_bytes(_desired_bytes(st["source"], st["header"]))
            copied.append(st["name"])
    return copied


def build_web_zip(safepy_root: Path, out_path: Path,
                  protect_root: Path | None = None) -> list[str]:
    """Zip the safepy package (GENERATED headers included) for the browser
    strict runner. Members: safepy/<mod>.py + safepy/adapters/<mod>.py +
    protect.py (safepy delegates result-side suppression to protect)."""
    import zipfile
    h = _generated_header("safepy")
    members = []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(safepy_root.glob("*.py")):
            name = f"safepy/{p.name}"
            z.writestr(name, _desired_bytes(p, h))
            members.append(name)
        adapters = safepy_root / "adapters"
        if adapters.is_dir():
            for p in sorted(adapters.glob("*.py")):
                name = f"safepy/adapters/{p.name}"
                z.writestr(name, _desired_bytes(p, h))
                members.append(name)
        protect_py = (protect_root or PROTECT_ROOT) / "protect.py"
        if protect_py.is_file():
            z.writestr("protect.py", _desired_bytes(protect_py, _generated_header("protect")))
            members.append("protect.py")
    return members


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sync engine files into microdata-api/server_code.")
    ap.add_argument("--apply", action="store_true",
                    help="copy drift/missing files (default: report only)")
    ap.add_argument("--web", action="store_true",
                    help="build vendor/safepy.zip for browser strict runs (Pyodide)")
    ap.add_argument("--source", default=str(HERE))
    ap.add_argument("--protect", default=str(PROTECT_ROOT))
    ap.add_argument("--safepy", default=str(SAFEPY_ROOT))
    ap.add_argument("--dest", default=str(DEST_ROOT))
    args = ap.parse_args(argv)

    # --web alene: bygg bare browser-zippen. --apply bygger den OGSÅ (safepy
    # endres ett sted, begge kopiene — Anvil + Pyodide — oppdateres i én kommando).
    if args.web:
        members = build_web_zip(Path(args.safepy), WEB_ZIP)
        print(f"Built {WEB_ZIP}: {len(members)} member(s)")
        return 0

    manifest = build_manifest(Path(args.source), Path(args.protect), Path(args.safepy))
    statuses = compute_status(manifest, Path(args.dest))
    print(format_report(statuses))

    if any(st["status"] == "missing_source" for st in statuses):
        print("\nERROR: one or more source files are missing — aborting.", file=sys.stderr)
        return 2

    pending = [st for st in statuses if st["status"] in ("drift", "missing_dest")]
    if args.apply:
        copied = apply_sync(statuses)
        print(f"\nApplied: copied {len(copied)} file(s): {', '.join(copied) or '(none)'}")
        members = build_web_zip(Path(args.safepy), WEB_ZIP)
        print(f"Built {WEB_ZIP}: {len(members)} member(s)")
    else:
        print(f"\nReport-only. {len(pending)} file(s) would change. "
              f"Re-run with --apply to copy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
