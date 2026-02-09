"""
Code-based Graders（代码评分器）

优先级最高的评分器类型，特点：
- 快速：毫秒级执行
- 便宜：无API调用
- 客观：可重复验证
- 可靠：不受模型随机性影响

适用场景：
- 工具调用验证（是否调用了预期工具）
- Token限制验证（是否超过预算）
- Plan Schema验证（是否符合格式）
- Outcome验证（数据库/文件是否正确）
- 响应格式验证（JSON Schema等）
"""

import json
import re
from typing import Any, Callable, Dict, List, Optional, Set

from evaluation.models import (
    GradeResult,
    GraderType,
    Outcome,
    Transcript,
)


class CodeBasedGraders:
    """
    基于代码的评分器集合
    
    使用方式：
        graders = CodeBasedGraders()
        
        # 验证工具调用
        result = graders.check_tool_calls(transcript, ["search", "write"])
        
        # 验证Token限制
        result = graders.check_token_limit(transcript, max_tokens=100000)
        
        # 验证响应包含关键词
        result = graders.check_response_contains(transcript, ["成功", "完成"])
    """
    
    # ===================
    # 工具调用相关验证
    # ===================
    
    @staticmethod
    def check_tool_calls(
        transcript: Transcript,
        expected_tools: List[str],
        strict: bool = False
    ) -> GradeResult:
        """
        验证是否调用了预期的工具
        
        Args:
            transcript: 转录记录
            expected_tools: 预期调用的工具列表
            strict: 严格模式（必须完全匹配，不能多也不能少）
            
        Returns:
            GradeResult: 评分结果
        """
        called_tools = set(transcript.get_all_tool_names())
        expected_set = set(expected_tools)
        
        # 检查是否包含所有预期工具
        missing_tools = expected_set - called_tools
        extra_tools = called_tools - expected_set if strict else set()
        
        passed = len(missing_tools) == 0 and len(extra_tools) == 0
        
        details = {
            "expected": list(expected_set),
            "called": list(called_tools),
            "missing": list(missing_tools),
        }
        if strict:
            details["extra"] = list(extra_tools)
        
        explanation = None
        if not passed:
            if missing_tools:
                explanation = f"缺少工具调用: {', '.join(missing_tools)}"
            if extra_tools:
                explanation = f"多余工具调用: {', '.join(extra_tools)}"
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_tool_calls",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=explanation,
            details=details,
        )
    
    @staticmethod
    def check_tool_call_order(
        transcript: Transcript,
        expected_order: List[str]
    ) -> GradeResult:
        """
        验证工具调用顺序是否正确
        
        Args:
            transcript: 转录记录
            expected_order: 预期的调用顺序
            
        Returns:
            GradeResult: 评分结果
        """
        called_tools = transcript.get_all_tool_names()
        
        # 使用子序列匹配（expected_order 必须按顺序出现在 called_tools 中）
        expected_idx = 0
        for tool in called_tools:
            if expected_idx < len(expected_order) and tool == expected_order[expected_idx]:
                expected_idx += 1
        
        passed = expected_idx == len(expected_order)
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_tool_call_order",
            passed=passed,
            score=1.0 if passed else expected_idx / len(expected_order) if expected_order else 0.0,
            explanation=f"顺序匹配 {expected_idx}/{len(expected_order)}" if not passed else None,
            details={
                "expected_order": expected_order,
                "actual_order": called_tools,
                "matched_count": expected_idx,
            },
        )
    
    @staticmethod
    def check_no_tool_errors(transcript: Transcript) -> GradeResult:
        """
        验证所有工具调用都成功（无错误）
        
        Args:
            transcript: 转录记录
            
        Returns:
            GradeResult: 评分结果
        """
        errors = [
            {"tool": tc.name, "error": tc.error}
            for tc in transcript.tool_calls
            if tc.error
        ]
        
        passed = len(errors) == 0
        total_calls = len(transcript.tool_calls)
        error_count = len(errors)
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_no_tool_errors",
            passed=passed,
            score=(total_calls - error_count) / total_calls if total_calls > 0 else 1.0,
            explanation=f"工具调用错误: {error_count}/{total_calls}" if not passed else None,
            details={
                "total_calls": total_calls,
                "error_count": error_count,
                "errors": errors,
            },
        )
    
    # ===================
    # Token 相关验证
    # ===================
    
    @staticmethod
    def check_token_limit(
        transcript: Transcript,
        max_tokens: int,
        token_type: str = "total"
    ) -> GradeResult:
        """
        验证Token是否超限
        
        Args:
            transcript: 转录记录
            max_tokens: Token上限
            token_type: Token类型（total/input/output/thinking）
            
        Returns:
            GradeResult: 评分结果
        """
        usage = transcript.token_usage
        
        if token_type == "total":
            actual_tokens = usage.total_tokens
        elif token_type == "input":
            actual_tokens = usage.input_tokens
        elif token_type == "output":
            actual_tokens = usage.output_tokens
        elif token_type == "thinking":
            actual_tokens = usage.thinking_tokens
        else:
            actual_tokens = usage.total_tokens
        
        passed = actual_tokens <= max_tokens
        # 计算一个渐进分数（越接近限制，分数越低）
        score = max(0.0, 1.0 - (actual_tokens - max_tokens) / max_tokens) if not passed else 1.0
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_token_limit",
            passed=passed,
            score=score,
            explanation=f"Token超限: {actual_tokens}/{max_tokens}" if not passed else None,
            details={
                "token_type": token_type,
                "max_tokens": max_tokens,
                "actual_tokens": actual_tokens,
                "usage_breakdown": {
                    "input": usage.input_tokens,
                    "output": usage.output_tokens,
                    "thinking": usage.thinking_tokens,
                    "cache_read": usage.cache_read_tokens,
                    "cache_write": usage.cache_write_tokens,
                },
            },
        )
    
    @staticmethod
    def check_token_efficiency(
        transcript: Transcript,
        max_tokens_per_tool_call: int = 5000
    ) -> GradeResult:
        """
        验证Token使用效率（平均每次工具调用的Token消耗）
        
        Args:
            transcript: 转录记录
            max_tokens_per_tool_call: 每次工具调用允许的最大Token数
            
        Returns:
            GradeResult: 评分结果
        """
        total_tokens = transcript.token_usage.total_tokens
        tool_calls = len(transcript.tool_calls)
        
        if tool_calls == 0:
            # 没有工具调用，按总Token评估
            return GradeResult(
                grader_type=GraderType.CODE,
                grader_name="check_token_efficiency",
                passed=True,
                score=1.0,
                explanation="无工具调用",
                details={"total_tokens": total_tokens, "tool_calls": 0},
            )
        
        tokens_per_call = total_tokens / tool_calls
        passed = tokens_per_call <= max_tokens_per_tool_call
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_token_efficiency",
            passed=passed,
            score=min(1.0, max_tokens_per_tool_call / tokens_per_call) if tokens_per_call > 0 else 1.0,
            explanation=f"Token效率: {tokens_per_call:.0f}/call (limit: {max_tokens_per_tool_call})" if not passed else None,
            details={
                "total_tokens": total_tokens,
                "tool_calls": tool_calls,
                "tokens_per_call": tokens_per_call,
                "max_per_call": max_tokens_per_tool_call,
            },
        )
    
    # ===================
    # 响应内容验证
    # ===================
    
    @staticmethod
    def check_response_contains(
        transcript: Transcript,
        keywords: List[str],
        case_sensitive: bool = False
    ) -> GradeResult:
        """
        验证最终响应是否包含关键词
        
        Args:
            transcript: 转录记录
            keywords: 必须包含的关键词列表
            case_sensitive: 是否大小写敏感
            
        Returns:
            GradeResult: 评分结果
        """
        response = transcript.get_final_response() or ""
        
        if not case_sensitive:
            response = response.lower()
            keywords = [k.lower() for k in keywords]
        
        found = {k: k in response for k in keywords}
        missing = [k for k, v in found.items() if not v]
        
        passed = len(missing) == 0
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_response_contains",
            passed=passed,
            score=sum(found.values()) / len(keywords) if keywords else 1.0,
            explanation=f"缺少关键词: {', '.join(missing)}" if missing else None,
            details={
                "keywords": keywords,
                "found": found,
                "missing": missing,
            },
        )
    
    @staticmethod
    def check_response_not_contains(
        transcript: Transcript,
        forbidden_keywords: List[str],
        case_sensitive: bool = False
    ) -> GradeResult:
        """
        验证最终响应不包含禁止词
        
        Args:
            transcript: 转录记录
            forbidden_keywords: 禁止出现的关键词列表
            case_sensitive: 是否大小写敏感
            
        Returns:
            GradeResult: 评分结果
        """
        response = transcript.get_final_response() or ""
        
        if not case_sensitive:
            response = response.lower()
            forbidden_keywords = [k.lower() for k in forbidden_keywords]
        
        found_forbidden = [k for k in forbidden_keywords if k in response]
        
        passed = len(found_forbidden) == 0
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_response_not_contains",
            passed=passed,
            score=1.0 - len(found_forbidden) / len(forbidden_keywords) if forbidden_keywords else 1.0,
            explanation=f"包含禁止词: {', '.join(found_forbidden)}" if found_forbidden else None,
            details={
                "forbidden_keywords": forbidden_keywords,
                "found_forbidden": found_forbidden,
            },
        )
    
    @staticmethod
    def check_response_length(
        transcript: Transcript,
        min_length: int = 0,
        max_length: int = 10000
    ) -> GradeResult:
        """
        验证响应长度是否在允许范围内
        
        Args:
            transcript: 转录记录
            min_length: 最小长度
            max_length: 最大长度
            
        Returns:
            GradeResult: 评分结果
        """
        response = transcript.get_final_response() or ""
        length = len(response)
        
        passed = min_length <= length <= max_length
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_response_length",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=f"响应长度 {length} 不在范围 [{min_length}, {max_length}]" if not passed else None,
            details={
                "length": length,
                "min_length": min_length,
                "max_length": max_length,
            },
        )
    
    @staticmethod
    def check_response_format(
        transcript: Transcript,
        expected_format: str = "text"
    ) -> GradeResult:
        """
        验证响应格式（text/json/markdown/code）
        
        Args:
            transcript: 转录记录
            expected_format: 预期格式
            
        Returns:
            GradeResult: 评分结果
        """
        response = transcript.get_final_response() or ""
        
        detected_format = "text"
        
        # 检测JSON
        if expected_format == "json":
            try:
                json.loads(response)
                detected_format = "json"
            except json.JSONDecodeError:
                # 尝试提取JSON块
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
                if json_match:
                    try:
                        json.loads(json_match.group(1))
                        detected_format = "json"
                    except json.JSONDecodeError:
                        pass
        
        # 检测Markdown
        elif expected_format == "markdown":
            # 简单检测：是否包含markdown特征
            md_patterns = [r'^#+\s', r'\*\*.*\*\*', r'\*.*\*', r'```', r'\|.*\|']
            if any(re.search(p, response, re.MULTILINE) for p in md_patterns):
                detected_format = "markdown"
        
        # 检测代码块
        elif expected_format == "code":
            if re.search(r'```\w*\n[\s\S]*?```', response):
                detected_format = "code"
        
        passed = detected_format == expected_format
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_response_format",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=f"格式不匹配: 预期 {expected_format}, 检测到 {detected_format}" if not passed else None,
            details={
                "expected_format": expected_format,
                "detected_format": detected_format,
            },
        )
    
    # ===================
    # Outcome 相关验证
    # ===================
    
    @staticmethod
    def check_outcome_database(
        outcome: Outcome,
        table: str,
        expected_conditions: Dict[str, Any]
    ) -> GradeResult:
        """
        验证数据库中是否存在预期记录
        
        Args:
            outcome: 结果记录
            table: 表名
            expected_conditions: 预期的记录条件
            
        Returns:
            GradeResult: 评分结果
        """
        passed = outcome.has_database_record(table, expected_conditions)
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_outcome_database",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=f"数据库中未找到预期记录" if not passed else None,
            details={
                "table": table,
                "expected_conditions": expected_conditions,
                "database_changes": outcome.database_changes,
            },
        )
    
    @staticmethod
    def check_outcome_file(
        outcome: Outcome,
        expected_file_path: str
    ) -> GradeResult:
        """
        验证是否创建了预期文件
        
        Args:
            outcome: 结果记录
            expected_file_path: 预期的文件路径
            
        Returns:
            GradeResult: 评分结果
        """
        passed = outcome.has_file(expected_file_path)
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_outcome_file",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=f"未创建预期文件: {expected_file_path}" if not passed else None,
            details={
                "expected_file": expected_file_path,
                "file_changes": outcome.file_changes,
            },
        )
    
    # ===================
    # 执行时间验证
    # ===================
    
    @staticmethod
    def check_execution_time(
        transcript: Transcript,
        max_duration_ms: int = 30000
    ) -> GradeResult:
        """
        验证执行时间是否在允许范围内
        
        Args:
            transcript: 转录记录
            max_duration_ms: 最大允许时间（毫秒）
            
        Returns:
            GradeResult: 评分结果
        """
        duration = transcript.duration_ms
        passed = duration <= max_duration_ms
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_execution_time",
            passed=passed,
            score=min(1.0, max_duration_ms / duration) if duration > 0 else 1.0,
            explanation=f"执行超时: {duration}ms > {max_duration_ms}ms" if not passed else None,
            details={
                "duration_ms": duration,
                "max_duration_ms": max_duration_ms,
            },
        )
    
    # ===================
    # 代码语法检查
    # ===================
    
    @staticmethod
    def check_code_syntax(
        transcript: Transcript,
        language: str = "python"
    ) -> GradeResult:
        """
        验证生成的代码语法是否正确
        
        Args:
            transcript: 转录记录
            language: 编程语言（python/javascript/typescript等）
            
        Returns:
            GradeResult: 评分结果
        """
        response = transcript.get_final_response() or ""
        
        # 提取代码块
        code_blocks = []
        if language == "python":
            # 提取 Python 代码块
            pattern = r'```(?:python)?\s*\n(.*?)```'
            matches = re.findall(pattern, response, re.DOTALL)
            code_blocks.extend(matches)
            
            # 如果没有代码块，尝试提取整个响应中的 Python 代码
            if not code_blocks:
                # 简单检测：是否包含 def、class、import 等 Python 关键字
                if any(keyword in response for keyword in ["def ", "class ", "import ", "from "]):
                    code_blocks.append(response)
        
        if not code_blocks:
            return GradeResult(
                grader_type=GraderType.CODE,
                grader_name="check_code_syntax",
                passed=True,
                score=1.0,
                explanation="未检测到代码块",
                details={"language": language, "code_blocks_found": 0},
            )
        
        # 验证语法（Python 使用 ast 模块）
        syntax_errors = []
        if language == "python":
            import ast
            for i, code in enumerate(code_blocks):
                try:
                    ast.parse(code)
                except SyntaxError as e:
                    syntax_errors.append({
                        "block_index": i,
                        "error": str(e),
                        "line": e.lineno,
                        "offset": e.offset,
                    })
        
        passed = len(syntax_errors) == 0
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_code_syntax",
            passed=passed,
            score=1.0 if passed else max(0.0, 1.0 - len(syntax_errors) / len(code_blocks)),
            explanation=f"语法错误: {len(syntax_errors)}/{len(code_blocks)} 个代码块" if syntax_errors else None,
            details={
                "language": language,
                "code_blocks_count": len(code_blocks),
                "syntax_errors": syntax_errors,
            },
        )
    
    # ===================
    # 中间结果检查点验证
    # ===================
    
    @staticmethod
    def check_checkpoint(
        transcript: Transcript,
        checkpoint_name: str,
        check_expression: str
    ) -> GradeResult:
        """
        验证中间结果检查点
        
        Args:
            transcript: 转录记录
            checkpoint_name: 检查点名称
            check_expression: 检查表达式，如 'plan_step_count >= 1'
            
        Returns:
            GradeResult: 评分结果
        """
        # 构建评估上下文
        context = {
            "plan_step_count": len(transcript.metadata.get("plan", {}).get("steps", [])),
            "tool_calls_count": len(transcript.tool_calls),
            "messages_count": len(transcript.messages),
            "token_usage": transcript.token_usage.total_tokens,
            "has_plan": "plan" in transcript.metadata,
            "has_tool_calls": len(transcript.tool_calls) > 0,
        }
        
        # 添加工具调用相关的辅助函数
        def tool_calls_contain(tool_name: str) -> bool:
            return tool_name in transcript.get_all_tool_names()
        
        def tool_calls_count() -> int:
            return len(transcript.tool_calls)
        
        # 安全执行检查表达式
        try:
            # 将表达式中的函数调用替换为实际调用
            safe_expr = check_expression
            # 替换 tool_calls_contain('xxx') 为实际调用
            import re as regex_module
            tool_contain_pattern = r"tool_calls_contain\(['\"](.+?)['\"]\)"
            matches = regex_module.findall(tool_contain_pattern, safe_expr)
            for tool_name in matches:
                result = tool_calls_contain(tool_name)
                safe_expr = safe_expr.replace(
                    f"tool_calls_contain('{tool_name}')",
                    str(result)
                ).replace(
                    f'tool_calls_contain("{tool_name}")',
                    str(result)
                )
            
            # 替换 tool_calls_count() 为实际调用
            safe_expr = safe_expr.replace("tool_calls_count()", str(tool_calls_count()))
            
            # 执行表达式
            result = eval(safe_expr, {"__builtins__": {}}, context)
            
            passed = bool(result)
            
        except Exception as e:
            passed = False
            result = None
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name=f"check_checkpoint_{checkpoint_name}",
            passed=passed,
            score=1.0 if passed else 0.0,
            explanation=f"检查点 '{checkpoint_name}' 未通过: {check_expression}" if not passed else None,
            details={
                "checkpoint_name": checkpoint_name,
                "check_expression": check_expression,
                "context": context,
                "result": result,
            },
        )
    
    # ===================
    # Plan Schema 验证
    # ===================
    
    @staticmethod
    def check_plan_schema(
        transcript: Transcript,
        required_fields: List[str] = None
    ) -> GradeResult:
        """
        验证Plan是否符合Schema
        
        Args:
            transcript: 转录记录
            required_fields: 必需的字段列表
            
        Returns:
            GradeResult: 评分结果
        """
        required_fields = required_fields or ["goal", "steps"]
        
        # 从transcript中提取plan（如果有）
        plan = transcript.metadata.get("plan", {})
        
        if not plan:
            # 尝试从工具调用结果中提取
            for tc in transcript.tool_calls:
                if tc.name == "plan_todo" and tc.result:
                    try:
                        if isinstance(tc.result, str):
                            plan = json.loads(tc.result)
                        else:
                            plan = tc.result
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue
        
        if not plan:
            return GradeResult(
                grader_type=GraderType.CODE,
                grader_name="check_plan_schema",
                passed=False,
                score=0.0,
                explanation="未找到Plan",
                details={"plan": None, "required_fields": required_fields},
            )
        
        # 检查必需字段
        missing_fields = [f for f in required_fields if f not in plan]
        passed = len(missing_fields) == 0
        
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_plan_schema",
            passed=passed,
            score=(len(required_fields) - len(missing_fields)) / len(required_fields) if required_fields else 1.0,
            explanation=f"Plan缺少字段: {', '.join(missing_fields)}" if missing_fields else None,
            details={
                "plan": plan,
                "required_fields": required_fields,
                "missing_fields": missing_fields,
            },
        )
    
    # ===================
    # 步骤数验证（小搭子效率性 E2）
    # ===================

    @staticmethod
    def check_step_count(
        transcript: Transcript,
        optimal_steps: int,
        max_acceptable_steps: int,
        step_definition: str = "tool_calls",
    ) -> GradeResult:
        """
        Verify that execution step count is within acceptable range.

        Step count is derived from tool_calls count (or plan steps if present).
        Pass if actual_steps <= max_acceptable_steps.
        Score: 1.0 if <= optimal, linear decay to 0.5 at max_acceptable, 0.2 beyond.

        Args:
            transcript: Transcript record.
            optimal_steps: Ideal step count.
            max_acceptable_steps: Maximum acceptable step count.
            step_definition: "tool_calls" (count tool invocations) or "plan_steps".

        Returns:
            GradeResult.
        """
        if step_definition == "plan_steps":
            plan = transcript.metadata.get("plan", {})
            steps = plan.get("steps", [])
            actual_steps = len(steps) if steps else len(transcript.tool_calls)
        else:
            actual_steps = len(transcript.tool_calls)

        passed = actual_steps <= max_acceptable_steps
        if actual_steps <= optimal_steps:
            score = 1.0
        elif actual_steps <= max_acceptable_steps:
            score = 0.5 + 0.5 * (max_acceptable_steps - actual_steps) / max(
                1, max_acceptable_steps - optimal_steps
            )
        else:
            score = 0.2

        explanation = None
        if not passed:
            explanation = (
                f"步骤数超限: {actual_steps} (最优={optimal_steps}, "
                f"上限={max_acceptable_steps})"
            )

        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name="check_step_count",
            passed=passed,
            score=score,
            explanation=explanation,
            details={
                "actual_steps": actual_steps,
                "optimal_steps": optimal_steps,
                "max_acceptable_steps": max_acceptable_steps,
            },
        )

    # ===================
    # 复合验证器（多条件组合）
    # ===================

    @classmethod
    def run_all_checks(
        cls,
        transcript: Transcript,
        outcome: Optional[Outcome] = None,
        checks: List[Dict[str, Any]] = None
    ) -> List[GradeResult]:
        """
        批量运行多个检查
        
        Args:
            transcript: 转录记录
            outcome: 结果记录（可选）
            checks: 检查配置列表，格式如：
                [
                    {"method": "check_tool_calls", "args": {"expected_tools": ["search"]}},
                    {"method": "check_token_limit", "args": {"max_tokens": 50000}},
                ]
                
        Returns:
            List[GradeResult]: 评分结果列表
        """
        checks = checks or []
        results = []
        
        for check in checks:
            method_name = check.get("method")
            args = check.get("args", {})
            
            if not hasattr(cls, method_name):
                results.append(GradeResult(
                    grader_type=GraderType.CODE,
                    grader_name=method_name,
                    passed=False,
                    score=0.0,
                    explanation=f"未知的检查方法: {method_name}",
                ))
                continue
            
            method = getattr(cls, method_name)
            
            # 根据方法签名传入参数
            if "outcome" in method.__code__.co_varnames and outcome:
                result = method(outcome=outcome, **args)
            else:
                result = method(transcript=transcript, **args)
            
            results.append(result)
        
        return results
