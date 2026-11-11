"""seed roles and permissions (frozen snapshot of app/modules/identity/permissions.py)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    "analytics.read",
    "audit.read",
    "consent.record",
    "dashboard.read",
    "document.download",
    "document.read",
    "document.upload",
    "encounter.create",
    "encounter.read",
    "encounter.update",
    "fhir.export",
    "followup.manage",
    "followup.read",
    "intake.answer",
    "intake.read",
    "intake.review",
    "ocr.process",
    "ocr.verify",
    "org.manage_members",
    "org.manage_settings",
    "org.view_members",
    "patient.create",
    "patient.read",
    "patient.update",
    "questionnaire.manage",
    "self.read_own_record",
    "summary.approve",
    "summary.edit",
    "summary.generate",
    "summary.read",
    "triage.acknowledge",
    "triage.manage_rules",
    "triage.read",
]

ROLES = {
    "hospital_admin": (
        "Hospital administrator",
        [
            "analytics.read",
            "audit.read",
            "dashboard.read",
            "org.manage_members",
            "org.manage_settings",
            "org.view_members",
        ],
    ),
    "receptionist": (
        "Receptionist",
        [
            "consent.record",
            "dashboard.read",
            "document.upload",
            "encounter.create",
            "encounter.read",
            "followup.manage",
            "followup.read",
            "patient.create",
            "patient.read",
            "patient.update",
        ],
    ),
    "clinical_assistant": (
        "Clinical assistant",
        [
            "consent.record",
            "dashboard.read",
            "document.download",
            "document.read",
            "document.upload",
            "encounter.create",
            "encounter.read",
            "followup.manage",
            "followup.read",
            "intake.answer",
            "intake.read",
            "ocr.process",
            "ocr.verify",
            "patient.create",
            "patient.read",
            "patient.update",
            "summary.read",
            "triage.read",
        ],
    ),
    "practitioner": (
        "Practitioner",
        [
            "analytics.read",
            "consent.record",
            "dashboard.read",
            "document.download",
            "document.read",
            "document.upload",
            "encounter.create",
            "encounter.read",
            "encounter.update",
            "fhir.export",
            "followup.manage",
            "followup.read",
            "intake.answer",
            "intake.read",
            "intake.review",
            "ocr.process",
            "ocr.verify",
            "patient.create",
            "patient.read",
            "patient.update",
            "questionnaire.manage",
            "summary.approve",
            "summary.edit",
            "summary.generate",
            "summary.read",
            "triage.acknowledge",
            "triage.manage_rules",
            "triage.read",
        ],
    ),
    "patient": ("Patient", ["self.read_own_record"]),
}


def upgrade() -> None:
    conn = op.get_bind()
    perm_ids = {}
    for code in PERMISSIONS:
        pid = uuid.uuid4()
        perm_ids[code] = pid
        conn.execute(
            sa.text("INSERT INTO permissions (id, code, description) VALUES (:id, :code, :d)"),
            {"id": pid, "code": code, "d": code.replace(".", ": ").replace("_", " ")},
        )
    for code, (name, role_perms) in ROLES.items():
        rid = uuid.uuid4()
        conn.execute(
            sa.text("INSERT INTO roles (id, code, name) VALUES (:id, :code, :name)"),
            {"id": rid, "code": code, "name": name},
        )
        for p in role_perms:
            conn.execute(
                sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
                {"r": rid, "p": perm_ids[p]},
            )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions")
    op.execute("DELETE FROM roles")
    op.execute("DELETE FROM permissions")
