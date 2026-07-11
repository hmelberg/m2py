# Kildekode-vakt mot Brython-fellen (verifisert 2026-07-11): en metode som
# refererer en global funksjon med SAMME navn som metoden blir stille en
# no-op i Brython 3.12 (CPython er korrekt, så vanlige tester er blinde).
# Testen bruker ast — den kjører kun i CPython (pytest), aldri i Brython.
import ast, glob, os

BRYTHON_DIR = os.path.join(os.path.dirname(__file__), '..')

def test_no_method_global_name_collisions():
    offenders = []
    for path in sorted(glob.glob(os.path.join(BRYTHON_DIR, '*.py'))):
        with open(path) as f:
            tree = ast.parse(f.read())
        module_funcs = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for meth in node.body:
                if not isinstance(meth, ast.FunctionDef) or meth.name not in module_funcs:
                    continue
                for sub in ast.walk(meth):
                    if (isinstance(sub, ast.Name) and sub.id == meth.name
                            and isinstance(sub.ctx, ast.Load)):
                        offenders.append('%s: %s.%s' % (
                            os.path.basename(path), node.name, meth.name))
                        break
    assert offenders == [], (
        'Brython-felle: metode refererer global med samme navn som metoden '
        '(stille no-op i Brython) — bruk underscore-alias som i '
        'matplotlib_brython.py: ' + ', '.join(offenders))

def test_no_setdefault_with_nonstring_keys():
    """Brython-felle 2 (verifisert 2026-07-11): dict.setdefault stringifiserer
    ikke-streng-nøkler i Brython 3.12 (tuple/int-nøkler blir ufinnbare).
    Kun setdefault med streng-LITERAL som nøkkel er tillatt i brython/*.py —
    ellers: eksplisitt `if k not in d: d[k] = ...`."""
    offenders = []
    for path in sorted(glob.glob(os.path.join(BRYTHON_DIR, '*.py'))):
        with open(path) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'setdefault'
                    and node.args
                    and not (isinstance(node.args[0], ast.Constant)
                             and isinstance(node.args[0].value, str))):
                offenders.append('%s:%d' % (os.path.basename(path), node.lineno))
    assert offenders == [], (
        'setdefault med ikke-streng-litteral nøkkel (Brython-felle): '
        + ', '.join(offenders))
