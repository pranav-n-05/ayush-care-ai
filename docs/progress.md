# Progress log

## 2026-11-11 — Phases 0–6 baseline (single working session)

Repository started empty (README + LICENSE). Built backend, frontend, infrastructure and docs.

### Verified (commands executed, see docs/evaluation/metrics.md)
* Backend: 82 pytest tests pass on PostgreSQL 17; ruff, ruff-format, mypy --strict clean;
  Alembic up/down/up + `alembic check` clean.
* Frontend: 12 Vitest tests; ESLint, `tsc --noEmit`, `next build` pass.
* `docker compose --profile full up --build` starts db, redis, migrate, api, worker(+beat), web;
  `scripts/demo-journey.sh` completes against it; container logs contain no synthetic clinical text.

### Bugs found by verification and fixed
* Blank age parsed as 0 in the patient form (Vitest).
* JSON `null` stored for non-answers, violating the value-iff-answered constraint (pytest).
* Document list returned 200 for another tenant's encounter instead of 404 (tenancy test).
* Language guard flagged quoted patient text and question wording (summary test).
* uvicorn access log recorded search query strings, e.g. patient names (smoke run) → replaced
  with path-only structured access log.
* Worker image missing `packaging` (container run); Next.js rewrites baked to localhost
  (container run) → build arg.

### Not done / known gaps
* Password-reset flow (table exists only), MFA, per-IP rate limiting, break-glass access.
* Triage rule authoring/approval API; summary-job sweeper and stuck-`running` reclaim.
* Real OCR/LLM/translation/speech providers; antivirus.
* Browser end-to-end tests (Playwright) and an accessibility audit; screenshots not captured.
* Patient merge workflow (duplicates are flagged only).
* CI workflow written but not yet run on GitHub (repository not pushed).

### Next bounded task
Add Playwright e2e for the core journey + axe accessibility checks, then the password-reset flow.
