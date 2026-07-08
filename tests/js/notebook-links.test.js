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
