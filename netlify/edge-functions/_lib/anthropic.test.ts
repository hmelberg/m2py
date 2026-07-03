import { assertEquals, assertRejects } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { fetchWithRetry, messageAnthropic, runAgenticStream } from "./anthropic.ts";

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

async function collectSse(stream: ReadableStream<Uint8Array>): Promise<Record<string, unknown>[]> {
  const text = await new Response(stream).text();
  return text.split("\n\n").filter((l) => l.startsWith("data: "))
    .map((l) => JSON.parse(l.slice(6)));
}

function apiTurns(turns: Record<string, unknown>[]): typeof fetch {
  let i = 0;
  return ((_u: string | URL | Request, _init?: RequestInit) =>
    Promise.resolve(new Response(JSON.stringify(turns[i++]), { status: 200 }))) as typeof fetch;
}

Deno.test("runAgenticStream: tool round-trip then final text", async () => {
  const fetchImpl = apiTurns([
    { stop_reason: "tool_use", usage: { input_tokens: 10, output_tokens: 5 },
      content: [{ type: "tool_use", id: "tu1", name: "probe", input: { url: "https://x/d.csv" } }] },
    { stop_reason: "end_turn", usage: { input_tokens: 20, output_tokens: 15 },
      content: [{ type: "text", text: "Her er scriptet." }] },
  ]);
  const calls: string[] = [];
  const events = await collectSse(runAgenticStream({
    apiKey: "k", model: "m", system: "s", userContent: "q",
    tools: [{ name: "probe", description: "d", input_schema: { type: "object" } }],
    executeTool: (name, input) => { calls.push(`${name}:${input.url}`); return Promise.resolve('{"ok":true}'); },
    turnsPerCall: 99,
    deps: { fetchImpl },
  }));
  assertEquals(calls, ["probe:https://x/d.csv"]);
  // Turn labels (replace:true) interleave with the tool label; the substantive
  // sequence is: turn-1 label, tool label, turn-2 label, text, done.
  assertEquals(events.map((e) => e.type), ["progress", "progress", "progress", "text", "done"]);
  assertEquals(events[0].replace, true);
  assertEquals(events[1].replace, undefined);
  assertEquals(events[2].replace, true);
  assertEquals(events[3].text, "Her er scriptet.");
  assertEquals(events[4].inputTokens, 30);
  assertEquals(events[4].outputTokens, 20);
});

Deno.test("runAgenticStream: hosted web_search/web_fetch surface as progress labels", async () => {
  const fetchImpl = apiTurns([
    { stop_reason: "pause_turn", usage: { input_tokens: 1, output_tokens: 1 },
      content: [{ type: "server_tool_use", id: "s1", name: "web_search", input: { query: "utdanning lønn norge" } }] },
    { stop_reason: "end_turn", usage: { input_tokens: 1, output_tokens: 1 },
      content: [
        { type: "server_tool_use", id: "s2", name: "web_fetch", input: { url: "https://ssb.no/x" } },
        { type: "text", text: "svar" },
      ] },
  ]);
  const events = await collectSse(runAgenticStream({
    apiKey: "k", model: "m", system: "s", userContent: "q", tools: [],
    executeTool: () => Promise.resolve(""),
    turnsPerCall: 99,
    deps: { fetchImpl },
  }));
  const labels = events.filter((e) => e.type === "progress" && !e.replace).map((e) => e.text);
  assertEquals(labels, ["🔎 Websøk: utdanning lønn norge", "🌐 Leser https://ssb.no/x"]);
  assertEquals(events.at(-1)?.type, "done");
});

Deno.test("runAgenticStream: budget exhausts into forced generation", async () => {
  const toolTurn = {
    stop_reason: "tool_use", usage: { input_tokens: 1, output_tokens: 1 },
    content: [{ type: "tool_use", id: "t", name: "probe", input: {} }],
  };
  const finalTurn = {
    stop_reason: "end_turn", usage: { input_tokens: 1, output_tokens: 1 },
    content: [{ type: "text", text: "ferdig" }],
  };
  let toolResults: string[] = [];
  const events = await collectSse(runAgenticStream({
    apiKey: "k", model: "m", system: "s", userContent: "q",
    tools: [], maxClientToolCalls: 2, turnsPerCall: 99,
    executeTool: () => { return Promise.resolve("data"); },
    deps: { fetchImpl: (( _u: string | URL | Request, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      const lastUser = body.messages.filter((m: { role: string }) => m.role === "user").pop();
      if (Array.isArray(lastUser?.content)) {
        for (const c of lastUser.content) if (c.type === "tool_result") toolResults.push(String(c.content));
      }
      const turn = body.messages.length >= 7 ? finalTurn : toolTurn; // 3 tool rounds then final
      return Promise.resolve(new Response(JSON.stringify(turn), { status: 200 }));
    }) as typeof fetch },
  }));
  // third call is over budget (max 2) -> its result is the budget message
  if (!toolResults[2]?.includes("budsjett")) throw new Error("ventet budsjett-melding: " + toolResults[2]);
  assertEquals(events.at(-1)?.type, "done");
});

Deno.test("runAgenticStream: default one turn per call — continue carries state, resume finishes", async () => {
  const fetchImpl = apiTurns([
    { stop_reason: "tool_use", usage: { input_tokens: 10, output_tokens: 5 },
      content: [{ type: "tool_use", id: "tu1", name: "probe", input: { url: "https://x/d.csv" } }] },
    { stop_reason: "end_turn", usage: { input_tokens: 20, output_tokens: 15 },
      content: [{ type: "text", text: "ferdig svar" }] },
  ]);
  const base = {
    apiKey: "k", model: "m", system: "s", userContent: "q", tools: [],
    executeTool: () => Promise.resolve('{"ok":true}'),
    continueExtra: () => ({ probed: [{ url: "https://x/d.csv", ok: true }] }),
    deps: { fetchImpl },
  };
  // Invocation 1: one tool turn, then hands back state instead of looping on.
  const ev1 = await collectSse(runAgenticStream(base));
  const cont = ev1.at(-1)!;
  assertEquals(cont.type, "continue");
  const st = cont.state as { turn: number; clientCalls: number; messages: unknown[]; usage: Record<string, number> };
  assertEquals(st.turn, 1);
  assertEquals(st.clientCalls, 1);
  assertEquals(st.messages.length, 3); // user q, assistant tool_use, user tool_result
  assertEquals((cont.probed as { url: string }[])[0].url, "https://x/d.csv");
  // Invocation 2: resumes from the state and finishes; usage summed across both.
  const ev2 = await collectSse(runAgenticStream({ ...base, resume: st as never }));
  assertEquals(ev2.filter((e) => e.type === "text")[0].text, "ferdig svar");
  const done = ev2.at(-1)!;
  assertEquals(done.type, "done");
  assertEquals(done.inputTokens, 30);
  assertEquals(done.outputTokens, 20);
});

Deno.test("runAgenticStream: API error surfaces as error event", async () => {
  const events = await collectSse(runAgenticStream({
    apiKey: "k", model: "m", system: "s", userContent: "q", tools: [],
    executeTool: () => Promise.resolve(""),
    deps: { fetchImpl: ((_u: string | URL | Request) =>
      Promise.resolve(new Response("boom", { status: 500 }))) as typeof fetch, retries: 0 },
  }));
  assertEquals(events.at(-1)?.type, "error");
});
