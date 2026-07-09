import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
const src = await Deno.readTextFile(new URL("../../../js/assembly-duckdb.js", import.meta.url));
(0, eval)(src);
// deno-lint-ignore no-explicit-any
const AD = (globalThis as any).AssemblyDuckdb;

Deno.test("canPushdown: true when every source is parquet/duckdb/sqlite", () => {
  const spec = { sources: ["p", "db__patients"], datasets: [] };
  const descriptors = { p: { url: "https://x/p.parquet", format: "parquet" },
    db__patients: { url: "https://x/panel.duckdb", format: "duckdb", table: "patients" } };
  assertEquals(AD.canPushdown(spec, descriptors), true);
});

Deno.test("canPushdown: csv qualifies (trinn B); json/other still do not", () => {
  const spec = { sources: ["p", "c"], datasets: [] };
  const descriptors = { p: { url: "https://x/p.parquet", format: "parquet" },
    c: { url: "https://x/c.csv", format: "csv" } };
  assertEquals(AD.canPushdown(spec, descriptors), true);
  const specJ = { sources: ["j"], datasets: [] };
  assertEquals(AD.canPushdown(specJ, { j: { url: "https://x/d.json", format: "json" } }), false);
  assertEquals(AD.canPushdown(specJ, { j: { url: "https://x/d.bin", format: "other" } }), false);
});

Deno.test("compile: csv source uses pandas-mimicking read_csv options", () => {
  // Trinn B: ingen dato/tid-autodeteksjon (pandas lar dem stå som strenger),
  // pandas-lignende NA-tokens, header=true. Skilletegn autodetekteres.
  const spec = { sources: ["c"], datasets: [{ name: "df", load: "c" }] };
  const descriptors = { c: { url: "https://x.example/data.csv", format: "csv" } };
  const { datasetStatements, attachStatements } = AD.compile(spec, descriptors);
  assertEquals(attachStatements.length, 0);
  const sql = datasetStatements[0].sql;
  if (!sql.includes("read_csv('https://x.example/data.csv'")) throw new Error("forventet read_csv(url): " + sql);
  if (!sql.includes("header = true")) throw new Error("forventet header=true: " + sql);
  if (!sql.includes("auto_type_candidates = ['BIGINT', 'DOUBLE', 'VARCHAR', 'BOOLEAN']"))
    throw new Error("forventet begrensede typekandidater: " + sql);
  if (!sql.includes("nullstr = ['', 'NA', 'N/A', 'NaN', 'nan', 'NULL', 'null']"))
    throw new Error("forventet pandas-NA-tokens: " + sql);
});

Deno.test("compile: import from csv + join with parquet mixes relation refs", () => {
  const spec = { sources: ["c", "p"], datasets: [
    { name: "d", key: "id", steps: [
      { op: "import", source: "c", columns: ["a"], how: "left" },
      { op: "import", source: "p", columns: ["b"], how: "left" }] }] };
  const descriptors = { c: { url: "https://x/c.csv", format: "csv" },
    p: { url: "https://x/p.parquet", format: "parquet" } };
  const sql = AD.compile(spec, descriptors).datasetStatements[0].sql;
  if (!sql.includes("read_csv(") || !sql.includes("read_parquet(")) {
    throw new Error("forventet begge lesefunksjonene: " + sql);
  }
});

Deno.test("compile: single import produces a column-projected SELECT", () => {
  const spec = { sources: ["p"], datasets: [
    { name: "onevar", key: "pid", steps: [{ op: "import", source: "p", columns: ["income"], how: "left" }] }] };
  const descriptors = { p: { url: "https://x.example/patients.parquet", format: "parquet" } };
  const { datasetStatements } = AD.compile(spec, descriptors);
  assertEquals(datasetStatements.length, 1);
  assertEquals(datasetStatements[0].name, "onevar");
  if (!datasetStatements[0].sql.includes("pid") || !datasetStatements[0].sql.includes("income")) {
    throw new Error("forventet projeksjon av pid+income, fikk: " + datasetStatements[0].sql);
  }
  if (!datasetStatements[0].sql.includes("read_parquet('https://x.example/patients.parquet')")) {
    throw new Error("forventet read_parquet(url) pushdown, fikk: " + datasetStatements[0].sql);
  }
});

Deno.test("compile: duckdb table source produces an ATTACH + qualified table reference", () => {
  const spec = { sources: ["db__patients"], datasets: [
    { name: "onevar", key: "pid", steps: [{ op: "import", source: "db__patients", columns: ["age"], how: "left" }] }] };
  const descriptors = { db__patients: { url: "https://x.example/panel.duckdb", format: "duckdb", table: "patients" } };
  const { attachStatements, datasetStatements } = AD.compile(spec, descriptors);
  assertEquals(attachStatements.length, 1);
  if (!attachStatements[0].includes("ATTACH") || !attachStatements[0].includes("panel.duckdb")) {
    throw new Error("forventet ATTACH mot panel.duckdb, fikk: " + attachStatements[0]);
  }
  if (!datasetStatements[0].sql.includes('"patients"')) {
    throw new Error("forventet referanse til tabellen patients, fikk: " + datasetStatements[0].sql);
  }
});

Deno.test("compile: two duckdb tables from the SAME file share one ATTACH", () => {
  const spec = { sources: ["db__patients", "db__visits"], datasets: [
    { name: "panel", key: "pid", steps: [
      { op: "import", source: "db__patients", columns: ["age"], how: "left" }] },
    { name: "visits", load: "db__visits" }] };
  const descriptors = {
    db__patients: { url: "https://x.example/panel.duckdb", format: "duckdb", table: "patients" },
    db__visits: { url: "https://x.example/panel.duckdb", format: "duckdb", table: "visits" } };
  const { attachStatements } = AD.compile(spec, descriptors);
  assertEquals(attachStatements.length, 1); // one file, one ATTACH, per design doc §1
});

Deno.test("compile: join between two constructed datasets", () => {
  const spec = { sources: ["p", "s"], datasets: [
    { name: "sales", load: "s" },
    { name: "panel", key: "pid", steps: [
      { op: "import", source: "p", columns: ["income"], how: "left" },
      { op: "join", from: "sales", on: "pid", how: "left" }] }] };
  const descriptors = { p: { url: "https://x/p.parquet", format: "parquet" }, s: { url: "https://x/s.parquet", format: "parquet" } };
  const { datasetStatements } = AD.compile(spec, descriptors);
  const panelSql = datasetStatements.find((d: { name: string }) => d.name === "panel").sql;
  if (!/JOIN/i.test(panelSql)) throw new Error("forventet SQL JOIN, fikk: " + panelSql);
});

Deno.test("compile: a join target declared AFTER the dataset that joins it still compiles", () => {
  // parseAssembly allows forward references (a create-dataset "B" that joins
  // "A" declared later in the script is valid) — compile() must not depend
  // on textual declaration order. 2026-07-07 regression: this used to throw
  // "ukjent datasett «sales»" because the old ordering put all "create-
  // dataset" entries in declaration order with no dependency awareness.
  const spec = { sources: ["p", "s"], datasets: [
    { name: "panel", key: "pid", steps: [
      { op: "import", source: "p", columns: ["income"], how: "left" },
      { op: "join", from: "sales", on: "pid", how: "left" }] },
    { name: "sales", load: "s" }] };
  const descriptors = { p: { url: "https://x/p.parquet", format: "parquet" }, s: { url: "https://x/s.parquet", format: "parquet" } };
  const { datasetStatements } = AD.compile(spec, descriptors);
  const panelSql = datasetStatements.find((d: { name: string }) => d.name === "panel").sql;
  if (!/JOIN/i.test(panelSql)) throw new Error("forventet SQL JOIN, fikk: " + panelSql);
  // "sales" must be compiled (and appear in datasetStatements) before "panel"
  const names = datasetStatements.map((d: { name: string }) => d.name);
  if (names.indexOf("sales") > names.indexOf("panel")) {
    throw new Error("forventet «sales» kompilert før «panel», fikk rekkefølge: " + names.join(", "));
  }
});
