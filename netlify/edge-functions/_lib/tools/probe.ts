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
