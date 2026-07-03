import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  clientIp,
  extractByokKey,
  type GateDeps,
  runGate,
  timingSafeEqual,
  upstreamErrorResponse,
} from "./auth.ts";

function req(opts: {
  method?: string;
  token?: string;
  contentLength?: number;
  ip?: string;
  xff?: string;
  byok?: string;
} = {}): Request {
  const headers = new Headers();
  if (opts.token !== undefined) headers.set("authorization", `Bearer ${opts.token}`);
  if (opts.contentLength !== undefined) {
    headers.set("content-length", String(opts.contentLength));
  }
  if (opts.ip) headers.set("x-nf-client-connection-ip", opts.ip);
  if (opts.xff) headers.set("x-forwarded-for", opts.xff);
  if (opts.byok !== undefined) headers.set("x-anthropic-key", opts.byok);
  return new Request("https://example.test/", {
    method: opts.method ?? "POST",
    headers,
  });
}

function makeDeps(over: Partial<GateDeps> = {}): GateDeps & { calls: { validate: number } } {
  const calls = { validate: 0 };
  const deps: GateDeps & { calls: { validate: number } } = {
    sharedToken: undefined,
    checkRateLimit: () => Promise.resolve({ allowed: true, retryAfterSeconds: 0 }),
    validateToken: () => {
      calls.validate++;
      return Promise.resolve(false);
    },
    now: () => 1000,
    cache: new Map<string, number>(),
    calls,
    ...over,
  };
  return deps;
}

Deno.test("timingSafeEqual: equal strings match, different do not", () => {
  assertEquals(timingSafeEqual("secret-token", "secret-token"), true);
  assertEquals(timingSafeEqual("secret-token", "secret-tokeX"), false);
  assertEquals(timingSafeEqual("short", "longer-value"), false);
  assertEquals(timingSafeEqual("", ""), true);
});

Deno.test("clientIp: trusts x-nf-client-connection-ip, ignores x-forwarded-for", () => {
  assertEquals(clientIp(req({ ip: "1.2.3.4" })), "1.2.3.4");
  // spoofable header must NOT be used
  assertEquals(clientIp(req({ xff: "9.9.9.9" })), "");
});

Deno.test("runGate: missing token -> 401", async () => {
  const resp = await runGate(req({ token: undefined }), { endpoint: "t", maxBodyBytes: 100 }, makeDeps());
  assertEquals(resp?.status, 401);
});

Deno.test("runGate: non-POST -> 405", async () => {
  const resp = await runGate(req({ method: "GET", token: "x" }), { endpoint: "t", maxBodyBytes: 100 }, makeDeps());
  assertEquals(resp?.status, 405);
});

Deno.test("runGate: oversized content-length -> 413", async () => {
  const resp = await runGate(req({ token: "x", contentLength: 999 }), { endpoint: "t", maxBodyBytes: 100 }, makeDeps());
  assertEquals(resp?.status, 413);
});

Deno.test("runGate: rate-limited -> 429 and Anvil NOT called (no amplification)", async () => {
  const deps = makeDeps({
    checkRateLimit: () => Promise.resolve({ allowed: false, retryAfterSeconds: 42 }),
  });
  const resp = await runGate(req({ token: "x" }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp?.status, 429);
  assertEquals(resp?.headers.get("Retry-After"), "42");
  assertEquals(deps.calls.validate, 0); // rate-limit ran before validation
});

Deno.test("runGate: valid shared token proceeds without calling Anvil", async () => {
  const deps = makeDeps({ sharedToken: "shared-secret" });
  const resp = await runGate(req({ token: "shared-secret" }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp, null);
  assertEquals(deps.calls.validate, 0);
});

Deno.test("runGate: invalid token -> 401", async () => {
  const deps = makeDeps({ validateToken: () => Promise.resolve(false) });
  const resp = await runGate(req({ token: "nope" }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp?.status, 401);
});

Deno.test("runGate: positive Anvil validation is cached (second call skips Anvil)", async () => {
  const cache = new Map<string, number>();
  let validateCalls = 0;
  const deps = makeDeps({
    cache,
    validateToken: () => {
      validateCalls++;
      return Promise.resolve(true);
    },
  });
  const r1 = await runGate(req({ token: "good" }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  const r2 = await runGate(req({ token: "good" }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(r1, null);
  assertEquals(r2, null);
  assertEquals(validateCalls, 1); // second request served from cache
});

Deno.test("runGate: expired cache entry triggers re-validation", async () => {
  const cache = new Map<string, number>([["good", 500]]); // expiry 500
  let validateCalls = 0;
  const deps = makeDeps({
    cache,
    now: () => 1000, // past expiry
    validateToken: () => {
      validateCalls++;
      return Promise.resolve(true);
    },
  });
  const resp = await runGate(req({ token: "good" }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp, null);
  assertEquals(validateCalls, 1);
});

// Admin gate tests
import { makeAnvilUserFetcher, runAdminGate, type AdminGateDeps } from "./auth.ts";

function adminDeps(over: Partial<AdminGateDeps> = {}): AdminGateDeps & { calls: { fetchUser: number } } {
  const calls = { fetchUser: 0 };
  return {
    calls,
    sharedToken: undefined,
    checkRateLimit: () => Promise.resolve({ allowed: true, retryAfterSeconds: 0 }),
    fetchUser: () => { calls.fetchUser++; return Promise.resolve({ ok: true, isAdmin: true }); },
    now: () => 1_000_000,
    cache: new Map(),
    ...over,
  };
}

Deno.test("runAdminGate: admin user passes, non-admin gets 403, invalid 401", async () => {
  const opts = { endpoint: "data-svar", maxBodyBytes: 1000 };
  assertEquals(await runAdminGate(req({ token: "t1" }), opts, adminDeps()), null);
  const r403 = await runAdminGate(req({ token: "t2" }), opts,
    adminDeps({ fetchUser: () => Promise.resolve({ ok: true, isAdmin: false }) }));
  assertEquals(r403?.status, 403);
  const r401 = await runAdminGate(req({ token: "t3" }), opts,
    adminDeps({ fetchUser: () => Promise.resolve({ ok: false, isAdmin: false }) }));
  assertEquals(r401?.status, 401);
});

Deno.test("runAdminGate: shared token is admin; result cached", async () => {
  const deps = adminDeps({ sharedToken: "hemmelig" });
  const opts = { endpoint: "data-svar", maxBodyBytes: 1000 };
  assertEquals(await runAdminGate(req({ token: "hemmelig" }), opts, deps), null);
  assertEquals(deps.calls.fetchUser, 0);
  assertEquals(await runAdminGate(req({ token: "bruker" }), opts, deps), null);
  assertEquals(await runAdminGate(req({ token: "bruker" }), opts, deps), null);
  assertEquals(deps.calls.fetchUser, 1); // second hit came from cache
});

Deno.test("runAdminGate: allowedMethods lets GET through when configured", async () => {
  const opts = { endpoint: "hent", maxBodyBytes: 0, allowedMethods: ["GET"] };
  const getReq = req({ token: "t", method: "GET" });
  assertEquals(await runAdminGate(getReq, opts, adminDeps()), null);
  const postOpts = { endpoint: "hent", maxBodyBytes: 0 }; // default POST-only
  assertEquals((await runAdminGate(getReq, postOpts, adminDeps()))?.status, 405);
});

Deno.test("makeAnvilUserFetcher maps /auth/me shape", async () => {
  const mk = (payload: unknown, status = 200) =>
    makeAnvilUserFetcher("https://anvil.test/auth/me", 1000,
      (() => Promise.resolve(new Response(JSON.stringify(payload), { status }))) as typeof fetch);
  assertEquals(await mk({ user: { is_admin: true } })("t"), { ok: true, isAdmin: true });
  assertEquals(await mk({ user: { is_admin: false } })("t"), { ok: true, isAdmin: false });
  assertEquals(await mk({ user: {} })("t"), { ok: true, isAdmin: false });
  assertEquals(await mk({}, 401)("t"), { ok: false, isAdmin: false });
});

// ── BYOK: user-supplied Anthropic key ──

const GOOD_KEY = "sk-ant-api03-abc123_DEF-456";

Deno.test("extractByokKey: accepts well-formed sk-ant key", () => {
  assertEquals(extractByokKey(req({ byok: GOOD_KEY })), GOOD_KEY);
});

Deno.test("extractByokKey: trims surrounding whitespace", () => {
  assertEquals(extractByokKey(req({ byok: `  ${GOOD_KEY}  ` })), GOOD_KEY);
});

Deno.test("extractByokKey: rejects wrong prefix, bad chars, empty, absent", () => {
  assertEquals(extractByokKey(req({ byok: "sk-live-abc" })), null);
  assertEquals(extractByokKey(req({ byok: "sk-ant-abc def" })), null);
  assertEquals(extractByokKey(req({ byok: "sk-ant-abc!" })), null);
  assertEquals(extractByokKey(req({ byok: "" })), null);
  assertEquals(extractByokKey(req({})), null);
});

Deno.test("extractByokKey: rejects keys longer than 250 chars", () => {
  const long = "sk-ant-" + "a".repeat(244); // total 251
  assertEquals(extractByokKey(req({ byok: long })), null);
  const ok = "sk-ant-" + "a".repeat(243); // total 250
  assertEquals(extractByokKey(req({ byok: ok })), ok);
});

Deno.test("upstreamErrorResponse: BYOK + Anthropic 401 -> 401 Ugyldig", async () => {
  const resp = upstreamErrorResponse(new Error("Anthropic API error 401"), GOOD_KEY);
  assertEquals(resp.status, 401);
  assertEquals(await resp.text(), "Ugyldig Anthropic-nøkkel");
});

Deno.test("upstreamErrorResponse: BYOK + other error -> 502", () => {
  assertEquals(upstreamErrorResponse(new Error("Anthropic API error 529"), GOOD_KEY).status, 502);
});

Deno.test("upstreamErrorResponse: no BYOK -> always 502", () => {
  assertEquals(upstreamErrorResponse(new Error("Anthropic API error 401"), null).status, 502);
});

// ── BYOK: runGate and runAdminGate paths ──

function makeByokAdminDeps(): AdminGateDeps & { calls: { fetchUser: number } } {
  const calls = { fetchUser: 0 };
  return {
    sharedToken: undefined,
    checkRateLimit: () => Promise.resolve({ allowed: true, retryAfterSeconds: 0 }),
    fetchUser: () => {
      calls.fetchUser++;
      return Promise.resolve({ ok: false, isAdmin: false });
    },
    now: () => 1000,
    cache: new Map<string, { exp: number; isAdmin: boolean }>(),
    calls,
  };
}

Deno.test("runGate: valid BYOK header, no bearer -> passes without validation", async () => {
  const deps = makeDeps();
  const resp = await runGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100, allowByok: true }, deps);
  assertEquals(resp, null);
  assertEquals(deps.calls.validate, 0);
});

Deno.test("runGate: malformed BYOK header, no bearer -> 401", async () => {
  const resp = await runGate(req({ byok: "not-a-key" }), { endpoint: "t", maxBodyBytes: 100, allowByok: true }, makeDeps());
  assertEquals(resp?.status, 401);
});

Deno.test("runGate: BYOK still method-checked -> 405", async () => {
  const resp = await runGate(req({ byok: GOOD_KEY, method: "GET" }), { endpoint: "t", maxBodyBytes: 100, allowByok: true }, makeDeps());
  assertEquals(resp?.status, 405);
});

Deno.test("runGate: BYOK still body-capped -> 413", async () => {
  const resp = await runGate(req({ byok: GOOD_KEY, contentLength: 999 }), { endpoint: "t", maxBodyBytes: 100, allowByok: true }, makeDeps());
  assertEquals(resp?.status, 413);
});

Deno.test("runGate: BYOK still rate-limited -> 429", async () => {
  const deps = makeDeps({
    checkRateLimit: () => Promise.resolve({ allowed: false, retryAfterSeconds: 7 }),
  });
  const resp = await runGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100, allowByok: true }, deps);
  assertEquals(resp?.status, 429);
});

Deno.test("runAdminGate: valid BYOK header, no bearer -> passes without admin", async () => {
  const deps = makeByokAdminDeps();
  const resp = await runAdminGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100, allowByok: true }, deps);
  assertEquals(resp, null);
  assertEquals(deps.calls.fetchUser, 0);
});

Deno.test("runAdminGate: no BYOK, non-admin token -> 403 (unchanged)", async () => {
  const deps = makeByokAdminDeps();
  deps.fetchUser = () => Promise.resolve({ ok: true, isAdmin: false });
  const resp = await runAdminGate(req({ token: "user-token" }), { endpoint: "t", maxBodyBytes: 100, allowByok: true }, deps);
  assertEquals(resp?.status, 403);
});

// ── BYOK is opt-in per endpoint (finding 1: hent must never allow it) ──

Deno.test("runGate: valid BYOK header, NO allowByok -> 401 (BYOK not accepted)", async () => {
  const deps = makeDeps();
  const resp = await runGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp?.status, 401);
});

Deno.test("runAdminGate: valid BYOK header, NO allowByok -> 401 (fetchUser not ok, BYOK ignored)", async () => {
  const deps = makeByokAdminDeps();
  const resp = await runAdminGate(req({ byok: GOOD_KEY }), { endpoint: "t", maxBodyBytes: 100 }, deps);
  assertEquals(resp?.status, 401);
});

Deno.test("runGate: allowByok, valid BYOK header AND invalid Bearer token both present -> passes (BYOK wins)", async () => {
  const deps = makeDeps({ validateToken: () => Promise.resolve(false) });
  const headers = new Headers();
  headers.set("authorization", "Bearer definitely-not-valid");
  headers.set("x-anthropic-key", GOOD_KEY);
  const request = new Request("https://example.test/", { method: "POST", headers });
  const resp = await runGate(request, { endpoint: "t", maxBodyBytes: 100, allowByok: true }, deps);
  assertEquals(resp, null);
  assertEquals(deps.calls.validate, 0); // BYOK short-circuits before token validation
});
