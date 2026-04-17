from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

from .config import Pix4DConfig, default_config
from .errors import Pix4DAutomationError, Pix4DNotFoundError, Pix4DWindowNotFoundError
from .screenshots import capture_screen
from .selectors import MAIN_WINDOW_TITLES, PROCESS_NAMES

try:
    from pywinauto import Application, Desktop, keyboard
except Exception:  # pragma: no cover - import depends on Windows desktop packages.
    Application = None
    Desktop = None
    keyboard = None

try:
    import win32con
    import win32gui
except Exception:  # pragma: no cover - import depends on pywin32.
    win32con = None
    win32gui = None


class Pix4DMaticController:
    def __init__(self, config: Pix4DConfig | None = None) -> None:
        self.config = config or default_config()

    def get_processes(self) -> list[psutil.Process]:
        processes: list[psutil.Process] = []
        for proc in psutil.process_iter(["pid", "name", "exe", "status", "create_time", "cpu_percent"]):
            try:
                name = proc.info.get("name") or ""
                exe = proc.info.get("exe") or ""
                if name in PROCESS_NAMES or name.lower() == "pix4dmatic.exe":
                    processes.append(proc)
                elif "pix4dmatic.exe" in exe.lower():
                    processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return processes

    def get_status(self) -> dict[str, Any]:
        processes = self.get_processes()
        windows = self._find_windows()
        return {
            "ok": True,
            "running": bool(processes),
            "processes": [self._process_info(proc) for proc in processes],
            "windows": windows,
            "configured_exe": str(self.config.pix4dmatic_exe) if self.config.pix4dmatic_exe else None,
        }

    def launch(self, exe_path: str | None = None, wait_for_window: bool = True) -> dict[str, Any]:
        existing = self.get_processes()
        if existing:
            return {"ok": True, "launched": False, "message": "PIX4Dmatic is already running.", "status": self.get_status()}

        exe = Path(exe_path) if exe_path else self.config.pix4dmatic_exe
        if not exe or not exe.exists():
            raise Pix4DNotFoundError("PIX4Dmatic executable was not found. Pass exe_path or configure pix4dmatic_exe.")

        subprocess.Popen([str(exe)], cwd=str(exe.parent))
        if wait_for_window:
            self.wait_for_window(self.config.default_timeout_sec)
        return {"ok": True, "launched": True, "status": self.get_status()}

    def focus(self) -> dict[str, Any]:
        window = self._main_window()
        if hasattr(window, "set_focus"):
            window.set_focus()
            return {"ok": True, "title": window.window_text()}

        if win32gui is None or win32con is None:
            raise Pix4DAutomationError("Neither pywinauto nor pywin32 focus support is available.")
        handle = window["handle"]
        win32gui.ShowWindow(handle, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(handle)
        return {"ok": True, "title": window["title"], "handle": handle}

    def screenshot(self, output_dir: str | None = None) -> dict[str, Any]:
        directory = Path(output_dir) if output_dir else self.config.diagnostics_dir
        path = capture_screen(directory)
        return {"ok": True, "path": str(path)}

    def send_hotkey(self, keys: str) -> dict[str, Any]:
        if keyboard is None:
            raise Pix4DAutomationError("pywinauto keyboard support is not available.")
        self.focus()
        keyboard.send_keys(keys)
        return {"ok": True, "keys": keys}

    def type_text(self, text: str, with_spaces: bool = True) -> dict[str, Any]:
        if keyboard is None:
            raise Pix4DAutomationError("pywinauto keyboard support is not available.")
        self.focus()
        keyboard.send_keys(text, with_spaces=with_spaces, pause=0.01)
        return {"ok": True, "chars": len(text)}

    def open_project(self, project_path: str) -> dict[str, Any]:
        path = Path(project_path)
        if not path.exists():
            raise Pix4DNotFoundError(f"Project file does not exist: {path}")
        self.launch(wait_for_window=False)
        exe = self._running_exe_path() or self.config.pix4dmatic_exe
        if not exe:
            raise Pix4DNotFoundError("Cannot determine PIX4Dmatic executable path.")
        subprocess.Popen([str(exe), str(path)], cwd=str(Path(exe).parent))
        self.wait_for_window(self.config.default_timeout_sec)
        return {"ok": True, "project_path": str(path), "status": self.get_status()}

    def wait_for_window(self, timeout_sec: int) -> dict[str, Any]:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            windows = self._find_windows()
            if windows:
                return {"ok": True, "windows": windows}
            time.sleep(1)
        raise Pix4DWindowNotFoundError(f"PIX4Dmatic window was not found within {timeout_sec} seconds.")

    def _running_exe_path(self) -> str | None:
        for proc in self.get_processes():
            try:
                exe = proc.exe()
                if exe:
                    return exe
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def _main_window(self):
        windows = self._desktop_windows()
        if windows:
            return windows[0]
        fallback_windows = self._win32_windows()
        if fallback_windows:
            return fallback_windows[0]
        if not windows:
            raise Pix4DWindowNotFoundError("PIX4Dmatic main window was not found.")
        return windows[0]

    def _desktop_windows(self):
        if Desktop is None:
            return []
        desktop = Desktop(backend="uia")
        matched = []
        for title in MAIN_WINDOW_TITLES:
            matched.extend(desktop.windows(title_re=f".*{title}.*", visible_only=True))
        unique = []
        seen = set()
        for window in matched:
            handle = window.handle
            if handle not in seen:
                unique.append(window)
                seen.add(handle)
        return unique

    def _find_windows(self) -> list[dict[str, Any]]:
        windows = self._find_uia_windows()
        if windows:
            return windows
        return self._win32_windows()

    def _find_uia_windows(self) -> list[dict[str, Any]]:
        if Desktop is None:
            return []
        windows = []
        for window in self._desktop_windows():
            try:
                rect = window.rectangle()
                windows.append(
                    {
                        "title": window.window_text(),
                        "handle": window.handle,
                        "rectangle": {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom,
                        },
                    }
                )
            except Exception:
                continue
        return windows

    def _win32_windows(self) -> list[dict[str, Any]]:
        if win32gui is None:
            return []
        windows: list[dict[str, Any]] = []

        def callback(handle, _extra):
            if not win32gui.IsWindowVisible(handle):
                return
            title = win32gui.GetWindowText(handle)
            if not title:
                return
            if not any(expected.lower() in title.lower() for expected in MAIN_WINDOW_TITLES):
                return
            left, top, right, bottom = win32gui.GetWindowRect(handle)
            windows.append(
                {
                    "title": title,
                    "handle": handle,
                    "backend": "win32",
                    "rectangle": {"left": left, "top": top, "right": right, "bottom": bottom},
                }
            )

        win32gui.EnumWindows(callback, None)
        return windows

    @staticmethod
    def _process_info(proc: psutil.Process) -> dict[str, Any]:
        try:
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "exe": proc.exe(),
                "status": proc.status(),
                "create_time": proc.create_time(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return {"pid": proc.pid, "name": None, "exe": None, "status": "unknown"}
