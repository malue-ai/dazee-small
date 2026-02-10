"""
失败检测器（Failure Detector）

检测各类失败情况：
1. 上下文溢出（触发L3预警但未压缩）
2. 工具调用失败（连续3次失败）
3. 用户负面反馈（thumbs-down）
4. 意图识别错误（路由到错误的智能体）
5. 超时异常
6. 响应质量问题
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from logger import get_logger

logger = get_logger(__name__)


class FailureType(str, Enum):
    """失败类型"""

    CONTEXT_OVERFLOW = "context_overflow"  # 上下文溢出
    TOOL_CALL_FAILURE = "tool_call_failure"  # 工具调用失败
    CONSECUTIVE_TOOL_ERRORS = "consecutive_tool_errors"  # 连续工具错误
    USER_NEGATIVE_FEEDBACK = "user_negative_feedback"  # 用户负面反馈
    INTENT_MISMATCH = "intent_mismatch"  # 意图识别错误
    TIMEOUT = "timeout"  # 超时
    RESPONSE_QUALITY = "response_quality"  # 响应质量问题
    SAFETY_VIOLATION = "safety_violation"  # 安全违规
    UNKNOWN_ERROR = "unknown_error"  # 未知错误
    OVER_ENGINEERING = "over_engineering"  # 过度工程化 [新增]
    LOGICAL_INCOHERENCE = "logical_incoherence"  # 逻辑不连贯 [新增]
    USER_RETRY = "user_retry"  # 用户重试（隐式不满） [新增]


class FailureSeverity(str, Enum):
    """失败严重程度"""

    LOW = "low"  # 轻微（可自动恢复）
    MEDIUM = "medium"  # 中等（需要关注）
    HIGH = "high"  # 严重（需要立即处理）
    CRITICAL = "critical"  # 致命（可能影响服务）


@dataclass
class FailureCase:
    """
    失败案例

    记录一次失败的完整信息，用于：
    1. 问题追溯和分析
    2. 转化为评估任务
    3. 改进系统
    """

    id: str
    failure_type: FailureType
    severity: FailureSeverity
    conversation_id: str
    user_id: Optional[str]
    timestamp: datetime = field(default_factory=datetime.now)

    # 输入上下文
    user_query: str = ""
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)

    # 失败详情
    error_message: str = ""
    stack_trace: Optional[str] = None

    # 执行记录
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    agent_response: str = ""

    # Token使用
    token_usage: Dict[str, int] = field(default_factory=dict)

    # 额外上下文
    context: Dict[str, Any] = field(default_factory=dict)

    # 处理状态
    status: str = "new"  # new, reviewed, converted, resolved
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "failure_type": self.failure_type.value,
            "severity": self.severity.value,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat(),
            "user_query": self.user_query,
            "conversation_history": self.conversation_history,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "tool_calls": self.tool_calls,
            "agent_response": self.agent_response,
            "token_usage": self.token_usage,
            "context": self.context,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


class FailureDetector:
    """
    失败检测器

    使用方式：
        detector = FailureDetector()

        # 注册失败处理器
        detector.on_failure(lambda case: print(f"检测到失败: {case.id}"))

        # 检测失败
        detector.detect_context_overflow(
            conversation_id="conv_123",
            current_tokens=210000,
            max_tokens=200000,
            user_query="..."
        )

        # 获取失败案例
        cases = detector.get_cases(failure_type=FailureType.CONTEXT_OVERFLOW)
    """

    def __init__(
        self,
        consecutive_error_threshold: int = 3,
        failure_handlers: Optional[List[Callable[[FailureCase], None]]] = None,
    ):
        """
        初始化失败检测器

        Args:
            consecutive_error_threshold: 连续错误阈值
            failure_handlers: 失败处理器列表
        """
        self.consecutive_error_threshold = consecutive_error_threshold
        self.failure_handlers = failure_handlers or []

        # 失败案例存储
        self.cases: List[FailureCase] = []

        # 连续错误计数（按conversation_id）
        self._consecutive_errors: Dict[str, List[datetime]] = defaultdict(list)

        # 统计计数
        self._stats = defaultdict(int)

    # ===================
    # 失败检测方法
    # ===================

    def detect_context_overflow(
        self,
        conversation_id: str,
        current_tokens: int,
        max_tokens: int,
        user_query: str,
        conversation_history: Optional[List[Dict]] = None,
        user_id: Optional[str] = None,
    ) -> FailureCase:
        """
        检测上下文溢出

        Args:
            conversation_id: 会话ID
            current_tokens: 当前Token数
            max_tokens: 最大Token数
            user_query: 用户查询
            conversation_history: 对话历史
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例
        """
        case = FailureCase(
            id=self._generate_id("ctx_overflow"),
            failure_type=FailureType.CONTEXT_OVERFLOW,
            severity=FailureSeverity.HIGH,
            conversation_id=conversation_id,
            user_id=user_id,
            user_query=user_query,
            conversation_history=conversation_history or [],
            error_message=f"上下文溢出: {current_tokens}/{max_tokens} tokens",
            token_usage={
                "current": current_tokens,
                "max": max_tokens,
                "overflow_ratio": current_tokens / max_tokens if max_tokens > 0 else 0,
            },
        )

        self._record_case(case)
        return case

    def detect_tool_failure(
        self,
        conversation_id: str,
        tool_name: str,
        error: str,
        user_query: str,
        tool_arguments: Optional[Dict] = None,
        user_id: Optional[str] = None,
    ) -> Optional[FailureCase]:
        """
        检测工具调用失败

        Args:
            conversation_id: 会话ID
            tool_name: 工具名称
            error: 错误信息
            user_query: 用户查询
            tool_arguments: 工具参数
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例（如果检测到连续错误）
        """
        # 记录错误
        now = datetime.now()
        self._consecutive_errors[conversation_id].append(now)

        # 清理过期记录（5分钟前的）
        cutoff = now - timedelta(minutes=5)
        self._consecutive_errors[conversation_id] = [
            t for t in self._consecutive_errors[conversation_id] if t > cutoff
        ]

        # 检查是否达到连续错误阈值
        if len(self._consecutive_errors[conversation_id]) >= self.consecutive_error_threshold:
            case = FailureCase(
                id=self._generate_id("tool_error"),
                failure_type=FailureType.CONSECUTIVE_TOOL_ERRORS,
                severity=FailureSeverity.MEDIUM,
                conversation_id=conversation_id,
                user_id=user_id,
                user_query=user_query,
                error_message=f"连续{self.consecutive_error_threshold}次工具调用失败: {tool_name}",
                tool_calls=[
                    {
                        "name": tool_name,
                        "arguments": tool_arguments or {},
                        "error": error,
                    }
                ],
                context={
                    "consecutive_errors": len(self._consecutive_errors[conversation_id]),
                },
            )

            self._record_case(case)

            # 重置计数
            self._consecutive_errors[conversation_id] = []

            return case

        return None

    def detect_user_negative_feedback(
        self,
        conversation_id: str,
        user_query: str,
        agent_response: str,
        feedback_comment: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> FailureCase:
        """
        检测用户负面反馈

        Args:
            conversation_id: 会话ID
            user_query: 用户查询
            agent_response: 智能体回复
            feedback_comment: 用户评论
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例
        """
        case = FailureCase(
            id=self._generate_id("negative_feedback"),
            failure_type=FailureType.USER_NEGATIVE_FEEDBACK,
            severity=FailureSeverity.MEDIUM,
            conversation_id=conversation_id,
            user_id=user_id,
            user_query=user_query,
            agent_response=agent_response,
            error_message=f"用户负面反馈: {feedback_comment or '无评论'}",
            context={
                "feedback_comment": feedback_comment,
            },
        )

        self._record_case(case)
        return case

    def detect_intent_mismatch(
        self,
        conversation_id: str,
        user_query: str,
        detected_intent: str,
        expected_intent: str,
        conversation_history: Optional[List[Dict]] = None,
        user_id: Optional[str] = None,
    ) -> FailureCase:
        """
        检测意图识别错误

        Args:
            conversation_id: 会话ID
            user_query: 用户查询
            detected_intent: 检测到的意图
            expected_intent: 预期意图
            conversation_history: 对话历史
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例
        """
        case = FailureCase(
            id=self._generate_id("intent_mismatch"),
            failure_type=FailureType.INTENT_MISMATCH,
            severity=FailureSeverity.MEDIUM,
            conversation_id=conversation_id,
            user_id=user_id,
            user_query=user_query,
            conversation_history=conversation_history or [],
            error_message=f"意图识别错误: 预期'{expected_intent}', 检测到'{detected_intent}'",
            context={
                "detected_intent": detected_intent,
                "expected_intent": expected_intent,
            },
        )

        self._record_case(case)
        return case

    def detect_timeout(
        self,
        conversation_id: str,
        user_query: str,
        timeout_seconds: float,
        partial_response: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> FailureCase:
        """
        检测超时

        Args:
            conversation_id: 会话ID
            user_query: 用户查询
            timeout_seconds: 超时时间（秒）
            partial_response: 部分响应
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例
        """
        case = FailureCase(
            id=self._generate_id("timeout"),
            failure_type=FailureType.TIMEOUT,
            severity=FailureSeverity.HIGH,
            conversation_id=conversation_id,
            user_id=user_id,
            user_query=user_query,
            agent_response=partial_response or "",
            error_message=f"执行超时: {timeout_seconds}秒",
            context={
                "timeout_seconds": timeout_seconds,
                "has_partial_response": bool(partial_response),
            },
        )

        self._record_case(case)
        return case

    def detect_generic_error(
        self,
        conversation_id: str,
        user_query: str,
        error: Exception,
        stack_trace: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> FailureCase:
        """
        检测通用错误

        Args:
            conversation_id: 会话ID
            user_query: 用户查询
            error: 异常对象
            stack_trace: 堆栈跟踪
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例
        """
        case = FailureCase(
            id=self._generate_id("error"),
            failure_type=FailureType.UNKNOWN_ERROR,
            severity=FailureSeverity.HIGH,
            conversation_id=conversation_id,
            user_id=user_id,
            user_query=user_query,
            error_message=str(error),
            stack_trace=stack_trace,
            context={
                "error_type": type(error).__name__,
            },
        )

        self._record_case(case)
        return case

    async def detect_response_quality(
        self,
        conversation_id: str,
        user_query: str,
        agent_response: str,
        transcript: Dict[str, Any],
        llm_judge: Any,
        user_id: Optional[str] = None,
    ) -> Optional[FailureCase]:
        """
        使用 LLM Judge 检测响应质量问题

        检测维度：
        1. 回答质量（准确性、完整性、流畅性）
        2. 过度工程化（工具调用过多、Plan 过于复杂）
        3. 逻辑连贯性（推理过程是否合理）

        Args:
            conversation_id: 会话ID
            user_query: 用户查询
            agent_response: 智能体回复
            transcript: 转录记录（包含工具调用、消息历史等）
            llm_judge: ModelBasedGraders 实例
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例（如果检测到质量问题）
        """
        try:
            # 构建 Transcript 对象（如果传入的是字典）
            from evaluation.models import Message, ToolCall, Transcript
            from models.usage import TokenUsage

            if isinstance(transcript, dict):
                # 从字典构建 Transcript
                messages = [
                    Message(**msg) if isinstance(msg, dict) else msg
                    for msg in transcript.get("messages", [])
                ]
                tool_calls = [
                    ToolCall(**tc) if isinstance(tc, dict) else tc
                    for tc in transcript.get("tool_calls", [])
                ]
                token_usage = TokenUsage(**transcript.get("token_usage", {}))

                transcript_obj = Transcript(
                    messages=messages,
                    tool_calls=tool_calls,
                    token_usage=token_usage,
                    duration_ms=transcript.get("duration_ms", 0),
                    metadata=transcript.get("metadata", {}),
                )
            else:
                transcript_obj = transcript

            # 调用 ModelBasedGraders 评估
            quality_result = await llm_judge.grade_response_quality(
                user_query=user_query,
                agent_response=agent_response,
            )

            over_eng_result = await llm_judge.grade_over_engineering(
                user_query=user_query,
                transcript=transcript_obj,
            )

            # 判断是否失败
            quality_failed = quality_result.score is not None and quality_result.score < 0.6
            over_eng_failed = over_eng_result.score is not None and over_eng_result.score < 0.6

            if quality_failed or over_eng_failed:
                failure_type = (
                    FailureType.OVER_ENGINEERING
                    if over_eng_failed
                    else FailureType.RESPONSE_QUALITY
                )

                case = FailureCase(
                    id=self._generate_id("quality"),
                    failure_type=failure_type,
                    severity=FailureSeverity.MEDIUM,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    user_query=user_query,
                    agent_response=agent_response,
                    error_message=f"响应质量问题: 质量评分={quality_result.score:.2f}, 过度工程化评分={over_eng_result.score:.2f}",
                    tool_calls=[
                        {
                            "name": tc.name,
                            "arguments": tc.arguments if hasattr(tc, "arguments") else {},
                        }
                        for tc in transcript_obj.tool_calls
                    ],
                    context={
                        "quality_score": quality_result.score,
                        "over_engineering_score": over_eng_result.score,
                        "quality_explanation": quality_result.explanation,
                        "over_engineering_explanation": over_eng_result.explanation,
                    },
                )

                self._record_case(case)
                return case

        except Exception as e:
            logger.error(f"检测响应质量失败: {e}", exc_info=True)

        return None

    def detect_user_retry(
        self,
        conversation_id: str,
        current_query: str,
        previous_queries: List[str],
        similarity_threshold: float = 0.85,
        user_id: Optional[str] = None,
    ) -> Optional[FailureCase]:
        """
        检测用户重试（隐式不满）

        当用户重新提问相似问题时，说明之前的回答可能不满意

        Args:
            conversation_id: 会话ID
            current_query: 当前查询
            previous_queries: 之前的查询列表（最近N条）
            similarity_threshold: 相似度阈值（默认0.85）
            user_id: 用户ID

        Returns:
            FailureCase: 失败案例（如果检测到重试）
        """
        # 计算与之前问题的相似度
        for prev_query in previous_queries[-3:]:  # 检查最近 3 条
            similarity = self._compute_similarity(current_query, prev_query)
            if similarity > similarity_threshold:
                case = FailureCase(
                    id=self._generate_id("retry"),
                    failure_type=FailureType.USER_RETRY,
                    severity=FailureSeverity.LOW,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    user_query=current_query,
                    error_message=f"用户重试相似问题: 相似度={similarity:.2f}, 之前问题='{prev_query[:50]}...'",
                    context={
                        "previous_query": prev_query,
                        "similarity": similarity,
                        "similarity_threshold": similarity_threshold,
                    },
                )

                self._record_case(case)
                return case

        return None

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度（简化版，使用 Jaccard 相似度）

        Args:
            text1: 文本1
            text2: 文本2

        Returns:
            float: 相似度（0-1）
        """
        # 简单的基于词汇的相似度
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    # ===================
    # 案例管理
    # ===================

    def _generate_id(self, prefix: str) -> str:
        """生成唯一ID"""
        import uuid

        return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4()}"

    def _record_case(self, case: FailureCase) -> None:
        """
        记录失败案例

        Args:
            case: 失败案例
        """
        self.cases.append(case)
        self._stats[case.failure_type.value] += 1

        logger.warning(
            f"🔴 检测到失败: [{case.failure_type.value}] {case.error_message} "
            f"(conversation: {case.conversation_id})"
        )

        # 调用处理器
        for handler in self.failure_handlers:
            try:
                handler(case)
            except Exception as e:
                logger.error(f"失败处理器执行异常: {e}")

    def on_failure(self, handler: Callable[[FailureCase], None]) -> None:
        """
        注册失败处理器

        Args:
            handler: 处理函数
        """
        self.failure_handlers.append(handler)

    def get_cases(
        self,
        failure_type: Optional[FailureType] = None,
        severity: Optional[FailureSeverity] = None,
        status: Optional[str] = None,
        time_range_hours: Optional[int] = None,
        limit: int = 100,
    ) -> List[FailureCase]:
        """
        获取失败案例

        Args:
            failure_type: 失败类型筛选
            severity: 严重程度筛选
            status: 状态筛选
            time_range_hours: 时间范围（小时）
            limit: 返回数量限制

        Returns:
            List[FailureCase]: 失败案例列表
        """
        cases = self.cases.copy()

        if failure_type:
            cases = [c for c in cases if c.failure_type == failure_type]

        if severity:
            cases = [c for c in cases if c.severity == severity]

        if status:
            cases = [c for c in cases if c.status == status]

        if time_range_hours:
            cutoff = datetime.now() - timedelta(hours=time_range_hours)
            cases = [c for c in cases if c.timestamp >= cutoff]

        # 按时间倒序
        cases.sort(key=lambda c: c.timestamp, reverse=True)

        return cases[:limit]

    def mark_reviewed(self, case_id: str, reviewer: str) -> Optional[FailureCase]:
        """
        标记案例为已审查

        Args:
            case_id: 案例ID
            reviewer: 审查人

        Returns:
            FailureCase: 更新后的案例
        """
        for case in self.cases:
            if case.id == case_id:
                case.status = "reviewed"
                case.reviewed_by = reviewer
                case.reviewed_at = datetime.now()
                return case
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        # 按类型统计
        by_type = defaultdict(int)
        by_severity = defaultdict(int)
        by_status = defaultdict(int)

        for case in self.cases:
            by_type[case.failure_type.value] += 1
            by_severity[case.severity.value] += 1
            by_status[case.status] += 1

        # 最近24小时
        cutoff = datetime.now() - timedelta(hours=24)
        recent_cases = [c for c in self.cases if c.timestamp >= cutoff]

        return {
            "total_cases": len(self.cases),
            "recent_24h": len(recent_cases),
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
            "by_status": dict(by_status),
            "pending_review": by_status.get("new", 0),
        }
