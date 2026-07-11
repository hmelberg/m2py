// tests/js/duckdb-native.test.js — port av tests/test_duckdb_bridge.py for
// JS-utgaven (js/duckdb-native.js). Parquet-/referenced-tables-casene er
// utelatt: de hører til pandas-registreringen som kun finnes i Python-veien.
const test = require('node:test');
const assert = require('node:assert');
const DN = require('../../js/duckdb-native.js');

test('split: basic', () => {
  assert.deepEqual(DN.splitSqlStatements('SELECT 1; SELECT 2'), ['SELECT 1', 'SELECT 2']);
});

test('split: trailing semicolon and blanks', () => {
  assert.deepEqual(DN.splitSqlStatements('SELECT 1;\n\n SELECT 2;\n'), ['SELECT 1', 'SELECT 2']);
});

test('split: ignores semicolon in string', () => {
  assert.deepEqual(DN.splitSqlStatements("SELECT ';' AS x; SELECT 2"), ["SELECT ';' AS x", 'SELECT 2']);
});

test('split: ignores semicolon in line comment', () => {
  assert.deepEqual(DN.splitSqlStatements('SELECT 1 -- ; not a split\n; SELECT 2'),
    ['SELECT 1 -- ; not a split', 'SELECT 2']);
});

test('split: ignores semicolon in block comment', () => {
  assert.deepEqual(DN.splitSqlStatements('SELECT 1 /* a ; b */ ; SELECT 2'),
    ['SELECT 1 /* a ; b */', 'SELECT 2']);
});

test('split: handles escaped single quote', () => {
  assert.deepEqual(DN.splitSqlStatements("SELECT 'it''s; here' AS x; SELECT 2"),
    ["SELECT 'it''s; here' AS x", 'SELECT 2']);
});

test('created: plain', () => {
  assert.deepEqual(DN.extractCreatedTables(['CREATE TABLE foo AS SELECT 1']), ['foo']);
});

test('created: or replace / temp / if not exists / quoted', () => {
  const stmts = [
    'CREATE OR REPLACE TABLE bar AS SELECT 1',
    'CREATE TEMP TABLE IF NOT EXISTS "baz" AS SELECT 2',
    'create temporary table Qux as select 3',
  ];
  assert.deepEqual(DN.extractCreatedTables(stmts), ['bar', 'baz', 'Qux']);
});

test('created: dedup preserves order', () => {
  const stmts = ['CREATE TABLE a AS SELECT 1', 'CREATE OR REPLACE TABLE a AS SELECT 2'];
  assert.deepEqual(DN.extractCreatedTables(stmts), ['a']);
});

test('created: ignores CREATE inside strings and comments', () => {
  const stmts = ["SELECT 'CREATE TABLE nope AS x' AS lbl /* CREATE TABLE heller_ikke AS y */"];
  assert.deepEqual(DN.extractCreatedTables(stmts), []);
});

test('preview: plain select', () => {
  assert.equal(DN.buildPreviewSelect(['CREATE TABLE a AS SELECT 1', 'SELECT * FROM a']), 'SELECT * FROM a');
});

test('preview: with cte', () => {
  const stmts = ['WITH t AS (SELECT 1 AS n) SELECT n FROM t'];
  assert.equal(DN.buildPreviewSelect(stmts), stmts[0]);
});

test('preview: none when last is ddl', () => {
  assert.equal(DN.buildPreviewSelect(['SELECT 1', 'CREATE TABLE a AS SELECT 1']), null);
});

test('preview: none when empty', () => {
  assert.equal(DN.buildPreviewSelect([]), null);
});

test('preview: leading comment before select still previews', () => {
  const stmt = '-- kommentar\nSELECT 1 AS x';
  assert.equal(DN.buildPreviewSelect([stmt]), stmt);
});

test('scrub: comment-only script becomes blank', () => {
  assert.equal(DN.scrub('-- bare en kommentar\n/* og en til */').trim(), '');
});

test('format: aligns columns and renders null as NaN', () => {
  const txt = DN.formatColumnsText({ navn: ['a', null, 'ccc'], n: [1, 22, 3] });
  assert.deepEqual(txt.split('\n'), [
    'navn   n',
    '   a   1',
    ' NaN  22',
    ' ccc   3',
  ]);
});

test('format: empty result gives empty string', () => {
  assert.equal(DN.formatColumnsText({}), '');
});
