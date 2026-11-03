USE [JorossFarmDB];
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

PRINT N'============================================================';
PRINT N'JOROSS FARM - FULL FARM DATA RESET';
PRINT N'INCLUDING LIVESTOCK PENS';
PRINT N'============================================================';
PRINT N'';

IF DB_NAME() <> N'JorossFarmDB'
BEGIN
    RAISERROR('STOP: This script can only run on JorossFarmDB.', 16, 1);
    RETURN;
END;

IF OBJECT_ID(N'dbo.users', N'U') IS NULL
   OR OBJECT_ID(N'dbo.roles', N'U') IS NULL
   OR OBJECT_ID(N'dbo.alembic_version', N'U') IS NULL
BEGIN
    RAISERROR('STOP: Required core tables users, roles, or alembic_version were not found.', 16, 1);
    RETURN;
END;

SELECT
    @@SERVERNAME AS SqlServerInstance,
    DB_NAME() AS DatabaseName,
    SUSER_SNAME() AS SqlLogin;

--------------------------------------------------------------------
-- TABLES TO CLEAR
--------------------------------------------------------------------
DECLARE @Targets TABLE
(
    table_name sysname NOT NULL PRIMARY KEY
);

INSERT INTO @Targets (table_name)
VALUES
    (N'audit_logs'),
    (N'crop_growth_records'),
    (N'crop_pest_diseases'),
    (N'crop_yield_records'),
    (N'crops'),
    (N'data_import_rows'),
    (N'data_import_batches'),
    (N'farm_activities'),
    (N'farm_alerts'),
    (N'farm_reports'),
    (N'inventory_stock_records'),
    (N'inventory_items'),
    (N'livestock_feeding_records'),
    (N'livestock_growth_records'),
    (N'livestock_processing_records'),
    (N'livestock_production_records'),
    (N'livestock_reproduction_records'),
    (N'livestock_sale_payments'),
    (N'livestock_sales'),
    (N'livestock_transactions'),
    (N'livestock_vaccination_records'),
    (N'resource_usages'),
    (N'livestock'),
    (N'livestock_pens');

--------------------------------------------------------------------
-- SAFETY CHECK: ALL EXPECTED OPERATIONAL TABLES MUST EXIST
--------------------------------------------------------------------
IF EXISTS
(
    SELECT 1
    FROM @Targets t
    WHERE OBJECT_ID(N'dbo.' + QUOTENAME(t.table_name), N'U') IS NULL
)
BEGIN
    SELECT
        t.table_name AS MissingOperationalTable
    FROM @Targets t
    WHERE OBJECT_ID(N'dbo.' + QUOTENAME(t.table_name), N'U') IS NULL
    ORDER BY t.table_name;

    RAISERROR('STOP: One or more expected operational tables are missing. No data was deleted.', 16, 1);
    RETURN;
END;

--------------------------------------------------------------------
-- SHOW RECORD COUNTS BEFORE RESET
--------------------------------------------------------------------
DECLARE @CountsBefore TABLE
(
    table_name sysname NOT NULL PRIMARY KEY,
    rows_before bigint NOT NULL
);

DECLARE
    @TableName sysname,
    @Sql nvarchar(max),
    @Rows bigint;

DECLARE CountCursor CURSOR LOCAL FAST_FORWARD FOR
SELECT table_name
FROM @Targets
ORDER BY table_name;

OPEN CountCursor;
FETCH NEXT FROM CountCursor INTO @TableName;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @Rows = 0;

    SET @Sql =
        N'SELECT @CountOut = COUNT_BIG(*) FROM dbo.'
        + QUOTENAME(@TableName)
        + N';';

    EXEC sys.sp_executesql
        @Sql,
        N'@CountOut bigint OUTPUT',
        @CountOut = @Rows OUTPUT;

    INSERT INTO @CountsBefore (table_name, rows_before)
    VALUES (@TableName, @Rows);

    FETCH NEXT FROM CountCursor INTO @TableName;
END;

CLOSE CountCursor;
DEALLOCATE CountCursor;

SELECT
    table_name AS TableToClear,
    rows_before AS RecordsBeforeReset
FROM @CountsBefore
ORDER BY table_name;

PRINT N'';
PRINT N'Starting full farm-data reset...';
PRINT N'';

BEGIN TRANSACTION;

--------------------------------------------------------------------
-- DISABLE CONSTRAINTS AND TRIGGERS ON TARGET TABLES
--------------------------------------------------------------------
DECLARE DisableCursor CURSOR LOCAL FAST_FORWARD FOR
SELECT table_name
FROM @Targets
ORDER BY table_name;

OPEN DisableCursor;
FETCH NEXT FROM DisableCursor INTO @TableName;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @Sql =
        N'ALTER TABLE dbo.'
        + QUOTENAME(@TableName)
        + N' NOCHECK CONSTRAINT ALL;';
    EXEC sys.sp_executesql @Sql;

    SET @Sql =
        N'DISABLE TRIGGER ALL ON dbo.'
        + QUOTENAME(@TableName)
        + N';';
    EXEC sys.sp_executesql @Sql;

    FETCH NEXT FROM DisableCursor INTO @TableName;
END;

CLOSE DisableCursor;
DEALLOCATE DisableCursor;

--------------------------------------------------------------------
-- DELETE CHILD / HISTORY / TRANSACTION DATA FIRST
--------------------------------------------------------------------
DELETE FROM dbo.data_import_rows;
DELETE FROM dbo.data_import_batches;

DELETE FROM dbo.livestock_sale_payments;
DELETE FROM dbo.livestock_sales;
DELETE FROM dbo.livestock_processing_records;
DELETE FROM dbo.livestock_feeding_records;
DELETE FROM dbo.livestock_production_records;
DELETE FROM dbo.livestock_reproduction_records;
DELETE FROM dbo.livestock_vaccination_records;
DELETE FROM dbo.livestock_transactions;
DELETE FROM dbo.livestock_growth_records;

DELETE FROM dbo.resource_usages;

DELETE FROM dbo.crop_pest_diseases;
DELETE FROM dbo.crop_yield_records;
DELETE FROM dbo.crop_growth_records;

DELETE FROM dbo.inventory_stock_records;

DELETE FROM dbo.farm_alerts;
DELETE FROM dbo.farm_reports;
DELETE FROM dbo.farm_activities;
DELETE FROM dbo.audit_logs;

--------------------------------------------------------------------
-- DELETE MASTER FARM DATA
--------------------------------------------------------------------
DELETE FROM dbo.livestock;
DELETE FROM dbo.livestock_pens;
DELETE FROM dbo.crops;
DELETE FROM dbo.inventory_items;

--------------------------------------------------------------------
-- RESET IDENTITY VALUES
--------------------------------------------------------------------
DECLARE ReseedCursor CURSOR LOCAL FAST_FORWARD FOR
SELECT table_name
FROM @Targets
ORDER BY table_name;

OPEN ReseedCursor;
FETCH NEXT FROM ReseedCursor INTO @TableName;

WHILE @@FETCH_STATUS = 0
BEGIN
    IF EXISTS
    (
        SELECT 1
        FROM sys.identity_columns ic
        INNER JOIN sys.tables t
            ON t.object_id = ic.object_id
        INNER JOIN sys.schemas s
            ON s.schema_id = t.schema_id
        WHERE s.name = N'dbo'
          AND t.name = @TableName
    )
    BEGIN
        SET @Sql =
            N'DBCC CHECKIDENT (''dbo.'
            + REPLACE(@TableName, '''', '''''')
            + N''', RESEED, 0) WITH NO_INFOMSGS;';

        EXEC sys.sp_executesql @Sql;
    END;

    FETCH NEXT FROM ReseedCursor INTO @TableName;
END;

CLOSE ReseedCursor;
DEALLOCATE ReseedCursor;

--------------------------------------------------------------------
-- RE-ENABLE CONSTRAINTS AND TRIGGERS
--------------------------------------------------------------------
DECLARE EnableCursor CURSOR LOCAL FAST_FORWARD FOR
SELECT table_name
FROM @Targets
ORDER BY table_name;

OPEN EnableCursor;
FETCH NEXT FROM EnableCursor INTO @TableName;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @Sql =
        N'ALTER TABLE dbo.'
        + QUOTENAME(@TableName)
        + N' WITH CHECK CHECK CONSTRAINT ALL;';
    EXEC sys.sp_executesql @Sql;

    SET @Sql =
        N'ENABLE TRIGGER ALL ON dbo.'
        + QUOTENAME(@TableName)
        + N';';
    EXEC sys.sp_executesql @Sql;

    FETCH NEXT FROM EnableCursor INTO @TableName;
END;

CLOSE EnableCursor;
DEALLOCATE EnableCursor;

--------------------------------------------------------------------
-- VERIFY BEFORE COMMIT
--------------------------------------------------------------------
DECLARE @Verify TABLE
(
    table_name sysname NOT NULL PRIMARY KEY,
    records bigint NOT NULL
);

DECLARE VerifyCursor CURSOR LOCAL FAST_FORWARD FOR
SELECT table_name
FROM @Targets
ORDER BY table_name;

OPEN VerifyCursor;
FETCH NEXT FROM VerifyCursor INTO @TableName;

WHILE @@FETCH_STATUS = 0
BEGIN
    SET @Rows = 0;

    SET @Sql =
        N'SELECT @CountOut = COUNT_BIG(*) FROM dbo.'
        + QUOTENAME(@TableName)
        + N';';

    EXEC sys.sp_executesql
        @Sql,
        N'@CountOut bigint OUTPUT',
        @CountOut = @Rows OUTPUT;

    INSERT INTO @Verify (table_name, records)
    VALUES (@TableName, @Rows);

    FETCH NEXT FROM VerifyCursor INTO @TableName;
END;

CLOSE VerifyCursor;
DEALLOCATE VerifyCursor;

IF EXISTS
(
    SELECT 1
    FROM @Verify
    WHERE records <> 0
)
BEGIN
    ROLLBACK TRANSACTION;

    SELECT
        table_name AS TableName,
        records AS RecordsRemaining,
        N'ERROR' AS Status
    FROM @Verify
    WHERE records <> 0
    ORDER BY table_name;

    RAISERROR('RESET FAILED: Some farm records remain. Transaction was rolled back.', 16, 1);
    RETURN;
END;

COMMIT TRANSACTION;

--------------------------------------------------------------------
-- SUCCESS OUTPUT
--------------------------------------------------------------------
PRINT N'';
PRINT N'============================================================';
PRINT N'SUCCESS: FULL FARM DATA RESET COMPLETED';
PRINT N'============================================================';
PRINT N'';
PRINT N'Deleted:';
PRINT N'  Crops and crop history';
PRINT N'  Inventory and stock history';
PRINT N'  Livestock and ALL livestock pens';
PRINT N'  Growth / feeding / vaccination / reproduction / production';
PRINT N'  Sales / payments / processing';
PRINT N'  Resource usage';
PRINT N'  Alerts / activities / reports / audit logs';
PRINT N'  Smart Import history';
PRINT N'';
PRINT N'Preserved:';
PRINT N'  Users';
PRINT N'  Roles';
PRINT N'  Alembic version';
PRINT N'  Alert settings';
PRINT N'  Report automation settings';
PRINT N'  Login history';
PRINT N'  Weather history';
PRINT N'  System backup records';
PRINT N'';

SELECT
    table_name AS ClearedTable,
    records AS RecordsAfterReset,
    N'CLEARED' AS Status
FROM @Verify
ORDER BY table_name;

SELECT
    N'users' AS PreservedTable,
    COUNT_BIG(*) AS Records
FROM dbo.users

UNION ALL
SELECT
    N'roles',
    COUNT_BIG(*)
FROM dbo.roles

UNION ALL
SELECT
    N'alembic_version',
    COUNT_BIG(*)
FROM dbo.alembic_version

UNION ALL
SELECT
    N'alert_settings',
    COUNT_BIG(*)
FROM dbo.alert_settings

UNION ALL
SELECT
    N'report_automation_settings',
    COUNT_BIG(*)
FROM dbo.report_automation_settings

UNION ALL
SELECT
    N'login_history',
    COUNT_BIG(*)
FROM dbo.login_history

UNION ALL
SELECT
    N'weather_history',
    COUNT_BIG(*)
FROM dbo.weather_history

UNION ALL
SELECT
    N'system_backups',
    COUNT_BIG(*)
FROM dbo.system_backups;

SELECT
    @@SERVERNAME AS SqlServerInstance,
    DB_NAME() AS DatabaseName,
    N'All farm operational tables, including livestock_pens, must show 0 / CLEARED.' AS VerificationMessage;

GO
