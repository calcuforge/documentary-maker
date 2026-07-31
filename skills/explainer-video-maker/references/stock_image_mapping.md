# Stock Image Mapping (asset_generation_method: stock, type: image)

> **When to load:** Step 6 (design scene list) — **ONLY when
> `project_config.yaml` → `stock_media.search_image` is `true`** (and
> `stock_media.sources` is non-empty). If `search_image` is `false`, do NOT
> use stock images; map these intents to AIGC (`text-to-image`) instead, per
> `expression_intent_mapping.md`.

Stock images (searched from Pexels / Pixabay / Unsplash) suit scenes where the
visual is **generic and non-specific** — the narration describes a mood,
context, or real-world setting, not a precise subject that must be depicted
accurately. Stock photos are faster and cheaper than AIGC and often more
realistic for real-world imagery.

| Use a stock image when… | Use AIGC instead when… |
|------------------------|------------------------|
| Generic environment: cityscape, nature, lab interior, office | A specific historical event or person must be depicted accurately |
| Atmosphere / mood backdrop (tension, optimism, nostalgia) | The visual must match narration details precisely (specific product, data) |
| Abstract concept illustration (technology, progress, future) | Consistent character/object appearance is needed across scenes |
| Real-world photographic look | A stylized or artistic rendering is required |
| No brand-specific or copyrighted content needed | Brand-specific or fictional content |

**Component choice:**
- `AssetImage` — static photo; use when text/data overlays the image or the
  scene is very short.
- `KenBurnsImage` — photo with cinematic zoom/pan; preferred for atmosphere,
  mood, and primary-visual scenes.

**Resolution:** the search targets the project's final resolution
(`video.resolution`). If no exact match exists it downloads the largest
available and the upscale step (Step 10) enlarges it to target.

---

## Mapping by intent category

### Narrative / Atmosphere

| Expression Intent | Example | Remotion Component | Reason |
|---|---|---|---|
| Establish a scene | 1950s New York street | KenBurnsImage | Zoom out + pan on a generic cityscape establishes place cheaply. |
| Create emotional atmosphere | A city under tension before war | KenBurnsImage | Subtle zoom-in on a moody real photo builds tension. |
| Express abstract concepts | Data center, server room | KenBurnsImage (pan) | Generic tech environments are abundant in stock; no AIGC precision needed. |
| Express memories | Rural landscape, old photographs | KenBurnsImage | Ken Burns on a nostalgic stock photo is the classic documentary memory look. |

### Character / People

| Expression Intent | Example | Remotion Component | Reason |
|---|---|---|---|
| Introduce a generic role | A scientist at work, a student | AssetImage / KenBurnsImage | Non-specific people are plentiful in stock; no need to generate. |

### Concept Explanation

| Expression Intent | Example | Remotion Component | Reason |
|---|---|---|---|
| Define a concept (generic) | Cloud computing, a library | AssetImage | A representative real photo quickly establishes context. |

### News

| Expression Intent | Example | Remotion Component | Reason |
|---|---|---|---|
| Introduce background | Historical context, cityscape | KenBurnsImage / AssetImage | Stock libraries have abundant generic backgrounds; no AIGC needed. |

### Product Introduction

| Expression Intent | Example | Remotion Component | Reason |
|---|---|---|---|
| Show context / use environment | Office desk, lifestyle setting | KenBurnsImage | Generic setting shots are ideal stock material (not the specific product). |
