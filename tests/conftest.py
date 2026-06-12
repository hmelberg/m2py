import sys
from pathlib import Path

# Gjør m2py.py, functions.py og protect.py i repo-roten importerbare fra tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
