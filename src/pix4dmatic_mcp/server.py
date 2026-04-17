from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import load_config
from .controller import Pix4DMaticController
from .errors import Pix4DMaticError
from .workflows import Pix4DWorkflows

mcp = FastMCP("pix4dmatic-mcp")
config = load_config()
controller = Pix4DMaticController(config)
workflows = Pix4DWorkflows(config)


def _safe(callable_obj, *args, **kwargs) -> dict[str, Any]:
    try:
        return callable_obj(*args, **kwargs)
    except Pix4DMaticError as exc:
        return exc.to_result()
    except Exception as exc:
        return {"ok": False, "code": "UNEXPECTED_ERROR", "message": str(exc)}


@mcp.tool()
def pix4d_get_status() -> dict[str, Any]:
    """Return PIX4Dmatic process and window status."""
    return _safe(controller.get_status)


@mcp.tool()
def pix4d_launch(exe_path: str | None = None) -> dict[str, Any]:
    """Launch PIX4Dmatic or attach to the existing process."""
    return _safe(controller.launch, exe_path)


@mcp.tool()
def pix4d_focus() -> dict[str, Any]:
    """Focus the PIX4Dmatic main window."""
    return _safe(controller.focus)


@mcp.tool()
def pix4d_screenshot(output_dir: str | None = None) -> dict[str, Any]:
    """Save a screenshot of the current desktop."""
    return _safe(controller.screenshot, output_dir)


@mcp.tool()
def pix4d_send_hotkey(keys: str) -> dict[str, Any]:
    """Send a pywinauto hotkey string to PIX4Dmatic, for example '^o' or '{F5}'."""
    return _safe(controller.send_hotkey, keys)


@mcp.tool()
def pix4d_type_text(text: str) -> dict[str, Any]:
    """Type plain text into the focused PIX4Dmatic control."""
    return _safe(controller.type_text, text)


@mcp.tool()
def pix4d_click_text(text: str, timeout_sec: int | None = None) -> dict[str, Any]:
    """Click a visible PIX4Dmatic UI control by accessible text."""
    return _safe(controller.click_text, text, timeout_sec)


@mcp.tool()
def pix4d_click_menu(path: list[str], timeout_sec: int | None = None) -> dict[str, Any]:
    """Click a menu or menu-like UI path by visible text labels."""
    return _safe(controller.click_menu, path, timeout_sec)


@mcp.tool()
def pix4d_get_ui_tree(depth: int = 3) -> dict[str, Any]:
    """Return a compact UI Automation tree for selector discovery."""
    return _safe(controller.get_ui_tree, depth)


@mcp.tool()
def pix4d_open_project(project_path: str) -> dict[str, Any]:
    """Open an existing PIX4Dmatic project file."""
    return _safe(controller.open_project, project_path)


@mcp.tool()
def pix4d_read_latest_logs(lines: int = 200, project_dir: str | None = None) -> dict[str, Any]:
    """Read recent lines from the newest discovered PIX4Dmatic log file."""
    return _safe(workflows.read_latest_logs, lines, project_dir)


@mcp.tool()
def pix4d_find_log_errors(lines: int = 1000, project_dir: str | None = None) -> dict[str, Any]:
    """Summarize warnings and errors from the latest PIX4Dmatic log."""
    return _safe(workflows.find_log_errors, lines, project_dir)


@mcp.tool()
def pix4d_start_processing(selectors: list[str] | None = None, timeout_sec: int | None = None) -> dict[str, Any]:
    """Start processing by clicking the first matching processing control."""
    return _safe(workflows.start_processing, selectors, timeout_sec)


@mcp.tool()
def pix4d_wait_until_idle(
    timeout_sec: int | None = None,
    poll_sec: int = 10,
    idle_cpu_percent: float = 5.0,
    idle_checks: int = 3,
    project_dir: str | None = None,
) -> dict[str, Any]:
    """Wait until PIX4Dmatic appears idle based on process CPU and recent logs."""
    return _safe(workflows.wait_until_idle, timeout_sec, poll_sec, idle_cpu_percent, idle_checks, project_dir)


@mcp.tool()
def pix4d_check_outputs(project_dir: str, expected: list[str]) -> dict[str, Any]:
    """Check whether expected PIX4Dmatic outputs exist under a project directory."""
    return _safe(workflows.check_outputs, project_dir, expected)


@mcp.tool()
def pix4d_analyze_project(project_dir: str, project_file: str | None = None) -> dict[str, Any]:
    """Inspect a PIX4Dmatic project folder for image references, logs, and outputs."""
    return _safe(workflows.analyze_project, project_dir, project_file)


@mcp.tool()
def pix4d_collect_diagnostics(output_dir: str, project_dir: str | None = None) -> dict[str, Any]:
    """Collect screenshot, recent logs, and status into a diagnostics directory."""
    return _safe(workflows.collect_diagnostics, output_dir, project_dir)


@mcp.tool()
def pix4d_run_job_object(job: dict[str, Any]) -> dict[str, Any]:
    """Run a job object against the current PIX4Dmatic session or an existing project_path."""
    return _safe(workflows.run_job_object, job)


@mcp.tool()
def pix4d_run_job(job_path: str) -> dict[str, Any]:
    """Load and run a JSON job file."""
    def _load_and_run() -> dict[str, Any]:
        with open(job_path, "r", encoding="utf-8") as file:
            job = json.load(file)
        return workflows.run_job_object(job)

    return _safe(_load_and_run)


@mcp.tool()
def pix4d_run_batch_object(batch: dict[str, Any]) -> dict[str, Any]:
    """Run multiple jobs sequentially from a batch object."""
    return _safe(workflows.run_batch_object, batch)


@mcp.tool()
def pix4d_run_batch(batch_path: str) -> dict[str, Any]:
    """Load and run a JSON batch file."""
    return _safe(workflows.run_batch_file, batch_path)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
