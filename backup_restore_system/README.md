# Backup and Restore System

A Python/FastAPI-based backup and restore system for SQL Server databases with Google Drive integration.

## Features

- **Local Backups**: Create ZIP backups of database records and photos
- **Google Drive Integration**: Upload backups to Google Drive
- **Scheduled Backups**: Automatic daily backups at 11 PM
- **Backup Validation**: Verify backup integrity before restore
- **Encryption**: Encrypt backups using Fernet encryption
- **Audit Logging**: Track all backup and restore activities
- **Recovery Kit**: Save application version and restore instructions
- **Email Verification**: Verify admin email before Google Drive connection
- **Backup Reminders**: Customizable backup reminders for admins
- **Smart Reminders**: Intelligent backup reminder system

## Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd backup_restore_system
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/Mac
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Set up Google Drive API**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a project and enable Google Drive API
   - Create OAuth 2.0 credentials
   - Download credentials.json and place in the project root
   - Update `GOOGLE_DRIVE_CREDENTIALS_PATH` in .env

6. **Generate encryption key**
   ```python
   from cryptography.fernet import Fernet
   print(Fernet.generate_key().decode())
   ```
   Add the generated key to `ENCRYPTION_KEY` in .env

7. **Run the application**
   ```bash
   uvicorn main:app --reload
   ```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | / | Health check |
| POST | /backup | Create a manual backup |
| POST | /validate-backup | Validate a backup file |
| POST | /restore | Restore from a backup |
| POST | /upload-to-google-drive | Upload backup to Google Drive |
| GET | /check-google-drive-access | Check Google Drive connection |
| POST | /encrypt-backup | Encrypt a backup |
| POST | /decrypt-backup | Decrypt a backup |
| POST | /send-verification-code | Send email verification code |
| POST | /verify-email | Verify email with code |
| POST | /authenticate-google-drive | Authenticate with Google Drive |
| POST | /set-backup-reminder | Set backup reminder settings |
| GET | /check-backup-status | Check backup status |

## Backup Format

Backups are created as ZIP files containing:
- Database records file
- Photos folder with all associated images

## Security

- Backups are encrypted using Fernet symmetric encryption
- Google Drive access uses OAuth 2.0 with minimal scopes
- Audit logs track all backup/restore operations
- Email verification ensures only authorized admins can configure cloud backups

## Scheduling

Automatic backups run daily at 11 PM. The scheduler starts automatically with the FastAPI application.

## Recovery Process

1. Select backup from local storage or Google Drive
2. Validate backup integrity
3. Decrypt if encrypted
4. Restore to temporary location
4. Verify records and photos
5. Switch to restored database with admin confirmation
6. Require user re-authentication

## Admin Settings

Access the admin settings interface at `/admin-settings` to:
- Verify your email
- Connect your Google Drive
- Configure backup reminders
- Check backup status
- Perform manual backups

## License

MIT