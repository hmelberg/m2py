// SSE pass-through that injects one synthetic event immediately before the
// `done` event (used for the deterministic source manifest in data-svar).
export function injectBeforeDone(
  stream: ReadableStream<Uint8Array>,
  makeEvent: () => Record<string, unknown> | null,
): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  let buffer = "";
  return new ReadableStream({
    async start(controller) {
      const reader = stream.getReader();
      const flushEvent = (raw: string) => {
        const dataLine = raw.split("\n").find((l) => l.startsWith("data:"));
        if (dataLine) {
          try {
            const obj = JSON.parse(dataLine.slice(5).trim());
            if (obj?.type === "done") {
              const extra = makeEvent();
              if (extra) controller.enqueue(enc.encode(`data: ${JSON.stringify(extra)}\n\n`));
            }
          } catch { /* pass through unparseable events untouched */ }
        }
        controller.enqueue(enc.encode(raw + "\n\n"));
      };
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += dec.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf("\n\n")) >= 0) {
            flushEvent(buffer.slice(0, idx));
            buffer = buffer.slice(idx + 2);
          }
        }
        if (buffer.trim()) flushEvent(buffer.trimEnd());
      } finally {
        reader.releaseLock();
        controller.close();
      }
    },
  });
}
