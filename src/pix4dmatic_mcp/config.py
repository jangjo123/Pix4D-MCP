from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class Pix4DConfig(BaseModel):
    pix4dmatic_exe: Path | None = None
    ui_language: str = "en"
    default_timeout_sec: int = 30
    processing_timeout_sec: int = 28800
    diagnostics_dir: Path = Field(default_factory=lambda: Path.cwd() / "diagnostics")
    log_search_dirs: list[Path] = Field(default_factory=list)
    allow_coordinate_click_fallback: bool = False

    @field_validator("pix4dmatic_exe", "diagnostics_dir", mode="before")
    @classmethod
    def _expand_optional_path(cls, value):
        if value is None or isinstance(value, Path):
            return value
        return Path(os.path.expandvars(os.path.expanduser(str(value))))

    @field_validator("log_search_dirs", mode="before")
    @classmethod
    def _expand_path_list(cls, value):
        if value is None:
            return []
        return [Path(os.path.expandvars(os.path.expanduser(str(item)))) for item in value]


def _default_log_dirs(user_profile: Path) -> list[Path]:
    return [
        user_profile / "AppData" / "Local" / "pix4d" / "PIX4Dmatic",
        user_profile / "AppData" / "Local" / "Pix4Dmatic",
        user_profile / "AppData" / "Roaming" / "pix4d",
    ]


def _candidate_executables() -> list[Path]:
    candidates = [
        os.environ.get("PIX4DMATIC_EXE"),
        r"C:\Program Files\PIX4Dmatic\PIX4Dmatic.exe",
        r"C:\Program Files\Pix4Dmatic\Pix4Dmatic.exe",
        r"C:\downloadx\PIX4Dmatic\PIX4Dmatic.exe",
    ]
    return [Path(os.path.expandvars(os.path.expanduser(path))) for path in candidates if path]


def default_config() -> Pix4DConfig:
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    exe = next((path for path in _candidate_executables() if path.exists()), None)
    return Pix4DConfig(
        pix4dmatic_exe=exe,
        diagnostics_dir=Path(os.environ.get("PIX4DMATIC_MCP_DIAGNOSTICS_DIR", Path.cwd() / "diagnostics")),
        log_search_dirs=_default_log_dirs(user_profile),
    )


def load_config(config_path: str | Path | None = None) -> Pix4DConfig:
    config = default_config()
    path_value = config_path or os.environ.get("PIX4DMATIC_MCP_CONFIG")
    candidate_paths = []
    if path_value:
        candidate_paths.append(Path(os.path.expandvars(os.path.expanduser(str(path_value)))))
    candidate_paths.extend([Path.cwd() / "pix4dmatic_mcp_config.json", Path.cwd() / "config" / "pix4dmatic_mcp_config.json"])

    data = {}
    for path in candidate_paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        break

    env_overrides = {
        "pix4dmatic_exe": os.environ.get("PIX4DMATIC_EXE"),
        "diagnostics_dir": os.environ.get("PIX4DMATIC_MCP_DIAGNOSTICS_DIR"),
    }
    data.update({key: value for key, value in env_overrides.items() if value})
    if not data:
        return config
    return config.model_copy(update=Pix4DConfig(**{**config.model_dump(), **data}).model_dump())
