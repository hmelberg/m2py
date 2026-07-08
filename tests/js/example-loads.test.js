// tests/js/example-loads.test.js
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs'); const path = require('node:path'); const vm = require('node:vm');
const root = path.join(__dirname, '..', '..');

function loadDD() {
  const code = fs.readFileSync(path.join(root, 'js', 'data-directives.js'), 'utf8');
  const sandbox = { window: {}, console }; vm.createContext(sandbox); vm.runInContext(code, sandbox);
  return sandbox.window.DataDirectives;
}
const DD = loadDD();
const FILES = ['ex_csv_iris.txt','ex_columns_penguins.txt','ex_enc_hospital.txt',
               'rex_csv_iris.txt','rex_columns_penguins.txt','rex_enc_hospital.txt'];

for (const f of FILES) {
  test('load directive parses: ' + f, () => {
    const text = fs.readFileSync(path.join(root, 'examples', f), 'utf8');
    const parsed = DD.parse(text);      // { connects, loads, errors } shape
    const loads = (parsed && parsed.loads) || [];
    assert.ok(loads.length >= 1, 'has at least one load directive');
    assert.ok(/^https?:\/\//.test(loads[0].target || ''), 'load target is a URL');
  });
}
