from .registry import domain_router


router = domain_router(
    "list_tasks_page",
    "task_management_summary",
    "get_task_detail",
    "list_tasks",
    "my_tasks",
    "my_tasks_page",
    "my_tasks_summary",
    "create_task",
    "start_task",
    "submit_task",
    "get_task_review_report",
    "review_task",
    "void_task",
    "resolve_task",
)
