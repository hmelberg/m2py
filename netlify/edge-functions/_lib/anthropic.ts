const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION = "2023-06-01";

export interface AnthropicStreamOptions {
  apiKey: string;
  model: string;
  prompt: string;
  maxTokens?: number;
}

export interface StreamEvent {
  type: "text" | "done" | "error";
  text?: string;
  inputTokens?: number;
  outputTokens?: number;
  message?: string;
}

export async function streamAnthropic(
  opts: AnthropicStreamOptions,
): Promise<ReadableStream<Uint8Array>> {
  const upstream = await fetch(ANTHROPIC_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": opts.apiKey,
      "anthropic-version": ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: opts.model,
      max_tokens: opts.maxTokens ?? 2000,
      stream: true,
      messages: [{ role: "user", content: opts.prompt }],
    }),
  });

  if (!upstream.ok || !upstream.body) {
    const body = await upstream.text();
    throw new Error(`Anthropic API error ${upstream.status}: ${body}`);
  }

  return transformAnthropicStream(upstream.body);
}

function transformAnthropicStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let buffer = "";
  let inputTokens = 0;
  let outputTokens = 0;

  return new ReadableStream({
    async start(controller) {
      const reader = upstream.getReader();
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let nlIdx;
          while ((nlIdx = buffer.indexOf("\n\n")) >= 0) {
            const event = buffer.slice(0, nlIdx);
            buffer = buffer.slice(nlIdx + 2);
            const dataLine = event.split("\n").find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            const payload = dataLine.slice(5).trim();
            if (!payload) continue;
            try {
              const obj = JSON.parse(payload);
              if (obj.type === "content_block_delta" && obj.delta?.type === "text_delta") {
                const out: StreamEvent = { type: "text", text: obj.delta.text };
                controller.enqueue(encoder.encode(`data: ${JSON.stringify(out)}\n\n`));
              } else if (obj.type === "message_start" && obj.message?.usage) {
                inputTokens = obj.message.usage.input_tokens ?? 0;
              } else if (obj.type === "message_delta" && obj.usage) {
                outputTokens = obj.usage.output_tokens ?? outputTokens;
              }
            } catch (_e) {
              // ignore non-JSON event data
            }
          }
        }
        const done: StreamEvent = {
          type: "done",
          inputTokens,
          outputTokens,
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(done)}\n\n`));
      } catch (e) {
        const err: StreamEvent = { type: "error", message: String(e) };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(err)}\n\n`));
      } finally {
        controller.close();
      }
    },
  });
}
