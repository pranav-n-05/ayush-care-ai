# Deployment runbook

> Local Compose proves the stack runs together. It does **not** prove encryption at rest,
> backup coverage, high availability or production readiness.

## Local full stack (containers)

```bash
docker compose --profile full up -d --build     # db, redis, migrate (one-shot), api, worker(+beat), web
docker compose exec api python -m app.cli seed-demo
./scripts/demo-journey.sh                        # scripted synthetic journey through the web proxy
open http://localhost:3000
```

Migrations run in the `migrate` service (`alembic upgrade head`) before `api` starts. The API
never creates tables at startup.

## Production checklist (not performed for this project)

* TLS at a reverse proxy; uvicorn `--proxy-headers --forwarded-allow-ips=<proxy>`.
* `AYUSH_ENVIRONMENT=production` (settings refuse dev DB credentials, insecure cookies and the
  inline dispatcher), `AYUSH_COOKIE_SECURE=true`, explicit `AYUSH_CORS_ALLOWED_ORIGINS` and
  `AYUSH_TRUSTED_ORIGINS`.
* Secrets from a secret manager, never from compose files. Rotate the DB password.
* PostgreSQL and Redis on private networks only; never publish their ports.
* Least privilege: app role without DDL; separate migration role; no `UPDATE/DELETE` on
  `audit_events` for the app role. Storage credentials scoped to one bucket/prefix.
* Encryption at rest via the managed database / volume / object store.
* Replace `LocalFileStorage` with an object store and an antivirus scanning step before
  releasing documents.
* Build the web image with `API_INTERNAL_URL` set (Next.js rewrites are resolved at build time).
* Per-IP rate limiting for `/api/v1/auth/*` at the proxy.
* Monitoring: `/health/live` (process), `/health/ready` (bounded DB check, 503 on failure),
  Celery `inspect ping`, structured JSON logs (paths only, no query strings or payloads).

## Backup and restore

```bash
# backup (custom format, compressed)
docker compose exec -T db pg_dump -U ayushcare -Fc ayushcare > backup-$(date +%F).dump
# restore into a fresh database
docker compose exec -T db createdb -U ayushcare ayushcare_restore
docker compose exec -T db pg_restore -U ayushcare -d ayushcare_restore --no-owner < backup-YYYY-MM-DD.dump
```

Documents live in the `storage` volume and must be backed up together with the database
(document rows reference storage keys and SHA-256 checksums; downloads verify the checksum).
A restore drill has **not** been executed and timed for this project; production use requires
encrypted backups, documented retention aligned with the privacy policy, and periodic restore
tests.
