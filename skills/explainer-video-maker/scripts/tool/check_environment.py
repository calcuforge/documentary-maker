#!/usr/bin/env python3
"""
Environment connectivity check for the ComfyUI + TTS backends.

Run right after project creation (Step 1) to confirm the runtime services the
pipeline depends on are actually reachable before investing in later steps. It
performs a lightweight TCP connect (no HTTP, no workflow run) to:

  - each registered ComfyUI node (from `comfyui-scheduler node list`); if no
    node is registered, the default http://127.0.0.1:8188 is probed. Used by
    AIGC and by the comfyui_indextts TTS backend.
  - the TTS endpoint:
      * tts.backend = comfyui_indextts → reuses the ComfyUI nodes (index_tts_2).
      * tts.backend = http_server      → probes tts.http.url (env-expanded).

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

DEFAULT_COMFYUI_URL = "http://127.0.0.1:8188"
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
    """TCP-probe the ComfyUI nodes. Returns a result dict."""
    nodes, list_error = list_comfyui_nodes()

    if list_error is not None or not nodes:
        candidates = [{"id": "default", "url": DEFAULT_COMFYUI_URL}]
        source = "default"
    else:
        candidates = [{"id": n.get("id", "node"), "url": n.get("url", "")} for n in nodes]
        source = "registered"

    node_results = []
    for cand in candidates:
        url = cand["url"]
        host, port = url_host_port(url)
        if not host:
            node_results.append({"id": cand["id"], "url": url, "reachable": False,
                                 "error": "invalid URL"})
            continue
        ok = tcp_reachable(host, port, timeout)
        node_results.append({"id": cand["id"], "url": url, "reachable": ok})

    reachable = any(r["reachable"] for r in node_results)

    guidance = []
    if list_error:
        guidance.append(list_error)
    if not reachable:
        if source == "registered":
            guidance.append(
                "ComfyUI node(s) unreachable. Start the ComfyUI server, or fix the "
                "registered address: comfyui-scheduler node add --id <id> --url http://<HOST>:8188"
            )
        else:
            guidance.append(
                "No reachable ComfyUI node (none registered; default "
                f"{DEFAULT_COMFYUI_URL} is down). Start ComfyUI and register a node: "
                "comfyui-scheduler node add --id node1 --url http://<HOST>:8188"
            )

    return {"reachable": reachable, "source": source, "nodes": node_results,
            "guidance": guidance}


def check_tts(project_config: dict, comfyui: dict, timeout: float) -> dict:
    """TCP-probe the TTS endpoint implied by tts.backend. Returns a result dict."""
    tts_config = project_config.get("tts", {})
    backend = tts_config.get("backend", "comfyui_indextts")

    if backend == "comfyui_indextts":
        reachable = comfyui["reachable"]
        result = {"backend": backend, "endpoint": "comfyui (index_tts_2 workflow)",
                  "reachable": reachable, "guidance": []}
        if not reachable:
            result["guidance"].append(
                "TTS backend comfyui_indextts runs on ComfyUI, so it is blocked by the "
                "ComfyUI failure above. Fix the ComfyUI node, or set tts.backend: http_server."
            )
        return result

    if backend == "http_server":
        raw_url = tts_config.get("http", {}).get("url", "")
        url = os.path.expandvars(raw_url)
        result = {"backend": backend, "endpoint": url, "reachable": False, "guidance": []}

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

    return {"backend": backend, "endpoint": "", "reachable": False, "guidance": [
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
