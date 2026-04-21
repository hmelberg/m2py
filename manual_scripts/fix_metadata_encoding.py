"""One-time repair for mojibake in variable_metadata.json.

The file contains double-encoded UTF-8: originally-correct UTF-8 bytes were
read as Windows-1252 (cp1252) and re-saved as UTF-8. E.g. bytes c3 b8 (ø)
became four chars Ã¸ (U+00C3 U+00B8), and e2 88 9e (∞) became âˆž (U+00E2
U+02C6 U+017E, where 0x88 -> U+02C6 and 0x9E -> U+017E are cp1252-specific).

Strategy per string: try s.encode('cp1252').decode('utf-8'). If that succeeds
it was mojibake -> use the repaired form. If the encode or decode fails, leave
the string as-is. This protects already-correct strings like "Tromsø" (its ø
is byte 0xf8, an invalid UTF-8 lead byte, so the decode step raises).
"""

import json
from pathlib import Path

PATH = Path(__file__).parent / "variable_metadata.json"


def try_repair(s: str):
    # Strings with no non-ASCII can't be mojibake; skip the encode roundtrip.
    if all(ord(c) < 0x80 for c in s):
        return None
    try:
        fixed = s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if fixed == s:
        return None
    return fixed


def repair_string(s, repairs):
    fixed = try_repair(s)
    if fixed is not None:
        repairs.append((s, fixed))
        return fixed
    return s


def walk(obj, repairs):
    if isinstance(obj, dict):
        return {repair_string(k, repairs): walk(v, repairs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [walk(v, repairs) for v in obj]
    if isinstance(obj, str):
        return repair_string(obj, repairs)
    return obj


def main():
    with open(PATH, encoding="utf-8") as f:
        data = json.load(f)

    repairs: list[tuple[str, str]] = []
    repaired = walk(data, repairs)

    with open(PATH, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(repaired, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Repaired {len(repairs)} strings.")
    print()
    print("--- First 5 repairs ---")
    for before, after in repairs[:5]:
        print(f"  {before[:70]!r}")
        print(f"  -> {after[:70]!r}")
        print()


if __name__ == "__main__":
    main()
