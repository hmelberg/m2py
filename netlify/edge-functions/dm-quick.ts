import {
  detectLanguage,
  parsePersonvernComments,
  type ScriptContext,
} from "./_lib/parse-script-context.ts";
import { streamAnthropic } from "./_lib/anthropic.ts";

interface RequestBody {
  script: string;
  active_columns?: string[];
}

function renderContextSection(ctx: ScriptContext): string {
  if (!ctx.hasAny) return "(Ingen personvern-kommentarer funnet i scriptet.)";
  const out: string[] = ["TIDLIGERE ERKLÆRT KONTEKST"];
  if (Object.keys(ctx.structured).length > 0) {
    out.push("", "Strukturert (fra personvern-blokk eller `personvern:<felt>:`-linjer):");
    for (const [field, value] of Object.entries(ctx.structured)) {
      out.push(`- ${field}: ${value}`);
    }
  }
  if (ctx.freetext.length > 0) {
    out.push("", "Fritekst (fra `personvern:`-linjer):");
    for (const f of ctx.freetext) {
      out.push(`- (linje ${f.line}) ${f.text}`);
    }
  }
  return out.join("\n");
}

async function loadPrompt(name: string): Promise<string> {
  const url = new URL(`./prompts/${name}.md`, import.meta.url);
  return await Deno.readTextFile(url);
}

export default async (request: Request): Promise<Response> => {
  if (request.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  let body: RequestBody;
  try {
    body = await request.json();
  } catch (_) {
    return new Response("Invalid JSON", { status: 400 });
  }
  if (!body.script || typeof body.script !== "string") {
    return new Response("Missing script", { status: 400 });
  }

  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  const model = Deno.env.get("ANTHROPIC_MODEL") ?? "claude-sonnet-4-6";
  if (!apiKey) {
    return new Response("Server misconfigured: ANTHROPIC_API_KEY missing", { status: 500 });
  }

  const ctx = parsePersonvernComments(body.script);
  const language = detectLanguage(body.script);
  const contextSection = renderContextSection(ctx);

  const [sharedPrinciples, dmQuickTemplate] = await Promise.all([
    loadPrompt("_shared-principles"),
    loadPrompt("dm-quick"),
  ]);

  const prompt = dmQuickTemplate
    .replace("{{SHARED_PRINCIPLES}}", sharedPrinciples)
    .replace("{{CONTEXT_SECTION}}", contextSection)
    .replace("{{LANGUAGE}}", language)
    .replace("{{SCRIPT}}", body.script);

  try {
    const stream = await streamAnthropic({ apiKey, model, prompt, maxTokens: 2000 });
    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  } catch (e) {
    return new Response(`Upstream error: ${e}`, { status: 502 });
  }
};
