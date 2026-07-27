# Theme Catalog

## Built-in themes

Located in `explainer-video-maker/themes/*.yaml`. Each theme is a partial override merged onto `project_prefs.yaml`'s `theme:` / `content:` blocks plus a `component_suggestions:` map (section-name → suggested component) and a `narrative_arc:` list hint for chapter design. All themes include a `voice_design:` block defining the narrator persona.

### Documentary & disaster

| Theme | primaryColor | accentColor | tone | voice persona |
| --- | --- | --- | --- | --- |
| `aviation-disaster` | `#b8c5d6` cool steel | `#c9303c` emergency red | serious | 沉稳严肃, authoritative |
| `history` | `#d4b483` parchment | `#8b4513` saddle brown | narrative | 温润深厚, historical gravitas |
| `crime` | `#a8b5c0` cold steel | `#c9303c` blood red | analytical | 冷静理性, detective-objective |
| `natural-disaster` | `#8ba98a` muted green | `#d97742` safety orange | serious | 沉稳坚定, firm but empathetic |

### Science & knowledge

| Theme | primaryColor | accentColor | tone | voice persona |
| --- | --- | --- | --- | --- |
| `animal-science` | `#2d8c4a` forest green | `#e8a840` warm amber | educational | 温和亲切, curious and bright |
| `life-science` | `#4a90d9` sky blue | `#e8724a` warm orange | casual | 亲切活泼, warm and approachable |
| `knowledge-sharing` | `#6c5ce7` deep purple | `#fd7e14` warm amber | educational | 亲切自然, scholarly but engaging |

### News & current events

| Theme | primaryColor | accentColor | tone | voice persona |
| --- | --- | --- | --- | --- |
| `tech-news` | `#5dade2` electric blue | `#00d4aa` neon teal | analytical | 干练专业, crisp and modern |
| `daily-news` | `#2c3e50` newspaper navy | `#c0392b` headline red | news-brief | 清晰稳重, anchor-broadcast |
| `current-affairs` | `#1a1a2e` editorial dark | `#c0392b` editorial red | serious | 沉稳有力, authoritative analyst |

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
| Wildlife, ocean life, animal behavior | animal-science |
| Everyday science, how things work, fun facts | life-science |
| General knowledge, "did you know", explainer | knowledge-sharing |
| War, dynasty, historical event, biography | history |
| Aviation accident, air crash, shipwreck | aviation-disaster |
| Murder, heist, fraud, cold case | crime |
| Earthquake, tsunami, flood, wildfire | natural-disaster |
| New product, AI breakthrough, tech trends | tech-news |
| Today's headlines, news roundup | daily-news |
| Social commentary, political analysis, hot topics | current-affairs |

For topics that cross categories, pick the dominant framing — the user's first sentence usually signals it. If unclear, ask.

## Custom per-video overrides

For one-off theme variations, create `videos/{video-name}/video_info.yaml` with a `theme:` block; it overrides project-level theme for that one video. (Not yet auto-consumed by compose_video in v1 — manually edit the generated `Video.tsx` defaults if needed. Future: compose_video reads video_info.yaml's theme block.)
