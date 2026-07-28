# Design Guide — Visual Minimums & Component Selection

## Component selection by content type

Each **shot** in `narration_script.yaml` (scenes → shots) composes source material with auxiliary layers. The `component` + `asset_id` fields pick the primary layout/material; `data:` and `text:` arrays add supporting charts, stats, quotes, and bullet points; `overlays:` add transparent animation layers — all rendered inside the same shot.

### Visual components (primary layer — shot `component`)

| Content type | Recommended component | Why |
| --- | --- | --- |
| Opening title / hook | `FullBleedLayout` + `MovingGradient` | Full-bleed impact, sets the tone |
| Chronological events | `Timeline` | SVG nodes + connectors draw progressively |
| Causal / process steps | `FlowChart` | Arrows show causation |
| System architecture | `DiagramReveal` | Nodes + edges |
| Comparison / before-after | `ComparisonCard` | Two-column with highlight |
| Photo / footage frame | `MediaSection` / `AssetImage` (inline) | Caption + image |
| Background image (full bleed) | `AssetImage` (background role) | Ken Burns effect + scrim |
| B-roll video | `AssetVideo` | Offscreen video playback |
| Generic / flexible | `FullBleedLayout` or `PaddedLayout` | Use when data+text items are the main content |

### Data types (secondary layer — `data[]`)

Each entry has a `type` field that maps to a Remotion component. Data items render below the main visual with a vertical gap.

| `type` | Component | Example props |
| --- | --- | --- |
| `stat` | `StatHighlight` | `value`, `unit`, `label`, `description` |
| `bar_chart` | `DataBar` | `title`, `items: [{label, value}]` |
| `metrics` | `MetricsRow` | `title`, `metrics: [{value, label, icon}]` |
| `steps` | `StepProgress` | `title`, `steps: [{label, description}]` |
| `flow` | `FlowChart` | `title`, `steps: [{label, description, icon}]` |
| `timeline` | `Timeline` | `title`, `items: [{label, description}]` |
| `comparison` | `ComparisonCard` | `left: {title, items}`, `right: {title, items}` |

### Text types (secondary layer — `text[]`)

| `type` | Component | Example props |
| --- | --- | --- |
| `quote` | `QuoteBlock` | `quote`, `attribution` |
| `key_points` | `IconCard` list | `title`, `items: [{icon, title, description}]` |
| `callout` | `IconCard` (single) | `icon`, `text` |
| `diagram` | `DiagramReveal` | `nodes: [{id, label}]`, `edges: [{from, to}]` |

### Visual composition per theme

The theme's `visual_composition:` block suggests how to balance the four visual source types. This is a **non-binding guide** — the agent uses it when designing each section's layers in Step 4. The goal is to match the category's content characteristics: documentary categories lean on AIGC (photos are rare), news categories lean on text components (articles are the content), science categories balance all four.

| Theme | AI合成 | 素材搜索 | 数据图表 | 文本组件 | Rationale |
| --- | --- | --- | --- | --- | --- |
| `aviation-disaster` | high | low | medium | low | 事故画面稀少，以AI生成为主 |
| `history` | high | medium | medium | medium | AI还原历史场景，辅以文物图片和文献 |
| `crime` | high | low | medium | medium | 案件细节图片稀少，辅以证据链图表 |
| `natural-disaster` | medium | medium | high | low | 新闻图片可获取，数据图表为主 |
| `animal-science` | medium | high | medium | low | 野生动物图片丰富，AI用于罕见行为 |
| `life-science` | low | medium | medium | high | 文本解释为主，AI合成示意图 |
| `knowledge-sharing` | medium | medium | high | medium | 概念可视化+数据+核心观点平衡 |
| `tech-news` | low | medium | medium | high | 文本展示技术细节，AI用于概念图 |
| `daily-news` | low | high | medium | high | 新闻配图可获取，AI合成几乎不用 |
| `current-affairs` | low | high | high | high | 观点+数据+事件图片三者并重 |

## Component → props cheat sheet

Each component takes a `props` object (the Remotion Composition's defaultProps, theme-derived) plus its own props:

```tsx
<Timeline props={props} items={[
  { label: "1998", description: "Project founded" },
  { label: "2024", description: "One million users" },
]} />

<FlowChart props={props} steps={[
  { label: "Input", description: "Raw data", icon: "file-input" },
  { label: "Process", description: "Transform", icon: "cpu" },
]} />

<DataBar props={props} items={[
  { label: "Category A", value: 82 },
  { label: "Category B", value: 64 },
]} />

<QuoteBlock props={props}
  quote="Design is how it works."
  attribution="Steve Jobs" />

<StatHighlight props={props}
  value="229" unit="人"
  label="全部遇难"
  description="Source: official report" />

<AssetImage props={props} id="hero_bg" role="background" />
<AssetImage props={props} id="app_shot" role="inline" caption="Screenshot" />
```

The full prop shapes live in `remotion-video-template/src/components/*.js` — read the source for an unfamiliar component.

## Visual minimums

| Element | Minimum | Reason |
| --- | --- | --- |
| Title font size | 72px (1080p) / 144px (4k) | Legible from a distance |
| Body font size | 24px (1080p) / 48px (4k) | Readable on phones |
| Caption / footer | 18px (1080p) | Acknowledgment of source |
| Icon size | 64px | Recognizable |
| Card padding | 32-40px horizontal | Breathing room |
| Section padding | 60-120px vertical | Avoid edge-kissing |
| Vertical bottom reserved | 160px (subtitle area) | Subtitles / progress bar |

## Scale4K wrapping

All content goes inside `<Scale4K orientation={...} scaleFactor={1|2}>`. The composition is designed at 1920×1080 (horizontal) or 1080×1920 (vertical); `scaleFactor=2` scales it to 4K. The in-scene shot progress bar and `<Subtitles>` render **outside** `Scale4K` so they paint at native resolution.

The generated per-scene `scene.tsx` already does this. Don't override it.

## Animation safety

| Rule | Why |
| --- | --- |
| Entrance duration ≤ 30 frames (1s) | Don't eat into content time |
| Animation disabled if `enableAnimations: false` | Accessibility / rendering speed |
| Spring presets used over custom springs | Consistency |
| Ken Burns only on background images | Inline images shouldn't move |
| Don't animate more than 4 elements in parallel | Visual overload |

## Scene rhythm

For a 6-minute explainer (~360s), aim for:

| Scene count | Avg duration | Best for |
| --- | --- | --- |
| 5 scenes | 72s each | Deep-dive tutorials, long-form history |
| 7 scenes | 51s each | Sweet spot — most explainer videos |
| 10 scenes | 36s each | News briefings, fast-paced tech news |
| 15 scenes | 24s each | Daily headlines (too much for educational) |

`project_prefs.content.section_count` defaults to 7 (target *scene* count). Documentary topics (aviation-disaster, crime) benefit from 8-9 scenes; news briefings (daily-news) work well at 5-7; knowledge-sharing fits 6-8.

Within a scene, keep shots between ~4s and ~15s — shorter reads as a cutaway/b-roll flash, longer as a dwell on one visual.

## Density per shot

| Tier | Items | Best for |
| --- | --- | --- |
| Impact | 1 (large text) | Hook, hero, summary — biggest type |
| Standard | 2-3 | Most shots — features, comparison, quote |
| Compact | 4-6 | Feature grid, ecosystem, multi-item data |
| Dense | 6+ | Data tables, detailed timelines — smallest type |

Pick by content load: a shot with 8 timeline items should use `Timeline` with small text and tight spacing; a shot with one big statistic should use `StatHighlight` with hero-size text. If one scene's shot would land in "Dense" while its neighbor is "Impact", split or reorder so adjacent shots don't whiplash.

## Content-type tips

- **Maps and locations** — for documentaries, disasters, historical events, use `DiagramReveal` with positioned nodes to show geography. No dedicated map component in the template yet.
- **Photo / footage** — `AssetImage` (inline role) inside `MediaSection` for photos with caption. `AssetVideo` for b-roll, keep ≤10s per clip.
- **Quote attribution** — `QuoteBlock` with `attribution` field (speaker + year/context).
- **Sensitive / data-heavy content** — use `StatHighlight` with a `description` field citing sources. Avoid sensationalized framing.
- **Animal / nature behavior** — `FlowChart` for behavioral sequences, `ComparisonCard` for species comparison, `MediaSection` for habitat photos.
- **Tech demos / processes** — `StepProgress` for numbered steps, `DiagramReveal` for architecture, `ComparisonCard` for before/after.
- **News stories** — `Timeline` for unfolding events, `MetricsRow` for key numbers, `FlowChart` for causal chains.
- **Knowledge / concepts** — `SplitLayout` (concept left, visual right), `FeatureGrid` for examples, `FlowChart` for how-it-works.

## Color palette per theme

Each theme's `primary_color` + `accent_color` pair is tuned for emotional tone and content type. Full palette in [themes.md](themes.md). Key pairs:

| Theme group | Feeling |
| --- | --- |
| Documentary (aviation, history, crime, disaster) | Dark, serious, archival |
| Science & knowledge (animal, life, knowledge-sharing) | Bright, warm, approachable |
| News (tech, daily, current-affairs) | Clean, bold, modern |

Don't fight the palette. If a section needs a different mood, swap the component rather than overriding the color.
