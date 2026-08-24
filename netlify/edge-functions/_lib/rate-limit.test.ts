import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { checkRateLimit } from "./rate-limit.ts";

// Mirrors MAX_CALLS in rate-limit.ts. One constant, so raising the budget
// does not mean rewriting assertions.
const LIMIT = 60;

// In-memory fake of the Netlify Blobs store.
function fakeStore() {
  const data = new Map<string, unknown>();
  return {
    get: (key: string) => Promise.resolve(data.get(key) ?? null),
    setJSON: (key: string, value: unknown) => {
      data.set(key, value);
      return Promise.resolve();
    },
  };
}

function throwingStore() {
  return {
    get: () => Promise.reject(new Error("blobs down")),
    setJSON: () => Promise.reject(new Error("blobs down")),
  };
}

Deno.test("checkRateLimit: empty ip is always allowed", async () => {
  const r = await checkRateLimit("ep", "", () => fakeStore());
  assertEquals(r.allowed, true);
});

Deno.test("checkRateLimit: allows up to the limit, then denies", async () => {
  const store = fakeStore();
  const getStoreImpl = () => store;
  let lastAllowed = true;
  for (let i = 0; i < LIMIT; i++) {
    const r = await checkRateLimit("ep", "1.2.3.4", getStoreImpl);
    lastAllowed = r.allowed;
  }
  assertEquals(lastAllowed, true); // the whole budget is within limit
  const denied = await checkRateLimit("ep", "1.2.3.4", getStoreImpl); // one over
  assertEquals(denied.allowed, false);
  assertEquals(denied.retryAfterSeconds > 0, true);
});

Deno.test("checkRateLimit: fails OPEN when the store throws (no 500 storm)", async () => {
  const r = await checkRateLimit("ep", "1.2.3.4", () => throwingStore());
  assertEquals(r.allowed, true);
});

Deno.test("checkRateLimit: separate IPs have separate budgets", async () => {
  const store = fakeStore();
  const getStoreImpl = () => store;
  for (let i = 0; i < LIMIT; i++) await checkRateLimit("ep", "a", getStoreImpl);
  const otherIp = await checkRateLimit("ep", "b", getStoreImpl);
  assertEquals(otherIp.allowed, true);
});
