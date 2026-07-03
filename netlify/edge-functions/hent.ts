// /api/hent — SSRF-hardened fetch proxy for Web mode (admin-only while the
// feature is admin-only; see spec §5). GET /api/hent?url=…[&body=…]
import { adminGate } from "./_lib/auth.ts";
import { loadRegistry } from "./_lib/registry.ts";
import { handleHent } from "./_lib/hent-core.ts";

export default async (request: Request): Promise<Response> => {
  const gateResp = await adminGate(request, {
    endpoint: "hent",
    maxBodyBytes: 0,
    allowedMethods: ["GET"],
  });
  if (gateResp) return gateResp;

  let registry;
  try {
    registry = await loadRegistry(new URL(request.url).origin);
  } catch (e) {
    console.error("hent: registry load failed:", e);
    return new Response("Kilderegister utilgjengelig", { status: 502 });
  }
  return handleHent(request, { registry, getEnv: (k) => Deno.env.get(k) });
};
