"""Backward-compatible workforce API facade.

All public URLs remain under ``/api/v1/workforce``. Route ownership is split by
domain in :mod:`app.routers.workforce_routes`; handler re-exports below preserve
existing imports used by integrations and the regression suite.
"""

from fastapi import APIRouter

from app.routers import workforce_handlers as _handlers
from app.routers.workforce_handlers import *  # noqa: F401,F403
from app.routers.workforce_routes import DOMAIN_ROUTERS


router = APIRouter()
for domain in DOMAIN_ROUTERS:
    router.routes.extend(domain.routes)

if {getattr(route, "name", None) for route in router.routes if getattr(route, "name", None)} != {
    getattr(route, "name", None)
    for route in _handlers.router.routes
    if getattr(route, "name", None)
}:
    raise RuntimeError("Workforce domain routers do not cover the compatibility API exactly.")


# Compatibility hooks for callers that patch the facade's farm clock in unit
# tests. Production route dispatch calls the original handlers directly.
farm_today = _handlers.farm_today
_require_workforce_access = _handlers._require_workforce_access
_require_manager = _handlers._require_manager
_manager = _handlers._manager


def _sync_compatibility_hooks() -> None:
    """Forward patched legacy hooks to the domain handler module.

    Some internal callers imported endpoint functions directly from this
    compatibility module and patched its clock or authorization helpers. Keep
    those integrations working while HTTP dispatch uses the split routers.
    """

    _handlers.farm_today = farm_today
    _handlers._require_workforce_access = _require_workforce_access
    _handlers._require_manager = _require_manager
    _handlers._manager = _manager


def _call_with_compatibility_hooks(handler, *args, **kwargs):
    """Apply legacy monkey-patches only for the duration of one direct call.

    Older tests and internal integrations patch symbols on this facade.  The
    split handler module must see those patches while the call is running, but
    keeping them installed afterwards leaks a mocked clock or authorization
    helper into unrelated requests handled by another route.
    """

    previous = (
        _handlers.farm_today,
        _handlers._require_workforce_access,
        _handlers._require_manager,
        _handlers._manager,
    )
    _sync_compatibility_hooks()
    try:
        return handler(*args, **kwargs)
    finally:
        (
            _handlers.farm_today,
            _handlers._require_workforce_access,
            _handlers._require_manager,
            _handlers._manager,
        ) = previous


def start_task(*args, **kwargs):
    return _call_with_compatibility_hooks(_handlers.start_task, *args, **kwargs)


def submit_task(*args, **kwargs):
    return _call_with_compatibility_hooks(_handlers.submit_task, *args, **kwargs)


def create_task(*args, **kwargs):
    return _call_with_compatibility_hooks(_handlers.create_task, *args, **kwargs)


def update_task_assignment(*args, **kwargs):
    return _call_with_compatibility_hooks(_handlers.update_task_assignment, *args, **kwargs)


def upsert_attendance(*args, **kwargs):
    return _call_with_compatibility_hooks(_handlers.upsert_attendance, *args, **kwargs)


def cancel_leave(*args, **kwargs):
    return _call_with_compatibility_hooks(_handlers.cancel_leave, *args, **kwargs)
