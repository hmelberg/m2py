# scanImports-tests: kjører engine-JS-en i node (ingen DOM trengs — IIFE-en
# definerer bare funksjoner og setter globalThis.BrythonEngine).
import json, os, shutil, subprocess
import pytest

ENGINE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'js', 'brython-engine.js'))

def scan(code):
    if shutil.which('node') is None:
        pytest.skip('node er ikke installert')
    js = ("require(process.argv[1]);"
          "const code = require('fs').readFileSync(0, 'utf8');"
          "process.stdout.write(JSON.stringify("
          "globalThis.BrythonEngine._scanImports(code)));")
    r = subprocess.run(['node', '-e', js, ENGINE],
                       input=code, capture_output=True, text=True, check=True)
    return json.loads(r.stdout)

def test_plain_import():
    assert scan('import pandas_brython as pd') == ['pandas_brython']

def test_from_import():
    assert scan('from plotly_express_brython import bar') == ['plotly_express_brython']

def test_comma_separated_imports():
    assert scan('import json, pandas_brython') == ['pandas_brython']

def test_unknown_modules_ignored():
    assert scan('import os\nimport sys\nx = 1') == []

def test_indented_import_found():
    assert scan('def f():\n    import pandas_brython\n') == ['pandas_brython']

def test_no_duplicates_first_mention_order():
    code = ('import plotly_express_brython\n'
            'import pandas_brython\n'
            'import plotly_express_brython\n')
    assert scan(code) == ['plotly_express_brython', 'pandas_brython']

def test_dotted_import_matches_first_segment():
    # Framtidige libs (matplotlib.pyplot); i dag: dotted form av kjent navn.
    assert scan('import pandas_brython.whatever') == ['pandas_brython']

def test_import_mid_line_not_matched_but_string_line_start_overmatches():
    # 'import' midt på en linje matcher ikke (regexen krever linjestart)...
    assert scan('x = "import pandas_brython"\nprint(x)') == []
    # ...men en docstring-LINJE som starter med 'import' over-matcher.
    # AKSEPTERT: harmløst — registrerer bare en lib koden aldri bruker.
    assert scan('s = """\nimport pandas_brython\n"""') == ['pandas_brython']
