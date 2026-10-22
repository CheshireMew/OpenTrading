"""Windows lifetime ownership for the single-console development launcher."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _BasicLimits), ('IoInfo', _IoCounters),
               ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
               ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]


def _kernel():
    if os.name != 'nt':
        raise RuntimeError('当前启动器用于 Windows。')
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    api.CreateEventW.restype = wintypes.HANDLE
    api.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    api.OpenEventW.restype = wintypes.HANDLE
    api.SetEvent.argtypes = [wintypes.HANDLE]
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    return api


def _check(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


class ProcessJob:
    """Closing the launcher also closes every descendant, including reload workers."""
    def __init__(self):
        self.api = _kernel()
        self.handle = _check(self.api.CreateJobObjectW(None, None))
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            _check(self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        except BaseException:
            self.close()
            raise

    def add(self, process):
        _check(self.api.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))))

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def event_name(root: Path):
    key = hashlib.sha256(str(root.resolve()).casefold().encode('utf8')).hexdigest()[:24]
    return 'Local\\OpenTradingLauncherStop-' + key


class StopEvent:
    def __init__(self, root):
        self.api = _kernel()
        self.handle = _check(self.api.CreateEventW(None, True, False, event_name(root)))

    def is_set(self):
        return self.api.WaitForSingleObject(self.handle, 0) == 0

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def request_stop(root):
    api = _kernel()
    handle = api.OpenEventW(0x0002, False, event_name(root))  # EVENT_MODIFY_STATE
    if not handle:
        return False
    try:
        _check(api.SetEvent(handle))
        return True
    finally:
        api.CloseHandle(handle)


class LauncherLock:
    def __init__(self, path):
        self.path, self.handle = Path(path), None

    def acquire(self):
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        handle.seek(0)
        handle.write(b'0')
        handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def close(self):
        if self.handle:
            import msvcrt
            try:
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self.handle.close()
                self.handle = None
