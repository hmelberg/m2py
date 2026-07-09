#!/usr/bin/env python3
"""Genererer js/modes/jmv_specs.js fra jamovi sine YAML-definisjoner.

Kjøring:  python3 tools/gen_jmv_specs.py
Kilder:   tools/jmv_yaml/{jmv,scatr}.yaml — kopier av jamovi-full.yaml fra
          jamovi-appen (samme filer ligger i jamovi sine GitHub-repoer).
"""
import json
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = {'jmv': ROOT / 'tools/jmv_yaml/jmv.yaml',
           'scatr': ROOT / 'tools/jmv_yaml/scatr.yaml'}
UI_DIR = ROOT / 'tools/jmv_yaml/ui'
PHASE1 = ['descriptives', 'ttestIS', 'ttestPS', 'ttestOneS', 'anovaOneW', 'anova',
          'anovaNP', 'corrMatrix', 'linReg', 'logRegBin', 'propTestN', 'contTables',
          'scat', 'ancova', 'corrPart', 'logRegMulti', 'logRegOrd', 'contTablesPaired',
          'reliability', 'pca', 'efa', 'anovaRMNP', 'logLinear', 'mancova']
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
    if t in ('List', 'NMXList'):
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


# u.yaml-typer -> kompakt layout-tre. Ukjente containere flates ut; ukjente
# løvnoder droppes. Se docs/PLAN_jamovi_fase3_dialoglayout.md.

def _parse_enable(expr):
    if isinstance(expr, str):
        m = re.fullmatch(r'\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', expr.strip())
        if m:
            return m.group(1)
    return None


def _group_cells(nodes):
    """Grupper nabosekvenser av _cell-markører i en flat nodeliste til ett
    grid-node hver; behold rekkefølgen på alt annet. Brukes både på toppnivå
    (parse_layout) og for enhver children-liste som bygges underveis
    (Label/CollapseBox kan selv inneholde LayoutBox-celler)."""
    out, buf = [], []

    def flush():
        if buf:
            out.append({'t': 'grid', 'cells': [
                {'col': c['col'], 'row': c['row'], 'children': c['children']}
                for c in sorted(buf, key=lambda c: (c['row'], c['col']))]})
            buf.clear()

    for n in nodes:
        if isinstance(n, dict) and n.get('t') == '_cell':
            buf.append(n)
        else:
            flush()
            out.append(n)
    flush()
    return out


def _layout_node(el, valid, warns):
    """Parser ett u.yaml-element. `cell: {column,row}` er et generelt idiom som
    kan stå på ALLE nodetyper (Label, LayoutBox, ...) — parse noden normalt og
    pakk resultatet i en _cell-markør, så plukker grid-grupperingen den opp."""
    node = _layout_node_inner(el, valid, warns)
    cell = el.get('cell')
    if isinstance(cell, dict) and node is not None:
        return {'t': '_cell', 'col': cell.get('column', 0), 'row': cell.get('row', 0),
                'children': node if isinstance(node, list) else [node]}
    return node


def _layout_node_inner(el, valid, warns):
    t = el.get('type')
    kids = el.get('children') or []

    def parsed_children():
        out = []
        for k in kids:
            n = _layout_node(k, valid, warns)
            if n is None:
                continue
            out.extend(n) if isinstance(n, list) else out.append(n)
        return _group_cells(out)

    def gated(node):
        en = _parse_enable(el.get('enable'))
        if en and en in valid:
            node['enable'] = en
        return node

    if t == 'VariableSupplier':
        targets = []
        def grab(e):
            if e.get('type') == 'VariablesListBox' and e.get('isTarget'):
                tg = {'name': e.get('name')}
                if e.get('maxItemCount'):
                    tg['max'] = e['maxItemCount']
                targets.append(tg)
            for c in (e.get('children') or []):
                grab(c)
        grab(el)
        targets = [tg for tg in targets if tg['name'] in valid or warns.append(f'ukjent rolle {tg["name"]}')]
        return {'t': 'supplier', 'targets': targets}

    if t == 'LayoutBox':
        return parsed_children()   # transparent container -> flat (evt. cell pakkes av _layout_node)

    if t == 'Label':
        ch = parsed_children()
        return gated({'t': 'label', 'label': el.get('label', ''), 'children': ch}) if ch else None

    def hoisted(nm):
        # Ugyldig (2.7.7-drift) navn: dropp selve noden, men behold gyldige
        # etterkommere ved å hoiste dem opp som en flat liste.
        warns.append(f'ukjent opsjon {nm}')
        return parsed_children() or None

    if t == 'CheckBox':
        opt = el.get('optionName')
        if opt is not None:
            # NMXList-del (flervalgs-checkboks): analog til RadioButton, men noden
            # representerer ETT element i en array-verdi (multivar/effectSize/postHocCorr/
            # postHocES o.l.) i stedet for en enkeltverdi. Nøstede barn (sett hos
            # postHocES_d i anova/ancova) disables når DENNE delen ikke er valgt —
            # se checkpart-håndteringen i js/modes/jamovi.js renderJmvLayout.
            if opt not in valid:
                return hoisted(opt)
            part = el.get('optionPart')
            node = {'t': 'checkpart', 'option': opt, 'part': part,
                    'label': el.get('label') or part}
            ch = parsed_children()
            if ch:
                node['children'] = ch
            return gated(node)
        nm = el.get('name')
        if nm not in valid:
            return hoisted(nm)
        node = {'t': 'check', 'name': nm}
        if el.get('label'):
            node['label'] = el['label']
        ch = parsed_children()
        if ch:
            node['children'] = ch
        return gated(node)

    if t == 'RadioButton':
        opt = el.get('optionName')
        if opt not in valid:
            return hoisted(opt)
        return gated({'t': 'radio', 'option': opt, 'part': el.get('optionPart'),
                      'label': el.get('label', el.get('optionPart', ''))})

    if t == 'ComboBox':
        nm = el.get('name')
        if nm not in valid:
            return hoisted(nm)
        return gated({'t': 'combo', 'name': nm, 'label': el.get('label', '')})

    if t == 'TextBox':
        nm = el.get('name')
        if nm not in valid:
            return hoisted(nm)
        node = {'t': 'text', 'name': nm, 'label': el.get('label', '')}
        if el.get('format'):
            node['format'] = str(el['format'])
        return gated(node)

    if t == 'CollapseBox':
        ch = parsed_children()
        return {'t': 'collapse', 'label': el.get('label', ''),
                'collapsed': bool(el.get('collapsed', True)), 'children': ch} if ch else None

    # Ukjent type: container -> flat ut barna; løvnode -> dropp
    ch = parsed_children()
    if ch:
        warns.append(f'flatet ut ukjent type {t}')
        return ch
    return None


def parse_layout(name, valid_names):
    path = UI_DIR / (name.lower() + '.u.yaml')
    if not path.exists():
        return None, []
    doc = yaml.safe_load(path.read_text())
    warns = []
    children = []
    for el in (doc.get('children') or []):
        n = _layout_node(el, valid_names, warns)
        if n is None:
            continue
        children.extend(n) if isinstance(n, list) else children.append(n)
    return {'t': 'root', 'children': _group_cells(children)}, warns


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
    for name, spec in specs.items():
        valid_names = {o['name'] for o in spec['options']}
        lay, warns = parse_layout(name, valid_names)
        if lay:
            spec['layout'] = lay
        for w in warns:
            print(f'{name}: {w}')
    js = ('// GENERERT av tools/gen_jmv_specs.py — ikke rediger for hånd.\n'
          'window.JMV_SPECS = '
          + json.dumps(specs, ensure_ascii=False, indent=1) + ';\n')
    (ROOT / 'js/modes/jmv_specs.js').write_text(js)
    print(f'Skrev {len(specs)} analyser til js/modes/jmv_specs.js')


if __name__ == '__main__':
    main()
