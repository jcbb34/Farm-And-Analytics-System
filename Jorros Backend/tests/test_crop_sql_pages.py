"""SQL crop filters match displayed lifecycle state without normalizing all rows."""
from datetime import timedelta
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session

import test_data_display_pages as display_fixture
from app.models import Crop
from app.services import resource_lists
from app.services.crop_projection import crop_projection, filtered_crop_query


class CropSqlPageTests(TestCase):
    def setUp(self):
        self.fixture = display_fixture.DataDisplayPagesTests()
        self.fixture.setUp()
        self.today = self.fixture.today

    def tearDown(self):
        self.fixture.tearDown()

    def crop(self, index, **values):
        row = self.fixture.crop(index)
        for key, value in values.items():
            setattr(row, key, value)
        return row

    def test_sql_page_only_normalizes_selected_rows_and_skips_summary(self):
        with Session(self.fixture.engine) as db:
            db.add_all(self.fixture.crop(i) for i in range(151)); db.commit()
            original = resource_lists._crop_rows
            normalized = []

            def inspect(*args, **kwargs):
                for row in original(*args, **kwargs):
                    normalized.append(row["id"])
                    yield row

            with patch.object(resource_lists, "_crop_rows", inspect), patch.object(resource_lists, "crop_summary", side_effect=AssertionError("summary repeated")):
                page = resource_lists.crop_listing(db, offset=100, limit=25, include_overview=False)
            self.assertEqual(page["total"], 151)
            self.assertEqual(len(page["items"]), 25)
            self.assertEqual(len(normalized), 25)
            self.assertIsNone(page["overview"])
            self.assertEqual(page["items"][0]["name"], "Crop 100")

    def test_sql_status_matches_displayed_progress_at_rounding_boundaries(self):
        crops = []
        for total in (1, 2, 7, 90, 365, 1000, 2000, 3000):
            for elapsed in sorted({0, 1, total, total + 1, int(total * .8994), int(total * .8995), int(total * .8996), total - 1}):
                crops.append(self.crop(len(crops), planting_date=self.today - timedelta(days=elapsed),
                    estimated_harvest=self.today + timedelta(days=total - elapsed)))
        for stage in ("Seeded", "Flowering", "Maturity", "Harvest Ready"):
            crops.append(self.fixture.crop(len(crops), observed_growth_stage=stage))
        crops.append(self.fixture.crop(len(crops), status="Failed"))
        crops.append(self.fixture.crop(len(crops), status="Harvested"))
        crops.append(self.fixture.crop(len(crops), status="Harvesting"))
        with Session(self.fixture.engine) as db:
            db.add_all(crops); db.commit()
            sql_status = {row["id"]: row["computed_status"] for row in db.execute(crop_projection()).mappings()}
            displayed = {row["id"]: row["status"] for row in resource_lists._crop_rows(db)}
            self.assertEqual(sql_status, displayed)
            for status in ("Planted", "Growing", "Ready for Harvest", "Harvesting", "Harvested", "Failed"):
                page = resource_lists.crop_listing(db, status_filter=status, limit=100, include_overview=False)
                self.assertEqual(page["total"], sum(value == status for value in displayed.values()))
                self.assertTrue(all(row["status"] == status for row in page["items"]))

    def test_sql_search_is_literal_and_summary_remains_whole_farm(self):
        with Session(self.fixture.engine) as db:
            db.add_all([self.fixture.crop(1), self.crop(2, variety="Rare_50%"), self.fixture.crop(3)])
            db.commit()
        page = self.fixture.get("/api/v1/display/crops", search="_50%", include_overview=False)
        self.assertEqual(page["total"], 1)
        self.assertIsNone(page["overview"])
        self.assertEqual(self.fixture.get("/api/v1/display/crops/summary")["total"], 3)
        with Session(self.fixture.engine) as db:
            self.assertEqual(db.scalar(select(Crop.variety).where(Crop.crop_code == "CRP-DISPLAY-2")), "Rare_50%")

    def test_query_compiles_for_sql_server_with_bounded_parameters(self):
        statement, ordering = filtered_crop_query(search="_50%", status_filter="Ready for Harvest")
        compiled = statement.order_by(*ordering).offset(100).limit(25).compile(dialect=mssql.dialect())
        sql = str(compiled)
        self.assertIn("DATEDIFF(day,", sql)
        self.assertIn("TRY_CONVERT(int,", sql)
        self.assertIn("ROW_NUMBER()", sql.upper())
        self.assertLess(len(compiled.params), 200)
        self.assertNotIn("SELECT EXISTS", sql.upper())
