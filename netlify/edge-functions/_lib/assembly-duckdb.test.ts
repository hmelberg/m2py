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

Deno.test("canPushdown: false when any source is csv/json", () => {
  const spec = { sources: ["p", "c"], datasets: [] };
  const descriptors = { p: { url: "https://x/p.parquet", format: "parquet" },
    c: { url: "https://x/c.csv", format: "csv" } };
  assertEquals(AD.canPushdown(spec, descriptors), false);
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
