"""Runner for extracted manual scripts.

For each .txt file in this directory, runs it through MicroInterpreter,
captures output and errors, and prints a summary.
"""
import sys
import time
import traceback
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from m2py import MicroInterpreter


def find_metadata():
    root = Path(__file__).resolve().parent.parent
    p = root / 'variable_metadata.json'
    return p if p.exists() else None


def run_one_script(script_path: Path, meta_path) -> dict:
    script_text = script_path.read_text(encoding='utf-8')
    engine = MicroInterpreter(metadata_path=meta_path)

    result = {
        'name': script_path.stem,
        'status': 'UNKNOWN',
        'output': '',
        'error': None,
        'tb': None,
        'feil_lines': [],
        'duration_s': 0.0,
    }

    start = time.time()
    try:
        output = engine.run_script(script_text)
        result['output'] = output or ''
        result['duration_s'] = time.time() - start

        feil = [l for l in (output or '').splitlines() if 'FEIL' in l.upper()]
        result['feil_lines'] = feil
        result['status'] = 'PARTIAL' if feil else 'OK'

    except Exception as e:
        result['duration_s'] = time.time() - start
        result['status'] = 'CRASH'
        result['error'] = str(e)
        result['tb'] = traceback.format_exc()

    return result


def main():
    meta = find_metadata()
    if not meta:
        print("WARNING: variable_metadata.json not found")

    script_dir = Path(__file__).resolve().parent
    scripts = sorted(script_dir.glob('[0-9]*.txt'))

    if not scripts:
        print("No scripts found in", script_dir)
        return

    print(f"Found {len(scripts)} scripts. Metadata: {meta}\n")
    results = []

    for sp in scripts:
        print(f"  Running {sp.name} ...", end=' ', flush=True)
        r = run_one_script(sp, meta)
        n_feil = len(r['feil_lines'])
        tag = r['status']
        if r['status'] == 'PARTIAL':
            tag = f"PARTIAL ({n_feil} FEIL)"
        print(f"[{tag}] ({r['duration_s']:.1f}s)")
        results.append(r)

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok = sum(1 for r in results if r['status'] == 'OK')
    partial = sum(1 for r in results if r['status'] == 'PARTIAL')
    crash = sum(1 for r in results if r['status'] == 'CRASH')
    print(f"  OK: {ok}  |  PARTIAL: {partial}  |  CRASH: {crash}  |  Total: {len(results)}")

    # Print details for non-OK scripts
    for r in results:
        if r['status'] == 'OK':
            continue
        print(f"\n--- {r['name']} [{r['status']}] ---")
        if r['error']:
            print(f"  Exception: {r['error']}")
        for fl in r['feil_lines']:
            print(f"  FEIL: {fl.strip()}")

    return results


if __name__ == '__main__':
    main()
