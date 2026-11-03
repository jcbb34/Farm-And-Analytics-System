from .registry import domain_router


router = domain_router(
    "upload_task_evidence",
    "view_task_evidence",
    "view_task_evidence_thumbnail",
    "view_legacy_workforce_evidence",
)
