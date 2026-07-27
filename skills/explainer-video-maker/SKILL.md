---
name: explainer-video-maker
description: Use when the user wants to produce a narration-driven explainer video — animal science, life science, history documentary, aviation disaster, true crime, tech news, daily briefing, current affairs, knowledge sharing, or natural disaster. Trigger on phrases like "动物科普", "生活科普", "为什么...", "历史纪录片", "空难纪录片", "案件纪实", "科技新闻", "今日新闻", "时事热点", "涨知识", "knowledge video", "explainer video", "animal documentary". Produces 1080p/4K horizontal or vertical video via research → script → AIGC visuals → TTS → Remotion → FFmpeg. Reuses the shared `remotion-video-template`; AIGC visuals come from ComfyUI workflows via `comfyui-scheduler`. Also trigger when the user wants to regenerate, re-render, or iterate on a video this skill already produced (reuse the existing `projects/{project}/videos/{name}/` directory). Do NOT trigger for generic video editing, podcasts, talking-head videos, trimming, or platform-bound publishing tasks (use video-podcast-maker for those).
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

# Explainer Video Maker

Narration-driven explainer video pipeline. Research → script → AIGC visuals → TTS → Remotion → FFmpeg. Covers animal science, life science, history documentaries, disaster stories, true crime, tech news, daily briefings, current affairs, knowledge sharing, and more. Output is platform-agnostic — no CTA, no thumbnails, no publish-info. A `video_info.yaml` records metadata for downstream cover-image / shorts generation later.

## Differences from `video-podcast-maker`

| Aspect | video-podcast-maker | explainer-video-maker |
| --- | --- | --- |
| Template | ships its own Remotion template | reuses shared `remotion-video-template` (no copy) |
| Visuals | mostly Remotion components + stock | Three-layer: AIGC (ComfyUI) + data charts (DataBar/StatHighlight/MetricsRow) + text (QuoteBlock/IconCard/FeatureGrid) |
| Content types | topic explainers, podcasts | 10 categories: animal/life science, history, disasters, crime, tech news, daily briefing, current affairs, knowledge sharing |
| Platform | bilibili / youtube / xiaohongshu / etc. | platform-agnostic — saves `video_info.yaml` instead |
| Preview | Remotion Studio gate before render | no browser preview (Step 9 renders directly) |
| Config | JSON | YAML with comments |
| TTS | ttsCN multi-backend | `comfyui index_tts` (default) OR HTTP multipart TTS server |

## Bootstrap

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`.

```bash
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python3 "${SKILL_DIR}/scripts/check_prereqs.py"
```

Prereqs check validates: `python3`, `ffmpeg`, `ffprobe`, `node`, `npx`, `comfyui-scheduler` on PATH, `remotion-video-template/` exists at the configured path, at least one ComfyUI node registered (via `comfyui-scheduler status`).

## Step 0: Voice Design (once per project)

Before any video is produced, generate a reference voice audio file for the project. Each project gets **exactly one** `voice_reference.wav` shared across all its videos.

1. Resolve the voice design attributes from the theme preset (`voice_design.voice_instruct`, `voice_design.content`, `voice_design.speed`) — each theme defines its own narrator persona using comma-separated attribute values (e.g. `男，中年，低音调`). Valid values are listed in [comfyui-scheduler/doc/workflow.md](../../comfyui-scheduler/doc/workflow.md#ominivoice_voice_design).
2. Choose a workflow: `project_prefs.workflows.voice_design` (default `ominivoice_voice_design`, or `qwen3_tts_voice_design`).
3. Run the voice design workflow:

   ```bash
   python3 "$SKILL_DIR/scripts/cli.py" comfyui run \
     -w ominivoice_voice_design \
     -i '{"voice_instruct":"男，中年，低音调","content":"这是一段参考语音样本。","speed":0.9}' \
     --dest-dir "$SKILL_DIR/../projects/$P/"
   ```

4. Rename the downloaded audio file to `voice_reference.wav` in the project root.
5. Set the path in project prefs so TTS steps auto-resolve it:

   ```bash
   python3 "$SKILL_DIR/scripts/cli.py" project set \
     --name $P --key tts.voice_file \
     --value "$SKILL_DIR/../projects/$P/voice_reference.wav"
   ```

**Skip if** `projects/{p}/voice_reference.wav` already exists and `tts.voice_file` is set. Re-generate only if the user asks to change the voice persona.

**Manual mode:** show the voice design prompt and ask "Generate this voice?" before running the workflow.

## Execution Modes

| Mode | Behavior |
| --- | --- |
| **Auto** (default) | Pipeline runs end-to-end. Manual mode gates only kick in when the user explicitly asks for control. |
| **Manual** | Each AI product — `narration_script.yaml`, AIGC assets, TTS audio, generated composition — waits for explicit user confirmation ("looks good, continue") before the next step. Set via `project.creation_mode: manual` or the user saying "interactive" / "let me review each step". |

Trigger keyword → category mapping (see `project_prefs.template.yaml` `triggers.keywords`):

- "动物科普" / "动物世界" → `animal-science`
- "为什么..." / "怎么回事" / "生活科普" / "冷知识" → `life-science`
- "历史纪录片" / "历史事件" → `history`
- "空难" / "航空事故" → `aviation-disaster`
- "案件纪实" / "真实犯罪" / "悬案" → `crime`
- "自然灾害" / "地震" / "海啸" → `natural-disaster`
- "科技新闻" / "新技术" / "AI" → `tech-news`
- "今日新闻" / "新闻简报" / "每日资讯" → `daily-news`
- "时事热点" / "社会热点" / "时事评论" → `current-affairs`
- "知识分享" / "科普" / "涨知识" / "你知道吗" → `knowledge-sharing`

## Workflow

At Step 1 start, create one task per step in your agent tracker. Mark `in_progress` on start, `completed` on finish. Files in `projects/{p}/videos/{v}/` are the durable record — if interrupted, inspect the directory to determine where to resume.

| # | Step | Output |
| --- | ------ | -------- |
| 0 | Voice design (once per project) | `projects/{p}/voice_reference.wav` |
| 1 | Define topic direction | `topic_definition.md` |
| 2 | Research topic (provider-driven: agent_search, web_fetch, rss, custom_script) | `topic_research.md` |
| 3 | Design chapters | `chapters.yaml` |
| 4 | Narration script + per-section visual design | `narration_script.yaml` |
| 5 | Asset plan & AIGC generation | `assets/manifest.json` |
| 6 | Generate TTS + SRT (char-estimated) + timing.json | `narration_audio.wav`, `.srt`, `timing.json` |
| 7 | Upscale to target resolution | updated `assets/*` |
| 8 | Generate per-video composition | `Video.tsx`, `entry.tsx` |
| 9 | Render | `output.mp4` |
| 10 | Mix BGM | `video_with_bgm.mp4` |
| 11 | Verify + save metadata | `final_video.mp4`, `video_info.yaml` |

### Step 2: Research Providers

Research is abstracted into four **provider types**, configured per theme in `research_providers:`. Generate a plan via `cli.py research plan --project $P --video $V`, then execute each provider in order. Same-type providers in one step can be parallelized.

| Provider | What the agent does |
| --- | --- |
| `agent_search` | Web search using the agent's native search tool. Runs each query in `queries`, reads top 3-5 results, cross-references facts. |
| `web_fetch` | Directly fetches each URL in `urls`. Extracts structured facts from Wikipedia infoboxes, official reports, databases. |
| `rss` | Fetches RSS feed URLs, parses `<item>` entries (title, link, description, pubDate), compiles headlines and summaries. |
| `custom_script` | **Agent writes a Python script** to retrieve structured data. Use `requests` + `feedparser` + `beautifulsoup4` (no other deps). Save to `videos/{v}/scripts/`, run via `python`, capture stdout. Delete after use unless the user asks to keep it. The `script_hint` in the plan describes what the script should do (e.g. RSS aggregator, news clusterer, data crawler). |

After all providers, merge findings into `topic_research.md`. See [references/workflow-script.md](references/workflow-script.md#step-2-research-topic) for the full provider spec, config examples, and output format.

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
| **Voice design** | One `voice_reference.wav` per project, generated by Step 0. All videos in the project share it. Re-generate only on user request. |
| **YAML config** | Project + video metadata in YAML. JSON only for `timing.json` and `assets/manifest.json` (consumed by Remotion at runtime via staticFile). |
| **ComfyUI batch ordering** | When generating multiple assets, group by workflow type. Run same-workflow jobs in parallel within each batch. Batches execute sequentially: voice_design → t2i → i2i → t2v → i2v → flf2v → multi_scene_i2v → video_upscale → image_upscale. Never mix different workflow IDs in one batch. See [references/workflow-assets.md](references/workflow-assets.md#5b-prime-batch-execution-strategy). |

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

Resources: `project`, `assets`, `tts`, `verify`, `themes`, `prereqs`, `research`, `compose`, `audit`, `schema`.

Each theme preset carries a `visual_composition:` block (non-binding guidance on how to balance AIGC vs stock vs data-chart vs text-component sources per category). See [references/design-guide.md](references/design-guide.md#visual-composition-per-theme) for the full table.

## User Preferences

Project-level preferences live in `projects/{name}/project_prefs.yaml`. Created from `project_prefs.template.yaml` on first `project create`. Per-video overrides go in `videos/{v}/video_info.yaml` (title, logline, etc.). See [references/troubleshooting.md](references/troubleshooting.md) for preference commands.
