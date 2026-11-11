"""Import every model so Alembic autogenerate and metadata see the full schema."""

from app.modules.audit.models import AuditEvent  # noqa: F401
from app.modules.documents.models import Document, DocumentVersion  # noqa: F401
from app.modules.encounters.models import Encounter  # noqa: F401
from app.modules.followups.models import FollowUpTask, Notification  # noqa: F401
from app.modules.identity.models import (  # noqa: F401
    Clinic,
    Invitation,
    Organization,
    OrganizationMembership,
    PasswordResetToken,
    PatientUserLink,
    Permission,
    Role,
    User,
    UserSession,
)
from app.modules.intake.models import (  # noqa: F401
    IntakeAnswer,
    IntakeSession,
    Question,
    QuestionnaireTemplate,
    QuestionnaireVersion,
)
from app.modules.ocr.models import ExtractedEntity, OCRJob  # noqa: F401
from app.modules.patients.models import (  # noqa: F401
    ConsentEvent,
    ConsentRecord,
    Patient,
    PatientIdentifier,
)
from app.modules.summaries.models import (  # noqa: F401
    ClinicalSummary,
    SummaryApproval,
    SummaryJob,
    SummaryVersion,
)
from app.modules.triage.models import TriageEvent, TriageRule, TriageRuleVersion  # noqa: F401
