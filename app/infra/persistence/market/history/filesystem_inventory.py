from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import stat as stat_module
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class ManagedObject:
    identity: str
    path: str
    logical_bytes: int
    allocated_bytes: int
    link_count: int


@dataclass(frozen=True, slots=True)
class StorageInventory:
    registered_roots: tuple[str, ...]
    logical_bytes: int
    filesystem_allocated_bytes: int
    managed_unique_object_bytes: int
    object_count: int
    path_count: int
    identity_algorithm: str
    allocation_algorithm: str
    checked_at: str
    unknown_paths: tuple[str, ...]
    objects: tuple[ManagedObject, ...]
    paths: tuple[ManagedObject, ...]

    def summary(self) -> dict[str, Any]:
        return {
            "registered_roots": list(self.registered_roots),
            "logical_bytes": self.logical_bytes,
            "filesystem_allocated_bytes": self.filesystem_allocated_bytes,
            "managed_unique_object_bytes": self.managed_unique_object_bytes,
            "object_count": self.object_count,
            "path_count": self.path_count,
            "identity_algorithm": self.identity_algorithm,
            "allocation_algorithm": self.allocation_algorithm,
            "checked_at": self.checked_at,
            "unknown_paths": list(self.unknown_paths),
        }


def registered_roots_inventory(roots: Iterable[Path]) -> StorageInventory:
    """Inventory registered roots using physical allocation and stable object identity."""

    normalized = unique_registered_paths(roots)
    objects: dict[str, ManagedObject] = {}
    managed_paths: list[ManagedObject] = []
    logical_bytes = 0
    path_count = 0
    unknown: list[str] = []
    pending: list[Path] = []
    seen_directories: set[str] = set()
    seen_paths: set[str] = set()
    for root in normalized:
        if root.is_symlink():
            unknown.append(f"{root}: registered root is a symbolic link")
        elif root.is_dir():
            pending.append(root)
        elif root.exists():
            unknown.append(f"{root}: registered root is not a directory")
    while pending:
        directory = pending.pop()
        directory_key = os.path.normcase(os.path.abspath(directory))
        if directory_key in seen_directories:
            continue
        seen_directories.add(directory_key)
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    try:
                        if entry.is_symlink():
                            unknown.append(f"{path}: symbolic link is not a managed object")
                        elif entry.is_dir(follow_symlinks=False):
                            pending.append(path)
                        elif entry.is_file(follow_symlinks=False):
                            absolute_path = Path(os.path.abspath(path))
                            path_key = os.path.normcase(str(absolute_path))
                            if path_key in seen_paths:
                                continue
                            seen_paths.add(path_key)
                            identity, size, allocated, links = file_storage_metadata(absolute_path)
                            logical_bytes += size
                            path_count += 1
                            managed = ManagedObject(
                                identity, str(absolute_path), size, allocated, links,
                            )
                            managed_paths.append(managed)
                            objects.setdefault(
                                identity,
                                managed,
                            )
                    except OSError as exc:
                        unknown.append(f"{path}: {exc}")
        except OSError as exc:
            unknown.append(f"{directory}: {exc}")
    values = tuple(sorted(objects.values(), key=lambda item: item.identity))
    return StorageInventory(
        registered_roots=tuple(str(path) for path in normalized),
        logical_bytes=logical_bytes,
        filesystem_allocated_bytes=sum(item.allocated_bytes for item in values),
        managed_unique_object_bytes=sum(item.logical_bytes for item in values),
        object_count=len(values),
        path_count=path_count,
        identity_algorithm=(
            "windows-volume-serial-and-file-index"
            if os.name == "nt"
            else "device-and-inode"
        ),
        allocation_algorithm=(
            "windows-FileStandardInfo.AllocationSize-per-unique-file"
            if os.name == "nt"
            else "st_blocks-or-conservative-logical-size-per-unique-file"
        ),
        checked_at=datetime.now(timezone.utc).isoformat(),
        unknown_paths=tuple(sorted(set(unknown))),
        objects=values,
        paths=tuple(sorted(managed_paths, key=lambda item: item.path.casefold())),
    )


def filesystem_allocated_bytes(path: Path) -> int:
    """Return the allocated byte count used by one file on the current filesystem."""

    return file_storage_metadata(path.expanduser().resolve())[2]


def managed_object_identity(path: Path) -> str:
    """Return the stable same-filesystem identity used to deduplicate managed files."""

    return file_storage_metadata(path.expanduser().resolve())[0]


def file_storage_metadata(path: Path) -> tuple[str, int, int, int]:
    if os.name == "nt":
        return _windows_file_storage_metadata(path)
    stat = path.stat()
    if not stat_module.S_ISREG(stat.st_mode):
        raise OSError(f"managed object is not a regular file: {path}")
    allocated = getattr(stat, "st_blocks", 0) * 512
    if allocated <= 0 and stat.st_size > 0:
        allocated = stat.st_size
    return f"{stat.st_dev:x}:{stat.st_ino:x}", stat.st_size, allocated, stat.st_nlink


def within_registered_roots(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def unique_registered_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    unique: dict[str, Path] = {}
    for path in paths:
        resolved = path.expanduser().resolve()
        unique.setdefault(os.path.normcase(str(resolved)), resolved)
    return tuple(unique.values())


class _ByHandleFileInformation(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


class _FileStandardInformation(ctypes.Structure):
    _fields_ = [
        ("AllocationSize", ctypes.c_longlong),
        ("EndOfFile", ctypes.c_longlong),
        ("NumberOfLinks", wintypes.DWORD),
        ("DeletePending", wintypes.BOOLEAN),
        ("Directory", wintypes.BOOLEAN),
    ]


if os.name == "nt":
    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CREATE_FILE = _KERNEL32.CreateFileW
    _CREATE_FILE.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _CREATE_FILE.restype = wintypes.HANDLE
    _GET_INFORMATION = _KERNEL32.GetFileInformationByHandle
    _GET_INFORMATION.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ByHandleFileInformation)]
    _GET_INFORMATION.restype = wintypes.BOOL
    _GET_EXTENDED_INFORMATION = _KERNEL32.GetFileInformationByHandleEx
    _GET_EXTENDED_INFORMATION.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _GET_EXTENDED_INFORMATION.restype = wintypes.BOOL
    _CLOSE_HANDLE = _KERNEL32.CloseHandle
    _CLOSE_HANDLE.argtypes = [wintypes.HANDLE]
    _CLOSE_HANDLE.restype = wintypes.BOOL


def _windows_file_storage_metadata(path: Path) -> tuple[str, int, int, int]:

    handle = _CREATE_FILE(
        str(path),
        0x0080,
        0x00000001 | 0x00000002 | 0x00000004,
        None,
        3,
        0x02000000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        information = _ByHandleFileInformation()
        if not _GET_INFORMATION(handle, ctypes.byref(information)):
            raise ctypes.WinError(ctypes.get_last_error())
        standard = _FileStandardInformation()
        if not _GET_EXTENDED_INFORMATION(
            handle,
            1,
            ctypes.byref(standard),
            ctypes.sizeof(standard),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        _CLOSE_HANDLE(handle)
    if standard.Directory:
        raise OSError(f"managed object is not a regular file: {path}")
    logical = (information.nFileSizeHigh << 32) | information.nFileSizeLow
    allocated = standard.AllocationSize
    identity = (
        f"{information.dwVolumeSerialNumber:08x}:"
        f"{information.nFileIndexHigh:08x}{information.nFileIndexLow:08x}"
    )
    return identity, logical, allocated, information.nNumberOfLinks
