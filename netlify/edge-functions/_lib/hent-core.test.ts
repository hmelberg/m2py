import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { handleHent } from "./hent-core.ts";
import { parseRegistry } from "./registry.ts";

const REG = parseRegistry([{
  id: "fred", navn: "FRED", utgiver: "Fed", tillit: "etablert", tilgang: "rest",
  base_url: "https://api.stlouisfed.org/fred/", cors: false,
  auth: { type: "api_key", env: "FRED_API_KEY", plassering: "query:api_key" },
}]);

function fakeFetch(log: string[]): typeof fetch {
  return ((input: string | URL | Request, init?: RequestInit) => {
    log.push(`${init?.method ?? "GET"} ${String(input)}`);
    if (init?.body) log.push(`body=${init.body}`);
    return Promise.resolve(new Response("csv,data\n1,2", {
      status: 200, headers: { "content-type": "text/csv" },
    }));
  }) as typeof fetch;
}

const deps = (log: string[], env: Record<string, string> = {}) => ({
  registry: REG,
  getEnv: (k: string) => env[k],
  fetchImpl: fakeFetch(log),
});

function req(qs: string): Request {
  return new Request(`https://app.test/api/hent?${qs}`, { method: "GET" });
}

Deno.test("handleHent proxies a public GET and passes content-type", async () => {
  const log: string[] = [];
  const r = await handleHent(req("url=" + encodeURIComponent("https://example.org/d.csv")), deps(log));
  assertEquals(r.status, 200);
  assertEquals(r.headers.get("content-type"), "text/csv");
  assertEquals(await r.text(), "csv,data\n1,2");
});

Deno.test("handleHent injects key only for registry-host URLs", async () => {
  const log: string[] = [];
  const d = deps(log, { FRED_API_KEY: "K123" });
  await handleHent(req("url=" + encodeURIComponent("https://api.stlouisfed.org/fred/series?series_id=UNRATE")), d);
  if (!log[0].includes("api_key=K123")) throw new Error("nøkkel ikke injisert: " + log[0]);
  const log2: string[] = [];
  await handleHent(req("url=" + encodeURIComponent("https://evil.example/fred/series")), { ...d, fetchImpl: fakeFetch(log2) });
  if (log2[0]?.includes("K123")) throw new Error("nøkkel lekket til fremmed vert");
});

Deno.test("handleHent rejects private URLs and missing url", async () => {
  assertEquals((await handleHent(req("url=" + encodeURIComponent("http://169.254.169.254/x")), deps([]))).status, 400);
  assertEquals((await handleHent(req("nope=1"), deps([]))).status, 400);
});

Deno.test("handleHent GET-wraps a POST body as application/json", async () => {
  const log: string[] = [];
  const body = JSON.stringify({ query: [], response: { format: "csv" } });
  await handleHent(req("url=" + encodeURIComponent("https://statfin.stat.fi/PXWeb/api/v1/en/t") + "&body=" + encodeURIComponent(body)), deps(log));
  assertEquals(log[0].startsWith("POST "), true);
  assertEquals(log[1], `body=${body}`);
});

Deno.test("handleHent caps oversized body param", async () => {
  const big = "x".repeat(20_001);
  const r = await handleHent(req("url=" + encodeURIComponent("https://example.org/t") + "&body=" + encodeURIComponent(big)), deps([]));
  assertEquals(r.status, 413);
});

Deno.test("handleHent never echoes upstream fetch errors (key leak) to the client", async () => {
  const rejectingFetch: typeof fetch = (() =>
    Promise.reject(new TypeError(
      "error sending request for url (https://api.stlouisfed.org/fred/series?api_key=K123): connect error",
    ))) as unknown as typeof fetch;
  const d = { registry: REG, getEnv: (k: string) => ({ FRED_API_KEY: "K123" } as Record<string, string>)[k], fetchImpl: rejectingFetch };
  const r = await handleHent(req("url=" + encodeURIComponent("https://api.stlouisfed.org/fred/series?series_id=UNRATE")), d);
  assertEquals(r.status, 502);
  const text = await r.text();
  if (text.includes("K123")) throw new Error("nøkkel lekket i feilrespons: " + text);
  if (text.includes("stlouisfed")) throw new Error("kilde-URL lekket i feilrespons: " + text);
});
