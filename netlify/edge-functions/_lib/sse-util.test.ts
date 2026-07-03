import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { injectBeforeDone } from "./sse-util.ts";

function sse(events: Record<string, unknown>[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const e of events) c.enqueue(enc.encode(`data: ${JSON.stringify(e)}\n\n`));
      c.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<Record<string, unknown>[]> {
  const text = await new Response(stream).text();
  return text.split("\n\n").filter((l) => l.startsWith("data: ")).map((l) => JSON.parse(l.slice(6)));
}

Deno.test("injectBeforeDone inserts sources right before done", async () => {
  const out = await collect(injectBeforeDone(
    sse([{ type: "text", text: "hei" }, { type: "done", outputTokens: 1 }]),
    () => ({ type: "sources", sources: [{ url: "https://x", ok: true }] }),
  ));
  assertEquals(out.map((e) => e.type), ["text", "sources", "done"]);
});

Deno.test("injectBeforeDone: null event and no done-event pass through", async () => {
  const a = await collect(injectBeforeDone(sse([{ type: "done" }]), () => null));
  assertEquals(a.map((e) => e.type), ["done"]);
  const b = await collect(injectBeforeDone(sse([{ type: "error", message: "x" }]), () => ({ type: "sources" })));
  assertEquals(b.map((e) => e.type), ["error"]);
});
