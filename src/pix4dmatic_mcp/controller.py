from __future__ import annotations

import subprocess
import sys
import time
import types
import tempfile
import re
from pathlib import Path
from typing import Any

import psutil

from .config import Pix4DConfig, load_config
from .errors import Pix4DAutomationError, Pix4DNotFoundError, Pix4DUserActionRequiredError, Pix4DWindowNotFoundError
from .screenshots import capture_screen
from .selectors import MAIN_WINDOW_TITLES, PROCESS_NAMES


def _prepare_comtypes_cache() -> None:
    """Use a writable cache so pywinauto/comtypes works in locked-down profiles."""
    try:
        import comtypes

        cache_dir = Path(tempfile.gettempdir()) / "pix4dmatic_mcp" / "comtypes_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        module = types.ModuleType("comtypes.gen")
        module.__path__ = [str(cache_dir)]
        sys.modules["comtypes.gen"] = module
        comtypes.gen = module
    except Exception:
        return


_prepare_comtypes_cache()

try:
    from pywinauto import Application, Desktop, keyboard, mouse
except Exception:  # pragma: no cover - import depends on Windows desktop packages.
    Application = None
    Desktop = None
    keyboard = None
    mouse = None

try:
    import win32api
    import win32con
    import win32gui
    import win32process
except Exception:  # pragma: no cover - import depends on pywin32.
    win32api = None
    win32con = None
    win32gui = None
    win32process = None


class Pix4DMaticController:
    def __init__(self, config: Pix4DConfig | None = None) -> None:
        self.config = config or load_config()

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
            "foreground_window": self._foreground_window_info(),
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
        self._force_foreground_window(handle)
        win32gui.SetForegroundWindow(handle)
        return {"ok": True, "title": window["title"], "handle": handle, "foreground_window": self._foreground_window_info()}

    def screenshot(self, output_dir: str | None = None) -> dict[str, Any]:
        directory = Path(output_dir) if output_dir else self.config.diagnostics_dir
        path = capture_screen(directory)
        return {"ok": True, "path": str(path)}

    def window_screenshot(self, output_dir: str | None = None) -> dict[str, Any]:
        if win32gui is None:
            raise Pix4DAutomationError("pywin32 screenshot support is not available.")
        from PIL import ImageGrab

        window = self._main_window()
        handle = window.handle if hasattr(window, "handle") else window["handle"]
        left, top, right, bottom = win32gui.GetWindowRect(handle)
        directory = Path(output_dir) if output_dir else self.config.diagnostics_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"pix4dmatic_window_{int(time.time())}.png"
        image = ImageGrab.grab(bbox=(left, top, right, bottom))
        image.save(path)
        return {"ok": True, "path": str(path), "handle": handle, "rectangle": {"left": left, "top": top, "right": right, "bottom": bottom}}

    def send_hotkey(self, keys: str) -> dict[str, Any]:
        if keyboard is None:
            raise Pix4DAutomationError("pywinauto keyboard support is not available.")
        self.focus()
        self._ensure_foreground_for_keyboard()
        keyboard.send_keys(keys)
        return {"ok": True, "keys": keys}

    def type_text(self, text: str, with_spaces: bool = True) -> dict[str, Any]:
        if keyboard is None:
            raise Pix4DAutomationError("pywinauto keyboard support is not available.")
        self.focus()
        self._ensure_foreground_for_keyboard()
        keyboard.send_keys(text, with_spaces=with_spaces, pause=0.01)
        return {"ok": True, "chars": len(text)}

    def click_text(self, text: str, timeout_sec: int | None = None) -> dict[str, Any]:
        timeout = timeout_sec or self.config.default_timeout_sec
        deadline = time.time() + timeout
        last_error: str | None = None
        while time.time() < deadline:
            try:
                window = self._uia_main_window()
                control = self._find_text_control(window, text)
                if control:
                    method = self._activate_control(control)
                    return {"ok": True, "text": text, "backend": "uia", "method": method}
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.5)
        message = f"Text control was not found within {timeout} seconds: {text}"
        if last_error:
            message = f"{message}. Last error: {last_error}"
        raise Pix4DWindowNotFoundError(message)

    def click_menu(self, path: list[str], timeout_sec: int | None = None) -> dict[str, Any]:
        if not path:
            raise Pix4DAutomationError("Menu path must contain at least one item.")
        clicked = []
        for item in path:
            self.click_text(item, timeout_sec=timeout_sec)
            clicked.append(item)
            time.sleep(0.3)
        return {"ok": True, "path": clicked}

    def click_coordinates(self, x: int, y: int) -> dict[str, Any]:
        if not self.config.allow_coordinate_click_fallback:
            raise Pix4DAutomationError("Coordinate click fallback is disabled in config.")
        if mouse is None:
            raise Pix4DAutomationError("pywinauto mouse support is not available.")
        self.focus()
        mouse.click(button="left", coords=(x, y))
        return {"ok": True, "x": x, "y": y}

    def get_ui_tree(self, depth: int = 3) -> dict[str, Any]:
        window = self._uia_main_window()
        controls = []
        for control in window.descendants():
            try:
                rectangle = control.rectangle()
                controls.append(
                    {
                        "text": control.window_text(),
                        "control_type": control.element_info.control_type,
                        "class_name": control.class_name(),
                        "automation_id": control.element_info.automation_id,
                        "rectangle": {
                            "left": rectangle.left,
                            "top": rectangle.top,
                            "right": rectangle.right,
                            "bottom": rectangle.bottom,
                        },
                    }
                )
            except Exception:
                continue
            if len(controls) >= 500:
                break
        return {"ok": True, "depth": depth, "controls": controls}

    def list_menu_items(self, menu_text: str, timeout_sec: int | None = None) -> dict[str, Any]:
        if keyboard is None:
            raise Pix4DAutomationError("pywinauto keyboard support is not available.")
        self.focus()
        self._ensure_foreground_for_keyboard()
        keyboard.send_keys("{ESC}")
        accelerator = self._menu_accelerator(menu_text)
        if accelerator:
            keyboard.send_keys(f"%{accelerator}")
        else:
            self.click_text(menu_text, timeout_sec=timeout_sec or self.config.default_timeout_sec)
        time.sleep(0.5)
        items = self._visible_menu_items()
        if len([item for item in items if item["control_type"] == "MenuItem"]) <= 1 and accelerator:
            self.click_text(menu_text, timeout_sec=timeout_sec or self.config.default_timeout_sec)
            time.sleep(0.5)
            items = self._visible_menu_items()
        keyboard.send_keys("{ESC}")
        return {"ok": True, "menu": menu_text, "items": items}

    def _visible_menu_items(self) -> list[dict[str, Any]]:
        items = []
        for control in self._uia_main_window().descendants():
            try:
                automation_id = control.element_info.automation_id
                control_type = control.element_info.control_type
                if control_type not in {"MenuItem", "Separator", "Menu"} and "MenuBarMenu" not in automation_id:
                    continue
                rect = control.rectangle()
                items.append(
                    {
                        "text": control.window_text(),
                        "control_type": control_type,
                        "automation_id": automation_id,
                        "enabled": control.is_enabled(),
                        "visible": control.is_visible(),
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
        return items

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

    def _uia_main_window(self):
        if Desktop is None or Application is None:
            raise Pix4DAutomationError("pywinauto UI Automation support is not available.")
        windows = self._desktop_windows()
        if windows:
            return windows[0]
        fallback = self._win32_windows()
        if not fallback:
            raise Pix4DWindowNotFoundError("PIX4Dmatic main window was not found.")
        handle = fallback[0]["handle"]
        app = Application(backend="uia").connect(handle=handle)
        return app.window(handle=handle)

    @staticmethod
    def _find_text_control(window, text: str):
        target = text.strip().lower()
        for control in window.descendants():
            try:
                values = [
                    control.window_text(),
                    control.element_info.name,
                    control.element_info.automation_id,
                ]
                if any(value and target in value.strip().lower() for value in values):
                    return control
            except Exception:
                continue
        return None

    @staticmethod
    def _activate_control(control) -> str:
        for method_name in ("invoke", "select", "click"):
            method = getattr(control, method_name, None)
            if method is None:
                continue
            try:
                method()
                return method_name
            except Exception:
                continue
        control.click_input()
        return "click_input"

    @staticmethod
    def _menu_accelerator(menu_text: str) -> str | None:
        match = re.search(r"\(([A-Za-z])\)", menu_text)
        if match:
            return match.group(1).lower()
        return None

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

    def _foreground_window_info(self) -> dict[str, Any] | None:
        if win32gui is None:
            return None
        try:
            handle = win32gui.GetForegroundWindow()
            return {"handle": handle, "title": win32gui.GetWindowText(handle)}
        except Exception:
            return None

    def _ensure_foreground_for_keyboard(self) -> None:
        foreground = self._foreground_window_info()
        if foreground and any(title.lower() in foreground.get("title", "").lower() for title in MAIN_WINDOW_TITLES):
            return
        raise Pix4DUserActionRequiredError(
            f"PIX4Dmatic is not the foreground window; keyboard input was blocked. Foreground: {foreground}"
        )

    @staticmethod
    def _force_foreground_window(handle: int) -> None:
        if win32gui is None or win32process is None or win32api is None:
            return
        try:
            foreground = win32gui.GetForegroundWindow()
            current_thread = win32api.GetCurrentThreadId()
            foreground_thread, _ = win32process.GetWindowThreadProcessId(foreground)
            target_thread, _ = win32process.GetWindowThreadProcessId(handle)
            win32process.AttachThreadInput(current_thread, foreground_thread, True)
            win32process.AttachThreadInput(current_thread, target_thread, True)
            win32gui.BringWindowToTop(handle)
            win32gui.SetActiveWindow(handle)
        except Exception:
            return
        finally:
            try:
                win32process.AttachThreadInput(current_thread, foreground_thread, False)
                win32process.AttachThreadInput(current_thread, target_thread, False)
            except Exception:
                pass

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
