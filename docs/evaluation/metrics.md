# Measured results

Only numbers actually measured are listed. Environment: macOS (Apple Silicon), Docker Desktop
29.7.2, PostgreSQL 17 (container), Python 3.13.0 local venv, Node 22.20.0. Date: 2026-11-11.

| Measurement | Result | Command |
|---|---|---|
| Backend tests (real PostgreSQL, Alembic-built schema) | 93 passed, 0 failed, 0 skipped (~40 s wall) | `cd apps/api && uv run pytest -q` |
| Frontend unit/component tests | 15 passed, 0 failed | `cd apps/web && npm test` |
| Static checks | ruff: 0 findings; ruff format: clean; mypy `--strict`: 0 errors in 84 files; ESLint: 0; `tsc --noEmit`: 0 | see README "Tests and checks" |
| Migration drift | `alembic check`: no new operations; up→down→up round trip passes | `test_migrations_downgrade_and_upgrade_roundtrip` |
| Scripted synthetic journey, local processes and full container stack | completed: intake (Tamil) → demo red flag → upload → OCR via Celery → verify → cited draft (9 claims, 1 contradiction) → approval | `scripts/demo-journey.sh` |
| Render-like run (production mode, `postgres://` URL, `$PORT`, Secure cookies, in-process jobs, fresh DB) | journey completed; startup recovery resumed a queued summary job | `BASE=http://localhost:3001 scripts/demo-journey.sh` |

| Live Render deployment (free tier) | journey completed against https://ayushcare-web.onrender.com on 2026-11-12 | `BASE=https://ayushcare-web.onrender.com scripts/demo-journey.sh` |

Not measured: code coverage, API latency/throughput, OCR accuracy, summary quality,
accessibility audit, restore time.
