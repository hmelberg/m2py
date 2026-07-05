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
    { target: "https://data.ssb.no/api/pxwebapi/v2-beta/tables", alias: "ssb", options: {} },
    { target: "fred", alias: "fred", options: {} },
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
    key: undefined,
    exec: undefined,
  });
  assertEquals(r[1].viaProxy, true);   // fred: auth + no CORS
  assertEquals(r[1].url, "https://api.stlouisfed.org/fred/series/observations?series_id=UNRATE&file_type=json");
  assertEquals(r[2].viaProxy, false);
  assertEquals(r[3].viaProxy, true);   // explicit /api/hent
});

Deno.test("resolve: unknown alias errors; unknown registry id becomes anvil", () => {
  const p = DD.parse("# load ukjent/sti.csv as x\n# connect finnesikke");
  const r = DD.resolve(p, REG);
  if (!r[0].error) throw new Error("ventet feil for ukjent alias");
  // Ukjent register-id er nå en Anvil-kilde (spec §1, regel 3) — feilen kommer
  // først ved /source_access-oppslaget (404 med norsk melding).
  const p2 = DD.parse("# connect finnesikke as fk\n# load fk/x.csv as y");
  const r2 = DD.resolve(p2, REG);
  assertEquals(r2[0].anvil, "finnesikke");
});

Deno.test("options: key() and exec() parse on connect and load", () => {
  const script = [
    "# connect helse2025 as h, key(ask)",
    "# connect kilde2 as k, key(qL7xK2mN9pR4sT6v), exec(remote)",
    "# load https://x.example/d.enc.json as df, key(abcDEF123)",
  ].join("\n");
  const p = DD.parse(script);
  assertEquals(p.connects[0].options, { key: "ask" });
  assertEquals(p.connects[1].options, { key: "qL7xK2mN9pR4sT6v", exec: "remote" });
  assertEquals(p.loads[0].options, { key: "abcDEF123" });
});

Deno.test("resolve: bare name not in registry becomes anvil source", () => {
  const script = [
    "# connect helse2025 as h, key(ask)",
    "# load h as df",
    "# connect ssb as s",
    "# load s/tables as t",
  ].join("\n");
  const r = DD.resolve(DD.parse(script), REG);
  assertEquals(r[0], { alias: "df", anvil: "helse2025", key: "ask", exec: undefined });
  assertEquals(r[1].viaProxy, false);            // ssb stays a registry source
  if (r[1].anvil) throw new Error("registry-id skal ikke bli anvil-kilde");
});

Deno.test("resolve: load-level key overrides connect-level key", () => {
  const p = DD.parse("# connect helse2025 as h, key(K1)\n# load h as df, key(K2)");
  const r = DD.resolve(p, REG);
  assertEquals(r[0].key, "K2");
});

Deno.test("scrubKeys: literals masked, ask kept", () => {
  const s = "# connect x as h, key(hemmelig123)\n# connect y as k, key(ask)";
  const out = DD.scrubKeys(s);
  if (out.includes("hemmelig123")) throw new Error("nøkkel lekket");
  if (!out.includes("key(***)")) throw new Error("mangler maskering");
  if (!out.includes("key(ask)")) throw new Error("key(ask) skal bevares");
});

Deno.test("parseAssembly: create-dataset + import + join + load", () => {
  const script = [
    "# connect people as p",
    "# connect sales_src as s",
    "# create-dataset panel, key(pid)",
    "# import p/income, p/edu into panel",
    "# import p/region into panel",
    "# load s as sales",
    "# join sales into panel on pid",
  ].join("\n");
  const { spec, errors } = DD.parseAssembly(script);
  assertEquals(errors, []);
  assertEquals(spec.sources.sort(), ["p", "s"]);
  const panel = spec.datasets.find((d: {name: string}) => d.name === "panel");
  assertEquals(panel.key, "pid");
  assertEquals(panel.steps.length, 3);
  assertEquals(panel.steps[0], {op: "import", source: "p", columns: ["income", "edu"], how: "left"});
  assertEquals(panel.steps[2], {op: "join", from: "sales", on: "pid", how: "left"});
  const sales = spec.datasets.find((d: {name: string}) => d.name === "sales");
  assertEquals(sales.load, "s");
});

Deno.test("parseAssembly: how override", () => {
  const { spec } = DD.parseAssembly(
    "# connect p as p\n# create-dataset d, key(id)\n# import p/x into d inner");
  assertEquals(spec.datasets[0].steps[0].how, "inner");
});

Deno.test("parseAssembly: import into missing dataset errors", () => {
  const { errors } = DD.parseAssembly("# connect p as p\n# import p/x into ghost");
  if (!errors.some((e: string) => e.includes("ghost"))) throw new Error("ventet feil for ukjent datasett");
});

Deno.test("parseAssembly: inline-URL load is NOT assembly (stays on the old path)", () => {
  // Assembly sources must be connect'd; a bare `load <url> as df` is the
  // legacy web-data path, so parseAssembly ignores it (empty spec).
  const { spec, errors } = DD.parseAssembly("# load https://x.example/d.csv as df");
  assertEquals(errors, []);
  assertEquals(spec.datasets, []);
  assertEquals(spec.sources, []);
});
