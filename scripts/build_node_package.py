"""Vendorer motoren inn i node/safestat_node/_engine/ før pip-bygging.
Kjør på nytt etter enhver motorendring (samme disiplin som sync_to_api.py)."""
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENGINE = ROOT / "node" / "safestat_node" / "_engine"
FILES = ["m2py.py", "m2py_remote.py", "m2py_translate.py", "m2py_protection.py",
         "protect.py", "functions.py", "mockdata_core.py"]

if ENGINE.exists():
    shutil.rmtree(ENGINE)
(ENGINE / "m2py_runtime").mkdir(parents=True)
for f in FILES:
    shutil.copy2(ROOT / f, ENGINE / f)
for p in sorted((ROOT / "m2py_runtime").glob("*.py")):
    shutil.copy2(p, ENGINE / "m2py_runtime" / p.name)
print("vendored:", len(FILES) + len(list((ENGINE / "m2py_runtime").glob("*.py"))), "filer")
