# google_drive/google_drive_utils.py
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config import GOOGLE_DRIVE_SCOPES, GOOGLE_DRIVE_TOKEN_PATH
from email_verification.email_verification import EmailVerification

class GoogleDriveManager:
    def __init__(self):
        self.email_verification = EmailVerification()
        self.creds = None

    def authenticate(self, email):
        if not self.email_verification.is_verified(email):
            raise HTTPException(status_code=400, detail="Email not verified")

        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', GOOGLE_DRIVE_SCOPES)
        self.creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open(GOOGLE_DRIVE_TOKEN_PATH, 'w') as token:
            token.write(self.creds.to_json())

        return {"message": "Google Drive authenticated successfully"}

    def upload_to_google_drive(self, backup_path, folder_id):
        if not self.creds or not self.creds.valid:
            raise HTTPException(status_code=401, detail="Google Drive not authenticated")

        service = build('drive', 'v3', credentials=self.creds)

        file_metadata = {
            'name': os.path.basename(backup_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(backup_path, resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

        return file.get('id')

    def check_google_drive_access(self):
        if not self.creds or not self.creds.valid:
            return "Access Denied: Not authenticated"

        try:
            service = build('drive', 'v3', credentials=self.creds)
            service.files().list(pageSize=1).execute()
            return "Access Granted"
        except Exception as e:
            return f"Access Denied: {str(e)}"