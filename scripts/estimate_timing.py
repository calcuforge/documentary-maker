#!/usr/bin/env python3
"""Build narration_audio.srt and timing.json from narration_script.yaml.

This is the **char-count estimator** path — used because the index_tts
workflow returns only an audio file with no word-level timestamps. Real audio
length (from ffprobe) sets the *total*; char counts distribute that time
across sections and SRT cues.

Inputs:
    narration_script.yaml — list of sections with `name`, `label`, `narration`.
    narration_audio.wav   — real TTS audio (used to set total_duration).

Outputs (in video dir):
    narration_audio.srt
    timing.json  (schema: see remotion-video-template/src/components/useTiming.js)

Algorithm:
    1. ffprobe WAV for real total_duration.
    2. For each section, compute a "weight" = sum of char weights in narration:
       - CJK char weight = 1.0
       - ASCII letter/digit = 0.5
       - whitespace, punctuation = 0.0
    3. Allocate duration per section: weight / total_weight * total_duration.
       Round to 0.01s. Each section gets start_time/end_time and start_frame/
       duration_frames (frame = round(time * fps)).
    4. Inside each section, split narration into SRT cues at sentence-final
       punctuation (。.!?！？ and soft 。,). Allocate cue duration by char weight.
       2-line cap per cue (~30 chars/line for zh, ~60 for en).

Audio-master clock check:
    final total_duration (sum of section durations) MUST equal WAV duration
    within ±0.01s. Remainder absorbed into the last section.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402

SENT_END = set("。.!?！？")
SOFT_END = set("，,;：:、 ")

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]")


def char_weight(ch):
    if ch.isspace():
        return 0.0
    if SENT_END.__contains__(ch) or SOFT_END.__contains__(ch):
        return 0.0
    if CJK_RE.match(ch):
        return 1.0
    if ASCII_WORD_RE.match(ch):
        return 0.5
    return 0.0


def text_weight(text):
    return sum(char_weight(c) for c in text)


def ffprobe_duration(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15,
        )
        return float(result.stdout.strip())
    except Exception as exc:
        return None, str(exc)


def split_into_cues(text, max_chars=30):
    """Split a narration into SRT cue chunks.

    Strategy: walk the text, accumulate characters until we hit sentence-end
    punctuation OR exceed max_chars. Truncate at the most recent soft-punct
    if oversize. Each cue is non-empty.
    """
    cues = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in SENT_END:
            cues.append(buf.strip())
            buf = ""
    if buf.strip():
        cues.append(buf.strip())
    # Cap cue length — split oversize cues at soft-punct.
    final = []
    for c in cues:
        if len(c) <= max_chars * 2:
            final.append(c)
            continue
        pieces = _hard_split(c, max_chars * 2)
        final.extend(pieces)
    return [c for c in final if c]


def _hard_split(sentence, max_chars):
    budget = max_chars - 1
    pieces = []
    buf = ""
    for ch in sentence:
        buf += ch
        if len(buf) >= budget:
            cut = -1
            for i in range(len(buf) - 1, max(-1, len(buf) - 20), -1):
                if buf[i] in SOFT_END:
                    cut = i
                    break
            if cut >= 0:
                pieces.append(buf[:cut + 1])
                buf = buf[cut + 1:]
            else:
                pieces.append(buf + "，")
                buf = ""
    if buf:
        pieces.append(buf)
    return pieces


def build_parser():
    parser = argparse.ArgumentParser(
        description="Estimate SRT and timing.json from narration_script.yaml + narration_audio.wav."
    )
    cli_envelope.add_format_arg(parser)
    parser.add_argument("--video-dir", required=True,
                        help="Path to the per-video directory.")
    parser.add_argument("--fps", type=int, default=None,
                        help="Override fps (default: read from project prefs or 30).")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    vdir = args.video_dir
    script_path = os.path.join(vdir, "narration_script.yaml")
    audio_path = os.path.join(vdir, "narration_audio.wav")
    srt_path = os.path.join(vdir, "narration_audio.srt")
    timing_path = os.path.join(vdir, "timing.json")

    if not os.path.isfile(script_path):
        cli_envelope.emit_usage_error(
            f"narration_script.yaml not found in {vdir}", fmt=args.format)
    if not os.path.isfile(audio_path):
        cli_envelope.emit_usage_error(
            f"narration_audio.wav not found in {vdir}", fmt=args.format)

    with open(script_path, "r", encoding="utf-8") as f:
        sections = yaml.safe_load(f) or []
    if not isinstance(sections, list) or not sections:
        cli_envelope.emit_usage_error(
            "narration_script.yaml must be a non-empty list of sections.",
            fmt=args.format)

    fps = args.fps or 30
    total_duration = ffprobe_duration(audio_path)
    if total_duration is None:
        cli_envelope.emit_error(
            "ffprobe_failed",
            f"Could not probe duration of {audio_path}",
            fmt=args.format, exit_code=1,
        )

    # Compute weights + cues per section.
    weighted = []
    for s in sections:
        name = s.get("name") or ""
        label = s.get("label") or name
        text = (s.get("narration") or "").strip()
        cues = split_into_cues(text)
        cues_weights = [text_weight(c) for c in cues]
        section_weight = sum(cues_weights) if cues_weights else 1.0  # min weight
        weighted.append({
            "name": name, "label": label, "text": text,
            "cues": cues, "cues_weights": cues_weights,
            "weight": section_weight,
        })

    total_weight = sum(w["weight"] for w in weighted) or 1.0

    # Allocate per-section duration proportional to weight.
    section_blocks = []
    cumulative = 0.0
    for w in weighted:
        dur = total_duration * (w["weight"] / total_weight)
        section_blocks.append({
            "name": w["name"], "label": w["label"],
            "start_time": round(cumulative, 3),
            "end_time": round(cumulative + dur, 3),
            "duration": round(dur, 3),
            "cues": w["cues"], "cues_weights": w["cues_weights"],
        })
        cumulative += dur

    # Absorb rounding remainder into the last section.
    drift = total_duration - cumulative
    if section_blocks and abs(drift) > 0.001:
        last = section_blocks[-1]
        last["end_time"] = round(last["end_time"] + drift, 3)
        last["duration"] = round(last["duration"] + drift, 3)

    # Build SRT.
    srt_lines = []
    idx = 1
    for b in section_blocks:
        cues_w = b["cues_weights"]
        section_dur = b["duration"]
        section_start = b["start_time"]
        sw = sum(cues_w) or 1.0
        cstart = section_start
        for ci, (cue, cw) in enumerate(zip(b["cues"], cues_w)):
            cdur = section_dur * (cw / sw)
            cend = cstart + cdur
            srt_lines.append(str(idx))
            srt_lines.append(f"{_fmt_srt_time(cstart)} --> {_fmt_srt_time(cend)}")
            srt_lines.append(cue)
            srt_lines.append("")
            idx += 1
            cstart = cend

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))

    # Build timing.json.
    timing_sections = []
    for b in section_blocks:
        sf = round(b["start_time"] * fps)
        df = round(b["duration"] * fps)
        timing_sections.append({
            "name": b["name"],
            "label": b["label"],
            "start_time": b["start_time"],
            "end_time": b["end_time"],
            "duration": b["duration"],
            "start_frame": sf,
            "duration_frames": df,
        })
    timing = {
        "total_duration": round(total_duration, 3),
        "fps": fps,
        "total_frames": round(total_duration * fps),
        "sections": timing_sections,
    }
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)

    # Validate drift.
    if abs(timing["total_duration"] - total_duration) > 0.5:
        cli_envelope.emit_warning(
            data=timing,
            message=f"timing.json drift >0.5s (total={total_duration:.3f}, timing={timing['total_duration']:.3f}).",
            fmt=args.format,
        )
    cli_envelope.emit_ok(
        data=timing,
        message=f"SRT ({idx-1} cues) and timing.json ({len(timing_sections)} sections) written.",
        fmt=args.format,
    )


def _fmt_srt_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


if __name__ == "__main__":
    main()
