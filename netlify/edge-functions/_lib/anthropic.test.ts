import { assertEquals, assertRejects } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { fetchWithRetry, messageAnthropic } from "./anthropic.ts";

const noSleep = (_ms: number) => Promise.resolve();

function resp(status: number, headers: Record<string, string> = {}): Response {
  return new Response("body", { status, headers });
}

Deno.test("fetchWithRetry: retries on 429 then returns success", async () => {
  let calls = 0;
  const fetchImpl = ((_url: string | URL | Request, _init?: RequestInit) => {
    calls++;
    return Promise.resolve(calls < 3 ? resp(429) : resp(200));
  }) as typeof fetch;
  const r = await fetchWithRetry("https://x/", { method: "POST" }, {
    fetchImpl,
    sleep: noSleep,
    retries: 3,
  });
  assertEquals(r.status, 200);
  assertEquals(calls, 3);
});

Deno.test("fetchWithRetry: retries on 529 (overloaded)", async () => {
  let calls = 0;
  const fetchImpl = (() => {
    calls++;
    return Promise.resolve(calls < 2 ? resp(529) : resp(200));
  }) as typeof fetch;
  const r = await fetchWithRetry("https://x/", {}, { fetchImpl, sleep: noSleep, retries: 2 });
  assertEquals(r.status, 200);
  assertEquals(calls, 2);
});

Deno.test("fetchWithRetry: does NOT retry on 400", async () => {
  let calls = 0;
  const fetchImpl = (() => {
    calls++;
    return Promise.resolve(resp(400));
  }) as typeof fetch;
  const r = await fetchWithRetry("https://x/", {}, { fetchImpl, sleep: noSleep, retries: 3 });
  assertEquals(r.status, 400);
  assertEquals(calls, 1);
});

Deno.test("fetchWithRetry: gives up after exhausting retries on 429", async () => {
  let calls = 0;
  const fetchImpl = (() => {
    calls++;
    return Promise.resolve(resp(429));
  }) as typeof fetch;
  const r = await fetchWithRetry("https://x/", {}, { fetchImpl, sleep: noSleep, retries: 2 });
  assertEquals(r.status, 429);
  assertEquals(calls, 3); // initial + 2 retries
});

Deno.test("fetchWithRetry: retries network errors, then propagates", async () => {
  let calls = 0;
  const fetchImpl = (() => {
    calls++;
    return Promise.reject(new Error("boom"));
  }) as typeof fetch;
  await assertRejects(
    () => fetchWithRetry("https://x/", {}, { fetchImpl, sleep: noSleep, retries: 2 }),
    Error,
    "boom",
  );
  assertEquals(calls, 3);
});

Deno.test("fetchWithRetry: honours numeric Retry-After (capped)", async () => {
  let calls = 0;
  const sleeps: number[] = [];
  const fetchImpl = (() => {
    calls++;
    return Promise.resolve(calls < 2 ? resp(429, { "retry-after": "3" }) : resp(200));
  }) as typeof fetch;
  await fetchWithRetry("https://x/", {}, {
    fetchImpl,
    sleep: (ms) => {
      sleeps.push(ms);
      return Promise.resolve();
    },
    retries: 2,
  });
  assertEquals(sleeps[0], 3000);
});

Deno.test("messageAnthropic returns text and usage from a non-streamed response", async () => {
  const fakeResponse = new Response(
    JSON.stringify({
      content: [{ type: "text", text: '["BEFOLKNING_KJOENN","INNTEKT_WLONN"]' }],
      usage: { input_tokens: 100, output_tokens: 12 },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
  const fetchImpl = (() => Promise.resolve(fakeResponse)) as typeof fetch;

  const out = await messageAnthropic(
    { apiKey: "k", model: "m", prompt: "q", system: "s", maxTokens: 64 },
    { fetchImpl },
  );
  assertEquals(out.text, '["BEFOLKNING_KJOENN","INNTEKT_WLONN"]');
  assertEquals(out.usage.outputTokens, 12);
});

Deno.test("messageAnthropic throws on non-OK upstream", async () => {
  const fetchImpl = (() => Promise.resolve(new Response("boom", { status: 500 }))) as typeof fetch;
  let threw = false;
  try {
    await messageAnthropic({ apiKey: "k", model: "m", prompt: "q" }, { fetchImpl });
  } catch (_e) {
    threw = true;
  }
  assertEquals(threw, true);
});
