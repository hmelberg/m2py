// tests/js/notebook-links.test.js
const test = require('node:test');
const assert = require('node:assert');
const NL = require('../../js/notebook-links.js');

test('hostnameMode: exact first-label prefixes', () => {
  assert.equal(NL.hostnameMode('py.openstat.app'), 'python');
  assert.equal(NL.hostnameMode('r.safestat.app'), 'r');
  assert.equal(NL.hostnameMode('duck.openstat.app'), 'duckdb');
});
test('hostnameMode: micro substring', () => {
  assert.equal(NL.hostnameMode('micro.safestat.app'), 'microdata');
  assert.equal(NL.hostnameMode('microdata.run'), 'microdata');
});
test('hostnameMode: bare/dev hosts default to python', () => {
  assert.equal(NL.hostnameMode('openstat.app'), 'python');
  assert.equal(NL.hostnameMode('safestat.app'), 'python');
  assert.equal(NL.hostnameMode('localhost'), 'python');
  assert.equal(NL.hostnameMode('deploy-preview-1--safestat.netlify.app'), 'python');
});
test('hostnameMode: no false prefix hit (spy != py)', () => {
  assert.equal(NL.hostnameMode('spy.openstat.app'), 'python'); // falls through to default, still python
  assert.equal(NL.hostnameMode('rstudio.example.com'), 'python'); // 'rstudio' != 'r'
});

test('classifyHash: dotted open → main+master candidates', () => {
  const r = NL.classifyHash('#hans.demo.analyses.income.py');
  assert.equal(r.action, 'open');
  assert.equal(r.kind, 'dotted');
  assert.deepEqual(r.urls, [
    'https://raw.githubusercontent.com/hans/demo/main/analyses/income.py',
    'https://raw.githubusercontent.com/hans/demo/master/analyses/income.py',
  ]);
});
test('classifyHash: dotted output prefix', () => {
  const r = NL.classifyHash('#output.hans.demo.income.py');
  assert.equal(r.action, 'output');
  assert.deepEqual(r.urls, [
    'https://raw.githubusercontent.com/hans/demo/main/income.py',
    'https://raw.githubusercontent.com/hans/demo/master/income.py',
  ]);
});
test('classifyHash: raw url fallback', () => {
  const r = NL.classifyHash('#url=https://gist.githubusercontent.com/u/abc/raw/x.py');
  assert.equal(r.action, 'open');
  assert.equal(r.kind, 'raw');
  assert.equal(r.raw, 'https://gist.githubusercontent.com/u/abc/raw/x.py');
});
test('classifyHash: output raw url', () => {
  const r = NL.classifyHash('#output=https://raw.githubusercontent.com/u/rr/main/a.r');
  assert.equal(r.action, 'output');
  assert.equal(r.kind, 'raw');
});
test('classifyHash: legacy share defers', () => {
  assert.deepEqual(NL.classifyHash('#s=H4sIAAA'), { action: 'open', kind: 'share' });
});
test('classifyHash: non-matching returns null', () => {
  assert.equal(NL.classifyHash(''), null);
  assert.equal(NL.classifyHash('#'), null);
  assert.equal(NL.classifyHash('#section-heading'), null);  // no extension / too few tokens
  assert.equal(NL.classifyHash('#only.two'), null);         // needs user.repo.path.ext
});

test('welcomeVariant: output-only shows nothing', () => {
  assert.equal(NL.welcomeVariant('micro.safestat.app', 'safestat', true), null);
});
test('welcomeVariant: micro host → microdata framing (either app)', () => {
  assert.equal(NL.welcomeVariant('microdata.run', 'openstat', false), 'microdata');
  assert.equal(NL.welcomeVariant('micro.safestat.app', 'safestat', false), 'microdata');
});
test('welcomeVariant: general framing per app', () => {
  assert.equal(NL.welcomeVariant('py.openstat.app', 'openstat', false), 'openstat_general');
  assert.equal(NL.welcomeVariant('safestat.app', 'safestat', false), 'safestat_general');
  assert.equal(NL.welcomeVariant('r.safestat.app', 'safestat', false), 'safestat_general');
});
