"""
SandboxWorker - 代码执行沙箱 Worker

将 E2B/Aliyun FC 等代码执行环境作为专业 Worker

适用场景：
1. 数据分析任务（Pandas、NumPy）
2. 代码生成与验证
3. 文件处理（PDF、Excel 等）
4. 需要隔离执行环境的任务

参考：
- E2B: https://e2b.dev/docs
- Aliyun FC: https://www.alibabacloud.com/product/function-compute
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .base import BaseWorker, WorkerType, WorkerInput, WorkerOutput, WorkerStatus

logger = logging.getLogger(__name__)


class SandboxWorker(BaseWorker):
    """
    Sandbox Worker - 使用代码执行沙箱完成任务
    
    支持后端：
    - e2b: E2B Sandbox（推荐，Firecracker MicroVM）
    - aliyun_fc: 阿里云函数计算
    - local: 本地 Docker 容器（开发用）
    
    工作流程：
    1. Orchestrator 发送代码生成任务
    2. SandboxWorker 调用 LLM 生成代码
    3. 在沙箱中执行代码
    4. 返回执行结果和产出物
    
    Example:
        worker = SandboxWorker(
            name="data-analyst",
            backend="e2b",
            specialization="data_analysis",
            template="data-science"  # E2B 预置模板
        )
        
        result = await worker.execute(WorkerInput(
            task_id="task-1",
            action="分析 sales.csv 数据，生成趋势图"
        ))
    
    配置示例 (worker_registry.yaml):
        workers:
          - name: data-analyst
            type: sandbox
            backend: e2b
            template: data-science
            specialization: data_analysis
            timeout: 300
    """
    
    def __init__(
        self,
        name: str,
        backend: str = "e2b",  # e2b / aliyun_fc / local
        template: str = None,  # 沙箱模板
        specialization: str = "code_execution",
        timeout: int = 300,
        model: str = "claude-sonnet-4-5-20250929",
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            name=name,
            worker_type=WorkerType.AGENT,  # 底层还是 Agent + 沙箱执行
            specialization=specialization,
            config=config
        )
        
        self.backend = backend
        self.template = template
        self.timeout = timeout
        self.model = model
        
        self._sandbox = None
        self._agent = None
        
        logger.info(f"SandboxWorker 初始化: {name} (后端: {backend})")
    
    async def _get_or_create_sandbox(self):
        """获取或创建沙箱实例"""
        if self._sandbox is None:
            if self.backend == "e2b":
                from services.sandbox_service import E2BSandboxService
                self._sandbox = E2BSandboxService(template=self.template)
                await self._sandbox.create()
            elif self.backend == "aliyun_fc":
                from services.sandbox_service import AliyunFCSandboxService
                self._sandbox = AliyunFCSandboxService()
            else:
                raise ValueError(f"不支持的沙箱后端: {self.backend}")
            
            logger.info(f"SandboxWorker '{self.name}' 沙箱已创建 ({self.backend})")
        
        return self._sandbox
    
    def _get_or_create_agent(self):
        """获取代码生成 Agent"""
        if self._agent is None:
            from core.agent import SimpleAgent
            
            # 代码生成专用 system prompt
            system_prompt = self._build_code_gen_prompt()
            
            self._agent = SimpleAgent(
                model=self.model,
                system_prompt=system_prompt
            )
        
        return self._agent
    
    def _build_code_gen_prompt(self) -> str:
        """构建代码生成 system prompt"""
        return """你是一个代码生成专家，专注于数据分析和自动化任务。

## 核心原则
1. 生成简洁、可执行的 Python 代码
2. 使用标准库和常用包（pandas, numpy, matplotlib 等）
3. 代码需要完整，可以直接运行
4. 处理边界情况和错误

## 输出格式
请将代码包裹在 ```python 代码块中。

## 可用环境
- Python 3.10+
- pandas, numpy, matplotlib, seaborn
- requests, beautifulsoup4
- openpyxl, python-pptx, reportlab

## 注意事项
- 文件保存到当前目录
- 图片使用 plt.savefig() 保存
- 输出结果使用 print() 显示
"""
    
    async def execute(self, input: WorkerInput) -> WorkerOutput:
        """
        执行沙箱任务
        
        流程：
        1. LLM 生成代码
        2. 在沙箱中执行
        3. 收集结果和产出物
        """
        start_time = datetime.now()
        
        try:
            logger.info(f"SandboxWorker '{self.name}' 开始任务: {input.action[:50]}...")
            
            # 1. 生成代码
            code = await self._generate_code(input)
            
            if not code:
                return WorkerOutput(
                    task_id=input.task_id,
                    status=WorkerStatus.FAILED,
                    error="代码生成失败"
                )
            
            # 2. 在沙箱中执行
            sandbox = await self._get_or_create_sandbox()
            execution_result = await sandbox.run_code(
                code=code,
                timeout=self.timeout
            )
            
            # 3. 收集产出物
            artifacts = await self._collect_artifacts(sandbox)
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # 判断执行状态
            if execution_result.get("error"):
                logger.warning(f"SandboxWorker '{self.name}' 代码执行有错误: {execution_result['error']}")
                
                return WorkerOutput(
                    task_id=input.task_id,
                    status=WorkerStatus.FAILED,
                    result=execution_result.get("output", ""),
                    error=execution_result.get("error"),
                    artifacts=artifacts,
                    duration=duration,
                    metadata={
                        "backend": self.backend,
                        "code": code,
                        "worker_type": "sandbox"
                    }
                )
            
            logger.info(f"SandboxWorker '{self.name}' 完成，耗时 {duration:.1f}s")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.COMPLETED,
                result=execution_result.get("output", ""),
                artifacts=artifacts,
                duration=duration,
                metadata={
                    "backend": self.backend,
                    "code": code,
                    "worker_type": "sandbox"
                }
            )
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"SandboxWorker '{self.name}' 执行失败: {e}")
            
            return WorkerOutput(
                task_id=input.task_id,
                status=WorkerStatus.FAILED,
                error=str(e),
                duration=duration
            )
    
    async def _generate_code(self, input: WorkerInput) -> Optional[str]:
        """使用 LLM 生成代码"""
        agent = self._get_or_create_agent()
        
        # 构建代码生成提示
        prompt = f"""请为以下任务生成 Python 代码：

## 任务
{input.action}

## 上下文
{json.dumps(input.context, ensure_ascii=False) if input.context else "无"}

## 前置任务结果
{json.dumps(input.dependencies_results, ensure_ascii=False) if input.dependencies_results else "无"}

请生成完整、可执行的代码。
"""
        
        # 调用 Agent 生成代码
        response = ""
        async for event in agent.chat(
            user_input=prompt,
            session_id=f"sandbox-code-gen-{input.task_id}"
        ):
            if event.get("type") == "content_delta":
                delta = event.get("data", {}).get("delta", "")
                if isinstance(delta, str):
                    response += delta
        
        # 提取代码块
        return self._extract_code(response)
    
    def _extract_code(self, response: str) -> Optional[str]:
        """从响应中提取代码块"""
        import re
        
        # 匹配 ```python ... ``` 代码块
        pattern = r'```python\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # 尝试匹配 ``` ... ``` 代码块
        pattern = r'```\s*(.*?)\s*```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        return None
    
    async def _collect_artifacts(self, sandbox) -> List[Dict]:
        """收集沙箱中的产出物"""
        artifacts = []
        
        try:
            # 列出沙箱中的文件
            files = await sandbox.list_files("./")
            
            for file_info in files:
                if file_info.get("type") == "file":
                    name = file_info.get("name", "")
                    # 收集常见产出物类型
                    if name.endswith((".png", ".jpg", ".pdf", ".xlsx", ".csv", ".html")):
                        artifacts.append({
                            "type": "file",
                            "name": name,
                            "path": file_info.get("path", f"./{name}"),
                            "size": file_info.get("size", 0)
                        })
        except Exception as e:
            logger.warning(f"收集产出物失败: {e}")
        
        return artifacts
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            sandbox = await self._get_or_create_sandbox()
            return sandbox is not None
        except Exception:
            return False
