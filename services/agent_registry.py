"""
Agent 注册服务 - Agent Registry Service

🆕 V9.5 单实例部署模式：
    每个 Agent 实例是独立的部署单元，启动时只加载指定实例。

职责：
1. 启动时加载指定的 Agent 实例（preload_instance）
2. 提供 get_agent(agent_id) 获取 Agent 实例（原型浅拷贝）
3. 管理 Agent 生命周期

设计原则：
- 单实例部署：每个进程只加载一个 Agent 实例
- 原型复用：clone_for_session() 浅拷贝，共享重量级组件
- 独立部署：实例之间完全解耦，适合容器化部署

使用方式：
    python main.py --instance=dazee_ppt
    AGENT_INSTANCE=dazee_ppt python main.py
"""

import asyncio
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
import yaml

from core.agent import AgentFactory
from core.events import create_event_manager, get_memory_storage
from core.prompt import load_instance_cache
from core.tool import InstanceRegistry, create_tool_loader, get_capability_registry
from logger import get_logger
from prompts.universal_agent_prompt import get_universal_agent_prompt
from utils.instance_loader import (
    _build_apis_prompt_section,
    _prepare_apis,
    get_instances_dir,
    list_instances,
    load_instance_config,
    load_instance_env_from_config,
    load_instance_prompt,
)

logger = get_logger(__name__)


@dataclass
class AgentConfig:
    """
    Agent 配置（预加载的数据，用于创建 Agent 实例）

    包含创建 Agent 所需的所有配置，但不包含 Agent 实例本身
    每次请求时使用这些配置创建新的 Agent 实例
    """

    name: str  # 实例名称（即 instances/ 下的目录名）
    description: str = ""
    version: str = "1.0.0"

    # 预加载的配置（来自 instance_loader）
    instance_config: Any = None  # InstanceConfig
    prompt_cache: Any = None  # InstancePromptCache
    full_prompt: str = ""  # 合并后的完整提示词

    # 元数据
    loaded_at: datetime = field(default_factory=datetime.now)
    load_time_ms: float = 0.0


class AgentNotFoundError(Exception):
    """Agent 不存在异常"""

    pass


class AgentRegistry:
    """
    Agent 注册表（单例）

    🆕 V9.5 单实例部署模式：
        每个 Agent 实例是独立的部署单元，启动时只加载指定实例。

    使用方法：
        registry = get_agent_registry()

        # 启动时加载指定实例（推荐）
        await registry.preload_instance("dazee_ppt")

        # 获取 Agent 实例（从原型浅拷贝）
        agent = await registry.get_agent("dazee_ppt", event_manager, ...)

        # 获取当前实例信息
        agents = registry.list_agents()
    """

    def __init__(self) -> None:
        # Agent 配置缓存（name -> AgentConfig）
        self._configs: Dict[str, AgentConfig] = {}

        # Agent 原型缓存（预创建的 Agent 实例，运行时复用）
        # 原型包含：LLM Service、工具注册表等重量级组件
        # 运行时通过 clone_for_session() 浅克隆并重置会话状态
        self._agent_prototypes: Dict[str, Any] = {}  # name -> Agent

        # 共享组件（跨 Agent 复用）
        self._shared_event_manager = None  # 共享的事件管理器（原型创建时使用）

        # 加载状态
        self._loaded = False
        self._loading = False
        self._load_lock = asyncio.Lock()

    # ==================== 单实例加载 ====================

    async def preload_instance(
        self,
        instance_name: str,
        force_refresh: bool = False,
        progress_callback=None,
    ) -> bool:
        """
        🆕 V9.5: 单实例加载模式（推荐的生产部署方式）

        每个实例是独立的部署单元，启动时只加载指定的实例。

        优势：
        - 启动更快：只加载一个实例
        - 隔离性好：实例之间完全解耦
        - 容器友好：适合 K8s 单 Pod 部署
        - 错误隔离：一个实例配置错误不影响其他实例

        Args:
            instance_name: 实例名称（instances/ 目录下的文件夹名）
            force_refresh: 是否强制刷新缓存
            progress_callback: async callback(step, message) for progress reporting

        Returns:
            是否加载成功

        Raises:
            FileNotFoundError: 实例目录不存在

        使用方式：
            # 方式 1：命令行参数
            python main.py --instance=dazee_ppt

            # 方式 2：环境变量
            AGENT_INSTANCE=dazee_ppt python main.py

            # 方式 3：Docker
            docker run -e AGENT_INSTANCE=dazee_ppt zenflux-agent
        """
        async with self._load_lock:
            start_time = datetime.now()

            # 验证实例是否存在
            instances_dir = get_instances_dir()
            instance_path = instances_dir / instance_name

            if not instance_path.exists():
                available = list_instances()
                raise FileNotFoundError(
                    f"实例 '{instance_name}' 不存在。\n"
                    f"可用实例: {available}\n"
                    f"实例目录: {instances_dir}"
                )

            logger.info(f"🚀 单实例模式: 加载 '{instance_name}'...")

            try:
                # 1. 加载实例配置
                await self._load_single_agent(
                    instance_name,
                    force_refresh=force_refresh,
                    progress_callback=progress_callback,
                )

                # 2. 创建 Agent 原型
                if self._shared_event_manager is None:
                    storage = get_memory_storage()
                    self._shared_event_manager = create_event_manager(storage)

                agent_config = self._configs[instance_name]
                prototype = await self._create_agent_prototype(
                    agent_config, self._shared_event_manager
                )

                if prototype:
                    self._agent_prototypes[instance_name] = prototype

                    total_time_ms = (datetime.now() - start_time).total_seconds() * 1000
                    self._loaded = True

                    logger.info(
                        f"✅ 单实例加载完成: {instance_name} "
                        f"(配置 {agent_config.load_time_ms:.0f}ms + 原型 {total_time_ms - agent_config.load_time_ms:.0f}ms = 总计 {total_time_ms:.0f}ms)"
                    )
                    return True
                else:
                    logger.warning(f"⚠️ 实例 '{instance_name}' 原型创建失败")
                    return False

            except Exception as e:
                logger.error(f"❌ 单实例加载失败: {instance_name} - {str(e)}", exc_info=True)
                raise

    async def preload_all(self, force_refresh: bool = False) -> int:
        """
        加载所有 Agent 实例配置

        遍历 instances/ 目录下的所有实例（排除 _template 等特殊目录），
        依次调用 preload_instance() 加载每个实例。

        对于没有缓存 prompt_results 的实例（需要跑 LLM 生成），
        推迟到后台异步加载，避免阻塞服务启动。

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            成功加载的实例数量（仅计算同步加载的）
        """
        instances = list_instances()
        loaded_count = 0
        deferred: list[str] = []

        for instance_name in instances:
            try:
                # Check if prompt_results are cached (fast path vs slow LLM path)
                if not force_refresh and self._needs_llm_generation(instance_name):
                    deferred.append(instance_name)
                    logger.info(
                        f"⏳ 实例 '{instance_name}' 需要 LLM 生成 prompt_results，"
                        f"推迟到后台加载"
                    )
                    continue

                success = await self.preload_instance(instance_name, force_refresh=force_refresh)
                if success:
                    loaded_count += 1
            except Exception as e:
                logger.warning(f"⚠️ 加载实例 '{instance_name}' 失败: {e}")
                continue

        self._loaded = loaded_count > 0

        # Launch deferred instances in background (non-blocking)
        if deferred:
            logger.info(f"🔄 {len(deferred)} 个实例将在后台异步加载: {deferred}")
            asyncio.create_task(self._deferred_load(deferred, force_refresh))

        return loaded_count

    def _needs_llm_generation(self, instance_name: str) -> bool:
        """
        Check if an instance needs slow LLM generation (no cached prompt_results).

        Quick synchronous check — only inspects the file system.
        """
        instance_path = get_instances_dir() / instance_name
        prompt_results_dir = instance_path / "prompt_results"

        if not prompt_results_dir.exists():
            return True

        # Check that at least the key files exist
        required_files = [
            "agent_schema.yaml",
            "intent_prompt.md",
            "medium_prompt.md",
            "complex_prompt.md",
        ]
        for fname in required_files:
            if not (prompt_results_dir / fname).exists():
                return True

        return False

    async def _deferred_load(self, instance_names: list[str], force_refresh: bool):
        """
        Load deferred instances in background after the server is already accepting
        requests. This prevents slow LLM generation from blocking startup.
        """
        for instance_name in instance_names:
            try:
                logger.info(f"🔄 后台加载实例: {instance_name}")
                success = await self.preload_instance(
                    instance_name, force_refresh=force_refresh
                )
                if success:
                    logger.info(f"✅ 后台加载完成: {instance_name}")
                else:
                    logger.warning(f"⚠️ 后台加载失败: {instance_name}")
            except Exception as e:
                logger.warning(f"⚠️ 后台加载实例 '{instance_name}' 失败: {e}")
                continue

    def get_current_instance(self) -> Optional[str]:
        """
        获取当前默认实例名称。

        优先级：
        1. AGENT_INSTANCE 环境变量（已在 main.py 中自动设置）
        2. 单实例模式下直接取唯一加载的实例

        Returns:
            当前实例名称，或 None
        """
        env_instance = os.environ.get("AGENT_INSTANCE")
        if env_instance and env_instance in self._configs:
            return env_instance
        if len(self._configs) == 1:
            return list(self._configs.keys())[0]
        return None

    # ==================== 获取 Agent ====================

    async def get_agent(self, agent_id: str, event_manager=None, conversation_service=None):
        """
        获取 Agent 实例（按需加载 + 原型复用）

        优化流程：
        1. 如果实例未加载，尝试按需加载（preload_instance）
        2. 从 _agent_prototypes 获取原型
        3. 调用 clone_for_session() 浅克隆并重置会话状态

        Args:
            agent_id: Agent ID（instances/ 目录名）
            event_manager: 事件管理器
            conversation_service: 会话服务

        Returns:
            就绪的 Agent 实例

        Raises:
            AgentNotFoundError: agent_id 在 instances/ 目录中不存在
        """
        # 🆕 V9.5: 按需加载 - 如果实例未加载，尝试加载它
        if agent_id not in self._configs:
            logger.info(f"📦 Agent '{agent_id}' 未加载，尝试按需加载...")
            try:
                await self.preload_instance(agent_id)
            except FileNotFoundError:
                available = list_instances()
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在。可用实例: {available}")

        config = self._configs[agent_id]

        # 切换 AGENT_INSTANCE 环境变量，确保下游存储组件
        # （Memory/Store/DB/Playbook）使用正确的实例隔离路径
        os.environ["AGENT_INSTANCE"] = agent_id

        # 如果未提供 event_manager，创建一个
        if event_manager is None:
            storage = get_memory_storage()
            event_manager = create_event_manager(storage)

        # 🆕 V7.1: 优先从原型复用
        if agent_id in self._agent_prototypes:
            prototype = self._agent_prototypes[agent_id]

            # 浅克隆并重置会话状态
            agent = prototype.clone_for_session(
                event_manager=event_manager, conversation_service=conversation_service
            )

            logger.debug(f"🚀 Agent '{agent_id}' 从原型克隆完成（快速路径）")
            return agent

        # 🔄 Fallback: 按需创建（首次或原型不存在）
        logger.info(f"⚠️ Agent '{agent_id}' 原型不存在，按需创建")

        # 准备 apis_config（用于 api_calling 自动注入认证和请求体模板）
        apis_config = None
        if config.instance_config and config.instance_config.apis:
            apis_config = [
                {
                    "name": api.name,
                    "base_url": api.base_url,
                    "headers": api.headers or {},
                    "description": api.description,
                    # 🔐 认证配置（用于 api_calling 动态注入）
                    "auth": (
                        {
                            "type": api.auth_type,
                            "header": api.auth_header,
                            "env": api.auth_env,
                        }
                        if api.auth_env
                        else None
                    ),
                    # 请求体配置（用于 api_calling 自动合成请求）
                    "request_body": api.request_body,
                    "default_method": api.default_method,
                    "default_mode": api.default_mode,
                    "poll_config": api.poll_config,
                }
                for api in config.instance_config.apis
            ]
            logger.debug(f"   📡 APIs: {[a['name'] for a in apis_config]}")

        # 在创建 Agent 前，用 instance_config.model 覆盖 schema.model
        instance_config = config.instance_config
        if (
            config.prompt_cache
            and config.prompt_cache.is_loaded
            and config.prompt_cache.agent_schema
        ):
            schema = config.prompt_cache.agent_schema
            if instance_config and instance_config.model and schema.model != instance_config.model:
                logger.info(
                    f"   model 覆盖: {schema.model or '(空)'} → {instance_config.model}"
                )
                schema.model = instance_config.model

            agent = await AgentFactory.from_schema(
                schema=schema,
                system_prompt=config.full_prompt,
                event_manager=event_manager,
                conversation_service=conversation_service,
                prompt_cache=config.prompt_cache,
                apis_config=apis_config,
            )
        else:
            # Fallback: 使用旧方式
            logger.warning(f"⚠️ Agent {agent_id} 的 PromptCache 未加载，使用 from_prompt")
            agent = await AgentFactory.from_prompt(
                system_prompt=config.full_prompt,
                event_manager=event_manager,
                conversation_service=conversation_service,
                use_default_if_failed=True,
            )
            # Fallback 模式也需要设置 apis_config
            if apis_config:
                agent.apis_config = apis_config

        # 设置实例级工具注册表
        await self._setup_instance_tools(agent, config)

        logger.debug(f"🤖 创建 Agent 实例: {agent_id}")

        return agent

    async def _create_agent_prototype(self, config: AgentConfig, event_manager):
        """
        🆕 V7.1: 创建 Agent 原型（部署态预创建）

        创建 Agent 原型（含 LLM、工具注册表）

        运行时通过 clone_for_session() 复用这些组件，仅重置会话状态

        Args:
            config: AgentConfig
            event_manager: 共享的事件管理器（用于原型初始化）

        Returns:
            Agent 原型实例
        """
        # 准备 apis_config（用于 api_calling 自动注入认证和请求体模板）
        apis_config = None
        if config.instance_config and config.instance_config.apis:
            apis_config = [
                {
                    "name": api.name,
                    "base_url": api.base_url,
                    "headers": api.headers or {},
                    "description": api.description,
                    # 🔐 认证配置（用于 api_calling 动态注入）
                    "auth": (
                        {
                            "type": api.auth_type,
                            "header": api.auth_header,
                            "env": api.auth_env,
                        }
                        if api.auth_env
                        else None
                    ),
                    # 请求体配置（用于 api_calling 自动合成请求）
                    "request_body": api.request_body,
                    "default_method": api.default_method,
                    "default_mode": api.default_mode,
                    "poll_config": api.poll_config,
                }
                for api in config.instance_config.apis
            ]

        # 使用缓存的 AgentSchema 创建 Agent（自动选择单/多智能体）
        if not (
            config.prompt_cache
            and config.prompt_cache.is_loaded
            and config.prompt_cache.agent_schema
        ):
            logger.warning(f"⚠️ Agent {config.name} 的 PromptCache 未加载，跳过原型创建")
            return None

        # 在创建 Agent 前，用 instance_config.model 覆盖 schema.model
        # agent_schema.yaml 中的 model 是生成时的默认值，运行时以 instance_config 为准
        # 这样 AgentFactory 创建 LLM service 时就能直接用正确的 provider/model
        instance_config = config.instance_config
        schema = config.prompt_cache.agent_schema
        if instance_config and instance_config.model:
            if schema.model != instance_config.model:
                logger.info(
                    f"   model 覆盖: {schema.model or '(空)'} → {instance_config.model}"
                )
                schema.model = instance_config.model

        # AgentFactory.from_schema() 创建 RVR-B Agent
        agent = await AgentFactory.from_schema(
            schema=schema,
            system_prompt=config.full_prompt,
            event_manager=event_manager,
            conversation_service=None,  # 原型不绑定会话服务
            prompt_cache=config.prompt_cache,
            apis_config=apis_config,
        )

        # 设置实例级工具
        if hasattr(agent, "_setup_instance_tools"):
            await self._setup_instance_tools(agent, config)

        # V11: 状态一致性（快照/回滚）
        try:
            from core.state import (
                ConsistencyCheckConfig,
                RollbackConfig,
                SnapshotConfig,
                StateConsistencyConfig,
                StateConsistencyManager,
            )

            sc_raw = (
                instance_config.state_consistency
                if instance_config and isinstance(
                    getattr(instance_config, "state_consistency", None), dict
                )
                else {}
            )
            if sc_raw and sc_raw.get("enabled", False):
                snap_raw = sc_raw.get("snapshot") if isinstance(sc_raw.get("snapshot"), dict) else {}
                rb_raw = sc_raw.get("rollback") if isinstance(sc_raw.get("rollback"), dict) else {}

                sc_config = StateConsistencyConfig(
                    enabled=True,
                    snapshot=SnapshotConfig(
                        storage_path=snap_raw.get("storage_path", ""),
                        retention_hours=int(snap_raw.get("retention_hours", 24)),
                        max_size_mb=int(snap_raw.get("max_size_mb", 500)),
                        capture_cwd=bool(snap_raw.get("capture_cwd", True)),
                        capture_files=bool(snap_raw.get("capture_files", True)),
                        capture_clipboard=bool(snap_raw.get("capture_clipboard", False)),
                    ),
                    rollback=RollbackConfig(
                        auto_rollback_on_consecutive_failures=int(
                            rb_raw.get("auto_rollback_on_consecutive_failures", 3)
                        ),
                        auto_rollback_on_critical_error=bool(
                            rb_raw.get("auto_rollback_on_critical_error", True)
                        ),
                        rollback_timeout_seconds=int(rb_raw.get("rollback_timeout_seconds", 60)),
                    ),
                )
                agent._state_consistency_manager = StateConsistencyManager(config=sc_config)
                agent._state_consistency_enabled = True
                logger.info(
                    f"   状态一致性: 已启用（快照路径={sc_config.snapshot.storage_path or '实例隔离'}, "
                    f"自动回滚={sc_config.rollback.auto_rollback_on_critical_error}）"
                )
            else:
                agent._state_consistency_manager = None
                agent._state_consistency_enabled = False
        except Exception as e:
            logger.warning(f"状态一致性初始化失败（不阻断启动）: {e}", exc_info=True)
            agent._state_consistency_manager = None
            agent._state_consistency_enabled = False

        # V12.1: 注入 SkillsLoader + SkillGroupRegistry 到 prompt_cache.runtime_context
        # 供 ToolSystemRoleProvider 在运行时按 intent 动态生成 skills_prompt
        # Reuse loader from instance_loader if already loaded (avoids duplicate scan)
        if instance_config and instance_config.skills_first_config:
            try:
                from core.skill.group_registry import SkillGroupRegistry

                skills_loader = getattr(agent, "_skills_loader", None)
                if skills_loader is None:
                    from core.skill import create_skills_loader

                    skills_loader = create_skills_loader(
                        skills_config=instance_config.skills_first_config,
                        instance_skills_dir=get_instances_dir() / config.name / "skills",
                        instance_name=config.name,
                    )
                    await skills_loader.load()

                skill_groups_cfg = (instance_config.raw_config or {}).get("skill_groups", {})
                group_registry = SkillGroupRegistry(skill_groups_cfg)

                agent._skills_loader = skills_loader

                if config.prompt_cache and hasattr(config.prompt_cache, "runtime_context"):
                    if config.prompt_cache.runtime_context is None:
                        config.prompt_cache.runtime_context = {}
                    config.prompt_cache.runtime_context["_skills_loader"] = skills_loader
                    config.prompt_cache.runtime_context["_skill_group_registry"] = group_registry

                    logger.info(f"   SkillGroupRegistry 已注入: {group_registry}")
            except Exception as e:
                logger.warning(f"Skills 注入失败（不阻断启动）: {e}", exc_info=True)

        # 标记为原型（用于 clone_for_session 判断）
        agent._is_prototype = True

        agent_type = "Agent"
        logger.debug(f"   原型类型: {agent_type}")

        return agent

    async def _setup_instance_tools(self, agent, config: AgentConfig):
        """
        设置实例级工具（Skills 等）

        Args:
            agent: Agent 实例
            config: AgentConfig
        """
        instance_config = config.instance_config
        if not instance_config:
            return

        global_registry = get_capability_registry()

        # 使用 ToolLoader 统一加载工具
        tool_loader = create_tool_loader(global_registry)

        # 加载所有工具（通用工具、Claude Skills）（异步）
        load_result = await tool_loader.load_tools(
            enabled_capabilities=instance_config.enabled_capabilities,
            skills=instance_config.skills,
        )

        # 创建过滤后的注册表
        filtered_registry = tool_loader.create_filtered_registry(
            instance_config.enabled_capabilities
        )

        # 🔧 V7.7 修复：更新 agent.capability_registry 为过滤后的版本
        # 确保 _register_tools_to_llm 使用正确的工具列表
        agent.capability_registry = filtered_registry

        # 🔧 V7.7: 同时更新 tool_executor.registry（确保工具执行使用正确的注册表）
        if hasattr(agent, "tool_executor") and agent.tool_executor:
            agent.tool_executor.registry = filtered_registry
            # 重新加载工具实例
            agent.tool_executor._load_tools()
            logger.debug(f"   🔧 已更新 tool_executor 注册表并重新加载工具")

        # 🔧 V7.7: 重新注册工具到 LLM（使用过滤后的注册表）
        if hasattr(agent, "_register_tools_to_llm"):
            agent._register_tools_to_llm()
            logger.debug(f"   🔧 已重新注册工具到 LLM（过滤后）")

        # 使用过滤后的 registry 创建实例级注册表
        instance_registry = InstanceRegistry(global_registry=filtered_registry)
        agent._instance_registry = instance_registry


    # ==================== 查询方法 ====================

    def list_agents(self) -> List[Dict[str, Any]]:
        """
        列出所有可用的 Agent

        Returns:
            Agent 信息列表
        """
        return [
            {
                "agent_id": config.name,
                "name": (
                    config.instance_config.name
                    if config.instance_config
                    else config.name
                ),
                "description": config.description,
                "version": config.version,
                "loaded_at": config.loaded_at.isoformat(),
                "load_time_ms": config.load_time_ms,
            }
            for config in self._configs.values()
        ]

    def has_agent(self, agent_id: str) -> bool:
        """检查 Agent 是否存在"""
        return agent_id in self._configs

    def get_agent_config(self, agent_id: str) -> Optional[AgentConfig]:
        """获取 Agent 配置（不创建实例）"""
        return self._configs.get(agent_id)

    @property
    def is_loaded(self) -> bool:
        """是否已加载"""
        return self._loaded

    @property
    def agent_count(self) -> int:
        """已加载的 Agent 数量"""
        return len(self._configs)

    def get_router(self, agent_id: str):
        """
        获取路由器（统一走 AgentFactory.create_route）
        """
        if agent_id not in self._configs:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")

        config = self._configs[agent_id]
        return AgentFactory.create_route(prompt_cache=config.prompt_cache)

    async def _load_single_agent(
        self,
        agent_id: str,
        force_refresh: bool = False,
        progress_callback=None,
    ):
        """
        加载单个 Agent 配置

        Args:
            agent_id: Agent ID
            force_refresh: 是否强制刷新缓存
            progress_callback: async callback(step, message) for progress reporting
        """
        instance_start = datetime.now()

        # 1. 加载实例环境变量（从 config.yaml 的 env_vars 段）
        load_instance_env_from_config(agent_id)

        # 2. 加载实例配置
        config = await load_instance_config(agent_id)

        # 2.0.1 注册自定义数据目录（若 config.yaml 配置了 storage.data_dir）
        storage_cfg = (config.raw_config or {}).get("storage", {})
        custom_data_dir = storage_cfg.get("data_dir") if isinstance(storage_cfg, dict) else None
        if custom_data_dir:
            from utils.app_paths import register_instance_data_dir
            register_instance_data_dir(agent_id, custom_data_dir)
            logger.info(f"   自定义存储路径: {custom_data_dir}")

        # 2.1 注入实例 LLM Profiles（必须在 InstancePromptCache 之前）
        from config.llm_config.loader import set_instance_profiles

        llm_profiles = (config.raw_config or {}).get("llm_profiles", {})
        if llm_profiles:
            set_instance_profiles(llm_profiles)

        # 3. 加载实例提示词
        instance_prompt = await load_instance_prompt(agent_id)

        # 4. 加载 InstancePromptCache
        instance_path = get_instances_dir() / agent_id
        cache_dir = instance_path / ".cache"

        prompt_cache = await load_instance_cache(
            instance_name=agent_id,
            raw_prompt=instance_prompt,
            config=config.raw_config,
            cache_dir=str(cache_dir),
            force_refresh=force_refresh,
            progress_callback=progress_callback,
        )

        # 5. 准备 APIs 运行时参数
        if config.apis:
            config.apis = _prepare_apis(config.apis)

        # 6. 合并完整提示词
        framework_prompt = await get_universal_agent_prompt()
        apis_prompt = _build_apis_prompt_section(config.apis)

        full_prompt = f"""# 实例配置

{instance_prompt}

---

{apis_prompt}

---

# 框架能力协议

{framework_prompt}
"""

        # 7. 填充 runtime_context（供运行时 Injectors 使用）
        if hasattr(prompt_cache, "runtime_context"):
            if prompt_cache.runtime_context is None:
                prompt_cache.runtime_context = {}
            prompt_cache.runtime_context["apis_prompt"] = apis_prompt
            prompt_cache.runtime_context["framework_prompt"] = framework_prompt

            # 环境检测（OS、已安装软件）
            try:
                from core.prompt.runtime_context_builder import (
                    detect_and_build_environment_context_async,
                )

                env_prompt = await detect_and_build_environment_context_async()
                if env_prompt:
                    prompt_cache.runtime_context["environment_prompt"] = env_prompt
            except Exception as e:
                logger.warning(f"环境检测失败（不阻断启动）: {e}")

            logger.info(
                f"   runtime_context 已填充: apis={len(apis_prompt)} 字符, "
                f"framework={len(framework_prompt)} 字符, "
                f"environment={'已注入' if prompt_cache.runtime_context.get('environment_prompt') else '未注入'}"
            )

        # 8. 创建/更新 AgentConfig
        load_time_ms = (datetime.now() - instance_start).total_seconds() * 1000

        agent_config = AgentConfig(
            name=agent_id,
            description=config.description,
            version=config.version,
            instance_config=config,
            prompt_cache=prompt_cache,
            full_prompt=full_prompt,
            load_time_ms=load_time_ms,
        )

        self._configs[agent_id] = agent_config

        logger.info(f"✅ Agent '{agent_id}' 加载完成 (耗时 {load_time_ms:.0f}ms)")

    async def _try_on_demand_load(self, agent_id: str) -> bool:
        """
        Try to on-demand load an agent that exists on disk but isn't in _configs.

        Returns:
            True if loaded successfully, False otherwise.
        """
        instances_dir = get_instances_dir()
        instance_path = instances_dir / agent_id
        if instance_path.exists() and (instance_path / "prompt.md").exists():
            try:
                logger.info(f"📦 Agent '{agent_id}' 按需加载中...")
                await self.preload_instance(agent_id)
                return agent_id in self._configs
            except Exception as e:
                logger.warning(f"⚠️ Agent '{agent_id}' 按需加载失败: {e}")
        return False

    def get_agent_detail(self, agent_id: str) -> Dict[str, Any]:
        """
        获取 Agent 详细信息

        Args:
            agent_id: Agent ID

        Returns:
            Agent 详细信息
        """
        if agent_id not in self._configs:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")

        config = self._configs[agent_id]
        instance_config = config.instance_config

        # 提取详细信息
        # config.name 是 agent_id（目录名），显示名称从 instance_config.name 获取
        display_name = instance_config.name if instance_config else config.name
        detail = {
            "agent_id": config.name,
            "name": display_name,
            "description": config.description,
            "version": config.version,
            "is_active": True,
            "loaded_at": config.loaded_at.isoformat(),
            "load_time_ms": config.load_time_ms,
        }

        if instance_config:
            # 转换 enabled_capabilities 为布尔值格式（前端友好）
            enabled_caps = {}
            if instance_config.enabled_capabilities:
                for k, v in instance_config.enabled_capabilities.items():
                    enabled_caps[k] = bool(v) if isinstance(v, int) else v

            # 格式化 REST APIs（返回完整配置）
            apis_formatted = []
            for a in instance_config.apis or []:
                apis_formatted.append(
                    {
                        "name": a.name,
                        "base_url": a.base_url,
                        "auth_type": a.auth.type if hasattr(a, "auth") and a.auth else "none",
                        "auth_env": a.auth.env if hasattr(a, "auth") and a.auth else None,
                        "doc": a.doc if hasattr(a, "doc") else None,
                        "capability": a.capability if hasattr(a, "capability") else None,
                        "description": a.description if hasattr(a, "description") else "",
                    }
                )

            detail.update(
                {
                    "model": instance_config.model,
                    "plan_manager_enabled": (
                        instance_config.plan_manager_enabled
                        if hasattr(instance_config, "plan_manager_enabled")
                        else False
                    ),
                    "enabled_capabilities": enabled_caps,
                    "apis": apis_formatted,
                    # skills 是 List[SkillConfig] 数据类，需要用属性访问
                    "skills": [s.name for s in (instance_config.skills or [])],
                }
            )

        # Fill model_capabilities from ModelRegistry
        model_name = detail.get("model")
        if model_name:
            from core.llm.model_registry import ModelRegistry

            model_cfg = ModelRegistry.get(model_name)
            if model_cfg:
                detail["model_capabilities"] = {
                    "provider": model_cfg.provider,
                    "display_name": model_cfg.display_name or model_cfg.model_name,
                    "supports_thinking": model_cfg.capabilities.supports_thinking,
                    "supports_vision": model_cfg.capabilities.supports_vision,
                    "supports_audio": model_cfg.capabilities.supports_audio,
                    "supports_streaming": model_cfg.capabilities.supports_streaming,
                    "max_tokens": model_cfg.capabilities.max_tokens,
                    "max_input_tokens": model_cfg.capabilities.max_input_tokens,
                }

        # Fill custom data_dir (None means default path is used)
        from utils.app_paths import get_instance_custom_data_dir

        detail["data_dir"] = get_instance_custom_data_dir(config.name)

        return detail

    async def get_agent_prompt(self, agent_id: str) -> str:
        """
        获取 Agent 的原始 prompt.md 内容（异步）

        Args:
            agent_id: Agent ID

        Returns:
            prompt.md 文件内容
        """
        if agent_id not in self._configs:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")

        instances_dir = get_instances_dir()
        prompt_path = instances_dir / agent_id / "prompt.md"

        if not prompt_path.exists():
            return ""

        async with aiofiles.open(prompt_path, "r", encoding="utf-8") as f:
            return await f.read()

    # ==================== 重载与卸载 ====================

    async def reload_agent(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        热重载 Agent 配置

        Args:
            agent_id: 指定 Agent ID，为 None 时重载所有

        Returns:
            重载结果摘要
        """
        if agent_id:
            # 重载单个 Agent
            if agent_id not in self._configs:
                raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")

            # 清除旧的原型和配置
            self._agent_prototypes.pop(agent_id, None)
            self._configs.pop(agent_id, None)

            # 重新加载
            await self.preload_instance(agent_id, force_refresh=True)

            logger.info(f"🔄 Agent '{agent_id}' 热重载完成")
            return {"reloaded": [agent_id], "failed": []}
        else:
            # 重载所有 Agent
            agent_ids = list(self._configs.keys())

            # 首次启动可能因缺少模型而加载失败，_configs 为空
            # 此时需要重新发现实例并尝试加载
            if not agent_ids:
                import os
                instance_name = os.environ.get("AGENT_INSTANCE")
                if not instance_name:
                    instances = list_instances()
                    if len(instances) == 1:
                        instance_name = instances[0]
                if instance_name:
                    agent_ids = [instance_name]
                    logger.info(
                        f"🔄 _configs 为空（首次加载可能失败），重新加载实例: {instance_name}"
                    )

            reloaded = []
            failed = []

            for aid in agent_ids:
                try:
                    self._agent_prototypes.pop(aid, None)
                    self._configs.pop(aid, None)
                    await self.preload_instance(aid, force_refresh=True)
                    reloaded.append(aid)
                except Exception as e:
                    logger.warning(f"⚠️ 重载 Agent '{aid}' 失败: {e}")
                    failed.append({"agent_id": aid, "error": str(e)})

            logger.info(f"🔄 热重载完成: {len(reloaded)} 成功, {len(failed)} 失败")
            return {"reloaded": reloaded, "failed": failed}

    def unload_agent(self, agent_id: str) -> None:
        """
        从注册表中卸载 Agent（不删除文件）

        Args:
            agent_id: Agent ID

        Raises:
            AgentNotFoundError: Agent 不存在
        """
        if agent_id not in self._configs:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")

        self._agent_prototypes.pop(agent_id, None)
        self._configs.pop(agent_id, None)

        logger.info(f"🗑️ Agent '{agent_id}' 已从注册表卸载")

    # ==================== 清理 ====================

    async def cleanup(self):
        """清理资源"""
        logger.info("🧹 清理 AgentRegistry 资源...")
        self._configs.clear()
        self._loaded = False
        logger.info("✅ AgentRegistry 资源已清理")


# ==================== 单例 ====================

_default_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """获取 AgentRegistry 单例"""
    global _default_registry
    if _default_registry is None:
        _default_registry = AgentRegistry()
    return _default_registry
