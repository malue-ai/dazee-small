---
name: slidespeak-generator
description: Generate professional presentations using SlideSpeak API with rich layouts and automatic content formatting
priority: high
---

# SlideSpeak Presentation Generator

Generate high-quality presentations programmatically using SlideSpeak's slide-by-slide API.

**API Documentation**: [https://docs.slidespeak.co/basics/api-references/slide-by-slide/](https://docs.slidespeak.co/basics/api-references/slide-by-slide/)

## API Specification Summary

### Endpoint

```
POST https://api.slidespeak.co/api/v1/presentation/generate/slide-by-slide
```

### Required Fields

**Top-level**:

* `template`: string - Template name (e.g., "DEFAULT")
* `slides`: array - List of slide configurations

**Per slide**:

* `title`: string - Slide title
* `layout` OR `layout_name`: string - Layout type (mutually exclusive)
* `item_amount`: integer - Number of items (must match layout constraints)
* `content`: string - Slide content

### Optional Fields

**Top-level**:

* `language`: string (default: "ORIGINAL")
* `fetch_images`: boolean (default: true)
* `verbosity`: "concise" | "standard" | "text-heavy" (default: "standard")
* `include_cover`: boolean (default: true)
* `include_table_of_contents`: boolean (default: true)
* `add_speaker_notes`: boolean (default: false)

**Per slide**:

* `images`: array of {type: "url"|"stock"|"ai", data: string}
* `chart`: object - Chart configuration (for CHART layout)
* `table`: string[][] - Table data (for TABLE layout)

### Layout Constraints (Official API Requirements)

**From API documentation**:

> The `item_amount` parameter must respect the item range constraints for each layout type.

**Fixed item_amount requirements**:

* `comparison`: exactly **2** items
* `swot`: exactly **4** items
* `pestel`: exactly **6** items
* `thanks`: **0** items

**Other layouts**: Use appropriate item_amount based on your content needs.

### Official Example

See the [official API documentation](https://docs.slidespeak.co/basics/api-references/slide-by-slide/#example-body) for complete examples including:

* ITEMS layout (wildlife presentation)
* TIMELINE layout (conservation timeline)
* COMPARISON layout (threats vs solutions)
* BIG_NUMBER layout (key statistics)
* TABLE layout (regional KPIs)

## Usage Approach

**Generate intelligent, high-quality presentations**:

1. **Understand user requirements** - What topic, how many slides, what style
2. **Gather rich content** - Use web_search or knowledge to collect detailed information
3. **Select appropriate layouts** - Match content type to layout (data→BIG_NUMBER, comparison→COMPARISON, etc.)
4. **Generate configuration** - Create well-structured JSON following API spec
5. **Call the tool** - `slidespeak_render(config=your_config)`

**Layout selection heuristics** (keep it flexible, but consistent):

* **ITEMS**: Use when you have parallel points of the same “level” (features, benefits, principles, checklist). It’s the safest default.
* **COMPARISON**: Use when the slide naturally splits into two sides (Before vs After / Problem vs Solution / Us vs Alternatives / Option A vs B). Ensure both sides have a clear label and comparable density.
* **BIG_NUMBER**: Use when you can express outcomes as KPIs, milestones, targets, or headline metrics (even ranges/goals are better than vague adjectives).
* **TIMELINE**: Use for phased execution, roadmap, rollout, milestones. Each phase should have an action + an output (what is done + what you get).
* **SWOT**: Use for structured risk/strategy review (market entry, product strategy, competitive context). Keep all quadrants at similar granularity.
* **TABLE**: Use when the content is inherently row/column aligned (region × KPI, plan × cost, tier × feature). Avoid forcing table-ish data into ITEMS.
* **CHART** (optional): Use for trend/share/distribution when you can provide dimensions and rough values/relationships.

Fallback rule:

* If the content doesn’t really fit a specialized layout, **degrade to ITEMS** rather than forcing it.

**Key principles**:

* Let your reasoning guide layout selection
* Create rich, professional content
* Respect the 4 fixed item_amount constraints (comparison=2, swot=4, pestel=6, thanks=0)
* Use images, charts, tables when appropriate

**Content formatting heuristics** (aim for “PPT-friendly inputs”, not essays):

* Prefer **labelled chunks** over prose: `Label: point, point, point.` is easier to format into bullets.
* Keep a slide **single-topic**: one slide = one message, supporting points only.
* Maintain **consistent granularity** within a slide: don’t mix strategy-level bullets with low-level implementation details in the same list.
* Add at least one “anchor” when natural: a number/time/comparison/constraint/actionable mechanism (helps the slide look credible).
* Avoid empty hype words: “revolutionary / disruptive / ultimate” tends to lower perceived professionalism.
* If `fetch_images` is true, include **concrete nouns** (scenes, industries, objects) so image selection has semantic anchors.

## Helper Resources

If you want to programmatically build configurations:

```bash
# View full API schema
cat /skills/library/slidespeak-generator/resources/api_schema.json

# Use config builder (optional)
cd /skills/library/slidespeak-generator
python3 scripts/config_builder.py '{"topic": "Product Demo", "pages": 8}'
```

## Tool Call Format

```python
slidespeak_render(
    config={
        "template": "DEFAULT",
        "language": "ORIGINAL",  # or "ENGLISH", "CHINESE"
        "fetch_images": True,
        "slides": [
            {
                "title": "产品概述",
                "layout": "ITEMS",
                "item_amount": 4,
                "content": "核心功能1: 一句话说明, 一句话补充. 核心功能2: ... 核心功能3: ... 技术优势: ..."
            },
            {
                "title": "市场对比",
                "layout": "COMPARISON",
                "item_amount": 2,  # Must be exactly 2
                "content": "传统方案: 痛点1, 痛点2, 痛点3. 我们方案: 优势1, 优势2, 优势3."
            },
            # ... more slides
        ]
    },
    save_dir="./outputs/ppt"
)
```

## Success Criteria

* Configuration follows official API specification
* Fixed item_amount constraints are respected
* Content is rich and professional
* Layout selection matches content type
* Presentation tells a compelling story

Quality self-check (lightweight, not rigid):

* Each slide’s content can be **visually separated** according to its layout (two sides for comparison, four buckets for SWOT, phases for timeline).
* Bullet candidates read like **talking points**, not paragraphs.
* Across the deck, the narrative roughly covers: **context/problem → approach → mechanism → value → evidence/metrics → plan/next steps** (as applicable).

**Focus on quality content generation.**
