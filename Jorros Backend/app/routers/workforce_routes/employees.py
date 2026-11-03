from .registry import domain_router


router = domain_router(
    "get_my_employee_profile",
    "list_farm_positions",
    "list_employees",
    "repair_employee_account_links",
    "get_employee_work_assignments",
    "get_employee_work_schedule",
    "update_employee_work_schedule",
    "create_employee",
    "update_employee",
    "change_employee_status",
    "archive_employee",
    "restore_employee",
)
