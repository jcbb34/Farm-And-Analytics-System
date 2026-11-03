# backup_utils.py
import os
import time
import zipfile
import shutil
from config import BACKUP_FOLDER, DATABASE_RECORDS_PATH, PHOTOS_FOLDER_PATH

# Create a backup
def create_backup():
    backup_name = f"backup_{int(time.time())}.zip"
    backup_path = os.path.join(BACKUP_FOLDER, backup_name)

    with zipfile.ZipFile(backup_path, 'w') as zipf:
        # Add database records
        if os.path.exists(DATABASE_RECORDS_PATH):
            zipf.write(DATABASE_RECORDS_PATH, os.path.basename(DATABASE_RECORDS_PATH))

        # Add photos
        if os.path.exists(PHOTOS_FOLDER_PATH):
            for root, dirs, files in os.walk(PHOTOS_FOLDER_PATH):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, PHOTOS_FOLDER_PATH)
                    zipf.write(file_path, arcname)

    return backup_path

# Validate a backup
def validate_backup(backup_path):
    try:
        with zipfile.ZipFile(backup_path, 'r') as zipf:
            zipf.testzip()  # Check for corruption
        return True
    except zipfile.BadZipFile:
        return False

# Restore a backup
def restore_backup(backup_path, restore_path):
    with zipfile.ZipFile(backup_path, 'r') as zipf:
        zipf.extractall(restore_path)

    # Additional logic to update database and photo paths if needed
    return True