---
name: explainer-video-maker
description: 旁白驱动的解说视频制作。覆盖动物科普、历史纪录、空难纪录、案件纪实、科技新闻、时事新闻、知识分享等10种分类。AI画面+数据图表+文本组件三层驱动。复用remotion-video-template和comfyui-scheduler。触发词：动物科普、空难纪录片、案件纪实、科技新闻。
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
| Visuals | mostly Remotion components + stock | Shot-based: each shot = source material (AIGC via ComfyUI / stock / user) + auxiliary layers (data charts, text components, transparent overlays) |
| Content types | topic explainers, podcasts | 10 categories: animal/life science, history, disasters, crime, tech news, daily briefing, current affairs, knowledge sharing |
| Platform | bilibili / youtube / xiaohongshu / etc. | platform-agnostic — saves `video_info.yaml` instead |
| Preview | Remotion Studio gate before render | no browser preview (Step 9 renders directly) |
| Config | JSON | YAML with comments |
| TTS | ttsCN multi-backend, chunked | **per-scene** `comfyui index_tts` (default) OR HTTP multipart TTS server, then merged |

## Workspace

**All project data lives under `<workspace>/projects/`** — the workspace is the directory you work from (the user's project folder), NEVER the skill installation directory. Scripts resolve the projects root in this order:

1. `EXPLAINER_PROJECTS_DIR` env var (explicit projects directory)
2. `EXPLAINER_WORKSPACE` env var (workspace root; projects go in `<root>/projects`)
3. `<CWD>/projects` (the normal case)

At workflow start: confirm the current working directory is the workspace root, then **scaffold the project and video directories** before any other work. Shell state doesn't persist between commands, but the working directory does — so a stable CWD is what keeps project resolution consistent:

```bash
pwd                 # must be the workspace root — cd there first if not
mkdir -p projects   # once per workspace
```

## Project Scaffolding (MANDATORY — before Step 1)

Every video MUST live inside a project. Before any content work, scaffold the project and video directories. ALL file outputs (topic_definition.md, narration_script.yaml, assets/, scenes/, renders, etc.) go under `projects/$P/videos/$V/`.

### 1. Determine project name and category

- **Project name**: lowercase, hyphen-separated, ≤64 chars. Derive from the user's topic — e.g. `aviation-disaster` for air crash videos, `animal-science` for animal documentaries. Suffix with `-vertical` for 9:16 orientation.
- **Category**: match from trigger keywords (see Execution Modes section below). If no clear match, default to `knowledge-sharing`.
- **Orientation**: horizontal (16:9) by default; vertical (9:16) if the user asks for shorts/vertical.

### 2. Create the project

```bash
python3 "$SKILL_DIR/scripts/cli.py" project create \
  --name $P \
  --category $CATEGORY \
  --orientation ${ORIENTATION:-horizontal} \
  --language ${LANGUAGE:-zh-CN}
```

This creates `projects/$P/project_prefs.yaml` with theme defaults merged from `themes/$CATEGORY.yaml`.

If the project already exists (e.g. a second video in the same project), skip `project create` and reuse the existing project.

### 3. Create the video subdirectory

```bash
python3 "$SKILL_DIR/scripts/cli.py" project video --name $P --video $V
```

This creates `projects/$P/videos/$V/` with `assets/` and `scenes/` subdirectories.

### 4. Set shell variables for the session

```bash
P="<project-name>"          # e.g. aviation-disaster
V="<video-name>"            # e.g. air-france-447
VDIR="$(pwd)/projects/$P/videos/$V"
```

Use `$P` and `$V` in all subsequent commands. Every file output goes under `$VDIR`.

**After scaffolding, proceed immediately to Step 0 (Voice Design).** Do NOT skip to Step 1.

`check_prereqs.py` prints the resolved workspace projects dir so you can confirm placement before creating anything.

## Bootstrap

Resolve `SKILL_DIR` to the directory containing this `SKILL.md`.

```bash
SKILL_DIR="${SKILL_DIR:-${CLAUDE_SKILL_DIR}}"
python3 "${SKILL_DIR}/scripts/check_prereqs.py"
```

Prereqs check validates: workspace projects dir resolution, `python3`, `ffmpeg`, `ffprobe`, `node`, `npx`, `comfyui-scheduler` on PATH, `remotion-video-template/` exists at the configured path, at least one ComfyUI node registered (via `comfyui-scheduler status`).

## Step 0: Voice Design (once per project)

Before any video is produced, generate a reference voice audio file for the project. Each project gets **exactly one** `voice_reference.wav` shared across all its videos.

### 0a. Check whether voice design is needed

Read `project_prefs.yaml` and check two conditions:

```bash
python3 -c "
import yaml, os
p = yaml.safe_load(open('projects/$P/project_prefs.yaml'))
vf = p.get('tts', {}).get('voice_file', '')
exists = os.path.isfile(vf) if vf else False
print(f'voice_file={vf}')
print(f'exists={exists}')
"
```

**Decision:**
- If `voice_file` is set AND the file exists on disk → **skip Step 0**, proceed to Step 1. The TTS step will read `tts.voice_file` from project prefs to find the reference audio.
- If `voice_file` is null/empty OR the file does not exist → **continue to 0b**. The project has no reference voice yet.

### 0b. Generate voice reference

1. Read the voice design attributes from `project_prefs.yaml` (the `voice_design` section was merged from the theme during `project create`): `voice_design.voice_instruct`, `voice_design.content`, `voice_design.speed`. Each theme defines its own narrator persona using comma-separated attribute values (e.g. `男，中年，低音调`). Valid values are listed in [comfyui-scheduler/doc/workflow.md](../../comfyui-scheduler/doc/workflow.md#ominivoice_voice_design).
2. Choose a workflow: `project_prefs.workflows.voice_design` (default `ominivoice_voice_design`, or `qwen3_tts_voice_design`).
3. Run the voice design workflow (from the workspace root — the download lands in the project dir):

   ```bash
   python3 "$SKILL_DIR/scripts/cli.py" comfyui run \
     -w ominivoice_voice_design \
     -i '{"voice_instruct":"男，中年，低音调","content":"这是一段参考语音样本。","speed":0.9}' \
     --dest-dir "projects/$P/"
   ```

4. Rename the downloaded audio file to `voice_reference.wav` in the project root.
5. Set the path in project prefs so TTS steps auto-resolve it (absolute path from workspace root):

   ```bash
   python3 "$SKILL_DIR/scripts/cli.py" project set \
     --name $P --key tts.voice_file \
     --value "$(pwd)/projects/$P/voice_reference.wav"
   ```

**Manual mode:** show the voice design prompt and ask "Generate this voice?" before running the workflow. Re-generate only if the user asks to change the voice persona.

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

At **Step 0** start, create one task per step (0–11) in your agent tracker. Mark `in_progress` on start, `completed` on finish. Files in `projects/{p}/videos/{v}/` are the durable record — if interrupted, inspect the directory to determine where to resume.

**Structure:** video → chapters → scenes → shots. A **shot** is the visual unit (source material + auxiliary layers: data charts, text components, transparent overlays). A **scene** is one or more shots and is the unit of narration, TTS, subtitles, and rendering. A **chapter** is an organizational grouping only.

| # | Step | Output |
| --- | ------ | -------- |
| 0 | Voice design (once per project) | `projects/{p}/voice_reference.wav` |
| 1 | Define topic direction | `topic_definition.md` |
| 2 | Research topic (provider-driven: agent_search, web_fetch, rss, custom_script) | `topic_research.md` |
| 3 | Design video structure (chapter → scene skeleton) | `narration_script.yaml` (skeleton) |
| 4 | Narration + per-scene shot design | `narration_script.yaml` (full: chapters → scenes → shots) |
| 5 | Shot asset plan & batch AIGC generation / lookup | `assets/manifest.json` (shot-level entries) |
| 6 | Per-scene TTS + SRT + timing (parallel), then merge | `scenes/{s}/narration.wav`, `.srt`, `timing.json`; root `timing.json` + `narration_audio.wav/.srt` |
| 7 | Upscale to target resolution | updated `assets/*` |
| 8 | Generate per-scene composition | `scenes/{s}/scene.tsx`, `entry.tsx`, `composition.json` |
| 9 | Render scenes (parallelizable) → ordered lossless merge | `scenes/{s}/scene.mp4` → `output.mp4` |
| 10 | Mix BGM | `video_with_bgm.mp4` |
| 11 | Verify + save metadata | `final_video.mp4`, `video_info.yaml` |

**Three parallelizable flows after structure design:**
- **Visuals** — Step 5 runs shot-level tasks (AI generation / upscale / asset lookup) in batched parallel; Step 9 renders each scene (narration + subtitles baked in), then merges scenes in order.
- **Audio & subtitles** — Step 6 runs one TTS + one subtitle task per scene, in parallel, then merges.
- **Assembly** — Step 9 scene merge (ordered) → Step 10 BGM last.

### Step 2: Research Topic (MANDATORY — do NOT skip)

Research is driven by **providers** configured in the theme's `research_providers:`. This step MUST be executed before any script writing — the research findings in `topic_research.md` are the factual foundation for the narration script.

**Region auto-detection:** The research planner detects whether the environment is inside China (CN) by testing connectivity to google.com. In CN mode, queries are automatically localized (Wikipedia→百度百科, NTSB→中国民航局, BBC→央视网, etc.) and blocked URLs (google.com, wikipedia.org, twitter.com, youtube.com, etc.) are flagged with domestic alternatives. Override with `RESEARCH_REGION=cn` or `RESEARCH_REGION=global` env var.

**2a. Generate the research plan:**

```bash
python3 "$SKILL_DIR/scripts/cli.py" research plan --project $P --video $V
```

**2b. Execute every enabled provider in the plan.** The JSON output contains one step per provider with an `action` field telling you exactly what to do.

**Web access priority** — for ALL web requests (search, fetch, RSS), use this fallback chain:

| Priority | Method | Command / Tool |
| --- | --- | --- |
| 1 (preferred) | Headless Chrome | `/usr/bin/chrome --headless --dump-dom --disable-gpu --no-sandbox "<url>"` |
| 2 (fallback) | Built-in web fetch | Agent's native WebFetch tool |

Chrome headless renders JavaScript, bypasses basic bot detection, and works through system proxy settings — essential for accessing international sources from CN environments. Use `--dump-dom` for static HTML extraction, or `--screenshot` for visual inspection. Fall back to WebFetch only if Chrome is not installed or exits non-zero.

| Provider | What the agent does |
| --- | --- |
| `agent_search` | Web search using the agent's native search tool. Runs each query in `queries`, reads top 3-5 results, cross-references facts. |
| `web_fetch` | Directly fetches each URL in `urls`. Extracts structured facts from Wikipedia infoboxes, official reports, databases. |
| `rss` | Fetches RSS feed URLs, parses `<item>` entries (title, link, description, pubDate), compiles headlines and summaries. |
| `custom_script` | **Agent writes a Python script** to retrieve structured data. Use `requests` + `feedparser` + `beautifulsoup4` (no other deps). Save to `videos/{v}/scripts/`, run via `python`, capture stdout. Delete after use unless the user asks to keep it. The `script_hint` in the plan describes what the script should do (e.g. RSS aggregator, news clusterer, data crawler). |

After all providers, merge findings into `topic_research.md`. See [references/workflow-script.md](references/workflow-script.md#step-2-research-topic) for the full provider spec, config examples, and output format.

### Step 3: Design Video Structure

Load [references/workflow-script.md](references/workflow-script.md) for detailed instructions. Key points:

- Read the theme's `narrative_arc` from `project_prefs.yaml` — it defines the chapter sequence (e.g. aviation-disaster: hook → background → event_timeline → cause_analysis → impact → aftermath → conclusion).
- Read `project_prefs.content.section_count` for the target scene count.
- Output a **skeleton** `narration_script.yaml` with `chapters:` and `scenes:` (names + labels only, no narration yet).
- Use `cli.py schema validate` to check the skeleton before proceeding.

### Step 4: Narration + Per-Scene Shot Design

Load [references/workflow-script.md](references/workflow-script.md) and [references/design-guide.md](references/design-guide.md) for detailed instructions. **This is the most critical design step** — every visual decision flows from here.

**Each shot MUST have three layers** (even if a layer is empty):

| Layer | Field | Examples |
| --- | --- | --- |
| Primary visual | `component` + `asset_id` | `FullBleedLayout` + `hero_bg`, `Timeline` + (no asset), `MediaSection` + `wreck_photo` |
| Data overlays | `data[]` | `StatHighlight` (casualty count), `DataBar` (safety stats), `Timeline` (event sequence) |
| Text overlays | `text[]` | `QuoteBlock` (investigator quote), `IconCard` (key findings) |

**Asset source distribution** — consult the theme's `visual_composition:` block in `project_prefs.yaml`. For aviation-disaster: AIGC=high, stock=low, data_charts=medium, text_components=low. This means most shots use AI-generated images/videos as the primary visual, with data charts as the secondary layer. **Do NOT make every shot a plain AI image** — mix in:

- **AI-generated video (t2v/i2v)** for b-roll shots (e.g. slow pan over wreckage, atmospheric establishing shots)
- **Data charts** for statistics-heavy scenes (e.g. `DataBar` for safety comparison, `StatHighlight` for fatality count)
- **Text components** for quotes and key findings (e.g. `QuoteBlock` for investigator statements)
- **Pure-text shots** where appropriate (e.g. `Timeline` with no asset_id for event chronology)

**Component selection** — consult the theme's `component_suggestions:` in `project_prefs.yaml`. Each scene type maps to a recommended component:
- `hero` → `FullBleedLayout`
- `timeline` / `event_sequence` → `Timeline`
- `cause_chain` / `cause_analysis` → `FlowChart`
- `impact` / `statistics` → `DataBar`
- `quote` → `QuoteBlock`
- `summary` → `StatHighlight`

Output the **full** `narration_script.yaml` with complete `narration` text per scene and detailed `shots[]` per scene. Run `cli.py schema validate` after writing.

### Step 5: Shot Asset Plan & Batch AIGC Generation

Load [references/workflow-assets.md](references/workflow-assets.md) for detailed instructions. **Register ALL planned assets before generating any.**

1. **Plan**: for every shot in `narration_script.yaml`, register an asset entry:
   ```bash
   python3 "$SKILL_DIR/scripts/cli.py" assets init --video-dir "$VDIR"
   python3 "$SKILL_DIR/scripts/cli.py" assets add \
     --video-dir "$VDIR" --id <id> --scene <s> --shot <sh> \
     --type <image|video> --role <background|inline|broll> \
     --source <t2i|t2v|i2v|text|stock> --status planned \
     --prompt "<detailed prompt>" --workflow <workflow_id>
   ```
   Shots with `component: Timeline` / `FlowChart` / `DataBar` / `StatHighlight` / `QuoteBlock` and no `asset_id` → `--source text --status resolved` (pure Remotion component, no AI generation needed).

2. **Generate in batched order** (see workflow-assets.md#5b-prime-batch-execution-strategy): t2i → i2i → t2v → i2v → flf2v → multi_scene_i2v. Same-workflow jobs in parallel, different workflows sequentially.

3. **After each batch**: update manifest from `planned` → `resolved`:
   ```bash
   python3 "$SKILL_DIR/scripts/cli.py" assets update \
     --video-dir "$VDIR" --id <id> --status resolved --path <filename>
   ```

4. **Validate**: `python3 "$SKILL_DIR/scripts/cli.py" assets validate --video-dir "$VDIR"`

**Minimum asset diversity rule**: a video with 5+ scenes MUST have at least one t2v/i2v video asset, at least two data/text-only shots (source=text), and at least one shot using a non-AIGC image source (stock or research-sourced). Pure t2i-only image slideshows are NOT acceptable output.

**Mandatory stops**:
- **Manual mode** — every step from 1 to 8 may pause for user review.
- **Step 11 (Verify gate)** — `verify_output.py` MUST pass before declaring the video done. Exit 0 = green; exit 2 = warnings still acceptable; exit 1 = failure.

## Hard Rules

| Rule | Requirement |
| --- | --- |
| **Shared template** | All videos import from `remotion-video-template/src/components`. NEVER copy the template per video. Per-video `Video.tsx`/`entry.tsx` live in the video dir. |
| **Project grouping** | Videos sharing config live under one `projects/{name}/`. `project_prefs.yaml` is the single source of project truth. |
| **Workspace placement** | `projects/` lives in the **workspace** (resolved from CWD; env overrides `EXPLAINER_WORKSPACE` / `EXPLAINER_PROJECTS_DIR`). Run every skill command from the workspace root. NEVER create projects inside the skill repo/install dir. |
| **Audio-master clock (scene level)** | Each scene's `scenes/{s}/timing.json.total_duration` equals `ffprobe scenes/{s}/narration.wav` exactly — per-scene TTS means the real scene audio sets the scene's total; no estimation at scene level. Shot durations distribute across the scene by `duration_hint_seconds` (even split without hints). The root `timing.json` aggregates scenes. See [references/audio-sync.md](references/audio-sync.md). |
| **Scene is the render unit** | One Remotion render per scene (`scenes/{s}/scene.mp4`, narration + subtitles baked in). Scenes merge via `cli.py merge` (`ffmpeg -f concat -c copy`, lossless). Transitions run between shots inside a scene; scene joins are hard cuts. |
| **Resolution** | 1080p (1920×1080 or 1080×1920) or 4K (3840×2160 or 2160×3840). Composition IDs: `MainVideo` / `MainVideo4K` / `MainVideoVertical`. |
| **No CTA** | Outro is plain closing narration; never platform CTA. |
| **No browser preview** | Render directly to file. Studio is not launched. |
| **Verify gate** | `verify_output.py` exit 0 (or 2 with reviewed warnings) before declaring done. |
| **`--public-dir`** | Every remotion command uses `--public-dir projects/{p}/videos/{v}/`. All outputs land in that dir. |
| **Voice design** | One `voice_reference.wav` per project, generated by Step 0. All videos in the project share it. Re-generate only on user request. |
| **YAML config** | Project + video metadata in YAML. JSON only for `timing.json` (root + per-scene), `assets/manifest.json`, and per-scene `composition.json` (consumed by Remotion at runtime via staticFile). |
| **ComfyUI batch ordering** | When generating multiple shot assets, group by workflow type. Run same-workflow jobs in parallel within each batch. Batches execute sequentially: voice_design → t2i → i2i → t2v → i2v → flf2v → multi_scene_i2v → video_upscale → image_upscale. Never mix different workflow IDs in one batch. See [references/workflow-assets.md](references/workflow-assets.md#5b-prime-batch-execution-strategy). |
| **Per-scene TTS normalization** | Every scene WAV is normalized to 48 kHz mono pcm_s16le so the merged track can be built with `ffmpeg -c copy`. Never hand-edit scene WAVs into a different format. |

## Per-Video Layout

Directory tree and naming rules: [references/project-layout.md](references/project-layout.md).

## Additional Resources

Load on demand — **do NOT load all at once**:

| File | Load when |
| --- | --- |
| [references/workflow-script.md](references/workflow-script.md) | Steps 1-4 + execution modes |
| [references/workflow-assets.md](references/workflow-assets.md) | Step 5 — AIGC pipeline selection + speed/quality tiers |
| [references/workflow-production.md](references/workflow-production.md) | Steps 6-10 — per-scene TTS, upscale, per-scene composition/render, scene merge, BGM |
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

Resources: `project`, `assets`, `tts` (run / merge), `verify`, `themes`, `prereqs`, `research`, `compose`, `merge`, `audit`, `schema`.

Each theme preset carries a `visual_composition:` block (non-binding guidance on how to balance AIGC vs stock vs data-chart vs text-component sources per category). See [references/design-guide.md](references/design-guide.md#visual-composition-per-theme) for the full table.

## User Preferences

Project-level preferences live in `projects/{name}/project_prefs.yaml`. Created from `project_prefs.template.yaml` on first `project create`. Per-video overrides go in `videos/{v}/video_info.yaml` (title, logline, etc.). See [references/troubleshooting.md](references/troubleshooting.md) for preference commands.
