"""Host-local gates and session generation, independent of the farm database."""

from contextlib import contextmanager
import functools
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from app.core.config import settings


class RecoveryBusy(RuntimeError):
    pass


def control_root():
    value = Path(settings.backup_control_dir)
    return (
        value.resolve()
        if value.is_absolute()
        else (Path(__file__).resolve().parents[2] / value).resolve()
    )


def runtime():
    path = control_root() / "runtime.json"
    if not path.exists():
        return {"epoch": "0", "maintenance": None}
    try:
        value = json.loads(path.read_text())
        if not isinstance(value.get("epoch"), str):
            raise ValueError()
        return value
    except (ValueError, OSError, AttributeError):
        raise RecoveryBusy(
            "Recovery state needs operator attention. Farm access is paused."
        ) from None


def write_runtime(**values):
    folder = control_root()
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = {**runtime(), **values}
    temporary = folder / (".runtime-" + uuid4().hex)
    with temporary.open("w") as file:
        json.dump(data, file)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, folder / "runtime.json")
    return data


def session_epoch():
    return runtime()["epoch"]


class HostLock:
    """Kernel released locks; shared requests and exclusive backup cutovers."""

    def __init__(self, name, *, shared=False, timeout=0):
        self.name, self.shared, self.timeout, self.file = name, shared, timeout, None

    def acquire(self):
        folder = control_root()
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = (folder / (self.name + ".lock")).open("a+b")
        started = time.monotonic()
        while True:
            try:
                if os.name == "nt":
                    import ctypes, msvcrt
                    from ctypes import wintypes

                    class OVERLAPPED(ctypes.Structure):
                        _fields_ = [
                            ("Internal", ctypes.c_size_t),
                            ("InternalHigh", ctypes.c_size_t),
                            ("Offset", wintypes.DWORD),
                            ("OffsetHigh", wintypes.DWORD),
                            ("hEvent", wintypes.HANDLE),
                        ]

                    self.overlapped = OVERLAPPED()
                    fn = ctypes.WinDLL("kernel32", use_last_error=True).LockFileEx
                    fn.argtypes = [
                        wintypes.HANDLE,
                        wintypes.DWORD,
                        wintypes.DWORD,
                        wintypes.DWORD,
                        wintypes.DWORD,
                        ctypes.POINTER(OVERLAPPED),
                    ]
                    fn.restype = wintypes.BOOL
                    if not fn(
                        msvcrt.get_osfhandle(self.file.fileno()),
                        1 | (0 if self.shared else 2),
                        0,
                        1,
                        0,
                        ctypes.byref(self.overlapped),
                    ):
                        raise BlockingIOError()
                else:
                    import fcntl

                    fcntl.flock(
                        self.file.fileno(),
                        (fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX)
                        | fcntl.LOCK_NB,
                    )
                return self
            except (BlockingIOError, OSError):
                if time.monotonic() - started >= self.timeout:
                    self.file.close()
                    self.file = None
                    raise RecoveryBusy(
                        "Another operation is using the system. Try again shortly."
                    ) from None
                time.sleep(0.05)

    def release(self):
        if self.file is None:
            return
        try:
            if os.name == "nt":
                import ctypes, msvcrt
                from ctypes import wintypes

                fn = ctypes.WinDLL("kernel32", use_last_error=True).UnlockFileEx
                fn.argtypes = [
                    wintypes.HANDLE,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                ]
                fn(
                    msvcrt.get_osfhandle(self.file.fileno()),
                    0,
                    1,
                    0,
                    ctypes.byref(self.overlapped),
                )
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.release()


@contextmanager
def farm_access(*, exclusive=False, timeout=0):
    if not exclusive and runtime().get("maintenance"):
        raise RecoveryBusy("Backup or recovery maintenance is in progress.")
    with HostLock("farm-access", shared=not exclusive, timeout=timeout):
        if not exclusive and runtime().get("maintenance"):
            raise RecoveryBusy("Backup or recovery maintenance is in progress.")
        yield


def guarded_background(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with farm_access():
            return fn(*args, **kwargs)

    return wrapped
