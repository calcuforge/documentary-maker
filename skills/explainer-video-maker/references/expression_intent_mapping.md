# AI Narration Video Production: Expression Intent Mapping

## Choosing AssetImage vs KenBurnsImage vs AssetVideo

When a scene uses a text-to-image workflow (or any static image), choose the Remotion component based on the Expression Intent:

| Intent | Component | Rationale |
|--------|-----------|-----------|
| Image is primary visual, needs cinematic feel | **KenBurnsImage** | Slow zoom/pan adds engagement without video cost |
| Image is background/atmosphere only | **KenBurnsImage** (or AssetImage) | Subtle motion enriches the backdrop |
| Heavy text/data overlay on top of image | **AssetImage** | Static image avoids distracting motion behind text |
| Image is informational (diagram, chart, screenshot) | **AssetImage** | Ken Burns motion adds no value to data |
| Quick scene, short duration | **AssetImage** | Motion may not be noticeable in very short scenes |
| Portrait / character introduction | **KenBurnsImage** (zoom="in") | Cinematic zoom draws focus to the subject |
| Product showcase, detail scanning | **KenBurnsImage** (with pan) | Pan reveals different product areas over time |

### When KenBurnsImage can replace AssetVideo

Text-to-video generation is **expensive and slow** (minutes per scene). When an Expression
Intent traditionally maps to AssetVideo, consider whether KenBurnsImage on a static
image could achieve a similar result at a fraction of the cost:

| AssetVideo scenario | Replace with KenBurnsImage? | Reasoning |
|---------------------|----------------------------|-----------|
| Establish a scene | **Yes** — `zoom="out"` + `pan` | A slow zoom out on a wide establishing shot is indistinguishable from video for many scenes |
| Create emotional atmosphere | **Yes** — `zoom="in"` | Subtle zoom on a moody image creates tension; video motion may distract |
| Express memories / nostalgia | **Yes** — `zoom="in"` | The Ken Burns "slow zoom on a photo" effect is the classic documentary look for memory sequences |
| Express abstract concepts | **Yes** — with `pan` | Symbolic imagery with slow pan feels as dynamic as video without the cost |
| Visualize future scenarios | **Maybe** — depends on scene | If the scene needs to show people moving or things happening → video; if it's a sweeping landscape/cityscape → KenBurnsImage |
| Recreate historical scenes | **No** — use AssetVideo | Historical events need people, action, and dynamic elements that a still image lacks |
| Recreate a news event | **No** — use AssetVideo | News footage needs the realism of actual motion |
| Show before-and-after changes | **No** — use AssetVideo | Transitions require multiple states; stick with video or first-last-frame workflows |
| Showcase dynamically (product) | **Maybe** — `pan` for detail | If just showing details → KenBurnsImage pan; if showing product in use → video |
| Express era transitions | **Maybe** — depends on scene | Abstract timeline transitions can use KenBurnsImage; literal transformation needs video |

**Rule of thumb**: if the scene's value comes from **atmosphere, mood, or visual context**,
KenBurnsImage is likely sufficient. If the scene's value comes from **action, movement,
or a process unfolding**, AssetVideo is necessary.

### When to use Stock Media (asset_generation_method: stock)

Stock media (searched from Pexels / Pixabay / Unsplash) is appropriate for scenes
where the visual is **generic and non-specific** — the narration describes a mood
or context, not a precise visual event. It is faster and cheaper than AIGC, and
often higher quality for real-world imagery.

| Use stock media when… | Use AIGC when… |
|----------------------|---------------|
| Generic environment: cityscape, nature, lab interior, office | Specific historical event or person must be depicted accurately |
| Atmosphere / mood backdrop (tension, optimism, nostalgia) | Visual must match narration details precisely (specific product, specific data) |
| Abstract concept illustration (technology, progress, future) | Consistent character/object appearance across multiple scenes |
| Real-world footage look (documentary B-roll feel) | Stylized or artistic rendering required |
| No brand-specific or copyrighted content needed | Brand-specific or fictional content |

**Component choice for stock assets:**
- Stock **image** → `AssetImage` (static) or `KenBurnsImage` (cinematic zoom/pan)
- Stock **video** → `AssetVideo`

**Resolution:** the search script targets the project's final resolution
(`video.resolution`). If no exact match exists, it downloads the largest
available and the upscale step (Step 10) enlarges it to target.

---

## 1. Narrative / Atmosphere

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Establish a scene | 1950s New York street | text-to-video | AssetVideo | Dynamic environments are more immersive than static images. |
| Establish a scene (still + motion) | 1950s New York street | text-to-image | KenBurnsImage | Static generation with Ken Burns (zoom out + pan) costs far less than video. |
| Establish a scene (stock) | 1950s New York street | stock search | KenBurnsImage / AssetVideo | Generic cityscape — stock photo/video is faster and more realistic than AIGC. |
| Recreate historical scenes | Ancient Egyptian pyramid construction | text-to-video | AssetVideo | Historical events require dynamic visual reconstruction. |
| Create emotional atmosphere | A city under tension before war | text-to-video | AssetVideo | Motion, lighting, and camera movement enhance emotional impact. |
| Create emotional atmosphere (still) | A city under tension before war | text-to-image | KenBurnsImage | Subtle zoom-in + pan on a moody static image builds tension. |
| Create emotional atmosphere (stock) | A city under tension before war | stock search | KenBurnsImage / AssetVideo | Real-world moody footage or photo; stock libraries have rich atmospheric content. |
| Express abstract concepts | Artificial intelligence is changing the world | text-to-image → image-to-video | AssetVideo | Abstract ideas benefit from symbolic imagery and subtle animation. |
| Express abstract concepts (stock) | Data center, server room | stock search | KenBurnsImage / AssetVideo | Generic tech environments are abundant in stock; no need for AIGC precision. |
| Visualize future scenarios | A smart city in 2050 | text-to-image → image-to-video | AssetVideo | Future concepts require creative generation with cinematic motion. |
| Express era transitions | Agricultural age to industrial age | text-to-video | AssetVideo | Long-term evolution is best represented through animated scenes. |
| Show before-and-after changes | City before and after renovation | image-edit → first-last-frame-to-video | AssetVideo | Explicit start and end states make transition animation natural. |
| Express memories | Childhood rural life | text-to-video | AssetVideo | Video better conveys nostalgia and emotional storytelling. |
| Express memories (stock) | Rural landscape, old photographs | stock search | KenBurnsImage | Ken Burns on a nostalgic stock photo is the classic documentary memory look. |

---

## 2. Character / People

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Introduce a person | Who is Steve Jobs | text-to-image | AssetImage | A portrait provides the clearest visual introduction. |
| Introduce a person (cinematic) | Who is Steve Jobs | text-to-image | KenBurnsImage | Slow zoom-in on portrait creates a dramatic, documentary feel. |
| Show personal journey | From startup failure to success | - | Timeline | Personal growth is naturally represented chronologically. |
| Present a quotation | "Innovation comes from different ideas." | - | QuoteBlock | Quotes deserve visual emphasis and attribution. |
| Summarize achievements | Three major contributions | - | IconCard | Key achievements are easy to scan as individual cards. |
| Compare two people | Steve Jobs vs Bill Gates | - | ComparisonCard | Side-by-side comparison highlights differences clearly. |
| Show relationship network | Collaboration between scientists | - | DiagramReveal | Network diagrams effectively visualize relationships. |

---

## 3. Concept Explanation

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Define a concept | What is quantum computing? | text-to-image | AssetImage | A representative illustration quickly establishes context. |
| Show key features | Three advantages of AI | - | FeatureGrid | Feature grids organize parallel information effectively. |
| Highlight key points | Five renewable energy trends | - | IconCard | Bullet-style cards improve readability. |
| Show system structure | Components of a computer | - | DiagramReveal | Structural relationships are best shown as diagrams. |
| Explain a mechanism | How an engine works | - | AnimationDemo | Animated demonstrations simplify complex mechanisms. |
| Show a workflow | AI model training pipeline | - | FlowChart | Sequential processes are naturally represented as flowcharts. |
| Show categories | Types of AI | - | FeatureGrid | Categories are easy to compare in a grid layout. |
| Show hierarchy | Internet technology architecture | - | DiagramReveal | Hierarchical structures benefit from node diagrams. |

---

## 4. Data / Facts

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Highlight a metric | 1 billion users | - | StatCounter | Animated counters emphasize important numbers. |
| Show growth trend | Market grew by 300% | - | DataBar | Animated bars make trends immediately visible. |
| Show rankings | Top 5 brands | - | DataTable | Rankings are easiest to read in tabular form. |
| Show specifications | CPU / RAM / Battery | - | DataTable | Technical parameters require structured presentation. |
| Show proportions | Energy mix | - | DataBar | Relative values are easy to compare visually. |
| Highlight statistics | 95% customer satisfaction | - | StatCounter | Large animated numbers attract attention. |
| Show yearly evolution | Company history over 20 years | - | Timeline | Time-based data belongs on a timeline. |

---

## 5. News

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Recreate a news event | Rocket launch | text-to-video | AssetVideo | Dynamic footage increases realism. |
| Recreate a news event (stock) | Rocket launch, city skyline | stock search | AssetVideo | Stock news/B-roll footage is realistic and free; ideal for generic events. |
| Introduce background | Historical context | text-to-image | AssetImage | Background information usually requires only a representative image. |
| Introduce background (cinematic) | Historical context | text-to-image | KenBurnsImage | Slow zoom out reveals the wider context; pan moves across a scene. |
| Introduce background (stock) | Historical context, cityscape | stock search | KenBurnsImage / AssetVideo | Stock libraries have abundant generic backgrounds; no AIGC needed. |
| Show event timeline | Development of the incident | - | Timeline | News events naturally follow chronological order. |
| Explain impact | Impact on supply chain | - | FlowChart | Cause-and-effect relationships are clearly visualized. |
| Present expert opinions | Expert quotes | - | QuoteBlock | Quotations highlight authority and credibility. |
| Show statistics | GDP growth | - | DataBar | Quantitative information is best shown visually. |

---

## 6. Product Introduction

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Showcase appearance | Smartphone design | text-to-image | AssetImage | Static product images clearly display appearance. |
| Scan product details | Smartphone design, detail view | text-to-image | KenBurnsImage | Ken Burns pan slowly reveals different product areas. |
| Showcase dynamically | 360° product rotation | text-to-image → image-to-video | AssetVideo | Motion better demonstrates product design. |
| Present selling points | Three core features | - | FeatureGrid | Features are easy to compare side by side. |
| List functions | Fast charging, waterproof | - | IconCard | Icon-based cards improve readability. |
| Compare products | iPhone vs Android | - | ComparisonCard | Comparison layouts simplify decision making. |
| Explain technology | Chip architecture | - | AnimationDemo | Animation clarifies technical principles. |
| Show user workflow | Product setup process | - | FlowChart | Step-by-step guidance fits a workflow diagram. |

---

## 7. Tutorials / Education

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Demonstrate steps | Register an account | - | FlowChart | Procedures are naturally sequential. |
| Demonstrate an experiment | Volcano simulation | - | AnimationDemo | Animation effectively illustrates dynamic processes. |
| Show source code | Python example | - | CodeBlock | Preserves syntax and readability. |
| Explain an algorithm | Machine learning workflow | - | FlowChart | Algorithms are process-oriented. |
| Show architecture | Cloud computing architecture | - | DiagramReveal | Architecture is best communicated visually. |
| Summarize knowledge | Three key takeaways | - | IconCard | Summary cards improve retention. |

---

## 8. Software Engineering

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Display code | REST API example | - | CodeBlock | Source code requires monospace formatting. |
| Show execution | Program execution | - | AnimationDemo | Execution flow is easier to understand dynamically. |
| Show architecture | Microservices | - | DiagramReveal | Node diagrams communicate architecture clearly. |
| Explain API flow | Request lifecycle | - | FlowChart | API interactions follow a sequential flow. |
| Show version history | Software evolution | - | Timeline | Version changes are chronological. |
| Highlight performance | 10× QPS improvement | - | StatCounter | Key metrics deserve numerical emphasis. |

---

## 9. Opinion / Commentary

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Highlight an opinion | The future belongs to AI | - | QuoteBlock | Important statements should stand out visually. |
| Summarize trends | Three future trends | - | IconCard | Trends are easy to digest as key points. |
| Compare viewpoints | Pros vs Cons | - | ComparisonCard | Contrasting ideas are clearer side by side. |
| Explain reasoning | Why renewable energy matters | - | FlowChart | Logical reasoning follows a causal flow. |
| Support with data | User growth statistics | - | DataBar | Data strengthens arguments visually. |

---

## 10. History / Timeline

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Show historical stages | 30 years of the Internet | - | Timeline | Historical progression is inherently chronological. |
| Show product evolution | iPhone generations | - | Timeline | Product iterations are timeline-based. |
| Show technology evolution | Semiconductor roadmap | - | Timeline | Technology development unfolds over time. |
| Show transformation | Building renovation | image-edit → first-last-frame-to-video | AssetVideo | Transformation is best shown through animated transitions. |

---

## 11. Relationships / Structure

| Expression Intent | Example | Workflow Type | Remotion Component | Reason |
|---|---|---|---|---|
| Show organization | Company structure | - | DiagramReveal | Organizational hierarchies are graph structures. |
| Show industry chain | Automotive supply chain | - | FlowChart | Supply chains follow directional flows. |
| Show ecosystem | AI ecosystem | - | DiagramReveal | Ecosystems contain interconnected entities. |
| Show causality | Causes of an economic crisis | - | FlowChart | Cause-and-effect relationships are sequential. |
| Show decision path | Customer purchase journey | - | FlowChart | Decision making follows a stepwise process. |