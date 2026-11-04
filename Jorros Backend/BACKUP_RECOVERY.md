# Backup & Recovery: installation and operator guide

This module provides complete recovery ZIPs and native SQL Server BAK files,
matching evidence photos, encrypted local storage, Google Drive, automatic backup
jobs, in-app reminders, staged restores, confirmed activation and rollback.

## Install without changing existing farm data

Keep an offline copy of the application, private environment settings, evidence
folder and existing backups. Stop the application before replacing source.
Install Jorros Backend/requirements.txt. In Jorros Frontend run npm ci and npm run
build. Existing Account/User Management fixes are retained.

No farm Alembic revision is added. The existing farm head is e5f6a7b8c9d0. Compare
python -m alembic current and python -m alembic heads on the actual installation.
Review any older pending farm migrations separately; never stamp to bypass them.

Run python scripts/backup_control.py init from Jorros Backend. The independent
control catalog uses versioned migration
app/services/backup_recovery/migrations/001_catalog.sql, schema 1. Initialization
is additive/idempotent and refuses a newer unsupported catalog version. A farm
restore never replaces this catalog, its audit history or schedules.

Protect BACKUP_CONTROL_DIR with OS permissions. Only the backend service and
local administrators should have access. Review Windows NTFS ACLs explicitly;
Python file modes alone do not configure Windows access policy.

Open System Settings > System Data > Backup & Recovery. Check SQL Server,
download the recovery key with password/2FA verification, store it separately
and acknowledge it before scheduling encrypted backups.

## Backend configuration

    BACKUP_CONTROL_DIR=storage/backup_control
    BACKUP_SQL_DIRECTORY=C:\JorossBackupTransfer
    BACKUP_WORKER_ENABLED=true
    BACKUP_WORKER_INTERVAL_SECONDS=5
    BACKUP_MAX_UPLOAD_BYTES=4294967296
    BACKUP_ACTIVATION_ENABLED=false
    BACKUP_GOOGLE_CLIENT_ID=
    BACKUP_GOOGLE_CLIENT_SECRET=
    BACKUP_GOOGLE_REDIRECT_URI=http://localhost:3000/api/v1/backup-recovery/drive/callback
    BACKUP_FRONTEND_RETURN_URL=http://localhost:3000/settings?section=data

Leave activation disabled until a full recovery drill passes on the actual SQL
Server installation. DATABASE_URL is an explicit alternative connection for
isolated tests. Leaving it blank preserves the existing SQL Server configuration.
Building source does not migrate, deploy or connect Google accounts.

The SQL transfer folder must be accessible to both Python and the SQL Server
service identity. For separate computers use an appropriate shared path. Give
those service identities read/write permission. Native backup needs BACKUP
DATABASE permission; staged database creation, restore, CHECKDB and switching
need the appropriate SQL Server administrative rights.

Enable Google Drive API, configure a Web OAuth client/consent screen and register
the exact callback URI. Use HTTPS in deployment; HTTP localhost is for setup.
Store client secrets on the backend. The app requests openid, email and
drive.file, verifies Google's signed identity and verified email, and binds
one-use PKCE state to the still-authorized Admin. Typing an email grants no access.

An app backup folder is created by default. The folder selector lists folders
already accessible to the app under drive.file. Reuse the same Google Cloud app
when recovering on another computer. Configure OAuth publishing for durable
unattended access; testing-mode refresh tokens may expire. A revoked connection
shows Needs reconnection; local backups continue. Refresh tokens and resumable
session locations are encrypted in the catalog. Uploads retain one preallocated
Drive file ID, resume from verified offsets, and verify remote size/checksum.

## Files, verification and retention

- .recovery.zip contains logical records, referenced photos/thumbnails, schema
  revision and hashes. This preserves the existing recovery format.
- .bak is a real SQL Server COPY_ONLY/CHECKSUM backup on a dedicated master
  AUTOCOMMIT connection. Matching .photos.zip contains the photos, BAK hash,
  SQL version and per-table record signatures. A BAK alone has no evidence photos.
- ZIP + BAK is the default. Native failure is Partial; a successful ZIP is retained.
- Farm files use AES-256-GCM when encryption is enabled. Downloads preserve .enc.
  Explicitly confirmed decrypted BAK downloads support manual SQL Server recovery.
- The readable .kit.zip contains matching application source and instructions.
  It excludes live environments, farm records, credentials, tokens and keys.
  Install its dependencies and reconfigure the replacement server before decrypting.
- Existing ZIP and legacy JSON history stays downloadable and protected. JSON-only
  legacy exports are explicitly labelled as records exports without photos.

File validated and Restore tested are separate states. VERIFYONLY does not count
as a real restore. Each selected format must pass its own separate database/photo
restore test: record signatures/counts, relationships, integrity, photos, schema,
basic module reads and an active restored Admin account. Tests expire in 24 hours.

Retention is opt-in and preserves Keep-marked sets, newest verified and newest
restore-tested sets. A replacement cloud backup must upload before automatic
cleanup. Retained previous databases/photos are separate from file retention.
Download an encrypted copy and separate recovery key to an offline drive.

App changes and background farm/report work pause during capture and activation.
Other SQL/file writers such as SSMS are outside these locks; exclude those writers
from the maintenance window too.

## Schedules and reminders

Schedules use Asia/Manila by default and support daily, weekly, monthly or every N
days. Days 29–31 clamp to shorter months' last day. One missed run catches up after
startup. Only one worker runs across API processes, manual operations and the
legacy backup endpoint. Interrupted uploads retry with bounded backoff; other
interrupted jobs become Incomplete. Activation never resumes automatically.

The API worker runs with no open browser. In-app reminders appear for Admins;
email/SMS delivery is not implemented. Keep the server computer running. If backup
jobs must run while the API is stopped, an authorized Windows operator can
configure Task Scheduler every five minutes:

    Program: <backend>\.venv\Scripts\python.exe
    Arguments: scripts\backup_control.py worker-once
    Start in: <backend>

Use the approved service identity and protect its credentials. A powered-off
computer cannot run jobs. Back up protected host/control configuration separately
if schedules/audit must survive loss of the computer; do not distribute its key
beside encrypted Google credentials.

## Required SQL Server drill before enabling activation

On a separate test installation, use generated records and photos. Create ZIP +
BAK and download every matching file plus a separate key. Perform a full ZIP test,
then a full BAK/photo test. Verify real RESTORE and DBCC CHECKDB, exact record
signatures, constraints, photo viewing, restored Admin access and reports.
Test wrong keys, damaged files/photos, wrong companion, unsupported schema/SQL
version, insufficient space, revoked Google access, upload interruption and process
restart. Enable activation on the test installation, switch and verify forced
sign-in, normal module functions and rollback. Record the results before approving
production configuration separately.

SQLite tests verify application orchestration, not native SQL Server behavior.
Newer BAKs cannot restore to older SQL Server versions. TDE or SQL backup encryption
may require separately exported SQL certificates/private keys; file encryption
does not export those certificates.

## Confirmed activation and disaster recovery

Activation rechecks the staged contents, requires current Admin password/2FA and
typed RESTORE, makes a safety backup when the current farm is available, pauses
farm changes and switches both resources. Approval expires in five minutes.
The previous database/photos remain for rollback. Recovery generations outside
the restored database invalidate existing tokens and login challenges. Sign in
using the accounts/passwords present in the restored database.

When farm login/database is unavailable, use an OS-administrator terminal on the
protected server with the matching application and SQL configuration:

    python scripts/backup_control.py status
    python scripts/backup_control.py import <set.recovery.zip.enc> --key-file <offline.key>
    python scripts/backup_control.py import <set.bak.enc> --photos <set.photos.zip.enc> --key-file <offline.key>
    python scripts/backup_control.py test <candidate-id>
    python scripts/backup_control.py activate <candidate-id> --confirm RESTORE --expected-database <DB_NAME>

Add --skip-current-backup only when the working database is unavailable. A healthy
farm cannot skip its safety backup. If the host key is missing but its catalog
and key-id remain, reinstall the matching key without overwriting an existing one:

    python scripts/backup_control.py --restore-missing-key <offline.key> status

Power/process loss during cutover retains a durable activation journal in
runtime.json and leaves farm access paused. Never delete that journal or clear
maintenance by hand. To reinstate and verify the previous safety copy:

    python scripts/backup_control.py repair-previous --confirm ROLLBACK --expected-database <DB_NAME>

The repair compares full records and photos against the safety backup before
reopening access. If the previous copy cannot be confirmed, or the interrupted
offline restore had no safety backup, a SQL administrator must inspect the journal
and retained copies. Unused staged copies can be discarded. Activated/rollback
databases are not dropped by staged cleanup.

References: Microsoft BACKUP/RESTORE VERIFYONLY documentation and Google Drive
manage-uploads / OAuth web-server documentation.
