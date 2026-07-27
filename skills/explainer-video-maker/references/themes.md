# Theme Catalog

## Built-in themes

Located in `explainer-video-maker/themes/*.yaml`. Each theme is a partial override merged onto `project_prefs.yaml`'s `theme:` / `content:` blocks plus a `component_suggestions:` map (section-name → suggested component) and a `narrative_arc:` list hint for chapter design.

| Theme | primaryColor | accentColor | tone | narrative arc |
| --- | --- | --- | --- | --- |
| `aviation-disaster` | `#b8c5d6` cool steel | `#c9303c` emergency red | serious | hook → background → event_timeline → cause_analysis → impact → aftermath → conclusion |
| `history` | `#d4b483` parchment | `#8b4513` saddle brown | narrative | hook → context → rise → climax → turning_point → legacy → conclusion |
| `crime` | `#a8b5c0` cold steel | `#c9303c` blood red | analytical | hook → crime_scene → background → investigation → trial → aftermath → conclusion |
| `natural-disaster` | `#8ba98a` muted green | `#d97742` safety orange | serious | hook → context → event_timeline → impact → cause_analysis → response → aftermath → conclusion |

## How themes apply

1. `cli.py project create --category <name>` sets `project.category` in `project_prefs.yaml`.
2. `scripts/compose_video.py` deep-merges `themes/<category>.yaml` onto the project prefs (theme fields override project prefs' theme block; explicit project prefs win over theme defaults).
3. Merged `theme.*` fields become the Remotion Composition's `defaultProps` (primaryColor, backgroundColor, etc.).
4. `component_suggestions` is a hint — the chapter designer reads it to suggest components per section name; `narration_script.yaml`'s `visual.component` is the final authority.
5. `narrative_arc` is a hint for Step 3 (chapter design) — the designer follows it unless the topic demands otherwise.

## Override precedence

Project prefs (explicit fields) > theme preset > defaults.

Example: project prefs set `theme.primary_color: "#1a2a3a"` and category=aviation-disaster. Theme aviation-disaster says `primary_color: "#b8c5d6"`. Final value: `#1a2a3a` (project prefs win).

To use a theme's color entirely, delete the explicit `theme.*` field from `project_prefs.yaml` (or set it to null).

## Adding a new theme

1. Create `themes/<new-name>.yaml` with the same shape as existing themes:

   ```yaml
   theme:
     primary_color: "#..."
     background_color: "#..."
     text_color: "#..."
     accent_color: "#..."
     transition_type: fade
     transition_duration: 18
   content:
     tone: serious | narrative | analytical
   component_suggestions:
     hero: FullBleedLayout
     overview: IconCard
     # ...
   narrative_arc:
     - hook
     - ...
     - conclusion
   ```

2. Add a trigger keyword mapping in `project_prefs.template.yaml` `triggers.keywords`:

   ```yaml
   triggers:
     keywords:
       <new-name>: ["关键词1", "关键词2"]
   ```

3. Update the SKILL.md description and the frontmatter trigger keywords.

4. (Optional) Add the theme to `check_prereqs.py`'s category choices list — currently just informational.

5. Test: `cli.py themes list` should show the new theme.

## Choosing a theme for a topic

| Topic pattern | Recommended theme |
| --- | --- |
| Aviation accident, air crash | aviation-disaster |
| Earthquake, tsunami, flood, wildfire | natural-disaster |
| Murder, heist, fraud, true crime | crime |
| War, dynasty, historical event, biography | history |

For topics that genuinely cross categories (e.g. a disaster caused by criminal negligence), pick the dominant framing — the user's first sentence usually signals it. If unclear, ask.

## Custom per-video overrides

For one-off theme variations, create `videos/{video-name}/video_info.yaml` with a `theme:` block; it overrides project-level theme for that one video. (Not yet auto-consumed by compose_video in v1 — manually edit the generated `Video.tsx` defaults if needed. Future: compose_video reads video_info.yaml's theme block.)
