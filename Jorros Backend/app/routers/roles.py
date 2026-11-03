from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_administrator
from app.models import Role, User
from app.schemas.auth import RoleResponse
from app.schemas.roles import RoleCreate, RoleUpdate


router = APIRouter(
    prefix="/api/v1/roles",
    tags=["Roles"],
)


PROTECTED_ROLES = {
    "System Administrator",
    "Manager",
    "Employee",
    "Farm Staff",
    "Viewer",
}


def get_role_or_404(role_id: int, db: Session) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found.",
        )
    return role


@router.get(
    "",
    response_model=list[RoleResponse],
)
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_administrator),
):
    statement = (
        select(Role)
        .where(Role.is_active == True)
        .order_by(Role.id)
    )
    return list(db.scalars(statement).all())


@router.post(
    "",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_administrator),
):
    name = payload.name.strip()
    existing = db.scalar(
        select(Role).where(func.lower(Role.name) == name.lower())
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A role with that name already exists.",
        )

    role = Role(
        name=name,
        description=(payload.description or "").strip() or None,
        is_active=True,
    )
    role.set_permissions(payload.permissions)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.put(
    "/{role_id}",
    response_model=RoleResponse,
)
def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_administrator),
):
    role = get_role_or_404(role_id, db)
    changes = payload.model_dump(exclude_unset=True)

    if role.name == "System Administrator" and "permissions" in changes:
        permissions = changes["permissions"] or []
        if "*" not in permissions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="System Administrator must retain full access.",
            )

    if (
        role.id == current_user.role_id
        and "permissions" in changes
        and "*" not in set(changes["permissions"] or [])
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove administrator access from your own active role.",
        )

    if (
        role.id == current_user.role_id
        and changes.get("is_active") is False
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot disable your own active administrator role.",
        )

    if "name" in changes:
        new_name = changes["name"].strip()
        if role.name in PROTECTED_ROLES and new_name != role.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Built-in roles cannot be renamed.",
            )
        duplicate = db.scalar(
            select(Role).where(
                func.lower(Role.name) == new_name.lower(),
                Role.id != role.id,
            )
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A role with that name already exists.",
            )
        role.name = new_name

    if "description" in changes:
        role.description = (changes["description"] or "").strip() or None

    if "permissions" in changes:
        role.set_permissions(changes["permissions"] or [])

    if "is_active" in changes:
        next_active = bool(changes["is_active"])
        if role.name in PROTECTED_ROLES and not next_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Built-in roles cannot be disabled.",
            )
        if role.is_active and not next_active:
            # Invalidate sessions now so tokens cannot become valid again if
            # this role is re-enabled later.
            assigned_users = list(
                db.scalars(
                    select(User).where(User.role_id == role.id)
                ).all()
            )
            for assigned_user in assigned_users:
                assigned_user.auth_version = int(assigned_user.auth_version or 0) + 1
        role.is_active = next_active

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to update role.",
        )

    db.refresh(role)
    return role


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_administrator),
):
    role = get_role_or_404(role_id, db)

    if role.name in PROTECTED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Built-in roles cannot be deleted.",
        )

    assigned_users = db.scalar(
        select(func.count(User.id)).where(User.role_id == role.id)
    ) or 0
    if assigned_users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reassign users before deleting this role.",
        )

    role.is_active = False
    db.commit()
