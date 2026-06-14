import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { assemblePrefix, coerceMode } from "../kode-svar.ts";

const PARTS = { catalogBlock: "CATX", kommuneBlock: "KOMX", commandBlock: "CMDX", functionBlock: "FNX" };

Deno.test("microdata prefix includes catalog, command, function, grammar and canonical examples", () => {
  const out = assemblePrefix("microdata", PARTS);
  assertEquals(out.includes("CATX"), true);
  assertEquals(out.includes("CMDX"), true);
  assertEquals(out.includes("FNX"), true);
  assertEquals(out.includes("KOMX"), true);
  assertEquals(out.includes("minimal grammatikk"), true);          // GRAMMAR_CHEATSHEET
  assertEquals(out.includes("Komplette eksempel-scripts"), true);  // CANONICAL_EXAMPLES
});

Deno.test("python prefix has Python preamble + #micro bridge + catalog, omits command/function/grammar", () => {
  const out = assemblePrefix("python", PARTS);
  assertEquals(out.includes("Python-miljø"), true);
  assertEquals(out.includes("#micro-bro"), true);
  assertEquals(out.includes("CATX"), true);
  assertEquals(out.includes("KOMX"), true);
  assertEquals(out.includes("CMDX"), false);
  assertEquals(out.includes("FNX"), false);
  assertEquals(out.includes("minimal grammatikk"), false);
  assertEquals(out.includes("Komplette eksempel-scripts"), false);
});

Deno.test("r prefix has R preamble, omits command/function", () => {
  const out = assemblePrefix("r", PARTS);
  assertEquals(out.includes("R-miljø"), true);
  assertEquals(out.includes("#micro-bro"), true);
  assertEquals(out.includes("CMDX"), false);
});

Deno.test("coerceMode validates the enum, defaulting to microdata", () => {
  assertEquals(coerceMode("python"), "python");
  assertEquals(coerceMode("r"), "r");
  assertEquals(coerceMode("microdata"), "microdata");
  assertEquals(coerceMode("bogus"), "microdata");
  assertEquals(coerceMode(undefined), "microdata");
});
