# Design Guide — Visual Minimums & Component Selection

## Component selection by content type

| Content type | Recommended component | Why |
| --- | --- | --- |
| Opening title / hook | `FullBleedLayout` + `MovingGradient` | Full-bleed impact, sets the tone |
| Chronological events | `Timeline` | SVG nodes + connectors draw progressively |
| Causal / process steps | `FlowChart` | Arrows show causation |
| System architecture | `DiagramReveal` | Nodes + edges, multiple layout styles |
| Comparison / before-after | `ComparisonCard` | Two-column with highlight |
| Single big stat / impact number | `StatHighlight` | One large number, label, source |
| Multiple KPIs | `MetricsRow` | 4-up dashboard |
| Bar chart / survey | `DataBar` | Animated bar fills |
| Tutorial steps / response | `StepProgress` | Numbered steps |
| Pull quote / testimony | `QuoteBlock` | Large quote + attribution |
| Feature list / grid | `FeatureGrid` / `IconCard` | Staggered entrance |
| Photo / footage frame | `MediaSection` / `AssetImage` (inline) | Caption + image |
| Background image (full bleed) | `AssetImage` (background role) | Ken Burns effect + scrim |
| B-roll video | `AssetVideo` | Offscreen video playback |

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

All content goes inside `<Scale4K orientation={...} scaleFactor={1|2}>`. The composition is designed at 1920×1080 (horizontal) or 1080×1920 (vertical); `scaleFactor=2` scales it to 4K. `ChapterProgressBar` and `<Subtitles>` render **outside** `Scale4K` so they paint at native resolution.

The generated `Video.tsx` already does this. Don't override it.

## Animation safety

| Rule | Why |
| --- | --- |
| Entrance duration ≤ 30 frames (1s) | Don't eat into content time |
| Animation disabled if `enableAnimations: false` | Accessibility / rendering speed |
| Spring presets used over custom springs | Consistency |
| Ken Burns only on background images | Inline images shouldn't move |
| Don't animate more than 4 elements in parallel | Visual overload |

## Section rhythm

For a 6-minute explainer (~360s), aim for:

| Section count | Avg duration | Best for |
| --- | --- | --- |
| 5 sections | 72s each | Deep-dive tutorials, long-form history |
| 7 sections | 51s each | Sweet spot — most explainer videos |
| 10 sections | 36s each | News briefings, fast-paced tech news |
| 15 sections | 24s each | Daily headlines (too much for educational) |

`project_prefs.content.section_count` defaults to 7. Documentary topics (aviation-disaster, crime) benefit from 8-9 sections; news briefings (daily-news) work well at 5-7; knowledge-sharing fits 6-8.

## Density per section

| Tier | Items | Best for |
| --- | --- | --- |
| Impact | 1 (large text) | Hook, hero, summary — biggest type |
| Standard | 2-3 | Most sections — features, comparison, quote |
| Compact | 4-6 | Feature grid, ecosystem, multi-item data |
| Dense | 6+ | Data tables, detailed timelines — smallest type |

Pick by content load: a section with 8 timeline items should use `Timeline` with small text and tight spacing; a section with one big statistic should use `StatHighlight` with hero-size text.

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
