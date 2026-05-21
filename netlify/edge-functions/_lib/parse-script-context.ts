const KNOWN_FIELDS = new Set([
  "formål",
  "sentrale variabler",
  "tidsperiode",
  "geografi",
  "sensitive grupper",
  "alternativer vurdert",
]);

const BLOCK_START_RE = /^\s*(?:\/\/+|#+)\s*personvern\s+blokk\s+start\s*$/i;
const BLOCK_END_RE = /^\s*(?:\/\/+|#+)\s*personvern\s+blokk\s+slutt\s*$/i;
const SINGLE_LINE_RE = /^\s*(?:\/\/+|#+)\s*personvern\s*:\s*(.*)$/i;
const BLOCK_INNER_RE = /^\s*(?:\/\/+|#+)\s*(.*)$/;
const NONCOMMENT_RE = /^\s*[^/#\s]/;

export interface ScriptContext {
  structured: Record<string, string>;
  freetext: { line: number; text: string }[];
  hasAny: boolean;
}

function classifyAndStore(
  raw: string,
  lineNumber: number,
  ctx: ScriptContext,
): void {
  const m = raw.match(/^([^:]+):\s*(.+)$/);
  if (m) {
    const field = m[1].trim().toLowerCase();
    const value = m[2].trim();
    if (KNOWN_FIELDS.has(field)) {
      ctx.structured[field] = value;
      ctx.hasAny = true;
      return;
    }
  }
  ctx.freetext.push({ line: lineNumber, text: raw.trim() });
  ctx.hasAny = true;
}

export function parsePersonvernComments(script: string): ScriptContext {
  const ctx: ScriptContext = { structured: {}, freetext: [], hasAny: false };
  const lines = script.split(/\r?\n/);
  let inBlock = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNo = i + 1;

    if (BLOCK_START_RE.test(line)) {
      inBlock = true;
      continue;
    }
    if (inBlock && BLOCK_END_RE.test(line)) {
      inBlock = false;
      continue;
    }
    if (inBlock) {
      if (NONCOMMENT_RE.test(line)) {
        inBlock = false;
        // fall through to normal parsing of this line
      } else {
        const m = line.match(BLOCK_INNER_RE);
        if (m && m[1].trim()) {
          classifyAndStore(m[1], lineNo, ctx);
        }
        continue;
      }
    }

    const single = line.match(SINGLE_LINE_RE);
    if (single) {
      classifyAndStore(single[1], lineNo, ctx);
    }
  }

  return ctx;
}
