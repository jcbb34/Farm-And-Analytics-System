# audit_logging.py
import logging
from config import AUDIT_LOG_PATH

# Configure logging
logging.basicConfig(
    filename=AUDIT_LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Log an action
def log_action(action, details):
    logging.info(f"{action}: {details}")