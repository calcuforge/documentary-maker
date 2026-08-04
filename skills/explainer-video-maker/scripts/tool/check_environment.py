#!/usr/bin/env python3
"""
Environment connectivity check for the ComfyUI + TTS backends.

Run right after project creation (Step 1) to confirm the runtime services the
pipeline depends on are actually reachable before investing in later steps. It
performs a lightweight TCP connect (no HTTP, no workflow run) to:

  - each registered ComfyUI node (from `comfyui-scheduler node list`). If the
    scheduler cannot list nodes, or NO node is registered, the check fails
    immediately (no default-URL fallback). Node URLs are env-expanded
    (${VAR}/$VAR/%VAR%) before probing; a leftover unexpanded variable is an
    error. Used by AIGC and by the comfyui_indextts TTS backend.
  - the TTS endpoint — only when `tts.backend = http_server`:
      * http_server → probes the configured tts.http.url (env-expanded).
      * comfyui_indextts → no separate check; index_tts_2 runs on the ComfyUI
        node covered above.

If something is unreachable, the JSON `data.guidance` lists concrete fixes
(register/start a ComfyUI node, or switch/configure the TTS backend).

Usage:
    python check_environment.py --project-config /abs/path/project_config.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from lib.yamlutil import load_yaml

# Matches a leftover, unexpanded env reference such as ${VAR}, $VAR or %VAR%.
UNRESOLVED_VAR_RE = re.compile(r"\$\{?\w|\%\w+\%")


def tcp_reachable(host: str, port: int, timeout: float) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def url_host_port(url: str) -> tuple[str | None, int | None]:
    """Extract (host, port) from a URL. Defaults port by scheme (http=80/https=443)."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return None, None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port


def list_comfyui_nodes() -> tuple[list[dict] | None, str | None]:
    """Query `comfyui-scheduler node list`. Returns (nodes, error)."""
    try:
        result = subprocess.run(
            ["comfyui-scheduler", "node", "list"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return None, ("comfyui-scheduler not found on PATH. "
                      "Install: pip install -e dep/comfyui-scheduler")
    except subprocess.TimeoutExpired:
        return None, "comfyui-scheduler node list timed out"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return None, f"comfyui-scheduler node list failed: {detail[:300]}"

    try:
        out = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, f"invalid JSON from comfyui-scheduler node list: {result.stdout[:200]}"

    return out.get("data", {}).get("nodes", []), None


def check_comfyui(timeout: float) -> dict:
    """TCP-probe the registered ComfyUI nodes. Returns a result dict.

    Node URLs are env-expanded (${VAR}/$VAR/%VAR%) before probing. When the
    scheduler cannot list nodes, or NO node is registered, the check fails
    immediately — no default-URL fallback.
    """
    nodes, list_error = list_comfyui_nodes()

    if list_error is not None:
        return {"reachable": False, "source": "none", "nodes": [],
                "guidance": [list_error]}
    if not nodes:
        return {"reachable": False, "source": "none", "nodes": [],
                "guidance": [
                    "No ComfyUI node is registered (comfyui-scheduler node list is empty). "
                    "Register one first: comfyui-scheduler node add --id node1 "
                    "--url http://<HOST>:8188, then re-run this check."
                ]}

    node_results = []
    for node in nodes:
        node_id = node.get("id", "node")
        raw_url = node.get("url", "")
        url = os.path.expandvars(raw_url)
        entry = {"id": node_id, "url": url}

        if not raw_url:
            entry["reachable"] = False
            entry["error"] = "empty URL"
        elif UNRESOLVED_VAR_RE.search(url):
            entry["reachable"] = False
            entry["error"] = ("unexpanded environment variable in URL — export it "
                              "(e.g. set the env var), or update the node URL")
        else:
            host, port = url_host_port(url)
            if not host:
                entry["reachable"] = False
                entry["error"] = "invalid URL"
            else:
                entry["reachable"] = tcp_reachable(host, port, timeout)
        node_results.append(entry)

    reachable = any(r.get("reachable") for r in node_results)

    guidance = []
    if not reachable:
        guidance.append(
            "ComfyUI node(s) unreachable. Start the ComfyUI server, or fix the "
            "registered address: comfyui-scheduler node add --id <id> --url http://<HOST>:8188"
        )

    return {"reachable": reachable, "source": "registered", "nodes": node_results,
            "guidance": guidance}


def check_tts(project_config: dict, comfyui: dict, timeout: float) -> dict:
    """TCP-probe the TTS endpoint implied by tts.backend. Returns a result dict.

    The index/TTS endpoint is checked ONLY for the http_server backend (its
    configured server URL). The comfyui_indextts backend has no separate
    check — index_tts_2 runs on the ComfyUI node covered by check_comfyui.
    """
    tts_config = project_config.get("tts", {})
    backend = tts_config.get("backend", "comfyui_indextts")

    if backend == "comfyui_indextts":
        result = {"backend": backend, "checked": False,
                  "endpoint": "comfyui (index_tts_2 workflow)",
                  "reachable": comfyui["reachable"], "guidance": []}
        if not comfyui["reachable"]:
            result["guidance"].append(
                "TTS backend comfyui_indextts runs on ComfyUI, so it is blocked by the "
                "ComfyUI failure above. Fix the ComfyUI node, or set tts.backend: http_server."
            )
        return result

    if backend == "http_server":
        raw_url = tts_config.get("http", {}).get("url", "")
        url = os.path.expandvars(raw_url)
        result = {"backend": backend, "checked": True, "endpoint": url,
                  "reachable": False, "guidance": []}

        if not raw_url:
            result["guidance"].append(
                "tts.backend is http_server but tts.http.url is empty. Set the URL, or "
                "switch tts.backend to comfyui_indextts."
            )
            return result

        if UNRESOLVED_VAR_RE.search(url):
            result["guidance"].append(
                f"tts.http.url '{url}' still contains an unexpanded environment variable. "
                "Export it (e.g. BACKEND_PROXY_ENDPOINT) before running TTS, or switch "
                "tts.backend to comfyui_indextts."
            )
            return result

        host, port = url_host_port(url)
        if not host:
            result["guidance"].append(
                f"Cannot parse a host from tts.http.url '{url}'. Fix the URL, or switch "
                "tts.backend to comfyui_indextts."
            )
            return result

        result["reachable"] = tcp_reachable(host, port, timeout)
        if not result["reachable"]:
            result["guidance"].append(
                f"TTS HTTP server unreachable at {url}. Start the server (and set any "
                "required env vars), or switch tts.backend to comfyui_indextts."
            )
        return result

    return {"backend": backend, "checked": True, "endpoint": "", "reachable": False,
            "guidance": [
                f"Unknown tts.backend '{backend}'. Set tts.backend to comfyui_indextts or http_server "
                "in project_config.yaml."
            ]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Check ComfyUI + TTS environment reachability")
    parser.add_argument("--project-config", required=True, help="Path to project_config.yaml (absolute)")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="Per-endpoint TCP connect timeout in seconds (default 5)")
    args = parser.parse_args()

    from lib.net import require_abs
    require_abs(args.project_config)

    project_config = load_yaml(args.project_config)

    comfyui = check_comfyui(args.timeout)
    tts = check_tts(project_config, comfyui, args.timeout)

    guidance = comfyui["guidance"] + tts["guidance"]
    ok = comfyui["reachable"] and tts["reachable"]

    data = {"comfyui": comfyui, "tts": tts, "guidance": guidance}

    if ok:
        print(json.dumps({
            "status": "ok",
            "msg": f"Environment ready: ComfyUI reachable ({comfyui['source']}), "
                   f"TTS backend '{tts['backend']}' reachable.",
            "data": data,
        }, ensure_ascii=False, indent=2))
        sys.exit(0)
    else:
        print(json.dumps({
            "status": "error",
            "msg": f"Environment not ready: ComfyUI reachable={comfyui['reachable']}, "
                   f"TTS reachable={tts['reachable']}. See data.guidance.",
            "data": data,
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
