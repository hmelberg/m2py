import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { searchCatalog } from "./search-catalog.ts";
import { parseRegistry } from "../registry.ts";

const REG = parseRegistry([
  { id: "ssb", navn: "SSB", utgiver: "SSB", tillit: "offisiell", tilgang: "pxweb",
    base_url: "https://data.ssb.no/api/pxwebapi/v2-beta/",
    sok_endepunkt: "https://data.ssb.no/api/pxwebapi/v2-beta/tables?query={q}&lang=no", cors: true },
  { id: "datanorge", navn: "data.norge.no", utgiver: "Digdir", tillit: "offisiell", tilgang: "ckan",
    base_url: "https://data.norge.no/",
    sok_endepunkt: "https://search.api.fellesdatakatalog.digdir.no/search", cors: true },
  { id: "owid", navn: "OWID", utgiver: "OWID", tillit: "etablert", tilgang: "fil",
    base_url: "https://ourworldindata.org/grapher/", cors: true },
]);

// PxWebApi v2 /tables response shape (subset)
const PXWEB_FIXTURE = {
  tables: [
    { id: "07459", label: "Befolkning, etter region, år og alder", firstPeriod: "1986", lastPeriod: "2026" },
    { id: "05839", label: "Arbeidsledige (AKU)", firstPeriod: "1996", lastPeriod: "2026" },
  ],
};

// Felles datakatalog /search response shape (subset)
const FDK_FIXTURE = {
  hits: [
    { id: "abc-123", title: { nb: "Drivstoffpriser" }, uri: "https://data.norge.no/datasets/abc-123" },
  ],
};

function fakeFetch(payload: unknown, capture: string[], bodies?: string[]): typeof fetch {
  return ((input: string | URL | Request, init?: RequestInit) => {
    capture.push(`${init?.method ?? "GET"} ${String(input)}`);
    if (bodies) bodies.push(String(init?.body ?? ""));
    return Promise.resolve(new Response(JSON.stringify(payload), { status: 200 }));
  }) as typeof fetch;
}

Deno.test("pxweb adapter: builds search URL, maps hits", async () => {
  const calls: string[] = [];
  const hits = await searchCatalog("ssb", "arbeidsledighet", { registry: REG, fetchImpl: fakeFetch(PXWEB_FIXTURE, calls) });
  assertEquals(calls[0], "GET https://data.ssb.no/api/pxwebapi/v2-beta/tables?query=arbeidsledighet&lang=no");
  assertEquals(hits.length, 2);
  assertEquals(hits[1], {
    source: "ssb", id: "05839", title: "Arbeidsledige (AKU)", period: "1996–2026",
    url: "https://data.ssb.no/api/pxwebapi/v2-beta/tables/05839",
  });
});

Deno.test("ckan/fdk adapter: POSTs query, maps hits", async () => {
  const calls: string[] = [];
  const bodies: string[] = [];
  const hits = await searchCatalog("datanorge", "drivstoff", { registry: REG, fetchImpl: fakeFetch(FDK_FIXTURE, calls, bodies) });
  assertEquals(calls[0].startsWith("POST https://search.api.fellesdatakatalog"), true);
  // Live API quirk (verified 2026-07-03): param is "q" (not "query"), and
  // filters.type must be restricted to "datasets" or results are dominated
  // by CONCEPT/other entity types.
  assertEquals(JSON.parse(bodies[0]), { q: "drivstoff", filters: { type: { value: "datasets" } } });
  assertEquals(hits[0].title, "Drivstoffpriser");
  assertEquals(hits[0].url, "https://data.norge.no/datasets/abc-123");
});

Deno.test("unknown and unsearchable sources throw clear errors", async () => {
  for (const [id, msg] of [["nope", "ukjent kilde"], ["owid", "ikke søkbar"]] as const) {
    let threw = "";
    try { await searchCatalog(id, "x", { registry: REG }); } catch (e) { threw = String(e); }
    if (!threw.includes(msg)) throw new Error(`${id}: ventet '${msg}', fikk: ${threw}`);
  }
});
