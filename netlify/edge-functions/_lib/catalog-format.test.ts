import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { abbrevType, cleanDescription, extractValidPeriod, renderLabels } from "./catalog-format.ts";

Deno.test("abbrevType maps classes and surfaces date format", () => {
  assertEquals(abbrevType("Alfanumerisk", ""), "alfa");
  assertEquals(abbrevType("Numerisk (heltall)", ""), "num");
  assertEquals(abbrevType("Numerisk (heltall)", "date:yyyymm"), "num·date:yyyymm");
});

Deno.test("extractValidPeriod uses start month-day for Tverrsnitt", () => {
  const d = "Noe. Gyldighetsperiode: 2015-02-16 – 2025-09-30";
  assertEquals(extractValidPeriod(d, "Tverrsnitt"), "2015-02-16…2025-02-16");
});

Deno.test("extractValidPeriod uses end month-day for Akkumulert", () => {
  const d = "Gyldighetsperiode: 1993-12-31 – 2023-12-31";
  assertEquals(extractValidPeriod(d, "Akkumulert"), "1993-12-31…2023-12-31");
});

Deno.test("extractValidPeriod keeps true window for Forløp", () => {
  const d = "Gyldighetsperiode: 2011-01-01 – 2017-12-31";
  assertEquals(extractValidPeriod(d, "Forløp"), "2011-01-01…2017-12-31");
});

Deno.test("extractValidPeriod falls back to coarse year span", () => {
  assertEquals(extractValidPeriod("Gyldighetsperiode: 1993–2023", ""), "1993–2023");
});

Deno.test("cleanDescription strips boilerplate tail and truncates", () => {
  assertEquals(cleanDescription("Kjønn. Enhetstype: Person", ""), "Kjønn.");
  assertEquals(cleanDescription("", "Kort tittel"), "Kort tittel");
  assertEquals(cleanDescription("x".repeat(250), "").length, 200);
});

Deno.test("renderLabels inlines ≤12 labels and skips big codelists", () => {
  assertEquals(renderLabels({ "1": "Mann", "2": "Kvinne" }), " {1=Mann, 2=Kvinne}");
  const big: Record<string, string> = {};
  for (let i = 0; i < 13; i++) big[String(i)] = "x";
  assertEquals(renderLabels(big), "");
});
