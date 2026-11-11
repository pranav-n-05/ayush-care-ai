import { describe, expect, it } from "vitest";

import { forwardRequestHeaders, forwardResponseHeaders, upstreamUrl } from "@/lib/proxy";

describe("api proxy", () => {
  it("builds upstream URLs without allowing path tricks", () => {
    expect(upstreamUrl("https://api.example.com/", ["patients", "abc"], "?q=x")).toBe("https://api.example.com/api/v1/patients/abc?q=x");
    expect(upstreamUrl("http://a", ["..", "admin"], "")).toBeNull();
    expect(upstreamUrl("http://a", ["patients", "."], "")).toBeNull();
    expect(upstreamUrl("http://a", ["x/y"], "")).toBe("http://a/api/v1/x%2Fy");
  });

  it("forwards only allowlisted request headers", () => {
    const h = forwardRequestHeaders(new Headers({ cookie: "ayush_session=1", "x-csrf-token": "t", authorization: "Bearer x", host: "evil" }));
    expect(h.get("cookie")).toBe("ayush_session=1");
    expect(h.get("x-csrf-token")).toBe("t");
    expect(h.get("authorization")).toBeNull();
    expect(h.get("host")).toBeNull();
  });

  it("keeps every Set-Cookie and drops encoding headers", () => {
    const up = new Headers();
    up.append("set-cookie", "ayush_session=a; HttpOnly");
    up.append("set-cookie", "ayush_csrf=b");
    up.set("content-encoding", "gzip");
    up.set("content-type", "application/json");
    const out = forwardResponseHeaders(up);
    expect(out.getSetCookie()).toEqual(["ayush_session=a; HttpOnly", "ayush_csrf=b"]);
    expect(out.get("content-encoding")).toBeNull();
    expect(out.get("content-type")).toBe("application/json");
  });
});
