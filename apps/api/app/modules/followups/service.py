import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.logging import get_logger
from app.core.timeutil import utcnow
from app.db.session import session_scope
from app.modules.audit.service import add_audit
from app.modules.encounters.service import get_encounter
from app.modules.followups.models import FollowUpTask, Notification
from app.modules.identity.access import OrgContext
from app.modules.patients.models import Patient
from app.modules.patients.service import consent_status, get_patient

log = get_logger("followups")
# Generic, non-clinical template. No diagnosis, medication or complaint text is ever included.
TEMPLATE = "follow_up_reminder_v1"


async def create_task(
    db: AsyncSession,
    ctx: OrgContext,
    patient_id: uuid.UUID,
    encounter_id: uuid.UUID | None,
    due_at: datetime,
    channel: str,
) -> FollowUpTask:
    await get_patient(db, ctx.organization_id, patient_id)
    if encounter_id:
        enc = await get_encounter(db, ctx.organization_id, encounter_id)
        if enc.patient_id != patient_id:
            raise ValidationFailed("Encounter belongs to a different patient")
    if due_at.tzinfo is None:
        raise ValidationFailed("due_at must include a timezone")
    task = FollowUpTask(
        organization_id=ctx.organization_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        due_at=due_at,
        channel=channel,
        created_by_user_id=ctx.user_id,
    )
    db.add(task)
    await db.flush()
    add_audit(
        db,
        action="followup.created",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="follow_up_task",
        entity_id=task.id,
    )
    await db.commit()
    return task


async def list_tasks(
    db: AsyncSession, org_id: uuid.UUID, patient_id: uuid.UUID | None, status: str | None
) -> list[FollowUpTask]:
    stmt = select(FollowUpTask).where(FollowUpTask.organization_id == org_id)
    if patient_id:
        stmt = stmt.where(FollowUpTask.patient_id == patient_id)
    if status:
        stmt = stmt.where(FollowUpTask.status == status)
    return list((await db.scalars(stmt.order_by(FollowUpTask.due_at).limit(200))).all())


async def set_task_status(
    db: AsyncSession, ctx: OrgContext, task_id: uuid.UUID, status: str
) -> FollowUpTask:
    task = await db.scalar(
        select(FollowUpTask).where(
            FollowUpTask.id == task_id, FollowUpTask.organization_id == ctx.organization_id
        )
    )
    if task is None:
        raise NotFound("Follow-up task not found")
    if task.status != "scheduled":
        raise Conflict("Only scheduled tasks can change status")
    task.status = status
    add_audit(
        db,
        action=f"followup.{status}",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="follow_up_task",
        entity_id=task.id,
    )
    await db.commit()
    return task


async def notifications_for(
    db: AsyncSession, org_id: uuid.UUID, task_id: uuid.UUID
) -> list[Notification]:
    return list(
        (
            await db.scalars(
                select(Notification)
                .where(
                    Notification.organization_id == org_id,
                    Notification.follow_up_task_id == task_id,
                )
                .order_by(Notification.created_at)
            )
        ).all()
    )


class DemoNotificationProvider:
    """DEMO: records delivery without contacting anyone."""

    name = "demo-log-only"

    def send(self, channel: str, destination: str, template_code: str) -> None:
        log.info("demo_notification_sent", channel=channel, template=template_code)


_notifier = DemoNotificationProvider()


async def dispatch_due_reminders(now: datetime | None = None) -> dict[str, int]:
    """Idempotent: the reminder for a task has one key, so re-runs never double-send."""
    now = now or utcnow()
    counts = {"sent": 0, "skipped_no_consent": 0, "skipped_no_contact": 0, "already_handled": 0}
    async with session_scope() as db:
        tasks = (
            await db.scalars(
                select(FollowUpTask)
                .where(FollowUpTask.status == "scheduled", FollowUpTask.due_at <= now)
                .limit(500)
            )
        ).all()
        work = [(t.id, t.organization_id, t.patient_id, t.channel) for t in tasks]
    for task_id, org_id, patient_id, channel in work:
        key = f"reminder:{task_id}"
        async with session_scope() as db:
            res = await db.execute(
                insert(Notification)
                .values(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    follow_up_task_id=task_id,
                    idempotency_key=key,
                    channel=channel,
                    template_code=TEMPLATE,
                    status="pending",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(Notification.id)
            )
            notif_id = res.scalar()
            if notif_id is None:
                counts["already_handled"] += 1
                continue
        async with session_scope() as db:
            notif = await db.get(Notification, notif_id, with_for_update=True)
            patient = await db.get(Patient, patient_id)
            assert notif is not None and patient is not None and patient.organization_id == org_id
            notif.attempts += 1
            notif.provider = _notifier.name
            consent = await consent_status(db, org_id, patient_id, "contact_reminders")
            destination = patient.email if channel == "email" else patient.phone
            if consent != "granted":
                notif.status = "skipped_no_consent"
            elif not destination:
                notif.status = "skipped_no_contact"
            else:
                try:
                    _notifier.send(channel, destination, TEMPLATE)
                    notif.status, notif.sent_at = "sent", utcnow()
                except Exception as exc:  # noqa: BLE001 - provider failure is recorded, not raised
                    notif.status, notif.last_error = "failed", type(exc).__name__
            counts[notif.status] = counts.get(notif.status, 0) + 1
            add_audit(
                db,
                action="notification.processed",
                organization_id=org_id,
                actor_user_id=None,
                entity_type="notification",
                entity_id=notif.id,
                details={"status": notif.status},
            )
    return counts
