"""Shared limits for browser sessions; all expiry decisions use server time."""
from datetime import datetime, timezone

SESSION_POLICY_VERSION = 1
IDLE_TIMEOUT_SECONDS = 15 * 60
WARNING_SECONDS = 60
MAX_SESSION_SECONDS = 8 * 60 * 60


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def epoch(value):
    return value.replace(tzinfo=timezone.utc).timestamp()
