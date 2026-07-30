# Workflow Steps — Detailed Instructions

> **When to load:** Always — this is the primary step-by-step guide for the agent.

## Overview

The pipeline produces narration-driven explainer videos through 9 steps.
Audio drives visuals: narration audio length determines frame counts.

Structure hierarchy: **Story → Narration → Scene**
- 1 story contains N narration units
- 1 narration unit contains N scene units
- Scene units split the narration duration by `percent`

### Project Output Layout

All pipeline artifacts live under the workspace `projects/` directory:

```text
projects/
├── {project_name}/
│   ├── project_config.yaml        # Step 1 — project global preferences
│   ├── voice_file.wav             # Step 1 — TTS reference voice
│   ├── {video_name}/
│   │   ├── video_config.yaml      # Step 2 — topic definition
│   │   ├── search_results/        # Step 3 — research artifacts
│   │   │   ├── result1.md
│   │   │   └── result2.md
│   │   ├── video_struct.yaml      # Step 4 — video structure definition
│   │   ├── stories/               # Step 5+7 — audio & AIGC assets
│   │   │   └── {story_id}/
│   │   │       └── {narration_id}/
│   │   │           ├── speech.wav
│   │   │           └── scenes/
│   │   │               ├── origin_{scene_id}.{png|mp4}
│   │   │               └── {scene_id}.{png|mp4}
│   │   ├── video_tasks.yaml       # Step 6 — AIGC task list
│   │   ├── remotion_sections.yaml # Step 8 — render config
│   │   └── result.mp4             # Step 9 — final video
```

---

### Execution Modes

| Mode | Behavior |
|------|----------|
| **Auto** (default) | Agent decides everything autonomously. No pauses. Runs Steps 1-9 end-to-end. |
| **Manual** | Agent pauses for confirmation at: (1) before generating project_config.yaml, (2) before topic selection, (3) after every step completes. |

**Mode detection:**
- **Step 1:** `project_config.yaml` does not exist yet. If the user explicitly requests manual interaction ("interactive", "手动模式", "I want to control each step"), run in manual mode. Otherwise default to auto. Write the decision into `project.creation_mode`.
- **Step 2 onwards:** Always read `project.creation_mode` from `project_config.yaml` to determine behavior. Do NOT rely on conversational memory — re-read the field from the file at each step boundary.

**Manual mode protocol:**
- Before Step 1: ask the user to confirm project parameters (style, audience, language, orientation, resolution, duration, TTS backend).
- Before Step 2: present the topic choice and wait for approval.
- After each step: report generated artifacts (list file paths), then wait for the user to say "continue" / "确认" / "ok" before proceeding.
- Never skip a confirmation gate in manual mode.

---

## Step 1: Project Initialization

**When:** First video request, or when category/parameters differ from existing projects.

> **Manual mode:** Before generating project_config.yaml, present all configurable
> fields to the user and ask for confirmation. Do NOT create the file until the
> user approves the parameters.

**What to do:**

1. Create project directory under `projects/`:
   ```
   projects/{project_name}/
   ```

2. Create `project_config.yaml` — fill these fields NOW:
   - `project.name` — descriptive project name
   - `project.project_root_path` — absolute path to the project dir
   - `project.creation_mode` — `auto` (pipeline runs end-to-end) or `manual` (confirm each AI product)
   - `project.language` — `zh-CN` or `en-US` (match user's language)
   - `project.video_style` — e.g., `documentary`, `knowledge_sharing`, `news_broadcast`, `product_intro`, `data_report`, `tutorial`
   - `project.target_audience` — e.g., `general`, `tech_enthusiasts`, `students`, `professionals`, `investors`
   - `video.orientation` — `horizontal` or `vertical`
   - `video.resolution` — `1080p` or `4k`
   - `video.fps` — typically `24`
   - `aigc.quality_tier` — `speed` (faster, lower res then upscale) or `quality`
   - `tts.backend` — `comfyui_indextts` or `http_server`
   - `tts.voice_file` — leave empty if voice not yet designed
   - `content.duration` — `short` (1-3min) / `medium` (3-7min) / `long` (7-15min)
   - `dependence_paths.remotion_template` — relative or absolute path to remotion-video-template

3. Fields that can wait for later steps:
   - `tts.voice_instruct` — Step 5 (or voice design step)
   - `theme.*` — defaults are fine initially, customize before Step 8
   - `subtitle.*` — defaults are fine
   - `rss_source_list` — Step 3

4. **Reference:** [demo_projects/project1/project_config.yaml](demo_projects/project1/project_config.yaml)

5. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_project_config.py" --config /abs/path/project_config.yaml
   ```
   Must exit 0 before proceeding.

6. If `tts.voice_file` is empty, generate a reference voice:
   ```bash
   comfyui-scheduler run -w ominivoice_voice_design -i '{"voice_instruct": "male, middle-aged, moderate pitch", "content": "This is a sample sentence for voice reference."}'
   ```
   Download the output and save as `projects/{name}/voice_file.wav`. Update `tts.voice_file` in the config.

---

## Step 2: Define Topic Direction

**When:** Every new video.

> **Manual mode:** Present the topic (auto-selected or user-specified) and ask
> the user to confirm before proceeding. In auto mode, proceed directly.

**What to do:**

1. Create video directory: `projects/{project_name}/video{N}/`

2. **Auto topic selection** (user only names a category):
   - The agent selects a specific topic that:
     - Fits the project's `video_style` category
     - Does not duplicate existing videos in this project
     - Has rich, explorable content
   - Example: user says "make an animal documentary" → agent picks "The Migration of Arctic Terns"

3. **Specific topic** (user names a topic):
   - Use the user's topic directly

4. Create `video_config.yaml`:
   ```yaml
   topic: <chosen topic title>
   ```

5. **Reference:** [demo_projects/project1/video1/video_config.yaml](demo_projects/project1/video1/video_config.yaml)

---

## Step 3: Topic Research

**When:** After topic is defined.

**What to do:**

1. **Default:** Use the agent's built-in `web_search` tool for initial research.

2. **Extended search** — choose providers based on video type:

   | Video Type | Recommended Providers |
   |-----------|----------------------|
   | Documentary | `search.py` (encyclopedia + search engine) |
   | News / Daily Report | `search_rss.py` (RSS feeds) |
   | Product / Price Report | Custom provider (agent-coded) |
   | Knowledge / Tutorial | `search.py` + agent web_search |

3. **Using search_provider/search.py:**
   ```bash
   python3 "${SKILL_DIR}/scripts/search_provider/search.py" \
     --query "Air France Flight 447 accident investigation" \
     --output /abs/path/projects/project1/video1/search_results/result1.md
   ```
   - Sources auto-detected by locale (China: bing+baike, else: google+wikipedia)
   - Override with `--sources bing,baike`

4. **Using search_provider/search_rss.py:**
   - First check `project_config.yaml` → `rss_source_list` for cached feeds
   - If suitable feeds exist, use them directly:
     ```bash
     python3 "${SKILL_DIR}/scripts/search_provider/search_rss.py" \
       --feed-url "https://rsshub.app/36kr/newsflashes" \
       --keywords "GPU,pricing" \
       --output /abs/path/projects/project1/video1/search_results/result2.md
     ```
   - If no suitable feeds, discover them:
     ```bash
     python3 "${SKILL_DIR}/scripts/tool/search_rss_discovery.py" \
       --query "GPU pricing news" \
       --output /abs/path/rss_sources.json
     ```
     Then cache discovered feeds into `project_config.yaml` → `rss_source_list`.

5. **Custom providers:** For specialized data (e.g., e-commerce price scraping), the agent writes a custom search provider script. Place it in `search_provider/` and document its usage.

6. Save all results to `projects/{project}/video{N}/search_results/result{M}.md`

7. **Reference:** [search-providers.md](search-providers.md) for provider details.

---

## Step 4: Design Video Structure

**When:** After research is complete.

**What to do:**

1. Based on research, design the video structure:
   - Divide content into **stories** (chapters/sections)
   - Each story has **narration units** (paragraphs of spoken text)
   - Each narration has **scene units** (visual elements)

2. For each scene, decide the expression method using
   [expression_intent_mapping.md](expression_intent_mapping.md):
   - **AIGC scenes** (`is_aigc_scene: true`): need AI-generated imagery/video
   - **Data/text scenes** (`is_aigc_scene: false`): filled with text/data directly into Remotion components

3. **Write narration content** — MUST follow [natural-narration.md](natural-narration.md):
   - No AI filler phrases
   - No rule-of-three abuse
   - Vary sentence length
   - State facts directly
   - Write for the ear, not the eye

4. Create `video_struct.yaml` with these fields per scene:
   - Fill NOW: `id`, `intent`, `percent`, `content`, `is_aigc_scene`, `type`, `remotion_component`, `visual_content`, `data`, `text`, `workflows`
   - Leave EMPTY (auto-filled later): `asset_path`, `total_frame`, `audio_path`, `origin_asset_path`

5. **Percent rule:** Within each narration unit, all scene `percent` values MUST sum to exactly 100.

6. **Reference:** [demo_projects/project1/video1/video_struct.yaml](demo_projects/project1/video1/video_struct.yaml)

7. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_video_struct.py" --video-struct /abs/path/video_struct.yaml
   ```
   If it fails, fix and re-validate. Do NOT proceed until exit 0.

---

## Step 5: TTS Synthesis + Frame Calculation

**When:** After video_struct.yaml passes validation.

**What to do:**

1. Run TTS synthesis:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_tts.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml
   ```
   This will:
   - Generate `speech.wav` for each narration unit
   - Measure audio duration via ffprobe
   - Calculate `total_frame = ceil(duration × fps)`
   - Update `video_struct.yaml` with `audio_path` and `total_frame`

2. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_audio.py" --video-struct /abs/path/video_struct.yaml
   ```

---

## Step 6: Plan AIGC Tasks

**When:** After TTS is complete and frames are calculated.

**What to do:**

1. Review `video_struct.yaml` — identify all scenes where `is_aigc_scene: true`.

2. For each AIGC scene, design:
   - **Prompt:** Based on `visual_content`, craft an effective generation prompt
   - **Workflow pipeline:** Choose from available workflows (see `comfyui-scheduler/doc/workflow.md`):
     - `z_image_fp16` — text-to-image
     - `ltx2.3_t2v_int8` — text-to-video
     - `ltx2.3_i2v_int8` — image-to-video
     - `ltx2.3_flf2v_int8` — first-last-frame-to-video
     - `qwen_image_edit_2511_int8_step4` — image-to-image
   - **Dependencies:** e.g., text-to-image → image-to-video (two groups)

3. Group tasks by `workflow_code`. Groups with dependencies go later.

4. Calculate dimensions based on `aigc.quality_tier`:
   - `speed`: image 1280×720, video 854×480
   - `quality`: image 1920×1080, video 1280×720

5. Calculate `total_frame` for video tasks from the scene's allocated frames:
   `scene_frames = narration.total_frame × scene.percent / 100`

6. Use `$taskN` placeholder in payload to reference dependent task output.

7. Create `video_tasks.yaml`:
   **Reference:** [demo_projects/project1/video1/video_tasks.yaml](demo_projects/project1/video1/video_tasks.yaml)

8. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_video_tasks.py" \
     --video-tasks /abs/path/video_tasks.yaml \
     --video-struct /abs/path/video_struct.yaml
   ```

---

## Step 7: Execute AIGC Tasks

**When:** After video_tasks.yaml passes validation.

**What to do:**

1. Run AIGC generation:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_aigc.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml \
     --video-tasks /abs/path/video_tasks.yaml
   ```
   This executes task groups in order, resolves `$taskN` dependencies,
   saves outputs as `origin_{scene_id}.{ext}`, and updates `origin_asset_path`.

2. Run upscale (if quality_tier requires it):
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_upscale.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml
   ```
   This upscales origin assets to target resolution and updates `asset_path`.

3. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_aigc_assets.py" \
     --video-struct /abs/path/video_struct.yaml --check-upscaled
   ```

---

## Step 8: Generate Remotion Rendering Config

**When:** After all assets are verified.

**What to do:**

1. Generate the config skeleton:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/generate_remotion_sections.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml \
     --output /abs/path/remotion_sections.yaml
   ```

2. **Fill `remotion_data` for each section.** The script generates the structure
   but `remotion_data` may need enrichment. Consult the remotion-video-template
   README.md for each component's expected data format:

   | Component | Key Fields |
   |-----------|-----------|
   | QuoteBlock | `heading`, `quote`, `attribution` |
   | FeatureGrid | `heading`, `columns`, `items[{icon, title, description}]` |
   | IconCard | `heading`, `icon`, `title`, `description` |
   | ComparisonCard | `heading`, `left{title, items[], highlight}`, `right{...}` |
   | StatCounter | `heading`, `items[{value, suffix, label, icon}]` |
   | DataBar | `heading`, `items[{label, value}]` |
   | Timeline | `heading`, `items[{label, description}]` |
   | FlowChart | `heading`, `steps[{label, description, icon}]` |
   | CodeBlock | `heading`, `title`, `lines[]` |
   | DataTable | `heading`, `headers[]`, `rows[][]`, `highlightRows[]` |
   | DiagramReveal | `heading`, `direction`, `nodes[{id, label}]`, `edges[{from, to}]` |
   | AnimationDemo | `heading`, `type`, `color` |
   | AssetImage | `src`, `role`, `caption` |
   | AssetVideo | `src`, `role`, `muted` |

3. **Reference:** [demo_projects/project1/video1/remotion_sections.yaml](demo_projects/project1/video1/remotion_sections.yaml)

4. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_remotion_sections.py" \
     --remotion-sections /abs/path/remotion_sections.yaml
   ```

---

## Step 9: Render Video

**When:** After remotion_sections.yaml passes validation.

**What to do:**

1. (Optional) Preview in Studio first:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/render.py" \
     --remotion-sections /abs/path/remotion_sections.yaml \
     --project-config /abs/path/project_config.yaml \
     --output /abs/path/result.mp4 \
     --studio
   ```

2. Render final video:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/render.py" \
     --remotion-sections /abs/path/remotion_sections.yaml \
     --project-config /abs/path/project_config.yaml \
     --output /abs/path/projects/{project}/video{N}/result.mp4
   ```

3. Verify the output file exists and is non-empty.

---

## Step Completion Reporting (Manual Mode)

In manual mode, after each step finishes, report artifacts and wait for user
confirmation. Use this template:

```
✅ Step {N} complete: {step name}

Generated artifacts:
- {file_path_1}
- {file_path_2}
...

{Optional: key summary, e.g. "3 stories, 8 narrations, 15 scenes" or
"TTS generated 8 audio files, total duration 4:32"}

Shall I proceed to Step {N+1}: {next step name}?
```

Per-step artifact summary:

| Step | Artifacts to report |
|------|-------------------|
| 1 | `project_config.yaml`, `voice_file.wav` (if generated) |
| 2 | `video_config.yaml` (show the chosen topic) |
| 3 | `search_results/result{N}.md` (list all, count of results) |
| 4 | `video_struct.yaml` (story/narration/scene counts) |
| 5 | `speech.wav` files (count, total duration) |
| 6 | `video_tasks.yaml` (task group count, total tasks) |
| 7 | `scenes/origin_*` + upscaled files (count) |
| 8 | `remotion_sections.yaml` (section count) |
| 9 | `result.mp4` (file size, duration) |

---

## Resuming After Interruption

If the pipeline is interrupted, inspect the video directory to determine
where to resume:

| Files present | Resume from |
|--------------|-------------|
| `video_config.yaml` only | Step 3 |
| + `search_results/` | Step 4 |
| + `video_struct.yaml` (no audio) | Step 4 validation → Step 5 |
| + audio files + frames set | Step 6 |
| + `video_tasks.yaml` | Step 7 |
| + `scenes/` with assets | Step 8 |
| + `remotion_sections.yaml` | Step 9 |
