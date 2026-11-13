"""Behavior equivalence and bounded reads, using synthetic SQLite data only."""
from datetime import date
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import event, select
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session

import test_multi_item_sales as sales_fixture
from app.models import LivestockProductionRecord, LivestockSale, LivestockSaleItem, Role, User
from app.routers.production_sales import overview
from app.services.production_overview import source_sales_totals, production_stock_totals
from app.services.production_sales_service import build_serialization_context, serialize_sale


class QueryOptimizationTests(TestCase):
    def setUp(self):
        self.fixture = sales_fixture.MultiItemSalesTests()
        self.fixture.setUp()
        self.db, self.engine = self.fixture.db, self.fixture.engine
        self.sequence = 0
        self.line_numbers = {}

    def tearDown(self):
        self.fixture.tearDown()

    def sale(self, source="Crop", amount=100, paid=60, balance=40, **extra):
        self.sequence += 1
        row = LivestockSale(sale_code=f"SALE-PERF-{self.sequence}", source_type=source, sale_type="Product", product_type="Test output",
            sale_date=date.today(), quantity=1, unit="kg", unit_price=amount, total_amount=amount,
            amount_paid=paid, balance_due=balance, payment_status="Partial", **extra)
        self.db.add(row); self.db.flush()
        return row

    def item(self, sale, source="Crop", amount=100, quantity=1, production_id=None):
        self.line_numbers[sale.id] = self.line_numbers.get(sale.id, 0) + 1
        row = LivestockSaleItem(sale_id=sale.id, line_number=self.line_numbers[sale.id], item_kind="Production", source_type=source,
            source_name_snapshot="Snapshot name", source_code_snapshot="TEST-CODE", product_type="Test output",
            quantity=quantity, unit="kg", unit_price=amount, line_total=amount, production_record_id=production_id)
        self.db.add(row)
        return row

    def test_aggregate_revenue_matches_serialized_mixed_legacy_void_and_zero_invoices(self):
        self.sale(source="Crop", crop_id=self.fixture.crop.id)
        mixed = self.sale(source="Mixed", amount=200, paid=80, balance=120)
        self.item(mixed, "Crop", 50); self.item(mixed, "Livestock", 100); self.item(mixed, "Inventory", 50)
        zero = self.sale(source="Crop", amount=0, paid=0, balance=0)
        self.item(zero, "Crop", 10)
        voided = self.sale(is_voided=True)
        self.item(voided, "Crop", 100)
        empty = self.sale(source="", crop_id=self.fixture.crop.id, amount=12, paid=12, balance=0)
        self.db.commit()
        expected = {"crop": [0.0, 0.0, 0.0], "livestock": [0.0, 0.0, 0.0]}
        for row in self.db.scalars(select(LivestockSale).where(LivestockSale.is_voided == False)):
            serialized = serialize_sale(self.db, row)
            for kind in expected:
                subtotal = sum(line["line_total"] for line in serialized["items"] if line["source_type"].lower() == kind)
                if subtotal <= 0: continue
                ratio = subtotal / serialized["total_amount"] if serialized["total_amount"] > 0 else 0
                expected[kind][0] += subtotal
                expected[kind][1] += serialized["amount_paid"] * ratio
                expected[kind][2] += serialized["balance_due"] * ratio
        actual = source_sales_totals(self.db)
        for kind in expected:
            for before, after in zip(expected[kind], actual[kind]): self.assertAlmostEqual(before, after, places=6)

    def test_stock_totals_do_not_double_count_legacy_fields_of_multi_item_invoices(self):
        identifier = self.fixture.crop_output.id
        modern = self.sale(production_record_id=identifier)
        modern.quantity = 99
        self.item(modern, quantity=10, production_id=identifier)
        legacy = self.sale(production_record_id=identifier); legacy.quantity = 5
        voided = self.sale(production_record_id=identifier, is_voided=True); voided.quantity = 50
        self.item(voided, quantity=50, production_id=identifier)
        self.db.commit()
        totals = production_stock_totals(self.db)
        self.assertEqual(totals["crop_available_kg"], 85)
        self.assertEqual(totals["crop_product_lots"], 1)
        self.fixture.crop_output.quantity = 1; self.db.commit()
        self.assertEqual(production_stock_totals(self.db)["crop_product_lots"], 0)

    def test_overview_database_reads_stay_bounded_as_invoices_grow(self):
        for _ in range(120): self.item(self.sale(), amount=100)
        self.db.commit()
        statements = []
        def record(connection, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith("SELECT"): statements.append(statement)
        event.listen(self.engine, "before_cursor_execute", record)
        try:
            with Session(self.engine) as db: result = overview(db=db, _=None)
        finally: event.remove(self.engine, "before_cursor_execute", record)
        self.assertEqual(result["sales_records"], 120)
        self.assertEqual(result["crop_revenue"], 12000)
        self.assertLessEqual(len(statements), 20)
        self.assertEqual(len(result["recent_sales"]), 10)

    def test_stock_aggregate_does_not_bind_every_production_id(self):
        self.db.add_all([LivestockProductionRecord(source_type="Crop", crop_id=self.fixture.crop.id,
            record_date=date.today(), output_type="Eggplant", quantity=1, unit="kg", track_sale_inventory=True) for _ in range(2205)])
        self.db.commit()
        parameters_seen = []
        def record(connection, cursor, statement, parameters, context, many): parameters_seen.append(len(parameters))
        event.listen(self.engine, "before_cursor_execute", record)
        try: totals = production_stock_totals(self.db)
        finally: event.remove(self.engine, "before_cursor_execute", record)
        self.assertEqual(totals["crop_product_lots"], 2206)
        self.assertEqual(totals["crop_available_kg"], 2305)
        self.assertLess(max(parameters_seen), 100)
        self.assertEqual(len(parameters_seen), 1)

    def test_batched_serialization_preserves_snapshots_legacy_and_current_user_names(self):
        role = Role(name="Performance test role")
        self.db.add(role); self.db.flush()
        self.db.add(User(user_code="USR-PERF", username="perf-user", full_name="Before", password_hash="synthetic", role_id=role.id)); self.db.flush()
        user = self.db.scalar(select(User).where(User.user_code == "USR-PERF"))
        modern = self.sale(source="Mixed", recorded_by_user_id=user.id); self.item(modern, amount=100)
        legacy = self.sale(crop_id=self.fixture.crop.id)
        self.db.commit()
        rows = list(self.db.scalars(select(LivestockSale)))
        expected = [serialize_sale(self.db, row) for row in rows]
        context = build_serialization_context(self.db, rows)
        self.assertEqual([serialize_sale(self.db, row, context=context) for row in rows], expected)
        user.full_name = "After"; self.db.commit()
        next_context = build_serialization_context(self.db, rows)
        self.assertEqual(serialize_sale(self.db, modern, context=next_context)["recorded_by_name"], "After")
        self.assertEqual(serialize_sale(self.db, modern, context=next_context)["items"][0]["source_name"], "Snapshot name")

    def test_aggregate_queries_compile_for_sql_server(self):
        statements = []
        execute = self.db.execute
        def record(statement, *args, **kwargs):
            statements.append(str(statement.compile(dialect=mssql.dialect())))
            return execute(statement, *args, **kwargs)
        with patch.object(self.db, "execute", record):
            source_sales_totals(self.db)
            production_stock_totals(self.db)
        self.assertEqual(len(statements), 2)
        self.assertTrue(all("SELECT EXISTS" not in statement for statement in statements))
        self.assertTrue(any("UNION ALL" in statement for statement in statements))
