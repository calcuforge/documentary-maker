# Workflow Steps — Detailed Instructions

> **When to load:** Always — this is the primary step-by-step guide for the agent.

## Overview

The pipeline produces narration-driven explainer videos through 9 steps.
Audio drives visuals: narration audio length determines frame counts.

Structure hierarchy: **Story → Scene** (each scene carries one narration)
- 1 story contains N scene units
- Each scene has exactly one nested `narration` (1 scene = 1 narration)
- The narration audio duration determines the scene's total frame count

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

> **Manual mode:** Before running init_project.py, present all configurable
> fields to the user and ask for confirmation. Do NOT create the project until
> the user approves the parameters.

**What to do:**

1. **Generate the project skeleton with the init script.** All default field
   values live in the template `scripts/project_config_tpl.yaml` (nothing is
   hardcoded in the script). The script copies the template into a new project
   directory under `projects/`, fills `project.project_root_path` (the only
   field it sets), and writes `project_config.yaml`:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/init_project.py" \
     --projects-dir /abs/path/projects \
     --project-dir-name air_crash_documentary
   ```
   - `--project-dir-name` is the project directory name (convention: the
     `video_style` category). A numeric suffix is appended if it already exists
     (`air_crash_documentary`, `air_crash_documentary2`, ...).
   - The JSON output's `data.project_dir` and `data.project_config` give the created
     project directory and `project_config.yaml` locations. `data.agent_supplement`
     lists the fields left empty for you to fill.

2. **Edit the created `project_config.yaml` directly** to supply the
   request-dependent fields and adjust defaults to match the request:
   - `project.name` — descriptive project name
   - `project.language` — `zh-CN` or `en-US` (match the user's language)
   - `project.video_style` — e.g., `documentary`, `knowledge_sharing`, `news_broadcast`, `product_intro`, `data_report`, `tutorial`
   - `project.target_audience` — e.g., `general`, `tech_enthusiasts`, `students`, `professionals`, `investors`
   - `dependence_paths.remotion_template` / `dependence_paths.comfyui_scheduler`
     — **required for validation**; paths to remotion-video-template and
     comfyui-scheduler (relative to the repo root, or absolute)
   - Adjust `video.orientation` / `resolution`, `content.duration`,
     `project.creation_mode`, and `tts.voice_instruct` as needed.
     `tts.voice_instruct` is **required** (e.g., `男，中年，中音调` or
     `male, middle-aged, moderate pitch`). See
     `comfyui-scheduler/doc/workflow.md` for the valid voice attributes.

3. Fields that can wait for later steps:
   - `tts.voice_file` — Step 5 (auto-generated from `voice_instruct`)
   - `theme.*` — defaults are fine initially, customize before Step 8
   - `subtitle.*` — defaults are fine
   - `rss_source_list` — Step 3

4. **Reference:** [demo_projects/project1/project_config.yaml](demo_projects/project1/project_config.yaml)

5. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_project_config.py" --config /abs/path/project_config.yaml
   ```
   Must exit 0 before proceeding.

6. (Optional) `tts.voice_file` is empty by default and auto-generates in Step 5.
   To pre-generate a reference voice now:
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

1. Create a **new** video directory: `projects/{project_name}/video{N}/`.
   Every video-making request gets its own directory — use the next available
   `N` (`video1`, `video2`, ...). **Never reuse or overwrite an existing
   `video{N}/`** for a new request.

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
     --output /abs/path/projects/air_crash_documentary/video1/search_results/result1.md
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
       --output /abs/path/projects/air_crash_documentary/video1/search_results/result2.md
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
   - Each story has **scene units** (visual elements)
   - Each scene carries exactly one **narration** (the spoken text for that scene)

   **Content volume reference** (from `content.duration` in project_config.yaml).
   Since 1 scene = 1 narration, the scene count equals the narration count:

   | Duration | Stories | Scenes (= narrations) | Approx. length |
   |----------|---------|-----------------------|----------------|
   | short (2-5min) | 2-3     | 10-15                 | ~4 min         |
   | medium (8-12min) | 5-7     | 25-30                 | ~10 min        |
   | long (15-20min) | 8-12    | 50-60                 | ~18 min        |

   **Each scene's narration MUST be ≤ 50 characters** (roughly 1-2 short
   sentences, ~10-12 seconds of speech). If a passage is longer, split it into
   multiple scenes. This is enforced by `verify_video_struct.py`.

   **Build the structure in segments — do NOT generate everything at once:**
   - **First pass (all at once):** lay out the whole `stories` list in one go —
     just each story's `id` + `name`. This is cheap and locks in the overall arc.
   - **Second pass (one story at a time):** then design the `scene_list` for
     **one story at a time** — its scenes, narrations, and expression methods —
     and finish it before moving to the next story. Do NOT generate every scene
     of every story in a single pass. Focusing on one story at a time produces
     richer, more detailed scenes and narrations.

2. For each scene, decide the expression method using
   [expression_intent_mapping.md](expression_intent_mapping.md):
   - **AIGC scenes** (`is_aigc_scene: true`): need AI-generated imagery/video
   - **Data/text scenes** (`is_aigc_scene: false`): filled with text/data directly into Remotion components

3. **Write narration content** — MUST follow [natural-narration.md](natural-narration.md):
   - **≤ 50 characters per narration** — split longer text into more scenes
   - No AI filler phrases
   - No rule-of-three abuse
   - Vary sentence length
   - State facts directly
   - Write for the ear, not the eye

4. Create `video_struct.yaml`, working **one story's `scene_list` at a time**
   (per the segmented approach above). Fill these fields per scene:
   - Fill NOW: `id`, `intent`, `is_aigc_scene`, `type`, `remotion_component`, `visual_content`, `data`, `text`, `workflows`, `narration.id`, `narration.content`
   - Leave EMPTY (auto-filled later): `asset_path`, `origin_asset_path`, `narration.total_frame`, `narration.audio_path`

5. **One scene = one narration:** Each scene has exactly one nested `narration`. There is no `percent` splitting — the scene occupies its whole narration duration.

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

1. Run TTS synthesis **(use `--timeout 3600` for safety — TTS may take several minutes per narration)**:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_tts.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml \
     --timeout 3600
   ```
   - `--timeout 3600` (default): per-TTS subprocess timeout (1h)
   This will:
   - Generate `speech.wav` for each scene's narration
   - **Compress WAV → MP3 (128kbps)** to reduce Remotion render memory
   - Measure audio duration via ffprobe (from WAV for accuracy)
   - Calculate `total_frame = ceil(duration × fps)`
   - Update `video_struct.yaml` `narration.audio_path` (pointing to .mp3) and `narration.total_frame`

   **Idempotent:** re-running skips narrations whose audio already exists
   (reported as `skipped`) — safe to resume after an interruption. Pass
   `--force` to regenerate ALL audio. Use `--force` after editing any
   `narration.content`, otherwise the stale audio is kept.

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

4. Use dimensions from `aigc` config:
   - Image tasks: `origin_image_width` × `origin_image_height` (default 1280×720)
   - Video tasks: `origin_video_width` × `origin_video_height` (default 1280×720)

5. Calculate `total_frame` for video tasks from the scene's narration:
   `scene_frames = narration.total_frame` (the scene owns its whole narration duration)

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

1. Run AIGC generation **(use `--total-timeout 7200` for safety — video generation may take 1-2h per task, set higher for many tasks)**:
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_aigc.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml \
     --video-tasks /abs/path/video_tasks.yaml \
     --total-timeout 7200
   ```
   - `--timeout 1800` (default): per-task subprocess timeout (30min per task)
   - `--total-timeout 7200` (default): entire script wall-clock timeout (2h). **Increase for longer videos with many tasks.**
   - Executes task groups in order, resolves `$taskN` dependencies,
     saves outputs as `origin_{scene_id}.{ext}`, and updates `origin_asset_path`.
   - **Idempotent:** tasks whose `origin_{scene_id}.{ext}` already exists
     (non-empty) are skipped (reported as `skipped`) — safe to resume after an
     interruption. Pass `--force` to re-execute ALL tasks. Use `--force` (or
     `--retry`) after editing task payloads, otherwise the stale outputs are kept.

   **Partial retry ("抽卡"):** To re-generate specific tasks (e.g., user is
   unsatisfied with a scene's result in manual mode):
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_aigc.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml \
     --video-tasks /abs/path/video_tasks.yaml \
     --retry 1,3
   ```
   - `--retry` accepts comma-separated task ordinals from video_tasks.yaml.
   - If a retried task has dependents (other tasks with `dependent_task` pointing
     to it), those dependents are **automatically included** in the retry set
     (transitive — the entire downstream chain re-executes).
   - The script deletes origin files for the retry set, then runs the normal
     pipeline. Unaffected tasks are skipped (their files still exist).
   - After retry, re-run `run_upscale.py` to regenerate upscaled assets for the
     affected scenes.

2. Run upscale (skips automatically if origin dimensions >= target):
   ```bash
   python3 "${SKILL_DIR}/scripts/tool/run_upscale.py" \
     --project-config /abs/path/project_config.yaml \
     --video-struct /abs/path/video_struct.yaml
   ```
   This upscales origin assets to target resolution, **compresses video assets
   with h264 crf 18** (significantly reduces file size for Remotion render
   without visible quality loss), and updates `asset_path`.

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

2. **Fill `remotion_data` for each scene.** The generated structure is nested:
   each `section_list` entry corresponds to one scene and its narration
   (`audio` + a single-entry `scene_list`). The script auto-populates
   `remotion_data` for AssetVideo/AssetImage and data/text scenes, but complex
   components may need enrichment. Consult the remotion-video-template README.md:

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

   **Icon field usage** — Components `FeatureGrid`, `IconCard`, `StatCounter`,
   `FlowChart` accept an `icon` field. Two formats are supported:

   | Format | Example | Description |
   |--------|---------|-------------|
   | Lucide name | `zap`, `arrow-right`, `Lightbulb`, `trending-up` | Any [Lucide icon](https://lucide.dev/icons/) name, kebab-case or PascalCase |
   | Emoji | `🚀`, `💡`, `📊` | Any emoji (≤4 chars), rendered as text |

   Commonly used icons for explainer videos:

   | Category | Icons |
   |----------|-------|
   | Tech | `cpu`, `code`, `server`, `database`, `cloud`, `wifi`, `smartphone` |
   | Data | `bar-chart`, `trending-up`, `pie-chart`, `activity`, `percent` |
   | People | `users`, `user`, `award`, `star`, `heart` |
   | Process | `zap`, `rocket`, `target`, `check-circle`, `arrow-right` |
   | Concepts | `lightbulb`, `book-open`, `globe`, `shield`, `key` |
   | Business | `dollar-sign`, `briefcase`, `shopping-cart`, `package`, `truck` |

   If an icon name is not found in Lucide, it renders as `[name]` placeholder text.

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

{Optional: key summary, e.g. "3 stories, 15 scenes (each with one narration)" or
"TTS generated 15 audio files, total duration 4:32"}

Shall I proceed to Step {N+1}: {next step name}?
```

Per-step artifact summary:

| Step | Artifacts to report |
|------|-------------------|
| 1 | `project_config.yaml`, `voice_file.wav` (if generated) |
| 2 | `video_config.yaml` (show the chosen topic) |
| 3 | `search_results/result{N}.md` (list all, count of results) |
| 4 | `video_struct.yaml` (story/scene counts; each scene = one narration) |
| 5 | `speech.wav` files (count, total duration) |
| 6 | `video_tasks.yaml` (task group count, total tasks) |
| 7 | `scenes/origin_*` + upscaled files (count) |
| 8 | `remotion_sections.yaml` (section count) |
| 9 | `result.mp4` (file size, duration) |

---

## Resuming After Interruption

> This applies only to continuing an **interrupted** pipeline for the *current*
> video request (recovery). It is NOT reuse: a brand-new video-making request
> always starts in a new `video{N}/` directory (see Step 2).

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
