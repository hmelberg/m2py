import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";

for (const f of ["data-directives.js", "data-loader.js"]) {
  (0, eval)(await Deno.readTextFile(new URL(`../../../js/${f}`, import.meta.url)));
}
// deno-lint-ignore no-explicit-any
const DL = (globalThis as any).DataLoader;

Deno.test("resolveAndFetchLoads: fetches, sniffs format, proxy fallback on CORS", async () => {
  const calls: string[] = [];
  const fetchImpl = ((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push(url + ((init?.headers as Record<string, string>)?.Authorization ? " [auth]" : ""));
    if (url.startsWith("https://blocked.example/")) return Promise.reject(new TypeError("CORS"));
    const body = url.includes("/api/hent?") ? "a;b\n1;2" : "x,y\n3,4";
    return Promise.resolve(new Response(body, { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const script = [
    "# load https://open.example/d.csv as direkte",
    "# load https://blocked.example/d.csv as sperret",
  ].join("\n");
  const out = await DL.resolveAndFetchLoads(script, { fetchImpl, registry: [], authToken: "T" });
  assertEquals(out.map((o: { alias: string; format: string }) => [o.alias, o.format]),
    [["direkte", "csv"], ["sperret", "csv"]]);
  // blocked URL retried via proxy with auth header
  const proxyCall = calls.find((c) => c.includes("/api/hent?url=https%3A%2F%2Fblocked.example"));
  if (!proxyCall?.includes("[auth]")) throw new Error("proxy-fallback mangler auth: " + calls.join(" | "));
});

Deno.test("sniffFormat: content-type wins over URL", () => {
  const mk = (ct: string) => new Response("", { headers: { "content-type": ct } });
  assertEquals(DL._sniffFormat(mk("text/html; charset=utf-8"), "https://x/api"), "html");
  assertEquals(DL._sniffFormat(mk("application/json"), "https://x/d.csv"), "json");
  assertEquals(DL._sniffFormat(mk("text/csv"), "https://x/tabell?format=csv"), "csv");
});
