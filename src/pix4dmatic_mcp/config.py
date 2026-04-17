from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class Pix4DConfig(BaseModel):
    pix4dmatic_exe: Path | None = None
    ui_language: str = "en"
    default_timeout_sec: int = 30
    processing_timeout_sec: int = 28800
    diagnostics_dir: Path = Field(default_factory=lambda: Path.cwd() / "diagnostics")
    log_search_dirs: list[Path] = Field(default_factory=list)
    allow_coordinate_click_fallback: bool = False


def default_config() -> Pix4DConfig:
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    candidates = [
        Path(r"C:\Program Files\PIX4Dmatic\PIX4Dmatic.exe"),
        Path(r"C:\Program Files\Pix4Dmatic\Pix4Dmatic.exe"),
        Path(r"C:\downloadx\PIX4Dmatic\PIX4Dmatic.exe"),
    ]
    exe = next((path for path in candidates if path.exists()), None)
    return Pix4DConfig(
        pix4dmatic_exe=exe,
        diagnostics_dir=Path.cwd() / "diagnostics",
        log_search_dirs=[
            user_profile / "AppData" / "Local" / "pix4d" / "PIX4Dmatic",
            user_profile / "AppData" / "Local" / "Pix4Dmatic",
            user_profile / "AppData" / "Roaming" / "pix4d",
        ],
    )
