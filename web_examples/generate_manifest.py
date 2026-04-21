"""Regenerer web_examples/manifest.json.

Leser alle kategorimapper (NN_navn) og deres .txt-scripts, trekker ut
titlene fra `// Example: <tittel>` på andre linje, og skriver en
manifest-fil som microdata_runner.html laster inn ved åpning av
web-eksempel-velgeren.

Kjør fra repo-roten:
    python web_examples/generate_manifest.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FOLDER_RE = re.compile(r"^(\d+)_(.+)$")
SCRIPT_RE = re.compile(r"^\d+_.*\.txt$")
TITLE_RE = re.compile(r"//\s*Example:\s*(.+?)\s*$")


def _prettify(raw: str) -> str:
    """'grunnleggende_operasjoner' -> 'Grunnleggende operasjoner'."""
    words = raw.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else raw


def _folder_label(name: str) -> str:
    m = FOLDER_RE.match(name)
    if not m:
        return _prettify(name)
    num, rest = m.group(1), m.group(2)
    return f"{num} — {_prettify(rest)}"


def _extract_title(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as f:
            for _ in range(5):  # tittel ligger typisk på linje 2
                line = f.readline()
                if not line:
                    break
                m = TITLE_RE.match(line.strip())
                if m:
                    return m.group(1)
    except OSError:
        pass
    # Fallback: avled fra filnavnet (strip NN_ og .txt, underscore -> space)
    stem = path.stem
    m = FOLDER_RE.match(stem)
    rest = m.group(2) if m else stem
    return _prettify(rest)


def build_manifest() -> dict:
    categories = []
    for folder in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        if not FOLDER_RE.match(folder.name):
            continue
        scripts = []
        for script in sorted(folder.iterdir()):
            if not script.is_file() or not SCRIPT_RE.match(script.name):
                continue
            scripts.append({
                "file": script.name,
                "label": _extract_title(script),
            })
        if scripts:
            categories.append({
                "folder": folder.name,
                "label": _folder_label(folder.name),
                "scripts": scripts,
            })
    return {"categories": categories}


def main() -> None:
    manifest = build_manifest()
    out = ROOT / "manifest.json"
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    total_scripts = sum(len(c["scripts"]) for c in manifest["categories"])
    print(
        f"Skrev {out.relative_to(ROOT.parent)} "
        f"({len(manifest['categories'])} kategorier, {total_scripts} scripts)."
    )


if __name__ == "__main__":
    main()
