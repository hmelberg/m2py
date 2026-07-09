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
              'scat', 'ancova', 'corrPart', 'logRegMulti', 'logRegOrd', 'contTablesPaired',
              'reliability', 'pca', 'efa', 'anovaRMNP', 'logLinear', 'mancova']:
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


def _find(node, pred):
    """Depth-first søk i layout-treet."""
    if pred(node):
        return node
    for child in (node.get('children') or []):
        hit = _find(child, pred)
        if hit:
            return hit
    for cell in (node.get('cells') or []):
        hit = _find({'children': cell.get('children') or []}, pred)
        if hit:
            return hit
    return None


def test_layout_ttestIS_struktur():
    s = load_specs()
    lay = s['ttestIS'].get('layout')
    assert lay and lay['t'] == 'root'
    assert _find(lay, lambda n: n.get('t') == 'supplier')
    tests_grp = _find(lay, lambda n: n.get('t') == 'label' and n.get('label') == 'Tests')
    assert tests_grp is not None
    students = _find(tests_grp, lambda n: n.get('t') == 'check' and n.get('name') == 'students')
    assert students is not None
    bf = _find(students, lambda n: n.get('t') == 'check' and n.get('name') == 'bf')
    assert bf is not None, 'bf skal være nøstet under students'
    bfprior = _find(bf, lambda n: n.get('t') == 'text' and n.get('name') == 'bfPrior')
    assert bfprior is not None and bfprior.get('enable') == 'bf'
    radio = _find(lay, lambda n: n.get('t') == 'radio' and n.get('option') == 'hypothesis'
                  and n.get('part') == 'oneGreater')
    assert radio is not None


def test_layout_gyldige_navn_og_dekning():
    s = load_specs()
    med_layout = [n for n in s if s[n].get('layout')]
    assert len(med_layout) >= 10, f'for få layouts: {med_layout}'
    for n in med_layout:
        gyldige = {o['name'] for o in s[n]['options']}
        def sjekk(node):
            nm = node.get('name') or node.get('option')
            if nm is not None:
                assert nm in gyldige, f'{n}: layout refererer ukjent opsjon {nm}'
            for t in (node.get('targets') or []):
                assert t['name'] in gyldige, f"{n}: ukjent rolle {t['name']} (nøstet supplier)"
            for c in (node.get('children') or []):
                sjekk(c)
            for cell in (node.get('cells') or []):
                for c in (cell.get('children') or []):
                    sjekk(c)
        for barn in s[n]['layout']['children']:
            if barn.get('t') == 'supplier':
                for t in barn['targets']:
                    assert t['name'] in gyldige, f"{n}: ukjent rolle {t['name']}"
            else:
                sjekk(barn)


def test_layout_descriptives_har_seksjoner():
    s = load_specs()
    lay = s['descriptives'].get('layout')
    assert lay is not None
    assert _find(lay, lambda n: n.get('t') == 'collapse'), 'descriptives skal ha CollapseBox'


def test_layout_corrMatrix_har_grid():
    # Regresjonsvakt: cell:-idiomet ligger direkte på Label-noder i corrmatrix.u.yaml,
    # ikke bare på LayoutBox — de fire seksjonene skal bli et 2x2-grid.
    s = load_specs()
    lay = s['corrMatrix'].get('layout')
    assert lay is not None
    grid = _find(lay, lambda n: n.get('t') == 'grid' and len(n.get('cells') or []) >= 2)
    assert grid is not None, 'corrMatrix skal ha minst ett grid med >= 2 celler'


def test_layout_ancova_struktur():
    # Task 3: ancova skal ha en supplier med dep/factors/covs-roller (samme
    # mønster som anova, men med kovariater i tillegg).
    s = load_specs()
    lay = s['ancova'].get('layout')
    assert lay and lay['t'] == 'root'
    sup = _find(lay, lambda n: n.get('t') == 'supplier' and n.get('targets'))
    assert sup is not None
    names = {t['name'] for t in sup['targets']}
    assert {'dep', 'factors', 'covs'} <= names, f'ancova supplier mangler roller: {names}'


def test_layout_anova_hoister_gyldige_barn():
    # Regresjonsvakt: postHocES_d er en NMXList-checkpart (optionName: postHocES,
    # optionPart: d) — den skal IKKE hoistes/droppes lenger (det gjorde den før
    # checkpart-støtten kom inn), og dens gyldige etterkommer postHocEsCi skal
    # fortsatt finnes i treet (nøstet under checkpart-noden).
    s = load_specs()
    lay = s['anova'].get('layout')
    assert lay is not None
    d = _find(lay, lambda n: n.get('t') == 'checkpart' and n.get('option') == 'postHocES'
              and n.get('part') == 'd')
    assert d is not None, 'postHocES_d skal bli en checkpart-node, ikke hoistes bort'
    assert _find(d, lambda n: n.get('name') == 'postHocEsCi'), \
        'postHocEsCi skal overleve nøstet under postHocES-checkparten'


def test_layout_mancova_checkpart_og_nmxlist_choices():
    # Task: MANCOVA i menyen + NMXList-checkparts. multivar_pillai i mancova.u.yaml
    # skal bli en checkpart-node {option: multivar, part: pillai}, og selve
    # multivar-opsjonen skal ha choices (samme normalisering som List).
    s = load_specs()
    assert s['mancova']['menuGroup'] == 'ANOVA'
    lay = s['mancova'].get('layout')
    assert lay is not None
    pillai = _find(lay, lambda n: n.get('t') == 'checkpart' and n.get('option') == 'multivar'
                    and n.get('part') == 'pillai')
    assert pillai is not None, 'multivar_pillai skal bli en checkpart-node'
    opts = {o['name']: o for o in s['mancova']['options']}
    assert opts['multivar']['type'] == 'NMXList'
    assert {c['value'] for c in opts['multivar']['choices']} == {'pillai', 'wilks', 'hotel', 'roy'}
    assert opts['multivar']['default'] == ['pillai', 'wilks', 'hotel', 'roy']


def test_layout_checkpart_dekket_av_flere_valg_sikkerhetsnett_ikke_duplisert():
    # NMXList er ikke en av SCALAR_LAYOUT_TYPES i js/modes/jamovi.js (Bool/List/Number/
    # Integer/String) — det skalar-baserte "Flere valg"-sikkerhetsnettet skal derfor
    # aldri prøve å tegne en NMXList-opsjon på nytt utenfor layoutet. Denne testen er en
    # regresjonsvakt for at ingen tidligere gjenstridige checkpart-drift-advarsler dukker
    # opp igjen for anova/ancova sine tre NMXList-opsjoner.
    s = load_specs()
    for n in ('anova', 'ancova'):
        lay = s[n]['layout']
        for opt in ('effectSize', 'postHocCorr', 'postHocES'):
            assert _find(lay, lambda node, opt=opt: node.get('t') == 'checkpart'
                         and node.get('option') == opt), f'{n}: {opt} mangler checkpart-noder'
