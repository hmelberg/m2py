#!/usr/bin/env python3
"""
py2m CLI — translate Python/pandas code to a microdata.no script.

Usage:
    python cli.py input.py
    python cli.py input.py --df mydf
    python cli.py input.py -o output.microdata
    python cli.py input.py --warnings
"""
import argparse
import sys
from py2m import transform


def main():
    parser = argparse.ArgumentParser(
        description="Translate Python/pandas code to microdata.no script"
    )
    parser.add_argument("input", help="Python source file to translate (use - for stdin)")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    parser.add_argument(
        "--df", default="df", metavar="NAME",
        help="Name of the main DataFrame variable (default: df)"
    )
    parser.add_argument(
        "--warnings", action="store_true",
        help="Print warnings to stderr"
    )
    args = parser.parse_args()

    if args.input == "-":
        source = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as f:
            source = f.read()

    result = transform(source, df_name=args.df)

    script = result.script()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(script + "\n")
    else:
        print(script)

    if args.warnings and result.warnings:
        for w in result.warnings:
            print(f"WARNING: {w}", file=sys.stderr)
    elif result.warnings:
        print(f"\n// {len(result.warnings)} warning(s) — run with --warnings to see details",
              file=sys.stderr)


if __name__ == "__main__":
    main()
