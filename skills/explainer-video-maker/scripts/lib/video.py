"""Shared video file utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path


def make_faststart(path: str) -> bool:
    """Re-mux an mp4 with +faststart (moov atom at the front) via stream copy.

    Lossless and fast. Non-faststart mp4s keep the moov atom at EOF, which makes
    Remotion time out fetching frames through HTTP range requests. Returns False
    on failure, leaving the original file untouched.
    """
    src = Path(path)
    if not src.exists() or src.stat().st_size == 0:
        return False
    tmp = str(src) + ".faststart.tmp.mp4"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", tmp],
            capture_output=True, text=True, timeout=300, check=True,
        )
        Path(tmp).replace(src)
        return True
    except (subprocess.SubprocessError, OSError):
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass
        return False
