import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.timeutil import utcnow
from app.modules.audit.service import add_audit
from app.modules.identity.access import OrgContext
from app.modules.triage.engine import Outcome, evaluate
from app.modules.triage.models import TriageEvent, TriageRule, TriageRuleVersion

if TYPE_CHECKING:
    from app.modules.intake.service import LoadedSession


async def active_rule_versions(db: AsyncSession, org_id: uuid.UUID) -> list[TriageRuleVersion]:
    """Latest active, non-retired version of each rule."""
    rows = (
        await db.scalars(
            select(TriageRuleVersion)
            .where(
                TriageRuleVersion.organization_id == org_id,
                TriageRuleVersion.is_active,
                TriageRuleVersion.status != "retired",
            )
            .order_by(TriageRuleVersion.rule_id, TriageRuleVersion.version_number.desc())
        )
    ).all()
    latest: dict[uuid.UUID, TriageRuleVersion] = {}
    for rv in rows:
        latest.setdefault(rv.rule_id, rv)
    return list(latest.values())


async def evaluate_session(db: AsyncSession, loaded: "LoadedSession") -> dict[str, int]:
    org_id = loaded.session.organization_id
    answers = loaded.answer_map()
    counts = {o.value: 0 for o in Outcome}
    for rv in await active_rule_versions(db, org_id):
        outcome, trigger_code = evaluate(rv.condition, answers)
        counts[outcome.value] += 1
        if outcome is not Outcome.TRIGGERED or trigger_code is None:
            continue
        q = loaded.questions[trigger_code]
        ans = loaded.current[q.id]
        await db.execute(
            insert(TriageEvent)
            .values(
                id=uuid.uuid4(),
                organization_id=org_id,
                encounter_id=loaded.session.encounter_id,
                rule_version_id=rv.id,
                intake_answer_id=ans.id,
                answer_revision=ans.revision,
                severity=rv.severity,
                reason=rv.reason,
                is_demo_rule=rv.status == "demo_only",
                status="open",
                evaluated_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["rule_version_id", "intake_answer_id"])
        )
    return counts


async def rule_coverage(db: AsyncSession, loaded: "LoadedSession") -> list[dict[str, str]]:
    """Per-rule outcome for display, so 'not evaluable' is visible rather than hidden."""
    answers = loaded.answer_map()
    out = []
    for rv in await active_rule_versions(db, loaded.session.organization_id):
        outcome, _ = evaluate(rv.condition, answers)
        out.append(
            {
                "rule_version_id": str(rv.id),
                "severity": rv.severity,
                "status": rv.status,
                "outcome": outcome.value,
            }
        )
    return out


async def list_events(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    encounter_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[TriageEvent]:
    stmt = select(TriageEvent).where(TriageEvent.organization_id == org_id)
    if encounter_id:
        stmt = stmt.where(TriageEvent.encounter_id == encounter_id)
    if status:
        stmt = stmt.where(TriageEvent.status == status)
    return list((await db.scalars(stmt.order_by(TriageEvent.evaluated_at.desc()).limit(200))).all())


_TRANSITIONS = {
    "acknowledge": ({"open"}, "acknowledged"),
    "escalate": ({"open", "acknowledged"}, "escalated"),
    "resolve": ({"open", "acknowledged", "escalated"}, "resolved"),
}
RESOLUTION_CODES = {
    "addressed_in_consultation",
    "referred",
    "not_applicable_after_review",
    "duplicate",
}


async def transition_event(
    db: AsyncSession, ctx: OrgContext, event_id: uuid.UUID, action: str, resolution_code: str | None
) -> TriageEvent:
    ev = await db.scalar(
        select(TriageEvent)
        .where(TriageEvent.id == event_id, TriageEvent.organization_id == ctx.organization_id)
        .with_for_update()
    )
    if ev is None:
        raise NotFound("Triage event not found")
    allowed_from, target = _TRANSITIONS[action]
    if ev.status not in allowed_from:
        raise Conflict(f"Cannot {action} an event that is {ev.status}")
    now = utcnow()
    if action == "acknowledge":
        ev.acknowledged_by_user_id, ev.acknowledged_at = ctx.user_id, now
    elif action == "escalate":
        ev.escalated_at = now
        ev.acknowledged_by_user_id = ev.acknowledged_by_user_id or ctx.user_id
        ev.acknowledged_at = ev.acknowledged_at or now
    else:
        if resolution_code not in RESOLUTION_CODES:
            raise ValidationFailed(f"resolution_code must be one of {sorted(RESOLUTION_CODES)}")
        ev.resolved_by_user_id, ev.resolved_at, ev.resolution_code = (
            ctx.user_id,
            now,
            resolution_code,
        )
    ev.status = target
    add_audit(
        db,
        action=f"triage.{action}",
        organization_id=ctx.organization_id,
        actor_user_id=ctx.user_id,
        entity_type="triage_event",
        entity_id=ev.id,
    )
    await db.commit()
    return ev


async def list_rules(
    db: AsyncSession, org_id: uuid.UUID
) -> list[tuple[TriageRule, TriageRuleVersion]]:
    rows = await active_rule_versions(db, org_id)
    rules = {
        r.id: r
        for r in (
            await db.scalars(select(TriageRule).where(TriageRule.organization_id == org_id))
        ).all()
    }
    return [(rules[rv.rule_id], rv) for rv in rows]
