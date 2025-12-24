# 通用能力路由框架

## 🎯 核心问题

**当多个执行方式（Skills/Tools/MCP/Code）都能完成同一任务时，如何统一管理优先级？**

这不是某个具体场景的问题，而是一个**通用的架构问题**。

---

## 🏗️ 设计原则

### 1. 统一抽象

所有执行方式统一为**Capability（能力）**：

```python
class Capability:
    name: str                    # 能力名称
    type: CapabilityType         # SKILL/TOOL/MCP/CODE
    subtype: str                 # PREBUILT/CUSTOM/EXTERNAL/DYNAMIC
    provider: str                # anthropic/user/external
    capabilities: List[str]      # 能力标签 ["ppt_generation"]
    priority: int                # 优先级 0-100
    cost: Dict                   # 成本 {time, money}
    constraints: Dict            # 约束条件
    metadata: Dict               # 扩展信息
```

### 2. 配置驱动

所有规则在配置文件中定义，不硬编码：

```yaml
# config/capabilities.yaml
capabilities:
  - name: slidespeak-generator
    type: SKILL
    priority: 85
    capabilities: [ppt_generation]
```

### 3. 可扩展

新增能力只需配置，无需改代码。

---

## 📋 配置格式

### 能力注册表

```yaml
# config/capabilities.yaml

capabilities:
  # ==================== Skills ====================
  - name: slidespeak-generator
    type: SKILL
    subtype: CUSTOM
    provider: user
    capabilities:
      - ppt_generation
      - presentation_creation
    priority: 85
    cost:
      time: medium
      money: low
    constraints:
      requires_api: true
      api_name: slidespeak
      min_quality: high
    metadata:
      preferred_for:
        - professional PPT
        - business presentation
      keywords:
        - 专业
        - 产品
        - 客户
  
  - name: pptx
    type: SKILL
    subtype: PREBUILT
    provider: anthropic
    capabilities:
      - ppt_generation
    priority: 60
    cost:
      time: fast
      money: free
    constraints:
      min_quality: medium
    metadata:
      preferred_for:
        - quick PPT
        - draft slides
      keywords:
        - 快速
        - 草稿
  
  # ==================== Tools ====================
  - name: create_ppt_tool
    type: TOOL
    provider: user
    capabilities:
      - ppt_generation
    priority: 50
    cost:
      time: fast
      money: free
  
  # ==================== MCP Servers ====================
  - name: office365:create_presentation
    type: MCP
    provider: microsoft
    capabilities:
      - ppt_generation
      - office_integration
    priority: 70
    constraints:
      requires_auth: true
    metadata:
      preferred_for:
        - Office compatibility
  
  # ==================== Code as Tools ====================
  - name: code_ppt_generator
    type: CODE
    provider: dynamic
    capabilities:
      - ppt_generation
    priority: 40
```

### 路由规则

```yaml
# config/routing_rules.yaml

routing_rules:
  # 默认类型优先级顺序
  default_type_priority:
    - SKILL:CUSTOM      # 第1: 用户定制Skills
    - MCP               # 第2: MCP服务
    - SKILL:PREBUILT    # 第3: 官方Skills
    - TOOL              # 第4: Tool函数
    - CODE              # 第5: 代码生成
  
  # 评分权重
  weights:
    explicit_mention: 1000   # 用户明确指定
    keyword_match: 100       # 关键词匹配
    quality_match: 20        # 质量匹配
    type_priority: 5         # 类型优先级
    context_continuity: 15   # 上下文连续性
  
  # 质量匹配规则
  quality_rules:
    - condition: "high quality OR professional"
      filter: "min_quality >= high"
      boost: 20
    
    - condition: "quick OR draft"
      filter: "cost.time == fast"
      boost: 30

# 任务特定规则
task_specific_rules:
  ppt_generation:
    default: slidespeak-generator
    routing:
      - keywords: [专业, 产品, 客户, professional, business]
        prefer: slidespeak-generator
        reason: "High quality requirement"
      
      - keywords: [快速, 草稿, quick, draft]
        prefer: pptx
        reason: "Speed over features"
      
      - keywords: [Office, 365, Teams]
        prefer: office365:create_presentation
        reason: "Office integration"
    
    fallback: pptx
```

---

## 🔧 路由引擎实现

### 核心算法

```python
class CapabilityRouter:
    """通用能力路由引擎"""
    
    def route(self, request: UserRequest, context: ExecutionContext) -> Capability:
        """
        路由算法:
        1. 分析请求 → 确定需要的能力标签
        2. 查找候选 → 找到所有匹配的能力
        3. 应用过滤 → 根据约束条件过滤
        4. 计算评分 → 综合多个维度打分
        5. 选择最佳 → 返回得分最高的能力
        """
        
        # Step 1: 分析请求
        required_caps = self._analyze_request(request)
        
        # Step 2: 查找候选
        candidates = self.registry.find_by_capabilities(required_caps)
        
        # Step 3: 应用过滤
        filtered = self._apply_filters(candidates, request, context)
        
        # Step 4: 计算评分
        scored = [(cap, self._calculate_score(cap, request, context)) 
                  for cap in filtered]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Step 5: 选择最佳
        return scored[0][0]
```

### 评分算法

```python
def _calculate_score(self, cap: Capability, request: UserRequest, 
                     context: ExecutionContext) -> float:
    """
    综合打分算法
    
    Score = base_priority           # 基础优先级 (0-100)
          + explicit_mention × 1000 # 用户明确指定
          + keyword_match × 100     # 关键词匹配度 (0-1)
          + quality_match × 20      # 质量要求匹配
          + type_priority × 5       # 类型优先级
          + context_continuity × 15 # 上下文连续性
          - cost_penalty            # 成本惩罚
    """
    score = 0.0
    
    # 1. 基础优先级 (0-100)
    score += cap.priority
    
    # 2. 显式提及加成
    if cap.name in request.explicit_mentions:
        score += self.config.weights.explicit_mention  # +1000
    
    # 3. 关键词匹配加成
    match_ratio = self._keyword_match_ratio(cap, request)
    score += match_ratio * self.config.weights.keyword_match  # +0~100
    
    # 4. 质量匹配加成
    if self._quality_matches(cap, request):
        score += self.config.weights.quality_match  # +20
    
    # 5. 类型优先级加成
    type_rank = self._get_type_rank(cap)
    score += (5 - type_rank) * self.config.weights.type_priority  # +0~25
    
    # 6. 上下文连续性加成
    if context.previous_capability == cap.name:
        score += self.config.weights.context_continuity  # +15
    
    # 7. 成本惩罚
    if cap.cost.get("time") == "slow":
        score -= 10
    if cap.cost.get("money") == "high":
        score -= 5
    
    return score
```

---

## 📊 路由示例

### 场景1: "创建产品介绍PPT"

```
请求分析:
- 能力需求: [ppt_generation]
- 关键词: [产品, 介绍, PPT]
- 质量要求: high (产品介绍暗示专业需求)

候选能力:
1. slidespeak-generator (SKILL:CUSTOM)
2. pptx (SKILL:PREBUILT)
3. office365:create_ppt (MCP)
4. create_ppt_tool (TOOL)
5. code_ppt_generator (CODE)

评分计算:
┌────────────────────────┬──────┬─────────┬─────────┬──────┬──────┬───────┐
│ Capability             │ Base │ Keyword │ Quality │ Type │ Cost │ Total │
├────────────────────────┼──────┼─────────┼─────────┼──────┼──────┼───────┤
│ slidespeak-generator   │  85  │  +100   │   +20   │  +25 │   0  │  230  │
│ pptx                   │  60  │    0    │    0    │  +15 │   0  │   75  │
│ office365:create_ppt   │  70  │    0    │    0    │  +20 │   0  │   90  │
│ create_ppt_tool        │  50  │    0    │    0    │  +10 │   0  │   60  │
│ code_ppt_generator     │  40  │    0    │    0    │   +5 │   0  │   45  │
└────────────────────────┴──────┴─────────┴─────────┴──────┴──────┴───────┘

选择: slidespeak-generator (230分) ✅
```

### 场景2: "快速生成PPT草稿"

```
请求分析:
- 能力需求: [ppt_generation]
- 关键词: [快速, 草稿, PPT]
- 质量要求: low (草稿暗示简单需求)
- 速度要求: fast (快速明确要求)

评分计算:
┌────────────────────────┬──────┬─────────┬───────┬──────┬──────┬───────┐
│ Capability             │ Base │ Keyword │ Speed │ Type │ Cost │ Total │
├────────────────────────┼──────┼─────────┼───────┼──────┼──────┼───────┤
│ slidespeak-generator   │  85  │    0    │   0   │  +25 │   0  │  110  │
│ pptx                   │  60  │  +100   │  +30  │  +15 │   0  │  205  │
│ office365:create_ppt   │  70  │    0    │   0   │  +20 │   0  │   90  │
│ create_ppt_tool        │  50  │    0    │  +30  │  +10 │   0  │   90  │
│ code_ppt_generator     │  40  │    0    │   0   │   +5 │   0  │   45  │
└────────────────────────┴──────┴─────────┴───────┴──────┴──────┴───────┘

选择: pptx (205分) ✅
```

### 场景3: "用SlideSpeak创建PPT"（显式指定）

```
请求分析:
- 能力需求: [ppt_generation]
- 关键词: [SlideSpeak, PPT]
- 显式指定: [SlideSpeak]

评分计算:
┌────────────────────────┬──────┬──────────┬──────┬───────┐
│ Capability             │ Base │ Explicit │ Type │ Total │
├────────────────────────┼──────┼──────────┼──────┼───────┤
│ slidespeak-generator   │  85  │  +1000   │  +25 │ 1110  │
│ pptx                   │  60  │     0    │  +15 │   75  │
│ ...                    │  ..  │    ..    │  ..  │  ...  │
└────────────────────────┴──────┴──────────┴──────┴───────┘

选择: slidespeak-generator (1110分) ✅
用户显式指定，优先级最高
```

---

## 🎯 集成到System Prompt

### 生成路由规则部分

```python
def generate_routing_section(config: Dict) -> str:
    """从配置生成System Prompt中的路由规则"""
    
    lines = []
    lines.append("# Capability Routing Rules")
    lines.append("")
    lines.append("When multiple capabilities can handle the same task:")
    lines.append("")
    
    # 通用规则
    lines.append("## Routing Protocol")
    lines.append("")
    lines.append("1. **Explicit Mention** (Weight: 1000)")
    lines.append("   If user mentions specific tool/skill name → Use it")
    lines.append("")
    lines.append("2. **Keyword Matching** (Weight: 100)")
    lines.append("   Match user keywords with capability's preferred_for")
    lines.append("")
    lines.append("3. **Quality Requirements** (Weight: 20)")
    lines.append("   High quality → Prefer high-quality capabilities")
    lines.append("   Quick/draft → Prefer fast capabilities")
    lines.append("")
    lines.append("4. **Type Priority** (Weight: 5)")
    for i, type_key in enumerate(config["default_type_priority"], 1):
        lines.append(f"   {i}. {type_key}")
    lines.append("")
    lines.append("5. **Context Continuity** (Weight: 15)")
    lines.append("   Continue with same capability for iterations")
    lines.append("")
    
    # 任务特定规则
    for task_name, task_config in config.get("task_specific_rules", {}).items():
        lines.append(f"## {task_name.replace('_', ' ').title()}")
        lines.append(f"Default: {task_config['default']}")
        for rule in task_config["routing"]:
            keywords = ", ".join(rule["keywords"])
            lines.append(f"- If [{keywords}] → {rule['prefer']}")
        lines.append("")
    
    return "\n".join(lines)
```

### System Prompt中的展示

```markdown
# Capability Routing Rules

When multiple capabilities can handle the same task:

## Routing Protocol

1. **Explicit Mention** (Weight: 1000)
   If user mentions specific tool/skill name → Use it

2. **Keyword Matching** (Weight: 100)
   Match user keywords with capability's preferred_for

3. **Quality Requirements** (Weight: 20)
   High quality → Prefer high-quality capabilities
   Quick/draft → Prefer fast capabilities

4. **Type Priority** (Weight: 5)
   1. SKILL:CUSTOM
   2. MCP
   3. SKILL:PREBUILT
   4. TOOL
   5. CODE

5. **Context Continuity** (Weight: 15)
   Continue with same capability for iterations

## PPT Generation

Default: slidespeak-generator 🥇

- If [专业, 产品, 客户, professional] → slidespeak-generator
- If [快速, 草稿, quick, draft] → pptx
- If [Office, 365, Teams] → office365:create_presentation

Fallback: pptx
```

---

## 🔄 扩展性

### 添加新能力

只需在配置文件中注册：

```yaml
# 添加新的PPT生成能力
capabilities:
  - name: canva_ppt_generator
    type: MCP
    provider: canva
    capabilities: [ppt_generation, design]
    priority: 80
    metadata:
      preferred_for: [beautiful, design, creative]
      keywords: [设计, 美观, 创意]
```

### 添加新的路由规则

```yaml
routing_rules:
  # 添加设计相关规则
  design_preference:
    enabled: true
    rules:
      - condition: "beautiful OR design OR creative"
        boost: 25
        filter: "design IN capabilities"
```

### 添加新任务类型

```yaml
task_specific_rules:
  video_generation:
    default: video_ai_skill
    routing:
      - keywords: [professional, high-quality]
        prefer: video_ai_skill
      - keywords: [quick, simple]
        prefer: video_tool
    fallback: video_tool
```

---

## 📊 对比表

### 路由决策对比

| 场景 | 关键词 | 选择 | 原因 |
|------|--------|------|------|
| "创建产品介绍PPT" | 产品, 介绍 | slidespeak-generator | 专业需求 + 高优先级 |
| "快速生成PPT草稿" | 快速, 草稿 | pptx | 速度匹配 |
| "用Office创建PPT" | Office | office365 | 显式指定 |
| "生成一个PPT" | 无特殊 | slidespeak-generator | 默认选择 |

### 优先级影响因素

| 因素 | 权重 | 说明 |
|------|------|------|
| 显式指定 | 1000 | 用户明确要求，最高优先级 |
| 关键词匹配 | 100 | 语义匹配度 |
| 质量要求 | 20 | 高质量/快速匹配 |
| 上下文 | 15 | 延续之前的选择 |
| 类型优先级 | 5 | Custom > MCP > Pre-built |

---

## ✅ 实现检查清单

- [ ] 定义Capability数据结构
- [ ] 实现CapabilityRegistry
- [ ] 实现CapabilityRouter
- [ ] 创建capabilities.yaml配置文件
- [ ] 创建routing_rules.yaml配置文件
- [ ] 实现配置加载器
- [ ] 集成到System Prompt
- [ ] 单元测试
- [ ] 集成测试

---

**配置驱动的统一路由，解决所有能力冲突问题！** 🎯


