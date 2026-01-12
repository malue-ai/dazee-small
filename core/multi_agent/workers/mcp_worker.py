"""
MCPWorker - MCP Server Worker

通过 MCP (Model Context Protocol) 调用远程服务作为 Worker

支持场景：
1. 远程部署的专业 Agent 服务
2. 第三方 MCP 兼容服务
3. Dify 平台的 MCP Server
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseWorker, WorkerType, WorkerInput, WorkerOutput, WorkerStatus

logger = logging.getLogger(__name__)


class MCPWorker(BaseWorker):
    """
    MCP Worker - 通过 MCP 协议调用远程服务
    
    MCP (Model Context Protocol) 是 Anthropic 提出的标准协议，
    用于 LLM 与外部工具/服务之间的通信。
    
    Dify 平台已原生支持 MCP Server 模式。
    
    Example:
        worker = MCPWorker(
            name="dify-data-analyst",
            specialization="data_analysis",
            server_url="https://api.dify.ai/mcp/server/xxx/mcp",
            auth_token="sk-xxx"
        )
        
        result = await worker.execute(WorkerInput(
            task_id="task-1",
            action="分析销售数据趋势"
        ))
    
    配置示例 (config.yaml):
        workers:
          - name: dify-analyst
            type: mcp
            specialization: data_analysis
            server_url: "https://api.dify.ai/mcp/server/xxx/mcp"
            auth_type: bearer
            auth_env: DIFY_API_KEY
    """
    
    def __init__(
        self,
        name: str,
        server_url: str,
        specialization: str = "general",
        server_name: str = None,
        auth_type: str = "bearer",  # none / bearer / api_key
        auth_token: str = None,
        auth_env: str = None,  # 从环境变量读取
        timeout: int = 60,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name=name,
            worker_type=WorkerType.MCP,
            specialization=specialization,
            config=config
        )
        
        self.server_url = server_url
        self.server_name = server_name or name
        self.auth_type = auth_type
        self.timeout = timeout
        
        # 处理认证
        self.auth_token = auth_token
        if auth_env and not auth_token:
            import os
            self.auth_token = os.getenv(auth_env)
        
        self._client = None
        
        logger.info(f"MCPWorker 初始化: {name} -> {server_url}")
    
    async def _get_or_create_client(self):
        """获取或创建 MCP 客户端"""
        if self._client is None:
            # 使用 ZenFlux 的 MCP 客户端
            from services.mcp_client import MCPClient
            
            self._client = MCPClient(
                server_url=self.server_url,
                server_name=self.server_name,
                auth_type=self.auth_type,
                auth_token=self.auth_token
            )
            
            # 初始化连接
            await self._client.initialize()
            
            logger.info(f"MCPWorker '{self.name}' MCP 客户端已连接")
        
        return self._client
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        通过 MCP 协议执行任务
        
        MCP 执行流程：
        1. 连接 MCP Server
        2. 发送 tools/call 请求
        3. 等待响应
        4. 解析结果
        """
        start_time = datetime.now()
        
        try:
            client = await self._get_or_create_client()
            
            logger.info(f"MCPWorker '{self.name}' 调用 MCP Server: {input.action[:50]}...")
            
            # 构建 MCP 请求
            # MCP 协议：使用 tools/call 方法
            request_params = {
                "name": "execute_task",  # MCP Server 需要实现的工具名
                "arguments": {
                    "task": input.action,
                    "context": input.context,
                    "dependencies": input.dependencies_results
                }
            }
            
            # 调用 MCP Server
            response = await client.call_tool(
                tool_name=request_params["name"],
                arguments=request_params["arguments"],
                timeout=input.timeout
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # 解析响应
            if response.get("error"):
                return WorkerOutput(
                    task_id=input.task_id,
                    status=WorkerStatus.FAILED,
                    error=response.get("error", {}).get("message", "未知错误"),
                    duration=duration,
                    metadata={"server_url": self.server_url}
                )
            
            result = response.get("result", {})
            
            logger.info(f"MCPWorker '{self.name}' MCP 调用完成，耗时 {duration:.1f}s")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.COMPLETED,
                result=result.get("content") or result,
                artifacts=result.get("artifacts", []),
                duration=duration,
                metadata={
                    "server_url": self.server_url,
                    "worker_type": "mcp"
                }
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"MCPWorker '{self.name}' MCP 调用失败: {e}")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=duration
            )
    
    async def health_check(self) -> bool:
        """健康检查 - 尝试连接 MCP Server"""
        try:
            client = await self._get_or_create_client()
            # MCP 协议：使用 ping 或 list_tools 验证连接
            tools = await client.list_tools()
            return len(tools) > 0
        except Exception as e:
            logger.warning(f"MCPWorker '{self.name}' 健康检查失败: {e}")
            return False
    
    async def list_available_tools(self) -> List[Dict]:
        """列出 MCP Server 提供的工具"""
        try:
            client = await self._get_or_create_client()
            return await client.list_tools()
        except Exception:
            return []
