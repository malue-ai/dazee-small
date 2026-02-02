"""
实例级工具注册表 - 统一管理实例级动态工具

职责：
1. 管理实例级 MCP 工具（从 instances/xxx/config.yaml 加载）
2. 管理实例级 REST APIs
3. 与全局 CapabilityRegistry 协同工作
4. 提供统一的工具发现接口

设计原则：
- 单实例单 Registry：每个 Agent 实例有自己的 InstanceToolRegistry
- 与全局 Registry 解耦：不污染全局单例
- 统一抽象：MCP 工具转换为 Capability 格式

使用方式：
    # 在 instance_loader.py 中
    instance_registry = InstanceToolRegistry()
    await instance_registry.register_mcp_tools(mcp_tools_config)
    
    # 获取所有工具（全局 + 实例）
    all_tools = instance_registry.get_all_tools()
"""

import json
import aiofiles
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum
from pathlib import Path

from logger import get_logger

logger = get_logger("zenflux.instance_registry")


class InstanceToolType(Enum):
    """实例级工具类型"""
    MCP = "MCP"           # MCP 协议工具
    REST_API = "REST_API" # REST API（通过 api_calling 调用）


@dataclass
class InstanceTool:
    """
    实例级工具定义
    
    统一表示 MCP 工具和 REST API，可转换为 Claude API 格式
    """
    name: str                                    # 工具名称（命名空间化：server_toolname）
    type: InstanceToolType                       # 工具类型
    description: str = ""                        # 工具描述
    input_schema: Dict[str, Any] = field(default_factory=dict)  # 输入参数 Schema
    
    # 🆕 V4.6: 能力类别（用户意图分类）
    capability: Optional[str] = None             # 如 document_creation, web_search 等
    
    # MCP 特有属性
    server_url: Optional[str] = None             # MCP 服务器 URL
    server_name: Optional[str] = None            # MCP 服务器名称
    original_name: Optional[str] = None          # MCP 工具原始名称
    mcp_client: Optional[Any] = None             # MCP 客户端实例
    
    # REST API 特有属性
    base_url: Optional[str] = None               # API 基础 URL
    api_doc: Optional[str] = None                # API 文档内容
    
    # 调用处理器
    handler: Optional[Callable[..., Awaitable[Any]]] = None
    
    def to_claude_tool(self) -> Dict[str, Any]:
        """
        转换为 Claude API 工具格式
        
        Returns:
            Claude API 兼容的工具定义
        """
        # 🔧 不再使用写死的 prompt 默认值
        # 如果没有 input_schema，使用空 schema（允许任意参数）
        schema = self.input_schema if self.input_schema else {
            "type": "object",
            "properties": {},
            "required": []
        }
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema
        }
    
    def to_capability_dict(self) -> Dict[str, Any]:
        """
        转换为 Capability 兼容格式（用于 discover_tools）
        
        Returns:
            与 capabilities.yaml 格式兼容的字典
        """
        return {
            "name": self.name,
            "type": "TOOL",
            "subtype": "MCP" if self.type == InstanceToolType.MCP else "REST",
            "provider": self.server_name or "instance",
            "capabilities": self._infer_capabilities(),
            "priority": 80,  # 实例工具优先级较高
            "metadata": {
                "description": self.description,
                "instance_tool": True,
                "tool_type": self.type.value
            },
            "input_schema": self.input_schema
        }
    
    def _infer_capabilities(self) -> List[str]:
        """
        🆕 V4.6 LLM 驱动的能力类别推断
        
        设计原则：
        - 利用 LLM 的语义理解和推理能力，而非简单关键词匹配
        - 如果显式配置了 capability，则使用配置值（覆盖推断）
        - 首次推断后缓存结果，避免重复调用 LLM
        
        Returns:
            推断出的能力类别列表（与 capability_categories 中的 ID 对应）
        """
        # 1. 优先使用显式配置的 capability（覆盖推断）
        if self.capability:
            return [self.capability]
        
        # 2. LLM 驱动的语义推断（如果有全局 registry）
        if hasattr(self, '_cached_capabilities'):
            return self._cached_capabilities
        
        # 尝试使用 LLM 推断（需要全局 registry）
        try:
            from core.tool.capability import get_capability_registry
            registry = get_capability_registry()
            
            # 获取所有业务能力类别定义
            business_capabilities = {}
            for cat in registry.capability_categories:
                if cat.get('category_type') == 'business':
                    cap_id = cat['id']
                    business_capabilities[cap_id] = cat.get('description', '')
            
            if business_capabilities:
                # 使用 LLM 进行语义匹配
                inferred = self._llm_based_inference(business_capabilities)
                if inferred:
                    self._cached_capabilities = inferred
                    return inferred
        except Exception as e:
            # LLM 推断失败，回退到关键词匹配
            logger.debug(f"LLM 推断失败，回退到关键词匹配: {str(e)}")
        
        # 3. 回退方案：简化的关键词匹配（仅核心关键词）
        capabilities = self._keyword_based_fallback()
        self._cached_capabilities = capabilities
        return capabilities
    
    def _llm_based_inference(self, business_capabilities: Dict[str, str]) -> List[str]:
        """
        使用 LLM 进行语义推断
        
        Args:
            business_capabilities: 业务能力字典 {能力ID: 描述}
            
        Returns:
            推断出的能力列表
        """
        try:
            from core.llm import create_llm_service
            
            # 构造推断 prompt
            capabilities_desc = "\n".join([
                f"- {cap_id}: {desc}" 
                for cap_id, desc in business_capabilities.items()
            ])
            
            prompt = f"""你是能力分类专家。根据工具的名称和描述，推断它属于哪些业务能力类别。

工具信息：
- 名称：{self.name}
- 描述：{self.description}

可选能力类别：
{capabilities_desc}

要求：
1. 根据工具的功能和用途，选择最匹配的 1-3 个能力类别
2. 只返回能力 ID，用逗号分隔
3. 如果不确定，返回最相关的 1 个
4. 只输出能力 ID，不要额外解释

输出格式示例：chart_generation,data_visualization"""

            # 调用 LLM
            # 🆕 使用配置化的 LLM Profile
            from config.llm_config import get_llm_profile
            profile = get_llm_profile("tool_capability_inference")
            llm_service = create_llm_service(**profile)
            response = llm_service.create_message(
                messages=[{"role": "user", "content": prompt}]
            )
            
            # 解析响应
            if hasattr(response, 'content') and response.content:
                content = response.content[0].text if isinstance(response.content, list) else response.content
                # 提取能力 ID
                capability_ids = [
                    cap.strip() 
                    for cap in content.strip().split(',')
                    if cap.strip() in business_capabilities
                ]
                
                if capability_ids:
                    logger.info(f"🤖 LLM 推断工具 {self.name} 的能力: {capability_ids}")
                    return capability_ids
        
        except Exception as e:
            logger.debug(f"LLM 推断失败: {str(e)}")
        
        return []
    
    def _keyword_based_fallback(self) -> List[str]:
        """
        V5.0: 保守默认值（不做关键词猜测）
        
        V5.0 策略：
        - 不使用关键词映射
        - 返回空列表，让系统使用通用路由
        - 能力应由 instance 的 config.yaml 显式配置
        
        Returns:
            空列表（保守默认值）
        """
        logger.info(f"⚠️ 工具 {self.name} 使用保守默认值（LLM 推断失败）")
        return []  # V5.0: 不做关键词猜测


class InstanceToolRegistry:
    """
    实例级工具注册表
    
    管理一个 Agent 实例的所有动态工具（MCP、REST API）
    与全局 CapabilityRegistry 协同工作
    
    🆕 V4.6: 支持 LLM 驱动的批量能力推断 + 缓存机制
    """
    
    def __init__(self, global_registry=None):
        """
        初始化实例工具注册表
        
        Args:
            global_registry: 全局 CapabilityRegistry（可选）
        """
        self._tools: Dict[str, InstanceTool] = {}
        self._mcp_clients: Dict[str, Any] = {}  # 缓存 MCP 客户端
        self._global_registry = global_registry
        self._inference_cache: Dict[str, List[str]] = {}  # 工具能力推断缓存 {tool_hash: capabilities}
    
    # ==================== 注册接口 ====================
    
    def register(self, tool: InstanceTool):
        """
        注册实例级工具
        
        Args:
            tool: InstanceTool 实例
        """
        self._tools[tool.name] = tool
        logger.info(f"📦 注册实例工具: {tool.name} ({tool.type.value})")
    
    async     def register_mcp_tool(
        self,
        name: str,
        server_url: str,
        server_name: str,
        tool_info: Dict[str, Any],
        mcp_client: Any,
        handler: Callable[..., Awaitable[Any]],
        capability: Optional[str] = None  # 🆕 V4.6: 能力类别
    ):
        """
        注册 MCP 工具
        
        Args:
            name: 工具名称（已命名空间化）
            server_url: MCP 服务器 URL
            server_name: 服务器名称
            tool_info: MCP 工具信息
            mcp_client: MCP 客户端实例
            handler: 工具调用处理器
            capability: 🆕 能力类别（用户意图分类，如 document_creation）
        """
        # 🆕 V4.6: 如果没有显式指定 capability，从缓存中查找
        if not capability:
            tool_hash = self._compute_tool_hash(name, tool_info.get("description", ""))
            cached_capabilities = self._inference_cache.get(tool_hash, [])
            if cached_capabilities:
                capability = cached_capabilities[0]  # 使用缓存的第一个能力
                logger.debug(f"   从缓存获取能力: {capability}")
        
        # 🔍 获取并验证 input_schema
        input_schema = tool_info.get("input_schema", {})
        if not input_schema or not isinstance(input_schema, dict):
            input_schema = {}
            logger.warning(f"⚠️ MCP 工具 {name} 没有 input_schema")
        else:
            # 记录 schema 参数信息，便于调试
            props = input_schema.get("properties", {})
            if props:
                logger.info(f"   📋 input_schema 参数: {list(props.keys())}")
            else:
                logger.debug(f"   📋 input_schema 为空或无 properties")
        
        tool = InstanceTool(
            name=name,
            type=InstanceToolType.MCP,
            description=tool_info.get("description", ""),
            input_schema=input_schema,
            capability=capability,  # 🆕 传递 capability
            server_url=server_url,
            server_name=server_name,
            original_name=tool_info.get("name"),
            mcp_client=mcp_client,
            handler=handler
        )
        self.register(tool)
        
        # 如果有 capability，记录日志
        if capability:
            logger.info(f"   📌 能力类别: {capability}")
        
        # 🆕 V4.6: 将推断结果存入缓存（用于后续保存）
        if not capability:
            # 触发推断（InstanceTool 的 _infer_capabilities 会被调用）
            inferred = tool._infer_capabilities()
            if inferred:
                tool_hash = self._compute_tool_hash(name, tool.description)
                self._inference_cache[tool_hash] = inferred
                logger.debug(f"   推断并缓存能力: {inferred}")
        
        # 缓存 MCP 客户端
        self._mcp_clients[server_url] = mcp_client
    
    def register_rest_api(
        self,
        name: str,
        base_url: str,
        description: str,
        api_doc: str,
        capability: Optional[str] = None  # 🆕 V4.6: 能力类别
    ):
        """
        注册 REST API
        
        Args:
            name: API 名称
            base_url: 基础 URL
            description: 描述
            api_doc: API 文档内容
            capability: 🆕 能力类别（用户意图分类）
        """
        tool_name = f"api_{name}"
        
        # 🆕 V4.6: 如果没有显式指定 capability，从缓存中查找
        if not capability:
            tool_hash = self._compute_tool_hash(tool_name, description)
            cached_capabilities = self._inference_cache.get(tool_hash, [])
            if cached_capabilities:
                capability = cached_capabilities[0]  # 使用缓存的第一个能力
                logger.debug(f"   从缓存获取能力: {capability}")
        
        tool = InstanceTool(
            name=tool_name,
            type=InstanceToolType.REST_API,
            description=description,
            capability=capability,  # 🆕 传递 capability
            base_url=base_url,
            api_doc=api_doc,
            input_schema={
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "description": "API 端点"},
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                    "body": {"type": "object", "description": "请求体"}
                },
                "required": ["endpoint"]
            }
        )
        self.register(tool)
        
        # 如果有 capability，记录日志
        if capability:
            logger.info(f"   📌 能力类别: {capability}")
        
        # 🆕 V4.6: 将推断结果存入缓存（用于后续保存）
        if not capability:
            # 触发推断
            inferred = tool._infer_capabilities()
            if inferred:
                tool_hash = self._compute_tool_hash(tool_name, description)
                self._inference_cache[tool_hash] = inferred
                logger.debug(f"   推断并缓存能力: {inferred}")
    
    # ==================== 查询接口 ====================
    
    def get(self, name: str) -> Optional[InstanceTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def get_all(self) -> List[InstanceTool]:
        """获取所有实例工具"""
        return list(self._tools.values())
    
    def get_by_type(self, tool_type: InstanceToolType) -> List[InstanceTool]:
        """按类型获取工具"""
        return [t for t in self._tools.values() if t.type == tool_type]
    
    def get_by_capability(self, capability: str) -> List[InstanceTool]:
        """
        🆕 V4.6: 按能力类别获取工具
        
        Args:
            capability: 能力类别，如 document_creation, web_search
            
        Returns:
            匹配该能力类别的工具列表
        """
        return [
            t for t in self._tools.values() 
            if t.capability == capability or capability in t._infer_capabilities()
        ]
    
    def get_mcp_client(self, server_url: str) -> Optional[Any]:
        """获取缓存的 MCP 客户端"""
        return self._mcp_clients.get(server_url)
    
    # ==================== 工具发现接口 ====================
    
    def get_tools_for_claude(self) -> List[Dict[str, Any]]:
        """
        获取 Claude API 格式的工具列表
        
        Returns:
            Claude API 兼容的工具定义列表
        """
        tools = []
        for t in self._tools.values():
            tool_def = t.to_claude_tool()
            # 🔍 调试：显示每个工具的 schema
            schema = tool_def.get("input_schema", {})
            props = schema.get("properties", {}) if isinstance(schema, dict) else {}
            logger.info(f"📤 Claude 工具: {tool_def['name']} -> 参数: {list(props.keys()) if props else '(无)'}")
            tools.append(tool_def)
        return tools
    
    def get_tools_for_discovery(self) -> List[Dict[str, Any]]:
        """
        获取用于工具发现的列表（与 capabilities.yaml 格式兼容）
        
        用于 Plan 阶段的 discover_tools()
        
        Returns:
            Capability 兼容格式的工具列表
        """
        return [t.to_capability_dict() for t in self._tools.values()]
    
    def get_all_tools_unified(self) -> List[Dict[str, Any]]:
        """
        获取统一格式的所有工具（全局 + 实例）
        
        Returns:
            合并后的工具列表，用于 Plan 阶段工具发现
        """
        tools = []
        
        # 1. 添加全局工具
        if self._global_registry:
            from core.tool.capability import CapabilityType
            
            for cap in self._global_registry.capabilities.values():
                # 只包含 TOOL 类型（SKILL 走不同路径）
                if cap.type == CapabilityType.TOOL:
                    tools.append({
                        "name": cap.name,
                        "type": "TOOL",
                        "subtype": cap.subtype,
                        "provider": cap.provider,
                        "description": cap.metadata.get("description", ""),
                        "capabilities": cap.capabilities,
                        "priority": cap.priority,
                        "source": "global"
                    })
        
        # 2. 添加实例工具
        for tool in self._tools.values():
            tools.append({
                "name": tool.name,
                "type": "TOOL",
                "subtype": tool.type.value,
                "provider": tool.server_name or "instance",
                "description": tool.description,
                "capabilities": tool._infer_capabilities(),
                "priority": 80,
                "source": "instance"
            })
        
        return tools
    
    # ==================== 调用接口 ====================
    
    async def invoke(self, tool_name: str, **kwargs) -> Any:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            **kwargs: 工具参数
            
        Returns:
            工具执行结果
        """
        tool = self.get(tool_name)
        if not tool:
            raise ValueError(f"工具不存在: {tool_name}")
        
        if not tool.handler:
            raise ValueError(f"工具没有配置处理器: {tool_name}")
        
        return await tool.handler(**kwargs)
    
    # ==================== 信息接口 ====================
    
    def summary(self) -> str:
        """生成摘要"""
        mcp_count = len(self.get_by_type(InstanceToolType.MCP))
        api_count = len(self.get_by_type(InstanceToolType.REST_API))
        return f"InstanceToolRegistry: {mcp_count} MCP工具, {api_count} REST APIs"
    
    def list_tool_names(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    # ==================== 缓存管理（🆕 V4.6）====================
    
    async def load_inference_cache(self, cache_path) -> bool:
        """
        异步加载工具推断缓存
        
        Args:
            cache_path: 缓存文件路径（Path 对象或字符串）
            
        Returns:
            成功返回 True
        """
        cache_file = Path(cache_path)
        if not cache_file.exists():
            logger.debug(f"工具推断缓存文件不存在: {cache_file}")
            return False
        
        try:
            async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                self._inference_cache = json.loads(content)
            logger.info(f"✅ 加载工具推断缓存: {len(self._inference_cache)} 个工具")
            return True
        except Exception as e:
            logger.error(f"加载工具推断缓存失败: {str(e)}")
            return False
    
    async def save_inference_cache(self, cache_path) -> bool:
        """
        异步保存工具推断缓存
        
        Args:
            cache_path: 缓存文件路径（Path 对象或字符串）
            
        Returns:
            成功返回 True
        """
        cache_file = Path(cache_path)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            async with aiofiles.open(cache_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(self._inference_cache, indent=2, ensure_ascii=False))
            logger.info(f"✅ 保存工具推断缓存: {len(self._inference_cache)} 个工具")
            return True
        except Exception as e:
            logger.error(f"保存工具推断缓存失败: {str(e)}")
            return False
    
    def _compute_tool_hash(self, tool_name: str, tool_description: str) -> str:
        """
        计算工具的 hash（用于缓存 key）
        
        Args:
            tool_name: 工具名称
            tool_description: 工具描述
            
        Returns:
            hash 字符串
        """
        import hashlib
        content = f"{tool_name}|{tool_description}"
        hasher = hashlib.sha256(content.encode('utf-8'))
        return f"sha256:{hasher.hexdigest()}"


# ==================== 便捷函数 ====================

def create_instance_registry(global_registry=None) -> InstanceToolRegistry:
    """
    创建实例工具注册表
    
    Args:
        global_registry: 全局 CapabilityRegistry
        
    Returns:
        InstanceToolRegistry 实例
    """
    return InstanceToolRegistry(global_registry=global_registry)
