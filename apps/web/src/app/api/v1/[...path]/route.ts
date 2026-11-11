import { forwardRequestHeaders, forwardResponseHeaders, upstreamUrl } from "@/lib/proxy";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(req: Request, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  const { path } = await ctx.params;
  const url = upstreamUrl(base, path, new URL(req.url).search);
  if (url === null) return Response.json({ error: { code: "not_found", message: "Not found", details: null } }, { status: 404 });
  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers: forwardRequestHeaders(req.headers),
      body: hasBody ? await req.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { error: { code: "upstream_unavailable", message: "The API is unavailable (it may be waking up). Try again shortly.", details: null } },
      { status: 503 },
    );
  }
  return new Response(upstream.body, { status: upstream.status, headers: forwardResponseHeaders(upstream.headers) });
}

export { proxy as DELETE, proxy as GET, proxy as POST, proxy as PUT };
