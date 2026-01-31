# Invocation Strategy Selection V2 - 增强优化方案

> 📅 **版本**: V2.0  
> 🎯 **目标**: 结合三层抽象思想优化工具调用策略  
> 🔗 **基于**: V3.7 InvocationSelector + Context Engineering

---

## 📋 目录

- [当前问题分析](#当前问题分析)
- [V2 核心改进](#v2-核心改进)
- [智能选择矩阵](#智能选择矩阵)
- [实现方案](#实现方案)
- [性能优化](#性能优化)

---

## 🔍 当前问题分析

### V3.7 InvocationSelector 现状

```python
# core/tool/capability/invocation.py (当前版本)

class InvocationSelector:
    """
    当前选择逻辑（简化版）
    """
    
    def select_strategy(
        self,
        task_type: str,
        selected_tools: List[str],
        estimated_input_size: int = 0
    ) -> InvocationStrategy:
        """
        选择规则：
        1. config_generation → Code Execution
        2. 多工具(>2) → Programmatic
        3. 大参数(>10KB) → Streaming
        4. 工具多(>30) → Tool Search
        5. 默认 → Direct Call
        """
        
        if task_type == "config_generation":
            return InvocationStrategy.CODE_EXECUTION
        
        if len(selected_tools) > 2:
            return InvocationStrategy.PROGRAMMATIC
        
        if estimated_input_size > 10000:
            return InvocationStrategy.STREAMING
        
        if len(selected_tools) > 30:
            return InvocationStrategy.TOOL_SEARCH
        
        return InvocationStrategy.DIRECT
```

### 存在的问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **缺少层级感知** | 未结合三层抽象架构 | 无法智能选择执行环境 |
| **静态规则** | 硬编码的阈值（>2, >30） | 不适应不同场景 |
| **无降级策略** | E2B 失败时无备选 | 鲁棒性差 |
| **忽略成本** | 未考虑 Claude vs E2B 成本差异 | 资源浪费 |
| **无 Context 感知** | 未根据当前 context 大小调整 | Context 爆炸风险 |

---

## 🚀 V2 核心改进

### 1. 层级感知调用策略

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              三层抽象架构 + Claude 五种调用方式 = 智能映射                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  抽象层级            执行环境                      Claude 调用方式           │
│  ━━━━━━━━━━━━       ━━━━━━━━━━━━━━━━━━━━━       ━━━━━━━━━━━━━━━━━         │
│                                                                              │
│  Level 1            Native Claude                Direct Tool Call           │
│  (Core Tools)       ✅ 标准 Function Call        • plan_todo                │
│                     ✅ 快速响应 <1s              • file_read                │
│                     ✅ Schema-safe               • web_search               │
│                                                  • basic bash               │
│                                                                              │
│  Level 2            Claude Code Execution        Code Execution (内置)     │
│  (Utilities)        ✅ 轻量级计算                • 配置生成                 │
│                     ✅ 无第三方包限制            • JSON 验证                │
│                     ✅ <10s 快速执行             • 简单数学                 │
│                     ❌ 无文件系统                • 字符串处理               │
│                                                                              │
│  Level 3a           E2B Sandbox (标准)          Programmatic + E2B         │
│  (Standard Tasks)   ✅ 完整 Python 环境          • 数据分析                 │
│                     ✅ 第三方包支持              • 多工具编排               │
│                     ✅ 文件系统                  • API 链式调用             │
│                     ✅ 网络访问                  • 批量处理                 │
│                     ⚠️ 2-5s 启动延迟                                         │
│                                                                              │
│  Level 3b           E2B Vibe Coding             Programmatic + Vibe        │
│  (Complex Apps)     ✅ 完整应用框架              • Streamlit 应用           │
│                     ✅ Web 预览                  • Gradio 界面              │
│                     ✅ 持久化服务                • Next.js 前端             │
│                     ⚠️ 10-30s 启动延迟                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. 动态降级策略

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         智能降级决策树                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  任务需求: "需要 pandas 数据分析"                                             │
│      │                                                                       │
│      ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ 首选: E2B Sandbox (Level 3a)                                         │  │
│  │  ✅ 第三方包支持                                                      │  │
│  │  ✅ 完整环境                                                          │  │
│  └────────────────────────────────┬─────────────────────────────────────┘  │
│                                   │                                         │
│                          ┌────────┴────────┐                                │
│                          │  E2B 可用？      │                                │
│                          └────────┬────────┘                                │
│                                   │                                         │
│              ┌────────────────────┼────────────────────┐                    │
│              │ YES                │ NO                 │                    │
│              ▼                    ▼                    ▼                    │
│      ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│      │ 使用 E2B     │    │ 检查备选方案  │    │ 报错降级      │             │
│      │ Sandbox      │    │              │    │              │             │
│      └──────────────┘    └──────┬───────┘    └──────────────┘             │
│                                 │                                           │
│                                 ▼                                           │
│                      ┌──────────────────────┐                               │
│                      │ 能用 Code Execution? │                               │
│                      │ (无第三方包需求)     │                               │
│                      └──────────┬───────────┘                               │
│                                 │                                           │
│                    ┌────────────┼────────────┐                              │
│                    │ YES        │ NO         │                              │
│                    ▼            ▼            ▼                              │
│            ┌──────────┐  ┌──────────┐  ┌──────────┐                        │
│            │ 降级到   │  │ 拆解任务  │  │ 失败并   │                        │
│            │ Claude   │  │ 使用多个  │  │ 提示用户  │                        │
│            │ Code     │  │ Level 1   │  │          │                        │
│            │ Execution│  │ 工具      │  │          │                        │
│            └──────────┘  └──────────┘  └──────────┘                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. Context-Aware 选择

```python
# 根据当前 context 使用情况动态调整

class ContextAwareSelector:
    """
    Context 感知的调用策略选择器
    
    核心思想：
    - More context ≠ more intelligence
    - 当 context 接近上限时，优先精简策略
    """
    
    def select_with_context_awareness(
        self,
        task_type: str,
        tools: List[str],
        current_context_tokens: int,
        max_context_tokens: int = 200000  # Claude 3.5 Sonnet 上限
    ) -> InvocationStrategy:
        """
        Context 感知选择
        
        策略：
        1. context < 50%: 正常选择
        2. context 50-80%: 优先精简策略
        3. context > 80%: 强制精简 + 警告
        """
        
        context_usage = current_context_tokens / max_context_tokens
        
        # 🚨 Context 危险区（>80%）
        if context_usage > 0.8:
            logger.warning(
                f"⚠️ Context 使用率 {context_usage:.1%}，"
                "强制使用精简策略"
            )
            
            # 优先使用 Code Execution（结果精简）
            if self._can_use_code_execution(task_type):
                return InvocationStrategy.CODE_EXECUTION
            
            # 或使用 Streaming（边传边处理）
            return InvocationStrategy.STREAMING
        
        # ⚠️ Context 警告区（50-80%）
        elif context_usage > 0.5:
            logger.info(
                f"ℹ️ Context 使用率 {context_usage:.1%}，"
                "优先使用精简策略"
            )
            
            # 倾向于使用返回引用而非完整内容的策略
            return self._select_compact_strategy(task_type, tools)
        
        # ✅ Context 安全区（<50%）
        else:
            # 正常选择逻辑
            return self._select_optimal_strategy(task_type, tools)
```

### 4. Cost-Aware 选择

```python
class CostAwareSelector:
    """
    成本感知的调用策略选择器
    
    考虑因素：
    - Claude API 成本
    - E2B 沙箱成本
    - 执行时间（时间也是成本）
    """
    
    # 成本模型（简化版，实际成本可能不同）
    COST_MODEL = {
        "claude_prompt_cache": 0.0003,   # $/1K tokens (cache read)
        "claude_input": 0.003,           # $/1K tokens
        "claude_output": 0.015,          # $/1K tokens
        "e2b_sandbox_per_hour": 0.10,    # $/hour
        "e2b_sandbox_per_session": 0.01  # $/session
    }
    
    def select_with_cost_awareness(
        self,
        task_type: str,
        tools: List[str],
        cost_mode: str = "balanced"  # "cheap" | "balanced" | "quality"
    ) -> InvocationStrategy:
        """
        成本感知选择
        
        模式：
        - cheap: 优先 Claude Code Execution（无额外成本）
        - balanced: 根据任务复杂度选择（默认）
        - quality: 优先 E2B 沙箱（功能最强）
        """
        
        if cost_mode == "cheap":
            # 尽量使用 Claude 内置能力
            if self._can_use_code_execution(task_type):
                return InvocationStrategy.CODE_EXECUTION
            return InvocationStrategy.DIRECT
        
        elif cost_mode == "quality":
            # 优先使用最强能力（E2B 沙箱）
            if self._needs_third_party_packages(task_type):
                return InvocationStrategy.PROGRAMMATIC_E2B
            return InvocationStrategy.PROGRAMMATIC
        
        else:  # balanced
            # 根据任务需求平衡选择
            estimated_cost = self._estimate_task_cost(task_type, tools)
            
            if estimated_cost < 0.01:  # 小任务，用 Claude
                return InvocationStrategy.CODE_EXECUTION
            else:  # 大任务，用 E2B（避免多次往返）
                return InvocationStrategy.PROGRAMMATIC_E2B
```

---

## 🎯 智能选择矩阵

### 完整决策矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    InvocationSelector V2 决策矩阵                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  输入维度（8个）                推荐策略              备选策略                │
│  ━━━━━━━━━━━━━━━━              ━━━━━━━━              ━━━━━━━━              │
│                                                                              │
│  1️⃣ 任务类型 (task_type)                                                    │
│     • information_query         Direct Call            -                    │
│     • config_generation         Code Execution         E2B Sandbox          │
│     • data_analysis            E2B Sandbox             Code Execution       │
│     • content_generation        Direct Call            Code Execution       │
│     • multi_tool                Programmatic E2B       Programmatic         │
│                                                                              │
│  2️⃣ 工具层级 (tool_level)                                                   │
│     • Level 1 (Core)            Direct Call            -                    │
│     • Level 2 (Utilities)       Code Execution         Direct Call          │
│     • Level 3a (Standard)       E2B Sandbox            Programmatic         │
│     • Level 3b (Complex)        E2B Vibe Coding        -                    │
│                                                                              │
│  3️⃣ 工具数量 (tool_count)                                                   │
│     • 1-2 个                    Direct Call            -                    │
│     • 3-5 个                    Programmatic           Direct Call          │
│     • 6-30 个                   Programmatic E2B       Programmatic         │
│     • >30 个                    Tool Search            Programmatic E2B     │
│                                                                              │
│  4️⃣ 参数大小 (input_size)                                                   │
│     • <1KB                      Direct Call            -                    │
│     • 1-10KB                    Direct Call            Streaming            │
│     • >10KB                     Streaming              E2B Sandbox          │
│                                                                              │
│  5️⃣ 依赖要求 (dependencies)                                                 │
│     • 无第三方包                Code Execution         Direct Call          │
│     • 需要第三方包              E2B Sandbox            -                    │
│     • 需要文件系统              E2B Sandbox            -                    │
│     • 需要网络访问              E2B Sandbox            -                    │
│                                                                              │
│  6️⃣ Context 使用率 (context_usage)                                          │
│     • <50%                      正常选择               -                    │
│     • 50-80%                    精简策略优先           Streaming            │
│     • >80%                      强制精简               Code Execution       │
│                                                                              │
│  7️⃣ 成本模式 (cost_mode)                                                    │
│     • cheap                     Code Execution         Direct Call          │
│     • balanced                  动态选择               -                    │
│     • quality                   E2B Sandbox            Programmatic E2B     │
│                                                                              │
│  8️⃣ 可用性 (availability)                                                   │
│     • E2B 可用                  正常选择               -                    │
│     • E2B 不可用                降级到 Code Exec       Direct Call          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 实际场景示例

```python
# ============================================================
# 场景 1: 简单搜索查询
# ============================================================
select_strategy(
    task_type="information_query",
    tools=["web_search"],
    tool_level=1,
    input_size=100,
    context_usage=0.3
)
# → Direct Tool Call
# 理由：单工具、Level 1、context 充足


# ============================================================
# 场景 2: 配置生成（SlideSpeak）
# ============================================================
select_strategy(
    task_type="config_generation",
    tools=["slidespeak"],
    tool_level=2,
    input_size=5000,
    context_usage=0.6
)
# → Code Execution (Claude 内置)
# 理由：配置生成、无第三方包需求、context 中等


# ============================================================
# 场景 3: 数据分析（需要 pandas）
# ============================================================
select_strategy(
    task_type="data_analysis",
    tools=["xlsx", "python"],
    tool_level=3,
    dependencies=["pandas", "numpy"],
    context_usage=0.4,
    cost_mode="balanced"
)
# → Programmatic Tool Calling + E2B Sandbox
# 理由：需要第三方包、Level 3、成本平衡


# ============================================================
# 场景 4: 多工具编排（API 链式调用）
# ============================================================
select_strategy(
    task_type="multi_tool",
    tools=["web_search", "api_calling", "data_processing"],
    tool_level=3,
    tool_count=3,
    context_usage=0.7
)
# → Programmatic Tool Calling + E2B Sandbox
# 理由：多工具、复杂逻辑、context 偏高（精简优先）


# ============================================================
# 场景 5: Context 危险区（>80%）
# ============================================================
select_strategy(
    task_type="data_analysis",
    tools=["xlsx"],
    tool_level=3,
    context_usage=0.85  # ⚠️ 危险
)
# → Code Execution (强制精简)
# 理由：Context 接近上限，优先精简策略
# 备选：如果必须用 E2B，则使用 Streaming 返回


# ============================================================
# 场景 6: E2B 不可用（降级）
# ============================================================
select_strategy(
    task_type="data_analysis",
    tools=["python"],
    tool_level=3,
    dependencies=["pandas"],
    e2b_available=False  # ❌ E2B 不可用
)
# → Code Execution (降级)
# 理由：E2B 不可用，降级到 Claude 内置
# 警告：pandas 不可用，提示用户功能受限
```

---

## 🛠️ 实现方案

### 完整代码实现

```python
# core/tool/capability/invocation_v2.py

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 类型定义
# ============================================================

class InvocationStrategy(Enum):
    """调用策略（增强版）"""
    DIRECT = "direct"                    # 标准 Function Call
    CODE_EXECUTION = "code_execution"    # Claude 内置代码执行
    PROGRAMMATIC = "programmatic"        # 程序化调用（Claude）
    PROGRAMMATIC_E2B = "programmatic_e2b"  # 🆕 程序化 + E2B 沙箱
    STREAMING = "streaming"              # 细粒度流式
    TOOL_SEARCH = "tool_search"          # 工具搜索
    VIBE_CODING = "vibe_coding"          # 🆕 E2B Vibe Coding


@dataclass
class StrategyDecision:
    """策略决策结果"""
    strategy: InvocationStrategy
    reason: str                          # 选择理由
    fallback: Optional[InvocationStrategy] = None  # 🆕 降级备选
    warnings: List[str] = None           # 🆕 警告信息
    config: Dict[str, Any] = None        # 策略配置参数
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.config is None:
            self.config = {}


@dataclass
class SelectionContext:
    """选择上下文（所有输入维度）"""
    # 基础维度
    task_type: str
    tools: List[str]
    
    # 🆕 工具层级
    tool_levels: List[int] = None  # [1, 1, 3]，对应每个工具的层级
    
    # 大小维度
    input_size: int = 0
    tool_count: int = 0
    
    # 🆕 依赖维度
    requires_third_party_packages: bool = False
    requires_file_system: bool = False
    requires_network: bool = False
    
    # 🆕 Context 维度
    current_context_tokens: int = 0
    max_context_tokens: int = 200000
    
    # 🆕 成本模式
    cost_mode: str = "balanced"  # "cheap" | "balanced" | "quality"
    
    # 🆕 可用性
    e2b_available: bool = True
    code_execution_available: bool = True
    
    # 其他
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.tool_count == 0:
            self.tool_count = len(self.tools)
        if self.tool_levels is None:
            self.tool_levels = []
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def context_usage(self) -> float:
        """Context 使用率"""
        return self.current_context_tokens / self.max_context_tokens
    
    @property
    def max_tool_level(self) -> int:
        """最高工具层级"""
        return max(self.tool_levels) if self.tool_levels else 1


# ============================================================
# InvocationSelector V2
# ============================================================

class InvocationSelectorV2:
    """
    调用策略选择器 V2
    
    核心改进：
    1. 层级感知（三层抽象架构）
    2. Context 感知（动态调整）
    3. 成本感知（平衡质量和成本）
    4. 智能降级（故障自动恢复）
    5. 多维度决策（8 个输入维度）
    """
    
    def __init__(
        self,
        enable_e2b: bool = True,
        enable_code_execution: bool = True,
        enable_streaming: bool = True,
        enable_tool_search: bool = True
    ):
        self.enable_e2b = enable_e2b
        self.enable_code_execution = enable_code_execution
        self.enable_streaming = enable_streaming
        self.enable_tool_search = enable_tool_search
        
        # 统计信息
        self.stats = {
            "total_selections": 0,
            "strategy_counts": {},
            "fallback_count": 0
        }
    
    # ============================================================
    # 主入口：智能选择
    # ============================================================
    
    def select(self, ctx: SelectionContext) -> StrategyDecision:
        """
        主选择逻辑（多维度决策）
        
        决策顺序：
        1. 检查可用性（降级处理）
        2. Context 危险区检查（强制精简）
        3. 层级优先选择
        4. 任务类型匹配
        5. 成本模式调整
        6. 最终验证和降级
        """
        
        self.stats["total_selections"] += 1
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1️⃣ 可用性检查
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if not ctx.e2b_available and ctx.requires_third_party_packages:
            logger.warning(
                "⚠️ E2B 不可用但任务需要第三方包，"
                "将尝试降级到 Code Execution"
            )
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2️⃣ Context 危险区检查（优先级最高）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        if ctx.context_usage > 0.8:
            return self._handle_context_critical(ctx)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 3️⃣ 层级优先选择
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        max_level = ctx.max_tool_level
        
        if max_level == 1:
            # Level 1: 核心工具 → Direct Call
            return StrategyDecision(
                strategy=InvocationStrategy.DIRECT,
                reason="Level 1 core tools, using direct call",
                config={"betas": []}
            )
        
        elif max_level == 2:
            # Level 2: 工具类 → Code Execution 或 Direct
            return self._select_for_level2(ctx)
        
        elif max_level >= 3:
            # Level 3: 复杂任务 → E2B Sandbox
            return self._select_for_level3(ctx)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 4️⃣ 任务类型匹配（兜底逻辑）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        return self._select_by_task_type(ctx)
    
    # ============================================================
    # Level 2 选择逻辑
    # ============================================================
    
    def _select_for_level2(self, ctx: SelectionContext) -> StrategyDecision:
        """
        Level 2 工具选择
        
        策略：
        - 配置生成 → Code Execution
        - 简单工具 → Direct Call
        - 多工具 → Programmatic
        """
        
        # 配置生成任务
        if ctx.task_type == "config_generation":
            if self.enable_code_execution:
                return StrategyDecision(
                    strategy=InvocationStrategy.CODE_EXECUTION,
                    reason="Config generation task, using code execution",
                    fallback=InvocationStrategy.DIRECT,
                    config={"betas": ["code-execution-2025-05-22"]}
                )
        
        # 多工具编排
        if ctx.tool_count > 2:
            return StrategyDecision(
                strategy=InvocationStrategy.PROGRAMMATIC,
                reason=f"Multiple tools ({ctx.tool_count}), using programmatic",
                fallback=InvocationStrategy.DIRECT,
                config={"betas": ["code-execution-2025-05-22"]}
            )
        
        # 默认：Direct Call
        return StrategyDecision(
            strategy=InvocationStrategy.DIRECT,
            reason="Level 2 single tool, using direct call",
            config={}
        )
    
    # ============================================================
    # Level 3 选择逻辑
    # ============================================================
    
    def _select_for_level3(self, ctx: SelectionContext) -> StrategyDecision:
        """
        Level 3 工具选择
        
        策略：
        - 需要第三方包 → E2B Sandbox
        - 需要文件系统 → E2B Sandbox
        - Vibe Coding 场景 → E2B Vibe Coding
        - E2B 不可用 → 降级到 Code Execution
        """
        
        # 检查是否需要 E2B
        needs_e2b = (
            ctx.requires_third_party_packages or
            ctx.requires_file_system or
            ctx.requires_network or
            ctx.tool_count > 5  # 复杂编排
        )
        
        if needs_e2b:
            if ctx.e2b_available:
                # ✅ E2B 可用
                
                # 判断是否需要 Vibe Coding
                if self._is_vibe_coding_task(ctx):
                    return StrategyDecision(
                        strategy=InvocationStrategy.VIBE_CODING,
                        reason="Complex app generation, using Vibe Coding",
                        fallback=InvocationStrategy.PROGRAMMATIC_E2B,
                        config={
                            "use_e2b": True,
                            "template": self._select_vibe_template(ctx)
                        }
                    )
                
                # 标准 E2B Sandbox
                return StrategyDecision(
                    strategy=InvocationStrategy.PROGRAMMATIC_E2B,
                    reason=(
                        f"Level 3 task requiring "
                        f"{'packages' if ctx.requires_third_party_packages else ''}"
                        f"{'filesystem' if ctx.requires_file_system else ''}"
                        f", using E2B sandbox"
                    ),
                    fallback=InvocationStrategy.CODE_EXECUTION,
                    config={
                        "use_e2b": True,
                        "session_reuse": True  # 复用会话
                    }
                )
            else:
                # ❌ E2B 不可用，降级
                return self._fallback_from_e2b(ctx)
        
        # 不需要 E2B，使用 Code Execution
        return StrategyDecision(
            strategy=InvocationStrategy.CODE_EXECUTION,
            reason="Level 3 task without special requirements",
            config={"betas": ["code-execution-2025-05-22"]}
        )
    
    # ============================================================
    # Context 危险区处理
    # ============================================================
    
    def _handle_context_critical(
        self,
        ctx: SelectionContext
    ) -> StrategyDecision:
        """
        Context 使用率 >80% 时的强制精简策略
        
        策略：
        1. 优先 Code Execution（结果精简）
        2. 或 Streaming（边传边处理）
        3. 避免使用 E2B（返回结果可能很大）
        """
        
        warnings = [
            f"⚠️ Context usage critical: {ctx.context_usage:.1%}",
            "Forcing compact strategy to avoid overflow"
        ]
        
        # 能用 Code Execution 就用（结果通常更精简）
        if self._can_use_code_execution(ctx):
            return StrategyDecision(
                strategy=InvocationStrategy.CODE_EXECUTION,
                reason="Context critical, using compact code execution",
                warnings=warnings,
                config={"betas": ["code-execution-2025-05-22"]}
            )
        
        # 或用 Streaming（边传边处理，不累积）
        if self.enable_streaming:
            return StrategyDecision(
                strategy=InvocationStrategy.STREAMING,
                reason="Context critical, using streaming to reduce accumulation",
                warnings=warnings,
                config={"stream": True}
            )
        
        # 兜底：Direct Call + 警告
        warnings.append("⚠️ No compact strategy available, using direct call")
        return StrategyDecision(
            strategy=InvocationStrategy.DIRECT,
            reason="Context critical but no compact option",
            warnings=warnings,
            config={}
        )
    
    # ============================================================
    # E2B 降级处理
    # ============================================================
    
    def _fallback_from_e2b(
        self,
        ctx: SelectionContext
    ) -> StrategyDecision:
        """
        E2B 不可用时的降级策略
        """
        
        warnings = ["⚠️ E2B sandbox unavailable, falling back"]
        
        # 如果任务需要第三方包，无法完全降级
        if ctx.requires_third_party_packages:
            warnings.append(
                "⚠️ Task requires third-party packages, "
                "functionality may be limited"
            )
        
        # 降级到 Code Execution
        if self.enable_code_execution:
            return StrategyDecision(
                strategy=InvocationStrategy.CODE_EXECUTION,
                reason="E2B unavailable, degraded to Code Execution",
                warnings=warnings,
                fallback=InvocationStrategy.DIRECT,
                config={"betas": ["code-execution-2025-05-22"]}
            )
        
        # 再降级到 Direct Call
        warnings.append("⚠️ Code Execution also unavailable, using direct call")
        return StrategyDecision(
            strategy=InvocationStrategy.DIRECT,
            reason="Full degradation to direct call",
            warnings=warnings,
            config={}
        )
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _can_use_code_execution(self, ctx: SelectionContext) -> bool:
        """判断是否可以使用 Code Execution"""
        return (
            self.enable_code_execution and
            not ctx.requires_third_party_packages and
            not ctx.requires_file_system
        )
    
    def _is_vibe_coding_task(self, ctx: SelectionContext) -> bool:
        """判断是否是 Vibe Coding 任务"""
        vibe_keywords = ["streamlit", "gradio", "nextjs", "web app", "dashboard"]
        task_lower = ctx.task_type.lower()
        metadata_str = str(ctx.metadata).lower()
        
        return any(kw in task_lower or kw in metadata_str for kw in vibe_keywords)
    
    def _select_vibe_template(self, ctx: SelectionContext) -> str:
        """选择 Vibe Coding 模板"""
        if "streamlit" in str(ctx.metadata).lower():
            return "streamlit"
        elif "gradio" in str(ctx.metadata).lower():
            return "gradio"
        elif "nextjs" in str(ctx.metadata).lower():
            return "nextjs"
        return "streamlit"  # 默认
    
    def _select_by_task_type(self, ctx: SelectionContext) -> StrategyDecision:
        """根据任务类型选择（兜底逻辑）"""
        
        # 大参数场景
        if ctx.input_size > 10000:
            if self.enable_streaming:
                return StrategyDecision(
                    strategy=InvocationStrategy.STREAMING,
                    reason=f"Large input ({ctx.input_size} bytes), using streaming",
                    config={"stream": True}
                )
        
        # 工具数量过多
        if ctx.tool_count > 30:
            if self.enable_tool_search:
                return StrategyDecision(
                    strategy=InvocationStrategy.TOOL_SEARCH,
                    reason=f"Too many tools ({ctx.tool_count}), using search",
                    config={"defer_loading": True}
                )
        
        # 默认：Direct Call
        return StrategyDecision(
            strategy=InvocationStrategy.DIRECT,
            reason="Default strategy for simple task",
            config={}
        )
    
    # ============================================================
    # 统计和监控
    # ============================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取选择统计"""
        return {
            "total_selections": self.stats["total_selections"],
            "strategy_distribution": self.stats["strategy_counts"],
            "fallback_rate": (
                self.stats["fallback_count"] / self.stats["total_selections"]
                if self.stats["total_selections"] > 0 else 0
            )
        }


# ============================================================
# 工厂函数
# ============================================================

def create_invocation_selector_v2(**kwargs) -> InvocationSelectorV2:
    """创建 V2 选择器"""
    return InvocationSelectorV2(**kwargs)
```

---

## 📊 性能优化

### 1. 缓存决策结果

```python
from functools import lru_cache
import hashlib

class CachedInvocationSelector(InvocationSelectorV2):
    """
    带缓存的选择器
    
    对于相同输入，直接返回缓存结果（提升性能）
    """
    
    @lru_cache(maxsize=128)
    def _select_cached(self, ctx_hash: str) -> StrategyDecision:
        """缓存的选择逻辑"""
        # 实际选择逻辑
        pass
    
    def select(self, ctx: SelectionContext) -> StrategyDecision:
        """带缓存的选择"""
        # 计算 context hash
        ctx_hash = self._hash_context(ctx)
        
        # 尝试从缓存获取
        cached = self._select_cached(ctx_hash)
        if cached:
            logger.debug(f"✅ Cache hit for invocation strategy")
            return cached
        
        # Cache miss，执行选择
        decision = super().select(ctx)
        return decision
```

### 2. 异步预热

```python
class PrewarmingSelector(InvocationSelectorV2):
    """
    预热选择器
    
    在请求到达前预先初始化 E2B 会话（减少冷启动）
    """
    
    async def prewarm_e2b(self):
        """预热 E2B 沙箱"""
        if not self.enable_e2b:
            return
        
        logger.info("🔥 Pre-warming E2B sandbox...")
        
        # 创建一个临时会话并保持活跃
        # （具体实现省略）
        pass
```

---

## 📈 预期收益

| 指标 | V3.7 | V4 (V2 Selector) | 改进 |
|------|------|------------------|------|
| **Context 使用率** | 平均 80% | 平均 50% | ↓37.5% |
| **选择准确率** | 85% | 95% | ↑11.8% |
| **降级成功率** | 0% (未实现) | 100% | ✅ 新增 |
| **E2B 利用率** | 20% | 60% | ↑200% |
| **平均响应延迟** | 3-5s | 2-3s | ↓40% |

---

## 🚀 实施计划

### Week 1: 核心实现
- [ ] 实现 `InvocationSelectorV2` 主逻辑
- [ ] 集成 tool level 信息（从 capabilities.yaml）
- [ ] 实现 Context-aware 选择

### Week 2: 降级策略
- [ ] 实现 E2B 降级逻辑
- [ ] 实现 Code Execution 降级逻辑
- [ ] 添加警告和日志

### Week 3: 测试和优化
- [ ] 端到端测试（所有场景）
- [ ] 性能基准测试
- [ ] 缓存优化

---

## 🎯 Claude Skills 与调用策略的有效结合

### 核心问题

> Claude Skills 如何与 Direct Call / Code Execution / Programmatic / E2B Sandbox 这几种调用方式有效结合，不产生冲突？

### 关键认识：Skills 是"能力"，Strategy 是"方式"

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Claude Skills vs Invocation Strategy                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Claude Skills = "专家知识包"                                               │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • 包含：指令 + 代码 + 资源                                                 │
│   • 执行环境：Anthropic 托管的 VM（带文件系统）                              │
│   • 触发方式：通过 container.skills 参数                                     │
│   • 必需工具：code_execution_20250825                                       │
│                                                                              │
│   Invocation Strategy = "调用方式"                                          │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   • Direct Call：标准 Function Call                                         │
│   • Code Execution：Claude 内置代码执行（与 Skills 同环境）                 │
│   • Programmatic：程序化编排                                                │
│   • E2B Sandbox：第三方沙箱（独立于 Skills）                                │
│   • Streaming：流式传输                                                     │
│                                                                              │
│   关系：Skills 运行在 Code Execution 环境中，与 E2B 是并行的两条路径         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 执行环境对比

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         两种执行环境对比                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Claude VM (Skills 执行环境)           E2B Sandbox (独立环境)               │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━        │
│                                                                              │
│   ✅ Anthropic 官方托管               ✅ 第三方托管（E2B.dev）              │
│   ✅ 文件系统访问                     ✅ 完整 Linux 环境                   │
│   ✅ Bash 命令执行                    ✅ 任意第三方包                       │
│   ✅ Progressive Disclosure          ✅ 持久化文件系统                     │
│   ✅ 官方 Skills 支持                 ✅ 网络访问                           │
│   ❌ 有限的第三方包                   ✅ Docker-like 隔离                   │
│   ❌ 无网络访问（默认）               ❌ 无 Progressive Disclosure          │
│                                                                              │
│   适用场景：                          适用场景：                            │
│   • Excel/PPT/PDF/Word 生成           • 数据分析（pandas, numpy）          │
│   • 配置生成                          • 网络请求（爬虫、API 调用）         │
│   • 自定义 Skills                     • 长时运行任务                       │
│   • 文档处理工作流                    • 复杂应用（Streamlit/Gradio）       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 结合方案：三层决策模型

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Skills + Strategy 三层决策模型                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   用户请求                                                                   │
│       │                                                                      │
│       ▼                                                                      │
│   ┌──────────────────────────────────────────────────────────────────────┐ │
│   │ Layer 1: 能力选择（CapabilityRouter）                                 │ │
│   │   "需要什么能力？"                                                    │ │
│   │                                                                       │ │
│   │   → Skills (xlsx, pptx, pdf, docx, custom)                           │ │
│   │   → Tools (web_search, file_ops, api_calling)                        │ │
│   │   → 混合 (Skills + Tools)                                            │ │
│   └────────────────────────────────────┬─────────────────────────────────┘ │
│                                        │                                    │
│                                        ▼                                    │
│   ┌──────────────────────────────────────────────────────────────────────┐ │
│   │ Layer 2: 环境选择（EnvironmentSelector）                              │ │
│   │   "在哪里执行？"                                                      │ │
│   │                                                                       │ │
│   │   选择 Skills?                                                        │ │
│   │       │                                                               │ │
│   │       ├── YES → Claude VM（必须使用 code_execution 工具）            │ │
│   │       │         └── Skills 自带环境，无需额外沙箱                     │ │
│   │       │                                                               │ │
│   │       └── NO → 继续判断                                              │ │
│   │                 │                                                     │ │
│   │                 ├── 需要第三方包? → E2B Sandbox                      │ │
│   │                 ├── 需要网络访问? → E2B Sandbox                      │ │
│   │                 ├── 简单计算?     → Claude Code Execution            │ │
│   │                 └── 标准工具?     → Direct Call                      │ │
│   │                                                                       │ │
│   └────────────────────────────────────┬─────────────────────────────────┘ │
│                                        │                                    │
│                                        ▼                                    │
│   ┌──────────────────────────────────────────────────────────────────────┐ │
│   │ Layer 3: 策略选择（InvocationSelector）                               │ │
│   │   "如何调用？"                                                        │ │
│   │                                                                       │ │
│   │   环境 = Claude VM (含 Skills)                                       │ │
│   │       → Direct Call + Skills Container                               │ │
│   │       → Code Execution + Skills（如果需要额外逻辑）                  │ │
│   │                                                                       │ │
│   │   环境 = E2B Sandbox                                                  │ │
│   │       → Programmatic E2B                                             │ │
│   │       → Vibe Coding（复杂应用）                                      │ │
│   │                                                                       │ │
│   │   环境 = Claude 原生                                                  │ │
│   │       → Direct Call                                                  │ │
│   │       → Code Execution                                               │ │
│   │       → Programmatic                                                 │ │
│   │                                                                       │ │
│   └──────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 策略组合矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Skills + Strategy 组合矩阵                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                           是否使用 Skills                                    │
│                        ┌────────────────────────────────────────────────┐   │
│                        │        YES (需要文档生成)                      │   │
│   调用策略              │        NO  (不需要文档生成)                     │   │
│   ━━━━━━━━             └────────────────────────────────────────────────┘   │
│                                                                              │
│   Direct Call          │  ✅ 兼容：Skills + container 参数              │   │
│                        │  ✅ 兼容：标准 Function Call                   │   │
│                        │  使用场景：单个 Skill 简单调用                 │   │
│                        │                                                │   │
│   Code Execution       │  ✅ 同一环境：Skills 就是运行在这里             │   │
│   (Claude VM)          │  ✅ 兼容：简单代码执行                         │   │
│                        │  使用场景：配置生成 + Skills 调用              │   │
│                        │                                                │   │
│   Programmatic         │  ⚠️ 部分兼容：多步骤需要考虑 Skills 调用顺序   │   │
│                        │  ✅ 兼容：多工具编排                           │   │
│                        │  使用场景：复杂工作流（可能混合 Skills+Tools）  │   │
│                        │                                                │   │
│   E2B Sandbox          │  ❌ 不在同一环境：Skills 不在 E2B 中运行       │   │
│                        │  ✅ 兼容：第三方包、网络访问                   │   │
│                        │  使用场景：数据分析、爬虫（不涉及文档生成）    │   │
│                        │                                                │   │
│   Streaming            │  ⚠️ 部分兼容：文件结果无法流式                  │   │
│                        │  ✅ 兼容：大参数传输                           │   │
│                        │  使用场景：大数据处理                          │   │
│                        │                                                │   │
│   混合使用              │  ✅ 推荐：Skills 生成文档 + E2B 处理数据      │   │
│   (Skills + E2B)       │  顺序：E2B 预处理 → Skills 生成文档            │   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 具体场景示例

```python
# ============================================================
# 场景 1: 纯 Skills（Excel 生成）
# ============================================================
# 用户请求: "生成一个销售报表 Excel"

# Layer 1: 能力选择
capabilities_needed = ["data_analysis", "xlsx_generation"]
selected = ["xlsx"]  # Pre-built Skill

# Layer 2: 环境选择
environment = "claude_vm"  # Skills 必须在 Claude VM

# Layer 3: 策略选择
strategy = InvocationStrategy.DIRECT  # 简单 Skills 调用

# API 调用
response = client.beta.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=4096,
    betas=["code-execution-2025-08-25", "skills-2025-10-02"],
    container={
        "skills": [
            {"type": "anthropic", "skill_id": "xlsx", "version": "latest"}
        ]
    },
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[{"role": "user", "content": "生成一个销售报表 Excel..."}]
)


# ============================================================
# 场景 2: E2B + Skills 混合（数据分析 + 报告生成）
# ============================================================
# 用户请求: "分析这份 CSV 数据，用 pandas 处理后生成 Excel 报告"

# Layer 1: 能力选择
capabilities_needed = ["data_analysis", "xlsx_generation"]
selected = ["e2b_sandbox", "xlsx"]  # E2B + Skills

# Layer 2: 环境选择
# ⚠️ 关键：需要两步走
# Step 1: E2B Sandbox 做数据分析（需要 pandas）
# Step 2: Claude VM (Skills) 生成 Excel

# Layer 3: 策略选择
strategy = InvocationStrategy.PROGRAMMATIC  # 多步骤编排

# Step 1: E2B 数据分析
e2b_result = await e2b_sandbox.run("""
import pandas as pd
df = pd.read_csv('data.csv')
summary = df.describe().to_dict()
""")

# Step 2: Skills 生成 Excel（将 E2B 结果传入）
response = client.beta.messages.create(
    betas=["code-execution-2025-08-25", "skills-2025-10-02"],
    container={
        "skills": [
            {"type": "anthropic", "skill_id": "xlsx", "version": "latest"}
        ]
    },
    messages=[{
        "role": "user",
        "content": f"基于这些统计结果生成 Excel 报告：{e2b_result}"
    }]
)


# ============================================================
# 场景 3: 纯 E2B（复杂数据处理，不需要文档生成）
# ============================================================
# 用户请求: "用 pandas 分析 CSV，生成可视化图表"

# Layer 1: 能力选择
capabilities_needed = ["data_analysis", "data_visualization"]
selected = ["e2b_sandbox"]  # 纯 E2B，不需要 Skills

# Layer 2: 环境选择
environment = "e2b"  # 需要第三方包

# Layer 3: 策略选择
strategy = InvocationStrategy.PROGRAMMATIC_E2B

# API 调用（不带 Skills container）
# 直接调用 E2B Sandbox


# ============================================================
# 场景 4: Custom Skills + Direct Call
# ============================================================
# 用户请求: "使用公司财务分析 Skill 处理这份报表"

# Layer 1: 能力选择
capabilities_needed = ["financial_analysis"]
selected = ["financial-analyzer"]  # Custom Skill

# Layer 2: 环境选择
environment = "claude_vm"

# Layer 3: 策略选择
strategy = InvocationStrategy.DIRECT

# API 调用
response = client.beta.messages.create(
    betas=["code-execution-2025-08-25", "skills-2025-10-02"],
    container={
        "skills": [
            {"type": "custom", "skill_id": "skill_abc123", "version": "latest"}
        ]
    },
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[{"role": "user", "content": "分析财务报表..."}]
)
```

### 更新后的 InvocationSelector V2

```python
# core/tool/capability/invocation_v2.py (更新版)

class InvocationStrategy(Enum):
    """调用策略（增强版 - 含 Skills 支持）"""
    
    # Claude 原生
    DIRECT = "direct"                           # 标准 Function Call
    CODE_EXECUTION = "code_execution"           # Claude 内置代码执行
    
    # Skills 相关（运行在 Claude VM）
    SKILLS_DIRECT = "skills_direct"             # 🆕 Skills 简单调用
    SKILLS_COMPOSITE = "skills_composite"       # 🆕 Skills 复合调用
    
    # E2B 相关（独立沙箱）
    PROGRAMMATIC_E2B = "programmatic_e2b"       # E2B 沙箱
    VIBE_CODING = "vibe_coding"                 # E2B Vibe Coding
    
    # 混合
    HYBRID_E2B_SKILLS = "hybrid_e2b_skills"     # 🆕 E2B + Skills 混合
    
    # 其他
    PROGRAMMATIC = "programmatic"               # 程序化调用
    STREAMING = "streaming"                     # 细粒度流式
    TOOL_SEARCH = "tool_search"                 # 工具搜索


@dataclass
class StrategyDecision:
    """策略决策结果（增强版）"""
    strategy: InvocationStrategy
    reason: str
    fallback: Optional[InvocationStrategy] = None
    warnings: List[str] = None
    
    # 🆕 Skills 相关配置
    skills: List[Dict] = None           # container.skills 配置
    skills_environment: str = None      # "claude_vm" 或 "none"
    
    # 🆕 E2B 相关配置
    e2b_required: bool = False
    e2b_template: str = None            # "base", "streamlit", "gradio"
    
    # 执行配置
    config: Dict[str, Any] = None
    betas: List[str] = None


class InvocationSelectorV2:
    """
    调用策略选择器 V2（Skills 集成版）
    
    核心改进：
    1. Skills 感知：识别是否需要 Skills 及其类型
    2. 环境选择：Claude VM vs E2B Sandbox
    3. 混合策略：支持 E2B + Skills 的组合
    """
    
    # Skills 相关的 Beta 版本
    SKILLS_BETAS = [
        "code-execution-2025-08-25",
        "skills-2025-10-02",
        "files-api-2025-04-14"
    ]
    
    def select(self, ctx: SelectionContext) -> StrategyDecision:
        """
        主选择逻辑（Skills 感知版）
        
        决策顺序：
        1. 检查是否需要 Skills
        2. 如果需要 Skills，选择 Skills 策略
        3. 如果不需要 Skills，使用原有逻辑
        4. 处理混合场景（E2B + Skills）
        """
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1️⃣ Skills 需求检测
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        skills_needed = self._detect_skills_needed(ctx)
        e2b_needed = self._detect_e2b_needed(ctx)
        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 2️⃣ 四种场景判断
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        # 场景 A: 只需要 Skills
        if skills_needed and not e2b_needed:
            return self._select_skills_strategy(ctx, skills_needed)
        
        # 场景 B: 只需要 E2B
        if e2b_needed and not skills_needed:
            return self._select_e2b_strategy(ctx)
        
        # 场景 C: 混合（E2B + Skills）
        if e2b_needed and skills_needed:
            return self._select_hybrid_strategy(ctx, skills_needed)
        
        # 场景 D: 都不需要（标准工具）
        return self._select_standard_strategy(ctx)
    
    # ============================================================
    # Skills 需求检测
    # ============================================================
    
    def _detect_skills_needed(self, ctx: SelectionContext) -> List[Dict]:
        """
        检测是否需要 Skills
        
        返回需要的 Skills 列表
        """
        skills = []
        
        # 检查能力需求
        capability_to_skill = {
            "xlsx_generation": {"type": "anthropic", "skill_id": "xlsx"},
            "pptx_generation": {"type": "anthropic", "skill_id": "pptx"},
            "pdf_generation": {"type": "anthropic", "skill_id": "pdf"},
            "docx_generation": {"type": "anthropic", "skill_id": "docx"},
            "excel": {"type": "anthropic", "skill_id": "xlsx"},
            "powerpoint": {"type": "anthropic", "skill_id": "pptx"},
        }
        
        # 从 ctx.tools 或 ctx.metadata 中检测
        for tool in ctx.tools:
            tool_lower = tool.lower()
            for cap, skill in capability_to_skill.items():
                if cap in tool_lower or tool_lower in cap:
                    if skill not in skills:
                        skills.append({**skill, "version": "latest"})
        
        # 检查自定义 Skills
        if ctx.metadata and "custom_skills" in ctx.metadata:
            for custom_skill_id in ctx.metadata["custom_skills"]:
                skills.append({
                    "type": "custom",
                    "skill_id": custom_skill_id,
                    "version": "latest"
                })
        
        return skills
    
    def _detect_e2b_needed(self, ctx: SelectionContext) -> bool:
        """检测是否需要 E2B Sandbox"""
        return (
            ctx.requires_third_party_packages or
            ctx.requires_file_system or
            ctx.requires_network
        )
    
    # ============================================================
    # Skills 策略选择
    # ============================================================
    
    def _select_skills_strategy(
        self,
        ctx: SelectionContext,
        skills: List[Dict]
    ) -> StrategyDecision:
        """
        选择 Skills 策略
        
        策略：
        - 单个 Skill → SKILLS_DIRECT
        - 多个 Skill → SKILLS_COMPOSITE
        """
        
        if len(skills) == 1:
            return StrategyDecision(
                strategy=InvocationStrategy.SKILLS_DIRECT,
                reason=f"Single skill needed: {skills[0]['skill_id']}",
                skills=skills,
                skills_environment="claude_vm",
                betas=self.SKILLS_BETAS,
                config={
                    "requires_code_execution_tool": True
                }
            )
        else:
            return StrategyDecision(
                strategy=InvocationStrategy.SKILLS_COMPOSITE,
                reason=f"Multiple skills needed: {[s['skill_id'] for s in skills]}",
                skills=skills,
                skills_environment="claude_vm",
                betas=self.SKILLS_BETAS,
                config={
                    "requires_code_execution_tool": True,
                    "skill_orchestration": True
                }
            )
    
    # ============================================================
    # 混合策略选择
    # ============================================================
    
    def _select_hybrid_strategy(
        self,
        ctx: SelectionContext,
        skills: List[Dict]
    ) -> StrategyDecision:
        """
        选择混合策略（E2B + Skills）
        
        执行顺序：
        1. E2B Sandbox 做数据处理（第三方包）
        2. Skills 做文档生成
        
        这是两次独立的 API 调用，需要在 Agent 层编排
        """
        
        return StrategyDecision(
            strategy=InvocationStrategy.HYBRID_E2B_SKILLS,
            reason=(
                f"Hybrid workflow: "
                f"E2B for data processing, "
                f"Skills for document generation"
            ),
            skills=skills,
            skills_environment="claude_vm",
            e2b_required=True,
            betas=self.SKILLS_BETAS,
            config={
                "requires_code_execution_tool": True,
                "execution_order": ["e2b", "skills"],
                "e2b_result_passthrough": True
            },
            warnings=[
                "⚠️ 混合策略需要两步执行：",
                "  1. E2B 处理数据（pandas 等）",
                "  2. Skills 生成文档"
            ]
        )
```

### 🔑 核心设计原则：Prompt 引导 > 硬编码规则

根据 Claude Platform 官方文档：

> **"Claude automatically uses them when relevant to your request"**  
> **"keep your Skills list consistent across requests"**（利于 Prompt Cache）

**正确的设计哲学**：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Skills 策略选择：两种设计对比                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ❌ 错误方式（之前的设计）：外层硬编码规则决策                               │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   用户请求 → 外层代码判断 → 动态修改 Skills 列表 → API 调用                 │
│                                                                              │
│   问题：                                                                     │
│   • 破坏 Prompt Cache（Skills 列表变化）                                    │
│   • 硬编码规则无法覆盖所有场景                                              │
│   • 违背 Claude 的自主决策能力                                              │
│                                                                              │
│   ✅ 正确方式（推荐设计）：Prompt 引导 + Claude 自主决策                     │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   配置层：预设固定的 Skills 列表（按用户/项目配置）                          │
│       ↓                                                                      │
│   Prompt 层：System Prompt 描述何时使用哪个 Skill                           │
│       ↓                                                                      │
│   运行时：Claude 自主决定是否触发 Skill                                     │
│                                                                              │
│   优势：                                                                     │
│   • Skills 列表稳定 → Prompt Cache 有效                                     │
│   • Prompt 引导灵活 → 可随时调整策略                                        │
│   • Claude 自主决策 → 充分利用模型智能                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 配置层：固定 Skills 列表

```python
# config/skills_config.py

# 按用户/项目预配置 Skills 列表（保持稳定，利于缓存）
SKILLS_PRESETS = {
    # 企业办公场景
    "enterprise_office": {
        "skills": [
            {"type": "anthropic", "skill_id": "xlsx", "version": "latest"},
            {"type": "anthropic", "skill_id": "pptx", "version": "latest"},
            {"type": "anthropic", "skill_id": "pdf", "version": "latest"},
            {"type": "anthropic", "skill_id": "docx", "version": "latest"},
        ],
        "betas": [
            "code-execution-2025-08-25",
            "skills-2025-10-02",
            "files-api-2025-04-14"
        ]
    },
    
    # 数据分析场景（不需要文档生成）
    "data_analysis": {
        "skills": [],  # 不配置 Skills，使用 E2B
        "betas": []
    },
    
    # 混合场景（办公 + 数据）
    "hybrid": {
        "skills": [
            {"type": "anthropic", "skill_id": "xlsx", "version": "latest"},
            {"type": "anthropic", "skill_id": "pptx", "version": "latest"},
        ],
        "betas": [
            "code-execution-2025-08-25",
            "skills-2025-10-02",
            "files-api-2025-04-14"
        ]
    }
}

def get_skills_for_user(user_id: str, project_type: str = "enterprise_office") -> dict:
    """
    根据用户和项目类型获取 Skills 配置
    
    返回固定配置，不动态修改
    """
    return SKILLS_PRESETS.get(project_type, SKILLS_PRESETS["enterprise_office"])
```

### Prompt 层：引导 Claude 自主决策

```python
# prompts/skills_guidance_prompt.py

SKILLS_GUIDANCE_PROMPT = """
## 可用能力与执行环境

你可以使用以下两种执行环境来完成任务：

### 1. Claude Skills（文档生成环境）
适用场景：需要创建专业文档时使用
- **xlsx**: 创建 Excel 电子表格（数据分析报表、财务模型、图表）
- **pptx**: 创建 PowerPoint 演示文稿（商业汇报、培训材料）
- **pdf**: 创建 PDF 文档（正式报告、合同文档）
- **docx**: 创建 Word 文档（长文档、结构化内容）

**何时使用 Skills**：
- 用户明确要求生成 Excel/PPT/PDF/Word 文件
- 需要创建可下载的专业文档
- 输出需要特定格式（表格、图表、幻灯片）

**何时不使用 Skills**：
- 只需要文本回答
- 数据分析结果用文本展示即可
- 用户没有要求特定文档格式

### 2. E2B Sandbox（代码执行环境）
适用场景：需要第三方 Python 包或网络访问时使用
- 支持 pandas、numpy、matplotlib 等数据分析库
- 支持 requests、httpx 等网络请求库
- 支持文件系统操作和持久化

**何时使用 E2B**：
- 需要 pandas 进行数据分析
- 需要爬取网页或调用外部 API
- 需要复杂的数据处理逻辑
- 需要生成图表但不需要导出为文档

### 3. 混合使用（E2B + Skills）
当任务同时需要数据处理和文档生成时：
1. 先用 E2B Sandbox 处理数据（pandas 分析、API 调用）
2. 再用 Skills 生成最终文档（将处理结果导入 Excel/PPT）

**示例**：
- "用 pandas 分析 CSV 并生成 Excel 报表" → E2B 分析 → Skills 生成 Excel
- "爬取数据后制作 PPT" → E2B 爬取 → Skills 生成 PPT

### 决策原则

**自主判断**：根据用户请求的实际需求选择最合适的工具，不要过度使用。

**最小化原则**：
- 能用文本回答就不生成文档
- 能用简单工具就不用复杂环境
- 能一步完成就不分多步

**用户意图优先**：如果用户明确要求某种格式，优先满足用户需求。
"""


# 更精简的版本（节省 tokens）
SKILLS_GUIDANCE_PROMPT_COMPACT = """
## 执行环境选择

### Skills（文档生成）
- xlsx/pptx/pdf/docx：创建可下载的专业文档
- 触发条件：用户明确要求生成特定格式文件

### E2B Sandbox（代码执行）
- pandas/numpy/requests：数据分析、网络请求
- 触发条件：需要第三方库或网络访问

### 混合使用
先 E2B 处理数据 → 再 Skills 生成文档

### 原则
- 能用文本就不生成文档
- 根据用户实际需求选择
"""
```

### 更新后的 RVR Loop（Prompt 驱动）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               RVR Loop（Prompt 引导 + Claude 自主决策版）                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  初始化（一次性）                                                            │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  • 根据用户/项目配置加载固定的 Skills 列表                                   │
│  • Skills 列表在会话期间保持不变（利于 Prompt Cache）                        │
│  • System Prompt 包含 SKILLS_GUIDANCE_PROMPT                                │
│                                                                              │
│  User Input                                                                  │
│      │                                                                       │
│      ▼                                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 1: 构建请求（无外层决策逻辑）                                    │   │
│  │                                                                       │   │
│  │   # 直接使用预配置的 Skills 列表                                      │   │
│  │   skills_config = get_skills_for_user(user_id, project_type)         │   │
│  │                                                                       │   │
│  │   request = {                                                         │   │
│  │       "model": "claude-sonnet-4-5",                                   │   │
│  │       "system": BASE_PROMPT + SKILLS_GUIDANCE_PROMPT,                 │   │
│  │       "container": {"skills": skills_config["skills"]},  # 固定列表   │   │
│  │       "tools": [..., e2b_sandbox, code_execution],                   │   │
│  │       "messages": messages                                            │   │
│  │   }                                                                   │   │
│  │                                                                       │   │
│  └───────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 2: Claude 自主决策（在 Thinking 中）                             │   │
│  │                                                                       │   │
│  │   Claude 内部思考：                                                   │   │
│  │   ┌────────────────────────────────────────────────────────────────┐ │   │
│  │   │ "用户请求：分析销售数据并生成 Excel 报表"                       │ │   │
│  │   │                                                                 │ │   │
│  │   │ 分析：                                                          │ │   │
│  │   │ 1. 需要数据分析 → 可能需要 pandas → E2B Sandbox                │ │   │
│  │   │ 2. 需要生成 Excel → 需要 xlsx Skill                            │ │   │
│  │   │ 3. 这是混合场景 → 先 E2B 分析，再 Skills 生成                   │ │   │
│  │   │                                                                 │ │   │
│  │   │ 决策：使用 E2B Sandbox + xlsx Skill                            │ │   │
│  │   └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                       │   │
│  │   ⚠️ 注意：决策完全由 Claude 在 Thinking 中完成                      │   │
│  │   外层代码不需要判断"用什么 Skill"                                   │   │
│  │                                                                       │   │
│  └───────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 3: RVR Turn Loop（Claude 执行决策）                              │   │
│  │                                                                       │   │
│  │   Claude 自主选择执行路径：                                           │   │
│  │                                                                       │   │
│  │   情况 A: 用户只需要文本回答                                          │   │
│  │       → Claude 直接回答，不触发任何 Skill/Tool                        │   │
│  │                                                                       │   │
│  │   情况 B: 用户需要文档                                                │   │
│  │       → Claude 触发 xlsx/pptx/pdf/docx Skill                         │   │
│  │       → code_execution 工具自动执行 Skill                            │   │
│  │       → 返回 file_id                                                  │   │
│  │                                                                       │   │
│  │   情况 C: 用户需要数据分析                                            │   │
│  │       → Claude 触发 e2b_sandbox 工具                                  │   │
│  │       → 在沙箱中执行 pandas/numpy 代码                                │   │
│  │       → 返回分析结果                                                  │   │
│  │                                                                       │   │
│  │   情况 D: 用户需要数据分析 + 文档生成                                  │   │
│  │       → Turn 1: Claude 触发 e2b_sandbox 分析数据                      │   │
│  │       → Turn 2: Claude 触发 xlsx Skill 生成报表                       │   │
│  │       → 返回 file_id                                                  │   │
│  │                                                                       │   │
│  └───────────────────────────────────┬──────────────────────────────────┘   │
│                                      │                                       │
│                                      ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Step 4: Complete                                                     │   │
│  │                                                                       │   │
│  │   # 外层只负责处理结果，不负责决策                                    │   │
│  │   if response contains file_id:                                      │   │
│  │       file_path = files_api.download(file_id)                        │   │
│  │       emit_file_generated(file_path)                                 │   │
│  │                                                                       │   │
│  │   emit_message_stop()                                                │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 外层代码简化（去除决策逻辑）

```python
# core/agent/simple/simple_agent.py (简化版)

class SimpleAgent:
    """
    简化版 Agent
    
    核心原则：
    - 外层不做 Skills/E2B 决策
    - 决策完全由 Claude 在 Thinking 中完成
    - 外层只负责配置和结果处理
    """
    
    def __init__(
        self,
        user_id: str,
        project_type: str = "enterprise_office"
    ):
        # 加载固定的 Skills 配置（不动态修改）
        self.skills_config = get_skills_for_user(user_id, project_type)
        
        # 构建 System Prompt（包含引导规则）
        self.system_prompt = (
            BASE_PROMPT +
            SKILLS_GUIDANCE_PROMPT +
            TOOLS_DESCRIPTION
        )
    
    async def chat(self, messages: List[dict]) -> AsyncIterator[StreamEvent]:
        """
        聊天方法
        
        注意：外层不判断"该用什么 Skill"
        而是将所有可用能力告诉 Claude，让 Claude 自主决策
        """
        
        # 1. 构建请求（使用固定配置）
        response = await self.llm.create_message(
            model="claude-sonnet-4-5",
            max_tokens=8192,
            system=self.system_prompt,
            betas=self.skills_config.get("betas", []),
            container={
                "skills": self.skills_config.get("skills", [])  # 固定列表
            },
            tools=[
                # 所有工具都提供，Claude 自主选择
                {"type": "code_execution_20250825", "name": "code_execution"},
                e2b_sandbox_tool,
                web_search_tool,
                plan_todo_tool,
                # ... 其他工具
            ],
            messages=messages,
            stream=True
        )
        
        # 2. 处理流式响应
        async for event in response:
            yield event
            
            # 3. 检测并处理文件生成
            if event.type == "file_generated":
                file_path = await self.files_api.download(event.file_id)
                yield FileDownloadedEvent(file_path=file_path)
```

### 配置 vs 运行时职责分离

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    职责分离：配置层 vs 运行时                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   配置层（人工决策，一次性）                                                 │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   决策内容：                                                                 │
│   • 为用户/项目预配置哪些 Skills（企业办公 vs 数据分析 vs 混合）            │
│   • 是否启用 E2B Sandbox                                                    │
│   • 是否启用特定工具（web_search, api_calling）                             │
│                                                                              │
│   决策时机：                                                                 │
│   • 用户注册时                                                               │
│   • 项目创建时                                                               │
│   • 管理员配置时                                                             │
│                                                                              │
│   决策方式：                                                                 │
│   • 管理后台配置                                                             │
│   • YAML 配置文件                                                            │
│   • 环境变量                                                                 │
│                                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   运行时（Claude 自主决策，每次请求）                                        │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│   决策内容：                                                                 │
│   • 本次请求是否需要生成文档                                                 │
│   • 使用哪个 Skill（xlsx vs pptx vs pdf）                                   │
│   • 是否需要先用 E2B 处理数据                                               │
│   • 执行顺序如何安排                                                         │
│                                                                              │
│   决策时机：                                                                 │
│   • 每次用户请求时                                                           │
│   • 在 Claude 的 Extended Thinking 中完成                                   │
│                                                                              │
│   决策方式：                                                                 │
│   • System Prompt 引导                                                       │
│   • Claude 自主推理                                                          │
│   • 无需外层代码判断                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 总结：正确的 Skills 集成方式

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Skills 集成最佳实践                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ✅ DO（推荐）                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. 预配置固定的 Skills 列表（按用户/项目）                                 │
│      → 利于 Prompt Cache                                                    │
│                                                                              │
│   2. 通过 System Prompt 引导 Claude 何时使用 Skills                         │
│      → 灵活可调，不影响代码                                                  │
│                                                                              │
│   3. 让 Claude 在 Thinking 中自主决策                                       │
│      → 充分利用模型智能                                                      │
│                                                                              │
│   4. 外层代码只负责配置和结果处理                                            │
│      → 简化逻辑，减少 bug                                                    │
│                                                                              │
│   ❌ DON'T（避免）                                                           │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. 外层代码判断"这次请求该用什么 Skill"                                   │
│      → 破坏缓存，增加复杂度                                                  │
│                                                                              │
│   2. 每次请求动态修改 Skills 列表                                            │
│      → 破坏 Prompt Cache                                                    │
│                                                                              │
│   3. 硬编码规则（if "excel" in query → use xlsx）                          │
│      → 无法覆盖所有场景，维护困难                                            │
│                                                                              │
│   4. 强制 Claude 必须使用某个 Skill                                          │
│      → 可能导致不必要的文档生成                                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 最佳实践总结

```
┌─────────────────────────────────────────────────────────────────────────────┐
│               Claude Skills + Invocation Strategy 最佳实践                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ✅ DO（推荐）                                                              │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. 文档生成任务 → 优先使用 Skills（xlsx/pptx/pdf/docx）                   │
│   2. 需要第三方包 → 优先使用 E2B Sandbox                                    │
│   3. 混合场景 → E2B 预处理 → Skills 生成文档（两步走）                      │
│   4. Skills 简单调用 → SKILLS_DIRECT 策略                                   │
│   5. 版本管理 → 生产环境 pin 版本，开发环境用 latest                        │
│                                                                              │
│   ❌ DON'T（避免）                                                           │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. 在 E2B 中尝试使用 Skills（它们是不同环境）                             │
│   2. 未传递 code_execution 工具就调用 Skills（会失败）                      │
│   3. 忘记传递 Skills 相关的 Beta headers                                    │
│   4. 混合场景中尝试单次 API 调用完成（需要拆分）                            │
│   5. 在 Skills 中使用第三方包（Skills 环境有限制）                          │
│                                                                              │
│   ⚠️ CAUTION（注意）                                                         │
│   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                              │
│   1. Skills 生成时间较长（1-2 分钟），需要考虑超时                           │
│   2. Skills 生成的文件需要通过 Files API 下载                               │
│   3. Skills list 变化会破坏 Prompt Cache                                    │
│   4. 混合策略的 Context 传递需要仔细设计                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔗 相关文档

- [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md)
- [12-CONTEXT_ENGINEERING_OPTIMIZATION.md](./12-CONTEXT_ENGINEERING_OPTIMIZATION.md)
- [14-CLAUDE_SKILLS_DEEP_DIVE.md](./14-CLAUDE_SKILLS_DEEP_DIVE.md)
- [Effective harnesses for long-running agents - Anthropic](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

