#!/usr/bin/env python3
"""
Re-mux mp4 files with +faststart (moov atom moved to the front) via stream copy.

Non-faststart mp4s (moov atom at EOF) cause Remotion to time out fetching frames
over HTTP range requests. Run this on AIGC video assets (origin_*.mp4 / scene*.mp4)
to make them faststart. Lossless — only re-muxes, never re-encodes.

Usage:
    python fix_faststart.py <file1.mp4> [file2.mp4 ...]

Exit codes: 0 = all OK, 1 = one or more files failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.video import make_faststart


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if args else 1)

    failed = []
    for p in args:
        if not p.lower().endswith(".mp4"):
            print(f"SKIP {p} (not an mp4)", file=sys.stderr)
            continue
        if make_faststart(p):
            print(f"OK   {p}")
        else:
            failed.append(p)
            print(f"FAIL {p}", file=sys.stderr)

    if failed:
        print(f"{len(failed)} file(s) failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)
    print("All files are now faststart.")


if __name__ == "__main__":
    main()
