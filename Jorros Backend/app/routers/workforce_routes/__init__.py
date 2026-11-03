"""Domain-owned route registries for the backward-compatible workforce API."""

from .assignments import router as assignments_router
from .attendance_leave import router as attendance_leave_router
from .care_protocols import router as care_protocols_router
from .employees import router as employees_router
from .evidence import router as evidence_router
from .resource_posting import router as resource_posting_router
from .task_lifecycle import router as task_lifecycle_router


DOMAIN_ROUTERS = (
    evidence_router,
    employees_router,
    task_lifecycle_router,
    assignments_router,
    attendance_leave_router,
    care_protocols_router,
    resource_posting_router,
)


__all__ = ["DOMAIN_ROUTERS"]
