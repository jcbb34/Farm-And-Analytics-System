# email_verification/email_verification.py
import random
import time
from datetime import datetime, timedelta
from fastapi import HTTPException
from config import EMAIL_VERIFICATION_CODE_EXPIRY, MAX_VERIFICATION_ATTEMPTS, MAX_RESEND_ATTEMPTS

class EmailVerification:
    def __init__(self):
        self.verification_codes = {}
        self.verification_attempts = {}
        self.resend_attempts = {}

    def generate_code(self):
        return str(random.randint(100000, 999999))

    def send_verification_code(self, email):
        if email in self.verification_codes:
            if self.resend_attempts.get(email, 0) >= MAX_RESEND_ATTEMPTS:
                raise HTTPException(status_code=400, detail="Maximum resend attempts reached")
            self.resend_attempts[email] = self.resend_attempts.get(email, 0) + 1

        code = self.generate_code()
        expiry_time = datetime.now() + timedelta(seconds=EMAIL_VERIFICATION_CODE_EXPIRY)

        self.verification_codes[email] = {
            'code': code,
            'expiry': expiry_time,
            'verified': False
        }

        # In a real implementation, you would send the email here
        print(f"Verification code for {email}: {code}")  # For demonstration only

        return {"message": "Verification code sent"}

    def verify_code(self, email, code):
        if email not in self.verification_codes:
            raise HTTPException(status_code=400, detail="No verification code sent for this email")

        verification_data = self.verification_codes[email]

        if verification_data['verified']:
            raise HTTPException(status_code=400, detail="Email already verified")

        if datetime.now() > verification_data['expiry']:
            del self.verification_codes[email]
            raise HTTPException(status_code=400, detail="Verification code expired")

        if self.verification_attempts.get(email, 0) >= MAX_VERIFICATION_ATTEMPTS:
            del self.verification_codes[email]
            raise HTTPException(status_code=400, detail="Maximum verification attempts reached")

        if verification_data['code'] != code:
            self.verification_attempts[email] = self.verification_attempts.get(email, 0) + 1
            raise HTTPException(status_code=400, detail="Invalid verification code")

        verification_data['verified'] = True
        return {"message": "Email verified successfully"}

    def is_verified(self, email):
        return email in self.verification_codes and self.verification_codes[email]['verified']