import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { probeUrl } from "./probe.ts";

function fakeFetch(body: string, headers: Record<string, string>): typeof fetch {
  return ((_i: string | URL | Request) =>
    Promise.resolve(new Response(body, { status: 200, headers }))) as typeof fetch;
}

Deno.test("probe CSV: header + sample rows + CORS flag", async () => {
  const csv = "kommune;aar;ledighet\n0301;2024;2.1\n1103;2024;2.4\n5001;2024;1.9\n";
  const r = await probeUrl("https://x.example/d.csv", {
    fetchImpl: fakeFetch(csv, { "content-type": "text/csv", "access-control-allow-origin": "*" }),
  });
  assertEquals(r.ok, true);
  assertEquals(r.cors, true);
  assertEquals(r.columns, ["kommune", "aar", "ledighet"]);
  assertEquals(r.sampleRows.length, 2);
  assertEquals(r.sampleRows[0], ["0301", "2024", "2.1"]);
});

Deno.test("probe JSON-stat: dimension ids as columns", async () => {
  const js = JSON.stringify({ label: "t", dimension: { Region: {}, Tid: {} }, value: [1, 2] });
  const r = await probeUrl("https://x.example/js", {
    fetchImpl: fakeFetch(js, { "content-type": "application/json" }),
  });
  assertEquals(r.columns, ["Region", "Tid"]);
});

Deno.test("probe JSON array-of-objects: keys as columns", async () => {
  const j = JSON.stringify([{ date: "2024-01-01", value: 3.2 }, { date: "2024-02-01", value: 3.1 }]);
  const r = await probeUrl("https://x.example/arr", {
    fetchImpl: fakeFetch(j, { "content-type": "application/json" }),
  });
  assertEquals(r.columns, ["date", "value"]);
  assertEquals(r.cors, false);
});

Deno.test("probe: non-public URL and HTTP errors reported, not thrown", async () => {
  const bad = await probeUrl("http://localhost/x");
  assertEquals(bad.ok, false);
  if (!bad.note?.includes("blokkert")) throw new Error("ventet blokkert-notat");
  const e404 = await probeUrl("https://x.example/gone", {
    fetchImpl: ((_i: string | URL | Request) => Promise.resolve(new Response("nope", { status: 404 }))) as typeof fetch,
  });
  assertEquals(e404.ok, false);
  assertEquals(e404.status, 404);
});
