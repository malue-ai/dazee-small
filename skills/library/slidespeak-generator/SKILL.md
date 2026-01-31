---
name: slidespeak-generator
description: |
  Guides the creation of professional business presentations with proper structure, 
  visual design, and content organization. This Skill provides best practices for:
  
  - Executive presentations and board decks (高管演示、董事会汇报)
  - Product demonstrations and launches (产品演示、发布会)
  - Business reviews and quarterly reports (业务回顾、季度报告)
  - Client-facing proposals and pitches (客户提案、商务演讲)
  - Internal training and onboarding materials (内部培训、入职材料)
  
  The Skill covers slide structure, content hierarchy, visual consistency, 
  data visualization principles, and storytelling techniques for impactful presentations.
  
priority: high
references_tools:
  - slidespeak_render  # 实际执行PPT生成的工具
  - web_search  # 用于收集内容素材
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
2. **Expand and enrich content** - Transform user's brief input into detailed, professional content
3. **Gather supporting information** - Use web_search when needed for facts, data, examples
4. **Select appropriate layouts** - Match content type to layout (data→BIG_NUMBER, comparison→COMPARISON, etc.)
5. **Generate configuration** - Create well-structured JSON following API spec
6. **Call the tool** - `slidespeak_render(config=your_config)` with `fetch_images: false` (default)

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
* Create rich, professional content with depth and substance
* Respect the 4 fixed item_amount constraints (comparison=2, swot=4, pestel=6, thanks=0)
* **Default to `fetch_images: false`** - Focus on strong content instead of relying on images
* Use charts and tables for data visualization when appropriate
* Expand user's brief inputs into comprehensive, well-structured content

## Content Expansion Strategy

**Transform brief user input into comprehensive, professional content**:

### 1. Content Enrichment Principles

* **Expand each concept**: User says "AI应用" → Expand to "AI应用：智能推荐系统提升用户转化率30%，自然语言处理实现客服自动化，计算机视觉赋能质量检测"
* **Add concrete examples**: Instead of "提高效率" → "提高效率：自动化流程减少人工操作80%，实时数据分析支持快速决策，智能调度优化资源利用率"
* **Include data/metrics**: Add numbers, percentages, timeframes to make content credible
* **Provide context**: Explain WHY something matters before listing WHAT it is
* **Use the Rule of 3**: Present 3-4 supporting points for each main idea

### 2. Professional PPT Design Guidelines

**Content Structure** (优秀PPT的黄金法则):

* **Progressive disclosure**: Start with big picture, then dive into details across slides
* **Problem → Solution flow**: Establish pain points before presenting solutions
* **Evidence-based**: Back claims with data, case studies, or specific examples
* **Action-oriented**: Each slide should drive toward a decision or next step

**Writing Style**:

* **Concise but complete**: 1-2 sentences per bullet, each sentence adds value
* **Active voice**: "AI提升效率40%" not "效率被AI提升了"
* **Specific over vague**: "降低成本200万元/年" not "大幅降低成本"
* **Parallel structure**: Keep similar items in similar grammatical form

**Visual Hierarchy**:

* **One core message per slide**: Title should reveal the conclusion
* **3-5 bullets maximum**: More than 5 items? Split into multiple slides or use table
* **Layered information**: Main point (bold/emphasized) → Supporting detail → Example

### 3. Content Formatting Heuristics

**Aim for "PPT-friendly inputs", not essays**:

* Prefer **labelled chunks** over prose: `Label: point, point, point.` is easier to format into bullets
* Keep a slide **single-topic**: one slide = one message, supporting points only
* Maintain **consistent granularity** within a slide: don't mix strategy-level bullets with low-level implementation details in the same list
* Add at least one "anchor" when natural: a number/time/comparison/constraint/actionable mechanism (helps the slide look credible)
* Avoid empty hype words: "revolutionary / disruptive / ultimate" tends to lower perceived professionalism
* **No images by default**: Let content stand on its own merit. Only suggest images if they're truly essential to understanding

### 4. Content Generation Examples

**❌ Weak (too brief)**:
```
Title: "产品特点"
Content: "功能强大. 易于使用. 性价比高."
```

**✅ Strong (expanded & detailed)**:
```
Title: "核心竞争优势"
Content: "技术领先：采用最新GPT-4架构，响应速度提升3倍，准确率达98%. 用户友好：零代码配置界面，10分钟即可上手，支持20+语言. 成本优势：按量计费模式，中小企业月均节省5000元，提供免费试用期."
```

**❌ Weak (generic)**:
```
Title: "市场机会"
Content: "市场规模大. 增长快. 竞争少."
```

**✅ Strong (specific & data-driven)**:
```
Title: "千亿市场蓝海"
Content: "市场规模：国内企业级AI市场2024年达1200亿元，年复合增长率35%. 需求缺口：85%的中小企业仍依赖传统软件，急需智能化升级. 竞争态势：头部玩家聚焦大客户，中小企业市场渗透率不足15%，存在显著机会窗口."
```

## Helper Resources

If you want to programmatically build configurations:

```bash
# View full API schema
cat /skills/library/library/slidespeak-generator/resources/api_schema.json

# Use config builder (optional)
cd /skills/library/library/slidespeak-generator
python3 scripts/config_builder.py '{"topic": "Product Demo", "pages": 8}'
```

## Tool Call Format

```python
slidespeak_render(
    config={
        "template": "DEFAULT",
        "language": "ORIGINAL",  # or "ENGLISH", "CHINESE"
        "fetch_images": False,  # ✅ Default: Focus on content, not images
        "verbosity": "text-heavy",  # Use detailed content mode
        "slides": [
            {
                "title": "核心产品能力",
                "layout": "ITEMS",
                "item_amount": 4,
                "content": "智能分析引擎：基于深度学习的实时数据处理，支持百万级并发，毫秒级响应. 多场景适配：覆盖电商、金融、教育等15个行业，提供开箱即用的预训练模型. 安全合规：通过ISO27001认证，支持私有化部署，数据100%本地存储. 灵活集成：提供REST API和SDK，支持主流开发语言，平均接入时间2天."
            },
            {
                "title": "方案对比优势",
                "layout": "COMPARISON",
                "item_amount": 2,  # Must be exactly 2
                "content": "传统SaaS方案：功能标准化无法定制，数据存储在公有云存在合规风险，按座位数收费成本高昂，平均月费800元/人. 我们的方案：支持深度定制满足特殊需求，私有化部署保障数据安全，按调用量灵活计费，中小企业月均节省60%成本."
            },
            {
                "title": "客户成功案例",
                "layout": "BIG_NUMBER",
                "item_amount": 3,
                "content": "效率提升 85%：某电商客户自动化处理订单，人力成本从50人降至8人. 营收增长 120%：某教育平台个性化推荐，用户转化率从12%提升至26%. 满意度 96%：500+企业客户NPS评分，续约率行业领先."
            }
            # ... more slides with rich, expanded content
        ]
    },
    save_dir="./outputs/ppt"
)
```

## Success Criteria

* Configuration follows official API specification
* Fixed item_amount constraints are respected
* **Content is detailed, specific, and actionable** - not generic or superficial
* **User's brief input is expanded 3-5x** with concrete examples, data, and context
* Layout selection matches content type
* Presentation tells a compelling story with clear narrative arc
* **No reliance on images** - content quality stands alone

## Quality Self-Check

**Content depth checklist**:

* [ ] Each bullet has **specific details** (numbers, examples, mechanisms)
* [ ] Main claims are **backed by evidence** (metrics, case studies, comparisons)
* [ ] Content answers **"So what?"** - explains impact and relevance
* [ ] Terminology is **precise** - no vague words like "很好"、"强大"、"先进"
* [ ] Each slide has **1-2 sentences per point**, not just keywords

**Structural quality**:

* [ ] Each slide's content can be **visually separated** according to its layout
* [ ] Bullet candidates read like **talking points**, not paragraphs
* [ ] Narrative arc: **context/problem → approach → mechanism → value → evidence → next steps**
* [ ] Progressive detail: Start broad (overview), end specific (action plan)

**Professional polish**:

* [ ] Titles are **outcome-focused**: "提升转化率40%" not "优化方案"
* [ ] Parallel structure maintained within each slide
* [ ] Consistent granularity (don't mix high-level strategy with low-level tactics)
* [ ] Active voice and confident tone throughout

## Content Expansion Workflow

When user provides brief input like "生成一个关于AI产品的PPT":

1. **Analyze intent**: What's the goal? Sales pitch? Product demo? Technical overview?
2. **Define structure**: Typically 8-12 slides covering:
   - Problem/Opportunity (with market data)
   - Solution Overview (with key differentiators)
   - Core Capabilities (with technical details)
   - Use Cases (with specific examples)
   - Results/Impact (with metrics)
   - Comparison (with competitive analysis)
   - Roadmap (with timeline)
   - Next Steps (with clear CTA)

3. **Expand each section**:
   - Take user's keywords and turn them into full sentences
   - Add context (why it matters)
   - Include specifics (how it works)
   - Provide evidence (data, examples)
   - Show impact (outcomes, benefits)

4. **Validate completeness**: Could a stranger understand this without you presenting?

**Remember: Your job is to transform sparse user input into presentation-ready, detailed content that tells a complete, compelling story.**
