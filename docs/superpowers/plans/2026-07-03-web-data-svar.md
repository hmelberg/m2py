# Web Mode (data-svar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A third, admin-only AI mode «Web» that answers general questions by discovering open data sources (agentic tool loop), generating a runnable python/r/duckdb script that loads verified data via `# connect`/`# load` directives, and auto-repairing up to 3 rounds.

**Architecture:** One agentic Netlify edge function (`data-svar.ts`) runs a server-side tool loop (search_catalog / table_metadata / probe + hosted web_search) against a curated registry (`data/data-sources.json`), then generates a script against *observed* schemas. An SSRF-hardened proxy (`/api/hent`) handles non-CORS and keyed sources (server-side key injection). The frontend gains connect/load directive parsing + local materialization and an auto-run/repair loop.

**Tech Stack:** Deno (Netlify Edge Functions), Anthropic Messages API (tool use + hosted web_search), plain browser JS (index.html/ai-chat.js), Pyodide/WebR/duckdb-wasm.

**Spec:** `docs/superpowers/specs/2026-07-03-web-data-svar-design.md` (read it first).

## Global Constraints

- Admin-only: the Web UI renders only for `user.is_admin`; `/api/data-svar` and `/api/hent` enforce admin server-side (403 otherwise).
- API keys never reach the browser or generated scripts; injection is server-side and only when the URL host matches the registry entry's host.
- Never generate against assumed schemas: dataset IDs/columns come from tool results; honest "fant ikke data" over fabrication.
- Directive verbs: `connect` (source) / `load` (extract). `require` stays as legacy extraction alias; microdata mode untouched.
- Tool budget ~12 client tool calls; auto-repair max 3 rounds.
- Tests: `deno test --allow-all netlify/edge-functions/_lib/` (std@0.224.0 asserts), fixture-driven, same style as existing `*.test.ts`.
- Commit after every task (dev branch). Norwegian user-facing strings; English code comments are fine (match file).
- Edge functions cannot bundle .md at runtime: prompt text lives as TS constants; `prompts/data-svar.md` is the source doc (kode-svar.md pattern).

## File Structure

```
data/data-sources.json                          registry (new)
netlify/edge-functions/
  hent.ts                                       CORS/key proxy (new)
  data-svar.ts                                  agentic endpoint (new)
  prompts/data-svar.md                          prompt source doc (new)
  _lib/
    registry.ts / registry.test.ts              load+validate registry, host match, prompt block (new)
    ssrf.ts / ssrf.test.ts                      public-URL guard + guarded fetch (new)
    auth.ts / auth.test.ts                      + runAdminGate/adminGate, allowedMethods (modify)
    anthropic.ts / anthropic.test.ts            + runAgenticStream tool loop (modify)
    data-svar-prompt.ts / data-svar-prompt.test.ts  system-prompt assembly + tool defs (new)
    tools/
      search-catalog.ts / search-catalog.test.ts   pxweb + ckan adapters (new)
      table-metadata.ts / table-metadata.test.ts   pxweb variable-level metadata (new)
      probe.ts / probe.test.ts                     endpoint probe: schema + CORS (new)
netlify.toml                                    map /api/data-svar + /api/hent (modify)
js/data-directives.js                           connect/load/require parser + resolver (new)
index.html                                      local materialization python/r/duckdb (modify)
js/ai-chat.js                                   Web mode UI, SSE progress/sources, auto-repair (modify)
docs/eval/data-svar-evalsett.md                 10-question eval set (new)
```

Ordering: Tasks 1–4 are server foundations (independent of AI), 5–8 tools + loop, 9–10 the endpoint, 11–13 frontend, 14 eval/docs. Each task is independently testable.

---

### Task 1: Registry — `data/data-sources.json` + `_lib/registry.ts`

**Files:**
- Create: `data/data-sources.json`
- Create: `netlify/edge-functions/_lib/registry.ts`
- Test: `netlify/edge-functions/_lib/registry.test.ts`

**Interfaces (Produces):**
- `interface SourceAuth { type: "api_key"; env: string; plassering: string }` (`plassering` = `"query:<param>"` or `"header:<name>"`)
- `interface DataSource { id: string; navn: string; utgiver: string; tillit: "offisiell"|"etablert"|"funnet"; tilgang: "pxweb"|"sdmx"|"rest"|"ckan"|"fil"; base_url: string; sok_endepunkt?: string; cors: boolean; join_nokler?: string[]; oppskrift?: Record<string,string>; sporrings_url_mal?: string; auth?: SourceAuth; quirks?: string }`
- `parseRegistry(json: unknown): DataSource[]` (throws on invalid)
- `loadRegistry(origin: string, fetchImpl?: typeof fetch): Promise<DataSource[]>` (module-cached; fetches `/data/data-sources.json`)
- `clearRegistryCache(): void` (tests)
- `findSource(reg: DataSource[], id: string): DataSource | null`
- `sourceForUrl(reg: DataSource[], url: string): DataSource | null` (exact host match on `base_url`)
- `renderRegistryBlock(reg: DataSource[]): string` (compact, byte-stable prompt block)

- [ ] **Step 1: Write the failing test**

`netlify/edge-functions/_lib/registry.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/registry.test.ts`
Expected: FAIL (module not found `./registry.ts`)

- [ ] **Step 3: Write `_lib/registry.ts`**

```ts
// Curated data-source registry for the Web mode (spec 2026-07-03-web-data-svar).
// The JSON file is served statically (like variable_metadata.json); this module
// loads, validates and caches it, and renders the compact prompt block.

export interface SourceAuth {
  type: "api_key";
  env: string;        // Netlify env var name holding the key
  plassering: string; // "query:<param>" | "header:<name>"
}

export interface DataSource {
  id: string;
  navn: string;
  utgiver: string;
  tillit: "offisiell" | "etablert" | "funnet";
  tilgang: "pxweb" | "sdmx" | "rest" | "ckan" | "fil";
  base_url: string;
  sok_endepunkt?: string;
  cors: boolean;
  join_nokler?: string[];
  oppskrift?: Record<string, string>;
  sporrings_url_mal?: string;
  auth?: SourceAuth;
  quirks?: string;
}

const TILLIT = new Set(["offisiell", "etablert", "funnet"]);
const TILGANG = new Set(["pxweb", "sdmx", "rest", "ckan", "fil"]);

export function parseRegistry(json: unknown): DataSource[] {
  if (!Array.isArray(json)) throw new Error("registeret må være en JSON-liste");
  return json.map((raw, i) => {
    const e = raw as Record<string, unknown>;
    for (const field of ["id", "navn", "utgiver", "tillit", "tilgang", "base_url"]) {
      if (typeof e[field] !== "string" || !(e[field] as string).trim()) {
        throw new Error(`kilde #${i}: mangler/ugyldig felt '${field}'`);
      }
    }
    if (!TILLIT.has(e.tillit as string)) throw new Error(`kilde ${e.id}: ukjent tillit '${e.tillit}'`);
    if (!TILGANG.has(e.tilgang as string)) throw new Error(`kilde ${e.id}: ukjent tilgang '${e.tilgang}'`);
    if (typeof e.cors !== "boolean") throw new Error(`kilde ${e.id}: 'cors' må være boolsk`);
    new URL(e.base_url as string); // throws on invalid
    return e as unknown as DataSource;
  });
}

let _cache: DataSource[] | null = null;
export function clearRegistryCache(): void { _cache = null; }

export async function loadRegistry(
  origin: string,
  fetchImpl: typeof fetch = fetch,
): Promise<DataSource[]> {
  if (_cache) return _cache;
  const res = await fetchImpl(new URL("/data/data-sources.json", origin).toString());
  if (!res.ok) throw new Error(`kunne ikke hente data-sources.json: ${res.status}`);
  _cache = parseRegistry(await res.json());
  return _cache;
}

export function findSource(reg: DataSource[], id: string): DataSource | null {
  return reg.find((s) => s.id === id) ?? null;
}

/** Exact host match against base_url — the guard for server-side key injection. */
export function sourceForUrl(reg: DataSource[], url: string): DataSource | null {
  let host: string;
  try { host = new URL(url).host; } catch { return null; }
  return reg.find((s) => {
    try { return new URL(s.base_url).host === host; } catch { return false; }
  }) ?? null;
}

/** Compact registry rendering for the cached system prefix. No auth details. */
export function renderRegistryBlock(reg: DataSource[]): string {
  const lines = reg.map((s) => {
    const bits = [`${s.tilgang}, base ${s.base_url}`];
    if (s.sok_endepunkt) bits.push("søkbar via search_catalog");
    if (s.auth) bits.push("krever nøkkel → hentes alltid via /api/hent");
    if (!s.cors) bits.push("ikke CORS → /api/hent");
    if (s.join_nokler?.length) bits.push(`join: ${s.join_nokler.join(", ")}`);
    const quirks = s.quirks ? ` — ${s.quirks}` : "";
    return `- **${s.id}** (${s.navn}; ${s.tillit}): ${bits.join("; ")}${quirks}`;
  });
  return `## Kilderegister (kuratert)\n\n${lines.join("\n")}`;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/registry.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the seed registry `data/data-sources.json`**

```json
[
  {
    "id": "ssb", "navn": "Statistisk sentralbyrå (PxWebApi 2)", "utgiver": "SSB",
    "tillit": "offisiell", "tilgang": "pxweb",
    "base_url": "https://data.ssb.no/api/pxwebapi/v2-beta/",
    "sok_endepunkt": "https://data.ssb.no/api/pxwebapi/v2-beta/tables?query={q}&lang=no",
    "cors": true,
    "join_nokler": ["kommunenummer", "fylkesnummer", "år"],
    "sporrings_url_mal": "https://data.ssb.no/api/pxwebapi/v2-beta/tables/{id}/data?valueCodes[{var}]={koder}&outputFormat=csv",
    "quirks": "GET med valueCodes per dimensjon; outputFormat=csv gir CSV direkte"
  },
  {
    "id": "eurostat", "navn": "Eurostat (dissemination API)", "utgiver": "Eurostat",
    "tillit": "offisiell", "tilgang": "rest",
    "base_url": "https://ec.europa.eu/eurostat/api/dissemination/",
    "cors": true,
    "join_nokler": ["geo (NUTS/ISO2)", "time"],
    "sporrings_url_mal": "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{dataset}/?format=SDMX-CSV&{dim}={kode}",
    "quirks": "SDMX-CSV via format=SDMX-CSV; dimensjonsfiltre i sti/spørring"
  },
  {
    "id": "worldbank", "navn": "World Bank Open Data", "utgiver": "Verdensbanken",
    "tillit": "offisiell", "tilgang": "rest",
    "base_url": "https://api.worldbank.org/v2/",
    "cors": true,
    "join_nokler": ["iso3c (land)", "date (år)"],
    "sporrings_url_mal": "https://api.worldbank.org/v2/country/{land}/indicator/{id}?format=json&per_page=20000",
    "quirks": "JSON er [meta, rader]; per_page må settes høyt; land som 'all' eller ISO-koder adskilt med ;"
  },
  {
    "id": "oecd", "navn": "OECD SDMX", "utgiver": "OECD",
    "tillit": "offisiell", "tilgang": "sdmx",
    "base_url": "https://sdmx.oecd.org/public/rest/",
    "cors": true,
    "join_nokler": ["LOCATION (ISO3)", "TIME_PERIOD"],
    "quirks": "SDMX-JSON/CSV; dataflow-id + nøkkel i sti; format=csvfile for CSV"
  },
  {
    "id": "who", "navn": "WHO Global Health Observatory (OData)", "utgiver": "WHO",
    "tillit": "offisiell", "tilgang": "rest",
    "base_url": "https://ghoapi.azureedge.net/api/",
    "cors": true,
    "join_nokler": ["SpatialDim (ISO3)", "TimeDim (år)"],
    "quirks": "OData: /api/{INDIKATORKODE}?$filter=...; JSON med value-liste"
  },
  {
    "id": "owid", "navn": "Our World in Data (grapher-CSV)", "utgiver": "OWID",
    "tillit": "etablert", "tilgang": "fil",
    "base_url": "https://ourworldindata.org/grapher/",
    "cors": true,
    "join_nokler": ["Entity/Code (land)", "Year"],
    "sporrings_url_mal": "https://ourworldindata.org/grapher/{slug}.csv",
    "quirks": "enhver grapher-side har .csv; kolonner Entity, Code, Year, verdi"
  },
  {
    "id": "fred", "navn": "FRED (St. Louis Fed)", "utgiver": "Federal Reserve",
    "tillit": "etablert", "tilgang": "rest",
    "base_url": "https://api.stlouisfed.org/fred/",
    "cors": false,
    "join_nokler": ["date"],
    "sporrings_url_mal": "https://api.stlouisfed.org/fred/series/observations?series_id={id}&file_type=json",
    "auth": { "type": "api_key", "env": "FRED_API_KEY", "plassering": "query:api_key" },
    "quirks": "krever api_key (injiseres av /api/hent); file_type=json"
  },
  {
    "id": "norgesbank", "navn": "Norges Bank (SDMX)", "utgiver": "Norges Bank",
    "tillit": "offisiell", "tilgang": "sdmx",
    "base_url": "https://data.norges-bank.no/api/",
    "cors": true,
    "join_nokler": ["TIME_PERIOD"],
    "quirks": "SDMX; format=csv støttes på data-endepunktet"
  },
  {
    "id": "datanorge", "navn": "data.norge.no (Felles datakatalog)", "utgiver": "Digdir",
    "tillit": "offisiell", "tilgang": "ckan",
    "base_url": "https://data.norge.no/",
    "sok_endepunkt": "https://search.api.fellesdatakatalog.digdir.no/search",
    "cors": true,
    "quirks": "katalog over datasett fra offentlige etater; selve datafilene ligger hos utgiver (probe før bruk)"
  },
  {
    "id": "githubraw", "navn": "GitHub raw-filer", "utgiver": "(varierer)",
    "tillit": "funnet", "tilgang": "fil",
    "base_url": "https://raw.githubusercontent.com/",
    "cors": true,
    "quirks": "discovery via web_search; ALLTID probe før bruk; tillit avhenger av repo-eier"
  },
  {
    "id": "wikipedia", "navn": "Wikipedia (tabeller i artikler)", "utgiver": "Wikimedia",
    "tillit": "etablert", "tilgang": "fil",
    "base_url": "https://en.wikipedia.org/wiki/",
    "cors": false,
    "oppskrift": { "python": "# load /api/hent?url=<url-enkodet artikkel-URL> as raw_html  →  import micropip; await micropip.install('lxml'); tabeller = pd.read_html(io.StringIO(raw_html)); df = tabeller[i]" },
    "quirks": "tabeller er load-bare via /api/hent + pd.read_html (lxml via micropip); velg riktig tabellindeks; no.wikipedia.org for norske artikler"
  }
]
```

- [ ] **Step 6: Verify live endpoints (adjust registry if reality differs)**

Run each and eyeball (2xx + plausible payload). These URLs are best-effort from documentation — **fix `base_url`/`sok_endepunkt`/`quirks` in the JSON to match reality; that is part of this task**:

```bash
curl -s "https://data.ssb.no/api/pxwebapi/v2-beta/tables?query=arbeidsledighet&lang=no" | head -c 400
curl -s "https://api.worldbank.org/v2/country/NOR/indicator/SL.UEM.TOTL.ZS?format=json&per_page=5" | head -c 400
curl -s "https://ourworldindata.org/grapher/co2.csv" | head -c 200
curl -s "https://ghoapi.azureedge.net/api/WHOSIS_000001?%24top=2" | head -c 300
curl -s "https://search.api.fellesdatakatalog.digdir.no/search" -X POST -H 'content-type: application/json' -d '{"query":"drivstoff"}' | head -c 300
```

If an endpoint is dead or shaped differently, correct the entry and note it in `quirks`. Re-run the registry tests afterwards.

- [ ] **Step 7: Validate the JSON file loads through parseRegistry**

Run: `cd netlify/edge-functions && deno eval "import { parseRegistry } from './_lib/registry.ts'; parseRegistry(JSON.parse(Deno.readTextFileSync('../../data/data-sources.json'))); console.log('OK');"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add data/data-sources.json netlify/edge-functions/_lib/registry.ts netlify/edge-functions/_lib/registry.test.ts
git commit -m "feat(web-svar): data-source registry — seed JSON + loader/validator/prompt block"
```

---

### Task 2: SSRF guard — `_lib/ssrf.ts`

**Files:**
- Create: `netlify/edge-functions/_lib/ssrf.ts`
- Test: `netlify/edge-functions/_lib/ssrf.test.ts`

**Interfaces (Produces):**
- `isPublicHttpUrl(raw: string): boolean`
- `interface GuardedResult { status: number; headers: Headers; body: Uint8Array; truncated: boolean; finalUrl: string }`
- `fetchGuarded(rawUrl: string, opts?: { method?: "GET"|"POST"; body?: string; headers?: Record<string,string>; timeoutMs?: number; maxBytes?: number; maxRedirects?: number; fetchImpl?: typeof fetch }): Promise<GuardedResult>` — manual redirect loop, per-hop `isPublicHttpUrl`, size-capped body read.

Known limitation (document in code comment, matches spec intent honestly): the edge runtime cannot pre-resolve DNS, so the guard is hostname-based (blocks IP-literals in private ranges, localhost, `.local`/`.internal`); it cannot catch a public hostname that resolves to a private IP. Mitigations: no credential forwarding, GET/POST-json only, size cap, timeout.

- [ ] **Step 1: Write the failing test**

`netlify/edge-functions/_lib/ssrf.test.ts`:

```ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { fetchGuarded, isPublicHttpUrl } from "./ssrf.ts";

Deno.test("isPublicHttpUrl blocks non-http, private and local hosts", () => {
  const bad = [
    "ftp://x.example/f", "file:///etc/passwd", "not a url",
    "http://localhost/x", "http://127.0.0.1/x", "http://10.0.0.5/x",
    "http://192.168.1.1/x", "http://172.16.9.9/x", "http://169.254.169.254/meta",
    "http://0.0.0.0/x", "http://[::1]/x", "http://foo.local/x", "http://db.internal/x",
  ];
  for (const u of bad) assertEquals(isPublicHttpUrl(u), false, u);
  const good = ["https://data.ssb.no/api/", "http://api.worldbank.org/v2/", "https://172.15.1.1/edge"];
  for (const u of good) assertEquals(isPublicHttpUrl(u), true, u);
});

function fakeFetch(routes: Record<string, () => Response>): typeof fetch {
  return ((input: string | URL | Request) => {
    const url = String(input);
    const hit = Object.keys(routes).find((k) => url.startsWith(k));
    if (!hit) return Promise.resolve(new Response("not found", { status: 404 }));
    return Promise.resolve(routes[hit]());
  }) as typeof fetch;
}

Deno.test("fetchGuarded follows public redirects, blocks private hop", async () => {
  const f = fakeFetch({
    "https://a.example/ok": () => new Response("DATA", { status: 200 }),
    "https://a.example/hop": () =>
      new Response(null, { status: 302, headers: { location: "https://a.example/ok" } }),
    "https://a.example/evil": () =>
      new Response(null, { status: 302, headers: { location: "http://169.254.169.254/meta" } }),
  });
  const ok = await fetchGuarded("https://a.example/hop", { fetchImpl: f });
  assertEquals(ok.status, 200);
  assertEquals(new TextDecoder().decode(ok.body), "DATA");
  assertEquals(ok.finalUrl, "https://a.example/ok");
  let threw = "";
  try { await fetchGuarded("https://a.example/evil", { fetchImpl: f }); } catch (e) { threw = String(e); }
  if (!threw.includes("blokkert")) throw new Error("privat redirect skulle blokkeres: " + threw);
});

Deno.test("fetchGuarded caps body size and flags truncation", async () => {
  const big = new Uint8Array(1024).fill(65);
  const f = fakeFetch({ "https://a.example/big": () => new Response(big, { status: 200 }) });
  const r = await fetchGuarded("https://a.example/big", { fetchImpl: f, maxBytes: 100 });
  assertEquals(r.truncated, true);
  assertEquals(r.body.length, 100);
});

Deno.test("fetchGuarded rejects non-public start URL", async () => {
  let threw = "";
  try { await fetchGuarded("http://localhost/x"); } catch (e) { threw = String(e); }
  if (!threw.includes("blokkert")) throw new Error("skulle blokkeres");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/ssrf.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `_lib/ssrf.ts`**

```ts
// SSRF guard for outbound fetches made on behalf of user-influenced URLs
// (/api/hent proxy and the probe tool). Hostname-based: the edge runtime
// cannot pre-resolve DNS, so a public hostname resolving to a private IP is
// not catchable here. Compensating controls: no credential forwarding,
// GET/POST-json only, byte cap, timeout, redirect hops re-checked.

const PRIVATE_V4 = [
  /^10\./, /^127\./, /^169\.254\./, /^192\.168\./, /^0\./,
  /^172\.(1[6-9]|2\d|3[01])\./,
];

export function isPublicHttpUrl(raw: string): boolean {
  let u: URL;
  try { u = new URL(raw); } catch { return false; }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  const host = u.hostname.toLowerCase();
  if (host === "localhost" || host.endsWith(".local") || host.endsWith(".internal")) return false;
  if (host.includes(":") || raw.includes("[")) return false; // IPv6 literals: reject
  if (/^\d+\.\d+\.\d+\.\d+$/.test(host) && PRIVATE_V4.some((re) => re.test(host))) return false;
  return true;
}

export interface GuardedResult {
  status: number;
  headers: Headers;
  body: Uint8Array;
  truncated: boolean;
  finalUrl: string;
}

export interface GuardedOptions {
  method?: "GET" | "POST";
  body?: string;
  headers?: Record<string, string>;
  timeoutMs?: number;
  maxBytes?: number;
  maxRedirects?: number;
  fetchImpl?: typeof fetch;
}

export async function fetchGuarded(rawUrl: string, opts: GuardedOptions = {}): Promise<GuardedResult> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const timeoutMs = opts.timeoutMs ?? 15_000;
  const maxBytes = opts.maxBytes ?? 50 * 1024 * 1024;
  const maxRedirects = opts.maxRedirects ?? 5;

  let url = rawUrl;
  for (let hop = 0; hop <= maxRedirects; hop++) {
    if (!isPublicHttpUrl(url)) throw new Error(`blokkert URL (ikke offentlig http/https): ${url}`);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const resp = await fetchImpl(url, {
        method: opts.method ?? "GET",
        body: opts.body,
        headers: opts.headers,
        redirect: "manual",
        signal: ctrl.signal,
      });
      if (resp.status >= 300 && resp.status < 400) {
        const loc = resp.headers.get("location");
        await resp.body?.cancel();
        if (!loc) throw new Error(`redirect uten Location fra ${url}`);
        url = new URL(loc, url).toString();
        continue;
      }
      // size-capped body read
      const chunks: Uint8Array[] = [];
      let total = 0;
      let truncated = false;
      if (resp.body) {
        const reader = resp.body.getReader();
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          if (total + value.length > maxBytes) {
            chunks.push(value.slice(0, maxBytes - total));
            total = maxBytes;
            truncated = true;
            await reader.cancel();
            break;
          }
          chunks.push(value);
          total += value.length;
        }
      }
      const body = new Uint8Array(total);
      let off = 0;
      for (const c of chunks) { body.set(c, off); off += c.length; }
      return { status: resp.status, headers: resp.headers, body, truncated, finalUrl: url };
    } finally {
      clearTimeout(timer);
    }
  }
  throw new Error(`for mange redirects fra ${rawUrl}`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/ssrf.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/ssrf.ts netlify/edge-functions/_lib/ssrf.test.ts
git commit -m "feat(web-svar): SSRF guard — public-URL check + guarded fetch (redirect hops, byte cap, timeout)"
```

---

### Task 3: Admin gate + GET support — `_lib/auth.ts`

**Files:**
- Modify: `netlify/edge-functions/_lib/auth.ts`
- Test: `netlify/edge-functions/_lib/auth.test.ts` (append tests; do not touch existing ones)

**Interfaces:**
- Consumes: existing `runGate`, `timingSafeEqual`, `clientIp`, `makeAnvilValidator` (unchanged behavior for existing endpoints).
- Produces:
  - `GateOptions` gains optional `allowedMethods?: string[]` (default `["POST"]`) — existing callers unaffected.
  - `interface UserInfo { ok: boolean; isAdmin: boolean }`
  - `makeAnvilUserFetcher(anvilUrl: string, timeoutMs?: number, fetchImpl?: typeof fetch): (token: string) => Promise<UserInfo>` — GET `/auth/me`, `ok` iff token valid, `isAdmin` iff `data.user.is_admin === true`.
  - `interface AdminGateDeps { sharedToken?: string; checkRateLimit: GateDeps["checkRateLimit"]; fetchUser: (token: string) => Promise<UserInfo>; now: () => number; cache: Map<string, { exp: number; isAdmin: boolean }> }`
  - `runAdminGate(request: Request, opts: GateOptions, deps: AdminGateDeps): Promise<Response | null>` — same steps 1–4 as `runGate` (token presence, method vs `allowedMethods`, body cap, rate limit), then: shared token ⇒ admin; else admin-cache; else `fetchUser` (cached). 401 when `!ok`, 403 `"Forbudt: krever admin"` when `!isAdmin`.
  - `adminGate(request: Request, opts: GateOptions): Promise<Response | null>` — env-wired like `gate`.

- [ ] **Step 1: Write the failing tests (append to auth.test.ts)**

```ts
import { makeAnvilUserFetcher, runAdminGate, type AdminGateDeps } from "./auth.ts";

function adminDeps(over: Partial<AdminGateDeps> = {}): AdminGateDeps & { calls: { fetchUser: number } } {
  const calls = { fetchUser: 0 };
  return {
    calls,
    sharedToken: undefined,
    checkRateLimit: () => Promise.resolve({ allowed: true, retryAfterSeconds: 0 }),
    fetchUser: () => { calls.fetchUser++; return Promise.resolve({ ok: true, isAdmin: true }); },
    now: () => 1_000_000,
    cache: new Map(),
    ...over,
  };
}

Deno.test("runAdminGate: admin user passes, non-admin gets 403, invalid 401", async () => {
  const opts = { endpoint: "data-svar", maxBodyBytes: 1000 };
  assertEquals(await runAdminGate(req({ token: "t1" }), opts, adminDeps()), null);
  const r403 = await runAdminGate(req({ token: "t2" }), opts,
    adminDeps({ fetchUser: () => Promise.resolve({ ok: true, isAdmin: false }) }));
  assertEquals(r403?.status, 403);
  const r401 = await runAdminGate(req({ token: "t3" }), opts,
    adminDeps({ fetchUser: () => Promise.resolve({ ok: false, isAdmin: false }) }));
  assertEquals(r401?.status, 401);
});

Deno.test("runAdminGate: shared token is admin; result cached", async () => {
  const deps = adminDeps({ sharedToken: "hemmelig" });
  const opts = { endpoint: "data-svar", maxBodyBytes: 1000 };
  assertEquals(await runAdminGate(req({ token: "hemmelig" }), opts, deps), null);
  assertEquals(deps.calls.fetchUser, 0);
  assertEquals(await runAdminGate(req({ token: "bruker" }), opts, deps), null);
  assertEquals(await runAdminGate(req({ token: "bruker" }), opts, deps), null);
  assertEquals(deps.calls.fetchUser, 1); // second hit came from cache
});

Deno.test("runAdminGate: allowedMethods lets GET through when configured", async () => {
  const opts = { endpoint: "hent", maxBodyBytes: 0, allowedMethods: ["GET"] };
  const getReq = req({ token: "t", method: "GET" });
  assertEquals(await runAdminGate(getReq, opts, adminDeps()), null);
  const postOpts = { endpoint: "hent", maxBodyBytes: 0 }; // default POST-only
  assertEquals((await runAdminGate(getReq, postOpts, adminDeps()))?.status, 405);
});

Deno.test("makeAnvilUserFetcher maps /auth/me shape", async () => {
  const mk = (payload: unknown, status = 200) =>
    makeAnvilUserFetcher("https://anvil.test/auth/me", 1000,
      (() => Promise.resolve(new Response(JSON.stringify(payload), { status }))) as typeof fetch);
  assertEquals(await mk({ user: { is_admin: true } })("t"), { ok: true, isAdmin: true });
  assertEquals(await mk({ user: { is_admin: false } })("t"), { ok: true, isAdmin: false });
  assertEquals(await mk({ user: {} })("t"), { ok: true, isAdmin: false });
  assertEquals(await mk({}, 401)("t"), { ok: false, isAdmin: false });
});
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/auth.test.ts`
Expected: FAIL (`runAdminGate` not exported); existing tests still PASS.

- [ ] **Step 3: Implement in `_lib/auth.ts`**

(a) In `GateOptions` add `allowedMethods?: string[];`. In `runGate` replace the method check with:

```ts
  const allowed = opts.allowedMethods ?? ["POST"];
  if (!allowed.includes(request.method)) {
    return new Response("Method not allowed", { status: 405 });
  }
```

(b) Append:

```ts
export interface UserInfo { ok: boolean; isAdmin: boolean; }

/** Like makeAnvilValidator, but returns the user's admin flag too. */
export function makeAnvilUserFetcher(
  anvilUrl: string,
  timeoutMs: number = ANVIL_TIMEOUT_MS,
  fetchImpl: typeof fetch = fetch,
): (token: string) => Promise<UserInfo> {
  return async (token: string): Promise<UserInfo> => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const resp = await fetchImpl(anvilUrl, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        signal: ctrl.signal,
      });
      if (!resp.ok) return { ok: false, isAdmin: false };
      const data = await resp.json();
      const ok = !!(data && (data.user || data.principal_kind === "service_token"));
      const isAdmin = !!(data && data.user && data.user.is_admin === true);
      return { ok, isAdmin };
    } catch (_e) {
      return { ok: false, isAdmin: false };
    } finally {
      clearTimeout(timer);
    }
  };
}

export interface AdminGateDeps {
  sharedToken?: string;
  checkRateLimit: GateDeps["checkRateLimit"];
  fetchUser: (token: string) => Promise<UserInfo>;
  now: () => number;
  cache: Map<string, { exp: number; isAdmin: boolean }>;
}

const _adminCache = new Map<string, { exp: number; isAdmin: boolean }>();

/** Gate + admin requirement (data-svar, hent). Shared token counts as admin. */
export async function runAdminGate(
  request: Request,
  opts: GateOptions,
  deps: AdminGateDeps,
): Promise<Response | null> {
  const authHeader = request.headers.get("authorization") ?? "";
  const presentedToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";
  if (!presentedToken) return new Response("Unauthorized: missing token", { status: 401 });

  const allowed = opts.allowedMethods ?? ["POST"];
  if (!allowed.includes(request.method)) {
    return new Response("Method not allowed", { status: 405 });
  }

  const contentLength = parseInt(request.headers.get("content-length") ?? "0", 10);
  if (contentLength > opts.maxBodyBytes) {
    return new Response("Payload too large", { status: 413 });
  }

  const rate = await deps.checkRateLimit(opts.endpoint, clientIp(request));
  if (!rate.allowed) {
    return new Response("Rate limited", {
      status: 429,
      headers: { "Retry-After": String(rate.retryAfterSeconds) },
    });
  }

  const now = deps.now();
  let info: UserInfo | null = null;
  if (deps.sharedToken && timingSafeEqual(presentedToken, deps.sharedToken)) {
    info = { ok: true, isAdmin: true };
  }
  if (!info) {
    const hit = deps.cache.get(presentedToken);
    if (hit && hit.exp > now) info = { ok: true, isAdmin: hit.isAdmin };
    else if (hit) deps.cache.delete(presentedToken);
  }
  if (!info) {
    const fetched = await deps.fetchUser(presentedToken);
    if (fetched.ok) {
      deps.cache.set(presentedToken, { exp: now + AUTH_CACHE_TTL_MS, isAdmin: fetched.isAdmin });
      info = fetched;
    }
  }
  if (!info?.ok) return new Response("Unauthorized", { status: 401 });
  if (!info.isAdmin) return new Response("Forbudt: krever admin", { status: 403 });
  return null;
}

/** Env-wired admin gate used by data-svar and hent. */
export function adminGate(request: Request, opts: GateOptions): Promise<Response | null> {
  const anvilUrl = Deno.env.get("M2PY_ANVIL_VALIDATE_URL") ?? ANVIL_DEFAULT_URL;
  return runAdminGate(request, opts, {
    sharedToken: Deno.env.get("M2PY_ACCESS_TOKEN") ?? undefined,
    checkRateLimit: defaultCheckRateLimit,
    fetchUser: makeAnvilUserFetcher(anvilUrl),
    now: () => Date.now(),
    cache: _adminCache,
  });
}
```

- [ ] **Step 4: Run the full auth suite**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/auth.test.ts`
Expected: PASS (all old + 4 new tests)

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/auth.ts netlify/edge-functions/_lib/auth.test.ts
git commit -m "feat(web-svar): admin gate (is_admin via /auth/me, cached) + allowedMethods on gate"
```

---
### Task 4: Proxy — `netlify/edge-functions/hent.ts` (`/api/hent`)

**Files:**
- Create: `netlify/edge-functions/hent.ts`
- Create: `netlify/edge-functions/_lib/hent-core.ts` (testable core; the handler is a thin env-wired wrapper)
- Test: `netlify/edge-functions/_lib/hent-core.test.ts`
- Modify: `netlify.toml` (add mapping)

**Interfaces:**
- Consumes: `adminGate` (Task 3), `fetchGuarded`/`isPublicHttpUrl` (Task 2), `loadRegistry`/`sourceForUrl` (Task 1).
- Produces: `handleHent(request: Request, deps: { registry: DataSource[]; getEnv: (k: string) => string | undefined; fetchImpl?: typeof fetch }): Promise<Response>` — the core, minus auth (handler runs `adminGate` first).
- Query contract: `GET /api/hent?url=<encoded>` (+ optional `body=<encoded JSON string>` ⇒ forwarded as POST `application/json`). Response: upstream body/status, upstream `content-type`, `x-hent-truncated: 1` when capped. Key injection only when `sourceForUrl` matches and the entry has `auth`.

- [ ] **Step 1: Write the failing test**

`netlify/edge-functions/_lib/hent-core.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/hent-core.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `_lib/hent-core.ts`**

```ts
// Core of the /api/hent proxy (auth handled by the wrapper). SSRF-hardened
// generic GET (+ GET-wrapped POST-json) with server-side key injection for
// registry sources. Keys never reach the browser (spec §5).
import { fetchGuarded, isPublicHttpUrl } from "./ssrf.ts";
import { sourceForUrl, type DataSource } from "./registry.ts";

const MAX_BODY_PARAM = 20_000;      // chars, URL-decoded
const MAX_RESPONSE = 50 * 1024 * 1024;
const TIMEOUT_MS = 25_000;

export interface HentDeps {
  registry: DataSource[];
  getEnv: (k: string) => string | undefined;
  fetchImpl?: typeof fetch;
}

export async function handleHent(request: Request, deps: HentDeps): Promise<Response> {
  const u = new URL(request.url);
  const target = u.searchParams.get("url") ?? "";
  const bodyParam = u.searchParams.get("body");
  if (!target || !isPublicHttpUrl(target)) {
    return new Response("Ugyldig eller manglende url-parameter", { status: 400 });
  }
  if (bodyParam && bodyParam.length > MAX_BODY_PARAM) {
    return new Response("body-parameter for stor", { status: 413 });
  }

  // Key injection — ONLY when the host matches a registry entry with auth.
  let finalUrl = target;
  const headers: Record<string, string> = {};
  const src = sourceForUrl(deps.registry, target);
  if (src?.auth) {
    const key = deps.getEnv(src.auth.env);
    if (!key) return new Response(`Nøkkel for ${src.id} er ikke konfigurert`, { status: 502 });
    const [kind, name] = src.auth.plassering.split(":");
    if (kind === "query") {
      const t = new URL(target);
      t.searchParams.set(name, key);
      finalUrl = t.toString();
    } else if (kind === "header") {
      headers[name] = key;
    }
  }
  if (bodyParam) headers["content-type"] = "application/json";

  try {
    const res = await fetchGuarded(finalUrl, {
      method: bodyParam ? "POST" : "GET",
      body: bodyParam ?? undefined,
      headers,
      timeoutMs: TIMEOUT_MS,
      maxBytes: MAX_RESPONSE,
      fetchImpl: deps.fetchImpl,
    });
    const out = new Headers({
      "content-type": res.headers.get("content-type") ?? "application/octet-stream",
      "cache-control": "no-store",
    });
    if (res.truncated) out.set("x-hent-truncated", "1");
    return new Response(res.body, { status: res.status, headers: out });
  } catch (e) {
    return new Response(`Proxy-feil: ${String(e).slice(0, 300)}`, { status: 502 });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/hent-core.test.ts`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the handler `netlify/edge-functions/hent.ts`**

```ts
// /api/hent — SSRF-hardened fetch proxy for Web mode (admin-only while the
// feature is admin-only; see spec §5). GET /api/hent?url=…[&body=…]
import { adminGate } from "./_lib/auth.ts";
import { loadRegistry } from "./_lib/registry.ts";
import { handleHent } from "./_lib/hent-core.ts";

export default async (request: Request): Promise<Response> => {
  const gateResp = await adminGate(request, {
    endpoint: "hent",
    maxBodyBytes: 0,
    allowedMethods: ["GET"],
  });
  if (gateResp) return gateResp;

  let registry;
  try {
    registry = await loadRegistry(new URL(request.url).origin);
  } catch (e) {
    console.error("hent: registry load failed:", e);
    return new Response("Kilderegister utilgjengelig", { status: 502 });
  }
  return handleHent(request, { registry, getEnv: (k) => Deno.env.get(k) });
};
```

- [ ] **Step 6: Map the route in `netlify.toml`**

After the existing `[[edge_functions]]` blocks add:

```toml
[[edge_functions]]
  function = "hent"
  path = "/api/hent"
```

- [ ] **Step 7: Smoke test locally**

Run: `netlify dev` (separate terminal), then:

```bash
curl -s -H "Authorization: Bearer $M2PY_ACCESS_TOKEN" \
  "http://localhost:8888/api/hent?url=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("https://ourworldindata.org/grapher/co2.csv"))')" | head -c 200
curl -s -o /dev/null -w '%{http_code}\n' "http://localhost:8888/api/hent?url=x"   # 401 (no token)
```

Expected: CSV header line; then `401`.

- [ ] **Step 8: Commit**

```bash
git add netlify/edge-functions/hent.ts netlify/edge-functions/_lib/hent-core.ts netlify/edge-functions/_lib/hent-core.test.ts netlify.toml
git commit -m "feat(web-svar): /api/hent proxy — SSRF-hardened GET + POST-wrap, server-side key injection, admin-gated"
```

---

### Task 5: Tool — `_lib/tools/search-catalog.ts` (PxWeb + CKAN adapters)

**Files:**
- Create: `netlify/edge-functions/_lib/tools/search-catalog.ts`
- Test: `netlify/edge-functions/_lib/tools/search-catalog.test.ts`

**Interfaces:**
- Consumes: `findSource`, `DataSource` (Task 1).
- Produces:
  - `interface CatalogHit { source: string; id: string; title: string; period?: string; url: string }`
  - `searchCatalog(sourceId: string, query: string, deps: { registry: DataSource[]; fetchImpl?: typeof fetch }): Promise<CatalogHit[]>` — throws with a clear Norwegian message when the source is unknown/unsearchable. Sources without adapters are reachable via web_search+probe instead; that rule lives in the prompt (Task 9).

- [ ] **Step 1: Write the failing test**

```ts
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

function fakeFetch(payload: unknown, capture: string[]): typeof fetch {
  return ((input: string | URL | Request, init?: RequestInit) => {
    capture.push(`${init?.method ?? "GET"} ${String(input)}`);
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
  const hits = await searchCatalog("datanorge", "drivstoff", { registry: REG, fetchImpl: fakeFetch(FDK_FIXTURE, calls) });
  assertEquals(calls[0].startsWith("POST https://search.api.fellesdatakatalog"), true);
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/tools/search-catalog.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `_lib/tools/search-catalog.ts`**

```ts
// search_catalog tool: per-source-type adapters over live catalog APIs.
// Adapters exist for pxweb (SSB & friends) and ckan (Felles datakatalog).
// Other tilgang values are reached via web_search + probe (prompt rule).
import { findSource, type DataSource } from "../registry.ts";

export interface CatalogHit {
  source: string;
  id: string;
  title: string;
  period?: string;
  url: string;
}

export interface CatalogDeps {
  registry: DataSource[];
  fetchImpl?: typeof fetch;
}

const MAX_HITS = 20;

export async function searchCatalog(
  sourceId: string,
  query: string,
  deps: CatalogDeps,
): Promise<CatalogHit[]> {
  const src = findSource(deps.registry, sourceId);
  if (!src) throw new Error(`ukjent kilde '${sourceId}' — bruk en id fra kilderegisteret`);
  if (!src.sok_endepunkt) throw new Error(`kilden '${sourceId}' er ikke søkbar — bruk web_search + probe i stedet`);
  const f = deps.fetchImpl ?? fetch;
  switch (src.tilgang) {
    case "pxweb": return pxwebSearch(src, query, f);
    case "ckan": return fdkSearch(src, query, f);
    default:
      throw new Error(`ingen søkeadapter for tilgang='${src.tilgang}' (kilde '${sourceId}') — bruk web_search + probe`);
  }
}

async function pxwebSearch(src: DataSource, query: string, f: typeof fetch): Promise<CatalogHit[]> {
  const url = src.sok_endepunkt!.replace("{q}", encodeURIComponent(query));
  const res = await f(url);
  if (!res.ok) throw new Error(`katalogsøk mot ${src.id} feilet: HTTP ${res.status}`);
  const json = await res.json();
  const tables = Array.isArray(json?.tables) ? json.tables : [];
  return tables.slice(0, MAX_HITS).map((t: Record<string, unknown>) => ({
    source: src.id,
    id: String(t.id ?? ""),
    title: String(t.label ?? ""),
    period: t.firstPeriod ? `${t.firstPeriod}–${t.lastPeriod ?? ""}` : undefined,
    url: new URL(`tables/${t.id}`, src.base_url).toString(),
  }));
}

async function fdkSearch(src: DataSource, query: string, f: typeof fetch): Promise<CatalogHit[]> {
  const res = await f(src.sok_endepunkt!, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, filters: {} }),
  });
  if (!res.ok) throw new Error(`katalogsøk mot ${src.id} feilet: HTTP ${res.status}`);
  const json = await res.json();
  const hits = Array.isArray(json?.hits) ? json.hits : [];
  return hits.slice(0, MAX_HITS).map((h: Record<string, unknown>) => {
    const title = h.title as Record<string, string> | string | undefined;
    return {
      source: src.id,
      id: String(h.id ?? ""),
      title: typeof title === "object" ? (title?.nb ?? Object.values(title ?? {})[0] ?? "") : String(title ?? ""),
      url: String(h.uri ?? ""),
    };
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/tools/search-catalog.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Live sanity check (fix adapter/fixtures if reality differs)**

```bash
cd netlify/edge-functions && deno eval "
import { searchCatalog } from './_lib/tools/search-catalog.ts';
import { parseRegistry } from './_lib/registry.ts';
const reg = parseRegistry(JSON.parse(Deno.readTextFileSync('../../data/data-sources.json')));
console.log((await searchCatalog('ssb', 'arbeidsledighet', { registry: reg })).slice(0, 3));
"
```

Expected: 1–3 real SSB table hits. If the live response shape differs from the fixture, update BOTH the adapter and the fixture, and note the quirk in `data-sources.json`.

- [ ] **Step 6: Commit**

```bash
git add netlify/edge-functions/_lib/tools/search-catalog.ts netlify/edge-functions/_lib/tools/search-catalog.test.ts
git commit -m "feat(web-svar): search_catalog tool — pxweb + felles-datakatalog adapters"
```

---

### Task 6: Tool — `_lib/tools/table-metadata.ts` (variable-level lookup)

**Files:**
- Create: `netlify/edge-functions/_lib/tools/table-metadata.ts`
- Test: `netlify/edge-functions/_lib/tools/table-metadata.test.ts`

**Interfaces:**
- Consumes: `findSource`, `DataSource` (Task 1).
- Produces:
  - `interface TableVariable { code: string; label: string; time: boolean; values: { code: string; label: string }[]; valuesTruncated: boolean }`
  - `interface TableMeta { source: string; id: string; title: string; variables: TableVariable[]; queryUrlTemplate?: string }`
  - `tableMetadata(sourceId: string, tableId: string, deps: { registry: DataSource[]; fetchImpl?: typeof fetch }): Promise<TableMeta>` — pxweb only in this slice; other sources throw a clear "bruk probe på data-URL-en" error. Values capped at 40 per variable (`valuesTruncated`), so codelists don't blow up the context.

- [ ] **Step 1: Write the failing test**

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/tools/table-metadata.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `_lib/tools/table-metadata.ts`**

```ts
// table_metadata tool: variable-level lookup for a catalog hit, so the model
// can build a MINIMAL query URL (spec: build datasets from variables).
import { findSource, type DataSource } from "../registry.ts";

export interface TableVariable {
  code: string;
  label: string;
  time: boolean;
  values: { code: string; label: string }[];
  valuesTruncated: boolean;
}

export interface TableMeta {
  source: string;
  id: string;
  title: string;
  variables: TableVariable[];
  queryUrlTemplate?: string;
}

const MAX_VALUES = 40;

export async function tableMetadata(
  sourceId: string,
  tableId: string,
  deps: { registry: DataSource[]; fetchImpl?: typeof fetch },
): Promise<TableMeta> {
  const src = findSource(deps.registry, sourceId);
  if (!src) throw new Error(`ukjent kilde '${sourceId}'`);
  if (src.tilgang !== "pxweb") {
    throw new Error(
      `table_metadata støtter bare pxweb-kilder ennå — for '${sourceId}': bruk probe på data-URL-en for å se kolonner`,
    );
  }
  const f = deps.fetchImpl ?? fetch;
  const url = new URL(`tables/${tableId}/metadata?lang=no`, src.base_url).toString();
  const res = await f(url);
  if (!res.ok) throw new Error(`metadata for ${sourceId}/${tableId} feilet: HTTP ${res.status}`);
  const json = await res.json();

  const dims = (json?.dimension ?? {}) as Record<string, {
    label?: string;
    category?: { index?: Record<string, number>; label?: Record<string, string> };
  }>;
  const timeDims = new Set<string>((json?.role?.time ?? []) as string[]);
  const variables: TableVariable[] = Object.entries(dims).map(([code, d]) => {
    const labels = d.category?.label ?? {};
    const codes = Object.keys(d.category?.index ?? labels);
    const values = codes.slice(0, MAX_VALUES).map((c) => ({ code: c, label: labels[c] ?? c }));
    return {
      code,
      label: d.label ?? code,
      time: timeDims.has(code),
      values,
      valuesTruncated: codes.length > MAX_VALUES,
    };
  });

  return {
    source: sourceId,
    id: tableId,
    title: String(json?.label ?? tableId),
    variables,
    queryUrlTemplate: src.sporrings_url_mal?.replace("{id}", tableId),
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/tools/table-metadata.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Live sanity check against SSB**

```bash
cd netlify/edge-functions && deno eval "
import { tableMetadata } from './_lib/tools/table-metadata.ts';
import { parseRegistry } from './_lib/registry.ts';
const reg = parseRegistry(JSON.parse(Deno.readTextFileSync('../../data/data-sources.json')));
const m = await tableMetadata('ssb', '05839', { registry: reg });
console.log(m.title, m.variables.map(v => v.code));
"
```

Expected: a real title + dimension codes. If the live metadata shape differs (v2-beta evolves), adjust adapter + fixture together and record the quirk in the registry.

- [ ] **Step 6: Commit**

```bash
git add netlify/edge-functions/_lib/tools/table-metadata.ts netlify/edge-functions/_lib/tools/table-metadata.test.ts
git commit -m "feat(web-svar): table_metadata tool — pxweb variable-level metadata with value cap"
```

---
### Task 7: Tool — `_lib/tools/probe.ts` (schema + CORS oracle)

**Files:**
- Create: `netlify/edge-functions/_lib/tools/probe.ts`
- Test: `netlify/edge-functions/_lib/tools/probe.test.ts`

**Interfaces:**
- Consumes: `fetchGuarded`, `isPublicHttpUrl` (Task 2).
- Produces:
  - `interface ProbeResult { ok: boolean; status: number; contentType: string; cors: boolean; columns: string[]; sampleRows: string[][]; truncated: boolean; note?: string }`
  - `probeUrl(url: string, deps?: { fetchImpl?: typeof fetch }): Promise<ProbeResult>` — small guarded GET (256 kB / 10 s); infers columns from CSV header (sniffs `,` vs `;`), JSON-stat (`dimension` keys), or JSON array-of-objects (keys of first element); `cors` = `access-control-allow-origin` is `*`.

- [ ] **Step 1: Write the failing test**

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/tools/probe.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `_lib/tools/probe.ts`**

```ts
// probe tool: the grounding step. Verifies an endpoint exists and reports
// OBSERVED schema (columns) + CORS, so generation never guesses.
import { fetchGuarded, isPublicHttpUrl } from "../ssrf.ts";

export interface ProbeResult {
  ok: boolean;
  status: number;
  contentType: string;
  cors: boolean;
  columns: string[];
  sampleRows: string[][];
  truncated: boolean;
  note?: string;
}

const MAX_PROBE_BYTES = 256 * 1024;
const PROBE_TIMEOUT_MS = 10_000;

export async function probeUrl(
  url: string,
  deps: { fetchImpl?: typeof fetch } = {},
): Promise<ProbeResult> {
  const empty: ProbeResult = {
    ok: false, status: 0, contentType: "", cors: false,
    columns: [], sampleRows: [], truncated: false,
  };
  if (!isPublicHttpUrl(url)) {
    return { ...empty, note: "blokkert: ikke en offentlig http(s)-URL" };
  }
  let res;
  try {
    res = await fetchGuarded(url, {
      maxBytes: MAX_PROBE_BYTES,
      timeoutMs: PROBE_TIMEOUT_MS,
      fetchImpl: deps.fetchImpl,
    });
  } catch (e) {
    return { ...empty, note: `probe feilet: ${String(e).slice(0, 200)}` };
  }
  const contentType = res.headers.get("content-type") ?? "";
  const cors = res.headers.get("access-control-allow-origin") === "*";
  if (res.status < 200 || res.status >= 300) {
    return { ...empty, status: res.status, contentType, cors, note: `HTTP ${res.status}` };
  }
  const text = new TextDecoder().decode(res.body);
  const { columns, sampleRows, note } = inferSchema(text, contentType);
  return {
    ok: true, status: res.status, contentType, cors,
    columns, sampleRows, truncated: res.truncated, note,
  };
}

function inferSchema(text: string, contentType: string): {
  columns: string[]; sampleRows: string[][]; note?: string;
} {
  const t = text.trimStart();
  const looksJson = contentType.includes("json") || t.startsWith("{") || t.startsWith("[");
  if (looksJson) {
    try {
      const json = JSON.parse(sliceCompleteJson(t));
      if (json && typeof json === "object" && !Array.isArray(json) && json.dimension) {
        return { columns: Object.keys(json.dimension), sampleRows: [], note: "JSON-stat" };
      }
      if (Array.isArray(json) && json.length && typeof json[0] === "object") {
        return {
          columns: Object.keys(json[0]),
          sampleRows: json.slice(0, 2).map((r: Record<string, unknown>) => Object.values(r).map(String)),
          note: "JSON-array",
        };
      }
      if (json && typeof json === "object") {
        return { columns: Object.keys(json), sampleRows: [], note: "JSON-objekt (toppnivå-nøkler)" };
      }
    } catch {
      return { columns: [], sampleRows: [], note: "JSON kunne ikke parses (trunkert?)" };
    }
  }
  // CSV: sniff separator on the header line
  const lines = text.split(/\r?\n/).filter((l) => l.length > 0).slice(0, 3);
  if (!lines.length) return { columns: [], sampleRows: [], note: "tomt svar" };
  const sep = (lines[0].match(/;/g)?.length ?? 0) > (lines[0].match(/,/g)?.length ?? 0) ? ";" : ",";
  const split = (l: string) => l.split(sep).map((c) => c.replace(/^"|"$/g, "").trim());
  return { columns: split(lines[0]), sampleRows: lines.slice(1).map(split), note: `CSV (skilletegn '${sep}')` };
}

/** Best-effort: probe reads a byte-capped prefix, so JSON may be cut off. */
function sliceCompleteJson(t: string): string {
  try { JSON.parse(t); return t; } catch { /* fall through */ }
  // For arrays: retry on the largest complete prefix ending at a '}' + ']'
  const lastObj = t.lastIndexOf("}");
  if (t.startsWith("[") && lastObj > 0) return t.slice(0, lastObj + 1) + "]";
  return t;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/tools/probe.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/tools/probe.ts netlify/edge-functions/_lib/tools/probe.test.ts
git commit -m "feat(web-svar): probe tool — guarded GET with schema inference (CSV/JSON-stat/JSON) and CORS flag"
```

---

### Task 8: Tool loop — `runAgenticStream` in `_lib/anthropic.ts`

**Files:**
- Modify: `netlify/edge-functions/_lib/anthropic.ts` (append; existing exports untouched)
- Test: `netlify/edge-functions/_lib/anthropic.test.ts` (append)

**Interfaces:**
- Consumes: `fetchWithRetry`, `RetryDeps` (existing).
- Produces:
  - `interface AgenticOptions { apiKey: string; model: string; system: string; userContent: string; tools: unknown[]; executeTool: (name: string, input: Record<string, unknown>) => Promise<string>; progressLabel?: (name: string, input: Record<string, unknown>) => string; maxTokens?: number; cacheTtl?: "5m" | "1h"; maxClientToolCalls?: number; maxTurns?: number; deps?: RetryDeps }`
  - `runAgenticStream(opts: AgenticOptions): ReadableStream<Uint8Array>` — SSE stream of `data: {...}` events: `{type:"progress",text}` per client tool call, `{type:"text",text}` for the final answer blocks, `{type:"done",inputTokens,outputTokens,cacheReadTokens,cacheCreationTokens}` (summed across turns), `{type:"error",message}`.

Design decisions (documented in code): loop turns are **non-streaming** (`stream:false`) — simplest correct tool loop; the final answer is emitted as one text event (accepted trade-off vs token streaming; the UI renders per-event). `stop_reason === "pause_turn"` (hosted web_search) ⇒ re-send with the assistant content appended. Client tool budget default 12; over budget the tool result tells the model to generate now. Per-call timeout 90 s via `deps.timeoutMs` default override (generation turns are long).

- [ ] **Step 1: Write the failing test (append to anthropic.test.ts)**

```ts
import { runAgenticStream } from "./anthropic.ts";

async function collectSse(stream: ReadableStream<Uint8Array>): Promise<Record<string, unknown>[]> {
  const text = await new Response(stream).text();
  return text.split("\n\n").filter((l) => l.startsWith("data: "))
    .map((l) => JSON.parse(l.slice(6)));
}

function apiTurns(turns: Record<string, unknown>[]): typeof fetch {
  let i = 0;
  return ((_u: string | URL | Request, _init?: RequestInit) =>
    Promise.resolve(new Response(JSON.stringify(turns[i++]), { status: 200 }))) as typeof fetch;
}

Deno.test("runAgenticStream: tool round-trip then final text", async () => {
  const fetchImpl = apiTurns([
    { stop_reason: "tool_use", usage: { input_tokens: 10, output_tokens: 5 },
      content: [{ type: "tool_use", id: "tu1", name: "probe", input: { url: "https://x/d.csv" } }] },
    { stop_reason: "end_turn", usage: { input_tokens: 20, output_tokens: 15 },
      content: [{ type: "text", text: "Her er scriptet." }] },
  ]);
  const calls: string[] = [];
  const events = await collectSse(runAgenticStream({
    apiKey: "k", model: "m", system: "s", userContent: "q",
    tools: [{ name: "probe", description: "d", input_schema: { type: "object" } }],
    executeTool: (name, input) => { calls.push(`${name}:${input.url}`); return Promise.resolve('{"ok":true}'); },
    deps: { fetchImpl },
  }));
  assertEquals(calls, ["probe:https://x/d.csv"]);
  assertEquals(events.map((e) => e.type), ["progress", "text", "done"]);
  assertEquals(events[1].text, "Her er scriptet.");
  assertEquals(events[2].inputTokens, 30);
  assertEquals(events[2].outputTokens, 20);
});

Deno.test("runAgenticStream: budget exhausts into forced generation", async () => {
  const toolTurn = {
    stop_reason: "tool_use", usage: { input_tokens: 1, output_tokens: 1 },
    content: [{ type: "tool_use", id: "t", name: "probe", input: {} }],
  };
  const finalTurn = {
    stop_reason: "end_turn", usage: { input_tokens: 1, output_tokens: 1 },
    content: [{ type: "text", text: "ferdig" }],
  };
  let toolResults: string[] = [];
  const events = await collectSse(runAgenticStream({
    apiKey: "k", model: "m", system: "s", userContent: "q",
    tools: [], maxClientToolCalls: 2,
    executeTool: () => { return Promise.resolve("data"); },
    deps: { fetchImpl: (( _u: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      const lastUser = body.messages.filter((m: { role: string }) => m.role === "user").pop();
      if (Array.isArray(lastUser?.content)) {
        for (const c of lastUser.content) if (c.type === "tool_result") toolResults.push(String(c.content));
      }
      const turn = body.messages.length >= 7 ? finalTurn : toolTurn; // 3 tool rounds then final
      return Promise.resolve(new Response(JSON.stringify(turn), { status: 200 }));
    }) as typeof fetch },
  }));
  // third call is over budget (max 2) -> its result is the budget message
  if (!toolResults[2]?.includes("budsjett")) throw new Error("ventet budsjett-melding: " + toolResults[2]);
  assertEquals(events.at(-1)?.type, "done");
});

Deno.test("runAgenticStream: API error surfaces as error event", async () => {
  const events = await collectSse(runAgenticStream({
    apiKey: "k", model: "m", system: "s", userContent: "q", tools: [],
    executeTool: () => Promise.resolve(""),
    deps: { fetchImpl: ((_u: string | URL | Request) =>
      Promise.resolve(new Response("boom", { status: 500 }))) as typeof fetch, retries: 0 },
  }));
  assertEquals(events.at(-1)?.type, "error");
});
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/anthropic.test.ts`
Expected: FAIL (`runAgenticStream` not exported); existing tests PASS.

- [ ] **Step 3: Append to `_lib/anthropic.ts`**

```ts
// ── Agentic tool loop (Web mode / data-svar) ─────────────────────────────
// Non-streaming turns while the model calls tools; the final answer is
// emitted as one SSE text event (accepted trade-off: no token streaming on
// the final turn — the loop stays simple and correct). Hosted tools
// (web_search) run inside the API; stop_reason "pause_turn" is resumed.

export interface AgenticOptions {
  apiKey: string;
  model: string;
  system: string;
  userContent: string;
  tools: unknown[];
  executeTool: (name: string, input: Record<string, unknown>) => Promise<string>;
  progressLabel?: (name: string, input: Record<string, unknown>) => string;
  maxTokens?: number;
  cacheTtl?: "5m" | "1h";
  maxClientToolCalls?: number;
  maxTurns?: number;
  deps?: RetryDeps;
}

const AGENTIC_TIMEOUT_MS = 90_000;

export function runAgenticStream(opts: AgenticOptions): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const maxClientCalls = opts.maxClientToolCalls ?? 12;
  const maxTurns = opts.maxTurns ?? 24;
  const deps: RetryDeps = { timeoutMs: AGENTIC_TIMEOUT_MS, ...opts.deps };
  const useLongTtl = opts.cacheTtl === "1h";

  return new ReadableStream({
    async start(controller) {
      const emit = (obj: Record<string, unknown>) =>
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "x-api-key": opts.apiKey,
        "anthropic-version": ANTHROPIC_VERSION,
      };
      if (useLongTtl) headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11";
      const system = [{
        type: "text",
        text: opts.system,
        cache_control: useLongTtl ? { type: "ephemeral", ttl: "1h" } : { type: "ephemeral" },
      }];

      const messages: Record<string, unknown>[] = [{ role: "user", content: opts.userContent }];
      let clientCalls = 0;
      let inputTokens = 0, outputTokens = 0, cacheRead = 0, cacheCreation = 0;

      try {
        for (let turn = 0; turn < maxTurns; turn++) {
          const resp = await fetchWithRetry(ANTHROPIC_API, {
            method: "POST",
            headers,
            body: JSON.stringify({
              model: opts.model,
              max_tokens: opts.maxTokens ?? 8192,
              stream: false,
              system,
              tools: opts.tools,
              messages,
            }),
          }, deps);
          if (!resp.ok) {
            const detail = await resp.text().catch(() => "");
            console.error(`Anthropic API error ${resp.status}: ${detail}`);
            throw new Error(`Anthropic API error ${resp.status}`);
          }
          const json = await resp.json();
          const u = json?.usage ?? {};
          inputTokens += u.input_tokens ?? 0;
          outputTokens += u.output_tokens ?? 0;
          cacheRead += u.cache_read_input_tokens ?? 0;
          cacheCreation += u.cache_creation_input_tokens ?? 0;
          const content = Array.isArray(json?.content) ? json.content : [];

          if (json.stop_reason === "pause_turn") {
            messages.push({ role: "assistant", content });
            continue;
          }
          const toolUses = content.filter((b: { type?: string }) => b.type === "tool_use");
          if (json.stop_reason === "tool_use" && toolUses.length) {
            messages.push({ role: "assistant", content });
            const results: Record<string, unknown>[] = [];
            for (const tu of toolUses) {
              clientCalls++;
              const label = opts.progressLabel?.(tu.name, tu.input ?? {}) ?? `Kjører ${tu.name} …`;
              emit({ type: "progress", text: label });
              let out: string;
              if (clientCalls > maxClientCalls) {
                out = "Verktøy-budsjettet er brukt opp — generer svaret NÅ med det du allerede har funnet. Vær ærlig om hva som mangler.";
              } else {
                try {
                  out = await opts.executeTool(tu.name, tu.input ?? {});
                } catch (e) {
                  out = `Verktøyfeil: ${String(e).slice(0, 300)}`;
                }
              }
              results.push({ type: "tool_result", tool_use_id: tu.id, content: out });
            }
            messages.push({ role: "user", content: results });
            continue;
          }
          // Final answer
          for (const b of content) {
            if (b.type === "text" && b.text) emit({ type: "text", text: b.text });
          }
          emit({
            type: "done",
            inputTokens, outputTokens,
            cacheReadTokens: cacheRead, cacheCreationTokens: cacheCreation,
          });
          controller.close();
          return;
        }
        throw new Error("tool-loopen nådde maks antall turer");
      } catch (e) {
        emit({ type: "error", message: String(e) });
        controller.close();
      }
    },
  });
}
```

- [ ] **Step 4: Run the full anthropic suite**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/anthropic.test.ts`
Expected: PASS (all old + 3 new tests)

- [ ] **Step 5: Commit**

```bash
git add netlify/edge-functions/_lib/anthropic.ts netlify/edge-functions/_lib/anthropic.test.ts
git commit -m "feat(web-svar): runAgenticStream — non-streaming tool loop with SSE progress, budget, pause_turn"
```

---

### Task 9: Prompt — `prompts/data-svar.md` + `_lib/data-svar-prompt.ts`

**Files:**
- Create: `netlify/edge-functions/_lib/data-svar-prompt.ts`
- Create: `netlify/edge-functions/prompts/data-svar.md` (source doc + changelog, kode-svar.md pattern)
- Test: `netlify/edge-functions/_lib/data-svar-prompt.test.ts`

**Interfaces:**
- Consumes: `renderRegistryBlock` output (string, Task 1).
- Produces:
  - `type DataMode = "python" | "r" | "duckdb"`
  - `coerceDataMode(m: unknown): DataMode` (default `"python"`)
  - `buildDataSvarSystem(mode: DataMode, registryBlock: string): string` — byte-stable for equal inputs (cacheable prefix)
  - `TOOL_DEFS: unknown[]` — Anthropic tool definitions for `search_catalog`, `table_metadata`, `probe` + hosted `web_search` (`{ type: "web_search_20250305", name: "web_search", max_uses: 5 }`)
  - `questionTurn(question: string, script?: string): string`
  - `repairTurn(question: string, script: string, error: string, round: number): string`
  - `progressLabel(name: string, input: Record<string, unknown>): string` (Norwegian progress lines)

- [ ] **Step 1: Write the failing test**

```ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  buildDataSvarSystem, coerceDataMode, progressLabel, questionTurn, repairTurn, TOOL_DEFS,
} from "./data-svar-prompt.ts";

Deno.test("coerceDataMode defaults to python", () => {
  assertEquals(coerceDataMode("r"), "r");
  assertEquals(coerceDataMode("duckdb"), "duckdb");
  assertEquals(coerceDataMode("m2py"), "python");
  assertEquals(coerceDataMode(undefined), "python");
});

Deno.test("system prompt: byte-stable, mode-specific, carries core rules", () => {
  const reg = "## Kilderegister (kuratert)\n\n- **ssb** …";
  const a = buildDataSvarSystem("python", reg);
  assertEquals(a, buildDataSvarSystem("python", reg));
  for (const needle of [
    "connect", "load", "probe", "aldri", "konfunder", "heterogenitet",
    "join", "Kilderegister", "transkribert", "modellkunnskap", "site:",
  ]) {
    if (!a.toLowerCase().includes(needle.toLowerCase())) throw new Error("mangler: " + needle);
  }
  const r = buildDataSvarSystem("r", reg);
  if (!r.includes("ggplot2") || a.includes("ggplot2")) throw new Error("modus-blokker feil");
  const d = buildDataSvarSystem("duckdb", reg);
  if (!d.includes("read_csv_auto")) throw new Error("duckdb-blokk mangler");
});

Deno.test("TOOL_DEFS: three client tools + hosted web_search/web_fetch", () => {
  const names = TOOL_DEFS.map((t) => (t as { name: string }).name);
  assertEquals(names, ["search_catalog", "table_metadata", "probe", "web_search", "web_fetch"]);
  assertEquals((TOOL_DEFS[3] as { type: string }).type, "web_search_20250305");
  assertEquals((TOOL_DEFS[4] as { type: string }).type, "web_fetch_20250910");
});

Deno.test("turns and progress labels", () => {
  if (!questionTurn("Hvor mange?", "x=1").includes("x=1")) throw new Error("script-kontekst mangler");
  const rep = repairTurn("q", "bad()", "NameError: x", 2);
  for (const n of ["bad()", "NameError", "2", "3"]) if (!rep.includes(n)) throw new Error("repair mangler " + n);
  if (!progressLabel("search_catalog", { source: "ssb", query: "ledighet" }).includes("ssb")) {
    throw new Error("progress-etikett");
  }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/data-svar-prompt.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `_lib/data-svar-prompt.ts`**

The full block text below is the v1 prompt — refine wording freely during eval runs (Task 14), but keep the block structure and the test needles.

```ts
// System prompt + tool definitions for /api/data-svar (Web mode).
// Source doc + changelog: netlify/edge-functions/prompts/data-svar.md
// Structure mirrors kode-svar.ts: named const blocks, assembled byte-stably.

export type DataMode = "python" | "r" | "duckdb";

export function coerceDataMode(m: unknown): DataMode {
  return m === "r" || m === "duckdb" ? m : "python";
}

const INTRO = `\
Du er en forskningsassistent som besvarer spørsmål med ÅPNE DATA og kjørbar
kode. Du svarer på brukerens språk (norsk/engelsk). Arbeidsflyt i TRE faser:

1. **TOLK** spørsmålet: hva er estimanden (beskrivelse? sammenligning?
   årsakseffekt?), analyseenhet, geografi og periode, og hvilken
   identifikasjonsstrategi som er realistisk. Lag en data-ønskeliste.
2. **FINN data med verktøyene** (search_catalog → table_metadata → probe;
   web_search/web_fetch for kilder utenfor registeret). Regler:
   - Datasett-ID-er og kolonnenavn skal komme fra verktøy-resultater.
     ALDRI generer mot antatte skjemaer eller funnede ID-er fra hukommelsen.
   - Alt funnet via web_search MÅ probes (eller leses med web_fetch) før
     det brukes i scriptet.
   - Tomt søk? Prøv synonymer, engelsk/norsk, en annen kilde. Bruk
     søkehåndverk: \`site:data.norge.no\`, \`filetype:csv\`, "dataset" +
     tema på engelsk.
   - Bygg MINIMALE uttrekk: bare variablene, periodene og geografiene
     analysen trenger (table_metadata gir kodene).
3. **GENERER** ett komplett, kjørbart script i brukerens modus (se
   Leveringsregler og modus-blokken). Finner du ikke data: si det ærlig,
   vis hva du søkte på, og foreslå omformuleringer. ALDRI fabrikker.`;

const DELIVERY = `\
## Leveringsregler (connect/load-direktiver)

Datakilder deklareres ØVERST i scriptet som kommentar-direktiver
(kommentartegn per språk: #, --, //):

\`\`\`
# connect https://data.ssb.no/api/pxwebapi/v2-beta/tables as ssb
# connect fred
# load ssb/05839/data?valueCodes[Kjonn]=0&outputFormat=csv as ledighet
# load https://ourworldindata.org/grapher/co2.csv as co2
\`\`\`

- \`# connect <base-url|register-id> [as alias]\` — kobler til en kilde.
- \`# load <url|alias/sti> as navn\` — henter ETT uttrekk; \`navn\` blir en
  hel DataFrame/data.frame/tabell i scriptet. Kolonnene er dem probe viste.
- Kilder uten CORS eller med nøkkel lastes via proxy:
  \`# load /api/hent?url=<url-enkodet> as navn\` (aldri ta med nøkler selv).
- POST-API-er GET-innpakkes: \`# load /api/hent?url=<endepunkt>&body=<url-enkodet-json> as navn\`.
- Flertrinns-API-kall som ikke passer i én load-linje skrives som kode med
  kilde-URL i kommentar.
- Siter HVER kilde med URL i en kommentar ved bruksstedet, og merk hvilke
  som er probe-verifisert.`;

const SCIENCE = `\
## Vitenskapelig kjerne (effekt- og sammenligningsspørsmål)

- **Rå → justert.** Vis først den enkle sammenligningen, deretter en justert
  modell som kontrollerer for konfunderende variabler som er RELEVANTE FOR
  AKKURAT DETTE SPØRSMÅLET og finnes i dataene — ingen fast liste. Vis
  hvordan estimatet flytter seg, og kommenter hvorfor.
- **Identifikasjon.** Velg enkleste troverdige design og OPPGI antakelsen:
  faste effekter (panel), diff-in-diff/event study (parallelle trender),
  IV (relevans+eksogenitet, sjekk første-trinns F), RDD (ingen manipulasjon
  rundt terskelen), syntetisk kontroll (pre-periode-tilpasning). Robuste/
  klyngede standardfeil der det er naturlig; rapporter alltid usikkerhet.
- **Heterogenitet.** Ta med ÉN grov, godt befolket oppdeling der det er
  naturlig; foreslå dypere oppdelinger i prosa.
- **Ærlighet.** Uten troverdig identifikasjon: si klart at resultatet er
  deskriptivt/assosiasjon, ikke årsak.`;

const INLINE = `\
## Datatilfangst-stigen (data uten endepunkt)

Foretrekk alltid nivå 1; gå nedover bare når nivået over ikke finnes:
1. **Probet endepunkt** (\`# load …\`). Wikipedia-tabeller ER load-bare:
   \`# load /api/hent?url=<url-enkodet artikkel> as raw\` og
   \`pd.read_html(io.StringIO(raw))\` (installer lxml med micropip).
2. **Transkribert fra hentet innhold**: har du LEST kilden (web_fetch), kan du
   skrive små tabeller (< ~50 rader) inline:
   \`data_<navn> = """..."""\` + \`pd.read_csv(io.StringIO(data_<navn>))\`
   (R: \`read.csv(text = "...")\`). KRAV: kilde-URL i kommentar ved blokken
   + merk «transkribert, ikke maskinelt verifisert».
3. **Modellkunnskap**: KUN stabile referansefakta (ISO-koder, kjente
   reformdatoer, klassifiseringer), merket «fra modellkunnskap — verifiser».
   ALDRI som utfallsvariabel — utfall skal komme fra nivå 1–2.

Nivå 2–3 er særlig riktig for lim-tabellene kausale design trenger
(reformdatoer, tiltaks-/kontrollgrupper, regiongrupperinger).`;

const MULTI = `\
## Flerkilde og sammenslåing

Å kombinere kilder er en styrke. Mønster: hver load-linje gir én ramme per
variabel/serie; FØRSTE analysesteg er å merge/joine til ÉN analysedataframe
når det er mulig og nyttig (join på år, landkode ISO2/ISO3, kommunenummer —
se join-nøkler i registeret). Harmoniser koder og enheter FØR join, kommenter
join-type (inner/left) og hvorfor, og sjekk radtall før/etter (stille
rad-tap er en klassisk feilkilde).`;

const MODE_PY = `\
## Modus: Python (Pyodide)

Forhåndslastet: pandas, numpy, scipy, statsmodels, matplotlib, seaborn,
plotly. Andre pakker: \`import micropip; await micropip.install("pakke")\`.
load-rammene er pandas-DataFrames. Presenter både tall og figur der det gjør
resultatet lettere å lese.

## Svarformat
Kort forklaring (1–3 setninger) av tilnærming og kilder, deretter ÉN kjørbar
\`\`\`python-blokk med connect/load-direktivene øverst. Ikke JSON.`;

const MODE_R = `\
## Modus: R (WebR)

tidyverse (dplyr, ggplot2, tidyr) og base R. Andre pakker:
\`webr::install("pakke")\`. load-rammene er data.frames. Figurer med ggplot2.

## Svarformat
Kort forklaring (1–3 setninger), deretter ÉN kjørbar \`\`\`r-blokk med
connect/load-direktivene øverst (--/# kommentar). Ikke JSON.`;

const MODE_DUCK = `\
## Modus: DuckDB (duckdb-wasm)

load-rammene blir tabeller (via read_csv_auto ved materialisering). Analyse i
SQL (CTE-er, vindusfunksjoner); hybrid med #py-blokk for figurer er mulig.

## Svarformat
Kort forklaring (1–3 setninger), deretter ÉN kjørbar \`\`\`sql-blokk med
connect/load-direktivene øverst (-- kommentar). Ikke JSON.`;

const MODE: Record<DataMode, string> = { python: MODE_PY, r: MODE_R, duckdb: MODE_DUCK };

export function buildDataSvarSystem(mode: DataMode, registryBlock: string): string {
  return [INTRO, DELIVERY, SCIENCE, INLINE, MULTI, MODE[mode], registryBlock].join("\n\n");
}

export const TOOL_DEFS: unknown[] = [
  {
    name: "search_catalog",
    description: "Søk i en registerkildes levende katalog (tabeller/datasett). Bruk id fra kilderegisteret.",
    input_schema: {
      type: "object",
      properties: {
        source: { type: "string", description: "kilde-id fra registeret, f.eks. 'ssb'" },
        query: { type: "string", description: "søkeord (prøv synonymer/begge språk ved tomt svar)" },
      },
      required: ["source", "query"],
    },
  },
  {
    name: "table_metadata",
    description: "Variabel-nivå metadata for en tabell fra search_catalog: dimensjoner, koder, tidsperioder — grunnlaget for et minimalt uttrekk.",
    input_schema: {
      type: "object",
      properties: {
        source: { type: "string" },
        table_id: { type: "string" },
      },
      required: ["source", "table_id"],
    },
  },
  {
    name: "probe",
    description: "Verifiser en data-URL: finnes den, hvilke kolonner har den (observert skjema), takler nettleseren CORS? Obligatorisk for alt fra web_search.",
    input_schema: {
      type: "object",
      properties: { url: { type: "string" } },
      required: ["url"],
    },
  },
  { type: "web_search_20250305", name: "web_search", max_uses: 5 },
  { type: "web_fetch_20250910", name: "web_fetch", max_uses: 5 },
];

export function questionTurn(question: string, script?: string): string {
  return [
    "# Brukerforespørsel",
    script?.trim() ? `**Gjeldende script i editor (kontekst):**\n\`\`\`\n${script.trim()}\n\`\`\`` : "",
    `**Spørsmål:** ${question}`,
  ].filter(Boolean).join("\n\n");
}

export function repairTurn(question: string, script: string, error: string, round: number): string {
  return [
    `# Reparasjonsrunde ${round} av 3`,
    `Scriptet du genererte for spørsmålet «${question}» feilet ved kjøring.`,
    `**Script:**\n\`\`\`\n${script}\n\`\`\``,
    `**Feil:**\n\`\`\`\n${error}\n\`\`\``,
    `Klassifiser feilen og reparer:`,
    `- Nettverk/CORS → bytt til /api/hent-innpakket load-linje, eller en annen kilde (re-probe gjerne).`,
    `- Skjema/kolonnefeil → probe URL-en på nytt og rett kolonnenavn.`,
    `- Logikkfeil → rett koden.`,
    `Svar med komplett, korrigert script i samme format som før.`,
  ].join("\n\n");
}

export function progressLabel(name: string, input: Record<string, unknown>): string {
  switch (name) {
    case "search_catalog": return `Søker i ${input.source ?? "katalog"}: «${input.query ?? ""}» …`;
    case "table_metadata": return `Henter variabler for ${input.source ?? ""}/${input.table_id ?? ""} …`;
    case "probe": return `Sjekker ${String(input.url ?? "").slice(0, 80)} …`;
    default: return `Kjører ${name} …`;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/data-svar-prompt.test.ts`
Expected: PASS (4 tests)

- [ ] **Step 5: Write the source doc `prompts/data-svar.md`**

```markdown
<!-- KILDE for data-svar-edge-funksjonen (Web-modus: generelle dataspørsmål
mot åpne kilder). TS-konstantene i _lib/data-svar-prompt.ts er render-målet;
denne fila er kildedokument + endringslogg (samme mønster som kode-svar.md).

Design: docs/superpowers/specs/2026-07-03-web-data-svar-design.md.

Blokkstruktur: INTRO (tre faser: tolk → finn → generer; søkehåndverk),
DELIVERY (connect/load-direktiver, proxy, POST-innpakking, kildesitering),
SCIENCE (rå→justert, identifikasjon, heterogenitet, ærlighet — utvidet fra
INFERENCE_STRATEGY_PYR i kode-svar.ts), INLINE (datatilfangst-stigen:
probet → transkribert-fra-web_fetch → modellkunnskap; aldri utfall fra
nivå 3), MULTI (merge til ÉN analysedataframe, join-nøkler, radtall
før/etter), MODE_PY/R/DUCK (miljø + svarformat), + registerblokk
(renderRegistryBlock, byte-stabil). Hosted tools: web_search + web_fetch.

Prompt-utviklingsloop (spec §7): endringer kjøres mot evalsettet
(docs/eval/data-svar-evalsett.md) før deploy; feilmønstre fra evals og
reparasjonsrunder blir nye promptregler eller register-quirks.

ENDRINGSLOGG
- 2026-07-03: v1 — blokkene opprettet per spec.
-->

Se `_lib/data-svar-prompt.ts` — innholdet er inlinet som TS-konstanter fordi
Deno Deploy ikke bundler .md-filer ved kjøretid.
```

- [ ] **Step 6: Commit**

```bash
git add netlify/edge-functions/_lib/data-svar-prompt.ts netlify/edge-functions/_lib/data-svar-prompt.test.ts netlify/edge-functions/prompts/data-svar.md
git commit -m "feat(web-svar): data-svar prompt blocks, tool defs, question/repair turns"
```

---
### Task 10: Endpoint — `netlify/edge-functions/data-svar.ts` (`/api/data-svar`)

**Files:**
- Create: `netlify/edge-functions/data-svar.ts`
- Create: `netlify/edge-functions/_lib/sse-util.ts` (stream wrapper)
- Test: `netlify/edge-functions/_lib/sse-util.test.ts`
- Modify: `netlify.toml`

**Interfaces:**
- Consumes: `adminGate` (T3), `loadRegistry`/`renderRegistryBlock` (T1), `searchCatalog` (T5), `tableMetadata` (T6), `probeUrl` (T7), `runAgenticStream` (T8), prompt module (T9).
- Produces:
  - `injectBeforeDone(stream: ReadableStream<Uint8Array>, makeEvent: () => Record<string, unknown> | null): ReadableStream<Uint8Array>` — passes SSE through; immediately before the `done` event, injects one extra event (the source manifest). Null ⇒ nothing injected.
  - HTTP contract: `POST /api/data-svar` body `{ question: string, mode?: "python"|"r"|"duckdb", script?: string, repair?: { script: string, error: string, round: number } }` → SSE with `progress`/`text`/`sources`/`done`/`error` events. `sources` event: `{ type: "sources", sources: [{ url, ok, cors, viaProxy }] }` built from the probe log (deterministic — not model-formatted).

- [ ] **Step 1: Write the failing test for the stream wrapper**

`netlify/edge-functions/_lib/sse-util.test.ts`:

```ts
import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { injectBeforeDone } from "./sse-util.ts";

function sse(events: Record<string, unknown>[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const e of events) c.enqueue(enc.encode(`data: ${JSON.stringify(e)}\n\n`));
      c.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<Record<string, unknown>[]> {
  const text = await new Response(stream).text();
  return text.split("\n\n").filter((l) => l.startsWith("data: ")).map((l) => JSON.parse(l.slice(6)));
}

Deno.test("injectBeforeDone inserts sources right before done", async () => {
  const out = await collect(injectBeforeDone(
    sse([{ type: "text", text: "hei" }, { type: "done", outputTokens: 1 }]),
    () => ({ type: "sources", sources: [{ url: "https://x", ok: true }] }),
  ));
  assertEquals(out.map((e) => e.type), ["text", "sources", "done"]);
});

Deno.test("injectBeforeDone: null event and no done-event pass through", async () => {
  const a = await collect(injectBeforeDone(sse([{ type: "done" }]), () => null));
  assertEquals(a.map((e) => e.type), ["done"]);
  const b = await collect(injectBeforeDone(sse([{ type: "error", message: "x" }]), () => ({ type: "sources" })));
  assertEquals(b.map((e) => e.type), ["error"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/sse-util.test.ts`
Expected: FAIL (module not found)

- [ ] **Step 3: Write `_lib/sse-util.ts`**

```ts
// SSE pass-through that injects one synthetic event immediately before the
// `done` event (used for the deterministic source manifest in data-svar).
export function injectBeforeDone(
  stream: ReadableStream<Uint8Array>,
  makeEvent: () => Record<string, unknown> | null,
): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  let buffer = "";
  return new ReadableStream({
    async start(controller) {
      const reader = stream.getReader();
      const flushEvent = (raw: string) => {
        const dataLine = raw.split("\n").find((l) => l.startsWith("data:"));
        if (dataLine) {
          try {
            const obj = JSON.parse(dataLine.slice(5).trim());
            if (obj?.type === "done") {
              const extra = makeEvent();
              if (extra) controller.enqueue(enc.encode(`data: ${JSON.stringify(extra)}\n\n`));
            }
          } catch { /* pass through unparseable events untouched */ }
        }
        controller.enqueue(enc.encode(raw + "\n\n"));
      };
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += dec.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf("\n\n")) >= 0) {
            flushEvent(buffer.slice(0, idx));
            buffer = buffer.slice(idx + 2);
          }
        }
        if (buffer.trim()) flushEvent(buffer.trimEnd());
      } finally {
        reader.releaseLock();
        controller.close();
      }
    },
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/sse-util.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the handler `netlify/edge-functions/data-svar.ts`**

```ts
// /api/data-svar — Web mode: agentic discovery + generation (admin-only).
// Spec: docs/superpowers/specs/2026-07-03-web-data-svar-design.md
import { adminGate } from "./_lib/auth.ts";
import { runAgenticStream } from "./_lib/anthropic.ts";
import { loadRegistry, renderRegistryBlock } from "./_lib/registry.ts";
import { searchCatalog } from "./_lib/tools/search-catalog.ts";
import { tableMetadata } from "./_lib/tools/table-metadata.ts";
import { probeUrl } from "./_lib/tools/probe.ts";
import { injectBeforeDone } from "./_lib/sse-util.ts";
import {
  buildDataSvarSystem, coerceDataMode, progressLabel, questionTurn, repairTurn, TOOL_DEFS,
} from "./_lib/data-svar-prompt.ts";

interface RepairBody { script: string; error: string; round: number; }
interface RequestBody {
  question?: string;
  mode?: string;
  script?: string;
  repair?: RepairBody;
}

export default async (request: Request): Promise<Response> => {
  const gateResp = await adminGate(request, { endpoint: "data-svar", maxBodyBytes: 120_000 });
  if (gateResp) return gateResp;

  let body: RequestBody;
  try { body = await request.json(); } catch { return new Response("Invalid JSON", { status: 400 }); }
  const question = (body.question ?? "").trim();
  if (!question) return new Response("Missing question", { status: 400 });
  const repair = body.repair;
  if (repair && (!repair.script || !repair.error || !(repair.round >= 1 && repair.round <= 3))) {
    return new Response("Invalid repair payload", { status: 400 });
  }

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("DATA_SVAR_MODEL") ?? Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    console.error("ANTHROPIC_API_KEY is not set");
    return new Response("Server configuration error", { status: 500 });
  }

  const origin = new URL(request.url).origin;
  let registry;
  try { registry = await loadRegistry(origin); } catch (e) {
    console.error("data-svar: registry load failed:", e);
    return new Response("Kilderegister utilgjengelig", { status: 502 });
  }

  const mode = coerceDataMode(body.mode);
  const system = buildDataSvarSystem(mode, renderRegistryBlock(registry));

  // Deterministic source manifest: collected from probe calls, not model text.
  const probed: { url: string; ok: boolean; cors: boolean; viaProxy: boolean }[] = [];

  const executeTool = async (name: string, input: Record<string, unknown>): Promise<string> => {
    if (name === "search_catalog") {
      return JSON.stringify(await searchCatalog(String(input.source ?? ""), String(input.query ?? ""), { registry }));
    }
    if (name === "table_metadata") {
      return JSON.stringify(await tableMetadata(String(input.source ?? ""), String(input.table_id ?? ""), { registry }));
    }
    if (name === "probe") {
      const url = String(input.url ?? "");
      const r = await probeUrl(url);
      probed.push({ url, ok: r.ok, cors: r.cors, viaProxy: r.ok && !r.cors });
      return JSON.stringify(r);
    }
    throw new Error(`ukjent verktøy: ${name}`);
  };

  const userContent = repair
    ? repairTurn(question, repair.script, repair.error, repair.round)
    : questionTurn(question, body.script);

  const inner = runAgenticStream({
    apiKey, model, system, userContent,
    tools: TOOL_DEFS,
    executeTool,
    progressLabel,
    cacheTtl: "1h",
    maxTokens: 8192,
    maxClientToolCalls: 12,
  });

  const stream = injectBeforeDone(inner, () =>
    probed.length ? { type: "sources", sources: probed } : null);

  return new Response(stream, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
};
```

- [ ] **Step 6: Map the route in `netlify.toml`**

```toml
[[edge_functions]]
  function = "data-svar"
  path = "/api/data-svar"
```

- [ ] **Step 7: Full test suite + live smoke test**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/`
Expected: all PASS.

Then with `netlify dev` running (needs `ANTHROPIC_API_KEY` in `.env`):

```bash
curl -N -X POST http://localhost:8888/api/data-svar \
  -H "Content-Type: application/json" -H "Authorization: Bearer $M2PY_ACCESS_TOKEN" \
  -d '{"question":"Hvordan har arbeidsledigheten i Norge utviklet seg siden 2010?","mode":"python"}'
```

Expected: stream of `progress` events (SSB catalog search, metadata, probes), then `text` with a python script containing `# connect`/`# load` lines, a `sources` event, and `done`. This is the first end-to-end run — expect prompt/adapter fixes; iterate here until one full happy path works.

- [ ] **Step 8: Commit**

```bash
git add netlify/edge-functions/data-svar.ts netlify/edge-functions/_lib/sse-util.ts netlify/edge-functions/_lib/sse-util.test.ts netlify.toml
git commit -m "feat(web-svar): /api/data-svar agentic endpoint — tool dispatch, source manifest, admin-gated"
```

---

### Task 11: Directive parser — `js/data-directives.js`

**Files:**
- Create: `js/data-directives.js`
- Test: `netlify/edge-functions/_lib/data-directives.test.ts` (deno test evals the plain-script file; lives with the other deno tests so `deno test _lib/` covers it)

**Interfaces:**
- Produces (attached to `window.DataDirectives` / `globalThis.DataDirectives`; plain script, no module system — loaded via `<script src="js/data-directives.js">`):
  - `parse(script)` → `{ connects: [{ target, alias }], loads: [{ verb: "load"|"require", target, alias, line }], errors: string[] }` — recognizes `connect`/`load` and legacy `require` **only as extraction when the target is a URL or `/api/hent?...`** (named `require <navn> as x` stays the server-routing directive handled by `maybeRunRemote`; this parser ignores it).
  - `resolve(parsed, registry)` → `[{ alias, url, viaProxy, error? }]` — expands `alias/path` targets against connects (base-URL or registry-id), flags `viaProxy` for registry sources with `auth` or `cors:false`, passes absolute URLs through, `/api/hent?...` targets get `viaProxy: true`.
  - `registry` argument: the parsed content of `/data/data-sources.json` (array), or `null` (then registry-id connects produce an error entry).

- [ ] **Step 1: Write the failing test**

`netlify/edge-functions/_lib/data-directives.test.ts`:

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/data-directives.test.ts`
Expected: FAIL (file not found / DD undefined)

- [ ] **Step 3: Write `js/data-directives.js`**

```js
// connect/load-direktiver for Web-modus (spec 5b/5c i
// docs/superpowers/specs/2026-07-03-web-data-svar-design.md).
//   # connect <base-url|register-id> [as alias]   — kilde
//   # load <url|alias/sti> as navn                — uttrekk (hel ramme)
//   # require <url> as navn                       — legacy-alias for load (D1)
// Ren parsing/resolusjon — ingen fetch her. Brukes av index.html
// (materialisering) og testes med deno via eval (data-directives.test.ts).
(function (global) {
  'use strict';

  var CONNECT_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*connect[ \t]+(\S+)(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?[ \t]*$/gim;
  var LOAD_RE = /^[ \t]*(?:#|--|\/\/)[ \t]*(load|require)[ \t]+(\S+)[ \t]+as[ \t]+([A-Za-z_]\w*)[ \t]*$/gim;

  function isUrlish(target) {
    return /^https?:\/\//i.test(target) || target.indexOf('/api/hent?') === 0;
  }

  function parse(script) {
    var connects = [], loads = [], errors = [], m;
    CONNECT_RE.lastIndex = 0;
    while ((m = CONNECT_RE.exec(script)) !== null) {
      var target = m[1];
      var alias = m[2] || (isUrlish(target) ? null : target); // register-id: alias = id
      if (!alias) { errors.push('connect med URL krever "as <alias>": ' + target); continue; }
      connects.push({ target: target, alias: alias });
    }
    LOAD_RE.lastIndex = 0;
    while ((m = LOAD_RE.exec(script)) !== null) {
      var verb = m[1].toLowerCase();
      // Legacy require er BARE vårt når målet er en URL (navngitte kilder
      // rutes til serveren av maybeRunRemote — ikke rør dem her).
      if (verb === 'require' && !isUrlish(m[2])) continue;
      loads.push({ verb: verb, target: m[2], alias: m[3], line: m[0].trim() });
    }
    return { connects: connects, loads: loads, errors: errors };
  }

  function findRegistrySource(registry, id) {
    if (!registry) return null;
    for (var i = 0; i < registry.length; i++) if (registry[i].id === id) return registry[i];
    return null;
  }

  function resolve(parsed, registry) {
    var byAlias = {};
    parsed.connects.forEach(function (c) { byAlias[c.alias] = c; });
    return parsed.loads.map(function (l) {
      if (isUrlish(l.target)) {
        return { alias: l.alias, url: l.target, viaProxy: l.target.indexOf('/api/hent?') === 0 };
      }
      var slash = l.target.indexOf('/');
      var head = slash > 0 ? l.target.slice(0, slash) : l.target;
      var rest = slash > 0 ? l.target.slice(slash + 1) : '';
      var conn = byAlias[head];
      if (!conn) return { alias: l.alias, url: '', viaProxy: false, error: 'ukjent kilde-alias «' + head + '» (mangler connect-linje?)' };
      var base, viaProxy = false;
      if (isUrlish(conn.target)) {
        base = conn.target;
      } else {
        var src = findRegistrySource(registry, conn.target);
        if (!src) return { alias: l.alias, url: '', viaProxy: false, error: 'ukjent register-id «' + conn.target + '»' };
        base = src.base_url;
        viaProxy = !!src.auth || src.cors === false;
      }
      if (base.charAt(base.length - 1) !== '/') base += '/';
      return { alias: l.alias, url: base + rest, viaProxy: viaProxy };
    });
  }

  global.DataDirectives = { parse: parse, resolve: resolve };
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd netlify/edge-functions && deno test --allow-all _lib/data-directives.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Include the script in `index.html`**

Find the existing script includes (search for `js/ai-chat.js`) and add before it:

```html
<script src="js/data-directives.js"></script>
```

- [ ] **Step 6: Commit**

```bash
git add js/data-directives.js netlify/edge-functions/_lib/data-directives.test.ts index.html
git commit -m "feat(web-svar): connect/load directive parser + resolver (legacy require URL alias)"
```

---
### Task 12: Local materialization (js/data-loader.js + three small runner hooks)

**Files:**
- Create: `js/data-loader.js` (ALL fetch/format logic — keeps index.html growth minimal)
- Test: `netlify/edge-functions/_lib/data-loader.test.ts`
- Modify: `index.html` (only: one `<script>` include + three ~10-line runner hooks)
- Manual test: example scripts (Step 4)

**Interfaces:**
- Consumes: `window.DataDirectives.parse/resolve` (Task 11), `/api/hent` (Task 4), `/data/data-sources.json` (Task 1).
- Produces: `window.DataLoader.resolveAndFetchLoads(script, deps?)` → `Promise<[{ alias, bytes: Uint8Array, format: "csv"|"json"|"parquet"|"html" }]>` — parses directives, resolves against the registry, fetches each load (direct → proxy fallback), sniffs format by response `content-type` (**content-based, not URL-extension** — closes loader gap 1 in spec §5b). Throws Norwegian errors naming the failing alias/URL. `deps` (all optional, for tests/wiring): `{ fetchImpl, registry, authToken }`.
- index.html's only new responsibility: binding the returned bytes into each runtime (FS write + one read call per alias).

Implementation notes for the engineer (read first):
- Find the runners: `grep -n "loadPyodideAndM2py\|webr\|duckdb" index.html`. Python execution ≈ the Pyodide path near `deriveSafeStatExecutor` usage (`index.html:7683-7740` region); the duckdb connection setup is near `index.html:2940-2990`; the R runner is found via `grep -n "webR\|webr" index.html`.
- Proxy fallback: try direct `fetch(url)`; on network error (CORS shows as `TypeError`) or when `viaProxy` is already true, retry as `fetch('/api/hent?url=' + encodeURIComponent(url), { headers: { Authorization: 'Bearer ' + token } })` where `token` comes from the same place ai-chat.js gets it (grep `Authorization` in `js/ai-chat.js`).
- Registry for `resolve`: fetch `/data/data-sources.json` once, cache in a module-level variable.

- [ ] **Step 1: Write `js/data-loader.js` (all logic lives here, not in index.html)**

```js
// Materialisering av connect/load-direktiver: parse → resolve → fetch.
// Ingen runtime-binding her — index.html binder bytes inn i pyodide/webr/
// duckdb med ~10 linjer per modus. deps er injiserbar for tester.
(function (global) {
  'use strict';

  var _registryCache = null;
  async function loadRegistry(fetchImpl) {
    if (_registryCache) return _registryCache;
    try {
      var r = await fetchImpl('data/data-sources.json');
      _registryCache = r.ok ? await r.json() : [];
    } catch (e) { _registryCache = []; }
    return _registryCache;
  }

  async function fetchLoadTarget(item, fetchImpl, authToken) {
    async function viaProxy() {
      var headers = authToken ? { 'Authorization': 'Bearer ' + authToken } : {};
      var pr = await fetchImpl('/api/hent?url=' + encodeURIComponent(item.url), { headers: headers });
      if (!pr.ok) throw new Error('proxy ' + pr.status + ' for ' + item.alias);
      return pr;
    }
    if (item.url.indexOf('/api/hent?') === 0) {
      var headers2 = authToken ? { 'Authorization': 'Bearer ' + authToken } : {};
      var r0 = await fetchImpl(item.url, { headers: headers2 });
      if (!r0.ok) throw new Error('proxy ' + r0.status + ' for ' + item.alias);
      return r0;
    }
    if (item.viaProxy) return viaProxy();
    try {
      var r1 = await fetchImpl(item.url);
      if (!r1.ok) throw new Error('HTTP ' + r1.status + ' for ' + item.alias + ' (' + item.url + ')');
      return r1;
    } catch (e) {
      if (e instanceof TypeError) return viaProxy();   // CORS/nettverk → proxy
      throw e;
    }
  }

  function sniffFormat(resp, url) {
    var ct = (resp.headers.get('content-type') || '').toLowerCase();
    if (ct.indexOf('parquet') >= 0 || /\.parquet(\?|$)/.test(url)) return 'parquet';
    if (ct.indexOf('json') >= 0) return 'json';
    if (ct.indexOf('html') >= 0) return 'html';   // f.eks. Wikipedia: bind som råtekst
    return 'csv';
  }

  // Hoved-API: [{alias, bytes(Uint8Array), format}] eller kast norsk feil.
  async function resolveAndFetchLoads(script, deps) {
    deps = deps || {};
    var fetchImpl = deps.fetchImpl || (typeof fetch !== 'undefined' ? fetch.bind(global) : null);
    var DD = global.DataDirectives;
    if (!DD || !fetchImpl) return [];
    var parsed = DD.parse(script);
    if (!parsed.loads.length) return [];
    var registry = deps.registry || await loadRegistry(fetchImpl);
    var resolved = DD.resolve(parsed, registry);
    var bad = resolved.filter(function (r) { return r.error; });
    if (bad.length) throw new Error('Direktivfeil: ' + bad.map(function (b) { return b.error; }).join('; '));
    return Promise.all(resolved.map(async function (item) {
      var resp = await fetchLoadTarget(item, fetchImpl, deps.authToken || null);
      var buf = new Uint8Array(await resp.arrayBuffer());
      return { alias: item.alias, bytes: buf, format: sniffFormat(resp, item.url) };
    }));
  }

  global.DataLoader = { resolveAndFetchLoads: resolveAndFetchLoads, _sniffFormat: sniffFormat };
})(typeof window !== 'undefined' ? window : globalThis);
```

- [ ] **Step 1b: Write and run the deno test**

`netlify/edge-functions/_lib/data-loader.test.ts`:

```ts
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
```

Run: `cd netlify/edge-functions && deno test --allow-all _lib/data-loader.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 1c: Include the script in `index.html`**

Next to the Task 11 include:

```html
<script src="js/data-loader.js"></script>
```

- [ ] **Step 2: Wire into the three runners**

**Python (Pyodide):** immediately before user code executes (same place the `#micro`-bridge / upload frames are injected — grep `_upload_df` for the pattern), add:

```js
        var _loads = await window.DataLoader.resolveAndFetchLoads(effectiveScript, { authToken: getAuthToken() });
        for (var _li = 0; _li < _loads.length; _li++) {
          var _ld = _loads[_li];
          var _path = '/home/pyodide/_webdata/' + _ld.alias + '.' + _ld.format;
          py.FS.mkdirTree('/home/pyodide/_webdata');
          py.FS.writeFile(_path, _ld.bytes);
          if (_ld.format === 'html') {
            // HTML (f.eks. Wikipedia): bind som råtekst — scriptet bruker
            // pd.read_html(io.StringIO(alias)) selv (se registry-oppskrift).
            await py.runPythonAsync(
              _ld.alias + ' = open(' + JSON.stringify(_path) + ', encoding="utf-8").read()'
            );
          } else {
            var _read = _ld.format === 'parquet' ? 'pd.read_parquet'
                      : _ld.format === 'json' ? 'pd.read_json' : 'pd.read_csv';
            await py.runPythonAsync(
              'import pandas as pd\n' + _ld.alias + ' = ' + _read + '(' + JSON.stringify(_path) + ')'
            );
          }
        }
```

**R (WebR):** same position in the R runner; write to the WebR FS and bind with `read.csv`/`jsonlite::fromJSON` (parquet: raise a clear "parquet støttes ikke i R-modus ennå"):

```js
        var _loadsR = await window.DataLoader.resolveAndFetchLoads(effectiveScript, { authToken: getAuthToken() });
        for (var _ri = 0; _ri < _loadsR.length; _ri++) {
          var _lr = _loadsR[_ri];
          if (_lr.format === 'parquet') throw new Error('parquet støttes ikke i R-modus ennå (' + _lr.alias + ')');
          var _rp = '/home/web_user/_webdata_' + _lr.alias + '.' + _lr.format;
          await webR.FS.writeFile(_rp, _lr.bytes);
          var _rcode = _lr.format === 'json'
            ? _lr.alias + ' <- jsonlite::fromJSON(' + JSON.stringify(_rp) + ')'
            : _lr.format === 'html'
            ? _lr.alias + ' <- paste(readLines(' + JSON.stringify(_rp) + ', warn = FALSE), collapse = "\\n")'
            : _lr.alias + ' <- read.csv(' + JSON.stringify(_rp) + ', check.names = FALSE)';
          await webR.evalRVoid(_rcode);
        }
```

**DuckDB:** after the connection exists, register bytes and create tables:

```js
        var _loadsD = await window.DataLoader.resolveAndFetchLoads(effectiveScript, { authToken: getAuthToken() });
        for (var _di = 0; _di < _loadsD.length; _di++) {
          var _ldd = _loadsD[_di];
          if (_ldd.format === 'html') throw new Error('html-kilder støttes ikke i duckdb-modus (' + _ldd.alias + ') — bruk python/r');
          var _fname = '_webdata_' + _ldd.alias + '.' + _ldd.format;
          await db.registerFileBuffer(_fname, _ldd.bytes);
          var _reader = _ldd.format === 'parquet' ? "read_parquet('" + _fname + "')"
                      : _ldd.format === 'json' ? "read_json_auto('" + _fname + "')"
                      : "read_csv_auto('" + _fname + "')";
          await conn.query('CREATE OR REPLACE TABLE "' + _ldd.alias + '" AS SELECT * FROM ' + _reader);
        }
```

Adapt variable names (`py`, `webR`, `db`, `conn`, `effectiveScript`) to what the surrounding runner actually uses — read the surrounding 30 lines first. Directive lines are comments in every language, so the script itself needs no rewriting.

- [ ] **Step 3: Guard the existing remote-routing path**

In `maybeRunRemote` (`index.html:7617`), directive scripts must not be misrouted: it already ignores URL-requires (`named.length` check). Verify `connect`/`load` lines cannot match its named-require regex (they use different verbs — confirm by running a quick console test in the browser devtools):

```js
DataDirectives.parse('# connect ssb\n# load ssb/x.csv as y').loads.length === 1
&& !/^[ \t]*(?:#|--|\/\/)[ \t]*require\s+\S+\s+as\s+\w+/im.test('# connect ssb\n# load ssb/x.csv as y')
```

Expected: `true`. (Regression guard: microdata-import → python-analysis hybrid scripts still run locally — spec D7.)

- [ ] **Step 4: Manual end-to-end check (all three modes)**

With `netlify dev` running and logged in as admin, paste and run each:

Python mode:
```
# load https://ourworldindata.org/grapher/co2.csv as co2
co2[co2["Entity"] == "Norway"].tail()
```
R mode:
```
# load https://ourworldindata.org/grapher/co2.csv as co2
tail(subset(co2, Entity == "Norway"))
```
DuckDB mode:
```
-- load https://ourworldindata.org/grapher/co2.csv as co2
SELECT * FROM co2 WHERE Entity = 'Norway' ORDER BY Year DESC LIMIT 5;
```

Expected: each shows Norway CO₂ rows. Then verify the proxy path in python mode with a FRED series (requires `FRED_API_KEY` in `.env`):

```
# connect fred
# load fred/series/observations?series_id=UNRATE&file_type=json as us
us
```

Expected: data loads via `/api/hent` (check the network tab: no `api_key` visible anywhere).

- [ ] **Step 5: Commit**

```bash
git add js/data-loader.js netlify/edge-functions/_lib/data-loader.test.ts index.html
git commit -m "feat(web-svar): data loader (fetch/format/proxy-fallback in js/data-loader.js) + minimal runner hooks in index.html"
```

---

### Task 13: Web mode UI + auto-repair — `js/ai-chat.js`

**Files:**
- Modify: `js/ai-chat.js`
- Manual test: Step 5

**Interfaces:**
- Consumes: `/api/data-svar` SSE contract (Task 10), `user.is_admin` (already in `js/ai-chat.js:1087`), existing mode toggle (`LS_KEY_AIMODE`, `state.anvilMode` at `js/ai-chat.js:7-17`), the existing v2 script-extraction + validation helpers (`js/ai-chat.js:690-830` region), the run entry point used by the editor's Kjør button.
- Produces: third AI mode `'web'` in `md_ai_mode`; `runWebAnswer(question)` flow: SSE render (progress lines → markdown text → source manifest) → insert script → syntax check → auto-run → on error re-POST with `repair` up to round 3 → honest failure message.

- [ ] **Step 1: Extend the mode state (js/ai-chat.js:7-17)**

Replace the boolean getter/setter with a three-value accessor, keeping back-compat:

```js
      const LS_KEY_AIMODE = 'md_ai_mode';   // 'fast' | 'anvil' | 'web'
      // …
        get aiMode() {
          const v = localStorage.getItem(LS_KEY_AIMODE);
          return v === 'anvil' || v === 'web' ? v : 'fast';
        },
        set aiMode(v) { localStorage.setItem(LS_KEY_AIMODE, v); },
        get anvilMode() { return this.aiMode === 'anvil'; },   // existing callers keep working
```

Update the settings UI that toggles fast/anvil (grep `anvilMode` in ai-chat.js and index.html) to a three-way choice; render the «Web» option **only when** `state.user && state.user.is_admin`, and only in python/r/duckdb editor modes (reuse the existing `activeEditorMode` check pattern; in microdata mode fall back to `'fast'`).

- [ ] **Step 2: Add the Web request path**

Next to the existing kode-svar fetch (`js/ai-chat.js:597`), add a `runWebAnswer(question)` that POSTs `/api/data-svar` and renders the SSE events:

```js
      async function runWebAnswer(question, repair, round) {
        const t0 = Date.now();
        const bubble = appendAssistantBubble();          // reuse existing bubble helper
        const progressBox = document.createElement('div');
        progressBox.className = 'ai-progress';
        bubble.appendChild(progressBox);
        let markdown = '';
        let sources = null;
        const resp = await fetch('/api/data-svar', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + getAuthToken() },
          body: JSON.stringify({
            question: question,
            mode: activeEditorMode,                       // 'python' | 'r' | 'duckdb'
            script: getEditorScript(),                    // existing helper for editor content
            repair: repair ? { script: repair.script, error: repair.error, round: round } : undefined,
          }),
        });
        if (!resp.ok) throw new Error('data-svar ' + resp.status);
        await consumeSse(resp, function onEvent(ev) {     // reuse the existing SSE reader pattern
          if (ev.type === 'progress') {
            const line = document.createElement('div');
            line.textContent = '⏳ ' + ev.text;
            progressBox.appendChild(line);
          } else if (ev.type === 'text') {
            markdown += ev.text;
            renderMarkdownInto(bubble, markdown);         // existing live renderer
          } else if (ev.type === 'sources') {
            sources = ev.sources;
          } else if (ev.type === 'error') {
            throw new Error(ev.message || 'ukjent feil');
          }
        });
        if (sources && sources.length) {
          const list = document.createElement('div');
          list.className = 'ai-sources';
          list.innerHTML = '<b>Kilder:</b> ' + sources.map(function (s) {
            return (s.ok ? '✅ ' : '⚠️ ') + '<a href="' + s.url + '" target="_blank" rel="noopener">'
              + s.url.replace(/^https?:\/\//, '').slice(0, 60) + '</a>' + (s.viaProxy ? ' (via proxy)' : '');
          }).join(' · ');
          bubble.appendChild(list);
        }
        return { markdown: markdown, latency: Date.now() - t0 };
      }
```

Adapt helper names (`appendAssistantBubble`, `consumeSse`, `renderMarkdownInto`, `getAuthToken`, `getEditorScript`) to the actual functions in ai-chat.js — every one has an existing equivalent in the kode-svar/v2 paths (`js/ai-chat.js:577-830`); read that region and reuse, do not duplicate.

- [ ] **Step 3: Auto-run + repair loop (max 3 rounds)**

After a successful `runWebAnswer`, extract the script block (reuse the v2 extraction helper around `js/ai-chat.js:690`), insert into the editor, then:

```js
      async function webAnswerWithRepair(question) {
        let round = 0, lastError = null, script = null;
        let result = await runWebAnswer(question, null, 0);
        while (true) {
          script = extractScriptBlock(result.markdown);   // existing helper
          if (!script) return;                            // prose answer (e.g. honest "fant ikke data")
          insertScriptIntoEditor(script);                 // existing helper
          try {
            lastError = await runScriptAndCaptureError(); // Step 4
            if (!lastError) return;                       // success
          } catch (e) { lastError = String(e); }
          round++;
          if (round > 3) {
            appendAssistantText(null,
              'Kunne ikke få scriptet til å kjøre etter 3 reparasjonsrunder. Siste feil:\n\n```\n'
              + lastError + '\n```\nScriptet står i editoren — juster gjerne manuelt.', {});
            return;
          }
          appendAssistantText(null, '⚙️ Reparasjonsrunde ' + round + ' — retter: ' + String(lastError).slice(0, 120), {});
          result = await runWebAnswer(question, { script: script, error: lastError }, round);
        }
      }
```

- [ ] **Step 4: `runScriptAndCaptureError`**

The editor's run path already surfaces errors into the output pane. Implement by invoking the same function the Kjør button calls (grep for the button's click handler in index.html; it dispatches on `activeEditorMode`) and capturing: resolve `null` on success, the error text on failure. If the run path only renders errors to DOM, capture by inspecting the output container for `.error` after the run promise settles — acceptable v1, note it in a comment.

- [ ] **Step 5: Manual end-to-end check**

With `netlify dev`, logged in as admin, python mode, AI mode «Web», ask: *«Hvordan har arbeidsledigheten i Norge utviklet seg siden 2010, og skiller Oslo seg fra resten av landet?»*

Expected: progress lines (SSB search → metadata → probe) stream in; answer with explanation + script with `# connect`/`# load` lines; sources listed with ✅; script auto-inserted and auto-run; on runtime error an automatic repair round fires (observe in the chat); final result shows table/figure. Also verify: logged in as non-admin (or logged out) the «Web» option is not rendered, and a hand-crafted `curl` POST to `/api/data-svar` without admin gets 403.

- [ ] **Step 6: Commit**

```bash
git add js/ai-chat.js index.html
git commit -m "feat(web-svar): Web AI mode — admin-only toggle, SSE progress/sources UI, auto-run with 3-round repair"
```

---

### Task 14: Eval set, docs, cross-repo note

**Files:**
- Create: `docs/eval/data-svar-evalsett.md`
- Modify: `netlify/edge-functions/README.md` (document the two new endpoints)
- Modify: `../safepy/docs/plan-integration.md` (D1 note — separate commit in the safepy repo)

- [ ] **Step 1: Write `docs/eval/data-svar-evalsett.md`**

```markdown
# Evalsett for data-svar (Web-modus)

Kjøres manuelt/halvautomatisk FØR hver promptendring deployes (spec §7).
Per spørsmål: kjør i angitt modus med AI-modus «Web», og sjekk kriteriene.

Kriterier (alle må holde):
1. Minst én kilde er probe-verifisert (✅ i kildelista) og reell (åpne URL-en).
2. Scriptet kjører (evt. etter ≤3 auto-reparasjoner).
3. connect/load-direktiver brukes for datainnlasting (ikke ad-hoc requests-kode
   for GET-bare uttrekk).
4. Svaret skiller beskrivelse fra årsak, og oppgir antakelser ved kausale metoder.
5. Ingen fabrikerte tabell-ID-er/kolonner (sjekk mot probe-loggen i progresslinjene).

| # | Modus | Spørsmål | Forventet kilde(r) |
|---|-------|----------|--------------------|
| 1 | python | Hvordan har arbeidsledigheten i Norge utviklet seg siden 2010? | SSB |
| 2 | python | Er det en sammenheng mellom BNP per innbygger og CO₂-utslipp per land? | OWID/Verdensbanken (flerkilde-join på landkode) |
| 3 | r | Hvordan har boligprisene i Norge utviklet seg sammenlignet med lønningene? | SSB (to tabeller, join på år) |
| 4 | duckdb | Hvilke kommuner har høyest andel eldre, og hvordan har det endret seg siste 10 år? | SSB |
| 5 | python | Påvirket pandemien sysselsettingen ulikt i ulike næringer? (event study-aktig) | SSB |
| 6 | python | Hvordan er USAs arbeidsledighet nå sammenlignet med før finanskrisen? | FRED (nøkkel via proxy) |
| 7 | r | Hvor mye har vaksinasjonsdekningen for meslinger endret seg globalt? | WHO GHO |
| 8 | python | Finn en åpen CSV om drivstoffpriser i Norge og vis utviklingen. | web_search + probe (datanorge/funnet kilde) |
| 9 | duckdb | Sammenlign renta i Norge og eurosonen siste 5 år. | Norges Bank + ECB/Eurostat (flerkilde) |
| 10 | python | Hva vet vi om effekten av kontantstøtte på mødres yrkesdeltakelse? | ærlighets-test: identifikasjon er vanskelig — svaret skal si det, og evt. vise deskriptiv utvikling med forbehold |
| 11 | python | Har kommuner som skiftet ordførerparti ved valget i 2023 hatt annerledes utvikling i ledighet? | SSB (utfall) + Wikipedia/transkribert lim-tabell for partiskifte (nivå 2 i datatilfangst-stigen, med kilde-URL) |

Resultatlogg (dato, #, PASS/FAIL, notat) føres nederst; feilmønstre omsettes
til promptregler i _lib/data-svar-prompt.ts eller quirks i data-sources.json.

## Resultatlogg
| Dato | # | Resultat | Notat |
|------|---|----------|-------|
```

- [ ] **Step 2: Run the eval set once, log results, fix the worst failures**

Run all 10 questions per the doc; append the log rows. Promote at least the recurring failure patterns into prompt-block edits (Task 9 file) or registry quirks — then re-run the affected questions. Prompt edits require the `_lib/data-svar-prompt.test.ts` suite to stay green.

- [ ] **Step 3: Document the endpoints in `netlify/edge-functions/README.md`**

Add to the endpoint list at the top:

```markdown
- `data-svar` → `/api/data-svar` — Web-modus (kun admin): agentisk tool-loop
  (search_catalog/table_metadata/probe + web_search) som finner åpne data og
  genererer python/r/duckdb-script med connect/load-direktiver. SSE-events:
  progress/text/sources/done/error. Prompt-kilde: `prompts/data-svar.md`;
  register: `data/data-sources.json`; evalsett: `docs/eval/data-svar-evalsett.md`.
- `hent` → `/api/hent?url=…[&body=…]` — SSRF-herdet GET-proxy (kun admin).
  Injiserer API-nøkler server-side for register-kilder (host-matchet);
  `body` GET-innpakker POST-json (PxWeb v1 o.l.).
```

And under env vars: `FRED_API_KEY` (optional), `DATA_SVAR_MODEL` (optional override).

- [ ] **Step 4: Commit (m2py)**

```bash
git add docs/eval/data-svar-evalsett.md netlify/edge-functions/README.md
git commit -m "docs(web-svar): eval set + endpoint docs"
```

- [ ] **Step 5: Cross-repo note in safepy (separate commit, safepy repo, dev branch)**

In `../safepy/docs/plan-integration.md`, D1 section, append one paragraph:

```markdown
Web-modus (m2py, 2026-07-03) utvider deklarasjonsflaten med to nye verb for
åpne kilder: `# connect <base|register-id> as alias` (kilde) og
`# load <url|alias/sti> as navn` (uttrekk, hel ramme). `# require <url>`
består som legacy-alias for uttrekk; navngitte requires (server-ruting) og
microdata-modusens require/import er uendret. Design:
m2py/docs/superpowers/specs/2026-07-03-web-data-svar-design.md.
```

```bash
cd ../safepy && git add docs/plan-integration.md && git commit -m "docs: note connect/load web-directive verbs added to the D1 declaration surface (m2py web mode)"
```

---

## Self-Review Notes (already applied)

- Spec coverage: all spec sections map to tasks — registry+keys (T1, T4), SSRF+proxy+POST-wrap (T2, T4), admin gating both endpoints (T3, T4, T10), tools incl. variable-level metadata (T5–T7), tool loop + budget + honest degradation (T8), prompt blocks incl. science core, delivery, multi-source merge, per-mode rules + prompt dev loop (T9, T14), endpoint + deterministic source manifest (T10), connect/load/legacy-require parsing (T11), loader extensions 1–3: content-type detection (T12 `sniffFormat`), dialect materialization (T12), POST-wrap (T4+T11 `/api/hent?…&body=…`), Web UI + auto-repair 3 rounds (T13), eval set + registry-quirk routine + D1 note (T14).
- Deliberately out of scope (matches spec): Eurostat/OECD/SDMX search adapters (reachable via web_search+probe; `search_catalog` throws a guiding error), non-admin rollout, probe/catalog caching, R parquet.
- Type consistency: `DataSource`/`CatalogHit`/`TableMeta`/`ProbeResult`/`AgenticOptions` names match across tasks; `viaProxy` naming consistent from probe → manifest → resolver.
- Known judgment calls documented inline: hostname-only SSRF (T2 comment), non-streaming final turn (T8), DOM-based error capture fallback (T13 Step 4).
- Datatilfangst-stigen (spec §5d): INLINE prompt block + hosted web_fetch (T9), Wikipedia registry entry with read_html recipe (T1), html format binding in all runners (T12), eval question 11 (T14).
- index.html footprint deliberately minimal: parsing in `js/data-directives.js` (T11), fetch/format/proxy in `js/data-loader.js` (T12); index.html gets only two script includes + three ~10-line runtime-binding hooks (FS write + read call per mode) — those must live there because they touch the pyodide/webr/duckdb instances the runners own.




