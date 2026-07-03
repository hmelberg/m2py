const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const ANTHROPIC_VERSION = "2023-06-01";

export interface AnthropicStreamOptions {
  apiKey: string;
  model: string;
  prompt: string;
  maxTokens?: number;
  // Optional cached system prefix. When set, it is sent as a `system` block
  // with a cache_control breakpoint so the (large, stable) prefix is billed
  // at cache-read rates on repeat requests instead of full input rates.
  system?: string;
  // Cache TTL for the system block. "1h" needs the extended-cache-ttl beta
  // header; "5m" (default) is GA. Ignored when `system` is unset.
  cacheTtl?: "5m" | "1h";
}

export interface StreamEvent {
  type: "text" | "done" | "error";
  text?: string;
  inputTokens?: number;
  outputTokens?: number;
  cacheReadTokens?: number;
  cacheCreationTokens?: number;
  message?: string;
}

const ANTHROPIC_TIMEOUT_MS = 30_000;
const ANTHROPIC_RETRIES = 2;

export interface RetryDeps {
  fetchImpl?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  retries?: number;
  timeoutMs?: number;
}

/**
 * POST with an abort timeout and retry/backoff on 429 (rate limited) and 529
 * (overloaded). Honours a numeric Retry-After when present. Network errors are
 * retried too; the final error propagates. Injectable for tests.
 */
export async function fetchWithRetry(
  url: string,
  init: RequestInit,
  deps: RetryDeps = {},
): Promise<Response> {
  const fetchImpl = deps.fetchImpl ?? fetch;
  const sleep = deps.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  const retries = deps.retries ?? ANTHROPIC_RETRIES;
  const timeoutMs = deps.timeoutMs ?? ANTHROPIC_TIMEOUT_MS;

  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const resp = await fetchImpl(url, { ...init, signal: ctrl.signal });
      clearTimeout(timer);
      if ((resp.status === 429 || resp.status === 529) && attempt < retries) {
        const ra = parseInt(resp.headers.get("retry-after") ?? "", 10);
        const delay = Number.isFinite(ra) && ra > 0
          ? Math.min(ra * 1000, 10_000)
          : Math.min(1000 * 2 ** attempt, 8000);
        await sleep(delay);
        continue;
      }
      return resp;
    } catch (e) {
      clearTimeout(timer);
      lastError = e;
      if (attempt < retries) {
        await sleep(Math.min(1000 * 2 ** attempt, 8000));
        continue;
      }
      throw e;
    }
  }
  throw lastError;
}

export async function streamAnthropic(
  opts: AnthropicStreamOptions,
): Promise<ReadableStream<Uint8Array>> {
  const useLongTtl = opts.cacheTtl === "1h";
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-api-key": opts.apiKey,
    "anthropic-version": ANTHROPIC_VERSION,
  };
  if (opts.system && useLongTtl) {
    headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11";
  }

  const requestBody: Record<string, unknown> = {
    model: opts.model,
    max_tokens: opts.maxTokens ?? 2000,
    stream: true,
    messages: [{ role: "user", content: opts.prompt }],
  };
  if (opts.system) {
    requestBody.system = [
      {
        type: "text",
        text: opts.system,
        cache_control: useLongTtl
          ? { type: "ephemeral", ttl: "1h" }
          : { type: "ephemeral" },
      },
    ];
  }

  const upstream = await fetchWithRetry(ANTHROPIC_API, {
    method: "POST",
    headers,
    body: JSON.stringify(requestBody),
  });

  if (!upstream.ok || !upstream.body) {
    // Log the upstream detail server-side, but do NOT echo it to the client
    // (it can contain account/key diagnostics). Callers surface a generic 502.
    const detail = await upstream.text().catch(() => "");
    console.error(`Anthropic API error ${upstream.status}: ${detail}`);
    throw new Error(`Anthropic API error ${upstream.status}`);
  }

  return transformAnthropicStream(upstream.body);
}

export interface AnthropicMessageResult {
  text: string;
  usage: {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    cacheCreationTokens: number;
  };
}

/**
 * Single, non-streaming completion. Used by the v2 variable-picker pass, which
 * needs the full result (a JSON array of variable names) before generation can
 * start. Reuses fetchWithRetry for timeout + 429/529 backoff. `deps` is
 * injectable for tests.
 */
export async function messageAnthropic(
  opts: AnthropicStreamOptions,
  deps: RetryDeps = {},
): Promise<AnthropicMessageResult> {
  const useLongTtl = opts.cacheTtl === "1h";
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "x-api-key": opts.apiKey,
    "anthropic-version": ANTHROPIC_VERSION,
  };
  if (opts.system && useLongTtl) {
    headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11";
  }
  const requestBody: Record<string, unknown> = {
    model: opts.model,
    max_tokens: opts.maxTokens ?? 1024,
    stream: false,
    messages: [{ role: "user", content: opts.prompt }],
  };
  if (opts.system) {
    requestBody.system = [
      {
        type: "text",
        text: opts.system,
        cache_control: useLongTtl ? { type: "ephemeral", ttl: "1h" } : { type: "ephemeral" },
      },
    ];
  }

  const resp = await fetchWithRetry(
    ANTHROPIC_API,
    { method: "POST", headers, body: JSON.stringify(requestBody) },
    deps,
  );
  if (!resp.ok) {
    const detail = await resp.text().catch(() => "");
    console.error(`Anthropic API error ${resp.status}: ${detail}`);
    throw new Error(`Anthropic API error ${resp.status}`);
  }
  const json = await resp.json();
  const text = Array.isArray(json?.content)
    ? json.content.filter((b: { type?: string }) => b?.type === "text")
        .map((b: { text?: string }) => b.text ?? "").join("")
    : "";
  const u = json?.usage ?? {};
  return {
    text,
    usage: {
      inputTokens: u.input_tokens ?? 0,
      outputTokens: u.output_tokens ?? 0,
      cacheReadTokens: u.cache_read_input_tokens ?? 0,
      cacheCreationTokens: u.cache_creation_input_tokens ?? 0,
    },
  };
}

function transformAnthropicStream(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let buffer = "";
  let inputTokens = 0;
  let outputTokens = 0;
  let cacheReadTokens = 0;
  let cacheCreationTokens = 0;

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
            if (!payload || payload === "[DONE]") continue;
            try {
              const obj = JSON.parse(payload);
              if (obj.type === "content_block_delta" && obj.delta?.type === "text_delta") {
                const out: StreamEvent = { type: "text", text: obj.delta.text };
                controller.enqueue(encoder.encode(`data: ${JSON.stringify(out)}\n\n`));
              } else if (obj.type === "message_start" && obj.message?.usage) {
                inputTokens = obj.message.usage.input_tokens ?? 0;
                cacheReadTokens = obj.message.usage.cache_read_input_tokens ?? 0;
                cacheCreationTokens = obj.message.usage.cache_creation_input_tokens ?? 0;
              } else if (obj.type === "message_delta" && obj.usage) {
                outputTokens = obj.usage.output_tokens ?? outputTokens;
              }
            } catch (_e) {
              // ignore non-JSON event data
            }
          }
        }
        // Drain any residual buffer content not yet terminated by \n\n
        if (buffer.trim()) {
          buffer += "\n\n";
          let nlIdx;
          while ((nlIdx = buffer.indexOf("\n\n")) >= 0) {
            const event = buffer.slice(0, nlIdx);
            buffer = buffer.slice(nlIdx + 2);
            const dataLine = event.split("\n").find((l) => l.startsWith("data:"));
            if (!dataLine) continue;
            const payload = dataLine.slice(5).trim();
            if (!payload || payload === "[DONE]") continue;
            try {
              const obj = JSON.parse(payload);
              if (obj.type === "content_block_delta" && obj.delta?.type === "text_delta") {
                const out: StreamEvent = { type: "text", text: obj.delta.text };
                controller.enqueue(encoder.encode(`data: ${JSON.stringify(out)}\n\n`));
              } else if (obj.type === "message_start" && obj.message?.usage) {
                inputTokens = obj.message.usage.input_tokens ?? 0;
                cacheReadTokens = obj.message.usage.cache_read_input_tokens ?? 0;
                cacheCreationTokens = obj.message.usage.cache_creation_input_tokens ?? 0;
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
          cacheReadTokens,
          cacheCreationTokens,
        };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(done)}\n\n`));
      } catch (e) {
        const err: StreamEvent = { type: "error", message: String(e) };
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(err)}\n\n`));
      } finally {
        reader.releaseLock();
        controller.close();
      }
    },
  });
}

// ── Agentic tool loop (Web mode / data-svar) ─────────────────────────────
// Non-streaming turns while the model calls tools; the final answer is
// emitted as one SSE text event (accepted trade-off: no token streaming on
// the final turn — the loop stays simple and correct). Hosted tools
// (web_search) run inside the API; stop_reason "pause_turn" is resumed.

export interface AgenticOptions {
  apiKey: string;
  model: string;
  system: string;
  userContent: string;
  tools: unknown[];
  executeTool: (name: string, input: Record<string, unknown>) => Promise<string>;
  progressLabel?: (name: string, input: Record<string, unknown>) => string;
  maxTokens?: number;
  cacheTtl?: "5m" | "1h";
  maxClientToolCalls?: number;
  maxTurns?: number;
  // Continuation protocol: Netlify caps CPU per edge invocation, so a run
  // that needs many API turns must be split across invocations. When the
  // per-call turn budget (turnsPerCall, default 1) is spent without a final
  // answer, the stream ends with {type:"continue", state, ...continueExtra()}
  // and the client re-POSTs with `resume` = that state.
  resume?: AgenticResumeState;
  turnsPerCall?: number;
  continueExtra?: () => Record<string, unknown>;
  deps?: RetryDeps;
}

// Everything the loop needs to pick up where a previous invocation stopped.
// Round-trips through the client verbatim; contains only the question, tool
// results and model output — never the system prompt or API keys.
export interface AgenticResumeState {
  messages: Record<string, unknown>[];
  turn: number;
  clientCalls: number;
  usage: {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    cacheCreationTokens: number;
  };
}

// Long final generations (multi-tool-call context, big final script) can
// exceed a 90s non-streaming turn. 180s trades a longer worst-case wait for
// fewer AbortErrors; the proper future fix is streaming the final turn
// instead of buffering it whole.
const AGENTIC_TIMEOUT_MS = 180_000;

// Netlify/CDN kills streamed responses that go silent for too long (~40-60s).
// Non-streaming API turns are exactly such silent windows, so while a turn is
// in flight we emit a progress event every 10s. `replace: true` tells the
// client to update the previous progress line in place instead of appending.
const HEARTBEAT_MS = 10_000;

export function runAgenticStream(opts: AgenticOptions): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const maxClientCalls = opts.maxClientToolCalls ?? 12;
  const maxTurns = opts.maxTurns ?? 24;
  const deps: RetryDeps = { timeoutMs: AGENTIC_TIMEOUT_MS, ...opts.deps };
  const useLongTtl = opts.cacheTtl === "1h";

  return new ReadableStream({
    async start(controller) {
      const emit = (obj: Record<string, unknown>) =>
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "x-api-key": opts.apiKey,
        "anthropic-version": ANTHROPIC_VERSION,
      };
      if (useLongTtl) headers["anthropic-beta"] = "extended-cache-ttl-2025-04-11";
      const system = [{
        type: "text",
        text: opts.system,
        cache_control: useLongTtl ? { type: "ephemeral", ttl: "1h" } : { type: "ephemeral" },
      }];

      const state: AgenticResumeState = opts.resume ?? {
        messages: [{ role: "user", content: opts.userContent }],
        turn: 0,
        clientCalls: 0,
        usage: { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheCreationTokens: 0 },
      };
      const turnsPerCall = opts.turnsPerCall ?? 1;

      try {
        for (let i = 0; i < turnsPerCall; i++) {
          if (state.turn >= maxTurns) throw new Error("tool-loopen nådde maks antall turer");
          const turnLabel = state.turn === 0
            ? "🧠 Tolker spørsmålet og planlegger"
            : `🤔 Arbeider med svaret (tur ${state.turn + 1})`;
          emit({ type: "progress", text: `${turnLabel} …`, replace: true });
          const turnStart = Date.now();
          const beat = setInterval(() => {
            const s = Math.round((Date.now() - turnStart) / 1000);
            try {
              emit({ type: "progress", text: `${turnLabel} … (${s} s)`, replace: true });
            } catch (_) { /* stream already closed */ }
          }, HEARTBEAT_MS);
          let resp: Response;
          try {
            resp = await fetchWithRetry(ANTHROPIC_API, {
              method: "POST",
              headers,
              body: JSON.stringify({
                model: opts.model,
                max_tokens: opts.maxTokens ?? 8192,
                stream: false,
                system,
                tools: opts.tools,
                messages: state.messages,
              }),
            }, deps);
          } finally {
            clearInterval(beat);
          }
          if (!resp.ok) {
            const detail = await resp.text().catch(() => "");
            console.error(`Anthropic API error ${resp.status}: ${detail}`);
            throw new Error(`Anthropic API error ${resp.status}`);
          }
          const json = await resp.json();
          state.turn++;
          const u = json?.usage ?? {};
          state.usage.inputTokens += u.input_tokens ?? 0;
          state.usage.outputTokens += u.output_tokens ?? 0;
          state.usage.cacheReadTokens += u.cache_read_input_tokens ?? 0;
          state.usage.cacheCreationTokens += u.cache_creation_input_tokens ?? 0;
          const content = Array.isArray(json?.content) ? json.content : [];

          // Hosted tools (web_search/web_fetch) run inside the API and are
          // otherwise invisible to the user — surface what was searched/read.
          for (const b of content) {
            if (b?.type !== "server_tool_use") continue;
            const inp = (b.input ?? {}) as Record<string, unknown>;
            const what = String(inp.query ?? inp.url ?? "").slice(0, 120);
            emit({
              type: "progress",
              text: b.name === "web_fetch" ? `🌐 Leser ${what}` : `🔎 Websøk: ${what}`,
            });
          }

          if (json.stop_reason === "pause_turn") {
            state.messages.push({ role: "assistant", content });
            continue;
          }
          const toolUses = content.filter((b: { type?: string }) => b.type === "tool_use");
          if (json.stop_reason === "tool_use" && toolUses.length) {
            state.messages.push({ role: "assistant", content });
            const results: Record<string, unknown>[] = [];
            for (const tu of toolUses) {
              state.clientCalls++;
              const label = opts.progressLabel?.(tu.name, tu.input ?? {}) ?? `Kjører ${tu.name} …`;
              emit({ type: "progress", text: label });
              let out: string;
              if (state.clientCalls > maxClientCalls) {
                out = "Verktøy-budsjettet er brukt opp — generer svaret NÅ med det du allerede har funnet. Vær ærlig om hva som mangler.";
              } else {
                try {
                  out = await opts.executeTool(tu.name, tu.input ?? {});
                } catch (e) {
                  out = `Verktøyfeil: ${String(e).slice(0, 300)}`;
                }
              }
              results.push({ type: "tool_result", tool_use_id: tu.id, content: out });
            }
            state.messages.push({ role: "user", content: results });
            continue;
          }
          // Final answer
          for (const b of content) {
            if (b.type === "text" && b.text) emit({ type: "text", text: b.text });
          }
          emit({ type: "done", ...state.usage });
          controller.close();
          return;
        }
        // Turn budget for THIS invocation spent without a final answer: hand
        // the state back so the client can continue in a fresh invocation.
        emit({ type: "continue", state, ...(opts.continueExtra?.() ?? {}) });
        controller.close();
        return;
      } catch (e) {
        emit({ type: "error", message: String(e) });
        controller.close();
      }
    },
  });
}
