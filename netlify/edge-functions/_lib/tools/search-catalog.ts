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
  // Live API quirk (verified 2026-07-03): the query param is "q" (not "query"),
  // and without filters.type the search spans concepts/informationmodels/services
  // too — restrict to datasets or hits are dominated by CONCEPT entries.
  const res = await f(src.sok_endepunkt!, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ q: query, filters: { type: { value: "datasets" } } }),
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
