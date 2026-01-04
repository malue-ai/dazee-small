# Capability 模块重构计划（V3）

> 📅 **创建日期**: 2025-12-30  
> 📅 **更新日期**: 2025-12-30  
> 🎯 **状态**: 准备实施

---

## 📋 背景与全面分析

### 当前 core/ 目录结构

```
core/
│
├── 📁 分散在根目录（需要重构）
│   ├── capability_registry.py   # 能力注册表（从 YAML 加载）
│   ├── capability_router.py     # 能力路由器（智能选择）
│   ├── invocation_selector.py   # 调用方式选择器
│   └── skills_manager.py        # Skills 管理器
│
├── 📁 tool/（已经是包结构 ✅）
│   ├── __init__.py
│   ├── selector.py              # ToolSelector（依赖 Registry + Router）
│   └── executor.py              # ToolExecutor（依赖 Registry）
│
└── 📁 context/（已经是包结构 ✅）
    ├── __init__.py
    ├── conversation.py          # Context（对话上下文）
    └── runtime.py               # RuntimeContext（运行时状态）
```

### 模块依赖关系分析

```
                    ┌─────────────────────────────────────────────┐
                    │            capabilities.yaml               │
                    └─────────────────────────────────────────────┘
                                         ↓ 加载
                    ┌─────────────────────────────────────────────┐
                    │          CapabilityRegistry                │
                    │  • 加载 Tools 配置                          │
                    │  • 提供查询接口                              │
                    └─────────────────────────────────────────────┘
                         ↓                           ↓
        ┌────────────────────────────┐   ┌────────────────────────────┐
        │      CapabilityRouter      │   │        SkillsManager       │
        │  • 智能评分算法              │   │  • 扫描 skills/library/    │
        │  • 上下文感知路由            │   │  • 渐进式加载内容           │
        │  • select_tools_for_cap... │   │  • 独立运行 ❌ 未整合        │
        └────────────────────────────┘   └────────────────────────────┘
                         ↓                           ↓
                    ┌─────────────────────────────────────────────┐
                    │               ToolSelector                 │
                    │  • 依赖 Registry + Router                   │
                    │  • select() 方法                            │
                    │  • get_tools_for_llm()                     │
                    │  ⚠️ 和 Router.select_tools_for... 重叠      │
                    └─────────────────────────────────────────────┘
                                         ↓
                    ┌─────────────────────────────────────────────┐
                    │               ToolExecutor                 │
                    │  • 依赖 Registry                            │
                    │  • 动态加载工具实现                          │
                    │  • execute() 执行工具                       │
                    └─────────────────────────────────────────────┘
```

### 🔴 发现的关键问题

#### 问题1: ToolSelector 和 Router 功能重叠

```python
# core/tool/selector.py - ToolSelector.select()
def select(self, required_capabilities: List[str], ...):
    for capability_tag in required_capabilities:
        matched = self.registry.find_by_capability_tag(capability_tag)
        # 按优先级排序、检查约束...

# core/capability_router.py - select_tools_for_capabilities()
def select_tools_for_capabilities(router, required_capabilities, ...):
    for capability_tag in required_capabilities:
        matched_tools = router.registry.find_by_capability_tag(capability_tag)
        # 按优先级排序、检查约束...
```

**两个函数做的事情几乎一样！** 需要决定保留哪个。

#### 问题2: ToolSelector 声明依赖 Router 但没使用

```python
# core/tool/selector.py 第 71-93 行
def __init__(self, registry=None, router=None):
    self.registry = registry
    self.router = router  # ← 保存了但没使用！
    
    if self.router is None:
        from core.capability_router import create_capability_router
        self.router = create_capability_router(self.registry)  # ← 创建了但没用
```

**`self.router` 在整个 ToolSelector 类中没有被使用！**

#### 问题3: 导入路径分散

```python
# core/tool/executor.py
from core.capability_registry import CapabilityRegistry, CapabilityType, Capability

# core/tool/selector.py
from core.capability_registry import create_capability_registry
from core.capability_router import create_capability_router

# 如果还有其他模块...
from core.skills_manager import SkillsManager
```

重构后需要统一更新这些导入。

#### 问题4: Registry 和 SkillsManager 重复扫描

```python
# CapabilityRegistry 加载 capabilities.yaml（包含部分 Skills 配置）
# SkillsManager 单独扫描 skills/library/ 目录

# 结果：Skills 元数据存在两份！
```

### ✅ 重新评估后的结论

**经过代码级分析，确认了问题和解决方案：**

| 模块 | 核心价值 | 是否保留 | 说明 |
|------|---------|---------|------|
| **CapabilityRegistry** | 配置驱动、统一抽象 | ✅ 保留 + 整合 Skills 发现 | 成为唯一的"能力发现"入口 |
| **CapabilityRouter** | 智能评分算法 | ✅ 保留（评分逻辑） | 但移除 `select_tools_for_capabilities()` |
| **InvocationSelector** | 调用策略选择 | ✅ 保留 | 5种调用方式决策树 |
| **SkillsManager** | 渐进式加载 | 🔄 重构为 SkillLoader | 只保留内容加载功能 |
| **ToolSelector** | 工具选择 + LLM格式转换 | ✅ 保留 | 继续作为选择和转换的入口 |
| **ToolExecutor** | 工具执行 | ✅ 保留 | 只需更新导入 |

### 真正的问题（精确版）

```
问题1: Registry 和 SkillsManager 都在做"能力发现"
  → 解决：Registry 整合 Skills 扫描，SkillLoader 只做内容加载

问题2: Router.select_tools_for_capabilities() 和 ToolSelector.select() 重叠
  → 解决：删除 Router 中的函数，保留 ToolSelector（它更完整）

问题3: ToolSelector 声明依赖 Router 但没使用
  → 解决：考虑是否要真正使用 Router 的评分逻辑

问题4: 4个模块分散在 core/ 根目录
  → 解决：统一放入 core/capability/ 包
```

---

## 🎯 重构目标

### 目标1: 统一包结构（不是合并模块！）

```
重构前: 4个模块分散在 core/ 根目录
────────────────────────────────
core/
├── capability_registry.py
├── capability_router.py
├── invocation_selector.py
└── skills_manager.py

重构后: 统一放入 core/capability/ 包
────────────────────────────────
core/capability/
├── __init__.py           # 统一导出接口
├── types.py              # 类型定义
├── registry.py           # CapabilityRegistry（整合Skills发现）
├── router.py             # CapabilityRouter（保留评分逻辑）
├── invocation.py         # InvocationSelector（保留决策树）
└── skill_loader.py       # SkillLoader（原SkillsManager重构）
```

### 目标2: 明确职责分工

| 模块 | 定位 | 核心职责 |
|------|------|---------|
| **Registry** | 能力字典 | 统一加载 Tools + Skills 配置，提供查询 |
| **Router** | 智能推荐 | 评分算法、上下文感知、选择最佳能力 |
| **InvocationSelector** | 策略优化器 | 决定调用方式（Direct/Code/Programmatic/Stream/Search）|
| **SkillLoader** | 知识加载器 | 渐进式加载 SKILL.md、resources、scripts |

### 目标3: 优化职责边界（精确版）

```
重构前的职责混乱：
──────────────────
Registry 和 SkillsManager 都在做"能力发现"           ← 重复！
Router.select_tools_for_capabilities() 
  和 ToolSelector.select() 功能一样                 ← 重叠！
ToolSelector 依赖 Router 但没使用                   ← 浪费！

重构后的职责清晰：
──────────────────
📚 Registry (能力发现 + 元数据管理)
    │
    ├─→ 提供能力清单给 ToolSelector
    │
    └─→ 提供能力清单给 Router

🎯 Router (智能评分算法)
    │
    └─→ 提供 route() 方法给需要"推荐"的场景
        （如：根据用户输入推荐最佳能力）

🔧 ToolSelector (工具筛选 + LLM格式转换)
    │
    ├─→ select() - 根据能力标签筛选工具
    └─→ get_tools_for_llm() - 转换为 Claude API 格式

🚀 InvocationSelector (调用策略)
    │
    └─→ 决定调用方式（Direct/Code/Programmatic/Stream/Search）

📦 SkillLoader (内容加载)
    │
    └─→ 渐进式加载 SKILL.md + resources + scripts
```

### 目标4: 明确 core/tool 和 core/capability 的关系

```
                    ┌─────────────────────┐
                    │   core/capability/  │  ← 能力管理层
                    ├─────────────────────┤
                    │  Registry           │  提供"有什么能力"
                    │  Router             │  提供"推荐什么能力"
                    │  SkillLoader        │  提供"加载能力内容"
                    │  InvocationSelector │  提供"如何调用"
                    └─────────────────────┘
                              ↓
                              ↓ 依赖
                              ↓
                    ┌─────────────────────┐
                    │    core/tool/       │  ← 工具执行层
                    ├─────────────────────┤
                    │  Selector           │  选择具体工具 + LLM格式转换
                    │  Executor           │  执行工具
                    └─────────────────────┘
                              ↓
                              ↓ 使用
                              ↓
                    ┌─────────────────────┐
                    │   core/context/     │  ← 状态管理层
                    ├─────────────────────┤
                    │  Context            │  对话上下文（持久化）
                    │  RuntimeContext     │  运行时状态（临时）
                    └─────────────────────┘
```

### 目标5: 清理冗余代码

| 要删除/移动的代码 | 位置 | 原因 |
|------------------|------|------|
| `select_tools_for_capabilities()` | `capability_router.py` | 和 `ToolSelector.select()` 重复 |
| `self.router` 依赖 | `ToolSelector.__init__()` | 声明了但没使用 |
| `_scan_skills()` | `SkillsManager` | 移到 Registry |
| `generate_skills_metadata_for_prompt()` | `SkillsManager` | 移到 Registry |

### 目标4: 保留各自优势

**为什么不合并这些模块？**

1. **CapabilityRegistry**: 配置驱动架构的基石，负责"有什么"
2. **CapabilityRouter**: 智能评分算法独特，负责"选什么"
3. **InvocationSelector**: 调用策略决策树清晰，负责"怎么调"
4. **SkillLoader**: 渐进式加载是 Skills 核心特性，负责"加载什么"

**过度合并的风险**：
- ❌ 评分算法和查询接口混在一起（单一职责原则）
- ❌ 文件变得臃肿（registry.py 会超过 1000 行）
- ❌ 测试困难（无法独立测试评分逻辑）

---

## 📐 重构方案（保守式重构）

### Phase 1: 创建统一包结构

**目标**：将4个模块整理到一个包中，不改变内部逻辑

```bash
mkdir -p core/capability
```

**文件清单**：

```python
# core/capability/__init__.py
"""
Capability 统一包

导出所有公共接口
"""
from .types import Capability, CapabilityType, CapabilitySubtype
from .registry import CapabilityRegistry, create_capability_registry
from .router import (
    CapabilityRouter, 
    create_capability_router,
    extract_keywords,
    select_tools_for_capabilities
)
from .invocation import (
    InvocationSelector, 
    InvocationType,
    InvocationStrategy,
    create_invocation_selector
)
from .skill_loader import SkillLoader, SkillInfo, create_skill_loader

__all__ = [
    # 类型
    "Capability",
    "CapabilityType", 
    "CapabilitySubtype",
    # Registry
    "CapabilityRegistry",
    "create_capability_registry",
    # Router
    "CapabilityRouter",
    "create_capability_router",
    "extract_keywords",
    "select_tools_for_capabilities",
    # Invocation
    "InvocationSelector",
    "InvocationType",
    "InvocationStrategy",
    "create_invocation_selector",
    # Skill
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
]
```

---

### Phase 2: 类型定义（types.py）

**迁移**：从 `capability_registry.py` 提取类型定义

```python
# core/capability/types.py
"""
Capability 类型定义

包含：
- CapabilityType (枚举)
- CapabilitySubtype (枚举)
- Capability (数据类)
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


class CapabilityType(Enum):
    """能力类型"""
    SKILL = "SKILL"    # 领域知识包（SKILL.md + scripts）
    TOOL = "TOOL"      # 预定义函数
    MCP = "MCP"        # MCP 服务器
    CODE = "CODE"      # 动态代码执行


class CapabilitySubtype(Enum):
    """能力子类型"""
    PREBUILT = "PREBUILT"    # Anthropic预置
    CUSTOM = "CUSTOM"        # 用户自定义
    NATIVE = "NATIVE"        # 系统原生
    EXTERNAL = "EXTERNAL"    # 外部服务
    DYNAMIC = "DYNAMIC"      # 动态生成


@dataclass
class Capability:
    """
    统一能力定义
    
    抽象所有执行方式（Skills/Tools/MCP/Code）
    """
    name: str
    type: CapabilityType
    subtype: str
    provider: str
    capabilities: List[str]      # 能力标签（如 ppt_generation）
    priority: int                # 基础优先级 0-100
    cost: Dict[str, str]         # 成本 {time: fast/medium/slow, money: free/low/high}
    constraints: Dict[str, Any]  # 约束条件
    metadata: Dict[str, Any]     # 扩展信息
    input_schema: Optional[Dict] = None  # 工具输入Schema（用于Claude API）
    
    def matches_keywords(self, keywords: List[str]) -> int:
        """计算关键词匹配度（原逻辑保留）"""
        # ... 保持原有实现
    
    def meets_constraints(self, context: Dict[str, Any] = None) -> bool:
        """检查是否满足约束条件（原逻辑保留）"""
        # ... 保持原有实现
    
    def to_tool_schema(self) -> Optional[Dict]:
        """转换为Claude API的tool schema格式（原逻辑保留）"""
        # ... 保持原有实现
```

---

### Phase 3: Registry 整合 Skills 发现

**迁移**：`capability_registry.py` → `core/capability/registry.py`

**核心变化**：整合 SkillsManager 的扫描逻辑

```python
# core/capability/registry.py
    """
能力注册表
    
    职责：
1. 从 capabilities.yaml 加载 Tools/MCP 配置
2. 扫描 skills/library/ 发现 Skills（🆕 整合自 SkillsManager）
    3. 提供统一查询接口
    """
from typing import Dict, List, Optional, Any
from pathlib import Path
import yaml

from .types import Capability, CapabilityType


class CapabilityRegistry:
    """
    统一能力注册表
    """
    
    def __init__(
        self, 
        config_path: Optional[str] = None,
        skills_dir: Optional[str] = None  # 🆕 新增参数
    ):
        self.capabilities: Dict[str, Capability] = {}
        self.categories: List[Dict[str, Any]] = []
        self.task_type_mappings: Dict[str, List[str]] = {}
        
        self._config_path = config_path or self._default_config_path()
        self._skills_dir = skills_dir or self._default_skills_dir()
        
        # 加载 Tools/MCP
        self._load_config()
        
        # 🆕 扫描 Skills
        self._scan_skills()
    
    def _default_skills_dir(self) -> str:
        """获取默认 Skills 目录"""
        return str(Path(__file__).parent.parent.parent / "skills" / "library")
    
    def _scan_skills(self):
        """
        🆕 扫描 Skills 目录（整合自 SkillsManager）
        
        将 Skills 注册为 Capability(type=SKILL)
        """
        skills_dir = Path(self._skills_dir)
        
        if not skills_dir.exists():
            print(f"⚠️ Skills directory not found: {skills_dir}")
            return
        
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            
            # 解析 YAML frontmatter
            metadata = self._parse_skill_frontmatter(skill_md)
            if not metadata:
                continue
            
            # 🆕 注册为 Capability
            skill_name = metadata.get('name', skill_dir.name)
            self.capabilities[skill_name] = Capability(
                name=skill_name,
                type=CapabilityType.SKILL,
                subtype="CUSTOM",
                provider="local",
                capabilities=metadata.get('capabilities', []),
                priority=self._parse_priority(metadata.get('priority', 'medium')),
                cost={'time': 'medium', 'money': 'free'},
                constraints={},
                metadata={
                    'description': metadata.get('description', ''),
                    'keywords': metadata.get('keywords', []),
                    'preferred_for': metadata.get('preferred_for', []),
                    'skill_path': str(skill_dir)  # 🆕 保存路径
                }
            )
    
    def _parse_skill_frontmatter(self, skill_md: Path) -> Optional[Dict]:
        """解析 SKILL.md 的 YAML frontmatter"""
        try:
            content = skill_md.read_text(encoding='utf-8')
            if not content.startswith('---'):
                return None
            
            end_idx = content.index('---', 3)
            frontmatter = content[3:end_idx].strip()
            return yaml.safe_load(frontmatter)
        except Exception as e:
            print(f"⚠️ Failed to parse {skill_md}: {e}")
            return None
    
    def _parse_priority(self, priority_str: str) -> int:
        """将优先级字符串转换为数字"""
        priority_map = {'low': 30, 'medium': 50, 'high': 80, 'critical': 90}
        return priority_map.get(priority_str.lower(), 50)
    
    # ... 原有方法保持不变 ...
    # get(), find_by_type(), find_candidates(), etc.
```

---

### Phase 4: Router 保持独立（保留评分逻辑）

**迁移**：`capability_router.py` → `core/capability/router.py`

**核心价值**：智能评分算法

```python
# core/capability/router.py
"""
能力路由器

职责：
1. 智能评分算法（多维度计算）
2. 上下文感知路由
3. 选择最佳能力

保留原因：
- 评分算法独特（优先级 + 类型权重 + 关键词匹配 + 成本惩罚）
- 与 ToolSelector 职责不同：Router 专注"评分"，Selector 专注"筛选"
"""
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from .registry import CapabilityRegistry
from .types import Capability, CapabilityType


@dataclass
class RoutingResult:
    """路由结果"""
    capability: Capability
    score: float
    reason: str
    alternatives: List[Tuple[Capability, float]] = None


class CapabilityRouter:
    """
    能力路由器
    
    核心价值：智能评分 + 上下文感知
    """
    
    def __init__(
        self,
        registry: CapabilityRegistry,
        rules_path: Optional[str] = None
    ):
        self.registry = registry
        # ... 保持原有实现 ...
    
    def route(
        self,
        keywords: List[str],
        task_type: str = None,
        quality_requirement: str = "medium",
        explicit_capability: str = None,
        context: Dict[str, Any] = None
    ) -> Optional[RoutingResult]:
        """
        路由到最合适的能力
        
        评分算法：
        Score = base_priority + type_weight×5 + subtype_weight×5 
              + keyword_match×2 + quality_match×20 
              + context_bonus - cost_penalty
        """
        # ... 保持原有实现 ...
    
    # ... 其他方法保持不变 ...


# 🆕 辅助函数：从 Plan 选择工具（与 ToolSelector 协同）
def select_tools_for_capabilities(
    router: CapabilityRouter,
        required_capabilities: List[str],
    context: Dict[str, Any] = None
) -> List[Capability]:
    """
    根据能力需求选择具体工具
    
    这是 Router 的核心功能：将抽象能力标签映射到具体工具
    """
    # ... 保持原有实现 ...
```

---

### Phase 5: InvocationSelector 保持独立

**迁移**：`invocation_selector.py` → `core/capability/invocation.py`

**核心价值**：调用策略决策树

```python
# core/capability/invocation.py
"""
调用方式选择器

职责：
根据任务特性选择最合适的调用方式：
1. Direct Tool Call - 标准调用
2. Code Execution - 配置生成/计算逻辑
3. Programmatic Tool Calling - 多工具编排
4. Fine-grained Streaming - 大参数(>10KB)
5. Tool Search - 工具数量>30时动态发现

保留原因：
- 概念独特（5种调用方式对应不同场景）
- 基于 Anthropic 官方最佳实践
- 决策树清晰（规则明确）
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum


class InvocationType(Enum):
    """调用方式类型"""
    DIRECT = "direct"
    CODE_EXECUTION = "code_execution"
    PROGRAMMATIC = "programmatic"
    STREAMING = "streaming"
    TOOL_SEARCH = "tool_search"


@dataclass
class InvocationStrategy:
    """调用策略"""
    type: InvocationType
    reason: str
    config: Dict[str, Any] = None


class InvocationSelector:
    """
    调用方式选择器
    
    核心价值：策略优化（根据任务特点选择最高效调用方式）
    """
    
    # ... 保持原有实现 ...
    
    def select_strategy(
        self,
        task_type: str,
        selected_tools: List[str],
        estimated_input_size: int = 0,
        total_available_tools: int = 0,
        context: Optional[Dict[str, Any]] = None
    ) -> InvocationStrategy:
        """
        选择最合适的调用策略
        
        决策树：
        1. 工具太多(>30) → Tool Search
        2. 参数太大(>10KB) → Streaming
        3. 配置生成 → Code Execution
        4. 多工具/批量 → Programmatic
        5. 默认 → Direct
        """
        # ... 保持原有实现 ...
```

---

### Phase 6: Skills 内容加载器（重构）

**迁移**：`skills_manager.py` → `core/capability/skill_loader.py`

**核心变化**：专注于"内容加载"，"能力发现"移到 Registry

```python
# core/capability/skill_loader.py
"""
Skill 内容加载器

职责：
1. 渐进式加载 SKILL.md 内容（Level 2）
2. 加载资源文件（Level 3）
3. 获取脚本路径

⚠️ 注意：
- "Skill 发现"由 CapabilityRegistry 负责（Level 1）
- SkillLoader 只负责"内容加载"（Level 2/3）
"""
from typing import Dict, Optional
from pathlib import Path
from dataclasses import dataclass


@dataclass
class SkillInfo:
    """Skill 信息（简化版）"""
    name: str
    skill_path: str
    
    # 缓存内容
    skill_md_content: Optional[str] = None
    resources: Optional[Dict[str, str]] = None
    content_loaded: bool = False
    resources_loaded: bool = False


class SkillLoader:
    """
    Skill 内容加载器
    
    核心价值：渐进式加载（按需加载内容）
    """
    
    def __init__(self):
        self._cache: Dict[str, SkillInfo] = {}
    
    def load_skill_content(self, skill_path: str) -> Optional[str]:
        """
        加载 SKILL.md 完整内容（Level 2）
        
        Args:
            skill_path: Skill 目录路径（从 Capability.metadata 获取）
            
        Returns:
            SKILL.md 的完整内容
        """
        # 检查缓存
        if skill_path in self._cache:
            skill_info = self._cache[skill_path]
            if skill_info.content_loaded:
                return skill_info.skill_md_content
        
        # 加载内容
        skill_md = Path(skill_path) / "SKILL.md"
        if not skill_md.exists():
            return None
        
        try:
            content = skill_md.read_text(encoding='utf-8')
            
            # 缓存
            if skill_path not in self._cache:
                self._cache[skill_path] = SkillInfo(
                    name=Path(skill_path).name,
                    skill_path=skill_path
                )
            
            self._cache[skill_path].skill_md_content = content
            self._cache[skill_path].content_loaded = True
            
            return content
        except Exception as e:
            print(f"⚠️ Failed to load {skill_md}: {e}")
            return None
    
    def load_skill_resources(self, skill_path: str) -> Dict[str, str]:
        """
        加载 Skill 资源文件（Level 3）
        
        Args:
            skill_path: Skill 目录路径
            
        Returns:
            资源文件字典 {filename: content}
        """
        # 检查缓存
        if skill_path in self._cache:
            skill_info = self._cache[skill_path]
            if skill_info.resources_loaded:
                return skill_info.resources or {}
        
        # 加载资源
        resources = {}
        resources_dir = Path(skill_path) / "resources"
        
        if resources_dir.exists():
            for file in resources_dir.iterdir():
                if file.is_file():
                    try:
                        resources[file.name] = file.read_text(encoding='utf-8')
                    except Exception as e:
                        print(f"⚠️ Failed to read {file}: {e}")
        
        # 缓存
        if skill_path not in self._cache:
            self._cache[skill_path] = SkillInfo(
                name=Path(skill_path).name,
                skill_path=skill_path
            )
        
        self._cache[skill_path].resources = resources
        self._cache[skill_path].resources_loaded = True
        
        return resources
    
    def get_skill_scripts(self, skill_path: str) -> Dict[str, str]:
        """
        获取 Skill 脚本文件路径
        
        Args:
            skill_path: Skill 目录路径
            
        Returns:
            脚本文件字典 {script_name: path}
        """
        scripts = {}
        scripts_dir = Path(skill_path) / "scripts"
        
        if scripts_dir.exists():
            for file in scripts_dir.iterdir():
                if file.is_file() and file.suffix == '.py':
                    scripts[file.stem] = str(file)
        
        return scripts


# 工厂函数
def create_skill_loader() -> SkillLoader:
    """创建 Skill 加载器"""
    return SkillLoader()
```

---

## 📁 最终文件结构

```
core/capability/              # 🆕 统一包
├── __init__.py               # 统一导出接口
├── types.py                  # 类型定义（Capability, CapabilityType）
├── registry.py               # CapabilityRegistry（整合 Skills 发现）
├── router.py                 # CapabilityRouter（保留评分逻辑）
├── invocation.py             # InvocationSelector（保留决策树）
└── skill_loader.py           # SkillLoader（专注内容加载）

skills/library/               # Skills 库目录（保持不变）
├── slidespeak-generator/
│   ├── SKILL.md
│   ├── scripts/
│   └── resources/
└── ...

config/                       # 配置文件（保持不变）
├── capabilities.yaml
└── routing_rules.yaml
```

### 文件大小估算

| 文件 | 预估行数 | 说明 |
|------|---------|------|
| `types.py` | ~150 | 类型定义 + 辅助方法 |
| `registry.py` | ~550 | 原有逻辑 + Skills 扫描（+100行）|
| `router.py` | ~380 | 保持原有逻辑 |
| `invocation.py` | ~350 | 保持原有逻辑 |
| `skill_loader.py` | ~150 | 简化后的加载逻辑 |
| **总计** | **~1580** | 比原来少 100+ 行（去除重复代码）|

### 导入示例

```python
# 方式1: 从包导入（推荐）
from core.capability import (
    CapabilityRegistry,
    CapabilityRouter,
    InvocationSelector,
    SkillLoader
)

# 方式2: 导入具体模块
from core.capability.registry import CapabilityRegistry
from core.capability.router import CapabilityRouter, select_tools_for_capabilities

# 方式3: 导入类型
from core.capability.types import Capability, CapabilityType
```

---

## 🔄 迁移步骤（分步实施）

### Step 1: 创建包结构 ✅

```bash
# 创建目录和文件
mkdir -p core/capability
touch core/capability/__init__.py
touch core/capability/types.py
touch core/capability/registry.py
touch core/capability/router.py
touch core/capability/invocation.py
touch core/capability/skill_loader.py
```

**预估时间**: 5分钟

---

### Step 2: 迁移类型定义 ✅

**目标**: 提取共享类型到 `types.py`

```bash
# 从 capability_registry.py 提取
# - CapabilityType (enum)
# - CapabilitySubtype (enum)
# - Capability (dataclass)
```

**具体操作**:
1. 复制类型定义到 `types.py`
2. 添加完整的 docstring
3. 保留所有方法（`matches_keywords()`, `meets_constraints()`, `to_tool_schema()`）

**预估时间**: 20分钟

---

### Step 3: 迁移 Registry（整合 Skills 发现）🔥

**目标**: 合并 `capability_registry.py` + `skills_manager.py` 的发现逻辑

**具体操作**:

1. **复制 `capability_registry.py` → `registry.py`**
   ```bash
   cp core/capability_registry.py core/capability/registry.py
   ```

2. **添加 Skills 扫描逻辑**（从 `skills_manager.py` 提取）:
   ```python
   # 新增方法
   def _scan_skills(self):
       """扫描 Skills 目录，注册为 Capability(type=SKILL)"""
       # 从 SkillsManager._scan_skills() 迁移
   
   def _parse_skill_frontmatter(self, skill_md: Path):
       """解析 SKILL.md 的 YAML frontmatter"""
       # 从 SkillsManager._parse_skill_metadata() 迁移
   ```

3. **更新 `__init__()` 方法**:
   ```python
   def __init__(self, config_path=None, skills_dir=None):
       # ... 原有逻辑 ...
       self._load_config()
       self._scan_skills()  # 🆕 新增
   ```

4. **更新导入**:
   ```python
   from .types import Capability, CapabilityType
   ```

**测试验证**:
```python
# 测试脚本
from core.capability.registry import CapabilityRegistry

registry = CapabilityRegistry()
print(f"Total capabilities: {len(registry.capabilities)}")
print(f"Skills: {len(registry.find_by_type(CapabilityType.SKILL))}")
print(f"Tools: {len(registry.find_by_type(CapabilityType.TOOL))}")

# 验证 Skills 是否正确加载
for cap in registry.find_by_type(CapabilityType.SKILL):
    print(f"  - {cap.name}: {cap.metadata.get('description', '')[:50]}")
```

**预估时间**: 1小时

---

### Step 4: 迁移 Router（保持原逻辑）✅

**目标**: 直接迁移，保留所有逻辑

**具体操作**:

1. **复制文件**:
   ```bash
   cp core/capability_router.py core/capability/router.py
   ```

2. **更新导入**:
```python
# 旧导入
   from .capability_registry import CapabilityRegistry, Capability
   
   # 新导入
   from .registry import CapabilityRegistry
   from .types import Capability, CapabilityType
   ```

3. **保持所有逻辑不变**（包括辅助函数）:
   - `CapabilityRouter` 类
   - `create_capability_router()` 函数
   - `extract_keywords()` 函数
   - `select_tools_for_capabilities()` 函数

**测试验证**:
```python
from core.capability.registry import CapabilityRegistry
from core.capability.router import CapabilityRouter, extract_keywords

registry = CapabilityRegistry()
router = CapabilityRouter(registry)

# 测试关键词提取
keywords = extract_keywords("帮我生成一个专业的PPT")
print(f"Keywords: {keywords}")

# 测试路由
result = router.route(keywords, quality_requirement="high")
if result:
    print(f"Selected: {result.capability.name} (score: {result.score})")
    print(f"Reason: {result.reason}")
```

**预估时间**: 30分钟

---

### Step 5: 迁移 InvocationSelector ✅

**目标**: 直接迁移，重命名文件

**具体操作**:

1. **复制文件**:
```bash
   cp core/invocation_selector.py core/capability/invocation.py
   ```

2. **更新导入**（如果有）:
   ```python
   # 保持独立，通常没有依赖
   ```

3. **保持所有逻辑不变**:
   - `InvocationType` (enum)
   - `InvocationStrategy` (dataclass)
   - `ToolCharacteristics` (dataclass)
   - `InvocationSelector` 类
   - `create_invocation_selector()` 函数

**测试验证**:
```python
from core.capability.invocation import (
    InvocationSelector, 
    InvocationType
)

selector = InvocationSelector(enable_tool_search=True)

# 测试策略选择
strategy = selector.select_strategy(
    task_type="multi_tool",
    selected_tools=["web_search", "plan_todo", "bash"],
    total_available_tools=50
)

print(f"Strategy: {strategy.type.value}")
print(f"Reason: {strategy.reason}")
```

**预估时间**: 20分钟

---

### Step 6: 创建 SkillLoader（简化版）🆕

**目标**: 从 `skills_manager.py` 提取"内容加载"逻辑

**具体操作**:

1. **创建 `skill_loader.py`**（见 Phase 6 代码示例）

2. **保留的功能**:
   - `load_skill_content()` - 加载 SKILL.md
   - `load_skill_resources()` - 加载资源文件
   - `get_skill_scripts()` - 获取脚本路径

3. **移除的功能**（已迁移到 Registry）:
   - ❌ `_scan_skills()` - 扫描目录
   - ❌ `find_by_keyword()` - 查询功能
   - ❌ `generate_skills_metadata_for_prompt()` - 元数据生成

**测试验证**:
```python
from core.capability.registry import CapabilityRegistry
from core.capability.skill_loader import SkillLoader

registry = CapabilityRegistry()
loader = SkillLoader()

# 获取某个 Skill
skill_cap = registry.get("slidespeak-generator")
if skill_cap:
    skill_path = skill_cap.metadata.get('skill_path')
    
    # 加载内容
    content = loader.load_skill_content(skill_path)
    print(f"SKILL.md length: {len(content) if content else 0}")
    
    # 加载资源
    resources = loader.load_skill_resources(skill_path)
    print(f"Resources: {list(resources.keys())}")
    
    # 获取脚本
    scripts = loader.get_skill_scripts(skill_path)
    print(f"Scripts: {list(scripts.keys())}")
```

**预估时间**: 40分钟

---

### Step 7: 配置 `__init__.py` ✅

**目标**: 统一导出接口

```python
# core/capability/__init__.py
"""
Capability 统一包

提供能力管理的完整功能：
- Registry: 能力发现 + 元数据管理
- Router: 智能评分 + 最佳推荐
- InvocationSelector: 调用策略选择
- SkillLoader: Skills 内容加载
"""
from .types import (
    Capability,
    CapabilityType,
    CapabilitySubtype
)
from .registry import (
    CapabilityRegistry,
    create_capability_registry
)
from .router import (
    CapabilityRouter,
    RoutingResult,
    create_capability_router,
    extract_keywords,
    select_tools_for_capabilities
)
from .invocation import (
    InvocationSelector,
    InvocationType,
    InvocationStrategy,
    ToolCharacteristics,
    create_invocation_selector
)
from .skill_loader import (
    SkillLoader,
    SkillInfo,
    create_skill_loader
)

__all__ = [
    # Types
    "Capability",
    "CapabilityType",
    "CapabilitySubtype",
    # Registry
    "CapabilityRegistry",
    "create_capability_registry",
    # Router
    "CapabilityRouter",
    "RoutingResult",
    "create_capability_router",
    "extract_keywords",
    "select_tools_for_capabilities",
    # Invocation
    "InvocationSelector",
    "InvocationType",
    "InvocationStrategy",
    "ToolCharacteristics",
    "create_invocation_selector",
    # Skill Loader
    "SkillLoader",
    "SkillInfo",
    "create_skill_loader",
]

__version__ = "1.0.0"
```

**预估时间**: 15分钟

---

### Step 8: 更新依赖模块 🔥

**目标**: 修改所有引用旧模块的地方

**📋 完整的依赖文件清单（已扫描确认）**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  文件                              │ 导入的模块                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  core/agent/simple_agent.py        │ capability_registry                   │
│  core/tool/selector.py             │ capability_registry, capability_router│
│  core/tool/executor.py             │ capability_registry                   │
│  tests/test_router_e2b.py          │ capability_registry, capability_router│
│  tests/test_agent_router_debug.py  │ capability_router                     │
│  tests/test_simple_task_logic.py   │ capability_registry                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**按文件详细更新**:

#### 8.1 core/agent/simple_agent.py

```python
# ❌ 旧导入（第 86 行）
from core.capability_registry import create_capability_registry

# ✅ 新导入
from core.capability import create_capability_registry
```

#### 8.2 core/tool/selector.py（最复杂）

```python
# ❌ 旧导入（第 88, 92, 112, 242 行）
from core.capability_registry import create_capability_registry
from core.capability_router import create_capability_router
from core.capability_registry import CapabilityType

# ✅ 新导入
from core.capability import (
    create_capability_registry,
    create_capability_router,
    CapabilityType
)

# ⚠️ 注意：ToolSelector 中的 self.router 当前没使用
# 需要决定：删除 router 依赖？还是真正使用它？
```

**关于 ToolSelector 的决策点**:

```python
# 方案 A: 删除未使用的 router 依赖（推荐）
class ToolSelector:
    def __init__(self, registry=None):  # 移除 router 参数
        self.registry = registry
        if self.registry is None:
            from core.capability import create_capability_registry
            self.registry = create_capability_registry()
        # 删除 self.router 相关代码

# 方案 B: 真正使用 router 的评分逻辑
class ToolSelector:
    def select(self, required_capabilities, ...):
        # 使用 router 的评分来排序工具
        for cap_tag in required_capabilities:
            result = self.router.route(keywords=[cap_tag], ...)
            if result:
                selected.append(result.capability)
```

#### 8.3 core/tool/executor.py

```python
# ❌ 旧导入（第 26-31 行）
from core.capability_registry import (
    CapabilityRegistry,
    CapabilityType,
    Capability,
    create_capability_registry
)

# ✅ 新导入
from core.capability import (
    CapabilityRegistry,
    CapabilityType,
    Capability,
    create_capability_registry
)
```

#### 8.4 tests/test_router_e2b.py

```python
# ❌ 旧导入（第 11-12 行）
from core.capability_registry import create_capability_registry
from core.capability_router import create_capability_router, select_tools_for_capabilities

# ✅ 新导入
from core.capability import (
    create_capability_registry,
    create_capability_router
)
# ⚠️ select_tools_for_capabilities 将被删除，改用 ToolSelector.select()
from core.tool import ToolSelector
```

#### 8.5 tests/test_agent_router_debug.py

```python
# ❌ 旧导入（第 12 行）
from core.capability_router import select_tools_for_capabilities

# ✅ 新导入
# select_tools_for_capabilities 将被删除，改用 ToolSelector.select()
from core.tool import ToolSelector
```

#### 8.6 tests/test_simple_task_logic.py

```python
# ❌ 旧导入（第 10 行）
from core.capability_registry import create_capability_registry

# ✅ 新导入
from core.capability import create_capability_registry
```

**迁移脚本（批量替换）**:

```bash
# 方法1: sed 批量替换（小心使用）
cd /Users/wangkangcheng/projects/zenflux_agent

# 替换 capability_registry
find . -name "*.py" -exec sed -i '' 's/from core\.capability_registry import/from core.capability import/g' {} \;

# 替换 capability_router
find . -name "*.py" -exec sed -i '' 's/from core\.capability_router import/from core.capability import/g' {} \;

# 替换 skills_manager（如果有）
find . -name "*.py" -exec sed -i '' 's/from core\.skills_manager import/from core.capability import/g' {} \;

# 替换 invocation_selector（如果有）
find . -name "*.py" -exec sed -i '' 's/from core\.invocation_selector import/from core.capability import/g' {} \;
```

```bash
# 方法2: 逐个文件手动修改（更安全）
# 推荐使用 IDE 的批量替换功能
```

**⚠️ 特殊处理: select_tools_for_capabilities()**

这个函数在 `capability_router.py` 中，但被 `tests/` 使用。
重构后会删除它，需要修改测试：

```python
# ❌ 旧代码
from core.capability_router import select_tools_for_capabilities
tools = select_tools_for_capabilities(router, ["web_search", "ppt_generation"])

# ✅ 新代码
from core.tool import ToolSelector
selector = ToolSelector(registry=registry)
result = selector.select(["web_search", "ppt_generation"])
tools = result.tools
```

**预估时间**: 1-2小时

---

### Step 9: 创建兼容层（过渡期）📦

**目标**: 保留旧文件作为别名，避免立即破坏

```python
# core/capability_registry.py (兼容层)
"""
⚠️ DEPRECATED: 此文件已迁移到 core/capability/registry.py
请使用新导入: from core.capability import CapabilityRegistry
"""
import warnings

warnings.warn(
    "capability_registry.py is deprecated. "
    "Use 'from core.capability import CapabilityRegistry' instead.",
    DeprecationWarning,
    stacklevel=2
)

# 转发到新模块
from core.capability.registry import *  # noqa

# 同理创建其他3个兼容层文件
```

**预估时间**: 30分钟

---

### Step 10: 测试验证 ✅

**集成测试**:

```python
# tests/test_capability_integration.py
"""测试 capability 包的集成功能"""
import pytest
from core.capability import (
    CapabilityRegistry,
    CapabilityRouter,
    InvocationSelector,
    SkillLoader,
    CapabilityType
)


def test_registry_loads_all_capabilities():
    """测试 Registry 加载 Tools + Skills"""
    registry = CapabilityRegistry()
    
    assert len(registry.capabilities) > 0
    tools = registry.find_by_type(CapabilityType.TOOL)
    skills = registry.find_by_type(CapabilityType.SKILL)
    
    assert len(tools) > 0
    assert len(skills) > 0
    print(f"✅ Loaded {len(tools)} tools, {len(skills)} skills")


def test_router_selects_best_capability():
    """测试 Router 智能选择"""
    registry = CapabilityRegistry()
    router = CapabilityRouter(registry)
    
    result = router.route(
        keywords=["ppt", "专业"],
        quality_requirement="high"
    )
    
    assert result is not None
    assert result.score > 0
    print(f"✅ Selected: {result.capability.name} (score: {result.score})")


def test_invocation_selector_strategies():
    """测试 InvocationSelector 策略选择"""
    selector = InvocationSelector()
    
    # 测试多工具场景
    strategy = selector.select_strategy(
        task_type="multi_tool",
        selected_tools=["tool1", "tool2", "tool3"]
    )
    
    assert strategy.type.value in ["programmatic", "direct"]
    print(f"✅ Strategy: {strategy.type.value}")


def test_skill_loader():
    """测试 SkillLoader 加载内容"""
    registry = CapabilityRegistry()
    loader = SkillLoader()
    
    # 查找第一个 Skill
    skills = registry.find_by_type(CapabilityType.SKILL)
    if skills:
        skill = skills[0]
        skill_path = skill.metadata.get('skill_path')
        
        # 加载内容
        content = loader.load_skill_content(skill_path)
        assert content is not None
        print(f"✅ Loaded skill: {skill.name}")


if __name__ == "__main__":
    test_registry_loads_all_capabilities()
    test_router_selects_best_capability()
    test_invocation_selector_strategies()
    test_skill_loader()
    print("\n🎉 All tests passed!")
```

**运行测试**:
```bash
python tests/test_capability_integration.py
```

**预估时间**: 1小时

---

### Step 11: 删除旧文件（可选）🗑️

**⚠️ 警告**: 确保所有依赖已更新后再执行

```bash
# 移动到备份目录
mkdir -p core/_deprecated
mv core/capability_registry.py core/_deprecated/
mv core/capability_router.py core/_deprecated/
mv core/skills_manager.py core/_deprecated/
mv core/invocation_selector.py core/_deprecated/

# 或直接删除（更彻底）
# rm core/capability_registry.py
# rm core/capability_router.py
# rm core/skills_manager.py
# rm core/invocation_selector.py
```

**预估时间**: 5分钟

---

### 📊 总体时间估算

| 步骤 | 预估时间 | 累计 |
|------|---------|------|
| Step 1: 创建包结构 | 5分钟 | 5分钟 |
| Step 2: 迁移类型定义 | 20分钟 | 25分钟 |
| Step 3: 迁移 Registry | 1小时 | 1.5小时 |
| Step 4: 迁移 Router | 30分钟 | 2小时 |
| Step 5: 迁移 InvocationSelector | 20分钟 | 2.3小时 |
| Step 6: 创建 SkillLoader | 40分钟 | 3小时 |
| Step 7: 配置 `__init__.py` | 15分钟 | 3.25小时 |
| Step 8: 更新依赖模块 | 1-2小时 | 4.5-5.5小时 |
| Step 9: 创建兼容层 | 30分钟 | 5-6小时 |
| Step 10: 测试验证 | 1小时 | 6-7小时 |
| Step 11: 删除旧文件 | 5分钟 | 6-7小时 |

**总计**: **6-7 小时**（完整重构 + 测试）

---

## ⚠️ 风险评估与缓解

### 风险矩阵

| 风险项 | 影响程度 | 发生概率 | 缓解措施 | 优先级 |
|--------|---------|---------|---------|--------|
| **导入路径变化** | 🔴 高 | 🔴 高 | 创建兼容层（Step 9）+ 分步迁移 | P0 |
| **Skills 加载逻辑变化** | 🟡 中 | 🟡 中 | 完整测试 Skills 发现 + 缓存逻辑 | P1 |
| **Router 评分逻辑丢失** | 🟡 中 | 🟢 低 | 保留原有代码 + 单元测试 | P1 |
| **InvocationSelector 逻辑变化** | 🟢 低 | 🟢 低 | 直接迁移，无逻辑修改 | P2 |
| **兼容性问题** | 🔴 高 | 🟡 中 | 保留旧文件作为别名（1-2个版本）| P0 |
| **测试覆盖不足** | 🟡 中 | 🟡 中 | 编写集成测试（Step 10）| P1 |

### 详细缓解措施

#### 1. 导入路径变化（P0）

**风险描述**：所有依赖模块的导入路径都需要修改

**缓解措施**：
```python
# 方案A: 兼容层（推荐）
# 保留旧文件，转发到新模块
# core/capability_registry.py
from core.capability.registry import *

# 方案B: 批量替换
# 使用脚本批量修改导入
find . -name "*.py" -exec sed -i '' 's/from core.capability_registry/from core.capability/g' {} \;

# 方案C: 渐进式迁移
# 先创建兼容层 → 逐个模块迁移 → 删除兼容层
```

**回滚方案**：
- 保留 `core/_deprecated/` 目录作为备份
- Git 标记关键 commit，必要时 revert

#### 2. Skills 加载逻辑变化（P1）

**风险描述**：将 Skills 扫描从 SkillsManager 迁移到 Registry 可能遗漏边界情况

**缓解措施**：
```python
# 测试清单
def test_skills_discovery():
    """验证 Skills 发现逻辑"""
    registry = CapabilityRegistry()
    
    # 1. 验证数量
    skills = registry.find_by_type(CapabilityType.SKILL)
    assert len(skills) > 0, "未发现任何 Skills"
    
    # 2. 验证元数据
    for skill in skills:
        assert skill.name
        assert skill.metadata.get('description')
        assert skill.metadata.get('skill_path')
    
    # 3. 验证路径正确性
    skill_path = Path(skills[0].metadata['skill_path'])
    assert skill_path.exists()
    assert (skill_path / "SKILL.md").exists()

# 对比测试（确保新旧结果一致）
def test_skills_parity():
    """对比新旧实现结果"""
    from core.skills_manager import SkillsManager
    from core.capability import CapabilityRegistry
    
    old_manager = SkillsManager()
    new_registry = CapabilityRegistry()
    
    old_skills = set(old_manager.list_skills())
    new_skills = {
        cap.name 
        for cap in new_registry.find_by_type(CapabilityType.SKILL)
    }
    
    assert old_skills == new_skills, "Skills 列表不一致"
```

#### 3. Router 评分逻辑丢失（P1）

**风险描述**：Router 保持独立，风险较低，但需确保导入正确

**缓解措施**：
```python
# 单元测试（验证评分逻辑）
def test_router_scoring():
    """验证评分算法"""
    registry = CapabilityRegistry()
    router = CapabilityRouter(registry)
    
    # 测试关键词匹配
    result = router.route(keywords=["ppt", "专业"], quality_requirement="high")
    assert result.score > 100  # 预期高分
    
    # 测试成本惩罚
    result_slow = router.route(keywords=["slow_tool"])
    result_fast = router.route(keywords=["fast_tool"])
    # fast_tool 应该分数更高（成本惩罚更低）
```

#### 4. 兼容性问题（P0）

**风险描述**：依赖模块可能无法立即迁移

**缓解措施**：
- 保留兼容层至少 1-2 个版本（约 2-4 周）
- 在兼容层添加 `DeprecationWarning`
- 更新文档说明迁移路径

```python
# core/capability_registry.py (兼容层)
import warnings

warnings.warn(
    "capability_registry.py is deprecated. "
    "Use 'from core.capability import CapabilityRegistry' instead. "
    "This compatibility layer will be removed in v2.0.",
    DeprecationWarning,
    stacklevel=2
)

from core.capability.registry import *
```

### 回滚计划

如果重构失败，按以下步骤回滚：

```bash
# 1. 恢复旧文件
cp core/_deprecated/*.py core/

# 2. 删除新包
rm -rf core/capability/

# 3. 恢复依赖模块的导入
git checkout -- core/agent/simple_agent.py
git checkout -- core/tool/selector.py

# 4. 运行测试确认
pytest tests/
```

---

## 📊 预期收益

### 1. 代码组织改善

| 维度 | 重构前 | 重构后 | 改善 |
|------|-------|--------|------|
| **文件分布** | 4个独立文件 | 1个包（6个文件）| ✅ 统一管理 |
| **模块数量** | 4个模块 | 4个模块（保留）| ➡️ 保持不变 |
| **概念清晰度** | 混乱（Capability ≈ Skill ≈ Tool）| 统一（Capability 包含 Skills/Tools）| ✅ 概念清晰 |
| **导入路径** | `from core.xxx` | `from core.capability import xxx` | ✅ 更清晰 |
| **职责边界** | 重叠（Registry + SkillsManager）| 明确（Registry 统一发现）| ✅ 无重复 |

### 2. 功能完整性

| 功能 | 重构前 | 重构后 | 说明 |
|------|-------|--------|------|
| **能力发现** | Registry + SkillsManager | Registry 统一 | ✅ 消除重复 |
| **智能评分** | Router（独立）| Router（保留）| ✅ 保留优势 |
| **调用策略** | InvocationSelector | InvocationSelector（保留）| ✅ 保留优势 |
| **内容加载** | SkillsManager | SkillLoader（简化）| ✅ 专注职责 |
| **渐进式加载** | 支持 Level 1/2/3 | 支持 Level 1/2/3 | ✅ 功能完整 |

### 3. 性能优化

| 指标 | 重构前 | 重构后 | 说明 |
|------|-------|--------|------|
| **启动时间** | 扫描2次（Registry + SkillsManager）| 扫描1次（Registry）| ✅ 减少50%扫描 |
| **内存占用** | 2份元数据缓存 | 1份元数据缓存 | ✅ 减少冗余 |
| **查询性能** | O(n) × 2 | O(n) × 1 | ✅ 查询更快 |

### 4. 代码行数

| 文件 | 重构前（行数）| 重构后（行数）| 变化 |
|------|-------------|-------------|------|
| `capability_registry.py` | 538 | → `registry.py` (550) | +12 |
| `capability_router.py` | 521 | → `router.py` (380) | -141 |
| `skills_manager.py` | 327 | → `skill_loader.py` (150) | -177 |
| `invocation_selector.py` | 349 | → `invocation.py` (350) | +1 |
| - | - | `types.py` (150) | +150 |
| - | - | `__init__.py` (80) | +80 |
| **总计** | **1735** | **1660** | **-75 (-4.3%)** |

### 5. 维护成本

| 维度 | 重构前 | 重构后 | 改善 |
|------|-------|--------|------|
| **新增能力** | 修改 2 处（Registry + SkillsManager）| 修改 1 处（Registry）| ✅ 减少50%工作量 |
| **修改评分** | 只修改 Router | 只修改 Router | ➡️ 保持不变 |
| **测试复杂度** | 4 个独立测试套件 | 1 个集成测试 + 4 个单元测试 | ✅ 更易测试 |
| **文档维护** | 4 份独立文档 | 1 份统一文档 | ✅ 减少75%文档 |

### 6. 开发体验

**重构前**：
```python
# ❌ 概念混乱
from core.capability_registry import CapabilityRegistry
from core.skills_manager import SkillsManager
from core.capability_router import CapabilityRouter
from core.invocation_selector import InvocationSelector

# 需要初始化4个对象
registry = CapabilityRegistry()
skills_manager = SkillsManager()  # 重复扫描！
router = CapabilityRouter(registry)
selector = InvocationSelector()

# Skills 信息分散在2个地方
skill_meta = registry.get("slidespeak-generator")  # 元数据
skill_content = skills_manager.load_skill_content("slidespeak-generator")  # 内容
```

**重构后**：
```python
# ✅ 统一导入
from core.capability import (
    CapabilityRegistry,
    CapabilityRouter,
    InvocationSelector,
    SkillLoader
)

# 初始化更清晰
registry = CapabilityRegistry()  # 自动扫描 Skills
router = CapabilityRouter(registry)
selector = InvocationSelector()
loader = SkillLoader()

# Skills 信息统一管理
skill_cap = registry.get("slidespeak-generator")  # 元数据（包含路径）
skill_content = loader.load_skill_content(
    skill_cap.metadata['skill_path']  # 内容加载
)
```

### 7. 扩展性改善

**新增能力类型（如 MCP）**：

重构前：
```python
# ❌ 需要修改多个地方
# 1. capability_registry.py - 添加 MCP 扫描
# 2. capability_router.py - 添加 MCP 评分权重
# 3. skills_manager.py - 可能需要支持 MCP 加载
```

重构后：
```python
# ✅ 只需修改 1 处
# core/capability/registry.py
def _scan_mcp_servers(self):
    """扫描 MCP 服务器"""
    # 统一注册为 Capability(type=MCP)
    pass

# Router 和 Loader 无需修改（通用逻辑）
```

### 8. 对外接口稳定性

| 接口 | 重构前 | 重构后 | 兼容性 |
|------|-------|--------|--------|
| `CapabilityRegistry` | ✅ 可用 | ✅ 可用 | 🟢 完全兼容 |
| `CapabilityRouter` | ✅ 可用 | ✅ 可用 | 🟢 完全兼容 |
| `InvocationSelector` | ✅ 可用 | ✅ 可用 | 🟢 完全兼容 |
| `SkillsManager` | ✅ 可用 | ❌ 废弃 → SkillLoader | 🟡 需迁移 |

**兼容层保证**：
```python
# 旧代码仍可运行（带警告）
from core.skills_manager import SkillsManager  # DeprecationWarning

# 新代码推荐写法
from core.capability import SkillLoader
```

---

## 🎯 总结

### 核心改进

1. ✅ **统一包结构**：4个分散模块 → 1个统一包（参考 `core/context/` 模式）
2. ✅ **消除重复**：Registry 整合 Skills 发现，减少扫描次数
3. ✅ **清理冗余**：删除 `select_tools_for_capabilities()`，统一使用 `ToolSelector`
4. ✅ **保留优势**：Router 评分、InvocationSelector 决策树独立保留
5. ✅ **简化职责**：SkillLoader 专注内容加载，不做发现
6. ✅ **提升体验**：统一导入、清晰概念、易于扩展

### 关键决策

| 决策 | 选择 | 原因 |
|------|------|------|
| **Router vs ToolSelector** | 保留两者 | Router 专注评分，ToolSelector 专注筛选+格式转换 |
| **select_tools_for_capabilities()** | 删除 | 和 ToolSelector.select() 重复 |
| **ToolSelector.router 依赖** | 删除 | 声明了但没使用，浪费资源 |
| **Skills 发现** | 整合到 Registry | 消除两处扫描，统一入口 |
| **InvocationSelector** | 保留 | 5种调用方式的决策树有独特价值 |

### 代码质量改进

```
重构前                              重构后
─────────                          ─────────
Registry + SkillsManager 重复扫描 →  Registry 统一扫描
select_tools_for_capabilities() 
  和 ToolSelector.select() 重复  →  只保留 ToolSelector.select()
ToolSelector 依赖 router 但没用  →  删除无用依赖
4个模块分散在 core/ 根目录      →  统一放入 core/capability/
```

### 实施建议

1. **分步实施**（不是一次性大重构）
2. **创建兼容层**（保证平滑过渡）
3. **完整测试**（集成测试 + 单元测试）
4. **渐进式迁移**（逐个模块更新导入）
5. **先改 core/tool/**（因为它直接依赖 capability 模块）

### 与 core/tool 和 core/context 的关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        依赖层次（从下到上）                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│  │   Agent     │────→│  core/tool  │────→│core/capability│              │
│  │             │     │  Selector   │     │  Registry    │              │
│  │             │     │  Executor   │     │  Router      │              │
│  └─────────────┘     └─────────────┘     │  Invocation  │              │
│         │                                │  SkillLoader │              │
│         │            ┌─────────────┐     └─────────────┘               │
│         └───────────→│core/context │                                   │
│                      │  Context    │                                   │
│                      │  Runtime    │                                   │
│                      └─────────────┘                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

重构影响范围：
• core/capability/（新建）     ← 主要工作
• core/tool/selector.py       ← 更新导入 + 清理 router 依赖
• core/tool/executor.py       ← 更新导入
• core/agent/simple_agent.py  ← 更新导入
• tests/                      ← 更新导入 + 适配 API 变化
```

---

## 🎨 参考模式：core/context/ 的良好设计

`core/context/` 包是一个很好的参考模式，展示了如何组织相关模块：

### 目录结构

```
core/context/
├── __init__.py         # 统一导出接口
├── conversation.py     # Context（对话上下文 - 持久化）
└── runtime.py          # RuntimeContext（运行时状态 - 临时）
```

### __init__.py 设计

```python
# core/context/__init__.py
from core.context.conversation import Context, create_context
from core.context.runtime import RuntimeContext, create_runtime_context

__all__ = [
    "Context",
    "create_context",
    "RuntimeContext", 
    "create_runtime_context",
]
```

**亮点**：
- ✅ 清晰的导出列表（`__all__`）
- ✅ 工厂函数（`create_xxx`）
- ✅ 职责分离（持久化 vs 临时状态）

### 职责分离

| 模块 | 职责 | 数据特点 |
|------|------|---------|
| `Context` | 对话上下文 | 持久化（数据库）、跨会话 |
| `RuntimeContext` | 运行时状态 | 临时、单次执行 |

**这正是我们重构 capability 包要参考的模式！**

| capability 模块 | 对应 context 模式 |
|----------------|------------------|
| `Registry` | 类似 `Context`（持久配置）|
| `Router` | 算法模块（独立逻辑）|
| `SkillLoader` | 类似 `RuntimeContext`（按需加载）|
| `InvocationSelector` | 策略模块（独立逻辑）|

---

## 🔗 相关文档

- [00-ARCHITECTURE-V4.md](./00-ARCHITECTURE-V4.md) - V4 架构总览
- [02-CAPABILITY-ROUTING.md](./02-CAPABILITY-ROUTING.md) - 能力路由设计
- [03-SKILLS-DISCOVERY.md](./03-SKILLS-DISCOVERY.md) - Skills 发现机制

---

## 📝 附录B: 代码片段对比

### B1. select_tools_for_capabilities() vs ToolSelector.select()

**位置1: `core/capability_router.py` (第 439-518 行)**

```python
def select_tools_for_capabilities(
    router: CapabilityRouter,
    required_capabilities: List[str],
    context: Dict[str, Any] = None
) -> List:
    """根据能力需求选择具体工具"""
    selected = []
    selected_skills_capabilities = set()
    context = context or {}
    
    # 1. 始终包含基础工具
    base_tool_names = ["plan_todo", "bash"]
    for name in base_tool_names:
        if cap := router.registry.get(name):
            if cap not in selected:
                selected.append(cap)
    
    # 2. 根据能力标签查找匹配的工具
    for capability_tag in required_capabilities:
        matched_tools = router.registry.find_by_capability_tag(capability_tag)
        # ... 排序、检查约束、添加到 selected ...
    
    # 3. 自动包含 Skills 依赖的底层工具
    # ...
    
    return selected
```

**位置2: `core/tool/selector.py` (第 95-189 行)**

```python
def select(
    self,
    required_capabilities: List[str],
    context: Optional[Dict[str, Any]] = None,
    include_native: bool = True
) -> ToolSelectionResult:
    """选择工具"""
    context = context or {}
    selected = []
    selected_skills_capabilities = set()
    
    # 1. 添加基础工具
    base_tools = []
    for name in self.BASE_TOOLS:  # ["plan_todo", "bash"]
        cap = self.registry.get(name)
        if cap and cap not in selected:
            selected.append(cap)
            base_tools.append(name)
    
    # 2. 根据能力标签选择工具
    for capability_tag in required_capabilities:
        matched = self.registry.find_by_capability_tag(capability_tag)
        # ... 排序、检查约束、添加到 selected ...
    
    # 3. 自动包含 Skills 依赖的底层工具
    # ...
    
    return ToolSelectionResult(tools=selected, ...)
```

**对比结论**：
- 🔴 **代码几乎一样！** 只是返回类型不同
- 🟢 `ToolSelector.select()` 更完整（有 `ToolSelectionResult`、`include_native`）
- 📌 **决策：删除 `select_tools_for_capabilities()`，统一使用 `ToolSelector`**

### B2. ToolSelector 中未使用的 router 依赖

```python
# core/tool/selector.py 第 71-93 行
class ToolSelector:
    def __init__(
        self,
        registry=None,
        router=None  # ← 这个参数
    ):
        self.registry = registry
        self.router = router  # ← 保存了
        
        if self.registry is None:
            from core.capability_registry import create_capability_registry
            self.registry = create_capability_registry()
        
        if self.router is None:
            from core.capability_router import create_capability_router
            self.router = create_capability_router(self.registry)  # ← 创建了
        
        # 但整个类中没有任何地方使用 self.router ！

# 搜索 "self.router" 在 selector.py 中的使用：
# - __init__ 中赋值：1 次
# - 其他方法中使用：0 次 ← 完全没用！
```

**决策选项**：

| 选项 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **A. 删除** | 移除 `router` 参数和相关代码 | 简化代码、减少依赖 | 可能未来需要时要加回来 |
| **B. 使用** | 在 `select()` 中使用 Router 评分 | 工具选择更智能 | 增加复杂度 |
| **C. 保留** | 保持现状（声明但不使用）| 最小改动 | 代码混乱、浪费资源 |

**推荐方案 A**：删除未使用的依赖，保持代码简洁。如果未来需要评分功能，再添加。

---

## 📝 附录

### A. 问题解答

**Q1: 为什么不把4个模块合并成1个大文件？**

A: 虽然它们都是"能力管理"相关，但职责不同：
- Registry = 字典（存储）
- Router = 推荐算法（计算）
- InvocationSelector = 策略优化器（决策）
- SkillLoader = 文件加载器（I/O）

合并会违反单一职责原则，导致：
- ❌ 文件过大（1000+ 行）
- ❌ 难以测试（无法独立测试评分逻辑）
- ❌ 难以复用（如果其他 Agent 只需要 Router）

**Q2: Skills 库目录要不要也放进 `core/capability/` ？**

A: **不要！** 两者性质不同：
- `core/capability/` = Python 代码（能力管理逻辑）
- `skills/library/` = 数据目录（知识文件）

类比：
- `core/capability/` 像数据库驱动（pymysql）
- `skills/library/` 像数据库文件（data.db）

它们应该分离：
```
core/capability/        # 管理代码
skills/library/         # 知识数据
    ├── slidespeak-generator/
    ├── excel-analyzer/
    └── ...
```

**Q3: SkillsManager 的其他功能（如 `generate_skills_metadata_for_prompt()`）去哪了？**

A: 迁移到 Registry：
```python
# 重构前
skills_manager = SkillsManager()
metadata = skills_manager.generate_skills_metadata_for_prompt()

# 重构后
registry = CapabilityRegistry()
skills = registry.find_by_type(CapabilityType.SKILL)
metadata = generate_skills_prompt(skills)  # 辅助函数
```

**Q4: 如果以后要支持更多能力类型（如 MCP），怎么扩展？**

A: 在 Registry 添加扫描逻辑即可：
```python
# core/capability/registry.py
def __init__(self, ...):
    self._load_config()      # Tools
    self._scan_skills()      # Skills
    self._scan_mcp_servers() # 🆕 MCP
```

Router 和 Loader 无需修改（它们是通用逻辑）。

**Q5: 兼容层会永久保留吗？**

A: 不会。计划：
- **v1.0**: 创建兼容层（带 DeprecationWarning）
- **v1.1-v1.2**: 逐步迁移依赖模块
- **v2.0**: 删除兼容层（约 2-4 周后）

---

### B. 迁移检查清单

**重构前检查**：
- [ ] 备份当前代码（创建 Git 分支）
- [ ] 运行现有测试确保通过
- [ ] 记录所有依赖模块（`grep -r "from core.capability"` ）

**重构中检查**：
- [ ] Step 1: 创建包结构
- [ ] Step 2: 迁移类型定义
- [ ] Step 3: 迁移 Registry（整合 Skills）
- [ ] Step 4: 迁移 Router
- [ ] Step 5: 迁移 InvocationSelector
- [ ] Step 6: 创建 SkillLoader
- [ ] Step 7: 配置 `__init__.py`
- [ ] Step 8: 更新依赖模块
- [ ] Step 9: 创建兼容层
- [ ] Step 10: 运行测试

**重构后验证**：
- [ ] 所有测试通过
- [ ] 手动测试关键功能（Skill 加载、工具选择）
- [ ] 检查日志无异常
- [ ] 文档更新
- [ ] 提交 PR 并 Code Review

---

### C. 术语对照表

| 术语 | 含义 | 示例 |
|------|------|------|
| **Capability** | 抽象能力（包含 Tools/Skills/MCP）| `ppt_generation` |
| **Tool** | 预定义函数（可直接调用）| `plan_todo`, `bash` |
| **Skill** | 领域知识包（SKILL.md + scripts）| `slidespeak-generator` |
| **Registry** | 能力注册表（统一管理）| 加载 + 查询 |
| **Router** | 能力路由器（智能选择）| 评分 + 推荐 |
| **InvocationSelector** | 调用方式选择器 | Direct/Code/Programmatic |
| **SkillLoader** | Skills 内容加载器 | 加载 SKILL.md |

---

## ✅ 状态更新

> 📅 **创建日期**: 2025-12-30  
> 📅 **更新日期**: 2025-12-30 （V3 - 完整代码分析版）  
> 🎯 **当前状态**: ✅ **准备实施**（代码级分析已完成）

### 📌 本次更新（V3）

1. ✅ 分析了 `core/tool/` 目录结构和代码
2. ✅ 分析了 `core/context/` 目录结构（作为参考模式）
3. ✅ 发现了 `select_tools_for_capabilities()` 和 `ToolSelector.select()` 的重复
4. ✅ 发现了 `ToolSelector` 中未使用的 `router` 依赖
5. ✅ 确认了所有需要更新导入的文件（6个文件）
6. ✅ 添加了详细的迁移命令和代码对比

### 下一步行动

```
1. 确认重构方案（你来确认！）
   □ 是否删除 select_tools_for_capabilities()？
   □ 是否删除 ToolSelector 中未使用的 router 依赖？
   □ 是否参考 core/context/ 的包结构模式？

2. 创建 Git 分支
   git checkout -b feature/capability-refactor

3. 按顺序执行 11 个 Step
   • Step 1-7: 创建 core/capability/ 包（~3小时）
   • Step 8: 更新依赖模块（~1.5小时）
   • Step 9-11: 兼容层、测试、清理（~2小时）

4. 运行测试验证
   pytest tests/
```

### 📊 完整工作量评估

| 阶段 | 文件 | 工作量 | 优先级 |
|------|------|--------|--------|
| 创建 core/capability/ | 6个新文件 | 3小时 | P0 |
| 更新 core/tool/ | 2个文件 | 1小时 | P0 |
| 更新 core/agent/ | 1个文件 | 15分钟 | P0 |
| 更新 tests/ | 3个文件 | 1小时 | P1 |
| 创建兼容层 | 4个文件 | 30分钟 | P1 |
| 测试验证 | - | 1小时 | P0 |
| **总计** | **16个文件** | **~7小时** | - |

### 负责人

- **架构设计**: @zenflux_agent
- **代码实施**: @developer
- **测试验证**: @qa_team
- **文档更新**: @tech_writer

---

**🎉 重构计划 V3 已完成！包含完整的代码分析和迁移方案。准备开始实施！**