from fastapi import APIRouter

from app.routers.workforce_handlers import router as handler_router


def domain_router(*endpoint_names: str) -> APIRouter:
    """Build a router from the existing, compatibility-tested handlers."""

    requested = set(endpoint_names)
    router = APIRouter()
    matched = set()

    for route in handler_router.routes:
        if route.name in requested:
            router.routes.append(route)
            matched.add(route.name)

    missing = requested - matched
    if missing:
        raise RuntimeError(
            "Workforce route registry references missing handlers: "
            + ", ".join(sorted(missing))
        )

    return router
