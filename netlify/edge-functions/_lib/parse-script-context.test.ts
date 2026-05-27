import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { detectLanguage, parsePersonvernComments, parsePersonvernDirectives } from "./parse-script-context.ts";

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

Deno.test("microdata-script detekteres", () => {
  const script = `
import all from BEFOLKNING
keep if alder >= 18
collapse (mean) inntekt, by(kommune)
`;
  assertEquals(detectLanguage(script), "microdata");
});

Deno.test("python-script detekteres", () => {
  const script = `
import pandas as pd
from sklearn import metrics
def analyze(df):
    return df.mean()
`;
  assertEquals(detectLanguage(script), "python");
});

Deno.test("r-script detekteres", () => {
  const script = `
library(dplyr)
df <- read.csv("data.csv")
df %>% filter(age >= 18)
`;
  assertEquals(detectLanguage(script), "r");
});

Deno.test("mixed-script detekteres", () => {
  const script = `
import all from BEFOLKNING
collapse (mean) inntekt
# Python-del nedenfor
import pandas as pd
df = pd.read_csv("output.csv")
`;
  assertEquals(detectLanguage(script), "mixed");
});

Deno.test("tomt script returnerer microdata som default", () => {
  assertEquals(detectLanguage(""), "microdata");
});

Deno.test("ett python-signal er ikke nok — returnerer microdata", () => {
  assertEquals(detectLanguage("def analyze(df):\n    return df"), "microdata");
});

Deno.test("to R-signaler er nok", () => {
  const script = `library(dplyr)\ndf <- read.csv("data.csv")`;
  assertEquals(detectLanguage(script), "r");
});

Deno.test("python/R tie går til python", () => {
  // 2 python-signaler (from import + def), 2 R-signaler (library + <-)
  const script = `library(dplyr)
from x import y
def foo():
    df <- 1
`;
  assertEquals(detectLanguage(script), "python");
});

// --- parsePersonvernDirectives ---

Deno.test("ingen direktiver gir tomt resultat", () => {
  const r = parsePersonvernDirectives("import all from BEFOLKNING");
  assertEquals(r, {});
});

Deno.test("revider-script: ja settes som true", () => {
  const r = parsePersonvernDirectives("// personvern: revider-script: ja");
  assertEquals(r.revider_script, true);
});

Deno.test("revider-script: nei settes som false", () => {
  const r = parsePersonvernDirectives("// personvern: revider-script: nei");
  assertEquals(r.revider_script, false);
});

Deno.test("revider-script: true settes som true", () => {
  const r = parsePersonvernDirectives("// personvern: revider-script: true");
  assertEquals(r.revider_script, true);
});

Deno.test("revider-script: false settes som false", () => {
  const r = parsePersonvernDirectives("// personvern: revider-script: false");
  assertEquals(r.revider_script, false);
});

Deno.test("# kommentartegn (Python/R) støttes i direktiv-parser", () => {
  const r = parsePersonvernDirectives("# personvern: revider-script: ja");
  assertEquals(r.revider_script, true);
});

Deno.test("direktiv inne i blokk fungerer", () => {
  const script = [
    "// personvern blokk start",
    "// formål: Test",
    "// revider-script: ja",
    "// personvern blokk slutt",
  ].join("\n");
  const r = parsePersonvernDirectives(script);
  assertEquals(r.revider_script, true);
});

Deno.test("ukjent direktiv-verdi ignoreres", () => {
  const r = parsePersonvernDirectives("// personvern: revider-script: kanskje");
  assertEquals(r.revider_script, undefined);
});

Deno.test("siste vinner ved konflikt i direktiv-parser", () => {
  const script = [
    "// personvern: revider-script: ja",
    "// personvern: revider-script: nei",
  ].join("\n");
  const r = parsePersonvernDirectives(script);
  assertEquals(r.revider_script, false);
});

Deno.test("strukturerte ikke-direktiv-felt påvirker ikke direktiv-parser", () => {
  const r = parsePersonvernDirectives("// personvern: formål: studere noe");
  assertEquals(r, {});
});
