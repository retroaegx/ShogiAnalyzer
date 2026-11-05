"""Do not let the bundled Python's library paths leak into USI engines/system tools."""
from contextlib import contextmanager
import os
import sys

from app_paths import is_frozen


def split_command(command: str) -> list[str]:
    if sys.platform != "win32":
        import shlex
        return shlex.split(command)
    # shlex(posix=False) retains quotes around paths with spaces, and passing
    # those quotes as part of argv[0] makes CreateProcess fail.
    import ctypes
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    count = ctypes.c_int()
    argv = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return list(argv[:count.value])
    finally:
        kernel.LocalFree(argv)



def external_env(env=None) -> dict[str, str]:
    result = dict(os.environ if env is None else env)
    if not is_frozen():
        return result
    for name in ("LD_LIBRARY_PATH", "LIBPATH"):
        original = result.pop(name + "_ORIG", None)
        result.pop(name, None)
        if original is not None:
            result[name] = original
    bundle = os.path.normcase(os.path.abspath(sys._MEIPASS))
    for name in ("PATH", "DYLD_LIBRARY_PATH"):
        if name in result:
            result[name] = os.pathsep.join(p for p in result[name].split(os.pathsep)
                if p and not os.path.normcase(os.path.abspath(p)).startswith(bundle + os.sep)
                and os.path.normcase(os.path.abspath(p)) != bundle)
    return result


@contextmanager
def external_libraries():
    # Windows uses a process-wide DLL directory rather than LD_LIBRARY_PATH.
    # Call only around spawn (without awaiting other work inside this context).
    if is_frozen() and sys.platform == "win32":
        import ctypes
        kernel = ctypes.windll.kernel32
        buffer = ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(buffer), buffer)
        kernel.SetDllDirectoryW(None)
        try:
            yield
        finally:
            kernel.SetDllDirectoryW(buffer.value or None)
    else:
        yield
