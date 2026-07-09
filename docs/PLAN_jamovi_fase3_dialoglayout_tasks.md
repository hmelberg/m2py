# jamovi fase 3 del 1 — implementeringsplan: dialog-layout fra u.yaml

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opsjonspanelene i jamovi-modus rendres fra jamovi sine egne u.yaml-layoutfiler — grupper, rutenett, nøstede/deaktiverbare under-opsjoner, radiogrupper og seksjoner — i stedet for dagens flate håndkurerte lister.

**Architecture:** `tools/gen_jmv_specs.py` får et u.yaml-parsesteg som legger et kompakt `layout`-tre på hver analyse i `js/modes/jmv_specs.js`; `js/modes/jamovi.js` får `renderJmvLayout()` som tegner treet og erstatter `JMV_SECTIONS`-løypa (med dagens flate rendering som fallback). Designdok: `docs/PLAN_jamovi_fase3_dialoglayout.md`.

**Tech Stack:** Python 3 + PyYAML + pytest (generator), vanilla JS IIFE + CSS (renderer), Chrome DevTools MCP (visuell verifisering).

## Global Constraints

- Motor-kontrakten er uendret: `values`-formen (roller = array, andre = skalar), `buildJmvCall`, `runJmvAnalysis`, live-oppdatering med `scheduleRun` og stale-guard skal IKKE endres.
- Layout-treet kan ALDRI referere et opsjonsnavn som ikke finnes i analysens `options` (generatoren validerer og dropper med varsel til stdout).
- Analyser uten `layout` (eller med parse-feil) skal fungere som i dag via fallback — aldri krasj.
- Fredet: `js/modes/jamovi_v1.js`, `css/modes/jamovi_v1.css`, `js/modes/jamovi_light.js`, `css/modes/jamovi_light.css`.
- Kodestil: `var`, IIFE, `T(...)` for norske strenger; generatorstil som eksisterende gen_jmv_specs.py.
- Arbeid på branch `jamovi-fase3-dialoger` i safestat; openstat synces i siste task.

---

### Task 1: Vendore u.yaml + generator-utvidelse

**Files:**
- Create: `tools/jmv_yaml/ui/<analyse>.u.yaml` (13 filer)
- Modify: `tools/gen_jmv_specs.py`
- Modify: `tests/test_gen_jmv_specs.py` (nye tester)
- Regenerate: `js/modes/jmv_specs.js`

**Interfaces:**
- Produces: `specs[<navn>].layout` — tre av noder:
  `{t:'supplier', targets:[{name, max?}]}` | `{t:'label', label, children}` | `{t:'grid', cells:[{col, row, children}]}` | `{t:'check', name, label?, enable?, children?}` | `{t:'radio', option, part, label, enable?}` | `{t:'combo', name, label?}` | `{t:'text', name, label?, format?, enable?}` | `{t:'collapse', label, collapsed, children}`
  Rot er alltid `{t:'root', children:[...]}`. Task 2 konsumerer dette eksakt.

- [ ] **Step 1: Hent u.yaml-filene**

```bash
mkdir -p tools/jmv_yaml/ui
for a in ttestis ttestps ttestones descriptives anovaonew anova anovanp corrmatrix linreg logregbin proptestn conttables; do
  curl -sf "https://raw.githubusercontent.com/jamovi/jmv/master/jamovi/$a.u.yaml" -o "tools/jmv_yaml/ui/$a.u.yaml" || echo "MANGLER: $a"
done
curl -sf "https://raw.githubusercontent.com/jamovi/scatr/master/jamovi/scat.u.yaml" -o tools/jmv_yaml/ui/scat.u.yaml || echo "MANGLER: scat"
ls tools/jmv_yaml/ui/ | wc -l   # forventet: 13
```

Hvis en fil mangler (404): noter i rapporten; analysen får da ingen layout (fallback).
Merk: `name:`-feltet INNI filen (f.eks. `ttestIS`) er nøkkelen mot specs — ikke filnavnet.

- [ ] **Step 2: Skriv de feilende testene** (legg til i `tests/test_gen_jmv_specs.py`)

```python
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
```

- [ ] **Step 3: Kjør — skal feile** (`python3 -m pytest tests/test_gen_jmv_specs.py -v` → nye tester FAILER på manglende layout)

- [ ] **Step 4: Implementér parseren i `tools/gen_jmv_specs.py`**

```python
UI_DIR = ROOT / 'tools/jmv_yaml/ui'

# u.yaml-typer -> kompakt layout-tre. Ukjente containere flates ut; ukjente
# løvnoder droppes. Se docs/PLAN_jamovi_fase3_dialoglayout.md.

def _parse_enable(expr):
    if isinstance(expr, str):
        m = re.fullmatch(r'\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)', expr.strip())
        if m:
            return m.group(1)
    return None


def _layout_node(el, valid, warns):
    t = el.get('type')
    kids = el.get('children') or []

    def parsed_children():
        out = []
        for k in kids:
            n = _layout_node(k, valid, warns)
            if n is None:
                continue
            out.extend(n) if isinstance(n, list) else out.append(n)
        return out

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
        if isinstance(el.get('cell'), dict):
            # celle håndteres av forelderen (grid-assemblering) — returner marker
            return {'t': '_cell', 'col': el['cell'].get('column', 0),
                    'row': el['cell'].get('row', 0), 'children': parsed_children()}
        return parsed_children()   # transparent container -> flat

    if t == 'Label':
        ch = parsed_children()
        return gated({'t': 'label', 'label': el.get('label', ''), 'children': ch}) if ch else None

    if t == 'CheckBox':
        nm = el.get('name')
        if nm not in valid:
            warns.append(f'ukjent opsjon {nm}'); return None
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
            warns.append(f'ukjent opsjon {opt}'); return None
        return gated({'t': 'radio', 'option': opt, 'part': el.get('optionPart'),
                      'label': el.get('label', el.get('optionPart', ''))})

    if t == 'ComboBox':
        nm = el.get('name')
        if nm not in valid:
            warns.append(f'ukjent opsjon {nm}'); return None
        return gated({'t': 'combo', 'name': nm, 'label': el.get('label', '')})

    if t == 'TextBox':
        nm = el.get('name')
        if nm not in valid:
            warns.append(f'ukjent opsjon {nm}'); return None
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


def _assemble(children):
    """Grupper _cell-markører til grid-noder; behold rekkefølgen ellers."""
    out, cells = [], []
    for n in children:
        (cells if isinstance(n, dict) and n.get('t') == '_cell' else out.append(n)) is None or cells.append(n) if False else None
    # (skriv dette lesbart i implementasjonen: to lister, én pass)
    return out, cells


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
    # grid-assemblering: nabosekvenser av _cell-markører -> ett grid
    final, cellbuf = [], []
    def flush():
        if cellbuf:
            final.append({'t': 'grid', 'cells': [
                {'col': c['col'], 'row': c['row'], 'children': c['children']}
                for c in sorted(cellbuf, key=lambda c: (c['row'], c['col']))]})
            cellbuf.clear()
    def walk_top(nodes):
        for n in nodes:
            if n.get('t') == '_cell':
                cellbuf.append(n)
            else:
                flush(); final.append(n)
        flush()
    walk_top(children)
    return {'t': 'root', 'children': final}, warns
```

Merk til implementeren: `_assemble`-utkastet over er bevisst erstattet av
flush/walk_top-logikken i `parse_layout` — implementér den lesbart, IKKE one-lineren.
`_cell`-markører kan også dukke opp nede i treet (Label/collapse-children) — kjør samme
flush-gruppering rekursivt der children settes (én hjelpefunksjon, bruk den begge steder).

I `main()`: etter at `specs[name]` er bygget — `lay, warns = parse_layout(name, {o['name'] for o in specs[name]['options']})`; sett `specs[name]['layout'] = lay` hvis lay; print hver warn med analysenavn.

- [ ] **Step 5: Kjør testene — alle grønne** (`python3 -m pytest tests/test_gen_jmv_specs.py -v`; eldre tester uendret grønne). Sjekk stdout-varslene: navn som droppes pga. 2.7.7-drift skal listes, ikke feile.

- [ ] **Step 6: Commit** — `git add tools/ tests/ js/modes/jmv_specs.js && git commit -m "jamovi fase 3: layout-trær fra jamovi sine u.yaml-filer i spec-generatoren"`

---

### Task 2: Renderer + CSS-polish

**Files:**
- Modify: `js/modes/jamovi.js` (renderJmvLayout; openJmvAnalysis bruker den; JMV_SECTIONS slettes)
- Modify: `css/modes/jamovi.css`

**Interfaces:**
- Consumes: `spec.layout` (Task 1-formen), eksisterende `control(o)`-byggerne, rolleboks-DOM/interaksjon, `values`/`scheduleRun`.
- Produces: `renderJmvLayout(root, ctx)` der `ctx = { spec, values, onChange, roleBoxBuilder }` — intern funksjon; openJmvAnalysis er eneste kaller.

- [ ] **Step 1: CSS** (legg til i `css/modes/jamovi.css`)

```css
/* fase 3: u.yaml-drevet layout */
.jmv-grid { display: grid; grid-template-columns: repeat(var(--jmv-grid-cols, 2), minmax(0, 1fr)); gap: 2px 22px; margin: 2px 0 8px; }
.jmv-optgroup { margin: 6px 0 10px; }
.jmv-optgroup > .jmv-optgroup-label { font: 600 12px/1.4 inherit; color: #444; margin: 4px 0 3px; }
.jmv-suboptions { margin: 1px 0 3px 20px; padding-left: 10px; border-left: 2px solid #e3e6ec; }
.jmv-opt-item input[type="radio"], .jmv-opt-item input[type="checkbox"] { margin: 0 2px 0 0; }
.jmv-opt-row { display: flex; align-items: center; gap: 6px; margin: 2px 0; font: 13px/1.4 inherit; }
.jmv-opt-row.jmv-disabled, .jmv-opt-item.jmv-disabled { opacity: .45; pointer-events: none; }
.jmv-opt-num { width: 64px; padding: 2px 5px; border: 1px solid #828282; border-radius: 3px; font: 13px inherit; }
.jmv-opt-txt { width: 140px; padding: 2px 5px; border: 1px solid #828282; border-radius: 3px; font: 13px inherit; }
```

- [ ] **Step 2: Implementér `renderJmvLayout` i jamovi.js** (over openJmvAnalysis)

Kjernen (fullstendig logikk; tilpass til eksisterende hjelpe-funksjoner):

```js
    // Tegner spec.layout (u.yaml-avledet) inn i body. Kontroll-tilstand leses/skrives
    // i values; hver endring kaller onChange() (=> scheduleRun). Deaktivering:
    //  - barn av en check disables når checken er false
    //  - noder med {enable:'navn'} disables når values[navn] er falsy
    function renderJmvLayout(root, ctx) {
      var body = ctx.body, values = ctx.values, onChange = ctx.onChange;
      var enableDeps = {};   // opsjonsnavn -> [DOM-elementer som skal ha disabled-stil]
      function dep(name, el) { (enableDeps[name] = enableDeps[name] || []).push(el); }
      function refreshDisabled() {
        Object.keys(enableDeps).forEach(function (name) {
          var off = !values[name];
          enableDeps[name].forEach(function (el) {
            el.classList.toggle('jmv-disabled', off);
            el.querySelectorAll('input,select').forEach(function (i) { i.disabled = off; });
          });
        });
      }
      function optByName(n) { return ctx.spec.options.filter(function (o) { return o.name === n; })[0]; }
      function draw(node, parent) {
        if (!node) return;
        if (node.t === 'supplier') { ctx.roleBoxBuilder(node.targets, parent); return; }
        if (node.t === 'grid') {
          var g = document.createElement('div'); g.className = 'jmv-grid';
          var maxCol = node.cells.reduce(function (m, c) { return Math.max(m, c.col); }, 0);
          g.style.setProperty('--jmv-grid-cols', String(maxCol + 1));
          node.cells.forEach(function (cell) {
            var cd = document.createElement('div');
            cd.style.gridColumn = String(cell.col + 1); cd.style.gridRow = String(cell.row + 1);
            (cell.children || []).forEach(function (k) { draw(k, cd); });
            g.appendChild(cd);
          });
          parent.appendChild(g); return;
        }
        if (node.t === 'label') {
          var grp = document.createElement('div'); grp.className = 'jmv-optgroup';
          var lb = document.createElement('div'); lb.className = 'jmv-optgroup-label';
          lb.textContent = node.label; grp.appendChild(lb);
          (node.children || []).forEach(function (k) { draw(k, grp); });
          if (node.enable) dep(node.enable, grp);
          parent.appendChild(grp); return;
        }
        if (node.t === 'collapse') {
          var sec = document.createElement('div'); sec.className = 'jmv-section' + (node.collapsed ? ' collapsed' : '');
          var hdr = document.createElement('div'); hdr.className = 'jmv-section-hdr';
          hdr.innerHTML = '<span class="jmv-section-caret">▾</span><span class="jmv-section-title">' + M.escapeHtml(node.label) + '</span>';
          hdr.addEventListener('click', function () { sec.classList.toggle('collapsed'); });
          var sb = document.createElement('div'); sb.className = 'jmv-section-body';
          (node.children || []).forEach(function (k) { draw(k, sb); });
          sec.appendChild(hdr); sec.appendChild(sb); parent.appendChild(sec); return;
        }
        if (node.t === 'check') {
          var o = optByName(node.name); if (!o) return;
          var row = document.createElement('label'); row.className = 'jmv-opt-row';
          var cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = !!values[node.name];
          row.appendChild(cb); row.appendChild(document.createTextNode(node.label || o.title));
          parent.appendChild(row);
          var subWrap = null;
          if (node.children && node.children.length) {
            subWrap = document.createElement('div'); subWrap.className = 'jmv-suboptions';
            node.children.forEach(function (k) { draw(k, subWrap); });
            parent.appendChild(subWrap);
            dep(node.name, subWrap);
          }
          cb.addEventListener('change', function () { values[node.name] = cb.checked; refreshDisabled(); onChange(); });
          if (node.enable) { dep(node.enable, row); if (subWrap) dep(node.enable, subWrap); }
          return;
        }
        if (node.t === 'radio') {
          var row2 = document.createElement('label'); row2.className = 'jmv-opt-row';
          var rb = document.createElement('input'); rb.type = 'radio';
          rb.name = 'jmvopt_' + ctx.uid + '_' + node.option;
          rb.checked = (values[node.option] === node.part);
          rb.addEventListener('change', function () { if (rb.checked) { values[node.option] = node.part; refreshDisabled(); onChange(); } });
          row2.appendChild(rb); row2.appendChild(document.createTextNode(node.label));
          if (node.enable) dep(node.enable, row2);
          parent.appendChild(row2); return;
        }
        if (node.t === 'combo') {
          var oc = optByName(node.name); if (!oc) return;
          var rowc = document.createElement('label'); rowc.className = 'jmv-opt-row';
          if (node.label || oc.title) rowc.appendChild(document.createTextNode((node.label || oc.title) + ' '));
          var sel = document.createElement('select'); sel.className = 'jmv-opt-select';
          (oc.choices || []).forEach(function (c) {
            var op = document.createElement('option'); op.value = c.value; op.textContent = c.title;
            if (c.value === values[node.name]) op.selected = true; sel.appendChild(op);
          });
          sel.addEventListener('change', function () { values[node.name] = sel.value; refreshDisabled(); onChange(); });
          rowc.appendChild(sel); if (node.enable) dep(node.enable, rowc);
          parent.appendChild(rowc); return;
        }
        if (node.t === 'text') {
          var ot = optByName(node.name); if (!ot) return;
          var rowt = document.createElement('label'); rowt.className = 'jmv-opt-row';
          rowt.appendChild(document.createTextNode((node.label || ot.title) + ' '));
          var inp = document.createElement('input');
          var numeric = (node.format === 'number' || ot.type === 'Number' || ot.type === 'Integer');
          inp.type = numeric ? 'number' : 'text';
          inp.className = numeric ? 'jmv-opt-num' : 'jmv-opt-txt';
          inp.value = (values[node.name] === null || values[node.name] === undefined) ? '' : values[node.name];
          if (ot.min !== undefined) inp.min = ot.min;
          if (ot.max !== undefined) inp.max = ot.max;
          inp.addEventListener('change', function () {
            values[node.name] = (inp.value === '') ? ot.default
              : (numeric ? Number(inp.value) : inp.value);
            refreshDisabled(); onChange();
          });
          rowt.appendChild(inp); if (node.enable) dep(node.enable, rowt);
          parent.appendChild(rowt); return;
        }
      }
      (root.children || []).forEach(function (k) { draw(k, body); });
      refreshDisabled();
    }
```

- [ ] **Step 3: Koble inn i `openJmvAnalysis`**

- Der rollebokser + seksjoner bygges i dag: hvis `spec.layout` finnes →
  `renderJmvLayout(spec.layout, { spec:spec, values:values, body:body, onChange:scheduleRun, uid:myGen, roleBoxBuilder:function(targets, parent){ ... } })`
  der `roleBoxBuilder` gjenbruker dagens variabelliste + rolleboks-kode, men bygger
  boksene i `targets`-rekkefølge (tittel fra `optByName(t.name).title`, maks fra
  `t.max`; Pairs-typen beholder dagens to-slots-oppførsel).
- Ellers (ingen layout): dagens flate fallback (behold `addSection`-hjelpen og
  «Flere valg», men SLETT `JMV_SECTIONS`-kartet og kall den generiske stien).
- Radio-defaults: `values[option]` er allerede initialisert fra `o.default` — radioen
  med matchende part blir checked ved åpning.

- [ ] **Step 4: Verifisering i nettleser (med screenshots — visuelt design)**

Server 8791 → jamovi-modus → harpo. Åpne **ttestIS**: Tests-gruppen med Student's
(og nøstet, deaktivert «Bayes factor»-linje med Prior-felt), Welch's, Mann-Whitney;
Hypothesis-radioene; Additional Statistics-kolonne ved siden av (grid). Huk av
«Bayes factor» → Prior-feltet aktiveres. Åpne **descriptives**: Statistics-seksjonen
som CollapseBox med kolonner; Plots-seksjon. Åpne **contTables**. TA 3 SCREENSHOTS
(ett per analyse-panel) og lagre til `.superpowers/sdd/fase3-screens/`. Live-oppdatering
skal virke som før (endre opsjon → resultat oppdateres). Konsoll ren.

- [ ] **Step 5: Commit** — `git add js/modes/jamovi.js css/modes/jamovi.css && git commit -m "jamovi fase 3: u.yaml-drevet dialogrendering med grupper, grid, nøsting og deaktivering"`

---

### Task 3: Synk openstat + roadmap-status

- [ ] Kopiér `js/modes/jamovi.js`, `js/modes/jmv_specs.js`, `css/modes/jamovi.css`, `tools/gen_jmv_specs.py`, `tools/jmv_yaml/ui/`, `tests/test_gen_jmv_specs.py` til openstat (md5-verifisér js/css). Kjør pytest + `node --check` i openstat.
- [ ] Huk av dialog-layout-punktet i `docs/ROADMAP.md` (begge repoer).
- [ ] Commit begge repoer (openstat på main): "jamovi fase 3: u.yaml-dialoglayout (synk fra safestat)". IKKE push — Hans vurderer visuelt først.

## Self-review-notater

- Kontraktene konsistente: layout-nodeformen i Task 1 == det renderJmvLayout konsumerer i Task 2 (t/name/option/part/label/enable/children/cells).
- `uid` for radiogruppe-navn bruker `myGen` (finnes i openJmvAnalysis-skopet).
- Fallback-stien beholdes eksplisitt (Global Constraints) — analyser uten u.yaml (f.eks. hvis en fil var 404) fungerer som i dag.
- Ingen placeholder-steg; generatorkoden i Task 1 Step 4 er komplett nok til transkripsjon + de to markerte punktene der implementeren skal skrive lesbar variant/rekursiv gruppering selv (eksplisitt beskrevet).
