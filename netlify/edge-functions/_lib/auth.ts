// Shared request gate for the AI edge functions (kode-svar, dm-vurder,
// tolk-resultat). Consolidates what was ~40 lines of copy-pasted auth /
// rate-limit / body-guard logic in each handler, and fixes several issues the
// duplicated version had:
//   - rate-limit runs BEFORE the (network) Anvil validation, so an attacker
//     can no longer amplify requests against the free-tier Anvil app;
//   - the shared-token comparison is constant-time;
//   - the Anvil call has a timeout (no hung isolates);
//   - positive validations are cached briefly in-isolate (fewer Anvil calls);
//   - the spoofable x-forwarded-for fallback for the client IP is dropped
//     (only the platform-set x-nf-client-connection-ip is trusted).
import { checkRateLimit as defaultCheckRateLimit } from "./rate-limit.ts";

const ANVIL_DEFAULT_URL = "https://mdataapi.anvil.app/_/api/auth/me";
const AUTH_CACHE_TTL_MS = 5 * 60 * 1000; // positive-validation cache lifetime
const ANVIL_TIMEOUT_MS = 4000;

// In-isolate positive-auth cache: token -> expiry epoch ms. Deliberately not
// persisted (no token material written to Blobs); a cold isolate just
// re-validates. A revoked token keeps working for at most AUTH_CACHE_TTL_MS.
const _authCache = new Map<string, number>();

/** Constant-time string comparison (no early return on first mismatch). */
export function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  const len = Math.max(ab.length, bb.length);
  let diff = ab.length ^ bb.length;
  for (let i = 0; i < len; i++) {
    diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  }
  return diff === 0;
}

/**
 * Client IP for rate limiting. On Netlify, x-nf-client-connection-ip is set by
 * the platform and cannot be forged by the client; x-forwarded-for can, so we
 * do NOT fall back to it (that fallback let a client spoof its IP to dodge the
 * per-IP limit).
 */
export function clientIp(request: Request): string {
  return request.headers.get("x-nf-client-connection-ip") ?? "";
}

/**
 * BYOK: user-supplied Anthropic key from the X-Anthropic-Key header. Only a
 * well-formed key (sk-ant-…, sane charset, ≤250 chars) counts; anything else
 * is treated as absent so the normal token path (and its 401) applies.
 * The value must never be logged or cached.
 */
export function extractByokKey(request: Request): string | null {
  const raw = (request.headers.get("x-anthropic-key") ?? "").trim();
  if (raw.length === 0 || raw.length > 250) return null;
  return /^sk-ant-[A-Za-z0-9_-]+$/.test(raw) ? raw : null;
}

/**
 * Map an upstream Anthropic failure to a client response. With BYOK, a 401
 * from Anthropic means the user's own key is invalid — surface that directly
 * instead of a generic 502 (the anthropic.ts helpers throw
 * `Error("Anthropic API error <status>")`).
 */
export function upstreamErrorResponse(e: unknown, byokKey: string | null): Response {
  if (byokKey && String(e).includes("Anthropic API error 401")) {
    return new Response("Ugyldig Anthropic-nøkkel", { status: 401 });
  }
  return new Response(`Upstream error: ${e}`, { status: 502 });
}

export interface GateOptions {
  endpoint: string;
  maxBodyBytes: number;
  allowedMethods?: string[];
  /**
   * Accept a well-formed X-Anthropic-Key in place of token/admin auth — only
   * for endpoints that forward the key to Anthropic, which validates it.
   * Never set this on endpoints that don't consume the key (they would
   * become effectively anonymous).
   */
  allowByok?: boolean;
}

export interface GateDeps {
  sharedToken?: string;
  checkRateLimit: (
    endpoint: string,
    ip: string,
  ) => Promise<{ allowed: boolean; retryAfterSeconds: number }>;
  validateToken: (token: string) => Promise<boolean>;
  now: () => number;
  cache: Map<string, number>;
}

interface BaseCheckResult {
  presentedToken: string;
  failure: Response | null;
}

/**
 * Steps 1-4 shared by runGate and runAdminGate: token presence, method check,
 * content-length cap, and rate limit (in that order, before any expensive
 * validation). Returns the extracted token plus a short-circuit Response when
 * one of the checks fails, or `failure: null` when the caller should proceed
 * to its own auth step.
 */
async function runBaseChecks(
  request: Request,
  opts: GateOptions,
  checkRateLimit: GateDeps["checkRateLimit"],
  requireToken = true,
): Promise<BaseCheckResult> {
  // 1. token presence (free) — skipped for BYOK requests, which carry the
  // user's own Anthropic key instead of an account token.
  const authHeader = request.headers.get("authorization") ?? "";
  const presentedToken = authHeader.startsWith("Bearer ")
    ? authHeader.slice(7).trim()
    : "";
  if (!presentedToken && requireToken) {
    return {
      presentedToken,
      failure: new Response("Unauthorized: missing token", { status: 401 }),
    };
  }

  // 2. method (free)
  const allowed = opts.allowedMethods ?? ["POST"];
  if (!allowed.includes(request.method)) {
    return {
      presentedToken,
      failure: new Response("Method not allowed", { status: 405 }),
    };
  }

  // 3. content-length guard (free)
  const contentLength = parseInt(
    request.headers.get("content-length") ?? "0",
    10,
  );
  if (contentLength > opts.maxBodyBytes) {
    return {
      presentedToken,
      failure: new Response("Payload too large", { status: 413 }),
    };
  }

  // 4. rate-limit BEFORE the expensive Anvil validation (no amplification)
  const rate = await checkRateLimit(opts.endpoint, clientIp(request));
  if (!rate.allowed) {
    return {
      presentedToken,
      failure: new Response("Rate limited", {
        status: 429,
        headers: { "Retry-After": String(rate.retryAfterSeconds) },
      }),
    };
  }

  return { presentedToken, failure: null };
}

/**
 * Core gate logic with injected dependencies (testable). Returns a Response to
 * short-circuit the request, or null when the caller should proceed.
 */
export async function runGate(
  request: Request,
  opts: GateOptions,
  deps: GateDeps,
): Promise<Response | null> {
  const byokKey = opts.allowByok ? extractByokKey(request) : null;
  const { presentedToken, failure } = await runBaseChecks(
    request,
    opts,
    deps.checkRateLimit,
    /* requireToken */ byokKey === null,
  );
  if (failure) return failure;

  // BYOK: the user's own Anthropic key replaces account auth. Method, body
  // and rate-limit checks above still ran; the handler uses the key upstream.
  // Deliberate server-side precedence: when both a valid BYOK header and a
  // Bearer token are present, BYOK wins and the token is never validated.
  if (byokKey !== null) return null;

  // 5. auth: cheap shared-token (constant-time) -> positive cache -> Anvil
  const now = deps.now();
  let authenticated = false;
  if (deps.sharedToken && timingSafeEqual(presentedToken, deps.sharedToken)) {
    authenticated = true;
  }
  if (!authenticated) {
    const exp = deps.cache.get(presentedToken);
    if (exp && exp > now) authenticated = true;
    else if (exp) deps.cache.delete(presentedToken);
  }
  if (!authenticated && await deps.validateToken(presentedToken)) {
    authenticated = true;
    deps.cache.set(presentedToken, now + AUTH_CACHE_TTL_MS);
  }
  if (!authenticated) {
    return new Response("Unauthorized", { status: 401 });
  }

  return null;
}

/** Build an Anvil /auth/me validator with an abort timeout. */
export function makeAnvilValidator(
  anvilUrl: string,
  timeoutMs: number = ANVIL_TIMEOUT_MS,
  fetchImpl: typeof fetch = fetch,
): (token: string) => Promise<boolean> {
  return async (token: string): Promise<boolean> => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const resp = await fetchImpl(anvilUrl, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` },
        signal: ctrl.signal,
      });
      if (!resp.ok) return false;
      const data = await resp.json();
      // /auth/me returns { principal_kind, user, ... }. Accept any successful
      // response — Anvil's whitelist gates who can log in.
      return !!(data &&
        (data.user || data.principal_kind === "service_token" ||
          data.principal_kind === "anonymous"));
    } catch (_e) {
      // network error / timeout -> treat as unauthorized rather than crashing
      return false;
    } finally {
      clearTimeout(timer);
    }
  };
}

/** Env-wired gate used by the handlers. */
export function gate(request: Request, opts: GateOptions): Promise<Response | null> {
  const anvilUrl = Deno.env.get("M2PY_ANVIL_VALIDATE_URL") ?? ANVIL_DEFAULT_URL;
  return runGate(request, opts, {
    sharedToken: Deno.env.get("M2PY_ACCESS_TOKEN") ?? undefined,
    checkRateLimit: defaultCheckRateLimit,
    validateToken: makeAnvilValidator(anvilUrl),
    now: () => Date.now(),
    cache: _authCache,
  });
}

export interface UserInfo {
  ok: boolean;
  isAdmin: boolean;
}

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
  const byokKey = opts.allowByok ? extractByokKey(request) : null;
  const { presentedToken, failure } = await runBaseChecks(
    request,
    opts,
    deps.checkRateLimit,
    /* requireToken */ byokKey === null,
  );
  if (failure) return failure;

  // BYOK: the user's own Anthropic key replaces account auth. Method, body
  // and rate-limit checks above still ran; the handler uses the key upstream.
  if (byokKey !== null) return null;

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
