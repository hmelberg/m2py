# Ende-til-ende for `# meta` → DataFrame.attrs['meta'] (2026-07-26).
#
# Kjeden: js/data-directives.js metaByTarget() former direktivene →
# motorenes buildDatasetSpec() hekter dem på spec-oppføringen →
# runnerens _bind_datasets() legger dem på framen. Testen kjører JS-leddet
# i node og python-leddet direkte, og sjekker at formen matcher.
import json
import os
import subprocess
import shutil
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'brython'))
sys.path.insert(0, os.path.join(ROOT, 'micropython'))

SCRIPT = '\n'.join([
    '# load ssb/07459 as boliger',
    '# meta boliger Kilde: SSB tabell 07459',
    '# meta boliger https://www.ssb.no/07459 Tabellside',
    '# meta boliger.region Fylkesinndeling per 2024',
    '# meta urelatert Skal ikke havne paa boliger',
])


def _meta_by_target(script):
    """
    Kjør JS-leddet. `# meta` er en openstat-funksjon — safestat sin
    data-directives.js har ikke META_RE i det hele tatt, så testene som
    krever den hoppes over der i stedet for å feile.
    """
    if shutil.which('node') is None:
        pytest.skip('node er ikke installert')
    js = ("global.window = global;"
          "require(process.argv[1]);"
          "const src = require('fs').readFileSync(0, 'utf8');"
          "if (typeof DataDirectives.metaByTarget !== 'function') "
          "{ process.stdout.write('null'); } else "
          "{ process.stdout.write(JSON.stringify(DataDirectives.metaByTarget(src))); }")
    r = subprocess.run(['node', '-e', js, os.path.join(ROOT, 'js', 'data-directives.js')],
                       input=script, capture_output=True, text=True, check=True)
    got = json.loads(r.stdout)
    if got is None:
        pytest.skip('dette repoet har ikke `# meta`-direktivet')
    return got


def test_meta_by_target_shape():
    got = _meta_by_target(SCRIPT)
    assert got['boliger']['text'] == ['Kilde: SSB tabell 07459']
    assert got['boliger']['links'] == [
        {'url': 'https://www.ssb.no/07459', 'label': 'Tabellside'}]
    assert got['boliger']['variables']['region']['text'] == ['Fylkesinndeling per 2024']
    assert 'urelatert' in got and 'boliger' not in got['urelatert']['text']


@pytest.mark.parametrize('runner_mod,pandas_mod', [
    ('brython_runner', 'pandas_brython'),
    ('micropython_runner', 'pandas_mpy'),
])
def test_bind_datasets_puts_meta_on_attrs(runner_mod, pandas_mod):
    runner = __import__(runner_mod)
    pd = __import__(pandas_mod)
    meta = _meta_by_target(SCRIPT)['boliger']
    spec = {'boliger': {'kind': 'csv', 'payload': 'region,verdi\nOslo,1\nViken,2\n',
                        'meta': meta}}
    err = runner._bind_datasets(json.dumps(spec))
    assert err == '', err
    df = runner._shared_vars['boliger']
    assert isinstance(df, pd.DataFrame)
    assert df.attrs['meta']['text'] == ['Kilde: SSB tabell 07459']
    assert df.attrs['meta']['links'][0]['url'] == 'https://www.ssb.no/07459'
    assert df.attrs['meta']['variables']['region']['text'] == ['Fylkesinndeling per 2024']
    # aliaset havner på df.name, og begge deler overlever avledning
    assert df.name == 'boliger'
    assert df.head(1).attrs['meta']['text'] == ['Kilde: SSB tabell 07459']
    assert df['region'].attrs['meta']['text'] == ['Kilde: SSB tabell 07459']


@pytest.mark.parametrize('runner_mod', ['brython_runner', 'micropython_runner'])
def test_bind_datasets_without_meta_still_works(runner_mod):
    runner = __import__(runner_mod)
    spec = {'rene_data': {'kind': 'csv', 'payload': 'a\n1\n'}}
    err = runner._bind_datasets(json.dumps(spec))
    assert err == '', err
    df = runner._shared_vars['rene_data']
    assert df.attrs == {}
    assert df.name == 'rene_data'


@pytest.mark.parametrize('runner_mod', ['brython_runner', 'micropython_runner'])
def test_dataset_info_reports_real_dtypes(runner_mod):
    # dtypes var hardkodet {} fram til 2026-07-26
    runner = __import__(runner_mod)
    if not hasattr(runner, '_dataset_info'):
        pytest.skip('runneren i dette repoet har ikke sidebar-refleksjon')
    spec = {'typer': {'kind': 'csv', 'payload': 'i,f,s\n1,1.5,a\n2,2.5,b\n'}}
    assert runner._bind_datasets(json.dumps(spec)) == ''
    info = json.loads(runner._dataset_info())
    assert info['typer']['dtypes'] == {'i': 'int64', 'f': 'float64', 's': 'object'}, \
        info['typer']['dtypes']
    assert info['typer']['nrows'] == 2


@pytest.mark.parametrize('runner_mod', ['brython_runner', 'micropython_runner'])
def test_dataset_rows_reports_real_dtypes(runner_mod):
    # ⊞-modalen gjettet selv og kunne bare skille float64 fra object; nå
    # skiller den int64/float64/object og ser hele kolonnen.
    runner = __import__(runner_mod)
    if not hasattr(runner, '_dataset_rows'):
        pytest.skip('runneren i dette repoet har ikke individata-modalen')
    spec = {'tabell': {'kind': 'csv', 'payload': 'i,f,s\n1,1.5,a\n2,2.5,b\n'}}
    assert runner._bind_datasets(json.dumps(spec)) == ''
    got = json.loads(runner._dataset_rows('tabell'))
    assert got['dtypes'] == {'i': 'int64', 'f': 'float64', 's': 'object'}, got['dtypes']
    assert got['total_rows'] == 2
