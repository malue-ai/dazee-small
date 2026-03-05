"""
PlaybookManager - 策略库管理器

V8.0 新增
V10.0 重构：统一走 Storage Backend，删除双重文件操作，修复实例隔离
V10.1 重构：独立向量库，Playbook 向量与用户记忆物理隔离

职责：
- 从成功会话中提取策略模式
- 管理策略的生命周期（草稿/待审核/已发布/已废弃）
- 策略检索和匹配（两层：task_type 预筛 + 独立向量库语义搜索）

向量存储架构：
- Playbook 使用独立的 playbook_vectors.db（SqliteVecVectorStore）
- 与用户记忆 mem0_vectors.db 物理隔离，KNN 搜索不受用户记忆数量影响
- Embedding 复用全局 GGUF 单例（GGUFEmbeddingProvider），零额外内存
"""

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from logger import get_logger
from utils.app_paths import get_instance_playbooks_dir, get_instance_playbook_vectors_path

logger = get_logger(__name__)

# Playbook unused for longer than this is considered stale and skipped during matching.
# Lazy evaluation: checked at match time, no background scan needed.
STALE_DAYS = 30


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
    last_used_at: Optional[str] = None  # 最后一次被匹配注入的时间（ISO 8601）

    def is_stale(self, stale_days: int = STALE_DAYS) -> bool:
        """
        Check if this entry has been unused for too long.

        Uses last_used_at if available, otherwise falls back to updated_at.
        Newly approved entries (never used) get a grace period from updated_at.
        """
        ref = self.last_used_at or self.updated_at or self.created_at
        try:
            ref_dt = datetime.fromisoformat(ref)
            return (datetime.now() - ref_dt).days > stale_days
        except (ValueError, TypeError):
            return False

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
        # 调用方未提供 task_type 时不做预筛（交给 Layer 2 语义判断）
        if not task_type:
            return True
        if "task_types" in self.trigger:
            return task_type in self.trigger["task_types"]
        # 无 task_types 限制的策略对所有类型适用
        return True

    def get_searchable_text(self) -> str:
        """
        生成用于语义搜索的文本描述。

        描述质量直接决定匹配精度（Precision-First）。
        合并名称、描述、工具序列、触发条件为一段文本，
        供 Mem0 向量/FTS5 搜索使用。

        Returns:
            可搜索的文本（不含"[策略]"等前缀，避免搜索噪音）
        """
        parts = [self.name, self.description]

        # 工具序列：兼容 purpose / description / tool 三种 key
        if self.tool_sequence:
            tools = [
                step.get("purpose", step.get("description", step.get("tool", "")))
                for step in self.tool_sequence
            ]
            tools = [t for t in tools if t]
            if tools:
                parts.append("步骤: " + " -> ".join(tools))

        # 触发条件中的 task_types 有助于 FTS5 关键词命中
        task_types = self.trigger.get("task_types", [])
        if task_types:
            parts.append("任务类型: " + ", ".join(task_types))

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
            llm_service: LLM 服务（用于策略提取，可选，未传时懒加载）
        """
        if storage_path is None:
            instance_name = os.getenv("AGENT_INSTANCE", "default")
            storage_path = str(get_instance_playbooks_dir(instance_name))

        self._storage_path = storage_path
        self._instance_name = os.getenv("AGENT_INSTANCE", "default")
        self.auto_save = auto_save
        self.min_reward_threshold = min_reward_threshold
        self._llm_service = llm_service

        # 延迟初始化的存储后端（JSON 文件）
        self._storage = None

        # 延迟初始化的向量存储（独立 playbook_vectors.db）
        self._vector_store = None
        self._embedding_model = None

        # 内存缓存
        self._entries: Dict[str, PlaybookEntry] = {}
        self._loaded = False

        logger.info(f"✅ PlaybookManager 初始化: storage={storage_path}")

    async def _get_llm_service(self):
        """
        Async getter for LLM service (lazy-loaded from config).

        使用 background_task profile（light tier），但覆盖 max_tokens
        以满足 playbook 描述生成（~200-300 tokens JSON 输出）。

        Follows the same pattern as MemoryExtractor.get_llm_service(),
        QualityController.get_llm_service(), etc.
        """
        if self._llm_service is None:
            try:
                from config.llm_config import get_llm_profile
                from core.llm import create_llm_service

                profile = await get_llm_profile(
                    "background_task", max_tokens=512
                )
                self._llm_service = create_llm_service(**profile)
            except Exception as e:
                logger.debug(f"LLM 服务懒加载失败（approve 时不生成描述）: {e}")
                return None
        return self._llm_service

    def _get_storage(self):
        """获取存储后端（延迟初始化）"""
        if self._storage is None:
            from core.playbook.storage import create_storage_backend

            self._storage = create_storage_backend(storage_path=self._storage_path)
        return self._storage

    def _get_vector_store(self):
        """
        获取 Playbook 专用的向量存储（延迟初始化）。

        使用独立的 playbook_vectors.db，与用户记忆 mem0_vectors.db 物理隔离。
        sqlite-vec KNN 查询不支持 WHERE 预过滤，共享表会导致 playbook
        向量被大量用户记忆挤出结果集。独立表确保 KNN 100% 命中 playbook。
        """
        if self._vector_store is None:
            from core.memory.mem0.sqlite_vec_store import SqliteVecVectorStore

            embedding = self._get_embedding_model()
            dims = embedding.config.embedding_dims if hasattr(embedding, "config") else 1024

            db_path = str(get_instance_playbook_vectors_path(self._instance_name))
            self._vector_store = SqliteVecVectorStore(
                collection_name="playbook_vectors",
                embedding_model_dims=dims,
                db_path=db_path,
            )
            logger.info(f"✅ Playbook 独立向量库初始化: {db_path} (dims={dims})")
        return self._vector_store

    def _get_embedding_model(self):
        """
        获取 Embedding 模型（延迟初始化，复用全局 GGUF 单例）。

        与 Mem0 Pool 共享同一个 GGUFEmbeddingProvider 实例（通过单例模式），
        零额外内存开销。通过 _GGUFEmbedderAdapter 包装为同步接口。
        """
        if self._embedding_model is None:
            from core.memory.mem0.pool import _GGUFEmbedderAdapter, Mem0MemoryPool

            adapter = Mem0MemoryPool._create_local_embedder()
            if adapter is not None:
                self._embedding_model = adapter
                logger.info("✅ Playbook embedding: 复用本地 GGUF (BGE-M3)")
            else:
                raise RuntimeError(
                    "Playbook 向量搜索需要本地 GGUF embedding 模型，"
                    "请确认 data/shared/models/bge-m3-Q4_K_M.gguf 存在"
                )
        return self._embedding_model

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
        """生成策略 ID（包含时间戳避免同 session 碰撞）"""
        ts = datetime.now().isoformat()
        content = f"{name}:{session_id or ts}:{ts}"
        return hashlib.md5(content.encode()).hexdigest()[:12]

    # ==================== 向量存储同步 ====================

    async def _delete_from_vector_store(self, entry_id: str):
        """
        从独立向量库删除指定 playbook 的向量记录。

        通过 vector_store.list(filters={"playbook_id": id}) 查找，
        再逐条删除。Best-effort：失败时静默跳过。
        """
        try:
            store = self._get_vector_store()
            results_and_count = store.list(
                filters={"playbook_id": entry_id}
            )
            results = results_and_count[0] if results_and_count else []

            deleted = 0
            for item in results:
                try:
                    store.delete(item.id)
                    deleted += 1
                except Exception:
                    pass

            if deleted:
                logger.debug(f"向量删除: playbook={entry_id}, 删除 {deleted} 条")
        except Exception as e:
            logger.debug(f"向量删除跳过: {e}")

    async def _sync_to_vector_store(self, entry: PlaybookEntry):
        """
        将 Playbook 描述写入独立向量库（upsert 语义：先删后增）。

        写入后 find_matching_async() 的 Layer 2 才能搜索到该条目。
        JSON 文件是 source of truth，向量库是搜索索引。
        Best-effort：向量库不可用时静默跳过。
        """
        try:
            # Step 1: 删除旧记录（避免重复条目）
            await self._delete_from_vector_store(entry.id)

            # Step 2: embed + 写入
            store = self._get_vector_store()
            embedding = self._get_embedding_model()

            searchable_text = entry.get_searchable_text()
            vec = embedding.embed(searchable_text)
            if not isinstance(vec, list):
                vec = vec.tolist() if hasattr(vec, "tolist") else list(vec)

            vec_id = str(uuid.uuid4())
            payload = {
                "playbook_id": entry.id,
                "data": searchable_text,
                "source": "playbook_manager",
                "task_types": ",".join(entry.trigger.get("task_types", [])),
                "created_at": datetime.now().isoformat(),
            }

            store.insert(
                vectors=[vec],
                ids=[vec_id],
                payloads=[payload],
            )
            logger.info(
                f"向量同步: playbook={entry.id}, "
                f"text={searchable_text[:60]}..."
            )
        except Exception as e:
            logger.warning(f"向量同步失败（playbook 暂时不可搜索）: {e}")

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
        # Approved-only indexing: new entries (DRAFT/PENDING) are NOT indexed.
        # Vector sync happens in approve() when the user confirms the strategy.

        logger.info(f"📝 创建策略: {name} (id={entry_id})")
        return entry

    def get(self, entry_id: str) -> Optional[PlaybookEntry]:
        """获取策略"""
        return self._entries.get(entry_id)

    def list_all(self, status: Optional[PlaybookStatus] = None, source: Optional[str] = None) -> List[PlaybookEntry]:
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
        """更新策略（同步向量索引以保持搜索数据一致）"""
        entry = self._entries.get(entry_id)
        if not entry:
            return None

        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)

        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)

        # 已审核的条目更新后需要同步向量索引
        if entry.status == PlaybookStatus.APPROVED:
            await self._sync_to_vector_store(entry)

        return entry

    async def delete(self, entry_id: str) -> bool:
        """删除策略（同步清理向量索引）"""
        if entry_id not in self._entries:
            return False

        del self._entries[entry_id]

        try:
            storage = self._get_storage()
            await storage.delete(entry_id)
        except Exception as e:
            logger.warning(f"⚠️ 删除策略文件失败: {e}")

        await self._delete_from_vector_store(entry_id)
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

    async def approve(self, entry_id: str, reviewer: str, notes: Optional[str] = None) -> bool:
        """
        审核通过（仅 PENDING_REVIEW → APPROVED）

        当 description 仍为自动提取的泛化模板时，尝试用 LLM 重新生成。
        高质量的 description 直接决定 Mem0 语义匹配的精度。
        """
        entry = self._entries.get(entry_id)
        if not entry or entry.status != PlaybookStatus.PENDING_REVIEW:
            return False

        # 如果 description 仍是默认模板（低区分度），尝试 LLM 重新生成
        if self._is_default_description(entry):
            llm = await self._get_llm_service()
            if llm:
                try:
                    name, description = await self._regenerate_description(entry)
                    entry.name = name
                    entry.description = description
                    logger.info(f"📝 LLM 重新生成描述: {name}")
                except Exception as e:
                    logger.warning(f"LLM 描述重新生成失败，保留原描述: {e}")

        entry.status = PlaybookStatus.APPROVED
        entry.reviewed_by = reviewer
        entry.review_notes = notes
        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)
        await self._sync_to_vector_store(entry)

        logger.info(f"✅ 策略审核通过: {entry.name} (by {reviewer})")
        return True

    @staticmethod
    def _is_default_description(entry: "PlaybookEntry") -> bool:
        """Check if description needs LLM refinement.

        Triggers for:
        - Missing description
        - Known default templates
        - Auto-extracted entries where description is just a truncated user query
          (name is a prefix of description, meaning no meaningful summarization happened)
        """
        if not entry.description:
            return True
        default_patterns = ["自动提取的策略", "自动生成的策略"]
        if any(p in entry.description for p in default_patterns):
            return True
        if entry.source == "auto" and entry.description.startswith(entry.name):
            return True
        return False

    async def _regenerate_description(
        self, entry: "PlaybookEntry"
    ) -> tuple[str, str]:
        """Regenerate name + description from entry's tool_sequence via LLM."""

        @dataclass
        class _FakeStep:
            action: str
            reward: float = 0.8
            is_critical: bool = False

        @dataclass
        class _FakeReward:
            session_id: str
            total_reward: float = 0.8
            success: bool = True
            step_rewards: list = None  # type: ignore[assignment]

            def __post_init__(self):
                if self.step_rewards is None:
                    self.step_rewards = []

        steps = [
            _FakeStep(action=f"tool:{t.get('tool', '')}")
            for t in (entry.tool_sequence or [])
        ]
        fake_reward = _FakeReward(
            session_id=entry.source_session_id or entry.id,
            step_rewards=steps,
        )
        return await self._generate_description_with_llm(
            fake_reward, entry.tool_sequence or [],
            user_query_hint=entry.description or "",
        )

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
        await self._delete_from_vector_store(entry_id)

        logger.info(f"❌ 策略审核拒绝: {entry.name} (by {reviewer})")
        return True

    async def deprecate(self, entry_id: str, reason: str = None) -> bool:
        """废弃策略（仅 APPROVED → DEPRECATED，同步清理 Mem0 索引）"""
        entry = self._entries.get(entry_id)
        if not entry or entry.status != PlaybookStatus.APPROVED:
            return False

        entry.status = PlaybookStatus.DEPRECATED
        entry.review_notes = reason
        entry.updated_at = datetime.now().isoformat()
        await self._save_entry(entry)

        # 废弃的策略不应出现在搜索结果中
        await self._delete_from_vector_store(entry_id)

        logger.info(f"🗑️ 策略已废弃: {entry.name}")
        return True

    async def rebuild_vector_index(self) -> Dict[str, int]:
        """Rebuild vector index: delete all vectors, re-index only APPROVED entries."""
        store = self._get_vector_store()
        all_records = store.list()[0]
        cleared = len(all_records)
        for record in all_records:
            store.delete(record.id)

        indexed = 0
        for entry in self._entries.values():
            if entry.status == PlaybookStatus.APPROVED:
                await self._sync_to_vector_store(entry)
                indexed += 1

        logger.info(f"🔄 向量索引重建: 清除 {cleared} 条, 重建 {indexed} 条 (approved)")
        return {"cleared": cleared, "indexed": indexed}

    # ==================== 策略提取 ====================

    async def extract_from_session(
        self,
        session_reward,
        use_llm: bool = True,
        user_query: str = "",
    ) -> Optional[PlaybookEntry]:
        """
        从成功会话中提取策略

        Args:
            session_reward: 会话奖励结果
            use_llm: 是否使用 LLM 生成描述
            user_query: 用户原始查询（用于生成有语义的策略描述，提高后续匹配率）

        Returns:
            提取的策略条目，或 None
        """
        # Dedup: skip if a playbook already exists for this session
        sid = session_reward.session_id
        for existing in self._entries.values():
            if existing.source_session_id == sid:
                logger.debug(
                    f"Playbook already exists for session {sid[:8]}..., "
                    f"skipping extraction (id={existing.id})"
                )
                return None

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

        # Deduplicated tool list (preserves order of first occurrence)
        seen_tools: set = set()
        unique_suggested: List[str] = []
        for t in (t["tool"] for t in tool_sequence):
            if t not in seen_tools:
                seen_tools.add(t)
                unique_suggested.append(t)

        strategy = {
            "execution_strategy": (
                session_reward.execution_strategy
                if hasattr(session_reward, "execution_strategy")
                else "rvr"
            ),
            "suggested_tools": unique_suggested,
            "max_turns": len(session_reward.step_rewards),
        }

        # 质量指标
        quality_metrics = {
            "avg_reward": session_reward.total_reward,
            "success_rate": 1.0 if session_reward.success else 0.0,
            "avg_turns": len(session_reward.step_rewards),
        }

        # 生成名称和描述
        # 优先用 user_query 保留语义信息（提高后续 Mem0 匹配率），
        # 否则用工具名摘要作默认值（不暴露 session_id）
        if user_query:
            name = user_query[:40].strip()
            description = user_query[:200].strip()
        else:
            tools_brief = ", ".join([t["tool"] for t in tool_sequence[:3]])
            name = f"Auto-{tools_brief}" if tool_sequence else "Auto-strategy"
            description = "自动提取的策略"

        if use_llm:
            llm = await self._get_llm_service()
            if llm:
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
        self, session_reward, tool_sequence: List[Dict],
        user_query_hint: str = "",
    ) -> tuple[str, str]:
        """
        使用 LLM 生成策略名称和描述。

        描述质量直接决定 Mem0 语义匹配的精度。
        泛化的描述（如"自动提取的策略"）会导致假阳性匹配。
        """
        from core.llm import Message

        tools_str = ", ".join([t["tool"] for t in tool_sequence])

        user_context_line = ""
        if user_query_hint:
            user_context_line = f"- 用户原始需求：{user_query_hint[:200]}\n"

        prompt = f"""根据以下会话执行信息，生成策略名称和描述。

会话信息：
{user_context_line}- 使用的工具序列：{tools_str}
- 执行步骤数：{len(session_reward.step_rewards)}
- 成功率：100%

要求：
1. 名称：10-20 字，概括这个策略的任务类型
2. 描述：1-2 句话，说明什么场景下使用。描述必须**具体**，能和不相关的任务区分开

<examples>
<example>
<tools>data_analysis_skill, chart_generation</tools>
<output>{{"name": "Excel 数据分析并生成图表", "description": "用户上传 Excel/CSV 表格文件，需要分析数据特征并生成可视化图表时使用"}}</output>
</example>
<example>
<tools>web_search, web_scraping</tools>
<output>{{"name": "网络搜索与信息整理", "description": "用户需要从互联网搜索特定主题的信息并整理成结构化摘要时使用"}}</output>
</example>
<example>
<tools>nodes, file_operation</tools>
<output>{{"name": "本地文件批量整理", "description": "用户需要扫描本地文件夹、按类型分类或批量重命名文件时使用"}}</output>
</example>
</examples>

输出 JSON 格式：
{{"name": "策略名称", "description": "策略描述"}}
"""

        llm = await self._get_llm_service()
        if not llm:
            return "自动策略", "自动生成的策略"

        response = await llm.create_message_async(
            messages=[Message(role="user", content=prompt)],
            system="你是一个策略库管理助手。生成的描述必须具体、有区分度，避免泛化。",
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
        min_score: float = 0.0,
        only_approved: bool = True,
    ) -> List[tuple["PlaybookEntry", float]]:
        """
        语义匹配策略（LLM-First 设计）

        两层匹配：
        1. Layer 1: task_type 预筛（确定性规则，<1ms）
        2. Layer 2: 独立向量库语义搜索（向量相似度，零额外 LLM 调用）

        独立向量库：playbook_vectors.db 只包含 playbook 条目，
        KNN 搜索 100% 命中 playbook，不受用户记忆数量影响。

        Args:
            query: 用户查询（自然语言）
            task_type: 意图识别输出的任务类型（可选）
            top_k: 返回前 k 个
            min_score: 最低匹配分数（默认 0.0，不做硬门控）
            only_approved: 仅返回已审核通过的策略

        Returns:
            [(策略, 匹配分数), ...]
        """
        # Layer 1: task_type 预筛 + 过期过滤（lazy evaluation）
        candidates = {
            entry_id: entry
            for entry_id, entry in self._entries.items()
            if (not only_approved or entry.status == PlaybookStatus.APPROVED)
            and entry.matches_task_type(task_type)
            and not entry.is_stale()
        }

        if not candidates:
            return []

        # Layer 2: 独立向量库搜索（表里只有 playbook，无需 user_id 过滤）
        try:
            store = self._get_vector_store()
            embedding = self._get_embedding_model()

            query_vector = embedding.embed(query)
            if not isinstance(query_vector, list):
                query_vector = query_vector.tolist() if hasattr(query_vector, "tolist") else list(query_vector)

            total_vectors = store.count() if hasattr(store, "count") else 200
            if total_vectors <= 200:
                fetch_limit = max(total_vectors, 1)
            else:
                fetch_limit = max(top_k * 10, 100)

            search_results_raw = store.search(
                query=query,
                vectors=[query_vector],
                limit=fetch_limit,
            )

            logger.info(
                f"Playbook 向量搜索: query={query[:40]}..., "
                f"results={len(search_results_raw)}, "
                f"candidates={list(candidates.keys())}"
            )

            # 匹配搜索结果和候选 Playbook（按 playbook_id 去重）
            matched = []
            seen_ids: set = set()
            for item in search_results_raw:
                payload = item.payload if hasattr(item, "payload") else {}
                playbook_id = payload.get("playbook_id", "")
                score = item.score if hasattr(item, "score") else 0.0

                if playbook_id in candidates and playbook_id not in seen_ids:
                    logger.info(
                        f"Playbook 匹配候选: id={playbook_id[:8]}, "
                        f"score={score:.3f}, min={min_score}, "
                        f"pass={'Y' if score >= min_score else 'N'}"
                    )

                if (
                    playbook_id in candidates
                    and playbook_id not in seen_ids
                    and score >= min_score
                ):
                    seen_ids.add(playbook_id)
                    matched.append((candidates[playbook_id], score))

            if matched:
                matched.sort(key=lambda x: x[1], reverse=True)
                return matched[:top_k]

        except Exception as e:
            logger.warning(f"Playbook 向量搜索失败: {e}")

        return []

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
        """Record a successful match+injection (updates usage_count and last_used_at)."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.usage_count += 1
            entry.last_used_at = datetime.now().isoformat()
            await self._save_entry(entry)

    # ==================== 统计信息 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        entries = list(self._entries.values())
        approved = [e for e in entries if e.status == PlaybookStatus.APPROVED]

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
            "stale_count": sum(1 for e in approved if e.is_stale()),
            "stale_days_threshold": STALE_DAYS,
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
