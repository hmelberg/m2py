import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  buildDataSvarSystem, coerceDataMode, progressLabel, questionTurn, repairTurn, TOOL_DEFS,
} from "./data-svar-prompt.ts";

Deno.test("coerceDataMode defaults to python", () => {
  assertEquals(coerceDataMode("r"), "r");
  assertEquals(coerceDataMode("duckdb"), "duckdb");
  assertEquals(coerceDataMode("m2py"), "python");
  assertEquals(coerceDataMode(undefined), "python");
});

Deno.test("system prompt: byte-stable, mode-specific, carries core rules", () => {
  const reg = "## Kilderegister (kuratert)\n\n- **ssb** …";
  const a = buildDataSvarSystem("python", reg);
  assertEquals(a, buildDataSvarSystem("python", reg));
  for (const needle of [
    "connect", "load", "probe", "aldri", "konfunder", "heterogenitet",
    "join", "Kilderegister", "transkribert", "modellkunnskap", "site:",
  ]) {
    if (!a.toLowerCase().includes(needle.toLowerCase())) throw new Error("mangler: " + needle);
  }
  const r = buildDataSvarSystem("r", reg);
  if (!r.includes("ggplot2") || a.includes("ggplot2")) throw new Error("modus-blokker feil");
  const d = buildDataSvarSystem("duckdb", reg);
  if (!d.includes("read_csv_auto")) throw new Error("duckdb-blokk mangler");
});

Deno.test("TOOL_DEFS: three client tools + hosted web_search/web_fetch", () => {
  const names = TOOL_DEFS.map((t) => (t as { name: string }).name);
  assertEquals(names, ["search_catalog", "table_metadata", "probe", "web_search", "web_fetch"]);
  assertEquals((TOOL_DEFS[3] as { type: string }).type, "web_search_20250305");
  assertEquals((TOOL_DEFS[4] as { type: string }).type, "web_fetch_20250910");
});

Deno.test("turns and progress labels", () => {
  if (!questionTurn("Hvor mange?", "x=1").includes("x=1")) throw new Error("script-kontekst mangler");
  const rep = repairTurn("q", "bad()", "NameError: x", 2);
  for (const n of ["bad()", "NameError", "2", "3"]) if (!rep.includes(n)) throw new Error("repair mangler " + n);
  if (!progressLabel("search_catalog", { source: "ssb", query: "ledighet" }).includes("ssb")) {
    throw new Error("progress-etikett");
  }
});
