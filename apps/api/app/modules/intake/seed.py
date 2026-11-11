import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.intake.seed_definition import DEMO_DEFINITION
from app.modules.intake.service import create_template_with_draft, publish_version_unchecked


async def seed_demo_questionnaire(db: AsyncSession, org_id: uuid.UUID) -> uuid.UUID:
    """Creates and publishes the demo questionnaire (clinical_review_status=demo_unreviewed)."""
    version = await create_template_with_draft(db, org_id, DEMO_DEFINITION)
    await publish_version_unchecked(db, version, publisher_user_id=None)
    return version.id
