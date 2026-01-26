"""
Plan/Todo Tool - 任务规划工具（智能版本 + 持久化支持）

设计原则：
1. 工具封装闭环：内部调用 Claude + Extended Thinking 生成智能计划
2. Agent 无需特殊逻辑，只负责编排
3. 🆕 自动持久化：通过 PlanMemory 支持跨 Session 恢复
4. 返回纯 JSON，前端自己渲染 UI

架构关系（V4.3 更新）：
```
┌─────────────────────────────────────────────────────────────┐
│  Frontend                                                    │
│  └── 接收 JSON，自己渲染 UI（进度条/看板/时间线）             │
└─────────────────────────────────────────────────────────────┘
                              ↑ plan_json (纯数据)
┌─────────────────────────────────────────────────────────────┐
│  Service 层 (ChatService)                                    │
│  ├── 接收 Tool 输出                                          │
│  ├── 更新 Conversation.metadata.plan                         │
│  └── 持久化到数据库                                          │
└─────────────────────────────────────────────────────────────┘
                              ↑ tool_result (智能生成结果)
┌─────────────────────────────────────────────────────────────┐
│  plan_todo_tool (智能工具)                                   │
│  ├── create_plan: 调用 Claude + Extended Thinking 生成计划   │
│  │               → 自动调用 PlanMemory.save_plan()          │
│  ├── update_step: 更新步骤状态                               │
│  │               → 自动调用 PlanMemory.update_step_status() │
│  ├── add_step: 动态添加步骤                                  │
│  └── replan: 重新规划                                        │
└─────────────────────────────────────────────────────────────┘
                              ↓ 自动持久化
┌─────────────────────────────────────────────────────────────┐
│  PlanMemory (core/memory/user/plan.py)                       │
│  ├── 存储位置: storage/users/{user_id}/plans/{task_id}.json │
│  ├── 核心规则: 步骤只能标记 passes: true，永不删除           │
│  └── 生成进度摘要: 用于自动注入 Prompt                       │
└─────────────────────────────────────────────────────────────┘
```

参考：
- Anthropic Blog: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- autonomous-coding 示例: feature_list.json + claude-progress.txt
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import aiofiles
from logger import get_logger
import os
import re
from pathlib import Path

from core.llm import create_claude_service, Message

logger = get_logger(__name__)


# ===== Skill 发现模块 =====
SKILLS_LIBRARY_PATH = Path(__file__).parent.parent / "skills" / "library"
CAPABILITIES_FILE = Path(__file__).parent.parent / "config" / "capabilities.yaml"


async def get_registered_skills_from_config() -> List[Dict[str, Any]]:
    """
    从 capabilities.yaml 读取已注册的 Skills（包含 skill_id）（异步）
    
    这是运行时的主要数据来源，不需要扫描本地目录。
    
    Returns:
        [
            {
                "name": "professional-ppt-generator",
                "skill_id": "skill_abc123xyz",
                "type": "SKILL",
                "subtype": "CUSTOM",
                "capabilities": ["ppt_generation", ...],
                "skill_path": "skills/library/professional-ppt-generator",
                ...
            },
            ...
        ]
    """
    import yaml
    
    if not CAPABILITIES_FILE.exists():
        logger.warning(f"⚠️ 配置文件不存在: {CAPABILITIES_FILE}")
        return []
    
    try:
        async with aiofiles.open(CAPABILITIES_FILE, 'r', encoding='utf-8') as f:
            content = await f.read()
            config = yaml.safe_load(content) or {}
        
        skills = []
        for cap in config.get("capabilities", []):
            # 筛选已注册的 Custom Skills（有 skill_id）
            if cap.get("type") == "SKILL" and cap.get("skill_id"):
                skills.append(cap)
        
        logger.info(f"📚 从 capabilities.yaml 读取 {len(skills)} 个已注册 Skills")
        return skills
        
    except Exception as e:
        logger.error(f"❌ 读取 capabilities.yaml 失败: {e}")
        return []


async def discover_skills() -> List[Dict[str, Any]]:
    """
    发现可用 Skills（异步）
    
    优先从 capabilities.yaml 读取已注册的 Skills（包含 skill_id），
    如果没有注册信息，则扫描本地 skills/library/ 目录。
    
    Returns:
        [
            {
                "name": "professional-ppt-generator",
                "skill_id": "skill_abc123xyz",  # 如果已注册
                "description": "根据用户需求，智能生成专业级 PPT",
                "version": "1.0.0",
                "tags": ["ppt", "presentation", "slidespeak"],
                "path": "/path/to/skill",
                "summary": "前 200 字摘要"
            },
            ...
        ]
    """
    # 1. 先从 capabilities.yaml 读取已注册的 Skills（异步）
    registered_skills = await get_registered_skills_from_config()
    registered_names = {s["name"] for s in registered_skills}
    
    # 2. 构建返回列表（已注册的优先）
    skills = []
    for cap in registered_skills:
        skill_path = cap.get("skill_path") or str(SKILLS_LIBRARY_PATH / cap["name"])
        skills.append({
            "name": cap["name"],
            "skill_id": cap.get("skill_id"),
            "description": cap.get("metadata", {}).get("description", ""),
            "version": "registered",
            "tags": cap.get("capabilities", []),
            "path": skill_path,
            "summary": cap.get("metadata", {}).get("description", "")[:200]
        })
    
    # 3. 扫描本地目录，补充未注册的 Skills
    if SKILLS_LIBRARY_PATH.exists():
        for skill_dir in SKILLS_LIBRARY_PATH.iterdir():
            if not skill_dir.is_dir() or skill_dir.name.startswith('_'):
                continue
            
            # 跳过已注册的
            if skill_dir.name in registered_names:
                continue
            
            skill_md_path = skill_dir / "SKILL.md"
            if not skill_md_path.exists():
                continue
            
            try:
                skill_info = await _parse_skill_md(skill_md_path)
                if skill_info:
                    skill_info["path"] = str(skill_dir)
                    skill_info["skill_id"] = None  # 未注册
                    skills.append(skill_info)
                    logger.debug(f"⚠️ 发现未注册 Skill: {skill_info['name']}")
            except Exception as e:
                logger.warning(f"⚠️ 解析 Skill 失败 {skill_dir.name}: {e}")
    
    logger.info(f"📚 共发现 {len(skills)} 个 Skills（{len(registered_skills)} 个已注册）")
    return skills


async def _parse_skill_md(skill_md_path: Path) -> Optional[Dict[str, Any]]:
    """
    解析 SKILL.md 文件，提取元数据（异步）
    """
    async with aiofiles.open(skill_md_path, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    # 解析 YAML frontmatter
    frontmatter_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not frontmatter_match:
        return None
    
    frontmatter = frontmatter_match.group(1)
    
    # 简单解析 YAML（避免引入额外依赖）
    skill_info = {
        "name": "",
        "description": "",
        "version": "1.0.0",
        "tags": [],
        "summary": ""
    }
    
    for line in frontmatter.split('\n'):
        line = line.strip()
        if line.startswith('name:'):
            skill_info["name"] = line.split(':', 1)[1].strip()
        elif line.startswith('description:'):
            skill_info["description"] = line.split(':', 1)[1].strip()
        elif line.startswith('version:'):
            skill_info["version"] = line.split(':', 1)[1].strip()
        elif line.startswith('- ') and skill_info.get("_in_tags"):
            skill_info["tags"].append(line[2:].strip())
        elif line == "tags:":
            skill_info["_in_tags"] = True
        elif line and not line.startswith('-'):
            skill_info["_in_tags"] = False
    
    skill_info.pop("_in_tags", None)
    
    # 提取 summary（第一个 ## 段落的前 300 字）
    body_start = frontmatter_match.end()
    body = content[body_start:body_start + 1000].strip()
    
    # 提取 "你是谁" 或第一个重要段落
    summary_match = re.search(r'## (你是谁|你的目标|简介)\s*\n+(.*?)(?=\n##|\Z)', body, re.DOTALL)
    if summary_match:
        skill_info["summary"] = summary_match.group(2).strip()[:300]
    else:
        skill_info["summary"] = body[:300]
    
    return skill_info if skill_info["name"] else None


def match_skills_for_query(query: str, skills: List[Dict]) -> List[Dict]:
    """
    根据用户查询匹配最相关的 Skills
    
    Args:
        query: 用户原始查询
        skills: 所有可用 Skills
        
    Returns:
        匹配的 Skills（按相关性排序）
    """
    if not skills:
        return []
    
    # 关键词匹配规则
    keyword_patterns = {
        "ppt": ["ppt", "演示", "presentation", "幻灯片", "slides"],
        "excel": ["excel", "表格", "xlsx", "数据分析", "spreadsheet"],
        "word": ["word", "文档", "document", "doc", "报告"],
        "planning": ["计划", "规划", "plan", "任务", "todo"]
    }
    
    query_lower = query.lower()
    matched = []
    
    for skill in skills:
        score = 0
        skill_tags = [t.lower() for t in skill.get("tags", [])]
        skill_name = skill.get("name", "").lower()
        skill_desc = skill.get("description", "").lower()
        
        # 1. 直接标签匹配
        for tag in skill_tags:
            if tag in query_lower:
                score += 10
        
        # 2. 关键词模式匹配
        for pattern_name, keywords in keyword_patterns.items():
            if any(kw in query_lower for kw in keywords):
                if any(kw in skill_name or kw in ' '.join(skill_tags) for kw in keywords):
                    score += 5
        
        # 3. 名称/描述相关性
        if any(word in skill_desc for word in query_lower.split()):
            score += 2
        
        if score > 0:
            matched.append({**skill, "_match_score": score})
    
    # 按匹配度排序
    matched.sort(key=lambda x: x.get("_match_score", 0), reverse=True)
    
    # 清理临时字段
    for m in matched:
        m.pop("_match_score", None)
    
    return matched[:3]  # 返回 top 3


def discover_all_tools(instance_tools: List[Dict] = None) -> List[Dict[str, Any]]:
    """
    🆕 V4.4 统一工具发现
    
    发现所有可用工具，包括：
    - 全局 Skills（从 capabilities.yaml）
    - 实例级 MCP 工具
    - 实例级 REST APIs
    
    Args:
        instance_tools: 实例级工具列表（从 InstanceToolRegistry.get_all_tools_unified()）
        
    Returns:
        统一格式的工具列表，用于 Plan 阶段工具推荐
    """
    all_tools = []
    
    # 1. 获取全局 Skills
    skills = discover_skills()
    for skill in skills:
        all_tools.append({
            "name": skill["name"],
            "type": "SKILL" if skill.get("skill_id") else "TOOL",
            "source": "global",
            "description": skill.get("description", ""),
            "tags": skill.get("tags", []),
            "skill_id": skill.get("skill_id")
        })
    
    # 2. 添加实例级工具
    if instance_tools:
        for tool in instance_tools:
            # 避免重复
            if not any(t["name"] == tool["name"] for t in all_tools):
                all_tools.append({
                    "name": tool["name"],
                    "type": tool.get("type", "TOOL"),
                    "source": tool.get("source", "instance"),
                    "description": tool.get("description", ""),
                    "tags": tool.get("capabilities", []),
                    "priority": tool.get("priority", 80)
                })
    
    logger.info(f"📚 统一工具发现: {len(all_tools)} 个工具（{len(skills)} 全局 + {len(instance_tools or [])} 实例）")
    return all_tools


def match_tools_for_query(query: str, tools: List[Dict]) -> List[Dict]:
    """
    🆕 V4.4 统一工具匹配
    
    根据用户查询匹配最相关的工具（Skills + MCP + APIs）
    
    Args:
        query: 用户原始查询
        tools: 所有可用工具（从 discover_all_tools()）
        
    Returns:
        匹配的工具（按相关性排序）
    """
    if not tools:
        return []
    
    # 扩展的关键词匹配规则
    keyword_patterns = {
        "ppt": ["ppt", "演示", "presentation", "幻灯片", "slides"],
        "excel": ["excel", "表格", "xlsx", "数据分析", "spreadsheet"],
        "word": ["word", "文档", "document", "doc", "报告"],
        "planning": ["计划", "规划", "plan", "任务", "todo"],
        # 🆕 新增实例工具常见关键词
        "flowchart": ["flowchart", "流程图", "图表", "chart", "关系图", "实体"],
        "workflow": ["workflow", "工作流", "dify", "自动化"],
        "api": ["api", "接口", "调用", "服务"]
    }
    
    query_lower = query.lower()
    matched = []
    
    for tool in tools:
        score = 0
        tool_tags = [t.lower() for t in tool.get("tags", [])]
        tool_name = tool.get("name", "").lower()
        tool_desc = tool.get("description", "").lower()
        
        # 1. 直接标签匹配
        for tag in tool_tags:
            if tag in query_lower:
                score += 10
        
        # 2. 关键词模式匹配
        for pattern_name, keywords in keyword_patterns.items():
            if any(kw in query_lower for kw in keywords):
                if any(kw in tool_name or kw in ' '.join(tool_tags) or kw in tool_desc for kw in keywords):
                    score += 5
        
        # 3. 名称/描述相关性
        for word in query_lower.split():
            if len(word) > 2:  # 跳过短词
                if word in tool_desc or word in tool_name:
                    score += 2
        
        # 4. 🆕 实例工具优先（MCP 工具通常更针对性）
        if tool.get("source") == "instance":
            score += 3
        
        if score > 0:
            matched.append({**tool, "_match_score": score})
    
    # 按匹配度排序
    matched.sort(key=lambda x: x.get("_match_score", 0), reverse=True)
    
    # 清理临时字段
    for m in matched:
        m.pop("_match_score", None)
    
    return matched[:5]  # 返回 top 5


# ===== 计划生成 Prompt =====
PLAN_GENERATION_PROMPT = """你是一个专业的任务规划专家。请根据用户的需求，生成一个详细且可执行的任务计划。

## 输入信息
- 用户需求: {user_query}
- 可用能力: {capabilities}
{skills_section}

## 输出格式要求
请以 JSON 格式输出计划，严格遵循以下结构：

```json
{{
    "goal": "用通俗易懂的语言描述任务目标（用户能理解的，不要技术术语）",
    "recommended_skill": {{
        "name": "匹配的 Skill 名称（如果有）",
        "skill_id": "Skill 的注册 ID（如果已注册）",
        "reason": "为什么推荐使用这个 Skill"
    }},
    "information_gaps": ["缺失的信息1", "缺失的信息2"],
    "steps": [
        {{
            "action": "具体要执行的动作描述（用户友好的步骤说明，解释这一步要做什么，用户能理解的语言）",
            "capability": "所需的能力分类",
            "skill_hint": "如果这一步应使用 Skill，填写 Skill 名称",
            "skill_id": "对应的 skill_id（如果有）",
            "purpose": "这一步的目的",
            "expected_output": "预期产出"
        }}
    ]
}}
```

## 重要：用户友好原则

**action 字段是展示给用户看的，必须遵循以下原则**：

1. **禁止技术术语**：
   - ❌ "调用 web_search 能力进行信息检索"
   - ✅ "搜索相关资料"
   - ❌ "执行 ppt_generation 工具生成演示文稿"
   - ✅ "制作PPT"
   - ❌ "调用 api_calling 进行数据分析"
   - ✅ "分析数据"

2. **使用日常语言**：
   - ❌ "初始化数据源并进行预处理"
   - ✅ "整理和准备数据"
   - ❌ "构建本体模型和实体关系"
   - ✅ "梳理业务流程"

3. **action 简洁明了**（5-15个字）：
   - ✅ "收集相关资料"、"整理内容大纲"、"生成PPT演示文稿"、"检查并优化内容"

4. **说人话**：
   - ❌ "通过调用深度搜索工具获取结构化信息数据"
   - ✅ "在网上查找相关的资料和数据"

## 规划原则
1. **Skill 优先**：如果有匹配的专业 Skill，优先使用 Skill 而非通用工具
2. 步骤要具体、可执行
3. 每个步骤只做一件事
4. 步骤之间要有逻辑顺序
5. 如果信息不足，在 information_gaps 中列出

## Skill 使用指引
- 如果匹配到 Skill，在 `recommended_skill` 中指定
- 在相关步骤的 `skill_hint` 中标注应使用的 Skill
- Skill 会在执行阶段被自动激活

请直接输出 JSON，不要添加其他说明。"""

# Skill 信息模板
SKILLS_SECTION_TEMPLATE = """
## 🎯 可用专业 Skills（优先使用）

以下是针对特定任务的专业 Skill，如果匹配请优先使用：

{skills_list}

**注意**：已注册的 Skill（有 skill_id）可在执行时直接调用。
"""

SKILL_ITEM_TEMPLATE = """### {name}
- **Skill ID**: {skill_id}
- **描述**: {description}
- **标签**: {tags}
- **能力**: {summary}
"""


class PlanTodoTool:
    """
    Plan/Todo 工具 - 智能版本 + 持久化支持
    
    关键设计：
    1. create_plan 调用 Claude + Extended Thinking 生成智能计划
    2. update_step/add_step 保持纯计算
    3. 🆕 自动持久化：通过 PlanMemory 支持跨 Session 恢复
    4. 接收 current_plan 作为参数
    
    持久化规则（借鉴 autonomous-coding）：
    - 步骤只能标记 passes: true，永不删除
    - 自动生成进度摘要用于 Prompt 注入
    - 对用户透明，框架自动处理
    """
    
    name = "plan_todo"
    description = """任务规划工具 - 智能版本（支持跨 Session 持久化）。

操作类型:
- create_plan: 创建智能任务计划（内部调用 Claude + Extended Thinking）
  data 格式: {
    "user_query": "用户的原始需求（必需）"
  }
  ⚠️ 工具会自动调用 Claude 生成最优计划！
  🆕 自动持久化到 PlanMemory，支持跨 Session 恢复

- update_step: 更新步骤状态
  data 格式: {"step_index": 0, "status": "completed|failed|in_progress", "result": "结果"}
  🆕 自动同步到 PlanMemory

- add_step: 动态添加步骤
  data 格式: {"action": "动作", "purpose": "目的"}

- replan: 重新生成计划（保留已完成步骤）
  data 格式: {
    "reason": "重新规划的原因（必需）",
    "strategy": "full（全量重规划）| incremental（保留已完成步骤，默认）"
  }
  ⚠️ 当发现以下情况时应该调用 replan:
    1. 多个步骤连续失败
    2. 发现原计划遗漏关键信息
    3. 用户需求发生变化
    4. 执行过程中发现更优方案

返回格式:
- status: success/error
- plan: 更新后的计划 JSON（由调用方存储）
- replan_count: 重新规划次数（replan 时返回）

注意：此工具不持有状态，plan 由调用方管理。
外部可通过静态方法 get_progress() / get_current_step() / get_context_for_llm() 查询计划状态。
"""
    
    def __init__(self, registry=None, memory_manager=None):
        """
        初始化工具
        
        Args:
            registry: CapabilityRegistry 实例（用于动态生成 Schema）
            memory_manager: MemoryManager 实例（用于 Plan 持久化）🆕
        """
        self._registry = registry
        self._memory_manager = memory_manager  # 🆕 PlanMemory 通过 MemoryManager 访问
        
        # 创建专用 LLM Service（启用 Extended Thinking）
        # 🆕 使用配置化的 LLM Profile
        from config.llm_config import get_llm_profile
        profile = get_llm_profile("plan_manager")
        self._llm = create_claude_service(**profile)
        
        persistence_status = "启用" if memory_manager else "禁用"
        logger.info(f"✅ PlanTodoTool 初始化完成（智能版本，Extended Thinking，持久化: {persistence_status}）")
    
    def get_input_schema(self) -> Dict:
        """
        动态生成 input_schema
        
        Returns:
            Tool 的 input_schema（Claude API 格式）
        """
        # 从 Registry 动态获取分类 ID
        capability_enum = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capability_enum = self._registry.get_category_ids()
        
        if not capability_enum:
            capability_enum = [
                "web_search", "ppt_generation", "document_creation",
                "data_analysis", "file_operations", "code_execution",
                "api_calling", "task_planning"
            ]
        
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "操作类型",
                    "enum": ["create_plan", "update_step", "add_step", "replan"]
                },
                "data": {
                    "type": "object",
                    "description": "操作数据",
                    "properties": {
                        "user_query": {
                            "type": "string",
                            "description": "用户的原始需求（create_plan 时必需）"
                        },
                        "goal": {
                            "type": "string",
                            "description": "任务目标（可选，create_plan 时会自动生成）"
                        },
                        "steps": {
                            "type": "array",
                            "description": "步骤列表（可选，create_plan 时会自动生成）",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string",
                                        "description": "步骤动作描述"
                                    },
                                    "capability": {
                                        "type": "string",
                                        "description": "所需能力分类",
                                        "enum": capability_enum
                                    },
                                    "purpose": {
                                        "type": "string",
                                        "description": "步骤目的"
                                    }
                                },
                                "required": ["action"]
                            }
                        },
                        "step_index": {
                            "type": "integer",
                            "description": "步骤索引（update_step 时必需）"
                        },
                        "status": {
                            "type": "string",
                            "description": "步骤状态（update_step 时必需）",
                            "enum": ["pending", "in_progress", "completed", "failed"]
                        },
                        "result": {
                            "type": "string",
                            "description": "步骤结果（update_step 时可选）"
                        },
                        "reason": {
                            "type": "string",
                            "description": "重新规划的原因（replan 时必需）"
                        },
                        "strategy": {
                            "type": "string",
                            "description": "重新规划策略（replan 时可选）",
                            "enum": ["full", "incremental"],
                            "default": "incremental"
                        }
                    }
                }
            },
            "required": ["operation"]
        }
    
    async def execute(
        self,
        operation: str,
        data: Dict[str, Any] = None,
        current_plan: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        执行工具操作
        
        Args:
            operation: 操作类型
            data: 操作数据
            current_plan: 当前计划（从 Conversation.metadata 传入）
            
        Returns:
            {
                "status": "success/error",
                "plan": {...},  # 新的计划 JSON
                "message": "..."
            }
        """
        data = data or {}
        
        try:
            if operation == "create_plan":
                # 智能计划生成（调用 Claude + Extended Thinking）
                result = await self._create_plan_smart(data)
                
                # 🆕 自动持久化到 PlanMemory
                if result.get("status") == "success" and self._memory_manager:
                    plan = result.get("plan", {})
                    self._persist_plan(plan)
                
                return result
                
            elif operation == "update_step":
                result = self._update_step(data, current_plan)
                
                # 🆕 同步步骤状态到 PlanMemory
                if result.get("status") == "success" and self._memory_manager:
                    plan = result.get("plan", {})
                    task_id = plan.get("task_id")
                    step_index = data.get("step_index")
                    status = data.get("status")
                    step_result = data.get("result", "")
                    
                    if task_id is not None and step_index is not None:
                        passes = (status == "completed")
                        self._memory_manager.plan.update_step_status(
                            task_id=task_id,
                            step_index=step_index,
                            passes=passes,
                            result=step_result
                        )
                
                return result
                
            elif operation == "add_step":
                return self._add_step(data, current_plan)
                
            elif operation == "replan":
                # 重新规划（保留已完成步骤或全量重规划）
                result = await self._replan(data, current_plan)
                
                # 🆕 更新持久化的计划
                if result.get("status") == "success" and self._memory_manager:
                    plan = result.get("plan", {})
                    self._persist_plan(plan)
                
                return result
            else:
                return {
                    "status": "error",
                    "message": f"Unknown operation: {operation}",
                    "available": ["create_plan", "update_step", "add_step", "replan"]
                }
        except Exception as e:
            logger.error(f"❌ PlanTodoTool 执行失败: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    def _persist_plan(self, plan: Dict) -> None:
        """
        持久化计划到 PlanMemory
        
        Args:
            plan: 计划数据
        """
        if not self._memory_manager:
            return
        
        try:
            task_id = plan.get("task_id")
            goal = plan.get("goal", "")
            steps = plan.get("steps", [])
            user_query = plan.get("user_query", "")
            
            # 提取元数据
            metadata = {
                "recommended_skill": plan.get("recommended_skill"),
                "matched_skills": plan.get("matched_skills"),
                "information_gaps": plan.get("information_gaps", []),
                "replan_count": plan.get("replan_count", 0)
            }
            
            self._memory_manager.plan.save_plan(
                task_id=task_id,
                goal=goal,
                steps=steps,
                user_query=user_query,
                metadata=metadata
            )
            
            logger.info(f"[PlanTodoTool] 计划已持久化: task_id={task_id}")
            
        except Exception as e:
            logger.warning(f"[PlanTodoTool] 持久化失败（不影响主流程）: {e}")
    
    def get_or_load_plan(self, task_id: str, current_plan: Optional[Dict] = None) -> Optional[Dict]:
        """
        获取或从持久化加载计划
        
        优先使用 current_plan，如果没有则从 PlanMemory 加载
        
        Args:
            task_id: 任务 ID
            current_plan: 当前内存中的计划
            
        Returns:
            计划数据，不存在则返回 None
        """
        if current_plan:
            return current_plan
        
        if self._memory_manager and task_id:
            return self._memory_manager.plan.load_plan(task_id)
        
        return None
    
    def get_session_summary(self, task_id: str) -> str:
        """
        获取 Session 进度摘要（用于注入 Prompt）
        
        Args:
            task_id: 任务 ID
            
        Returns:
            格式化的进度摘要
        """
        if not self._memory_manager:
            return ""
        
        return self._memory_manager.plan.get_session_summary(task_id)
    
    def has_persistent_plan(self, task_id: str) -> bool:
        """
        检查是否有持久化的计划
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否存在持久化计划
        """
        if not self._memory_manager:
            return False
        
        return self._memory_manager.plan.has_persistent_plan(task_id)
    
    async def _create_plan_smart(self, data: Dict) -> Dict:
        """
        智能创建任务计划（调用 Claude + Extended Thinking）
        
        Args:
            data: {user_query, goal?, steps?}
            
        Returns:
            {status, plan, message}
        """
        user_query = data.get('user_query', '')
        
        # 如果已提供完整的 goal 和 steps，直接使用（向后兼容）
        if data.get('goal') and data.get('steps'):
            logger.info("📋 使用提供的计划结构（向后兼容模式）")
            return self._create_plan_from_data(data)
        
        if not user_query:
            return {"status": "error", "message": "user_query is required for smart plan generation"}
        
        # 获取可用能力列表
        capabilities = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capabilities = self._registry.get_category_ids()
        if not capabilities:
            capabilities = [
                "web_search", "ppt_generation", "document_creation",
                "data_analysis", "file_operations", "code_execution",
                "code_sandbox", "app_generation", "api_calling", "task_planning"
            ]
        
        # 🆕 V4.4 修正: Plan 阶段只发现 Skills（用于 skill_id 匹配）
        # 不获取所有具体工具，避免上下文过长
        # 具体工具在执行阶段根据 Plan 步骤的 capability 动态选择
        all_skills = discover_skills()
        matched_skills = match_skills_for_query(user_query, all_skills)
        
        # 构建 Skills 信息段落
        skills_section = ""
        if matched_skills:
            skills_list = "\n".join([
                SKILL_ITEM_TEMPLATE.format(
                    name=s["name"],
                    skill_id=s.get("skill_id") or "未注册（请运行 skill_cli.py register）",
                    description=s.get("description", ""),
                    tags=", ".join(s.get("tags", [])),
                    summary=s.get("summary", "")[:200]
                )
                for s in matched_skills
            ])
            skills_section = SKILLS_SECTION_TEMPLATE.format(skills_list=skills_list)
            registered_count = sum(1 for s in matched_skills if s.get("skill_id"))
            logger.info(f"🎯 匹配到 {len(matched_skills)} 个 Skills（{registered_count} 个已注册）: {[s['name'] for s in matched_skills]}")
        else:
            logger.info("ℹ️ 未匹配到专业 Skill，将使用通用工具")
        
        # 构建 Prompt（包含 Skill 信息）
        prompt = PLAN_GENERATION_PROMPT.format(
            user_query=user_query,
            capabilities=", ".join(capabilities),
            skills_section=skills_section
        )
        
        logger.info(f"🧠 调用 Claude + Extended Thinking 生成计划...")
        logger.info(f"   用户需求: {user_query[:100]}...")
        if matched_skills:
            logger.info(f"   推荐 Skills: {[s['name'] for s in matched_skills]}")
        
        try:
            # 调用 Claude（启用 Extended Thinking）
            response = await self._llm.create_message_async(
                messages=[Message(role="user", content=prompt)],
                system="你是一个专业的任务规划专家，擅长将复杂任务分解为可执行的步骤。"
            )
            
            # 解析 JSON 响应
            content = response.content.strip()
            
            # 移除可能的 markdown 代码块标记
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            plan_data = json.loads(content)
            
            logger.info(f"✅ Claude 生成计划成功: {plan_data.get('goal', '')[:50]}...")
            
            # 提取推荐的 Skill
            recommended_skill = plan_data.get("recommended_skill")
            if recommended_skill:
                logger.info(f"🎯 推荐使用 Skill: {recommended_skill.get('name')} - {recommended_skill.get('reason', '')[:50]}")
            
            # 使用生成的数据创建计划
            return self._create_plan_from_data({
                "goal": plan_data.get("goal", user_query),
                "steps": plan_data.get("steps", []),
                "information_gaps": plan_data.get("information_gaps", []),
                "user_query": user_query,
                "recommended_skill": recommended_skill,
                "matched_skills": matched_skills  # 传递匹配的 Skills
            })
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 解析失败: {e}")
            logger.error(f"   响应内容: {content[:200]}...")
            # 降级：使用简单的默认计划
            return self._create_plan_from_data({
                "goal": user_query,
                "steps": [{"action": user_query, "capability": "task_planning"}],
                "user_query": user_query
            })
        except Exception as e:
            logger.error(f"❌ Claude 调用失败: {e}", exc_info=True)
            return {"status": "error", "message": f"Plan generation failed: {str(e)}"}
    
    def _create_plan_from_data(self, data: Dict) -> Dict:
        """
        从数据创建计划结构（纯计算）
        
        Args:
            data: {goal, steps, information_gaps, user_query, recommended_skill?, matched_skills?}
            
        Returns:
            {status, plan, message}
        """
        goal = data.get('goal', '')
        steps = data.get('steps', [])
        information_gaps = data.get('information_gaps', [])
        user_query = data.get('user_query', '')
        recommended_skill = data.get('recommended_skill')  # 🆕
        matched_skills = data.get('matched_skills', [])    # 🆕
        
        if not goal:
            return {"status": "error", "message": "Goal is required"}
        
        created_at = datetime.now().isoformat()
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 构建 plan 结构
        plan = {
            "task_id": task_id,
            "goal": goal,
            "user_query": user_query,
            "created_at": created_at,
            "updated_at": created_at,
            "information_gaps": information_gaps,
            "status": "executing",
            "current_step": 0,
            "total_steps": len(steps),
            "completed_steps": 0,
            "failed_steps": 0,
            "retry_count": 0,
            # 🆕 Skill 发现结果
            "recommended_skill": recommended_skill,
            "matched_skills": [
                {"name": s["name"], "description": s.get("description", "")}
                for s in matched_skills
            ] if matched_skills else [],
            "steps": []
        }
        
        for i, step in enumerate(steps):
            # 兼容字符串和字典两种格式
            if isinstance(step, str):
                step_data = {
                    "action": step,
                    "capability": "",
                    "query": "",
                    "purpose": "",
                    "expected_output": ""
                }
            else:
                step_data = step
            
            plan["steps"].append({
                "step_id": i + 1,
                "index": i,
                "action": step_data.get('action', ''),
                "capability": step_data.get('capability', ''),
                "skill_hint": step_data.get('skill_hint', ''),  # 🆕 Skill 提示
                "query": step_data.get('query', ''),
                "purpose": step_data.get('purpose', ''),
                "expected_output": step_data.get('expected_output', ''),
                "status": "pending" if i > 0 else "in_progress",
                "result": None,
                "retry_count": 0,
                "started_at": None,
                "completed_at": None
            })
        
        return {
            "status": "success",
            "message": f"Plan created: {goal}",
            "plan": plan
        }
    
    def _update_step(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        更新步骤状态（纯计算）
        
        Args:
            data: {step_index, status, result}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message}
        """
        if not current_plan:
            return {"status": "error", "message": "No active plan"}
        
        step_index = data.get('step_index')
        status = data.get('status', 'completed')
        result = data.get('result', '')
        
        if step_index is None:
            return {"status": "error", "message": "step_index is required"}
        
        if step_index >= len(current_plan.get('steps', [])):
            return {"status": "error", "message": f"Invalid step_index: {step_index}"}
        
        # 复制 plan（不修改原对象）
        plan = self._deep_copy_plan(current_plan)
        now = datetime.now().isoformat()
        plan["updated_at"] = now
        
        # 更新步骤
        step = plan['steps'][step_index]
        old_status = step['status']
        step['status'] = status
        step['result'] = result
        
        if status == 'in_progress' and not step.get('started_at'):
            step['started_at'] = now
        elif status in ['completed', 'failed']:
            step['completed_at'] = now
        
        # 处理重试
        if status == 'failed' and old_status != 'failed':
            step['retry_count'] = step.get('retry_count', 0) + 1
            plan['retry_count'] = plan.get('retry_count', 0) + 1
        
        # 统计
        plan['completed_steps'] = sum(1 for s in plan['steps'] if s['status'] == 'completed')
        plan['failed_steps'] = sum(1 for s in plan['steps'] if s['status'] == 'failed')
        
        # 自动推进 current_step
        if status == 'completed' and step_index == plan['current_step']:
            plan['current_step'] = min(step_index + 1, len(plan['steps']))
            # 标记下一步为 in_progress
            if plan['current_step'] < len(plan['steps']):
                plan['steps'][plan['current_step']]['status'] = 'in_progress'
                plan['steps'][plan['current_step']]['started_at'] = now
        
        # 检查是否全部完成
        all_done = all(s['status'] in ['completed', 'failed'] for s in plan['steps'])
        if all_done:
            if plan['completed_steps'] == len(plan['steps']):
                plan['status'] = 'completed'
            elif plan['failed_steps'] > 0:
                plan['status'] = 'partial'
        
        return {
            "status": "success",
            "message": f"Step {step_index + 1} → {status}",
            "plan": plan
        }
    
    def _add_step(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        动态添加步骤（纯计算）
        
        Args:
            data: {action, capability, purpose}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message}
        """
        if not current_plan:
            return {"status": "error", "message": "No active plan"}
        
        action = data.get('action', '')
        capability = data.get('capability', '')
        purpose = data.get('purpose', '')
        
        if not action:
            return {"status": "error", "message": "action is required"}
        
        # 复制 plan
        plan = self._deep_copy_plan(current_plan)
        now = datetime.now().isoformat()
        plan["updated_at"] = now
        
        new_index = len(plan['steps'])
        plan['steps'].append({
            "step_id": new_index + 1,
            "index": new_index,
            "action": action,
            "capability": capability,
            "purpose": purpose,
            "status": "pending",
            "result": None,
            "retry_count": 0,
            "started_at": None,
            "completed_at": None
        })
        plan['total_steps'] = len(plan['steps'])
        
        return {
            "status": "success",
            "message": f"Step {new_index + 1} added",
            "plan": plan
        }
    
    async def _replan(self, data: Dict, current_plan: Optional[Dict]) -> Dict:
        """
        重新生成计划（调用 Claude + Extended Thinking）
        
        策略：
        - incremental（默认）：保留已完成的步骤，只重新生成剩余步骤
        - full：全量重新生成计划（忽略已完成步骤）
        
        Args:
            data: {reason, strategy}
            current_plan: 当前计划
            
        Returns:
            {status, plan, message, replan_count}
        """
        reason = data.get('reason', '')
        strategy = data.get('strategy', 'incremental')
        
        if not reason:
            return {"status": "error", "message": "reason is required for replan"}
        
        if not current_plan:
            return {"status": "error", "message": "No active plan to replan"}
        
        # 检查重规划次数限制
        replan_count = current_plan.get('replan_count', 0) + 1
        max_replan = 3  # 默认最大重规划次数
        if replan_count > max_replan:
            return {
                "status": "error",
                "message": f"已达到最大重规划次数 ({max_replan})，请尝试其他方法",
                "replan_count": replan_count - 1
            }
        
        logger.info(f"🔄 开始重新规划 (第 {replan_count} 次)...")
        logger.info(f"   原因: {reason}")
        logger.info(f"   策略: {strategy}")
        
        # 获取原始用户需求
        user_query = current_plan.get('user_query', current_plan.get('goal', ''))
        
        # 收集执行上下文
        completed_steps = []
        failed_steps = []
        pending_steps = []
        
        for step in current_plan.get('steps', []):
            if step['status'] == 'completed':
                completed_steps.append({
                    'action': step['action'],
                    'result': step.get('result', '')
                })
            elif step['status'] == 'failed':
                failed_steps.append({
                    'action': step['action'],
                    'result': step.get('result', '')
                })
            else:
                pending_steps.append(step['action'])
        
        # 构建重规划 Prompt
        replan_prompt = self._build_replan_prompt(
            user_query=user_query,
            reason=reason,
            strategy=strategy,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            pending_steps=pending_steps,
            original_goal=current_plan.get('goal', '')
        )
        
        try:
            # 调用 Claude 重新规划
            response = await self._llm.create_message_async(
                messages=[Message(role="user", content=replan_prompt)],
                system="你是一个专业的任务规划专家。请根据执行情况重新规划任务，确保能够成功完成用户目标。"
            )
            
            # 解析响应
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            new_plan_data = json.loads(content)
            
            # 构建新计划
            now = datetime.now().isoformat()
            
            if strategy == "incremental":
                # 增量策略：保留已完成步骤
                new_plan = self._deep_copy_plan(current_plan)
                new_plan["updated_at"] = now
                new_plan["replan_count"] = replan_count
                new_plan["replan_reason"] = reason
                new_plan["status"] = "executing"
                
                # 移除未完成的步骤
                new_plan["steps"] = [s for s in new_plan["steps"] if s["status"] == "completed"]
                
                # 添加新生成的步骤
                new_steps = new_plan_data.get('steps', [])
                for i, step in enumerate(new_steps):
                    if isinstance(step, str):
                        step_data = {"action": step, "capability": "", "purpose": ""}
                    else:
                        step_data = step
                    
                    new_index = len(new_plan["steps"])
                    new_plan["steps"].append({
                        "step_id": new_index + 1,
                        "index": new_index,
                        "action": step_data.get('action', ''),
                        "capability": step_data.get('capability', ''),
                        "purpose": step_data.get('purpose', ''),
                        "expected_output": step_data.get('expected_output', ''),
                        "status": "in_progress" if new_index == len(new_plan["steps"]) else "pending",
                        "result": None,
                        "retry_count": 0,
                        "started_at": now if new_index == len(new_plan["steps"]) - 1 else None,
                        "completed_at": None
                    })
                
                # 更新计划元数据
                new_plan["total_steps"] = len(new_plan["steps"])
                new_plan["current_step"] = len(completed_steps)
                
            else:
                # 全量策略：完全重新生成
                result = self._create_plan_from_data({
                    "goal": new_plan_data.get("goal", current_plan.get("goal")),
                    "steps": new_plan_data.get("steps", []),
                    "information_gaps": new_plan_data.get("information_gaps", []),
                    "user_query": user_query
                })
                
                if result["status"] != "success":
                    return result
                
                new_plan = result["plan"]
                new_plan["replan_count"] = replan_count
                new_plan["replan_reason"] = reason
                new_plan["previous_completed_steps"] = completed_steps  # 保存历史记录
            
            logger.info(f"✅ 重新规划完成: {len(new_plan['steps'])} 个步骤")
            
            return {
                "status": "success",
                "message": f"Plan regenerated ({strategy}): {reason}",
                "plan": new_plan,
                "replan_count": replan_count
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ 重规划 JSON 解析失败: {e}")
            return {"status": "error", "message": f"Replan JSON parse error: {str(e)}"}
        except Exception as e:
            logger.error(f"❌ 重规划失败: {e}", exc_info=True)
            return {"status": "error", "message": f"Replan failed: {str(e)}"}
    
    def _build_replan_prompt(
        self,
        user_query: str,
        reason: str,
        strategy: str,
        completed_steps: List[Dict],
        failed_steps: List[Dict],
        pending_steps: List[str],
        original_goal: str
    ) -> str:
        """构建重规划 Prompt"""
        
        # 已完成步骤摘要
        completed_summary = ""
        if completed_steps:
            completed_summary = "\n".join([
                f"  ✅ {s['action']}: {s['result'][:100]}..." if len(s.get('result', '')) > 100 else f"  ✅ {s['action']}: {s.get('result', '无结果')}"
                for s in completed_steps
            ])
        else:
            completed_summary = "  （无）"
        
        # 失败步骤摘要
        failed_summary = ""
        if failed_steps:
            failed_summary = "\n".join([
                f"  ❌ {s['action']}: {s['result'][:100]}..." if len(s.get('result', '')) > 100 else f"  ❌ {s['action']}: {s.get('result', '未知错误')}"
                for s in failed_steps
            ])
        else:
            failed_summary = "  （无）"
        
        # 待执行步骤
        pending_summary = "\n".join([f"  ⏳ {s}" for s in pending_steps]) if pending_steps else "  （无）"
        
        # 获取可用能力
        capabilities = []
        if self._registry and hasattr(self._registry, 'get_category_ids'):
            capabilities = self._registry.get_category_ids()
        if not capabilities:
            capabilities = ["web_search", "code_execution", "code_sandbox", "file_operations", "api_calling"]
        
        prompt = f"""# 任务重规划请求

## 原始用户需求
{user_query}

## 原始目标
{original_goal}

## 重规划原因
{reason}

## 执行情况

### 已完成步骤
{completed_summary}

### 失败步骤
{failed_summary}

### 待执行步骤（将被替换）
{pending_summary}

## 重规划策略
- **{strategy}**: {'保留已完成步骤，只生成新的剩余步骤' if strategy == 'incremental' else '完全重新生成计划'}

## 可用能力
{', '.join(capabilities)}

## 输出要求
请生成新的任务计划，格式如下：

```json
{{
    "goal": "更新后的目标描述",
    "steps": [
        {{
            "action": "具体动作",
            "capability": "所需能力",
            "purpose": "目的"
        }}
    ],
    "information_gaps": ["如果有缺失信息"]
}}
```

{'注意：只需要生成**剩余步骤**，已完成的步骤会被保留。' if strategy == 'incremental' else '注意：生成完整的新计划。'}

请直接输出 JSON，不要添加其他说明。"""
        
        return prompt
    
    def _deep_copy_plan(self, plan: Dict) -> Dict:
        """深拷贝 plan 对象"""
        import copy
        return copy.deepcopy(plan)
    
    # ==================== 辅助方法（静态，供外部使用）====================
    
    @staticmethod
    def get_progress(plan: Optional[Dict]) -> Dict[str, Any]:
        """
        获取计划进度信息
        
        Args:
            plan: 计划对象
            
        Returns:
            {
                "has_plan": bool,
                "total": int,
                "completed": int,
                "failed": int,
                "progress": float (0-1),
                "current_step": int,
                "status": str
            }
        """
        if not plan:
            return {
                "has_plan": False,
                "total": 0,
                "completed": 0,
                "failed": 0,
                "progress": 0.0,
                "current_step": 0,
                "status": "none"
            }
        
        total = plan.get('total_steps', len(plan.get('steps', [])))
        completed = plan.get('completed_steps', 0)
        failed = plan.get('failed_steps', 0)
        
        return {
            "has_plan": True,
            "total": total,
            "completed": completed,
            "failed": failed,
            "progress": completed / total if total > 0 else 0.0,
            "current_step": plan.get('current_step', 0),
            "status": plan.get('status', 'executing'),
            "goal": plan.get('goal', '')
        }
    
    @staticmethod
    def get_current_step(plan: Optional[Dict]) -> Optional[Dict]:
        """获取当前步骤"""
        if not plan:
            return None
        idx = plan.get('current_step', 0)
        steps = plan.get('steps', [])
        if 0 <= idx < len(steps):
            return steps[idx]
        return None
    
    @staticmethod
    def get_context_for_llm(plan: Optional[Dict]) -> str:
        """
        获取精简的 Plan 上下文给 LLM
        
        减少 tokens 消耗
        """
        if not plan:
            return "[Plan] No active plan"
        
        total = plan.get('total_steps', 0)
        current_idx = plan.get('current_step', 0)
        completed = plan.get('completed_steps', 0)
        status = plan.get('status', 'executing')
        
        current_step = None
        steps = plan.get('steps', [])
        if 0 <= current_idx < len(steps):
            current_step = steps[current_idx]
        
        lines = [
            f"[Plan] {plan.get('goal', '')}",
            f"Status: {status} | Progress: {completed}/{total}"
        ]
        
        if current_step:
            lines.append(f"Current: {current_step.get('action', '')} → {current_step.get('purpose', '')}")
        
        return "\n".join(lines)


# 工具 Schema（用于 Claude API 注册）
PLAN_TODO_TOOL_SCHEMA = {
    "name": "plan_todo",
    "description": """智能任务规划工具。

操作：
- create_plan: 智能创建计划 {"user_query": "用户需求"}（自动调用 Claude + Extended Thinking）
- update_step: 更新步骤 {"step_index": 0, "status": "completed|failed|in_progress", "result": "..."}
- add_step: 添加步骤 {"action": "...", "purpose": "..."}
- replan: 重新规划 {"reason": "原因", "strategy": "full|incremental"}

返回新的 plan JSON，存储在消息列表的 tool_result 中。""",
    "input_schema": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "操作类型",
                "enum": ["create_plan", "update_step", "add_step", "replan"]
            },
            "data": {
                "type": "object",
                "description": "操作数据"
            }
        },
        "required": ["operation"]
    }
}


def create_plan_todo_tool(registry=None, memory_manager=None) -> PlanTodoTool:
    """
    创建 Plan/Todo 工具实例
    
    Args:
        registry: CapabilityRegistry 实例（用于动态生成 Schema）
        memory_manager: MemoryManager 实例（用于 Plan 持久化）🆕
    
    Returns:
        PlanTodoTool 实例
    """
    return PlanTodoTool(registry=registry, memory_manager=memory_manager)
