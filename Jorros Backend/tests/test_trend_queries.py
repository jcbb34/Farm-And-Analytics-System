"""Monthly aggregates preserve coverage, growth boundaries, voids and payments."""
from datetime import date, datetime
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import event
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session

import test_multi_item_sales as sales_fixture
from app.models import (CropYieldRecord, InventoryItem, Livestock, LivestockFeedingRecord, LivestockGrowthRecord,
    LivestockProcessingRecord, LivestockProductionRecord, LivestockReproductionRecord,
    LivestockSale, LivestockSalePayment, WeatherHistory)
from app.services.trend_analytics import build_trend_analysis
from app.services.trend_queries import load_trend_aggregates


class TrendQueryTests(TestCase):
    def setUp(self):
        self.fixture = sales_fixture.MultiItemSalesTests()
        self.fixture.setUp()
        self.db, self.engine = self.fixture.db, self.fixture.engine
        self.start, self.end = date(2026, 1, 1), date(2026, 3, 31)
        animal = self.fixture.meat_livestock
        feed = InventoryItem(item_code="INV-TREND-FEED", name="Synthetic feed", category="Feed", quantity=1000, unit="kg",
            supplier="Synthetic", date_acquired=date(2025, 12, 1), location="Test storage")
        self.db.add(feed); self.db.flush()
        for month in range(1, 4):
            for day in range(1, 11):
                number = (month - 1) * 10 + day
                recorded = date(2026, month, day)
                self.db.add(WeatherHistory(recorded_date=recorded, observed_at=datetime(2026, month, day, 8), location="Synthetic",
                    temperature_c=20 + day, humidity_percent=60 + day, rainfall_mm=day, condition="Test"))
                self.db.add(LivestockFeedingRecord(livestock_id=animal.id, inventory_item_id=feed.id, feeding_date=recorded,
                    feeding_slot="Morning", feed_type="Synthetic feed", planned_quantity_kg=2, actual_quantity_kg=2))
                self.db.add(LivestockGrowthRecord(livestock_id=animal.id, measurement_date=recorded, weight_kg=19 + number,
                    previous_weight_kg=18 + number, days_since_previous=1, average_daily_gain_kg=1 if day % 2 else None,
                    animals_measured=5, measurement_basis="Average"))
            self.db.add(CropYieldRecord(crop_id=self.fixture.crop.id, harvest_date=date(2026, month, 1), quantity_kg=10 * (month + 1), harvest_type="Partial Harvest"))
            self.db.add(LivestockReproductionRecord(livestock_id=animal.id, event_date=date(2026, month, 2), record_type="Birth",
                offspring_count=5, alive_offspring=4, breeder_female_quantity=2, confirmed_pregnant_quantity=1, eggs_set=10, fertile_eggs=8, loss_count=1))
            for number in range(2):
                output = LivestockProductionRecord(livestock_id=animal.id, source_type="Livestock", record_date=date(2026, month, 3 + number),
                    output_type="Eggs", unit="pcs", quantity=10, track_sale_inventory=True)
                self.db.add(output); self.db.flush()
                if month == 3 and number == 1:
                    self.db.add(LivestockProcessingRecord(livestock_id=animal.id, production_record_id=output.id,
                        processing_date=date(2026, month, 4), animals_processed=1, meat_output_kg=10, is_voided=True))
        invoice = LivestockSale(sale_code="SALE-TREND-A", source_type="Crop", crop_id=self.fixture.crop.id, sale_type="Product", product_type="Test",
            sale_date=date(2026, 1, 2), quantity=1, unit="kg", unit_price=100, total_amount=100, amount_paid=100, balance_due=0, payment_status="Paid")
        self.db.add(invoice); self.db.flush()
        self.db.add_all([LivestockSalePayment(sale_id=invoice.id, payment_date=date(2026, 1, 3), amount=60, payment_method="Cash"),
            LivestockSalePayment(sale_id=invoice.id, payment_date=date(2026, 2, 3), amount=40, payment_method="Cash")])
        self.db.add(LivestockSale(sale_code="SALE-TREND-VOID", source_type="Livestock", sale_type="Product", product_type="Test",
            sale_date=date(2026, 3, 2), quantity=1, unit="kg", unit_price=900, total_amount=900, amount_paid=0, balance_due=900, payment_status="Unpaid", is_voided=True))
        self.fixture.breeding_livestock.is_archived = True
        self.db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def test_monthly_values_coverage_voids_and_cross_month_payments(self):
        result = build_trend_analysis(self.db, self.start, self.end)
        self.assertEqual([row["crop_yield_kg"] for row in result["monthly"]], [20, 30, 40])
        self.assertEqual([row["feed_consumption_kg"] for row in result["monthly"]], [20, 20, 20])
        self.assertEqual([row["production"]["Eggs (pcs)"] for row in result["monthly"]], [20, 20, 10])
        self.assertEqual([row["cash_collected"] for row in result["monthly"]], [60, 40, 0])
        self.assertTrue(all(row["average_daily_gain_kg"] == 1 for row in result["monthly"]))
        self.assertTrue(all(row["average_rainfall_mm"] == 5.5 for row in result["monthly"]))
        self.assertEqual(result["reproduction_summary"]["offspring_recorded"], 15)
        self.assertEqual(result["reproduction_summary"]["offspring_survival_percent"], 80)
        self.assertEqual(result["data_coverage"]["weather_records"], 30)
        self.assertEqual(result["data_coverage"]["livestock_growth_records"], 30)
        self.assertEqual(result["data_coverage"]["voided_production_records_excluded"], 1)
        self.assertEqual(result["data_coverage"]["sales_records"], 1)
        self.assertEqual(result["health_distribution"], [{"label": "Healthy", "value": 5}])

    def test_growth_uses_first_last_and_full_measurement_count(self):
        data = load_trend_aggregates(self.db, self.start, self.end)
        self.assertEqual(len(data["growth_records"]), 2)
        row = build_trend_analysis(self.db, self.start, self.end)["growth_summary"][0]
        self.assertEqual(row["measurements"], 31)
        self.assertEqual(row["start_weight_kg"], 19)
        self.assertEqual(row["latest_weight_kg"], 49)
        self.assertEqual(row["start_date"], "2025-12-31")
        self.assertEqual(row["latest_date"], "2026-03-10")
        self.assertEqual(row["average_daily_gain_kg"], 0.4348)

    def test_legacy_blank_health_and_unknown_labels_combine(self):
        for index, (status, quantity) in enumerate((("", 2), ("Unknown", 3))):
            self.db.add(Livestock(animal_code=f"LIV-TREND-UNKNOWN-{index}", record_name=f"Synthetic unknown {index}",
                animal_type="Pig", breed="Test", quantity=quantity, weight_kg=10, healthy_quantity=quantity,
                pen_location="Test", daily_feed_kg=1, date_of_birth=date(2025, 1, 1), date_acquired=date(2025, 2, 1), health_status=status))
        self.db.commit()
        self.assertEqual(load_trend_aggregates(self.db, self.start, self.end)["health"], {"Healthy": 5, "Unknown": 5})

    def test_empty_period_preserves_missing_data_and_does_not_hydrate_histories(self):
        loaded = []
        def on_load(session, instance): loaded.append(type(instance).__name__)
        event.listen(Session, "loaded_as_persistent", on_load)
        try:
            with Session(self.engine) as db: result = build_trend_analysis(db, date(2020, 1, 1), date(2020, 1, 31))
        finally: event.remove(Session, "loaded_as_persistent", on_load)
        self.assertEqual(loaded, [])
        self.assertEqual(result["monthly"][0]["crop_yield_kg"], 0)
        self.assertIsNone(result["monthly"][0]["average_rainfall_mm"])
        self.assertEqual(result["growth_summary"], [])
        self.assertTrue(all(row["correlation"] is None for row in result["factor_analysis"]))

    def test_populated_period_uses_scalar_queries_and_sql_server_compilation(self):
        loaded, statements = [], []
        def on_load(session, instance): loaded.append(type(instance).__name__)
        event.listen(Session, "loaded_as_persistent", on_load)
        try:
            with Session(self.engine) as db:
                execute = db.execute
                def inspect(statement, *args, **kwargs):
                    statements.append(str(statement.compile(dialect=mssql.dialect())))
                    return execute(statement, *args, **kwargs)
                with patch.object(db, "execute", inspect): result = build_trend_analysis(db, self.start, self.end)
        finally: event.remove(Session, "loaded_as_persistent", on_load)
        self.assertEqual(loaded, [])
        self.assertEqual(result["data_coverage"]["feeding_records"], 30)
        self.assertLessEqual(len(statements), 10)
        self.assertTrue(any("row_number()" in sql.lower() for sql in statements))
        self.assertFalse(any("SUM(CASE WHEN (EXISTS" in sql.upper() for sql in statements))
