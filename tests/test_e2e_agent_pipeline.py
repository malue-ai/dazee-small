"""
端到端智能体管道质量测试

核心目标：验证用户能否得到满意的高质量答案

测试分为两个层次：
1. 核心目标（Answer Quality）：用户得到想要的答案
2. 必要条件（Pipeline）：技术管道正确运行，每个环节质量达标

关键理念：
- 最终答案质量 = 管道每个环节质量的累积
- Pipeline 不仅要"能跑通"，还要"跑好"
- 当答案不达标时，需要归因分析是哪个环节出问题

测试场景：
- 真实用户角色（产品经理、技术负责人、运营人员等）
- 真实业务需求（调研、系统设计、PPT制作等）
- 三种意图覆盖（系统搭建、BI问数、综合咨询）

估计消耗：~50-100K tokens（约 $0.5-1.0）
"""

# 1. 标准库
import os
import sys
import asyncio
import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

# 2. 第三方库
import pytest

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _setup_project_path():
    """延迟设置项目路径，避免在导入时触发项目模块加载"""
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))


# ============================================================
# 数据结构定义
# ============================================================

@dataclass
class StageQuality:
    """单个环节的质量数据"""
    stage_name: str
    success: bool
    quality_score: float  # 0-10
    details: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0
    issues: List[str] = field(default_factory=list)


@dataclass
class ToolExecution:
    """工具执行记录"""
    tool_name: str
    input_params: Dict[str, Any]
    output_summary: str
    success: bool
    duration_ms: float
    quality_score: float  # 0-10
    issues: List[str] = field(default_factory=list)


@dataclass
class AnswerQualityScore:
    """答案质量评分"""
    accuracy: float  # 准确性 0-10
    completeness: float  # 完整性 0-10
    relevance: float  # 相关性 0-10
    actionability: float  # 可操作性 0-10
    professionalism: float  # 专业度 0-10
    format_quality: float  # 格式友好 0-10
    
    @property
    def overall(self) -> float:
        """总体评分"""
        weights = {
            'accuracy': 0.25,
            'completeness': 0.20,
            'relevance': 0.15,
            'actionability': 0.20,
            'professionalism': 0.15,
            'format_quality': 0.05
        }
        return (
            self.accuracy * weights['accuracy'] +
            self.completeness * weights['completeness'] +
            self.relevance * weights['relevance'] +
            self.actionability * weights['actionability'] +
            self.professionalism * weights['professionalism'] +
            self.format_quality * weights['format_quality']
        )


@dataclass
class TestScenario:
    """测试场景定义"""
    name: str
    user_role: str
    query: str
    expected_intent_id: int
    expected_complexity: str
    expected_tools: List[str]
    quality_criteria: Dict[str, str]
    files: Optional[List[Dict]] = None  # 附件文件


@dataclass
class ScenarioResult:
    """场景测试结果"""
    scenario: TestScenario
    pipeline_stages: List[StageQuality]
    tool_executions: List[ToolExecution]
    answer_quality: AnswerQualityScore
    final_response: str
    total_duration_ms: float
    token_usage: Dict[str, int]
    root_cause: Optional[str] = None  # 如果质量不达标，根因是什么


# ============================================================
# Pipeline 中间结果质量追踪器
# ============================================================

class PipelineQualityTracer:
    """
    管道中间结果质量追踪器
    
    追踪每个环节的质量，分析对最终答案的影响
    
    6个关键环节：
    1. 意图识别 - 识别错误 → 整个流程走偏
    2. 路由决策 - 路由错误 → 选错处理策略
    3. 工具选择 - 选错工具 → 无法获取正确信息
    4. 工具执行 - 执行失败 → 信息不足
    5. LLM推理 - 推理质量差 → 分析不到位
    6. 输出组装 - 格式差 → 用户体验差
    """
    
    def __init__(self):
        self.stages: Dict[str, StageQuality] = {}
        self.tool_executions: List[ToolExecution] = []
        self.start_time: float = 0
        self.events: List[Dict] = []
    
    def start_trace(self):
        """开始追踪"""
        self.start_time = time.time()
        self.stages = {}
        self.tool_executions = []
        self.events = []
        self._log_event("trace_start", {})
    
    def _log_event(self, event_type: str, data: Dict):
        """记录事件"""
        self.events.append({
            "timestamp": datetime.now().isoformat(),
            "elapsed_ms": (time.time() - self.start_time) * 1000 if self.start_time else 0,
            "type": event_type,
            "data": data
        })
    
    # ========== 环节1：意图识别 ==========
    def trace_intent_recognition(
        self,
        query: str,
        recognized_intent: Dict,
        expected_intent: Optional[Dict] = None,
        duration_ms: float = 0
    ) -> StageQuality:
        """
        追踪意图识别质量
        
        检查点：
        - intent_id 是否正确
        - complexity 判断是否准确
        - is_follow_up 识别是否正确
        """
        issues = []
        quality_score = 10.0
        
        # 检查意图匹配
        if expected_intent:
            if recognized_intent.get("intent_id") != expected_intent.get("intent_id"):
                issues.append(f"意图识别错误: 期望 {expected_intent.get('intent_id')}, 实际 {recognized_intent.get('intent_id')}")
                quality_score -= 5.0
            
            if recognized_intent.get("complexity") != expected_intent.get("complexity"):
                issues.append(f"复杂度判断错误: 期望 {expected_intent.get('complexity')}, 实际 {recognized_intent.get('complexity')}")
                quality_score -= 2.0
        
        # 检查置信度
        confidence = recognized_intent.get("confidence", 0)
        if confidence < 0.8:
            issues.append(f"意图识别置信度较低: {confidence}")
            quality_score -= 1.0
        
        stage = StageQuality(
            stage_name="intent_recognition",
            success=len(issues) == 0 or quality_score >= 7.0,
            quality_score=max(0, quality_score),
            details={
                "query": query,
                "recognized": recognized_intent,
                "expected": expected_intent
            },
            duration_ms=duration_ms,
            issues=issues
        )
        
        self.stages["intent_recognition"] = stage
        self._log_event("intent_recognition", {
            "recognized": recognized_intent,
            "quality_score": quality_score,
            "issues": issues
        })
        
        return stage
    
    # ========== 环节2：路由决策 ==========
    def trace_routing_decision(
        self,
        intent: Dict,
        routing_decision: Dict,
        duration_ms: float = 0
    ) -> StageQuality:
        """
        追踪路由决策质量
        
        检查点：
        - agent_type 是否与意图匹配
        - execution_strategy 是否最优
        """
        issues = []
        quality_score = 10.0
        
        agent_type = routing_decision.get("agent_type", "simple")
        intent_id = intent.get("intent_id", 3)
        
        # 意图1（系统搭建）通常需要 simple agent + 两步工作流
        # 意图2（BI问数）通常需要 simple agent
        # 意图3（综合咨询）根据复杂度决定
        
        # 基本合理性检查
        if intent_id == 1 and agent_type == "multi":
            # 意图1 不一定需要 multi-agent
            pass
        
        stage = StageQuality(
            stage_name="routing_decision",
            success=True,
            quality_score=quality_score,
            details={
                "intent": intent,
                "decision": routing_decision
            },
            duration_ms=duration_ms,
            issues=issues
        )
        
        self.stages["routing_decision"] = stage
        self._log_event("routing_decision", {
            "decision": routing_decision,
            "quality_score": quality_score
        })
        
        return stage
    
    # ========== 环节3：工具选择 ==========
    def trace_tool_selection(
        self,
        intent: Dict,
        selected_tools: List[str],
        expected_tools: Optional[List[str]] = None
    ) -> StageQuality:
        """
        追踪工具选择质量
        
        检查点：
        - 是否选择了与意图匹配的工具
        - 是否遗漏必要工具
        """
        issues = []
        quality_score = 10.0
        
        if expected_tools:
            # 检查是否包含所有期望的工具
            missing_tools = set(expected_tools) - set(selected_tools)
            if missing_tools:
                issues.append(f"遗漏必要工具: {missing_tools}")
                quality_score -= 2.0 * len(missing_tools)
        
        # 意图1必须包含两步工作流工具
        intent_id = intent.get("intent_id", 3)
        if intent_id == 1:
            required_tools = ["Ontology_TextToChart", "api_calling"]
            for tool in required_tools:
                if not any(tool.lower() in t.lower() for t in selected_tools):
                    issues.append(f"意图1缺少必要工具: {tool}")
                    quality_score -= 3.0
        
        stage = StageQuality(
            stage_name="tool_selection",
            success=quality_score >= 7.0,
            quality_score=max(0, quality_score),
            details={
                "intent": intent,
                "selected": selected_tools,
                "expected": expected_tools
            },
            issues=issues
        )
        
        self.stages["tool_selection"] = stage
        self._log_event("tool_selection", {
            "selected": selected_tools,
            "quality_score": quality_score,
            "issues": issues
        })
        
        return stage
    
    # ========== 环节4：工具执行 ==========
    def trace_tool_execution(
        self,
        tool_name: str,
        input_params: Dict,
        output: Any,
        success: bool,
        duration_ms: float
    ) -> ToolExecution:
        """
        追踪单次工具执行质量
        
        检查点：
        - 是否执行成功
        - 返回结果是否有效（非空、格式正确）
        - 结果信息量是否充分
        """
        issues = []
        quality_score = 10.0
        
        if not success:
            issues.append("工具执行失败")
            quality_score = 0
        else:
            # 检查输出有效性
            if output is None:
                issues.append("工具返回空结果")
                quality_score -= 5.0
            elif isinstance(output, dict):
                if output.get("error"):
                    issues.append(f"工具返回错误: {output.get('error')}")
                    quality_score -= 5.0
            elif isinstance(output, str) and len(output) < 10:
                issues.append("工具返回结果过短")
                quality_score -= 2.0
        
        # 检查耗时
        expected_durations = {
            "tavily_search": 5000,
            "Ontology_TextToChart": 120000,
            "api_calling": 600000,
            "text2document": 120000,
            "slidespeak_render": 360000,
        }
        expected = expected_durations.get(tool_name, 30000)
        if duration_ms > expected * 2:
            issues.append(f"工具执行超时: {duration_ms}ms > 期望 {expected}ms")
        
        # 生成输出摘要
        output_summary = self._summarize_output(output)
        
        execution = ToolExecution(
            tool_name=tool_name,
            input_params=input_params,
            output_summary=output_summary,
            success=success,
            duration_ms=duration_ms,
            quality_score=max(0, quality_score),
            issues=issues
        )
        
        self.tool_executions.append(execution)
        self._log_event("tool_execution", {
            "tool_name": tool_name,
            "success": success,
            "duration_ms": duration_ms,
            "quality_score": quality_score,
            "issues": issues
        })
        
        return execution
    
    def _summarize_output(self, output: Any, max_length: int = 200) -> str:
        """生成输出摘要"""
        if output is None:
            return "(空)"
        if isinstance(output, str):
            return output[:max_length] + "..." if len(output) > max_length else output
        if isinstance(output, dict):
            # 提取关键字段
            keys = list(output.keys())[:5]
            summary = {k: str(output[k])[:50] for k in keys if k in output}
            return json.dumps(summary, ensure_ascii=False)
        return str(output)[:max_length]
    
    # ========== 环节5：LLM推理 ==========
    def trace_llm_reasoning(
        self,
        context_length: int,
        output_length: int,
        thinking_tokens: int = 0,
        reasoning_quality: Optional[float] = None
    ) -> StageQuality:
        """
        追踪 LLM 推理质量
        
        检查点：
        - 思考深度（thinking_tokens）
        - 输出长度是否合理
        """
        issues = []
        quality_score = reasoning_quality if reasoning_quality else 8.0
        
        # 检查思考深度
        if thinking_tokens < 1000 and context_length > 5000:
            issues.append("思考深度可能不足")
            quality_score -= 1.0
        
        stage = StageQuality(
            stage_name="llm_reasoning",
            success=True,
            quality_score=quality_score,
            details={
                "context_length": context_length,
                "output_length": output_length,
                "thinking_tokens": thinking_tokens
            },
            issues=issues
        )
        
        self.stages["llm_reasoning"] = stage
        self._log_event("llm_reasoning", {
            "context_length": context_length,
            "output_length": output_length,
            "thinking_tokens": thinking_tokens,
            "quality_score": quality_score
        })
        
        return stage
    
    # ========== 环节6：输出组装 ==========
    def trace_output_assembly(
        self,
        expected_format: str,
        actual_output: Dict,
        files: Optional[List[Dict]] = None
    ) -> StageQuality:
        """
        追踪输出组装质量
        
        检查点：
        - 格式是否符合预期
        - 内容是否完整
        - 文件链接是否有效
        """
        issues = []
        quality_score = 10.0
        
        # 检查文件有效性
        if files:
            for f in files:
                url = f.get("url", "")
                if not url or not url.startswith("http"):
                    issues.append(f"文件 URL 无效: {f.get('name')}")
                    quality_score -= 2.0
        
        stage = StageQuality(
            stage_name="output_assembly",
            success=quality_score >= 7.0,
            quality_score=max(0, quality_score),
            details={
                "expected_format": expected_format,
                "files_count": len(files) if files else 0
            },
            issues=issues
        )
        
        self.stages["output_assembly"] = stage
        self._log_event("output_assembly", {
            "expected_format": expected_format,
            "quality_score": quality_score,
            "issues": issues
        })
        
        return stage
    
    # ========== 质量归因分析 ==========
    def analyze_quality_attribution(self, final_score: float) -> Dict:
        """
        当最终答案质量不达标时，分析是哪个环节出了问题
        """
        if final_score >= 8.5:
            return {"status": "达标", "root_cause": None, "issues": []}
        
        issues = []
        
        # 逐环节检查
        for stage_name, stage in self.stages.items():
            if not stage.success or stage.quality_score < 7.0:
                issues.append({
                    "stage": stage_name,
                    "impact": self._get_stage_impact(stage_name),
                    "quality_score": stage.quality_score,
                    "issues": stage.issues,
                    "suggestion": self._get_suggestion(stage_name, stage.issues)
                })
        
        # 检查工具执行
        failed_tools = [t for t in self.tool_executions if not t.success]
        if failed_tools:
            issues.append({
                "stage": "tool_execution",
                "impact": "中高",
                "issue": f"{len(failed_tools)} 个工具执行失败",
                "failed_tools": [t.tool_name for t in failed_tools],
                "suggestion": "检查工具配置和网络连接"
            })
        
        # 低质量工具结果
        low_quality_tools = [t for t in self.tool_executions if t.quality_score < 7.0]
        if low_quality_tools:
            issues.append({
                "stage": "tool_result_quality",
                "impact": "中高",
                "issue": f"{len(low_quality_tools)} 个工具返回结果质量不足",
                "tools": [t.tool_name for t in low_quality_tools],
                "suggestion": "优化工具参数或更换信息源"
            })
        
        # 确定根因
        root_cause = issues[0]["stage"] if issues else "未知"
        
        return {
            "status": "不达标",
            "final_score": final_score,
            "root_cause": root_cause,
            "issues": issues
        }
    
    def _get_stage_impact(self, stage_name: str) -> str:
        """获取环节对最终质量的影响程度"""
        impacts = {
            "intent_recognition": "高（方向性错误不可挽回）",
            "routing_decision": "高（策略错误影响全局）",
            "tool_selection": "中高（影响信息获取）",
            "tool_execution": "中高（信息基础）",
            "llm_reasoning": "高（核心价值产出）",
            "output_assembly": "中（用户体验）"
        }
        return impacts.get(stage_name, "中")
    
    def _get_suggestion(self, stage_name: str, issues: List[str]) -> str:
        """获取改进建议"""
        suggestions = {
            "intent_recognition": "检查意图识别提示词或增加训练数据",
            "routing_decision": "优化路由规则",
            "tool_selection": "优化工具选择策略",
            "llm_reasoning": "增加 thinking_budget 或优化提示词",
            "output_assembly": "检查输出格式规范"
        }
        return suggestions.get(stage_name, "需要进一步分析")
    
    def get_pipeline_summary(self) -> Dict:
        """获取管道质量摘要"""
        tool_success_rate = (
            len([t for t in self.tool_executions if t.success]) / len(self.tool_executions)
            if self.tool_executions else 1.0
        )
        
        avg_tool_quality = (
            sum(t.quality_score for t in self.tool_executions) / len(self.tool_executions)
            if self.tool_executions else 10.0
        )
        
        return {
            "stages": {
                name: {
                    "success": stage.success,
                    "quality_score": stage.quality_score,
                    "issues_count": len(stage.issues)
                }
                for name, stage in self.stages.items()
            },
            "tool_executions": {
                "total": len(self.tool_executions),
                "success_rate": tool_success_rate,
                "avg_quality": avg_tool_quality
            },
            "total_duration_ms": (time.time() - self.start_time) * 1000 if self.start_time else 0
        }


# ============================================================
# 答案质量评估器
# ============================================================

class AnswerQualityEvaluator:
    """
    用户答案质量评估器
    
    核心原则：评估用户是否得到了想要的答案
    
    评估维度：
    - 准确性：答案是否正确、无事实错误
    - 完整性：是否完整回答了用户问题
    - 相关性：答案是否切中要点、不跑题
    - 可操作性：用户能否据此采取行动
    - 专业度：答案的深度和专业水平
    - 格式友好：结构清晰、易读易理解
    """
    
    def __init__(self, llm_service=None):
        """
        初始化评估器
        
        Args:
            llm_service: 可选的 LLM 服务，用于 LLM-as-Judge
        """
        self.llm_service = llm_service
    
    def evaluate(
        self,
        query: str,
        response: str,
        scenario: TestScenario,
        tool_outputs: List[Dict] = None
    ) -> AnswerQualityScore:
        """
        综合评估答案质量
        """
        # 基于规则的评估
        accuracy = self._evaluate_accuracy(query, response, tool_outputs)
        completeness = self._evaluate_completeness(query, response, scenario)
        relevance = self._evaluate_relevance(query, response)
        actionability = self._evaluate_actionability(query, response, scenario)
        professionalism = self._evaluate_professionalism(response)
        format_quality = self._evaluate_format(response)
        
        return AnswerQualityScore(
            accuracy=accuracy,
            completeness=completeness,
            relevance=relevance,
            actionability=actionability,
            professionalism=professionalism,
            format_quality=format_quality
        )
    
    def _evaluate_accuracy(
        self,
        query: str,
        response: str,
        tool_outputs: List[Dict] = None
    ) -> float:
        """评估准确性"""
        score = 8.0  # 基础分
        
        # 检查是否包含常见的错误模式
        error_patterns = [
            ("我无法", -1.0),
            ("抱歉，我不能", -1.0),
            ("错误", -0.5),
            ("失败", -0.5),
        ]
        
        for pattern, penalty in error_patterns:
            if pattern in response:
                score += penalty
        
        # 检查是否引用了工具结果
        if tool_outputs:
            # 简单检查是否使用了工具返回的信息
            for output in tool_outputs:
                if isinstance(output, dict):
                    # 检查关键数据是否出现在响应中
                    pass
        
        return max(0, min(10, score))
    
    def _evaluate_completeness(
        self,
        query: str,
        response: str,
        scenario: TestScenario
    ) -> float:
        """评估完整性"""
        score = 8.0
        
        # 检查响应长度
        if len(response) < 100:
            score -= 3.0
        elif len(response) < 500:
            score -= 1.0
        
        # 检查是否包含质量标准中的关键要素
        for key, criteria in scenario.quality_criteria.items():
            # 简单关键词匹配
            keywords = criteria.split("、") if "、" in criteria else [criteria]
            matched = any(kw in response for kw in keywords if len(kw) > 2)
            if not matched:
                score -= 0.5
        
        return max(0, min(10, score))
    
    def _evaluate_relevance(self, query: str, response: str) -> float:
        """评估相关性"""
        score = 8.0
        
        # 提取 query 中的关键词
        # 简单实现：检查 query 中的名词是否出现在 response 中
        query_words = [w for w in query if len(w) > 2]
        
        return max(0, min(10, score))
    
    def _evaluate_actionability(
        self,
        query: str,
        response: str,
        scenario: TestScenario
    ) -> float:
        """评估可操作性"""
        score = 7.0
        
        # 检查是否包含可操作的元素
        actionable_indicators = [
            ("建议", 0.5),
            ("步骤", 0.5),
            ("可以", 0.3),
            ("方案", 0.5),
            ("实施", 0.3),
            ("下载", 0.5),
            ("链接", 0.3),
        ]
        
        for indicator, bonus in actionable_indicators:
            if indicator in response:
                score += bonus
        
        return max(0, min(10, score))
    
    def _evaluate_professionalism(self, response: str) -> float:
        """评估专业度"""
        score = 7.0
        
        # 检查专业性指标
        professional_indicators = [
            ("分析", 0.3),
            ("数据", 0.3),
            ("趋势", 0.3),
            ("核心", 0.2),
            ("关键", 0.2),
            ("优势", 0.2),
            ("挑战", 0.2),
        ]
        
        for indicator, bonus in professional_indicators:
            if indicator in response:
                score += bonus
        
        return max(0, min(10, score))
    
    def _evaluate_format(self, response: str) -> float:
        """评估格式友好度"""
        score = 7.0
        
        # 检查格式元素
        format_indicators = [
            ("##", 0.5),  # 标题
            ("- ", 0.3),  # 列表
            ("1.", 0.3),  # 编号
            ("|", 0.3),   # 表格
            ("```", 0.5), # 代码块
        ]
        
        for indicator, bonus in format_indicators:
            if indicator in response:
                score += bonus
        
        return max(0, min(10, score))
    
    async def llm_as_judge(
        self,
        query: str,
        response: str,
        criteria: List[str] = None
    ) -> Dict:
        """
        使用 LLM 作为评估者
        """
        if not self.llm_service:
            return {"error": "LLM service not configured"}
        
        judge_prompt = f"""你是一个严格的答案质量评估专家。请评估以下答案是否满足用户需求。

用户问题：
{query}

Agent 答案：
{response[:3000]}...

请从以下维度评分（1-10分）并给出简要理由：

1. 准确性：答案是否正确？有无事实错误？
2. 完整性：是否完整回答了用户问题？有无遗漏？
3. 可操作性：用户能否直接使用这个答案？
4. 专业度：分析是否有深度？是否提供了专业见解？
5. 总体满意度：如果你是用户，满意吗？

请以 JSON 格式返回：
{{
    "accuracy": {{"score": X, "reason": "..."}},
    "completeness": {{"score": X, "reason": "..."}},
    "actionability": {{"score": X, "reason": "..."}},
    "professionalism": {{"score": X, "reason": "..."}},
    "overall": {{"score": X, "reason": "..."}}
}}
"""
        
        try:
            result = await self.llm_service.create_message_async(
                messages=[{"role": "user", "content": judge_prompt}],
                max_tokens=1000
            )
            # 解析 JSON 响应
            return {"raw_response": result.content}
        except Exception as e:
            return {"error": str(e)}


# ============================================================
# 测试场景定义
# ============================================================

# 真实用户场景
TEST_SCENARIOS = [
    # 场景1：产品经理调研竞品
    TestScenario(
        name="产品经理调研竞品",
        user_role="产品经理",
        query="帮我调研抖音和快手的电商功能差异，给出对比分析",
        expected_intent_id=3,
        expected_complexity="medium",
        expected_tools=["tavily_search"],
        quality_criteria={
            "对比表格": "对比表格、功能对比",
            "核心差异": "核心差异、主要区别",
            "数据支撑": "数据、用户量、GMV"
        }
    ),
    
    # 场景2：技术负责人系统设计
    TestScenario(
        name="技术负责人系统设计",
        user_role="技术负责人",
        query="设计一个支持100万日活的用户积分系统，包含积分获取、消耗、等级体系",
        expected_intent_id=1,
        expected_complexity="complex",
        expected_tools=["Ontology_TextToChart", "api_calling"],
        quality_criteria={
            "架构图": "流程图、架构",
            "数据模型": "实体、属性、关系",
            "技术选型": "技术方案、存储、缓存"
        }
    ),
    
    # 场景3：运营人员制作PPT
    TestScenario(
        name="运营人员制作PPT",
        user_role="运营人员",
        query="帮我做一个2024年AI发展趋势的PPT，用于内部分享",
        expected_intent_id=3,
        expected_complexity="complex",
        expected_tools=["plan_todo", "tavily_search", "slidespeak_render"],
        quality_criteria={
            "完整PPT": "PPT、演示文稿",
            "数据准确": "趋势、数据",
            "结构清晰": "目录、章节"
        }
    ),
    
    # 场景4：简单代码生成
    TestScenario(
        name="开发者代码生成",
        user_role="开发者",
        query="用Python写一个能处理百万数据的快速排序程序，要求性能优化",
        expected_intent_id=3,
        expected_complexity="simple",
        expected_tools=[],  # 可能不需要工具
        quality_criteria={
            "可运行代码": "def、return、代码",
            "性能优化": "优化、性能",
            "使用说明": "示例、用法"
        }
    ),
    
    # 场景5：追问场景
    TestScenario(
        name="追问场景",
        user_role="用户",
        query="那如果要降序排列呢？",
        expected_intent_id=3,
        expected_complexity="simple",
        expected_tools=[],
        quality_criteria={
            "直接回答": "降序、reverse"
        }
    ),
    
    # 场景6：简单问答
    TestScenario(
        name="简单知识问答",
        user_role="用户",
        query="什么是RAG技术？它和传统搜索有什么区别？",
        expected_intent_id=3,
        expected_complexity="simple",
        expected_tools=[],
        quality_criteria={
            "概念解释": "RAG、检索增强",
            "区别对比": "区别、不同"
        }
    ),
]


# ============================================================
# 测试辅助函数
# ============================================================

def load_env():
    """加载环境变量"""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
            logger.info(f"加载 .env: {env_path}")
            return True
        else:
            logger.warning(f".env 不存在: {env_path}")
            return False
    except Exception as e:
        logger.error(f"加载 .env 失败: {e}")
        return False


def check_api_keys() -> Dict[str, bool]:
    """检查必需的 API 密钥"""
    return {
        "ANTHROPIC_API_KEY": bool(os.getenv("ANTHROPIC_API_KEY")),
        "DIFY_API_KEY": bool(os.getenv("DIFY_API_KEY")),
        "COZE_API_KEY": bool(os.getenv("COZE_API_KEY")),
    }


def setup_project_imports():
    """设置项目导入路径并加载环境变量"""
    _setup_project_path()
    load_env()


# ============================================================
# 测试用例
# ============================================================

class TestE2EAgentPipeline:
    """端到端智能体管道测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """测试前置设置"""
        # 延迟设置项目导入
        setup_project_imports()
        self.tracer = PipelineQualityTracer()
        self.evaluator = AnswerQualityEvaluator()
        self.results: List[ScenarioResult] = []
    
    # ========== 部署态测试 ==========
    
    @pytest.mark.asyncio
    async def test_deployment_preload_instance(self):
        """
        部署态测试：验证 Agent 实例预加载
        """
        print("\n" + "=" * 80)
        print("【部署态测试】Agent 实例预加载")
        print("=" * 80)
        
        from services.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        
        # 计时
        start_time = time.time()
        
        # 预加载 test_agent
        success = await registry.preload_instance("test_agent")
        
        load_time_ms = (time.time() - start_time) * 1000
        
        print(f"\n📦 加载结果: {'成功' if success else '失败'}")
        print(f"⏱️ 加载耗时: {load_time_ms:.2f}ms")
        
        # 验证
        assert success, "Agent 实例加载失败"
        assert load_time_ms < 500, f"加载耗时超过 500ms: {load_time_ms}ms"
        
        # 验证缓存
        agents = registry.list_agents()
        assert len(agents) > 0, "没有已加载的 Agent"
        print(f"✅ 已加载 Agent: {[a.get('name') for a in agents]}")
    
    @pytest.mark.asyncio
    async def test_runtime_agent_clone(self):
        """
        运行态测试：验证 Agent 克隆性能
        """
        print("\n" + "=" * 80)
        print("【运行态测试】Agent 克隆性能")
        print("=" * 80)
        
        from services.agent_registry import get_agent_registry
        from core.events import EventManager
        
        registry = get_agent_registry()
        
        # 确保已加载
        await registry.preload_instance("test_agent")
        
        # 创建事件管理器
        event_manager = EventManager(storage=None)
        
        # 计时克隆
        start_time = time.time()
        
        agent = await registry.get_agent(
            agent_id="test_agent",
            event_manager=event_manager
        )
        
        clone_time_ms = (time.time() - start_time) * 1000
        
        print(f"\n⏱️ 克隆耗时: {clone_time_ms:.2f}ms")
        print(f"📊 Agent 类型: {type(agent).__name__}")
        
        # 验证
        assert agent is not None, "Agent 克隆失败"
        assert clone_time_ms < 10, f"克隆耗时超过 10ms: {clone_time_ms}ms"
        
        # 验证不是原型
        assert not getattr(agent, '_is_prototype', True), "返回的是原型而非克隆"
        
        print("✅ Agent 克隆验证通过")
    
    # ========== 意图识别测试 ==========
    
    @pytest.mark.asyncio
    async def test_intent_recognition_accuracy(self):
        """
        意图识别测试：验证三种意图的识别准确率
        """
        print("\n" + "=" * 80)
        print("【意图识别测试】三种意图识别准确率")
        print("=" * 80)
        
        api_keys = check_api_keys()
        if not api_keys.get("ANTHROPIC_API_KEY"):
            pytest.skip("缺少 ANTHROPIC_API_KEY")
        
        from core.routing import AgentRouter
        from core.llm import create_llm_service
        
        # 创建 LLM 服务
        llm = create_llm_service(
            provider="claude",
            model="claude-3-5-haiku-20241022",
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            enable_thinking=False,
            max_tokens=1024
        )
        
        router = AgentRouter(llm_service=llm, enable_llm=True)
        
        correct_count = 0
        total_count = len(TEST_SCENARIOS)
        
        for scenario in TEST_SCENARIOS:
            print(f"\n📝 测试场景: {scenario.name}")
            print(f"   Query: {scenario.query[:50]}...")
            
            # 路由决策
            start_time = time.time()
            decision = await router.route(
                user_query=scenario.query,
                conversation_history=[]
            )
            duration_ms = (time.time() - start_time) * 1000
            
            # 提取意图信息
            intent_id = getattr(decision.intent, 'intent_id', 3) if hasattr(decision, 'intent') else 3
            complexity = getattr(decision.intent, 'complexity', 'simple') if hasattr(decision, 'intent') else 'simple'
            
            # 追踪
            self.tracer.trace_intent_recognition(
                query=scenario.query,
                recognized_intent={
                    "intent_id": intent_id,
                    "complexity": str(complexity),
                },
                expected_intent={
                    "intent_id": scenario.expected_intent_id,
                    "complexity": scenario.expected_complexity
                },
                duration_ms=duration_ms
            )
            
            # 验证
            is_correct = (intent_id == scenario.expected_intent_id)
            if is_correct:
                correct_count += 1
                print(f"   ✅ 意图识别正确: intent_id={intent_id}")
            else:
                print(f"   ❌ 意图识别错误: 期望 {scenario.expected_intent_id}, 实际 {intent_id}")
            
            print(f"   ⏱️ 耗时: {duration_ms:.2f}ms")
        
        accuracy = correct_count / total_count
        print(f"\n📊 意图识别准确率: {correct_count}/{total_count} = {accuracy:.1%}")
        
        assert accuracy >= 0.8, f"意图识别准确率低于 80%: {accuracy:.1%}"
    
    # ========== 完整场景测试 ==========
    
    @pytest.mark.asyncio
    async def test_scenario_simple_qa(self):
        """
        场景测试：简单知识问答
        """
        await self._run_scenario_test(TEST_SCENARIOS[5])  # 简单知识问答
    
    @pytest.mark.asyncio
    async def test_scenario_code_generation(self):
        """
        场景测试：代码生成
        """
        await self._run_scenario_test(TEST_SCENARIOS[3])  # 开发者代码生成
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_scenario_research(self):
        """
        场景测试：调研分析（耗时较长）
        """
        await self._run_scenario_test(TEST_SCENARIOS[0])  # 产品经理调研竞品
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_scenario_system_design(self):
        """
        场景测试：系统设计（耗时很长）
        """
        await self._run_scenario_test(TEST_SCENARIOS[1])  # 技术负责人系统设计
    
    async def _run_scenario_test(self, scenario: TestScenario, use_real_api: bool = True):
        """
        运行单个场景测试
        
        Args:
            scenario: 测试场景定义
            use_real_api: 是否使用真实 API（默认 True）
        """
        print("\n" + "=" * 80)
        print(f"【场景测试】{scenario.name}")
        print(f"用户角色: {scenario.user_role}")
        print(f"Query: {scenario.query}")
        print("=" * 80)
        
        api_keys = check_api_keys()
        if not api_keys.get("ANTHROPIC_API_KEY"):
            pytest.skip("缺少 ANTHROPIC_API_KEY")
        
        # 开始追踪
        self.tracer.start_trace()
        start_time = time.time()
        
        # ========== 1. 部署态：预加载 Agent ==========
        from services.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        preload_start = time.time()
        await registry.preload_instance("test_agent")
        preload_time = (time.time() - preload_start) * 1000
        print(f"\n📦 Agent 预加载: {preload_time:.2f}ms")
        
        if use_real_api:
            # ========== 2. 意图识别 ==========
            from core.routing import AgentRouter
            from core.llm import create_llm_service
            
            intent_start = time.time()
            llm = create_llm_service(
                provider="claude",
                model="claude-3-5-haiku-20241022",
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                enable_thinking=False,
                max_tokens=1024
            )
            router = AgentRouter(llm_service=llm, enable_llm=True)
            
            routing_decision = await router.route(
                user_query=scenario.query,
                conversation_history=[]
            )
            intent_time = (time.time() - intent_start) * 1000
            
            # 提取意图信息
            intent_info = {
                "intent_id": getattr(routing_decision.intent, 'intent_id', 3) if hasattr(routing_decision, 'intent') else 3,
                "complexity": str(getattr(routing_decision.intent, 'complexity', 'simple')) if hasattr(routing_decision, 'intent') else 'simple',
                "is_follow_up": getattr(routing_decision.intent, 'is_follow_up', False) if hasattr(routing_decision, 'intent') else False,
                "confidence": getattr(routing_decision.intent, 'confidence', 0.8) if hasattr(routing_decision, 'intent') else 0.8
            }
            
            print(f"\n🎯 意图识别: intent_id={intent_info['intent_id']}, complexity={intent_info['complexity']}")
            print(f"   耗时: {intent_time:.2f}ms")
            
            # 追踪意图识别
            self.tracer.trace_intent_recognition(
                query=scenario.query,
                recognized_intent=intent_info,
                expected_intent={
                    "intent_id": scenario.expected_intent_id,
                    "complexity": scenario.expected_complexity
                },
                duration_ms=intent_time
            )
            
            # 追踪路由决策
            routing_info = {
                "agent_type": routing_decision.agent_type if hasattr(routing_decision, 'agent_type') else "simple",
                "execution_strategy": routing_decision.execution_strategy if hasattr(routing_decision, 'execution_strategy') else "rvr"
            }
            self.tracer.trace_routing_decision(
                intent=intent_info,
                routing_decision=routing_info,
                duration_ms=intent_time
            )
            
            # ========== 3. 执行 Agent ==========
            from services.chat_service import ChatService
            
            chat_service = ChatService(enable_routing=True)
            
            # 生成测试用的 user_id 和 conversation_id
            test_user_id = f"test_user_{int(time.time())}"
            test_conversation_id = None  # 让系统自动创建
            
            print(f"\n🚀 开始执行 Agent...")
            execution_start = time.time()
            
            # 收集响应
            full_response = ""
            events_collected = []
            tool_calls = []
            token_usage = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
            
            try:
                async for event in chat_service.chat(
                    message=scenario.query,
                    user_id=test_user_id,
                    conversation_id=test_conversation_id,
                    stream=True,
                    agent_id="test_agent"
                ):
                    events_collected.append(event)
                    
                    # 解析事件
                    event_type = event.get("type", "")
                    
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            full_response += delta.get("text", "")
                    
                    elif event_type == "tool_use":
                        tool_name = event.get("name", "unknown")
                        tool_input = event.get("input", {})
                        tool_calls.append({"name": tool_name, "input": tool_input})
                        print(f"   🔧 工具调用: {tool_name}")
                    
                    elif event_type == "tool_result":
                        tool_name = event.get("tool_name", "unknown")
                        success = not event.get("is_error", False)
                        output = event.get("content", "")
                        
                        # 追踪工具执行
                        self.tracer.trace_tool_execution(
                            tool_name=tool_name,
                            input_params={},
                            output=output,
                            success=success,
                            duration_ms=0  # 从事件中无法获取精确耗时
                        )
                    
                    elif event_type == "message_stop":
                        # 提取 token 使用统计
                        usage = event.get("usage", {})
                        token_usage["input_tokens"] = usage.get("input_tokens", 0)
                        token_usage["output_tokens"] = usage.get("output_tokens", 0)
                    
                    elif event_type == "thinking":
                        thinking_content = event.get("thinking", "")
                        token_usage["thinking_tokens"] += len(thinking_content) // 4  # 估算
                
            except Exception as e:
                logger.error(f"Agent 执行失败: {e}")
                print(f"\n❌ Agent 执行失败: {e}")
                full_response = f"执行失败: {str(e)}"
            
            execution_time = (time.time() - execution_start) * 1000
            print(f"\n⏱️ 执行耗时: {execution_time:.2f}ms")
            print(f"📝 响应长度: {len(full_response)} 字符")
            print(f"🔧 工具调用: {len(tool_calls)} 次")
            
            # 追踪工具选择
            selected_tools = [t["name"] for t in tool_calls]
            self.tracer.trace_tool_selection(
                intent=intent_info,
                selected_tools=selected_tools,
                expected_tools=scenario.expected_tools
            )
            
            # 追踪 LLM 推理
            self.tracer.trace_llm_reasoning(
                context_length=len(scenario.query),
                output_length=len(full_response),
                thinking_tokens=token_usage.get("thinking_tokens", 0)
            )
            
            # 追踪输出组装
            self.tracer.trace_output_assembly(
                expected_format="complex" if scenario.expected_complexity == "complex" else "simple",
                actual_output={"response": full_response},
                files=None
            )
            
        else:
            # 模拟模式
            full_response = f"这是对 '{scenario.query[:30]}...' 的模拟响应。包含分析、建议和结论。"
            token_usage = {"input_tokens": 100, "output_tokens": 200, "thinking_tokens": 50}
            execution_time = 100
            
            self.tracer.trace_intent_recognition(
                query=scenario.query,
                recognized_intent={
                    "intent_id": scenario.expected_intent_id,
                    "complexity": scenario.expected_complexity
                },
                expected_intent={
                    "intent_id": scenario.expected_intent_id,
                    "complexity": scenario.expected_complexity
                },
                duration_ms=100
            )
        
        # ========== 4. 评估答案质量 ==========
        quality = self.evaluator.evaluate(
            query=scenario.query,
            response=full_response,
            scenario=scenario
        )
        
        total_time = (time.time() - start_time) * 1000
        
        print(f"\n" + "=" * 60)
        print(f"📊 答案质量评分")
        print(f"=" * 60)
        print(f"   准确性:     {quality.accuracy:.1f}/10")
        print(f"   完整性:     {quality.completeness:.1f}/10")
        print(f"   相关性:     {quality.relevance:.1f}/10")
        print(f"   可操作性:   {quality.actionability:.1f}/10")
        print(f"   专业度:     {quality.professionalism:.1f}/10")
        print(f"   格式友好:   {quality.format_quality:.1f}/10")
        print(f"   ─────────────────────────")
        print(f"   总体评分:   {quality.overall:.1f}/10")
        
        # ========== 5. 归因分析 ==========
        attribution = self.tracer.analyze_quality_attribution(quality.overall)
        if attribution["status"] == "不达标":
            print(f"\n⚠️ 质量不达标，根因分析:")
            print(f"   根因: {attribution['root_cause']}")
            for issue in attribution["issues"]:
                print(f"   - [{issue.get('stage')}] {issue.get('issue', '')}")
                if issue.get('suggestion'):
                    print(f"     建议: {issue.get('suggestion')}")
        else:
            print(f"\n✅ 答案质量达标")
        
        # ========== 6. 管道摘要 ==========
        summary = self.tracer.get_pipeline_summary()
        print(f"\n📈 Pipeline 中间环节质量:")
        for stage_name, stage_info in summary.get("stages", {}).items():
            status = "✓" if stage_info.get("success") else "✗"
            score = stage_info.get("quality_score", 0)
            print(f"   {status} {stage_name}: {score:.1f}/10")
        
        print(f"\n📊 统计:")
        print(f"   总耗时: {total_time:.2f}ms")
        print(f"   工具执行: {summary['tool_executions']['total']} 次 (成功率: {summary['tool_executions']['success_rate']:.0%})")
        print(f"   Token: input={token_usage.get('input_tokens', 0)}, output={token_usage.get('output_tokens', 0)}, thinking={token_usage.get('thinking_tokens', 0)}")
        
        # ========== 7. 响应预览 ==========
        print(f"\n📝 响应预览 (前 500 字符):")
        print("-" * 60)
        print(full_response[:500] + ("..." if len(full_response) > 500 else ""))
        print("-" * 60)
        
        # ========== 8. 断言 ==========
        assert quality.overall >= 6.0, f"答案质量低于 6.0: {quality.overall:.1f}"
        
        return ScenarioResult(
            scenario=scenario,
            pipeline_stages=list(self.tracer.stages.values()),
            tool_executions=self.tracer.tool_executions,
            answer_quality=quality,
            final_response=full_response,
            total_duration_ms=total_time,
            token_usage=token_usage,
            root_cause=attribution.get("root_cause")
        )


# ============================================================
# 测试报告生成
# ============================================================

def generate_test_report(results: List[ScenarioResult]) -> str:
    """生成测试报告"""
    report = []
    report.append("=" * 80)
    report.append("              Zenflux Agent 端到端质量测试报告")
    report.append("              核心目标：用户是否得到了满意的答案")
    report.append("=" * 80)
    report.append("")
    
    # 答案质量汇总
    if results:
        avg_overall = sum(r.answer_quality.overall for r in results) / len(results)
        report.append(f"总测试场景: {len(results)}")
        report.append(f"平均满意度: {avg_overall:.1f}/10")
        report.append("")
    
    return "\n".join(report)


# ============================================================
# 快速冒烟测试（不需要 API Key 和项目依赖）
# ============================================================

class TestE2ESmokeTest:
    """
    快速冒烟测试 - 验证测试框架本身
    
    这些测试完全独立，不依赖项目模块或数据库
    """
    
    def test_tracer_initialization(self):
        """测试 PipelineQualityTracer 初始化"""
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        
        assert tracer.start_time > 0
        assert len(tracer.stages) == 0
        assert len(tracer.tool_executions) == 0
        print("✅ PipelineQualityTracer 初始化测试通过")
    
    def test_tracer_intent_recognition(self):
        """测试意图识别追踪"""
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        
        stage = tracer.trace_intent_recognition(
            query="设计一个CRM系统",
            recognized_intent={"intent_id": 1, "complexity": "complex"},
            expected_intent={"intent_id": 1, "complexity": "complex"},
            duration_ms=100
        )
        
        assert stage.stage_name == "intent_recognition"
        assert stage.success == True
        assert stage.quality_score >= 9.0
        print(f"✅ 意图识别追踪测试通过: quality_score={stage.quality_score}")
    
    def test_tracer_tool_execution(self):
        """测试工具执行追踪"""
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        
        execution = tracer.trace_tool_execution(
            tool_name="tavily_search",
            input_params={"query": "AI趋势"},
            output={"results": ["result1", "result2"]},
            success=True,
            duration_ms=2000
        )
        
        assert execution.tool_name == "tavily_search"
        assert execution.success == True
        assert execution.quality_score >= 8.0
        print(f"✅ 工具执行追踪测试通过: quality_score={execution.quality_score}")
    
    def test_quality_attribution_pass(self):
        """测试质量归因 - 达标情况"""
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        
        # 添加正常的阶段数据
        tracer.trace_intent_recognition(
            query="测试",
            recognized_intent={"intent_id": 3},
            duration_ms=100
        )
        
        attribution = tracer.analyze_quality_attribution(final_score=9.0)
        
        assert attribution["status"] == "达标"
        assert attribution["root_cause"] is None
        print("✅ 质量归因（达标）测试通过")
    
    def test_quality_attribution_fail(self):
        """测试质量归因 - 不达标情况"""
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        
        # 添加有问题的阶段数据
        tracer.trace_intent_recognition(
            query="设计CRM系统",
            recognized_intent={"intent_id": 3},  # 错误：应该是 1
            expected_intent={"intent_id": 1},
            duration_ms=100
        )
        
        attribution = tracer.analyze_quality_attribution(final_score=6.0)
        
        assert attribution["status"] == "不达标"
        assert attribution["root_cause"] == "intent_recognition"
        print(f"✅ 质量归因（不达标）测试通过: root_cause={attribution['root_cause']}")
    
    def test_evaluator_basic(self):
        """测试答案质量评估器基础功能"""
        evaluator = AnswerQualityEvaluator()
        
        # 直接创建 TestScenario 实例（不依赖项目导入）
        scenario = TestScenario(
            name="测试场景",
            user_role="用户",
            query="什么是RAG？",
            expected_intent_id=3,
            expected_complexity="simple",
            expected_tools=[],
            quality_criteria={"概念解释": "RAG、检索"}
        )
        
        quality = evaluator.evaluate(
            query="什么是RAG？",
            response="RAG（Retrieval-Augmented Generation）是一种结合检索和生成的技术。它通过检索相关文档来增强语言模型的回答能力，可以提供更准确、更有依据的回答。",
            scenario=scenario
        )
        
        assert quality.overall > 0
        assert 0 <= quality.accuracy <= 10
        assert 0 <= quality.completeness <= 10
        print(f"✅ 答案质量评估器测试通过: overall={quality.overall:.1f}")
    
    def test_scenario_definition(self):
        """测试场景定义完整性"""
        assert len(TEST_SCENARIOS) >= 6
        
        for scenario in TEST_SCENARIOS:
            assert scenario.name
            assert scenario.user_role
            assert scenario.query
            assert scenario.expected_intent_id in [1, 2, 3]
            assert scenario.expected_complexity in ["simple", "medium", "complex"]
        
        print(f"✅ 场景定义测试通过: {len(TEST_SCENARIOS)} 个场景")
    
    def test_answer_quality_score_calculation(self):
        """测试答案质量评分计算"""
        score = AnswerQualityScore(
            accuracy=8.0,
            completeness=7.0,
            relevance=8.5,
            actionability=7.5,
            professionalism=8.0,
            format_quality=7.0
        )
        
        # 验证加权平均计算
        expected = (
            8.0 * 0.25 +   # accuracy
            7.0 * 0.20 +   # completeness
            8.5 * 0.15 +   # relevance
            7.5 * 0.20 +   # actionability
            8.0 * 0.15 +   # professionalism
            7.0 * 0.05     # format_quality
        )
        
        assert abs(score.overall - expected) < 0.01
        print(f"✅ 评分计算测试通过: overall={score.overall:.2f}")
    
    def test_pipeline_summary(self):
        """测试管道摘要生成"""
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        
        # 添加一些追踪数据
        tracer.trace_intent_recognition(
            query="测试查询",
            recognized_intent={"intent_id": 3},
            duration_ms=100
        )
        tracer.trace_tool_execution(
            tool_name="search",
            input_params={},
            output="结果",
            success=True,
            duration_ms=500
        )
        
        summary = tracer.get_pipeline_summary()
        
        assert "stages" in summary
        assert "tool_executions" in summary
        assert summary["tool_executions"]["total"] == 1
        assert summary["tool_executions"]["success_rate"] == 1.0
        print(f"✅ 管道摘要测试通过: {summary['tool_executions']['total']} 工具调用")


# ============================================================
# 独立冒烟测试运行器（不依赖 pytest 收集）
# ============================================================

def run_standalone_smoke_tests():
    """
    独立运行冒烟测试，不触发项目模块导入
    """
    print("=" * 60)
    print("  独立冒烟测试 - 验证测试框架核心功能")
    print("=" * 60)
    print()
    
    passed = 0
    failed = 0
    
    # 测试 1: PipelineQualityTracer 初始化
    try:
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        assert tracer.start_time > 0
        assert len(tracer.stages) == 0
        print("✅ [1/9] PipelineQualityTracer 初始化测试通过")
        passed += 1
    except Exception as e:
        print(f"❌ [1/9] PipelineQualityTracer 初始化测试失败: {e}")
        failed += 1
    
    # 测试 2: 意图识别追踪
    try:
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        stage = tracer.trace_intent_recognition(
            query="设计一个CRM系统",
            recognized_intent={"intent_id": 1, "complexity": "complex"},
            expected_intent={"intent_id": 1, "complexity": "complex"},
            duration_ms=100
        )
        assert stage.stage_name == "intent_recognition"
        assert stage.success == True
        assert stage.quality_score >= 9.0
        print(f"✅ [2/9] 意图识别追踪测试通过: quality_score={stage.quality_score}")
        passed += 1
    except Exception as e:
        print(f"❌ [2/9] 意图识别追踪测试失败: {e}")
        failed += 1
    
    # 测试 3: 工具执行追踪
    try:
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        execution = tracer.trace_tool_execution(
            tool_name="tavily_search",
            input_params={"query": "AI趋势"},
            output={"results": ["result1", "result2"]},
            success=True,
            duration_ms=2000
        )
        assert execution.tool_name == "tavily_search"
        assert execution.success == True
        assert execution.quality_score >= 8.0
        print(f"✅ [3/9] 工具执行追踪测试通过: quality_score={execution.quality_score}")
        passed += 1
    except Exception as e:
        print(f"❌ [3/9] 工具执行追踪测试失败: {e}")
        failed += 1
    
    # 测试 4: 质量归因（达标）
    try:
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        tracer.trace_intent_recognition(
            query="测试",
            recognized_intent={"intent_id": 3},
            duration_ms=100
        )
        attribution = tracer.analyze_quality_attribution(final_score=9.0)
        assert attribution["status"] == "达标"
        assert attribution["root_cause"] is None
        print("✅ [4/9] 质量归因（达标）测试通过")
        passed += 1
    except Exception as e:
        print(f"❌ [4/9] 质量归因（达标）测试失败: {e}")
        failed += 1
    
    # 测试 5: 质量归因（不达标）
    try:
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        tracer.trace_intent_recognition(
            query="设计CRM系统",
            recognized_intent={"intent_id": 3},
            expected_intent={"intent_id": 1},
            duration_ms=100
        )
        attribution = tracer.analyze_quality_attribution(final_score=6.0)
        assert attribution["status"] == "不达标"
        assert attribution["root_cause"] == "intent_recognition"
        print(f"✅ [5/9] 质量归因（不达标）测试通过: root_cause={attribution['root_cause']}")
        passed += 1
    except Exception as e:
        print(f"❌ [5/9] 质量归因（不达标）测试失败: {e}")
        failed += 1
    
    # 测试 6: 答案质量评估器
    try:
        evaluator = AnswerQualityEvaluator()
        scenario = TestScenario(
            name="测试场景",
            user_role="用户",
            query="什么是RAG？",
            expected_intent_id=3,
            expected_complexity="simple",
            expected_tools=[],
            quality_criteria={"概念解释": "RAG、检索"}
        )
        quality = evaluator.evaluate(
            query="什么是RAG？",
            response="RAG是一种结合检索和生成的技术。",
            scenario=scenario
        )
        assert quality.overall > 0
        assert 0 <= quality.accuracy <= 10
        print(f"✅ [6/9] 答案质量评估器测试通过: overall={quality.overall:.1f}")
        passed += 1
    except Exception as e:
        print(f"❌ [6/9] 答案质量评估器测试失败: {e}")
        failed += 1
    
    # 测试 7: 场景定义
    try:
        assert len(TEST_SCENARIOS) >= 6
        for scenario in TEST_SCENARIOS:
            assert scenario.name
            assert scenario.user_role
            assert scenario.query
        print(f"✅ [7/9] 场景定义测试通过: {len(TEST_SCENARIOS)} 个场景")
        passed += 1
    except Exception as e:
        print(f"❌ [7/9] 场景定义测试失败: {e}")
        failed += 1
    
    # 测试 8: 评分计算
    try:
        score = AnswerQualityScore(
            accuracy=8.0,
            completeness=7.0,
            relevance=8.5,
            actionability=7.5,
            professionalism=8.0,
            format_quality=7.0
        )
        expected = (
            8.0 * 0.25 + 7.0 * 0.20 + 8.5 * 0.15 +
            7.5 * 0.20 + 8.0 * 0.15 + 7.0 * 0.05
        )
        assert abs(score.overall - expected) < 0.01
        print(f"✅ [8/9] 评分计算测试通过: overall={score.overall:.2f}")
        passed += 1
    except Exception as e:
        print(f"❌ [8/9] 评分计算测试失败: {e}")
        failed += 1
    
    # 测试 9: 管道摘要
    try:
        tracer = PipelineQualityTracer()
        tracer.start_trace()
        tracer.trace_intent_recognition(
            query="测试查询",
            recognized_intent={"intent_id": 3},
            duration_ms=100
        )
        tracer.trace_tool_execution(
            tool_name="search",
            input_params={},
            output="结果",
            success=True,
            duration_ms=500
        )
        summary = tracer.get_pipeline_summary()
        assert "stages" in summary
        assert "tool_executions" in summary
        assert summary["tool_executions"]["total"] == 1
        print(f"✅ [9/9] 管道摘要测试通过: {summary['tool_executions']['total']} 工具调用")
        passed += 1
    except Exception as e:
        print(f"❌ [9/9] 管道摘要测试失败: {e}")
        failed += 1
    
    # 结果摘要
    print()
    print("=" * 60)
    if failed == 0:
        print(f"  全部通过！({passed}/{passed + failed})")
    else:
        print(f"  通过: {passed}, 失败: {failed}")
    print("=" * 60)
    
    return failed == 0


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    import sys
    
    # 解析参数
    if len(sys.argv) > 1:
        if sys.argv[1] == "smoke":
            # 独立运行冒烟测试（不需要 API 和数据库）
            success = run_standalone_smoke_tests()
            sys.exit(0 if success else 1)
        elif sys.argv[1] == "quick":
            # 快速测试（简单场景）- 需要设置环境
            setup_project_imports()
            pytest.main([__file__, "-v", "-s", "-k", "simple_qa or code_generation"])
        elif sys.argv[1] == "full":
            # 完整测试
            setup_project_imports()
            pytest.main([__file__, "-v", "-s"])
        else:
            print(f"未知参数: {sys.argv[1]}")
            print("可用参数: smoke, quick, full")
            print("  smoke - 独立冒烟测试（不需要环境配置）")
            print("  quick - 快速场景测试（需要 API Key）")
            print("  full  - 完整测试（需要数据库和 API Key）")
    else:
        # 默认：运行独立冒烟测试
        success = run_standalone_smoke_tests()
        sys.exit(0 if success else 1)
