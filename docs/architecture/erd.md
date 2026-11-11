# Entity relationship overview

All tables use UUID primary keys and timezone-aware timestamps. Tenant-owned tables carry
`organization_id`; arrows below are composite `(organization_id, id)` foreign keys unless noted.

```mermaid
erDiagram
  organizations ||--o{ clinics : has
  organizations ||--o{ organization_memberships : has
  users ||--o{ organization_memberships : "global identity"
  organization_memberships }o--o{ roles : membership_roles
  roles }o--o{ permissions : role_permissions
  users ||--o{ sessions : has
  organizations ||--o{ invitations : issues
  users ||--o{ password_reset_tokens : "schema only"
  patients ||--o{ patient_identifiers : has
  patients ||--o{ consent_records : has
  consent_records ||--o{ consent_events : history
  patients ||--o| patient_user_links : "patient self-access"
  patients ||--o{ encounters : has
  questionnaire_templates ||--o{ questionnaire_versions : versions
  questionnaire_versions ||--o{ questions : "materialized at publish"
  encounters ||--o{ intake_sessions : has
  questionnaire_versions ||--o{ intake_sessions : "pinned to"
  intake_sessions ||--o{ intake_answers : "revisions"
  questions ||--o{ intake_answers : answers
  triage_rules ||--o{ triage_rule_versions : versions
  triage_rule_versions ||--o{ triage_events : produces
  intake_answers ||--o{ triage_events : triggers
  encounters ||--o{ documents : has
  documents ||--o{ document_versions : versions
  document_versions ||--o{ ocr_jobs : processed_by
  ocr_jobs ||--o{ extracted_entities : extracts
  encounters ||--o| clinical_summaries : has
  clinical_summaries ||--o{ summary_versions : "immutable versions"
  summary_versions ||--o| summary_approvals : approved_by
  encounters ||--o{ summary_jobs : jobs
  patients ||--o{ follow_up_tasks : has
  follow_up_tasks ||--o{ notifications : "one per idempotency key"
  organizations ||--o{ audit_events : records
```

## Notable constraints

| Constraint | Purpose |
|---|---|
| `uq_intake_answers_current` (partial unique on `is_current`) | exactly one current revision per question |
| `ck_intake_answers_value_iff_answered` | value present only when `answer_status = answered`; unknown/declined/not-applicable are explicit states |
| `ck_triage_rule_versions_demo_never_clinical` | demo rules can never be enabled for clinical use |
| `ck_triage_rule_versions_approval_required` | clinical use requires a recorded approver |
| `uq_summary_approvals_summary_version_id` | one approval per immutable version (approval race backstop) |
| `uq_clinical_summaries_organization_id` + `encounter_id` | one summary lineage per encounter |
| `uq_ocr_jobs_…_idempotency_key`, `uq_summary_jobs_…` | idempotent job submission |
| `uq_notifications_idempotency_key` | duplicate-send prevention |
| `ck_patients_birth_date_or_age` | DOB or (age + as-of date) recorded with precision |

## Deletion semantics

No clinical table cascades deletes. Foreign keys to users/patients/encounters are `RESTRICT`.
Patients are deactivated, never deleted, until a reviewed retention policy exists
(see `docs/security/privacy-and-retention.md`). Only session/membership-role join rows cascade.
