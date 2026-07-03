import { assertEquals, assertThrows } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  clearRegistryCache, findSource, loadRegistry, parseRegistry,
  renderRegistryBlock, sourceForUrl, type DataSource,
} from "./registry.ts";

const VALID = [{
  id: "ssb", navn: "Statistisk sentralbyrå (PxWebApi)", utgiver: "SSB",
  tillit: "offisiell", tilgang: "pxweb",
  base_url: "https://data.ssb.no/api/pxwebapi/v2-beta/",
  sok_endepunkt: "https://data.ssb.no/api/pxwebapi/v2-beta/tables?query={q}&lang=no",
  cors: true, join_nokler: ["kommunenummer", "år"],
}, {
  id: "fred", navn: "FRED", utgiver: "St. Louis Fed", tillit: "etablert",
  tilgang: "rest", base_url: "https://api.stlouisfed.org/fred/", cors: false,
  auth: { type: "api_key", env: "FRED_API_KEY", plassering: "query:api_key" },
}];

Deno.test("parseRegistry accepts valid entries", () => {
  const reg = parseRegistry(VALID);
  assertEquals(reg.length, 2);
  assertEquals(reg[0].id, "ssb");
});

Deno.test("parseRegistry rejects missing base_url and bad tillit", () => {
  assertThrows(() => parseRegistry([{ id: "x", tilgang: "rest", cors: true }]));
  assertThrows(() => parseRegistry([{ ...VALID[0], tillit: "hemmelig" }]));
  assertThrows(() => parseRegistry({ not: "an array" }));
});

Deno.test("findSource / sourceForUrl", () => {
  const reg = parseRegistry(VALID);
  assertEquals(findSource(reg, "fred")?.id, "fred");
  assertEquals(findSource(reg, "nope"), null);
  assertEquals(sourceForUrl(reg, "https://api.stlouisfed.org/fred/series?x=1")?.id, "fred");
  assertEquals(sourceForUrl(reg, "https://evil.example/fred/"), null);
  assertEquals(sourceForUrl(reg, "not a url"), null);
});

Deno.test("loadRegistry fetches once and caches", async () => {
  clearRegistryCache();
  let calls = 0;
  const fetchImpl = ((_u: string | URL | Request) => {
    calls++;
    return Promise.resolve(new Response(JSON.stringify(VALID), { status: 200 }));
  }) as typeof fetch;
  const a = await loadRegistry("https://app.test", fetchImpl);
  const b = await loadRegistry("https://app.test", fetchImpl);
  assertEquals(a.length, 2);
  assertEquals(b, a);
  assertEquals(calls, 1);
  clearRegistryCache();
});

Deno.test("renderRegistryBlock is compact and byte-stable", () => {
  const reg = parseRegistry(VALID) as DataSource[];
  const block = renderRegistryBlock(reg);
  assertEquals(block, renderRegistryBlock(reg)); // stable
  if (!block.includes("ssb") || !block.includes("søkbar")) throw new Error("mangler innhold:\n" + block);
  if (block.includes("FRED_API_KEY")) throw new Error("auth-detaljer skal ikke i prompt");
});
