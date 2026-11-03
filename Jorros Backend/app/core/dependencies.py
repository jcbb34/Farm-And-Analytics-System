from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.models import User
from app.routers.auth import get_current_user


TASK_ONLY_WORKFORCE_PERMISSION = "workforce:submit"
TASK_ONLY_ELEVATED_PERMISSIONS = {
    "*",
    "workforce:manage",
    "workforce:review",
    "workforce:attendance",
}


def permissions_are_task_only(permissions) -> bool:
    permission_set = set(permissions or [])
    return (
        TASK_ONLY_WORKFORCE_PERMISSION in permission_set
        and not permission_set.intersection(TASK_ONLY_ELEVATED_PERMISSIONS)
    )


def is_task_only_user(user: User) -> bool:
    """Return True for employee-style accounts based on capabilities, not role names.

    A task-only account has task submission permission but no workforce-wide
    management/review/attendance authority.  This also safely constrains legacy
    Employee/Farm Staff roles whose stored permission JSON may still contain old
    broad view/settings permissions.
    """
    return permissions_are_task_only(user.permissions)


def has_permission(user: User, permission: str) -> bool:
    permissions = set(user.permissions or [])
    if "*" in permissions:
        return True
    if is_task_only_user(user):
        return permission == TASK_ONLY_WORKFORCE_PERMISSION
    return permission in permissions


def require_permission(permission: str) -> Callable:
    def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}.",
            )
        return current_user

    return dependency


def require_administrator(
    current_user: User = Depends(get_current_user),
) -> User:
    if not has_permission(current_user, "*"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System Administrator access is required.",
        )

    return current_user
