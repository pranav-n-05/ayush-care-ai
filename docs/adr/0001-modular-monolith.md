# ADR 0001: Modular monolith

Status: Accepted (2026-11-11)

**Context.** Small team (one student developer), shared transactional data (patients,
encounters, answers, summaries) and strong consistency needs (approvals, tenant integrity).

**Decision.** One FastAPI codebase split into domain modules under `app/modules/*`, each with
models, service and routes. One Celery worker from the same codebase for long-running jobs.

**Consequences.** Single deploy unit and single database transaction boundary; module
boundaries are enforced by convention (services call other modules' services, not their
tables). Splitting later would require replacing in-process calls with APIs.
