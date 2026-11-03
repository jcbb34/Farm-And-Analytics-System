# backup/backup_reminder.py
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from config import DEFAULT_BACKUP_REMINDER_DAYS

class BackupReminder:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.last_backup = None
        self.reminder_days = DEFAULT_BACKUP_REMINDER_DAYS
        self.reminder_enabled = True
        self.reminder_time = "09:00"  # Default reminder time

    def set_reminder_days(self, days):
        self.reminder_days = days

    def set_reminder_time(self, time_str):
        self.reminder_time = time_str

    def enable_reminder(self, enabled):
        self.reminder_enabled = enabled

    def record_backup(self):
        self.last_backup = datetime.now()

    def check_backup_status(self):
        if not self.last_backup:
            return "No backups recorded"

        next_reminder = self.last_backup + timedelta(days=self.reminder_days)
        if datetime.now() >= next_reminder:
            return "Backup overdue"
        else:
            return f"Next backup due on {next_reminder.strftime('%Y-%m-%d')}"

    def send_reminder(self):
        if not self.reminder_enabled:
            return

        status = self.check_backup_status()
        if status == "Backup overdue":
            print("Reminder: Backup is overdue!")  # Replace with actual notification

    def start_scheduler(self):
        self.scheduler.add_job(self.send_reminder, 'cron', hour=int(self.reminder_time.split(':')[0]), minute=int(self.reminder_time.split(':')[1]))
        self.scheduler.start()

    def stop_scheduler(self):
        self.scheduler.shutdown()