from .registry import domain_router


router = domain_router(
    "list_care_templates",
    "create_care_template",
    "update_care_template",
    "copy_care_template",
    "publish_care_template",
    "deactivate_care_template",
    "import_care_protocols",
    "import_care_protocols_csv",
    "match_care_protocols",
    "generate_care_tasks",
)
