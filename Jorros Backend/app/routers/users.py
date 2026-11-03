from app.routers.archives import ArchiveRequest
from app.services.archive_service import change_archive_state, permanent_delete
from app.services.personal_details import apply_personal_details
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.dependencies import is_task_only_user, permissions_are_task_only, require_administrator
from app.routers.auth import get_current_user
from app.core.security import hash_password
from app.models import Role, User
from app.services.db_concurrency import acquire_transaction_lock
from app.schemas.auth import UserResponse
from app.schemas.users import UserCreate, UserProfileUpdate, UserUpdate


router = APIRouter(
    prefix="/api/v1/users",
    tags=["Users"],
)


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_user_or_404(
    user_id: int,
    db: Session,
) -> User:
    statement = (
        select(User)
        .options(
            joinedload(User.role)
        )
        .where(
            User.id == user_id
        )
    )

    user = db.scalar(statement)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user


def get_role_or_404(
    role_name: str,
    db: Session,
) -> Role:
    role = db.scalar(
        select(Role).where(
            Role.name == role_name
        )
    )

    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role.",
        )

    if not role.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role is inactive.",
        )

    return role


def generate_user_code(
    db: Session,
) -> str:
    acquire_transaction_lock(db, "code:user")
    highest_id = db.scalar(
        select(
            func.max(User.id)
        )
    )

    next_id = int(
        highest_id or 0
    ) + 1

    return f"USR-{1000 + next_id}"


# =========================================================
# UPDATE OWN PROFILE
# =========================================================

@router.put(
    "/me",
    response_model=UserResponse,
)
def update_own_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    changes = payload.model_dump(exclude_unset=True)

    if "username" in changes:
        username = changes["username"].strip().lower()
        duplicate = db.scalar(
            select(User).where(
                func.lower(User.username) == username,
                User.id != current_user.id,
            )
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",
            )
        current_user.username = username

    if "email" in changes:
        email_value = changes["email"]
        email = str(email_value).strip().lower() if email_value is not None else None
        if email is None and not is_task_only_user(current_user):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is optional only for employee accounts.",
            )
        if email:
            duplicate = db.scalar(
                select(User).where(
                    func.lower(User.email) == email,
                    User.id != current_user.id,
                )
            )
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email address already exists.",
                )
        current_user.email = email

    apply_personal_details(current_user, changes)
    if "full_name" in changes:
        current_user.full_name = changes["full_name"].strip()

    if "contact_number" in changes:
        current_user.contact_number = changes["contact_number"]

    if "position" in changes:
        current_user.position = changes["position"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update account information.",
        )

    return get_user_or_404(current_user.id, db)


# =========================================================
# GET ALL USERS
# =========================================================

@router.get(
    "",
    response_model=list[UserResponse],
)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(
        require_administrator
    ),
):
    statement = (
        select(User)
        .options(
            joinedload(User.role)
        )
        .order_by(User.id)
    )

    return list(
        db.scalars(statement).all()
    )


# =========================================================
# GET ONE USER
# =========================================================

@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_administrator
    ),
):
    return get_user_or_404(
        user_id,
        db,
    )


# =========================================================
# CREATE USER
# =========================================================

@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_administrator
    ),
):
    username = (
        payload.username
        .strip()
        .lower()
    )

    email = (
        str(payload.email).strip().lower()
        if payload.email is not None
        else None
    )

    existing_username = db.scalar(
        select(User).where(
            func.lower(User.username)
            == username
        )
    )

    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists.",
        )

    role = get_role_or_404(
        payload.role_name,
        db,
    )

    if email is None and not permissions_are_task_only(role.permissions):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is optional only for employee accounts.",
        )

    if email:
        existing_email = db.scalar(
            select(User).where(
                func.lower(User.email) == email
            )
        )
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email address already exists.",
            )

    user = User(
        user_code=generate_user_code(
            db
        ),
        full_name=(
            payload.full_name
            .strip()
        ),
        username=username,
        email=email,
        contact_number=(
            payload.contact_number
        ),
        position=(
            payload.position
        ),
        password_hash=hash_password(
            payload.password
        ),
        status="Active",
        role_id=role.id,
    )

    apply_personal_details(user, payload.model_dump(exclude_unset=True))
    db.add(user)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Unable to create user. "
                "Username, email, or user code "
                "already exists."
            ),
        )

    return get_user_or_404(
        user.id,
        db,
    )


# =========================================================
# UPDATE USER
# =========================================================

@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_administrator
    ),
):
    user = get_user_or_404(
        user_id,
        db,
    )

    changes = payload.model_dump(
        exclude_unset=True
    )

    if user.status == "Archived":
        raise HTTPException(409, "Archived user accounts are read-only. Restore the account first.")
    if changes.get("status") == "Archived" and user.id != current_user.id:
        raise HTTPException(409, "Use the Archive action and provide an archive reason.")

    requested_role = None
    if "role_name" in changes:
        requested_role = get_role_or_404(
            changes["role_name"],
            db,
        )

    # Prevent administrator from disabling
    # or archiving their own account.
    if (
        current_user.id == user.id
        and changes.get("status")
        in {
            "Disabled",
            "Archived",
        }
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "You cannot disable or archive "
                "your own account."
            ),
        )

    # Prevent any wildcard administrator (including custom admin roles)
    # from accidentally removing their own administrative access.
    if (
        current_user.id == user.id
        and requested_role is not None
        and "*" not in set(requested_role.permissions or [])
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "You cannot remove your own administrator access."
            ),
        )

    # Username
    if "username" in changes:
        username = (
            changes["username"]
            .strip()
            .lower()
        )

        duplicate = db.scalar(
            select(User).where(
                func.lower(
                    User.username
                ) == username,
                User.id != user.id,
            )
        )

        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists.",
            )

        user.username = username

    # Email
    if "email" in changes:
        email_value = changes["email"]
        email = str(email_value).strip().lower() if email_value is not None else None
        target_role = requested_role or user.role
        if email is None and target_role and not permissions_are_task_only(target_role.permissions):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is optional only for employee accounts.",
            )
        if email:
            duplicate = db.scalar(
                select(User).where(
                    func.lower(User.email) == email,
                    User.id != user.id,
                )
            )
            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email address already exists.",
                )
        user.email = email

    apply_personal_details(user, changes)

    # Full name
    if "full_name" in changes:
        user.full_name = (
            changes["full_name"]
            .strip()
        )

    # Contact number
    if "contact_number" in changes:
        user.contact_number = (
            changes["contact_number"]
        )

    # Position
    if "position" in changes:
        user.position = (
            changes["position"]
        )

    # Password
    if "password" in changes:
        user.password_hash = (
            hash_password(
                changes["password"]
            )
        )
        # An administrator password reset must revoke tokens issued before
        # the reset, just like the self-service change-password flow.
        user.auth_version = int(user.auth_version or 0) + 1

    # Role
    if requested_role is not None:
        if not permissions_are_task_only(requested_role.permissions) and not user.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Add an email before changing this account to a non-employee role.",
            )
        user.role_id = requested_role.id

    # Status
    if "status" in changes:
        allowed_statuses = {
            "Active",
            "Disabled",
            "Archived",
        }

        if (
            changes["status"]
            not in allowed_statuses
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid account status.",
            )

        next_status = changes["status"]
        if next_status in {"Disabled", "Archived"} and user.status != next_status:
            user.auth_version = int(user.auth_version or 0) + 1
        user.status = next_status

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update user.",
        )

    return get_user_or_404(
        user.id,
        db,
    )


# =========================================================
# ARCHIVE USER
# =========================================================

@router.post(
    "/{user_id}/archive",
    response_model=UserResponse,
)
def archive_user(
    user_id: int,
    payload: ArchiveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_administrator
    ),
):
    record = change_archive_state(db, "User", user_id, current_user, archive=True, reason=payload.reason)
    db.commit()
    db.refresh(record)
    return get_user_or_404(record.id, db)


# =========================================================
# RESTORE USER
# =========================================================

@router.post(
    "/{user_id}/restore",
    response_model=UserResponse,
)
def restore_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_administrator
    ),
):
    record = change_archive_state(db, "User", user_id, _, archive=False)
    db.commit()
    db.refresh(record)
    return get_user_or_404(record.id, db)


# =========================================================
# DISABLE USER
# =========================================================

@router.post(
    "/{user_id}/disable",
    response_model=UserResponse,
)
def disable_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_administrator
    ),
):
    user = get_user_or_404(
        user_id,
        db,
    )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "You cannot disable "
                "your own account."
            ),
        )

    user.status = "Disabled"
    user.auth_version = int(user.auth_version or 0) + 1

    db.commit()

    return get_user_or_404(
        user.id,
        db,
    )


# =========================================================
# ACTIVATE USER
# =========================================================

@router.post(
    "/{user_id}/activate",
    response_model=UserResponse,
)
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_administrator
    ),
):
    user = get_user_or_404(
        user_id,
        db,
    )

    user.status = "Active"

    db.commit()

    return get_user_or_404(
        user.id,
        db,
    )