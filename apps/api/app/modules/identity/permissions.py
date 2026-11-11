"""Authoritative permission matrix. The migration seeds roles/permissions from this module and
a test asserts the database matches it. Authorization reads the database at request time."""

from enum import StrEnum


class P(StrEnum):
    ORG_VIEW_MEMBERS = "org.view_members"
    ORG_MANAGE_MEMBERS = "org.manage_members"
    ORG_MANAGE_SETTINGS = "org.manage_settings"
    AUDIT_READ = "audit.read"
    ANALYTICS_READ = "analytics.read"
    DASHBOARD_READ = "dashboard.read"
    PATIENT_READ = "patient.read"
    PATIENT_CREATE = "patient.create"
    PATIENT_UPDATE = "patient.update"
    CONSENT_RECORD = "consent.record"
    ENCOUNTER_READ = "encounter.read"
    ENCOUNTER_CREATE = "encounter.create"
    ENCOUNTER_UPDATE = "encounter.update"
    QUESTIONNAIRE_MANAGE = "questionnaire.manage"
    INTAKE_READ = "intake.read"
    INTAKE_ANSWER = "intake.answer"
    INTAKE_REVIEW = "intake.review"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_READ = "document.read"
    DOCUMENT_DOWNLOAD = "document.download"
    OCR_PROCESS = "ocr.process"
    OCR_VERIFY = "ocr.verify"
    SUMMARY_READ = "summary.read"
    SUMMARY_GENERATE = "summary.generate"
    SUMMARY_EDIT = "summary.edit"
    SUMMARY_APPROVE = "summary.approve"
    TRIAGE_READ = "triage.read"
    TRIAGE_ACKNOWLEDGE = "triage.acknowledge"
    TRIAGE_MANAGE_RULES = "triage.manage_rules"
    FOLLOWUP_READ = "followup.read"
    FOLLOWUP_MANAGE = "followup.manage"
    FHIR_EXPORT = "fhir.export"
    SELF_READ_OWN_RECORD = "self.read_own_record"


DESCRIPTIONS: dict[P, str] = {p: p.value.replace(".", ": ").replace("_", " ") for p in P}


class R(StrEnum):
    HOSPITAL_ADMIN = "hospital_admin"
    PRACTITIONER = "practitioner"
    CLINICAL_ASSISTANT = "clinical_assistant"
    RECEPTIONIST = "receptionist"
    PATIENT = "patient"


ROLE_NAMES: dict[R, str] = {
    R.HOSPITAL_ADMIN: "Hospital administrator",
    R.PRACTITIONER: "Practitioner",
    R.CLINICAL_ASSISTANT: "Clinical assistant",
    R.RECEPTIONIST: "Receptionist",
    R.PATIENT: "Patient",
}

_FRONT_DESK = {
    P.DASHBOARD_READ,
    P.PATIENT_READ,
    P.PATIENT_CREATE,
    P.PATIENT_UPDATE,
    P.CONSENT_RECORD,
    P.ENCOUNTER_READ,
    P.ENCOUNTER_CREATE,
    P.DOCUMENT_UPLOAD,
    P.FOLLOWUP_READ,
    P.FOLLOWUP_MANAGE,
}

MATRIX: dict[R, frozenset[P]] = {
    # Administration only: no clinical-content permissions.
    R.HOSPITAL_ADMIN: frozenset(
        {
            P.ORG_VIEW_MEMBERS,
            P.ORG_MANAGE_MEMBERS,
            P.ORG_MANAGE_SETTINGS,
            P.AUDIT_READ,
            P.ANALYTICS_READ,
            P.DASHBOARD_READ,
        }
    ),
    R.RECEPTIONIST: frozenset(_FRONT_DESK),
    R.CLINICAL_ASSISTANT: frozenset(
        _FRONT_DESK
        | {
            P.INTAKE_READ,
            P.INTAKE_ANSWER,
            P.DOCUMENT_READ,
            P.DOCUMENT_DOWNLOAD,
            P.OCR_PROCESS,
            P.OCR_VERIFY,
            P.SUMMARY_READ,
            P.TRIAGE_READ,
        }
    ),
    R.PRACTITIONER: frozenset(
        _FRONT_DESK
        | {
            P.ENCOUNTER_UPDATE,
            P.QUESTIONNAIRE_MANAGE,
            P.INTAKE_READ,
            P.INTAKE_ANSWER,
            P.INTAKE_REVIEW,
            P.DOCUMENT_READ,
            P.DOCUMENT_DOWNLOAD,
            P.OCR_PROCESS,
            P.OCR_VERIFY,
            P.SUMMARY_READ,
            P.SUMMARY_GENERATE,
            P.SUMMARY_EDIT,
            P.SUMMARY_APPROVE,
            P.TRIAGE_READ,
            P.TRIAGE_ACKNOWLEDGE,
            P.TRIAGE_MANAGE_RULES,
            P.ANALYTICS_READ,
            P.FHIR_EXPORT,
        }
    ),
    R.PATIENT: frozenset({P.SELF_READ_OWN_RECORD}),
}

# Roles a hospital administrator may assign. Nobody can assign roles via public endpoints,
# and administrators cannot grant themselves additional roles (enforced in the service).
ASSIGNABLE_BY_ADMIN = frozenset(
    {R.HOSPITAL_ADMIN, R.PRACTITIONER, R.CLINICAL_ASSISTANT, R.RECEPTIONIST}
)
