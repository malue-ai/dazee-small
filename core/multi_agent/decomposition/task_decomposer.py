"""
任务分解器

使用 LLM 语义分解复杂任务为子任务

设计原则（Prompt-First）：
- 使用 Few-shot 引导 LLM 分解
- 代码只做调用和解析
- 复用 SemanticInference 基础设施
"""

import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

from logger import get_logger
from ..fsm.states import SubTaskState, SubTaskStatus
from .prompts import DECOMPOSITION_FEW_SHOT, WORKER_PROMPT_FEW_SHOT

logger = get_logger("task_decomposer")


@dataclass
class DecompositionResult:
    """任务分解结果"""
    success: bool
    reasoning: str
    sub_tasks: List[SubTaskState]
    parallelizable_groups: List[List[str]]
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "reasoning": self.reasoning,
            "sub_tasks": [st.to_dict() for st in self.sub_tasks],
            "parallelizable_groups": self.parallelizable_groups,
            "error": self.error
        }


@dataclass 
class WorkerPromptResult:
    """Worker 提示词生成结果"""
    success: bool
    reasoning: str
    system_prompt: str
    error: Optional[str] = None


class TaskDecomposer:
    """
    任务分解器
    
    使用 LLM 语义分解任务，遵循 Prompt-First 原则
    
    使用示例：
        decomposer = TaskDecomposer(llm_service=claude_service)
        
        result = await decomposer.decompose(
            user_query="重构代码并补充测试"
        )
        
        for sub_task in result.sub_tasks:
            print(f"{sub_task.id}: {sub_task.action}")
    """
    
    def __init__(
        self,
        llm_service=None,           # Claude/LLM 服务
        model: str = "claude-haiku-4-5-20250514",  # 使用快速模型分解
        decomposition_prompt: str = None,
        worker_prompt_template: str = None
    ):
        """
        初始化任务分解器
        
        Args:
            llm_service: LLM 服务实例
            model: 使用的模型（分解用 Haiku 快且便宜）
            decomposition_prompt: 自定义分解提示词
            worker_prompt_template: 自定义 Worker 提示词模板
        """
        self.llm_service = llm_service
        self.model = model
        self.decomposition_prompt = decomposition_prompt or DECOMPOSITION_FEW_SHOT
        self.worker_prompt_template = worker_prompt_template or WORKER_PROMPT_FEW_SHOT
        
        logger.info(f"TaskDecomposer 初始化完成 (model={model})")
    
    async def decompose(
        self,
        user_query: str,
        context: Dict[str, Any] = None
    ) -> DecompositionResult:
        """
        分解任务
        
        Args:
            user_query: 用户原始请求
            context: 额外上下文（可选）
            
        Returns:
            DecompositionResult
        """
        logger.info(f"开始任务分解: {user_query[:50]}...")
        
        # 构建 Prompt（使用 replace 避免 format 的 { } 冲突）
        prompt = self.decomposition_prompt.replace("{user_query}", user_query)
        
        try:
            # 调用 LLM
            if self.llm_service:
                response = await self._call_llm(prompt)
            else:
                # Fallback: 简单规则分解（用于测试）
                response = self._fallback_decompose(user_query)
            
            # 解析响应
            result = self._parse_decomposition_response(response)
            
            logger.info(
                f"任务分解完成: {len(result.sub_tasks)} 个子任务，"
                f"{len(result.parallelizable_groups)} 个并行组"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"任务分解失败: {e}")
            return DecompositionResult(
                success=False,
                reasoning="",
                sub_tasks=[],
                parallelizable_groups=[],
                error=str(e)
            )
    
    async def generate_worker_prompt(
        self,
        sub_task: SubTaskState
    ) -> WorkerPromptResult:
        """
        为子任务生成 Worker 系统提示词（Fallback 方法）
        
        ⚠️ 注意：此方法作为 fallback 使用。
        正确的方式是在 instances/{instance_name}/workers/ 目录中
        预配置 Worker 系统提示词（prompt.md），运行时直接使用。
        
        只有当 instance 中未配置对应 Worker 时，才会调用此方法动态生成。
        
        Args:
            sub_task: 子任务
            
        Returns:
            WorkerPromptResult
        """
        logger.warning(
            f"⚠️ [Fallback] 动态生成 Worker 提示词: {sub_task.id} "
            f"(推荐在 instance 配置中预设 Worker 提示词)"
        )
        
        # 构建 Prompt（使用 replace 避免 format 的 { } 冲突）
        sub_task_json = json.dumps({
            "action": sub_task.action,
            "specialization": sub_task.specialization
        }, ensure_ascii=False)
        
        prompt = self.worker_prompt_template.replace("{sub_task}", sub_task_json)
        
        try:
            if self.llm_service:
                response = await self._call_llm(prompt)
            else:
                # Fallback: 使用默认模板
                response = self._fallback_worker_prompt(sub_task)
            
            result = self._parse_worker_prompt_response(response)
            
            logger.info(f"Worker 提示词生成完成: {sub_task.id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Worker 提示词生成失败: {e}")
            return WorkerPromptResult(
                success=False,
                reasoning="",
                system_prompt="",
                error=str(e)
            )
    
    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        from core.llm import Message
        
        response = await self.llm_service.create_message_async(
            messages=[Message(role="user", content=prompt)]
        )
        
        # 提取文本响应
        if hasattr(response, 'content'):
            content = response.content
            # 处理列表格式
            if isinstance(content, list):
                for block in content:
                    if hasattr(block, 'text'):
                        return block.text
                    elif isinstance(block, dict) and block.get('type') == 'text':
                        return block.get('text', '')
            # 处理字符串格式
            elif isinstance(content, str):
                return content
        
        return str(response)
    
    def _parse_decomposition_response(self, response: str) -> DecompositionResult:
        """解析分解响应"""
        try:
            # 提取 JSON
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            
            # 构建 SubTaskState 列表
            sub_tasks = []
            for st_data in data.get("sub_tasks", []):
                sub_task = SubTaskState(
                    id=st_data["id"],
                    action=st_data["action"],
                    specialization=st_data.get("specialization", "general"),
                    status=SubTaskStatus.PENDING,
                    dependencies=st_data.get("dependencies", []),
                    created_at=datetime.now()
                )
                sub_tasks.append(sub_task)
            
            return DecompositionResult(
                success=True,
                reasoning=data.get("reasoning", ""),
                sub_tasks=sub_tasks,
                parallelizable_groups=data.get("parallelizable_groups", [])
            )
            
        except Exception as e:
            logger.warning(f"解析分解响应失败: {e}")
            raise ValueError(f"无法解析分解响应: {e}")
    
    def _parse_worker_prompt_response(self, response: str) -> WorkerPromptResult:
        """解析 Worker 提示词响应"""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)
            
            return WorkerPromptResult(
                success=True,
                reasoning=data.get("reasoning", ""),
                system_prompt=data.get("system_prompt", "")
            )
            
        except Exception as e:
            logger.warning(f"解析 Worker 提示词响应失败: {e}")
            raise ValueError(f"无法解析 Worker 提示词响应: {e}")
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON"""
        # 尝试找到 JSON 块
        import re
        
        # 匹配 ```json ... ``` 格式
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            return json_match.group(1).strip()
        
        # 尝试直接解析
        # 找到第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return text[start:end + 1]
        
        raise ValueError("未找到 JSON 内容")
    
    def _fallback_decompose(self, user_query: str) -> str:
        """
        Fallback 分解（用于测试或无 LLM 时）
        
        简单规则匹配
        """
        sub_tasks = []
        task_id = 1
        
        query_lower = user_query.lower()
        
        # 检测研究任务
        if any(kw in query_lower for kw in ["研究", "分析", "调研", "research"]):
            sub_tasks.append({
                "id": f"task-{task_id}",
                "action": "信息收集和研究分析",
                "specialization": "research",
                "dependencies": [],
                "estimated_time": 600,
                "can_parallel": True
            })
            task_id += 1
        
        # 检测文档任务
        if any(kw in query_lower for kw in ["ppt", "报告", "文档", "document"]):
            deps = [f"task-{task_id - 1}"] if sub_tasks else []
            sub_tasks.append({
                "id": f"task-{task_id}",
                "action": "生成文档/报告",
                "specialization": "document",
                "dependencies": deps,
                "estimated_time": 500,
                "can_parallel": len(deps) == 0
            })
            task_id += 1
        
        # 检测代码任务
        if any(kw in query_lower for kw in ["代码", "重构", "测试", "code", "refactor"]):
            sub_tasks.append({
                "id": f"task-{task_id}",
                "action": "代码开发/重构",
                "specialization": "code",
                "dependencies": [],
                "estimated_time": 600,
                "can_parallel": True
            })
            task_id += 1
        
        # 默认通用任务
        if not sub_tasks:
            sub_tasks.append({
                "id": "task-1",
                "action": user_query,
                "specialization": "general",
                "dependencies": [],
                "estimated_time": 300,
                "can_parallel": True
            })
        
        # 构建并行组
        parallel_groups = []
        no_deps = [st["id"] for st in sub_tasks if not st["dependencies"]]
        has_deps = [st["id"] for st in sub_tasks if st["dependencies"]]
        
        if no_deps:
            parallel_groups.append(no_deps)
        if has_deps:
            parallel_groups.append(has_deps)
        
        result = {
            "reasoning": "Fallback 规则分解（无 LLM 服务）",
            "sub_tasks": sub_tasks,
            "parallelizable_groups": parallel_groups
        }
        
        return json.dumps(result, ensure_ascii=False)
    
    def _fallback_worker_prompt(self, sub_task: SubTaskState) -> str:
        """Fallback Worker 提示词生成"""
        prompts = {
            "research": f"你是一位专业的研究分析师。\n\n当前任务：{sub_task.action}\n\n请系统性地收集和分析相关信息，提供有洞察的结论。",
            "document": f"你是一位专业的文档撰写专家。\n\n当前任务：{sub_task.action}\n\n请生成结构清晰、内容专业的文档。",
            "data_analysis": f"你是一位数据分析专家。\n\n当前任务：{sub_task.action}\n\n请进行严谨的数据分析，提供可视化和洞察。",
            "code": f"你是一位资深软件工程师。\n\n当前任务：{sub_task.action}\n\n请编写高质量、可维护的代码。",
            "general": f"你是一位专业的 AI 助手。\n\n当前任务：{sub_task.action}"
        }
        
        prompt = prompts.get(sub_task.specialization, prompts["general"])
        
        result = {
            "reasoning": "使用默认模板生成",
            "system_prompt": prompt
        }
        
        return json.dumps(result, ensure_ascii=False)


def create_task_decomposer(
    llm_service=None,
    **kwargs
) -> TaskDecomposer:
    """
    创建任务分解器
    
    工厂函数
    """
    return TaskDecomposer(
        llm_service=llm_service,
        **kwargs
    )

    def generate_mermaid_dag(self, sub_tasks: List["SubTaskState"]) -> str:
        """
        生成 Mermaid 流程图（🆕 V6.0 可视化支持）
        
        Args:
            sub_tasks: 子任务列表
            
        Returns:
            Mermaid 格式的 DAG 字符串
        """
        lines = ["graph TD"]
        
        # 为每个子任务生成节点
        for sub_task in sub_tasks:
            # 节点 ID（替换 - 为 _，Mermaid 不支持）
            node_id = sub_task.id.replace("-", "_")
            
            # 节点标签（截断过长的文本）
            label = sub_task.action[:40] + "..." if len(sub_task.action) > 40 else sub_task.action
            label = label.replace('"', "'")  # 转义引号
            
            # 添加节点定义
            lines.append(f'    {node_id}["{label}"]')
            
            # 添加依赖关系（边）
            for dep_id in sub_task.dependencies:
                dep_node_id = dep_id.replace("-", "_")
                lines.append(f"    {dep_node_id} --> {node_id}")
        
        # 添加样式（可选）
        lines.append("")
        lines.append("    %% 节点样式")
        lines.append("    classDef default fill:#E8F4F8,stroke:#333,stroke-width:2px")
        
        return "\n".join(lines)
