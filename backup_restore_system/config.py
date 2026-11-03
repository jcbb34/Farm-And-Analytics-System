# config.py
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Paths
BACKUP_FOLDER = os.path.join(os.getcwd(), "backups")
RECOVERY_KIT_PATH = os.path.join(os.getcwd(), "recovery_kit.txt")
AUDIT_LOG_PATH = os.path.join(os.getcwd(), "backup_audit.log")

# Google Drive
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
GOOGLE_DRIVE_CREDENTIALS_PATH = os.getenv("GOOGLE_DRIVE_CREDENTIALS_PATH")
GOOGLE_DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.file']
GOOGLE_DRIVE_TOKEN_PATH = os.path.join(os.getcwd(), 'google_drive_token.json')

# Encryption
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

# Database paths
DATABASE_RECORDS_PATH = os.getenv("DATABASE_RECORDS_PATH")
PHOTOS_FOLDER_PATH = os.getenv("PHOTOS_FOLDER_PATH")

# Email Verification
EMAIL_VERIFICATION_CODE_EXPIRY = 3600  # 1 hour in seconds
MAX_VERIFICATION_ATTEMPTS = 3
MAX_RESEND_ATTEMPTS = 3

# Backup Settings
DEFAULT_BACKUP_REMINDER_DAYS = 7

# Ensure directories exist
os.makedirs(BACKUP_FOLDER, exist_ok=True)