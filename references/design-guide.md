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

For a 6-minute documentary (~360s), aim for:

| Section count | Avg duration |
| --- | --- |
| 5 sections | 72s each — too long, viewers lose focus |
| 7 sections | 51s each — sweet spot |
| 10 sections | 36s each — kinetic, fast-paced |
| 15 sections | 24s each — too fragmented |

`project_prefs.content.section_count` defaults to 7. Aviation-disaster and crime topics benefit from 8-9 sections (more timeline detail); short historical vignettes can fit in 5-6.

## Density per section

| Tier | Items | Best for |
| --- | --- | --- |
| Impact | 1 (large text) | Hook, hero, summary — biggest type |
| Standard | 2-3 | Most sections — features, comparison, quote |
| Compact | 4-6 | Feature grid, ecosystem, multi-item data |
| Dense | 6+ | Data tables, detailed timelines — smallest type |

Pick by content load: a section with 8 timeline items should use `Timeline` with small text and tight spacing; a section with one big statistic should use `StatHighlight` with hero-size text.

## Documentaries-specific tips

- **Maps and locations** — for aviation disasters / wars / natural disasters, use `DiagramReveal` with positioned nodes to show geography. No dedicated map component in the template yet.
- **Photo evidence** — `AssetImage` (inline role) inside `MediaSection` for archival photos with caption.
- **Footage** — `AssetVideo` for b-roll, keep ≤10s per clip to maintain pace.
- **Quote attribution** — for famous quotes, include speaker + year. Use `QuoteBlock` with `attribution="Steve Jobs, 1996"`.
- **Sensitive content** — for casualty stats, use `StatHighlight` with a `description` field citing the source ("Source: official accident report, 1999"). Avoid sensationalized framing.

## Color palette per theme

Each theme's `primary_color` + `accent_color` pair is tuned for emotional tone:

- aviation-disaster: cool steel + emergency red — cold, urgent, technical
- history: parchment + saddle brown — warm, archival, contemplative
- crime: cold steel + blood red — dark, analytical, suspenseful
- natural-disaster: muted green + safety orange — naturalistic, alert

Don't fight the palette. If a section needs a different mood, swap the component (e.g. QuoteBlock on a somber line) rather than overriding the color.
