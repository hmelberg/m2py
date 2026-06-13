import sys
from pathlib import Path

# Gjør m2py.py, functions.py og protect.py i repo-roten importerbare fra tests/
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

# Pre-importer m2py FØR py2m legges på stien. Både repo-roten og py2m/ har en
# functions.py; m2py må binde repo-rotens (ellers mangler ln/rowmax m.m. i
# generate-eval). Når den er importert, er den cachet i sys.modules.
import functions  # noqa: F401,E402
import m2py       # noqa: F401,E402

# Deretter: gjør py2m-pakken importerbar for ekvivalens-harnessen.
sys.path.insert(0, str(_root / "py2m"))
