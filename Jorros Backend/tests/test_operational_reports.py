import json
import os
import sys
import unittest
from unittest.mock import patch
from datetime import date, datetime, time, timedelta
from types import ModuleType

from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret")

try:
    import pyodbc  # noqa: F401
except ModuleNotFoundError:
    class _TestBase(DeclarativeBase):
        pass
    database_module = ModuleType("app.core.database")
    database_module.Base = _TestBase
    database_module.get_db = lambda: iter((None,))
    sys.modules.setdefault("app.core.database", database_module)

from app.core.database import Base
from app.core.farm_time import farm_today, farm_now_naive
from app.models import (  # noqa: F401
    Crop, CropYieldRecord, Employee, EmployeeWorkSchedule, EmployeeWorkScheduleDay,
    FarmActivity, FarmReport, InventoryItem, InventoryStockRecord, Livestock,
    LivestockProductionRecord, LivestockSale, ReportAutomationSettings, ResourceUsage,
    StaffAttendance, StaffLeave, TaskAssignmentHistory, TaskSubmission,
)
from app.services.operational_report_builder import build_operational_report_snapshot
from app.services.report_query import build_report_list_statement
from app.services.report_csv import build_report_csv
from app.services.report_generation_service import create_report_record
from app.services.report_scheduler import (
    _candidate_periods, _latest_daily, _period_key, _report_status,
    attendance_schema_missing_columns, run_due_report_automation,
)
from app.services.report_pdf import _operational_main, _styles, generate_report_pdf


class OperationalReportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        today = farm_today()
        this_monday = today - timedelta(days=today.weekday())
        self.week_start = this_monday - timedelta(days=7)
        self.week_end = self.week_start + timedelta(days=6)
        self.day = self.week_start
        self.employee = Employee(
            employee_code="EMP-RPT-1", full_name="Report Worker", employment_status="Active",
            date_hired=self.week_start - timedelta(days=30), is_archived=False,
        )
        self.backup = Employee(
            employee_code="EMP-RPT-2", full_name="Backup Worker", employment_status="Active",
            date_hired=self.week_start - timedelta(days=30), is_archived=False,
        )
        self.db.add_all([self.employee, self.backup]); self.db.flush()
        self._schedule(self.employee); self._schedule(self.backup)
        self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def _schedule(self, employee):
        schedule = EmployeeWorkSchedule(
            employee_id=employee.id, effective_from=self.week_start - timedelta(days=30),
            timezone="Asia/Manila", schedule_type="Fixed", status="Active",
        )
        self.db.add(schedule); self.db.flush()
        for dow in range(7):
            working = dow < 5
            self.db.add(EmployeeWorkScheduleDay(
                schedule_id=schedule.id, day_of_week=dow, is_working_day=working,
                start_time=time(7, 0) if working else None,
                end_time=time(16, 0) if working else None,
                break_start_time=time(12, 0) if working else None,
                break_end_time=time(13, 0) if working else None,
            ))
        self.db.flush()
        return schedule

    def _task(self, code, when, status="Pending", assigned=None, source_module="Workforce", source_type="manual"):
        assigned = assigned or self.employee
        row = FarmActivity(
            activity_code=code, name=code.replace("-", " "), category="General Care",
            related_to="Report Source", location="Farm", activity_date=when, start_time=time(8, 0),
            end_time=time(9, 0), assigned_by="Manager", assigned_to=assigned.full_name,
            assigned_employee_id=assigned.id, default_employee_id=assigned.id,
            assignment_source="manual", status=status, priority="Medium", requires_review=True,
            requires_evidence=False, source_module=source_module, source_type=source_type,
            is_archived=False,
        )
        self.db.add(row); self.db.flush(); return row

    def _inventory(self, code="INV-RPT-1", name="Grower Feed", category="Livestock Feed"):
        row = InventoryItem(
            item_code=code, name=name, category=category, quantity=100, unit="kg",
            reorder_level=10, cost=20, price=25, supplier="Supplier", date_acquired=self.week_start,
            location="Store", is_archived=False,
        )
        self.db.add(row); self.db.flush(); return row

    def _crop(self):
        row = Crop(
            crop_code="CRP-RPT-1", name="Tomato", variety="Roma", field="Field A",
            area_hectares=1, quantity_planted=100, current_surviving=90,
            planting_date=self.week_start - timedelta(days=60), estimated_harvest=self.week_start,
            status="Harvesting", assigned_employee_id=self.employee.id,
        )
        self.db.add(row); self.db.flush(); return row

    def _livestock(self, item):
        row = Livestock(
            animal_code="LIV-RPT-1", record_name="Pig Batch A", animal_type="Pig", breed="Large White",
            quantity=10, sex="Mixed", date_of_birth=self.week_start - timedelta(days=100), weight_kg=35,
            pen_location="Pig Pen 1", health_status="Healthy", growth_status="Growing",
            vaccination_status="Vaccinated", date_acquired=self.week_start - timedelta(days=90),
            feed_inventory_item_id=item.id, daily_feed_kg=2, feed_times="Twice Daily", feed_type=item.name,
            is_archived=False,
        )
        self.db.add(row); self.db.flush(); return row

    def test_daily_and_weekly_attendance_formulas_exclude_leave_and_rest_days(self):
        # Mon/Tue/Wed present, Thu absent, Fri approved leave; weekend rest.
        for offset, status, late, early in [
            (0, "Checked Out", 0, 0), (1, "Checked Out", 12, 0), (2, "Early Departure", 0, 30),
            (3, "Absent", None, None),
        ]:
            day = self.week_start + timedelta(days=offset)
            self.db.add(StaffAttendance(
                employee_id=self.employee.id, attendance_date=day, scheduled_start_time=time(7),
                scheduled_end_time=time(16), check_in_at=None if status == "Absent" else datetime.combine(day, time(7, 0)) + timedelta(minutes=late or 0),
                check_out_at=None if status == "Absent" else datetime.combine(day, time(16, 0)) - timedelta(minutes=early or 0),
                status=status, minutes_late=late, minutes_early=early, attendance_source="Employee Self-Service",
            ))
        self.db.add(StaffLeave(
            employee_id=self.employee.id, leave_type="Vacation Leave", start_date=self.week_start + timedelta(days=4),
            end_date=self.week_start + timedelta(days=4), status="Approved",
        ))
        self.db.commit()
        daily = build_operational_report_snapshot(self.db, "Daily Attendance Report", self.week_start, self.week_end, {"employee_id": self.employee.id})
        weekly = build_operational_report_snapshot(self.db, "Weekly Attendance Summary", self.week_start, self.week_end, {"employee_id": self.employee.id})
        self.assertEqual(daily["metrics"]["absent"], 1)
        row = weekly["operational_rows"][0]
        self.assertEqual(row["scheduled_workdays"], 4)
        self.assertEqual(row["days_present"], 3)
        self.assertEqual(row["late_arrivals"], 1)
        self.assertEqual(row["early_departures"], 1)
        self.assertEqual(row["approved_leave"], 1)
        self.assertEqual(row["rest_days"], 2)
        self.assertEqual(row["attendance_percentage"], 75.0)

    def test_restored_employee_with_old_archive_timestamp_appears_in_new_reports(self):
        # Legacy restores left archived_at in place even after reactivation.
        self.employee.archived_at = datetime.combine(self.week_start - timedelta(days=10), time(12))
        self.employee.is_archived = False
        checked_in = datetime.combine(self.day, time(7, 5))
        self.db.add(StaffAttendance(
            employee_id=self.employee.id, attendance_date=self.day, check_in_at=checked_in,
            status="Present", attendance_source="Employee Self-Service",
        ))
        self.db.commit()
        daily = build_operational_report_snapshot(
            self.db, "Daily Attendance Report", self.day, self.day, {"employee_id": self.employee.id},
        )
        weekly = build_operational_report_snapshot(
            self.db, "Weekly Attendance Summary", self.week_start, self.week_end, {"employee_id": self.employee.id},
        )
        self.assertEqual(daily["operational_rows"][0]["employee"], self.employee.full_name)
        self.assertEqual(daily["operational_rows"][0]["check_in"], checked_in.isoformat())
        self.assertEqual(weekly["operational_rows"][0]["days_present"], 1)

        self.employee.is_archived = True
        self.db.commit()
        archived = build_operational_report_snapshot(
            self.db, "Daily Attendance Report", self.day, self.day, {"employee_id": self.employee.id},
        )
        self.assertEqual(archived["operational_rows"], [])

    def test_task_performance_and_coverage_use_assignment_history(self):
        completed = self._task("TASK-RPT-DONE", self.day, "Completed")
        completed.completed_at = datetime.combine(self.day, time(8, 45))
        returned = self._task("TASK-RPT-RETURN", self.day, "Returned for Correction")
        self.db.add(TaskSubmission(
            activity_id=completed.id, employee_id=self.employee.id, attempt_number=1,
            actual_quantity=2, actual_unit="kg", evidence_url="evidence://test",
            review_status="Approved", submitted_at=datetime.combine(self.day, time(8, 30)),
        ))
        self.db.add(TaskAssignmentHistory(
            activity_id=returned.id, old_employee_id=self.employee.id, new_employee_id=self.backup.id,
            assignment_source="Attendance Coverage", old_assignment_source="automatic_default",
            new_assignment_source="Attendance Coverage", is_automatic=True, coverage_date=self.day,
            actor_name="Manager", reason="Confirmed Absent", changed_at=datetime.combine(self.day, time(7, 30)),
        ))
        self.db.commit()
        perf = build_operational_report_snapshot(self.db, "Task Completion and Employee Performance", self.week_start, self.week_end, {})
        cov = build_operational_report_snapshot(self.db, "Task Coverage and Reassignment", self.week_start, self.week_end, {})
        self.assertEqual(perf["metrics"]["completed_approved"], 1)
        self.assertEqual(perf["metrics"]["returned"], 1)
        self.assertEqual(perf["sections"]["task_details"][0]["evidence_available"], True)
        self.assertEqual(cov["metrics"]["attendance_absent_sick"], 1)
        self.assertEqual(cov["operational_rows"][0]["original_employee"], self.employee.full_name)
        self.assertEqual(cov["operational_rows"][0]["covering_employee"], self.backup.full_name)

    def test_care_compliance_uses_approved_submission_actual_quantity(self):
        task = self._task("FEED-RPT-1", self.day, "Completed", source_module="Livestock", source_type="care_template_step")
        task.name = "Morning Feeding"; task.category = "Feeding"; task.source_protocol_family_code = "CARE-PIG"; task.source_protocol_version = 2
        task.planned_quantity = 10; task.planned_unit = "kg"
        self.db.add(TaskSubmission(
            activity_id=task.id, employee_id=self.employee.id, attempt_number=1, actual_quantity=9.5,
            actual_unit="kg", review_status="Approved", submitted_at=datetime.combine(self.day, time(9)),
        ))
        self.db.commit()
        report = build_operational_report_snapshot(self.db, "Care Protocol Compliance", self.day, self.day, {})
        self.assertEqual(report["metrics"]["completed_approved"], 1)
        self.assertEqual(report["operational_rows"][0]["actual_approved_quantity"], 9.5)
        self.assertEqual(report["operational_rows"][0]["care_category"], "Feeding")

    def test_crop_inventory_and_sales_totals_are_recorded_facts(self):
        crop = self._crop(); item = self._inventory("INV-FERT-RPT", "Complete Fertilizer", "Fertilizer")
        self.db.add(CropYieldRecord(crop_id=crop.id, harvest_date=self.day, quantity_kg=500, damaged_quantity_kg=20))
        self.db.add(ResourceUsage(
            inventory_item_id=item.id, module="Crop", crop_id=crop.id, usage_type="Fertilizer", quantity=5,
            unit="kg", item_code_snapshot=item.item_code, item_name_snapshot=item.name, category_snapshot=item.category,
            usage_date=self.day, task_posting_active=False, is_voided=False,
        ))
        prod = LivestockProductionRecord(
            source_type="Crop", crop_id=crop.id, output_type="Harvest", record_date=self.day,
            gross_quantity=500, loss_quantity=20, farm_use_quantity=10, reserved_quantity=20,
            quantity=450, unit="kg", track_sale_inventory=True,
        )
        self.db.add(prod); self.db.flush()
        self.db.add(LivestockSale(
            sale_code="SALE-RPT-1", sale_type="Crop Sale", source_type="Crop", crop_id=crop.id,
            production_record_id=prod.id, sale_date=self.day, product_type="Tomato", quantity=100,
            unit="kg", unit_price=40, total_amount=4000, amount_paid=3000, balance_due=1000,
            buyer_name="Buyer", payment_status="Partial", is_voided=False,
        ))
        self.db.add(InventoryStockRecord(
            inventory_item_id=item.id, adjustment_type="Stock In", quantity=20, previous_quantity=80,
            new_quantity=100, adjustment_date=self.day, reason="Delivery",
        ))
        self.db.commit()
        crop_report = build_operational_report_snapshot(self.db, "Crop Yield and Input Usage", self.day, self.day, {})
        inventory_report = build_operational_report_snapshot(self.db, "Inventory Movement and Resource Usage", self.day, self.day, {})
        sales_report = build_operational_report_snapshot(self.db, "Production and Sales Summary", self.day, self.day, {})
        self.assertEqual(crop_report["metrics"]["actual_harvest_kg"], 500.0)
        self.assertEqual(crop_report["operational_rows"][0]["fertilizer_usage"], "5.0 kg")
        self.assertEqual(inventory_report["operational_rows"][0]["opening_quantity"], 80.0)
        self.assertEqual(sales_report["metrics"]["revenue"], 4000.0)
        self.assertEqual(sales_report["metrics"]["outstanding"], 1000.0)

    def test_livestock_feed_counts_only_approved_task_posting_and_not_legacy_confirmation(self):
        item = self._inventory(); animal = self._livestock(item)
        approved_task = self._task("FEED-APPROVED", self.day, "Completed", source_module="Livestock", source_type="livestock_feeding")
        approved_task.name="Morning Feeding"; approved_task.category="Feeding"; approved_task.source_record_id=animal.id; approved_task.planned_quantity=10; approved_task.planned_unit="kg"
        rejected_task = self._task("FEED-NOT-APPROVED", self.day, "Submitted for Review", source_module="Livestock", source_type="livestock_feeding")
        rejected_task.name="Afternoon Feeding"; rejected_task.category="Feeding"; rejected_task.source_record_id=animal.id; rejected_task.planned_quantity=8; rejected_task.planned_unit="kg"
        sub1=TaskSubmission(activity_id=approved_task.id,employee_id=self.employee.id,attempt_number=1,actual_quantity=9,actual_unit="kg",review_status="Approved")
        sub2=TaskSubmission(activity_id=rejected_task.id,employee_id=self.employee.id,attempt_number=1,actual_quantity=8,actual_unit="kg",review_status="Submitted for Review")
        self.db.add_all([sub1,sub2]); self.db.flush()
        self.db.add_all([
            ResourceUsage(inventory_item_id=item.id,module="Livestock",livestock_id=animal.id,activity_id=approved_task.id,task_submission_id=sub1.id,task_posting_active=True,usage_type="Feeding",quantity=9,unit="kg",item_name_snapshot=item.name,category_snapshot=item.category,usage_date=self.day,is_voided=False),
            # This row mimics an unapproved/competing path and must not be counted.
            ResourceUsage(inventory_item_id=item.id,module="Livestock",livestock_id=animal.id,activity_id=rejected_task.id,task_submission_id=sub2.id,task_posting_active=False,usage_type="Feeding",quantity=8,unit="kg",item_name_snapshot=item.name,category_snapshot=item.category,usage_date=self.day,is_voided=False),
        ])
        self.db.commit()
        report=build_operational_report_snapshot(self.db,"Livestock Feeding, Growth, and Health",self.day,self.day,{})
        self.assertEqual(report["metrics"]["approved_feeding_records"],1)
        self.assertEqual(report["metrics"]["approved_feed_quantity"],9.0)
        self.assertEqual(report["operational_rows"][0]["approved_actual_feed"],9.0)

    def test_not_recorded_is_not_silently_zero(self):
        crop=self._crop(); self.db.commit()
        report=build_operational_report_snapshot(self.db,"Crop Yield and Input Usage",self.day,self.day,{"crop_id":crop.id})
        row=report["operational_rows"][0]
        self.assertEqual(row["actual_harvest_kg"],"Not Recorded")
        self.assertEqual(row["yield_kg_per_hectare"],"Not Recorded")

    def test_operational_report_has_no_recommendations_and_csv_uses_same_snapshot(self):
        report=create_report_record(
            self.db,title="Daily Attendance",category="Workforce",report_type="Daily Attendance Report",
            start_date=self.day,end_date=self.day,prepared_by="Manager",status="Final",generate_pdf=False,
            filters={"employee_id":self.employee.id},
        )
        self.assertEqual(report.recommendations,[])
        self.assertEqual(report.snapshot["filters"]["employee_id"],self.employee.id)
        csv_text=build_report_csv(report)
        self.assertIn("Report Details",csv_text)
        self.assertIn("Generated Source",csv_text)
        self.assertNotIn("Recommended Actions",csv_text)

    def test_automation_keys_are_report_type_specific_and_repeated_run_is_idempotent(self):
        self.db.add(ReportAutomationSettings(
            daily_enabled=True, weekly_enabled=False, monthly_enabled=False, yearly_enabled=False,
            prepared_by="System Generated", auto_generate_pdf=False,
        )); self.db.commit()
        now=farm_now_naive(); start,end=_latest_daily(now,"00:05",True)
        self.assertNotEqual(_period_key("Daily","Daily Attendance Report",start,end),_period_key("Daily","Task Completion and Employee Performance",start,end))
        first=run_due_report_automation(self.db,force=True)
        second=run_due_report_automation(self.db,force=True)
        self.assertEqual(len(first),3)
        self.assertEqual(len(second),0)
        keys=list(self.db.scalars(select(FarmReport.automation_period_key).where(FarmReport.is_automatic==True)).all())
        self.assertEqual(len(keys),len(set(keys)))


    def test_scheduler_catches_up_missing_daily_periods_after_downtime(self):
        latest_due_start, latest_due_end = _latest_daily(farm_now_naive(), "00:05", True)
        old_end = latest_due_end - timedelta(days=3)
        create_report_record(
            self.db, title="Old Daily Attendance", category="Workforce",
            report_type="Daily Attendance Report", start_date=old_end, end_date=old_end,
            prepared_by="System", status="Final", is_automatic=True, frequency="Daily",
            automation_period_key=_period_key("Daily", "Daily Attendance Report", old_end, old_end),
            generate_pdf=False,
        )
        periods = _candidate_periods(
            self.db, "Daily", "Daily Attendance Report", (latest_due_start, latest_due_end)
        )
        self.assertEqual(periods, [
            (old_end + timedelta(days=1), old_end + timedelta(days=1)),
            (old_end + timedelta(days=2), old_end + timedelta(days=2)),
            (old_end + timedelta(days=3), old_end + timedelta(days=3)),
        ])

    def test_automation_creates_revised_version_instead_of_rewriting_final_source(self):
        self.db.add(ReportAutomationSettings(
            daily_enabled=True, weekly_enabled=False, monthly_enabled=False, yearly_enabled=False,
            prepared_by="System Generated", auto_generate_pdf=False,
        )); self.db.commit()
        first=run_due_report_automation(self.db,force=True)
        daily=next(r for r in first if r.report_type=="Daily Attendance Report")
        original_snapshot=daily.snapshot_json
        period=daily.start_date
        self.db.add(StaffAttendance(
            employee_id=self.employee.id,attendance_date=period,status="Present",attendance_source="Manager Assisted",
            check_in_at=datetime.combine(period,time(7)),check_out_at=datetime.combine(period,time(16)),minutes_late=0,minutes_early=0,
        )); self.db.commit()
        changed=run_due_report_automation(self.db,force=True)
        revisions=[r for r in changed if r.report_type=="Daily Attendance Report"]
        self.assertEqual(len(revisions),1)
        self.assertEqual(revisions[0].status,"Revised")
        self.assertEqual(revisions[0].revision_of_report_id,daily.id)
        self.db.refresh(daily)
        self.assertEqual(daily.snapshot_json,original_snapshot)


    def test_report_list_uses_server_side_pagination_and_filters(self):
        create_report_record(
            self.db, title="Manual Attendance", category="Workforce",
            report_type="Daily Attendance Report", start_date=self.day, end_date=self.day,
            prepared_by="Manager", status="Final", is_automatic=False, generate_pdf=False,
        )
        create_report_record(
            self.db, title="System Attendance", category="Workforce",
            report_type="Daily Attendance Report", start_date=self.day, end_date=self.day,
            prepared_by="System", status="Final", is_automatic=True, frequency="Daily",
            automation_period_key="test:attendance:system", generate_pdf=False,
        )
        statement = build_report_list_statement(
            include_archived=False, offset=0, limit=1, search=None, category="Workforce",
            report_status="Final", start_date=None, end_date=None, source="System",
        )
        page = list(self.db.scalars(statement).all())
        self.assertEqual(len(page), 1)
        self.assertTrue(page[0].is_automatic)
        self.assertEqual(page[0].title, "System Attendance")

    def test_daily_status_needs_review_or_final_from_factual_issues(self):
        self.assertEqual(_report_status("Daily Attendance Report",{"metrics":{"possible_absences":1,"missing_checkouts":0}}),"Needs Review")
        self.assertEqual(_report_status("Daily Attendance Report",{"metrics":{"possible_absences":0,"missing_checkouts":0}}),"Final")

    def test_daily_pdf_table_displays_attendance_status_and_check_out(self):
        recorded_tables = []

        def capture_table(headers, rows, widths=None):
            recorded_tables.append((headers, rows))
            return "table"

        snapshot = {"operational_rows": [{
            "employee_id": self.employee.id, "employee": self.employee.full_name,
            "employee_code": self.employee.employee_code, "work_date": self.day.isoformat(),
            "scheduled_shift": "07:00-16:00", "check_in": "07:00", "check_out": "16:00",
            "attendance_status": "Checked Out",
        }]}
        with patch("app.services.report_pdf._table", side_effect=capture_table):
            _operational_main(
                type("Report", (), {"report_type": "Daily Attendance Report"})(), snapshot, _styles(), 1,
            )
        headers, rows = recorded_tables[0]
        self.assertIn("Attendance Status", headers)
        self.assertIn("Check Out", headers)
        self.assertIn("Checked Out", rows[0])

    def test_operational_pdf_accepts_plain_string_data_quality_notes(self):
        report = FarmReport(
            report_code="RPT-PDF-STRING-NOTES",
            title="Daily Attendance Report",
            category="Workforce",
            report_type="Daily Attendance Report",
            start_date=self.day,
            end_date=self.day,
            generated_date=self.day,
            prepared_by="System",
            status="Final",
            summary="Recorded attendance facts.",
            snapshot_json=json.dumps({
                "report_kind": "operational_factual",
                "metrics": {"employees": 1},
                "operational_rows": [{"employee": self.employee.full_name, "attendance_status": "On Time"}],
                "report_options": {"included_sections": ["data_quality"]},
            }),
            comparison_json="{}",
            findings_json="[]",
            recommendations_json="[]",
            data_quality_json=json.dumps([
                "This report contains recorded historical facts only.",
                {"level": "Info", "message": "Structured notices remain supported."},
            ]),
            revision_number=1,
            is_automatic=False,
        )
        self.db.add(report)
        self.db.commit()
        pdf_path = generate_report_pdf(report)
        try:
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_operational_pdf_tolerates_legacy_text_rows_and_kpis(self):
        report = FarmReport(
            report_code="RPT-LEGACY-PDF",
            title="Legacy Operational Snapshot",
            category="Workforce",
            report_type="Daily Attendance Report",
            start_date=self.day,
            end_date=self.day,
            generated_date=self.day,
            prepared_by="System",
            status="Final",
            summary="Legacy snapshot compatibility",
            snapshot_json=json.dumps({
                "report_kind": "operational_factual",
                "report_options": {
                    "included_sections": [
                        "kpi_overview",
                        "detailed_analysis",
                        "data_quality",
                    ]
                },
                "metrics": {"employees": 1},
                "executive_kpis": ["Legacy KPI row"],
                "operational_rows": [
                    "Legacy text detail",
                    json.dumps({"employee": "Worker", "status": "Present"}),
                ],
            }),
            comparison_json="{}",
            findings_json="[]",
            recommendations_json="[]",
            data_quality_json=json.dumps(["Legacy note"]),
        )
        pdf_path = generate_report_pdf(report)
        try:
            self.assertTrue(pdf_path.exists())
            self.assertGreater(pdf_path.stat().st_size, 0)
        finally:
            pdf_path.unlink(missing_ok=True)

    def test_all_operational_report_types_can_generate_pdf_from_current_snapshot(self):
        report_types = [
            ("Workforce", "Daily Attendance Report"),
            ("Workforce", "Weekly Attendance Summary"),
            ("Task", "Task Completion and Employee Performance"),
            ("Task", "Task Coverage and Reassignment"),
            ("Farm", "Care Protocol Compliance"),
            ("Crop", "Crop Yield and Input Usage"),
            ("Livestock", "Livestock Feeding, Growth, and Health"),
            ("Inventory", "Inventory Movement and Resource Usage"),
            ("Production & Sales", "Production and Sales Summary"),
            ("Farm", "Generated Report History and Audit Trail"),
        ]
        for index, (category, report_type) in enumerate(report_types, start=1):
            with self.subTest(report_type=report_type):
                report = create_report_record(
                    self.db,
                    title=report_type,
                    category=category,
                    report_type=report_type,
                    start_date=self.day,
                    end_date=self.day,
                    prepared_by="System",
                    status="Final",
                    generate_pdf=False,
                )
                path = generate_report_pdf(report)
                try:
                    self.assertTrue(path.exists())
                    self.assertGreater(path.stat().st_size, 0)
                finally:
                    path.unlink(missing_ok=True)


    def test_attendance_schema_readiness_detects_missing_prompt_10_5_columns(self):
        class FakeInspector:
            def get_columns(self, table_name):
                self.table_name = table_name
                return [{"name": "id"}, {"name": "employee_id"}, {"name": "attendance_date"}, {"name": "status"}]

        with patch("app.services.report_scheduler.inspect", return_value=FakeInspector()):
            missing = attendance_schema_missing_columns(self.db)
        self.assertIn("check_in_at", missing)
        self.assertIn("attendance_source", missing)
        self.assertIn("updated_by_user_id", missing)

    def test_scheduler_skips_only_attendance_reports_when_attendance_schema_is_behind(self):
        settings = ReportAutomationSettings(
            daily_enabled=True, daily_time="00:00", weekly_enabled=False, monthly_enabled=False, yearly_enabled=False,
            prepared_by="System", auto_generate_pdf=False,
        )
        self.db.add(settings)
        self.db.commit()
        calls = []

        def fake_generate(db, **kwargs):
            calls.append(kwargs["report_type"])
            return None

        with patch("app.services.report_scheduler.attendance_schema_missing_columns", return_value={"check_in_at"}), \
             patch("app.services.report_scheduler._generate_or_revise", side_effect=fake_generate):
            run_due_report_automation(self.db, force=True)

        self.assertNotIn("Daily Attendance Report", calls)
        self.assertIn("Task Completion and Employee Performance", calls)
        self.assertIn("Inventory Movement and Resource Usage", calls)


if __name__ == "__main__":
    unittest.main()
