import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { parsePersonvernComments } from "./parse-script-context.ts";

Deno.test("ingen kommentarer gir tom struktur", () => {
  const result = parsePersonvernComments("import all from BEFOLKNING\nkeep if alder >= 18");
  assertEquals(result.structured, {});
  assertEquals(result.freetext, []);
  assertEquals(result.hasAny, false);
});

Deno.test("enkeltlinje med kjent feltnavn er strukturert", () => {
  const script = "// personvern: formål: Studere utdanning og inntekt";
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Studere utdanning og inntekt");
  assertEquals(r.freetext, []);
  assertEquals(r.hasAny, true);
});

Deno.test("enkeltlinje uten kjent feltnavn er fritekst", () => {
  const script = "// personvern: kommune nødvendig for regionale analyser";
  const r = parsePersonvernComments(script);
  assertEquals(r.structured, {});
  assertEquals(r.freetext.length, 1);
  assertEquals(r.freetext[0].text, "kommune nødvendig for regionale analyser");
  assertEquals(r.freetext[0].line, 1);
});

Deno.test("blokk-form med strukturerte felter", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "// sentrale variabler: A, B",
    "// personvern blokk slutt",
    "import all from BEFOLKNING",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
  assertEquals(r.structured["sentrale variabler"], "A, B");
});

Deno.test("blokk med fritekst-linje", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "// fritekst-merknad uten feltnavn",
    "// personvern blokk slutt",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
  assertEquals(r.freetext.length, 1);
  assertEquals(r.freetext[0].text, "fritekst-merknad uten feltnavn");
});

Deno.test("# kommentartegn (Python/R) støttes", () => {
  const script = "# personvern: formål: Test fra Python";
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test fra Python");
});

Deno.test("manglende blokk-slutt — stopper ved ikke-kommentar-linje", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "import all from BEFOLKNING",
    "keep if alder >= 18",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
});

Deno.test("siste definisjon vinner ved konflikt", () => {
  const script = [
    "// personvern: formål: Gammel",
    "// personvern: formål: Ny",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Ny");
});

Deno.test("tom linje inne i blokk ignoreres", () => {
  const script = [
    "// personvern blokk start",
    "",
    "// formål: Test",
    "// personvern blokk slutt",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
});

Deno.test("CRLF line endings støttes", () => {
  const script = "// personvern: formål: Test\r\n// personvern: sentrale variabler: A\r\n";
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Test");
  assertEquals(r.structured["sentrale variabler"], "A");
});

Deno.test("# blokk-form støttes", () => {
  const script = [
    "# personvern blokk start",
    "# formål: Python-test",
    "# sentrale variabler: X, Y",
    "# personvern blokk slutt",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.structured["formål"], "Python-test");
  assertEquals(r.structured["sentrale variabler"], "X, Y");
});

Deno.test("hasAny er true i blokk-form path", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "// personvern blokk slutt",
  ].join("\n");
  const r = parsePersonvernComments(script);
  assertEquals(r.hasAny, true);
});
