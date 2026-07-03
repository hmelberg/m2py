import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { tableMetadata } from "./table-metadata.ts";
import { parseRegistry } from "../registry.ts";

const REG = parseRegistry([
  { id: "ssb", navn: "SSB", utgiver: "SSB", tillit: "offisiell", tilgang: "pxweb",
    base_url: "https://data.ssb.no/api/pxwebapi/v2-beta/", cors: true,
    sporrings_url_mal: "https://data.ssb.no/api/pxwebapi/v2-beta/tables/{id}/data?valueCodes[{var}]={koder}&outputFormat=csv" },
  { id: "owid", navn: "OWID", utgiver: "OWID", tillit: "etablert", tilgang: "fil",
    base_url: "https://ourworldindata.org/grapher/", cors: true },
]);

// PxWebApi v2 /tables/{id}/metadata shape (subset): JSON-stat2-like dimensions
const META_FIXTURE = {
  label: "05839: Arbeidsledige (AKU), etter kjønn og år",
  dimension: {
    Kjonn: { label: "kjønn", category: { index: { "0": 0, "1": 1, "2": 2 },
      label: { "0": "Begge kjønn", "1": "Menn", "2": "Kvinner" } } },
    Tid: { label: "år", extension: { elimination: false },
      category: { index: Object.fromEntries(Array.from({ length: 50 }, (_, i) => [String(1996 + i), i])),
        label: Object.fromEntries(Array.from({ length: 50 }, (_, i) => [String(1996 + i), String(1996 + i)])) } },
  },
  role: { time: ["Tid"] },
};

function fakeFetch(payload: unknown, capture: string[]): typeof fetch {
  return ((input: string | URL | Request) => {
    capture.push(String(input));
    return Promise.resolve(new Response(JSON.stringify(payload), { status: 200 }));
  }) as typeof fetch;
}

Deno.test("pxweb metadata: variables, time flag, value cap, query template", async () => {
  const calls: string[] = [];
  const meta = await tableMetadata("ssb", "05839", { registry: REG, fetchImpl: fakeFetch(META_FIXTURE, calls) });
  assertEquals(calls[0], "https://data.ssb.no/api/pxwebapi/v2-beta/tables/05839/metadata?lang=no");
  assertEquals(meta.title.startsWith("05839"), true);
  const kjonn = meta.variables.find((v) => v.code === "Kjonn")!;
  assertEquals(kjonn.time, false);
  assertEquals(kjonn.values.length, 3);
  assertEquals(kjonn.values[1], { code: "1", label: "Menn" });
  const tid = meta.variables.find((v) => v.code === "Tid")!;
  assertEquals(tid.time, true);
  assertEquals(tid.values.length, 40);          // capped
  assertEquals(tid.valuesTruncated, true);
  assertEquals(meta.queryUrlTemplate?.includes("{id}") ?? true, false); // {id} substituted
});

Deno.test("non-pxweb source throws with probe guidance", async () => {
  let threw = "";
  try { await tableMetadata("owid", "co2", { registry: REG }); } catch (e) { threw = String(e); }
  if (!threw.includes("probe")) throw new Error("ventet probe-henvisning: " + threw);
});
