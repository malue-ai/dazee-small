"""
Promptfoo 适配器
将 Promptfoo 的评估结果转换为 ZenFlux 评估系统格式
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import (
    Checkpoint,
    EvaluationReport,
    GradeResult,
    GraderType,
    Message,
    Task,
    TaskInput,
    TaskResult,
    TokenUsage,
    Transcript,
    Trial,
    TrialStatus,
)
from .graders.code_based import CodeBasedGraders
from .graders.model_based import ModelBasedGraders


class PromptfooAdapter:
    """
    Promptfoo 结果转换器
    
    将 Promptfoo 的 JSON 结果转换为 ZenFlux EvaluationReport
    
    使用方式：
        adapter = PromptfooAdapter()
        report = adapter.convert_result("promptfoo_results.json")
    """
    
    def __init__(
        self,
        code_graders: Optional[CodeBasedGraders] = None,
        model_graders: Optional[ModelBasedGraders] = None
    ):
        """
        初始化适配器
        
        Args:
            code_graders: Code-based graders 实例（可选）
            model_graders: Model-based graders 实例（可选）
        """
        self.code_graders = code_graders or CodeBasedGraders()
        self.model_graders = model_graders
    
    def convert_result(
        self,
        promptfoo_result_path: Path,
        suite_name: str = "promptfoo",
        suite_id: Optional[str] = None
    ) -> EvaluationReport:
        """
        转换 Promptfoo 结果文件为 ZenFlux EvaluationReport
        
        Args:
            promptfoo_result_path: Promptfoo 结果 JSON 文件路径
            suite_name: 套件名称
            suite_id: 套件 ID（可选，默认自动生成）
            
        Returns:
            EvaluationReport: ZenFlux 评估报告
        """
        # 读取 Promptfoo 结果
        with open(promptfoo_result_path, "r", encoding="utf-8") as f:
            promptfoo_data = json.load(f)
        
        # 转换结果
        task_results = []
        for result_item in promptfoo_data.get("results", []):
            task_result = self._convert_test_case(result_item)
            if task_result:
                task_results.append(task_result)
        
        # 计算统计信息
        total_tasks = len(task_results)
        passed_tasks = sum(1 for tr in task_results if tr.pass_rate >= 0.5)
        failed_tasks = total_tasks - passed_tasks
        unstable_tasks = sum(1 for tr in task_results if not tr.is_stable)
        
        # 汇总 Token 使用
        total_token_usage = TokenUsage()
        total_duration = 0.0
        
        for tr in task_results:
            for trial in tr.trials:
                if trial.transcript and trial.transcript.token_usage:
                    usage = trial.transcript.token_usage
                    total_token_usage.input_tokens += usage.input_tokens
                    total_token_usage.output_tokens += usage.output_tokens
                    total_token_usage.thinking_tokens += usage.thinking_tokens
                
                if trial.duration_seconds:
                    total_duration += trial.duration_seconds
        
        # 创建报告
        report = EvaluationReport(
            report_id=str(uuid4()),
            suite_id=suite_id or f"promptfoo_{suite_name}",
            suite_name=suite_name,
            task_results=task_results,
            total_tasks=total_tasks,
            passed_tasks=passed_tasks,
            failed_tasks=failed_tasks,
            unstable_tasks=unstable_tasks,
            total_token_usage=total_token_usage,
            total_duration_seconds=total_duration,
            created_at=datetime.utcnow()
        )
        
        return report
    
    def _convert_test_case(self, promptfoo_result: Dict[str, Any]) -> Optional[TaskResult]:
        """
        转换单个 Promptfoo test case 为 TaskResult
        
        Args:
            promptfoo_result: Promptfoo 单个测试结果
            
        Returns:
            TaskResult: ZenFlux 任务结果
        """
        test_id = promptfoo_result.get("id", str(uuid4()))
        prompt_data = promptfoo_result.get("prompt", {})
        response_data = promptfoo_result.get("response", {})
        assert_results = promptfoo_result.get("assert", [])
        
        # 创建 Transcript
        transcript = self._create_transcript(prompt_data, response_data)
        
        # 转换断言为 GradeResult
        grade_results = []
        for assert_item in assert_results:
            grade_result = self._convert_assert(assert_item, transcript)
            if grade_result:
                grade_results.append(grade_result)
        
        # 创建 Trial
        trial = Trial(
            trial_id=str(uuid4()),
            task_id=test_id,
            trial_number=1,
            status=TrialStatus.COMPLETED,
            transcript=transcript,
            outcome=None,
            grade_results=grade_results,
            error=None,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        # 创建 TaskResult
        task_result = TaskResult(
            task_id=test_id,
            task_description=prompt_data.get("display", prompt_data.get("raw", "")),
            trials=[trial]
        )
        
        return task_result
    
    def _create_transcript(
        self,
        prompt_data: Dict[str, Any],
        response_data: Dict[str, Any]
    ) -> Transcript:
        """
        从 Promptfoo 数据创建 Transcript
        
        Args:
            prompt_data: Prompt 数据
            response_data: Response 数据
            
        Returns:
            Transcript: ZenFlux 转录记录
        """
        # 创建消息
        messages = [
            Message(
                role="user",
                content=prompt_data.get("raw", prompt_data.get("display", "")),
                tool_calls=[],
                timestamp=datetime.utcnow()
            ),
            Message(
                role="assistant",
                content=response_data.get("output", ""),
                tool_calls=[],
                timestamp=datetime.utcnow()
            )
        ]
        
        # Token 使用
        token_usage_data = response_data.get("tokenUsage", {})
        token_usage = TokenUsage(
            input_tokens=token_usage_data.get("prompt", token_usage_data.get("total", 0)) // 2,
            output_tokens=token_usage_data.get("completion", token_usage_data.get("total", 0)) // 2,
            thinking_tokens=0,
            cache_read_tokens=0,
            cache_write_tokens=0
        )
        
        # 延迟（如果有）
        latency_ms = response_data.get("latencyMs", 0)
        
        return Transcript(
            messages=messages,
            tool_calls=[],
            token_usage=token_usage,
            duration_ms=latency_ms,
            metadata={
                "source": "promptfoo",
                "provider": response_data.get("provider", ""),
                "model": response_data.get("model", "")
            }
        )
    
    def _convert_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> Optional[GradeResult]:
        """
        转换 Promptfoo 断言为 GradeResult
        
        Args:
            assert_item: Promptfoo 断言结果
            transcript: 转录记录（用于某些检查）
            
        Returns:
            GradeResult: ZenFlux 评分结果
        """
        assert_type = assert_item.get("type", "")
        passed = assert_item.get("pass", False)
        score = assert_item.get("score", 1.0 if passed else 0.0)
        reason = assert_item.get("reason", "")
        value = assert_item.get("value")
        threshold = assert_item.get("threshold")
        
        # 根据断言类型选择对应的 grader
        if assert_type in ["contains", "not-contains"]:
            return self._convert_contains_assert(assert_item, transcript, assert_type == "not-contains")
        elif assert_type == "regex":
            return self._convert_regex_assert(assert_item, transcript)
        elif assert_type in ["javascript", "python"]:
            return self._convert_custom_assert(assert_item, transcript)
        elif assert_type in ["llm-rubric", "model-graded"]:
            return self._convert_llm_assert(assert_item, transcript)
        elif assert_type == "cost":
            return self._convert_cost_assert(assert_item, transcript)
        elif assert_type == "latency":
            return self._convert_latency_assert(assert_item, transcript)
        elif assert_type == "equals":
            return self._convert_equals_assert(assert_item, transcript)
        elif assert_type in ["is-json", "is-valid-openapi"]:
            return self._convert_json_assert(assert_item, transcript)
        elif assert_type == "similar":
            return self._convert_similarity_assert(assert_item, transcript)
        else:
            # 通用转换（保留原始信息）
            return GradeResult(
                grader_type=GraderType.CODE,
                grader_name=f"promptfoo_{assert_type}",
                passed=passed,
                score=score,
                explanation=reason,
                details={
                    "type": assert_type,
                    "value": value,
                    "threshold": threshold,
                    "original": assert_item
                }
            )
    
    def _convert_contains_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript,
        negated: bool = False
    ) -> GradeResult:
        """转换 contains/not-contains 断言"""
        value = assert_item.get("value", "")
        passed = assert_item.get("pass", False)
        reason = assert_item.get("reason", "")
        
        # 使用 CodeBasedGraders 检查
        response = transcript.get_final_response() or ""
        contains = value.lower() in response.lower() if value else False
        
        if negated:
            passed = not contains
        else:
            passed = contains
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_response_contains",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=reason or (f"{'不包含' if negated else '包含'} '{value}'" if not passed else None),
            details={
                "value": value,
                "negated": negated,
                "response_snippet": response[:100] if response else ""
            }
        )
    
    def _convert_regex_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 regex 断言"""
        pattern = assert_item.get("value", "")
        passed = assert_item.get("pass", False)
        reason = assert_item.get("reason", "")
        
        response = transcript.get_final_response() or ""
        matches = bool(re.search(pattern, response, re.IGNORECASE | re.MULTILINE))
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_response_matches",
            passed=matches,
            score=1.0 if matches else 0.0,
            explanation=reason or (f"正则不匹配: {pattern}" if not matches else None),
            details={
                "pattern": pattern,
                "matched": matches
            }
        )
    
    def _convert_custom_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 javascript/python 自定义断言"""
        passed = assert_item.get("pass", False)
        score = assert_item.get("score", 1.0 if passed else 0.0)
        reason = assert_item.get("reason", "")
        assert_type = assert_item.get("type", "")
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name=f"promptfoo_custom_{assert_type}",
            passed=passed,
            score=score,
            explanation=reason,
            details={
                "type": assert_type,
                "original": assert_item
            }
        )
    
    def _convert_llm_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 LLM-as-Judge 断言"""
        passed = assert_item.get("pass", False)
        score = assert_item.get("score", 1.0 if passed else 0.0)
        reason = assert_item.get("reason", "")
        rubric = assert_item.get("rubric", "")
        
        # 如果有 model_graders，可以重新评估
        # 否则直接使用 Promptfoo 的结果
        return GradeResult(
            grader_type=GraderType.MODEL,
            grader_name="promptfoo_llm_rubric",
            passed=passed,
            score=score,
            explanation=reason,
            confidence=assert_item.get("confidence", 0.8 if passed else 0.5),
            needs_human_review=assert_item.get("needsReview", False),
            details={
                "rubric": rubric,
                "original": assert_item
            }
        )
    
    def _convert_cost_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 cost 断言"""
        threshold = assert_item.get("threshold", 0)
        passed = assert_item.get("pass", False)
        reason = assert_item.get("reason", "")
        
        # 使用 CodeBasedGraders 检查 Token 限制
        if transcript.token_usage:
            total_tokens = transcript.token_usage.total_tokens
            passed = total_tokens <= threshold
            
            return GradeResult(
                grader_type=GraderType.CODE,
                grader_name="check_token_limit",
                passed=passed,
                score=1.0 if passed else max(0.0, 1.0 - (total_tokens - threshold) / threshold),
                explanation=reason or (f"Token 超限: {total_tokens}/{threshold}" if not passed else None),
                details={
                    "threshold": threshold,
                    "actual": total_tokens,
                    "usage": transcript.token_usage.model_dump() if hasattr(transcript.token_usage, "model_dump") else {}
                }
            )
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_token_limit",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=reason,
            details={"threshold": threshold}
        )
    
    def _convert_latency_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 latency 断言"""
        threshold_ms = assert_item.get("threshold", 0)
        passed = assert_item.get("pass", False)
        reason = assert_item.get("reason", "")
        
        actual_latency = transcript.duration_ms
        passed = actual_latency <= threshold_ms if threshold_ms > 0 else passed
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_latency",
            passed=passed,
            score=1.0 if passed else max(0.0, 1.0 - (actual_latency - threshold_ms) / threshold_ms),
            explanation=reason or (f"延迟超限: {actual_latency}ms/{threshold_ms}ms" if not passed else None),
            details={
                "threshold_ms": threshold_ms,
                "actual_ms": actual_latency
            }
        )
    
    def _convert_equals_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 equals 断言"""
        expected = assert_item.get("value", "")
        passed = assert_item.get("pass", False)
        reason = assert_item.get("reason", "")
        
        response = transcript.get_final_response() or ""
        matches = response.strip() == expected.strip()
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_response_equals",
            passed=matches,
            score=1.0 if matches else 0.0,
            explanation=reason or (f"不匹配: 期望 '{expected}', 实际 '{response[:50]}...'" if not matches else None),
            details={
                "expected": expected,
                "actual": response
            }
        )
    
    def _convert_json_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 JSON 格式断言"""
        passed = assert_item.get("pass", False)
        reason = assert_item.get("reason", "")
        
        response = transcript.get_final_response() or ""
        is_valid_json = False
        
        try:
            json.loads(response)
            is_valid_json = True
        except (json.JSONDecodeError, TypeError):
            pass
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_json_schema",
            passed=is_valid_json,
            score=1.0 if is_valid_json else 0.0,
            explanation=reason or ("JSON 格式无效" if not is_valid_json else None),
            details={
                "response_snippet": response[:200]
            }
        )
    
    def _convert_similarity_assert(
        self,
        assert_item: Dict[str, Any],
        transcript: Transcript
    ) -> GradeResult:
        """转换 similarity 断言"""
        passed = assert_item.get("pass", False)
        score = assert_item.get("score", 1.0 if passed else 0.0)
        reason = assert_item.get("reason", "")
        threshold = assert_item.get("threshold", 0.8)
        
        return GradeResult(
            grader_type=GraderType.MODEL,
            grader_name="promptfoo_similarity",
            passed=passed,
            score=score,
            explanation=reason,
            confidence=min(1.0, score / threshold) if threshold > 0 else 0.8,
            details={
                "threshold": threshold,
                "similarity_score": score
            }
        )


def convert_promptfoo_result(
    promptfoo_result_path: Path,
    suite_name: str = "promptfoo",
    output_path: Optional[Path] = None
) -> EvaluationReport:
    """
    便捷函数：转换 Promptfoo 结果文件
    
    Args:
        promptfoo_result_path: Promptfoo 结果 JSON 文件路径
        suite_name: 套件名称
        output_path: 输出路径（可选，保存为 ZenFlux 报告格式）
        
    Returns:
        EvaluationReport: ZenFlux 评估报告
    """
    adapter = PromptfooAdapter()
    report = adapter.convert_result(promptfoo_result_path, suite_name)
    
    if output_path:
        import json
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, ensure_ascii=False, default=str)
    
    return report
