"""
实例级提示词缓存管理器 - InstancePromptCache

🆕 V5.5: 场景化提示词分解 + prompt_results 可视化输出

设计原则：
1. 实例启动时一次性加载，全局缓存
2. 用空间换时间，避免重复分析
3. 所有提示词版本启动时生成，运行时直接取缓存
4. 🆕 V5.0: 支持持久化到本地文件，避免重复 LLM 分析
5. 🆕 V5.5: 输出到 prompt_results/ 目录供运营查看和编辑

数据流：
┌─────────────────────────────────────────────────────────────┐
│ 启动阶段（优先加载 prompt_results/）                            │
│ 1. 检查 prompt_results/ 是否存在且有效                         │
│ 2. 检测源文件变化（prompt.md / config.yaml）                   │
│ 3. 检测运营手动编辑（保护手动修改的文件）                        │
│ 4. 需要重新生成时：LLM 分解任务 → 写入 prompt_results/          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 运行阶段（每次请求，毫秒级）                                     │
│ 1. 直接从内存缓存获取 intent_prompt                            │
│ 2. 意图识别 → 复杂度                                          │
│ 3. 直接从内存缓存获取对应版本 system_prompt                     │
└─────────────────────────────────────────────────────────────┘

文件结构：
├── .cache/                 # 二进制缓存（JSON）
│   ├── prompt_cache.json
│   ├── agent_schema.json
│   └── cache_meta.json
│
└── prompt_results/         # 🆕 运营可见可编辑
    ├── README.md           # 使用说明
    ├── agent_schema.yaml   # AgentSchema
    ├── intent_prompt.md    # 意图识别提示词
    ├── simple_prompt.md    # 简单任务提示词
    ├── medium_prompt.md    # 中等任务提示词
    ├── complex_prompt.md   # 复杂任务提示词
    └── _metadata.json      # 元数据
"""

# 1. 标准库
import asyncio
import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Protocol

# Type alias for progress callback: async def callback(step: int, message: str) -> None
ProgressCallback = Optional[Callable[[int, str], Coroutine[Any, Any, None]]]

# 2. 第三方库
import aiofiles

# 3. 本地模块
# 注意：为避免循环导入，AgentFactory 延迟导入
from config.llm_config import get_llm_profile
from core.llm import create_llm_service
from core.llm.base import Message
from core.prompt.framework_rules import (
    get_complex_prompt_template,
    get_intent_prompt_template,
    get_medium_prompt_template,
    get_merge_prompts,
    get_simple_prompt_template,
)
from core.prompt.intent_prompt_generator import IntentPromptGenerator
from core.prompt.prompt_layer import PromptParser, PromptSchema, TaskComplexity, generate_prompt
from core.prompt.prompt_results_writer import PromptResults, PromptResultsWriter
from core.schemas import DEFAULT_AGENT_SCHEMA, AgentSchema
from logger import get_logger
from prompts.intent_recognition_prompt import get_intent_recognition_prompt

logger = get_logger("instance_cache")


# ============================================================
# 缓存存储后端抽象（预留云端同步扩展点）
# ============================================================


class CacheStorageBackend(ABC):
    """
    缓存存储后端抽象接口（异步）

    🆕 V5.0: 预留云端同步扩展点
    当前实现：LocalFileBackend
    未来扩展：CloudSyncBackend（S3/OSS/数据库）
    """

    @abstractmethod
    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存缓存数据（异步）"""
        pass

    @abstractmethod
    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """加载缓存数据（异步）"""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """删除缓存（异步）"""
        pass


class LocalFileBackend(CacheStorageBackend):
    """
    本地文件存储后端（异步）

    存储位置：instances/xxx/.cache/
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{key}.json"

    async def save(self, key: str, data: Dict[str, Any]) -> bool:
        """保存到本地 JSON 文件（异步）"""
        try:
            path = self._get_path(key)
            content = json.dumps(data, ensure_ascii=False, indent=2)
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
            logger.debug(f"💾 已保存缓存: {path}")
            return True
        except Exception as e:
            logger.error(f"❌ 保存缓存失败: {e}")
            return False

    async def load(self, key: str) -> Optional[Dict[str, Any]]:
        """从本地 JSON 文件加载（异步）"""
        try:
            path = self._get_path(key)
            if not path.exists():
                return None
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            logger.error(f"❌ 加载缓存失败: {e}")
            return None

    def exists(self, key: str) -> bool:
        """检查本地文件是否存在"""
        return self._get_path(key).exists()

    async def delete(self, key: str) -> bool:
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
        self.agent_schema: Optional[Any] = None  # AgentSchema

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

        # 🆕 V5.5: 实例路径（用于 prompt_results 输出）
        self._instance_path: Optional[Path] = None
        self._prompt_results_writer: Optional[Any] = None  # PromptResultsWriter

        # 🆕 V5.1: 运行时上下文（APIs + framework_prompt）
        # 由 instance_loader 设置，Agent 运行时追加到缓存版本
        self.runtime_context: Dict[str, str] = {}

        # 性能指标
        self.metrics = CacheMetrics()

        logger.debug(f"📦 创建 InstancePromptCache: {instance_name}")

    def set_cache_dir(self, cache_dir: str) -> None:
        """
        设置缓存目录（启用持久化）

        🆕 V5.0: 设置后将使用 LocalFileBackend 进行持久化
        🆕 V5.5: 同时初始化 PromptResultsWriter

        Args:
            cache_dir: 缓存目录路径（如 instances/test_agent/.cache）
        """
        self._cache_dir = Path(cache_dir)
        self._storage_backend = LocalFileBackend(self._cache_dir)

        # 🆕 V5.5: 从 .cache 目录推断实例路径并初始化 PromptResultsWriter
        self._instance_path = self._cache_dir.parent

        self._prompt_results_writer = PromptResultsWriter(self._instance_path)

        logger.debug(f"📁 设置缓存目录: {cache_dir}")
        logger.debug(f"📁 实例路径: {self._instance_path}")

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
        force_refresh: bool = False,
        progress_callback: ProgressCallback = None,
    ) -> bool:
        """
        一次性加载所有提示词版本（幂等）

        🆕 V5.5 加载流程：
        1. 检查是否已加载（幂等）
        2. 🆕 尝试从 prompt_results/ 加载（运营可编辑版本）
        3. 检测源文件变化，决定是否需要重新生成
        4. 🆕 分解 LLM 任务生成场景化提示词
        5. 写入 prompt_results/ 供运营查看

        Args:
            raw_prompt: 运营写的原始系统提示词
            config: 实例配置（来自 config.yaml）
            force_refresh: 强制刷新缓存
            progress_callback: async callback(step, message) for progress reporting

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

            # 保存原始提示词和哈希
            self._raw_prompt = raw_prompt
            self._raw_prompt_hash = prompt_hash
            self._config_hash = config_hash

            # 🆕 V5.5: 优先从 prompt_results/ 加载（运营可编辑版本）
            if not force_refresh and self._prompt_results_writer:
                disk_start = time.time()
                if await self._try_load_from_prompt_results():
                    self.metrics.disk_hits += 1
                    self.metrics.disk_load_time_ms = (time.time() - disk_start) * 1000
                    self.metrics.load_time_ms = (time.time() - start_time) * 1000
                    self.is_loaded = True

                    # 🆕 V7.10: 从磁盘加载后也要应用 config.yaml 的覆盖配置
                    # 确保 thinking_mode 等运行时配置生效
                    if config:
                        self._merge_config_overrides(config)

                    logger.info(f"✅ 从 prompt_results/ 加载: {self.instance_name}")
                    logger.info(f"   加载耗时: {self.metrics.disk_load_time_ms:.0f}ms")
                    return True
                else:
                    self.metrics.disk_misses += 1
                    logger.debug(f"📁 prompt_results/ 未命中或需要更新")

            # 🆕 V5.0: 尝试从 .cache/ 磁盘加载缓存（fallback）
            if not force_refresh and self._storage_backend:
                disk_start = time.time()
                if await self._try_load_from_disk(combined_hash):
                    self.metrics.disk_hits += 1
                    self.metrics.disk_load_time_ms = (time.time() - disk_start) * 1000
                    self.metrics.load_time_ms = (time.time() - start_time) * 1000
                    self.is_loaded = True

                    logger.info(f"✅ 从磁盘缓存加载: {self.instance_name}")
                    logger.info(f"   磁盘加载耗时: {self.metrics.disk_load_time_ms:.0f}ms")
                    return True
                else:
                    self.metrics.disk_misses += 1
                    logger.debug(f"📁 磁盘缓存未命中或已失效")

            # 缓存未命中，执行 LLM 分解任务
            self.metrics.cache_misses += 1
            logger.info(f"🔄 开始 LLM 场景化分解: {self.instance_name}")

            try:
                # 🆕 V5.5: 分解 LLM 任务生成场景化提示词
                llm_start = time.time()
                await self._generate_decomposed_prompts(raw_prompt, config, progress_callback)
                self.metrics.llm_analysis_time_ms = (time.time() - llm_start) * 1000

                self.is_loaded = True
                self.metrics.load_time_ms = (time.time() - start_time) * 1000

                # 🆕 V5.5: 写入 prompt_results/ 供运营查看
                if self._prompt_results_writer:
                    await self._save_to_prompt_results()

                # 🆕 V5.0: 同时写入 .cache/ 磁盘缓存
                if self._storage_backend:
                    await self._save_to_disk(combined_hash)

                logger.info(f"✅ InstancePromptCache 加载完成: {self.instance_name}")
                logger.info(f"   LLM 分解生成: {self.metrics.llm_analysis_time_ms:.0f}ms")
                logger.info(f"   总耗时: {self.metrics.load_time_ms:.0f}ms")

                return True

            except Exception as e:
                logger.error(f"❌ 加载 InstancePromptCache 失败: {e}", exc_info=True)
                # 使用 fallback
                await self._load_fallback(raw_prompt)
                return False

    # ============================================================
    # 🆕 V5.5: prompt_results/ 目录加载和保存
    # ============================================================

    async def _try_load_from_prompt_results(self) -> bool:
        """
        🆕 V5.5: 尝试从 prompt_results/ 加载（异步版本）

        优先使用运营手动编辑的版本

        Returns:
            是否成功加载
        """
        if not self._prompt_results_writer:
            return False

        try:
            # 检查是否需要重新生成（异步调用）
            regen_flags = await self._prompt_results_writer.should_regenerate()

            # 如果所有文件都不需要重新生成，直接加载
            if not any(regen_flags.values()):
                existing = await self._prompt_results_writer.load_existing()
                if existing:
                    self._load_from_prompt_results(existing)
                    logger.debug(f"📂 从 prompt_results/ 加载完成（无需更新）")
                    return True

            # 如果部分文件需要重新生成，先加载现有的（保护手动编辑的）
            if self._prompt_results_writer.is_valid():
                existing = await self._prompt_results_writer.load_existing()
                if existing:
                    # 只加载不需要重新生成的部分
                    self._load_partial_from_prompt_results(existing, regen_flags)
                    logger.debug(f"📂 从 prompt_results/ 部分加载（需要更新部分文件）")
                    # 返回 False 触发重新生成缺失的部分
                    return False

            return False

        except Exception as e:
            logger.warning(f"⚠️ 从 prompt_results/ 加载失败: {e}")
            return False

    def _load_from_prompt_results(self, results) -> None:
        """从 PromptResults 加载到内存"""
        # 加载 AgentSchema
        if results.agent_schema:
            try:
                self.agent_schema = AgentSchema(**results.agent_schema)
            except Exception as e:
                logger.warning(f"⚠️ AgentSchema 加载失败: {e}，使用默认")
                self.agent_schema = DEFAULT_AGENT_SCHEMA

        # 加载场景化提示词
        self.intent_prompt = results.intent_prompt
        self.system_prompt_simple = results.simple_prompt
        self.system_prompt_medium = results.medium_prompt
        self.system_prompt_complex = results.complex_prompt

        # 创建简单的 PromptSchema
        self.prompt_schema = PromptSchema(raw_prompt=self._raw_prompt)

    def _load_partial_from_prompt_results(self, results, regen_flags: Dict[str, bool]) -> None:
        """部分加载（保护手动编辑的文件）"""
        # 加载 AgentSchema（如果不需要重新生成）
        if not regen_flags.get("agent_schema", True) and results.agent_schema:
            try:
                self.agent_schema = AgentSchema(**results.agent_schema)
            except Exception:
                pass

        # 加载不需要重新生成的提示词
        if not regen_flags.get("intent_prompt", True):
            self.intent_prompt = results.intent_prompt
        if not regen_flags.get("simple_prompt", True):
            self.system_prompt_simple = results.simple_prompt
        if not regen_flags.get("medium_prompt", True):
            self.system_prompt_medium = results.medium_prompt
        if not regen_flags.get("complex_prompt", True):
            self.system_prompt_complex = results.complex_prompt

    async def _save_to_prompt_results(self) -> bool:
        """
        🆕 V5.5: 保存到 prompt_results/ 目录

        Returns:
            是否成功保存
        """
        if not self._prompt_results_writer:
            return False

        try:
            # 构建结果
            results = PromptResults(
                agent_schema=(
                    self._agent_schema_to_dict(self.agent_schema) if self.agent_schema else {}
                ),
                intent_prompt=self.intent_prompt or "",
                simple_prompt=self.system_prompt_simple or "",
                medium_prompt=self.system_prompt_medium or "",
                complex_prompt=self.system_prompt_complex or "",
            )

            # 写入
            success = await self._prompt_results_writer.write_all(results)

            if success:
                logger.info(f"📂 已写入 prompt_results/ 目录")

            return success

        except Exception as e:
            logger.error(f"❌ 保存到 prompt_results/ 失败: {e}")
            return False

    # ============================================================
    # 🆕 V5.5: 分解 LLM 任务生成场景化提示词
    # ============================================================

    async def _generate_decomposed_prompts(
        self,
        raw_prompt: str,
        config: Optional[Dict[str, Any]] = None,
        progress_callback: ProgressCallback = None,
    ):
        """
        🆕 V5.5: 分解 LLM 任务生成场景化提示词

        将单次超长任务分解为 5 个独立任务：
        1. 生成 AgentSchema
        2. 生成意图识别提示词
        3. 生成简单任务提示词
        4. 生成中等任务提示词
        5. 生成复杂任务提示词

        每个任务独立执行，避免单次任务过重导致超时
        """
        logger.info("   📋 开始分解 LLM 任务...")

        # 检查哪些需要重新生成
        regen_flags = {
            "agent_schema": True,
            "intent_prompt": True,
            "simple_prompt": True,
            "medium_prompt": True,
            "complex_prompt": True,
        }

        if self._prompt_results_writer:
            regen_flags = await self._prompt_results_writer.should_regenerate()

        # Task 1: 生成 AgentSchema
        if regen_flags.get("agent_schema", True) or not self.agent_schema:
            if progress_callback:
                await progress_callback(2, "分析角色定义...")
            logger.info("   Task 1/5: 生成 AgentSchema...")
            await self._generate_agent_schema(raw_prompt, config)
            logger.info(
                f"   ✅ AgentSchema: {self.agent_schema.name if self.agent_schema else 'Default'}"
            )
        else:
            logger.info("   Task 1/5: AgentSchema（已存在，跳过）")

        # Task 2: 生成意图识别提示词
        if regen_flags.get("intent_prompt", True) or not self.intent_prompt:
            if progress_callback:
                await progress_callback(3, "生成意图识别...")
            logger.info("   Task 2/5: 生成意图识别提示词...")
            await self._generate_intent_prompt_decomposed(raw_prompt)
            logger.info(f"   ✅ 意图识别提示词: {len(self.intent_prompt or '')} 字符")
        else:
            logger.info("   Task 2/5: 意图识别提示词（已存在，跳过）")

        # Task 3: 生成简单任务提示词
        if regen_flags.get("simple_prompt", True) or not self.system_prompt_simple:
            if progress_callback:
                await progress_callback(4, "生成场景提示词(1/3)...")
            logger.info("   Task 3/5: 生成简单任务提示词...")
            await self._generate_simple_prompt_decomposed(raw_prompt)
            logger.info(f"   ✅ 简单任务提示词: {len(self.system_prompt_simple or '')} 字符")
        else:
            logger.info("   Task 3/5: 简单任务提示词（已存在，跳过）")

        # Task 4: 生成中等任务提示词
        if regen_flags.get("medium_prompt", True) or not self.system_prompt_medium:
            if progress_callback:
                await progress_callback(5, "生成场景提示词(2/3)...")
            logger.info("   Task 4/5: 生成中等任务提示词...")
            await self._generate_medium_prompt_decomposed(raw_prompt)
            logger.info(f"   ✅ 中等任务提示词: {len(self.system_prompt_medium or '')} 字符")
        else:
            logger.info("   Task 4/5: 中等任务提示词（已存在，跳过）")

        # Task 5: 生成复杂任务提示词
        if regen_flags.get("complex_prompt", True) or not self.system_prompt_complex:
            if progress_callback:
                await progress_callback(6, "生成场景提示词(3/3)...")
            logger.info("   Task 5/5: 生成复杂任务提示词...")
            await self._generate_complex_prompt_decomposed(raw_prompt)
            logger.info(f"   ✅ 复杂任务提示词: {len(self.system_prompt_complex or '')} 字符")
        else:
            logger.info("   Task 5/5: 复杂任务提示词（已存在，跳过）")

        # 创建 PromptSchema
        self.prompt_schema = PromptSchema(raw_prompt=raw_prompt)

        logger.info("   ✅ 所有分解任务完成")

    async def _generate_intent_prompt_decomposed(self, raw_prompt: str):
        """
        生成意图识别提示词（分解任务）

        🆕 V6.1: 如果 AgentSchema 已生成，注入能力摘要确保意图分类与 Agent 能力一致
        """
        try:
            # 获取 LLM Profile
            try:
                profile = await get_llm_profile("prompt_decomposer")
            except KeyError:
                profile = await get_llm_profile("llm_analyzer")

            llm_service = create_llm_service(**profile)

            # 🆕 V6.1: 获取 AgentSchema 能力摘要（如果已生成）
            schema_summary = self._build_schema_summary()

            # 构建提示词（传入完整 prompt 用于提取意图定义，模板内部会限制长度）
            prompt_template = await get_intent_prompt_template(raw_prompt, schema_summary)

            # 调用 LLM（使用 Message 对象而非字典）
            response = await llm_service.create_message_async(
                messages=[Message(role="user", content=prompt_template)],
                max_tokens=8000,
            )

            self.intent_prompt = response.content.strip()

        except Exception as e:
            logger.warning(f"⚠️ 意图识别提示词生成失败: {e}，使用默认")
            from core.prompt.intent_prompt_generator import IntentPromptGenerator

            self.intent_prompt = IntentPromptGenerator.get_default()

    def _build_schema_summary(self) -> str:
        """
        🆕 V6.1 构建 AgentSchema 能力摘要

        用于注入意图识别提示词，确保 task_type 分类与 Agent 实际能力一致。

        Returns:
            Schema 能力摘要文本（Markdown 格式），如果 Schema 未生成则返回空字符串
        """
        if not self.agent_schema:
            return ""

        try:
            schema = self.agent_schema

            # 提取已启用的工具
            tools = schema.tools if schema.tools else []
            tools_str = ", ".join(tools) if tools else "无"

            # 提取已启用的技能
            skills = []
            if schema.skills:
                for s in schema.skills:
                    if hasattr(s, "name"):
                        skills.append(s.name)
                    elif isinstance(s, dict):
                        skills.append(s.get("name", str(s)))
                    else:
                        skills.append(str(s))
            skills_str = ", ".join(skills) if skills else "无"

            # 规划能力
            plan_enabled = schema.plan_manager.enabled if schema.plan_manager else False
            plan_str = "启用" if plan_enabled else "禁用"

            return f"""
---

## Agent 能力参考

意图分类时确保与 Agent 实际能力匹配：

- **已启用工具**: {tools_str}
- **已启用技能**: {skills_str}
- **规划能力**: {plan_str}

如果用户请求涉及上述未启用的能力，应将 complexity 标记为较高。
"""
        except Exception as e:
            logger.warning(f"⚠️ 构建 Schema 摘要失败: {e}")
            return ""

    async def _generate_simple_prompt_decomposed(self, raw_prompt: str):
        """生成简单任务提示词（分解任务）"""
        try:
            try:
                profile = await get_llm_profile("prompt_decomposer")
            except KeyError:
                profile = await get_llm_profile("llm_analyzer")

            llm_service = create_llm_service(**profile)

            # 构建提示词（传入完整的 raw_prompt）
            prompt_template = await get_simple_prompt_template(raw_prompt)

            response = await llm_service.create_message_async(
                messages=[Message(role="user", content=prompt_template)],
                max_tokens=20000,
            )

            self.system_prompt_simple = response.content.strip()

        except Exception as e:
            logger.warning(f"⚠️ 简单任务提示词生成失败: {e}，使用 fallback")
            # Fallback: 提取核心部分
            self.system_prompt_simple = self._build_fallback_prompt(
                self._extract_core_sections(raw_prompt), "简单查询", max_size=15000
            )

    async def _generate_medium_prompt_decomposed(self, raw_prompt: str):
        """生成中等任务提示词（分解任务）"""
        try:
            try:
                profile = await get_llm_profile("prompt_decomposer")
            except KeyError:
                profile = await get_llm_profile("llm_analyzer")

            llm_service = create_llm_service(**profile)

            prompt_template = await get_medium_prompt_template(raw_prompt)

            response = await llm_service.create_message_async(
                messages=[Message(role="user", content=prompt_template)],
                max_tokens=50000,
            )

            self.system_prompt_medium = response.content.strip()

        except Exception as e:
            logger.warning(f"⚠️ 中等任务提示词生成失败: {e}，使用 fallback")
            self.system_prompt_medium = self._build_fallback_prompt(
                raw_prompt[:40000] if len(raw_prompt) > 40000 else raw_prompt,
                "中等任务",
                max_size=40000,
            )

    async def _generate_complex_prompt_decomposed(self, raw_prompt: str):
        """生成复杂任务提示词（分解任务）"""
        try:
            try:
                profile = await get_llm_profile("prompt_decomposer")
            except KeyError:
                profile = await get_llm_profile("llm_analyzer")

            llm_service = create_llm_service(**profile)

            prompt_template = await get_complex_prompt_template(raw_prompt)

            response = await llm_service.create_message_async(
                messages=[Message(role="user", content=prompt_template)],
                max_tokens=32000,  # 兼容所有模型（Claude/Qwen）
            )

            self.system_prompt_complex = response.content.strip()

        except Exception as e:
            logger.warning(f"⚠️ 复杂任务提示词生成失败: {e}，使用 fallback")
            self.system_prompt_complex = self._build_fallback_prompt(
                raw_prompt[:80000] if len(raw_prompt) > 80000 else raw_prompt,
                "复杂任务",
                max_size=80000,
            )

    # ============================================================
    # 🆕 V5.0: 磁盘持久化方法
    # ============================================================

    async def _try_load_from_disk(self, expected_hash: str) -> bool:
        """
        尝试从磁盘加载缓存（异步）

        Args:
            expected_hash: 期望的内容哈希（用于验证缓存有效性）

        Returns:
            是否成功加载
        """
        if not self._storage_backend:
            return False

        try:
            # 1. 加载并验证缓存元数据
            meta_data = await self._storage_backend.load(self.CACHE_KEY_META)
            if not meta_data:
                logger.debug("📁 缓存元数据不存在")
                return False

            meta = CacheMeta.from_dict(meta_data)

            # 验证哈希是否匹配
            if meta.combined_hash != expected_hash:
                logger.debug(
                    f"📁 缓存哈希不匹配: {meta.combined_hash[:8]}... != {expected_hash[:8]}..."
                )
                return False

            # 验证版本兼容性
            if meta.version != "5.0":
                logger.debug(f"📁 缓存版本不兼容: {meta.version}")
                return False

            # 2. 加载提示词缓存
            prompt_data = await self._storage_backend.load(self.CACHE_KEY_PROMPTS)
            if not prompt_data:
                logger.debug("📁 提示词缓存不存在")
                return False

            self.system_prompt_simple = prompt_data.get("system_prompt_simple")
            self.system_prompt_medium = prompt_data.get("system_prompt_medium")
            self.system_prompt_complex = prompt_data.get("system_prompt_complex")
            self.intent_prompt = prompt_data.get("intent_prompt")

            # 3. 加载 AgentSchema 缓存
            schema_data = await self._storage_backend.load(self.CACHE_KEY_SCHEMA)
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

    async def _save_to_disk(self, combined_hash: str) -> bool:
        """
        保存缓存到磁盘（异步）

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
            await self._storage_backend.save(self.CACHE_KEY_META, meta.to_dict())

            # 2. 保存提示词缓存
            prompt_data = {
                "system_prompt_simple": self.system_prompt_simple,
                "system_prompt_medium": self.system_prompt_medium,
                "system_prompt_complex": self.system_prompt_complex,
                "intent_prompt": self.intent_prompt,
            }
            await self._storage_backend.save(self.CACHE_KEY_PROMPTS, prompt_data)

            # 3. 保存 AgentSchema 缓存
            if self.agent_schema:
                try:
                    # AgentSchema 是 dataclass，需要转换为 dict
                    schema_dict = self._agent_schema_to_dict(self.agent_schema)
                    await self._storage_backend.save(self.CACHE_KEY_SCHEMA, schema_dict)
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
            elif hasattr(obj, "__dict__"):
                # 普通对象，跳过不可序列化的属性
                result = {}
                for key, value in obj.__dict__.items():
                    if not key.startswith("_"):  # 跳过私有属性
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
                "name": getattr(schema, "name", "Unknown"),
                "model": getattr(schema, "model", None),
            }

    async def clear_disk_cache(self) -> bool:
        """
        清除磁盘缓存（异步）

        Returns:
            是否成功清除
        """
        if not self._storage_backend:
            return False

        try:
            await self._storage_backend.delete(self.CACHE_KEY_META)
            await self._storage_backend.delete(self.CACHE_KEY_PROMPTS)
            await self._storage_backend.delete(self.CACHE_KEY_SCHEMA)
            logger.info(f"🧹 已清除磁盘缓存: {self.instance_name}")
            return True
        except Exception as e:
            logger.error(f"❌ 清除磁盘缓存失败: {e}")
            return False

    async def _analyze_with_llm(self, raw_prompt: str, config: Optional[Dict[str, Any]] = None):
        """
        🆕 V5.2: 使用 LLM 语义分析并智能合并框架规则

        流程：
        1. 框架规则 + 运营 prompt → LLM 智能合并 → 最终系统提示词
        2. 分析最终提示词 → PromptSchema
        3. 生成 Agent 配置 → AgentSchema

        架构参考：docs/15-FRAMEWORK_PROMPT_CONTRACT.md
        """
        # 🆕 V5.4: 跳过 LLM 合并步骤（架构修正）
        #
        # 原因分析（基于实际日志）：
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 1. Input: 82k 字符 prompt.md + 5k 框架规则 ≈ 27k tokens
        # 2. Task: LLM 需要"智能合并"（语义融合，非拼接）
        # 3. Output: 生成新的完整系统提示词 ≈ 25k tokens
        # 4. 结果: 每次请求都超时（600秒），重试 3 次，共 2.5 小时失败
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        #
        # 架构问题（违反 15-FRAMEWORK_PROMPT_CONTRACT.md）：
        # - prompt.md 已经是运营精心编写的完整系统提示词
        # - 让 LLM "智能合并" = 让 LLM 重写整个系统提示词
        # - 任务过于复杂，Sonnet 无法在合理时间内完成
        #
        # 正确架构：
        # - 框架规则通过 Schema 和组件体现（已实现）
        # - 运行时动态追加（已实现：prompt_cache.runtime_context）
        # - 不应该在启动时合并

        logger.info("   Step 1: 使用运营提示词（跳过 LLM 合并，直接分析）...")
        merged_prompt = raw_prompt
        self._raw_user_prompt = raw_prompt
        self._merged_prompt = raw_prompt
        logger.info(f"   ✅ 提示词长度: {len(merged_prompt):,} 字符")

        # Step 2: 解析 PromptSchema（使用合并后的提示词）
        logger.info("   Step 2: 解析 PromptSchema...")
        self.prompt_schema = await PromptParser.parse_async(merged_prompt, use_llm=True)
        logger.info(
            f"   PromptSchema: {self.prompt_schema.agent_name} ({len(self.prompt_schema.modules)} 模块)"
        )

        # 2. 生成 AgentSchema（使用高质量 Prompt + few-shot）
        await self._generate_agent_schema(raw_prompt, config)
        logger.info(f"   AgentSchema: {self.agent_schema.name if self.agent_schema else 'Default'}")

    async def _generate_agent_schema(
        self, raw_prompt: str, config: Optional[Dict[str, Any]] = None
    ):
        """
        使用高质量 Prompt + few-shot 生成 AgentSchema

        🆕 V5.0: 应用级重试逻辑

        核心哲学：规则写在高质量 Prompt 里，不写在代码里
        """
        # 🆕 V5.0: 应用级重试配置
        max_retries = 2
        retry_delay = 1.0  # 秒

        for attempt in range(max_retries + 1):
            try:
                # 延迟导入 AgentFactory，避免循环依赖
                from core.agent.factory import AgentFactory

                # 调用 LLM 生成 Schema（使用高质量 Prompt + few-shot）
                self.agent_schema = await AgentFactory._generate_schema(raw_prompt)

                # 合并实例配置（config.yaml 中的覆盖）
                if config:
                    self._merge_config_overrides(config)

                return  # 成功，退出重试循环

            except Exception as e:
                if attempt < max_retries:
                    logger.warning(
                        f"⚠️ AgentSchema 生成失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}"
                    )
                    await asyncio.sleep(retry_delay * (attempt + 1))  # 递增延迟
                else:
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

        # 合并 prompts 配置（必须在 thinking_mode 之前，验证器依赖它）
        prompts_config = config.get("prompts", {})
        logger.debug(
            f"📋 config keys: {list(config.keys())}, prompts_config: {bool(prompts_config)}"
        )
        if prompts_config:
            from core.schemas.validator import PrefaceConfig, PromptsConfig, SimulatedThinkingConfig

            # 构建 PromptsConfig
            preface_cfg = prompts_config.get("preface")
            simulated_thinking_cfg = prompts_config.get("simulated_thinking")

            preface = None
            if preface_cfg:
                preface = PrefaceConfig(
                    enabled=preface_cfg.get("enabled", True),
                    max_tokens=preface_cfg.get("max_tokens", 150),
                    template=preface_cfg.get("template", ""),
                )

            simulated_thinking = None
            if simulated_thinking_cfg:
                simulated_thinking = SimulatedThinkingConfig(
                    guide=simulated_thinking_cfg.get("guide", "")
                )

            self.agent_schema.prompts = PromptsConfig(
                preface=preface, simulated_thinking=simulated_thinking
            )
            logger.info("📝 prompts 配置已应用")

        # 合并 LLM 超参数（thinking_mode 必须在 prompts 之后）
        llm_config = agent_config.get("llm", {})
        if llm_config:
            # 处理 thinking_mode（直接在 AgentSchema 上）
            if "thinking_mode" in llm_config:
                self.agent_schema.thinking_mode = llm_config["thinking_mode"]
                logger.info(f"🧠 thinking_mode 配置已应用: {llm_config['thinking_mode']}")

            # 处理其他 LLM 配置（如果有 llm_config 属性）
            if hasattr(self.agent_schema, "llm_config"):
                for key, value in llm_config.items():
                    if key != "thinking_mode" and hasattr(self.agent_schema.llm_config, key):
                        setattr(self.agent_schema.llm_config, key, value)

    async def _generate_all_prompts(self):
        """
        🆕 V5.2: 生成三个版本的系统提示词

        基于 LLM 智能合并后的提示词，按复杂度裁剪生成三个版本
        """
        if not self.prompt_schema:
            logger.warning("⚠️ PromptSchema 未加载，跳过提示词生成")
            return

        # 🆕 V5.2: 确保 PromptSchema 包含合并后的提示词
        if hasattr(self, "_merged_prompt") and self._merged_prompt:
            self.prompt_schema.raw_prompt = self._merged_prompt
            logger.info(f"   使用 LLM 合并后的提示词作为基础: {len(self._merged_prompt)} 字符")

        # 更新排除模块（根据 AgentSchema）
        self.prompt_schema.update_exclusions(self.agent_schema)

        # 生成三个版本（基于合并后的提示词按复杂度裁剪）
        self.system_prompt_simple = generate_prompt(
            self.prompt_schema, TaskComplexity.SIMPLE, self.agent_schema
        )

        self.system_prompt_medium = generate_prompt(
            self.prompt_schema, TaskComplexity.MEDIUM, self.agent_schema
        )

        self.system_prompt_complex = generate_prompt(
            self.prompt_schema, TaskComplexity.COMPLEX, self.agent_schema
        )

        logger.info(f"   系统提示词版本:")
        logger.info(f"     Simple: {len(self.system_prompt_simple)} 字符")
        logger.info(f"     Medium: {len(self.system_prompt_medium)} 字符")
        logger.info(f"     Complex: {len(self.system_prompt_complex)} 字符")

    async def _generate_intent_prompt(self):
        """生成意图识别提示词"""
        if self.prompt_schema:
            # 从 PromptSchema 动态生成（用户配置优先）
            self.intent_prompt = IntentPromptGenerator.generate(self.prompt_schema)
            logger.info(f"   意图识别提示词: {len(self.intent_prompt)} 字符 (动态生成)")
        else:
            # 使用高质量默认
            self.intent_prompt = IntentPromptGenerator.get_default()
            logger.info(f"   意图识别提示词: {len(self.intent_prompt)} 字符 (默认)")

    async def _load_fallback(self, raw_prompt: str):
        """
        加载失败时的 fallback

        🆕 V5.1: 即使 fallback 也要生成合理大小的提示词版本
        """
        logger.warning("⚠️ 使用 fallback 加载")

        # 使用最简单的配置
        self.prompt_schema = PromptSchema(raw_prompt=raw_prompt)
        self.agent_schema = DEFAULT_AGENT_SCHEMA

        # 🆕 V5.1: 即使 fallback 也要生成精简版本
        # 提取核心内容（角色定义 + 禁令）
        core_sections = self._extract_core_sections(raw_prompt)

        # Simple: 仅核心规则（限制 15k 字符）
        self.system_prompt_simple = self._build_fallback_prompt(
            core_sections, "简单查询", max_size=15000
        )

        # Medium: 核心 + 部分扩展（限制 40k 字符）
        self.system_prompt_medium = self._build_fallback_prompt(
            raw_prompt[:40000] if len(raw_prompt) > 40000 else raw_prompt,
            "中等任务",
            max_size=40000,
        )

        # Complex: 完整版本（限制 80k 字符）
        self.system_prompt_complex = self._build_fallback_prompt(
            raw_prompt[:80000] if len(raw_prompt) > 80000 else raw_prompt,
            "复杂任务",
            max_size=80000,
        )

        logger.info(
            f"   Fallback 版本: Simple={len(self.system_prompt_simple)}, "
            f"Medium={len(self.system_prompt_medium)}, "
            f"Complex={len(self.system_prompt_complex)} 字符"
        )

        # 使用默认意图识别提示词
        self.intent_prompt = get_intent_recognition_prompt()

        self.is_loaded = True

    def _extract_core_sections(self, raw_prompt: str) -> str:
        """
        🆕 V5.1: 从原始提示词中提取核心部分

        提取内容：
        - 角色定义（开头到第一个主要分隔符）
        - 绝对禁令（<absolute_prohibitions> 标签内容）
        - 输出格式基础规则
        """
        import re

        parts = []

        # 1. 提取角色定义（开头部分）
        # 找到第一个主要分隔符的位置
        separators = ["<absolute_prohibitions", "## 绝对禁令", "---\n\n#", "==="]
        end_pos = len(raw_prompt)
        for sep in separators:
            pos = raw_prompt.find(sep)
            if pos > 0 and pos < end_pos:
                end_pos = pos

        role_section = raw_prompt[: min(end_pos, 3000)].strip()
        if role_section:
            parts.append(role_section)

        # 2. 提取绝对禁令
        prohibitions_match = re.search(
            r"<absolute_prohibitions.*?>.*?</absolute_prohibitions>", raw_prompt, re.DOTALL
        )
        if prohibitions_match:
            parts.append(prohibitions_match.group(0)[:3000])  # 限制大小

        # 3. 提取输出格式核心规则
        output_patterns = [
            r"## \d*\.?\s*核心架构.*?(?=^## \d|^# |\Z)",
            r"三段式.*?输出格式.*?(?=\n\n\n|\Z)",
        ]
        for pattern in output_patterns:
            match = re.search(pattern, raw_prompt, re.MULTILINE | re.DOTALL)
            if match:
                parts.append(match.group(0)[:5000])
                break

        return "\n\n---\n\n".join(parts)

    def _build_fallback_prompt(self, content: str, mode: str, max_size: int) -> str:
        """
        🆕 V5.1: 构建 fallback 版本的提示词
        """
        header = f"""# GeneralAgent

---

## 当前任务模式：{mode}

"""

        # 确保不超过大小限制
        available_size = max_size - len(header) - 100  # 预留缓冲
        if len(content) > available_size:
            content = content[:available_size].rsplit("\n", 1)[0]
            content += "\n\n<!-- 内容已精简 -->"

        return header + content

    def get_system_prompt(self, complexity) -> str:
        """
        获取对应复杂度的系统提示词（直接从缓存取）

        Args:
            complexity: TaskComplexity 枚举

        Returns:
            对应版本的系统提示词
        """
        if not self.is_loaded:
            logger.warning("⚠️ 缓存未加载，返回空字符串")
            return ""

        if complexity == TaskComplexity.SIMPLE:
            return self.system_prompt_simple or ""
        elif complexity == TaskComplexity.MEDIUM:
            return self.system_prompt_medium or ""
        else:
            return self.system_prompt_complex or ""

    def get_full_system_prompt(self, complexity) -> str:
        """
        🆕 V5.1: 获取完整的系统提示词（缓存版本 + 运行时上下文）

        运行时动态组装：
        1. 从缓存获取对应复杂度的精简版本
        2. 追加运行时上下文（APIs 描述 + 框架协议）

        Args:
            complexity: TaskComplexity 枚举

        Returns:
            完整的系统提示词（缓存版本 + 运行时上下文）
        """
        # 1. 获取缓存的精简版本
        base_prompt = self.get_system_prompt(complexity)

        if not base_prompt:
            logger.warning(f"⚠️ 缓存版本为空: complexity={complexity}")
            return ""

        # 2. 如果没有运行时上下文，直接返回缓存版本
        if not self.runtime_context:
            return base_prompt

        # 3. 追加运行时上下文
        apis_prompt = self.runtime_context.get("apis_prompt", "")
        framework_prompt = self.runtime_context.get("framework_prompt", "")
        environment_prompt = self.runtime_context.get("environment_prompt", "")  # 🆕 V6.0

        # 组装完整提示词
        parts = [base_prompt]

        # 🆕 V6.0: 环境信息优先注入（让 Agent 了解运行环境）
        if environment_prompt:
            parts.append(f"\n\n---\n\n{environment_prompt}")

        if apis_prompt:
            parts.append(f"\n\n---\n\n{apis_prompt}")

        if framework_prompt:
            parts.append(f"\n\n---\n\n# 框架能力协议\n\n{framework_prompt}")

        full_prompt = "".join(parts)

        runtime_len = len(apis_prompt) + len(framework_prompt) + len(environment_prompt)
        logger.debug(
            f"✅ 组装完整系统提示词: 缓存={len(base_prompt)} + 运行时={runtime_len} = {len(full_prompt)} 字符"
        )

        return full_prompt

    def get_intent_prompt(self) -> str:
        """
        获取意图识别提示词（用户配置 or 默认）

        Returns:
            意图识别提示词
        """
        if self.intent_prompt:
            return self.intent_prompt

        # fallback 到默认
        return get_intent_recognition_prompt()

    def get_cached_system_blocks(
        self, complexity, user_profile: Optional[str] = None, tools_context: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        构建多层缓存的 system blocks（用于 Claude Prompt Caching）

        🆕 前缀缓存优化策略：
        Claude 的缓存是累积式前缀匹配，从开头到断点的整个前缀序列会被缓存。
        多个断点可以实现分级缓存，提高不同场景下的命中率。

        缓存层级（按稳定性从高到低排序）：
        - Layer 1: 框架规则（1h 缓存）- 跨 Agent 共享，命中率最高
        - Layer 2: 实例提示词（1h 缓存）- 同 Agent 共享
        - Layer 3: Skills + 工具（1h 缓存）- 运行期稳定
        - Layer 4: Mem0 用户画像（不缓存）- 每次检索结果不同

        断点策略（Claude 最多支持 4 个断点）：
        - 断点 1: 框架规则后 → 跨 Agent、跨用户共享
        - 断点 2: 实例提示词后 → 同 Agent 不同用户共享
        - 断点 3: Skills + 工具后 → 同 Agent 同用户不同轮次共享
        - 用户画像不缓存 → 动态内容放最后

        Args:
            complexity: TaskComplexity 枚举（SIMPLE/MEDIUM/COMPLEX）
            user_profile: Mem0 用户画像（可选，不缓存）
            tools_context: Skills + 工具定义（可选，1h 缓存）

        Returns:
            List[Dict] - Claude API 的 system blocks 格式（带 _cache_layer 元数据）

        Example:
            system_blocks = cache.get_cached_system_blocks(
                complexity=TaskComplexity.MEDIUM,
                user_profile=mem0_profile,
                tools_context=skills_metadata
            )
            response = await llm.create_message_async(messages, system=system_blocks)
        """
        system_blocks = []

        # Layer 1: 框架规则（最稳定，跨 Agent 共享）
        # 框架升级 → 重启 → 运行期稳定
        # 🔧 断点 1：所有 Agent 共享框架规则
        framework_prompt = self.runtime_context.get("framework_prompt", "")
        if framework_prompt:
            system_blocks.append(
                {
                    "type": "text",
                    "text": f"# 框架能力协议\n\n{framework_prompt}",
                    "_cache_layer": 1,  # 🆕 元数据：标记为第 1 层缓存
                }
            )
            logger.debug(f"📦 Layer 1 (框架规则): {len(framework_prompt)} 字符 [cache_layer=1]")

        # Layer 2: 实例核心提示词（同 Agent 共享）
        # 运营优化 → 重启 → 运行期稳定
        # 🔧 断点 2：同 Agent 的不同用户/会话共享
        instance_prompt = self.get_system_prompt(complexity)
        if instance_prompt:
            system_blocks.append(
                {
                    "type": "text",
                    "text": instance_prompt,
                    "_cache_layer": 2,  # 🆕 元数据：标记为第 2 层缓存
                }
            )
            logger.debug(f"📦 Layer 2 (实例提示词): {len(instance_prompt)} 字符 [cache_layer=2]")

        # Layer 3: APIs + 工具定义（运行期稳定）
        # 工具更新 → 重启 → 运行期稳定
        # 优先使用传入的 tools_context，否则使用 runtime_context 中的 apis_prompt
        tools_text = tools_context or self.runtime_context.get("apis_prompt", "")
        if tools_text:
            system_blocks.append(
                {
                    "type": "text",
                    "text": tools_text,
                    "_cache_layer": 3,  # 🆕 元数据：标记为第 3 层缓存（与 Skills 合并）
                }
            )
            logger.debug(f"📦 Layer 3 (APIs+工具): {len(tools_text)} 字符 [cache_layer=3]")

        # Layer 3.5: Skills Prompt（与工具合并为同一层缓存）
        # 将 <available_skills> XML 注入到提示词，Agent 通过 read 工具读取 SKILL.md
        # 🔧 断点 3：在 Skills 后添加，同 Agent 同用户不同轮次共享
        skills_prompt = self.runtime_context.get("skills_prompt", "")
        if skills_prompt:
            system_blocks.append(
                {"type": "text", "text": skills_prompt, "_cache_layer": 3}  # 🆕 与工具合并为第 3 层
            )
            logger.debug(f"📦 Layer 3.5 (Skills Prompt): {len(skills_prompt)} 字符 [cache_layer=3]")

        # Layer 4: Mem0 用户画像（不缓存）
        # 基于语义检索，每次 query 不同 → 结果不同 → 不能缓存
        # 🔧 动态内容放最后，不影响前缀缓存命中
        if user_profile:
            system_blocks.append(
                {
                    "type": "text",
                    "text": f"# 用户画像\n\n{user_profile}",
                    "_cache_layer": 0,  # 🆕 元数据：0 表示不缓存
                }
            )
            logger.debug(f"📦 Layer 4 (用户画像): {len(user_profile)} 字符 [不缓存]")

        # 统计缓存层
        cached_layers = len([b for b in system_blocks if b.get("_cache_layer", 0) > 0])
        logger.info(
            f"🗂️ 构建多层缓存 system blocks: {len(system_blocks)} 层, "
            f"其中 {cached_layers} 层启用缓存"
        )

        return system_blocks

    def get_cached_intent_blocks(self) -> List[Dict[str, Any]]:
        """
        构建意图识别的 system blocks（用于 Claude Prompt Caching）

        意图识别提示词在运行期只读，启用缓存（5分钟 TTL，Claude 固定）

        Returns:
            List[Dict] - Claude API 的 system blocks 格式
        """
        intent_prompt = self.get_intent_prompt()

        if not intent_prompt:
            return []

        # 🔧 不在这里添加 cache_control，由 claude.py 统一处理
        system_blocks = [{"type": "text", "text": intent_prompt}]

        logger.debug(f"🗂️ 构建意图识别 system blocks: {len(intent_prompt)} 字符")

        return system_blocks

    @staticmethod
    def _compute_hash(content: str) -> str:
        """计算内容哈希"""
        return hashlib.md5(content.encode()).hexdigest()

    def get_status(self) -> Dict[str, Any]:
        """获取缓存状态（调试用）"""
        return {
            "instance_name": self.instance_name,
            "is_loaded": self.is_loaded,
            "prompt_schema": (
                self.prompt_schema.agent_name
                if self.prompt_schema and hasattr(self.prompt_schema, "agent_name")
                else None
            ),
            "agent_schema": (
                self.agent_schema.name
                if self.agent_schema and hasattr(self.agent_schema, "name")
                else None
            ),
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
                "has_disk_cache": (
                    self._storage_backend.exists(self.CACHE_KEY_META)
                    if self._storage_backend
                    else False
                ),
            },
            "metrics": {
                "load_time_ms": self.metrics.load_time_ms,
                "disk_load_time_ms": self.metrics.disk_load_time_ms,
                "llm_analysis_time_ms": self.metrics.llm_analysis_time_ms,
                "cache_hits": self.metrics.cache_hits,
                "cache_misses": self.metrics.cache_misses,
                "disk_hits": self.metrics.disk_hits,
                "disk_misses": self.metrics.disk_misses,
            },
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
    force_refresh: bool = False,
    progress_callback: ProgressCallback = None,
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
        progress_callback: async callback(step, message) for progress reporting

    Returns:
        加载完成的 InstancePromptCache
    """
    cache = get_instance_cache(instance_name)

    # 🆕 V5.0: 设置缓存目录（启用持久化）
    if cache_dir:
        cache.set_cache_dir(cache_dir)

    await cache.load_once(raw_prompt, config, force_refresh, progress_callback)
    return cache
