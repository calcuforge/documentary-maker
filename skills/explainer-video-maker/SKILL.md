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

Audio drives visuals: each scene carries exactly one narration, and that
narration's audio duration determines the scene's total frame count.

## Contents

- [Prerequisites](#prerequisites)
- [Project Management](#project-management)
- [Execution Modes](#execution-modes) — Auto (default) vs Manual
- [Workflow (11 Steps)](#workflow)
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

**Project directory naming:** `scripts/tool/init_project.py` creates the project
directory from the `scripts/project_config_tpl.yaml` template, named via its
`--project-dir-name` argument (convention: the `video_style` value). If the name
already exists, a numeric suffix is appended automatically: `documentary`,
`documentary2`, `documentary3`, ... After creation, edit `project_config.yaml`
to set the actual `project.name`, `project.video_style`, and other
request-dependent fields.

**Video directory — never reuse.** Every video-making request creates a NEW
`video{N}/` directory (`video1`, `video2`, ...). Each time the user asks to make
a video, create the next available `video{N}/`; never reuse or overwrite an
existing one. (Resuming an *interrupted* pipeline continues the same in-progress
`video{N}/` — that is recovery, not reuse.)

**Project directory reuse** (the table below is about the *project* dir, not the
video dir):

| Situation | Action |
|-----------|--------|
| First video request | Run Step 1: create `projects/{video_style}/` |
| Same category + same parameters | Reuse existing project, then create a new `video{N}/` inside it |
| Different category or parameters | Run Step 1: create a new project directory |

To determine project reuse: compare `project.video_style`, `project.target_audience`,
and `video.resolution`/`video.orientation`. If all match, reuse the project (but
still create a new `video{N}/`).

### Project Output Layout

```text
projects/
├── project1/
│   ├── project_config.yaml        # Project global preferences
│   ├── voice_file.wav             # TTS reference voice (shared by all videos)
│   ├── video1/
│   │   ├── result.mp4             # Final rendered video
│   │   ├── video_config.yaml      # Topic definition
│   │   ├── video_struct.yaml      # Video structure (stories → scenes; each scene carries one narration)
│   │   ├── video_tasks.yaml       # AIGC task list
│   │   ├── remotion_sections.yaml # Remotion render config
│   │   ├── tmp/                   # General temporary files (cache, discovery results, etc.)
│   │   ├── search_results/
│   │   │   ├── result1.md         # Research result 1
│   │   │   └── result2.md         # Research result 2
│   │   └── stories/
│   │       ├── story1/
│   │       │   ├── script.md      # Chapter narration script (Step 5)
│   │       │   └── narration1/
│   │       │       ├── speech.wav # Narration audio
│   │       │       └── scenes/
│   │       │           ├── video_prompt.yaml  # Structured video prompt (Step 8a)
│   │       │           ├── origin_scene1.png  # AIGC raw output
│   │       │           ├── scene1.png         # Upscaled asset
│   │       │           ├── origin_scene2.mp4
│   │       │           └── scene2.mp4
│   │       └── story2/
│   └── video2/
└── project2/
```

Detailed structure reference: [templates/demo_projects/](templates/demo_projects/)

---

## Execution Modes

### Auto Mode (default)

The agent makes **all decisions autonomously** across all 11 steps. No user
interaction is required until the final video is ready. Infer sensible
defaults from the user's request (language, style, audience, duration).

### Manual Mode

The agent **pauses for user confirmation** at key points:

| When | What to ask / report |
|------|---------------------|
| **Before Step 1** (project_config generation) | Ask user to confirm: video_style, target_audience, language, orientation, resolution, duration, tts backend |
| **Before Step 2** (topic selection) | Present the chosen topic (auto) or confirm the user's topic; ask user to approve before proceeding |
| **After each step completes** | Report which artifacts were generated (file paths), then wait for user confirmation before starting the next step |

In manual mode, never proceed to the next step until the user explicitly
confirms (e.g., "ok", "continue", "next", "确认", "继续").

### Mode Detection

- **Step 1:** project_config.yaml does not yet exist. If the user explicitly
  requests manual interaction ("I want to control each step", "interactive",
  "手动模式"), run Step 1 in manual mode (ask before creating the config).
  Otherwise default to auto. Write the chosen mode into `project.creation_mode`.
- **Step 2 onwards:** Read `project.creation_mode` from project_config.yaml to
  determine behavior. Do NOT rely on conversational memory — always re-read the
  field from the file.

---

## Workflow

> Detailed step-by-step instructions: [references/workflow-steps.md](references/workflow-steps.md)

| # | Step | Key Script | Output |
|---|------|-----------|--------|
| 1 | Project initialization | `scripts/tool/init_project.py`, `scripts/verify/verify_project_config.py` | `project_config.yaml` |
| 2 | Define topic | — (agent research) | `video_config.yaml` |
| 3 | Topic research | `scripts/search_provider/search.py`, `scripts/search_provider/search_rss.py` | `search_results/*.md` |
| 4 | Design chapter list | `scripts/verify/verify_stories.py` | `video_struct.yaml` (stories only) |
| 5 | Write chapter scripts | `scripts/verify/verify_story_scripts.py` | `stories/{story_id}/script.md` |
| 6 | Design scene list | `scripts/tool/generate_scene_list.py`, `scripts/verify/verify_video_struct.py` | `video_struct.yaml` (full structure) |
| 7 | TTS + frame calculation | `scripts/tool/run_tts.py`, `scripts/verify/verify_audio.py` | `speech.wav` per scene |
| 8 | Design AIGC prompts + plan tasks | `scripts/tool/build_video_prompt.py`, `scripts/verify/verify_video_tasks.py` | `video_prompt.yaml` per scene, `video_tasks.yaml` |
| 9 | Execute AIGC tasks | `scripts/tool/run_aigc.py`, `scripts/tool/run_upscale.py`, `scripts/verify/verify_aigc_assets.py` | `scenes/` assets |
| 10 | Generate remotion config | `scripts/tool/generate_remotion_sections.py`, `scripts/verify/verify_remotion_sections.py` | `remotion_sections.yaml` |
| 11 | Render video | `scripts/tool/render.py` | `result.mp4` |

**Mandatory validation gates:**

- After Step 1: `verify_project_config.py` must exit 0
- After Step 4: `verify_stories.py` must exit 0 (re-do step if not)
- After Step 5: `verify_story_scripts.py` must exit 0
- After Step 6: `verify_video_struct.py` must exit 0
- After Step 7: `verify_audio.py` must exit 0
- After Step 8: `verify_video_tasks.py` must exit 0
- After Step 9: `verify_aigc_assets.py` must exit 0
- After Step 10: `verify_remotion_sections.py` must exit 0

---

## Hard Rules

| Rule | Requirement |
|------|-------------|
| **Projects under workspace** | All project directories MUST be under `projects/` in the workspace. Never create outside. |
| **New video dir per request** | Every video-making request creates a NEW `video{N}/` directory. Never reuse or overwrite an existing `video{N}/` — always pick the next available `N`. |
| **Audio-master clock** | Each scene's narration audio duration determines that scene's total frames. `total_frame = ceil(audio_duration × fps)`. Never hand-estimate. |
| **One scene = one narration** | Every scene carries exactly one nested `narration`. There is no separate narration layer and no `percent` splitting. |
| **Script = merged narrations** | A chapter's `script.md` MUST equal all its scene narrations concatenated in order. Splitting a script into scenes must not add/drop/reword text. Enforced by `verify_video_struct.py`. |
| **Locale-aware search** | Detect network locale. China → use Baidu Baike, Bing; elsewhere → Wikipedia, Google. |
| **Playwright for web** | All website access uses Playwright Chromium (headless), except where `curl` is explicitly specified (RSS feeds). |
| **Anti-slop narration** | Narration text MUST follow [references/natural-narration.md](references/natural-narration.md). No AI-sounding filler, no rhetorical hooks, no rule-of-three abuse. |
| **Narration length** | Each scene's narration `content` MUST be ≤ 50 characters (a ceiling, not a target — aim for ~20-45 chars of substance and vary length; don't make them all tiny). Enforced by `verify_video_struct.py`. Split longer text into more scenes. |
| **Verify before proceed** | Each step's verify script must pass before moving to the next step. |
| **Absolute paths** | All script path arguments (`--config`, `--video-struct`, `--output`, etc.) MUST be absolute paths. Scripts reject relative paths with an error. |
| **Output confined to project** | ALL agent-produced files (search results, scripts, audio, AIGC assets, remotion configs, rendered video) MUST be written under the project directory's pre-defined resource dirs or its `tmp/` directory. Scripts that produce output files MUST expose a `--output` (or equivalent) parameter so output paths are explicit. NEVER write to system temp dirs (`/tmp`, `%TEMP%`, `TMPDIR`), the workspace root, or any path outside the project. |
| **AIGC cross-scene consistency** | For subjects that appear across multiple AIGC scenes (recurring characters, specific objects, branded items, consistent environments), the `common.subject.description` and `common.style` fields in all their `video_prompt.yaml` files MUST use the SAME appearance description (same wording, same visual attributes). This prevents ComfyUI from generating visually inconsistent outputs for the same subject across scenes. If a character/object appears in N scenes, write the description once, then reuse it verbatim in all N prompt files. |

---

## References

Load on demand — do NOT load all at once:

| File | Load when |
|------|-----------|
| [references/workflow-steps.md](references/workflow-steps.md) | **Always** — detailed per-step instructions |
| [references/natural-narration.md](references/natural-narration.md) | Step 5 — writing chapter narration scripts |
| [references/search-providers.md](references/search-providers.md) | Step 3 — topic research |
| [references/expression_intent_mapping.md](references/expression_intent_mapping.md) | Step 6 — choosing scene types and components |
| [templates/demo_projects/](templates/demo_projects/) | Any step — reference for config file structure |
