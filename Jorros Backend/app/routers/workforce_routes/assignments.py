from .registry import domain_router


router = domain_router(
    "update_task_assignment",
    "task_assignment_history",
)
