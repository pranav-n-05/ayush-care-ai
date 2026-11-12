#!/bin/sh
# Container entrypoint. Optional startup steps for hosts without a pre-deploy hook
# (e.g. Render free tier): AYUSH_MIGRATE_ON_START=true runs Alembic migrations;
# AYUSH_SEED_DEMO_ON_START=true seeds the synthetic demo (idempotent; refused in
# production unless AYUSH_PUBLIC_DEMO=true). The app itself never creates tables.
set -e
if [ "${AYUSH_MIGRATE_ON_START:-false}" = "true" ]; then
  alembic upgrade head
fi
if [ "${AYUSH_SEED_DEMO_ON_START:-false}" = "true" ]; then
  python -m app.cli seed-demo
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
