"""
结果聚合器

将多个 Worker 的执行结果聚合为最终输出

功能：
- 结果收集
- 冲突消解
- 格式统一
- 最终输出生成
"""

# 1. 标准库
import json
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

# 2. 第三方库（无）

# 3. 本地模块
from core.llm.base import Message
from logger import get_logger
from ..decomposition.prompts import AGGREGATION_PROMPT

logger = get_logger("result_aggregator")


@dataclass
class AggregationResult:
    """聚合结果"""
    success: bool
    final_output: Any
    worker_results: Dict[str, Any]
    reasoning: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "final_output": self.final_output,
            "worker_results": self.worker_results,
            "reasoning": self.reasoning,
            "error": self.error
        }


class ResultAggregator:
    """
    结果聚合器
    
    将多个 Worker 的结果合并为最终输出
    
    使用示例：
        aggregator = ResultAggregator(llm_service=claude_service)
        
        result = await aggregator.aggregate(
            user_query="研究 Top 5 云计算公司的 AI 战略",
            worker_results={
                "task-1": {"company": "AWS", "strategy": "..."},
                "task-2": {"company": "Azure", "strategy": "..."},
                ...
            }
        )
    """
    
    def __init__(
        self,
        llm_service=None,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        """
        初始化聚合器
        
        Args:
            llm_service: LLM 服务实例
            model: 使用的模型
        """
        self.llm_service = llm_service
        self.model = model
        
        logger.info("ResultAggregator 初始化完成")
    
    async def aggregate(
        self,
        user_query: str,
        worker_results: Dict[str, Any]
    ) -> AggregationResult:
        """
        聚合 Worker 结果
        
        Args:
            user_query: 用户原始请求
            worker_results: Worker 执行结果 {task_id: result}
            
        Returns:
            AggregationResult
        """
        logger.info(f"开始聚合 {len(worker_results)} 个 Worker 结果")
        
        # 过滤成功的结果
        successful_results = {
            task_id: result
            for task_id, result in worker_results.items()
            if result.get("success", True)  # 默认认为成功
        }
        
        if not successful_results:
            return AggregationResult(
                success=False,
                final_output=None,
                worker_results=worker_results,
                error="没有成功的 Worker 结果可聚合"
            )
        
        # 简单聚合（无 LLM）
        if not self.llm_service:
            return self._simple_aggregate(user_query, successful_results)
        
        # LLM 智能聚合
        try:
            return await self._llm_aggregate(user_query, successful_results)
        except Exception as e:
            logger.error(f"LLM 聚合失败: {e}")
            # Fallback 到简单聚合
            return self._simple_aggregate(user_query, successful_results)
    
    def _simple_aggregate(
        self,
        user_query: str,
        worker_results: Dict[str, Any]
    ) -> AggregationResult:
        """简单聚合（直接合并）"""
        # 按 task_id 排序
        sorted_results = sorted(worker_results.items(), key=lambda x: x[0])
        
        # 提取实际结果内容
        aggregated = []
        for task_id, result in sorted_results:
            content = result.get("result", result)
            if isinstance(content, dict):
                content = content.get("content", content.get("message", str(content)))
            aggregated.append({
                "task_id": task_id,
                "content": content
            })
        
        return AggregationResult(
            success=True,
            final_output={
                "query": user_query,
                "results": aggregated,
                "summary": f"共完成 {len(aggregated)} 个子任务"
            },
            worker_results=worker_results,
            reasoning="简单合并（无 LLM 聚合）"
        )
    
    async def _llm_aggregate(
        self,
        user_query: str,
        worker_results: Dict[str, Any]
    ) -> AggregationResult:
        """LLM 智能聚合"""
        # 格式化 Worker 结果
        formatted_results = self._format_results_for_prompt(worker_results)
        
        # 构建 Prompt
        prompt = AGGREGATION_PROMPT.format(
            user_query=user_query,
            worker_results=formatted_results
        )
        
        # 调用 LLM
        response = await self.llm_service.create_message_async(
            model=self.model,
            max_tokens=16000,  # 增加以满足 extended thinking 要求
            messages=[
                Message(role="user", content=prompt)
            ]
        )
        
        # 提取响应
        output = self._extract_llm_response(response)
        
        return AggregationResult(
            success=True,
            final_output=output,
            worker_results=worker_results,
            reasoning="LLM 智能聚合"
        )
    
    def _format_results_for_prompt(self, results: Dict[str, Any]) -> str:
        """格式化结果用于 Prompt"""
        formatted = []
        
        for task_id, result in results.items():
            content = result.get("result", result)
            formatted.append(f"### {task_id}\n{json.dumps(content, ensure_ascii=False, indent=2)}")
        
        return "\n\n".join(formatted)
    
    def _extract_llm_response(self, response) -> str:
        """提取 LLM 响应"""
        if hasattr(response, 'content'):
            for block in response.content:
                if hasattr(block, 'text'):
                    return block.text
        
        return str(response)


def create_result_aggregator(
    llm_service=None,
    **kwargs
) -> ResultAggregator:
    """创建聚合器"""
    return ResultAggregator(
        llm_service=llm_service,
        **kwargs
    )
