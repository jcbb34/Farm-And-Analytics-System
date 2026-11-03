import os
import sys
import unittest
from datetime import date, timedelta
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_DRIVER", "ODBC Driver 18 for SQL Server")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret")

try:
    import pyodbc  # noqa: F401
except (ImportError, ModuleNotFoundError):
    class _TestBase(DeclarativeBase):
        pass

    database_module = ModuleType("app.core.database")
    database_module.Base = _TestBase
    database_module.get_db = lambda: iter((None,))
    sys.modules.setdefault("app.core.database", database_module)

from app.core.database import Base
from app.models import (
    AuditLog,
    Crop,
    InventoryItem,
    InventoryStockRecord,
    Livestock,
    LivestockProductionRecord,
    LivestockSale,
    LivestockSaleItem,
    LivestockSalePayment,
)
from app.routers.production_sales import add_sale as add_sale_endpoint
from app.schemas.production_sales import (
    ProcessingCreate,
    SaleCreate,
    SalePaymentCreate,
)
from app.services.production_sales_service import (
    add_sale_payment,
    create_processing,
    create_sale,
    production_available_quantity,
    void_sale,
)
from app.services.farm_intelligence import build_farm_intelligence_overview


class MultiItemSalesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.today = date.today()
        self.actor = SimpleNamespace(id=1, full_name="Farm Manager", username="manager")

        self.crop = Crop(
            crop_code="CRP-SALE-1", name="Eggplant", variety="Long Purple",
            field="Field A", area_hectares=1, quantity_planted=100,
            current_surviving=95, planting_date=self.today - timedelta(days=90),
            estimated_harvest=self.today, status="Harvesting",
        )
        self.meat_livestock = self._livestock(
            "LIV-MEAT-1", "Pig Finisher Batch", "Meat", 5, male=3, female=2
        )
        self.breeding_livestock = self._livestock(
            "LIV-BREED-1", "Breeding Pig Batch", "Breeding", 3, male=1, female=2
        )
        self.product = InventoryItem(
            item_code="INV-PRODUCT-1", name="Farm Chili Sauce",
            category="Processed Product", quantity=30, unit="bottles",
            reorder_level=5, cost=25, price=45, is_saleable=True,
            supplier="JoRoss Farm", date_acquired=self.today - timedelta(days=2),
            location="Finished Goods", is_archived=False,
        )
        self.db.add_all([self.crop, self.meat_livestock, self.breeding_livestock, self.product])
        self.db.flush()
        self.crop_output = LivestockProductionRecord(
            source_type="Crop", crop_id=self.crop.id, output_type="Eggplant",
            record_date=self.today, gross_quantity=100, loss_quantity=0,
            farm_use_quantity=0, reserved_quantity=0, quantity=100,
            unit="kg", destination="Available for sale", track_sale_inventory=True,
        )
        self.db.add(self.crop_output)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _livestock(self, code, name, purpose, quantity, *, male, female):
        return Livestock(
            animal_code=code, record_name=name, animal_type="Pig", breed="Large White",
            quantity=quantity, sex="Mixed", male_quantity=male, female_quantity=female,
            unknown_sex_quantity=0, healthy_quantity=quantity, at_risk_quantity=0,
            sick_quantity=0, under_treatment_quantity=0, health_status="Healthy",
            growth_status="Market Ready", production_purpose=purpose,
            date_of_birth=self.today - timedelta(days=180), weight_kg=80,
            pen_location="Pig Pen", date_acquired=self.today - timedelta(days=150),
            vaccination_status="Vaccinated", is_archived=False,
        )

    def _invoice(self):
        return SaleCreate.model_validate({
            "sale_date": self.today.isoformat(),
            "buyer_name": "Town Market",
            "payment_status": "Partial",
            "amount_paid": 200,
            "payment_method": "Cash",
            "items": [
                {
                    "item_kind": "Production",
                    "production_record_id": self.crop_output.id,
                    "quantity": 10,
                    "unit": "kg",
                    "unit_price": 50,
                },
                {
                    "item_kind": "Inventory",
                    "inventory_item_id": self.product.id,
                    "quantity": 2,
                    "unit": "bottles",
                    "unit_price": 45,
                },
                {
                    "item_kind": "Live Animal",
                    "livestock_id": self.meat_livestock.id,
                    "quantity": 1,
                    "unit": "head",
                    "unit_price": 1000,
                    "male_quantity": 1,
                },
            ],
        })

    def test_multi_item_invoice_updates_every_source_and_preserves_lines(self):
        result = create_sale(self.db, self._invoice(), self.actor)
        self.db.commit()

        self.assertEqual(result["item_count"], 3)
        self.assertEqual(result["source_type"], "Mixed")
        self.assertEqual(result["total_amount"], 1590.0)
        self.assertEqual(result["amount_paid"], 200.0)
        self.assertEqual(result["balance_due"], 1390.0)
        self.assertEqual(self.meat_livestock.quantity, 4)
        self.assertEqual(self.meat_livestock.male_quantity, 2)
        self.assertEqual(float(self.product.quantity), 28.0)
        self.assertEqual(float(production_available_quantity(self.db, self.crop_output)), 90.0)
        self.assertEqual(len(self.db.scalars(select(LivestockSaleItem)).all()), 3)
        movement = self.db.scalar(select(InventoryStockRecord).where(InventoryStockRecord.adjustment_type == "Sale"))
        self.assertIsNotNone(movement)
        self.assertEqual(movement.reference, result["sale_code"])

    def test_invoice_idempotency_prevents_double_stock_deduction(self):
        payload = self._invoice()
        with patch("app.routers.production_sales.evaluate_automatic_tasks"), patch(
            "app.routers.production_sales.evaluate_production_sales_alerts_only"
        ), patch("app.routers.production_sales.evaluate_livestock_alerts_only"):
            first = add_sale_endpoint(payload=payload, idempotency_key="sale-retry-1", db=self.db, current_user=self.actor)
            second = add_sale_endpoint(payload=payload, idempotency_key="sale-retry-1", db=self.db, current_user=self.actor)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.db.scalar(select(LivestockSale).where(LivestockSale.is_voided == False)).id, first["id"])
        self.assertEqual(self.meat_livestock.quantity, 4)
        self.assertEqual(float(self.product.quantity), 28.0)
        self.assertEqual(float(production_available_quantity(self.db, self.crop_output)), 90.0)

    def test_farm_intelligence_handles_decimal_sold_quantities(self):
        create_sale(self.db, self._invoice(), self.actor)
        self.db.commit()

        overview = build_farm_intelligence_overview(self.db, months=12)

        self.assertEqual(overview["period"]["months"], 12)
        self.assertEqual(overview["metrics"]["crop_available_kg"], 90.0)
        self.assertIn("risk_summary", overview)

    def test_partial_payment_history_becomes_paid_without_replacing_history(self):
        sale = create_sale(self.db, self._invoice(), self.actor)
        payment_result = add_sale_payment(
            self.db,
            sale["id"],
            SalePaymentCreate(payment_date=self.today, amount=1390, payment_method="GCash"),
            self.actor,
        )
        self.db.commit()
        self.assertEqual(payment_result["sale"]["payment_status"], "Paid")
        self.assertEqual(payment_result["sale"]["balance_due"], 0)
        payments = list(self.db.scalars(select(LivestockSalePayment).where(LivestockSalePayment.sale_id == sale["id"])).all())
        self.assertEqual(len(payments), 2)
        self.assertEqual(sorted(float(payment.amount) for payment in payments), [200.0, 1390.0])

    def test_void_restores_live_inventory_and_production_stock(self):
        sale = create_sale(self.db, self._invoice(), self.actor)
        self.db.flush()
        voided = void_sale(self.db, sale["id"], "Customer cancelled the complete invoice", self.actor)
        self.db.commit()
        self.assertTrue(voided["is_voided"])
        self.assertEqual(self.meat_livestock.quantity, 5)
        self.assertEqual(self.meat_livestock.male_quantity, 3)
        self.assertEqual(float(self.product.quantity), 30.0)
        self.assertEqual(float(production_available_quantity(self.db, self.crop_output)), 100.0)
        returned = self.db.scalar(select(InventoryStockRecord).where(InventoryStockRecord.adjustment_type == "Returned"))
        self.assertIsNotNone(returned)

    def test_processing_is_restricted_to_explicit_meat_purpose(self):
        payload = ProcessingCreate(
            livestock_id=self.breeding_livestock.id,
            processing_date=self.today,
            animals_processed=1,
            male_quantity=1,
            meat_output_kg=50,
            live_weight_kg=80,
        )
        with self.assertRaises(HTTPException) as error:
            create_processing(self.db, payload, self.actor)
        self.assertIn("Production Purpose", str(error.exception.detail))
        self.assertEqual(self.breeding_livestock.quantity, 3)

        payload.livestock_id = self.meat_livestock.id
        result = create_processing(self.db, payload, self.actor)
        self.db.commit()
        self.assertEqual(result["meat_output_kg"], 50.0)
        self.assertEqual(self.meat_livestock.quantity, 4)
        production = self.db.get(LivestockProductionRecord, result["production_record_id"])
        self.assertEqual(production.output_type, "Meat")


if __name__ == "__main__":
    unittest.main()
