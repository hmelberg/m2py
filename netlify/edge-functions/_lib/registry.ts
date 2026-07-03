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
