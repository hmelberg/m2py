"""Tester for tools/gen_jmv_specs.py — genererer js/modes/jmv_specs.js fra jamovi-YAML."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_specs():
    subprocess.run([sys.executable, str(ROOT / 'tools/gen_jmv_specs.py')], check=True)
    txt = (ROOT / 'js/modes/jmv_specs.js').read_text()
    return json.loads(txt[txt.index('=') + 1:].rstrip().rstrip(';'))


def test_alle_fase1_analyser_er_med():
    s = load_specs()
    for n in ['descriptives', 'ttestIS', 'ttestPS', 'ttestOneS', 'anovaOneW', 'anova',
              'anovaNP', 'corrMatrix', 'linReg', 'logRegBin', 'propTestN', 'contTables',
              'scat']:
        assert n in s, n
        assert len(s[n]['options']) > 0, f'{n} har ingen opsjoner'


def test_ttestIS_opsjoner():
    s = load_specs()
    opts = {o['name']: o for o in s['ttestIS']['options']}
    assert opts['welchs']['type'] == 'Bool' and opts['welchs']['default'] is False
    assert opts['vars']['type'] == 'Variables'
    assert opts['hypothesis']['type'] == 'List'
    assert any(c['value'] == 'different' for c in opts['hypothesis']['choices'])
    assert 'data' not in opts  # Data-typen skal filtreres bort


def test_descriptives_har_statistikk_og_plottopsjoner():
    s = load_specs()
    names = [o['name'] for o in s['descriptives']['options']]
    for n in ['hist', 'box', 'violin', 'bar', 'sd', 'skew', 'kurt', 'pcValues', 'splitBy']:
        assert n in names, n


def test_scat_har_opsjoner_og_riktig_meny():
    s = load_specs()
    assert s['scat']['menuGroup'] == 'Exploration'
    scat_names = [o['name'] for o in s['scat']['options']]
    for n in ['x', 'y', 'group']:
        assert n in scat_names, n


def test_menygrupper():
    s = load_specs()
    assert s['descriptives']['menuGroup'] == 'Exploration'
    assert s['scat']['menuGroup'] == 'Exploration'     # ikke '.'-oppføringen
    assert s['anovaNP']['menuSubgroup'] == 'Non-Parametric'
