"""
PromptManager - 事件驱动的 Prompt 追加管理

核心思想：
- 与 RuntimeContext 高度耦合，在 Agent 运行时动态追加
- 事件触发 Prompt 追加（不是写死的规则）
- 防止重复追加（同一 fragment_id 只追加一次）

使用场景：
- 第 1 轮：session_start → 追加 sandbox_context
- 第 N 轮：调用 RAG 工具返回结果 → 追加 rag_context
- 第 M 轮：检测到 PPT 任务 → 追加 ppt_rules

与 RuntimeContext 集成：
    from core.context import RuntimeContext, PromptManager
    
    ctx = RuntimeContext(session_id="sess_123")
    prompt_mgr = PromptManager()
    
    # 会话开始时
    prompt_mgr.on_session_start(ctx, conversation_id="conv_456", user_id="user_789")
    
    # 工具执行后（如 RAG）
    prompt_mgr.on_tool_result(ctx, tool_name="rag_search", result=rag_result)
    
    # 获取当前 System Prompt（包含所有追加）
    system_prompt = prompt_mgr.build_system_prompt(ctx, base_prompt="...")
"""

import logging
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from pathlib import Path

if TYPE_CHECKING:
    from .runtime import RuntimeContext

logger = logging.getLogger(__name__)


# ===== 追加规则定义 =====

@dataclass
class PromptAppendRule:
    """Prompt 追加规则"""
    event_type: str                              # 触发事件类型
    fragment_id: str                             # 片段 ID
    condition: Optional[Callable[[Dict], bool]] = None  # 条件判断函数
    priority: int = 50                           # 优先级（越高越靠前）


@dataclass
class AppendedFragment:
    """已追加的片段"""
    fragment_id: str
    content: str
    priority: int
    event_type: str  # 触发的事件类型


@dataclass
class PromptState:
    """
    Prompt 追加状态（存储在 RuntimeContext 中）
    
    每个 RuntimeContext 独立维护，追加是累积的
    """
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    appended_fragments: Dict[str, AppendedFragment] = field(default_factory=dict)
    
    def append(
        self,
        fragment_id: str,
        content: str,
        priority: int,
        event_type: str,
        allow_update: bool = False
    ) -> bool:
        """
        追加片段（防止重复追加）
        
        Args:
            fragment_id: 片段 ID
            content: 片段内容
            priority: 优先级
            event_type: 触发的事件类型
            allow_update: 是否允许更新已存在的片段（默认 False）
            
        Returns:
            是否成功追加（如果已存在且不允许更新，返回 False）
        """
        # 防止重复追加
        if fragment_id in self.appended_fragments and not allow_update:
            logger.debug(f"⏭️ 跳过重复追加: {fragment_id}")
            return False
        
        self.appended_fragments[fragment_id] = AppendedFragment(
            fragment_id=fragment_id,
            content=content,
            priority=priority,
            event_type=event_type
        )
        logger.info(f"📝 Prompt 追加: {fragment_id} (priority={priority}, trigger={event_type})")
        return True
    
    def get_sorted_content(self) -> str:
        """
        获取按优先级排序的内容
        
        Returns:
            组装好的追加内容
        """
        if not self.appended_fragments:
            return ""
        
        sorted_fragments = sorted(
            self.appended_fragments.values(),
            key=lambda f: f.priority,
            reverse=True  # 优先级高的在前
        )
        return "\n\n---\n\n".join(f.content for f in sorted_fragments)
    
    def has_fragment(self, fragment_id: str) -> bool:
        """检查是否已追加某片段"""
        return fragment_id in self.appended_fragments
    
    def get_fragment_ids(self) -> List[str]:
        """获取所有已追加的片段 ID"""
        return list(self.appended_fragments.keys())
    
    def remove_fragment(self, fragment_id: str) -> bool:
        """移除片段"""
        if fragment_id in self.appended_fragments:
            del self.appended_fragments[fragment_id]
            logger.debug(f"🗑️ 移除片段: {fragment_id}")
            return True
        return False
    
    def clear(self):
        """清空所有追加"""
        self.appended_fragments.clear()
        logger.debug("🗑️ 清空所有 Prompt 追加")


class PromptManager:
    """
    事件驱动的 Prompt 管理器（与 RuntimeContext 集成）
    
    职责：
    1. 在 Agent 运行时动态追加 Prompt
    2. 防止重复追加（同一 fragment_id 只追加一次）
    3. 构建最终 System Prompt
    
    使用方式：
        ctx = RuntimeContext(session_id="sess_123")
        prompt_mgr = PromptManager()
        
        # 会话开始
        prompt_mgr.on_session_start(ctx, conversation_id="conv_456")
        
        # 工具执行后
        prompt_mgr.on_tool_result(ctx, tool_name="rag_search", result={...})
        
        # 获取 System Prompt
        system_prompt = prompt_mgr.build_system_prompt(ctx, base_prompt="...")
    """
    
    _instance: Optional["PromptManager"] = None
    
    # RuntimeContext 中存储 PromptState 的属性名
    PROMPT_STATE_ATTR = "_prompt_state"
    
    def __init__(self, fragments_dir: str = "prompts/fragments"):
        # 片段目录
        self._fragments_dir = Path(fragments_dir)
        
        # 片段缓存（启动时加载）
        self._fragment_cache: Dict[str, str] = {}
        
        # 加载片段
        self._load_fragments()
    
    @classmethod
    def get_instance(cls, fragments_dir: str = "prompts/fragments") -> "PromptManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(fragments_dir)
        return cls._instance
    
    def _load_fragments(self):
        """加载所有片段文件到缓存"""
        if not self._fragments_dir.exists():
            logger.warning(f"片段目录不存在: {self._fragments_dir}")
            return
        
        for file_path in self._fragments_dir.glob("*.md"):
            fragment_id = file_path.stem  # 文件名（不含扩展名）
            try:
                self._fragment_cache[fragment_id] = file_path.read_text(encoding="utf-8")
                logger.debug(f"📄 加载片段: {fragment_id}")
            except Exception as e:
                logger.error(f"加载片段失败 {fragment_id}: {e}")
    
    def _get_or_create_state(self, ctx: "RuntimeContext") -> PromptState:
        """
        从 RuntimeContext 获取或创建 PromptState
        
        Args:
            ctx: RuntimeContext 实例
            
        Returns:
            PromptState 实例
        """
        if not hasattr(ctx, self.PROMPT_STATE_ATTR):
            setattr(ctx, self.PROMPT_STATE_ATTR, PromptState())
        return getattr(ctx, self.PROMPT_STATE_ATTR)
    
    # ===== 事件触发方法（在 Agent 运行时调用） =====
    
    def on_session_start(
        self,
        ctx: "RuntimeContext",
        conversation_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        会话开始时调用 → 追加 sandbox_context
        
        Args:
            ctx: RuntimeContext 实例
            conversation_id: 对话 ID
            user_id: 用户 ID（可选）
            
        Returns:
            是否成功追加
        """
        state = self._get_or_create_state(ctx)
        state.conversation_id = conversation_id
        state.user_id = user_id
        
        # 构建沙盒上下文
        content = self._build_sandbox_context(state)
        if not content:
            return False
        
        return state.append(
            fragment_id="sandbox_context",
            content=content,
            priority=100,
            event_type="session_start"
        )
    
    def on_tool_result(
        self,
        ctx: "RuntimeContext",
        tool_name: str,
        result: Any,
        tool_id: Optional[str] = None
    ) -> bool:
        """
        工具执行完成后调用 → 根据工具类型追加对应上下文
        
        这是核心方法，在 Agent 的 RVR 循环中，工具执行后调用
        
        Args:
            ctx: RuntimeContext 实例
            tool_name: 工具名称
            result: 工具执行结果
            tool_id: 工具调用 ID（可选）
            
        Returns:
            是否成功追加
        """
        state = self._get_or_create_state(ctx)
        
        # RAG 相关工具 → 追加 RAG 上下文
        if tool_name in ("rag_search", "knowledge_search", "vector_search"):
            return self._append_rag_context(state, result)
        
        # 文件相关工具 → 追加文件上下文
        if tool_name in ("file_upload", "file_read"):
            return self._append_file_context(state, result)
        
        # E2B 沙盒工具 → 追加 E2B 规范（如果还没追加）
        if tool_name.startswith("e2b_") or tool_name.startswith("sandbox_"):
            return self._append_from_cache(state, "e2b_rules", priority=60, event_type="tool_result")
        
        return False
    
    def on_task_detected(
        self,
        ctx: "RuntimeContext",
        task_type: str,
        confidence: float = 1.0,
        variables: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        任务类型识别后调用 → 追加任务规范（支持变量注入）
        
        Args:
            ctx: RuntimeContext 实例
            task_type: 任务类型 (ppt_generation, excel_generation, code_task)
            confidence: 置信度
            variables: 自定义变量，用于替换片段中的 {{variable}} 占位符
            
        Returns:
            是否成功追加
            
        示例:
            # 生成 PPT 时注入自定义变量
            prompt_mgr.on_task_detected(
                ctx, 
                "ppt_generation",
                variables={"theme": "商务蓝", "page_count": 10}
            )
        """
        state = self._get_or_create_state(ctx)
        
        # 根据任务类型选择片段
        fragment_mapping = {
            "ppt_generation": "ppt_rules",
            "excel_generation": "excel_rules",
            "code_task": "code_rules",
        }
        
        fragment_id = fragment_mapping.get(task_type)
        if not fragment_id:
            return False
        
        return self._append_from_cache(
            state,
            fragment_id,
            priority=70,
            event_type="task_detected",
            variables=variables
        )
    
    def on_context_injected(
        self,
        ctx: "RuntimeContext",
        variables: Dict[str, Any]
    ) -> bool:
        """
        前端变量注入时调用 → 追加用户上下文
        
        Args:
            ctx: RuntimeContext 实例
            variables: 前端变量 {"location": "北京", "timezone": "Asia/Shanghai", ...}
            
        Returns:
            是否成功追加
        """
        state = self._get_or_create_state(ctx)
        
        content = self._build_user_context(variables)
        if not content:
            return False
        
        return state.append(
            fragment_id="user_context",
            content=content,
            priority=90,
            event_type="context_injected"
        )
    
    def on_files_uploaded(
        self,
        ctx: "RuntimeContext",
        files: List[Dict[str, Any]]
    ) -> bool:
        """
        文件上传时调用 → 追加文件上下文
        
        Args:
            ctx: RuntimeContext 实例
            files: 文件列表 [{"name": "...", "type": "...", "size": ...}, ...]
            
        Returns:
            是否成功追加
        """
        state = self._get_or_create_state(ctx)
        
        content = self._build_file_context(files)
        if not content:
            return False
        
        return state.append(
            fragment_id="file_context",
            content=content,
            priority=80,
            event_type="files_uploaded"
        )
    
    def append_custom(
        self,
        ctx: "RuntimeContext",
        fragment_id: str,
        content: str,
        priority: int = 50,
        allow_update: bool = False
    ) -> bool:
        """
        追加自定义内容
        
        Args:
            ctx: RuntimeContext 实例
            fragment_id: 片段 ID（用于防重复）
            content: 内容
            priority: 优先级
            allow_update: 是否允许更新已存在的片段
            
        Returns:
            是否成功追加
        """
        state = self._get_or_create_state(ctx)
        return state.append(
            fragment_id=fragment_id,
            content=content,
            priority=priority,
            event_type="custom",
            allow_update=allow_update
        )
    
    def append_fragment(
        self,
        ctx: "RuntimeContext",
        fragment_id: str,
        priority: int = 50,
        variables: Optional[Dict[str, Any]] = None,
        allow_update: bool = False
    ) -> bool:
        """
        追加缓存中的片段（支持变量注入）
        
        这是外部调用的主要方法，用于从缓存加载片段并注入变量。
        
        Args:
            ctx: RuntimeContext 实例
            fragment_id: 片段 ID（对应 prompts/fragments/ 下的文件名，不含 .md）
            priority: 优先级（越高越靠前）
            variables: 变量字典，用于替换 {{variable}} 占位符
            allow_update: 是否允许更新已存在的片段
            
        Returns:
            是否成功追加
            
        示例:
            # 加载 e2b_rules.md 并注入变量
            prompt_mgr.append_fragment(
                ctx,
                "e2b_rules",
                priority=60,
                variables={"sandbox_timeout": 300, "max_file_size": "10MB"}
            )
            
        片段变量格式:
            在 .md 文件中使用 {{variable_name}} 格式：
            - 会话 ID: {{conversation_id}}
            - 超时时间: {{sandbox_timeout}} 秒
        """
        state = self._get_or_create_state(ctx)
        
        content = self._fragment_cache.get(fragment_id, "")
        if not content:
            logger.warning(f"片段不存在: {fragment_id}")
            return False
        
        # 变量注入
        if variables:
            content = self._render_template(content, variables)
        
        # 注入 state 中的默认变量
        default_vars = {
            "conversation_id": state.conversation_id or "",
            "user_id": state.user_id or "",
        }
        content = self._render_template(content, default_vars)
        
        return state.append(
            fragment_id=fragment_id,
            content=content,
            priority=priority,
            event_type="fragment",
            allow_update=allow_update
        )
    
    def get_available_fragments(self) -> List[str]:
        """
        获取所有可用的片段 ID
        
        Returns:
            片段 ID 列表
        """
        return list(self._fragment_cache.keys())
    
    def reload_fragments(self):
        """
        重新加载所有片段（热更新）
        
        适用于修改了 prompts/fragments/ 下的文件后，不重启服务即可生效
        """
        self._fragment_cache.clear()
        self._load_fragments()
        logger.info(f"🔄 重新加载片段，共 {len(self._fragment_cache)} 个")
    
    # ===== 内部追加方法 =====
    
    def _append_rag_context(self, state: PromptState, result: Any) -> bool:
        """追加 RAG 上下文"""
        # 提取 RAG 结果
        if isinstance(result, dict):
            results_text = result.get("results", result.get("content", ""))
        elif isinstance(result, str):
            results_text = result
        else:
            results_text = str(result)
        
        if not results_text:
            return False
        
        content = self._build_rag_context(results_text)
        return state.append(
            fragment_id="rag_context",
            content=content,
            priority=85,
            event_type="tool_result",
            allow_update=True  # RAG 可以更新（多次检索）
        )
    
    def _append_file_context(self, state: PromptState, result: Any) -> bool:
        """追加文件上下文"""
        if isinstance(result, dict):
            files = result.get("files", [result])
        elif isinstance(result, list):
            files = result
        else:
            return False
        
        content = self._build_file_context(files)
        if not content:
            return False
        
        return state.append(
            fragment_id="file_context",
            content=content,
            priority=80,
            event_type="tool_result",
            allow_update=True  # 文件可以更新（多个文件）
        )
    
    def _append_from_cache(
        self,
        state: PromptState,
        fragment_id: str,
        priority: int,
        event_type: str,
        variables: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        从缓存追加片段（支持变量注入）
        
        Args:
            state: PromptState 实例
            fragment_id: 片段 ID
            priority: 优先级
            event_type: 事件类型
            variables: 变量字典，用于替换 {{variable}} 占位符
            
        Returns:
            是否成功追加
            
        变量格式：
            片段中使用 {{variable_name}} 格式的占位符
            例如：{{conversation_id}}, {{user_id}}, {{file_name}}
        """
        content = self._fragment_cache.get(fragment_id, "")
        if not content:
            logger.warning(f"片段不存在: {fragment_id}")
            return False
        
        # 变量注入
        if variables:
            content = self._render_template(content, variables)
        
        # 也注入 state 中的默认变量
        default_vars = {
            "conversation_id": state.conversation_id or "",
            "user_id": state.user_id or "",
        }
        content = self._render_template(content, default_vars)
        
        return state.append(
            fragment_id=fragment_id,
            content=content,
            priority=priority,
            event_type=event_type
        )
    
    def _render_template(self, template: str, variables: Dict[str, Any]) -> str:
        """
        渲染模板，替换 {{variable}} 占位符
        
        Args:
            template: 模板字符串
            variables: 变量字典
            
        Returns:
            渲染后的字符串
        """
        import re
        
        def replace_var(match):
            var_name = match.group(1).strip()
            value = variables.get(var_name)
            if value is not None:
                return str(value)
            # 未找到变量，保留原样
            return match.group(0)
        
        # 匹配 {{variable}} 格式
        return re.sub(r'\{\{(\w+)\}\}', replace_var, template)
    
    # ===== 动态内容生成 =====
    
    def _build_sandbox_context(self, state: PromptState) -> str:
        """
        构建沙盒上下文
        
        Args:
            state: PromptState 实例
            
        Returns:
            沙盒上下文内容
        """
        conversation_id = state.conversation_id
        user_id = state.user_id
        
        if not conversation_id:
            return ""
        
        content = f"""
# 📌 当前会话上下文（CRITICAL）

**必须使用以下参数调用 sandbox_* 工具：**

- **conversation_id**: `{conversation_id}`
"""
        
        if user_id:
            content += f"- **user_id**: `{user_id}`\n"
        
        content += f"""
## 沙盒工具使用示例

```json
{{
    "conversation_id": "{conversation_id}",
    "path": "/home/user/app/index.html",
    "content": "..."
}}
```

⚠️ **注意**：调用 sandbox_* 工具时必须使用上面的 conversation_id，否则会失败。
"""
        return content.strip()
    
    def _build_user_context(self, variables: Dict[str, Any]) -> str:
        """
        构建用户上下文
        
        Args:
            variables: 前端变量
            
        Returns:
            用户上下文内容
        """
        if not variables:
            return ""
        
        lines = ["# 用户上下文（系统自动注入，帮助你理解用户环境）", ""]
        
        for var_name, var_data in variables.items():
            if isinstance(var_data, dict):
                value = var_data.get("value", "")
                description = var_data.get("description", "")
                if value:
                    lines.append(f"- **{var_name}**: {value}（{description}）")
            else:
                lines.append(f"- **{var_name}**: {var_data}")
        
        return "\n".join(lines)
    
    def _build_rag_context(self, results: str) -> str:
        """
        构建 RAG 上下文
        
        Args:
            results: RAG 检索结果
            
        Returns:
            RAG 上下文内容
        """
        if not results:
            return ""
        
        return f"""
# 📚 相关知识（来自知识库）

以下是从知识库检索到的相关信息，请优先参考：

{results}

---

**注意**：如果以上知识不足以回答用户问题，可以使用 web_search 工具获取更多信息。
""".strip()
    
    def _build_file_context(self, files: List[Dict[str, Any]]) -> str:
        """
        构建文件上下文
        
        Args:
            files: 文件列表
            
        Returns:
            文件上下文内容
        """
        if not files:
            return ""
        
        lines = ["# 📎 用户上传的文件", ""]
        
        for f in files:
            name = f.get("name", "unknown")
            file_type = f.get("type", "unknown")
            size = f.get("size", 0)
            lines.append(f"- **{name}** ({file_type}, {size} bytes)")
        
        lines.append("")
        lines.append("请根据用户的问题处理这些文件。")
        
        return "\n".join(lines)
    
    # ===== System Prompt 构建 =====
    
    def build_system_prompt(
        self,
        ctx: "RuntimeContext",
        base_prompt: Optional[str] = None
    ) -> str:
        """
        构建最终 System Prompt
        
        Args:
            ctx: RuntimeContext 实例
            base_prompt: 基础 Prompt（可选，如果不传则只返回追加内容）
            
        Returns:
            完整的 System Prompt
        """
        state = self._get_or_create_state(ctx)
        
        # 获取所有追加内容
        appended_content = state.get_sorted_content()
        
        if base_prompt:
            if appended_content:
                return f"{base_prompt}\n\n---\n\n{appended_content}"
            return base_prompt
        
        return appended_content
    
    def get_appended_fragments(self, ctx: "RuntimeContext") -> List[str]:
        """
        获取已追加的片段列表
        
        Args:
            ctx: RuntimeContext 实例
            
        Returns:
            片段 ID 列表
        """
        state = self._get_or_create_state(ctx)
        return state.get_fragment_ids()
    
    def has_fragment(self, ctx: "RuntimeContext", fragment_id: str) -> bool:
        """
        检查是否已追加某片段
        
        Args:
            ctx: RuntimeContext 实例
            fragment_id: 片段 ID
            
        Returns:
            是否已追加
        """
        state = self._get_or_create_state(ctx)
        return state.has_fragment(fragment_id)
    
    def clear_prompts(self, ctx: "RuntimeContext"):
        """
        清空当前上下文的所有追加
        
        Args:
            ctx: RuntimeContext 实例
        """
        state = self._get_or_create_state(ctx)
        state.clear()
    
    def get_prompt_state(self, ctx: "RuntimeContext") -> PromptState:
        """
        获取当前上下文的 PromptState
        
        Args:
            ctx: RuntimeContext 实例
            
        Returns:
            PromptState 实例
        """
        return self._get_or_create_state(ctx)


# ===== 工厂函数 =====

def create_prompt_manager(fragments_dir: str = "prompts/fragments") -> PromptManager:
    """
    创建 PromptManager 实例
    
    Args:
        fragments_dir: 片段目录
        
    Returns:
        PromptManager 实例
    """
    return PromptManager(fragments_dir)


def get_prompt_manager() -> PromptManager:
    """
    获取 PromptManager 单例
    
    Returns:
        PromptManager 单例实例
    """
    return PromptManager.get_instance()

