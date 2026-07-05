"""--web target: zip the safepy package for Pyodide (browser strict runs)."""
import subprocess
import sys
import zipfile
from pathlib import Path

import sync_to_api

ROOT = Path(sync_to_api.__file__).resolve().parent
SAFEPY_ROOT = ROOT.parent / "safepy" / "safepy"


def test_build_web_zip_members_and_importability(tmp_path):
    out = tmp_path / "safepy.zip"
    members = sync_to_api.build_web_zip(SAFEPY_ROOT, out)
    assert "safepy/__init__.py" in members
    assert "safepy/client_shape.py" in members
    assert "safepy/encfile.py" in members
    assert any(m.startswith("safepy/adapters/") for m in members)
    assert "protect.py" in members          # safepy delegerer undertrykking til protect
    with zipfile.ZipFile(out) as z:
        header = z.read("safepy/client_shape.py").decode()
    assert "GENERATED COPY" in header

    # the archive must be importable as a package (what Pyodide will do)
    ex = tmp_path / "x"
    with zipfile.ZipFile(out) as z:
        z.extractall(ex)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]); "
         "from safepy import client_shape, encfile; "
         "print(client_shape.error_shape('s', 'm')['err'])",
         str(ex)],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "m"
