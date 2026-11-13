"""Bounded creation choices preserve global search matches and selections."""

import unittest
from sqlalchemy import select
from sqlalchemy.orm import Session
import test_data_display_pages as fixture
from app.models import Crop, InventoryItem, User


class ResourceChoicePagesTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.DataDisplayPagesTests(methodName="runTest")
        self.fixture.setUp()
        self.engine, self.client = self.fixture.engine, self.fixture.client

    def tearDown(self):
        self.fixture.tearDown()

    def get(self, **query):
        return self.fixture.get("/api/v1/activities/resource-choices", **query)

    def test_searches_all_rows_and_keeps_selected_separate_from_page_total(self):
        with Session(self.engine) as db:
            db.add_all(
                [self.fixture.crop(i) for i in range(81)]
                + [self.fixture.crop(999, is_archived=True)]
            )
            db.flush()
            chosen = db.scalar(select(Crop.id).where(Crop.crop_code == "CRP-DISPLAY-0"))
            db.commit()
        pages = [self.get(domain="Crop", offset=offset) for offset in (0, 25, 50, 75)]
        self.assertEqual([len(page["items"]) for page in pages], [25, 25, 25, 6])
        self.assertEqual(pages[0]["total"], 81)
        self.assertEqual(
            len({row["id"] for page in pages for row in page["items"]}), 81
        )
        match = self.get(domain="Crop", search="Crop 080", selected_id=chosen)
        self.assertEqual(match["total"], 1)
        self.assertEqual(match["items"][0]["cropCode"], "CRP-DISPLAY-80")
        self.assertEqual(match["selected"]["id"], chosen)
        empty = self.get(domain="Crop", search="no such crop", selected_id=chosen)
        self.assertEqual(
            (empty["items"], empty["total"], empty["selected"]["id"]), ([], 0, chosen)
        )

    def test_literal_search_and_supply_compatibility_exclude_wrong_stock(self):
        with Session(self.engine) as db:
            for i, (name, category, archived) in enumerate(
                [
                    ("50%_feed", "Livestock Feed", False),
                    ("500_feed", "Livestock Feed", False),
                    ("Soil", "Fertilizer", False),
                    ("Seeds", "Seed", False),
                    ("Old feed", "Feed", True),
                    ("My vaccine", "Farm Supplies", False),
                ]
            ):
                db.add(
                    InventoryItem(
                        item_code=f"INV-CHOICE-{i}",
                        name=name,
                        category=category,
                        quantity=100,
                        unit="kg",
                        reorder_level=0,
                        cost=1,
                        supplier="Test",
                        date_acquired=self.fixture.today,
                        location="Store",
                        is_archived=archived,
                    )
                )
            db.commit()
        self.assertEqual(self.get(domain="Inventory", search="50%_")["total"], 1)
        feed = self.get(domain="Inventory", work_module="Livestock", work_kind="feed")
        self.assertEqual(feed["total"], 2)
        self.assertTrue(
            all(row["category"] == "Livestock Feed" for row in feed["items"])
        )
        self.assertEqual(
            [
                row["name"]
                for row in self.get(
                    domain="Inventory", work_module="Crop", work_kind="fertilizer"
                )["items"]
            ],
            ["Soil"],
        )
        self.assertEqual(
            [
                row["name"]
                for row in self.get(
                    domain="Inventory", work_module="Livestock", work_kind="vaccine"
                )["items"]
            ],
            ["My vaccine"],
        )

    def test_livestock_slots_permissions_and_limits(self):
        with Session(self.engine) as db:
            db.add(self.fixture.animal(1, feed_times="Twice Daily"))
            db.get(User, self.fixture.user_ids["MANAGER"]).role.set_permissions(
                ["workforce:manage", "activities:view"]
            )
            db.commit()
        row = self.get(domain="Livestock")["items"][0]
        self.assertEqual(row["feeding_slots"], ["Morning", "Afternoon"])
        self.assertEqual(row["recordName"], "Batch 001")
        url = "/api/v1/activities/resource-choices"
        self.assertEqual(
            self.client.get(url, params={"domain": "Crop"}).status_code, 401
        )
        self.assertEqual(
            self.client.get(
                url, params={"domain": "Crop"}, headers=self.fixture.headers("WORKER1")
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                url, params={"domain": "Crop"}, headers=self.fixture.headers("MANAGER")
            ).status_code,
            200,
        )
        for params in (
            {"domain": "Other"},
            {"domain": "Crop", "limit": 101},
            {"domain": "Crop", "offset": -1},
            {"domain": "Inventory", "work_kind": "wrong"},
        ):
            self.assertEqual(
                self.client.get(
                    url, params=params, headers=self.fixture.headers("ADMIN")
                ).status_code,
                422,
            )
