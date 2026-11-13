import json
from types import SimpleNamespace
from unittest import TestCase

from app.services.performance_diagnostics import collect_performance_diagnostics


class FakeConnection:
    dialect = SimpleNamespace(name="mssql")

    def __init__(self, fail=False): self.calls, self.fail, self.rows = [], fail, []

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        if self.fail: raise RuntimeError("password=private-connection-detail")
        self.rows = [{"query_id": 42, "query_hash": "0xABC"}] if "AS total_duration_ms" in str(statement) else []
        return self

    def mappings(self): return iter(self.rows)


class PerformanceDiagnosticTests(TestCase):
    def test_default_export_only_reads_metadata_and_binds_limits(self):
        connection = FakeConnection()
        report = collect_performance_diagnostics(connection, hours=12, limit=10)
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql, _ in connection.calls))
        self.assertEqual(len(connection.calls), 5)
        self.assertNotIn("query_text", report)
        self.assertEqual(connection.calls[2][1], {"limit": 10, "hours": 12})

    def test_permission_errors_do_not_export_connection_details(self):
        report = collect_performance_diagnostics(FakeConnection(fail=True))
        self.assertFalse(report["query_store"]["available"])
        self.assertNotIn("private-connection-detail", json.dumps(report))

    def test_query_text_requires_explicit_option_and_uses_returned_ids(self):
        connection = FakeConnection()
        report = collect_performance_diagnostics(connection, include_sql=True)
        self.assertIn("query_text", report)
        self.assertEqual(connection.calls[-1][1], {"query_ids": [42]})

    def test_diagnostic_rejects_invalid_ranges_and_non_sql_server_without_reads(self):
        connection = FakeConnection()
        for options in ({"hours": 0}, {"hours": 169}, {"limit": 101}):
            with self.assertRaises(ValueError): collect_performance_diagnostics(connection, **options)
        connection.dialect = SimpleNamespace(name="sqlite")
        with self.assertRaises(ValueError): collect_performance_diagnostics(connection)
        self.assertEqual(connection.calls, [])

class StoreConnection(FakeConnection):
    def __init__(self, state='READ_WRITE', samples=True, denied=False):
        super().__init__(); self.state,self.samples,self.denied=state,samples,denied
    def execute(self, statement, parameters):
        self.calls.append((str(statement),parameters))
        if 'FROM sys.database_query_store_options' in str(statement):
            self.rows=[{'actual_state_desc':self.state,'readonly_reason':0}]
        elif 'AS total_duration_ms' in str(statement):
            if self.denied:raise RuntimeError('credential=must-not-export')
            self.rows=[{'query_id':9,'executions':10,'total_duration_ms':1200,'total_cpu_ms':400,'total_logical_reads_pages':250}] if self.samples else []
        else:self.rows=[]
        return self

class QueryStoreCollectionTests(TestCase):
    def test_collection_states_do_not_claim_unavailable_workloads_are_fast(self):
        for state,samples,denied,expected in [('OFF',False,False,'disabled'),('READ_ONLY',True,False,'read_only'),('READ_WRITE',False,False,'no_samples'),('READ_WRITE',True,False,'measured'),('READ_WRITE',True,True,'statistics_unavailable'),('ERROR',False,False,'error')]:
            with self.subTest(state=state,samples=samples,denied=denied):
                connection=StoreConnection(state,samples,denied)
                report=collect_performance_diagnostics(connection)
                self.assertEqual(report['collection_status'],expected)
                self.assertTrue(report['next_action'])
                self.assertNotIn('must-not-export',json.dumps(report))
                self.assertTrue(all(sql.lstrip().startswith('SELECT') for sql,_ in connection.calls))
    def test_duration_cpu_and_reads_rankings_only_select_whitelisted_metrics(self):
        for ranking,metric in [('duration','total_duration_ms'),('cpu','total_cpu_ms'),('reads','total_logical_reads_pages')]:
            connection=StoreConnection()
            report=collect_performance_diagnostics(connection,sort_by=ranking)
            self.assertEqual(report['ranking'],ranking)
            self.assertIn(f'ORDER BY {metric} DESC',connection.calls[2][0])
            self.assertIn('intervals',report['window_semantics'])
        connection=StoreConnection()
        with self.assertRaises(ValueError):collect_performance_diagnostics(connection,sort_by='duration; DROP TABLE crops')
        self.assertEqual(connection.calls,[])
