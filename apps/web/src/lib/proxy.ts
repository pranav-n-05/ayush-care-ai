/** Server-side proxy helpers: the browser only talks to this origin; requests to /api/v1/* are
 * forwarded to the FastAPI service named by API_INTERNAL_URL (read at runtime, so the target
 * can change without rebuilding). Only an allowlist of headers is forwarded. */

const FORWARD_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "idempotency-key",
  "origin",
  "x-csrf-token",
  "x-request-id",
];

// Hop-by-hop or body-encoding headers that must not be copied from the upstream response
// (Node's fetch has already decoded the body).
const DROP_RESPONSE_HEADERS = new Set([
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "set-cookie",
  "transfer-encoding",
]);

export function upstreamUrl(base: string, path: string[], search: string): string | null {
  // Dot segments could escape /api/v1 on the upstream after URL normalization.
  if (path.some((p) => p === "." || p === ".." || p === "")) return null;
  const safe = path.map((p) => encodeURIComponent(p)).join("/");
  return `${base.replace(/\/+$/, "")}/api/v1/${safe}${search}`;
}

export function forwardRequestHeaders(incoming: Headers): Headers {
  const out = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const v = incoming.get(name);
    if (v !== null) out.set(name, v);
  }
  return out;
}

export function forwardResponseHeaders(upstream: Headers): Headers {
  const out = new Headers();
  upstream.forEach((value, name) => {
    if (!DROP_RESPONSE_HEADERS.has(name.toLowerCase())) out.set(name, value);
  });
  for (const cookie of upstream.getSetCookie()) out.append("set-cookie", cookie);
  return out;
}
