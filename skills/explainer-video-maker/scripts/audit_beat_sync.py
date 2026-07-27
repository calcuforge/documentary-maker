#!/usr/bin/env python3
"""Audit beat-vs-narration alignment.

Flags sections whose `duration_frames` (from timing.json) drift >1.5s from
their narration char-weight estimate. Useful before rendering to catch
sections that will visibly desync.

Exit 0 = clean; 2 = warnings (publishable); 1 = errors.
"""
import argparse
import json
import os
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import estimate_timing  # noqa: E402

DRIFT_THRESHOLD_S = 1.5


def build_parser():
    parser = argparse.ArgumentParser(description="Audit section timing drift.")
    cli_envelope.add_format_arg(parser)
    parser.add_argument("--video-dir", required=True)
    parser.add_argument("--threshold", type=float, default=DRIFT_THRESHOLD_S,
                        help="Drift threshold in seconds (default 1.5).")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    timing_path = os.path.join(args.video_dir, "timing.json")
    script_path = os.path.join(args.video_dir, "narration_script.yaml")
    if not os.path.isfile(timing_path):
        cli_envelope.emit_usage_error(f"timing.json not found: {timing_path}",
                                      fmt=args.format)
    if not os.path.isfile(script_path):
        cli_envelope.emit_usage_error(f"narration_script.yaml not found: {script_path}",
                                      fmt=args.format)
    with open(timing_path, "r", encoding="utf-8") as f:
        timing = json.load(f)
    with open(script_path, "r", encoding="utf-8") as f:
        sections = yaml.safe_load(f) or []

    total = timing.get("total_duration", 0)
    weights = []
    for s in sections:
        text = (s.get("narration") or "").strip()
        weights.append(estimate_timing.text_weight(text) or 1.0)
    tw = sum(weights) or 1.0

    flagged = []
    for sec, w in zip(timing.get("sections", []), weights):
        expected = total * (w / tw)
        actual = sec.get("duration", 0)
        drift = abs(actual - expected)
        if drift > args.threshold:
            flagged.append({
                "section": sec.get("name"),
                "expected_s": round(expected, 2),
                "actual_s": round(actual, 2),
                "drift_s": round(drift, 2),
            })

    if flagged:
        cli_envelope.emit_warning(
            data={"flagged": flagged, "threshold_s": args.threshold},
            message=f"{len(flagged)} section(s) drift > {args.threshold}s.",
            fmt=args.format,
        )
    cli_envelope.emit_ok(
        data={"flagged": [], "threshold_s": args.threshold},
        message="No drift exceeded threshold.",
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
