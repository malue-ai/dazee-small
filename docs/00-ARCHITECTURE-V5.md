# ZenFlux Agent V5 架构文档

> 📅 **发布日期**: 2026-01-09  
> 🎯 **版本**: V5.0 - 实例级提示词缓存 + LLM 语义驱动 Schema + 本地文件持久化  
> 🔗 **前版本**: [V4.6 架构](./00-ARCHITECTURE-V4.md)

---

## 📋 目录

- [版本概述](#版本概述)
- [核心设计原则](#核心设计原则)
- [架构流程](#架构流程)
  - [启动阶段](#启动阶段)
  - [运行阶段](#运行阶段)
- [核心组件](#核心组件)
  - [InstancePromptCache](#instancepromptcache)
  - [IntentPromptGenerator](#intentpromptgenerator)
  - [LLM Schema 生成器](#llm-schema-生成器)
  - [CacheStorageBackend](#cachestoragebackend)
- [与 V4.6 的差异](#与-v46-的差异)
- [代码-架构一致性清单](#代码-架构一致性清单)
- [目录结构](#目录结构)
- [快速验证](#快速验证)

---

## 版本概述

V5.0 是一次**重大架构升级**，核心变化：

1. **实例级提示词缓存**: 启动时一次性生成所有提示词版本，运行时直接取用
2. **LLM 语义驱动 Schema**: 用 Few-shot 引导 LLM 推理配置，而非硬编码关键词规则
3. **Prompt-First 设计原则**: 规则写在 Prompt 里，不写在代码里
4. **🆕 本地文件持久化**: 缓存数据持久化到 `.cache/` 目录，避免每次重启都 LLM 分析

```
V5.0 核心理念：用空间换时间 + LLM 语义理解 + 本地持久化
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

首次启动（一次性，2-3秒）:
├── LLM 分析 prompt.md → PromptSchema + AgentSchema
├── 生成 3 版本系统提示词（Simple/Medium/Complex）
├── 生成意图识别提示词
├── 缓存到 InstancePromptCache（内存）
└── 🆕 持久化到 .cache/ 目录（磁盘）

后续启动（配置未变，< 100ms）:
├── 🆕 读取 .cache/cache_meta.json 验证哈希
├── 🆕 哈希匹配 → 直接从磁盘加载缓存
└── 跳过 LLM 分析，立即可用

配置变更后启动（需要手动重启）:
├── 🆕 哈希不匹配 → 重新 LLM 分析
└── 更新磁盘缓存

运行阶段（每次请求，毫秒级）:
├── 直接从内存缓存取 intent_prompt
├── 意图识别 → 复杂度
├── 直接从内存缓存取 system_prompt
└── LLM 执行任务

⚠️ 注意：配置变更（prompt.md / config.yaml）后需要重启 Agent
```

---

## 核心设计原则

### Prompt-First 原则

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   核心哲学：规则写在 Prompt 里，不写在代码里                     │
│                                                                 │
│   ❌ V4.6 代码硬编码规则（泛化能力极差）：                       │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ if "excel" in prompt_lower:                             │   │
│   │     skills.append("xlsx")  # 只能识别关键词              │   │
│   │ if "ppt" in prompt_lower:                               │   │
│   │     skills.append("pptx")  # 无法理解业务意图            │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   ✅ V5.0 Few-shot 引导 LLM 推理（强泛化能力）：                │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │ <example>                                               │   │
│   │   <prompt>帮我分析销售数据，生成周报</prompt>            │   │
│   │   <reasoning>数据分析+表格生成（虽无"excel"关键词）</reasoning>│
│   │   <schema>{"skills": [{"skill_id": "xlsx"}]}</schema>   │   │
│   │ </example>                                              │   │
│   │                                                         │   │
│   │ LLM 通过 Few-shot 学习推理模式，可泛化到：              │   │
│   │ - "整理成报告" → docx                                   │   │
│   │ - "准备演示材料" → pptx（虽未提及"PPT"）                │   │
│   │ - "分析竞品" → web_search + docx                        │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│   维护方式：修改 Few-shot 示例即可扩展能力，无需改代码           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 用空间换时间原则

| 阶段 | 开销 | 频率 |
|------|------|------|
| 启动时 LLM 分析 | ~2-3秒 | 一次 |
| 运行时取缓存 | <1ms | 每次请求 |

---

## 架构流程

### 启动阶段

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         启动阶段流程图                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   instances/test_agent/                                                  │
│   ├── prompt.md        ─────────┐                                       │
│   ├── config.yaml               │                                       │
│   └── .env                      ▼                                       │
│                        ┌────────────────┐                               │
│                        │ instance_loader │                               │
│                        └────────┬───────┘                               │
│                                 │                                        │
│                                 ▼                                        │
│                   ┌──────────────────────────┐                          │
│                   │ InstancePromptCache      │                          │
│                   │ .load_once()             │                          │
│                   └─────────────┬────────────┘                          │
│                                 │                                        │
│         ┌───────────────────────┼───────────────────────┐               │
│         ▼                       ▼                       ▼               │
│  ┌────────────────┐   ┌─────────────────┐   ┌────────────────────┐     │
│  │ LLM 语义分析    │   │ LLM 语义分析     │   │ IntentPromptGenerator│   │
│  │ → PromptSchema │   │ → AgentSchema   │   │ .generate()         │     │
│  └───────┬────────┘   └───────┬─────────┘   └─────────┬──────────┘     │
│          │                    │                       │                 │
│          ▼                    ▼                       ▼                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    InstancePromptCache                           │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐             │   │
│  │  │ prompt_schema │ │ agent_schema │ │ intent_prompt │             │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘             │   │
│  │  ┌─────────────────────────────────────────────────┐            │   │
│  │  │ system_prompt_simple | system_prompt_medium | system_prompt_complex │
│  │  └─────────────────────────────────────────────────┘            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  关键产出：                                                              │
│  • PromptSchema: 提示词结构（模块、复杂度关键词等）                      │
│  • AgentSchema: Agent 配置（工具、Skills、组件开关等）                   │
│  • 3 版本系统提示词: Simple/Medium/Complex                              │
│  • 意图识别提示词: 动态生成（用户配置优先）                              │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**代码入口**: `scripts/instance_loader.py` → `create_agent_from_instance()`

```python
# 启动时一次性加载（核心代码）
from core.prompt import InstancePromptCache, load_instance_cache

prompt_cache = await load_instance_cache(
    instance_name=instance_name,
    raw_prompt=instance_prompt,
    config=config.raw_config,
    force_refresh=False
)
```

### 运行阶段

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         运行阶段流程图                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   用户请求: "帮我生成一个产品介绍 PPT"                                    │
│                        │                                                 │
│                        ▼                                                 │
│            ┌───────────────────────┐                                    │
│            │    SimpleAgent.chat() │                                    │
│            └───────────┬───────────┘                                    │
│                        │                                                 │
│   ┌────────────────────┼────────────────────┐                           │
│   │         阶段 1: 意图识别                 │                           │
│   │                    ▼                    │                           │
│   │  ┌─────────────────────────────────┐   │                           │
│   │  │ IntentAnalyzer._get_intent_prompt()│   │                           │
│   │  │       ↓                          │   │                           │
│   │  │ _prompt_cache.get_intent_prompt() │  │  ◄─ 直接从缓存取          │
│   │  │       ↓                          │   │                           │
│   │  │ LLM (Haiku) → IntentResult       │   │                           │
│   │  │   • task_type: content_generation│   │                           │
│   │  │   • complexity: COMPLEX          │   │                           │
│   │  │   • needs_plan: true             │   │                           │
│   │  └─────────────────────────────────┘   │                           │
│   └────────────────────┬────────────────────┘                           │
│                        │                                                 │
│   ┌────────────────────┼────────────────────┐                           │
│   │      阶段 4: 系统提示词组装             │                           │
│   │                    ▼                    │                           │
│   │  ┌─────────────────────────────────┐   │                           │
│   │  │ _prompt_cache.get_system_prompt() │  │  ◄─ 直接从缓存取          │
│   │  │   (TaskComplexity.COMPLEX)       │   │                           │
│   │  │       ↓                          │   │                           │
│   │  │ system_prompt_complex (预生成)   │   │                           │
│   │  └─────────────────────────────────┘   │                           │
│   └────────────────────┬────────────────────┘                           │
│                        │                                                 │
│                        ▼                                                 │
│            ┌───────────────────────┐                                    │
│            │ LLM (Sonnet) 执行任务  │                                    │
│            └───────────────────────┘                                    │
│                                                                          │
│   性能优势：                                                              │
│   • 意图提示词: 缓存命中，0ms 分析开销                                   │
│   • 系统提示词: 缓存命中，0ms 生成开销                                   │
│   • 总节省: ~500ms/请求（避免每次 LLM 分析）                             │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### InstancePromptCache

**文件**: `core/prompt/instance_cache.py`

**职责**:
- 实例启动时一次性加载所有提示词版本
- 运行时提供毫秒级的提示词访问
- 管理缓存生命周期（包括失效检测）

```python
class InstancePromptCache:
    """
    实例级提示词缓存管理器（单例模式）
    
    核心属性：
    - prompt_schema: 解析后的提示词结构
    - agent_schema: Agent 配置
    - system_prompt_simple: Simple 版系统提示词
    - system_prompt_medium: Medium 版系统提示词
    - system_prompt_complex: Complex 版系统提示词
    - intent_prompt: 意图识别提示词
    """
    
    # 单例存储
    _instances: Dict[str, "InstancePromptCache"] = {}
    
    @classmethod
    def get_instance(cls, instance_name: str) -> "InstancePromptCache":
        """获取实例缓存（单例）"""
        if instance_name not in cls._instances:
            cls._instances[instance_name] = cls(instance_name)
        return cls._instances[instance_name]
    
    async def load_once(self, raw_prompt: str, config=None, force_refresh=False):
        """一次性加载（幂等）"""
        # 1. LLM 语义分析 → PromptSchema + AgentSchema
        # 2. 生成三个版本系统提示词
        # 3. 生成意图识别提示词
        pass
    
    def get_system_prompt(self, complexity: TaskComplexity) -> str:
        """获取对应复杂度的系统提示词（直接从缓存取）"""
        pass
    
    def get_intent_prompt(self) -> str:
        """获取意图识别提示词"""
        pass
```

**使用方式**:

```python
# 获取缓存实例
cache = InstancePromptCache.get_instance("test_agent")

# 启动时一次性加载
await cache.load_once(raw_prompt)

# 运行时获取
intent_prompt = cache.get_intent_prompt()  # 直接取
system_prompt = cache.get_system_prompt(TaskComplexity.MEDIUM)  # 直接取
```

### IntentPromptGenerator

**文件**: `core/prompt/intent_prompt_generator.py`

**职责**:
- 从 PromptSchema 动态生成意图识别提示词
- 用户配置优先，缺失用高质量默认

```python
class IntentPromptGenerator:
    """
    动态意图识别提示词生成器
    
    原则：用户配置优先，缺失用高质量默认
    """
    
    @classmethod
    def generate(cls, schema: PromptSchema) -> str:
        """
        根据 PromptSchema 生成意图识别提示词
        
        提取内容：
        1. 意图分类规则（如果运营定义了）
        2. 复杂度判断规则（如果运营定义了）
        3. 记忆检索规则（few-shot 示例驱动）
        """
        pass
    
    @classmethod
    def get_default(cls) -> str:
        """获取高质量默认提示词"""
        pass
```

### LLM Schema 生成器

**文件**: `core/agent/factory.py` → `_generate_schema_with_llm()`

**核心理念**:
- 删除硬编码关键词规则
- 使用高质量 Prompt + Few-shot 引导 LLM 推理

```python
# V4.6 硬编码规则（已删除）
if any(kw in prompt_lower for kw in ["excel", "表格", "xlsx"]):
    skills.append(SkillConfig(skill_id="xlsx"))

# V5.0 Few-shot 引导 LLM 推理
SCHEMA_GENERATOR_PROMPT = """
## Few-shot 示例

<example>
<prompt>帮我分析销售数据，生成周报</prompt>
<reasoning>业务场景：数据分析 + 表格生成（虽无"excel"关键词，但需要 xlsx）</reasoning>
<schema>{"tools": ["e2b_sandbox"], "skills": [{"skill_id": "xlsx"}]}</schema>
</example>

<example>
<prompt>帮我准备下周的产品演示材料</prompt>
<reasoning>业务场景：演示文稿（虽无"PPT"关键词，但"演示材料"暗示 pptx）</reasoning>
<schema>{"skills": [{"skill_id": "pptx"}]}</schema>
</example>
"""
```

### CacheStorageBackend

**文件**: `core/prompt/instance_cache.py`

**职责**:
- 🆕 V5.0: 缓存存储后端抽象，预留云端同步扩展点
- 当前实现: `LocalFileBackend`（本地文件系统）
- 未来扩展: `CloudSyncBackend`（S3/OSS/数据库）

```python
class CacheStorageBackend(ABC):
    """
    缓存存储后端抽象接口
    
    🆕 V5.0: 预留云端同步扩展点
    """
    
    @abstractmethod
    def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存缓存数据"""
        pass
    
    @abstractmethod
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载缓存数据"""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        pass


class LocalFileBackend(CacheStorageBackend):
    """
    本地文件存储后端
    
    存储位置：instances/xxx/.cache/
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存到本地 JSON 文件"""
        path = self.cache_dir / f"{key}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
```

**缓存文件结构**:

```
instances/test_agent/.cache/
├── prompt_cache.json       # 提示词缓存（3 版本系统提示词 + 意图提示词）
├── agent_schema.json       # AgentSchema 缓存
├── cache_meta.json         # 缓存元数据（哈希、时间戳、版本）
└── tools_inference.json    # 工具推断缓存（已有）
```

**缓存失效策略**:

```python
@dataclass
class CacheMeta:
    """缓存元数据"""
    prompt_hash: str        # prompt.md 的哈希
    config_hash: str        # config.yaml 的哈希
    combined_hash: str      # 组合哈希
    created_at: str         # 创建时间
    version: str = "5.0"    # 缓存版本

# 启动时验证
if meta.combined_hash != computed_hash:
    # 配置已变更，重新 LLM 分析
    pass
```

---

## 与 V4.6 的差异

| 维度 | V4.6 | V5.0 | 改进 |
|------|------|------|------|
| **提示词生成** | 每次请求动态裁剪 | 启动时一次性生成 3 版本 | 运行时零开销 |
| **Schema 生成** | 硬编码关键词规则 | LLM 语义分析 + Few-shot | 泛化能力强 |
| **意图提示词** | 硬编码模板 | 动态生成（用户配置优先） | 可定制 |
| **缓存管理** | 无统一缓存 | InstancePromptCache 单例 | 全局复用 |
| **🆕 持久化** | 无（每次重启 LLM 分析） | 本地文件持久化 | 后续启动 < 100ms |
| **🆕 云端扩展** | 无 | 预留 CacheStorageBackend 接口 | 未来可云同步 |
| **维护成本** | 高（改规则需改代码） | 低（改 Few-shot 即可） | Prompt-First |

---

## 代码-架构一致性清单

> ⚠️ **重要**: 确保代码实现与架构设计一致

| 架构要求 | 代码实现状态 | 文件位置 | 说明 |
|---------|-------------|---------|------|
| InstancePromptCache 单例模式 | ✅ 一致 | `core/prompt/instance_cache.py:111-124` | `get_instance()` 实现单例 |
| 启动时一次性加载 3 版本提示词 | ✅ 一致 | `instance_cache.py:277-310` | `_generate_all_prompts()` |
| IntentAnalyzer 使用缓存 intent_prompt | ✅ 一致 | `intent_analyzer.py:211-215` | `_get_intent_prompt()` 从缓存取 |
| SimpleAgent 使用缓存 system_prompt | ✅ **已修复** | `simple_agent.py:530-567` | 优先从 `_prompt_cache.get_system_prompt()` 取 |
| LLM 语义分析生成 AgentSchema | ✅ 一致 | `factory.py` | `_generate_schema_with_llm()` |
| IntentPromptGenerator 动态生成 | ✅ 一致 | `intent_prompt_generator.py` | `generate()` 方法 |
| 🆕 本地文件持久化 | ✅ 一致 | `instance_cache.py` | `_save_to_disk()` / `_try_load_from_disk()` |
| 🆕 CacheStorageBackend 抽象 | ✅ 一致 | `instance_cache.py:43-100` | 预留云端扩展点 |
| 🆕 缓存失效策略（哈希比对） | ✅ 一致 | `instance_cache.py:CacheMeta` | `prompt_hash` + `config_hash` |
| 🆕 instance_loader 传递 cache_dir | ✅ 一致 | `instance_loader.py:500-505` | 启用磁盘持久化 |

### 已修复项 (2026-01-09)

**修复**: `SimpleAgent.chat()` 现已使用 `_prompt_cache.get_system_prompt()`

**修复后代码** (`simple_agent.py:530-567`):
```python
# 🆕 V5.0: 优先使用 InstancePromptCache（启动时预生成，运行时零开销）
if self._prompt_cache and self._prompt_cache.is_loaded:
    # ========== V5.0: 直接从缓存取系统提示词 ==========
    from core.prompt import detect_complexity
    
    # 检测任务复杂度（使用缓存的 prompt_schema）
    complexity = detect_complexity(user_query, self._prompt_cache.prompt_schema)
    
    # 直接从缓存获取对应版本的提示词（启动时已预生成）
    base_prompt = self._prompt_cache.get_system_prompt(complexity)
    # ...
    logger.info(f"✅ V5.0 使用缓存提示词: {complexity.value}")
    
elif self.prompt_schema:
    # ========== Fallback: 动态生成（V4.6 兼容模式）==========
    # ...
```

**验证结果**: 端到端测试通过，日志显示 `✅ V5.0 使用缓存提示词: complex`

---

## 目录结构

```
zenflux_agent/
├── core/
│   ├── prompt/                     # 🆕 V5.0 核心模块
│   │   ├── __init__.py             # 统一导出
│   │   ├── instance_cache.py       # 🔥 实例级缓存管理器（单例模式 + 持久化）
│   │   │                           # 包含: InstancePromptCache, CacheStorageBackend,
│   │   │                           #       LocalFileBackend, CacheMeta
│   │   ├── intent_prompt_generator.py  # 🔥 动态意图提示词生成
│   │   ├── prompt_layer.py         # 提示词分层管理
│   │   ├── complexity_detector.py  # 复杂度检测器
│   │   └── llm_analyzer.py         # LLM 提示词语义分析器
│   │
│   ├── agent/
│   │   ├── factory.py              # 🔥 删除硬编码规则，改用 LLM 语义分析
│   │   ├── simple_agent.py         # ✅ 已修复：使用 _prompt_cache
│   │   └── intent_analyzer.py      # ✅ 已使用 _prompt_cache
│   │
│   └── ...
│
├── instances/
│   └── test_agent/                 # 示例实例
│       ├── prompt.md               # 运营写的系统提示词
│       ├── config.yaml             # 实例配置
│       ├── .env                    # 环境变量
│       └── .cache/                 # 🆕 V5.0 缓存目录（持久化）
│           ├── prompt_cache.json   #   提示词缓存（3 版本系统提示词 + 意图提示词）
│           ├── agent_schema.json   #   AgentSchema 缓存
│           ├── cache_meta.json     #   缓存元数据（哈希、时间戳）
│           └── tools_inference.json#   工具推断缓存（已有）
│
├── scripts/
│   ├── instance_loader.py          # 实例加载器（调用 InstancePromptCache，传 cache_dir）
│   ├── run_instance.py             # 运营入口
│   └── ops_e2e_verify.py           # 端到端验证脚本
│
└── docs/
    ├── 00-ARCHITECTURE-V5.md       # 🆕 本文档
    └── 00-ARCHITECTURE-V4.md       # V4 历史版本
```

---

## 快速验证

### 验证 InstancePromptCache 加载

```bash
cd CoT_agent/mvp/zenflux_agent
source /path/to/venv/bin/activate

# 运行端到端验证
python scripts/ops_e2e_verify.py --instance test_agent
```

预期输出:
```
✅ InstancePromptCache 加载: Simple=749字符, Medium=760字符, Complex=768字符
```

### 🆕 验证磁盘持久化

**首次启动（LLM 分析 + 写缓存）**:
```bash
# 清除现有缓存
rm -rf instances/test_agent/.cache/*.json

# 首次启动
python scripts/run_instance.py --instance test_agent
```

预期日志:
```
🔄 开始 LLM 分析: test_agent
   LLM 分析: 2312ms
💾 缓存已保存到磁盘: instances/test_agent/.cache
```

**后续启动（从磁盘加载）**:
```bash
# 再次启动（不清除缓存）
python scripts/run_instance.py --instance test_agent
```

预期日志:
```
✅ 从磁盘缓存加载: test_agent
   磁盘加载耗时: 45ms
```

**验证缓存文件**:
```bash
ls -la instances/test_agent/.cache/
# 预期输出:
# -rw-r--r--  prompt_cache.json      # 提示词缓存
# -rw-r--r--  agent_schema.json      # AgentSchema 缓存
# -rw-r--r--  cache_meta.json        # 缓存元数据
# -rw-r--r--  tools_inference.json   # 工具推断缓存

cat instances/test_agent/.cache/cache_meta.json
# 预期输出:
# {
#   "prompt_hash": "abc123...",
#   "config_hash": "def456...",
#   "combined_hash": "ghi789...",
#   "created_at": "2026-01-09T...",
#   "version": "5.0"
# }
```

### 验证缓存失效

```bash
# 修改 prompt.md
echo "# 新增内容" >> instances/test_agent/prompt.md

# 重新启动（配置变更，触发缓存失效）
python scripts/run_instance.py --instance test_agent
```

预期日志:
```
📁 缓存哈希不匹配: abc123... != xyz456...
🔄 开始 LLM 分析: test_agent
```

---

## 运营操作指南

### 配置变更后重启流程

当运营修改了 `prompt.md` 或 `config.yaml` 后，需要**手动重启** Agent 才能生效：

```bash
# 1. 修改配置文件
vim instances/test_agent/prompt.md
# 或
vim instances/test_agent/config.yaml

# 2. 重启 Agent（会自动检测配置变更）
python scripts/run_instance.py --instance test_agent
```

**自动检测机制**：
- 启动时计算 `prompt.md` + `config.yaml` 的内容哈希
- 与 `.cache/cache_meta.json` 中的哈希比对
- 哈希匹配 → 直接从磁盘加载缓存（< 100ms）
- 哈希不匹配 → 重新 LLM 分析 + 更新缓存（2-3秒）

**可选：强制刷新缓存**：
```bash
# 跳过哈希检测，强制重新生成缓存
python scripts/run_instance.py --instance test_agent --force-refresh
```

### 验证缓存使用

在 `SimpleAgent.chat()` 中添加日志:
```python
logger.info(f"系统提示词来源: {'缓存' if from_cache else '动态生成'}")
```

预期：每次请求都应显示 `来源: 缓存`

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V5.0.1 | 2026-01-09 | 🆕 本地文件持久化 + CacheStorageBackend 抽象（预留云端扩展） |
| V5.0 | 2026-01-09 | 实例级提示词缓存 + LLM 语义驱动 Schema |
| V4.6 | 2026-01-08 | 智能记忆检索决策 |
| V4.5 | - | Mem0 用户画像层 |
| V4.4 | - | Skills + Tools 整合 |
