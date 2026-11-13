"""Read-only SQL Server diagnostics. Query text is excluded by default."""
from datetime import datetime, timezone
from sqlalchemy import bindparam, text


SERVER = """SELECT DB_NAME() AS database_name,
    CONVERT(nvarchar(128), SERVERPROPERTY('ProductVersion')) AS product_version,
    CONVERT(nvarchar(128), SERVERPROPERTY('Edition')) AS edition"""
STORE = """SELECT actual_state_desc, desired_state_desc, readonly_reason,
    current_storage_size_mb, max_storage_size_mb, query_capture_mode_desc,
    interval_length_minutes FROM sys.database_query_store_options"""
QUERIES = """SELECT TOP (:limit) q.query_id,
    CONVERT(varchar(18), q.query_hash, 1) AS query_hash,
    COUNT(DISTINCT p.plan_id) AS plan_count,
    SUM(CONVERT(bigint, r.count_executions)) AS executions,
    SUM(r.avg_duration * r.count_executions) / 1000.0 AS total_duration_ms,
    SUM(r.avg_duration * r.count_executions) / NULLIF(SUM(CONVERT(float, r.count_executions)), 0) / 1000.0 AS average_duration_ms,
    MAX(r.max_duration) / 1000.0 AS maximum_duration_ms,
    SUM(r.avg_cpu_time * r.count_executions) / 1000.0 AS total_cpu_ms,
    SUM(r.avg_logical_io_reads * r.count_executions) AS total_logical_reads_pages,
    SUM(r.avg_cpu_time * r.count_executions) / NULLIF(SUM(CONVERT(float, r.count_executions)), 0) / 1000.0 AS average_cpu_ms,
    SUM(r.avg_logical_io_reads * r.count_executions) / NULLIF(SUM(CONVERT(float, r.count_executions)), 0) AS average_logical_reads_pages,
    MIN(r.first_execution_time) AS first_observed_execution,
    MAX(r.last_execution_time) AS last_observed_execution
FROM sys.query_store_query AS q
JOIN sys.query_store_plan AS p ON p.query_id = q.query_id
JOIN sys.query_store_runtime_stats AS r ON r.plan_id = p.plan_id
JOIN sys.query_store_runtime_stats_interval AS i ON i.runtime_stats_interval_id = r.runtime_stats_interval_id
WHERE i.end_time >= DATEADD(hour, -:hours, SYSUTCDATETIME()) AND r.execution_type = 0
GROUP BY q.query_id, q.query_hash
ORDER BY total_duration_ms DESC, q.query_id"""
RANKINGS = {"duration": "total_duration_ms", "cpu": "total_cpu_ms", "reads": "total_logical_reads_pages"}
TABLES = """SELECT TOP (:limit) t.name AS table_name, SUM(p.rows) AS approximate_rows
FROM sys.tables AS t JOIN sys.partitions AS p ON p.object_id = t.object_id
WHERE t.is_ms_shipped = 0 AND p.index_id IN (0, 1)
GROUP BY t.name ORDER BY approximate_rows DESC, t.name"""
INDEXES = """SELECT t.name AS table_name, i.name AS index_name, i.type_desc,
    i.is_unique, i.has_filter, i.filter_definition, c.name AS column_name,
    ic.key_ordinal, ic.is_included_column
FROM sys.tables AS t JOIN sys.indexes AS i ON i.object_id = t.object_id
JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE t.is_ms_shipped = 0 AND i.is_hypothetical = 0
ORDER BY t.name, i.index_id, ic.index_column_id"""


def _read(connection, statement, parameters=None):
    try:
        return {"available": True, "rows": [dict(row) for row in connection.execute(statement, parameters or {}).mappings()]}
    except Exception:
        # Drivers can put connection details in exception messages. Keep the
        # diagnostic export limited to metadata, without credential-bearing text.
        return {"available": False, "reason": "Unavailable with this account, SQL Server version, or Query Store configuration."}


def collect_performance_diagnostics(connection, *, hours=24, limit=20, include_sql=False, sort_by="duration"):
    if not 1 <= hours <= 168 or not 1 <= limit <= 100:
        raise ValueError("Choose 1–168 hours and 1–100 queries.")
    if connection.dialect.name != "mssql":
        raise ValueError("These diagnostics require your actual SQL Server installation.")
    if sort_by not in RANKINGS:
        raise ValueError("Choose duration, cpu, or reads for query ranking.")
    query_statement = QUERIES.replace("ORDER BY total_duration_ms", "ORDER BY " + RANKINGS[sort_by])
    report = {"captured_at": datetime.now(timezone.utc).isoformat(), "hours": hours,
        "ranking": sort_by, "measurement_source": "SQL Server Query Store",
        "window_semantics": "Complete Query Store runtime intervals overlapping the requested lookback; totals may include executions before the exact boundary.",
        "server": _read(connection, text(SERVER)), "query_store": _read(connection, text(STORE)),
        "top_queries": _read(connection, text(query_statement), {"limit": limit, "hours": hours}),
        "tables": _read(connection, text(TABLES), {"limit": limit}), "indexes": _read(connection, text(INDEXES))}
    if include_sql and report["top_queries"]["available"]:
        ids = [row["query_id"] for row in report["top_queries"]["rows"]]
        statement = text("""SELECT q.query_id, t.query_sql_text FROM sys.query_store_query AS q
            JOIN sys.query_store_query_text AS t ON t.query_text_id = q.query_text_id WHERE q.query_id IN :query_ids""")\
            .bindparams(bindparam("query_ids", expanding=True))
        report["query_text"] = _read(connection, statement, {"query_ids": ids}) if ids else {"available": True, "rows": []}
    report["guidance"] = [
        "Run during representative use of the slow pages and compare query duration, reads and plans in SSMS.",
        "Query Store may be off on older SQL Server installations. This script does not enable it or change its settings.",
        "Viewing Query Store statistics requires VIEW DATABASE STATE, or VIEW DATABASE PERFORMANCE STATE on SQL Server 2022 and later.",
        "No indexes, records, database settings or permissions were changed.",
    ]
    store = report["query_store"]
    state = store["rows"][0].get("actual_state_desc") if store["available"] and store["rows"] else None
    if not store["available"] or not state:
        status, action = "unavailable", "Query Store metadata could not be verified. Check the SQL Server version and Query Store viewing permissions; no performance conclusion can be drawn."
    elif state == "OFF":
        status, action = "disabled", "Query Store is OFF. In SSMS, open this database's Properties > Query Store and select Read Write. Use the slow pages, then rerun this exporter. Enabling collection is a separate database setting change."
    elif state == "ERROR":
        status, action = "error", "Query Store reports ERROR. Ask the database administrator to review its health before collecting a workload."
    elif not report["top_queries"]["available"]:
        status, action = "statistics_unavailable", "Query Store options are readable but runtime statistics are not. Review VIEW DATABASE STATE / VIEW DATABASE PERFORMANCE STATE permissions."
    elif state == "READ_ONLY":
        status, action = "read_only", "Query Store is READ_ONLY: retained history is available, but new activity may not be collected. Review readonly_reason and storage limits in SSMS."
    elif not report["top_queries"]["rows"]:
        status, action = "no_samples", "No successful executions were recorded in this window. Use the affected pages while collection is enabled, then rerun. An empty report does not establish that the system is fast."
    else:
        status, action = "measured", "Review the highest-ranked queries in SSMS using their query IDs and hashes. Compare duration, CPU, reads and execution count before deciding on a query or index change."
    report["collection_status"] = status
    report["next_action"] = action
    return report
