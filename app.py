import os
import sys


def _setup_logging():
    """Windowed builds have no console: send stderr to a small log file so crashes are diagnosable."""
    try:
        from config import APP_DIR
        APP_DIR.mkdir(parents=True, exist_ok=True)
        path = APP_DIR / "apextorrent.log"
        if path.exists() and path.stat().st_size > 1_000_000:
            path.unlink()
        log = open(path, "a", buffering=1, encoding="utf-8")
        if sys.stderr is None or getattr(sys, "frozen", False):
            sys.stderr = log
        if sys.stdout is None:
            sys.stdout = log
    except OSError:
        pass


_MUTEX = None


def _create_mutex():
    """Named mutex so the Inno Setup installer/uninstaller (AppMutex) can detect a running instance."""
    global _MUTEX
    if os.name == "nt":
        try:
            import ctypes
            _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, "ApexTorrentSingleInstanceMutex")
        except Exception:
            pass


if __name__ == "__main__":
    _setup_logging()
    if "--selftest" not in sys.argv:
        _create_mutex()
    from gui import main
    sys.exit(main())
