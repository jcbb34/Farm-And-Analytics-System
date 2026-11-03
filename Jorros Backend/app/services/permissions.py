DEFAULT_ROLE_PERMISSIONS = {
    "System Administrator": ["*"],
    "Administrator": ["*"],
    "Admin": ["*"],
    "Owner": ["*"],
    "Manager": [
        "dashboard:view",
        "crops:view", "crops:create", "crops:update", "crops:archive", "crops:export",
        "livestock:view", "livestock:create", "livestock:update", "livestock:archive", "livestock:export",
        "production_sales:view", "production_sales:update",
        "inventory:view", "inventory:create", "inventory:update", "inventory:adjust", "inventory:archive", "inventory:export",
        "alerts:view", "alerts:create", "alerts:update", "alerts:test",
        "reports:view", "reports:create", "reports:update", "reports:export",
        "intelligence:view", "intelligence:update",
        "activities:view", "activities:create", "activities:update",
        "workforce:view", "workforce:manage", "workforce:review", "workforce:attendance",
        "imports:preview", "imports:commit", "weather:view",
        "settings:view", "settings:profile", "notifications:view",
    ],
    "Employee": [
        "workforce:submit",
    ],
    # Legacy role follows the same task-only workflow.
    "Farm Staff": [
        "workforce:submit",
    ],
    "Viewer": [
        "dashboard:view", "crops:view", "crops:export", "livestock:view", "livestock:export",
        "production_sales:view", "inventory:view", "inventory:export", "alerts:view",
        "reports:view", "reports:export", "intelligence:view", "activities:view",
        "weather:view", "settings:view", "settings:profile", "notifications:view",
    ],
}


def default_permissions_for_role(role_name: str | None) -> list[str]:
    return list(DEFAULT_ROLE_PERMISSIONS.get(str(role_name or "").strip(), []))


def normalize_permissions(permissions) -> list[str]:
    return sorted({str(item).strip() for item in (permissions or []) if str(item).strip()})
