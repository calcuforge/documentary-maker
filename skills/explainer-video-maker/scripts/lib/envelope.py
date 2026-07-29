"""
Unified JSON envelope for script output.

All scripts emit JSON to stdout with a unified structure:
    {"status": "ok"|"error", "msg": "<human-readable>", "data": {...}}

Exit codes: 0 = success, 1 = error, 2 = validation warnings.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def ok(msg: str, data: dict[str, Any] | None = None) -> None:
    """Print success envelope and exit 0."""
    print(json.dumps({"status": "ok", "msg": msg, "data": data or {}}, ensure_ascii=False, indent=2))
    sys.exit(0)


def error(msg: str, data: dict[str, Any] | None = None) -> None:
    """Print error envelope and exit 1."""
    print(json.dumps({"status": "error", "msg": msg, "data": data or {}}, ensure_ascii=False, indent=2))
    sys.exit(1)


def warn(msg: str, data: dict[str, Any] | None = None) -> None:
    """Print warning envelope and exit 2."""
    print(json.dumps({"status": "warning", "msg": msg, "data": data or {}}, ensure_ascii=False, indent=2))
    sys.exit(2)


def emit(status: str, msg: str, data: dict[str, Any] | None = None, code: int = 0) -> None:
    """Print envelope with explicit exit code."""
    print(json.dumps({"status": status, "msg": msg, "data": data or {}}, ensure_ascii=False, indent=2))
    sys.exit(code)
