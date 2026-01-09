"""
实例级提示词缓存管理器 - InstancePromptCache

🆕 V5.0: 支持本地文件持久化，启动时优先加载磁盘缓存

设计原则：
1. 实例启动时一次性加载，全局缓存
2. 用空间换时间，避免重复分析
3. 所有提示词版本启动时生成，运行时直接取缓存
4. 🆕 V5.0: 支持持久化到本地文件，避免重复 LLM 分析

数据流：
┌─────────────────────────────────────────────────────────────┐
│ 启动阶段（优先加载磁盘缓存）                                    │
│ 1. 检查 .cache/ 目录是否有有效缓存                             │
│ 2. 有效缓存 → 直接加载（< 100ms）                              │
│ 3. 无效/无缓存 → LLM 分析（2-3秒）→ 写入磁盘缓存               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 运行阶段（每次请求，毫秒级）                                     │
│ 1. 直接从内存缓存获取 intent_prompt                            │
│ 2. 意图识别 → 复杂度                                          │
│ 3. 直接从内存缓存获取对应版本 system_prompt                     │
└─────────────────────────────────────────────────────────────┘

缓存文件结构（.cache/）：
├── prompt_cache.json       # 提示词缓存
├── agent_schema.json       # AgentSchema 缓存
└── cache_meta.json         # 缓存元数据（哈希、时间戳）
"""

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, Protocol

import json

from logger import get_logger

logger = get_logger("instance_cache")


# ============================================================
# 缓存存储后端抽象（预留云端同步扩展点）
# ============================================================

class CacheStorageBackend(ABC):
    """
    缓存存储后端抽象接口
    
    🆕 V5.0: 预留云端同步扩展点
    当前实现：LocalFileBackend
    未来扩展：CloudSyncBackend（S3/OSS/数据库）
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
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存"""
        pass


class LocalFileBackend(CacheStorageBackend):
    """
    本地文件存储后端
    
    存储位置：instances/xxx/.cache/
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{key}.json"
    
    def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存到本地 JSON 文件"""
        try:
            path = self._get_path(key)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"💾 已保存缓存: {path}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存缓存失败: {e}")
            return False
    
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """从本地 JSON 文件加载"""
        try:
            path = self._get_path(key)
            if not path.exists():
                return None
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ 加载缓存失败: {e}")
            return None
    
    def exists(self, key: str) -> bool:
        """检查本地文件是否存在"""
        return self._get_path(key).exists()
    
    def delete(self, key: str) -> bool:
        """删除本地缓存文件"""
        try:
            path = self._get_path(key)
            if path.exists():
                path.unlink()
            return True
        except Exception as e:
            logger.error(f"❌ 删除缓存失败: {e}")
            return False


# ============================================================
# 缓存数据结构
# ============================================================

@dataclass
class CacheMetrics:
    """缓存性能指标"""
    load_time_ms: float = 0
    llm_analysis_time_ms: float = 0
    prompt_generation_time_ms: float = 0
    disk_load_time_ms: float = 0  # 🆕 V5.0: 磁盘加载耗时
    cache_hits: int = 0
    cache_misses: int = 0
    disk_hits: int = 0  # 🆕 V5.0: 磁盘缓存命中次数
    disk_misses: int = 0  # 🆕 V5.0: 磁盘缓存未命中次数


@dataclass
class CacheMeta:
    """
    缓存元数据
    
    用于判断缓存是否有效（基于内容哈希）
    """
    prompt_hash: str  # prompt.md 的哈希
    config_hash: str  # config.yaml 的哈希
    combined_hash: str  # 组合哈希
    created_at: str  # 创建时间
    version: str = "5.0"  # 缓存版本
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheMeta":
        return cls(
            prompt_hash=data.get("prompt_hash", ""),
            config_hash=data.get("config_hash", ""),
            combined_hash=data.get("combined_hash", ""),
            created_at=data.get("created_at", ""),
            version=data.get("version", "5.0"),
        )


class InstancePromptCache:
    """
    实例级提示词缓存管理器（单例模式）
    
    核心职责：
    1. 实例启动时一次性加载所有提示词版本
    2. 运行时提供毫秒级的提示词访问
    3. 管理缓存生命周期（包括失效检测）
    4. 🆕 V5.0: 支持本地文件持久化
    
    使用方式：
    ```python
    # 获取缓存实例（单例）
    cache = InstancePromptCache.get_instance("test_agent")
    
    # 设置缓存目录（持久化）
    cache.set_cache_dir("/path/to/instances/test_agent/.cache")
    
    # 启动时一次性加载（优先加载磁盘缓存）
    await cache.load_once(raw_prompt, config, force_refresh=False)
    
    # 运行时获取提示词
    intent_prompt = cache.get_intent_prompt()
    system_prompt = cache.get_system_prompt(TaskComplexity.MEDIUM)
    agent_schema = cache.agent_schema
    ```
    """
    
    # 类级别的实例存储（单例模式）
    _instances: Dict[str, "InstancePromptCache"] = {}
    
    # 缓存文件 key
    CACHE_KEY_PROMPTS = "prompt_cache"
    CACHE_KEY_SCHEMA = "agent_schema"
    CACHE_KEY_META = "cache_meta"
    
    def __init__(self, instance_name: str):
        """
        初始化缓存实例
        
        Args:
            instance_name: 实例名称（如 "test_agent"）
        """
        self.instance_name = instance_name
        
        # 解析后的 Schema
        self.prompt_schema: Optional[Any] = None  # PromptSchema
        self.agent_schema: Optional[Any] = None   # AgentSchema
        
        # 三个版本的系统提示词（启动时一次性生成）
        self.system_prompt_simple: Optional[str] = None
        self.system_prompt_medium: Optional[str] = None
        self.system_prompt_complex: Optional[str] = None
        
        # 意图识别提示词（启动时一次性生成）
        self.intent_prompt: Optional[str] = None
        
        # 原始提示词（用于缓存失效检测）
        self._raw_prompt: str = ""
        self._raw_prompt_hash: str = ""
        self._config_hash: str = ""
        
        # 加载状态
        self.is_loaded: bool = False
        self._load_lock = asyncio.Lock()
        
        # 🆕 V5.0: 持久化存储后端
        self._storage_backend: Optional[CacheStorageBackend] = None
        self._cache_dir: Optional[Path] = None
        
        # 性能指标
        self.metrics = CacheMetrics()
        
        logger.debug(f"📦 创建 InstancePromptCache: {instance_name}")
    
    def set_cache_dir(self, cache_dir: str) -> None:
        """
        设置缓存目录（启用持久化）
        
        🆕 V5.0: 设置后将使用 LocalFileBackend 进行持久化
        
        Args:
            cache_dir: 缓存目录路径（如 instances/test_agent/.cache）
        """
        self._cache_dir = Path(cache_dir)
        self._storage_backend = LocalFileBackend(self._cache_dir)
        logger.debug(f"📁 设置缓存目录: {cache_dir}")
    
    @classmethod
    def get_instance(cls, instance_name: str) -> "InstancePromptCache":
        """
        获取实例缓存（单例模式）
        
        Args:
            instance_name: 实例名称
            
        Returns:
            InstancePromptCache 实例
        """
        if instance_name not in cls._instances:
            cls._instances[instance_name] = cls(instance_name)
        return cls._instances[instance_name]
    
    @classmethod
    def clear_all(cls):
        """清除所有缓存实例（测试用）"""
        cls._instances.clear()
        logger.info("🧹 已清除所有 InstancePromptCache 实例")
    
    async def load_once(
        self,
        raw_prompt: str,
        config: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> bool:
        """
        一次性加载所有提示词版本（幂等）
        
        🆕 V5.0 加载流程：
        1. 检查是否已加载（幂等）
        2. 🆕 尝试从磁盘加载缓存（优先）
        3. 缓存无效时：LLM 分析 → 生成提示词 → 写入磁盘
        
        Args:
            raw_prompt: 运营写的原始系统提示词
            config: 实例配置（来自 config.yaml）
            force_refresh: 强制刷新缓存
            
        Returns:
            是否成功加载
        """
        start_time = time.time()
        
        async with self._load_lock:
            # 计算内容哈希（用于失效检测）
            prompt_hash = self._compute_hash(raw_prompt)
            config_hash = self._compute_hash(json.dumps(config or {}, sort_keys=True))
            combined_hash = self._compute_hash(prompt_hash + config_hash)
            
            # 检查内存缓存是否有效
            if self.is_loaded and not force_refresh:
                if combined_hash == self._compute_hash(self._raw_prompt_hash + self._config_hash):
                    self.metrics.cache_hits += 1
                    logger.debug(f"✅ 内存缓存命中: {self.instance_name}")
                    return True
                else:
                    logger.info(f"⚠️ 配置已变化，重新加载: {self.instance_name}")
            
            # 🆕 V5.0: 尝试从磁盘加载缓存
            if not force_refresh and self._storage_backend:
                disk_start = time.time()
                if self._try_load_from_disk(combined_hash):
                    self.metrics.disk_hits += 1
                    self.metrics.disk_load_time_ms = (time.time() - disk_start) * 1000
                    self.metrics.load_time_ms = (time.time() - start_time) * 1000
                    
                    # 保存哈希用于后续比对
                    self._raw_prompt = raw_prompt
                    self._raw_prompt_hash = prompt_hash
                    self._config_hash = config_hash
                    self.is_loaded = True
                    
                    logger.info(f"✅ 从磁盘缓存加载: {self.instance_name}")
                    logger.info(f"   磁盘加载耗时: {self.metrics.disk_load_time_ms:.0f}ms")
                    return True
                else:
                    self.metrics.disk_misses += 1
                    logger.debug(f"📁 磁盘缓存未命中或已失效")
            
            # 缓存未命中，执行 LLM 分析
            self.metrics.cache_misses += 1
            logger.info(f"🔄 开始 LLM 分析: {self.instance_name}")
            
            try:
                # 保存原始提示词和哈希
                self._raw_prompt = raw_prompt
                self._raw_prompt_hash = prompt_hash
                self._config_hash = config_hash
                
                # 1. LLM 语义分析 → PromptSchema + AgentSchema
                llm_start = time.time()
                await self._analyze_with_llm(raw_prompt, config)
                self.metrics.llm_analysis_time_ms = (time.time() - llm_start) * 1000
                
                # 2. 生成三个版本的系统提示词
                gen_start = time.time()
                await self._generate_all_prompts()
                self.metrics.prompt_generation_time_ms = (time.time() - gen_start) * 1000
                
                # 3. 生成意图识别提示词
                await self._generate_intent_prompt()
                
                self.is_loaded = True
                self.metrics.load_time_ms = (time.time() - start_time) * 1000
                
                # 🆕 V5.0: 写入磁盘缓存
                if self._storage_backend:
                    self._save_to_disk(combined_hash)
                
                logger.info(f"✅ InstancePromptCache 加载完成: {self.instance_name}")
                logger.info(f"   LLM 分析: {self.metrics.llm_analysis_time_ms:.0f}ms")
                logger.info(f"   提示词生成: {self.metrics.prompt_generation_time_ms:.0f}ms")
                logger.info(f"   总耗时: {self.metrics.load_time_ms:.0f}ms")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ 加载 InstancePromptCache 失败: {e}", exc_info=True)
                # 使用 fallback
                await self._load_fallback(raw_prompt)
                return False
    
    # ============================================================
    # 🆕 V5.0: 磁盘持久化方法
    # ============================================================
    
    def _try_load_from_disk(self, expected_hash: str) -> bool:
        """
        尝试从磁盘加载缓存
        
        Args:
            expected_hash: 期望的内容哈希（用于验证缓存有效性）
            
        Returns:
            是否成功加载
        """
        if not self._storage_backend:
            return False
        
        try:
            # 1. 加载并验证缓存元数据
            meta_data = self._storage_backend.load(self.CACHE_KEY_META)
            if not meta_data:
                logger.debug("📁 缓存元数据不存在")
                return False
            
            meta = CacheMeta.from_dict(meta_data)
            
            # 验证哈希是否匹配
            if meta.combined_hash != expected_hash:
                logger.debug(f"📁 缓存哈希不匹配: {meta.combined_hash[:8]}... != {expected_hash[:8]}...")
                return False
            
            # 验证版本兼容性
            if meta.version != "5.0":
                logger.debug(f"📁 缓存版本不兼容: {meta.version}")
                return False
            
            # 2. 加载提示词缓存
            prompt_data = self._storage_backend.load(self.CACHE_KEY_PROMPTS)
            if not prompt_data:
                logger.debug("📁 提示词缓存不存在")
                return False
            
            self.system_prompt_simple = prompt_data.get("system_prompt_simple")
            self.system_prompt_medium = prompt_data.get("system_prompt_medium")
            self.system_prompt_complex = prompt_data.get("system_prompt_complex")
            self.intent_prompt = prompt_data.get("intent_prompt")
            
            # 3. 加载 AgentSchema 缓存
            schema_data = self._storage_backend.load(self.CACHE_KEY_SCHEMA)
            if schema_data:
                from core.schemas import AgentSchema
                try:
                    self.agent_schema = AgentSchema(**schema_data)
                except Exception as e:
                    logger.warning(f"⚠️ AgentSchema 反序列化失败: {e}，使用默认")
                    from core.schemas import DEFAULT_AGENT_SCHEMA
                    self.agent_schema = DEFAULT_AGENT_SCHEMA
            
            # 4. 重建 PromptSchema（简化版，不需要完整解析）
            from core.prompt import PromptSchema
            self.prompt_schema = PromptSchema(raw_prompt=self._raw_prompt)
            
            logger.debug(f"📁 从磁盘加载缓存成功")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ 从磁盘加载缓存失败: {e}")
            return False
    
    def _save_to_disk(self, combined_hash: str) -> bool:
        """
        保存缓存到磁盘
        
        Args:
            combined_hash: 内容组合哈希
            
        Returns:
            是否成功保存
        """
        if not self._storage_backend:
            return False
        
        try:
            # 1. 保存缓存元数据
            meta = CacheMeta(
                prompt_hash=self._raw_prompt_hash,
                config_hash=self._config_hash,
                combined_hash=combined_hash,
                created_at=datetime.now().isoformat(),
                version="5.0",
            )
            self._storage_backend.save(self.CACHE_KEY_META, meta.to_dict())
            
            # 2. 保存提示词缓存
            prompt_data = {
                "system_prompt_simple": self.system_prompt_simple,
                "system_prompt_medium": self.system_prompt_medium,
                "system_prompt_complex": self.system_prompt_complex,
                "intent_prompt": self.intent_prompt,
            }
            self._storage_backend.save(self.CACHE_KEY_PROMPTS, prompt_data)
            
            # 3. 保存 AgentSchema 缓存
            if self.agent_schema:
                try:
                    # AgentSchema 是 dataclass，需要转换为 dict
                    schema_dict = self._agent_schema_to_dict(self.agent_schema)
                    self._storage_backend.save(self.CACHE_KEY_SCHEMA, schema_dict)
                except Exception as e:
                    logger.warning(f"⚠️ AgentSchema 序列化失败: {e}")
            
            logger.info(f"💾 缓存已保存到磁盘: {self._cache_dir}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存缓存到磁盘失败: {e}")
            return False
    
    def _agent_schema_to_dict(self, schema) -> Dict[str, Any]:
        """将 AgentSchema 转换为可序列化的字典"""
        from dataclasses import asdict, is_dataclass
        from enum import Enum
        
        def make_serializable(obj):
            """递归处理对象使其可 JSON 序列化"""
            if obj is None:
                return None
            elif isinstance(obj, (str, int, float, bool)):
                return obj
            elif isinstance(obj, Enum):
                return obj.value
            elif isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [make_serializable(item) for item in obj]
            elif is_dataclass(obj):
                try:
                    return make_serializable(asdict(obj))
                except Exception:
                    # asdict 失败时手动处理
                    result = {}
                    for key in obj.__dataclass_fields__.keys():
                        value = getattr(obj, key, None)
                        result[key] = make_serializable(value)
                    return result
            elif hasattr(obj, '__dict__'):
                # 普通对象，跳过不可序列化的属性
                result = {}
                for key, value in obj.__dict__.items():
                    if not key.startswith('_'):  # 跳过私有属性
                        try:
                            serialized = make_serializable(value)
                            result[key] = serialized
                        except Exception:
                            pass  # 跳过无法序列化的属性
                return result
            else:
                # 尝试转换为字符串
                try:
                    return str(obj)
                except Exception:
                    return None
        
        try:
            return make_serializable(schema)
        except Exception as e:
            logger.warning(f"⚠️ Schema 序列化部分失败: {e}")
            # 返回基本信息
            return {
                "name": getattr(schema, 'name', 'Unknown'),
                "model": getattr(schema, 'model', None),
            }
    
    def clear_disk_cache(self) -> bool:
        """
        清除磁盘缓存
        
        Returns:
            是否成功清除
        """
        if not self._storage_backend:
            return False
        
        try:
            self._storage_backend.delete(self.CACHE_KEY_META)
            self._storage_backend.delete(self.CACHE_KEY_PROMPTS)
            self._storage_backend.delete(self.CACHE_KEY_SCHEMA)
            logger.info(f"🧹 已清除磁盘缓存: {self.instance_name}")
            return True
        except Exception as e:
            logger.error(f"❌ 清除磁盘缓存失败: {e}")
            return False
    
    async def _analyze_with_llm(
        self,
        raw_prompt: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        使用 LLM 语义分析提示词
        
        生成：
        - PromptSchema: 提示词结构
        - AgentSchema: Agent 配置（使用高质量 Prompt + few-shot）
        """
        # 1. 解析 PromptSchema
        from core.prompt import parse_prompt
        self.prompt_schema = parse_prompt(raw_prompt, use_llm=True)
        logger.info(f"   PromptSchema: {self.prompt_schema.agent_name} ({len(self.prompt_schema.modules)} 模块)")
        
        # 2. 生成 AgentSchema（使用高质量 Prompt + few-shot）
        await self._generate_agent_schema(raw_prompt, config)
        logger.info(f"   AgentSchema: {self.agent_schema.name if self.agent_schema else 'Default'}")
    
    async def _generate_agent_schema(
        self,
        raw_prompt: str,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        使用高质量 Prompt + few-shot 生成 AgentSchema
        
        核心哲学：规则写在高质量 Prompt 里，不写在代码里
        """
        from core.agent.factory import AgentFactory
        from core.schemas import DEFAULT_AGENT_SCHEMA
        
        try:
            # 调用 LLM 生成 Schema（使用高质量 Prompt + few-shot）
            self.agent_schema = await AgentFactory._generate_schema(raw_prompt)
            
            # 合并实例配置（config.yaml 中的覆盖）
            if config:
                self._merge_config_overrides(config)
                
        except Exception as e:
            logger.warning(f"⚠️ AgentSchema 生成失败: {e}，使用默认配置")
            self.agent_schema = DEFAULT_AGENT_SCHEMA
    
    def _merge_config_overrides(self, config: Dict[str, Any]):
        """合并 config.yaml 中的覆盖配置"""
        if not self.agent_schema:
            return
            
        # 合并 agent 配置
        agent_config = config.get("agent", {})
        if agent_config:
            if "model" in agent_config:
                self.agent_schema.model = agent_config["model"]
            if "max_turns" in agent_config:
                self.agent_schema.max_turns = agent_config["max_turns"]
            if "plan_manager_enabled" in agent_config:
                self.agent_schema.plan_manager.enabled = agent_config["plan_manager_enabled"]
        
        # 合并 LLM 超参数
        llm_config = agent_config.get("llm", {})
        if llm_config and hasattr(self.agent_schema, 'llm_config'):
            for key, value in llm_config.items():
                if hasattr(self.agent_schema.llm_config, key):
                    setattr(self.agent_schema.llm_config, key, value)
    
    async def _generate_all_prompts(self):
        """生成三个版本的系统提示词"""
        from core.prompt import generate_prompt, TaskComplexity
        
        if not self.prompt_schema:
            logger.warning("⚠️ PromptSchema 未加载，跳过提示词生成")
            return
        
        # 更新排除模块（根据 AgentSchema）
        self.prompt_schema.update_exclusions(self.agent_schema)
        
        # 生成三个版本
        self.system_prompt_simple = generate_prompt(
            self.prompt_schema, 
            TaskComplexity.SIMPLE,
            self.agent_schema
        )
        
        self.system_prompt_medium = generate_prompt(
            self.prompt_schema,
            TaskComplexity.MEDIUM,
            self.agent_schema
        )
        
        self.system_prompt_complex = generate_prompt(
            self.prompt_schema,
            TaskComplexity.COMPLEX,
            self.agent_schema
        )
        
        logger.info(f"   系统提示词版本:")
        logger.info(f"     Simple: {len(self.system_prompt_simple)} 字符")
        logger.info(f"     Medium: {len(self.system_prompt_medium)} 字符")
        logger.info(f"     Complex: {len(self.system_prompt_complex)} 字符")
    
    async def _generate_intent_prompt(self):
        """生成意图识别提示词"""
        from core.prompt.intent_prompt_generator import IntentPromptGenerator
        
        if self.prompt_schema:
            # 从 PromptSchema 动态生成（用户配置优先）
            self.intent_prompt = IntentPromptGenerator.generate(self.prompt_schema)
            logger.info(f"   意图识别提示词: {len(self.intent_prompt)} 字符 (动态生成)")
        else:
            # 使用高质量默认
            self.intent_prompt = IntentPromptGenerator.get_default()
            logger.info(f"   意图识别提示词: {len(self.intent_prompt)} 字符 (默认)")
    
    async def _load_fallback(self, raw_prompt: str):
        """加载失败时的 fallback"""
        from core.prompt import PromptSchema
        from core.schemas import DEFAULT_AGENT_SCHEMA
        from prompts.intent_recognition_prompt import get_intent_recognition_prompt
        
        logger.warning("⚠️ 使用 fallback 加载")
        
        # 使用最简单的配置
        self.prompt_schema = PromptSchema(raw_prompt=raw_prompt)
        self.agent_schema = DEFAULT_AGENT_SCHEMA
        
        # 使用原始提示词作为所有版本
        self.system_prompt_simple = raw_prompt
        self.system_prompt_medium = raw_prompt
        self.system_prompt_complex = raw_prompt
        
        # 使用默认意图识别提示词
        self.intent_prompt = get_intent_recognition_prompt()
        
        self.is_loaded = True
    
    def get_system_prompt(self, complexity) -> str:
        """
        获取对应复杂度的系统提示词（直接从缓存取）
        
        Args:
            complexity: TaskComplexity 枚举
            
        Returns:
            对应版本的系统提示词
        """
        from core.prompt import TaskComplexity
        
        if not self.is_loaded:
            logger.warning("⚠️ 缓存未加载，返回空字符串")
            return ""
        
        if complexity == TaskComplexity.SIMPLE:
            return self.system_prompt_simple or ""
        elif complexity == TaskComplexity.MEDIUM:
            return self.system_prompt_medium or ""
        else:
            return self.system_prompt_complex or ""
    
    def get_intent_prompt(self) -> str:
        """
        获取意图识别提示词（用户配置 or 默认）
        
        Returns:
            意图识别提示词
        """
        if self.intent_prompt:
            return self.intent_prompt
        
        # fallback 到默认
        from prompts.intent_recognition_prompt import get_intent_recognition_prompt
        return get_intent_recognition_prompt()
    
    @staticmethod
    def _compute_hash(content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode()).hexdigest()
    
    def get_status(self) -> Dict[str, Any]:
        """获取缓存状态（调试用）"""
        return {
            "instance_name": self.instance_name,
            "is_loaded": self.is_loaded,
            "prompt_schema": self.prompt_schema.agent_name if self.prompt_schema and hasattr(self.prompt_schema, 'agent_name') else None,
            "agent_schema": self.agent_schema.name if self.agent_schema and hasattr(self.agent_schema, 'name') else None,
            "system_prompts": {
                "simple": len(self.system_prompt_simple or ""),
                "medium": len(self.system_prompt_medium or ""),
                "complex": len(self.system_prompt_complex or ""),
            },
            "intent_prompt": len(self.intent_prompt or ""),
            # 🆕 V5.0: 持久化状态
            "persistence": {
                "enabled": self._storage_backend is not None,
                "cache_dir": str(self._cache_dir) if self._cache_dir else None,
                "has_disk_cache": self._storage_backend.exists(self.CACHE_KEY_META) if self._storage_backend else False,
            },
            "metrics": {
                "load_time_ms": self.metrics.load_time_ms,
                "disk_load_time_ms": self.metrics.disk_load_time_ms,
                "llm_analysis_time_ms": self.metrics.llm_analysis_time_ms,
                "cache_hits": self.metrics.cache_hits,
                "cache_misses": self.metrics.cache_misses,
                "disk_hits": self.metrics.disk_hits,
                "disk_misses": self.metrics.disk_misses,
            }
        }


# ============================================================
# 便捷函数
# ============================================================

def get_instance_cache(instance_name: str) -> InstancePromptCache:
    """获取实例缓存（便捷函数）"""
    return InstancePromptCache.get_instance(instance_name)


async def load_instance_cache(
    instance_name: str,
    raw_prompt: str,
    config: Optional[Dict[str, Any]] = None,
    cache_dir: Optional[str] = None,
    force_refresh: bool = False
) -> InstancePromptCache:
    """
    加载实例缓存（便捷函数）
    
    🆕 V5.0: 支持设置缓存目录实现持久化
    
    Args:
        instance_name: 实例名称
        raw_prompt: 原始提示词
        config: 实例配置
        cache_dir: 缓存目录路径（启用持久化）
        force_refresh: 强制刷新
        
    Returns:
        加载完成的 InstancePromptCache
    """
    cache = get_instance_cache(instance_name)
    
    # 🆕 V5.0: 设置缓存目录（启用持久化）
    if cache_dir:
        cache.set_cache_dir(cache_dir)
    
    await cache.load_once(raw_prompt, config, force_refresh)
    return cache
