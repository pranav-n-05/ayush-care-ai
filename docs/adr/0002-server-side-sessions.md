# ADR 0002: Opaque server-side sessions in HttpOnly cookies

Status: Accepted (2026-11-11)

**Decision.**
* Login issues a 256-bit random session token in cookie `ayush_session` (`HttpOnly`, `Secure`
  outside local dev — enforced in production by settings validation, `SameSite=Lax`, `Path=/`).
* Only `sha256(token)` is stored (`sessions.token_hash`). Absolute TTL 8 h, idle TTL 30 min,
  revocation on logout, "revoke other sessions", member deactivation and user deactivation.
* A new session (new token) is issued on every login (rotation). Passwords: Argon2id via
  `argon2-cffi`, rehash on parameter change, 12-character minimum.
* CSRF: a second random token is returned in the login body and in a readable `ayush_csrf`
  cookie; its hash is bound to the session. Unsafe methods require `X-CSRF-Token` matching
  that hash, and any `Origin` header must be in `trusted_origins`.
* CORS is restricted to configured origins; in the shipped setup the browser only talks to
  the Next.js origin, which proxies `/api/v1/*`, so cookies stay first-party.
* Organization context comes from `sessions.active_membership_id`, selected at login (single
  membership) or via `POST /auth/active-organization` (membership verified). Requests can never
  name a tenant directly.
* Login failures return one generic message; 5 failures lock the account for 15 min (same
  message while locked). Per-IP throttling is **not** implemented and should be added at the
  reverse proxy.

**Rejected.** JWTs in localStorage (XSS-exfiltratable, hard to revoke).

**Proxy/HTTPS.** Production must terminate TLS at a reverse proxy, run uvicorn with
`--proxy-headers --forwarded-allow-ips <proxy ip>`, and set `AYUSH_COOKIE_SECURE=true`.
