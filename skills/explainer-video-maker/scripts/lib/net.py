"""
Network utilities — locale-aware site selection, subprocess helpers.
"""

from __future__ import annotations

import locale
import os
import subprocess
import sys
from typing import Optional


def is_china_network() -> bool:
    """Heuristic: detect if the local environment is likely in China.

    Checks:
    1. System locale contains 'zh' or 'CN'
    2. Environment variable REGION is set to CN
    3. Timezone hint (TZ contains Asia/Shanghai or Asia/Chongqing etc.)
    """
    # Check env override first
    region = os.environ.get("REGION", "").upper()
    if region == "CN":
        return True
    if region in ("US", "UK", "JP", "KR", "EU"):
        return False

    # Check locale
    try:
        loc = locale.getdefaultlocale()[0] or ""
    except Exception:
        loc = ""
    if "zh" in loc.lower() or "cn" in loc.lower():
        return True

    # Check timezone
    tz = os.environ.get("TZ", "")
    china_zones = ("Asia/Shanghai", "Asia/Chongqing", "Asia/Urumqi", "PRC")
    if tz in china_zones:
        return True

    return False


def get_search_engine() -> str:
    """Return the appropriate search engine URL based on network locale."""
    if is_china_network():
        return "https://www.bing.com"
    return "https://www.google.com"


def get_encyclopedia_url() -> str:
    """Return the appropriate encyclopedia base URL."""
    if is_china_network():
        return "https://baike.baidu.com"
    return "https://en.wikipedia.org"


def download_file(url: str, output_path: str, timeout: int = 120) -> str:
    """Download a file from a URL to output_path.

    Supports both http(s):// and file:// URLs.
    Returns the output path on success, raises RuntimeError on failure.
    """
    from pathlib import Path
    from urllib.parse import urlparse, unquote

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)

    if parsed.scheme == "file":
        # Local file — just copy
        src = unquote(parsed.path)
        # Handle Windows paths: file:///C:/... → C:/...
        if src.startswith("/") and len(src) > 2 and src[2] == ":":
            src = src[1:]
        if not os.path.exists(src):
            raise RuntimeError(f"Local file not found: {src}")
        import shutil
        shutil.copy2(src, output_path)
        return output_path

    elif parsed.scheme in ("http", "https"):
        import requests
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return output_path

    else:
        raise RuntimeError(f"Unsupported URL scheme '{parsed.scheme}': {url}")


def run_command(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Run a subprocess command, returning the CompletedProcess.

    Raises SystemExit on timeout or non-zero exit.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        print(f"ERROR: Command timed out after {timeout}s: {' '.join(cmd)}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERROR: Command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)


def run_command_checked(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
) -> str:
    """Run a command and return stdout. Exits on failure."""
    result = run_command(cmd, cwd=cwd, timeout=timeout)
    if result.returncode != 0:
        print(f"ERROR: Command failed (exit {result.returncode}): {' '.join(cmd)}", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout
