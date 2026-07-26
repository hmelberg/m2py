# Størrelsesbudsjett for pandas-shimene, og en kjøring av
# differensialtestene mot MicroPython-porten.
#
# Bakgrunn: i brython-modus må hver kilde-KB hentes over nett OG kompileres av
# Brython i JavaScript, så filstørrelse er en direkte ytelseskostnad.
#
# Dette er en FARTSDUMP, ikke et forbud. Å la kjernen vokse er noen ganger
# helt riktig — en feature som hører hjemme i Series/DataFrame blir dårligere
# av å presses ut i en egen pakke. Poenget med testen er at veksten skal være
# et bevisst valg og ikke skje umerket. Treffer du taket: vurder om en egen,
# token-lastet pakke (LIB_REGISTRY.tokens) passer bedre, og hvis ikke — hev
# grensen og skriv hvorfor i commit-meldingen.
#
# Spec: docs/superpowers/specs/2026-07-26-pandas-parity-design.md
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# Grenser satt 2026-07-26 med romslig margin over faktisk størrelse (181 og
# 194 KB) — de skal fange løpsk vekst, ikke normal utvikling.
BUDGET_KB = {
    'brython/pandas_brython.py': 260,
    'micropython/pandas_mpy.py': 275,
}


@pytest.mark.parametrize('rel_path,limit_kb', sorted(BUDGET_KB.items()))
def test_shim_size_within_budget(rel_path, limit_kb):
    # microdata har brython-modus men ikke micropython — hopp over det som
    # ikke finnes i dette repoet i stedet for å feile.
    full = os.path.join(ROOT, rel_path)
    if not os.path.exists(full):
        pytest.skip('%s finnes ikke i dette repoet' % rel_path)
    size_kb = os.path.getsize(full) / 1024
    assert size_kb <= limit_kb, (
        '%s er %.1f KB, over fartsdumpen på %d KB. Det er ikke nødvendigvis '
        'feil — vurder om en egen token-lastet pakke passer bedre, og hev '
        'ellers grensen bevisst og begrunn den i commit-meldingen.'
        % (rel_path, size_kb, limit_kb))


def test_import_pandas_does_not_cost_plotly():
    """
    `import pandas_*` skal ikke lenger dra med seg plotly. Regnestykket for en
    økt UTEN plotting: 181 KB i stedet for 181+144 KB.
    """
    checked = 0
    for engine, pandas_mod, plotly_mod in (
            ('js/brython-engine.js', 'pandas_brython', 'plotly_express_brython'),
            ('js/micropython-engine.js', 'pandas_mpy', 'plotly_express_mpy')):
        if not os.path.exists(os.path.join(ROOT, engine)):
            continue          # microdata har ingen micropython-motor
        checked += 1
        src = open(os.path.join(ROOT, engine)).read()
        line = [ln for ln in src.splitlines()
                if ln.strip().startswith(pandas_mod + ':')]
        assert len(line) == 1, 'fant ikke %s-oppføringen i %s' % (pandas_mod, engine)
        assert plotly_mod not in line[0], (
            '%s har fått plotly som deps igjen i %s — da betaler alle '
            'pandas-økter for 144 KB de ikke bruker.' % (pandas_mod, engine))
        assert "tokens: ['.plot']" in src, (
            'token-triggeren for plotly mangler i %s' % engine)
    assert checked, 'fant ingen motorfiler å sjekke'


def test_differential_suite_passes_against_micropython_port():
    """
    Kjører hele paritetssuiten mot micropython/pandas_mpy.py. Portene er
    divergerende kopier, så API-likhet er ikke nok — semantikken må testes.
    """
    if not os.path.exists(os.path.join(ROOT, 'micropython', 'pandas_mpy.py')):
        pytest.skip('dette repoet har ikke micropython-modus')
    env = dict(os.environ)
    env['PANDAS_SHIM'] = 'mpy'
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__),
                                      'test_pandas_parity_diff.py')],
        capture_output=True, text=True, env=env, cwd=ROOT)
    assert result.returncode == 0, (
        'differensialtestene feiler mot mpy-porten:\n%s' % result.stdout[-3000:])
