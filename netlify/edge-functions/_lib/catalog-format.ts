// Pure catalog-field formatters shared by the v1 prompt builder (kode-svar.ts)
// and the v2 variable picker (variable-picker.ts). No Netlify/auth deps so the
// tests stay fast and run under `deno test --allow-all _lib/`.

// "Numerisk (heltall)"/"Numerisk (desimaltall)" → "num"; "Alfanumerisk" → "alfa".
export function abbrevType(microdataDatatype: string, dataType: string): string {
  const mdt = (microdataDatatype || "").toLowerCase();
  let cls = "";
  if (mdt.startsWith("alfa")) cls = "alfa";
  else if (mdt.startsWith("num")) cls = "num";
  else cls = (microdataDatatype || dataType || "").trim();
  const dt = (dataType || "").toLowerCase();
  if (dt.startsWith("date")) return `${cls || "num"}·${dataType}`;
  return cls || dataType;
}

// Returns "2015-02-16…2025-02-16" (annual grid), "2011-01-01…2017-12-31"
// (free Forløp window), "1993–2023"/"1993–" (coarse year span), or "".
export function extractValidPeriod(description: string, temporalitet = ""): string {
  const full = (description || "").match(
    /Gyldighetsperiode:\s*(\d{4})-(\d{2}-\d{2})\s*[–—-]\s*(\d{4})-(\d{2}-\d{2})/i,
  );
  if (full) {
    const [, startYear, startMD, endYear, endMD] = full;
    const temp = temporalitet.toLowerCase();
    if (temp === "tverrsnitt") {
      return `${startYear}-${startMD}…${endYear}-${startMD}`;
    }
    if (temp === "akkumulert") {
      return `${startYear}-${endMD}…${endYear}-${endMD}`;
    }
    return `${startYear}-${startMD}…${endYear}-${endMD}`;
  }
  const m = (description || "").match(/Gyldighetsperiode:\s*([0-9]{4})[^.]*?(?:[–—-]\s*([0-9]{4}))?/i);
  if (!m) return "";
  const start = m[1];
  const end = m[2];
  if ((description || "").includes("Gyldighetsperiode") && /∞/.test(description) && !end) {
    return `${start}–`;
  }
  if (start && end) return `${start}–${end}`;
  if (start) return `${start}–`;
  return "";
}

// Strip the structured boilerplate tail so only the human description remains.
export function cleanDescription(description: string, shortTitle: string): string {
  let d = (description || "").trim();
  const cut = d.search(/\s*(Enhetstype:|Temporalitet:|Gyldighetsperiode:)/i);
  if (cut >= 0) d = d.slice(0, cut).trim();
  d = d.replace(/\s+/g, " ").trim();
  if (!d) d = (shortTitle || "").trim();
  if (d.length > 200) d = d.slice(0, 197) + "...";
  return d;
}

// Inline enum labels. Show up to LABEL_SHOW codes (empirically almost every
// catalog variable has ≤30, so most show in full); beyond that, show the first
// LABEL_SHOW and summarise the remainder with a count. Even a partial sample
// anchors the stored code FORMAT (string vs numeric, leading zeros, dotted
// hierarchy), which is what the model most often lacks. (v2's focused block
// uses its own larger-budget renderer for picked variables.)
const LABEL_SHOW = 30;
export function renderLabels(labels: unknown): string {
  if (!labels || typeof labels !== "object") return "";
  const entries = Object.entries(labels as Record<string, unknown>);
  if (entries.length === 0) return "";
  const shown = entries.slice(0, LABEL_SHOW).map(([k, val]) => `${k}=${String(val)}`);
  const extra = entries.length - shown.length;
  const tail = extra > 0 ? `, …(+${extra} flere)` : "";
  return ` {${shown.join(", ")}${tail}}`;
}
