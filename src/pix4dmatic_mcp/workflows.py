from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from .config import Pix4DConfig, default_config
from .controller import Pix4DMaticController
from .errors import Pix4DMaticError, Pix4DTimeoutError, Pix4DUserActionRequiredError
from .logs import find_log_files, read_tail, summarize_log_lines
from .screenshots import capture_screen
from .selectors import BUTTON_START_PROCESSING


OUTPUT_PATTERNS = {
    "quality_report": ["*quality*report*.pdf", "*report*.pdf", "*quality*.html"],
    "orthomosaic": ["*orthomosaic*.tif", "*orthomosaic*.tiff", "*ortho*.tif", "*ortho*.tiff"],
    "dsm": ["*dsm*.tif", "*dsm*.tiff"],
    "dtm": ["*dtm*.tif", "*dtm*.tiff"],
    "dense_point_cloud": ["*.las", "*.laz", "*point*cloud*"],
    "mesh": ["*.obj", "*.ply", "*.fbx"],
    "contour_lines": ["*contour*.shp", "*contour*.dxf"],
}


class Pix4DWorkflows:
    def __init__(self, config: Pix4DConfig | None = None) -> None:
        self.config = config or default_config()
        self.controller = Pix4DMaticController(self.config)

    def read_latest_logs(self, lines: int = 200, project_dir: str | None = None) -> dict[str, Any]:
        logs = find_log_files(self.config.log_search_dirs, Path(project_dir) if project_dir else None)
        if not logs:
            return {"ok": True, "logs": [], "message": "No PIX4Dmatic log files were found."}
        latest = logs[0]
        tail = read_tail(latest.path, lines=lines)
        return {
            "ok": True,
            "latest_log": str(latest.path),
            "latest_log_modified_ts": latest.modified_ts,
            "lines": tail,
            "summary": summarize_log_lines(tail),
        }

    def find_log_errors(self, lines: int = 1000, project_dir: str | None = None) -> dict[str, Any]:
        result = self.read_latest_logs(lines=lines, project_dir=project_dir)
        if not result.get("latest_log"):
            return result
        return {"ok": True, "latest_log": result["latest_log"], "summary": result["summary"]}

    def start_processing(self, selectors: list[str] | None = None, timeout_sec: int | None = None) -> dict[str, Any]:
        candidates = selectors or BUTTON_START_PROCESSING
        attempts = []
        for text in candidates:
            try:
                result = self.controller.click_text(text, timeout_sec=timeout_sec or 3)
                if result.get("ok"):
                    return {"ok": True, "method": "click_text", "selector": text, "attempts": attempts}
                attempts.append({"selector": text, "result": result})
            except Pix4DMaticError as exc:
                attempts.append({"selector": text, "result": exc.to_result()})
        raise Pix4DUserActionRequiredError(
            "Could not find a processing start control. Use pix4d_get_ui_tree to inspect the current UI."
        )

    def wait_until_idle(
        self,
        timeout_sec: int | None = None,
        poll_sec: int = 10,
        idle_cpu_percent: float = 5.0,
        idle_checks: int = 3,
        project_dir: str | None = None,
    ) -> dict[str, Any]:
        timeout = timeout_sec or self.config.processing_timeout_sec
        deadline = time.time() + timeout
        consecutive_idle = 0
        samples = []
        last_summary: dict[str, Any] | None = None

        for proc in self.controller.get_processes():
            try:
                proc.cpu_percent(interval=None)
            except Exception:
                continue

        while time.time() < deadline:
            time.sleep(max(1, poll_sec))
            process_samples = []
            cpu_total = 0.0
            for proc in self.controller.get_processes():
                try:
                    cpu = proc.cpu_percent(interval=None)
                    cpu_total += cpu
                    process_samples.append({"pid": proc.pid, "name": proc.name(), "cpu_percent": cpu})
                except Exception:
                    continue

            log_result = self.read_latest_logs(lines=300, project_dir=project_dir)
            last_summary = log_result.get("summary") if log_result.get("ok") else None
            error_count = int(last_summary.get("error_count", 0)) if last_summary else 0
            completion_count = int(last_summary.get("completion_count", 0)) if last_summary else 0
            sample = {
                "timestamp": time.time(),
                "cpu_total": cpu_total,
                "processes": process_samples,
                "latest_log": log_result.get("latest_log"),
                "error_count": error_count,
                "completion_count": completion_count,
            }
            samples.append(sample)
            samples = samples[-20:]

            if completion_count > 0 and cpu_total <= idle_cpu_percent:
                return {
                    "ok": True,
                    "state": "completed_or_idle",
                    "message": "Completion text was found in logs and PIX4Dmatic CPU is idle.",
                    "samples": samples,
                    "log_summary": last_summary,
                }

            if cpu_total <= idle_cpu_percent:
                consecutive_idle += 1
            else:
                consecutive_idle = 0

            if consecutive_idle >= idle_checks:
                return {
                    "ok": True,
                    "state": "idle",
                    "message": "PIX4Dmatic CPU stayed below the idle threshold.",
                    "samples": samples,
                    "log_summary": last_summary,
                }

        raise Pix4DTimeoutError(f"PIX4Dmatic did not become idle within {timeout} seconds.")

    def run_job_object(self, job: dict[str, Any]) -> dict[str, Any]:
        project_path = job.get("project_path")
        project_dir = job.get("project_dir")
        expected_outputs = job.get("expected_outputs") or []
        timeout_sec = int(job.get("timeout_sec") or self.config.processing_timeout_sec)
        dry_run = bool(job.get("dry_run", False))
        use_current_session = bool(job.get("use_current_session", False))

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "job_id": job.get("job_id"),
                "would_open_project": project_path,
                "would_use_current_session": use_current_session and not project_path,
                "would_start_processing": True,
                "expected_outputs": expected_outputs,
            }

        if project_path:
            open_result = self.controller.open_project(project_path)
        elif use_current_session:
            open_result = {"ok": True, "message": "Using current PIX4Dmatic session."}
        else:
            raise Pix4DUserActionRequiredError(
                "Job must provide project_path or set use_current_session=true to process the current session."
            )

        start_result = self.start_processing(timeout_sec=job.get("ui_timeout_sec"))
        wait_result = self.wait_until_idle(timeout_sec=timeout_sec, project_dir=project_dir)
        output_result = None
        if project_dir and expected_outputs:
            output_result = self.check_outputs(project_dir, expected_outputs)

        ok = bool(wait_result.get("ok")) and (output_result is None or bool(output_result.get("ok")))
        return {
            "ok": ok,
            "job_id": job.get("job_id"),
            "open_project": open_result,
            "start_processing": start_result,
            "wait": wait_result,
            "outputs": output_result,
        }

    def check_outputs(self, project_dir: str, expected: list[str]) -> dict[str, Any]:
        root = Path(project_dir)
        if not root.exists():
            return {"ok": False, "code": "PROJECT_DIR_NOT_FOUND", "message": f"Project directory does not exist: {root}"}

        checks = []
        all_found = True
        for item in expected:
            patterns = OUTPUT_PATTERNS.get(item, [item])
            matches = []
            for pattern in patterns:
                matches.extend(str(path) for path in root.rglob(pattern) if path.is_file())
            checks.append({"name": item, "found": bool(matches), "matches": sorted(set(matches))[:50]})
            all_found = all_found and bool(matches)

        return {"ok": all_found, "project_dir": str(root), "checks": checks}

    def collect_diagnostics(self, output_dir: str, project_dir: str | None = None) -> dict[str, Any]:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        screenshot = capture_screen(destination, prefix="diagnostic")
        logs = find_log_files(self.config.log_search_dirs, Path(project_dir) if project_dir else None)
        copied_logs = []
        for log in logs[:5]:
            target = destination / log.path.name
            try:
                shutil.copy2(log.path, target)
                copied_logs.append(str(target))
            except OSError:
                continue
        return {"ok": True, "screenshot": str(screenshot), "logs": copied_logs, "status": self.controller.get_status()}
