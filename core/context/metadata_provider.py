"""
Conversation Metadata Provider - 通用的对话元数据获取器

设计原则：
1. 统一接口：从 conversation.metadata 获取各种上下文数据
2. 可扩展：后续添加新数据类型只需添加 get_xxx() 方法
3. 懒加载：只在需要时查询数据库
4. 类型安全：每种数据类型都有明确的结构定义

使用方式：
    provider = ConversationMetadataProvider(conversation_id)
    plan = await provider.get_plan()
    compression_info = await provider.get_compression_info()
    
    # 或者一次性获取所有需要的数据
    context_data = await provider.get_context_data(["plan", "compression"])
"""

from typing import Any, Dict, List, Optional, TypeVar, Callable, Awaitable
from dataclasses import dataclass
from logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class MetadataField:
    """
    Metadata 字段配置
    
    Attributes:
        key: metadata 中的键名
        default: 默认值
        processor: 可选的后处理函数
    """
    key: str
    default: Any = None
    processor: Optional[Callable[[Any], Any]] = None


class ConversationMetadataProvider:
    """
    对话元数据提供器
    
    统一从 conversation.metadata 获取各种上下文数据。
    支持缓存、懒加载和可配置的后处理。
    
    已支持的字段：
    - plan: 任务计划数据
    - compression: 对话压缩信息
    
    扩展方式：
    1. 在 FIELD_CONFIGS 中添加字段配置
    2. 添加对应的 get_xxx() 方法
    """
    
    # 字段配置（集中管理所有支持的 metadata 字段）
    FIELD_CONFIGS: Dict[str, MetadataField] = {
        "plan": MetadataField(
            key="plan",
            default=None,
        ),
        "compression": MetadataField(
            key="compression",
            default=None,
        ),
        # 🆕 后续扩展示例：
        # "user_preferences": MetadataField(
        #     key="user_preferences",
        #     default={},
        # ),
        # "session_context": MetadataField(
        #     key="session_context",
        #     default={},
        # ),
    }
    
    def __init__(self, conversation_id: Optional[str] = None):
        """
        初始化 Provider
        
        Args:
            conversation_id: 对话 ID
        """
        self._conversation_id = conversation_id
        self._conversation_service = None
        self._metadata_cache: Optional[Dict[str, Any]] = None
        self._cache_loaded = False
    
    async def _get_conversation_service(self):
        """延迟加载 ConversationService"""
        if self._conversation_service is None:
            from services.conversation_service import ConversationService
            self._conversation_service = ConversationService()
        return self._conversation_service
    
    async def _load_metadata(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        加载对话的 metadata（带缓存）
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            metadata 字典
        """
        if self._cache_loaded and not force_refresh and self._metadata_cache is not None:
            return self._metadata_cache
        
        if not self._conversation_id:
            self._metadata_cache = {}
            self._cache_loaded = True
            return self._metadata_cache
        
        try:
            service = await self._get_conversation_service()
            conversation = await service.get_conversation(self._conversation_id)
            
            if conversation and conversation.metadata:
                self._metadata_cache = conversation.metadata if isinstance(conversation.metadata, dict) else {}
            else:
                self._metadata_cache = {}
            
            self._cache_loaded = True
            logger.debug(f"📋 已加载 metadata: conversation_id={self._conversation_id}, keys={list(self._metadata_cache.keys())}")
            
        except Exception as e:
            logger.warning(f"加载 metadata 失败: {e}")
            self._metadata_cache = {}
            self._cache_loaded = True
        
        return self._metadata_cache
    
    def _get_field(
        self, 
        metadata: Dict[str, Any], 
        field_name: str
    ) -> Any:
        """
        从 metadata 获取指定字段
        
        Args:
            metadata: metadata 字典
            field_name: 字段名（必须在 FIELD_CONFIGS 中定义）
            
        Returns:
            字段值（经过 processor 处理后）
        """
        config = self.FIELD_CONFIGS.get(field_name)
        if not config:
            logger.warning(f"⚠️ 未知的 metadata 字段: {field_name}")
            return None
        
        value = metadata.get(config.key, config.default)
        
        # 应用 processor
        if value is not None and config.processor:
            try:
                value = config.processor(value)
            except Exception as e:
                logger.warning(f"字段 {field_name} 处理失败: {e}")
                value = config.default
        
        return value
    
    # ==================== 公开的获取方法 ====================
    
    async def get_plan(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取当前计划
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            计划数据，不存在则返回 None
        """
        metadata = await self._load_metadata(force_refresh)
        plan = self._get_field(metadata, "plan")
        
        if plan:
            logger.debug(f"📋 获取 plan: {plan.get('name', 'Unknown')}")
        
        return plan
    
    async def get_compression_info(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        获取对话压缩信息
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            压缩信息，不存在则返回 None
        """
        metadata = await self._load_metadata(force_refresh)
        return self._get_field(metadata, "compression")
    
    async def get_context_data(
        self, 
        fields: List[str], 
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        批量获取多个字段（一次数据库查询）
        
        Args:
            fields: 需要获取的字段列表，如 ["plan", "compression"]
            force_refresh: 是否强制刷新缓存
            
        Returns:
            字段名 -> 字段值 的字典
            
        Example:
            data = await provider.get_context_data(["plan", "compression"])
            plan = data.get("plan")
            compression = data.get("compression")
        """
        metadata = await self._load_metadata(force_refresh)
        
        result = {}
        for field_name in fields:
            result[field_name] = self._get_field(metadata, field_name)
        
        return result
    
    async def get_raw_metadata(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        获取原始 metadata（不经过字段配置处理）
        
        适用于需要访问未在 FIELD_CONFIGS 中定义的字段
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            原始 metadata 字典
        """
        return await self._load_metadata(force_refresh)
    
    def invalidate_cache(self) -> None:
        """清除缓存，下次获取时会重新查询数据库"""
        self._metadata_cache = None
        self._cache_loaded = False
        logger.debug(f"🔄 metadata 缓存已清除: conversation_id={self._conversation_id}")
    
    def set_conversation_id(self, conversation_id: str) -> None:
        """
        设置/更新 conversation_id（同时清除缓存）
        
        Args:
            conversation_id: 新的对话 ID
        """
        if self._conversation_id != conversation_id:
            self._conversation_id = conversation_id
            self.invalidate_cache()


# ==================== 便捷函数 ====================

async def load_plan_for_context(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    便捷函数：加载对话的计划数据
    
    用于替代原有的 load_plan_for_session()，提供更统一的接口
    
    Args:
        conversation_id: 对话 ID
        
    Returns:
        计划数据，不存在则返回 None
    """
    provider = ConversationMetadataProvider(conversation_id)
    plan = await provider.get_plan()
    
    if plan:
        logger.info(f"📋 已加载计划: {plan.get('name', 'Unknown')}, conversation_id={conversation_id}")
    
    return plan


async def load_context_metadata(
    conversation_id: str,
    fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    便捷函数：批量加载上下文元数据
    
    Args:
        conversation_id: 对话 ID
        fields: 需要加载的字段列表，默认 ["plan", "compression"]
        
    Returns:
        字段名 -> 字段值 的字典
        
    Example:
        context = await load_context_metadata("conv_123", ["plan"])
        plan = context.get("plan")
    """
    if fields is None:
        fields = ["plan", "compression"]
    
    provider = ConversationMetadataProvider(conversation_id)
    return await provider.get_context_data(fields)
