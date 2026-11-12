# Deploying the public synthetic demo on Render (free tier)

`render.yaml` defines two free Docker web services and one free PostgreSQL database, all in
the Singapore region:

| Resource | Purpose |
|---|---|
| `ayushcare-api` | FastAPI. `start.sh` runs `alembic upgrade head` and `seed-demo` (idempotent) when `AYUSH_MIGRATE_ON_START` / `AYUSH_SEED_DEMO_ON_START` are true, then uvicorn on `$PORT`. OCR and summary jobs run in-process (`AYUSH_JOB_DISPATCHER=inprocess`). |
| `ayushcare-web` | Next.js standalone server. `/api/v1/*` is proxied at runtime to `API_INTERNAL_URL`. |
| `ayushcare-db` | PostgreSQL 17 (free). |

## Steps

1. Open https://dashboard.render.com/blueprint/new?repo=https://github.com/pranav-n-05/ayush-care-ai
2. Sign in, connect GitHub if asked, keep the Blueprint name, click **Apply**.
3. When both services are live, check the URLs Render assigned. If they are not
   `https://ayushcare-api.onrender.com` and `https://ayushcare-web.onrender.com` (names
   already taken), update and save:
   * `ayushcare-web` → `API_INTERNAL_URL` = the API's URL
   * `ayushcare-api` → `AYUSH_TRUSTED_ORIGINS` and `AYUSH_CORS_ALLOWED_ORIGINS` =
     `["<web URL>"]`
4. Open the web URL and log in with a demo account from the README.
5. Optional end-to-end check: `BASE=https://<web URL> ./scripts/demo-journey.sh`.

## Free-tier trade-offs

* Services sleep after ~15 minutes idle; the first request takes ~30–60 s (the web shows
  "The API is unavailable (it may be waking up)" if the API is still starting).
* Free PostgreSQL expires after 30 days; upgrade or recreate it (the start command will
  migrate and reseed a new database automatically).
* No persistent disk: uploaded documents are lost on restart/redeploy. Downloads and OCR of
  lost files return clear errors ("Stored file is no longer available").
* In-process jobs run inside the single API instance; jobs left `queued` (or orphaned in
  `running` >10 min) are recovered at startup. For real workloads use a Celery worker
  (`AYUSH_JOB_DISPATCHER=celery` + Redis), as in `docker-compose.yml`.
* `AYUSH_PUBLIC_DEMO=true` allows seeding the synthetic demo accounts in production mode.
  Anyone with the README password can log in; never enter real data.

## Verified before publishing (2026-11-11)

The same images and start command were run locally with Render-like settings
(`AYUSH_ENVIRONMENT=production`, `postgres://` URL, `PORT=10000`, Secure cookies, in-process
jobs, fresh database); `scripts/demo-journey.sh` completed and startup job recovery worked.

## Live deployment (2026-11-12)

* Web: https://ayushcare-web.onrender.com · API: https://ayushcare-api.onrender.com
  (`/health/ready` → database ok). Region: Singapore, free plans.
* `BASE=https://ayushcare-web.onrender.com ./scripts/demo-journey.sh` completed against the live
  services (intake → red flag → upload → OCR → verify → cited draft → approval), and the
  practitioner login reached the dashboard in a browser.
* First deploy failed (exit 127): Render passed the quoted `sh -c` `dockerCommand` as a single
  executable name. Fixed by moving startup steps into `apps/api/start.sh`.
