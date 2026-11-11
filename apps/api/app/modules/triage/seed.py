import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.triage.models import TriageRule, TriageRuleVersion

# DEMO ONLY: illustrative rules written without clinical review. The database constraint
# `demo_never_clinical` prevents enabling these for clinical use.
DEMO_RULES = [
    {
        "code": "demo_chest_pain_breathless",
        "name": "Chest pain with breathlessness or sweating (DEMO)",
        "condition": {
            "all": [
                {"question": "chest_pain", "op": "is_true"},
                {"question": "chest_pain_breathless", "op": "is_true"},
            ]
        },
        "severity": "demo_urgent_review",
        "reason": "Patient reports chest pain with breathlessness or sweating (demo rule, not clinically validated).",
    },
    {
        "code": "demo_high_severity",
        "name": "Self-reported severity 9 or 10 (DEMO)",
        "condition": {"all": [{"question": "severity", "op": "gte", "value": 9}]},
        "severity": "demo_prompt_review",
        "reason": "Patient rates severity at 9 or above (demo rule, not clinically validated).",
    },
    {
        "code": "demo_unplanned_weight_loss",
        "name": "Unplanned weight loss reported (DEMO)",
        "condition": {
            "all": [{"question": "associated_symptoms", "op": "contains", "value": "weight_loss"}]
        },
        "severity": "demo_review",
        "reason": "Patient reports unplanned weight loss (demo rule, not clinically validated).",
    },
]


async def seed_demo_rules(db: AsyncSession, org_id: uuid.UUID) -> None:
    for spec in DEMO_RULES:
        rule = TriageRule(organization_id=org_id, code=spec["code"], name=spec["name"])
        db.add(rule)
        await db.flush()
        db.add(
            TriageRuleVersion(
                organization_id=org_id,
                rule_id=rule.id,
                version_number=1,
                condition=spec["condition"],
                severity=spec["severity"],
                reason=spec["reason"],
                status="demo_only",
                clinical_use_enabled=False,
            )
        )
    await db.flush()
