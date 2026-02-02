# 通用能力路由框架

> 📅 **最后更新**: 2025-12-30  
> 🎯 **适用版本**: V4.0  
> ✅ **实现状态**: 已完成（core/tool/capability/）

## 🎯 核心问题

**当多个执行方式（Skills/Tools/MCP/Code）都能完成同一任务时，如何统一管理优先级？**

这不是某个具体场景的问题，而是一个**通用的架构问题**。

## 🆕 V4.0 实现状态

✅ **已完成模块化重构**（2025-12-30）

```
core/tool/capability/
├── registry.py       # ✅ CapabilityRegistry（能力注册表）
├── router.py         # ✅ CapabilityRouter（智能路由器）
├── invocation.py     # ✅ InvocationSelector（调用策略）
├── skill_loader.py   # ✅ SkillLoader（Skills 加载器）
└── types.py          # ✅ Capability 类型定义
```

**关键特性**：
- ✅ 配置驱动（capabilities.yaml + routing_rules.yaml）
- ✅ 智能评分算法（多维度综合打分）
- ✅ 自动 Skills 发现
- ✅ 动态工具筛选
- ✅ 扩展性强（新增工具只需配置）

---

## 🚀 V4.0 快速开始

### 基础使用

```python
from core.tool.capability import CapabilityRegistry, CapabilityRouter

# 1. 初始化（自动加载配置）
registry = CapabilityRegistry()
router = CapabilityRouter(registry)

# 2. 选择最佳能力
result = router.select_best(
    required_capabilities=["ppt_generation"],
    user_query="创建专业的产品PPT"
)

print(f"选中: {result.capability.name}")
print(f"得分: {result.score}")
print(f"原因: {result.reason}")

# 输出:
# 选中: slidespeak-generator
# 得分: 230
# 原因: 基础优先级: 85; 关键词匹配: +30; 类型权重(SKILL): +10; 子类型权重(CUSTOM): +15
```

### 添加新能力（仅需配置）

```yaml
# config/capabilities.yaml
capabilities:
  - name: my_custom_ppt_tool
    type: TOOL
    subtype: CUSTOM
    provider: user
    capabilities:
      - ppt_generation
    priority: 75
    metadata:
      description: "我的自定义PPT工具"
      keywords:
        - 自定义
        - 模板
      preferred_for:
        - custom template PPT
```

**无需修改代码，重启即生效！** ✅

### 查询能力

```python
# 查找所有 PPT 生成能力
ppt_caps = registry.find_by_capability("ppt_generation")
for cap in ppt_caps:
    print(f"{cap.name} (优先级: {cap.priority})")

# 输出:
# slidespeak-generator (优先级: 85)
# my_custom_ppt_tool (优先级: 75)
# pptx (优先级: 60)
```

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

## 🔧 V4.0 路由引擎实现

### 实际代码位置

```
core/tool/capability/router.py - CapabilityRouter (✅ 已实现)
```

### 核心算法（实际实现）

```python
class CapabilityRouter:
    """
    通用能力路由引擎
    
    文件位置: core/tool/capability/router.py
    """
    
    def select_best(
        self,
        required_capabilities: List[str],
        user_query: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> RoutingResult:
        """
        选择最佳能力（实际 API）
        
        路由算法:
        1. 查找候选 → 从 Registry 匹配能力标签
        2. 应用过滤 → 检查约束条件（API可用性、网络等）
        3. 计算评分 → 综合多维度打分
        4. 选择最佳 → 返回得分最高的能力 + 备选方案
        """
        
        # Step 1: 查找候选能力
        candidates = []
        for cap_name in required_capabilities:
            caps = self.registry.find_by_capability(cap_name)
            candidates.extend(caps)
        
        if not candidates:
            raise ValueError(f"No capabilities found for: {required_capabilities}")
        
        # Step 2: 应用过滤（约束条件）
        filtered = self._apply_constraints(candidates, context)
        
        # Step 3: 计算评分
        scored = []
        for cap in filtered:
            score, reason = self._calculate_score(
                cap,
                user_query=user_query,
                context=context
            )
            scored.append((cap, score, reason))
        
        # 按分数降序排序
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Step 4: 返回最佳 + 备选
        best_cap, best_score, best_reason = scored[0]
        alternatives = [(c, s) for c, s, _ in scored[1:6]]  # 保留前5个备选
        
        return RoutingResult(
            capability=best_cap,
            score=best_score,
            reason=best_reason,
            alternatives=alternatives
        )
    
    def select_multiple(
        self,
        required_capabilities: List[str],
        user_query: Optional[str] = None,
        top_n: int = 3
    ) -> List[RoutingResult]:
        """
        选择多个候选能力（供 LLM 智能选择）
        
        使用场景：
        - 保留多个高分能力，由 LLM 根据上下文决策
        - 例如：ppt_generation 可能返回 slidespeak 和 pptx
        """
        # 类似 select_best，但返回前 N 个
        # ...
```

**实际使用示例**：

```python
# 在 ToolSelector 中调用
from core.tool.capability import CapabilityRouter

router = CapabilityRouter(registry)

# 单一最佳选择
result = router.select_best(
    required_capabilities=["ppt_generation"],
    user_query="创建专业的产品PPT"
)

print(result.capability.name)  # slidespeak-generator
print(result.score)            # 230
print(result.reason)           # "关键词匹配: 专业, 产品; 高质量需求"

# 多候选选择（供 LLM 决策）
results = router.select_multiple(
    required_capabilities=["ppt_generation"],
    top_n=2
)
# 返回: [slidespeak-generator, pptx]
# LLM 根据上下文自主选择
```

### V4.0 评分算法（实际实现）

**代码位置**: `core/tool/capability/router.py` 的 `_calculate_score()` 方法

```python
def _calculate_score(
    self,
    cap: Capability,
    user_query: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Tuple[float, str]:
    """
    综合打分算法（V4.0 实际实现）
    
    计算公式：
    Score = base_priority               # 基础优先级 (0-100)
          + explicit_mention × 1000     # 用户明确指定
          + keyword_match_score         # 关键词匹配 (0-15分/关键词)
          + type_weight                 # 类型权重 (4-10)
          + subtype_weight              # 子类型权重 (3-15)
          + context_boost               # 上下文加成 (0-20)
          - constraint_penalty          # 约束未满足惩罚
    
    Returns:
        (score, reason): 分数 + 评分原因
    """
    score = 0.0
    reasons = []
    
    # 1. 基础优先级
    score += cap.priority
    reasons.append(f"基础优先级: {cap.priority}")
    
    # 2. 显式提及检测（最高优先级）
    if user_query and self._is_explicitly_mentioned(cap, user_query):
        score += 1000
        reasons.append(f"显式指定: +1000")
    
    # 3. 关键词匹配
    if user_query:
        keywords = self._extract_keywords(user_query)
        keyword_score = cap.matches_keywords(keywords)
        if keyword_score > 0:
            score += keyword_score
            reasons.append(f"关键词匹配: +{keyword_score}")
    
    # 4. 类型权重
    type_weight = self.type_weights.get(cap.type, 0)
    score += type_weight
    reasons.append(f"类型权重({cap.type.value}): +{type_weight}")
    
    # 5. 子类型权重
    subtype_weight = self.subtype_weights.get(cap.subtype, 0)
    if subtype_weight > 0:
        score += subtype_weight
        reasons.append(f"子类型权重({cap.subtype}): +{subtype_weight}")
    
    # 6. 上下文连续性
    if context and context.get('previous_capability') == cap.name:
        score += 20
        reasons.append("上下文连续性: +20")
    
    # 7. 成本考虑（轻微惩罚）
    if cap.cost.get('time') == 'slow':
        score -= 5
        reasons.append("慢速惩罚: -5")
    if cap.cost.get('money') == 'high':
        score -= 3
        reasons.append("高成本惩罚: -3")
    
    reason_str = "; ".join(reasons)
    return score, reason_str
```

**实际权重配置**（来自代码）:

```python
# core/tool/capability/router.py
type_weights = {
    CapabilityType.SKILL: 10,   # Skills 最高
    CapabilityType.TOOL: 8,
    CapabilityType.MCP: 6,
    CapabilityType.CODE: 4
}

subtype_weights = {
    "CUSTOM": 15,      # 自定义最高
    "PREBUILT": 10,
    "NATIVE": 8,
    "EXTERNAL": 5,
    "DYNAMIC": 3
}
```

**关键词匹配实现**（来自 `types.py`）:

```python
# core/tool/capability/types.py
class Capability:
    def matches_keywords(self, keywords: List[str]) -> int:
        """
        计算关键词匹配分数
        
        匹配规则:
        - capabilities 标签匹配: +15 分/关键词
        - preferred_for 匹配: +10 分/关键词
        - metadata.keywords 匹配: +5 分/关键词
        - description 匹配: +3 分/关键词
        """
        score = 0
        for kw in keywords:
            kw_lower = kw.lower()
            
            if any(kw_lower in c.lower() for c in self.capabilities):
                score += 15  # 能力标签匹配（权重最高）
            
            if any(kw_lower in p.lower() 
                   for p in self.metadata.get('preferred_for', [])):
                score += 10  # preferred_for 匹配
            
            if any(kw_lower in k.lower() 
                   for k in self.metadata.get('keywords', [])):
                score += 5   # keywords 匹配
            
            if kw_lower in self.metadata.get('description', '').lower():
                score += 3   # description 匹配
    
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

## ✅ V4.0 实现检查清单

- [x] ✅ 定义Capability数据结构 (`core/tool/capability/types.py`)
- [x] ✅ 实现CapabilityRegistry (`core/tool/capability/registry.py`)
- [x] ✅ 实现CapabilityRouter (`core/tool/capability/router.py`)
- [x] ✅ 创建capabilities.yaml配置文件 (`config/capabilities.yaml`)
- [x] ✅ 创建routing_rules.yaml配置文件 (`config/routing_rules.yaml`)
- [x] ✅ 实现配置加载器（内置在 Registry 和 Router 中）
- [x] ✅ 集成到 ToolSelector (`core/tool/selector.py`)
- [x] ✅ 集成到 SimpleAgent (`core/agent/simple/simple_agent.py`)
- [ ] ⏳ 单元测试（部分完成）
- [ ] ⏳ 集成测试（端到端测试通过）

---

## 🔗 V4.0 架构集成

### 在 Agent 中的使用

```python
# core/agent/simple/simple_agent.py
from core.tool.capability import CapabilityRegistry, CapabilityRouter
from core.tool import ToolSelector, ToolExecutor

class SimpleAgent:
    def __init__(self, event_manager=None):
        # 1. 初始化能力注册表
        self.registry = CapabilityRegistry()
        
        # 2. 初始化路由器
        self.router = CapabilityRouter(registry=self.registry)
        
        # 3. 初始化工具选择器（使用 Router）
        self.tool_selector = ToolSelector(
            registry=self.registry,
            router=self.router
        )
        
        # 4. 初始化工具执行器
        self.tool_executor = ToolExecutor(event_manager=event_manager)
    
    async def chat(self, user_input: str):
        # ... Intent Analysis ...
        
        # 使用 Router 选择最佳工具
        routing_result = self.router.select_best(
            required_capabilities=["ppt_generation"],
            user_query=user_input
        )
        
        # 获取选中的工具
        selected_tools = self.tool_selector.select(
            required_capabilities=routing_result.capability.capabilities
        )
        
        # 执行工具
        for tool in selected_tools:
            result = await self.tool_executor.execute(
                tool_name=tool.name,
                tool_input=params
            )
```

### 数据流

```
用户输入: "创建专业的产品PPT"
    ↓
Intent Analyzer: task_type = "content_generation"
    ↓
CapabilityRegistry: 查找 ["ppt_generation"] 的所有候选
    ↓ [slidespeak-generator, pptx, office365:create_ppt, ...]
    ↓
CapabilityRouter: 计算评分
    ↓ slidespeak-generator (230分)
    ↓ pptx (75分)
    ↓ office365 (90分)
    ↓
ToolSelector: 返回最佳工具列表
    ↓ [slidespeak-generator]
    ↓
ToolExecutor: 执行工具
    ↓ 调用 SlideSpeak API
    ↓
返回结果给用户
```

### 配置文件结构

```
config/
├── capabilities.yaml          # 能力定义（统一数据源）
│   ├── capability_categories  # 能力分类（8个）
│   ├── task_type_mappings     # 任务类型映射
│   └── capabilities           # 具体能力列表
│       ├── Skills
│       ├── Tools
│       ├── MCP Servers
│       └── Code Capabilities
│
└── routing_rules.yaml         # 路由规则（可选）
    ├── type_weights           # 类型权重
    ├── subtype_weights        # 子类型权重
    └── task_specific_rules    # 任务特定规则
```

---

## 🎯 核心收益

### V4.0 架构优势

| 特性 | V3.7 | V4.0 | 改进 |
|------|------|------|------|
| **模块化** | 分散在多个文件 | 统一子包 `core/tool/capability/` | ✅ 清晰边界 |
| **配置驱动** | 部分硬编码 | 完全配置驱动 | ✅ 易于扩展 |
| **路由智能** | 简单优先级 | 多维度评分算法 | ✅ 更精准 |
| **Skills 发现** | 手动注册 | 自动扫描 `skills/library/` | ✅ 零配置 |
| **类型系统** | 混乱 | 完整类型定义 | ✅ 类型安全 |
| **可测试性** | 困难 | 模块独立可测 | ✅ 易于测试 |

### 实际效果

**场景：PPT 生成**

```
旧设计（V3.7）:
- 硬编码优先级
- LLM 从所有工具中选择（12个）
- 容易选错

新设计（V4.0）:
- Router 智能评分
- 只传递相关工具给 LLM（2-3个）
- 显著提高准确率
```

**成功案例**：
- ✅ 用户说"专业的产品PPT" → 自动选择 slidespeak-generator
- ✅ 用户说"快速草稿PPT" → 自动选择 pptx
- ✅ 用户说"用 SlideSpeak" → 显式指定，直接使用

---

## 🔧 故障排查

### 问题1: 能力未找到

```python
# 错误: ValueError: No capabilities found for: ['xxx']

# 解决方法:
# 1. 检查 capabilities.yaml 中是否定义了该能力
# 2. 检查 capabilities 字段是否包含正确的标签
# 3. 重启应用，确保配置已加载
```

### 问题2: 选择了错误的工具

```python
# 原因: 评分算法导致
# 解决方法:
# 1. 调整 priority（基础优先级）
# 2. 添加/优化 keywords 和 preferred_for
# 3. 检查 routing_rules.yaml 的权重配置
```

### 问题3: Skills 未自动发现

```python
# 原因: skills/library/ 目录结构不正确
# 解决方法:
# 1. 确保每个 Skill 有 skill.yaml 文件
# 2. 检查 skill.yaml 格式是否正确
# 3. 查看启动日志中的 Skills 扫描信息
```

### 调试技巧

```python
# 启用详细日志
import logging
logging.getLogger("core.tool.capability").setLevel(logging.DEBUG)

# 查看所有已注册的能力
for name, cap in registry.capabilities.items():
    print(f"{name}: {cap.type.value}, priority={cap.priority}")

# 查看路由详情
result = router.select_best(
    required_capabilities=["ppt_generation"],
    user_query="测试"
)
print(f"最佳: {result.capability.name} ({result.score}分)")
print(f"原因: {result.reason}")
print("备选:")
for cap, score in result.alternatives[:3]:
    print(f"  - {cap.name} ({score}分)")
```

---

## 💡 最佳实践

### 1. 优先级设置

```yaml
# 推荐范围:
# 80-100: 高质量、官方推荐
# 60-79:  标准质量
# 40-59:  备用选项
# 20-39:  实验性功能
# 0-19:   不推荐使用

capabilities:
  - name: premium_tool
    priority: 90  # 推荐
  
  - name: standard_tool
    priority: 70  # 标准
  
  - name: fallback_tool
    priority: 50  # 备用
```

### 2. 关键词优化

```yaml
# ✅ 好的关键词设置
metadata:
  keywords:
    - 专业      # 具体
    - 产品      # 领域
    - 客户      # 场景
  preferred_for:
    - professional PPT
    - product presentation
    - client meeting

# ❌ 不好的关键词设置
metadata:
  keywords:
    - 好        # 太泛
    - PPT       # 重复
```

### 3. 成本标注

```yaml
# 明确标注成本，帮助路由决策
cost:
  time: fast     # fast/medium/slow
  money: free    # free/low/medium/high

# 高成本工具会有轻微惩罚
# 但如果质量明显更好，仍会被选中
```

### 4. 约束条件

```yaml
# 使用约束条件过滤不可用的能力
constraints:
  requires_api: true          # 需要 API 密钥
  api_name: slidespeak        # 具体 API 名称
  requires_network: true      # 需要网络
  min_quality: high           # 质量要求

# Router 会自动检查这些约束
# 不满足的能力会被过滤掉
```

### 5. 测试新能力

```python
# 添加新能力后，先测试评分
result = router.select_best(
    required_capabilities=["your_capability"],
    user_query="测试查询"
)

# 检查是否被正确选中
assert result.capability.name == "expected_tool"

# 检查评分是否合理
print(f"得分: {result.score}")
print(f"原因: {result.reason}")
```

---

## 📚 相关文档

| 文档 | 说明 | 状态 |
|------|------|------|
| [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) | V4.0 完整架构 | ✅ 最新 |
| [02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md) | 本文档 | ✅ V4.0 |
| `core/tool/capability/` | 实际代码实现 | ✅ 已完成 |

---

**V4.0: 配置驱动的智能路由，彻底解决能力冲突问题！** 🎯


