from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import ImageGrab


def capture_screen(output_dir: Path, prefix: str = "pix4dmatic") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{prefix}_{timestamp}.png"
    image = ImageGrab.grab()
    image.save(path)
    return path
