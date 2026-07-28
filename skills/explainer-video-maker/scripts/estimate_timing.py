#!/usr/bin/env python3
"""Build scene-level narration.srt and timing.json.

This is the **scene-level char-count estimator**. TTS is generated per scene,
so real audio length (ffprobe of the scene WAV) sets the scene's *total*
duration exactly. Within the scene:

    - shot durations are distributed across the scene's total by
      `duration_hint_seconds` (shots without a hint get the mean of the
      hinted shots; a scene with no hints at all splits evenly);
    - SRT cues are split from the scene narration at sentence-final
      punctuation and their durations allocated by char weight.

Inputs (per scene):
    narration_script.yaml      — chapters → scenes → shots.
    scenes/{scene}/narration.wav — real TTS audio for this scene.

Outputs (in the scene dir):
    scenes/{scene}/narration.srt   — cues timed relative to the scene (from 0).
    scenes/{scene}/timing.json     — schema:
        {
          "scene": "hero",
          "total_duration": 12.34,
          "fps": 30,
          "total_frames": 370,
          "shots": [
            { "name": "hero_01", "start_time": 0.0, "end_time": 6.1,
              "duration": 6.1, "start_frame": 0, "duration_frames": 183 }
          ]
        }

Audio-master clock rule (scene level):
    timing.total_duration equals ffprobe(narration.wav) within ±0.01s.
    Rounding remainders are absorbed into the last shot / last cue.

Video-level aggregation (root timing.json, merged SRT, merged WAV) is done
by `generate_tts.py merge`, not here.
"""
import argparse
import json
import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import cli_envelope  # noqa: E402
import script_schema  # noqa: E402

SENT_END = set("。.!?！？")
SOFT_END = set("，,;：:、 ")

CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]")
ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]")


def char_weight(ch):
    if ch.isspace():
        return 0.0
    if ch in SENT_END or ch in SOFT_END:
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


def _fmt_srt_time(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def distribute_shot_durations(shots, total_duration):
    """Allocate scene duration across shots.

    Weights: `duration_hint_seconds` when any shot has one (unhinted shots
    get the mean of the positive hints); otherwise equal weights.
    Returns a list of durations summing to total_duration (remainder
    absorbed into the last shot).
    """
    n = len(shots)
    if n == 0:
        return []
    hints = []
    for s in shots:
        h = s.get("duration_hint_seconds")
        try:
            h = float(h) if h is not None else 0.0
        except (TypeError, ValueError):
            h = 0.0
        hints.append(max(0.0, h))
    if any(h > 0 for h in hints):
        positive = [h for h in hints if h > 0]
        fallback = sum(positive) / len(positive)
        weights = [h if h > 0 else fallback for h in hints]
    else:
        weights = [1.0] * n
    tw = sum(weights) or 1.0
    durs = [total_duration * (w / tw) for w in weights]
    # Absorb rounding remainder into the last shot.
    drift = total_duration - sum(durs)
    durs[-1] = durs[-1] + drift
    return durs


def build_scene_timing(scene, total_duration, fps):
    """Build the shots block for a scene's timing.json."""
    shots = script_schema.effective_shots(scene)
    durs = distribute_shot_durations(shots, total_duration)
    blocks = []
    cumulative = 0.0
    for shot, dur in zip(shots, durs):
        start = round(cumulative, 3)
        end = round(cumulative + dur, 3)
        blocks.append({
            "name": shot["name"],
            "start_time": start,
            "end_time": end,
            "duration": round(dur, 3),
            "start_frame": round(start * fps),
            "duration_frames": max(1, round(dur * fps)),
        })
        cumulative += dur
    # Frames: recompute from rounded times; absorb frame rounding into last.
    total_frames = round(total_duration * fps)
    if blocks:
        frame_sum = sum(b["duration_frames"] for b in blocks)
        blocks[-1]["duration_frames"] += total_frames - frame_sum
        blocks[-1]["duration_frames"] = max(1, blocks[-1]["duration_frames"])
    return blocks, total_frames


def build_scene_srt(narration_text, total_duration):
    """Split scene narration into cues; allocate time by char weight.

    Returns (srt_string, cue_count). Times are relative to the scene start.
    """
    cues = split_into_cues((narration_text or "").strip())
    if not cues:
        return "", 0
    weights = [text_weight(c) or 1.0 for c in cues]
    tw = sum(weights)
    lines = []
    cstart = 0.0
    for i, (cue, w) in enumerate(zip(cues, weights)):
        cdur = total_duration * (w / tw)
        cend = total_duration if i == len(cues) - 1 else cstart + cdur
        lines.append(str(i + 1))
        lines.append(f"{_fmt_srt_time(cstart)} --> {_fmt_srt_time(cend)}")
        lines.append(cue)
        lines.append("")
        cstart = cend
    return "\n".join(lines), len(cues)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Build scene-level narration.srt + timing.json from "
                    "narration_script.yaml and the scene's TTS audio."
    )
    cli_envelope.add_format_arg(parser)
    parser.add_argument("--video-dir", required=True,
                        help="Path to the per-video directory.")
    parser.add_argument("--scene", required=True,
                        help="Scene name (subdirectory of scenes/).")
    parser.add_argument("--fps", type=int, default=None,
                        help="Override fps (default 30).")
    parser.add_argument("--narration-script", default=None,
                        help="Path to narration_script.yaml (default: video dir).")
    parser.add_argument("--audio", default=None,
                        help="Path to the scene WAV (default: scenes/{scene}/narration.wav).")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    vdir = args.video_dir
    scene_name = args.scene
    script_path = args.narration_script or os.path.join(vdir, "narration_script.yaml")
    audio_path = args.audio or os.path.join(vdir, "scenes", scene_name, "narration.wav")
    scene_dir = os.path.join(vdir, "scenes", scene_name)
    srt_path = os.path.join(scene_dir, "narration.srt")
    timing_path = os.path.join(scene_dir, "timing.json")

    try:
        script = script_schema.load_script(script_path)
    except script_schema.SchemaError as exc:
        cli_envelope.emit_usage_error(str(exc), fmt=args.format)
    scene = script_schema.find_scene(script, scene_name)
    if scene is None:
        cli_envelope.emit_usage_error(
            f"Scene '{scene_name}' not found in {script_path}. "
            f"Known scenes: {[s['name'] for s in script['scenes']]}",
            fmt=args.format)

    if not os.path.isfile(audio_path):
        cli_envelope.emit_usage_error(
            f"Scene audio not found: {audio_path}. Run `tts run --scene {scene_name}` first.",
            fmt=args.format)

    fps = args.fps or 30
    probed = ffprobe_duration(audio_path)
    total_duration = probed[0] if isinstance(probed, tuple) else probed
    if total_duration is None:
        cli_envelope.emit_error(
            "ffprobe_failed",
            f"Could not probe duration of {audio_path}: {probed[1] if isinstance(probed, tuple) else ''}",
            fmt=args.format, exit_code=1,
        )

    shots, total_frames = build_scene_timing(scene, total_duration, fps)
    srt_text, cue_count = build_scene_srt(scene.get("narration") or "", total_duration)

    os.makedirs(scene_dir, exist_ok=True)
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_text)
    timing = {
        "scene": scene_name,
        "total_duration": round(total_duration, 3),
        "fps": fps,
        "total_frames": total_frames,
        "shots": shots,
    }
    with open(timing_path, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)

    if not (scene.get("narration") or "").strip():
        cli_envelope.emit_warning(
            data=timing,
            message=f"Scene '{scene_name}' has no narration text; SRT is empty.",
            fmt=args.format,
        )
    cli_envelope.emit_ok(
        data=timing,
        message=(f"Scene '{scene_name}': SRT ({cue_count} cues) + timing.json "
                 f"({len(shots)} shots, {total_duration:.2f}s) written."),
        fmt=args.format,
    )


if __name__ == "__main__":
    main()
