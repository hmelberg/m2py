import { assertEquals, assertRejects } from "https://deno.land/std@0.224.0/assert/mod.ts";

for (const f of ["data-directives.js", "data-loader.js", "enc-crypto.js"]) {
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
  assertEquals(out.loads.map((o: { alias: string; format: string }) => [o.alias, o.format]),
    [["direkte", "csv"], ["sperret", "csv"]]);
  assertEquals(out.remote, []);
  // blocked URL retried via proxy with auth header
  const proxyCall = calls.find((c) => c.includes("/api/hent?url=https%3A%2F%2Fblocked.example"));
  if (!proxyCall?.includes("[auth]")) throw new Error("proxy-fallback mangler auth: " + calls.join(" | "));
});

Deno.test("resolveAndFetchLoads: BYOK-nøkkel sendes som X-Anthropic-Key på proxy-kall når token mangler", async () => {
  const calls: { url: string; headers: Record<string, string> }[] = [];
  const fetchImpl = ((input: string | URL | Request, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, headers: (init?.headers as Record<string, string>) ?? {} });
    if (url.startsWith("https://blocked.example/")) return Promise.reject(new TypeError("CORS"));
    return Promise.resolve(new Response("x,y\n1,2", { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const script = "# load https://blocked.example/d.csv as sperret";
  await DL.resolveAndFetchLoads(script, { fetchImpl, registry: [], anthropicKey: "sk-ant-test123" });
  const proxy = calls.find((c) => c.url.includes("/api/hent?url="));
  if (!proxy) throw new Error("ingen proxy-kall: " + calls.map((c) => c.url).join(" | "));
  assertEquals(proxy.headers["X-Anthropic-Key"], "sk-ant-test123");
  assertEquals(proxy.headers["Authorization"], undefined);
});

Deno.test("resolveAndFetchLoads: innloggingstoken har forrang over BYOK-nøkkel", async () => {
  const calls: { url: string; headers: Record<string, string> }[] = [];
  const fetchImpl = ((input: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(input), headers: (init?.headers as Record<string, string>) ?? {} });
    return Promise.resolve(new Response("x,y\n1,2", { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const script = "# load /api/hent?url=https%3A%2F%2Fx.example%2Fd.csv as via";
  await DL.resolveAndFetchLoads(script, { fetchImpl, registry: [], authToken: "T", anthropicKey: "sk-ant-test123" });
  const proxy = calls.find((c) => c.url.includes("/api/hent?url="));
  if (!proxy) throw new Error("ingen proxy-kall");
  assertEquals(proxy.headers["Authorization"], "Bearer T");
  assertEquals(proxy.headers["X-Anthropic-Key"], undefined);
});

Deno.test("sniffFormat: content-type wins over URL", () => {
  const mk = (ct: string) => new Response("", { headers: { "content-type": ct } });
  assertEquals(DL._sniffFormat(mk("text/html; charset=utf-8"), "https://x/api"), "html");
  assertEquals(DL._sniffFormat(mk("application/json"), "https://x/d.csv"), "json");
  assertEquals(DL._sniffFormat(mk("text/csv"), "https://x/tabell?format=csv"), "csv");
});

// deno-lint-ignore no-explicit-any
const EC = (globalThis as any).EncCrypto;

function jsonResp(obj: unknown, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
}

Deno.test("anvil grant: fetch + decrypt with released key (mode 3)", async () => {
  const plain = new TextEncoder().encode("a,b\n1,2\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access?id=helse2025"))
      return Promise.resolve(jsonResp({ remote_only: false, location: "https://x.example/d.enc.json",
        payload_format: "csv", fingerprint: envelope.fingerprint, encrypted: true, key }));
    if (url === "https://x.example/d.enc.json")
      return Promise.resolve(jsonResp(envelope));
    throw new Error("uventet URL: " + url);
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect helse2025 as h\n# load h as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.remote, []);
  assertEquals(out.loads[0].format, "csv");
  assertEquals(new TextDecoder().decode(out.loads[0].bytes), "a,b\n1,2\n");
});

Deno.test("anvil remote_only routes to remote list", async () => {
  const fetchImpl = (() =>
    Promise.resolve(jsonResp({ remote_only: true, default_exec: "remote" }))) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect kreft as k, key(ask)\n# load k as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.loads, []);
  assertEquals(out.remote, [{ alias: "df", sourceId: "kreft", key: "ask" }]);
});

Deno.test("anvil 404 gives norsk tilgangsfeil", async () => {
  const fetchImpl = (() =>
    Promise.resolve(jsonResp({ error: "unknown source: x" }, 404))) as typeof fetch;
  await assertRejects(
    () => DL.resolveAndFetchLoads("# connect ukjent as u\n# load u as df",
      { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" }),
    Error, "mangler tilgang");
});

Deno.test("anvil 404 tags the error for the request-access UI (roadmap §2a)", async () => {
  const fetchImpl = (() =>
    Promise.resolve(jsonResp({ error: "unknown source: x" }, 404))) as typeof fetch;
  try {
    await DL.resolveAndFetchLoads("# connect ukjent as u\n# load u as df",
      { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
    throw new Error("expected rejection");
  } catch (e) {
    assertEquals((e as { accessDenied?: boolean }).accessDenied, true);
    assertEquals((e as { sourceId?: string }).sourceId, "ukjent");
    assertEquals((e as { apiBase?: string }).apiBase, "https://api.test");
  }
});

Deno.test("mode 1: url envelope + key literal decrypts without anvil", async () => {
  const plain = new TextEncoder().encode("x,y\n9,8\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = (() => Promise.resolve(jsonResp(envelope))) as typeof fetch;
  const out = await DL.resolveAndFetchLoads(
    `# load https://x.example/d.enc.json as df, key(${key})`,
    { fetchImpl, registry: [] });
  assertEquals(new TextDecoder().decode(out.loads[0].bytes), "x,y\n9,8\n");
});

Deno.test("envelope without key prompts via promptKey(ask)", async () => {
  const plain = new TextEncoder().encode("q\n1\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = (() => Promise.resolve(jsonResp(envelope))) as typeof fetch;
  let asked = "";
  const out = await DL.resolveAndFetchLoads(
    "# load https://x.example/d.enc.json as df, key(ask)",
    { fetchImpl, registry: [], promptKey: (alias: string) => { asked = alias; return Promise.resolve(key); } });
  assertEquals(asked, "df");
  assertEquals(new TextDecoder().decode(out.loads[0].bytes), "q\n1\n");
});

Deno.test("grant fingerprint mismatch is refused (byttet fil)", async () => {
  const { envelope, key } = await EC.encryptBytes(new TextEncoder().encode("a\n1\n"), "csv");
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: "feilfinger", encrypted: true, key }));
    return Promise.resolve(jsonResp(envelope));
  }) as typeof fetch;
  await assertRejects(
    () => DL.resolveAndFetchLoads("# connect s as s\n# load s as df",
      { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" }),
    Error, "endret siden den ble registrert");
});

Deno.test("strict grant marks the load and carries level", async () => {
  const plain = new TextEncoder().encode("a,b\n1,2\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: envelope.fingerprint,
      encrypted: true, local_profile: "strict", level: "protected", key }));
    return Promise.resolve(jsonResp(envelope));
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect helse as h\n# load h as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T",
      authorizeStrict: () => Promise.resolve({}) });
  assertEquals(out.loads[0].strict, true);
  assertEquals(out.loads[0].level, "protected");
  // V4: strict+kryptert dekrypteres ALDRI i JS — konvolutt + nøkkel videre
  assertEquals(out.loads[0].bytes, null);
  assertEquals(out.loads[0].envelope.format, "safepy-enc-v1");
  assertEquals(out.loads[0].key, key);
});

Deno.test("strict without authorize callback is refused", async () => {
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: null, encrypted: true,
      local_profile: "strict", level: "protected" }));
    return Promise.resolve(jsonResp({}));
  }) as typeof fetch;
  await assertRejects(
    () => DL.resolveAndFetchLoads("# connect helse as h\n# load h as df",
      { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" }),
    Error, "authorizeStrict");
});

Deno.test("strict without any key never prompts — hard refusal", async () => {
  const plain = new TextEncoder().encode("a\n1\n");
  const { envelope } = await EC.encryptBytes(plain, "csv");
  let prompted = false;
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: envelope.fingerprint,
      encrypted: true, local_profile: "strict", level: "protected" }));
    return Promise.resolve(jsonResp(envelope));
  }) as typeof fetch;
  await assertRejects(
    () => DL.resolveAndFetchLoads("# connect helse as h\n# load h as df",
      { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T",
        authorizeStrict: () => Promise.resolve({}),
        promptKey: () => { prompted = true; return Promise.resolve("x".repeat(43)); } }),
    Error, "ikke autorisert med nøkkel");
  if (prompted) throw new Error("strict skal aldri bruke promptKey");
});

Deno.test("open grant leaves strict undefined", async () => {
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.csv",
      payload_format: "csv", fingerprint: null, encrypted: false,
      local_profile: "open", level: "public" }));
    return Promise.resolve(new Response("a,b\n1,2", { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect demo as d\n# load d as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.loads[0].strict, undefined);
});

Deno.test("protected source with local_mode=open exposes level without forcing strict", async () => {
  // The sidebar's click-to-view gating needs the real level even when a
  // registered source's local_mode allows it to run in the ordinary
  // non-strict path — l.strict must stay false/undefined here, but l.level
  // must still say "protected" so the UI doesn't treat it as public.
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.csv",
      payload_format: "csv", fingerprint: null, encrypted: false,
      local_profile: "open", level: "protected" }));
    return Promise.resolve(new Response("a,b\n1,2", { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect demo as d\n# load d as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.loads[0].level, "protected");
  assertEquals(out.loads[0].strict, undefined);
});

Deno.test("strict encrypted grant uses authorizeStrict for keys", async () => {
  const plain = new TextEncoder().encode("a\n1\n");
  const { envelope, key } = await EC.encryptBytes(plain, "csv");
  let authorizedWith: string[] = [];
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(jsonResp({
      remote_only: false, location: "https://x.example/d.enc.json",
      payload_format: "csv", fingerprint: envelope.fingerprint,
      encrypted: true, local_profile: "strict", level: "protected" }));
    return Promise.resolve(jsonResp(envelope));
  }) as typeof fetch;
  const out = await DL.resolveAndFetchLoads("# connect helse as h\n# load h as df",
    { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T",
      authorizeStrict: (ids: string[]) => { authorizedWith = ids; return Promise.resolve({ helse: key }); } });
  assertEquals(authorizedWith, ["helse"]);
  // V4: nøkkelen fra authorize følger konvolutten — dekryptering skjer i kjøringen
  assertEquals(out.loads[0].bytes, null);
  assertEquals(out.loads[0].envelope.format, "safepy-enc-v1");
  assertEquals(out.loads[0].key, key);
  assertEquals(out.loads[0].strict, true);
});

Deno.test("resolveAndAssemble: fetches spec sources + returns spec", async () => {
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    const body = url.includes("people") ? "pid,income\n1,10\n2,20" : "pid,amount\n1,5";
    return Promise.resolve(new Response(body, { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const script = [
    "# connect https://x.example/people.csv as p",
    "# connect https://x.example/sales.csv as s",
    "# create-dataset panel, key(pid)",
    "# import p/income into panel",
    "# load s as sales",
    "# join sales into panel on pid",
  ].join("\n");
  const out = await DL.resolveAndAssemble(script, { fetchImpl, registry: [] });
  assertEquals(out.remote, []);
  assertEquals(out.sources.map((x: {alias: string}) => x.alias).sort(), ["p", "s"]);
  assertEquals(out.spec.datasets.find((d: {name: string}) => d.name === "panel").key, "pid");
  const p = out.sources.find((x: {alias: string}) => x.alias === "p");
  assertEquals(new TextDecoder().decode(p.bytes), "pid,income\n1,10\n2,20");
});

Deno.test("resolveSourcesOnly: no network calls, returns url/format/table per source", async () => {
  const script = [
    "# connect https://x.example/panel.duckdb as db, kind(duckdb)",
    "# connect https://x.example/inc.parquet as inc, kind(parquet)",
    "# create-dataset combined, key(pid)",
    "# import db/patients.age into combined",
    "# import inc/income into combined",
  ].join("\n");
  const out = await DL.resolveSourcesOnly(script, { registry: [] });
  assertEquals(out.descriptors["db__patients"], { url: "https://x.example/panel.duckdb", format: "duckdb", table: "patients" });
  assertEquals(out.descriptors["inc"], { url: "https://x.example/inc.parquet", format: "parquet", table: undefined });
});

Deno.test("resolveSourcesOnly: anvil/protected sources are excluded from descriptors", async () => {
  const script = "# connect helse2025 as h\n# create-dataset d, key(pid)\n# import h/x into d";
  const out = await DL.resolveSourcesOnly(script, { registry: [] });
  assertEquals(out.descriptors, {});
});

Deno.test("resolveAndAssemble: a remote source routes the whole run remote", async () => {
  const fetchImpl = ((input: string | URL | Request) => {
    const url = String(input);
    if (url.includes("/source_access")) return Promise.resolve(
      new Response(JSON.stringify({ remote_only: true, default_exec: "remote" }),
        { status: 200, headers: { "content-type": "application/json" } }));
    return Promise.resolve(new Response("pid,x\n1,2", { status: 200, headers: { "content-type": "text/csv" } }));
  }) as typeof fetch;
  const script = [
    "# connect helse2025 as h",
    "# create-dataset panel, key(pid)",
    "# import h/x into panel",
  ].join("\n");
  const out = await DL.resolveAndAssemble(script, { fetchImpl, registry: [], apiBase: "https://api.test", authToken: "T" });
  assertEquals(out.remote, [{ alias: "h", sourceId: "helse2025", key: undefined }]);
  assertEquals(out.sources, []);
});

Deno.test("sniffFormat: explicit kind always wins over content-type/extension", () => {
  const mk = (ct: string) => new Response("", { headers: { "content-type": ct } });
  assertEquals(DL._sniffFormat(mk("text/csv"), "https://x/panel.duckdb", "duckdb"), "duckdb");
  assertEquals(DL._sniffFormat(mk(""), "https://x/export?id=42", "sqlite"), "sqlite");
});

Deno.test("sniffFormat: .duckdb/.sqlite extensions sniffed without kind()", () => {
  const mk = () => new Response("", { headers: {} });
  assertEquals(DL._sniffFormat(mk(), "https://x.example/panel.duckdb"), "duckdb");
  assertEquals(DL._sniffFormat(mk(), "https://x.example/small.sqlite"), "sqlite");
  assertEquals(DL._sniffFormat(mk(), "https://x.example/small.sqlite3"), "sqlite");
});

Deno.test("resolveAndFetchLoads: duckdb load carries table + kind through to the output item", async () => {
  const fetchImpl = (() => Promise.resolve(
    new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { "content-type": "application/octet-stream" } })
  )) as typeof fetch;
  const script = [
    "# connect https://x.example/panel.duckdb as db, kind(duckdb)",
    "# load db/patients as p",
  ].join("\n");
  const out = await DL.resolveAndFetchLoads(script, { fetchImpl, registry: [] });
  assertEquals(out.loads[0].format, "duckdb");
  assertEquals(out.loads[0].table, "patients");
  assertEquals(out.loads[0].kind, "duckdb");
});

Deno.test("resolveAndFetchLoads: two loads against the same duckdb URL fetch the file only once", async () => {
  let fetchCount = 0;
  const fetchImpl = (() => {
    fetchCount++;
    return Promise.resolve(new Response(new Uint8Array([9, 9]),
      { status: 200, headers: { "content-type": "application/octet-stream" } }));
  }) as typeof fetch;
  const script = [
    "# connect https://x.example/panel.duckdb as db, kind(duckdb)",
    "# load db/patients as p",
    "# load db/visits as v",
  ].join("\n");
  const out = await DL.resolveAndFetchLoads(script, { fetchImpl, registry: [] });
  assertEquals(out.loads.map((l: { alias: string }) => l.alias), ["p", "v"]);
  assertEquals(fetchCount, 1);
});

Deno.test("resolveAndAssemble: table-qualified sources re-fetch via alias/table, not the synthetic key", async () => {
  const seen: string[] = [];
  const fetchImpl = ((input: string | URL | Request) => {
    seen.push(String(input));
    return Promise.resolve(new Response(new Uint8Array([1]),
      { status: 200, headers: { "content-type": "application/octet-stream" } }));
  }) as typeof fetch;
  const script = [
    "# connect https://x.example/panel.duckdb as db, kind(duckdb)",
    "# create-dataset panel, key(pid)",
    "# import db/patients.age, db/patients.sex into panel",
  ].join("\n");
  const out = await DL.resolveAndAssemble(script, { fetchImpl, registry: [] });
  assertEquals(out.sources.map((s: { alias: string }) => s.alias), ["db__patients"]);
  assertEquals(out.sources[0].table, "patients");
  assertEquals(seen, ["https://x.example/panel.duckdb"]);
});
