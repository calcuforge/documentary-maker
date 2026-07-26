#!/usr/bin/env python3
"""Thin wrapper around `comfyui-scheduler run`.

Shells out to the CLI, parses the JSON envelope, and downloads output files
into the per-video `assets/` directory. Returns a list of local file paths.

Commands:
    run --workflow-id <id> --inputs '<json>' --dest-dir <dir>
        [--output-node TITLE] [--node NODE]
    status
"""
import argparse
import json
import os
import subprocess
import sys
from urllib.parse import urlparse, urlsplit, urlunsplit

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402


def _run_subprocess(argv, fmt, timeout=None):
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        cli_envelope.emit_error(
            "timeout", f"Command timed out: {' '.join(argv)}", fmt=fmt,
        )
    return result


def _download_file(url, dest_dir, kind="image"):
    os.makedirs(dest_dir, exist_ok=True)
    try:
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
    except Exception as exc:
        return None, str(exc)
    # Derive filename from URL; if missing, synthesize.
    parsed = urlsplit(url)
    filename = os.path.basename(parsed.path) or f"output_{kind}.bin"
    # Strip any query-induced suffix; keep only the basename.
    filename = filename.split("?")[0]
    dest = os.path.join(dest_dir, filename)
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return dest, None


def run_workflow(workflow_id, inputs, dest_dir, output_node=None, node=None, fmt="text"):
    if not shutil_which("comfyui-scheduler"):
        cli_envelope.emit_error(
            "prereqs_failed",
            "comfyui-scheduler is not on PATH. pip install -e ../comfyui-scheduler",
            fmt=fmt, exit_code=1,
        )
    argv = [
        "comfyui-scheduler", "run",
        "-w", workflow_id,
        "-i", json.dumps(inputs) if isinstance(inputs, dict) else inputs,
    ]
    if output_node:
        argv += ["--output-node", output_node]
    if node:
        argv += ["-n", node]
    result = _run_subprocess(argv, fmt)
    if result.returncode != 0:
        cli_envelope.emit_error(
            "workflow_failed",
            f"comfyui-scheduler exited {result.returncode}: {result.stderr.strip()}",
            details={"stdout": result.stdout, "stderr": result.stderr},
            fmt=fmt, exit_code=1,
        )
    try:
        envelope = json.loads(result.stdout)
    except Exception:
        cli_envelope.emit_error(
            "workflow_failed",
            f"Could not parse comfyui-scheduler JSON: {result.stdout!r}",
            fmt=fmt, exit_code=1,
        )
    data = envelope.get("data", {}) if isinstance(envelope, dict) else {}
    files = data.get("files", [])
    local_files = []
    download_errors = []
    for f in files:
        url = f.get("url")
        kind = f.get("kind", "image")
        if not url:
            continue
        local, err = _download_file(url, dest_dir, kind=kind)
        if err:
            download_errors.append({"url": url, "error": err})
        else:
            local_files.append({
                "kind": kind, "url": url, "filename": f.get("filename"),
                "local_path": local,
            })
    cli_envelope.emit_ok(
        data={
            "workflow_id": workflow_id,
            "task_id": data.get("task_id"),
            "prompt_id": data.get("prompt_id"),
            "output_type": data.get("output_type"),
            "files": local_files,
            "download_errors": download_errors,
        },
        message=f"Workflow {workflow_id} completed; {len(local_files)} file(s) downloaded.",
        fmt=fmt,
    )


def shutil_which(cmd):
    import shutil
    return shutil.which(cmd)


def build_parser():
    parser = argparse.ArgumentParser(description="ComfyUI workflow runner.")
    cli_envelope.add_format_arg(parser)
    sub = parser.add_subparsers(dest="action", required=True)

    p_run = sub.add_parser("run", help="Run a workflow by id and download outputs.")
    p_run.add_argument("--workflow-id", "-w", required=True)
    p_run.add_argument("--inputs", "-i", required=True,
                       help="JSON object of input values, or @file.json to read from a file.")
    p_run.add_argument("--dest-dir", required=True,
                       help="Directory to download output files into.")
    p_run.add_argument("--output-node", default=None)
    p_run.add_argument("--node", "-n", default=None)

    sub.add_parser("status", help="Show comfyui-scheduler node status.")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.action == "status":
        result = _run_subprocess(["comfyui-scheduler", "status"], args.format)
        sys.stdout.write(result.stdout)
        sys.exit(result.returncode)
    elif args.action == "run":
        inputs = args.inputs
        if inputs.startswith("@"):
            with open(inputs[1:], "r", encoding="utf-8") as f:
                inputs = f.read()
        try:
            inputs_obj = json.loads(inputs)
        except Exception:
            cli_envelope.emit_usage_error(
                f"Could not parse --inputs as JSON: {inputs!r}",
                fmt=args.format,
            )
        run_workflow(args.workflow_id, inputs_obj, args.dest_dir,
                     output_node=args.output_node, node=args.node, fmt=args.format)


if __name__ == "__main__":
    main()
