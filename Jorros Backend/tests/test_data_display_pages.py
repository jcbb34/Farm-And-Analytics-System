"""Exact totals, filters before paging, read-only lists and authorized histories."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_release_http_authorization import ReleaseHttpAuthorizationTests
from app.core.farm_time import farm_today
from app.models import AuditLog, Crop, CropGrowthRecord, CropYieldRecord, FarmActivity, Livestock, LivestockProductionRecord, LivestockSale, LivestockSaleItem, LivestockVaccinationRecord, InventoryItem, ResourceUsage, User
from app.routers import activities, crops, display, livestock, production_sales, resource_usages


class DataDisplayPagesTests(ReleaseHttpAuthorizationTests):
    def setUp(self):
        super().setUp()
        for module in (display, crops, livestock, activities, production_sales, resource_usages): self.client.app.include_router(module.router)
        self.today = farm_today()

    def get(self, path, user="ADMIN", **params):
        result = self.client.get(path, params=params, headers=self.headers(user))
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def crop(self, index=0, **values):
        return Crop(crop_code=f"CRP-DISPLAY-{index}", name=f"Crop {index:03}", variety="Test", field="Field A",
            area_hectares=1, quantity_planted=100, current_surviving=95, fertilizer_quantity_kg=0,
            planting_date=self.today - timedelta(days=30), estimated_harvest=self.today + timedelta(days=60),
            **{"status": "Growing", "is_archived": False, **values})

    def animal(self, index=0, **values):
        return Livestock(animal_code=f"LIV-DISPLAY-{index}", record_name=f"Batch {index:03}", animal_type="Pig", breed="Test",
            quantity=10, weight_kg=25, healthy_quantity=10, pen_location="Pen A", daily_feed_kg=2,
            date_of_birth=self.today - timedelta(days=60), date_acquired=self.today - timedelta(days=30),
            **{"is_archived": False, **values})

    def test_crop_pages_keep_global_totals_and_search_all_rows(self):
        with Session(self.engine) as db:
            db.add_all([self.crop(index) for index in range(121)] + [self.crop(999, is_archived=True)])
            db.commit()
        first = self.get("/api/v1/display/crops", limit=50)
        second = self.get("/api/v1/display/crops", limit=50, offset=50)
        third = self.get("/api/v1/display/crops", limit=50, offset=100)
        self.assertEqual([len(page["items"]) for page in (first, second, third)], [50, 50, 21])
        self.assertEqual(len({row["id"] for page in (first, second, third) for row in page["items"]}), 121)
        self.assertEqual(first["total"], 121)
        self.assertEqual(first["overview"]["total"], 121)
        self.assertEqual(first["overview"]["analytics"]["productivityStats"]["totalArea"], 121)
        match = self.get("/api/v1/display/crops", search="Crop 120")
        self.assertEqual(match["total"], 1)
        self.assertEqual(match["overview"]["total"], 121)
        self.assertEqual(self.get("/api/v1/display/crops", status_filter="Archived")["total"], 1)

    def test_crop_page_computes_readiness_without_writing_status(self):
        row = self.crop(1)
        row.planting_date = self.today - timedelta(days=95)
        row.estimated_harvest = self.today + timedelta(days=5)
        with Session(self.engine) as db: db.add(row); db.commit()
        page = self.get("/api/v1/display/crops", status_filter="Ready for Harvest")
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["status"], "Ready for Harvest")
        with Session(self.engine) as db: self.assertEqual(db.scalar(select(Crop.status)), "Growing")

    def test_crop_list_omits_histories_but_detail_keeps_every_measurement(self):
        with Session(self.engine) as db:
            crop = self.crop(); db.add(crop); db.flush(); crop_id = crop.id
            db.add_all([CropGrowthRecord(crop_id=crop_id, growth_percentage=25, status="Growing", update_date=self.today) for _ in range(55)])
            db.commit()
        row = self.get("/api/v1/display/crops")["items"][0]
        self.assertNotIn("growth_records", row)
        self.assertNotIn("yield_records", row)
        self.assertEqual(len(self.get(f"/api/v1/crops/{crop_id}")["growth_records"]), 55)

    def test_dashboard_crop_chart_is_bounded_and_totals_are_complete(self):
        with Session(self.engine) as db:
            db.add_all([self.crop(i) for i in range(80)]); db.flush()
            crop_id = db.scalar(select(Crop.id))
            db.add_all([CropGrowthRecord(crop_id=crop_id, growth_percentage=25, status="Growing", update_date=self.today) for _ in range(40)])
            db.commit()
        data = self.get("/api/v1/display/crops/overview", start_date=self.today.isoformat(), end_date=self.today.isoformat())
        self.assertEqual(data["total"], 80)
        self.assertEqual(len(data["chart_records"]), 12)
        self.assertEqual(sum(len(row["growth_records"]) for row in data["chart_records"]), 12)
        self.assertEqual(data["status_counts"]["Growing"], 80)

    def test_crop_harvest_history_has_exact_total_and_no_duplicate_pages(self):
        with Session(self.engine) as db:
            crop = self.crop(); db.add(crop); db.flush()
            db.add_all([CropYieldRecord(crop_id=crop.id, harvest_date=self.today, quantity_kg=3, harvest_type="Partial Harvest") for _ in range(35)])
            db.commit()
        first = self.get("/api/v1/display/crop-yields")
        second = self.get("/api/v1/display/crop-yields", offset=25)
        self.assertEqual([len(first["items"]), len(second["items"])], [25, 10])
        self.assertEqual(first["total"], 35)
        self.assertEqual(len({row["id"] for row in first["items"] + second["items"]}), 35)
        stats = self.get("/api/v1/display/crops")["overview"]["analytics"]["productivityStats"]
        self.assertEqual(stats["totalYield"], 105)

    def test_livestock_page_totals_and_analytics_do_not_use_page_size(self):
        with Session(self.engine) as db: db.add_all([self.animal(i) for i in range(115)]); db.commit()
        page = self.get("/api/v1/display/livestock", limit=50)
        self.assertEqual(page["total"], 115)
        self.assertEqual(len(page["items"]), 50)
        self.assertEqual(page["overview"]["total"], 1150)
        self.assertEqual(page["overview"]["analytics"]["population"]["Pig"], 1150)
        self.assertEqual(page["overview"]["analytics"]["planned_feed"]["Pig"], 2300)
        match = self.get("/api/v1/display/livestock", search="Batch 114")
        self.assertEqual(match["total"], 1)
        self.assertEqual(match["overview"]["total"], 1150)

    def test_livestock_detail_history_is_not_needed_by_list(self):
        with Session(self.engine) as db:
            animal = self.animal(); db.add(animal); db.flush(); animal_id = animal.id
            db.add_all([LivestockVaccinationRecord(livestock_id=animal_id, vaccine="Test vaccine", date_administered=self.today, status="Done") for _ in range(31)])
            db.commit()
        listing = self.get("/api/v1/display/livestock")["items"][0]
        self.assertNotIn("vaccination_records", listing)
        self.assertEqual(len(self.get(f"/api/v1/livestock/{animal_id}")["vaccination_records"]), 31)
        first = self.get("/api/v1/display/livestock/records", kind="vaccinations")
        second = self.get("/api/v1/display/livestock/records", kind="vaccinations", offset=25)
        self.assertEqual([first["total"], len(first["items"]), len(second["items"])], [31, 25, 6])

    def test_resource_pages_require_module_permissions_and_validate_limits(self):
        for path in ("crops", "livestock", "crop-yields", "livestock/records"):
            url = f"/api/v1/display/{path}"
            self.assertEqual(self.client.get(url, headers=self.headers("WORKER1")).status_code, 403)
            self.assertEqual(self.client.get(url).status_code, 401)
            self.assertEqual(self.client.get(url, params={"limit": 101}, headers=self.headers("ADMIN")).status_code, 422)
            self.assertEqual(self.client.get(url, params={"offset": -1}, headers=self.headers("ADMIN")).status_code, 422)

    def test_dashboard_activity_paging_search_and_employee_isolation(self):
        with Session(self.engine) as db:
            worker = db.get(User, self.user_ids["WORKER1"])
            worker.role.set_permissions(["workforce:submit", "activities:view", "workforce:attendance"])
            db.add_all([FarmActivity(activity_code=f"ACT-DISPLAY-{i}", name=f"Extra task {i:03}", category="General Care",
                related_to="Field", location="Field", assigned_by="Scan Manager", assigned_to="Unassigned", activity_date=self.today, start_time=time(8), status="Pending", priority="Medium") for i in range(105)])
            db.commit()
        params = {"view": "upcoming", "date_from": self.today.isoformat(), "date_to": self.today.isoformat()}
        data = self.get("/api/v1/activities/page", **params)
        self.assertEqual([len(data["items"]), data["total"]], [25, 105])
        match = self.get("/api/v1/activities/page", **params, search="Extra task 104")
        self.assertEqual(match["total"], 1)
        self.assertEqual(self.get("/api/v1/activities/page", "WORKER1", **params)["total"], 0)
        self.assertEqual(self.get("/api/v1/activities/summary", activity_date=self.today.isoformat())["tasks_today"], 105)
        self.assertEqual(self.get("/api/v1/activities/summary", "WORKER1", activity_date=self.today.isoformat())["tasks_today"], 0)

    def test_production_scope_and_search_find_rows_before_offset(self):
        with Session(self.engine) as db:
            crop = self.crop(); animal = self.animal(); db.add_all([crop, animal]); db.flush()
            db.add(LivestockProductionRecord(source_type="Crop", crop_id=crop.id, output_type="Hidden older harvest", record_date=self.today - timedelta(days=1), quantity=20, unit="kg"))
            db.add_all([LivestockProductionRecord(source_type="Livestock", livestock_id=animal.id, output_type="Eggs", record_date=self.today, quantity=10, unit="pcs") for _ in range(65)])
            db.commit()
        scoped = self.get("/api/v1/production-sales/production", source_type="Crop", limit=50)
        searched = self.get("/api/v1/production-sales/production", search="Hidden older harvest", limit=50)
        self.assertEqual(len(scoped), 1)
        self.assertEqual(len(searched), 1)
        self.assertEqual(scoped[0]["id"], searched[0]["id"])

    def test_sales_search_finds_invoice_lines_and_scopes_mixed_invoices(self):
        with Session(self.engine) as db:
            crop = self.crop(); db.add(crop); db.flush()
            sale = LivestockSale(sale_code="SALE-DISPLAY", source_type="Mixed", sale_type="Product", product_type="Mixed items", sale_date=self.today,
                quantity=1, unit="kg", unit_price=10, total_amount=10, amount_paid=10, balance_due=0, payment_status="Paid")
            db.add(sale); db.flush()
            db.add(LivestockSaleItem(sale_id=sale.id, line_number=1, item_kind="Production", source_type="Crop", crop_id=crop.id,
                source_name_snapshot="Older crop", source_code_snapshot="EXACT-CROP-120", product_type="100%_special seed", quantity=1, unit="kg", unit_price=10, line_total=10))
            db.commit()
        rows = self.get("/api/v1/production-sales/sales", source_type="Crop", search="EXACT-CROP-120", limit=50)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sale_code"], "SALE-DISPLAY")
        self.assertEqual(len(self.get("/api/v1/production-sales/sales", search="%_special")), 1)
        self.assertEqual(len(self.get("/api/v1/production-sales/sales", search="%_absent")), 0)

    def test_consumption_summary_groups_units_and_excludes_voided_and_other_dates(self):
        with Session(self.engine) as db:
            item = InventoryItem(item_code="INV-DISPLAY", name="Feed", category="Feed", quantity=100, unit="kg", reorder_level=0, cost=1,
                supplier="Test supplier", date_acquired=self.today, location="Test storage")
            db.add(item); db.flush()
            for module, kind, unit, quantity, day, voided in [
                ("Crop", "Fertilizer", "kg", 2, self.today, False),
                ("Crop", "Fertilizer", "kg", 3, self.today, False),
                ("Crop", "Fertilizer", "g", 100, self.today, False),
                ("Livestock", "Feed", "kg", 8, self.today, False),
                ("Livestock", "Feed", "kg", 50, self.today, True),
                ("Livestock", "Feed", "kg", 99, self.today - timedelta(days=1), False),
            ]:
                db.add(ResourceUsage(inventory_item_id=item.id, module=module, usage_type=kind, unit=unit,
                    quantity=quantity, usage_date=day, is_voided=voided))
            worker = db.get(User, self.user_ids["WORKER1"])
            worker.role.set_permissions(["crops:view", "workforce:attendance"])
            db.commit()
        params = {"start_date": self.today.isoformat(), "end_date": self.today.isoformat()}
        data = self.get("/api/v1/resource-usages/consumption-summary", **params)
        self.assertEqual(data["total"], 4)
        self.assertEqual({(r["usage_type"], r["unit"]): r["quantity"] for r in data["rows"]},
            {("Fertilizer", "kg"): 5, ("Fertilizer", "g"): 100, ("Feed", "kg"): 8})
        restricted = self.get("/api/v1/resource-usages/consumption-summary", "WORKER1", **params)
        self.assertEqual(restricted["total"], 3)
        self.assertTrue(all(r["usage_type"] == "Fertilizer" for r in restricted["rows"]))
        self.assertEqual(self.client.get("/api/v1/resource-usages/consumption-summary", params=params, headers=self.headers("MANAGER")).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/resource-usages/consumption-summary", params={**params, "start_date": (self.today + timedelta(days=1)).isoformat()}, headers=self.headers("ADMIN")).status_code, 422)

    def test_crop_projection_uses_sql_server_compatible_exists_predicate(self):
        from sqlalchemy.dialects import mssql
        from app.services.resource_lists import _crop_rows
        class ProjectionOnly:
            sql = ""
            def execute(self, statement):
                self.sql = str(statement.compile(dialect=mssql.dialect()))
                return self
            def mappings(self): return []
        capture = ProjectionOnly()
        self.assertEqual(list(_crop_rows(capture)), [])
        self.assertIn("CASE WHEN (EXISTS", capture.sql)
        self.assertNotIn("SELECT EXISTS", capture.sql)
        self.assertIn("SELECT TOP", capture.sql)

    def test_reopened_crop_uses_yield_id_boundary_even_at_same_timestamp(self):
        instant = datetime.combine(self.today, time(8))
        with Session(self.engine) as db:
            row = self.crop(7, status="Ready for Harvest", confirmed_ready_at=instant)
            db.add(row); db.flush()
            final = CropYieldRecord(crop_id=row.id, harvest_date=self.today, quantity_kg=10, harvest_type="Final Harvest", created_at=instant)
            db.add(final); db.flush()
            db.add(AuditLog(event_type="audit", module="Crop", action="Reopened crop cycle", entity_id=row.crop_code,
                actor_name="Test Admin", created_at=instant, details=f"Previous final yield ID: {final.id}"))
            db.commit()
            crop_id = row.id
        self.assertEqual(self.get("/api/v1/display/crops")["items"][0]["status"], "Ready for Harvest")
        with Session(self.engine) as db:
            db.add(CropYieldRecord(crop_id=crop_id, harvest_date=self.today, quantity_kg=2, harvest_type="Partial Harvest", created_at=instant))
            db.commit()
        self.assertEqual(self.get("/api/v1/display/crops")["items"][0]["status"], "Harvesting")
