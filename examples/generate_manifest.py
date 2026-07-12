"""Regenerer examples/manifest.json fra mappestrukturen.

Én mappe per modus under examples/ (mappenavnet ER modus-nøkkelen). Ett
valgfritt undernivå (NN_kategori) blir en kategori-underoverskrift i menyen.
Labelen leses fra en `# label:`-linje (eller `-- label:` / `// label:`),
ellers `#options.title`, ellers avledet fra filnavnet.

Kjør fra repo-roten:
    python examples/generate_manifest.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # .../examples
NUM_RE = re.compile(r"^(\d+)_(.+)$")
LABEL_RE = re.compile(r"^\s*(?:#|--|//)\s*label:\s*(.+?)\s*$")
TITLE_RE = re.compile(r"""^\s*#options\.title\s*=\s*["'](.+?)["']\s*$""")
SKIP_DIRS = {"tests"}


def pretty(raw: str) -> str:
    words = raw.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else raw


def folder_label(name: str) -> str:
    m = NUM_RE.match(name)
    if not m:
        return pretty(name)
    return f"{m.group(1)} — {pretty(m.group(2))}"


def label_for(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as f:
            lines = []
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                lines.append(line)

        # First pass: check for label-source rules (# label:, -- label:, // label:)
        for line in lines:
            m = LABEL_RE.match(line)
            if m:
                return m.group(1)

        # Second pass: check for #options.title
        for line in lines:
            m = TITLE_RE.match(line)
            if m:
                return m.group(1)
    except (OSError, UnicodeDecodeError):
        pass

    # Fallback: derive from filename
    stem = path.stem
    m = NUM_RE.match(stem)
    return pretty(m.group(2) if m else stem)


def _scripts_in(folder: Path, root: Path, group: str | None) -> list[dict]:
    out = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and p.suffix == ".txt":
            rel = p.relative_to(root).as_posix()
            out.append({"file": rel, "label": label_for(p), "group": group})
    return out


def build_manifest(root: Path = ROOT) -> dict:
    manifest: dict[str, list] = {}
    for mode_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        name = mode_dir.name
        if name.startswith(".") or name.startswith("_") or name in SKIP_DIRS:
            continue
        entries = _scripts_in(mode_dir, root, None)
        for sub in sorted(p for p in mode_dir.iterdir() if p.is_dir()):
            if sub.name.startswith(".") or sub.name.startswith("_"):
                continue
            entries.extend(_scripts_in(sub, root, folder_label(sub.name)))
        if entries:
            manifest[name] = entries
    return manifest


def main() -> None:
    manifest = build_manifest()
    out = ROOT / "manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    total = sum(len(v) for v in manifest.values())
    print(f"Skrev {out.name} ({len(manifest)} modi, {total} eksempler).")


if __name__ == "__main__":
    main()
