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
  if (host.includes(":")) return false; // IPv6 literals: reject
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
  const initialHost = new URL(rawUrl).host;
  for (let hop = 0; hop <= maxRedirects; hop++) {
    if (!isPublicHttpUrl(url)) throw new Error(`blokkert URL (ikke offentlig http/https): ${url}`);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    // Auth/credential headers (e.g. a header-injected API key) must never be
    // replayed to a host other than the one the caller originally targeted —
    // a redirect to a foreign host must not receive them.
    const sameHost = new URL(url).host === initialHost;
    try {
      const resp = await fetchImpl(url, {
        method: opts.method ?? "GET",
        body: opts.body,
        headers: sameHost ? opts.headers : {},
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
