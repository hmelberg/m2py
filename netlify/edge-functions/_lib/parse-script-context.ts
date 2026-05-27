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

const DIRECTIVES = new Set([
  "revider-script",
]);

const TRUE_VALUES = new Set(["ja", "yes", "true", "1", "på", "on"]);
const FALSE_VALUES = new Set(["nei", "no", "false", "0", "av", "off"]);

export interface ScriptDirectives {
  revider_script?: boolean;
}

function parseBoolean(value: string): boolean | undefined {
  const v = value.trim().toLowerCase();
  if (TRUE_VALUES.has(v)) return true;
  if (FALSE_VALUES.has(v)) return false;
  return undefined;
}

function classifyDirective(raw: string, directives: ScriptDirectives): void {
  const m = raw.match(/^([^:]+):\s*(.+)$/);
  if (!m) return;
  const name = m[1].trim().toLowerCase();
  const value = m[2].trim();
  if (!DIRECTIVES.has(name)) return;
  if (name === "revider-script") {
    const b = parseBoolean(value);
    if (b !== undefined) directives.revider_script = b;
  }
}

export function parsePersonvernDirectives(script: string): ScriptDirectives {
  const directives: ScriptDirectives = {};
  const lines = script.split(/\r?\n/);
  let inBlock = false;

  for (const line of lines) {
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
        // fall through
      } else {
        const m = line.match(BLOCK_INNER_RE);
        if (m && m[1].trim()) {
          classifyDirective(m[1], directives);
        }
        continue;
      }
    }

    const single = line.match(SINGLE_LINE_RE);
    if (single) {
      classifyDirective(single[1], directives);
    }
  }

  return directives;
}

export type Language = "microdata" | "python" | "r" | "mixed";

const MICRODATA_PATTERNS = [
  /^\s*import\s+(all\s+)?(variables?\s+)?[^\n]*[ \t]from[ \t]+\w+/im,
  /\bcollapse\s*\(\s*(mean|sum|sd|count|median|min|max|p\d+)/i,
  /^\s*tabulate\s+\w+/im,
  /^\s*summarize\s+\w+/im,
  /^\s*keep\s+if\s+/im,
  /^\s*drop\s+if\s+/im,
  // m2py merge: "merge VAR into DATASET on KEY" — NOT Stata's "merge 1:m using"
  /^\s*merge\s+\w+\s+(into|onto)\s+/im,
];

const PYTHON_PATTERNS = [
  /^\s*from\s+\w+\s+import\s+/m,
  /^\s*import\s+\w+(\s+as\s+\w+)?$/m,
  /^\s*def\s+\w+\s*\(/m,
  /^\s*class\s+\w+/m,
  /\bpd\.|np\.|pandas|numpy\b/i,
];

const R_PATTERNS = [
  /^\s*library\s*\(/m,
  /<-\s*[a-zA-Z0-9_(]/,
  /\bdata\.frame\b/,
  /%>%/,
  /^\s*require\s*\(/m,
];

function countMatches(script: string, patterns: RegExp[]): number {
  let n = 0;
  for (const p of patterns) if (p.test(script)) n++;
  return n;
}

/**
 * Detects the scripting language of a script.
 *
 * Thresholds are asymmetric by design:
 *   - Microdata: ≥1 pattern match (microdata keywords are domain-specific and rarely appear by accident)
 *   - Python/R:  ≥2 pattern matches to avoid single-token false positives (e.g. a lone `<-` or `def`)
 * Empty/whitespace-only input defaults to "microdata".
 * When Python and R scores are equal (tie), "python" is returned.
 */
export function detectLanguage(script: string): Language {
  if (!script.trim()) return "microdata";

  const microdataScore = countMatches(script, MICRODATA_PATTERNS);
  const pythonScore = countMatches(script, PYTHON_PATTERNS);
  const rScore = countMatches(script, R_PATTERNS);

  const hasMicrodata = microdataScore >= 1;
  const hasPython = pythonScore >= 2;
  const hasR = rScore >= 2;

  if (hasMicrodata && (hasPython || hasR)) return "mixed";
  if (hasMicrodata) return "microdata";
  if (hasPython && !hasR) return "python";
  if (hasR && !hasPython) return "r";
  if (hasPython && hasR) return pythonScore >= rScore ? "python" : "r";
  return "microdata";
}
