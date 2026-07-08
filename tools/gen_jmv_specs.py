#!/usr/bin/env python3
"""Genererer js/modes/jmv_specs.js fra jamovi sine YAML-definisjoner.

Kjøring:  python3 tools/gen_jmv_specs.py
Kilder:   tools/jmv_yaml/{jmv,scatr}.yaml — kopier av jamovi-full.yaml fra
          jamovi-appen (samme filer ligger i jamovi sine GitHub-repoer).
"""
import json
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = {'jmv': ROOT / 'tools/jmv_yaml/jmv.yaml',
           'scatr': ROOT / 'tools/jmv_yaml/scatr.yaml'}
PHASE1 = ['descriptives', 'ttestIS', 'ttestPS', 'ttestOneS', 'anovaOneW', 'anova',
          'anovaNP', 'corrMatrix', 'linReg', 'logRegBin', 'propTestN', 'contTables',
          'scat']
# pareto finnes ikke i CRAN/wasm-scatr 1.0.1 — fase 2 når nyere scatr bygges som wasm.
ROLE_TYPES = {'Variable', 'Variables', 'Pairs'}
SKIP_TYPES = {'Data', 'Output'}


def convert_option(o):
    t = o.get('type')
    if t in SKIP_TYPES or o.get('hidden'):
        return None
    out = {'name': o['name'], 'type': t,
           'title': o.get('title') or o['name'], 'default': o.get('default')}
    if t in ROLE_TYPES:
        out['suggested'] = o.get('suggested') or []
        out['permitted'] = o.get('permitted') or []
    if t == 'List':
        out['choices'] = [
            {'value': c.get('name'), 'title': c.get('title', c.get('name'))}
            if isinstance(c, dict) else {'value': c, 'title': c}
            for c in (o.get('options') or [])]
    if t in ('Number', 'Integer'):
        if o.get('min') is not None:
            out['min'] = o.get('min')
        if o.get('max') is not None:
            out['max'] = o.get('max')
    return out


def main():
    specs = {}
    for ns, path in SOURCES.items():
        for doc in yaml.safe_load_all(path.read_text()):
            if not isinstance(doc, dict):
                continue
            for a in doc.get('analyses', []):
                name = a.get('name')
                if name not in PHASE1:
                    continue
                # scatr har duplikate oppføringer per analyse: én med
                # menuGroup '.'/'More' som bærer hele options-listen, og én
                # menyplasserings-stub (f.eks. 'Exploration') uten options.
                # Flett: options fra oppføringen som har dem, menyfelter fra
                # oppføringen som ikke er '.'/'More'.
                opts = [o for o in (convert_option(o)
                                    for o in a.get('options') or []) if o]
                is_menu_entry = a.get('menuGroup') not in ('.', 'More')
                spec = specs.get(name)
                if spec is None:
                    spec = specs[name] = {
                        'name': name, 'ns': ns, 'title': a.get('title'),
                        'menuGroup': None, 'menuSubgroup': '',
                        'menuTitle': None, 'menuSubtitle': '',
                        'options': [],
                    }
                if opts and not spec['options']:
                    spec['options'] = opts
                if is_menu_entry and spec['menuGroup'] is None:
                    spec.update(
                        title=a.get('title'),
                        menuGroup=a.get('menuGroup'),
                        menuSubgroup=a.get('menuSubgroup') or '',
                        menuTitle=a.get('menuTitle'),
                        menuSubtitle=a.get('menuSubtitle') or '')
    missing = [n for n in PHASE1 if n not in specs]
    if missing:
        raise SystemExit(f'Mangler analyser i YAML: {missing}')
    js = ('// GENERERT av tools/gen_jmv_specs.py — ikke rediger for hånd.\n'
          'window.JMV_SPECS = '
          + json.dumps(specs, ensure_ascii=False, indent=1) + ';\n')
    (ROOT / 'js/modes/jmv_specs.js').write_text(js)
    print(f'Skrev {len(specs)} analyser til js/modes/jmv_specs.js')


if __name__ == '__main__':
    main()
