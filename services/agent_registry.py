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
# TODO: 迁移到 local_store
# from infra.pools import get_mcp_pool
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

logger = get_logger("agent_registry")


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
        # 原型包含：LLM Service、工具注册表、MCP 客户端等重量级组件
        # 运行时通过 clone_for_session() 浅克隆并重置会话状态
        self._agent_prototypes: Dict[str, Any] = {}  # name -> Agent

        # 共享组件（跨 Agent 复用）
        self._shared_event_manager = None  # 共享的事件管理器（原型创建时使用）

        # 加载状态
        self._loaded = False
        self._loading = False
        self._load_lock = asyncio.Lock()

    # ==================== 单实例加载 ====================

    async def preload_instance(self, instance_name: str, force_refresh: bool = False) -> bool:
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
                await self._load_single_agent(instance_name, force_refresh=force_refresh)

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

        Args:
            force_refresh: 是否强制刷新缓存

        Returns:
            成功加载的实例数量
        """
        instances = list_instances()
        loaded_count = 0

        for instance_name in instances:
            try:
                success = await self.preload_instance(instance_name, force_refresh=force_refresh)
                if success:
                    loaded_count += 1
            except Exception as e:
                logger.warning(f"⚠️ 加载实例 '{instance_name}' 失败: {e}")
                continue

        self._loaded = loaded_count > 0
        return loaded_count

    def get_current_instance(self) -> Optional[str]:
        """
        获取当前加载的实例名称（单实例模式下使用）

        Returns:
            当前实例名称，如果是多实例模式或未加载则返回 None
        """
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

        # 使用缓存的 AgentSchema 和 PromptCache 创建 Agent
        if (
            config.prompt_cache
            and config.prompt_cache.is_loaded
            and config.prompt_cache.agent_schema
        ):
            agent = await AgentFactory.from_schema(
                schema=config.prompt_cache.agent_schema,
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

        # 应用配置覆盖
        instance_config = config.instance_config
        if instance_config:
            if instance_config.model:
                agent.model = instance_config.model
            if instance_config.max_turns:
                agent._max_steps = instance_config.max_turns

        # 设置实例级工具注册表
        await self._setup_instance_tools(agent, config)

        logger.debug(f"🤖 创建 Agent 实例: {agent_id}")

        return agent

    async def _create_agent_prototype(self, config: AgentConfig, event_manager):
        """
        🆕 V7.1: 创建 Agent 原型（部署态预创建）

        创建 Agent 原型（含 LLM、工具注册表、MCP 客户端）

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

        # AgentFactory.from_schema() 创建 RVR-B Agent
        agent = await AgentFactory.from_schema(
            schema=config.prompt_cache.agent_schema,
            system_prompt=config.full_prompt,
            event_manager=event_manager,
            conversation_service=None,  # 原型不绑定会话服务
            prompt_cache=config.prompt_cache,
            apis_config=apis_config,
        )

        # 应用配置覆盖
        instance_config = config.instance_config
        if instance_config:
            if instance_config.model:
                agent.model = instance_config.model
            if instance_config.max_turns:
                agent._max_steps = instance_config.max_turns

        # 设置实例级工具
        if hasattr(agent, "_setup_instance_tools"):
            await self._setup_instance_tools(agent, config)

        # 标记为原型（用于 clone_for_session 判断）
        agent._is_prototype = True

        agent_type = "Agent"
        logger.debug(f"   原型类型: {agent_type}")

        return agent

    async def _setup_instance_tools(self, agent, config: AgentConfig):
        """
        设置实例级工具（MCP 工具、Skills 等）

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

        # 加载所有工具（通用工具、MCP 工具、Claude Skills）（异步）
        load_result = await tool_loader.load_tools(
            enabled_capabilities=instance_config.enabled_capabilities,
            mcp_tools=instance_config.mcp_tools,
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

        # 注册 MCP 工具（如果有）
        if instance_config.mcp_tools:
            await self._register_mcp_tools(agent, instance_config.mcp_tools, instance_registry)

    async def _register_mcp_tools(self, agent, mcp_tools: List[Dict[str, Any]], instance_registry):
        """
        注册 MCP 工具

        🔧 V7.6 修复：改为**同步发现模式**，启动时连接 MCP 服务器并获取真实的 input_schema
        这样 LLM 才能知道每个工具需要什么参数

        Args:
            agent: Agent 实例
            mcp_tools: MCP 工具配置列表
            instance_registry: 实例级工具注册表
        """
        logger.info(f"📦 注册 MCP 工具（同步发现模式）: {len(mcp_tools)} 个配置")

        # 按 server_url 分组，避免重复连接同一服务器
        servers: Dict[str, Dict[str, Any]] = {}
        for tool_config in mcp_tools:
            server_url = tool_config.get("server_url")
            if not server_url:
                continue

            if server_url not in servers:
                servers[server_url] = {
                    "server_name": tool_config.get("server_name", "unknown"),
                    "auth_type": tool_config.get("auth_type", "none"),
                    "auth_env": tool_config.get("auth_env"),
                    "capability": tool_config.get("capability"),
                }

        # 连接每个 MCP 服务器并发现工具
        # TODO: 迁移到 local_store
        # pool = get_mcp_pool()
        pool = None  # Stub

        for server_url, server_config in servers.items():
            server_name = server_config["server_name"]
            auth_type = server_config["auth_type"]
            auth_env = server_config["auth_env"]
            capability = server_config["capability"]

            try:
                # 获取认证令牌
                auth_token = None
                if auth_type in ("bearer", "api_key") and auth_env:
                    auth_token = os.getenv(auth_env)
                    if not auth_token:
                        logger.warning(
                            f"⚠️ MCP 服务器 {server_name} 的密钥环境变量 {auth_env} 未设置，跳过"
                        )
                        continue

                # 🔧 将 MCP 连接操作隔离到独立 task 中，避免 anyio cancel scope 污染主流程
                async def _isolated_mcp_connect(_pool, _server_url, _server_name, _auth_token):
                    """在独立 task 中连接 MCP，隔离 cancel scope"""
                    try:
                        client = await _pool.get_client(
                            server_url=_server_url, server_name=_server_name, auth_token=_auth_token
                        )
                        if client:
                            tools = await client.discover_tools()
                            return client, tools
                        return None, []
                    except asyncio.CancelledError:
                        logger.warning(f"   ⚠️ MCP 连接被取消（隔离）: {_server_name}")
                        return None, []
                    except Exception as e:
                        logger.warning(f"   ⚠️ MCP 连接异常（隔离）: {_server_name}: {e}")
                        return None, []

                logger.info(f"   🔌 连接 MCP 服务器: {server_name}")

                # TODO: 迁移到 local_store
                # 在独立 task 中执行 MCP 连接，隔离 anyio cancel scope
                # connect_task = asyncio.create_task(
                #     _isolated_mcp_connect(pool, server_url, server_name, auth_token)
                # )
                # client, tools = await connect_task
                client, tools = None, []  # Stub

                # 短暂等待让事件循环处理残留的 cancel scope
                await asyncio.sleep(0)

                if not client:
                    logger.warning(f"   ❌ MCP 服务器 {server_name} 连接失败，跳过")
                    continue

                logger.info(f"   ✅ {server_name}: 发现 {len(tools)} 个工具")

                # 注册每个发现的工具
                for tool_info in tools:
                    tool_name = tool_info.get("name")  # 已经带 server_name 前缀
                    original_name = tool_info.get("original_name", tool_name)
                    description = tool_info.get("description", "")
                    input_schema = tool_info.get("input_schema", {})

                    # 🆕 检查配置文件中是否有该工具的自定义描述（覆盖 MCP 服务器的描述）
                    config_description = None
                    for tool_config in mcp_tools:
                        if (
                            tool_config.get("name") == original_name
                            and tool_config.get("server_url") == server_url
                        ):
                            config_description = tool_config.get("description")
                            if config_description:
                                logger.info(f"      ✏️ 使用配置文件中的自定义描述覆盖 MCP 描述")
                                description = config_description
                                # 同时更新 tool_info 中的 description
                                tool_info["description"] = config_description
                            break

                    # 🔍 显示工具的参数信息
                    schema_props = (
                        input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
                    )
                    param_info = f"参数: {list(schema_props.keys())}" if schema_props else "无参数"
                    logger.info(f"      • {tool_name} ({param_info})")

                    # 创建工具处理器（闭包捕获变量）
                    async def make_handler(_server_url, _server_name, _auth_token, _orig_name):
                        async def handler(tool_input: Dict[str, Any], context=None):
                            # TODO: 迁移到 local_store
                            return {"success": False, "error": "MCP pool not available - TODO: 迁移到 local_store"}
                        return handler

                    handler = await make_handler(server_url, server_name, auth_token, original_name)

                    # 🔧 注册到 InstanceRegistry，传入真实的 tool_info（包含 input_schema）
                    await instance_registry.register_mcp_tool(
                        name=tool_name,
                        server_url=server_url,
                        server_name=server_name,
                        tool_info=tool_info,  # 包含真实的 input_schema！
                        mcp_client=client,
                        handler=handler,
                        capability=capability,
                    )

                    # 同时注册到 Agent 的 tool_executor
                    if hasattr(agent, "tool_executor") and agent.tool_executor:
                        agent.tool_executor.register_handler(tool_name, handler)

            except Exception as e:
                logger.warning(f"⚠️ 注册 MCP 服务器 {server_name} 的工具失败: {str(e)}")

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

    async def _load_single_agent(self, agent_id: str, force_refresh: bool = False):
        """
        加载单个 Agent 配置

        Args:
            agent_id: Agent ID
            force_refresh: 是否强制刷新缓存
        """
        instance_start = datetime.now()

        # 1. 加载实例环境变量（从 config.yaml 的 env_vars 段）
        load_instance_env_from_config(agent_id)

        # 2. 加载实例配置
        config = await load_instance_config(agent_id)

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

        # 7. 创建/更新 AgentConfig
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
        detail = {
            "agent_id": config.name,
            "name": config.name,
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

            # 格式化 MCP 工具（返回完整配置）
            mcp_tools_formatted = []
            for t in instance_config.mcp_tools or []:
                mcp_tools_formatted.append(
                    {
                        "name": t.get("name", "unknown"),
                        "server_url": t.get("server_url", ""),
                        "server_name": t.get("server_name", ""),
                        "auth_type": t.get("auth_type", "none"),
                        "auth_env": t.get("auth_env"),
                        "capability": t.get("capability"),
                        "description": t.get("description", ""),
                    }
                )

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
                    "max_turns": instance_config.max_turns,
                    "plan_manager_enabled": (
                        instance_config.plan_manager_enabled
                        if hasattr(instance_config, "plan_manager_enabled")
                        else False
                    ),
                    "enabled_capabilities": enabled_caps,
                    "mcp_tools": mcp_tools_formatted,
                    "apis": apis_formatted,
                    # skills 是 List[SkillConfig] 数据类，需要用属性访问
                    "skills": [s.name for s in (instance_config.skills or [])],
                }
            )

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
