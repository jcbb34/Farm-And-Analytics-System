# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from backup.backup_utils import create_backup
from google_drive.google_drive_utils import upload_to_google_drive
from audit.audit_logging import log_action

scheduler = BackgroundScheduler()

def scheduled_backup():
    try:
        backup_path = create_backup()
        log_action("Scheduled Backup Created", backup_path)

        # Upload to Google Drive
        file_id = upload_to_google_drive(backup_path)
        log_action("Scheduled Backup Uploaded to Google Drive", f"File ID: {file_id}")
    except Exception as e:
        log_action("Scheduled Backup Failed", str(e))

# Schedule daily backup at 11 PM
scheduler.add_job(scheduled_backup, 'cron', hour=23, minute=0)

def start_scheduler():
    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()