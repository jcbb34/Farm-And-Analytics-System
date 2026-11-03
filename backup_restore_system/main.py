# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from backup.backup_utils import create_backup, restore_backup, validate_backup
from google_drive.google_drive_utils import GoogleDriveManager
from audit.audit_logging import log_action
from encryption.encryption_utils import encrypt_backup, decrypt_backup
from backup.scheduler import start_scheduler, stop_scheduler
from backup.backup_reminder import BackupReminder
from email_verification.email_verification import EmailVerification
from config import BACKUP_FOLDER
import uvicorn
from fastapi.responses import HTMLResponse
import os

app = FastAPI()

# Initialize services
google_drive_manager = GoogleDriveManager()
email_verification = EmailVerification()
backup_reminder = BackupReminder()

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Start scheduler on startup
@app.on_event("startup")
async def startup_event():
    start_scheduler()
    backup_reminder.start_scheduler()

# Stop scheduler on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    stop_scheduler()
    backup_reminder.stop_scheduler()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def root(request):
    return templates.TemplateResponse("index.html", {"request": request})

# Admin Settings
@app.get("/admin-settings", response_class=HTMLResponse)
async def admin_settings(request):
    return templates.TemplateResponse("admin_settings.html", {"request": request})

# Email Verification Endpoints
@app.post("/send-verification-code")
async def send_verification_code(email: str):
    try:
        return email_verification.send_verification_code(email)
    except HTTPException as e:
        raise e

@app.post("/verify-email")
async def verify_email(email: str, code: str):
    try:
        return email_verification.verify_code(email, code)
    except HTTPException as e:
        raise e

# Google Drive Endpoints
@app.post("/authenticate-google-drive")
async def authenticate_google_drive(email: str):
    try:
        return google_drive_manager.authenticate(email)
    except HTTPException as e:
        raise e

@app.post("/upload-to-google-drive")
async def upload_to_google_drive_endpoint(backup_path: str, folder_id: str):
    try:
        file_id = google_drive_manager.upload_to_google_drive(backup_path, folder_id)
        log_action("Upload to Google Drive", f"File ID: {file_id}, Path: {backup_path}")
        return {"status": "success", "file_id": file_id}
    except HTTPException as e:
        log_action("Upload to Google Drive Failed", str(e))
        raise e

@app.get("/check-google-drive-access")
async def check_google_drive_access_endpoint():
    try:
        access_status = google_drive_manager.check_google_drive_access()
        log_action("Google Drive Access Check", f"Status: {access_status}")
        return {"status": "success", "access_status": access_status}
    except Exception as e:
        log_action("Google Drive Access Check Failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Backup Reminder Endpoints
@app.post("/set-backup-reminder")
async def set_backup_reminder(days: int, time: str, enabled: bool):
    backup_reminder.set_reminder_days(days)
    backup_reminder.set_reminder_time(time)
    backup_reminder.enable_reminder(enabled)
    return {"status": "success", "message": "Backup reminder settings updated"}

@app.get("/check-backup-status")
async def check_backup_status():
    status = backup_reminder.check_backup_status()
    return {"status": "success", "backup_status": status}

# Backup Endpoints
@app.post("/backup")
async def backup():
    try:
        backup_path = create_backup()
        backup_reminder.record_backup()
        log_action("Backup Created", backup_path)
        return {"status": "success", "backup_path": backup_path}
    except Exception as e:
        log_action("Backup Failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Validation and Restore Endpoints
@app.post("/validate-backup")
async def validate_backup_endpoint(backup_path: str):
    try:
        is_valid = validate_backup(backup_path)
        log_action("Backup Validation", f"Valid: {is_valid}, Path: {backup_path}")
        return {"status": "success", "is_valid": is_valid}
    except Exception as e:
        log_action("Backup Validation Failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/restore")
async def restore_backup_endpoint(backup_path: str, restore_path: str):
    try:
        restore_backup(backup_path, restore_path)
        log_action("Backup Restored", f"From: {backup_path}, To: {restore_path}")
        return {"status": "success"}
    except Exception as e:
        log_action("Backup Restore Failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Encryption Endpoints
@app.post("/encrypt-backup")
async def encrypt_backup_endpoint(backup_path: str):
    try:
        encrypted_path = encrypt_backup(backup_path)
        log_action("Backup Encrypted", f"Path: {encrypted_path}")
        return {"status": "success", "encrypted_path": encrypted_path}
    except Exception as e:
        log_action("Backup Encryption Failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/decrypt-backup")
async def decrypt_backup_endpoint(encrypted_path: str, output_path: str):
    try:
        decrypt_backup(encrypted_path, output_path)
        log_action("Backup Decrypted", f"From: {encrypted_path}, To: {output_path}")
        return {"status": "success"}
    except Exception as e:
        log_action("Backup Decryption Failed", str(e))
        raise HTTPException(status_code=500, detail=str(e))