# Clinical safety boundaries

This is a **student portfolio project using synthetic data**. It is not a medical device, is
not clinically validated, and must not be used with real patients.

| Boundary | How it is enforced | Evidence |
|---|---|---|
| AI never diagnoses/prescribes | demo provider only restates sources; validator language guard; disclaimer in every draft | `test_validator_rejections` |
| Drafts until approved | summaries start `draft`; approval needs `summary.approve` + attestation; edits create new drafts | `test_approval_flow_and_new_edit_requires_reapproval` |
| Traceability | every claim cites `(kind, id, revision)`; fabricated, stale or cross-tenant citations rejected | `test_invalid_model_output_never_becomes_a_summary`, `test_validator_rejections` |
| Patient-reported vs observed | answers carry `source`; claim provenance must match | `test_end_to_end_draft_with_citations` |
| Originals preserved | answers and OCR reviews are append-only revisions; original language text kept | `test_intake_branching_validation_and_revisions`, `test_entity_review_creates_revisions` |
| OCR unverified until reviewed | only `verified`/`corrected` entities are citable | `test_end_to_end_draft_with_citations` |
| Red flags deterministic, demo rules disabled for clinical use | pure engine + DB constraint | `test_demo_red_flag_rules`, `test_demo_rules_cannot_be_enabled_clinically` |
| Missing ≠ absent | explicit `unknown/declined/not_applicable`; hidden = `not_asked`; rules `not_evaluable` | intake/triage tests |
| No Prakriti/Vikriti inference | only practitioner free-text/status fields; no scoring code exists | `seed_definition.py` |
| Untrusted input is data | sources JSON-encoded in prompts; no tool execution; injection text appears only as quoted patient data | `test_prompt_encodes_untrusted_text_as_data`, e2e test |
| Approval race | row lock + unique constraint | `test_concurrent_approvals_only_one_succeeds` |
| Stale approval | approval refused if sources changed since the version was generated | `test_source_change_blocks_approval` |
| Consent for AI | generation refused without `ai_assisted_documentation` consent | `test_generation_requires_ai_consent` |

Not reviewed by any clinician: the questionnaire, its Hindi/Tamil drafts, the demo red-flag
rules, the severity labels, and the demo summary wording. All need qualified review before any
non-demo use.
