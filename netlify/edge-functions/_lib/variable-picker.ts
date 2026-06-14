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
