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

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable
from enum import Enum

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
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema or {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "输入内容"
                    }
                },
                "required": ["query"]
            }
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
        🆕 V4.6 自动推断能力类别
        
        设计原则：
        - FDE 无需手动配置 capability，框架自动推断
        - 如果显式配置了 capability，则使用配置值（覆盖推断）
        - 基于工具名称和描述进行关键词匹配
        
        Returns:
            推断出的能力类别列表（与 capability_categories 中的 ID 对应）
        """
        # 1. 优先使用显式配置的 capability（覆盖推断）
        if self.capability:
            return [self.capability]
        
        # 2. 自动推断：基于名称和描述的关键词匹配
        name_lower = self.name.lower()
        desc_lower = self.description.lower()
        text = f"{name_lower} {desc_lower}"
        
        capabilities = []
        
        # ===== 内容生成类 =====
        # 图表生成（flowchart, 架构图, 思维导图）
        if any(kw in text for kw in [
            "flowchart", "chart", "diagram", "graph", "架构图", "流程图", 
            "思维导图", "mindmap", "关系图", "uml", "er图"
        ]):
            capabilities.append("chart_generation")
        
        # PPT 生成
        if any(kw in text for kw in [
            "ppt", "powerpoint", "slides", "presentation", "演示", "幻灯片"
        ]):
            capabilities.append("ppt_generation")
        
        # 文档生成（Word/PDF/报告）
        if any(kw in text for kw in [
            "document", "word", "pdf", "report", "文档", "报告", "合同", "说明书"
        ]):
            capabilities.append("document_creation")
        
        # 图片生成
        if any(kw in text for kw in [
            "image", "picture", "photo", "图片", "生成图", "ai绘画", "dalle", "midjourney"
        ]):
            capabilities.append("image_generation")
        
        # 视频生成
        if any(kw in text for kw in [
            "video", "视频", "动画", "animation"
        ]):
            capabilities.append("video_generation")
        
        # ===== 信息获取类 =====
        # 互联网搜索
        if any(kw in text for kw in [
            "search", "搜索", "查询", "检索", "google", "bing"
        ]):
            capabilities.append("web_search")
        
        # 新闻搜索
        if any(kw in text for kw in [
            "news", "新闻", "资讯", "热点", "动态"
        ]):
            capabilities.append("news_search")
        
        # 学术搜索
        if any(kw in text for kw in [
            "paper", "academic", "论文", "学术", "研究", "arxiv", "scholar"
        ]):
            capabilities.append("academic_search")
        
        # 市场数据
        if any(kw in text for kw in [
            "market", "stock", "finance", "市场", "股票", "金融", "财务"
        ]):
            capabilities.append("market_data")
        
        # ===== 数据处理类 =====
        # 数据分析
        if any(kw in text for kw in [
            "analysis", "analyze", "分析", "统计", "excel", "数据处理"
        ]):
            capabilities.append("data_analysis")
        
        # 数据可视化
        if any(kw in text for kw in [
            "visualization", "可视化", "图表", "dashboard", "报表"
        ]):
            capabilities.append("data_visualization")
        
        # 文件转换
        if any(kw in text for kw in [
            "convert", "转换", "格式转换", "pdf转", "转pdf"
        ]):
            capabilities.append("file_conversion")
        
        # ===== 业务集成类 =====
        # CRM
        if any(kw in text for kw in [
            "crm", "客户", "销售", "salesforce", "hubspot"
        ]):
            capabilities.append("crm_integration")
        
        # ERP
        if any(kw in text for kw in [
            "erp", "库存", "订单", "sap", "oracle"
        ]):
            capabilities.append("erp_integration")
        
        # 消息通知
        if any(kw in text for kw in [
            "email", "sms", "notification", "邮件", "短信", "钉钉", "飞书", "微信"
        ]):
            capabilities.append("notification")
        
        # 3. 如果没有匹配到任何能力，返回空列表（让框架使用默认行为）
        # 不再默认返回 api_calling，因为那是内部实现手段
        return capabilities


class InstanceToolRegistry:
    """
    实例级工具注册表
    
    管理一个 Agent 实例的所有动态工具（MCP、REST API）
    与全局 CapabilityRegistry 协同工作
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
    
    # ==================== 注册接口 ====================
    
    def register(self, tool: InstanceTool):
        """
        注册实例级工具
        
        Args:
            tool: InstanceTool 实例
        """
        self._tools[tool.name] = tool
        logger.info(f"📦 注册实例工具: {tool.name} ({tool.type.value})")
    
    async def register_mcp_tool(
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
        tool = InstanceTool(
            name=name,
            type=InstanceToolType.MCP,
            description=tool_info.get("description", ""),
            input_schema=tool_info.get("input_schema", {}),
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
        tool = InstanceTool(
            name=f"api_{name}",
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
        return [t.to_claude_tool() for t in self._tools.values()]
    
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
