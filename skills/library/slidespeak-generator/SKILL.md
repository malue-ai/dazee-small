---
name: slidespeak-generator
description: Generate professional presentations using SlideSpeak API with rich layouts and automatic content formatting
priority: high
---

# SlideSpeak Presentation Generator

Generate high-quality presentations programmatically using SlideSpeak's slide-by-slide API.

**API Documentation**: https://docs.slidespeak.co/basics/api-references/slide-by-slide/

## API Specification Summary

### Endpoint
```
POST https://api.slidespeak.co/api/v1/presentation/generate/slide-by-slide
```

### Required Fields

**Top-level**:
- `template`: string - Template name (e.g., "DEFAULT")
- `slides`: array - List of slide configurations

**Per slide**:
- `title`: string - Slide title
- `layout` OR `layout_name`: string - Layout type (mutually exclusive)
- `item_amount`: integer - Number of items (must match layout constraints)
- `content`: string - Slide content

### Optional Fields

**Top-level**:
- `language`: string (default: "ORIGINAL")
- `fetch_images`: boolean (default: true)
- `verbosity`: "concise" | "standard" | "text-heavy" (default: "standard")
- `include_cover`: boolean (default: true)
- `include_table_of_contents`: boolean (default: true)
- `add_speaker_notes`: boolean (default: false)

**Per slide**:
- `images`: array of {type: "url"|"stock"|"ai", data: string}
- `chart`: object - Chart configuration (for CHART layout)
- `table`: string[][] - Table data (for TABLE layout)

### Layout Constraints (Official API Requirements)

**From API documentation**:
> The `item_amount` parameter must respect the item range constraints for each layout type.

**Fixed item_amount requirements**:
- `comparison`: exactly **2** items
- `swot`: exactly **4** items
- `pestel`: exactly **6** items
- `thanks`: **0** items

**Other layouts**: Use appropriate item_amount based on your content needs.

### Official Example

See the [official API documentation](https://docs.slidespeak.co/basics/api-references/slide-by-slide/#example-body) for complete examples including:
- ITEMS layout (wildlife presentation)
- TIMELINE layout (conservation timeline)
- COMPARISON layout (threats vs solutions)
- BIG_NUMBER layout (key statistics)
- TABLE layout (regional KPIs)

## Usage Approach

**Generate intelligent, high-quality presentations**:

1. **Understand user requirements** - What topic, how many slides, what style
2. **Gather rich content** - Use web_search or knowledge to collect detailed information
3. **Select appropriate layouts** - Match content type to layout (data→BIG_NUMBER, comparison→COMPARISON, etc.)
4. **Generate configuration** - Create well-structured JSON following API spec
5. **Call the tool** - `slidespeak_render(config=your_config)`

**Key principles**:
- Let your reasoning guide layout selection
- Create rich, professional content
- Respect the 4 fixed item_amount constraints (comparison=2, swot=4, pestel=6, thanks=0)
- Use images, charts, tables when appropriate

## Helper Resources

If you want to programmatically build configurations:

```bash
# View full API schema
cat agent_v3/skills/library/slidespeak-generator/resources/api_schema.json

# Use config builder (optional)
cd agent_v3/skills/library/slidespeak-generator
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
                "content": "核心功能1 核心功能2 核心功能3 技术优势"
            },
            {
                "title": "市场对比",
                "layout": "COMPARISON",
                "item_amount": 2,  # Must be exactly 2
                "content": "我们的产品优势 竞品的不足"
            },
            # ... more slides
        ]
    },
    save_dir="./outputs/ppt"
)
```

## Success Criteria

- Configuration follows official API specification
- Fixed item_amount constraints are respected
- Content is rich and professional
- Layout selection matches content type
- Presentation tells a compelling story

**Focus on quality content generation.**
