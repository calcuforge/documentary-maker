# Workflow Steps — Production Phase (Steps 8–11)

> **When to load:** Step 8 through Step 11 — AIGC prompt design, task execution,
> upscale, Remotion config generation, and final render. Also includes step
> completion reporting and resumption logic.

**Prerequisite:** [workflow-content.md](workflow-content.md) Steps 5–7 must be
complete (all narration audio generated, `total_frame` fields populated).

---

## Step 8: Design AIGC Prompts and Plan Tasks

**When:** After TTS is complete and frames are calculated.

This step has two parts: **8a** designs structured video prompts (saved per
scene), and **8b** plans the AIGC tasks in `video_tasks.yaml` using those prompts.

### Step 8a — Design Structured Video Prompts

1. Review `video_struct.yaml` — identify all scenes where `is_aigc_scene: true`.
   For each AIGC scene, based on its `intent` and `visual_content`, design a
   structured video prompt and save it to
   `stories/{story_id}/{narration_id}/scenes/video_prompt.yaml`:

   ```yaml
   video_prompt:
     type: text_to_video  # text_to_video / image_to_video / text_to_image
     common:
       subject:    {main: "...", description: "..."}
       scene:      {location: "...", environment: "..."}
       time:       {period: "...", lighting: "..."}
       style:      {visual: "...", color: "...", quality: "..."}
       action:     {description: "..."}
       camera:     {shot: "...", movement: "...", angle: "..."}
     text_to_video:
       prompt: "<one-sentence prompt>"
       negative: ["term1", "term2"]
     image_to_video:
       motion:
         type: camera_and_object_motion
         camera: {movement: "..."}
         object: {movement: "..."}
     text_to_image:
       prompt: "<one-sentence prompt>"
       negative: ["term1", "term2"]
   ```

   - For video scenes (`type: video`): include both `text_to_video` and
     `image_to_video` sections (one prompt file covers both workflow tasks).
   - For image scenes (`type: image`): include only the `text_to_image` section.
   - **Before choosing `type: video`:** text-to-video generation is slow and
     expensive. Evaluate whether the scene truly needs action/motion, or whether
     atmosphere/mood is the goal. If atmosphere suffices, use `type: image` +
     `KenBurnsImage` component instead — a static image with Ken Burns zoom/pan
     achieves cinematic feel at far lower cost. See
     `expression_intent_mapping.md` for a per-scenario substitution table.
   - Work **one story at a time** (consistent with Steps 5-6).

2. **Cross-scene consistency — recurring subjects.** Before writing any prompt
   files, scan ALL scenes across ALL stories to identify subjects that appear
   more than once: recurring characters (e.g., "Einstein"), specific objects
   (e.g., "a red 1965 Ford Mustang"), branded items, or consistent environments
   (e.g., "a 1950s New York street"). For each recurring subject, write ONE
   canonical `common.subject.description` and `common.style` block, then reuse
   it **verbatim** across all scenes where that subject appears. Do NOT rephrase
   or vary the wording — even small differences cause ComfyUI to produce
   visually inconsistent outputs. This is mandatory for generated imagery; AIGC
   models have no persistent identity across independent generations, so prompt
   consistency is the only mechanism to approximate visual continuity.

### Step 8b — Plan AIGC Tasks

1. **Plan tasks one story at a time** — do NOT plan all stories' tasks in a
   single pass. For the current story, identify its AIGC scenes, generate their
   prompts, and append the tasks to `video_tasks.yaml`.

2. For each AIGC scene in the current story:
   - **Generate the flat prompt** by calling `build_video_prompt.py` on the
     scene's `video_prompt.yaml` (call once per task type for scenes with both
     t2v and i2v tasks):
     ```bash
     python3 "${SKILL_DIR}/scripts/tool/build_video_prompt.py" \
       --prompt-yaml /abs/path/to/video_prompt.yaml --type text_to_video
     ```
     Use the output `data.prompt` in the task payload's `prompt` field.
   - **Workflow pipeline:** Choose from available workflows (see `comfyui-scheduler/doc/workflow.md`):
     - `z_image_fp16` — text-to-image
     - `ltx2.3_t2v_int8` — text-to-video
     - `ltx2.3_i2v_int8` — image-to-video
     - `ltx2.3_flf2v_int8` — first-last-frame-to-video
     - `qwen_image_edit_2511_int8_step4` — image-to-image
   - **Dependencies:** e.g., text-to-image → image-to-video (two groups)

3. Append the current story's tasks to `video_tasks.yaml`:
   - **Group by `workflow_code`** — tasks are organized by workflow and shared
     across stories. Append this story's tasks to the matching group (create the
     group the first time a `workflow_code` appears). Groups that others depend
     on go first (`task_group_ordinal`).
   - **Global ordinals** — keep one continuous `ordinal` counter across all
     stories; do NOT restart it per story.
   - Use `$taskN` in a payload to reference a dependent task's output (a scene's
     image-to-video task depends on its own text-to-image task).
   - Use dimensions from `aigc` config:
     - Image tasks: `origin_image_width` × `origin_image_height` (default 1280×720)
     - Video tasks: `origin_video_width` × `origin_video_height` (default 1280×720)
   - Calculate `total_frame` for video tasks from the scene's narration:
     `scene_frames = narration.total_frame` (the scene owns its whole narration duration).

4. Repeat for every story until all AIGC tasks are in `video_tasks.yaml`.

5. **Reference:** [demo_projects/project1/video1/video_tasks.yaml](demo_projects/project1/video1/video_tasks.yaml)

6. **Validate:**
   ```bash
   python3 "${SKILL_DIR}/scripts/verify/verify_video_tasks.py" \
     --video-tasks /abs/path/video_tasks.yaml \
     --video-struct /abs/path/video_struct.yaml
   ```

---

## Step 9: Execute AIGC Tasks

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

## Step 10: Generate Remotion Rendering Config

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
   | KenBurnsImage | `src`, `role`, `zoom` (in/out/none), `pan` (left/right/up/down/up-left/up-right/down-left/down-right/none), `caption`, `dim`, `totalFrame` |

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

## Step 11: Render Video

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
   Rendering is **segmented**: the video is split into frame-range segments
   (default 600 frames each), rendered in parallel, then concatenated with
   ffmpeg. The number of concurrent segment workers is **auto-sized from the CPU
   count** — inside a container the cgroup v2 CPU limit is read, so rendering
   stays within the container's quota (per-render concurrency is scaled to
   match). This is all automatic; override via `render.segment_frames` /
   `render.segment_workers` in project_config.yaml only if needed.

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
| 4 | `video_struct.yaml` (story count — chapter list) |
| 5 | `stories/{story_id}/script.md` (count; each meets `min_story_chars`) |
| 6 | `video_struct.yaml` (scene count; each scene = one narration) |
| 7 | `speech.wav` files (count, total duration) |
| 8 | `video_tasks.yaml` (task group count, total tasks) |
| 9 | `scenes/origin_*` + upscaled files (count) |
| 10 | `remotion_sections.yaml` (section count) |
| 11 | `result.mp4` (file size, duration) |

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
| + `search_results/` | Step 4 (design chapters) |
| + `video_struct.yaml` (chapters only, no scripts) | Step 5 (write scripts) |
| + `stories/*/script.md` (scripts, no scenes yet) | Step 6 (design scenes) |
| + `video_struct.yaml` (full scenes, no audio) | Step 7 (TTS) |
| + audio files + frames set | Step 8 (plan AIGC) |
| + `video_tasks.yaml` | Step 9 (execute AIGC) |
| + `scenes/` with assets | Step 10 (generate remotion) |
| + `remotion_sections.yaml` | Step 11 (render) |
