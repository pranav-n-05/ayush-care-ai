import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.request_context import get_correlation_id
from app.db.session import session_scope
from app.modules.audit.models import AuditEvent

# Keys that must never appear in audit details (clinical payloads, credentials).
_FORBIDDEN = {"password", "token", "value", "text", "answer", "content", "name", "phone", "email"}


def _clean(details: dict[str, Any] | None) -> dict[str, Any]:
    if not details:
        return {}
    bad = [k for k in details if k.lower() in _FORBIDDEN]
    if bad:
        raise ValueError(f"Audit details may not contain sensitive keys: {bad}")
    return details


def add_audit(
    db: AsyncSession,
    *,
    action: str,
    organization_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    outcome: str = "success",
    details: dict[str, Any] | None = None,
) -> None:
    """Stage an audit event in the caller's transaction (commits atomically with the action)."""
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            correlation_id=get_correlation_id(),
            details=_clean(details),
        )
    )


async def record_audit_independently(**kwargs: Any) -> None:
    """For denials/failures: persist even though the request transaction will roll back."""
    async with session_scope() as db:
        add_audit(db, **kwargs)
