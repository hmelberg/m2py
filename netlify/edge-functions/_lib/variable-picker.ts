import { abbrevType, cleanDescription, extractValidPeriod } from "./catalog-format.ts";

export interface CatalogMeta {
  variables?: Record<string, Record<string, unknown>>;
}

// Extract a JSON array of strings from the picker reply. The reply may be a
// bare array, fenced (```json ... ```), or wrapped in prose. We scan for the
// first '[' ... matching ']' and JSON.parse it; anything else → [].
export function parsePickerResponse(text: string): string[] {
  if (!text) return [];
  const start = text.indexOf("[");
  if (start < 0) return [];
  let depth = 0, end = -1, instr = false, esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (instr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') instr = false;
    } else if (ch === '"') instr = true;
    else if (ch === "[") depth++;
    else if (ch === "]") { depth--; if (depth === 0) { end = i; break; } }
  }
  if (end < 0) return [];
  try {
    const arr = JSON.parse(text.slice(start, end + 1));
    if (!Array.isArray(arr)) return [];
    return arr.filter((x): x is string => typeof x === "string").map((s) => s.trim()).filter(Boolean);
  } catch {
    return [];
  }
}

// Keep only names that exist in the catalog, preserving order, de-duplicated,
// capped at `cap`. This is the grounding step: hallucinated names are dropped.
export function groundNames(names: string[], meta: CatalogMeta, cap = 20): string[] {
  const variables = meta?.variables ?? {};
  const seen = new Set<string>();
  const out: string[] = [];
  for (const name of names) {
    if (!Object.prototype.hasOwnProperty.call(variables, name)) continue;
    if (seen.has(name)) continue;
    seen.add(name);
    out.push(name);
    if (out.length >= cap) break;
  }
  return out;
}

function tagFor(v: Record<string, unknown>): string {
  const dataType = String(v.data_type ?? "");
  const mdt = String(v.microdata_datatype ?? "");
  const temp = String(v.temporalitet ?? "");
  const ehtp = String(v.enhetstype ?? "");
  const period = extractValidPeriod(String(v.description ?? ""), temp);
  const parts = [abbrevType(mdt, dataType), temp, ehtp];
  if (period) parts.push(period);
  return `[${parts.filter(Boolean).join(", ")}]`;
}

// Compact catalog for the picker model: one line per variable, grouped by bank.
// Enough signal (name, tag, short description) to judge relevance; cheap enough
// to send as a stable, cacheable system block.
export function renderNameList(meta: CatalogMeta): string {
  const variables = meta?.variables ?? {};
  const lines: string[] = [
    "## Variabelliste (velg fra disse navnene)",
    "",
    "Hver linje: `NAVN [type, temporalitet, enhetstype, gyldig-datoer] — kort beskrivelse`.",
    "",
  ];
  const names = Object.keys(variables).sort((a, b) => a.localeCompare(b));
  for (const name of names) {
    const v = variables[name];
    const text = cleanDescription(String(v.description ?? ""), String(v.short_title ?? ""));
    lines.push(text ? `- \`${name}\` ${tagFor(v)} — ${text}` : `- \`${name}\` ${tagFor(v)}`);
  }
  return lines.join("\n");
}

// Larger-budget label rendering for a single picked variable. Shows up to
// FOCUS_CAP codes (the focused block can afford fuller codelists than the
// prefix catalog), summarising any remainder with a count.
const FOCUS_CAP = 200;
function renderEntriesCapped(entries: Array<[string, unknown]>): string {
  if (entries.length === 0) return "";
  const shown = entries.slice(0, FOCUS_CAP).map(([k, val]) => `${k}=${String(val)}`);
  const extra = entries.length - shown.length;
  const tail = extra > 0 ? `, …(+${extra} flere)` : "";
  return ` {${shown.join(", ")}${tail}}`;
}

function renderLabelsFull(labels: unknown): string {
  if (!labels || typeof labels !== "object") return "";
  return renderEntriesCapped(Object.entries(labels as Record<string, unknown>));
}

// Optional per-variable codelists fetched on demand (from /codelists/<NAME>.json),
// keyed by variable name → { code: label }. Used for big classifications
// (STYRK/NACE/…) whose codes are NOT inlined in variable_metadata.json.
export type CodelistMap = Record<string, Record<string, unknown>>;

// Rich block for the picked variables, injected at the top of the generation
// user turn. For a variable with an injected codelist, that fuller list wins
// over the (often empty) inline labels. Returns "" when there are no picks.
export function renderFocusedBlock(
  names: string[],
  meta: CatalogMeta,
  codelists: CodelistMap = {},
): string {
  const variables = meta?.variables ?? {};
  const picked = names.filter((n) => Object.prototype.hasOwnProperty.call(variables, n));
  if (picked.length === 0) return "";
  const lines: string[] = [
    "## Mest relevante variabler for dette spørsmålet",
    "",
    "Disse er valgt som mest relevante for spørsmålet (med fullstendig kodeliste).",
    "Bruk dem hvis de passer — men hele katalogen er fortsatt tilgjengelig i",
    "systemkonteksten, så velg andre variabler derfra om disse ikke dekker behovet.",
    "",
  ];
  for (const name of picked) {
    const v = variables[name];
    const text = cleanDescription(String(v.description ?? ""), String(v.short_title ?? ""));
    const cl = codelists[name];
    const labels = cl && typeof cl === "object" && Object.keys(cl).length > 0
      ? renderEntriesCapped(Object.entries(cl))
      : renderLabelsFull(v.labels);
    lines.push(text ? `- \`${name}\` ${tagFor(v)} — ${text}${labels}` : `- \`${name}\` ${tagFor(v)}${labels}`);
  }
  return lines.join("\n");
}
