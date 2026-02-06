"""
上下文工程模块（Context Engineering）

基于先进上下文管理架构原理实现的策略：
1. KV-Cache 优化 - 保持前缀稳定，最大化缓存命中率
2. Todo 重写 - 将任务目标注入上下文末尾（对抗 Lost-in-the-Middle）
3. 工具遮蔽 - 状态机驱动的工具可见性控制
4. 可恢复压缩 - 保留引用丢弃内容
5. 结构化变异 - 随机化输出格式防止模式模仿
6. 错误保留 - 保留失败记录作为学习素材

参考：
- Anthropic Blog: Effective harnesses for long-running agents
- ZenFlux V4.3 架构
- 先进 Agent 上下文管理最佳实践
"""

# 1. 标准库
import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from logger import get_logger

# 3. 本地模块
from tools.plan_todo_tool import format_plan_for_prompt
from utils.message_utils import append_text_to_last_block

# 2. 第三方库（无）


logger = get_logger(__name__)


# ===== 1. KV-Cache 优化 =====


class CacheOptimizer:
    """
    KV-Cache 优化器

    核心原则（保持前缀稳定）：
    - 时间戳不放前缀
    - Context 只追加不修改
    - 序列化确定性（sort_keys）

    效果：缓存命中的输入成本降低 10 倍（$0.30 vs $3.00/MTok）
    """

    @staticmethod
    def sort_json_keys(obj: Any) -> Any:
        """
        确保 JSON 键顺序一致性（序列化确定性）

        Args:
            obj: 任意 Python 对象

        Returns:
            键排序后的对象
        """
        if isinstance(obj, dict):
            return {k: CacheOptimizer.sort_json_keys(v) for k, v in sorted(obj.items())}
        elif isinstance(obj, list):
            return [CacheOptimizer.sort_json_keys(item) for item in obj]
        return obj

    @staticmethod
    def stable_json_dumps(obj: Any, **kwargs) -> str:
        """
        稳定的 JSON 序列化（保证相同输入产生相同输出）

        Args:
            obj: 要序列化的对象
            **kwargs: json.dumps 的其他参数

        Returns:
            JSON 字符串
        """
        sorted_obj = CacheOptimizer.sort_json_keys(obj)
        return json.dumps(sorted_obj, ensure_ascii=False, sort_keys=True, **kwargs)

    @staticmethod
    def extract_timestamp_safe(content: str) -> Tuple[str, Optional[str]]:
        """
        安全提取时间戳（不影响前缀稳定性）

        时间戳不应放在消息前缀，应该：
        1. 放在消息末尾
        2. 通过 metadata 传递
        3. 使用独立字段

        Args:
            content: 消息内容

        Returns:
            (不含时间戳的内容, 提取的时间戳)
        """
        # 匹配常见时间戳格式
        timestamp_patterns = [
            r"\[(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\]",
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}):? ",
        ]

        timestamp = None
        clean_content = content

        for pattern in timestamp_patterns:
            match = re.search(pattern, content)
            if match:
                timestamp = match.group(1)
                clean_content = re.sub(pattern, "", content).strip()
                break

        return clean_content, timestamp

    @staticmethod
    def calculate_prefix_hash(messages: List[Dict], prefix_length: int = -1) -> str:
        """
        计算消息前缀的哈希值（用于监控缓存命中）

        Args:
            messages: 消息列表
            prefix_length: 前缀长度（-1 表示除最后一条）

        Returns:
            前缀哈希值
        """
        if prefix_length == -1:
            prefix_length = len(messages) - 1 if messages else 0

        prefix_messages = messages[:prefix_length]
        prefix_str = CacheOptimizer.stable_json_dumps(prefix_messages)
        return hashlib.md5(prefix_str.encode()).hexdigest()[:12]


# ===== 2. Todo 重写（对抗 Lost-in-the-Middle） =====


class TodoRewriter:
    """
    Todo 重写器

    核心策略：将任务目标始终放在上下文末尾（注意力高区）

    通过 todo.md 在每步完成后更新，让目标始终在末尾。
    ZenFlux 使用 plan_todo_tool.get_context_for_llm() 实现类似效果。
    """

    @staticmethod
    def inject_plan_context(
        messages: List[Dict],
        plan: Optional[Dict],
        position: str = "end",  # "end" | "system_suffix" | "user_prefix"
    ) -> List[Dict]:
        """
        将 Plan 状态注入消息列表

        Args:
            messages: 原始消息列表
            plan: 当前计划
            position: 注入位置
                - "end": 添加到最后一条用户消息末尾
                - "system_suffix": 作为系统提示词后缀
                - "user_prefix": 添加到用户消息前

        Returns:
            注入后的消息列表
        """
        if not plan:
            return messages

        # 生成 Plan 上下文（使用新的格式化函数）
        plan_context = format_plan_for_prompt(plan)

        if not plan_context:
            return messages

        # 防止重复注入：如果历史消息里已包含旧的 Plan 注入块，先移除再追加
        # 注入格式固定为 "\n\n---\n📋 {plan_context}"，其中 plan_context 以 "## 当前任务计划" 开头
        marker = "\n\n---\n📋 ## 当前任务计划"

        # 深拷贝避免修改原列表
        result = [msg.copy() for msg in messages]

        if position == "end" and result:
            # 找到最后一条用户消息，使用通用方法追加
            for i in range(len(result) - 1, -1, -1):
                if result[i].get("role") == "user":
                    content = result[i].get("content", "")
                    if isinstance(content, str):
                        if marker in content:
                            content = content.split(marker)[0]
                        result[i]["content"] = f"{content}\n\n---\n📋 {plan_context}"
                    elif isinstance(content, list):
                        # content_blocks 格式，使用通用方法
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_value = block.get("text", "")
                                if isinstance(text_value, str) and marker in text_value:
                                    block["text"] = text_value.split(marker)[0]

                        # 清理可能产生的空 text block（Claude API 不接受空 block）
                        content[:] = [
                            b
                            for b in content
                            if not (
                                isinstance(b, dict)
                                and b.get("type") == "text"
                                and not str(b.get("text", "")).strip()
                            )
                        ]
                        append_text_to_last_block(content, f"\n\n---\n📋 {plan_context}")
                    break

        elif position == "user_prefix" and result:
            # 找到最后一条用户消息，添加前缀
            for i in range(len(result) - 1, -1, -1):
                if result[i].get("role") == "user":
                    content = result[i].get("content", "")
                    if isinstance(content, str):
                        result[i]["content"] = f"📋 {plan_context}\n\n---\n{content}"
                    elif isinstance(content, list):
                        # content_blocks 格式，在第一个 text block 前添加
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                block["text"] = f"📋 {plan_context}\n\n---\n{block['text']}"
                                break
                    break

        return result

    @staticmethod
    def generate_todo_reminder(plan: Optional[Dict]) -> str:
        """
        生成 Todo 提醒文本（用于注入末尾）

        Args:
            plan: 当前计划（新格式：name, overview, todos）

        Returns:
            Todo 提醒文本
        """
        if not plan:
            return ""

        # 新格式：name, todos
        goal = plan.get("name", "")
        todos = plan.get("todos", [])
        total_steps = len(todos)
        completed = sum(1 for t in todos if t.get("status") == "completed")
        in_progress_todos = [t for t in todos if t.get("status") == "in_progress"]
        pending_todos = [t for t in todos if t.get("status") == "pending"]

        # 确定当前步骤
        current_step = completed
        current_action = ""
        if in_progress_todos:
            current_action = in_progress_todos[0].get("content", "")
        elif pending_todos:
            current_action = pending_todos[0].get("content", "")

        status = "completed" if completed == total_steps else "executing"

        lines = [
            f"🎯 **当前目标**: {goal}",
            f"📊 **进度**: {completed}/{total_steps} ({int(completed/total_steps*100) if total_steps > 0 else 0}%)",
        ]

        if current_action and status == "executing":
            lines.append(f"⏳ **当前步骤**: {current_action}")

        if status == "completed":
            lines.append("✅ **状态**: 任务已完成")
        elif status == "partial":
            lines.append("⚠️ **状态**: 部分完成（有失败步骤）")

        return "\n".join(lines)


# ===== 3. 工具遮蔽（Tool Masking） =====


class AgentState(Enum):
    """Agent 状态枚举"""

    IDLE = "idle"
    PLANNING = "planning"
    BROWSING = "browsing"  # 浏览网页
    CODING = "coding"  # 编写代码
    SEARCHING = "searching"  # 搜索信息
    EXECUTING = "executing"  # 执行工具
    VALIDATING = "validating"  # 验证结果


@dataclass
class ToolMaskConfig:
    """工具遮蔽配置"""

    # 状态 → 允许的工具前缀
    # 🆕 bash/text_editor 已移除，改用 sandbox_* 工具
    state_tool_prefixes: Dict[AgentState, List[str]] = field(
        default_factory=lambda: {
            AgentState.IDLE: ["plan_", "web_", "file_", "sandbox_"],
            AgentState.PLANNING: ["plan_"],
            AgentState.BROWSING: ["web_", "browser_", "exa_"],
            AgentState.CODING: ["sandbox_", "e2b_", "code_"],
            AgentState.SEARCHING: ["web_", "exa_", "knowledge_"],
            AgentState.EXECUTING: ["*"],  # 允许所有
            AgentState.VALIDATING: ["plan_", "file_"],
        }
    )


class ToolMasker:
    """
    工具遮蔽器

    策略：工具列表保持不变，但通过状态机动态控制「此刻能选哪些」

    实现方式：
    - 工具定义始终完整（保护 KV-Cache）
    - 通过 logits mask 屏蔽不符合前缀的选项
    - ZenFlux 实现：在工具选择阶段过滤
    """

    def __init__(self, config: Optional[ToolMaskConfig] = None) -> None:
        self.config = config or ToolMaskConfig()
        self._current_state = AgentState.IDLE
        self._state_history: List[Tuple[datetime, AgentState]] = []

    @property
    def current_state(self) -> AgentState:
        return self._current_state

    def transition_to(self, new_state: AgentState) -> None:
        """
        状态转换

        Args:
            new_state: 新状态
        """
        if new_state != self._current_state:
            self._state_history.append((datetime.now(), new_state))
            logger.debug(f"🔄 Agent 状态转换: {self._current_state.value} → {new_state.value}")
            self._current_state = new_state

    def get_allowed_tools(self, all_tools: List[str]) -> List[str]:
        """
        获取当前状态下允许的工具

        Args:
            all_tools: 所有可用工具名称

        Returns:
            允许的工具列表
        """
        prefixes = self.config.state_tool_prefixes.get(self._current_state, ["*"])

        if "*" in prefixes:
            return all_tools

        allowed = []
        for tool in all_tools:
            for prefix in prefixes:
                if tool.startswith(prefix):
                    allowed.append(tool)
                    break

        return allowed

    def mask_tool_definitions(
        self,
        tool_definitions: List[Dict],
        strategy: str = "filter",  # "filter" | "disable" | "deprioritize"
    ) -> List[Dict]:
        """
        遮蔽工具定义

        Args:
            tool_definitions: 工具定义列表
            strategy: 遮蔽策略
                - "filter": 完全移除（会破坏 KV-Cache）
                - "disable": 保留定义但标记禁用（推荐）
                - "deprioritize": 保留但降低优先级

        Returns:
            处理后的工具定义
        """
        if strategy == "filter":
            # ⚠️ 会破坏 KV-Cache，不推荐
            allowed_names = set(self.get_allowed_tools([t["name"] for t in tool_definitions]))
            return [t for t in tool_definitions if t["name"] in allowed_names]

        elif strategy == "disable":
            # 推荐：保持定义完整，通过 description 提示禁用
            allowed_names = set(self.get_allowed_tools([t["name"] for t in tool_definitions]))
            result = []
            for tool in tool_definitions:
                tool_copy = tool.copy()
                if tool["name"] not in allowed_names:
                    tool_copy["description"] = (
                        f"[DISABLED in current state] {tool.get('description', '')}"
                    )
                result.append(tool_copy)
            return result

        else:  # deprioritize
            # 通过描述降低优先级
            allowed_names = set(self.get_allowed_tools([t["name"] for t in tool_definitions]))
            result = []
            for tool in tool_definitions:
                tool_copy = tool.copy()
                if tool["name"] not in allowed_names:
                    tool_copy["description"] = f"[Low priority] {tool.get('description', '')}"
                result.append(tool_copy)
            return result

    def infer_state_from_action(self, action: str, tool_name: Optional[str] = None) -> AgentState:
        """
        从动作推断状态

        Args:
            action: 动作描述
            tool_name: 工具名称

        Returns:
            推断的状态
        """
        action_lower = action.lower()

        if tool_name:
            if tool_name.startswith("plan_"):
                return AgentState.PLANNING
            elif tool_name.startswith(("web_", "exa_", "browser_")):
                return AgentState.BROWSING
            elif tool_name.startswith(("sandbox_", "e2b_", "code_")):
                return AgentState.CODING

        if any(kw in action_lower for kw in ["搜索", "查找", "search", "find"]):
            return AgentState.SEARCHING
        elif any(kw in action_lower for kw in ["代码", "编程", "code", "script"]):
            return AgentState.CODING
        elif any(kw in action_lower for kw in ["计划", "规划", "plan"]):
            return AgentState.PLANNING
        elif any(kw in action_lower for kw in ["验证", "检查", "validate", "check"]):
            return AgentState.VALIDATING

        return AgentState.EXECUTING


# ===== 4. 工具结果压缩（已移至 core.context.compaction.tool_result）=====
# 使用方式：
#   from core.context.compaction.tool_result import ToolResultCompressor
#   compressor = ToolResultCompressor()
#   text, metadata = await compressor.compress_if_needed(tool_name, tool_id, result)


# ===== 5. 结构化变异 =====


class StructuralVariation:
    """
    结构化变异器

    核心目的：打破表面模式匹配，迫使模型关注「内容」而非「格式」

    策略：
    - 随机变换序列化模板
    - 变换措辞和顺序
    - 变异程度随上下文长度和重复次数动态调整
    - 上限 80% 以保持可读性
    """

    # 进度表示模板
    PROGRESS_TEMPLATES = [
        "📊 进度: {completed}/{total} ({percent}%)",
        "✅ 已完成 {completed} / 共 {total} 步骤 ({percent}%)",
        "进度 [{bar}] {percent}%",
        "Step {current} of {total} | {percent}% done",
        "🎯 {completed}/{total} 完成",
    ]

    # 状态描述变体
    STATUS_VARIANTS = {
        "completed": ["已完成", "Done", "✓", "完成", "Finished"],
        "pending": ["待执行", "Pending", "○", "等待中", "Waiting"],
        "in_progress": ["执行中", "Running", "◐", "进行中", "Working"],
        "failed": ["失败", "Failed", "✗", "错误", "Error"],
    }

    # 分隔符变体
    SEPARATOR_VARIANTS = [
        "---",
        "===",
        "***",
        "───────────",
        "• • •",
    ]

    def __init__(
        self, variation_level: float = 0.3, max_variation: float = 0.8  # 0-1，越高变异越大
    ):
        self.variation_level = min(variation_level, max_variation)
        self._variation_count = 0

    def vary_progress_display(self, completed: int, total: int, current: int = 0) -> str:
        """
        变异进度显示格式

        Args:
            completed: 已完成数量
            total: 总数量
            current: 当前步骤

        Returns:
            变异后的进度文本
        """
        percent = int(completed / total * 100) if total > 0 else 0

        # 根据变异等级选择模板
        if random.random() < self.variation_level:
            template = random.choice(self.PROGRESS_TEMPLATES)
        else:
            template = self.PROGRESS_TEMPLATES[0]  # 默认模板

        # 生成进度条
        bar_length = 10
        filled = int(bar_length * completed / total) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_length - filled)

        return template.format(
            completed=completed, total=total, percent=percent, current=current + 1, bar=bar
        )

    def vary_status(self, status: str) -> str:
        """变异状态文本"""
        variants = self.STATUS_VARIANTS.get(status, [status])
        if random.random() < self.variation_level:
            return random.choice(variants)
        return variants[0]

    def vary_separator(self) -> str:
        """变异分隔符"""
        if random.random() < self.variation_level:
            return random.choice(self.SEPARATOR_VARIANTS)
        return self.SEPARATOR_VARIANTS[0]

    def vary_list_format(self, items: List[str], list_type: str = "bullet") -> str:
        """
        变异列表格式

        Args:
            items: 列表项
            list_type: 列表类型 ("bullet" | "numbered" | "checkbox")

        Returns:
            格式化的列表
        """
        formats = {
            "bullet": ["• ", "- ", "* ", "→ ", "◆ "],
            "numbered": ["{i}. ", "{i}) ", "({i}) ", "[{i}] "],
            "checkbox": ["[ ] ", "☐ ", "□ ", "◻ "],
        }

        prefixes = formats.get(list_type, formats["bullet"])

        if random.random() < self.variation_level:
            prefix_template = random.choice(prefixes)
        else:
            prefix_template = prefixes[0]

        result = []
        for i, item in enumerate(items, 1):
            prefix = prefix_template.format(i=i)
            result.append(f"{prefix}{item}")

        return "\n".join(result)

    def adjust_variation_level(self, context_length: int, repetition_count: int = 0) -> None:
        """
        动态调整变异等级

        Args:
            context_length: 上下文长度（tokens）
            repetition_count: 重复次数
        """
        # 上下文越长，变异越大（防止模式固化）
        length_factor = min(context_length / 100000, 1.0) * 0.3

        # 重复次数越多，变异越大
        repetition_factor = min(repetition_count / 10, 1.0) * 0.2

        self.variation_level = min(0.3 + length_factor + repetition_factor, 0.8)  # 上限

        self._variation_count += 1


# ===== 6. 错误保留 =====


@dataclass
class ErrorRecord:
    """错误记录"""

    tool_name: str
    error_type: str
    error_message: str
    input_params: Dict[str, Any]
    timestamp: str
    context: Optional[str] = None
    recovery_action: Optional[str] = None


class ErrorRetention:
    """
    错误保留器

    核心策略：完整保留错误记录，作为学习素材

    效果：模型能看到「刚才这个关键词没找到结果」，下一步自然会换个方向
    """

    def __init__(self, max_errors: int = 10) -> None:
        self.max_errors = max_errors
        self._errors: List[ErrorRecord] = []

    def record_error(
        self,
        tool_name: str,
        error: Exception,
        input_params: Dict[str, Any],
        context: Optional[str] = None,
    ) -> ErrorRecord:
        """
        记录错误

        Args:
            tool_name: 工具名称
            error: 异常对象
            input_params: 输入参数
            context: 上下文信息

        Returns:
            错误记录
        """
        record = ErrorRecord(
            tool_name=tool_name,
            error_type=type(error).__name__,
            error_message=str(error),
            input_params=input_params,
            timestamp=datetime.now().isoformat(),
            context=context,
        )

        self._errors.append(record)

        # 保持错误记录数量限制
        if len(self._errors) > self.max_errors:
            self._errors = self._errors[-self.max_errors :]

        logger.debug(f"📝 记录错误: {tool_name} - {record.error_type}")

        return record

    def record_recovery(self, error_record: ErrorRecord, recovery_action: str) -> None:
        """
        记录恢复动作

        Args:
            error_record: 错误记录
            recovery_action: 恢复动作描述
        """
        error_record.recovery_action = recovery_action

    def get_error_context(self, tool_name: Optional[str] = None) -> str:
        """
        获取错误上下文（用于注入 LLM）

        Args:
            tool_name: 过滤特定工具的错误

        Returns:
            错误上下文文本
        """
        errors = self._errors
        if tool_name:
            errors = [e for e in errors if e.tool_name == tool_name]

        if not errors:
            return ""

        lines = ["⚠️ 最近的错误记录（避免重复）："]

        for err in errors[-5:]:  # 最多显示 5 条
            lines.append(f"- {err.tool_name}: {err.error_message[:100]}")
            if err.recovery_action:
                lines.append(f"  → 恢复: {err.recovery_action}")

        return "\n".join(lines)

    def get_recent_errors(self, count: int = 5) -> List[ErrorRecord]:
        """获取最近的错误"""
        return self._errors[-count:]

    def clear(self) -> None:
        """清除错误记录"""
        self._errors.clear()


# ===== 整合类：ContextEngineeringManager =====


class ContextEngineeringManager:
    """
    上下文工程管理器（整合所有功能）

    提供统一接口管理：
    - KV-Cache 优化
    - Todo 重写
    - 工具遮蔽
    - 结构化变异
    - 错误保留

    工具结果压缩请使用：core.context.compaction.tool_result.ToolResultCompressor
    """

    def __init__(self) -> None:
        """初始化上下文工程管理器"""
        self.cache_optimizer = CacheOptimizer()
        self.todo_rewriter = TodoRewriter()
        self.tool_masker = ToolMasker()
        self.variation = StructuralVariation()
        self.error_retention = ErrorRetention()

        # 统计
        self._stats = {"cache_hits": 0, "variations": 0, "errors_recorded": 0}

    def prepare_messages_for_llm(
        self,
        messages: List[Dict],
        plan: Optional[Dict] = None,
        inject_plan: bool = True,
        inject_errors: bool = True,
    ) -> List[Dict]:
        """
        为 LLM 准备消息（应用所有优化）

        Args:
            messages: 原始消息列表
            plan: 当前计划
            inject_plan: 是否注入 Plan 状态
            inject_errors: 是否注入错误上下文

        Returns:
            优化后的消息列表
        """
        result = messages

        # 1. 注入 Plan 状态（Todo 重写）
        if inject_plan and plan:
            result = self.todo_rewriter.inject_plan_context(result, plan, position="end")

        # 2. 注入错误上下文
        if inject_errors:
            error_context = self.error_retention.get_error_context()
            if error_context and result:
                for i in range(len(result) - 1, -1, -1):
                    if result[i].get("role") == "user":
                        content = result[i].get("content", "")
                        if isinstance(content, str):
                            result[i] = result[i].copy()
                            result[i]["content"] = f"{content}\n\n{error_context}"
                        break

        return result

    def get_allowed_tools(self, all_tools: List[str]) -> List[str]:
        """获取当前状态下允许的工具"""
        return self.tool_masker.get_allowed_tools(all_tools)

    def transition_state(self, new_state: AgentState) -> None:
        """转换 Agent 状态"""
        self.tool_masker.transition_to(new_state)

    def record_error(self, tool_name: str, error: Exception, input_params: Dict[str, Any]):
        """记录错误"""
        self.error_retention.record_error(tool_name, error, input_params)
        self._stats["errors_recorded"] += 1

    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        return self._stats.copy()


# ===== 工厂函数 =====


def create_context_engineering_manager() -> ContextEngineeringManager:
    """
    创建上下文工程管理器

    Returns:
        ContextEngineeringManager 实例
    """
    return ContextEngineeringManager()
