from __future__ import annotations

import shutil
import time
import json
import re
from pathlib import Path
from typing import Any

from .config import Pix4DConfig, load_config
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
    "dense_point_cloud": ["*.las", "*.laz", "*.xyz", "*point*cloud*"],
    "mesh": ["*.obj", "*.ply", "*.fbx"],
    "contour_lines": ["*contour*.shp", "*contour*.dxf"],
}

IMAGE_PATH_PATTERN = re.compile(rb"[A-Za-z]:/[^\x00-\x1f\"<>|]+?\.(?:jpg|jpeg|tif|tiff|png)", re.IGNORECASE)


class Pix4DWorkflows:
    def __init__(self, config: Pix4DConfig | None = None) -> None:
        self.config = config or load_config()
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

        try:
            start_result = self.start_processing(timeout_sec=job.get("ui_timeout_sec"))
            wait_result = self.wait_until_idle(timeout_sec=timeout_sec, project_dir=project_dir)
            output_result = None
            if project_dir and expected_outputs:
                output_result = self.check_outputs(project_dir, expected_outputs)

            ok = bool(wait_result.get("ok")) and (output_result is None or bool(output_result.get("ok")))
            result = {
                "ok": ok,
                "job_id": job.get("job_id"),
                "open_project": open_result,
                "start_processing": start_result,
                "wait": wait_result,
                "outputs": output_result,
            }
            if not ok:
                result["diagnostics"] = self.collect_job_diagnostics(job)
            return result
        except Pix4DMaticError:
            raise
        except Exception as exc:
            diagnostics = self.collect_job_diagnostics(job)
            return {
                "ok": False,
                "job_id": job.get("job_id"),
                "code": "JOB_FAILED",
                "message": str(exc),
                "open_project": open_result,
                "diagnostics": diagnostics,
            }

    def run_batch_object(self, batch: dict[str, Any]) -> dict[str, Any]:
        jobs = batch.get("jobs") or []
        if not isinstance(jobs, list) or not jobs:
            raise Pix4DUserActionRequiredError("Batch must contain a non-empty jobs list.")

        continue_on_failure = bool(batch.get("continue_on_failure", False))
        results = []
        for index, job in enumerate(jobs):
            merged_job = {**batch.get("job_defaults", {}), **job}
            if "job_id" not in merged_job:
                merged_job["job_id"] = f"job_{index + 1}"
            result = self.run_job_object(merged_job)
            results.append(result)
            if not result.get("ok") and not continue_on_failure:
                break

        return {
            "ok": all(result.get("ok") for result in results) and len(results) == len(jobs),
            "batch_id": batch.get("batch_id"),
            "total_jobs": len(jobs),
            "completed_jobs": len(results),
            "continue_on_failure": continue_on_failure,
            "results": results,
        }

    def run_batch_file(self, batch_path: str) -> dict[str, Any]:
        path = Path(batch_path)
        with path.open("r", encoding="utf-8") as file:
            batch = json.load(file)
        return self.run_batch_object(batch)

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

    def analyze_project(self, project_dir: str, project_file: str | None = None) -> dict[str, Any]:
        root = Path(project_dir)
        if not root.exists():
            return {"ok": False, "code": "PROJECT_DIR_NOT_FOUND", "message": f"Project directory does not exist: {root}"}

        p4m = Path(project_file) if project_file else root / "root.p4m"
        image_refs = self._extract_image_references(p4m) if p4m.exists() else []
        existing_images = [path for path in image_refs if Path(path).exists()]

        file_counts = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower() or "<none>"
            file_counts[suffix] = file_counts.get(suffix, 0) + 1

        expected = ["quality_report", "orthomosaic", "dsm", "dtm", "dense_point_cloud", "mesh", "contour_lines"]
        outputs = self.check_outputs(str(root), expected)
        logs = self.read_latest_logs(lines=120, project_dir=str(root))
        return {
            "ok": True,
            "project_dir": str(root),
            "project_file": str(p4m) if p4m.exists() else None,
            "image_reference_count": len(image_refs),
            "existing_image_count": len(existing_images),
            "missing_image_count": len(image_refs) - len(existing_images),
            "image_references_sample": image_refs[:20],
            "file_counts": dict(sorted(file_counts.items())),
            "outputs": outputs,
            "latest_logs": logs,
        }

    def detect_blockers(self, project_dir: str | None = None) -> dict[str, Any]:
        tree = self.controller.get_ui_tree(depth=4)
        controls = tree.get("controls", [])
        visible_texts = [control.get("text") for control in controls if control.get("text")]
        process_menu = self.controller.list_menu_items("프로세스(P)", timeout_sec=5)
        process_items = [
            item for item in process_menu.get("items", [])
            if item.get("control_type") == "MenuItem" and item.get("automation_id")
        ]
        disabled_process_items = [item for item in process_items if not item.get("enabled")]
        latest_logs = self.read_latest_logs(lines=120, project_dir=project_dir)
        log_summary = latest_logs.get("summary", {})

        blockers = []
        if "평가판 시작" in visible_texts or "Start trial" in visible_texts:
            blockers.append(
                {
                    "code": "TRIAL_OR_LICENSE_PROMPT_VISIBLE",
                    "message": "The PIX4Dmatic toolbar exposes a trial/license action.",
                }
            )
        if process_items and len(disabled_process_items) == len(process_items):
            blockers.append(
                {
                    "code": "PROCESSING_MENU_DISABLED",
                    "message": "All processing menu items are disabled in the current UI state.",
                }
            )
        if log_summary.get("error_count"):
            license_errors = [
                line for line in log_summary.get("errors", [])
                if "license" in line.lower()
            ]
            if license_errors:
                blockers.append(
                    {
                        "code": "LICENSE_ERRORS_IN_LOG",
                        "message": "Recent logs contain license-related errors.",
                        "errors": license_errors[-10:],
                    }
                )

        return {
            "ok": not blockers,
            "blockers": blockers,
            "visible_texts": visible_texts,
            "process_menu": process_menu,
            "latest_logs": latest_logs,
        }

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

    def collect_job_diagnostics(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = str(job.get("job_id") or "job")
        project_dir = job.get("project_dir")
        output_dir = Path(job.get("diagnostics_dir") or self.config.diagnostics_dir / job_id)
        result = self.collect_diagnostics(str(output_dir), project_dir=project_dir)
        report_path = output_dir / "diagnostics.json"
        payload = {
            "job": job,
            "diagnostics": result,
            "logs": self.read_latest_logs(lines=200, project_dir=project_dir),
        }
        try:
            report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            result["report"] = str(report_path)
        except OSError as exc:
            result["report_error"] = str(exc)
        return result

    @staticmethod
    def _extract_image_references(project_file: Path) -> list[str]:
        try:
            data = project_file.read_bytes()
        except OSError:
            return []
        refs = []
        seen = set()
        for match in IMAGE_PATH_PATTERN.finditer(data):
            value = match.group(0).decode("utf-8", errors="ignore")
            if value not in seen:
                refs.append(value)
                seen.add(value)
        return refs
