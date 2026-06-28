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

import { renderFocusedBlock, renderNameList } from "./variable-picker.ts";

const META = {
  variables: {
    BEFOLKNING_KJOENN: {
      databank: "no.ssb.fdb",
      microdata_datatype: "Alfanumerisk",
      data_type: "",
      temporalitet: "Fast",
      enhetstype: "Person",
      short_title: "Kjønn",
      description: "Personens kjønn. Enhetstype: Person",
      labels: { "1": "Mann", "2": "Kvinne" },
    },
    NUS2000: {
      databank: "no.ssb.fdb",
      microdata_datatype: "Alfanumerisk",
      data_type: "",
      temporalitet: "Tverrsnitt",
      enhetstype: "Person",
      short_title: "Utdanning",
      description: "Utdanningskode. Gyldighetsperiode: 2000-10-01 – 2020-10-01",
      labels: Object.fromEntries(Array.from({ length: 30 }, (_, i) => [String(i), "niva" + i])),
    },
  },
};

Deno.test("renderNameList lists every variable name with a tag", () => {
  const out = renderNameList(META);
  assertEquals(out.includes("BEFOLKNING_KJOENN"), true);
  assertEquals(out.includes("NUS2000"), true);
  // Description is preferred over short_title (matches v1 renderCatalog).
  assertEquals(out.includes("Personens kjønn"), true);
});

Deno.test("renderFocusedBlock includes full (uncapped) codelist for picked vars", () => {
  const out = renderFocusedBlock(["NUS2000"], META);
  assertEquals(out.includes("niva29"), true);
  assertEquals(out.includes("NUS2000"), true);
  assertEquals(out.includes("Tverrsnitt"), true);
});

Deno.test("renderFocusedBlock returns empty string for no picks", () => {
  assertEquals(renderFocusedBlock([], META), "");
});

Deno.test("renderFocusedBlock uses injected codelist when var lacks inline labels", () => {
  const meta = {
    variables: {
      REGSYS_X: {
        databank: "no.ssb.fdb", microdata_datatype: "Alfanumerisk", data_type: "",
        temporalitet: "Tverrsnitt", enhetstype: "Person", short_title: "Yrke",
        description: "Yrkeskode", labels: {},
      },
    },
  };
  const codelists = { REGSYS_X: { "1": "Ledere", "2": "Akademiske yrker" } };
  const out = renderFocusedBlock(["REGSYS_X"], meta, codelists);
  assertEquals(out.includes("Akademiske yrker"), true);
});

Deno.test("renderFocusedBlock caps very large codelists", () => {
  const big: Record<string, string> = {};
  for (let i = 0; i < 250; i++) big[String(i)] = "k" + i;
  const meta = { variables: { V: { labels: {} } } };
  const out = renderFocusedBlock(["V"], meta, { V: big });
  assertEquals(out.includes("(+50 flere)"), true); // 250 - 200
});
