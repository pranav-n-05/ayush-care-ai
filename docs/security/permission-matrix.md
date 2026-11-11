# Permission matrix

Source of truth: `apps/api/app/modules/identity/permissions.py`. Migration `0002` seeds the
database; `tests/test_authorization.py::test_database_roles_match_code_matrix` asserts they match.
Roles attach to an **organization membership**, never to the global user.

| Permission | Hospital admin | Practitioner | Clinical assistant | Receptionist | Patient |
|---|:-:|:-:|:-:|:-:|:-:|
| org.view_members / org.manage_members / org.manage_settings | ✓ | | | | |
| audit.read | ✓ | | | | |
| analytics.read | ✓ | ✓ | | | |
| dashboard.read | ✓ | ✓ | ✓ | ✓ | |
| patient.read / create / update, consent.record | | ✓ | ✓ | ✓ | |
| encounter.read / create | | ✓ | ✓ | ✓ | |
| encounter.update | | ✓ | | | |
| questionnaire.manage | | ✓ | | | |
| intake.read / intake.answer | | ✓ | ✓ | | |
| intake.review (practitioner fields, post-submit edits, mark reviewed) | | ✓ | | | |
| document.upload | | ✓ | ✓ | ✓ | |
| document.read / document.download | | ✓ | ✓ | | |
| ocr.process / ocr.verify | | ✓ | ✓ | | |
| summary.read | | ✓ | ✓ | | |
| summary.generate / summary.edit / summary.approve | | ✓ | | | |
| triage.read | | ✓ | ✓ | | |
| triage.acknowledge / triage.manage_rules | | ✓ | | | |
| followup.read / followup.manage | | ✓ | ✓ | ✓ | |
| fhir.export | | ✓ | | | |
| self.read_own_record | | | | | ✓ |

Notes and policies:

* **Platform administrator** is a user flag (`users.is_platform_admin`), not a role. It allows
  `POST /api/v1/platform/organizations` only. It grants no membership and therefore no clinical
  permission; exceptional clinical access would require a separate, audited break-glass policy
  that is **not implemented**.
* **Hospital administrators** have no clinical-content permissions by design.
* Administrators may assign only staff roles (`hospital_admin`, `practitioner`,
  `clinical_assistant`, `receptionist`). They cannot change their own roles or deactivate
  themselves. Deactivating a member revokes sessions bound to that membership.
* Clinical assistants can verify OCR transcription (`ocr.verify`). This is a transcription-
  accuracy check, not a clinical judgement; organizations may want to restrict it further.
* Every denial is written to `audit_events` (`authorization.denied`) in an independent
  transaction so it survives the request rollback.
