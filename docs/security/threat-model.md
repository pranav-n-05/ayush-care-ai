# Threat model (STRIDE summary)

Scope: web app, API, worker, PostgreSQL, Redis, object storage. Assets: synthetic patient
records, answers, documents, summaries, credentials/sessions, audit trail.

| Threat | Example | Mitigation implemented | Residual / not implemented |
|---|---|---|---|
| Spoofing | credential stuffing | Argon2id, generic errors, account lockout, timing-equalized lookup | no per-IP rate limit, no MFA |
| Spoofing | stolen session | HttpOnly cookie, hashed at rest, idle + absolute expiry, revocation | no device binding |
| Tampering | CSRF | session-bound CSRF token + Origin allowlist + SameSite=Lax | — |
| Tampering | cross-tenant write | tenant from session only; service checks; composite FKs | — |
| Tampering | approval race / lost update | row locks, version checks, unique constraints, `lock_version` on patients | — |
| Tampering | malicious upload | allowlist, magic bytes, size/page/dimension limits, PDF active-content rejection, opaque keys, `attachment` + `nosniff` + sandbox CSP on download | **no antivirus**; files released as `passed_validation_only` |
| Repudiation | denied/altered actions | audit events with actor, org, entity, outcome, correlation ID | audit table is ordinary and mutable (see audit.md) |
| Information disclosure | logs | redacting logger; access log omits query strings; audit details reject sensitive keys | Next.js/proxy logs must be configured separately |
| Information disclosure | IDOR | every lookup filters by session org; 404 for other tenants | — |
| Information disclosure | external AI | no external provider; org approval gate | — |
| DoS | huge uploads / slow queries | bounded reads, statement timeout, pool limits | no global rate limiting |
| Elevation | role self-assignment | admins can't edit own roles; assignable-role allowlist; platform admin has no clinical access | no break-glass workflow |
| Prompt injection | instructions in answers/OCR | JSON-encoded sources, no tools, output validation, practitioner approval | a real LLM may still produce misleading but cited text; human review is the control |
