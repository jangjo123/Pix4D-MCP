from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


LOG_SUFFIXES = {".log", ".txt"}
ERROR_KEYWORDS = [
    "[Error]",
    "error",
    "failed",
    "crash",
    "not enough memory",
    "not enough disk",
    "license",
    "missing image",
]
WARNING_KEYWORDS = ["[Warning]", "warning"]
COMPLETION_KEYWORDS = ["completed", "finished", "done", "successfully"]
PROCESSING_KEYWORDS = ["processing", "running", "started"]


@dataclass(frozen=True)
class LogFile:
    path: Path
    modified_ts: float


def find_log_files(search_dirs: list[Path], project_dir: Path | None = None) -> list[LogFile]:
    roots = list(search_dirs)
    if project_dir:
        roots.extend([project_dir / "log", project_dir / "logs", project_dir / "report", project_dir / "reports"])

    found: list[LogFile] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in LOG_SUFFIXES:
                try:
                    found.append(LogFile(path=path, modified_ts=path.stat().st_mtime))
                except OSError:
                    continue
    return sorted(found, key=lambda item: item.modified_ts, reverse=True)


def read_tail(path: Path, lines: int = 200) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-lines:]


def summarize_log_lines(lines: list[str]) -> dict:
    errors = [line for line in lines if any(keyword.lower() in line.lower() for keyword in ERROR_KEYWORDS)]
    warnings = [line for line in lines if any(keyword.lower() in line.lower() for keyword in WARNING_KEYWORDS)]
    completions = [line for line in lines if any(keyword in line.lower() for keyword in COMPLETION_KEYWORDS)]
    processing = [line for line in lines if any(keyword in line.lower() for keyword in PROCESSING_KEYWORDS)]
    return {
        "error_count": len(errors),
        "warning_count": len(warnings),
        "completion_count": len(completions),
        "processing_count": len(processing),
        "errors": errors[-50:],
        "warnings": warnings[-50:],
        "completions": completions[-20:],
        "processing": processing[-20:],
    }
