"""
Token 审计模块

功能：
1. 记录每次 Agent 执行的 Token 消耗
2. 支持多维度统计（智能体级、会话级、用户级）
3. 与评估系统集成，用于成本分析
4. 安全保护：异常消耗告警

架构位置：core/monitoring/token_audit.py
依赖：evaluation/models.py (TokenUsage)
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from evaluation.models import TokenUsage

logger = logging.getLogger(__name__)


class AuditLevel(str, Enum):
    """审计级别"""
    TURN = "turn"           # 单轮对话
    SESSION = "session"     # 单次会话
    CONVERSATION = "conversation"  # 整个对话
    USER = "user"           # 用户级别
    AGENT = "agent"         # 智能体级别


class TokenAuditRecord(BaseModel):
    """Token 审计记录"""
    record_id: str = Field(..., description="记录唯一标识")
    level: AuditLevel = Field(..., description="审计级别")
    
    # 关联 ID
    session_id: Optional[str] = Field(None, description="会话 ID")
    conversation_id: Optional[str] = Field(None, description="对话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    agent_id: Optional[str] = Field(None, description="智能体 ID")
    turn_number: Optional[int] = Field(None, description="对话轮次")
    
    # Token 使用详情
    usage: TokenUsage = Field(default_factory=TokenUsage, description="Token 使用统计")
    
    # 元数据
    model: str = Field("unknown", description="使用的模型")
    timestamp: datetime = Field(default_factory=datetime.now)
    duration_ms: int = Field(0, description="执行耗时（毫秒）")
    
    # 用户查询信息（脱敏后）
    query_length: int = Field(0, description="用户查询长度")
    query_hash: Optional[str] = Field(None, description="用户查询哈希（用于去重）")
    
    # 安全标记
    is_anomaly: bool = Field(False, description="是否为异常消耗")
    anomaly_reason: Optional[str] = Field(None, description="异常原因")


class TokenAuditStats(BaseModel):
    """Token 审计统计"""
    total_records: int = 0
    
    # 总计
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    
    # 平均值
    avg_input_tokens: float = 0.0
    avg_output_tokens: float = 0.0
    avg_thinking_tokens: float = 0.0
    
    # 峰值
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    max_thinking_tokens: int = 0
    
    # 异常统计
    anomaly_count: int = 0
    anomaly_rate: float = 0.0
    
    # 时间范围
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def total_tokens(self) -> int:
        """总 Token 数"""
        return self.total_input_tokens + self.total_output_tokens + self.total_thinking_tokens
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        total_read = self.total_input_tokens
        if total_read == 0:
            return 0.0
        return self.total_cache_read_tokens / total_read


class TokenAuditor:
    """
    Token 审计器
    
    功能：
    1. 记录每次执行的 Token 消耗
    2. 多维度统计分析
    3. 异常检测与告警
    4. 与评估系统集成
    """
    
    def __init__(
        self,
        # 异常检测阈值
        max_input_tokens: int = 150_000,      # 单次最大输入 Token
        max_output_tokens: int = 50_000,      # 单次最大输出 Token
        max_thinking_tokens: int = 100_000,   # 单次最大 Thinking Token
        # 存储配置
        max_records: int = 10_000,            # 最大保留记录数
        enable_persistence: bool = False      # 是否持久化（默认内存）
    ):
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.max_thinking_tokens = max_thinking_tokens
        self.max_records = max_records
        self.enable_persistence = enable_persistence
        
        # 内存存储
        self._records: List[TokenAuditRecord] = []
        
        # 按维度索引（快速查询）
        self._by_session: Dict[str, List[str]] = {}      # session_id -> record_ids
        self._by_conversation: Dict[str, List[str]] = {} # conversation_id -> record_ids
        self._by_user: Dict[str, List[str]] = {}         # user_id -> record_ids
        self._by_agent: Dict[str, List[str]] = {}        # agent_id -> record_ids
        
        logger.info(
            f"✅ TokenAuditor 初始化: max_input={max_input_tokens:,}, "
            f"max_output={max_output_tokens:,}, max_thinking={max_thinking_tokens:,}"
        )
    
    def record(
        self,
        session_id: str,
        usage: TokenUsage,
        *,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        turn_number: Optional[int] = None,
        model: str = "unknown",
        duration_ms: int = 0,
        query_length: int = 0,
        query_hash: Optional[str] = None
    ) -> TokenAuditRecord:
        """
        记录一次 Token 消耗
        
        Args:
            session_id: 会话 ID
            usage: Token 使用统计
            conversation_id: 对话 ID
            user_id: 用户 ID
            agent_id: 智能体 ID
            turn_number: 对话轮次
            model: 使用的模型
            duration_ms: 执行耗时
            query_length: 用户查询长度
            query_hash: 用户查询哈希
            
        Returns:
            TokenAuditRecord 记录
        """
        record_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._records)}"
        
        # 异常检测
        is_anomaly = False
        anomaly_reason = None
        
        if usage.input_tokens > self.max_input_tokens:
            is_anomaly = True
            anomaly_reason = f"输入 Token 超限: {usage.input_tokens:,} > {self.max_input_tokens:,}"
        elif usage.output_tokens > self.max_output_tokens:
            is_anomaly = True
            anomaly_reason = f"输出 Token 超限: {usage.output_tokens:,} > {self.max_output_tokens:,}"
        elif usage.thinking_tokens > self.max_thinking_tokens:
            is_anomaly = True
            anomaly_reason = f"Thinking Token 超限: {usage.thinking_tokens:,} > {self.max_thinking_tokens:,}"
        
        if is_anomaly:
            logger.warning(f"⚠️ Token 异常告警: {anomaly_reason} (session={session_id})")
        
        # 创建记录
        record = TokenAuditRecord(
            record_id=record_id,
            level=AuditLevel.TURN,
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            agent_id=agent_id,
            turn_number=turn_number,
            usage=usage,
            model=model,
            duration_ms=duration_ms,
            query_length=query_length,
            query_hash=query_hash,
            is_anomaly=is_anomaly,
            anomaly_reason=anomaly_reason
        )
        
        # 存储
        self._records.append(record)
        
        # 更新索引
        if session_id:
            self._by_session.setdefault(session_id, []).append(record_id)
        if conversation_id:
            self._by_conversation.setdefault(conversation_id, []).append(record_id)
        if user_id:
            self._by_user.setdefault(user_id, []).append(record_id)
        if agent_id:
            self._by_agent.setdefault(agent_id, []).append(record_id)
        
        # 限制记录数
        if len(self._records) > self.max_records:
            self._cleanup_old_records()
        
        logger.debug(
            f"📊 Token 记录: input={usage.input_tokens:,}, output={usage.output_tokens:,}, "
            f"thinking={usage.thinking_tokens:,}, cache_read={usage.cache_read_tokens:,}"
        )
        
        return record
    
    def get_stats(
        self,
        *,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> TokenAuditStats:
        """
        获取 Token 审计统计
        
        Args:
            session_id: 按会话筛选
            conversation_id: 按对话筛选
            user_id: 按用户筛选
            agent_id: 按智能体筛选
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            TokenAuditStats 统计
        """
        # 筛选记录
        records = self._filter_records(
            session_id=session_id,
            conversation_id=conversation_id,
            user_id=user_id,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time
        )
        
        if not records:
            return TokenAuditStats()
        
        # 计算统计
        total_input = sum(r.usage.input_tokens for r in records)
        total_output = sum(r.usage.output_tokens for r in records)
        total_thinking = sum(r.usage.thinking_tokens for r in records)
        total_cache_read = sum(r.usage.cache_read_tokens for r in records)
        total_cache_write = sum(r.usage.cache_write_tokens for r in records)
        
        max_input = max(r.usage.input_tokens for r in records)
        max_output = max(r.usage.output_tokens for r in records)
        max_thinking = max(r.usage.thinking_tokens for r in records)
        
        anomaly_count = sum(1 for r in records if r.is_anomaly)
        
        n = len(records)
        
        return TokenAuditStats(
            total_records=n,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_thinking_tokens=total_thinking,
            total_cache_read_tokens=total_cache_read,
            total_cache_write_tokens=total_cache_write,
            avg_input_tokens=total_input / n,
            avg_output_tokens=total_output / n,
            avg_thinking_tokens=total_thinking / n,
            max_input_tokens=max_input,
            max_output_tokens=max_output,
            max_thinking_tokens=max_thinking,
            anomaly_count=anomaly_count,
            anomaly_rate=anomaly_count / n,
            start_time=min(r.timestamp for r in records),
            end_time=max(r.timestamp for r in records)
        )
    
    def get_comparison(
        self,
        agent_ids: List[str]
    ) -> Dict[str, TokenAuditStats]:
        """
        比较多个智能体的 Token 消耗
        
        Args:
            agent_ids: 智能体 ID 列表
            
        Returns:
            Dict[agent_id, TokenAuditStats]
        """
        result = {}
        for agent_id in agent_ids:
            result[agent_id] = self.get_stats(agent_id=agent_id)
        return result
    
    def export_for_evaluation(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        导出评估系统所需的 Token 数据
        
        Args:
            session_id: 会话 ID
            
        Returns:
            与 evaluation/models.py TokenUsage 兼容的字典
        """
        stats = self.get_stats(session_id=session_id)
        
        return {
            "input_tokens": stats.total_input_tokens,
            "output_tokens": stats.total_output_tokens,
            "thinking_tokens": stats.total_thinking_tokens,
            "cache_read_tokens": stats.total_cache_read_tokens,
            "cache_write_tokens": stats.total_cache_write_tokens,
            "total_tokens": stats.total_tokens,
            "cache_hit_rate": stats.cache_hit_rate,
            "anomaly_count": stats.anomaly_count,
            "anomaly_rate": stats.anomaly_rate
        }
    
    def _filter_records(
        self,
        *,
        session_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[TokenAuditRecord]:
        """筛选记录"""
        records = self._records
        
        if session_id:
            record_ids = set(self._by_session.get(session_id, []))
            records = [r for r in records if r.record_id in record_ids]
        
        if conversation_id:
            record_ids = set(self._by_conversation.get(conversation_id, []))
            records = [r for r in records if r.record_id in record_ids]
        
        if user_id:
            record_ids = set(self._by_user.get(user_id, []))
            records = [r for r in records if r.record_id in record_ids]
        
        if agent_id:
            record_ids = set(self._by_agent.get(agent_id, []))
            records = [r for r in records if r.record_id in record_ids]
        
        if start_time:
            records = [r for r in records if r.timestamp >= start_time]
        
        if end_time:
            records = [r for r in records if r.timestamp <= end_time]
        
        return records
    
    def _cleanup_old_records(self):
        """清理旧记录（保留最近的 max_records 条）"""
        if len(self._records) <= self.max_records:
            return
        
        # 按时间排序，保留最新的
        self._records.sort(key=lambda r: r.timestamp, reverse=True)
        removed = self._records[self.max_records:]
        self._records = self._records[:self.max_records]
        
        # 更新索引
        removed_ids = {r.record_id for r in removed}
        
        for key in list(self._by_session.keys()):
            self._by_session[key] = [
                rid for rid in self._by_session[key] 
                if rid not in removed_ids
            ]
            if not self._by_session[key]:
                del self._by_session[key]
        
        # 同样处理其他索引...
        logger.info(f"🧹 清理旧审计记录: 移除 {len(removed)} 条")


# ============================================================
# 全局实例（单例模式）
# ============================================================

_auditor: Optional[TokenAuditor] = None


def get_token_auditor() -> TokenAuditor:
    """获取全局 Token 审计器实例"""
    global _auditor
    if _auditor is None:
        _auditor = TokenAuditor()
    return _auditor


def create_token_auditor(**kwargs) -> TokenAuditor:
    """创建新的 Token 审计器实例"""
    return TokenAuditor(**kwargs)
