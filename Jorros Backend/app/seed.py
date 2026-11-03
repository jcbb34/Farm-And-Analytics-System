from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Role, User


ROLES = [
    {
        "name": "System Administrator",
        "description": "Complete access to all JoRoss Farm modules.",
    },
    {
        "name": "Manager",
        "description": "Manages farm operations, employee tasks, reviews, attendance, and records.",
    },
    {
        "name": "Employee",
        "description": "Uses My Tasks and submits assigned farm work for review.",
    },
    {
        "name": "Farm Staff",
        "description": "Legacy employee role; uses the employee task workflow.",
    },
    {
        "name": "Viewer",
        "description": "Can view farm records and reports only.",
    },
]


def seed_database():
    db = SessionLocal()

    try:
        for role_data in ROLES:
            existing_role = db.scalar(
                select(Role).where(Role.name == role_data["name"])
            )

            if existing_role is None:
                db.add(Role(**role_data))

        db.commit()

        administrator_role = db.scalar(
            select(Role).where(Role.name == "System Administrator")
        )

        if administrator_role is None:
            raise RuntimeError("System Administrator role could not be created.")

        admin_username = settings.seed_admin_username.strip().lower() or "admin"
        admin = db.scalar(
            select(User).where(User.username == admin_username)
        )

        if admin is None:
            password = settings.seed_admin_password.strip()
            if not password:
                raise RuntimeError(
                    "SEED_ADMIN_PASSWORD is required in Jorros Backend/.env "
                    "before seeding a fresh database."
                )

            admin = User(
                user_code="USR-1001",
                full_name=settings.seed_admin_full_name.strip() or "System Administrator",
                username=admin_username,
                email=settings.seed_admin_email.strip(),
                contact_number=settings.seed_admin_contact_number.strip(),
                position=settings.seed_admin_position.strip() or "Farm Administrator",
                password_hash=hash_password(password),
                status="Active",
                role_id=administrator_role.id,
            )

            db.add(admin)
            db.commit()
            print("Administrator created.")
        else:
            print("Administrator already exists.")

        print("Database seed completed.")

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
