import ctypes
import sys

from trackerblox.app import TrackerbloxApp

_MUTEX_NAME = "TrackerbloxSingleInstanceMutex"
_ERROR_ALREADY_EXISTS = 183


def _acquire_single_instance_mutex() -> object:
    """Create a named Windows mutex. Returns the handle, or exits if already running."""
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
        ctypes.windll.kernel32.CloseHandle(handle)
        ctypes.windll.user32.MessageBoxW(
            None,
            "Trackerblox is already running.\n\nCheck the system tray.",
            "Trackerblox",
            0x40,  # MB_ICONINFORMATION
        )
        sys.exit(0)
    return handle


def main() -> None:
    _mutex = _acquire_single_instance_mutex()  # noqa: F841 — keeps mutex alive for process lifetime
    app = TrackerbloxApp()
    app.start(show_dashboard=True)


if __name__ == "__main__":
    main()
