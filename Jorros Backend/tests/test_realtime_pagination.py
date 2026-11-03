"""Bounded, authorized task pages and committed change notices."""
import asyncio
from datetime import date, datetime, timedelta, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from test_release_http_authorization import ReleaseHttpAuthorizationTests
from app.models import Employee, FarmActivity, FarmAlert, FarmChangeEvent, FarmReport, InventoryItem, InventoryStockRecord, LivestockProductionRecord, User
from app.routers.events import load_authorized_events, router as events_router, stream_changes
from app.routers.reports import router as reports_router
from app.routers.production_sales import router as production_sales_router
from app.routers.inventory import router as inventory_router
from app.routers.alerts import router as alerts_router
from app.services.change_events import prune_change_events


class RealtimePaginationTests(ReleaseHttpAuthorizationTests):
    def test_event_retention_prunes_only_expired_rows(self):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with Session(self.engine) as db:
            old = FarmChangeEvent(event_type="inventory.updated", entity_type="Inventory",
                                  modules_json='["inventory"]', created_at=now-timedelta(days=15))
            recent = FarmChangeEvent(event_type="inventory.updated", entity_type="Inventory",
                                     modules_json='["inventory"]', created_at=now-timedelta(days=1))
            db.add_all([old, recent])
            db.commit()
            recent_id = recent.id
        with Session(self.engine) as db:
            self.assertEqual(prune_change_events(db), 1)
            self.assertIsNotNone(db.get(FarmChangeEvent, recent_id))
            self.assertEqual(prune_change_events(db), 0)

    def test_alert_pages_filter_and_count_without_downloaded_history(self):
        self.client.app.include_router(alerts_router)
        with Session(self.engine) as db:
            db.add_all([FarmAlert(
                alert_name=f"Alert {index}", category="Inventory", subject="Feed",
                alert_type="Threshold", condition="Below", threshold="5",
                priority="High" if index % 2 else "Medium",
                status="Completed" if index < 25 else "Active",
                is_automatic=False,
            ) for index in range(125)])
            db.commit()
        url = "/api/v1/alerts/page?limit=50"
        first = self.client.get(url, headers=self.headers("ADMIN"))
        second = self.client.get(url + "&offset=50", headers=self.headers("ADMIN"))
        self.assertEqual([first.status_code, second.status_code], [200, 200])
        self.assertEqual(first.json()["total"], 100)
        self.assertEqual(len({row["id"] for row in first.json()["items"] + second.json()["items"]}), 100)
        history = self.client.get(url + "&view=history", headers=self.headers("ADMIN"))
        self.assertEqual(history.json()["total"], 25)
        high = self.client.get(url + "&priority=high", headers=self.headers("ADMIN"))
        self.assertEqual(high.json()["total"], 50)
        searched = self.client.get(url + "&search=Alert%20124", headers=self.headers("ADMIN"))
        self.assertEqual(searched.json()["total"], 1)
        summary = self.client.get("/api/v1/alerts/summary", headers=self.headers("ADMIN"))
        self.assertEqual(summary.json()["active"], 100)
        self.assertEqual(summary.json()["history"], 25)
        self.assertEqual(summary.json()["high_priority"], 50)
        self.assertEqual(self.client.get(url, headers=self.headers("WORKER1")).status_code, 403)

    def test_inventory_page_filters_exact_total_and_summary(self):
        self.client.app.include_router(inventory_router)
        with Session(self.engine) as db:
            db.add_all([InventoryItem(
                item_code=f"INV-PAGE-{index}", name=f"Feed Lot {index}", category="Feed",
                quantity=0 if index == 119 else 10, unit="kg", reorder_level=2,
                cost=5, price=6, supplier="Farm" if index % 2 else "Vendor",
                date_acquired=date(2026, 9, 15), location="Barn",
            ) for index in range(120)])
            db.commit()
        url = "/api/v1/inventory/page?limit=50"
        pages = [self.client.get(f"{url}&offset={offset}", headers=self.headers("ADMIN"))
                 for offset in (0, 50, 100)]
        self.assertTrue(all(result.status_code == 200 for result in pages))
        self.assertEqual([len(result.json()["items"]) for result in pages], [50, 50, 20])
        self.assertEqual({result.json()["total"] for result in pages}, {120})
        self.assertEqual(len({item["id"] for result in pages for item in result.json()["items"]}), 120)
        filtered = self.client.get(url + "&search=Feed%20Lot%20119&stock_status=Out%20of%20Stock&supplier=Farm",
                                   headers=self.headers("ADMIN"))
        self.assertEqual(filtered.json()["total"], 1)
        self.assertEqual(filtered.json()["items"][0]["item_code"], "INV-PAGE-119")
        summary = self.client.get("/api/v1/inventory/summary", headers=self.headers("ADMIN"))
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["total"], 120)
        self.assertEqual(summary.json()["out_of_stock"], 1)
        self.assertEqual(summary.json()["supplier_count"], 2)
        self.assertEqual(summary.json()["total_value"], 5950)
        self.assertEqual(self.client.get(url + "&offset=-1", headers=self.headers("ADMIN")).status_code, 422)
        self.assertEqual(self.client.get(url, headers=self.headers("WORKER1")).status_code, 403)

    def test_inventory_chart_uses_aggregate_and_detail_is_still_available(self):
        self.client.app.include_router(inventory_router)
        with Session(self.engine) as db:
            item = InventoryItem(item_code="INV-CHART", name="Feed", category="Feed",
                                 quantity=13, unit="kg", reorder_level=2, cost=5, price=6,
                                 supplier="Farm", date_acquired=date.today(), location="Barn")
            db.add(item)
            db.flush()
            db.add_all([
                InventoryStockRecord(inventory_item_id=item.id, adjustment_type="Restock",
                                     quantity=20, previous_quantity=0, new_quantity=20,
                                     adjustment_date=date.today(), reason="Delivered"),
                InventoryStockRecord(inventory_item_id=item.id, adjustment_type="Set Exact Quantity",
                                     quantity=7, previous_quantity=20, new_quantity=13,
                                     adjustment_date=date.today(), reason="Counted"),
            ])
            db.commit()
            item_id = item.id
        summary = self.client.get("/api/v1/inventory/movements/summary", headers=self.headers("ADMIN"))
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(len(summary.json()), 1)
        self.assertEqual(summary.json()[0]["incoming"], 20)
        self.assertEqual(summary.json()[0]["outgoing"], 7)
        listing = self.client.get("/api/v1/inventory", headers=self.headers("ADMIN"))
        self.assertNotIn("stock_history", listing.json()[0])
        detail = self.client.get(f"/api/v1/inventory/{item_id}", headers=self.headers("ADMIN"))
        self.assertEqual(len(detail.json()["stock_history"]), 2)

    def test_initial_stream_boundary_requests_refresh(self):
        class DisconnectedRequest:
            async def is_disconnected(self):
                return True

        with Session(self.engine, expire_on_commit=False) as db:
            user = db.scalar(select(User).options(joinedload(User.role)).where(
                User.id == self.user_ids["ADMIN"]))

            async def read_boundary():
                response = await stream_changes(DisconnectedRequest(), since=None,
                                                last_event_id=None, db=db, user=user)
                return [part async for part in response.body_iterator]

            parts = asyncio.run(read_boundary())
            self.assertTrue(any("event: ready" in part and '"cursor"' in part for part in parts))

    def test_production_history_pages_do_not_stop_at_previous_limit(self):
        self.client.app.include_router(production_sales_router)
        with Session(self.engine) as db:
            db.add_all([LivestockProductionRecord(
                source_type="Crop", output_type=f"Harvest {index}",
                record_date=date(2026, 9, 15), quantity=10, unit="kg",
                track_sale_inventory=True,
            ) for index in range(125)])
            db.commit()
        uri = "/api/v1/production-sales/production?limit=50"
        ids = []
        for offset, expected in ((0, 50), (50, 50), (100, 25)):
            response = self.client.get(f"{uri}&offset={offset}", headers=self.headers("ADMIN"))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()), expected)
            ids += [row["id"] for row in response.json()]
        self.assertEqual(len(set(ids)), 125)
        self.assertEqual(self.client.get(f"{uri}&offset=-1", headers=self.headers("ADMIN")).status_code, 422)
        self.assertEqual(self.client.get(uri, headers=self.headers("WORKER1")).status_code, 403)

    def test_stream_requires_bearer_and_valid_cursor(self):
        self.client.app.include_router(events_router)
        self.assertEqual(self.client.get("/api/v1/events/stream").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/events/stream", params={"since": -1},
                                         headers=self.headers("WORKER1")).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/events/stream", headers={
            **self.headers("WORKER1"), "Last-Event-ID": "invalid"
        }).status_code, 400)

    def test_report_list_does_not_rewrite_saved_snapshot(self):
        self.client.app.include_router(reports_router)
        with Session(self.engine) as db:
            report = FarmReport(
                report_code="RPT-SNAPSHOT-1", title="Saved result", category="Workforce",
                report_type="Daily Attendance Report", start_date=date(2026, 9, 8),
                end_date=date(2026, 9, 8), generated_date=date(2026, 9, 8),
                prepared_by="Manager", status="Final", summary="Historical fact",
                snapshot_json='{"data_as_of":"2026-09-08","attendance":1}',
                findings_json="[]", data_quality_json="[]",
            )
            db.add(report)
            db.commit()
            report_id = report.id
            cursor = db.scalar(select(func.max(FarmChangeEvent.id))) or 0
        response = self.client.get("/api/v1/reports", headers=self.headers("ADMIN"))
        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.engine) as db:
            self.assertEqual(db.get(FarmReport, report_id).snapshot_json,
                             '{"data_as_of":"2026-09-08","attendance":1}')
            self.assertEqual(db.scalar(select(func.count(FarmChangeEvent.id)).where(
                FarmChangeEvent.id > cursor)), 0)

    def test_page_filters_total_summary_and_private_detail(self):
        with Session(self.engine) as db:
            employee_id = db.scalar(select(Employee.id).where(Employee.full_name == "Test Worker One"))
            db.add_all([FarmActivity(
                activity_code=f"ACT-PAGE-{index}", name=f"Feed plot {index}",
                category="General Care", related_to="Farm", location="Field",
                activity_date=date(2026, 9, 15), start_time=time(8), assigned_by="Manager",
                assigned_to="Test Worker One", assigned_employee_id=employee_id,
                status="Completed", priority="High", requires_review=True,
                requires_evidence=False, needs_reassignment=False, is_archived=False,
            ) for index in range(200)])
            db.commit()
        url = "/api/v1/workforce/tasks/page"
        response = self.client.get(f"{url}?status=Completed&employee_id={employee_id}&limit=25",
                                   headers=self.headers("MANAGER"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 200)
        self.assertEqual(len(response.json()["items"]), 25)
        searched = self.client.get(f"{url}?status=Completed&employee_id={employee_id}&search=Feed%20plot%20199",
                                   headers=self.headers("MANAGER"))
        self.assertEqual(searched.json()["total"], 1)
        self.assertEqual(searched.json()["items"][0]["activity_code"], "ACT-PAGE-199")
        second = self.client.get(f"{url}?status=Completed&employee_id={employee_id}&offset=175&limit=25",
                                 headers=self.headers("MANAGER"))
        self.assertEqual(len(second.json()["items"]), 25)
        self.assertEqual(self.client.get(url, headers=self.headers("WORKER2")).json()["total"], 1)
        task_id = response.json()["items"][0]["id"]
        self.assertEqual(self.client.get(f"/api/v1/workforce/tasks/{task_id}",
                                         headers=self.headers("WORKER2")).status_code, 404)
        summary = self.client.get("/api/v1/workforce/tasks/summary", headers=self.headers("MANAGER"))
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["pending"], 2)
        mine = self.client.get("/api/v1/workforce/my-tasks/page?view=completed&limit=25",
                               headers=self.headers("WORKER1"))
        self.assertEqual(mine.status_code, 200, mine.text)
        self.assertEqual(mine.json()["total"], 200)
        self.assertEqual(len(mine.json()["items"]), 25)
        searched_mine = self.client.get("/api/v1/workforce/my-tasks/page?view=completed&search=plot%20199",
                                        headers=self.headers("WORKER1"))
        self.assertEqual(searched_mine.json()["total"], 1)
        self.assertEqual(self.client.get("/api/v1/workforce/my-tasks/page?view=completed",
                                         headers=self.headers("WORKER2")).json()["total"], 0)

    def test_rollback_batch_and_private_delivery(self):
        with Session(self.engine) as db:
            users = {name: db.scalar(select(User).options(joinedload(User.role)).where(
                User.id == self.user_ids[name])) for name in ("WORKER1", "WORKER2", "MANAGER")}
            employee_ids = {name: db.scalar(select(Employee.id).where(Employee.login_user_id == users[name].id))
                            for name in ("WORKER1", "WORKER2")}
            cursor = db.scalar(select(func.max(FarmChangeEvent.id))) or 0
        with Session(self.engine) as db:
            task = db.scalar(select(FarmActivity).where(FarmActivity.activity_code == "ACT-REL-1"))
            task.status = "Submitted for Review"
            db.flush()
            db.rollback()
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(FarmChangeEvent.id)).where(FarmChangeEvent.id > cursor)), 0)
        with Session(self.engine) as db:
            task = db.scalar(select(FarmActivity).where(FarmActivity.activity_code == "ACT-REL-1"))
            task.status = "Submitted for Review"
            db.commit()
        with Session(self.engine) as db:
            manager, _ = load_authorized_events(db, users["MANAGER"], None, cursor)
            worker, _ = load_authorized_events(db, users["WORKER1"], employee_ids["WORKER1"], cursor)
            other, _ = load_authorized_events(db, users["WORKER2"], employee_ids["WORKER2"], cursor)
        self.assertTrue(any("tasks" in item["modules"] for item in manager))
        self.assertTrue(any("my_tasks" in item["modules"] for item in worker))
        self.assertEqual(other, [])

        with Session(self.engine) as db:
            db.add_all([FarmActivity(
                activity_code=f"ACT-BATCH-{index}", name=f"Batch {index}",
                category="General Care", related_to="Farm", location="Field",
                activity_date=date(2026, 9, 15), start_time=time(8), assigned_by="Manager",
                assigned_to="Test Worker One", assigned_employee_id=employee_ids["WORKER1"],
                status="Pending", priority="Medium", requires_review=True,
                requires_evidence=False, needs_reassignment=False, is_archived=False,
            ) for index in range(100)])
            db.commit()
        with Session(self.engine) as db:
            notices, _ = load_authorized_events(db, users["WORKER1"], employee_ids["WORKER1"], cursor)
        self.assertLessEqual(len(notices), 2)
        self.assertTrue(any(item["event_type"] == "task.batch" for item in notices))
