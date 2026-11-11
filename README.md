# AyushCare AI

AI-assisted, multilingual patient case-taking and clinical documentation platform, built as a
student portfolio project around the user-supplied SIH26047 (Ministry of AYUSH) problem theme:
structured history collection, document digitization and practitioner-reviewed summaries.

> **Safety disclaimer.** Synthetic data only. Not a medical device, not clinically validated,
> not certified for ABDM, DPDP or any regulation, and not production-ready. AI output is a
> draft that restates cited records; it never diagnoses or prescribes and requires a
> practitioner's approval of a specific version. No affiliation with SIH or the Ministry of
> AYUSH is implied.

## What it does

* **Registration** — DOB or age-with-as-of-date (with precision), clinically relevant sex,
  contact, preferred language (en/hi/ta), identifiers, consent with history, possible-duplicate
  flags (never auto-merged).
* **Adaptive intake** — versioned questionnaires pinned per session; server-side validation,
  explicit branching with cycle detection; `unknown / declined / not applicable` are distinct
  from a "no"; every change is a new revision; original-language text is preserved and
  untranslated/draft-translated text is flagged. Demo Ayurveda template (Ahara, Vihara, Nidra,
  Mala, Mutra, Agni/Koshta, Manasika, Ashtavidha/Dashavidha observations) — no Prakriti inference.
* **Red flags** — deterministic, versioned rules; `not evaluable` when data is missing; demo
  rules are blocked from clinical use by a database constraint.
* **Documents & OCR** — validated uploads, authenticated downloads, idempotent bounded OCR jobs
  (Celery), extracted fields unverified until a reviewer verifies or corrects them.
* **AI documentation** — structured draft (presenting complaint, HPI, history, medications &
  allergies, Ayurveda observations, missing information, contradictions, clarification
  questions); each claim cites `(source, revision)`; fabricated/stale/cross-tenant citations
  are rejected; approval is concurrency-safe and invalidated by later edits or source changes.
* **Practitioner workflow** — dashboard with metric definitions, patient timeline, follow-ups
  with consent-aware, idempotent reminders, analytics with explicit denominators, audit log,
  FHIR R4 Patient export (unvalidated mapping).
* **Multi-tenancy** — organization context comes only from the session; composite tenant
  foreign keys; platform admins and hospital admins get no clinical access.

## Stack

Next.js 16 (App Router) · React 19 · TypeScript · Tailwind 4 · TanStack Query · React Hook Form
· Zod | FastAPI · Pydantic 2 · SQLAlchemy 2 (async, asyncpg) · Alembic · PostgreSQL 17 · Redis ·
Celery · Argon2id | Docker Compose · GitHub Actions. Direct dependencies are pinned
(`apps/api/uv.lock`, `apps/web/package-lock.json`).

## Repository layout

```
apps/api        FastAPI modular monolith, Alembic migrations, Celery worker, pytest suite
apps/web        Next.js app (proxies /api/v1 to the API), Vitest suite
docs/           architecture, ERD, ADRs, permission matrix, safety, threat model, runbook, evaluation
scripts/        demo-journey.sh (scripted synthetic end-to-end journey)
```

## Quick start (local development)

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/) 0.12+, Node 22.

```bash
docker compose up -d db redis

cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed-demo          # synthetic org + demo users
uv run uvicorn app.main:app --reload        # http://localhost:8000/docs
# optional, for OCR/summary jobs: AYUSH_JOB_DISPATCHER=celery in .env, then
uv run celery -A app.workers.celery_app worker --beat --loglevel=INFO

cd ../web
npm ci
npm run dev                                  # http://localhost:3000
```

Deploy a free public demo on Render: see `docs/deployment/render.md` (one-click Blueprint).

Full containerized stack: `docker compose --profile full up -d --build`, then
`docker compose exec api python -m app.cli seed-demo` and `./scripts/demo-journey.sh`.

### Synthetic demo credentials (local only; `seed-demo` refuses to run in production)

Password for all: `Synthetic-Demo-Only-2026`

| Role | Email |
|---|---|
| Hospital administrator | admin@demo.example.org |
| Practitioner | vaidya@demo.example.org |
| Clinical assistant | assistant@demo.example.org |
| Receptionist | frontdesk@demo.example.org |
| Patient (linked to a synthetic record) | patient@demo.example.org |

Platform administrators are created explicitly:
`AYUSH_BOOTSTRAP_PASSWORD=... uv run python -m app.cli bootstrap-platform-admin --email ... --name ...`.

## Tests and checks

```bash
cd apps/api && uv run pytest -q && uv run ruff check app tests migrations && uv run mypy app
cd apps/web && npm run lint && npm run typecheck && npm test && npm run build
```

Backend tests need the compose `db` service (they create and migrate a throwaway
`ayushcare_test` database). Latest measured results: `docs/evaluation/metrics.md`.

## Demo script

Registration → Tamil intake → demo red flag → document upload → OCR → field verification →
AI draft with citations → practitioner approval: `scripts/demo-journey.sh` (API) or the same
steps in the UI (Patients → patient → New encounter → Intake / Documents / Summary tabs).

## Limitations

See `docs/progress.md` (known gaps) and `docs/resume.md` (implemented vs demo-only vs planned).
Highlights: demo OCR reads `.txt` only; the summarizer is a deterministic template, not an LLM;
questionnaire, translations and red-flag rules are unreviewed demos; no antivirus, MFA, password
reset or per-IP rate limiting; no browser e2e tests or screenshots yet.

## License

MIT — see `LICENSE`.
