"""
UserMemoryInjector - 用户记忆注入器

职责（唯一归口）：
1. 从 MEMORY.md 读取用户可编辑的记忆档案（Source of Truth）
2. 从 Mem0 语义搜索用户相关记忆（补充）
3. 从 FTS5 分类召回 style/preference 记忆（兜底，始终生效）
4. 三路并行 asyncio.gather → 融合去重 → 预算控制 → <user_memory> 注入

读取闭环：
- MEMORY.md 是用户可见可编辑的记忆源（60% 预算）
- Mem0 是语义搜索的补充（40% 预算，与分类召回共享）
- 三路并行，总延迟 = max(三者) 而非 sum

缓存策略：SESSION（5min 缓存）
注入位置：Phase 2 - User Context Message
优先级：90（最高，用户信息最重要）
"""

import asyncio
import re
from typing import List, Optional

from logger import get_logger

from ..base import BaseInjector, CacheStrategy, InjectionPhase, InjectionResult
from ..context import InjectionContext

logger = get_logger("injectors.phase2.user_memory")

# 注入预算控制（符合 RULE 18-context-engineering 的 Injector 预算规范）
# 记忆召回上限 500 tokens ≈ 1500 中文字符
MAX_INJECT_CHARS = 1500

# MEMORY.md 在融合中的最大预算占比
_MD_BUDGET_RATIO = 0.6  # 60% 给 MEMORY.md, 40% 给 Mem0 + 分类召回

# Mem0 语义搜索最大返回条数
_MEM0_SEARCH_LIMIT = 10

# Mem0 混合搜索最低分阈值（方向 C：过滤低质量噪音）
# score < 0.35 的记忆基本无参考价值，白占注入预算
_MEM0_MIN_SCORE = 0.35


class UserMemoryInjector(BaseInjector):
    """
    用户记忆注入器（记忆检索的唯一归口）

    三路并行融合：
    1. MEMORY.md（用户可编辑，Source of Truth）
    2. Mem0 语义搜索（按当前 query 检索相关记忆）
    3. FTS5 分类召回（style/preference 类别，始终生效）

    输出示例：
    ```
    <user_memory>
    ## 记忆档案
    - 用户偏好 Python 编程
    - 喜欢简洁的代码风格

    ## 相关记忆
    - 老张是永辉项目的负责人
    - 合同金额 150 万，周三签约

    ## 用户风格/偏好（始终生效）
    - 毒舌风格，说话犀利
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
        注入用户记忆（三路并行融合）

        始终走融合路径，不依赖外部预加载。
        """
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

    # ================================================================
    # 三路并行融合
    # ================================================================

    async def _fetch_fused_memory(
        self, context: InjectionContext
    ) -> Optional[str]:
        """
        三路并行获取 → 融合去重 → 预算分配。

        1. MEMORY.md (primary, 60% budget)
        2. Mem0 semantic search (supplementary)
        3. Category recall: style/preference (always-on fallback)

        使用 asyncio.gather(return_exceptions=True) 保证任一路失败不影响其他。
        """
        md_task = self._fetch_from_markdown(context)
        mem0_task = self._fetch_from_mem0(context)
        style_task = self._recall_by_category(
            context.user_id, categories=["style", "preference"]
        )

        results = await asyncio.gather(
            md_task, mem0_task, style_task,
            return_exceptions=True,
        )

        # 解包结果，异常降级为 None / []
        md_content = results[0] if not isinstance(results[0], Exception) else None
        mem0_lines = results[1] if not isinstance(results[1], Exception) else None
        style_memories = results[2] if not isinstance(results[2], Exception) else []

        if isinstance(results[0], Exception):
            logger.warning(f"MEMORY.md 读取异常: {results[0]}")
        if isinstance(results[1], Exception):
            logger.warning(f"Mem0 语义搜索异常: {results[1]}")
        if isinstance(results[2], Exception):
            logger.debug(f"分类召回异常 (non-fatal): {results[2]}")

        if not md_content and not mem0_lines and not style_memories:
            return None

        # Budget allocation
        md_budget = int(MAX_INJECT_CHARS * _MD_BUDGET_RATIO)
        mem0_budget = MAX_INJECT_CHARS - md_budget

        parts = []

        # Part 1: MEMORY.md (Source of Truth)
        if md_content:
            trimmed = self._trim_markdown_memory(md_content, md_budget)
            if trimmed:
                parts.append(trimmed)

        # Part 2: Mem0 语义搜索结果
        if mem0_lines:
            mem0_text = "## 相关记忆\n" + "\n".join(f"- {line}" for line in mem0_lines)
            if len(mem0_text) > mem0_budget:
                mem0_text = mem0_text[:mem0_budget]
            if mem0_text.strip():
                parts.append(mem0_text)

        # Part 3: 分类召回（与 Mem0 结果去重）
        if style_memories:
            # 去重：排除已出现在 Mem0 结果中的条目
            existing = set(mem0_lines or [])
            new_items = [m for m in style_memories if m not in existing]
            if new_items:
                parts.append(
                    "## 用户风格/偏好（始终生效）\n"
                    + "\n".join(f"- {m}" for m in new_items)
                )

        if not parts:
            return None

        return "\n\n".join(parts)

    # ================================================================
    # 数据源 1: MEMORY.md
    # ================================================================

    async def _fetch_from_markdown(
        self, context: InjectionContext
    ) -> Optional[str]:
        """
        Read MEMORY.md via InstanceMemoryManager.

        This is the Source of Truth — user editable memory file.
        """
        try:
            from core.memory.instance_memory import get_instance_memory_manager

            from utils.memory_config import load_memory_config
            mem_cfg = await load_memory_config()

            mgr = get_instance_memory_manager(
                user_id=context.user_id or "default",
                mem0_enabled=False,  # Only need file layer for injection
                enabled=mem_cfg.enabled,
            )
            content = await mgr.get_memory_context()

            if not content or len(content.strip()) < 20:
                return None

            logger.debug(f"MEMORY.md 读取成功: {len(content)} 字符")
            return content

        except Exception as e:
            logger.warning(f"MEMORY.md 读取失败: {e}")
            return None

    # ================================================================
    # 数据源 2: Mem0 语义搜索（异步包装）
    # ================================================================

    async def _fetch_from_mem0(
        self, context: InjectionContext
    ) -> Optional[List[str]]:
        """
        从 Mem0 语义搜索用户相关记忆。

        返回纯文本列表（不含格式化指令），格式化由融合层统一处理。
        使用 asyncio.to_thread 包装同步 Mem0 调用，避免阻塞事件循环。

        搜索 query 增强：长任务中 user_query 可能是"继续"等短追问，
        拼接第一条用户消息（原始任务描述）提升召回准确性。
        """
        if not context.user_id or not context.user_query:
            return None

        try:
            from core.memory.mem0.pool import get_mem0_pool

            pool = get_mem0_pool()

            # 增强搜索 query：拼接原始任务描述
            # 长任务中 user_query 可能是"继续"/"好的"等短追问，
            # 导致 Mem0 语义搜索召回不相关的记忆。
            # 第一条 user 消息（原始任务）在 preserve_first_messages 保护区内，始终可用。
            search_query = context.user_query
            if context.history_messages and len(context.user_query) < 20:
                first_user_text = self._extract_first_user_text(
                    context.history_messages
                )
                if first_user_text and first_user_text != context.user_query:
                    search_query = f"{first_user_text} {context.user_query}"
                    logger.debug(
                        f"Memory Recall query 增强: "
                        f"'{context.user_query}' → '{search_query[:80]}...'"
                    )

            # 同步 Mem0 混合搜索放入线程池，不阻塞事件循环
            # 内部自动执行：向量搜索 + FTS5 关键词搜索 → 加权合并 → min_score 过滤
            memories = await asyncio.to_thread(
                pool.search,
                user_id=context.user_id,
                query=search_query,
                limit=_MEM0_SEARCH_LIMIT,
                min_score=_MEM0_MIN_SCORE,
            )

            if not memories:
                return None

            # 提取纯文本内容（不附加格式化指令，由融合层统一处理）
            lines = []
            for mem in memories:
                content = mem.get("memory", "")
                if content and content.strip():
                    lines.append(content.strip())

            if not lines:
                return None

            logger.debug(f"Mem0 语义搜索: {len(lines)} 条记忆")
            return lines

        except Exception as e:
            logger.warning(f"Mem0 语义搜索失败: {e}")
            return None

    # ================================================================
    # 数据源 3: FTS5 分类召回
    # ================================================================

    async def _recall_by_category(
        self, user_id: str, categories: list[str], limit: int = 5
    ) -> list[str]:
        """
        Recall memories by category from InstanceMemoryManager FTS5 index.

        Unlike semantic search, this uses exact category match —
        guarantees style memories are always recalled even when
        semantic distance is too large (fixes G1 "写健身房文章" case).
        """
        if not user_id:
            return []

        try:
            from core.memory.instance_memory import get_instance_memory_manager

            mgr = get_instance_memory_manager(
                user_id=user_id, mem0_enabled=False, enabled=True
            )
            results = []
            for cat in categories:
                items = await mgr.recall(query=cat, limit=limit)
                for item in items:
                    content = (
                        item.get("content", "") if isinstance(item, dict) else str(item)
                    )
                    if content.strip() and content not in results:
                        results.append(content.strip())
            return results[:limit]
        except Exception as e:
            logger.debug(f"Category recall from FTS5 failed: {e}")
            return []

    # ================================================================
    # 工具方法
    # ================================================================

    @staticmethod
    def _extract_first_user_text(
        history_messages: list[dict],
    ) -> Optional[str]:
        """
        Extract text from the first user message in history.

        Used to enrich short follow-up queries ("继续") with the
        original task description for better memory recall.

        Args:
            history_messages: conversation history (list of dicts)

        Returns:
            First user message text (truncated to 200 chars), or None.
        """
        for msg in history_messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                text = content.strip()
                return text[:200] if len(text) > 200 else text
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if text:
                            return text[:200] if len(text) > 200 else text
            break  # Only check the first user message
        return None

    # Sections that must survive budget trimming (identity > preferences).
    # Order matters: first section listed gets highest priority.
    _PRIORITY_SECTIONS = ["基本信息", "关于你"]

    @staticmethod
    def _trim_markdown_memory(content: str, max_chars: int) -> str:
        """
        Trim MEMORY.md content intelligently with priority ordering.

        Strategy:
        1. Always keep priority sections first (基本信息, 关于你)
        2. Fill remaining budget with other sections in document order
        3. Skip template placeholders and blockquote instructions
        """
        if len(content) <= max_chars:
            return content

        lines = content.split("\n")

        # Parse into sections: [(section_name, [lines]), ...]
        sections: list[tuple[str, list[str]]] = []
        current_name = ""
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Skip template placeholders and blockquotes
            if stripped.startswith("（") and stripped.endswith("）"):
                continue
            if stripped.startswith(">"):
                continue

            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading:
                if current_lines:
                    sections.append((current_name, current_lines))
                current_name = heading.group(2).strip()
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_name, current_lines))

        # Reorder: priority sections first, then rest in original order
        priority = []
        rest = []
        priority_names = set(
            UserMemoryInjector._PRIORITY_SECTIONS
        )
        for name, sec_lines in sections:
            if name in priority_names:
                priority.append((name, sec_lines))
            else:
                rest.append((name, sec_lines))

        ordered = priority + rest

        # Fill budget
        result = []
        total = 0
        for _name, sec_lines in ordered:
            for line in sec_lines:
                line_len = len(line) + 1
                if total + line_len > max_chars:
                    return "\n".join(result)
                result.append(line)
                total += line_len

        return "\n".join(result)
