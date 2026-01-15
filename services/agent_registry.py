"""
Agent 注册服务 - Agent Registry Service

职责：
1. 启动时预加载所有 instances/ 目录下的 Agent 配置
2. 提供 get_agent(agent_id) 获取 Agent 实例（工厂模式）
3. 提供 list_agents() 列出所有可用 Agent
4. 管理 Agent 生命周期

设计原则：
- 工厂模式：每次请求创建新的 Agent 实例，共享配置但独立状态
- 预加载配置：启动时加载所有实例的 InstancePromptCache，避免运行时 LLM 分析
- 单例模式：AgentRegistry 全局唯一
"""

import asyncio
import os
import re
import shutil
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from logger import get_logger
from core.agent import AgentFactory
from core.events import create_event_manager, get_memory_storage
from core.prompt import load_instance_cache
from core.tool import InstanceToolRegistry, get_capability_registry, create_tool_loader
from prompts.universal_agent_prompt import get_universal_agent_prompt
from scripts.instance_loader import (
    list_instances,
    load_instance_config,
    load_instance_prompt,
    load_instance_env,
    _prepare_apis,
    _build_apis_prompt_section,
    get_instances_dir,
)
from services.mcp_client import get_mcp_client, create_mcp_tool_definition

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
    
    使用方法：
        registry = get_agent_registry()
        
        # 启动时预加载所有 Agent
        await registry.preload_all()
        
        # 获取 Agent 实例（每次调用创建新实例）
        agent = await registry.get_agent("test_agent", event_manager, ...)
        
        # 列出所有可用 Agent
        agents = registry.list_agents()
    """
    
    def __init__(self):
        # Agent 配置缓存（name -> AgentConfig）
        self._configs: Dict[str, AgentConfig] = {}
        
        # 加载状态
        self._loaded = False
        self._loading = False
        self._load_lock = asyncio.Lock()
    
    # ==================== 预加载 ====================
    
    async def preload_all(self, force_refresh: bool = False) -> int:
        """
        预加载所有 instances/ 目录下的 Agent 配置
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            成功加载的 Agent 数量
        """
        async with self._load_lock:
            if self._loaded and not force_refresh:
                logger.info("✅ Agent 配置已加载，跳过重复加载")
                return len(self._configs)
            
            self._loading = True
            start_time = datetime.now()
            
            try:
                instances = list_instances()
                logger.info(f"🔍 发现 {len(instances)} 个 Agent 实例")
                
                loaded_count = 0
                
                for instance_name in instances:
                    try:
                        instance_start = datetime.now()
                        logger.info(f"📦 预加载 Agent: {instance_name}")
                        
                        # 1. 加载环境变量
                        load_instance_env(instance_name)
                        
                        # 2. 加载实例配置
                        config = load_instance_config(instance_name)
                        
                        # 3. 加载实例提示词
                        instance_prompt = load_instance_prompt(instance_name)
                        
                        # 4. 加载 InstancePromptCache（核心：包含 AgentSchema、系统提示词等）
                        instance_path = get_instances_dir() / instance_name
                        cache_dir = instance_path / ".cache"
                        
                        prompt_cache = await load_instance_cache(
                            instance_name=instance_name,
                            raw_prompt=instance_prompt,
                            config=config.raw_config,
                            cache_dir=str(cache_dir),
                            force_refresh=force_refresh
                        )
                        
                        # 5. 准备 APIs 运行时参数
                        if config.apis:
                            config.apis = _prepare_apis(config.apis)
                        
                        # 6. 合并完整提示词
                        framework_prompt = get_universal_agent_prompt()
                        apis_prompt = _build_apis_prompt_section(config.apis)
                        
                        full_prompt = f"""# 实例配置

{instance_prompt}

---

{apis_prompt}

---

# 框架能力协议

{framework_prompt}
"""
                        
                        # 7. 创建 AgentConfig
                        load_time_ms = (datetime.now() - instance_start).total_seconds() * 1000
                        
                        agent_config = AgentConfig(
                            name=instance_name,
                            description=config.description,
                            version=config.version,
                            instance_config=config,
                            prompt_cache=prompt_cache,
                            full_prompt=full_prompt,
                            load_time_ms=load_time_ms
                        )
                        
                        self._configs[instance_name] = agent_config
                        loaded_count += 1
                        
                        logger.info(
                            f"   ✅ {instance_name} 加载完成 "
                            f"(耗时 {load_time_ms:.0f}ms)"
                        )
                        
                    except Exception as e:
                        logger.error(f"   ❌ {instance_name} 加载失败: {str(e)}", exc_info=True)
                
                total_time_ms = (datetime.now() - start_time).total_seconds() * 1000
                self._loaded = True
                
                logger.info(
                    f"🎉 Agent 预加载完成: {loaded_count}/{len(instances)} 个成功 "
                    f"(总耗时 {total_time_ms:.0f}ms)"
                )
                
                return loaded_count
                
            finally:
                self._loading = False
    
    # ==================== 获取 Agent ====================
    
    async def get_agent(
        self,
        agent_id: str,
        event_manager=None,
        workspace_dir: str = None,
        conversation_service=None
    ):
        """
        获取 Agent 实例（工厂模式：每次创建新实例）
        
        Args:
            agent_id: Agent ID（instances/ 目录名）
            event_manager: 事件管理器
            workspace_dir: 工作目录
            conversation_service: 会话服务
            
        Returns:
            新创建的 Agent 实例
            
        Raises:
            AgentNotFoundError: agent_id 不存在
        """
        if agent_id not in self._configs:
            available = list(self._configs.keys())
            raise AgentNotFoundError(
                f"Agent '{agent_id}' 不存在，可用的 Agent: {available}"
            )
        
        config = self._configs[agent_id]
        
        # 如果未提供 event_manager，创建一个
        if event_manager is None:
            storage = get_memory_storage()
            event_manager = create_event_manager(storage)
        
        # 🆕 准备 apis_config（用于 api_calling 自动注入认证）
        apis_config = None
        if config.instance_config and config.instance_config.apis:
            apis_config = [
                {
                    "name": api.name,
                    "base_url": api.base_url,
                    "headers": api.headers or {},
                    "description": api.description,
                }
                for api in config.instance_config.apis
            ]
            logger.debug(f"   📡 APIs: {[a['name'] for a in apis_config]}")
        
        # 使用缓存的 AgentSchema 和 PromptCache 创建 Agent
        if config.prompt_cache and config.prompt_cache.is_loaded and config.prompt_cache.agent_schema:
            agent = AgentFactory.from_schema(
                schema=config.prompt_cache.agent_schema,
                system_prompt=config.full_prompt,
                event_manager=event_manager,
                workspace_dir=workspace_dir,
                conversation_service=conversation_service,
                prompt_cache=config.prompt_cache,
                apis_config=apis_config,  # 🆕 传递预配置的 APIs
            )
        else:
            # Fallback: 使用旧方式
            logger.warning(f"⚠️ Agent {agent_id} 的 PromptCache 未加载，使用 from_prompt")
            agent = await AgentFactory.from_prompt(
                system_prompt=config.full_prompt,
                event_manager=event_manager,
                workspace_dir=workspace_dir,
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
                agent.max_turns = instance_config.max_turns
        
        # 设置实例级工具注册表
        await self._setup_instance_tools(agent, config)
        
        logger.debug(f"🤖 创建 Agent 实例: {agent_id}")
        
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
        
        # 加载所有工具（通用工具、MCP 工具、Claude Skills）
        load_result = tool_loader.load_tools(
            enabled_capabilities=instance_config.enabled_capabilities,
            mcp_tools=instance_config.mcp_tools,
            skills=instance_config.skills,
        )
        
        # 创建过滤后的注册表
        filtered_registry = tool_loader.create_filtered_registry(
            instance_config.enabled_capabilities
        )
        
        # 使用过滤后的 registry 创建实例级注册表
        instance_registry = InstanceToolRegistry(global_registry=filtered_registry)
        agent._instance_registry = instance_registry
        
        # 注册 MCP 工具（如果有）
        if instance_config.mcp_tools:
            await self._register_mcp_tools(agent, instance_config.mcp_tools, instance_registry)
    
    async def _register_mcp_tools(
        self,
        agent,
        mcp_tools: List[Dict[str, Any]],
        instance_registry
    ):
        """
        注册 MCP 工具
        
        Args:
            agent: Agent 实例
            mcp_tools: MCP 工具配置列表
            instance_registry: 实例级工具注册表
        """
        mcp_tool_definitions = []
        
        for tool_config in mcp_tools:
            name = tool_config.get("name", "unknown")
            try:
                server_url = tool_config.get("server_url")
                server_name = tool_config.get("server_name", name)
                auth_type = tool_config.get("auth_type", "none")
                auth_env = tool_config.get("auth_env")
                
                if not server_url:
                    continue
                
                # 获取认证令牌
                auth_token = None
                if auth_type in ("bearer", "api_key") and auth_env:
                    auth_token = os.getenv(auth_env)
                    if not auth_token:
                        logger.warning(f"⚠️ MCP 工具 {name} 的密钥环境变量 {auth_env} 未设置")
                        continue
                
                # 获取 MCP 客户端
                client = await get_mcp_client(
                    server_url=server_url,
                    server_name=server_name,
                    auth_token=auth_token
                )
                
                # 🆕 处理连接失败的情况
                if client is None:
                    logger.warning(f"⚠️ MCP 客户端连接失败，跳过工具 {name}")
                    continue
                
                if client._connected:
                    tools = client._tools
                    if not tools:
                        tools_list = await client.discover_tools()
                        tools = {t['name']: t for t in tools_list}
                    
                    for tool_name, tool_info in tools.items():
                        tool_def = create_mcp_tool_definition(tool_info, client)
                        mcp_tool_definitions.append(tool_def)
                        
                        # 注册到 InstanceToolRegistry
                        capability = tool_config.get("capability")
                        original_name = tool_info.get("original_name", tool_name)
                        
                        async def make_handler(_client, _orig_name, _server_url, _server_name, _auth_token):
                            async def handler(tool_input: Dict[str, Any]):
                                # #region agent log
                                import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "agent_registry.py:handler:entry", "message": "进入 MCP handler(registry)", "data": {"orig_name": _orig_name, "client_connected": _client._connected if _client else False}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,B,E"}) + '\n')
                                # #endregion
                                # 检查客户端状态，断开则重新获取
                                current_client = _client
                                if not _client._connected or not _client._session:
                                    # #region agent log
                                    import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "agent_registry.py:handler:reconnect", "message": "需重新获取客户端", "data": {"orig_name": _orig_name}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A,B"}) + '\n')
                                    # #endregion
                                    current_client = await get_mcp_client(
                                        server_url=_server_url,
                                        server_name=_server_name,
                                        auth_token=_auth_token,
                                        force_reconnect=True  # 强制重连
                                    )
                                    if not current_client:
                                        return {"success": False, "error": "MCP 服务器连接失败"}
                                
                                # 调用工具
                                result = await current_client.call_tool(_orig_name, tool_input)
                                
                                # 如果需要重连，自动重试一次
                                if result.get("_need_reconnect"):
                                    # #region agent log
                                    import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "agent_registry.py:handler:auto_retry", "message": "检测到连接断开，自动重连重试", "data": {"orig_name": _orig_name}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "A"}) + '\n')
                                    # #endregion
                                    # 强制重连
                                    current_client = await get_mcp_client(
                                        server_url=_server_url,
                                        server_name=_server_name,
                                        auth_token=_auth_token,
                                        force_reconnect=True
                                    )
                                    if not current_client:
                                        return {"success": False, "error": "MCP 服务器重连失败"}
                                    result = await current_client.call_tool(_orig_name, tool_input)
                                
                                return result
                            return handler
                        
                        handler = await make_handler(client, original_name, server_url, server_name, auth_token)
                        
                        await instance_registry.register_mcp_tool(
                            name=tool_name,
                            server_url=server_url,
                            server_name=server_name,
                            tool_info=tool_info,
                            mcp_client=client,
                            handler=handler,
                            capability=capability
                        )
                    
                    # 保存客户端引用
                    if hasattr(agent, '_mcp_clients'):
                        if client not in agent._mcp_clients:
                            agent._mcp_clients.append(client)
                    else:
                        agent._mcp_clients = [client]
                        
            except Exception as e:
                logger.warning(f"⚠️ 注册 MCP 工具 {name} 失败: {str(e)}")
        
        # 将 MCP 工具定义注入到 Agent
        if mcp_tool_definitions:
            if hasattr(agent, '_mcp_tools'):
                agent._mcp_tools.extend(mcp_tool_definitions)
            else:
                agent._mcp_tools = mcp_tool_definitions
            
            # 注册到 tool_executor（带自动重连逻辑）
            if hasattr(agent, 'tool_executor'):
                for tool_def in mcp_tool_definitions:
                    tool_name = tool_def['name']
                    original_name = tool_def['_original_name']
                    # 获取连接信息用于重连
                    _server_url = tool_def.get('_server_url')
                    _server_name = tool_def.get('_server_name')
                    _auth_token = tool_def.get('_auth_token')
                    
                    async def mcp_handler(
                        tool_input: Dict[str, Any], 
                        _url=_server_url, 
                        _name=_server_name, 
                        _token=_auth_token,
                        _orig_name=original_name
                    ):
                        # #region agent log
                        import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "agent_registry.py:tool_executor_handler:entry", "message": "进入 tool_executor MCP handler", "data": {"orig_name": _orig_name, "server_name": _name}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "F"}) + '\n')
                        # #endregion
                        # 每次调用动态获取客户端
                        current_client = await get_mcp_client(
                            server_url=_url,
                            server_name=_name,
                            auth_token=_token
                        )
                        if not current_client:
                            return {"success": False, "error": "MCP 服务器连接失败"}
                        
                        result = await current_client.call_tool(_orig_name, tool_input)
                        
                        # 如果需要重连，自动重试
                        if result.get("_need_reconnect"):
                            # #region agent log
                            import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "agent_registry.py:tool_executor_handler:auto_retry", "message": "自动重连重试", "data": {"orig_name": _orig_name}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "F"}) + '\n')
                            # #endregion
                            current_client = await get_mcp_client(
                                server_url=_url,
                                server_name=_name,
                                auth_token=_token,
                                force_reconnect=True
                            )
                            if not current_client:
                                return {"success": False, "error": "MCP 服务器重连失败"}
                            result = await current_client.call_tool(_orig_name, tool_input)
                        
                        # #region agent log
                        import json as _json; open('/Users/kens0n/projects/zenflux_agent/.cursor/debug.log', 'a').write(_json.dumps({"location": "agent_registry.py:tool_executor_handler:return", "message": "处理器返回", "data": {"orig_name": _orig_name, "success": result.get("success"), "has_error": "error" in result}, "timestamp": __import__('time').time() * 1000, "sessionId": "debug-session", "hypothesisId": "G"}) + '\n')
                        # #endregion
                        return result
                    
                    agent.tool_executor.register_handler(tool_name, mcp_handler)
    
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
                "load_time_ms": config.load_time_ms
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
    
    # ==================== CRUD 操作 ====================
    
    async def create_agent(
        self,
        agent_id: str,
        description: str = "",
        prompt: str = "",
        model: str = "claude-sonnet-4-5-20250929",
        max_turns: int = 20,
        plan_manager_enabled: bool = True,
        enabled_capabilities: Dict[str, bool] = None,
        mcp_tools: List[Dict[str, Any]] = None,
        apis: List[Dict[str, Any]] = None,
        memory: Dict[str, Any] = None,
        llm: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        创建新的 Agent
        
        Args:
            agent_id: Agent ID（将作为目录名）
            description: Agent 描述
            prompt: 提示词内容（写入 prompt.md）
            model: 使用的模型
            max_turns: 最大对话轮数
            plan_manager_enabled: 是否启用计划管理器
            enabled_capabilities: 启用的工具能力
            mcp_tools: MCP 工具配置
            apis: REST API 配置
            memory: 记忆配置
            llm: LLM 超参数
            
        Returns:
            创建结果
            
        Raises:
            ValueError: agent_id 已存在或格式不合法
        """
        # 验证 agent_id 格式
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', agent_id):
            raise ValueError(f"agent_id 格式不合法: {agent_id}，必须以字母开头，只能包含字母、数字、下划线、连字符")
        
        # 检查是否已存在
        if agent_id in self._configs:
            raise ValueError(f"Agent '{agent_id}' 已存在")
        
        instances_dir = get_instances_dir()
        agent_dir = instances_dir / agent_id
        
        if agent_dir.exists():
            raise ValueError(f"目录已存在: {agent_dir}")
        
        try:
            # 创建目录结构
            agent_dir.mkdir(parents=True)
            (agent_dir / "api_desc").mkdir(exist_ok=True)
            (agent_dir / "skills").mkdir(exist_ok=True)
            
            # 生成 config.yaml
            config_data = {
                "instance": {
                    "name": agent_id,
                    "description": description,
                    "version": "1.0.0",
                },
                "agent": {
                    "model": model,
                    "max_turns": max_turns,
                    "plan_manager_enabled": plan_manager_enabled,
                },
            }
            
            # 添加 LLM 配置
            if llm:
                config_data["agent"]["llm"] = llm
            
            # 添加 enabled_capabilities
            if enabled_capabilities:
                config_data["enabled_capabilities"] = {
                    k: (1 if v else 0) for k, v in enabled_capabilities.items()
                }
            
            # 添加 MCP 工具
            if mcp_tools:
                config_data["mcp_tools"] = mcp_tools
            
            # 添加 APIs
            if apis:
                config_data["apis"] = apis
            
            # 添加 Memory
            if memory:
                config_data["memory"] = memory
            else:
                config_data["memory"] = {
                    "mem0_enabled": True,
                    "smart_retrieval": True,
                    "retention_policy": "user",
                }
            
            # 写入 config.yaml
            config_path = agent_dir / "config.yaml"
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            
            # 写入 prompt.md
            prompt_path = agent_dir / "prompt.md"
            prompt_content = prompt if prompt else f"""# {agent_id}

## 角色定位

你是一个专业的 AI 助手。

## 任务能力

请根据用户需求提供帮助。
"""
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(prompt_content)
            
            # 预加载新创建的 Agent
            await self._load_single_agent(agent_id)
            
            logger.info(f"✅ Agent '{agent_id}' 创建成功")
            
            return {
                "agent_id": agent_id,
                "path": str(agent_dir),
                "message": f"Agent '{agent_id}' 创建成功",
            }
            
        except Exception as e:
            # 回滚：删除已创建的目录
            import shutil
            if agent_dir.exists():
                shutil.rmtree(agent_dir)
            raise
    
    async def update_agent(
        self,
        agent_id: str,
        description: str = None,
        prompt: str = None,
        model: str = None,
        max_turns: int = None,
        plan_manager_enabled: bool = None,
        enabled_capabilities: Dict[str, bool] = None,
        mcp_tools: List[Dict[str, Any]] = None,
        apis: List[Dict[str, Any]] = None,
        memory: Dict[str, Any] = None,
        llm: Dict[str, Any] = None,
        is_active: bool = None,
    ) -> Dict[str, Any]:
        """
        更新 Agent 配置
        
        Args:
            agent_id: Agent ID
            (其他参数参见 create_agent)
            
        Returns:
            更新结果
        """
        if agent_id not in self._configs:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")
        
        instances_dir = get_instances_dir()
        agent_dir = instances_dir / agent_id
        config_path = agent_dir / "config.yaml"
        prompt_path = agent_dir / "prompt.md"
        
        # 读取现有配置
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        
        # 更新配置
        updated_fields = []
        
        if description is not None:
            config_data.setdefault("instance", {})["description"] = description
            updated_fields.append("description")
        
        if model is not None:
            config_data.setdefault("agent", {})["model"] = model
            updated_fields.append("model")
        
        if max_turns is not None:
            config_data.setdefault("agent", {})["max_turns"] = max_turns
            updated_fields.append("max_turns")
        
        if plan_manager_enabled is not None:
            config_data.setdefault("agent", {})["plan_manager_enabled"] = plan_manager_enabled
            updated_fields.append("plan_manager_enabled")
        
        if llm is not None:
            config_data.setdefault("agent", {})["llm"] = llm
            updated_fields.append("llm")
        
        if enabled_capabilities is not None:
            config_data["enabled_capabilities"] = {
                k: (1 if v else 0) for k, v in enabled_capabilities.items()
            }
            updated_fields.append("enabled_capabilities")
        
        if mcp_tools is not None:
            config_data["mcp_tools"] = mcp_tools
            updated_fields.append("mcp_tools")
        
        if apis is not None:
            config_data["apis"] = apis
            updated_fields.append("apis")
        
        if memory is not None:
            config_data["memory"] = memory
            updated_fields.append("memory")
        
        # 写入更新后的配置
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        # 更新 prompt.md
        if prompt is not None:
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(prompt)
            updated_fields.append("prompt")
        
        # 重新加载 Agent 配置
        await self._load_single_agent(agent_id, force_refresh=True)
        
        logger.info(f"✅ Agent '{agent_id}' 更新成功，更新字段: {updated_fields}")
        
        return {
            "agent_id": agent_id,
            "updated_fields": updated_fields,
            "message": f"Agent '{agent_id}' 更新成功",
        }
    
    async def delete_agent(self, agent_id: str, force: bool = False) -> Dict[str, Any]:
        """
        删除 Agent
        
        Args:
            agent_id: Agent ID
            force: 是否强制删除（即使文件系统删除失败也从注册表移除）
            
        Returns:
            删除结果
        """
        if agent_id not in self._configs:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")
        
        # 保护 _template 不被删除
        if agent_id == "_template":
            raise ValueError("不能删除模板目录 '_template'")
        
        instances_dir = get_instances_dir()
        agent_dir = instances_dir / agent_id
        
        try:
            # 删除文件系统
            if agent_dir.exists():
                shutil.rmtree(agent_dir)
                logger.info(f"🗑️ 已删除目录: {agent_dir}")
        except Exception as e:
            if not force:
                raise ValueError(f"删除目录失败: {e}")
            logger.warning(f"⚠️ 删除目录失败，但继续从注册表移除: {e}")
        
        # 从注册表移除
        del self._configs[agent_id]
        
        logger.info(f"✅ Agent '{agent_id}' 已删除")
        
        return {
            "agent_id": agent_id,
            "message": f"Agent '{agent_id}' 已删除",
        }
    
    async def reload_agent(self, agent_id: str = None) -> Dict[str, Any]:
        """
        重新加载 Agent 配置
        
        Args:
            agent_id: Agent ID，如果为 None 则重载所有
            
        Returns:
            重载结果
        """
        if agent_id:
            if agent_id not in self._configs:
                # 可能是新创建的，尝试加载
                try:
                    await self._load_single_agent(agent_id)
                    return {
                        "agent_id": agent_id,
                        "message": f"Agent '{agent_id}' 加载成功",
                    }
                except Exception as e:
                    raise AgentNotFoundError(f"Agent '{agent_id}' 不存在: {e}")
            
            await self._load_single_agent(agent_id, force_refresh=True)
            return {
                "agent_id": agent_id,
                "message": f"Agent '{agent_id}' 重新加载成功",
            }
        else:
            # 重载所有
            count = await self.preload_all(force_refresh=True)
            return {
                "reloaded_count": count,
                "message": f"已重新加载 {count} 个 Agent",
            }
    
    async def _load_single_agent(self, agent_id: str, force_refresh: bool = False):
        """
        加载单个 Agent 配置
        
        Args:
            agent_id: Agent ID
            force_refresh: 是否强制刷新缓存
        """
        instance_start = datetime.now()
        
        # 1. 加载环境变量
        load_instance_env(agent_id)
        
        # 2. 加载实例配置
        config = load_instance_config(agent_id)
        
        # 3. 加载实例提示词
        instance_prompt = load_instance_prompt(agent_id)
        
        # 4. 加载 InstancePromptCache
        instance_path = get_instances_dir() / agent_id
        cache_dir = instance_path / ".cache"
        
        prompt_cache = await load_instance_cache(
            instance_name=agent_id,
            raw_prompt=instance_prompt,
            config=config.raw_config,
            cache_dir=str(cache_dir),
            force_refresh=force_refresh
        )
        
        # 5. 准备 APIs 运行时参数
        if config.apis:
            config.apis = _prepare_apis(config.apis)
        
        # 6. 合并完整提示词
        framework_prompt = get_universal_agent_prompt()
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
            load_time_ms=load_time_ms
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
            for t in (instance_config.mcp_tools or []):
                mcp_tools_formatted.append({
                    "name": t.get("name", "unknown"),
                    "server_url": t.get("server_url", ""),
                    "server_name": t.get("server_name", ""),
                    "auth_type": t.get("auth_type", "none"),
                    "auth_env": t.get("auth_env"),
                    "capability": t.get("capability"),
                    "description": t.get("description", ""),
                })
            
            # 格式化 REST APIs（返回完整配置）
            apis_formatted = []
            for a in (instance_config.apis or []):
                apis_formatted.append({
                    "name": a.name,
                    "base_url": a.base_url,
                    "auth_type": a.auth.type if hasattr(a, 'auth') and a.auth else "none",
                    "auth_env": a.auth.env if hasattr(a, 'auth') and a.auth else None,
                    "doc": a.doc if hasattr(a, 'doc') else None,
                    "capability": a.capability if hasattr(a, 'capability') else None,
                    "description": a.description if hasattr(a, 'description') else "",
                })
            
            detail.update({
                "model": instance_config.model,
                "max_turns": instance_config.max_turns,
                "plan_manager_enabled": instance_config.plan_manager_enabled if hasattr(instance_config, 'plan_manager_enabled') else False,
                "enabled_capabilities": enabled_caps,
                "mcp_tools": mcp_tools_formatted,
                "apis": apis_formatted,
                # skills 是 List[SkillConfig] 数据类，需要用属性访问
                "skills": [s.name for s in (instance_config.skills or [])],
            })
        
        return detail
    
    def get_agent_prompt(self, agent_id: str) -> str:
        """
        获取 Agent 的原始 prompt.md 内容
        
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
        
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    
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

