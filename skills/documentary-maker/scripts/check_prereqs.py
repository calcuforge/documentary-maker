#!/usr/bin/env python3
"""Verify all documentary-maker prerequisites are present.

Checks:
    - python3 (implicit — we're running)
    - ffmpeg, ffprobe on PATH
    - node, npx on PATH
    - comfyui-scheduler command available
    - remotion-video-template exists at the configured path
    - at least one ComfyUI node registered (warns if none — TTS/AIGC will fail)

Exit codes:
    0 — all hard prerequisites satisfied
    1 — missing one or more hard prerequisites
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402


def _which(cmd):
    return shutil.which(cmd) is not None


def _check_cmd(cmd, label, required=True):
    if _which(cmd):
        return ("ok", f"{label}: found")
    return ("fail" if required else "warn", f"{label}: NOT FOUND on PATH")


def _check_template(template_rel):
    template_path = os.path.normpath(os.path.join(SKILL_DIR, template_rel))
    if os.path.isdir(template_path) and os.path.isfile(
        os.path.join(template_path, "package.json")
    ):
        node_modules = os.path.join(template_path, "node_modules")
        nm_status = "with node_modules" if os.path.isdir(node_modules) else "WITHOUT node_modules (run npm install)"
        return ("ok", f"remotion-video-template: {template_path} ({nm_status})")
    return ("fail", f"remotion-video-template: NOT FOUND at {template_path}")


def _check_comfyui_scheduler():
    if not _which("comfyui-scheduler"):
        return ("fail", "comfyui-scheduler: NOT on PATH (pip install -e ../comfyui-scheduler)")
    try:
        result = subprocess.run(
            ["comfyui-scheduler", "status"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ("warn", f"comfyui-scheduler: installed but `status` failed: {result.stderr.strip()}")
        return ("ok", "comfyui-scheduler: installed and reachable")
    except Exception as exc:
        return ("warn", f"comfyui-scheduler: installed but `status` raised: {exc}")


def _check_comfyui_nodes():
    if not _which("comfyui-scheduler"):
        return ("warn", "comfyui-scheduler: skipped (not installed)")
    try:
        result = subprocess.run(
            ["comfyui-scheduler", "node", "list", "--format", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return ("warn", "comfyui node list: failed")
        out = json.loads(result.stdout or "{}")
        nodes = out.get("data", {}).get("nodes", []) if isinstance(out, dict) else []
        if not nodes:
            return ("warn", "comfyui: NO nodes registered (run `comfyui-scheduler node add ...`)")
        return ("ok", f"comfyui: {len(nodes)} node(s) registered")
    except Exception as exc:
        return ("warn", f"comfyui node list: {exc}")


def build_parser():
    parser = argparse.ArgumentParser(description="Check documentary-maker prerequisites.")
    cli_envelope.add_format_arg(parser)
    parser.add_argument(
        "--template-path", default=None,
        help="Override the remotion-video-template path (relative to SKILL_DIR).",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    template_rel = args.template_path or "../../remotion-video-template"
    checks = [
        _check_cmd("ffmpeg", "ffmpeg"),
        _check_cmd("ffprobe", "ffprobe"),
        _check_cmd("node", "node"),
        _check_cmd("npx", "npx"),
        _check_template(template_rel),
        _check_comfyui_scheduler(),
        _check_comfyui_nodes(),
    ]
    failures = [c for s, c in checks if s == "fail"]
    warnings = [c for s, c in checks if s == "warn"]
    oks = [c for s, c in checks if s == "ok"]

    if failures:
        cli_envelope.emit_error(
            "prereqs_failed",
            "Missing one or more hard prerequisites.",
            details={"failures": failures, "warnings": warnings, "ok": oks},
            fmt=args.format, exit_code=1,
        )
    if warnings:
        cli_envelope.emit_warning(
            data={"failures": failures, "warnings": warnings, "ok": oks},
            message="All hard prerequisites OK; warnings present (TTS/AIGC may be limited).",
            fmt=args.format,
        )
    cli_envelope.emit_ok(
        data={"ok": oks, "warnings": warnings},
        message="All prerequisites satisfied.",
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
