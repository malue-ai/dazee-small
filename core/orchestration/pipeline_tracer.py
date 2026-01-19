"""
E2EPipelineTracer - 端到端管道追踪器

职责：
- 追踪用户 Query 到最终 Response 的完整链路
- 记录每个阶段的输入、处理过程、输出
- 提供可观测性和调试能力
- 生成结构化的执行报告

设计原则：
- 每个阶段独立追踪，支持并行执行
- 日志级别可配置（DEBUG/INFO/WARNING/ERROR）
- 支持 JSON 格式导出
- 异常情况自动捕获和记录

使用方式：
    tracer = create_pipeline_tracer(session_id="xxx")
    
    with tracer.stage("intent_analysis") as stage:
        stage.input({"messages": messages})
        result = intent_analyzer.analyze(messages)
        stage.output({"intent": result})
    
    # 或者使用装饰器
    @tracer.trace("tool_execution")
    async def execute_tool(tool_name, params):
        ...
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from contextlib import contextmanager
import traceback

from logger import get_logger

logger = get_logger("pipeline_tracer")


class StageStatus(Enum):
    """阶段状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PipelineStage:
    """
    管道阶段记录
    
    包含一个处理阶段的完整信息：
    - 阶段名称和描述
    - 输入数据
    - 处理过程日志
    - 输出数据
    - 执行时间和状态
    """
    name: str
    description: str = ""
    status: StageStatus = StageStatus.PENDING
    
    # 输入输出
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    
    # 处理过程
    process_logs: List[str] = field(default_factory=list)
    
    # 时间记录
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    
    # 错误信息
    error: Optional[str] = None
    error_traceback: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def start(self) -> None:
        """开始执行"""
        self.status = StageStatus.RUNNING
        self.start_time = time.time()
        logger.info(f"📍 [{self.name}] 开始执行")
        if self.description:
            logger.info(f"   描述: {self.description}")
    
    def log(self, message: str) -> None:
        """记录处理过程"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"
        self.process_logs.append(log_entry)
        logger.debug(f"   [{self.name}] {message}")
    
    def set_input(self, data: Dict[str, Any]) -> None:
        """设置输入数据"""
        self.input_data = data
        # 打印简化的输入日志
        input_preview = self._preview_data(data)
        logger.info(f"   📥 输入: {input_preview}")
    
    def set_output(self, data: Dict[str, Any]) -> None:
        """设置输出数据"""
        self.output_data = data
        output_preview = self._preview_data(data)
        logger.info(f"   📤 输出: {output_preview}")
    
    def complete(self, output: Dict[str, Any] = None) -> None:
        """完成执行"""
        self.status = StageStatus.COMPLETED
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        
        if output:
            self.set_output(output)
        
        logger.info(f"✅ [{self.name}] 完成 (耗时: {self.duration_ms:.1f}ms)")
    
    def fail(self, error: Exception) -> None:
        """标记失败"""
        self.status = StageStatus.FAILED
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.error = str(error)
        self.error_traceback = traceback.format_exc()
        
        logger.error(f"❌ [{self.name}] 失败: {error}")
        logger.debug(f"   Traceback: {self.error_traceback}")
    
    def skip(self, reason: str = "") -> None:
        """跳过执行"""
        self.status = StageStatus.SKIPPED
        self.metadata["skip_reason"] = reason
        logger.info(f"⏭️ [{self.name}] 跳过: {reason}")
    
    def _preview_data(self, data: Dict[str, Any], max_length: int = 200) -> str:
        """生成数据预览"""
        try:
            json_str = json.dumps(data, ensure_ascii=False, default=str)
            if len(json_str) > max_length:
                return json_str[:max_length] + "..."
            return json_str
        except Exception:
            return str(data)[:max_length]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "input": self.input_data,
            "output": self.output_data,
            "process_logs": self.process_logs,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "metadata": self.metadata
        }


class E2EPipelineTracer:
    """
    端到端管道追踪器
    
    追踪完整的请求处理流程：
    1. 用户输入接收
    2. 意图分析
    3. 工具选择
    4. 代码生成（如果需要）
    5. 代码验证（如果需要）
    6. 工具/代码执行
    7. 结果验证
    8. 响应生成
    """
    
    # 标准阶段定义
    STAGE_DEFINITIONS = {
        "input_receive": "用户输入接收",
        "intent_analysis": "意图分析",
        "tool_selection": "工具选择",
        "code_generation": "代码生成",
        "code_validation": "代码语法验证",
        "tool_execution": "工具执行",
        "code_execution": "代码执行（E2B）",
        "result_validation": "执行结果验证",
        "response_generation": "响应生成",
        "error_recovery": "错误恢复"
    }
    
    def __init__(
        self,
        session_id: str,
        conversation_id: str = None,
        enable_detailed_log: bool = True
    ):
        """
        初始化追踪器
        
        Args:
            session_id: 会话ID
            conversation_id: 对话ID
            enable_detailed_log: 是否启用详细日志
        """
        self.session_id = session_id
        self.conversation_id = conversation_id
        self.enable_detailed_log = enable_detailed_log
        
        # 阶段记录
        self.stages: Dict[str, PipelineStage] = {}
        self.stage_order: List[str] = []  # 记录执行顺序
        
        # 全局追踪
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.user_query: str = ""
        self.final_response: str = ""
        
        # 统计信息
        self.stats = {
            "total_stages": 0,
            "completed_stages": 0,
            "failed_stages": 0,
            "skipped_stages": 0,
            "total_duration_ms": 0,
            "code_executions": 0,
            "tool_calls": 0
        }
        
        # 🆕 警告列表（用于记录流程异常但不影响执行的问题）
        self.warnings: List[str] = []
        
        logger.info(f"\n{'='*70}")
        logger.info(f"🚀 E2E Pipeline Tracer 启动")
        logger.info(f"   Session: {session_id}")
        logger.info(f"   Conversation: {conversation_id or 'N/A'}")
        logger.info(f"{'='*70}")
    
    def set_user_query(self, query: str) -> None:
        """设置用户查询"""
        self.user_query = query
        logger.info(f"\n📝 用户 Query:")
        logger.info(f"   \"{query[:200]}{'...' if len(query) > 200 else ''}\"")
    
    @contextmanager
    def stage(self, stage_name: str, description: str = None) -> Any:
        """
        阶段上下文管理器
        
        使用方式：
            with tracer.stage("intent_analysis") as stage:
                stage.set_input({"messages": messages})
                result = analyze(messages)
                stage.set_output({"intent": result})
        
        Args:
            stage_name: 阶段名称
            description: 阶段描述（如果不提供，使用默认定义）
        """
        # 使用默认描述或自定义描述
        if description is None:
            description = self.STAGE_DEFINITIONS.get(stage_name, stage_name)
        
        # 创建阶段
        stage = PipelineStage(name=stage_name, description=description)
        self.stages[stage_name] = stage
        self.stage_order.append(stage_name)
        self.stats["total_stages"] += 1
        
        stage.start()
        
        try:
            yield stage
            
            # 如果没有显式完成，自动完成
            if stage.status == StageStatus.RUNNING:
                stage.complete()
            
            self.stats["completed_stages"] += 1
            
        except Exception as e:
            stage.fail(e)
            self.stats["failed_stages"] += 1
            raise
    
    def create_stage(self, stage_name: str, description: str = None) -> PipelineStage:
        """
        手动创建阶段（不使用上下文管理器）
        
        Args:
            stage_name: 阶段名称
            description: 阶段描述
            
        Returns:
            PipelineStage 实例
        """
        if description is None:
            description = self.STAGE_DEFINITIONS.get(stage_name, stage_name)
        
        stage = PipelineStage(name=stage_name, description=description)
        self.stages[stage_name] = stage
        self.stage_order.append(stage_name)
        self.stats["total_stages"] += 1
        
        return stage
    
    def complete_stage(self, stage_name: str, output: Dict[str, Any] = None) -> None:
        """手动完成阶段"""
        if stage_name in self.stages:
            stage = self.stages[stage_name]
            stage.complete(output)
            self.stats["completed_stages"] += 1
    
    def fail_stage(self, stage_name: str, error: Exception) -> None:
        """手动标记阶段失败"""
        if stage_name in self.stages:
            stage = self.stages[stage_name]
            stage.fail(error)
            self.stats["failed_stages"] += 1
    
    def log_code_execution(self) -> None:
        """记录一次代码执行"""
        self.stats["code_executions"] += 1
    
    def log_tool_call(self, tool_name: str) -> None:
        """记录一次工具调用"""
        self.stats["tool_calls"] += 1
        logger.debug(f"📊 [Tracer] 工具调用 #{self.stats['tool_calls']}: {tool_name}")
    
    def add_warning(self, warning: str) -> None:
        """
        添加警告信息
        
        用于记录流程异常但不影响执行的问题，如:
        - Plan Creation 被跳过
        - 工具选择异常
        - 超时但继续执行
        
        Args:
            warning: 警告信息
        """
        self.warnings.append(warning)
        logger.warning(f"⚠️ [Tracer] {warning}")
    
    def set_final_response(self, response: str) -> None:
        """设置最终响应"""
        self.final_response = response
    
    def finish(self) -> None:
        """结束追踪"""
        self.end_time = time.time()
        self.stats["total_duration_ms"] = (self.end_time - self.start_time) * 1000
        
        # 打印执行摘要
        self._print_summary()
    
    def _print_summary(self) -> None:
        """打印执行摘要"""
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 E2E Pipeline 执行摘要")
        logger.info(f"{'='*70}")
        
        logger.info(f"\n📍 执行路径:")
        for i, stage_name in enumerate(self.stage_order, 1):
            stage = self.stages[stage_name]
            status_icon = {
                StageStatus.COMPLETED: "✅",
                StageStatus.FAILED: "❌",
                StageStatus.SKIPPED: "⏭️",
                StageStatus.RUNNING: "🔄",
                StageStatus.PENDING: "⏳"
            }.get(stage.status, "❓")
            
            duration = f"{stage.duration_ms:.1f}ms" if stage.duration_ms else "N/A"
            logger.info(f"   {i}. {status_icon} {stage.name}: {stage.description} ({duration})")
        
        logger.info(f"\n📈 统计信息:")
        logger.info(f"   - 总阶段数: {self.stats['total_stages']}")
        logger.info(f"   - 完成: {self.stats['completed_stages']}")
        logger.info(f"   - 失败: {self.stats['failed_stages']}")
        logger.info(f"   - 跳过: {self.stats['skipped_stages']}")
        logger.info(f"   - 代码执行次数: {self.stats['code_executions']}")
        logger.info(f"   - 工具调用次数: {self.stats['tool_calls']}")
        logger.info(f"   - 总耗时: {self.stats['total_duration_ms']:.1f}ms")
        
        # 🆕 显示警告信息
        if self.warnings:
            logger.warning(f"\n⚠️ 警告信息 ({len(self.warnings)} 条):")
            for i, warning in enumerate(self.warnings, 1):
                logger.warning(f"   {i}. {warning}")
        
        if self.final_response:
            # 响应预览增加到 1000 字符，避免截断过多
            response_preview = self.final_response[:1000] + "..." if len(self.final_response) > 1000 else self.final_response
            logger.info(f"\n📄 最终响应预览:")
            logger.info(f"   {response_preview}")
    
    def to_dict(self) -> Dict[str, Any]:
        """导出为字典格式"""
        return {
            "session_id": self.session_id,
            "conversation_id": self.conversation_id,
            "user_query": self.user_query,
            "final_response": self.final_response,
            "stages": {name: stage.to_dict() for name, stage in self.stages.items()},
            "stage_order": self.stage_order,
            "stats": self.stats,
            "warnings": self.warnings,  # 🆕 包含警告信息
            "start_time": datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None,
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None
        }
    
    def to_json(self, indent: int = 2) -> str:
        """导出为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)
    
    def get_failed_stages(self) -> List[PipelineStage]:
        """获取失败的阶段"""
        return [s for s in self.stages.values() if s.status == StageStatus.FAILED]
    
    def get_stage(self, stage_name: str) -> Optional[PipelineStage]:
        """获取指定阶段"""
        return self.stages.get(stage_name)


def create_pipeline_tracer(
    session_id: str,
    conversation_id: str = None,
    enable_detailed_log: bool = True
) -> E2EPipelineTracer:
    """
    创建管道追踪器
    
    Args:
        session_id: 会话ID
        conversation_id: 对话ID
        enable_detailed_log: 是否启用详细日志
        
    Returns:
        E2EPipelineTracer 实例
    """
    return E2EPipelineTracer(
        session_id=session_id,
        conversation_id=conversation_id,
        enable_detailed_log=enable_detailed_log
    )

