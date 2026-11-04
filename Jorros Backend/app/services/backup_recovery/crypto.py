"""Streaming authenticated encryption. Keys never accompany backup files."""

import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
from cryptography.exceptions import InvalidTag
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from app.core.recovery_runtime import HostLock

MAGIC = b"JOROSS-ENC1\n"
CHUNK = 1024 * 1024


class BackupError(ValueError):
    pass


def sha256_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(CHUNK), b""):
            result.update(block)
    return result.hexdigest()


def encrypted_file(path):
    with Path(path).open("rb") as file:
        return file.read(len(MAGIC)) == MAGIC


class Keyring:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / "recovery.key"
        with HostLock("key-init", timeout=10):
            marker = root / "key-id"
            if not self.path.exists():
                if marker.exists():
                    raise BackupError(
                        "The host recovery key is missing. Reinstall its matching offline copy."
                    )
                with os.fdopen(
                    os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600),
                    "wb",
                ) as file:
                    file.write(base64.urlsafe_b64encode(secrets.token_bytes(32)))
                    file.flush()
                    os.fsync(file.fileno())
            self.raw = self.parse(self.path.read_bytes())
            self.id = hashlib.sha256(self.raw).hexdigest()[:32]
            if marker.exists() and marker.read_text().strip() != self.id:
                raise BackupError("The host recovery key does not match its catalog.")
            marker.write_text(self.id)

    @staticmethod
    def parse(value):
        try:
            raw = base64.urlsafe_b64decode(value.strip())
            if len(raw) != 32:
                raise ValueError()
            return raw
        except (ValueError, TypeError):
            raise BackupError("Choose a valid Joross recovery key file.") from None

    def fernet(self):
        return Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(self.raw + b"/google/v1").digest())
        )

    def seal(self, value):
        return self.fernet().encrypt(json.dumps(value).encode()).decode()

    def unseal(self, value):
        try:
            return json.loads(self.fernet().decrypt(value.encode()))
        except (InvalidToken, ValueError):
            raise BackupError(
                "Saved Google access could not be unlocked. Reconnect Google Drive."
            ) from None

    def encrypt(self, source, target):
        header = MAGIC + bytes.fromhex(self.id) + secrets.token_bytes(12)
        cipher = Cipher(algorithms.AES(self.raw), modes.GCM(header[-12:])).encryptor()
        cipher.authenticate_additional_data(header)
        try:
            with Path(source).open("rb") as original, Path(target).open("wb") as output:
                output.write(header)
                for block in iter(lambda: original.read(CHUNK), b""):
                    output.write(cipher.update(block))
                output.write(cipher.finalize())
                output.write(cipher.tag)
        except Exception:
            Path(target).unlink(missing_ok=True)
            raise

    def decrypt(self, source, target, key=None):
        raw = self.raw if key is None else self.parse(key)
        size = Path(source).stat().st_size
        length = len(MAGIC) + 28
        try:
            with Path(source).open("rb") as original:
                header = original.read(length)
                if (
                    size < length + 16
                    or not header.startswith(MAGIC)
                    or header[len(MAGIC) : len(MAGIC) + 16].hex()
                    != hashlib.sha256(raw).hexdigest()[:32]
                ):
                    raise BackupError("This backup requires its matching recovery key.")
                original.seek(-16, 2)
                tag = original.read(16)
                original.seek(length)
                cipher = Cipher(
                    algorithms.AES(raw), modes.GCM(header[-12:], tag)
                ).decryptor()
                cipher.authenticate_additional_data(header)
                remaining = size - length - 16
                with Path(target).open("wb") as output:
                    while remaining:
                        block = original.read(min(CHUNK, remaining))
                        if not block:
                            raise BackupError("Encrypted backup is incomplete.")
                        remaining -= len(block)
                        output.write(cipher.update(block))
                    output.write(cipher.finalize())
        except Exception as error:
            Path(target).unlink(missing_ok=True)
            if isinstance(error, InvalidTag):
                raise BackupError(
                    "The encrypted backup failed its integrity check."
                ) from None
            raise
