import os
import unittest

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret")


from app.schemas.workforce import TaskResponse, TaskSubmissionResponse
from app.services.shared_device import sanitize_shared_device_task_response


class SharedDevicePrivacyTests(unittest.TestCase):
    def test_shared_device_response_removes_other_staff_identity_but_keeps_employee_work_state(self):
        submission = TaskSubmissionResponse.model_construct(
            id=21,
            activity_id=7,
            employee_id=5,
            employee_name="Current Employee",
            recorded_by_user_id=44,
            recorded_by_name="Manager Recorder",
            reviewed_by_name="Manager Reviewer",
            reviewed_by_user_id=45,
            review_feedback="Please correct the quantity.",
        )
        task = TaskResponse.model_construct(
            id=7,
            name="Water Eggplant",
            assigned_by="Manager Maria",
            assigned_to="Current Employee",
            employee_name="Current Employee",
            previous_employee_name="Previous Worker",
            reassignment_reason="Previous worker unavailable",
            leave_coverage_id=9,
            related_leave_id=10,
            original_employee_id=11,
            original_employee_name="Employee On Leave",
            covering_employee_id=5,
            covering_employee_name="Current Employee",
            coverage_start_date=None,
            coverage_end_date=None,
            coverage_reason="Private leave reason",
            coverage_status="Active",
            coverage_indicator="Coverage Ending",
            latest_submission=submission,
        )

        safe = sanitize_shared_device_task_response(task)

        self.assertEqual(safe.assigned_by, "Farm Manager")
        self.assertEqual(safe.assigned_to, "Current Employee")
        self.assertEqual(safe.employee_name, "Current Employee")
        self.assertIsNone(safe.previous_employee_name)
        self.assertIsNone(safe.original_employee_id)
        self.assertIsNone(safe.original_employee_name)
        self.assertIsNone(safe.covering_employee_id)
        self.assertIsNone(safe.covering_employee_name)
        self.assertIsNone(safe.coverage_reason)
        self.assertIsNone(safe.related_leave_id)
        self.assertEqual(safe.latest_submission.review_feedback, "Please correct the quantity.")
        self.assertIsNone(safe.latest_submission.recorded_by_user_id)
        self.assertIsNone(safe.latest_submission.recorded_by_name)
        self.assertIsNone(safe.latest_submission.reviewed_by_user_id)
        self.assertIsNone(safe.latest_submission.reviewed_by_name)


if __name__ == "__main__":
    unittest.main()
