// tests/js/dashboard.test.js — rene funksjoner i js/dashboard.js
// (spec docs/superpowers/specs/2026-07-09-dashboard-design.md)
const test = require('node:test');
const assert = require('node:assert');
const D = require('../../js/dashboard.js');

const SCRIPT = [
  '#options.view = dashboard',
  '#options.title = "Dødsårsaker"',
  '# load https://x.example/d.csv as df',
  'prep = 1',
  '',
  '#input year = slider(1990, 2024, step=1, default=2020)',
  '#input cause = dropdown("Kreft", "Hjertesykdom", "Ulykker")',
  '#input per100k = checkbox(default=True, label="Per 100k")',
  '',
  'mellom = year * 2',
  '',
  '#%% Utvikling, wide',
  'sub = df[df.cause == cause]',
  'print(sub)',
  '',
  '#%% Topp 10, row=nokkeltall, deps=year',
  'print(year)',
].join('\n');

test('parse: options, setup zone, inputs, cells', () => {
  const p = D.parse(SCRIPT);
  assert.equal(p.title, 'Dødsårsaker');
  assert.ok(p.setupCode.includes('prep = 1'));
  assert.ok(!p.setupCode.includes('#input'));
  assert.deepEqual(p.inputs.map(i => i.name), ['year', 'cause', 'per100k']);
  assert.equal(p.inputs[0].type, 'slider');
  assert.equal(p.inputs[0].min, 1990);
  assert.equal(p.inputs[0].max, 2024);
  assert.equal(p.inputs[0].default, 2020);
  assert.deepEqual(p.inputs[1].choices, ['Kreft', 'Hjertesykdom', 'Ulykker']);
  assert.equal(p.inputs[1].default, 'Kreft');          // first choice
  assert.equal(p.inputs[2].default, true);
  assert.equal(p.inputs[2].label, 'Per 100k');
  assert.equal(p.cells.length, 3);                     // unnamed pre-cell + 2 named
  assert.equal(p.cells[0].name, '');                   // "mellom = year * 2"
  assert.equal(p.cells[1].name, 'Utvikling');
  assert.equal(p.cells[1].wide, true);
  assert.equal(p.cells[2].row, 'nokkeltall');
  assert.deepEqual(p.cells[2].deps, ['year']);
  assert.equal(p.errors.length, 0);
});

test('parse: norwegian alias bred, tab attr, // and -- markers', () => {
  const p = D.parse([
    '//input x = slider(0, 10)',
    '//%% A, bred, tab=Oversikt',
    'x',
    '-- %% B, tab=Detaljer',
    'x',
  ].join('\n'));
  assert.equal(p.inputs[0].default, 0);                // default = min
  assert.equal(p.cells[0].wide, true);
  assert.equal(p.cells[0].tab, 'Oversikt');
  assert.equal(p.cells[1].tab, 'Detaljer');
});

test('parse: errors on bad input line and duplicate name', () => {
  const p = D.parse('#input 9bad = slider(0,1)\n#input a = slider(0,1)\n#input a = slider(0,1)\n#%% C\na');
  assert.ok(p.errors.length >= 2);
});

test('parse: no #input → direktiver i setup, hele scriptet som celle (dropdown-dashboard)', () => {
  const p = D.parse('# load https://x/y.csv as df\nprint(df)');
  assert.equal(p.inputs.length, 0);
  assert.equal(p.cells.length, 1);                     // vanlig script → ett kort
  assert.ok(p.cells[0].code.includes('print(df)'));
  assert.ok(p.setupCode.includes('# load'));           // pipeline materialiserer loads
  assert.ok(!p.setupCode.includes('print(df)'));       // kode kjøres i cellen, ikke to ganger
});

test('parse: %% inside code line is not a cell marker', () => {
  const p = D.parse('#input a = slider(0,1)\nx = 5 %% 3  # ikke marker');
  assert.equal(p.cells.length, 1);
  assert.equal(p.cells[0].name, '');
});

test('assignStatement: python and r serialization', () => {
  assert.equal(D.assignStatement('python', 'year', 2021), 'year = 2021');
  assert.equal(D.assignStatement('python', 'ok', true), 'ok = True');
  assert.equal(D.assignStatement('python', 'c', 'Kreft "x"'), 'c = "Kreft \\"x\\""');
  assert.equal(D.assignStatement('r', 'year', 2021), 'year <- 2021');
  assert.equal(D.assignStatement('r', 'ok', false), 'ok <- FALSE');
  assert.equal(D.assignStatement('r', 'c', 'Kreft'), 'c <- "Kreft"');
});

test('planReruns: mention, transitive, deps override', () => {
  const cells = [
    { name: 'a', deps: null, code: 'sub = df[df.cause == cause]\nprint(sub)' },
    { name: 'b', deps: null, code: 'print(sub)' },                  // transitiv via sub
    { name: 'c', deps: null, code: 'print(year)' },
    { name: 'd', deps: ['year'], code: 'print("whatever cause")' }, // deps overstyrer tekst
  ];
  assert.deepEqual(D.planReruns(cells, ['cause'], 'python'), [0, 1]);
  assert.deepEqual(D.planReruns(cells, ['year'], 'python'), [2, 3]);
});

test('planReruns: opaque cell → it and everything after re-runs', () => {
  const op = [
    { name: 'a', deps: null, code: 'x = year' },
    { name: 'b', deps: null, code: 'globals()["y"] = 1' },
    { name: 'c', deps: null, code: 'print(1)' },
  ];
  assert.deepEqual(D.planReruns(op, ['year'], 'python'), [0, 1, 2]);
});

test('planReruns: r assignment forms', () => {
  const rc = [
    { name: 'a', deps: null, code: 'sub <- df[df$cause == cause,]' },
    { name: 'b', deps: null, code: 'plot(sub)' },
    { name: 'c', deps: null, code: 'plot(annet)' },
  ];
  assert.deepEqual(D.planReruns(rc, ['cause'], 'r'), [0, 1]);
});

test('planReruns: nothing affected → empty', () => {
  const cells = [{ name: 'a', deps: null, code: 'print(1)' }];
  assert.deepEqual(D.planReruns(cells, ['year'], 'python'), []);
});

test('groupLayout: cards, rows, tab sets, tab break', () => {
  const cells = [
    { name: 'a', row: null, tab: null }, { name: 'b', row: 'kpi', tab: null },
    { name: 'c', row: 'kpi', tab: null }, { name: 'd', row: null, tab: 'X' },
    { name: 'e', row: null, tab: 'Y' }, { name: 'f', row: null, tab: null },
    { name: 'g', row: null, tab: 'Z' },
  ];
  const g = D.groupLayout(cells);
  assert.deepEqual(g.map(x => x.kind), ['card', 'row', 'tabs', 'card', 'tabs']);
  assert.deepEqual(g[1].indexes, [1, 2]);
  assert.deepEqual(g[2].tabs.map(t => t.label), ['X', 'Y']);
  assert.deepEqual(g[2].tabs[0].indexes, [3]);
  assert.equal(g[0].index, 0);
});

test('createQueue: coalesces, one pending batch, sequential', async () => {
  const runs = [];
  let resolveRun;
  const q = D.createQueue(batch => new Promise(res => { runs.push(batch); resolveRun = res; }), 1);
  q.change('year', 2000); q.change('year', 2001);
  await new Promise(r => setTimeout(r, 15));
  assert.deepEqual(runs, [{ year: 2001 }]);            // koalesert før kjøring
  q.change('year', 2005); q.change('cause', 'K');      // kommer mens run 1 pågår
  await new Promise(r => setTimeout(r, 15));
  assert.equal(runs.length, 1);                        // venter fortsatt på run 1
  resolveRun();
  await new Promise(r => setTimeout(r, 15));
  assert.deepEqual(runs[1], { year: 2005, cause: 'K' });
  resolveRun();
});
