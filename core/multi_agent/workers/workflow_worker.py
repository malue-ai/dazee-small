"""
WorkflowWorker - Workflow 平台 Worker

支持调用 Coze、Dify 等平台的 Workflow 作为 Worker

支持平台：
1. Coze（字节跳动）
2. Dify
3. Langflow
4. 其他支持 HTTP API 的 Workflow 平台
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from .base import BaseWorker, WorkerType, WorkerInput, WorkerOutput, WorkerStatus

logger = logging.getLogger(__name__)


class WorkflowPlatform(Enum):
    """Workflow 平台类型"""
    COZE = "coze"
    DIFY = "dify"
    LANGFLOW = "langflow"
    CUSTOM = "custom"  # 自定义 HTTP API


class WorkflowWorker(BaseWorker):
    """
    Workflow Worker - 调用外部 Workflow 平台
    
    支持将 Coze、Dify 等平台的 Workflow 作为 Multi-Agent 的 Worker。
    
    优势：
    1. 运营可在可视化平台配置复杂 Workflow
    2. 利用平台的成熟能力（知识库、插件等）
    3. 降低开发成本
    
    Example (Coze):
        worker = WorkflowWorker(
            name="coze-research",
            platform=WorkflowPlatform.COZE,
            workflow_id="7xxxxxxxxx",
            api_key="pat_xxxxx",
            specialization="research"
        )
    
    Example (Dify):
        worker = WorkflowWorker(
            name="dify-analyst",
            platform=WorkflowPlatform.DIFY,
            workflow_url="https://api.dify.ai/v1/workflows/run",
            api_key="app-xxxxx",
            specialization="data_analysis"
        )
    
    配置示例 (config.yaml):
        workers:
          - name: coze-research
            type: workflow
            platform: coze
            workflow_id: "7xxxxxxxxx"
            auth_env: COZE_API_KEY
            specialization: research
    """
    
    # 平台 API 端点
    PLATFORM_ENDPOINTS = {
        WorkflowPlatform.COZE: "https://api.coze.cn/v1/workflow/run",
        WorkflowPlatform.DIFY: "{base_url}/v1/workflows/run",
    }
    
    def __init__(
        self,
        name: str,
        platform: WorkflowPlatform = WorkflowPlatform.CUSTOM,
        workflow_id: str = None,
        workflow_url: str = None,
        base_url: str = None,
        api_key: str = None,
        api_key_env: str = None,
        specialization: str = "general",
        timeout: int = 120,
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name=name,
            worker_type=WorkerType.WORKFLOW,
            specialization=specialization,
            config=config
        )
        
        self.platform = platform
        self.workflow_id = workflow_id
        self.timeout = timeout
        
        # 处理 API Key
        self.api_key = api_key
        if api_key_env and not api_key:
            import os
            self.api_key = os.getenv(api_key_env)
        
        # 构建 Workflow URL
        self.workflow_url = self._build_workflow_url(workflow_url, base_url)
        
        logger.info(f"WorkflowWorker 初始化: {name} (平台: {platform.value})")
    
    def _build_workflow_url(self, workflow_url: str, base_url: str) -> str:
        """构建 Workflow URL"""
        if workflow_url:
            return workflow_url
        
        if self.platform == WorkflowPlatform.COZE:
            return self.PLATFORM_ENDPOINTS[WorkflowPlatform.COZE]
        
        if self.platform == WorkflowPlatform.DIFY:
            base = base_url or "https://api.dify.ai"
            return self.PLATFORM_ENDPOINTS[WorkflowPlatform.DIFY].format(base_url=base)
        
        raise ValueError(f"平台 {self.platform} 需要提供 workflow_url")
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        执行 Workflow
        
        根据平台类型调用对应的 API
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"WorkflowWorker '{self.name}' 调用 Workflow: {input.action[:50]}...")
            
            # 根据平台构建请求
            if self.platform == WorkflowPlatform.COZE:
                result = await self._execute_coze(input)
            elif self.platform == WorkflowPlatform.DIFY:
                result = await self._execute_dify(input)
            else:
                result = await self._execute_custom(input)
            
            duration = (datetime.now() - start_time).total_seconds()
            result.duration = duration
            
            logger.info(f"WorkflowWorker '{self.name}' Workflow 完成，耗时 {duration:.1f}s")
            
            return result
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"WorkflowWorker '{self.name}' Workflow 调用失败: {e}")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=duration
            )
    
    async def _execute_coze(self, input: WorkerInput) -> WorkerOutput:
        """
        执行 Coze Workflow
        
        Coze API 文档：https://www.coze.cn/docs/developer_guides/workflow_run
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Coze Workflow 请求格式
        payload = {
            "workflow_id": self.workflow_id,
            "parameters": {
                "task": input.action,
                "context": json.dumps(input.context, ensure_ascii=False),
                "dependencies": json.dumps(input.dependencies_results, ensure_ascii=False)
            }
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.workflow_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
        
        # 解析 Coze 响应
        if data.get("code") != 0:
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=data.get("msg", "Coze Workflow 执行失败")
            )
        
        result_data = data.get("data", "")
        
        return WorkerOutput(
            task_id=input.task_id,
            status=WorkerStatus.COMPLETED,
            result=result_data,
            metadata={
                "platform": "coze",
                "workflow_id": self.workflow_id,
                "debug_url": data.get("debug_url")
            }
        )
    
    async def _execute_dify(self, input: WorkerInput) -> WorkerOutput:
        """
        执行 Dify Workflow
        
        Dify API 文档：https://docs.dify.ai/v/zh-hans/guides/workflow/api
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Dify Workflow 请求格式
        payload = {
            "inputs": {
                "task": input.action,
                "context": json.dumps(input.context, ensure_ascii=False),
                "dependencies": json.dumps(input.dependencies_results, ensure_ascii=False)
            },
            "response_mode": "blocking",  # 或 "streaming"
            "user": f"worker-{self.name}"
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.workflow_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
        
        # 解析 Dify 响应
        if data.get("status") == "failed":
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=data.get("error", "Dify Workflow 执行失败")
            )
        
        outputs = data.get("data", {}).get("outputs", {})
        result_text = outputs.get("text") or outputs.get("result") or json.dumps(outputs)
        
        return WorkerOutput(
            task_id=input.task_id,
            status=WorkerStatus.COMPLETED,
            result=result_text,
            metadata={
                "platform": "dify",
                "workflow_run_id": data.get("workflow_run_id"),
                "total_tokens": data.get("data", {}).get("total_tokens", 0)
            }
        )
    
    async def _execute_custom(self, input: WorkerInput) -> WorkerOutput:
        """
        执行自定义 HTTP Workflow
        
        通用格式：POST 请求，JSON body
        """
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {
            "task_id": input.task_id,
            "action": input.action,
            "context": input.context,
            "dependencies_results": input.dependencies_results
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.workflow_url,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
        
        return WorkerOutput(
            task_id=input.task_id,
            status=WorkerStatus.COMPLETED if data.get("success", True) else WorkerStatus.FAILED,
            result=data.get("result"),
            error=data.get("error"),
            metadata={
                "platform": "custom",
                "workflow_url": self.workflow_url
            }
        )
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 简单的连接测试
            async with httpx.AsyncClient(timeout=10) as client:
                # 尝试 HEAD 请求
                response = await client.head(self.workflow_url)
                return response.status_code < 500
        except Exception:
            return False
