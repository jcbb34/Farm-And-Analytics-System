# encryption_utils.py
from cryptography.fernet import Fernet
from config import ENCRYPTION_KEY

# Encrypt a backup
def encrypt_backup(backup_path):
    fernet = Fernet(ENCRYPTION_KEY)
    encrypted_path = backup_path + ".enc"

    with open(backup_path, 'rb') as f:
        data = f.read()

    encrypted_data = fernet.encrypt(data)

    with open(encrypted_path, 'wb') as f:
        f.write(encrypted_data)

    return encrypted_path

# Decrypt a backup
def decrypt_backup(encrypted_path, output_path):
    fernet = Fernet(ENCRYPTION_KEY)

    with open(encrypted_path, 'rb') as f:
        encrypted_data = f.read()

    decrypted_data = fernet.decrypt(encrypted_data)

    with open(output_path, 'wb') as f:
        f.write(decrypted_data)

    return output_path