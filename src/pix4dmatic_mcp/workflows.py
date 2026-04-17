from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import Pix4DConfig, default_config
from .controller import Pix4DMaticController
from .logs import find_log_files, read_tail, summarize_log_lines
from .screenshots import capture_screen


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
            "lines": tail,
            "summary": summarize_log_lines(tail),
        }

    def find_log_errors(self, lines: int = 1000, project_dir: str | None = None) -> dict[str, Any]:
        result = self.read_latest_logs(lines=lines, project_dir=project_dir)
        if not result.get("latest_log"):
            return result
        return {"ok": True, "latest_log": result["latest_log"], "summary": result["summary"]}

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
