"""
Network utilities — locale-aware site selection, subprocess helpers.
"""

from __future__ import annotations

import functools
import locale
import os
import socket
import subprocess
import sys
from typing import Optional


def require_abs(*paths: str) -> None:
    """Validate that all given paths are absolute. Exits with error if not."""
    for p in paths:
        if p and not os.path.isabs(p):
            print(f"ERROR: Path must be absolute, got: {p}", file=sys.stderr)
            sys.exit(1)


def _tcp_reachable(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    """True if a TCP connection to host:port can be established."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@functools.lru_cache(maxsize=1)
def _probe_china_network() -> Optional[bool]:
    """Probe reachability: True = domestic China, False = international,
    None = inconclusive (e.g. no network). Baidu reachable while Google is
    blocked ⇒ behind the GFW — this holds even when the system locale is English.
    """
    china_ok = _tcp_reachable("www.baidu.com")
    intl_ok = _tcp_reachable("www.google.com")
    if china_ok and not intl_ok:
        return True
    if intl_ok:
        return False
    return None


def is_china_network() -> bool:
    """Detect a domestic China network.

    Order:
    1. REGION env override (authoritative when set).
    2. Network-reachability probe (Baidu reachable + Google blocked ⇒ China) —
       reliable even when the system locale / timezone say otherwise.
    3. Locale / timezone heuristics as a fallback when the probe is inconclusive
       (e.g. no network at all).
    """
    # Env override first (fast, authoritative)
    region = os.environ.get("REGION", "").upper()
    if region == "CN":
        return True
    if region in ("US", "UK", "JP", "KR", "EU"):
        return False

    # Network-reachability probe (cached) — the decisive check
    probed = _probe_china_network()
    if probed is not None:
        return probed

    # Locale fallback
    try:
        loc = locale.getdefaultlocale()[0] or ""
    except Exception:
        loc = ""
    if "zh" in loc.lower() or "cn" in loc.lower():
        return True

    # Timezone fallback
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
