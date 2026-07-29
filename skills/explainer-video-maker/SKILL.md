---
name: explainer-video-maker
description: >
  Use when the user wants to create an explainer, documentary, knowledge-sharing,
  news-broadcast, product-introduction, or data-report video from a topic.
  Trigger keywords: "make a documentary", "make a video about", "make an explainer",
  "make a news video", "make a product intro", "make a knowledge video",
  "help me make a ... video". Also trigger for Chinese equivalents like
  "帮我制作一个...纪录片/视频", "做一个...解说视频". Supports auto topic selection
  when user only names a category. Produces video via research → struct design →
  TTS → AIGC → Remotion render → MP4. Do NOT trigger for generic video editing,
  trimming, or format conversion.
argument-hint: "[topic or category]"
effort: high
category: Content Creation
version: 1.0.0
created: 2026-07-30
permissions:
  - env
  - file_read
  - file_write
  - network
  - shell
dependencies:
  - remotion-video-template
  - comfyui-scheduler
metadata:
  requires:
    bins: [python3, ffmpeg, ffprobe, node, npx, comfyui-scheduler]
    python: [requests, pyyaml, playwright]
---

# Explainer Video Maker

Automated pipeline for **narration-driven explainer videos** from any topic.
Supports documentaries, knowledge sharing, news, data reports, product
introductions, and any format suitable for narrated explanation.

Audio drives visuals: narration audio duration determines total frame count
for all scene units under each narration unit.

## Contents

- [Prerequisites](#prerequisites)
- [Project Management](#project-management)
- [Workflow (9 Steps)](#workflow)
- [Hard Rules](#hard-rules)
- [References](#references)

---

## Prerequisites

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`.

```bash
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python3 "${SKILL_DIR}/scripts/tool/check_prereqs.py"
```

External dependencies:
- Python >= 3.10, `requests`, `pyyaml`, `playwright` (+ `playwright install chromium`)
- `ffmpeg`, `ffprobe` on PATH
- Node.js >= 18, `npx`
- `comfyui-scheduler` CLI (`pip install -e ../comfyui-scheduler`)
- A running ComfyUI server with default workflows imported
- `remotion-video-template/` with `node_modules/` installed (`npm install`)

---

## Project Management

**All projects MUST live under the workspace `projects/` directory.**

| Situation | Action |
|-----------|--------|
| First video request | Run Step 1: create a new project |
| Same category + same parameters | Reuse existing project, create a new `video{N}/` subdirectory |
| Different category or parameters | Run Step 1: create a new project |

To determine reuse: compare `project.video_style`, `project.target_audience`,
and `video.resolution`/`video.orientation`. If all match, reuse.

---

## Workflow

> Detailed step-by-step instructions: [references/workflow-steps.md](references/workflow-steps.md)

| # | Step | Key Script | Output |
|---|------|-----------|--------|
| 1 | Project initialization | `scripts/verify/verify_project_config.py` | `project_config.yaml` |
| 2 | Define topic | — (agent research) | `video_config.yaml` |
| 3 | Topic research | `scripts/search_provider/search.py`, `scripts/search_provider/search_rss.py` | `search_results/*.md` |
| 4 | Design video structure | `scripts/verify/verify_video_struct.py` | `video_struct.yaml` |
| 5 | TTS + frame calculation | `scripts/tool/run_tts.py`, `scripts/verify/verify_audio.py` | `speech.wav` per narration |
| 6 | Plan AIGC tasks | `scripts/verify/verify_video_tasks.py` | `video_tasks.yaml` |
| 7 | Execute AIGC tasks | `scripts/tool/run_aigc.py`, `scripts/tool/run_upscale.py`, `scripts/verify/verify_aigc_assets.py` | `scenes/` assets |
| 8 | Generate remotion config | `scripts/tool/generate_remotion_sections.py`, `scripts/verify/verify_remotion_sections.py` | `remotion_sections.yaml` |
| 9 | Render video | `scripts/tool/render.py` | `result.mp4` |

**Mandatory validation gates:**

- After Step 1: `verify_project_config.py` must exit 0
- After Step 4: `verify_video_struct.py` must exit 0 (re-do step if not)
- After Step 5: `verify_audio.py` must exit 0
- After Step 6: `verify_video_tasks.py` must exit 0
- After Step 7: `verify_aigc_assets.py` must exit 0
- After Step 8: `verify_remotion_sections.py` must exit 0

---

## Hard Rules

| Rule | Requirement |
|------|-------------|
| **Projects under workspace** | All project directories MUST be under `projects/` in the workspace. Never create outside. |
| **Audio-master clock** | Narration audio duration determines total frames. `total_frame = ceil(audio_duration × fps)`. Never hand-estimate. |
| **Percent sum** | Scene `percent` values within each narration unit MUST sum to exactly 100. |
| **Locale-aware search** | Detect network locale. China → use Baidu Baike, Bing; elsewhere → Wikipedia, Google. |
| **Playwright for web** | All website access uses Playwright Chromium (headless), except where `curl` is explicitly specified (RSS feeds). |
| **Anti-slop narration** | Narration text MUST follow [references/natural-narration.md](references/natural-narration.md). No AI-sounding filler, no rhetorical hooks, no rule-of-three abuse. |
| **Verify before proceed** | Each step's verify script must pass before moving to the next step. |

---

## References

Load on demand — do NOT load all at once:

| File | Load when |
|------|-----------|
| [references/workflow-steps.md](references/workflow-steps.md) | **Always** — detailed per-step instructions |
| [references/natural-narration.md](references/natural-narration.md) | Step 4 — writing narration content |
| [references/search-providers.md](references/search-providers.md) | Step 3 — topic research |
| [references/expression_intent_mapping.md](references/expression_intent_mapping.md) | Step 4 — choosing scene types and components |
| [templates/demo_projects/](templates/demo_projects/) | Any step — reference for config file structure |
