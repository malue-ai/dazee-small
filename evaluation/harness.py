"""
Evaluation Harness（评估工具）

评估系统的核心执行引擎，负责：
1. 加载评估套件（YAML配置）
2. 执行评估任务（支持多次Trial）
3. 调用评分器（Code/Model/Human）
4. 生成评估报告

设计参考：Anthropic 评估方法论 + Promptfoo
"""

import asyncio
import uuid
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from evaluation.models import (
    Checkpoint,
    EvaluationReport,
    EvaluationSuite,
    GradeResult,
    GraderConfig,
    GraderType,
    Outcome,
    Task,
    TaskInput,
    TaskResult,
    TokenUsage,
    Transcript,
    Trial,
    TrialStatus,
)
from evaluation.graders.code_based import CodeBasedGraders
from evaluation.graders.model_based import ModelBasedGraders


class EvaluationHarness:
    """
    评估工具（Evaluation Harness）
    
    使用方式：
        # 初始化
        harness = EvaluationHarness(
            agent_factory=my_agent_factory,
            llm_service=claude_service
        )
        
        # 加载评估套件
        suite = harness.load_suite("evaluation/suites/conversation/intent_understanding.yaml")
        
        # 运行评估
        report = await harness.run_suite(suite)
        
        # 输出报告
        print(report.to_summary())
    """
    
    def __init__(
        self,
        agent_factory: Optional[Callable] = None,
        llm_service: Optional[Any] = None,
        suites_dir: str = "evaluation/suites",
    ):
        """
        初始化评估工具
        
        Args:
            agent_factory: Agent工厂函数（用于创建待测试的Agent）
            llm_service: LLM服务（用于Model-based Graders）
            suites_dir: 评估套件目录
        """
        self.agent_factory = agent_factory
        self.llm_service = llm_service
        self.suites_dir = Path(suites_dir)
        
        # 初始化评分器
        self.code_graders = CodeBasedGraders()
        self.model_graders = ModelBasedGraders(llm_service=llm_service)
        
    # ===================
    # 套件加载
    # ===================
    
    def load_suite(self, path: str) -> EvaluationSuite:
        """
        从YAML文件加载评估套件
        
        Args:
            path: YAML文件路径
            
        Returns:
            EvaluationSuite: 评估套件
        """
        file_path = Path(path)
        
        if not file_path.is_absolute():
            file_path = self.suites_dir / path
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        # 解析任务
        tasks = []
        for task_data in data.get("tasks", []):
            task = self._parse_task(task_data)
            tasks.append(task)
        
        return EvaluationSuite(
            id=data.get("id", file_path.stem),
            name=data.get("name", file_path.stem),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            tasks=tasks,
            default_trials=data.get("default_trials", 3),
            metadata=data.get("metadata", {}),
        )
    
    def _parse_task(self, data: Dict[str, Any]) -> Task:
        """
        解析任务配置
        
        Args:
            data: 任务配置字典
            
        Returns:
            Task: 任务对象
        """
        # 解析输入
        input_data = data.get("input", {})
        task_input = TaskInput(
            user_query=input_data.get("user_query", ""),
            conversation_history=input_data.get("conversation_history", []),
            context=input_data.get("context", {}),
            files=input_data.get("files", []),
        )
        
        # 解析评分器配置
        graders = []
        for grader_data in data.get("graders", []):
            grader = GraderConfig(
                type=GraderType(grader_data.get("type", "code")),
                name=grader_data.get("name", grader_data.get("check", "unknown")),
                check=grader_data.get("check"),
                rubric=grader_data.get("rubric"),
                min_score=grader_data.get("min_score"),
                weight=grader_data.get("weight", 1.0),
            )
            graders.append(grader)
        
        # 解析中间检查点
        checkpoints = []
        for cp_data in data.get("checkpoints", []):
            checkpoint = Checkpoint(
                name=cp_data.get("name", ""),
                check=cp_data.get("check", ""),
                description=cp_data.get("description"),
            )
            checkpoints.append(checkpoint)
        
        # 解析推荐答案
        reference_answer = data.get("reference_answer")
        
        return Task(
            id=data.get("id", str(uuid.uuid4())[:8]),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            input=task_input,
            graders=graders,
            trials=data.get("trials", 3),
            timeout_seconds=data.get("timeout_seconds", 60),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            checkpoints=checkpoints,
            reference_answer=reference_answer,
        )
    
    def load_all_suites(self) -> List[EvaluationSuite]:
        """
        加载所有评估套件
        
        Returns:
            List[EvaluationSuite]: 评估套件列表
        """
        suites = []
        
        for yaml_file in self.suites_dir.rglob("*.yaml"):
            try:
                suite = self.load_suite(str(yaml_file))
                suites.append(suite)
            except Exception as e:
                print(f"Warning: Failed to load suite {yaml_file}: {e}")
        
        return suites
    
    # ===================
    # 评估执行
    # ===================
    
    async def run_suite(
        self,
        suite: EvaluationSuite,
        concurrency: int = 5,
        verbose: bool = True
    ) -> EvaluationReport:
        """
        运行评估套件
        
        Args:
            suite: 评估套件
            concurrency: 并发数
            verbose: 是否输出详细日志
            
        Returns:
            EvaluationReport: 评估报告
        """
        if verbose:
            print(f"📊 开始评估套件: {suite.name}")
            print(f"   任务数: {len(suite.tasks)}")
            print(f"   默认试验次数: {suite.default_trials}")
        
        start_time = datetime.now()
        task_results = []
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)
        
        async def run_task_with_semaphore(task: Task) -> TaskResult:
            async with semaphore:
                return await self.run_task(task, verbose=verbose)
        
        # 并发执行所有任务
        tasks_coroutines = [
            run_task_with_semaphore(task) 
            for task in suite.tasks
        ]
        task_results = await asyncio.gather(*tasks_coroutines)
        
        end_time = datetime.now()
        
        # 统计结果
        passed_tasks = sum(1 for tr in task_results if tr.pass_rate >= 0.5)
        failed_tasks = len(task_results) - passed_tasks
        unstable_tasks = sum(1 for tr in task_results if not tr.is_stable)
        
        # 汇总Token使用
        total_token_usage = TokenUsage()
        for tr in task_results:
            for trial in tr.trials:
                if trial.transcript:
                    usage = trial.transcript.token_usage
                    total_token_usage.input_tokens += usage.input_tokens
                    total_token_usage.output_tokens += usage.output_tokens
                    total_token_usage.thinking_tokens += usage.thinking_tokens
        
        report = EvaluationReport(
            report_id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            suite_id=suite.id,
            suite_name=suite.name,
            task_results=task_results,
            total_tasks=len(suite.tasks),
            passed_tasks=passed_tasks,
            failed_tasks=failed_tasks,
            unstable_tasks=unstable_tasks,
            total_token_usage=total_token_usage,
            total_duration_seconds=(end_time - start_time).total_seconds(),
        )
        
        if verbose:
            print(f"\n✅ 评估完成!")
            print(f"   通过: {passed_tasks}/{len(suite.tasks)}")
            print(f"   通过率: {report.pass_rate:.1%}")
            print(f"   不稳定任务: {unstable_tasks}")
            print(f"   总Token: {total_token_usage.total_tokens}")
            print(f"   耗时: {report.total_duration_seconds:.1f}s")
        
        return report
    
    async def run_task(
        self,
        task: Task,
        verbose: bool = False
    ) -> TaskResult:
        """
        运行单个评估任务（多次Trial）
        
        Args:
            task: 评估任务
            verbose: 是否输出详细日志
            
        Returns:
            TaskResult: 任务结果
        """
        if verbose:
            print(f"  📝 任务: {task.id} - {task.description[:50]}...")
        
        trials = []
        
        for i in range(task.trials):
            trial = await self.run_trial(task, trial_number=i + 1)
            trials.append(trial)
            
            if verbose:
                status = "✓" if trial.passed else "✗"
                score_str = f"{trial.average_score:.2f}" if trial.average_score else "N/A"
                print(f"     Trial {i+1}: {status} (score: {score_str})")
        
        return TaskResult(
            task_id=task.id,
            task_description=task.description,
            trials=trials,
        )
    
    async def run_trial(
        self,
        task: Task,
        trial_number: int
    ) -> Trial:
        """
        运行单次试验
        
        Args:
            task: 评估任务
            trial_number: 试验序号
            
        Returns:
            Trial: 试验结果
        """
        trial = Trial(
            trial_id=f"{task.id}_trial_{trial_number}",
            task_id=task.id,
            trial_number=trial_number,
            status=TrialStatus.RUNNING,
            started_at=datetime.now(),
        )
        
        try:
            # 1. 执行Agent（获取Transcript和Outcome）
            transcript, outcome = await self._execute_agent(task)
            trial.transcript = transcript
            trial.outcome = outcome
            
            # 2. 检查中间检查点（新增）
            if task.checkpoints:
                checkpoint_results = await self._check_checkpoints(task, transcript)
                # 将检查点结果添加到 grade_results
                trial.grade_results.extend(checkpoint_results)
            
            # 3. 运行评分器
            grade_results = await self._run_graders(
                task=task,
                transcript=transcript,
                outcome=outcome,
            )
            trial.grade_results.extend(grade_results)
            
            # 4. 更新状态
            trial.status = TrialStatus.COMPLETED
            trial.completed_at = datetime.now()
            
        except asyncio.TimeoutError:
            trial.status = TrialStatus.TIMEOUT
            trial.error = f"执行超时（{task.timeout_seconds}s）"
            trial.completed_at = datetime.now()
            
        except Exception as e:
            trial.status = TrialStatus.FAILED
            trial.error = str(e)
            trial.completed_at = datetime.now()
        
        return trial
    
    async def _execute_agent(
        self,
        task: Task
    ) -> tuple[Transcript, Outcome]:
        """
        执行Agent并收集Transcript和Outcome
        
        Args:
            task: 评估任务
            
        Returns:
            Tuple[Transcript, Outcome]: 转录记录和结果记录
        """
        if self.agent_factory is None:
            # 模拟模式（用于测试）
            return self._mock_execution(task)
        
        # 创建Agent实例
        agent = await self.agent_factory()
        
        # 执行Agent
        start_time = datetime.now()
        
        result = await asyncio.wait_for(
            agent.chat(
                user_query=task.input.user_query,
                conversation_history=task.input.conversation_history,
            ),
            timeout=task.timeout_seconds,
        )
        
        end_time = datetime.now()
        
        # 构建Transcript
        transcript = Transcript(
            messages=result.get("messages", []),
            tool_calls=result.get("tool_calls", []),
            token_usage=result.get("token_usage", TokenUsage()),
            duration_ms=int((end_time - start_time).total_seconds() * 1000),
            metadata=result.get("metadata", {}),
        )
        
        # 构建Outcome
        outcome = Outcome(
            database_changes=result.get("database_changes", []),
            file_changes=result.get("file_changes", []),
            external_api_calls=result.get("external_api_calls", []),
            custom_outcomes=result.get("custom_outcomes", {}),
        )
        
        return transcript, outcome
    
    def _mock_execution(self, task: Task) -> tuple[Transcript, Outcome]:
        """
        模拟执行（用于测试评估系统本身）
        
        Args:
            task: 评估任务
            
        Returns:
            Tuple[Transcript, Outcome]: 模拟的转录记录和结果记录
        """
        from evaluation.models import Message, ToolCall
        
        # 模拟工具调用
        mock_tool_calls = [
            ToolCall(
                name="search",
                arguments={"query": task.input.user_query},
                result="模拟搜索结果",
            ),
        ]
        
        # 模拟消息
        mock_messages = [
            Message(role="user", content=task.input.user_query),
            Message(
                role="assistant", 
                content=f"这是针对'{task.input.user_query}'的模拟回答。",
                tool_calls=mock_tool_calls,
            ),
        ]
        
        transcript = Transcript(
            messages=mock_messages,
            tool_calls=mock_tool_calls,
            token_usage=TokenUsage(
                input_tokens=100,
                output_tokens=50,
                thinking_tokens=0,
            ),
            duration_ms=500,
        )
        
        outcome = Outcome()
        
        return transcript, outcome
    
    async def _check_checkpoints(
        self,
        task: Task,
        transcript: Transcript
    ) -> List[GradeResult]:
        """
        检查中间结果检查点
        
        Args:
            task: 评估任务
            transcript: 转录记录
            
        Returns:
            List[GradeResult]: 检查点结果
        """
        results = []
        
        for checkpoint in task.checkpoints:
            try:
                # 使用 CodeBasedGraders 的 check_checkpoint 方法
                result = self.code_graders.check_checkpoint(
                    transcript=transcript,
                    checkpoint_name=checkpoint.name,
                    check_expression=checkpoint.check,
                )
                results.append(result)
            except Exception as e:
                results.append(GradeResult(
                    grader_type=GraderType.CODE,
                    grader_name=f"checkpoint_{checkpoint.name}",
                    passed=False,
                    score=0.0,
                    explanation=f"检查点验证失败: {str(e)}",
                ))
        
        return results
    
    async def _run_graders(
        self,
        task: Task,
        transcript: Transcript,
        outcome: Outcome
    ) -> List[GradeResult]:
        """
        运行所有配置的评分器
        
        Args:
            task: 评估任务
            transcript: 转录记录
            outcome: 结果记录
            
        Returns:
            List[GradeResult]: 评分结果列表
        """
        results = []
        
        for grader_config in task.graders:
            try:
                if grader_config.type == GraderType.CODE:
                    result = self._run_code_grader(grader_config, transcript, outcome)
                elif grader_config.type == GraderType.MODEL:
                    result = await self._run_model_grader(grader_config, task, transcript)
                else:
                    # Human grader 不在自动评估中运行
                    continue
                
                results.append(result)
                
            except Exception as e:
                results.append(GradeResult(
                    grader_type=grader_config.type,
                    grader_name=grader_config.name,
                    passed=False,
                    score=0.0,
                    explanation=f"评分器执行失败: {str(e)}",
                ))
        
        return results
    
    def _run_code_grader(
        self,
        config: GraderConfig,
        transcript: Transcript,
        outcome: Outcome
    ) -> GradeResult:
        """
        运行Code-based评分器
        
        Args:
            config: 评分器配置
            transcript: 转录记录
            outcome: 结果记录
            
        Returns:
            GradeResult: 评分结果
        """
        check = config.check or config.name
        
        # 解析检查表达式
        # 支持的格式：
        # - "tool_calls_contain('search')"
        # - "check_token_limit(50000)"
        # - "check_response_contains(['关键词1', '关键词2'])"
        
        if check.startswith("tool_calls_contain"):
            # 提取工具名称
            import re
            match = re.search(r"tool_calls_contain\(['\"](.+?)['\"]\)", check)
            if match:
                tool_name = match.group(1)
                return self.code_graders.check_tool_calls(
                    transcript, [tool_name]
                )
        
        elif check.startswith("check_token_limit"):
            import re
            match = re.search(r"check_token_limit\((\d+)\)", check)
            if match:
                max_tokens = int(match.group(1))
                return self.code_graders.check_token_limit(
                    transcript, max_tokens
                )
        
        elif check.startswith("check_response_contains"):
            import re
            import ast
            match = re.search(r"check_response_contains\((\[.+?\])\)", check)
            if match:
                keywords = ast.literal_eval(match.group(1))
                return self.code_graders.check_response_contains(
                    transcript, keywords
                )
        
        elif check.startswith("check_no_tool_errors"):
            return self.code_graders.check_no_tool_errors(transcript)
        
        elif check.startswith("check_execution_time"):
            import re
            match = re.search(r"check_execution_time\((\d+)\)", check)
            if match:
                max_duration = int(match.group(1))
                return self.code_graders.check_execution_time(
                    transcript, max_duration
                )

        elif check.startswith("check_step_count"):
            import re
            match = re.search(r"check_step_count\((\d+),\s*(\d+)\)", check)
            if match:
                optimal = int(match.group(1))
                max_accept = int(match.group(2))
                return self.code_graders.check_step_count(
                    transcript, optimal, max_accept
                )

        # 默认：未知的检查表达式
        return GradeResult(
            grader_type=GraderType.CODE,
            grader_name=check,
            passed=False,
            score=0.0,
            explanation=f"未知的检查表达式: {check}",
        )
    
    async def _run_model_grader(
        self,
        config: GraderConfig,
        task: Task,
        transcript: Transcript
    ) -> GradeResult:
        """
        运行Model-based评分器
        
        Args:
            config: 评分器配置
            task: 评估任务
            transcript: 转录记录
            
        Returns:
            GradeResult: 评分结果
        """
        rubric = config.rubric or config.name
        
        if rubric == "grade_intent_understanding":
            result = await self.model_graders.grade_intent_understanding(
                user_query=task.input.user_query,
                agent_response=transcript.get_final_response() or "",
            )
        
        elif rubric == "grade_over_engineering":
            result = await self.model_graders.grade_over_engineering(
                user_query=task.input.user_query,
                transcript=transcript,
            )
        
        elif rubric == "grade_response_quality":
            # Build task context for Judge (expected behavior, verification points)
            task_context_parts = [f"用例 ID: {task.id}", f"用例描述: {task.description}"]
            if task.metadata:
                if task.metadata.get("expected_behavior"):
                    task_context_parts.append(f"预期行为: {task.metadata['expected_behavior']}")
                # Pass all metadata for Judge reference
                for k, v in task.metadata.items():
                    if k != "expected_behavior" and k != "multi_turn_sequence":
                        task_context_parts.append(f"{k}: {v}")
            # Include tool call summary from transcript
            tool_calls = transcript.tool_calls if hasattr(transcript, 'tool_calls') else []
            if tool_calls:
                tool_names = [tc.name for tc in tool_calls if hasattr(tc, 'name')]
                task_context_parts.append(f"工具调用链: {' → '.join(tool_names)} (共 {len(tool_names)} 次)")
            # Include token usage
            if hasattr(transcript, 'token_usage') and transcript.token_usage:
                tu = transcript.token_usage
                task_context_parts.append(
                    f"Token 消耗: input={getattr(tu, 'input_tokens', 0):,}, "
                    f"output={getattr(tu, 'output_tokens', 0):,}, "
                    f"thinking={getattr(tu, 'thinking_tokens', 0):,}"
                )
            task_context = "\n".join(task_context_parts)

            result = await self.model_graders.grade_response_quality(
                user_query=task.input.user_query,
                agent_response=transcript.get_final_response() or "",
                context=task_context,
            )
        
        elif rubric == "grade_logical_coherence":
            result = await self.model_graders.grade_logical_coherence(
                transcript=transcript,
            )
        
        elif rubric == "grade_safety_compliance":
            result = await self.model_graders.grade_safety_compliance(
                user_query=task.input.user_query,
                agent_response=transcript.get_final_response() or "",
            )
        
        elif rubric == "grade_intermediate_output":
            # 需要从 task 或 transcript 中提取中间输出
            intermediate_output = transcript.metadata.get("intermediate_output", "")
            step_description = task.description
            success_criteria = task.metadata.get("success_criteria", [])
            result = await self.model_graders.grade_intermediate_output(
                intermediate_output=intermediate_output,
                step_description=step_description,
                success_criteria=success_criteria,
            )
        
        # V11.0: 移除 grade_multi_agent_coordination（不再支持多智能体）
        
        elif rubric == "grade_against_reference":
            reference_answer = task.reference_answer or ""
            result = await self.model_graders.grade_against_reference(
                agent_response=transcript.get_final_response() or "",
                reference_answer=reference_answer,
            )

        elif rubric == "grade_skill_selection":
            meta = task.metadata or {}
            result = await self.model_graders.grade_skill_selection(
                user_query=task.input.user_query,
                transcript=transcript,
                optimal_tools=meta.get("optimal_tools"),
                suboptimal_tools=meta.get("suboptimal_tools"),
            )

        elif rubric == "grade_planning_depth":
            meta = task.metadata or {}
            result = await self.model_graders.grade_planning_depth(
                user_query=task.input.user_query,
                transcript=transcript,
                expected_planning=meta.get("expected_planning"),
            )

        elif rubric == "grade_rollback_safety":
            # B9/B10 回滚安全专项评估 — 需要完整上下文才能准确诊断
            task_context_parts = [f"用例 ID: {task.id}", f"用例描述: {task.description}"]
            if task.metadata:
                if task.metadata.get("expected_behavior"):
                    task_context_parts.append(f"预期行为: {task.metadata['expected_behavior']}")
                for k, v in task.metadata.items():
                    if k not in ("expected_behavior", "multi_turn_sequence"):
                        task_context_parts.append(f"{k}: {v}")
            # 工具调用链（关键：回滚诊断需要看到 snapshot/rollback 事件）
            tool_calls = transcript.tool_calls if hasattr(transcript, 'tool_calls') else []
            if tool_calls:
                tool_names = [tc.name for tc in tool_calls if hasattr(tc, 'name')]
                task_context_parts.append(f"工具调用链: {' → '.join(tool_names)} (共 {len(tool_names)} 次)")
            if hasattr(transcript, 'token_usage') and transcript.token_usage:
                tu = transcript.token_usage
                task_context_parts.append(
                    f"Token 消耗: input={getattr(tu, 'input_tokens', 0):,}, "
                    f"output={getattr(tu, 'output_tokens', 0):,}"
                )
            task_context = "\n".join(task_context_parts)

            # 使用 judge_prompts.yaml 中的专项提示词 + 完整上下文
            result = await self.model_graders.grade_response_quality(
                user_query=task.input.user_query,
                agent_response=transcript.get_final_response() or "",
                context=task_context,
                rubric_override="grade_rollback_safety",
            )
            result.grader_name = "grade_rollback_safety"

        else:
            # 自定义 Rubric — 也传入上下文（避免信息丢失）
            context_parts = [f"用例 ID: {task.id}", f"用例描述: {task.description}"]
            if task.metadata and task.metadata.get("expected_behavior"):
                context_parts.append(f"预期行为: {task.metadata['expected_behavior']}")
            tool_calls = transcript.tool_calls if hasattr(transcript, 'tool_calls') else []
            if tool_calls:
                tool_names = [tc.name for tc in tool_calls if hasattr(tc, 'name')]
                context_parts.append(f"工具调用链: {' → '.join(tool_names)} (共 {len(tool_names)} 次)")
            custom_context = "\n".join(context_parts) if context_parts else None

            result = await self.model_graders.grade_with_custom_rubric(
                content=transcript.get_final_response() or "",
                rubric=rubric,
                context={"task_context": custom_context} if custom_context else None,
            )
        
        # Model grader is an EVALUATOR, not a gate.
        # Always mark as passed — scores are advisory for human review.
        # PASS/FAIL is determined solely by code graders (check_no_tool_errors etc.)
        result.passed = True
        result.needs_human_review = True
        
        return result
    
    # ===================
    # 报告生成
    # ===================
    
    def generate_markdown_report(
        self,
        report: EvaluationReport
    ) -> str:
        """
        生成Markdown格式的评估报告
        
        Args:
            report: 评估报告
            
        Returns:
            str: Markdown报告内容
        """
        lines = [
            f"# 评估报告: {report.suite_name}",
            f"",
            f"**报告ID**: {report.report_id}",
            f"**生成时间**: {report.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## 📊 总体统计",
            f"",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 总任务数 | {report.total_tasks} |",
            f"| 通过任务 | {report.passed_tasks} |",
            f"| 失败任务 | {report.failed_tasks} |",
            f"| 通过率 | {report.pass_rate:.1%} |",
            f"| 不稳定任务 | {report.unstable_tasks} |",
            f"| 平均分 | {f'{report.average_score:.2f}' if report.average_score else 'N/A'} |",
            f"| 总Token | {report.total_token_usage.total_tokens} |",
            f"| 总耗时 | {report.total_duration_seconds:.1f}s |",
            f"",
            f"## 📝 任务详情",
            f"",
        ]
        
        for tr in report.task_results:
            status = "✅" if tr.pass_rate >= 0.5 else "❌"
            stability = "⚠️" if not tr.is_stable else ""
            
            lines.extend([
                f"### {status} {tr.task_id} {stability}",
                f"",
                f"**描述**: {tr.task_description}",
                f"",
                f"| Trial | 状态 | 分数 | 详情 |",
                f"|-------|------|------|------|",
            ])
            
            for trial in tr.trials:
                trial_status = "✓" if trial.passed else "✗"
                score = f"{trial.average_score:.2f}" if trial.average_score else "N/A"
                duration = f"{trial.duration_seconds:.1f}s" if trial.duration_seconds else "N/A"
                
                lines.append(
                    f"| Trial {trial.trial_number} | {trial_status} | {score} | {duration} |"
                )
            
            lines.extend([
                f"",
                f"**通过率**: {tr.pass_rate:.1%}",
                f"**平均分**: {f'{tr.average_score:.2f}' if tr.average_score else 'N/A'}",
                f"**稳定性**: {'稳定' if tr.is_stable else '不稳定（标准差: ' + (f'{tr.score_std:.2f}' if tr.score_std is not None else 'N/A') + '）'}",
                f"",
                f"---",
                f"",
            ])
        
        return "\n".join(lines)
    
    def save_report(
        self,
        report: EvaluationReport,
        output_dir: str = "evaluation/reports"
    ) -> str:
        """
        保存评估报告
        
        Args:
            report: 评估报告
            output_dir: 输出目录
            
        Returns:
            str: 报告文件路径
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 保存Markdown报告
        md_content = self.generate_markdown_report(report)
        md_file = output_path / f"{report.report_id}.md"
        
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
        
        # 保存JSON数据
        import json
        json_file = output_path / f"{report.report_id}.json"
        
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, ensure_ascii=False, indent=2, default=str)
        
        return str(md_file)
    
    @staticmethod
    def load_report(report_path: Path) -> EvaluationReport:
        """
        加载评估报告
        
        Args:
            report_path: 报告文件路径（JSON格式）
            
        Returns:
            EvaluationReport: 评估报告对象
        """
        import json
        
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 处理 datetime 字符串
        def parse_datetime(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ["created_at", "timestamp"] and isinstance(value, str):
                        try:
                            obj[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        except:
                            pass
                    elif isinstance(value, (dict, list)):
                        parse_datetime(value)
            elif isinstance(obj, list):
                for item in obj:
                    parse_datetime(item)
            return obj
        
        data = parse_datetime(data)
        
        return EvaluationReport(**data)
