from datetime import timedelta
from unittest import TestCase

from sqlalchemy.orm import Session
import test_data_display_pages as display_fixture
from app.models import InventoryItem, LivestockProductionRecord, LivestockSale, LivestockSaleItem


class SaleStockTests(TestCase):
    def setUp(self):
        self.farm = display_fixture.DataDisplayPagesTests()
        self.farm.setUp()

    def tearDown(self):
        self.farm.tearDown()

    def get(self, **query):
        return self.farm.get("/api/v1/production-sales/stock", **query)

    def test_stock_search_and_pages_include_older_matches(self):
        with Session(self.farm.engine) as db:
            crop = self.farm.crop(); db.add(crop); db.flush()
            db.add(LivestockProductionRecord(source_type="Crop", crop_id=crop.id, output_type="Older 100%_special harvest",
                record_date=self.farm.today - timedelta(days=1), quantity=10, unit="kg", track_sale_inventory=True))
            db.add_all([LivestockProductionRecord(source_type="Crop", crop_id=crop.id, output_type=f"Eggplant {number}",
                record_date=self.farm.today, quantity=2, unit="kg", track_sale_inventory=True) for number in range(70)])
            db.commit()
        first, second = self.get(), self.get(offset=25)
        self.assertEqual(first["total"], 71)
        self.assertEqual(len(first["items"]), 25)
        self.assertFalse({row["id"] for row in first["items"]} & {row["id"] for row in second["items"]})
        found = self.get(search="%_special")
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["items"][0]["available_quantity"], 10)
        self.assertEqual(self.get(search="%_absent")["total"], 0)

    def test_stock_availability_uses_lines_once_and_ignores_voided_sales(self):
        with Session(self.farm.engine) as db:
            crop = self.farm.crop(); db.add(crop); db.flush()
            lot = LivestockProductionRecord(source_type="Crop", crop_id=crop.id, output_type="Eggplant",
                record_date=self.farm.today, quantity=100, unit="kg", track_sale_inventory=True)
            db.add(lot); db.flush()
            for index, quantity, line, voided in [(1, 80, 10, False), (2, 5, None, False), (3, 50, 50, True)]:
                sale = LivestockSale(sale_code=f"STOCK-SALE-{index}", source_type="Crop", sale_type="Product", product_type="Eggplant",
                    production_record_id=lot.id, sale_date=self.farm.today, quantity=quantity, unit="kg", unit_price=1,
                    total_amount=quantity, amount_paid=0, balance_due=quantity, payment_status="Unpaid", is_voided=voided)
                db.add(sale); db.flush()
                if line is not None:
                    db.add(LivestockSaleItem(sale_id=sale.id, line_number=1, item_kind="Production", source_type="Crop", production_record_id=lot.id,
                        source_name_snapshot="Eggplant", source_code_snapshot="TEST", product_type="Eggplant", quantity=line, unit="kg", unit_price=1, line_total=line))
            db.commit()
        self.assertEqual(self.get()["items"][0]["available_quantity"], 85)

    def test_live_and_inventory_sources_only_include_eligible_stock(self):
        with Session(self.farm.engine) as db:
            db.add_all([self.farm.animal(1), self.farm.animal(2, is_archived=True), self.farm.animal(3, lifecycle_status="Sold")])
            for index, saleable, quantity, archived in [(1, True, 10, False), (2, False, 10, False), (3, True, 0, False), (4, True, 10, True)]:
                db.add(InventoryItem(item_code=f"INV-STOCK-{index}", name=f"Test product {index}", category="Product", quantity=quantity, unit="bottles",
                    price=25, is_saleable=saleable, is_archived=archived, supplier="Test", date_acquired=self.farm.today, location="Store"))
            db.commit()
        self.assertEqual(self.get(kind="Live Animal")["total"], 1)
        products = self.get(kind="Inventory")
        self.assertEqual(products["total"], 1)
        self.assertEqual(products["items"][0]["suggested_price"], 25)
        self.assertEqual(products["items"][0]["unit"], "bottles")

    def test_stock_endpoint_keeps_authorization_and_limit_boundaries(self):
        path = "/api/v1/production-sales/stock"
        self.assertEqual(self.farm.client.get(path).status_code, 401)
        self.assertEqual(self.farm.client.get(path, headers=self.farm.headers("WORKER1")).status_code, 403)
        for params in [{"limit": 101}, {"offset": -1}, {"kind": "anything"}, {"search": "x" * 121}]:
            self.assertEqual(self.farm.client.get(path, params=params, headers=self.farm.headers("ADMIN")).status_code, 422)
