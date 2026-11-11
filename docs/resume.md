# Resume material (verified capabilities only)

**AyushCare AI | Full-Stack & AI Engineering Project (portfolio, synthetic data)**
Next.js, TypeScript, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Redis, Celery, Docker

- Built a multi-tenant FastAPI/PostgreSQL backend for practitioner-reviewed patient intake with
  a versioned questionnaire engine (conditional branching, cycle detection, revisioned answers,
  explicit unknown/declined states) and English/Hindi/Tamil rendering.
- Implemented opaque server-side sessions (Argon2id, hashed tokens, CSRF + origin checks,
  idle/absolute expiry, revocation) and a database-seeded RBAC matrix with organization-scoped
  authorization enforced by service checks and composite tenant foreign keys; covered by
  82 backend tests on real PostgreSQL.
- Developed an OCR → reviewer-verification → AI-draft pipeline with idempotent, bounded Celery
  jobs; drafts are structured outputs whose every claim must cite an existing source revision,
  and approval binds a practitioner to an immutable version under row-level locking.

## Status of features

| Implemented & tested | Demo-only | Planned / not implemented |
|---|---|---|
| auth, sessions, invitations, RBAC, tenancy, audit | demo questionnaire + Hindi/Tamil drafts (unreviewed) | password reset flow, MFA, per-IP rate limiting |
| patients, consent, duplicate flags, encounters | demo red-flag rules (DB-blocked from clinical use) | rule authoring/approval API |
| intake engine, triage engine | demo text "OCR" provider (.txt only) | PaddleOCR / image OCR |
| documents, OCR jobs, entity review | deterministic demo summarizer (no LLM) | real LLM provider + evaluation |
| summaries, citations, approval, follow-ups | demo notification provider (log only) | antivirus scanning, speech/translation providers |
| dashboard, analytics, FHIR Patient export (unvalidated) | | ABDM sandbox work, FHIR validation, e2e browser tests |

Do not claim: SIH participation/selection, ministry partnership, ABDM/DPDP compliance,
clinical validation, production deployment, or usage metrics.
