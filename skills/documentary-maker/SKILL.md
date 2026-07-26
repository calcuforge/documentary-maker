---
name: documentary-maker
description: Use when the user wants to produce a narration-driven documentary video — history, aviation disaster, true crime, or natural disaster. Trigger on phrases like "制作历史纪录片", "帮我做一个空难纪录片", "案件纪录片", "地震纪录片", "aviation disaster documentary", "history documentary", "crime documentary". Produces 1080p/4K horizontal or vertical video via research → script → AIGC visuals → TTS → Remotion → FFmpeg. Reuses the shared `remotion-video-template`; AIGC visuals come from ComfyUI workflows via `comfyui-scheduler`. Also trigger when the user wants to regenerate, re-render, or iterate on a documentary this skill already produced (reuse the existing `projects/{project}/videos/{name}/` directory). Do NOT trigger for generic video editing, podcasts, talking-head explainer videos, trimming, or platform-bound publishing tasks (use video-podcast-maker for those).
argument-hint: "[topic]"
effort: high
author: calcuforge
category: Content Creation
version: 1.0.0
permissions:
  - env
  - file_read
  - file_write
  - network
  - shell
dependencies:
  - comfyui-scheduler
  - remotion-video-template
metadata:
  emoji: "🎞️"
---

# Documentary Maker

Narration-driven documentary pipeline. Research → script → AIGC visuals → TTS → Remotion → FFmpeg. Output is platform-agnostic — no CTA, no thumbnails, no publish-info. A `video_info.yaml` records metadata for downstream cover-image / shorts generation later.

## Differences from `video-podcast-maker`

| Aspect | video-podcast-maker | documentary-maker |
| --- | --- | --- |
| Template | ships its own Remotion template | reuses shared `remotion-video-template` (no copy) |
| Visuals | mostly Remotion components + stock | AIGC-heavy (ComfyUI t2i / i2v / flf2v / upscale) |
| Platform | bilibili / youtube / xiaohongshu / etc. | platform-agnostic — saves `video_info.yaml` instead |
| Preview | Remotion Studio gate before render | no browser preview (Step 9 renders directly) |
| Config | JSON | YAML with comments |
| TTS | ttsCN multi-backend | `comfyui index_tts` (default) OR OpenAI-compatible HTTP server |

## Bootstrap

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`.

```bash
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python3 "${SKILL_DIR}/scripts/check_prereqs.py"
```

Prereqs check validates: `python3`, `ffmpeg`, `ffprobe`, `node`, `npx`, `comfyui-scheduler` on PATH, `remotion-video-template/` exists at the configured path, at least one ComfyUI node registered (via `comfyui-scheduler status`). TTS backend prereqs (a `voice_file` for index_tts, or a server URL for HTTP) are validated lazily at Step 6.

## Execution Modes

| Mode | Behavior |
| --- | --- |
| **Auto** (default) | Pipeline runs end-to-end. Manual mode gates only kick in when the user explicitly asks for control. |
| **Manual** | Each AI product — `narration_script.yaml`, AIGC assets, TTS audio, generated composition — waits for explicit user confirmation ("looks good, continue") before the next step. Set via `project.creation_mode: manual` or the user saying "interactive" / "let me review each step". |

Trigger keyword → category mapping (see `project_prefs.template.yaml` `triggers.keywords`):

- "空难" / "航空事故" → `aviation-disaster`
- "历史纪录片" → `history`
- "案件纪实" / "真实犯罪" → `crime`
- "自然灾害" / "地震" / "海啸" → `natural-disaster`

## Workflow

At Step 1 start, create one task per step in your agent tracker. Mark `in_progress` on start, `completed` on finish. Files in `projects/{p}/videos/{v}/` are the durable record — if interrupted, inspect the directory to determine where to resume.

| # | Step | Output |
| --- | ------ | -------- |
| 1 | Define topic direction | `topic_definition.md` |
| 2 | Research topic (web search/fetch) | `topic_research.md` |
| 3 | Design chapters | `chapters.yaml` |
| 4 | Narration script + per-section visual design | `narration_script.yaml` |
| 5 | Asset plan & AIGC generation | `assets/manifest.json` |
| 6 | Generate TTS + SRT (char-estimated) + timing.json | `narration_audio.wav`, `.srt`, `timing.json` |
| 7 | Upscale to target resolution | updated `assets/*` |
| 8 | Generate per-video composition | `Video.tsx`, `entry.tsx` |
| 9 | Render | `output.mp4` |
| 10 | Mix BGM | `video_with_bgm.mp4` |
| 11 | Verify + save metadata | `final_video.mp4`, `video_info.yaml` |

**Mandatory stops**:
- **Manual mode** — every step from 1 to 8 may pause for user review.
- **Step 11 (Verify gate)** — `verify_output.py` MUST pass before declaring the video done. Exit 0 = green; exit 2 = warnings still acceptable; exit 1 = failure.

## Hard Rules

| Rule | Requirement |
| --- | --- |
| **Shared template** | All videos import from `remotion-video-template/src/components`. NEVER copy the template per video. Per-video `Video.tsx`/`entry.tsx` live in the video dir. |
| **Project grouping** | Videos sharing config live under one `projects/{name}/`. `project_prefs.yaml` is the single source of project truth. |
| **Audio-master clock** | `timing.json.total_duration` matches `narration_audio.wav` within ±0.5s. Char-count estimates the *distribution*; real audio length sets the *total*. See [references/audio-sync.md](references/audio-sync.md). |
| **Resolution** | 1080p (1920×1080 or 1080×1920) or 4K (3840×2160 or 2160×3840). Composition IDs: `MainVideo` / `MainVideo4K` / `MainVideoVertical`. |
| **No CTA** | Outro is plain closing narration; never platform CTA. |
| **No browser preview** | Render directly to file. Studio is not launched. |
| **Verify gate** | `verify_output.py` exit 0 (or 2 with reviewed warnings) before declaring done. |
| **`--public-dir`** | Every remotion command uses `--public-dir projects/{p}/videos/{v}/`. All outputs land in that dir. |
| **YAML config** | Project + video metadata in YAML. JSON only for `timing.json` and `assets/manifest.json` (consumed by Remotion at runtime via staticFile). |

## Per-Video Layout

Directory tree and naming rules: [references/project-layout.md](references/project-layout.md).

## Additional Resources

Load on demand — **do NOT load all at once**:

| File | Load when |
| --- | --- |
| [references/workflow-script.md](references/workflow-script.md) | Steps 1-4 + execution modes |
| [references/workflow-assets.md](references/workflow-assets.md) | Step 5 — AIGC pipeline selection + speed/quality tiers |
| [references/workflow-production.md](references/workflow-production.md) | Steps 6-10 — TTS, upscale, composition, render, BGM |
| [references/workflow-finish.md](references/workflow-finish.md) | Step 11 — verify + video_info.yaml |
| [references/themes.md](references/themes.md) | Theme catalog, adding new themes |
| [references/project-layout.md](references/project-layout.md) | Directory structure, --public-dir, file naming |
| [references/audio-sync.md](references/audio-sync.md) | Char-estimate rules, alignment checkpoints |
| [references/design-guide.md](references/design-guide.md) | Component selection by content type, visual minimums |
| [references/troubleshooting.md](references/troubleshooting.md) | Errors, comfyui/ffmpeg/remotion debug |

All scripts are reachable through one dispatcher:

```bash
python3 ${SKILL_DIR}/scripts/cli.py --help
```

Resources: `project`, `assets`, `tts`, `verify`, `themes`, `prereqs`, `compose`, `audit`, `schema`.

## User Preferences

Project-level preferences live in `projects/{name}/project_prefs.yaml`. Created from `project_prefs.template.yaml` on first `project create`. Per-video overrides go in `videos/{v}/video_info.yaml` (title, logline, etc.). See [references/troubleshooting.md](references/troubleshooting.md) for preference commands.
