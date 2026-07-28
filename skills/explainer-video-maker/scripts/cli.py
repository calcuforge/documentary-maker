#!/usr/bin/env python3
"""Top-level dispatcher for explainer-video-maker.

Forwards to individual scripts via subprocess so each script's argparse
stays self-contained. Mirrors the video-podcast-maker `cli.py` pattern.

Resources / actions:
    project   create | list | show | set | video
    assets    init | add | list | update | validate
    tts       run | merge
    comfyui   run | status
    themes    list | show | resolve
    research  plan
    compose
    merge      (concatenate rendered scenes into output.mp4)
    audit      beats
    verify
    prereqs
    schema     [<method>]

Usage:
    python3 scripts/cli.py --help
    python3 scripts/cli.py <resource> --help
    python3 scripts/cli.py <resource> <action> [args...]
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402

# method -> (script filename, description)
METHODS = {
    "project.create":   ("project.py",      "Create a new project."),
    "project.list":     ("project.py",      "List all projects."),
    "project.show":     ("project.py",      "Show project prefs."),
    "project.set":      ("project.py",      "Set a project preference."),
    "project.video":    ("project.py",      "Create a per-video scaffold."),

    "assets.init":      ("assets.py",       "Initialize an empty manifest."),
    "assets.add":       ("assets.py",       "Register an asset."),
    "assets.list":      ("assets.py",       "List manifest entries."),
    "assets.update":    ("assets.py",       "Update an asset entry."),
    "assets.validate":  ("assets.py",       "Validate manifest integrity."),

    "tts.run":          ("generate_tts.py", "Synthesize per-scene TTS + SRT + timing."),
    "tts.merge":        ("generate_tts.py", "Merge scene audio/SRT/timing into video-level artifacts."),

    "comfyui.run":      ("comfyui.py",      "Run a ComfyUI workflow by id."),
    "comfyui.status":   ("comfyui.py",      "Show comfyui-scheduler node status."),

    "themes.list":      ("themes.py",       "List available themes."),
    "themes.show":      ("themes.py",       "Show one theme preset."),
    "themes.resolve":   ("themes.py",       "Deep-merge theme onto project prefs."),

    "research.plan":    ("research.py",     "Generate a research plan from provider config."),

    "compose":          ("compose_video.py", "Generate per-scene Remotion composition files."),
    "merge":            ("merge_video.py",  "Concatenate rendered scenes into output.mp4."),
    "audit.beats":      ("audit_beat_sync.py", "Audit scene timing drift."),
    "verify":           ("verify_output.py", "End-of-pipeline acceptance gate."),
    "prereqs":          ("check_prereqs.py", "Check prerequisites."),
}

# method -> (subcommand_name, expected_script_positional_or_subparser)
# Each script's main() builds its own argparse. We forward by stripping the
# leading "<resource>" argv word and passing "<action> <rest>".

# Map of "resource" -> script and the action aliases it understands.
RESOURCE_TO_SCRIPT = {
    "project": "project.py",
    "assets": "assets.py",
    "tts": "generate_tts.py",
    "comfyui": "comfyui.py",
    "themes": "themes.py",
    "research": "research.py",
    "compose": "compose_video.py",
    "merge": "merge_video.py",
    "audit": "audit_beat_sync.py",  # action: beats
    "verify": "verify_output.py",
    "prereqs": "check_prereqs.py",
}

# Some scripts use a subparser (action is the first positional arg), others
# (compose, merge, verify, prereqs) take their args directly with no subcommand.
SCRIPTS_WITHOUT_SUBCOMMAND = {"compose_video.py", "merge_video.py",
                              "verify_output.py", "check_prereqs.py"}


def build_parser():
    parser = argparse.ArgumentParser(
        description="explainer-video-maker CLI dispatcher.",
        epilog="Run `cli.py <resource> --help` for per-resource details. "
               "Or `cli.py schema` to list all known methods.",
    )
    parser.add_argument("resource", nargs="?",
                        help="One of: " + ", ".join(sorted(RESOURCE_TO_SCRIPT)))
    parser.add_argument("rest", nargs=argparse.REMAINDER,
                        help="Args forwarded to the underlying script.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Schema shortcut.
    if argv and argv[0] == "schema":
        if len(argv) > 1:
            key = argv[1]
            if key not in METHODS:
                cli_envelope.emit_usage_error(f"Unknown method: {key}", fmt="text")
            spec = {"method": key, "script": METHODS[key][0], "description": METHODS[key][1]}
            print(json.dumps(spec, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps({"methods": {k: {"script": v[0], "description": v[1]}
                                       for k, v in METHODS.items()}},
                          ensure_ascii=False, indent=2))
        return 0

    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.resource:
        parser.print_help()
        return 0

    resource = args.resource
    if resource not in RESOURCE_TO_SCRIPT:
        cli_envelope.emit_usage_error(
            f"Unknown resource: {resource}. Available: {sorted(RESOURCE_TO_SCRIPT)}",
            fmt=args.format,
        )

    script_name = RESOURCE_TO_SCRIPT[resource]
    script_path = os.path.join(SCRIPT_DIR, script_name)

    # Build the forwarded argv. Strip the resource word, keep the rest.
    forwarded = list(args.rest)
    # argparse REMAINDER leaves leading "--" in some shells; strip it.
    while forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    # Pass --format through to the inner script so JSON envelopes work
    # uniformly. Normalize its position: pull it out wherever it appears and
    # re-insert it BEFORE any subcommand, because subparser-based scripts
    # (tts/project/assets/...) define --format on the parent parser and would
    # reject `run ... --format json` after the subcommand word.
    fmt_args = []
    rest_args = []
    forwarded_iter = iter(forwarded)
    for tok in forwarded_iter:
        if tok == "--format":
            fmt_args = ["--format", next(forwarded_iter, "text")]
        elif tok.startswith("--format="):
            fmt_args = ["--format", tok.split("=", 1)[1]]
        else:
            rest_args.append(tok)
    if args.format == "json" and not fmt_args:
        fmt_args = ["--format", "json"]
    forwarded = fmt_args + rest_args

    cmd = [sys.executable, script_path] + forwarded
    try:
        result = subprocess.run(cmd, encoding="utf-8", timeout=1800)
        return result.returncode
    except FileNotFoundError:
        cli_envelope.emit_error(
            "prereqs_failed",
            f"Python could not run {script_path}",
            fmt=args.format, exit_code=1,
        )
    except subprocess.TimeoutExpired:
        cli_envelope.emit_error(
            "timeout",
            f"Command timed out after 30min: {' '.join(cmd)}",
            fmt=args.format, exit_code=1,
        )


if __name__ == "__main__":
    sys.exit(main())
