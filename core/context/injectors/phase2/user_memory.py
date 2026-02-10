"""
UserMemoryInjector - 用户记忆注入器

职责：
1. 从 MEMORY.md 读取用户可编辑的记忆档案（Source of Truth）
2. 从 Mem0 获取语义搜索的用户画像（补充）
3. 融合去重后格式化为 XML 标签注入
4. 控制注入预算（MAX_TOKENS=500，符合上下文工程规范）

读取闭环：
- MEMORY.md 是用户可见可编辑的记忆源
- Mem0 是语义搜索的补充
- 两个来源融合后注入上下文

缓存策略：SESSION（5min 缓存）
注入位置：Phase 2 - User Context Message
优先级：90（最高，用户信息最重要）
"""

from typing import Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.user_memory")

# 注入预算控制（符合 RULE 18-context-engineering 的 Injector 预算规范）
# 记忆召回上限 500 tokens ≈ 1500 中文字符
MAX_INJECT_CHARS = 1500

# MEMORY.md 在融合中的最大预算占比
_MD_BUDGET_RATIO = 0.6  # 60% 给 MEMORY.md, 40% 给 Mem0


class UserMemoryInjector(BaseInjector):
    """
    用户记忆注入器

    融合读取 MEMORY.md（用户可编辑）+ Mem0（语义搜索），
    注入到 user context message。

    输出示例：
    ```
    <user_memory>
    ## 记忆档案
    - 用户偏好 Python 编程
    - 喜欢简洁的代码风格

    ## 相关记忆
    - 常用 FastAPI 框架
    - 使用 macOS 开发环境
    </user_memory>
    ```
    """

    @property
    def name(self) -> str:
        return "user_memory"

    @property
    def phase(self) -> InjectionPhase:
        return InjectionPhase.USER_CONTEXT

    @property
    def cache_strategy(self) -> CacheStrategy:
        # 用户画像相对稳定，会话级缓存
        return CacheStrategy.SESSION

    @property
    def priority(self) -> int:
        # 用户信息最重要，放在最前面
        return 90

    async def should_inject(self, context: InjectionContext) -> bool:
        """需要有用户 ID 且未跳过记忆检索"""
        if not context.user_id:
            return False
        # 尊重意图分析的 skip_memory 信号（简单问答无需记忆召回）
        intent = context.intent
        if intent and getattr(intent, "skip_memory", False):
            logger.debug("skip_memory=True, 跳过用户记忆注入")
            return False
        return True

    async def inject(self, context: InjectionContext) -> InjectionResult:
        """
        注入用户记忆（融合 MEMORY.md + Mem0）

        1. 从 MEMORY.md 读取用户记忆档案（Source of Truth）
        2. 从 Mem0 获取语义搜索补充
        3. 融合去重后注入
        """
        # 1. 检查预加载的用户画像（向后兼容）
        user_profile = context.get("user_profile")

        if user_profile:
            logger.debug(f"使用预加载的用户画像: {len(user_profile)} 字符")
        else:
            # 2. 融合读取：MEMORY.md + Mem0
            user_profile = await self._fetch_fused_memory(context)

        if not user_profile:
            logger.debug("用户画像为空，跳过")
            return InjectionResult()

        # 预算控制：截断到 MAX_INJECT_CHARS（~500 tokens）
        if len(user_profile) > MAX_INJECT_CHARS:
            user_profile = user_profile[:MAX_INJECT_CHARS] + "\n..."
            logger.info(
                f"UserMemoryInjector: 截断到 {MAX_INJECT_CHARS} 字符（预算控制）"
            )
        else:
            logger.info(f"UserMemoryInjector: {len(user_profile)} 字符")

        return InjectionResult(content=user_profile, xml_tag="user_memory")

    async def _fetch_fused_memory(
        self, context: InjectionContext
    ) -> Optional[str]:
        """
        Fused memory read: MEMORY.md (primary) + Mem0 (supplementary).

        MEMORY.md is the Source of Truth — user can directly edit it.
        Mem0 provides semantic search for relevant memories.
        Both are merged and deduped within budget.
        """
        md_content = await self._fetch_from_markdown(context)
        mem0_content = await self._fetch_from_mem0(context)

        if not md_content and not mem0_content:
            return None

        # Budget allocation
        md_budget = int(MAX_INJECT_CHARS * _MD_BUDGET_RATIO)
        mem0_budget = MAX_INJECT_CHARS - md_budget

        parts = []

        if md_content:
            # Trim MEMORY.md to budget, keep meaningful content
            trimmed = self._trim_markdown_memory(md_content, md_budget)
            if trimmed:
                parts.append(trimmed)

        if mem0_content:
            # Mem0 content already formatted, trim to remaining budget
            if len(mem0_content) > mem0_budget:
                mem0_content = mem0_content[:mem0_budget]
            if mem0_content.strip():
                parts.append(mem0_content)

        if not parts:
            return None

        return "\n\n".join(parts)

    async def _fetch_from_markdown(
        self, context: InjectionContext
    ) -> Optional[str]:
        """
        Read MEMORY.md via InstanceMemoryManager.

        This is the Source of Truth — user editable memory file.
        """
        try:
            from core.memory.instance_memory import InstanceMemoryManager

            # Read memory.enabled from config (same pattern as memory_flush.py)
            _memory_enabled = True
            try:
                import os
                import yaml
                from utils.app_paths import get_instances_dir
                _inst = os.getenv("AGENT_INSTANCE", "default")
                _cfg_path = get_instances_dir() / _inst / "config" / "memory.yaml"
                if _cfg_path.exists():
                    with open(_cfg_path) as _f:
                        _mem_section = (yaml.safe_load(_f) or {}).get("memory", {})
                    _memory_enabled = _mem_section.get("enabled", True)
            except Exception:
                pass

            mgr = InstanceMemoryManager(
                user_id=context.user_id or "default",
                mem0_enabled=False,  # Only need file layer for injection
                enabled=_memory_enabled,
            )
            content = await mgr.get_memory_context()

            if not content or len(content.strip()) < 20:
                return None

            logger.debug(
                f"MEMORY.md 读取成功: {len(content)} 字符"
            )
            return content

        except Exception as e:
            logger.warning(f"MEMORY.md 读取失败: {e}")
            return None

    async def _fetch_from_mem0(
        self, context: InjectionContext
    ) -> Optional[str]:
        """
        Fetch user profile from Mem0 — hybrid strategy:
        1. Semantic search on current query (finds task-relevant memories)
        2. Category recall: always fetch latest style/preference memories
           (even if current query is unrelated — user style should ALWAYS apply)

        This fixes the G1 failure where "写健身房文章" didn't recall "毒舌风格"
        because semantic distance was too large.
        """
        if not context.user_id:
            return None

        parts = []
        try:
            # Strategy 1: Semantic search (existing behavior)
            from core.agent.context.prompt_builder import fetch_user_profile

            profile = fetch_user_profile(
                user_id=context.user_id,
                user_query=context.user_query or "",
            )
            if profile and profile.strip():
                parts.append(profile)

        except ImportError:
            logger.debug("prompt_builder 模块不可用，跳过 Mem0 语义搜索")
        except Exception as e:
            logger.warning(f"Mem0 语义搜索失败: {e}")

        try:
            # Strategy 2: Category recall — always fetch style/preference
            # These should ALWAYS be injected regardless of current query topic
            style_memories = await self._recall_by_category(
                context.user_id, categories=["style", "preference"]
            )
            if style_memories:
                # Dedupe against semantic results
                existing = set((parts[0] or "").split("\n")) if parts else set()
                new_items = [m for m in style_memories if m not in existing]
                if new_items:
                    parts.append(
                        "## 用户风格/偏好（始终生效）\n" + "\n".join(f"- {m}" for m in new_items)
                    )
                    logger.info(
                        f"Category recall: {len(new_items)} style/preference memories injected"
                    )
        except Exception as e:
            logger.debug(f"Category recall failed (non-fatal): {e}")

        return "\n\n".join(parts) if parts else None

    async def _recall_by_category(
        self, user_id: str, categories: list[str], limit: int = 5
    ) -> list[str]:
        """Recall memories by category from InstanceMemoryManager FTS5 index.

        Unlike semantic search, this uses exact category match —
        guarantees style memories are always recalled.
        """
        try:
            from core.memory.instance_memory import InstanceMemoryManager

            mgr = InstanceMemoryManager(
                user_id=user_id, mem0_enabled=False, enabled=True
            )
            results = []
            for cat in categories:
                items = await mgr.recall(query=cat, limit=limit)
                for item in items:
                    content = item.get("content", "") if isinstance(item, dict) else str(item)
                    if content.strip() and content not in results:
                        results.append(content.strip())
            return results[:limit]
        except Exception as e:
            logger.debug(f"Category recall from FTS5 failed: {e}")
            return []

    @staticmethod
    def _trim_markdown_memory(content: str, max_chars: int) -> str:
        """
        Trim MEMORY.md content intelligently.

        Keeps section headers and non-placeholder entries.
        Skips template placeholder lines like （小搭子还不了解你...）.
        """
        if len(content) <= max_chars:
            return content

        lines = content.split("\n")
        result = []
        total = 0

        for line in lines:
            stripped = line.strip()
            # Skip template placeholders
            if stripped.startswith("（") and stripped.endswith("）"):
                continue
            # Skip blockquote instructions
            if stripped.startswith(">"):
                continue

            line_len = len(line) + 1  # +1 for newline
            if total + line_len > max_chars:
                break
            result.append(line)
            total += line_len

        return "\n".join(result)
