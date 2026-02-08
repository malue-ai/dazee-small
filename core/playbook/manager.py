"""
PlaybookManager - 策略库管理器

V8.0 新增
V10.0 重构：统一走 Storage Backend，删除双重文件操作，修复实例隔离

职责：
- 从成功会话中提取策略模式
- 管理策略的生命周期（草稿/待审核/已发布/已废弃）
- 策略检索和匹配（两层：task_type 预筛 + Mem0 语义搜索）
"""

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from logger import get_logger
from utils.app_paths import get_instance_playbooks_dir

logger = get_logger(__name__)


class PlaybookStatus(Enum):
    """策略状态"""

    DRAFT = "draft"  # 草稿（自动生成）
    PENDING_REVIEW = "pending"  # 待审核
    APPROVED = "approved"  # 已发布
    REJECTED = "rejected"  # 已拒绝
    DEPRECATED = "deprecated"  # 已废弃


@dataclass
class PlaybookEntry:
    """
    策略条目

    描述一个成功的执行模式，包括：
    - 触发条件（什么场景下使用）
    - 执行策略（怎么执行）
    - 工具序列（使用哪些工具）
    - 质量指标（预期效果）
    """

    id: str  # 唯一 ID
    name: str  # 策略名称
    description: str  # 策略描述

    # 触发条件
    trigger: Dict[str, Any] = field(default_factory=dict)
    # {
    #   "task_types": ["data_analysis"],
    #   "complexity_range": [4, 7],
    # }

    # 执行策略
    strategy: Dict[str, Any] = field(default_factory=dict)
    # {
    #   "execution_strategy": "rvr-b",
    #   "suggested_tools": ["data_analysis_skill", "chart_generation"],
    #   "max_turns": 15,
    #   "planning_depth": "full"
    # }

    # 工具序列模板
    tool_sequence: List[Dict[str, Any]] = field(default_factory=list)
    # [
    #   {"tool": "data_analysis_skill", "purpose": "数据查询"},
    #   {"tool": "chart_generation", "purpose": "生成图表"}
    # ]

    # 质量指标
    quality_metrics: Dict[str, float] = field(default_factory=dict)
    # {
    #   "avg_reward": 0.85,
    #   "success_rate": 0.92,
    #   "avg_turns": 8.5
    # }

    # 元数据
    status: PlaybookStatus = PlaybookStatus.DRAFT
    source: str = "auto"  # auto / manual / import
    source_session_id: Optional[str] = None  # 来源会话 ID
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewed_by: Optional[str] = None  # 审核人
    review_notes: Optional[str] = None  # 审核备注
    usage_count: int = 0  # 使用次数

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlaybookEntry":
        """从字典创建（过滤未知字段，避免 TypeError）"""
        data = data.copy()
        if isinstance(data.get("status"), str):
            data["status"] = PlaybookStatus(data["status"])
        known_fields = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def matches_task_type(self, task_type: str) -> bool:
        """
        Layer 1 预筛：task_type 确定性匹配（<1ms）

        仅用于快速过滤候选集，不做语义判断。
        属于"简单确定性任务"（规则允许的场景）。

        Args:
            task_type: 意图识别输出的任务类型

        Returns:
            是否属于同类型任务
        """
        if "task_types" in self.trigger:
            return task_type in self.trigger["task_types"]
        # 无 task_types 限制的策略对所有类型适用
        return True

    def get_searchable_text(self) -> str:
        """
        生成用于语义搜索的文本描述

        将 Playbook 的名称、描述、工具序列合并为一段文本，
        供 Mem0 向量搜索使用。

        Returns:
            可搜索的文本
        """
        parts = [self.name, self.description]
        if self.tool_sequence:
            tools = [
                step.get("description", step.get("tool", ""))
                for step in self.tool_sequence
            ]
            parts.append("步骤: " + " -> ".join(tools))
        return " | ".join(filter(None, parts))


class PlaybookManager:
    """
    策略库管理器

    所有 IO 操作统一走 Storage Backend，不直接操作文件。

    使用方式：
        manager = create_playbook_manager()
        await manager.load_all_async()

        # 从高分会话提取策略
        entry = await manager.extract_from_session(session_reward)

        # 审核策略
        await manager.approve(entry.id, reviewer="admin", notes="verified")

        # 检索匹配策略
        matches = await manager.find_matching_async(query, task_type)
    """

    def __init__(
        self,
        storage_path: str = None,
        auto_save: bool = True,
        min_reward_threshold: float = 0.7,
        llm_service=None,
    ):
        """
        初始化策略库管理器

        Args:
            storage_path: 存储路径，默认使用实例隔离路径
            auto_save: 是否自动保存
            min_reward_threshold: 最低奖励阈值（用于自动提取）
            llm_service: LLM 服务（用于策略提取）
        """
        if storage_path is None:
            instance_name = os.getenv("AGENT_INSTANCE", "default")
            storage_path = str(get_instance_playbooks_dir(instance_name))

        self._storage_path = storage_path
        self.auto_save = auto_save
        self.min_reward_threshold = min_reward_threshold
        self.llm = llm_service

        # 延迟初始化的存储后端
        self._storage = None

        # 内存缓存
        self._entries: Dict[str, PlaybookEntry] = {}
        self._loaded = False

        logger.info(f"✅ PlaybookManager 初始化: storage={storage_path}")

    def _get_storage(self):
        """获取存储后端（延迟初始化）"""
        if self._storage is None:
            from core.playbook.storage import create_storage_backend

            self._storage = create_storage_backend(storage_path=self._storage_path)
        return self._storage

    async def load_all_async(self):
        """
        异步加载所有策略

        使用方式：
            await manager.load_all_async()
        """
        if self._loaded:
            return

        try:
            storage = self._get_storage()
            entries_data = await storage.list_all()

            for data in entries_data:
                entry = PlaybookEntry.from_dict(data)
                self._entries[entry.id] = entry

            self._loaded = True
            logger.info(f"📚 加载 {len(self._entries)} 个策略条目")
        except Exception as e:
            logger.error(f"❌ 加载策略库失败: {e}")

    async def _save_entry(self, entry: PlaybookEntry):
        """通过 Storage Backend 保存单个策略"""
        if not self.auto_save:
            return

        try:
            storage = self._get_storage()
            await storage.save(entry.id, entry.to_dict())
            await self._save_index()
        except Exception as e:
            logger.error(f"❌ 保存策略失败: {e}")

    async def _save_index(self):
        """通过 Storage Backend 保存索引"""
        try:
            storage = self._get_storage()
            index = {
                "entries": list(self._entries.keys()),
                "updated_at": datetime.now().isoformat(),
                "stats": {
                    "total": len(self._entries),
                    "approved": sum(
                        1 for e in self._entries.values() if e.status == PlaybookStatus.APPROVED
                    ),
                    "pending": sum(
                        1
                        for e in self._entries.values()
                        if e.status == PlaybookStatus.PENDING_REVIEW
                    ),
                },
            }
            await storage.save_index(index)
        except Exception as e:
            logger.warning(f"⚠️ 保存索引失败: {e}")

    def _generate_id(self, name: str, session_id: str = None) -> str:
        """生成策略 ID"""
        content = f"{name}:{session_id or datetime.now().isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    # ==================== Mem0 同步 ====================

    async def _sync_to_mem0(self, entry: PlaybookEntry):
        """
        将 Playbook 描述写入 Mem0，用于语义匹配。

        写入后 find_matching_async() 的 Layer 2 才能搜索到该条目。
        Best-effort：Mem0 不可用时静默跳过。
        """
        try:
            from core.memory.mem0 import get_mem0_pool

            pool = get_mem0_pool()
            pool.add(
                user_id="playbook",
                messages=[
                    {"role": "user", "content": f"[策略] {entry.get_searchable_text()}"}
                ],
                metadata={
                    "playbook_id": entry.id,
                    "source": "playbook_manager",
                    "task_types": ",".join(entry.trigger.get("task_types", [])),
                },
            )
            logger.debug(f"Mem0 同步: playbook={entry.id}")
        except Exception as e:
            logger.debug(f"Mem0 同步跳过: {e}")

    # ==================== CRUD 操作 ====================

    async def create(
        self,
        name: str,
        description: str,
        trigger: Dict[str, Any],
        strategy: Dict[str, Any],
        tool_sequence: List[Dict[str, Any]] = None,
        quality_metrics: Dict[str, float] = None,
        source: str = "manual",
        source_session_id: str = None,
    ) -> PlaybookEntry:
        """
        创建新策略

        Args:
            name: 策略名称
            description: 描述
            trigger: 触发条件
            strategy: 执行策略
            tool_sequence: 工具序列
            quality_metrics: 质量指标
            source: 来源（auto/manual/import）
            source_session_id: 来源会话 ID

        Returns:
            PlaybookEntry
        """
        entry_id = self._generate_id(name, source_session_id)

        entry = PlaybookEntry(
            id=entry_id,
            name=name,
            description=description,
            trigger=trigger,
            strategy=strategy,
            tool_sequence=tool_sequence or [],
            quality_metrics=quality_metrics or {},
            source=source,
            source_session_id=source_session_id,
            status=PlaybookStatus.DRAFT if source == "auto" else PlaybookStatus.PENDING_REVIEW,
        )

        self._entries[entry_id] = entry
        await self._save_entry(entry)
        await self._sync_to_mem0(entry)

        logger.info(f"📝 创建策略: {name} (id={entry_id})")
        return entry

    def get(self, entry_id: str) -> Optional[PlaybookEntry]:
        """获取策略"""
        return self._entries.get(entry_id)

    def list_all(self, status: PlaybookStatus = None, source: str = None) -> List[PlaybookEntry]:
        """
        列出所有策略

        Args:
            status: 过滤状态
            source: 过滤来源

        Returns:
            策略列表
        """
        entries = list(self._entries.values())

        if status:
            entries = [e for e in entries if e.status == status]

        if source:
            entries = [e for e in entries if e.source == source]

        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    async def update(self, entry_id: str, **updates) -> Optional[PlaybookEntry]:
        """更新策略"""
        entry = self._entries.get(entry_id)
        if not entry:
            return None

        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)

        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)

        return entry

    async def delete(self, entry_id: str) -> bool:
        """删除策略"""
        if entry_id not in self._entries:
            return False

        del self._entries[entry_id]

        try:
            storage = self._get_storage()
            await storage.delete(entry_id)
        except Exception as e:
            logger.warning(f"⚠️ 删除策略文件失败: {e}")

        await self._save_index()
        return True

    # ==================== 审核流程 ====================

    async def submit_for_review(self, entry_id: str) -> bool:
        """提交审核（仅 DRAFT → PENDING_REVIEW）"""
        entry = self._entries.get(entry_id)
        if not entry or entry.status != PlaybookStatus.DRAFT:
            return False

        entry.status = PlaybookStatus.PENDING_REVIEW
        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)

        logger.info(f"📤 策略提交审核: {entry.name}")
        return True

    async def approve(self, entry_id: str, reviewer: str, notes: str = None) -> bool:
        """审核通过（仅 PENDING_REVIEW → APPROVED）"""
        entry = self._entries.get(entry_id)
        if not entry or entry.status != PlaybookStatus.PENDING_REVIEW:
            return False

        entry.status = PlaybookStatus.APPROVED
        entry.reviewed_by = reviewer
        entry.review_notes = notes
        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)

        logger.info(f"✅ 策略审核通过: {entry.name} (by {reviewer})")
        return True

    async def reject(self, entry_id: str, reviewer: str, reason: str) -> bool:
        """审核拒绝（仅 PENDING_REVIEW → REJECTED）"""
        entry = self._entries.get(entry_id)
        if not entry or entry.status != PlaybookStatus.PENDING_REVIEW:
            return False

        entry.status = PlaybookStatus.REJECTED
        entry.reviewed_by = reviewer
        entry.review_notes = reason
        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)

        logger.info(f"❌ 策略审核拒绝: {entry.name} (by {reviewer})")
        return True

    async def deprecate(self, entry_id: str, reason: str = None) -> bool:
        """废弃策略（仅 APPROVED → DEPRECATED）"""
        entry = self._entries.get(entry_id)
        if not entry or entry.status != PlaybookStatus.APPROVED:
            return False

        entry.status = PlaybookStatus.DEPRECATED
        entry.review_notes = reason
        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)

        logger.info(f"🗑️ 策略已废弃: {entry.name}")
        return True

    # ==================== 策略提取 ====================

    async def extract_from_session(
        self, session_reward, use_llm: bool = True  # SessionReward from RewardAttribution
    ) -> Optional[PlaybookEntry]:
        """
        从成功会话中提取策略

        Args:
            session_reward: 会话奖励结果
            use_llm: 是否使用 LLM 生成描述

        Returns:
            提取的策略条目，或 None
        """
        # 检查奖励阈值
        if session_reward.total_reward < self.min_reward_threshold:
            logger.debug(
                f"会话奖励 {session_reward.total_reward:.2f} "
                f"< 阈值 {self.min_reward_threshold}"
            )
            return None

        # 提取工具序列
        tool_sequence = []
        for step in session_reward.step_rewards:
            if step.action.startswith("tool:"):
                tool_name = step.action.replace("tool:", "")
                tool_sequence.append(
                    {"tool": tool_name, "reward": step.reward, "is_critical": step.is_critical}
                )

        # 构建触发条件
        trigger = {
            "task_types": (
                [session_reward.task_type] if hasattr(session_reward, "task_type") else []
            ),
            "complexity_range": [4, 8],  # 默认范围
        }

        # 构建执行策略
        strategy = {
            "execution_strategy": (
                session_reward.execution_strategy
                if hasattr(session_reward, "execution_strategy")
                else "rvr"
            ),
            "suggested_tools": [t["tool"] for t in tool_sequence],
            "max_turns": len(session_reward.step_rewards),
        }

        # 质量指标
        quality_metrics = {
            "avg_reward": session_reward.total_reward,
            "success_rate": 1.0 if session_reward.success else 0.0,
            "avg_turns": len(session_reward.step_rewards),
        }

        # 生成名称和描述
        name = f"Auto-{session_reward.session_id[:8]}"
        description = f"从会话 {session_reward.session_id} 自动提取的策略"

        if use_llm and self.llm:
            try:
                name, description = await self._generate_description_with_llm(
                    session_reward, tool_sequence
                )
            except Exception as e:
                logger.warning(f"LLM 生成描述失败: {e}")

        # 创建策略条目（quality_metrics 直接传入，避免双重保存）
        entry = await self.create(
            name=name,
            description=description,
            trigger=trigger,
            strategy=strategy,
            tool_sequence=tool_sequence,
            quality_metrics=quality_metrics,
            source="auto",
            source_session_id=session_reward.session_id,
        )

        logger.info(
            f"🎯 自动提取策略: {name} (reward={session_reward.total_reward:.2f})"
        )

        return entry

    async def _generate_description_with_llm(
        self, session_reward, tool_sequence: List[Dict]
    ) -> tuple[str, str]:
        """使用 LLM 生成策略名称和描述"""
        from core.llm import Message

        tools_str = ", ".join([t["tool"] for t in tool_sequence])

        prompt = f"""根据以下会话执行信息，生成一个简洁的策略名称和描述。

会话信息：
- 使用的工具序列：{tools_str}
- 执行步骤数：{len(session_reward.step_rewards)}
- 成功率：100%

要求：
1. 名称：简洁，10-20 字，描述这个策略的用途
2. 描述：1-2 句话，说明什么场景下使用这个策略

输出 JSON 格式：
{{"name": "策略名称", "description": "策略描述"}}
"""

        response = await self.llm.create_message_async(
            messages=[Message(role="user", content=prompt)],
            system="你是一个策略库管理助手，帮助生成清晰的策略描述。",
        )

        import re

        match = re.search(r"\{[\s\S]*\}", response.content)
        if match:
            data = json.loads(match.group())
            return data.get("name", "自动策略"), data.get("description", "自动生成的策略")

        return "自动策略", "自动生成的策略"

    # ==================== 策略匹配（LLM-First 语义匹配）====================

    async def find_matching_async(
        self,
        query: str,
        task_type: str = "",
        top_k: int = 3,
        min_score: float = 0.3,
        only_approved: bool = True,
    ) -> List[tuple["PlaybookEntry", float]]:
        """
        语义匹配策略（LLM-First 设计）

        两层匹配：
        1. Layer 1: task_type 预筛（确定性规则，<1ms）
        2. Layer 2: Mem0 语义搜索（向量相似度，零额外 LLM 调用）

        Args:
            query: 用户查询（自然语言）
            task_type: 意图识别输出的任务类型（可选）
            top_k: 返回前 k 个
            min_score: 最低匹配分数
            only_approved: 仅返回已审核通过的策略

        Returns:
            [(策略, 匹配分数), ...]
        """
        # Layer 1: task_type 预筛
        candidates = {
            entry_id: entry
            for entry_id, entry in self._entries.items()
            if (not only_approved or entry.status == PlaybookStatus.APPROVED)
            and entry.matches_task_type(task_type)
        }

        if not candidates:
            return []

        # Layer 2: Mem0 语义搜索
        try:
            from core.memory.mem0 import get_mem0_pool

            pool = get_mem0_pool()
            search_results = pool.search(
                user_id="playbook",
                query=f"任务策略: {query}",
                limit=top_k * 2,
            )

            # 匹配搜索结果和候选 Playbook
            matched = []
            for result in search_results:
                metadata = result.get("metadata") or {}
                playbook_id = metadata.get("playbook_id", "")
                score = result.get("score", 0.0)

                if playbook_id in candidates and score >= min_score:
                    matched.append((candidates[playbook_id], score))

            if matched:
                matched.sort(key=lambda x: x[1], reverse=True)
                return matched[:top_k]

        except Exception as e:
            logger.warning(f"Mem0 语义匹配失败，降级到全量返回: {e}")

        # 降级：Mem0 不可用时按使用次数排序，给予低置信度分数
        fallback = sorted(
            candidates.values(),
            key=lambda e: e.usage_count,
            reverse=True,
        )
        return [(entry, 0.5) for entry in fallback[:top_k]]

    def find_matching(
        self,
        context: Dict[str, Any],
        top_k: int = 3,
        min_score: float = 0.5,
        only_approved: bool = True,
    ) -> List[tuple["PlaybookEntry", float]]:
        """
        同步匹配策略（仅 task_type 预筛）

        推荐使用 find_matching_async() 进行语义匹配。

        Args:
            context: 上下文信息（task_type, query, complexity_score）
            top_k: 返回前 k 个
            min_score: 最低匹配分数
            only_approved: 仅返回已审核通过的策略

        Returns:
            [(策略, 匹配分数), ...]
        """
        task_type = context.get("task_type", "")
        candidates = []

        for entry in self._entries.values():
            if only_approved and entry.status != PlaybookStatus.APPROVED:
                continue
            if entry.matches_task_type(task_type):
                candidates.append((entry, 0.5))

        # 按使用次数排序
        candidates.sort(key=lambda x: x[0].usage_count, reverse=True)
        return candidates[:top_k]

    async def record_usage(self, entry_id: str):
        """记录策略使用"""
        entry = self._entries.get(entry_id)
        if entry:
            entry.usage_count += 1
            await self._save_entry(entry)

    # ==================== 统计信息 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        entries = list(self._entries.values())

        return {
            "total": len(entries),
            "by_status": {
                status.value: sum(1 for e in entries if e.status == status)
                for status in PlaybookStatus
            },
            "by_source": {
                "auto": sum(1 for e in entries if e.source == "auto"),
                "manual": sum(1 for e in entries if e.source == "manual"),
                "import": sum(1 for e in entries if e.source == "import"),
            },
            "total_usage": sum(e.usage_count for e in entries),
            "avg_quality": (
                sum(e.quality_metrics.get("avg_reward", 0) for e in entries) / len(entries)
                if entries
                else 0
            ),
        }


def create_playbook_manager(
    storage_path: str = None,
    llm_service=None,
    **kwargs,
) -> PlaybookManager:
    """
    创建策略库管理器

    Args:
        storage_path: 存储路径，默认使用实例隔离路径
        llm_service: LLM 服务
        **kwargs: 其他参数

    Returns:
        PlaybookManager 实例

    使用示例：
        manager = create_playbook_manager()
        await manager.load_all_async()
    """
    return PlaybookManager(
        storage_path=storage_path,
        llm_service=llm_service,
        **kwargs,
    )
