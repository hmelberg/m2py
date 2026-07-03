import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

// js/data-directives.js is a plain browser script: evaluate it and read the global.
const src = await Deno.readTextFile(new URL("../../../js/data-directives.js", import.meta.url));
(0, eval)(src);
// deno-lint-ignore no-explicit-any
const DD = (globalThis as any).DataDirectives;

const REG = [
  { id: "ssb", base_url: "https://data.ssb.no/api/pxwebapi/v2-beta/", cors: true },
  { id: "fred", base_url: "https://api.stlouisfed.org/fred/", cors: false,
    auth: { type: "api_key", env: "FRED_API_KEY", plassering: "query:api_key" } },
];

Deno.test("parse: connect + load + legacy require URL; comment markers #, --, //", () => {
  const script = [
    "# connect https://data.ssb.no/api/pxwebapi/v2-beta/tables as ssb",
    "-- connect fred",
    "// load https://ourworldindata.org/grapher/co2.csv as co2",
    "# load ssb/05839/data?outputFormat=csv as ledighet",
    "# require https://x.example/gammel.csv as gammel",
    "# require registrert_kilde as srv",      // named require: NOT ours
    "x = 1  # load ikke-et-direktiv",          // not at line start pattern -> ignored
  ].join("\n");
  const p = DD.parse(script);
  assertEquals(p.connects, [
    { target: "https://data.ssb.no/api/pxwebapi/v2-beta/tables", alias: "ssb" },
    { target: "fred", alias: "fred" },
  ]);
  assertEquals(p.loads.map((l: { alias: string }) => l.alias), ["co2", "ledighet", "gammel"]);
  assertEquals(p.loads[2].verb, "require");
});

Deno.test("resolve: alias expansion, registry id, proxy flags", () => {
  const script = [
    "# connect https://data.ssb.no/api/pxwebapi/v2-beta/ as ssb",
    "# connect fred",
    "# load ssb/tables/05839/data?outputFormat=csv as ledighet",
    "# load fred/series/observations?series_id=UNRATE&file_type=json as us",
    "# load https://ourworldindata.org/grapher/co2.csv as co2",
    "# load /api/hent?url=https%3A%2F%2Fstatfin.stat.fi%2Ft&body=%7B%7D as fi",
  ].join("\n");
  const r = DD.resolve(DD.parse(script), REG);
  assertEquals(r[0], {
    alias: "ledighet",
    url: "https://data.ssb.no/api/pxwebapi/v2-beta/tables/05839/data?outputFormat=csv",
    viaProxy: false,
  });
  assertEquals(r[1].viaProxy, true);   // fred: auth + no CORS
  assertEquals(r[1].url, "https://api.stlouisfed.org/fred/series/observations?series_id=UNRATE&file_type=json");
  assertEquals(r[2].viaProxy, false);
  assertEquals(r[3].viaProxy, true);   // explicit /api/hent
});

Deno.test("resolve: unknown alias and unknown registry id give errors", () => {
  const p = DD.parse("# load ukjent/sti.csv as x\n# connect finnesikke");
  const r = DD.resolve(p, REG);
  if (!r[0].error) throw new Error("ventet feil for ukjent alias");
  const p2 = DD.parse("# connect finnesikke as fk\n# load fk/x.csv as y");
  const r2 = DD.resolve(p2, REG);
  if (!r2[0].error) throw new Error("ventet feil for ukjent register-id");
});
