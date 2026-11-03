from app.models.role import Role
from app.models.user import User
from app.models.void_operation import VoidOperation
from app.models.login_history import LoginHistory
from app.models.creation_command import FarmCreationCommand
from app.models.code_counter import CodeCounter
from app.models.scheduler_status import SchedulerStatus
from app.models.change_event import FarmChangeEvent
from app.models.farm_event import FarmEvent, FarmEventTask, FarmEventAcknowledgement, FarmEventAudit, FarmEventReport

from app.models.crop import (
    Crop,
    CropGrowthRecord,
    CropYieldRecord,
    CropPestDisease,
)

from app.models.livestock import (
    Livestock,
    LivestockPen,
    LivestockTransaction,
    LivestockVaccinationRecord,
    LivestockReproductionRecord,
    LivestockProductionRecord,
    LivestockFeedingRecord,
    LivestockGrowthRecord,
    LivestockGrowthProfile,
    LivestockGrowthProfileStage,
    LivestockGrowthStageOverrideAudit,
)

from app.models.inventory import (
    InventoryItem,
    InventoryStockRecord,
)
from app.models.resource_usage import ResourceUsage

from app.models.activity import FarmActivity

from app.models.workforce import (
    Employee,
    FarmPosition,
    EmployeePosition,
    EmployeeWorkSchedule,
    EmployeeWorkScheduleDay,
    TaskAssignmentHistory,
    TaskSubmission,
    TaskEvidence,
    StaffAttendance,
    StaffAttendanceAudit,
    AttendanceSettings,
    StaffLeave,
    TaskLeaveCoverage,
    StaffShift,
    CareTemplate,
    CareTemplateStep,
)

from app.models.alert import (
    FarmAlert,
    AlertSettings,
)

from app.models.report import (
    FarmReport,
    ReportAutomationSettings,
)

from app.models.backup import SystemBackup

from app.models.audit_log import AuditLog
from app.models.weather_history import WeatherHistory

from app.models.import_batch import (
    DataImportBatch,
    DataImportRow,
)


from app.models.production_sale import (
    LivestockSale,
    LivestockSaleItem,
    LivestockSalePayment,
    LivestockProcessingRecord,
)

__all__ = [
    "Role",
    "User",
    "LoginHistory",
    "FarmCreationCommand",
    "CodeCounter",
    "SchedulerStatus",
    "FarmChangeEvent",
    "FarmEvent", "FarmEventTask", "FarmEventAcknowledgement", "FarmEventAudit", "FarmEventReport",
    "Crop",
    "CropGrowthRecord",
    "CropYieldRecord",
    "CropPestDisease",
    "Livestock",
    "LivestockPen",
    "LivestockTransaction",
    "LivestockVaccinationRecord",
    "LivestockReproductionRecord",
    "LivestockProductionRecord",
    "LivestockFeedingRecord",
    "LivestockGrowthRecord",
    "LivestockGrowthProfile",
    "LivestockGrowthProfileStage",
    "LivestockGrowthStageOverrideAudit",
    "InventoryItem",
    "InventoryStockRecord",
    "ResourceUsage",
    "FarmActivity",
    "CareTemplateStep",
    "CareTemplate",
    "StaffLeave",
    "TaskLeaveCoverage",
    "StaffShift",
    "StaffAttendance",
    "StaffAttendanceAudit",
    "AttendanceSettings",
    "TaskSubmission",
    "TaskEvidence",
    "Employee",
    "FarmPosition",
    "EmployeePosition",
    "EmployeeWorkSchedule",
    "EmployeeWorkScheduleDay",
    "TaskAssignmentHistory",
    "FarmAlert",
    "AlertSettings",
    "FarmReport",
    "ReportAutomationSettings",
    "SystemBackup",
    "AuditLog",
    "WeatherHistory",
    "DataImportBatch",
    "DataImportRow",
    "LivestockSale",
    "LivestockSaleItem",
    "LivestockSalePayment",
    "LivestockProcessingRecord",
]

# Import after all mapped classes have been registered.
from app.services.change_events import install_change_events
install_change_events()
