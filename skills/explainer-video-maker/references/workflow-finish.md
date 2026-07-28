# Workflow — Finish Phase (Step 11)

> **Load when:** entering Step 11, or when the user asks about verification or final metadata.

## Step 11: Verify + Save Metadata

### 11a. Verify gate (mandatory)

```bash
python3 "$SKILL_DIR/scripts/cli.py" verify --project $P --video $V
```

Checks (see `scripts/verify_output.py`):

- Every scene in `narration_script.yaml` has `scenes/{s}/scene.mp4` rendered.
- Per-scene `scenes/{s}/timing.json` matches `scenes/{s}/narration.wav` within ±0.5s.
- Root `timing.json` exists, `total_duration` matches `narration_audio.wav` within ±0.5s.
- `final_video.mp4` (or fallback to `video_with_bgm.mp4` / `output.mp4`) exists and plays.
- Resolution matches project config (1920×1080 / 3840×2160 / 1080×1920 / 2160×3840).
- Audio-video duration drift <0.5s.
- `assets/manifest.json` — every `status: resolved` entry has a file on disk.
- `video_info.yaml` written (Step 11b below).

Exit codes:
- `0` — green.
- `2` — warnings (acceptable — e.g. `video_info.yaml` was missing but everything else passed). Fix before declaring done if possible.
- `1` — failure (blocking). Fix and re-run.

**Never declare a video "done" until verify exits 0 or 2.**

### 11b. Write video_info.yaml

The platform-agnostic metadata file for downstream cover-image / shorts generation. Schema:

```yaml
title: 瑞士航空111号班机空难
logline: 1998年大西洋上空，一场由电线故障引发的灾难与成因
category: aviation-disaster
orientation: horizontal
resolution: 1080p
fps: 30
duration_seconds: 360
language: zh-CN
theme: aviation-disaster
project: aviation-disaster-horizontal
video: swissair-111
created: 2026-07-26
workflow_version: 1.0

chapters:                          # from root timing.json
  - name: opening
    label: 开篇
    start: 0.0
    duration: 60.0
    scenes:
      - { name: hero, label: 引子, start: 0.0, duration: 15.0 }
      - { name: timeline, label: 时间线, start: 15.0, duration: 45.0 }
  - name: main
    label: 主体
    start: 60.0
    duration: 115.0
    scenes:
      - { name: cause_chain, label: 事故链条, start: 60.0, duration: 50.0 }
      - { name: impact, label: 影响, start: 110.0, duration: 40.0 }
      - { name: summary, label: 反思, start: 150.0, duration: 25.0 }

sources:                           # from topic_research.md
  - https://en.wikipedia.org/wiki/Swissair_Flight_111
  - https://www.tsb.gc.ca/eng/rapports-reports/aviation/1998/a98h0003/...

key_frame_timestamps:              # for downstream thumbnails / shorts / cover art
  - { time: 0.0, scene: hero, asset_id: hero_bg, description: "Title card" }
  - { time: 15.0, scene: timeline, asset_id: timeline_chart, description: "Event timeline" }
  - { time: 60.0, scene: cause_chain, description: "Causal flowchart" }
  - { time: 110.0, scene: impact, description: "Casualty stats" }

tags:
  - 航空事故
  - 瑞士航空
  - MD-11
  - 1998
  - 飞行安全

assets:                            # summary of manifest entries
  - { id: hero_bg, type: image, source: t2i, workflow: z_image_fp16 }
  - { id: timeline_chart, type: image, source: user }
```

The agent writes this file at the end of Step 11 by reading `timing.json` (for chapters), the manifest (for asset summary), and `topic_research.md` (for sources). Title/logline/tags come from the agent's own writing.

### 11c. Final video file

`final_video.mp4` is created in Step 10 (just a copy of `video_with_bgm.mp4`). If for some reason Step 10 was skipped (no BGM config), copy `output.mp4` instead:

```bash
[ -f "$VDIR/video_with_bgm.mp4" ] && cp "$VDIR/video_with_bgm.mp4" "$VDIR/final_video.mp4" \
  || cp "$VDIR/output.mp4" "$VDIR/final_video.mp4"
```

`verify_output.py` will pick `final_video.mp4` first, falling back to `video_with_bgm.mp4` then `output.mp4`.

---

## Reporting to the user

After the verify gate passes:

```
✅ Video complete.

Project: aviation-disaster-horizontal
Video:   swissair-111
Path:    projects/aviation-disaster-horizontal/videos/swissair-111/final_video.mp4
Duration: 6:00 (360s)
Resolution: 1920×1080 @ 30fps
Theme: aviation-disaster

Chapters:
  00:00  引子
  00:15  时间线
  01:00  事故链条
  01:50  影响
  02:30  反思

Metadata saved to: video_info.yaml
Use it for downstream cover-image / shorts / publishing tasks.
```

## Regenerating an existing video

If `videos/{name}/` already exists and the user iterates ("regenerate", "re-render", "I edited the script"), reuse the dir. The scene-based pipeline makes iteration cheap — only affected scenes re-synthesize / re-render, then re-merge.

| Change | Re-run (scoped) |
| --- | --- |
| One scene's narration | `tts run --scene {s}` → `tts merge` → render scene {s} → `merge` → Step 10 → 11 |
| One shot's component / props / overlays | `compose` → render scene {s} → `merge` → Step 10 → 11 |
| One scene's shot added/removed | Step 4 (edit yaml) → plan new assets if any (Step 5) → `compose` → render scene {s} → `merge` → 10 → 11 |
| Project theme / colors | `compose` → re-render ALL scenes → `merge` → 10 → 11 |
| Resolution change | Step 7 (re-upscale) → `compose` → re-render ALL scenes → `merge` → 10 → 11 |
| New asset in one scene | Step 5 → `compose` → render that scene → `merge` → 10 → 11 |

`compose` regenerates all scene files (fast — text generation only); you only need to **render** the scenes whose inputs changed. Always finish with `merge` + Step 10 (BGM) + Step 11 (verify), since `output.mp4` / `video_with_bgm.mp4` are stale after any scene re-render.

Never start a fresh project dir for an iteration.
