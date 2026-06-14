import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { groundNames, parsePickerResponse } from "./variable-picker.ts";

Deno.test("parsePickerResponse reads a clean JSON array", () => {
  assertEquals(parsePickerResponse('["A","B","C"]'), ["A", "B", "C"]);
});

Deno.test("parsePickerResponse extracts an array from prose/fences", () => {
  const reply = 'Her er de relevante:\n```json\n["INNTEKT_WLONN", "BEFOLKNING_KJOENN"]\n```';
  assertEquals(parsePickerResponse(reply), ["INNTEKT_WLONN", "BEFOLKNING_KJOENN"]);
});

Deno.test("parsePickerResponse returns [] on junk", () => {
  assertEquals(parsePickerResponse("ingen liste her"), []);
  assertEquals(parsePickerResponse(""), []);
  assertEquals(parsePickerResponse("[not, valid, json]"), []);
});

Deno.test("groundNames keeps only real names, dedupes, and caps", () => {
  const meta = { variables: { A: {}, B: {}, C: {} } };
  assertEquals(groundNames(["A", "X", "B", "A"], meta, 20), ["A", "B"]);
  assertEquals(groundNames(["A", "B", "C"], meta, 2), ["A", "B"]);
  assertEquals(groundNames(["nope"], meta, 20), []);
});
