from datetime import time, timedelta
from unittest import TestCase

from sqlalchemy import select
from sqlalchemy.orm import Session
import test_data_display_pages as display_fixture
from app.models import Employee, FarmActivity, User


class CalendarPageTests(TestCase):
    def setUp(self):
        self.farm = display_fixture.DataDisplayPagesTests()
        self.farm.setUp()
        self.day = self.farm.today + timedelta(days=30)

    def tearDown(self): self.farm.tearDown()

    def activity(self, index, **extra):
        return FarmActivity(activity_code=f"CAL-PAGE-{index}", name=f"Calendar event {index:03}", category="Livestock Feeding",
            related_to="Field", location="Test location", assigned_by="Synthetic", assigned_to="Unassigned",
            activity_date=self.day, start_time=time(8), status="Pending", priority="Medium", **extra)

    def get(self, endpoint, user="ADMIN", **extra):
        return self.farm.get(f"/api/v1/activities/calendar/{endpoint}", user, date_from=self.day.isoformat(), date_to=self.day.isoformat(), **extra)

    def test_calendar_summary_counts_every_event_but_only_returns_four_previews_per_day(self):
        with Session(self.farm.engine) as db:
            rows = [self.activity(number) for number in range(75)]
            rows[0].category, rows[0].status = "Harvesting", "Completed"
            rows[-1].is_archived = True
            outside = self.activity(99); outside.activity_date = self.day + timedelta(days=1)
            db.add_all(rows + [outside]); db.commit()
        data = self.get("summary")
        self.assertEqual(data["summary"], {"total": 74, "harvests": 1, "livestock": 73, "completed": 1})
        self.assertEqual(len(data["days"]), 1)
        self.assertEqual(data["days"][0]["total"], 74)
        self.assertEqual(len(data["days"][0]["items"]), 4)

    def test_calendar_day_details_page_without_duplicates(self):
        with Session(self.farm.engine) as db: db.add_all([self.activity(number) for number in range(63)]); db.commit()
        pages = [self.get("events", offset=offset) for offset in (0, 25, 50)]
        self.assertEqual([len(page["items"]) for page in pages], [25, 25, 13])
        self.assertTrue(all(page["total"] == 63 for page in pages))
        identifiers = [row["id"] for page in pages for row in page["items"]]
        self.assertEqual(len(set(identifiers)), 63)
        self.assertEqual(identifiers, sorted(identifiers))

    def test_calendar_summary_and_details_share_employee_visibility(self):
        with Session(self.farm.engine) as db:
            worker = db.get(User, self.farm.user_ids["WORKER1"])
            worker.role.set_permissions(["workforce:submit", "activities:view", "workforce:attendance"])
            employee_id = db.scalar(select(Employee.id).where(Employee.login_user_id == worker.id))
            db.add_all([self.activity(index, assigned_employee_id=employee_id if index < 2 else None) for index in range(9)])
            db.commit()
        self.assertEqual(self.get("summary", "WORKER1")["summary"]["total"], 2)
        self.assertEqual(self.get("events", "WORKER1")["total"], 2)
        self.assertEqual(self.get("summary")["summary"]["total"], 9)

    def test_calendar_authorization_limits_and_dates(self):
        for endpoint in ("summary", "events"):
            path = f"/api/v1/activities/calendar/{endpoint}"
            self.assertEqual(self.farm.client.get(path).status_code, 401)
            self.assertEqual(self.farm.client.get(path, headers=self.farm.headers("WORKER1")).status_code, 403)
            params = {"date_from": self.day.isoformat(), "date_to": (self.day + timedelta(days=371)).isoformat()}
            self.assertEqual(self.farm.client.get(path, params=params, headers=self.farm.headers("ADMIN")).status_code, 422)
            params["date_to"] = (self.day - timedelta(days=1)).isoformat()
            self.assertEqual(self.farm.client.get(path, params=params, headers=self.farm.headers("ADMIN")).status_code, 422)
        for params in ({"limit": 101}, {"offset": -1}):
            self.assertEqual(self.farm.client.get("/api/v1/activities/calendar/events", params={"date_from": self.day.isoformat(), "date_to": self.day.isoformat(), **params}, headers=self.farm.headers("ADMIN")).status_code, 422)
