"""
Memory Manager - 统一记忆管理器

职责：
- 整合各层记忆（Working、User、System）
- 提供统一的内存访问接口
- 管理记忆的生命周期

设计原则：
- 统一入口：所有记忆通过 Manager 访问
- 按需加载：只在需要时创建子记忆
- 可扩展：支持添加新的记忆类型
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from logger import get_logger

from .working import WorkingMemory, create_working_memory
from .user import (
    EpisodicMemory, create_episodic_memory,
    PreferenceMemory, create_preference_memory,
    E2BMemory, create_e2b_memory,  # E2B 现在是用户级记忆
    PlanMemory, create_plan_memory  # 🆕 任务计划持久化
)
from .system import SkillMemory, create_skill_memory, CacheMemory, create_cache_memory
from .mem0 import get_mem0_pool
from .mem0.schemas import MemoryCard, MemoryCardCategory

logger = get_logger("memory.manager")


class MemoryManager:
    """
    统一记忆管理器
    
    整合三层记忆：
    - Working Memory（会话级短期记忆）
    - User Memory（用户级长期记忆）
    - System Memory（系统级全局记忆）
    
    Args:
        user_id: 用户 ID（用于隔离用户级记忆）
        storage_dir: 存储目录（用于持久化）
    """
    
    def __init__(
        self,
        user_id: Optional[str] = None,
        storage_dir: Optional[str] = None
    ):
        self.user_id = user_id
        self.storage_dir = storage_dir
        
        # === 会话级记忆 ===
        self.working = create_working_memory()
        
        # === 用户级记忆 ===
        # E2B 沙箱记忆（用户的云端计算环境）
        self.e2b = create_e2b_memory(user_id=user_id)
        
        # 用户经验和偏好（按需创建）
        self._episodic: Optional[EpisodicMemory] = None
        self._preference: Optional[PreferenceMemory] = None
        self._plan: Optional[PlanMemory] = None  # 🆕 任务计划持久化
        
        # === 系统级记忆（单例）===
        self._skill: Optional[SkillMemory] = None
        self._cache: Optional[CacheMemory] = None
    
    # ==================== 用户级记忆（懒加载）====================
    
    @property
    def episodic(self) -> EpisodicMemory:
        """获取用户历史经验记忆（懒加载）"""
        if self._episodic is None:
            self._episodic = create_episodic_memory(
                user_id=self.user_id,
                storage_dir=self.storage_dir
            )
        return self._episodic
    
    @property
    def preference(self) -> PreferenceMemory:
        """获取用户偏好记忆（懒加载）"""
        if self._preference is None:
            self._preference = create_preference_memory(
                user_id=self.user_id,
                storage_dir=self.storage_dir
            )
        return self._preference
    
    @property
    def plan(self) -> PlanMemory:
        """
        获取任务计划记忆（懒加载）
        
        🆕 V4.3 新增：支持跨 Session 任务计划持久化
        
        用途：
        - 保存任务计划（首次 Session）
        - 恢复任务进度（后续 Session）
        - 生成进度摘要（自动注入 Prompt）
        """
        if self._plan is None:
            self._plan = create_plan_memory(
                user_id=self.user_id,
                storage_dir=self.storage_dir
            )
        return self._plan
    
    # ==================== 系统级记忆（懒加载）====================
    
    @property
    def skill(self) -> SkillMemory:
        """获取 Skill 缓存（懒加载）- 本地工作流技能"""
        if self._skill is None:
            self._skill = create_skill_memory()
        return self._skill
    
    @property
    def cache(self) -> CacheMemory:
        """获取系统缓存（懒加载）"""
        if self._cache is None:
            self._cache = create_cache_memory()
        return self._cache
    
    # ==================== 生命周期管理 ====================
    
    def start_task(self, task_id: str, user_intent: str):
        """
        开始新任务
        
        Args:
            task_id: 任务 ID
            user_intent: 用户意图
        """
        self.working.clear()
        self.working.update_metadata("task_id", task_id)
        self.working.update_metadata("user_intent", user_intent)
        self.working.update_metadata("start_time", datetime.now().isoformat())
        
        if self.user_id:
            self.working.update_metadata("user_id", self.user_id)
        
        logger.debug(f"[MemoryManager] 开始任务: task_id={task_id}")
    
    def end_task(self, result: Any, save_to_episodic: bool = True):
        """
        结束任务
        
        Args:
            result: 任务结果
            save_to_episodic: 是否保存到用户历史
        """
        task_id = self.working.get_metadata("task_id", "unknown")
        user_intent = self.working.get_metadata("user_intent", "")
        
        if save_to_episodic:
            self.episodic.add_episode(
                task_id=task_id,
                user_intent=user_intent,
                result=result,
                metadata=self.working.metadata.copy()
            )
        
        logger.debug(f"[MemoryManager] 结束任务: task_id={task_id}")
    
    def clear_session(self):
        """清空会话级记忆（保留持久沙箱）"""
        self.working.clear()
        self.e2b.clear_temporary()  # 只清除临时沙箱
    
    def clear_all(self):
        """清空所有记忆（慎用）"""
        self.working.clear()
        self.e2b.clear_all()  # 清除所有沙箱（包括持久）
        
        if self._episodic:
            self._episodic.clear()
        if self._preference:
            self._preference.clear()
        if self._plan:
            self._plan.clear()  # 🆕 清除任务计划
        if self._skill:
            self._skill.clear()
        if self._cache:
            self._cache.clear()
    
    # ==================== 上下文生成 ====================
    
    def get_context_for_llm(
        self,
        include_episodic: bool = False,
        include_persona: bool = True,
        max_persona_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        为 LLM 准备上下文
        
        Args:
            include_episodic: 是否包含历史经验
            include_persona: 是否包含用户画像（新增）
            max_persona_tokens: 画像 Token 上限（新增）
            
        Returns:
            上下文字典
        """
        context = {
            "messages": self.working.get_messages(),
            "tool_history": self.working.get_tool_history(),
            "metadata": self.working.metadata
        }
        
        # E2B 上下文
        e2b_context = self.e2b.get_context_for_llm()
        if e2b_context:
            context["e2b_context"] = e2b_context
        
        # 历史经验
        if include_episodic:
            user_intent = self.working.get_metadata("user_intent", "")
            if user_intent:
                similar = self.episodic.get_similar_episodes(user_intent, top_k=2)
                context["similar_episodes"] = similar
        
        # 用户画像注入（预计算注入模式，新增）
        if include_persona and self.user_id:
            try:
                from .mem0.update.persona_builder import get_persona_builder
                from .mem0.retrieval.formatter import create_dazee_prompt_section
                
                # 获取显式记忆
                explicit_memories = self.list_memory_cards(limit=10)
                
                # 构建画像（异步操作，这里简化同步调用）
                # 注意：实际使用时应该异步调用，这里先提供同步接口
                builder = get_persona_builder()
                import asyncio
                
                # 尝试从当前事件循环获取，如果没有则创建新的
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 如果事件循环正在运行，使用 create_task 或 defer
                        # 这里简化处理：只注入显式记忆
                        persona_prompt = None
                        if explicit_memories:
                            # 简化版本：仅使用显式记忆
                            from .mem0.retrieval.formatter import format_memories_for_prompt
                            memories_dict = [
                                {
                                    "memory": card.content,
                                    "id": card.id,
                                    "created_at": card.created_at.isoformat(),
                                    "metadata": card.to_mem0_metadata()
                                }
                                for card in explicit_memories[:5]
                            ]
                            persona_prompt = format_memories_for_prompt(
                                memories_dict,
                                language="zh",
                                max_memories=5
                            )
                        if persona_prompt:
                            context["user_persona"] = persona_prompt
                    else:
                        # 事件循环未运行，可以直接运行
                        persona = loop.run_until_complete(
                            builder.build_persona(
                                user_id=self.user_id,
                                explicit_memories=explicit_memories
                            )
                        )
                        persona_prompt = create_dazee_prompt_section(
                            persona=persona,
                            explicit_memories=explicit_memories,
                            max_tokens=max_persona_tokens
                        )
                        if persona_prompt:
                            context["user_persona"] = persona_prompt
                except RuntimeError:
                    # 没有事件循环，创建新的
                    persona = asyncio.run(
                        builder.build_persona(
                            user_id=self.user_id,
                            explicit_memories=explicit_memories
                        )
                    )
                    persona_prompt = create_dazee_prompt_section(
                        persona=persona,
                        explicit_memories=explicit_memories,
                        max_tokens=max_persona_tokens
                    )
                    if persona_prompt:
                        context["user_persona"] = persona_prompt
                        
            except Exception as e:
                logger.warning(f"[MemoryManager] 画像注入失败: {e}，跳过画像注入")
        
        return context
    
    # ==================== 显式记忆管理（记忆卡片）====================
    
    def create_memory_card(
        self,
        content: str,
        category: MemoryCardCategory = MemoryCardCategory.OTHER,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        visibility: str = "public",
        ttl_minutes: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        check_sensitive: bool = True,
        check_conflicts: bool = True
    ) -> MemoryCard:
        """
        创建记忆卡片（显式记忆）
        
        Args:
            content: 记忆内容
            category: 记忆分类
            title: 标题（可选）
            tags: 标签列表
            visibility: 可见性（public/private/filtered）
            ttl_minutes: 过期时间（分钟），None 表示永不过期
            metadata: 额外元数据
            check_sensitive: 是否检查敏感信息（新增）
            check_conflicts: 是否检查冲突（新增）
            
        Returns:
            MemoryCard 对象
        """
        if not self.user_id:
            raise ValueError("user_id 不能为空，请先设置 user_id")
        
        import uuid
        from datetime import datetime
        from .mem0.schemas import MemoryType, MemorySource, MemoryVisibility as MemVisibility
        from .mem0.update.quality_control import get_quality_controller
        from .mem0 import get_mem0_pool
        
        quality_controller = get_quality_controller()
        pool = get_mem0_pool()
        
        # 取 Top-K 相似记忆（Mem0 更新阶段逻辑）
        similar_memories = pool.search(
            user_id=self.user_id,
            query=content,
            limit=5
        ) if check_conflicts else []
        
        # 更新阶段决策（LLM 驱动）
        if check_sensitive or check_conflicts:
            decision = quality_controller._run_update_stage(content, similar_memories)
        else:
            decision = {"memory": [{"id": "0", "text": content, "event": "ADD"}]}

        actions = quality_controller.extract_update_actions(decision)
        update_targets = []
        action = "NONE"

        if actions["delete"]:
            update_targets = [item.get("id") for item in actions["delete"] if item.get("id")]
            for target_id in update_targets:
                pool.delete(memory_id=target_id, user_id=self.user_id)
            logger.info(
                f"[MemoryManager] 删除记忆: user_id={self.user_id}, targets={len(update_targets)}"
            )
            action = "DELETE"
            content = actions["delete"][0].get("text") or content
            card_id = f"deleted_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        elif actions["update"]:
            update_targets = [item.get("id") for item in actions["update"] if item.get("id")]
            for item in actions["update"]:
                if item.get("id"):
                    pool.update(memory_id=item["id"], data=item.get("text", ""), user_id=self.user_id)
            logger.info(
                f"[MemoryManager] 更新记忆: user_id={self.user_id}, targets={len(update_targets)}"
            )
            action = "UPDATE"
            content = actions["update"][0].get("text") or content
            card_id = update_targets[0] if update_targets else (
                f"updated_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            )
        elif actions["add"]:
            action = "ADD"
            content = actions["add"][0].get("text") or content
            card_id = f"card_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        else:
            # NONE：无需新增或更新，返回未持久化的卡片
            card_id = f"noop_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 解析 visibility 枚举
        vis_enum = MemVisibility(visibility) if isinstance(visibility, str) else visibility
        
        # 创建记忆卡片
        card = MemoryCard(
            id=card_id,
            user_id=self.user_id,
            content=content,
            category=category,
            title=title,
            tags=tags or [],
            visibility=vis_enum,
            ttl_minutes=ttl_minutes,
            metadata=metadata or {}
        )
        
        # 保存到 Mem0（仅 ADD 时写入）
        if action == "ADD":
            message = card.to_mem0_message()
            mem_metadata = card.to_mem0_metadata()
            
            result = pool.add(
                user_id=self.user_id,
                messages=[message],
                metadata=mem_metadata,
                memory_type=card.memory_type.value,
                source=card.source.value,
                visibility=card.visibility.value,
                ttl_minutes=ttl_minutes
            )
            
            # 从 Mem0 结果中获取 memory_id（如果有）
            if result.get("results"):
                mem_result = result["results"][0]
                if "id" in mem_result:
                    card.metadata["mem0_id"] = mem_result["id"]
        else:
            card.metadata["update_action"] = action
            card.metadata["update_targets"] = update_targets
        
        logger.info(
            f"[MemoryManager] 创建记忆卡片: user_id={self.user_id}, "
            f"id={card_id}, category={category.value}, title={title}"
        )
        
        return card
    
    def clean_expired_memories(
        self,
        memory_types: Optional[List[str]] = None
    ) -> int:
        """
        清理过期记忆
        
        Args:
            memory_types: 要清理的记忆类型列表（None 表示清理所有类型）
            
        Returns:
            清理的记忆数量
        """
        if not self.user_id:
            return 0
        
        try:
            from .mem0.update.quality_control import get_quality_controller
            quality_controller = get_quality_controller()
            return quality_controller.clean_expired_memories(
                user_id=self.user_id,
                memory_types=memory_types
            )
        except Exception as e:
            logger.error(f"[MemoryManager] 清理过期记忆失败: {e}")
            return 0
    
    def get_memory_ttl_status(self) -> Dict[str, Any]:
        """
        获取记忆 TTL 状态
        
        Returns:
            TTL 状态信息
        """
        if not self.user_id:
            return {}
        
        try:
            from .mem0.update.quality_control import get_quality_controller
            quality_controller = get_quality_controller()
            return quality_controller.get_memory_ttl_status(user_id=self.user_id)
        except Exception as e:
            logger.error(f"[MemoryManager] 获取 TTL 状态失败: {e}")
            return {}
    
    def list_memory_cards(
        self,
        category: Optional[MemoryCardCategory] = None,
        limit: int = 50,
        include_expired: bool = False
    ) -> List[MemoryCard]:
        """
        列出用户的记忆卡片
        
        Args:
            category: 过滤分类（可选）
            limit: 返回数量限制
            include_expired: 是否包含已过期的卡片
            
        Returns:
            记忆卡片列表
        """
        if not self.user_id:
            return []
        
        try:
            pool = get_mem0_pool()
            # 获取所有记忆（Mem0 不支持按 metadata 过滤，所以我们需要在内存中过滤）
            all_memories = pool.get_all(user_id=self.user_id, limit=200)
            
            cards = []
            for mem in all_memories:
                # 检查是否是显式记忆
                mem_metadata = mem.get("metadata", {})
                if mem_metadata.get("memory_type") != "explicit":
                    continue
                
                # 检查分类
                if category and mem_metadata.get("category") != category.value:
                    continue
                
                # 尝试构建 MemoryCard
                try:
                    card_data = {
                        "id": mem_metadata.get("card_id") or mem.get("id", mem.get("memory_id", "")),
                        "user_id": self.user_id,
                        "content": mem.get("memory", ""),
                        "category": mem_metadata.get("category", "other"),
                        "title": mem_metadata.get("title"),
                        "tags": mem_metadata.get("tags", []),
                        "memory_type": mem_metadata.get("memory_type", "explicit"),
                        "source": mem_metadata.get("source", "user_card"),
                        "visibility": mem_metadata.get("visibility", "public"),
                        "ttl_minutes": mem_metadata.get("ttl_minutes"),
                        "metadata": {k: v for k, v in mem_metadata.items() 
                                   if k not in ["memory_type", "source", "visibility", 
                                               "category", "title", "tags", "ttl_minutes", "card_id"]},
                        "created_at": mem.get("created_at", datetime.now().isoformat()),
                        "updated_at": mem.get("updated_at", mem.get("created_at", datetime.now().isoformat())),
                        "expires_at": mem_metadata.get("expires_at")
                    }
                    card_data["metadata"]["mem0_id"] = mem.get("id", mem.get("memory_id", ""))
                    
                    card = MemoryCard.from_dict(card_data)
                    
                    # 检查过期
                    if not include_expired and card.is_expired():
                        continue
                    
                    cards.append(card)
                except Exception as e:
                    logger.warning(f"[MemoryManager] 解析记忆卡片失败: {e}")
                    continue
            
            # 按创建时间倒序排序
            cards.sort(key=lambda c: c.created_at, reverse=True)
            
            logger.info(
                f"[MemoryManager] 列出记忆卡片: user_id={self.user_id}, "
                f"总数={len(cards)}, 分类={category.value if category else 'all'}"
            )
            
            return cards[:limit]
            
        except Exception as e:
            logger.error(f"[MemoryManager] 列出记忆卡片失败: {e}")
            return []
    
    def get_memory_card(self, card_id: str) -> Optional[MemoryCard]:
        """
        获取单个记忆卡片
        
        Args:
            card_id: 记忆卡片 ID
            
        Returns:
            MemoryCard 对象，不存在则返回 None
        """
        if not self.user_id:
            return None
        
        try:
            pool = get_mem0_pool()
            # Mem0 的 get_all 不支持按 ID 查询，所以我们需要列出所有然后过滤
            cards = self.list_memory_cards(limit=200, include_expired=True)
            
            for card in cards:
                if card.id == card_id or card.metadata.get("mem0_id") == card_id:
                    return card
            
            return None
            
        except Exception as e:
            logger.error(f"[MemoryManager] 获取记忆卡片失败: {e}")
            return None
    
    def delete_memory_card(self, card_id: str) -> bool:
        """
        删除记忆卡片
        
        Args:
            card_id: 记忆卡片 ID
            
        Returns:
            是否删除成功
        """
        if not self.user_id:
            return False
        
        try:
            # 先获取卡片，找到 Mem0 的 memory_id
            card = self.get_memory_card(card_id)
            if not card:
                logger.warning(f"[MemoryManager] 记忆卡片不存在: card_id={card_id}")
                return False
            
            pool = get_mem0_pool()
            
            # 尝试使用 Mem0 的 ID 删除
            mem0_id = card.metadata.get("mem0_id") or card_id
            success = pool.delete(memory_id=mem0_id, user_id=self.user_id)
            
            if success:
                logger.info(
                    f"[MemoryManager] 删除记忆卡片: user_id={self.user_id}, "
                    f"card_id={card_id}, mem0_id={mem0_id}"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"[MemoryManager] 删除记忆卡片失败: {e}")
            return False
    
    def search_memory_cards(
        self,
        query: str,
        category: Optional[MemoryCardCategory] = None,
        limit: int = 10
    ) -> List[MemoryCard]:
        """
        搜索记忆卡片
        
        Args:
            query: 搜索查询
            category: 过滤分类（可选）
            limit: 返回数量限制
            
        Returns:
            记忆卡片列表
        """
        if not self.user_id:
            return []
        
        try:
            pool = get_mem0_pool()
            # 使用 Mem0 的搜索功能
            memories = pool.search(user_id=self.user_id, query=query, limit=limit * 2)
            
            cards = []
            for mem in memories:
                mem_metadata = mem.get("metadata", {})
                
                # 只返回显式记忆
                if mem_metadata.get("memory_type") != "explicit":
                    continue
                
                # 检查分类
                if category and mem_metadata.get("category") != category.value:
                    continue
                
                # 构建 MemoryCard
                try:
                    card_data = {
                        "id": mem_metadata.get("card_id") or mem.get("id", mem.get("memory_id", "")),
                        "user_id": self.user_id,
                        "content": mem.get("memory", ""),
                        "category": mem_metadata.get("category", "other"),
                        "title": mem_metadata.get("title"),
                        "tags": mem_metadata.get("tags", []),
                        "memory_type": mem_metadata.get("memory_type", "explicit"),
                        "source": mem_metadata.get("source", "user_card"),
                        "visibility": mem_metadata.get("visibility", "public"),
                        "ttl_minutes": mem_metadata.get("ttl_minutes"),
                        "metadata": {k: v for k, v in mem_metadata.items() 
                                   if k not in ["memory_type", "source", "visibility", 
                                               "category", "title", "tags", "ttl_minutes", "card_id"]},
                        "created_at": mem.get("created_at", datetime.now().isoformat()),
                        "updated_at": mem.get("updated_at", mem.get("created_at", datetime.now().isoformat())),
                        "expires_at": mem_metadata.get("expires_at")
                    }
                    card_data["metadata"]["mem0_id"] = mem.get("id", mem.get("memory_id", ""))
                    
                    card = MemoryCard.from_dict(card_data)
                    cards.append(card)
                except Exception as e:
                    logger.warning(f"[MemoryManager] 解析记忆卡片失败: {e}")
                    continue
            
            logger.info(
                f"[MemoryManager] 搜索记忆卡片: user_id={self.user_id}, "
                f"query={query[:30]}..., 结果数={len(cards)}"
            )
            
            return cards[:limit]
            
        except Exception as e:
            logger.error(f"[MemoryManager] 搜索记忆卡片失败: {e}")
            return []
    
    # ==================== 用户切换 ====================
    
    def switch_user(self, user_id: str):
        """
        切换用户
        
        会清空用户级记忆缓存，下次访问时重新加载
        
        Args:
            user_id: 新用户 ID
        """
        self.user_id = user_id
        self._episodic = None
        self._preference = None
        logger.debug(f"[MemoryManager] 切换用户: user_id={user_id}")
    
    # ==================== 状态查询 ====================
    
    def summary(self) -> str:
        """获取摘要信息"""
        return (
            f"MemoryManager("
            f"user_id={self.user_id}, "
            f"working={self.working.summary()}, "
            f"e2b={'active' if self.e2b.has_active_session() else 'none'}, "
            f"episodic={'loaded' if self._episodic else 'not_loaded'}, "
            f"plan={'loaded' if self._plan else 'not_loaded'}, "
            f"skill={'loaded' if self._skill else 'not_loaded'})"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "user_id": self.user_id,
            "storage_dir": self.storage_dir,
            "working": self.working.to_dict(),
            "e2b": self.e2b.to_dict(),
            "episodic_loaded": self._episodic is not None,
            "preference_loaded": self._preference is not None,
            "plan_loaded": self._plan is not None,  # 🆕
            "skill_loaded": self._skill is not None,
            "cache_loaded": self._cache is not None
        }


# ==================== 工厂函数 ====================

def create_memory_manager(
    user_id: Optional[str] = None,
    storage_dir: Optional[str] = None
) -> MemoryManager:
    """
    创建 MemoryManager 实例
    
    Args:
        user_id: 用户 ID（用于隔离用户级记忆）
        storage_dir: 存储目录（用于持久化）
        
    Returns:
        配置好的 MemoryManager 实例
    """
    return MemoryManager(user_id=user_id, storage_dir=storage_dir)


def create_user_memory_manager(
    user_id: str,
    storage_dir: Optional[str] = None
) -> MemoryManager:
    """
    创建用户专属的 MemoryManager
    
    Args:
        user_id: 用户 ID（必填）
        storage_dir: 存储目录
        
    Returns:
        配置好的 MemoryManager 实例
    """
    if not user_id:
        raise ValueError("user_id 不能为空")
    
    return MemoryManager(user_id=user_id, storage_dir=storage_dir)

