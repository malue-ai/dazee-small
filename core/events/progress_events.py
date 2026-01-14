"""
进度事件

提供用户体验增强的进度反馈机制
"""

from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime

from logger import get_logger
from core.events.base import EventEmitter

logger = get_logger(__name__)


class StageType(str, Enum):
    """阶段类型"""
    # 意图分析
    INTENT_ANALYSIS = "intent_analysis"
    
    # 计划生成
    PLAN_GENERATION = "plan_generation"
    
    # 记忆检索
    MEMORY_RETRIEVAL = "memory_retrieval"
    
    # 工具选择
    TOOL_SELECTION = "tool_selection"
    
    # 工具执行
    TOOL_EXECUTION = "tool_execution"
    
    # 内容生成
    CONTENT_GENERATION = "content_generation"
    
    # 结果验证
    RESULT_VALIDATION = "result_validation"
    
    # 后处理
    POST_PROCESSING = "post_processing"


class StageStatus(str, Enum):
    """阶段状态"""
    PENDING = "pending"          # 待开始
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"      # 已完成
    SKIPPED = "skipped"          # 已跳过
    FAILED = "failed"            # 失败


class ProgressEmitter(EventEmitter):
    """
    进度事件发射器
    
    提供阶段通知、进度百分比、预估时间等用户体验增强功能
    """
    
    async def emit_stage_start(
        self,
        session_id: str,
        stage: StageType,
        stage_name: str,
        description: Optional[str] = None,
        estimated_duration: Optional[float] = None
    ):
        """
        发送阶段开始事件
        
        Args:
            session_id: 会话ID
            stage: 阶段类型
            stage_name: 阶段名称（用户可见）
            description: 阶段描述
            estimated_duration: 预估耗时（秒）
        """
        await self.emit(
            "progress_stage_start",
            session_id,
            data={
                "stage": stage.value,
                "stage_name": stage_name,
                "description": description,
                "estimated_duration": estimated_duration,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        logger.debug(
            f"🚀 阶段开始: {stage_name} (session={session_id})"
        )
    
    async def emit_stage_end(
        self,
        session_id: str,
        stage: StageType,
        stage_name: str,
        status: StageStatus,
        duration: Optional[float] = None,
        result_summary: Optional[str] = None
    ):
        """
        发送阶段结束事件
        
        Args:
            session_id: 会话ID
            stage: 阶段类型
            stage_name: 阶段名称
            status: 阶段状态
            duration: 实际耗时（秒）
            result_summary: 结果摘要
        """
        await self.emit(
            "progress_stage_end",
            session_id,
            data={
                "stage": stage.value,
                "stage_name": stage_name,
                "status": status.value,
                "duration": duration,
                "result_summary": result_summary,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        status_emoji = {
            StageStatus.COMPLETED: "✅",
            StageStatus.SKIPPED: "⏭️",
            StageStatus.FAILED: "❌"
        }.get(status, "")
        
        logger.debug(
            f"{status_emoji} 阶段结束: {stage_name} "
            f"(status={status.value}, duration={duration:.2f}s)"
        )
    
    async def emit_progress_update(
        self,
        session_id: str,
        current_step: int,
        total_steps: int,
        progress: float,
        current_action: str,
        estimated_remaining_time: Optional[float] = None
    ):
        """
        发送进度更新事件
        
        Args:
            session_id: 会话ID
            current_step: 当前步骤（从1开始）
            total_steps: 总步骤数
            progress: 进度百分比（0.0-1.0）
            current_action: 当前动作描述
            estimated_remaining_time: 预估剩余时间（秒）
        """
        await self.emit(
            "progress_update",
            session_id,
            data={
                "current_step": current_step,
                "total_steps": total_steps,
                "progress": progress,
                "progress_percent": int(progress * 100),
                "current_action": current_action,
                "estimated_remaining_time": estimated_remaining_time,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        logger.debug(
            f"📊 进度更新: {current_step}/{total_steps} ({progress:.1%}) "
            f"- {current_action}"
        )
    
    async def emit_intermediate_result(
        self,
        session_id: str,
        result_type: str,
        result_data: Any,
        display_message: Optional[str] = None
    ):
        """
        发送中间结果事件（展示给用户）
        
        Args:
            session_id: 会话ID
            result_type: 结果类型（如 "search_results", "analysis"）
            result_data: 结果数据
            display_message: 用户可见的消息
        """
        await self.emit(
            "progress_intermediate_result",
            session_id,
            data={
                "result_type": result_type,
                "result_data": result_data,
                "display_message": display_message,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        logger.debug(
            f"📦 中间结果: {result_type} (session={session_id})"
        )
    
    async def emit_waiting_notification(
        self,
        session_id: str,
        reason: str,
        estimated_wait_time: Optional[float] = None,
        tips: Optional[List[str]] = None
    ):
        """
        发送等待通知（长时间操作时提示用户）
        
        Args:
            session_id: 会话ID
            reason: 等待原因
            estimated_wait_time: 预估等待时间（秒）
            tips: 提示信息列表
        """
        await self.emit(
            "progress_waiting",
            session_id,
            data={
                "reason": reason,
                "estimated_wait_time": estimated_wait_time,
                "tips": tips or [],
                "timestamp": datetime.now().isoformat()
            }
        )
        
        logger.debug(
            f"⏰ 等待通知: {reason} "
            f"(预计{estimated_wait_time}秒)"
        )
    
    async def emit_retry_notification(
        self,
        session_id: str,
        operation: str,
        attempt: int,
        max_attempts: int,
        reason: str,
        next_retry_in: Optional[float] = None
    ):
        """
        发送重试通知
        
        Args:
            session_id: 会话ID
            operation: 操作名称
            attempt: 当前尝试次数
            max_attempts: 最大尝试次数
            reason: 重试原因
            next_retry_in: 下次重试延迟（秒）
        """
        await self.emit(
            "progress_retry",
            session_id,
            data={
                "operation": operation,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "reason": reason,
                "next_retry_in": next_retry_in,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        logger.debug(
            f"🔄 重试通知: {operation} "
            f"(第{attempt}/{max_attempts}次)"
        )
    
    async def emit_cancellation_available(
        self,
        session_id: str,
        can_cancel: bool,
        cancel_message: Optional[str] = None
    ):
        """
        发送取消可用性通知
        
        Args:
            session_id: 会话ID
            can_cancel: 是否可取消
            cancel_message: 取消提示消息
        """
        await self.emit(
            "progress_cancellation",
            session_id,
            data={
                "can_cancel": can_cancel,
                "cancel_message": cancel_message,
                "timestamp": datetime.now().isoformat()
            }
        )
