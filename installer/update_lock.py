"""Shared application / exclusive updater lock, released by the OS after a crash."""
from __future__ import annotations
from contextlib import contextmanager
import os
from pathlib import Path
import sys

LOCK_NAME = '.shogianalyzer-update.lock'


class InstallationBusy(RuntimeError):
    pass


@contextmanager
def installation_lock(root: Path, *, shared: bool = False):
    path = root / LOCK_NAME
    if path.is_symlink():
        raise RuntimeError('Update lock must not be a symbolic link')
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
        except FileExistsError:
            fd = os.open(path, flags)
    locked = False
    try:
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            class Overlapped(ctypes.Structure):
                _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                            ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                         wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
            kernel.LockFileEx.restype = wintypes.BOOL
            kernel.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                           wintypes.DWORD, ctypes.POINTER(Overlapped)]
            handle = msvcrt.get_osfhandle(fd); overlapped = Overlapped()
            if not kernel.LockFileEx(handle, 1 | (0 if shared else 2), 0, 1, 0, ctypes.byref(overlapped)):
                raise OSError(ctypes.get_last_error(), 'Application or updater is running')
        else:
            import fcntl
            fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        locked = True
        yield
    except OSError as exc:
        if not locked:
            raise InstallationBusy('ShogiAnalyzer または更新処理が実行中です。終了してからやり直してください。') from exc
        raise
    finally:
        if locked:
            if sys.platform == 'win32':
                kernel.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(overlapped))
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
