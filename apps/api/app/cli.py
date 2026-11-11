"""Operational commands.

python -m app.cli bootstrap-platform-admin --email admin@example.org --name "Ops"
    Password is read from AYUSH_BOOTSTRAP_PASSWORD or prompted; refuses if any platform
    admin already exists. No default credentials exist.

python -m app.cli seed-demo
    Creates a SYNTHETIC demo organization with one user per role. Refuses in production.
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import dispose_engine, session_scope
from app.modules.identity.models import (
    Organization,
    OrganizationMembership,
    PatientUserLink,
    Role,
    User,
)
from app.modules.identity.permissions import R

DEMO_PASSWORD = "Synthetic-Demo-Only-2026"  # noqa: S105 - documented synthetic demo credential
DEMO_USERS = [
    ("admin@demo.example.org", "Asha Admin (synthetic)", R.HOSPITAL_ADMIN),
    ("vaidya@demo.example.org", "Dr. Vaidya Demo (synthetic)", R.PRACTITIONER),
    ("assistant@demo.example.org", "Chitra Assistant (synthetic)", R.CLINICAL_ASSISTANT),
    ("frontdesk@demo.example.org", "Ravi Reception (synthetic)", R.RECEPTIONIST),
]


async def bootstrap_platform_admin(email: str, name: str, password: str) -> None:
    async with session_scope() as db:
        if await db.scalar(select(User).where(User.is_platform_admin)):
            raise SystemExit("A platform administrator already exists; refusing to create another.")
        db.add(
            User(
                email=email.strip().lower(),
                full_name=name,
                password_hash=hash_password(password),
                is_platform_admin=True,
            )
        )
    print("Platform administrator created.")


async def seed_demo() -> None:
    if get_settings().environment == "production":
        raise SystemExit("seed-demo is disabled in production")
    from app.modules.intake.seed import seed_demo_questionnaire
    from app.modules.patients.models import ConsentEvent, ConsentRecord, Patient
    from app.modules.triage.seed import seed_demo_rules

    async with session_scope() as db:
        if await db.scalar(select(Organization).where(Organization.slug == "demo-ayurveda-clinic")):
            print("Demo organization already exists.")
            return
        org = Organization(name="Demo Ayurveda Clinic (synthetic)", slug="demo-ayurveda-clinic")
        db.add(org)
        await db.flush()
        await seed_demo_questionnaire(db, org.id)
        await seed_demo_rules(db, org.id)
        roles = {r.code: r for r in (await db.scalars(select(Role))).all()}
        users = {}
        for email, name, role in DEMO_USERS:
            u = User(email=email, full_name=name, password_hash=hash_password(DEMO_PASSWORD))
            db.add(u)
            await db.flush()
            m = OrganizationMembership(organization_id=org.id, user_id=u.id)
            m.roles = [roles[role.value]]
            db.add(m)
            users[role] = u
        import datetime as dt

        practitioner = users[R.PRACTITIONER]
        samples = [
            ("Meera", "Synthetic", dt.date(1988, 4, 12), "female", "+919000000001", "ta"),
            ("Arjun", "Testcase", dt.date(1975, 9, 30), "male", "+919000000002", "hi"),
        ]
        patients: list[Patient] = []
        for given, family, dob, sex, phone, lang in samples:
            p = Patient(
                organization_id=org.id,
                record_number=f"AYU-DEMO{len(patients) + 1:04d}",
                given_name=given,
                family_name=family,
                birth_date=dob,
                birth_date_precision="exact",
                sex_for_clinical_use=sex,
                phone=phone,
                preferred_language=lang,
                created_by_user_id=practitioner.id,
            )
            db.add(p)
            await db.flush()
            for ctype in ("data_processing", "ai_assisted_documentation", "contact_reminders"):
                rec = ConsentRecord(
                    organization_id=org.id, patient_id=p.id, consent_type=ctype, status="granted"
                )
                db.add(rec)
                await db.flush()
                db.add(
                    ConsentEvent(
                        organization_id=org.id,
                        consent_record_id=rec.id,
                        status="granted",
                        method="written",
                        recorded_by_user_id=practitioner.id,
                    )
                )
            patients.append(p)
        pu = User(
            email="patient@demo.example.org",
            full_name="Meera Synthetic",
            password_hash=hash_password(DEMO_PASSWORD),
        )
        db.add(pu)
        await db.flush()
        pm = OrganizationMembership(organization_id=org.id, user_id=pu.id)
        pm.roles = [roles[R.PATIENT.value]]
        db.add(pm)
        db.add(PatientUserLink(organization_id=org.id, user_id=pu.id, patient_id=patients[0].id))
    print("Seeded synthetic demo organization. Demo users (password documented in README):")
    for email, _, role in DEMO_USERS:
        print(f"  {role.value:20s} {email}")
    print(f"  {'patient':20s} patient@demo.example.org")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap-platform-admin")
    b.add_argument("--email", required=True)
    b.add_argument("--name", required=True)
    sub.add_parser("seed-demo")
    args = parser.parse_args()

    async def run() -> None:
        try:
            if args.cmd == "bootstrap-platform-admin":
                pw = os.environ.get("AYUSH_BOOTSTRAP_PASSWORD") or getpass.getpass("Password: ")
                await bootstrap_platform_admin(args.email, args.name, pw)
            else:
                await seed_demo()
        finally:
            await dispose_engine()

    try:
        asyncio.run(run())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
