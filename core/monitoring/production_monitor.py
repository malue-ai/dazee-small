"""
生产监控器（Production Monitor）

实时监控生产环境，负责：
1. 采集性能指标（响应延迟、Token消耗、工具调用成功率）
2. 触发告警（阈值超限时）
3. 记录审计日志（用于问题追溯）
4. 与失败检测器协同工作
"""

import asyncio
import time
from logger import get_logger
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = get_logger(__name__)


class MetricType(str, Enum):
    """指标类型"""
    LATENCY = "latency"                    # 响应延迟（毫秒）
    TOKEN_INPUT = "token_input"            # 输入Token数
    TOKEN_OUTPUT = "token_output"          # 输出Token数
    TOKEN_TOTAL = "token_total"            # 总Token数
    TOOL_CALL_SUCCESS = "tool_call_success"  # 工具调用成功率
    TOOL_CALL_ERROR = "tool_call_error"    # 工具调用错误数
    CONTEXT_OVERFLOW = "context_overflow"  # 上下文溢出次数
    USER_FEEDBACK_NEGATIVE = "user_feedback_negative"  # 负面反馈数


class AlertLevel(str, Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MetricPoint:
    """指标数据点"""
    metric_type: MetricType
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class Alert:
    """告警"""
    level: AlertLevel
    metric_type: MetricType
    message: str
    value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "metric": self.metric_type.value,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


class ProductionMonitor:
    """
    生产监控器
    
    使用方式：
        monitor = ProductionMonitor()
        
        # 记录指标
        monitor.record_latency(conversation_id="conv_123", latency_ms=500)
        monitor.record_token_usage(conversation_id="conv_123", input=1000, output=500)
        
        # 获取统计
        stats = monitor.get_statistics(time_range_minutes=60)
        
        # 获取告警
        alerts = monitor.get_recent_alerts()
    """
    
    def __init__(
        self,
        alert_handlers: Optional[List[Callable[[Alert], None]]] = None,
        max_history_size: int = 10000,
    ):
        """
        初始化生产监控器
        
        Args:
            alert_handlers: 告警处理器列表
            max_history_size: 历史数据最大条数
        """
        self.alert_handlers = alert_handlers or []
        self.max_history_size = max_history_size
        
        # 指标历史（使用deque自动限制大小）
        self.metrics_history: deque[MetricPoint] = deque(maxlen=max_history_size)
        
        # 告警历史
        self.alerts_history: deque[Alert] = deque(maxlen=1000)
        
        # 告警阈值配置
        self.thresholds = {
            MetricType.LATENCY: {
                AlertLevel.WARNING: 5000,   # 5秒
                AlertLevel.ERROR: 10000,    # 10秒
                AlertLevel.CRITICAL: 30000, # 30秒
            },
            MetricType.TOKEN_TOTAL: {
                AlertLevel.WARNING: 150000,   # 150K
                AlertLevel.ERROR: 190000,     # 190K
                AlertLevel.CRITICAL: 200000,  # 200K（接近溢出）
            },
            MetricType.TOOL_CALL_ERROR: {
                AlertLevel.WARNING: 3,   # 3次错误
                AlertLevel.ERROR: 5,     # 5次错误
                AlertLevel.CRITICAL: 10, # 10次错误
            },
            MetricType.CONTEXT_OVERFLOW: {
                AlertLevel.ERROR: 1,     # 任何溢出都是错误
            },
        }
        
        # 计数器（用于统计）
        self._counters: Dict[str, int] = {}
        
    # ===================
    # 指标记录
    # ===================
    
    def record_metric(
        self,
        metric_type: MetricType,
        value: float,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        记录指标
        
        Args:
            metric_type: 指标类型
            value: 指标值
            labels: 标签（如conversation_id, user_id等）
        """
        point = MetricPoint(
            metric_type=metric_type,
            value=value,
            labels=labels or {},
        )
        self.metrics_history.append(point)
        
        # 检查是否需要告警
        self._check_threshold(point)
        
        logger.debug(f"📊 记录指标: {metric_type.value}={value}")
    
    def record_latency(
        self,
        latency_ms: float,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        记录响应延迟
        
        Args:
            latency_ms: 延迟（毫秒）
            conversation_id: 会话ID
            user_id: 用户ID
        """
        labels = {}
        if conversation_id:
            labels["conversation_id"] = conversation_id
        if user_id:
            labels["user_id"] = user_id
        
        self.record_metric(MetricType.LATENCY, latency_ms, labels)
    
    def record_token_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int = 0,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        记录Token使用量
        
        Args:
            input_tokens: 输入Token数
            output_tokens: 输出Token数
            thinking_tokens: 思考Token数
            conversation_id: 会话ID
            user_id: 用户ID
        """
        labels = {}
        if conversation_id:
            labels["conversation_id"] = conversation_id
        if user_id:
            labels["user_id"] = user_id
        
        self.record_metric(MetricType.TOKEN_INPUT, input_tokens, labels)
        self.record_metric(MetricType.TOKEN_OUTPUT, output_tokens, labels)
        self.record_metric(
            MetricType.TOKEN_TOTAL, 
            input_tokens + output_tokens + thinking_tokens, 
            labels
        )
    
    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> None:
        """
        记录工具调用
        
        Args:
            tool_name: 工具名称
            success: 是否成功
            duration_ms: 执行时长
            error: 错误信息
            conversation_id: 会话ID
        """
        labels = {"tool": tool_name}
        if conversation_id:
            labels["conversation_id"] = conversation_id
        
        if success:
            self.record_metric(MetricType.TOOL_CALL_SUCCESS, 1, labels)
        else:
            self.record_metric(MetricType.TOOL_CALL_ERROR, 1, labels)
            logger.warning(f"⚠️ 工具调用失败: {tool_name}, 错误: {error}")
    
    def record_context_overflow(
        self,
        conversation_id: str,
        current_tokens: int,
        max_tokens: int
    ) -> None:
        """
        记录上下文溢出
        
        Args:
            conversation_id: 会话ID
            current_tokens: 当前Token数
            max_tokens: 最大Token数
        """
        labels = {
            "conversation_id": conversation_id,
            "current_tokens": str(current_tokens),
            "max_tokens": str(max_tokens),
        }
        
        self.record_metric(MetricType.CONTEXT_OVERFLOW, 1, labels)
        logger.error(f"🚨 上下文溢出: {conversation_id}, {current_tokens}/{max_tokens}")
    
    def record_user_feedback(
        self,
        feedback_type: str,
        conversation_id: str,
        user_id: Optional[str] = None,
        comment: Optional[str] = None
    ) -> None:
        """
        记录用户反馈
        
        Args:
            feedback_type: 反馈类型（positive/negative）
            conversation_id: 会话ID
            user_id: 用户ID
            comment: 用户评论
        """
        labels = {
            "conversation_id": conversation_id,
            "feedback_type": feedback_type,
        }
        if user_id:
            labels["user_id"] = user_id
        if comment:
            labels["comment"] = comment[:100]  # 截断
        
        if feedback_type == "negative":
            self.record_metric(MetricType.USER_FEEDBACK_NEGATIVE, 1, labels)
            logger.warning(f"👎 用户负面反馈: {conversation_id}")
    
    # ===================
    # 阈值检查与告警
    # ===================
    
    def _check_threshold(self, point: MetricPoint) -> None:
        """
        检查指标是否超过阈值，触发告警
        
        Args:
            point: 指标数据点
        """
        thresholds = self.thresholds.get(point.metric_type, {})
        
        for level, threshold in thresholds.items():
            if point.value >= threshold:
                alert = Alert(
                    level=level,
                    metric_type=point.metric_type,
                    message=f"{point.metric_type.value} 超过阈值: {point.value} >= {threshold}",
                    value=point.value,
                    threshold=threshold,
                    labels=point.labels,
                )
                self._trigger_alert(alert)
                break  # 只触发最高级别的告警
    
    def _trigger_alert(self, alert: Alert) -> None:
        """
        触发告警
        
        Args:
            alert: 告警对象
        """
        self.alerts_history.append(alert)
        
        # 记录日志
        log_msg = f"🚨 告警 [{alert.level.value}]: {alert.message}"
        if alert.level == AlertLevel.CRITICAL:
            logger.critical(log_msg)
        elif alert.level == AlertLevel.ERROR:
            logger.error(log_msg)
        elif alert.level == AlertLevel.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
        
        # 调用告警处理器
        for handler in self.alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"告警处理器执行失败: {e}")
    
    def add_alert_handler(self, handler: Callable[[Alert], None]) -> None:
        """
        添加告警处理器
        
        Args:
            handler: 告警处理函数
        """
        self.alert_handlers.append(handler)
    
    # ===================
    # 统计查询
    # ===================
    
    def get_statistics(
        self,
        time_range_minutes: int = 60,
        metric_types: Optional[List[MetricType]] = None
    ) -> Dict[str, Any]:
        """
        获取统计信息
        
        Args:
            time_range_minutes: 时间范围（分钟）
            metric_types: 指定的指标类型
            
        Returns:
            Dict: 统计信息
        """
        cutoff = datetime.now() - timedelta(minutes=time_range_minutes)
        
        # 筛选时间范围内的指标
        recent_metrics = [
            m for m in self.metrics_history 
            if m.timestamp >= cutoff
        ]
        
        # 按类型分组
        by_type: Dict[MetricType, List[float]] = {}
        for m in recent_metrics:
            if metric_types is None or m.metric_type in metric_types:
                if m.metric_type not in by_type:
                    by_type[m.metric_type] = []
                by_type[m.metric_type].append(m.value)
        
        # 计算统计量
        stats = {}
        for metric_type, values in by_type.items():
            if values:
                stats[metric_type.value] = {
                    "count": len(values),
                    "sum": sum(values),
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }
        
        return {
            "time_range_minutes": time_range_minutes,
            "total_points": len(recent_metrics),
            "metrics": stats,
        }
    
    def get_recent_alerts(
        self,
        limit: int = 100,
        level: Optional[AlertLevel] = None
    ) -> List[Dict[str, Any]]:
        """
        获取最近的告警
        
        Args:
            limit: 返回数量限制
            level: 告警级别筛选
            
        Returns:
            List[Dict]: 告警列表
        """
        alerts = list(self.alerts_history)
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        # 按时间倒序
        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        
        return [a.to_dict() for a in alerts[:limit]]
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        获取健康状态
        
        Returns:
            Dict: 健康状态
        """
        # 最近5分钟的统计
        stats = self.get_statistics(time_range_minutes=5)
        
        # 最近的告警
        recent_alerts = self.get_recent_alerts(limit=10)
        
        # 计算健康评分
        health_score = 100
        
        # 根据告警扣分
        for alert in recent_alerts:
            if alert["level"] == "critical":
                health_score -= 30
            elif alert["level"] == "error":
                health_score -= 10
            elif alert["level"] == "warning":
                health_score -= 5
        
        health_score = max(0, health_score)
        
        # 确定状态
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 50:
            status = "degraded"
        else:
            status = "unhealthy"
        
        return {
            "status": status,
            "health_score": health_score,
            "statistics": stats,
            "recent_alerts_count": len(recent_alerts),
            "timestamp": datetime.now().isoformat(),
        }


class MonitoringContext:
    """
    监控上下文管理器（用于自动记录指标）
    
    使用方式：
        async with MonitoringContext(monitor, conversation_id="conv_123") as ctx:
            # 执行Agent
            result = await agent.chat(...)
            
            # 记录Token使用
            ctx.record_tokens(input=1000, output=500)
            
        # 自动记录延迟
    """
    
    def __init__(
        self,
        monitor: ProductionMonitor,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        self.monitor = monitor
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.start_time: Optional[float] = None
        
    async def __aenter__(self):
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            latency_ms = (time.time() - self.start_time) * 1000
            self.monitor.record_latency(
                latency_ms=latency_ms,
                conversation_id=self.conversation_id,
                user_id=self.user_id,
            )
        
        # 如果有异常，记录
        if exc_type:
            logger.error(f"监控上下文异常: {exc_val}")
        
        return False
    
    def record_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int = 0
    ) -> None:
        """记录Token使用"""
        self.monitor.record_token_usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            conversation_id=self.conversation_id,
            user_id=self.user_id,
        )
    
    def record_tool_call(
        self,
        tool_name: str,
        success: bool,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None
    ) -> None:
        """记录工具调用"""
        self.monitor.record_tool_call(
            tool_name=tool_name,
            success=success,
            duration_ms=duration_ms,
            error=error,
            conversation_id=self.conversation_id,
        )
